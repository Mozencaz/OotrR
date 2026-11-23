import _src_path  # noqa: F401  (src on sys.path)
import ctypes
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.tracker.game_overlay import ICONS, icon_name, overlay_model
from oot_rando.tracker import icon_extract, live_memory
from oot_rando.tracker.live_memory import (LiveGameData, LiveUnavailable, parse_bools, GAMEDATA_SLOT,
                                           SEQUENCE_IS_CHILDHOOD, HOOKSHOT_MAIN, MEM_COMMIT, emulator_layout,
                                           BOOL64_PROBE, BOOL64_TYPE, EMULATOR_EXES, LinuxProcessMemory,
                                           denied_message, exe_link_name, linux_emulator_pids, names_match,
                                           parse_exe_names, parse_maps, plain_name, ptrace_scope,
                                           readable_regions, MemfdWindows, is_guest_memfd, memfd_mappings,
                                           HOST_BASE, port_layout, linux_port_pids)


def gamedata_image(bools, size=16, gamedata_slot=GAMEDATA_SLOT, at=0, bool64=None, bool64_at=BOOL64_TYPE):
    """Guest memory as Hookshot lays out GameDataMgr: {guest address: bytes}.

    ``bool64``: {key: value} of Bool64bitKey records, written in the given order at ``bool64_at``."""
    table = bytearray(size * 8)
    entries = bytearray(len(bools) * 24)
    for index, (key, value) in enumerate(bools.items()):
        slot = key % size
        while struct.unpack_from('<I', table, slot * 8)[0]:
            slot = (slot + 1) % size
        struct.pack_into('<II', table, slot * 8, key, index)
        entries[index * 24 + 22] = int(value)
    holder, manager, table_at, entries_at = (at + offset for offset in (0x1000, 0x2000, 0x3000, 0x5000))
    header = bytearray(48 if bool64 is None else 0xD10)
    struct.pack_into('<I', header, 16, len(bools))
    struct.pack_into('<Q', header, 24, entries_at)
    struct.pack_into('<Q', header, 32, table_at)
    struct.pack_into('<I', header, 44, size)
    image = {gamedata_slot: struct.pack('<Q', holder), holder: struct.pack('<Q', manager),
             manager: bytes(header), table_at: bytes(table), entries_at: bytes(entries)}
    if bool64 is not None:
        records_at = at + 0x8000
        records = b''.join(struct.pack('<QIB3x', key, 0, value) for key, value in bool64.items())
        struct.pack_into('<IIQ', header, bool64_at, len(bool64), 0, records_at)
        image[manager], image[records_at] = bytes(header), records
    return image


class FakeMemory:
    def __init__(self, regions):
        self.regions = regions

    def attach(self):
        pass

    def close(self):
        pass

    def read(self, guest, size):
        for start, data in self.regions.items():
            if start <= guest and guest + size <= start + len(data):
                return data[guest - start:guest - start + size]
        raise LiveUnavailable(hex(guest))


class LiveGameDataTests(unittest.TestCase):
    def test_reads_bools_through_the_hash_table(self):
        bools = {SEQUENCE_IS_CHILDHOOD: True, 17: False, 33: True}   # 17 and 33 collide (mod 16)
        snapshot = LiveGameData(FakeMemory(gamedata_image(bools))).snapshot()
        self.assertEqual(snapshot['bool'], bools)

    def test_rejects_a_table_without_known_keys(self):
        with self.assertRaises(LiveUnavailable):
            LiveGameData(FakeMemory(gamedata_image({5: True}))).snapshot()

    def test_not_loaded_yet(self):
        regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True})
        regions[0x1000] = struct.pack('<Q', 0)
        with self.assertRaises(LiveUnavailable):
            LiveGameData(FakeMemory(regions)).snapshot()

    def test_reads_bool64_flags(self):
        bool64 = {5: 1, BOOL64_PROBE - 1: 0, BOOL64_PROBE: 1, BOOL64_PROBE + 7: 1}
        snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64=bool64))).snapshot()
        self.assertTrue(snapshot['bool64_complete'])
        self.assertEqual(snapshot['bool64'], {5: True, BOOL64_PROBE: True, BOOL64_PROBE + 7: True})

    def test_seed_keys_appended_after_the_sorted_ones(self):
        # A seed's GameData adds Bool64bitKey entries: the game appends them, unsorted.
        bool64 = {5: 0, BOOL64_PROBE: 0, BOOL64_PROBE + 9: 1, 7: 1, 3: 0, 6: 1}
        snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64=bool64))).snapshot()
        self.assertTrue(snapshot['bool64_complete'])
        self.assertEqual(snapshot['bool64'], {BOOL64_PROBE + 9: True, 7: True, 6: True})

    def test_finds_bool64_flags_moved_in_the_manager(self):
        regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64={BOOL64_PROBE: 0, BOOL64_PROBE + 1: 1},
                                 bool64_at=BOOL64_TYPE + 0x30)
        snapshot = LiveGameData(FakeMemory(regions)).snapshot()
        self.assertEqual(snapshot['bool64'], {BOOL64_PROBE + 1: True})

    def test_bool64_falls_back_to_the_save(self):
        cases = {'unreadable': None, 'no probe key': {1: 1, 2: 1},
                 'probe outside the sorted part': {5: 1, 2: 1, BOOL64_PROBE: 1}}
        for name, bool64 in cases.items():
            with self.subTest(name):
                snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True},
                                                                  bool64=bool64))).snapshot()
                self.assertTrue(snapshot['bool'][SEQUENCE_IS_CHILDHOOD])
                self.assertFalse(snapshot['bool64_complete'])
                self.assertNotIn('bool64', snapshot)
                self.assertIn('Bool64bitKey', snapshot['bool64_status'])

    def test_parse_skips_out_of_range_indices(self):
        table = struct.pack('<IIII', 7, 0, 9, 5)
        self.assertEqual(parse_bools(table, bytes(24), 1), {7: False})


class EmulatorLayoutTests(unittest.TestCase):
    """An emulator maps guest memory at a random host base and loads main at a random page."""
    BASE, MAIN = 0x5A3400000000, 0x80347000

    def host_memory(self, loaded=True):
        slot = self.MAIN + GAMEDATA_SLOT - HOOKSHOT_MAIN
        guest = gamedata_image({SEQUENCE_IS_CHILDHOOD: True, 17: False}, gamedata_slot=slot, at=0x90000000)
        if not loaded:
            guest[slot] = struct.pack('<Q', 0)
        regions = {self.BASE + address: data for address, data in guest.items()}
        regions[self.BASE + self.MAIN] = struct.pack('<II', 1, 0x40) + bytes(56) + b'MOD0'
        reader = FakeMemory(regions)

        def read(address, size):
            try:
                return reader.read(address, size)
            except LiveUnavailable:
                return None
        listing = [(self.BASE + self.MAIN, 0x1000, MEM_COMMIT), (self.BASE + 0x90000000, 0x10000, MEM_COMMIT)]
        return listing, read, slot

    def test_finds_base_and_slot(self):
        listing, read, slot = self.host_memory()
        self.assertEqual(emulator_layout(listing, read), (self.BASE, slot))

    def test_game_data_not_loaded(self):
        listing, read, _ = self.host_memory(loaded=False)
        self.assertIsNone(emulator_layout(listing, read))

    def test_finds_base_and_slot_from_linux_maps(self):
        # Ryuchii on Linux: guest pages are mappings of its memfd inside one reserved window.
        listing, read, slot = self.host_memory()
        lines = [f'{self.BASE:x}-{self.BASE + self.MAIN:x} ---p 00000000 00:00 0']
        lines += [f'{start:x}-{start + size:x} rw-s 00012000 00:01 4321    /memfd:HostMemory (deleted)'
                  for start, size, _ in listing]
        self.assertEqual(emulator_layout(readable_regions(parse_maps('\n'.join(lines))), read), (self.BASE, slot))


class LinuxProcessTests(unittest.TestCase):
    """Linux process access, from fake /proc text and folders (the syscalls run in the Linux CI)."""
    MAPS = (
        '55d0c0a00000-55d0c0a21000 r--p 00000000 08:02 1234                       /usr/bin/ryuchii\n'
        '7f0000000000-7f0000001000 rw-s 00012000 00:01 4321                       /memfd:HostMemory (deleted)\n'
        '7f0000001000-7f0000002000 ---p 00000000 00:00 0 \n'
        '7f0000002000-7f0000003000 rw-s 00000000 00:0e 99                         /dev/dri/renderD128\n'
        '7f0000003000-7f0000004000 rw-s 00000000 00:19 98                         /dev/shm/eden_mem\n'
        '7f0000005000-7f0000006000 rw-p 00000000 00:00 0 \n'
        '7ffd1c3fe000-7ffd1c402000 r--p 00000000 00:00 0                          [vvar]\n'
        '7ffd1c402000-7ffd1c404000 r-xp 00000000 00:00 0                          [vdso]\n'
        'ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]\n')

    def fake_proc(self, processes, scope=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for pid, comm in processes.items():
            (root / str(pid)).mkdir()
            (root / str(pid) / 'comm').write_text(comm + '\n', encoding='utf-8')
            (root / str(pid) / 'maps').write_text(self.MAPS, encoding='utf-8')
        (root / 'self').mkdir()
        if scope is not None:
            (root / 'sys' / 'kernel' / 'yama').mkdir(parents=True)
            (root / 'sys' / 'kernel' / 'yama' / 'ptrace_scope').write_text(f'{scope}\n', encoding='ascii')
        return str(root)

    def test_parses_maps(self):
        rows = parse_maps(self.MAPS)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[1], (0x7F0000000000, 0x1000, 'rw-s', '/memfd:HostMemory (deleted)'))
        self.assertEqual(rows[2], (0x7F0000001000, 0x1000, '---p', ''))

    def test_keeps_readable_mappings_only(self):
        regions = readable_regions(parse_maps(self.MAPS))
        self.assertEqual([start for start, _, _ in regions],
                         [0x55D0C0A00000, 0x7F0000000000, 0x7F0000003000, 0x7F0000005000, 0x7FFD1C402000])
        self.assertEqual({state for _, _, state in regions}, {MEM_COMMIT})

    def test_names_with_or_without_exe(self):
        self.assertEqual(plain_name('C:\\Emu\\Ryuchii.EXE'), 'ryuchii')
        self.assertEqual(plain_name('ryuchii'), 'ryuchii')
        self.assertEqual(exe_link_name('/home/deck/Ryuchii/usr/bin/ryuchii (deleted)'), 'ryuchii')
        self.assertTrue(names_match({'ryuchii'}, {plain_name(name) for name in EMULATOR_EXES}))
        # /proc/<pid>/comm keeps 15 characters of a longer name.
        self.assertTrue(names_match({'ryuchii-green-h'}, {'ryuchii-green-hat-boy'}))
        self.assertFalse(names_match({'ryuchii-green'}, {'ryuchii-green-hat-boy'}))
        self.assertFalse(names_match({'bash', ''}, {'ryuchii'}))

    def test_finds_emulators_by_comm(self):
        proc = self.fake_proc({100: 'ryuchii', 200: 'bash', 300: 'MyEmu', 400: 'ryuchii'})
        emulators = EMULATOR_EXES | parse_exe_names('MyEmu.exe')
        self.assertEqual(linux_emulator_pids(emulators, proc, own=400), [100, 300])
        self.assertEqual(linux_emulator_pids(EMULATOR_EXES, proc + '-missing'), [])

    def test_ptrace_scope(self):
        self.assertEqual(ptrace_scope(self.fake_proc({}, scope=1)), 1)
        self.assertIsNone(ptrace_scope(self.fake_proc({})))

    def test_denied_messages_name_the_value_and_the_fix(self):
        self.assertIn('PR_SET_PTRACER_ANY', denied_message(1))
        for scope in (0, 1, 2, 3):
            self.assertIn(f'ptrace_scope is {scope}', denied_message(scope))
        self.assertNotIn('ptrace_scope', denied_message(None))

    def test_refused_memory_reports_ptrace_scope(self):
        class Refused(LinuxProcessMemory):
            def _open(self, pid, flags):
                raise PermissionError(13, 'Permission denied')
        memory = Refused(self.fake_proc({100: 'ryuchii'}, scope=1))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES):
            with self.assertRaises(LiveUnavailable) as caught:
                LiveGameData(memory).snapshot()
        self.assertIn('ptrace_scope is 1', str(caught.exception))
        self.assertIn('PR_SET_PTRACER', str(caught.exception))
        with self.assertRaises(LiveUnavailable) as again:   # before the next scan: the same reason
            LiveGameData(memory).snapshot()
        self.assertEqual(str(again.exception), str(caught.exception))

    def test_no_emulator_running(self):
        memory = LinuxProcessMemory(self.fake_proc({200: 'bash'}))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES):
            with self.assertRaises(LiveUnavailable) as caught:
                memory.attach()
        self.assertEqual(str(caught.exception), 'game not running')

    def test_process_memory_of_this_system(self):
        if os.name == 'nt':
            self.assertIsInstance(live_memory.process_memory(), live_memory.ProcessMemory)
        elif sys.platform.startswith('linux'):
            self.assertIsInstance(live_memory.process_memory(), LinuxProcessMemory)
        self.assertEqual(live_memory.supported(), os.name == 'nt' or sys.platform.startswith('linux'))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'reads /proc/self/mem')
    def test_reads_and_writes_this_process(self):
        buffer = ctypes.create_string_buffer(b'ootrr-live', 16)
        address = ctypes.addressof(buffer)
        rows = readable_regions(parse_maps(Path('/proc/self/maps').read_text(encoding='utf-8')))
        self.assertTrue(any(start <= address < start + size for start, size, _ in rows))
        memory = LinuxProcessMemory()
        memory.fd, memory.pid, memory.base = os.open('/proc/self/mem', os.O_RDONLY), 'self', 0
        try:
            self.assertEqual(memory.read(address, 10), b'ootrr-live')
            memory.write(address, b'O')
            self.assertEqual(buffer.raw[:10], b'Ootrr-live')
            with self.assertRaises(LiveUnavailable):
                memory.read(0, 8)   # unmapped
        finally:
            memory.close()


class MemfdTests(unittest.TestCase):
    """The guest memory file route, which kernel.yama.ptrace_scope 1 allows."""
    BASE, MAIN, DATA = 0x7EE300000000, 0x80347000, 0x90000000
    # The rows of a Steam Deck's maps (round 3b) look like these: page-sized protection changes, one inode.
    MAPS = (
        '7ee397e00000-7ee397e17000 ---s 21000000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee397e17000-7ee397e18000 rw-s 21017000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee397e18000-7ee397e23000 ---s 21018000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee398000000-7ee398001000 rw-s 00000000 00:01 1369                       /memfd:HostMemory\n'
        '7ee398001000-7ee398002000 rw-s 00004000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee398002000-7ee398003000 rw-s 00000000 00:01 77                         /memfd:Other\n'
        '7ee398003000-7ee398004000 rw-p 00000000 00:00 0 \n')

    def test_link_names(self):
        self.assertTrue(is_guest_memfd('/memfd:HostMemory (deleted)'))
        self.assertTrue(is_guest_memfd('/memfd:HostMemory'))
        self.assertTrue(is_guest_memfd('/memfd:longshot-guest (deleted)'))
        self.assertFalse(is_guest_memfd('/memfd:HostMemoryX'))
        self.assertFalse(is_guest_memfd('/memfd:pipewire-memfd:flags=0x0000000f,type=2,size=2312 (deleted)'))
        self.assertFalse(is_guest_memfd('/dev/shm/HostMemory'))

    def test_mappings_of_any_protection(self):
        rows = memfd_mappings(self.MAPS)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], (0x7EE397E00000, 0x17000, 0x21000000, 1369))
        self.assertEqual(rows[4], (0x7EE398001000, 0x1000, 0x4000, 1369))

    def test_windows_join_only_continuous_mappings(self):
        windows = MemfdWindows(memfd_mappings(self.MAPS))
        self.assertEqual(windows.windows, [(0x7EE397E00000, 0x23000, 0x21000000), (0x7EE398000000, 0x1000, 0),
                                           (0x7EE398001000, 0x1000, 0x4000)])
        self.assertEqual(windows.pieces(0x7EE397E16FF8, 16), [(0x21016FF8, 16)])   # across a protection change
        self.assertEqual(windows.pieces(0x7EE398000FFC, 8), [(0xFFC, 4), (0x4000, 4)])
        self.assertIsNone(windows.pieces(0x7EE397E22FFC, 8))   # runs past the mapping
        self.assertIsNone(windows.pieces(0x7EE397DFFFFF, 2))   # starts before it
        self.assertIsNone(windows.pieces(0x7EE398002000, 1))
        self.assertEqual(windows.pieces(0x7EE398000000, 0), [])

    def guest_file(self, folder):
        """A guest memory file and its maps text: main, the GameData slot (a protected page) and the data."""
        slot = self.MAIN + GAMEDATA_SLOT - HOOKSHOT_MAIN
        image = gamedata_image({SEQUENCE_IS_CHILDHOOD: True, 17: False}, gamedata_slot=slot, at=self.DATA)
        image[self.MAIN] = struct.pack('<II', 1, 0x40) + bytes(56) + b'MOD0'
        # guest page -> (file offset, size, protection); the file pages are not in guest order
        layout = {self.MAIN: (0x20000, 0x1000, 'rw-s'), slot & ~0xFFF: (0x0, 0x1000, '---s'),
                  self.DATA: (0x1000, 0x10000, 'rw-s')}
        content = bytearray(0x21000)
        for guest, data in image.items():
            page = max(start for start in layout if start <= guest)
            offset = layout[page][0] + guest - page
            content[offset:offset + len(data)] = data
        path = Path(folder, 'HostMemory')
        path.write_bytes(bytes(content))
        inode = os.stat(path).st_ino
        lines = [f'{self.BASE + page:x}-{self.BASE + page + size:x} {protection} {offset:08x} 00:01 {inode}'
                 f'    /memfd:HostMemory (deleted)' for page, (offset, size, protection) in sorted(layout.items())]
        return path, '\n'.join(lines) + '\n', slot

    def test_attaches_and_writes_through_the_file(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path, maps, slot = self.guest_file(folder.name)
        proc = Path(folder.name, 'proc')
        (proc / '100').mkdir(parents=True)
        (proc / '100' / 'comm').write_text('ryuchii\n', encoding='utf-8')
        (proc / '100' / 'maps').write_text(maps, encoding='utf-8')

        def pread(fd, size, offset):   # os.pread is POSIX only; the file is read by path
            with open(path, 'rb') as file:
                file.seek(offset)
                return file.read(size)

        def pwrite(fd, data, offset):
            with open(path, 'r+b') as file:
                file.seek(offset)
                return file.write(data)

        class Memfd(LinuxProcessMemory):
            def _guest_memfds(self, pid):
                return [str(path)]

            def _open(self, pid, flags):
                raise AssertionError('/proc/<pid>/mem opened')

        memory = Memfd(str(proc))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES), \
                mock.patch.object(live_memory.os, 'pread', pread, create=True), \
                mock.patch.object(live_memory.os, 'pwrite', pwrite, create=True):
            try:
                snapshot = LiveGameData(memory).snapshot()
                self.assertEqual((memory.base, memory.slot), (self.BASE, slot))
                self.assertTrue(snapshot['bool'][SEQUENCE_IS_CHILDHOOD])
                memory.write(self.DATA + 0x5000 + 24 + 22, b'\x01')   # key 17's value byte
                self.assertTrue(LiveGameData(memory).snapshot()['bool'][17])
                with self.assertRaises(LiveUnavailable):
                    memory.read(self.DATA + 0x20000, 8)   # not mapped, even after reading maps again
            finally:
                memory.close()

    def port_proc(self, folder):
        """Longshot's Linux build as the round of 18/11 saw it: the game, its crash watcher (same
        exe, no guest window), and a sparse guest file mapped at HOST_BASE from offset 0."""
        game = Path(folder, 'Longshot')
        (game / 'bin').mkdir(parents=True)
        (game / 'bin' / 'longshot').touch()
        (game / 'image.bin').touch()
        (game / 'romfs').mkdir()
        data = 0x90000000
        image = gamedata_image({SEQUENCE_IS_CHILDHOOD: True, 17: False}, at=data)
        path = Path(folder, 'longshot-guest')
        with open(path, 'wb') as file:
            for guest, raw in image.items():
                file.seek(guest)
                file.write(raw)
        inode = os.stat(path).st_ino
        proc = Path(folder, 'proc')
        maps = {100: f'{HOST_BASE:x}-{HOST_BASE + 0x8000000000:x} rw-s 00000000 00:01 {inode}'
                     f'    /memfd:longshot-guest (deleted)\n'
                     '7f9279a89000-7f9279a8d000 r--p 00000000 00:01 7404    /memfd:kwin-dmabuf-feedback-table (deleted)\n',
                200: '7f9279a89000-7f9279a8d000 r--p 00000000 00:01 7404    /dev/zero\n'}
        for pid, text in maps.items():
            (proc / str(pid)).mkdir(parents=True)
            (proc / str(pid) / 'comm').write_text('longshot\n', encoding='utf-8')
            (proc / str(pid) / 'maps').write_text(text, encoding='utf-8')
            os.symlink(game / 'bin' / 'longshot', proc / str(pid) / 'exe')
        return proc, path, data, game

    @unittest.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'POSIX symlinks')
    def test_attaches_to_native_longshot_through_its_guest_file(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        proc, path, data, game = self.port_proc(folder.name)
        self.assertEqual(linux_port_pids(str(proc)), [100, 200])

        def pread(fd, size, offset):
            with open(path, 'rb') as file:
                file.seek(offset)
                return file.read(size)

        def pwrite(fd, raw, offset):
            with open(path, 'r+b') as file:
                file.seek(offset)
                return file.write(raw)

        class Memfd(LinuxProcessMemory):
            def _guest_memfds(self, pid):
                return [str(path)] if pid == 100 else []

            def _open(self, pid, flags):
                raise AssertionError('/proc/<pid>/mem opened')

        memory = Memfd(str(proc))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES), \
                mock.patch.object(live_memory.os, 'pread', pread, create=True), \
                mock.patch.object(live_memory.os, 'pwrite', pwrite, create=True):
            try:
                snapshot = LiveGameData(memory).snapshot()
                self.assertEqual((memory.pid, memory.base, memory.slot), (100, HOST_BASE, GAMEDATA_SLOT))
                self.assertEqual(Path(memory.image), game / 'bin' / 'longshot')
                self.assertTrue(snapshot['bool'][SEQUENCE_IS_CHILDHOOD])
                memory.write(data + 0x5000 + 24 + 22, b'\x01')   # key 17's value byte
                self.assertTrue(LiveGameData(memory).snapshot()['bool'][17])
            finally:
                memory.close()
            self.assertEqual(memory.image, '')

    @unittest.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'POSIX symlinks')
    def test_a_port_without_guest_window_is_not_read(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        proc, _, _, _ = self.port_proc(folder.name)

        class NoFile(LinuxProcessMemory):
            def _guest_memfds(self, pid):
                return []

            def _open(self, pid, flags):
                if pid == 200:
                    raise AssertionError('the crash watcher was opened')
                raise PermissionError

        memory = NoFile(str(proc))
        with self.assertRaises(LiveUnavailable) as caught:
            memory.attach()
        self.assertIn('Linux refused', str(caught.exception))   # the game (100) has a window, no readable file

    def test_port_layout(self):
        image = gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, at=0x90000000)
        memory = FakeMemory({HOST_BASE + guest: raw for guest, raw in image.items()})

        def read(host, size):
            try:
                return memory.read(host, size)
            except LiveUnavailable:
                return None
        self.assertEqual(port_layout(read), (HOST_BASE, GAMEDATA_SLOT))
        self.assertIsNone(port_layout(lambda host, size: None))

    @unittest.skipUnless(sys.platform.startswith('linux') and hasattr(os, 'memfd_create'), 'a Linux memfd')
    def test_reads_and_writes_a_memfd_of_this_process(self):
        import mmap
        fd = os.memfd_create('HostMemory', 0)
        try:
            os.ftruncate(fd, 0x3000)
            os.pwrite(fd, b'ootrr-live', 0x2000)
            view = mmap.mmap(fd, 0x1000, offset=0x2000)
            pointer = ctypes.c_char.from_buffer(view)
            address = ctypes.addressof(pointer)
            memory = LinuxProcessMemory()
            paths = memory._guest_memfds(os.getpid())
            self.assertTrue(paths)
            mine = [p for p in paths if os.stat(p).st_ino == os.fstat(fd).st_ino]
            self.assertTrue(mine)   # two entries: mmap keeps its own duplicate of the descriptor
            memory.fd, memory.pid, memory.base, memory.memfd = os.open(mine[0], os.O_RDONLY), os.getpid(), 0, mine[0]
            memory.inode = os.fstat(fd).st_ino
            memory.windows = MemfdWindows([row for row in memfd_mappings(Path('/proc/self/maps').read_text())
                                           if row[3] == memory.inode])
            self.assertEqual(memory.read(address, 10), b'ootrr-live')
            memory.write(address, b'O')
            self.assertEqual(view[:10], b'Ootrr-live')
            memory.close()
            del pointer
            view.close()
        finally:
            os.close(fd)


class FakeLive:
    def __init__(self, bools=None, error=None, bool64=None):
        self.bools, self.error, self.bool64 = bools, error, bool64

    def snapshot(self):
        if self.error:
            raise LiveUnavailable(self.error)
        if self.bool64 is None:
            return {'bool': self.bools, 'bool64_complete': False, 'sha256': 'x'}
        return {'bool': self.bools, 'bool64': self.bool64, 'bool64_complete': True, 'sha256': 'x'}


class MergeLiveTests(unittest.TestCase):
    def session(self, live):
        session = TrackerSession.__new__(TrackerSession)
        session.live, session.live_status = live, ''
        return session

    def test_live_overrides_save_for_this_seed_only(self):
        snapshot = {'bool': {1: False, 2: True}}
        self.assertEqual(self.session(FakeLive({99: True, 1: True}))._merge_live(snapshot, 99), 'x')
        self.assertEqual(snapshot['bool'], {1: True, 2: True, 99: True})

    def test_live_bool64_replaces_the_save_s(self):
        snapshot = {'bool': {}, 'bool64': {7: True}, 'bool64_complete': True}
        session = self.session(FakeLive({99: True}, bool64={8: True}))
        session._merge_live(snapshot, 99)
        self.assertEqual(snapshot['bool64'], {8: True})
        self.assertTrue(session.live_bool64)

    def test_unreadable_bool64_keeps_the_save_s(self):
        snapshot = {'bool': {}, 'bool64': {7: True}, 'bool64_complete': True}
        session = self.session(FakeLive({99: True}))
        session._merge_live(snapshot, 99)
        self.assertEqual(snapshot['bool64'], {7: True})
        self.assertFalse(session.live_bool64)

    def test_other_game_keeps_the_save(self):
        session = self.session(FakeLive({99: False, 1: True}))
        snapshot = {'bool': {1: False}}
        self.assertIsNone(session._merge_live(snapshot, 99))
        self.assertEqual(snapshot['bool'], {1: False})
        self.assertIn('seed', session.live_status)

    def test_unavailable_game_keeps_the_save(self):
        session = self.session(FakeLive(error='game not running'))
        self.assertIsNone(session._merge_live({'bool': {}}, 99))
        self.assertEqual(session.live_status, 'game not running')


class IconTests(unittest.TestCase):
    def test_deblock_inverts_the_gob_layout(self):
        width, height, log2 = 9, 20, 1   # partial GOB column and two GOB rows
        gob_height = 1 << log2
        width_gobs = -(-width * 16 // 64)
        raw = bytearray(512 * gob_height * width_gobs * 2)
        for y in range(height):
            for x in range(width):
                address = ((y // (8 * gob_height)) * 512 * gob_height * width_gobs
                           + ((y % (8 * gob_height)) // 8) * 512 + (x // 4) * 512 * gob_height
                           + (y & 1) * 16 + ((y >> 1) & 1) * 32 + (x & 1) * 64 + ((y >> 2) & 1) * 128
                           + ((x >> 1) & 1) * 256)
                raw[address:address + 16] = bytes([x, y]) * 8
        linear = icon_extract.deblock_linear(bytes(raw), width, height, log2)
        for y in range(height):
            for x in range(width):
                at = (y * width + x) * 16
                self.assertEqual(linear[at:at + 2], bytes([x, y]))

    def test_icon_levels(self):
        self.assertEqual(icon_name('Progressive Hookshot', 0), 'Item_Hookshot')
        self.assertEqual(icon_name('Progressive Hookshot', 2), 'Item_Longshot')
        self.assertEqual(icon_name('Progressive Hookshot', 7), 'Item_Longshot')
        self.assertIsNone(icon_name('Forest Medallion', 1))

    def test_every_grid_item_has_an_icon_or_shape(self):
        model = overlay_model({}, set(), set(), [], {})
        for row in model['cells']:
            for cell in row:
                self.assertTrue(cell['icon'] or cell['shape'], cell['item'])

    def test_icon_names_exist_in_the_romfs_when_installed(self):
        hookshot = os.environ.get('OOT_HOOKSHOT_DIR')
        folder = Path(hookshot or '.') / 'romfs' / 'UI' / 'Tex' / 'Icon'
        if not hookshot or not folder.is_dir():
            self.skipTest('OOT_HOOKSHOT_DIR (Hookshot folder with romfs) not set')
        for names in ICONS.values():
            for name in names:
                self.assertTrue((folder / f'{name}.bntx.zs').is_file(), name)


if __name__ == '__main__':
    unittest.main()
