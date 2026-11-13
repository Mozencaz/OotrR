import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest
from pathlib import Path

from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.tracker.game_overlay import ICONS, icon_name, overlay_model
from oot_rando.tracker import icon_extract
from oot_rando.tracker.live_memory import (LiveGameData, LiveUnavailable, parse_bools, GAMEDATA_SLOT,
                                           SEQUENCE_IS_CHILDHOOD, HOOKSHOT_MAIN, MEM_COMMIT, emulator_layout,
                                           BOOL64_PROBE, BOOL64_TYPE)


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

    def test_finds_bool64_flags_moved_in_the_manager(self):
        regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64={BOOL64_PROBE: 0, BOOL64_PROBE + 1: 1},
                                 bool64_at=BOOL64_TYPE + 0x30)
        snapshot = LiveGameData(FakeMemory(regions)).snapshot()
        self.assertEqual(snapshot['bool64'], {BOOL64_PROBE + 1: True})

    def test_bool64_falls_back_to_the_save(self):
        cases = {'unreadable': None, 'no probe key': {1: 1, 2: 1}, 'not sorted': {BOOL64_PROBE: 1, 3: 1}}
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
