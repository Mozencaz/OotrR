"""Read-only, real-time GameData bools from a running Hookshot game (Windows).

Layout, as Hookshot v2.1.0's own cheat menu reads it (tools/host/hos_main.c, oot_gamedata_set_bool):
- guest memory is one window at the fixed host address A64_HOST_BASE = 0x100000000000
  (rt/a64.h; nx2 builds use 64-bit guest addresses: host = base + guest);
- the guest pointer at OOT_GAMEDATA_SLOT (0x84c9e180) points to a holder whose first word is
  the GameDataMgr;
- GameDataMgr+32: (hash u32, index u32) open-addressing table, its size u32 at +44, probe
  start hash % size, key 0 = empty slot;
- GameDataMgr+24: Bool entries, 24 bytes each, value byte at +22; their count u32 at +16.

Only the Bool type is documented there. Bool64bitKey (most chest collection flags) keeps
coming from progress.sav. The only write is ``LiveGameData.set_bool`` (the Archipelago
client's reception signal, ``patching.ap_mailbox``): one value byte, as the cheat menu does.
"""
import ctypes
import hashlib
import struct
import time
from pathlib import Path

HOST_BASE = 0x100000000000
GAMEDATA_SLOT = 0x84C9E180
SEQUENCE_IS_CHILDHOOD = 0xCEA220D3   # murmur3('Sequence_IsChildhood'), always present
MAX_TABLE, MAX_BOOLS = 1 << 20, 1 << 20
GAME_EXE = 'hookshot.exe'


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


class ProcessMemory:
    """ReadProcessMemory on the first hookshot.exe process that maps the guest window."""
    def __init__(self):
        from ctypes import wintypes
        self.wt = wintypes
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self.handle, self.pid, self.next_scan = None, None, 0.0

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
        for pid in self._pids():
            handle = self.k32.OpenProcess(0x0010 | 0x1000, False, pid)   # VM_READ | QUERY_LIMITED_INFORMATION
            if not handle:
                continue
            if self._exe(handle) == GAME_EXE and self._probe(handle):
                self.handle, self.pid = handle, pid
                return
            self.k32.CloseHandle(handle)
        raise LiveUnavailable('game not running')

    def _probe(self, handle):
        """The launcher is also hookshot.exe: keep the process whose guest window is mapped."""
        buffer, done = ctypes.create_string_buffer(8), ctypes.c_size_t()
        return bool(self.k32.ReadProcessMemory(handle, ctypes.c_void_p(HOST_BASE + GAMEDATA_SLOT), buffer, 8,
                                               ctypes.byref(done)))

    def read(self, guest, size):
        buffer, done = ctypes.create_string_buffer(size), ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(self.handle, ctypes.c_void_p(HOST_BASE + guest), buffer, size,
                                          ctypes.byref(done)) or done.value != size:
            raise LiveUnavailable(f'cannot read at {guest:#x}')
        return buffer.raw

    def write(self, guest, data):
        """WriteProcessMemory through a handle opened for this write only."""
        handle = self.k32.OpenProcess(0x0008 | 0x0020 | 0x0010, False, self.pid)   # VM_OPERATION|VM_WRITE|VM_READ
        if not handle:
            raise LiveUnavailable('cannot open the game for writing')
        try:
            self.k32.WriteProcessMemory.argtypes = [self.wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p,
                                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            done = ctypes.c_size_t()
            if not self.k32.WriteProcessMemory(handle, ctypes.c_void_p(HOST_BASE + guest), data, len(data),
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
            holder = self.u64(GAMEDATA_SLOT)
            manager = self.u64(holder) if holder else 0
            if not manager:
                raise LiveUnavailable('game data not loaded yet')
            table, size = self.u64(manager + 32), self.u32(manager + 44)
            entries, count = self.u64(manager + 24), self.u32(manager + 16)
            if not (table and entries and 0 < size <= MAX_TABLE and 0 < count <= MAX_BOOLS):
                raise LiveUnavailable('unexpected GameData structure (Hookshot version?)')
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
        digest = hashlib.sha256(raw_entries).hexdigest()
        return {'bool': bools, 'sha256': digest}


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
            holder = self.u64(EVENTMGR_SLOT)
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
        print('Lecture impossible :', error)
    else:
        print(f"{len(data['bool'])} booleans read; Sequence_IsChildhood = {data['bool'][SEQUENCE_IS_CHILDHOOD]}")
    try:
        print('Event playing (dialogue, cutscene…):', LiveEventState().playing())
    except LiveUnavailable as error:
        print('Event state unreadable:', error)


if __name__ == '__main__':
    main()
