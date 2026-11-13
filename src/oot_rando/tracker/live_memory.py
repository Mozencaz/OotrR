"""Real-time GameData bools from a running game: Hookshot, or a yuzu-family emulator (Windows).

Layout, as Hookshot v2.1.0's own cheat menu reads it (tools/host/hos_main.c, oot_gamedata_set_bool):
- guest memory is one window at the fixed host address A64_HOST_BASE = 0x100000000000
  (rt/a64.h; nx2 builds use 64-bit guest addresses: host = base + guest);
- the guest pointer at OOT_GAMEDATA_SLOT (0x84c9e180) points to a holder whose first word is
  the GameDataMgr;
- GameDataMgr+32: (hash u32, index u32) open-addressing table, its size u32 at +44, probe
  start hash % size, key 0 = empty slot;
- GameDataMgr+24: Bool entries, 24 bytes each, value byte at +22; their count u32 at +16.

Emulators (Eden, Lichii, yuzu and forks) run the same game code, so the structures are the
same; only two addresses differ, and change at every boot:
- guest memory is a window of the emulator process ("fastmem"): host = base + guest;
- the main module is loaded at a random page near 0x80000000 (Hookshot keeps it at
  0x80020000); the GameData slot sits at GAMEDATA_SLOT - HOOKSHOT_MAIN from its start.
``emulator_layout`` finds the modules by their MOD0 header in the process, then tries the
possible guest addresses of each, keeping the one where the slot leads to a GameData table
holding a known key.

Bool64bitKey flags (keyed by a placed actor's u64 instance hash: Gold Skulltulas, heart
containers, free-standing items...) are not in Hookshot's menu. Their layout comes from the
sloperina practice menu (PracticeROM/sloperina, docs/FINDINGS.md "Bool64bitKey", update
v131072): a u32 count at GameDataMgr+0xC58 and, at the pointer in +0xC60, records sorted by
key, 16 bytes each (u64 key, u32 reset type, u8 value at +0xC). The game binary-searches them
for its Gold Skulltula count. When they cannot be read they keep coming from progress.sav.
The only write is ``LiveGameData.set_bool`` (the Archipelago
client's reception signal, ``patching.ap_mailbox``): one value byte, as the cheat menu does.
"""
import bisect
import ctypes
import hashlib
import struct
import time
from pathlib import Path

HOST_BASE = 0x100000000000
GAMEDATA_SLOT = 0x84C9E180
SEQUENCE_IS_CHILDHOOD = 0xCEA220D3   # murmur3('Sequence_IsChildhood'), always present
MAX_TABLE, MAX_BOOLS = 1 << 20, 1 << 20
BOOL64_TYPE = 0xC58                       # GameDataMgr offset of the Bool64bitKey entry (v131072)
BOOL64_SCAN = range(0xC08, 0xD08, 8)      # other offsets tried if the game's layout moved
BOOL64_RECORD = 16
BOOL64_PROBE = 0xECDC46B409ED7D38         # the game's first Gold Skulltula: every save knows it
GAME_EXE = 'hookshot.exe'
EMULATOR_EXES = {'lichii.exe', 'ryuchii.exe', 'eden.exe', 'yuzu.exe', 'suyu.exe', 'citron.exe', 'sudachi.exe'}
EXTRA_EMULATORS_KEY = 'extra_emulators'   # gui_state.json: executables the player added (Setup page)


def parse_exe_names(text):
    """Executable names from a free list (commas, semicolons or lines): lower case, '.exe' added."""
    from pathlib import PureWindowsPath
    names = set()
    for part in text.replace(';', ',').replace('\n', ',').split(','):
        name = PureWindowsPath(part.strip().strip('"')).name.lower()
        if name:
            names.add(name if name.endswith('.exe') else name + '.exe')
    return names


_extra_emulators = None   # set by the application; None: read once from its saved state


def set_extra_emulators(text):
    """Executables the player listed (Setup page), used by the next process scan."""
    global _extra_emulators
    _extra_emulators = parse_exe_names(text or '')


def emulator_exes():
    """Known yuzu-family executables plus the ones the player listed in the application."""
    if _extra_emulators is None:
        import json
        from oot_rando.paths import state_dir
        try:
            extra = json.loads((state_dir() / 'gui_state.json').read_text(encoding='utf-8')).get(EXTRA_EMULATORS_KEY)
        except (OSError, ValueError, AttributeError):
            extra = ''
        set_extra_emulators(extra if isinstance(extra, str) else '')
    return EMULATOR_EXES | _extra_emulators


HOOKSHOT_MAIN = 0x80020000                 # where Hookshot keeps the main module
MEM_COMMIT = 0x1000
MAX_MODULE = 0x10000000                              # MOD0 may sit past the first region (main: +0x3c4705c)
GUEST_CODE = range(0x80000000, 0x84000000, 0x1000)   # where emulators load the main module


class LiveUnavailable(Exception):
    pass


def parse_bools(table, entries, count):
    """{hash: bool} from the raw hash table and Bool entries (pure: tested without a game)."""
    result = {}
    for slot in range(len(table) // 8):
        key, index = struct.unpack_from('<II', table, slot * 8)
        if key and index < count:
            result[key] = bool(entries[index * 24 + 22] & 1)
    return result


def parse_bool64(records, count):
    """{key: True} of the set Bool64bitKey flags, or None when ``records`` is not the sorted
    table that knows :data:`BOOL64_PROBE` (pure: tested without a game)."""
    keys, flags = [], {}
    for index in range(count):
        key, value = struct.unpack_from('<Q4xB', records, index * BOOL64_RECORD)
        if keys and key <= keys[-1]:
            return None
        keys.append(key)
        if value == 1:
            flags[key] = True
    position = bisect.bisect_left(keys, BOOL64_PROBE)
    return flags if position < len(keys) and keys[position] == BOOL64_PROBE else None


def valid_slot(read, slot):
    """True when guest ``slot`` leads to a GameData manager whose table knows a vanilla key.

    ``read(guest, size)`` returns bytes or None. Pure: tested without a game.
    """
    def pointer(address):
        raw = read(address, 8)
        value = struct.unpack('<Q', raw)[0] if raw else 0
        return value if 0x10000 <= value < 1 << 48 and not value & 7 else 0

    holder = pointer(slot)
    manager = pointer(holder) if holder else 0
    header = read(manager, 48) if manager else None
    if not header:
        return False
    count, size = struct.unpack_from('<I', header, 16)[0], struct.unpack_from('<I', header, 44)[0]
    entries, table = struct.unpack_from('<QQ', header, 24)
    if not (table and entries and 0 < size <= MAX_TABLE and 0 < count <= MAX_BOOLS):
        return False
    raw = read(table, size * 8)
    index = bool_slot(raw, size, SEQUENCE_IS_CHILDHOOD) if raw else None
    return index is not None and index < count


def module_starts(regions, read):
    """Host addresses of the loaded NSO modules (committed regions starting with a MOD0 pointer)."""
    result = []
    for address, size, state in regions:
        if state != MEM_COMMIT or size < 0x1000:
            continue
        head = read(address, 8)
        offset = struct.unpack_from('<I', head, 4)[0] if head else 0
        if 8 <= offset < MAX_MODULE and not offset & 3 and read(address + offset, 4) == b'MOD0':
            result.append(address)
    return result


def emulator_layout(regions, read):
    """(host base of guest memory, guest GameData slot) in an emulator process, or None.

    ``regions``: (address, size, state) of the process, in address order; ``read(host, size)``
    returns bytes or None. Pure: tested without a game.
    """
    offset = GAMEDATA_SLOT - HOOKSHOT_MAIN
    for module in module_starts(regions, read):
        raw = read(module + offset, 8)
        if not raw or not struct.unpack('<Q', raw)[0]:
            continue   # not main, or the game has not loaded its data yet
        for guest in GUEST_CODE:
            base = module - guest
            if valid_slot(lambda address, length: read(base + address, length), guest + offset):
                return base, guest + offset
    return None


class MemoryRegion(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_ulonglong), ('AllocationBase', ctypes.c_ulonglong),
                ('AllocationProtect', ctypes.c_ulong), ('PartitionId', ctypes.c_ushort),
                ('RegionSize', ctypes.c_ulonglong), ('State', ctypes.c_ulong),
                ('Protect', ctypes.c_ulong), ('Type', ctypes.c_ulong)]


class ProcessMemory:
    """ReadProcessMemory on the running game: Hookshot, else an emulator that has the game loaded.

    ``base``: host address of guest address 0; ``slot``: guest address of the GameData slot.
    """
    def __init__(self):
        from ctypes import wintypes
        self.wt = wintypes
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self.k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(MemoryRegion),
                                            ctypes.c_size_t]
        self.k32.VirtualQueryEx.restype = ctypes.c_size_t
        self.handle, self.pid, self.next_scan = None, None, 0.0
        self.base, self.slot = HOST_BASE, GAMEDATA_SLOT

    def _pids(self):
        from ctypes import wintypes
        psapi = ctypes.WinDLL('psapi')
        array = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        psapi.EnumProcesses(array, ctypes.sizeof(array), ctypes.byref(needed))
        return list(array[:needed.value // 4])

    def _exe(self, handle):
        size = self.wt.DWORD(520)
        buffer = ctypes.create_unicode_buffer(size.value)
        if self.k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name.lower()
        return ''

    def attach(self):
        if self.handle:
            code = self.wt.DWORD()
            if self.k32.GetExitCodeProcess(self.handle, ctypes.byref(code)) and code.value == 259:  # STILL_ACTIVE
                return
            self.close()
        now = time.monotonic()
        if now < self.next_scan:
            raise LiveUnavailable('game not running')
        self.next_scan = now + 5   # scanning every process each second would be wasteful
        emulators = emulator_exes()
        for pid in self._pids():
            handle = self.k32.OpenProcess(0x0010 | 0x0400, False, pid)   # VM_READ | QUERY_INFORMATION
            if not handle:
                continue
            name = self._exe(handle)
            layout = None
            if name == GAME_EXE and self._probe(handle):
                layout = HOST_BASE, GAMEDATA_SLOT
            elif name in emulators:
                layout = emulator_layout(self._regions(handle), lambda host, size: self._read(handle, host, size))
            if layout:
                self.handle, self.pid = handle, pid
                self.base, self.slot = layout
                return
            self.k32.CloseHandle(handle)
        raise LiveUnavailable('game not running')

    def _regions(self, handle):
        """(address, size, state) of every region of the process, in address order."""
        result, address, region = [], 0, MemoryRegion()
        while self.k32.VirtualQueryEx(handle, address, ctypes.byref(region), ctypes.sizeof(region)):
            result.append((region.BaseAddress, region.RegionSize, region.State))
            address = region.BaseAddress + region.RegionSize
        return result

    def _read(self, handle, host, size):
        buffer, done = ctypes.create_string_buffer(size), ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(handle, ctypes.c_void_p(host), buffer, size, ctypes.byref(done)) \
                or done.value != size:
            return None
        return buffer.raw

    def _probe(self, handle):
        """The launcher is also hookshot.exe: keep the process whose guest window is mapped."""
        buffer, done = ctypes.create_string_buffer(8), ctypes.c_size_t()
        return bool(self.k32.ReadProcessMemory(handle, ctypes.c_void_p(HOST_BASE + GAMEDATA_SLOT), buffer, 8,
                                               ctypes.byref(done)))

    def read(self, guest, size):
        data = self._read(self.handle, self.base + guest, size)
        if data is None:
            raise LiveUnavailable(f'cannot read at {guest:#x}')
        return data

    def write(self, guest, data):
        """WriteProcessMemory through a handle opened for this write only."""
        handle = self.k32.OpenProcess(0x0008 | 0x0020 | 0x0010, False, self.pid)   # VM_OPERATION|VM_WRITE|VM_READ
        if not handle:
            raise LiveUnavailable('cannot open the game for writing')
        try:
            self.k32.WriteProcessMemory.argtypes = [self.wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p,
                                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            done = ctypes.c_size_t()
            if not self.k32.WriteProcessMemory(handle, ctypes.c_void_p(self.base + guest), data, len(data),
                                               ctypes.byref(done)) or done.value != len(data):
                raise LiveUnavailable(f'cannot write at {guest:#x}')
        finally:
            self.k32.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.k32.CloseHandle(self.handle)
        self.handle, self.pid = None, None


class LiveGameData:
    """snapshot() -> {'bool': {hash: bool}, 'sha256': ...} or raises LiveUnavailable."""
    def __init__(self, memory=None):
        self.memory = memory or ProcessMemory()

    def u64(self, guest):
        return struct.unpack('<Q', self.memory.read(guest, 8))[0]

    def u32(self, guest):
        return struct.unpack('<I', self.memory.read(guest, 4))[0]

    def snapshot(self):
        try:
            self.memory.attach()
            holder = self.u64(getattr(self.memory, 'slot', GAMEDATA_SLOT))
            manager = self.u64(holder) if holder else 0
            if not manager:
                raise LiveUnavailable('game data not loaded yet')
            table, size = self.u64(manager + 32), self.u32(manager + 44)
            entries, count = self.u64(manager + 24), self.u32(manager + 16)
            if not (table and entries and 0 < size <= MAX_TABLE and 0 < count <= MAX_BOOLS):
                raise LiveUnavailable('unexpected GameData structure (game version?)')
            raw_table = self.memory.read(table, size * 8)
            raw_entries = self.memory.read(entries, count * 24)
        except LiveUnavailable:
            self.memory.close()
            raise
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error))
        self._layout = (table, size, entries, count)
        bools = parse_bools(raw_table, raw_entries, count)
        if SEQUENCE_IS_CHILDHOOD not in bools:
            raise LiveUnavailable('GameData table not recognised')
        digest = hashlib.sha256(raw_entries)
        snapshot = {'bool': bools, 'bool64_complete': False}
        try:
            snapshot['bool64'], raw_records = self._bool64(manager)
            snapshot['bool64_complete'] = True
            digest.update(raw_records)
        except LiveUnavailable as error:
            snapshot['bool64_status'] = str(error)
        snapshot['sha256'] = digest.hexdigest()
        return snapshot

    def _bool64(self, manager):
        """({key: True} of the set Bool64bitKey flags, raw records), or LiveUnavailable."""
        offsets = [self._bool64_offset] if getattr(self, '_bool64_offset', None) else []
        for offset in offsets + [BOOL64_TYPE] + [o for o in BOOL64_SCAN if o != BOOL64_TYPE]:
            try:
                count, records = self.u32(manager + offset), self.u64(manager + offset + 8)
                if not (0 < count <= MAX_BOOLS and records and not records & 7):
                    continue
                raw = self.memory.read(records, count * BOOL64_RECORD)
            except LiveUnavailable:
                continue
            flags = parse_bool64(raw, count)
            if flags is not None:
                self._bool64_offset = offset
                return flags, raw
        self._bool64_offset = None
        raise LiveUnavailable('Bool64bitKey flags not found (game version?)')


def bool_slot(table, size, key):
    """Index of Bool ``key`` in the raw (hash, index) table, or None (pure)."""
    for probe in range(size):
        slot = (key + probe) % size
        found, index = struct.unpack_from('<II', table, slot * 8)
        if not found:
            return None
        if found == key:
            return index
    return None


def set_bool_in(data, key, value):
    """``data``: a LiveGameData. Writes Bool ``key`` (hash); False when the game does not know it."""
    data.snapshot()   # attach and check the structure
    table, size, entries, count = data._layout
    index = bool_slot(data.memory.read(table, size * 8), size, key)
    if index is None or index >= count:
        return False
    position = entries + index * 24 + 22
    current = data.memory.read(position, 1)[0]
    data.memory.write(position, bytes([(current & ~1) | int(bool(value))]))
    return True


# EventMgr, as Hookshot's teleport cheat reads it (hos_main.c, OOT_EVENTMGR_SLOT): a guest
# pointer to a holder whose first word is the manager; its u64 at +104 is non-zero while an
# event plays ("the Main sequence's 'Event' test"). Talks, cutscenes, chests are all events.
EVENTMGR_SLOT = 0x84C9E090
EVENT_PLAYING_OFFSET = 104


def event_playing_from(holder, manager, word):
    """Pure decision from the three words read (tested without a game)."""
    if not holder or not manager:
        raise LiveUnavailable('event manager not loaded yet')
    return word != 0


class LiveEventState:
    """``playing()`` -> bool, or raises LiveUnavailable. Reads 24 bytes, never writes."""
    def __init__(self, memory=None):
        self.memory = memory or ProcessMemory()

    def u64(self, guest):
        return struct.unpack('<Q', self.memory.read(guest, 8))[0]

    def playing(self):
        try:
            self.memory.attach()
            holder = self.u64(getattr(self.memory, 'slot', GAMEDATA_SLOT) - GAMEDATA_SLOT + EVENTMGR_SLOT)
            manager = self.u64(holder) if holder else 0
            word = self.u64(manager + EVENT_PLAYING_OFFSET) if manager else 0
        except LiveUnavailable:
            self.memory.close()
            raise
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error))
        return event_playing_from(holder, manager, word)


def main():
    """Diagnostic (game running; reads only): ``python -m oot_rando memory``."""
    try:
        data = LiveGameData().snapshot()
    except LiveUnavailable as error:
        print('Cannot read the game:', error)
    else:
        print(f"{len(data['bool'])} booleans read; Sequence_IsChildhood = {data['bool'][SEQUENCE_IS_CHILDHOOD]}")
    try:
        print('Event playing (dialogue, cutscene…):', LiveEventState().playing())
    except LiveUnavailable as error:
        print('Event state unreadable:', error)


if __name__ == '__main__':
    main()
