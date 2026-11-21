"""The in-game console's mailbox: Archipelago messages written into the running game's memory.

The game has no network of its own, so the in-game tracker module (``ingame_tracker``, 0.5.0 and
later) keeps a block of its own data that this client fills: lines of text, the connection's
status and a heartbeat. The module draws them over the game (its console) and writes back the seed
it runs and how many lines it has taken. The layout is ``ingame_tracker/src/mailbox.h``, documented
in ``docs/ingame-tracker-format.md`` ("The console's mailbox").

Finding it: emulators load the game's modules one after the other in guest memory (rtld, main,
subsdk0-9, sdk). From main (its place comes from ``live_memory``'s layout) the walk follows each
module's MOD0 header to the next one, keeps the module whose first words carry the tracker's
signature, and looks in its data for the mailbox's magic. Only ``attach``, ``read`` and ``write`` of
``live_memory.ProcessMemory`` are used, so it works wherever live memory does (Windows).

Writing: the sequence word goes odd, then the entries, the head and the status are written, then the
sequence goes even; the module ignores a write it sees half done. The heartbeat counts up about
once a second; the module says "Archipelago client not running" after 10 s without it.
"""
from collections import deque
import struct
import threading
import time

MAGIC = b'OOTRCON1'
VERSION = 1
HEADER_SIZE = 0x80
CAPACITY = 32
ENTRY_SIZE = 168
TEXT_ROOM = 164
STATUS_ROOM = 64
SEED_ID_ROOM = 24
# offsets in the mailbox (mailbox.h)
SEQUENCE, HEAD, HEARTBEAT, STATUS, STATUS_TEXT, SEED_ID, READ_HEAD, MODULE_VERSION = (
    0x10, 0x14, 0x18, 0x1C, 0x20, 0x60, 0x78, 0x7C)
HEADER = struct.Struct('<8sHHHHIIIB3x64s24sII')
STATUS_NONE, STATUS_DISCONNECTED, STATUS_CONNECTING, STATUS_CONNECTED = range(4)
# the console's kinds of message (console.h's console_kind_t); an entry stores kind + 1
KIND_RECEIVED, KIND_SENT, KIND_HINT, KIND_CHAT, KIND_SERVER, KIND_OTHERS = range(6)
KIND_COUNT = 6
OTHERS_MODULE_VERSION = 0x000600  # modules before it show KIND_OTHERS as server notices, so it isn't sent to them

MODULE_SIGNATURE = b'OOTRTRK\0'   # the tracker module's crt0.S, at its start + 8
PAGE = 0x1000
MAX_MODULES = 16
MAX_GAP_PAGES = 256               # pages looked at past a module for the next one
MAX_DATA = 4 << 20                # a module with more code and data than this is not the tracker's
READ_CHUNK = 0x10000
QUEUE = 200                       # lines kept while the game takes none (the oldest go first)
assert HEADER.size == HEADER_SIZE


def classify(packet, slot):
    """The console kind of a PrintJSON packet for player ``slot``.

    Items: received when they are for this slot (found here or elsewhere), sent when this slot found
    them for another, other players' items when neither (a player finding their own, or one sending to
    a third). Hints, chat (also the server's), and everything else (joins, goals, releases, countdowns,
    command answers...) as server notices.
    """
    kind = packet.get('type')
    if kind in ('ItemSend', 'ItemCheat'):
        finder = (packet.get('item') or {}).get('player')
        if packet.get('receiving') == slot:
            return KIND_RECEIVED
        if finder == slot:
            return KIND_SENT
        return KIND_OTHERS
    if kind == 'Hint':
        return KIND_HINT
    if kind in ('Chat', 'ServerChat'):
        return KIND_CHAT
    return KIND_SERVER


def utf8_cut(text, room):
    """``text`` as UTF-8 on one line, cut to at most ``room`` bytes without splitting a character."""
    data = ' '.join(str(text).replace('\0', '').split()).encode('utf-8')
    if len(data) <= room:
        return data
    end = room
    while end and data[end] & 0xC0 == 0x80:
        end -= 1
    return data[:end]


def entry(kind, text):
    data = utf8_cut(text, TEXT_ROOM)
    return struct.pack('<BBH', kind + 1, len(data), 0) + data.ljust(TEXT_ROOM, b'\0')


def header(data):
    """The mailbox header's fields from its 0x80 bytes, or None if they are not a mailbox of this version."""
    if not data or len(data) < HEADER_SIZE:
        return None
    (magic, version, header_size, capacity, entry_size, sequence, head, heartbeat, status, status_text,
     seed_id, read_head, module_version) = HEADER.unpack_from(data)
    if (magic, version, header_size, capacity, entry_size) != (MAGIC, VERSION, HEADER_SIZE, CAPACITY, ENTRY_SIZE):
        return None
    return {'sequence': sequence, 'head': head, 'heartbeat': heartbeat, 'status': status,
            'seed_id': seed_id.split(b'\0', 1)[0].decode('ascii', 'replace'), 'read_head': read_head,
            'module_version': module_version}


def _u32(read, address):
    data = read(address, 4)
    return struct.unpack('<I', data)[0] if data and len(data) == 4 else None


def module_image(read, start):
    """(end of code and data, end of the whole image, page aligned) of the module at ``start``, or None."""
    mod0 = _u32(read, start + 4)
    if mod0 is None or not 8 <= mod0 < 0x10000000 or mod0 & 3 or read(start + mod0, 4) != b'MOD0':
        return None
    bss_start, bss_end = _u32(read, start + mod0 + 8), _u32(read, start + mod0 + 12)
    if bss_start is None or bss_end is None:
        return None
    # the offsets are signed and relative to MOD0
    data_end = start + mod0 + struct.unpack('<i', struct.pack('<I', bss_start))[0]
    image_end = start + mod0 + struct.unpack('<i', struct.pack('<I', bss_end))[0]
    if not start < data_end <= image_end:
        return None
    return data_end, (image_end + PAGE - 1) & ~(PAGE - 1)


def modules_after(read, main):
    """Starts of main and the modules loaded after it, in guest memory."""
    starts, at = [], main
    while len(starts) < MAX_MODULES:
        image = module_image(read, at)
        if image is None:
            for page in range(1, MAX_GAP_PAGES + 1):   # a gap between images: look a little further
                if module_image(read, at + page * PAGE):
                    at += page * PAGE
                    break
            else:
                return starts
            continue
        starts.append(at)
        at = image[1]
    return starts


def _read_span(read, start, end):
    """Bytes in [start, end), unreadable chunks as zeros."""
    out = bytearray()
    for address in range(start, end, READ_CHUNK):
        size = min(READ_CHUNK, end - address)
        out += read(address, size) or bytes(size)
    return bytes(out)


def find_mailbox(read, main):
    """Guest address of the tracker module's mailbox, or None. ``read(guest, size)``: bytes or None."""
    for start in modules_after(read, main)[1:]:
        if read(start + 8, len(MODULE_SIGNATURE)) != MODULE_SIGNATURE:
            continue
        data_end, _ = module_image(read, start)
        if data_end - start > MAX_DATA:
            continue
        data = _read_span(read, start, data_end)
        at = data.find(MAGIC)
        while at >= 0:
            if not at % 16 and header(data[at:at + HEADER_SIZE]):
                return start + at
            at = data.find(MAGIC, at + 1)
    return None


def main_start(memory):
    """Guest address of main in an attached ``live_memory`` reader (from its GameData slot)."""
    from oot_rando.tracker.live_memory import GAMEDATA_SLOT, HOOKSHOT_MAIN
    return memory.slot - (GAMEDATA_SLOT - HOOKSHOT_MAIN)


class ConsoleMailbox:
    """Lines and status for the console of the game running seed ``seed_id`` (the seed folder's 16
    characters). ``add`` and ``set_status`` may be called from any thread; ``step`` (about once a
    second, one thread) writes them into the game."""

    def __init__(self, seed_id, memory=None):
        self.seed_id = seed_id
        self.memory = memory
        self.address, self.layout = None, None
        self.state = 'not started'
        self._lock = threading.Lock()
        self._lines = deque(maxlen=QUEUE)
        self._status, self._status_text = STATUS_NONE, b''
        self._written_status = None

    def add(self, kind, text):
        if str(text).strip():
            with self._lock:
                self._lines.append(entry(kind, text))

    def set_status(self, status, text=''):
        with self._lock:
            self._status, self._status_text = status, utf8_cut(text, STATUS_ROOM - 1)

    def waiting(self):
        with self._lock:
            return len(self._lines)

    def _read(self, guest, size):
        from oot_rando.tracker.live_memory import LiveUnavailable
        try:
            return self.memory.read(guest, size)
        except LiveUnavailable:
            return None

    def _attach(self):
        """The mailbox's current header, after finding it if needed; None (and ``state`` says why) if
        there is none to write to."""
        from oot_rando.tracker.live_memory import LiveUnavailable, ProcessMemory
        if self.memory is None:
            self.memory = ProcessMemory()
        try:
            self.memory.attach()
        except LiveUnavailable as error:
            self.address, self.state = None, 'game not reachable (' + str(error) + ')'
            return None
        layout = (self.memory.base, self.memory.slot)
        if layout != self.layout:
            self.address, self.layout = None, layout
        fields = header(self._read(self.address, HEADER_SIZE)) if self.address is not None else None
        if fields is None:
            self.address = find_mailbox(self._read, main_start(self.memory))
            fields = header(self._read(self.address, HEADER_SIZE)) if self.address is not None else None
        if fields is None:
            self.address = None
            self.state = 'no in-game console in the running game (in-game tracker 0.5.0 or later)'
            return None
        if not fields['seed_id']:
            self.state = 'the game has not read its seed yet'
            return None
        if fields['seed_id'] != self.seed_id:
            self.state = 'the running game plays another seed'
            return None
        return fields

    def running_seed(self):
        """Whether the running game is this seed with its console (for auto-connecting)."""
        return self._attach() is not None

    def step(self):
        """One write. True if the game has this seed's mailbox and it was written."""
        from oot_rando.tracker.live_memory import LiveUnavailable
        fields = self._attach()
        if fields is None:
            return False
        with self._lock:
            if fields['module_version'] < OTHERS_MODULE_VERSION:
                self._lines = deque((line for line in self._lines if line[0] != KIND_OTHERS + 1), maxlen=QUEUE)
            free = max(0, CAPACITY - (fields['head'] - fields['read_head'])) if fields['head'] >= fields['read_head'] \
                else CAPACITY
            lines = list(self._lines)[:free]
            status, status_text = self._status, self._status_text
        heartbeat = (fields['heartbeat'] + 1) & 0xFFFFFFFF
        try:
            if lines or (status, status_text) != self._written_status:
                self._write_all(fields, lines, heartbeat, status, status_text)
                self._written_status = (status, status_text)
            else:
                self.memory.write(self.address + HEARTBEAT, struct.pack('<I', heartbeat))
        except LiveUnavailable as error:
            self.state = 'cannot write in the game (' + str(error) + ')'
            return False
        with self._lock:
            for line in lines:   # the queue may have dropped its oldest meanwhile
                if self._lines and self._lines[0] is line:
                    self._lines.popleft()
        self.state = 'writing to the in-game console'
        return True

    def _write_all(self, fields, lines, heartbeat, status, status_text):
        sequence, head = fields['sequence'], fields['head']
        if sequence & 1:   # left odd by a client that stopped midway
            sequence += 1
        write = self.memory.write
        write(self.address + SEQUENCE, struct.pack('<I', (sequence + 1) & 0xFFFFFFFF))
        for index, line in enumerate(lines):
            write(self.address + HEADER_SIZE + (head + index) % CAPACITY * ENTRY_SIZE, line)
        block = struct.pack('<IIB3x', (head + len(lines)) & 0xFFFFFFFF, heartbeat, status)
        write(self.address + HEAD, block + status_text.ljust(STATUS_ROOM, b'\0'))
        write(self.address + SEQUENCE, struct.pack('<I', (sequence + 2) & 0xFFFFFFFF))
