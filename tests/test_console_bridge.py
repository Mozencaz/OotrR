"""The in-game console's mailbox (archipelago.console_bridge), its feed from the Archipelago client and
archipelago.json (archipelago.autoconnect), on fake game memory."""
import _src_path  # noqa: F401  (src on sys.path)
import json
import re
import struct
import tempfile
import time
import unittest
from pathlib import Path

from oot_rando.archipelago import autoconnect, console_bridge as cb
from oot_rando.archipelago import client as ap
from oot_rando.tracker.live_memory import GAMEDATA_SLOT, HOOKSHOT_MAIN, LiveUnavailable

REPOSITORY = Path(__file__).resolve().parents[1]
MAILBOX_H = REPOSITORY / 'ingame_tracker' / 'src' / 'mailbox.h'
SEED = '76069ecc4740cec6'
PAGE = 0x1000


class FakeMemory:
    """Guest memory of a running game, page by page (unmapped pages can't be read), with the
    interface of live_memory.ProcessMemory."""

    def __init__(self, main):
        self.pages, self.base, self.slot = {}, 0x7000_0000_0000, main + (GAMEDATA_SLOT - HOOKSHOT_MAIN)
        self.writes, self.attached, self.reachable = [], 0, True

    def map(self, address, data):
        for index, value in enumerate(data):
            self.pages.setdefault((address + index) // PAGE * PAGE, bytearray(PAGE))[(address + index) % PAGE] = value

    def attach(self):
        self.attached += 1
        if not self.reachable:
            raise LiveUnavailable('game not running')

    def read(self, guest, size):
        out = bytearray()
        for address in range(guest, guest + size):
            page = self.pages.get(address // PAGE * PAGE)
            if page is None:
                raise LiveUnavailable(f'cannot read at {guest:#x}')
            out.append(page[address % PAGE])
        return bytes(out)

    def write(self, guest, data):
        self.read(guest, len(data))
        for index, value in enumerate(data):
            self.pages[(guest + index) // PAGE * PAGE][(guest + index) % PAGE] = value
        self.writes.append((guest, bytes(data)))


def module(size, bss, signature=b'', data=b'', data_at=0):
    """An NSO image as loaded: the word at +4 points at MOD0, whose bss offsets say where it ends."""
    image = bytearray(size)
    struct.pack_into('<II', image, 0, 0, 0x40)
    image[8:8 + len(signature)] = signature
    image[0x40:0x44] = b'MOD0'
    struct.pack_into('<iii', image, 0x44, 0, size - 0x40, size + bss - 0x40)
    image[data_at:data_at + len(data)] = data
    return bytes(image)


def blank_mailbox(seed=SEED, module_version=0x000500):
    box = bytearray(cb.HEADER_SIZE + cb.CAPACITY * cb.ENTRY_SIZE)
    struct.pack_into('<8sHHHH', box, 0, cb.MAGIC, cb.VERSION, cb.HEADER_SIZE, cb.CAPACITY, cb.ENTRY_SIZE)
    box[cb.SEED_ID:cb.SEED_ID + len(seed)] = seed.encode()
    struct.pack_into('<I', box, cb.MODULE_VERSION, module_version)
    return bytes(box)


MAIN = 0x8000_4000
TRACKER = MAIN + 0x6000 + 0x2000 + 2 * PAGE   # after main (5 pages + 1 of bss), subsdk0 (2) and a gap
MAILBOX_AT = 0x3010


def game(seed=SEED, tracker=True, module_version=0x000500):
    """Main, a subsdk0 holding the magic too (not the tracker's), a gap, the tracker module."""
    memory = FakeMemory(MAIN)
    memory.map(MAIN, module(0x5000, 0x1000))
    memory.map(MAIN + 0x6000, module(0x2000, 0, data=blank_mailbox(), data_at=0x800))
    if tracker:
        decoy = b'xx' + cb.MAGIC   # not aligned: not a mailbox
        image = bytearray(module(0x5000 + len(blank_mailbox()), 0x3000, cb.MODULE_SIGNATURE,
                                 blank_mailbox(seed, module_version), MAILBOX_AT))
        image[0x2000:0x2000 + len(decoy)] = decoy
        memory.map(TRACKER, bytes(image))
    return memory


def fields(memory):
    return cb.header(memory.read(TRACKER + MAILBOX_AT, cb.HEADER_SIZE))


def entries(memory):
    """What the module would take: the entries [read_head, head), as (kind, text)."""
    box = fields(memory)
    out = []
    for n in range(box['read_head'], box['head']):
        raw = memory.read(TRACKER + MAILBOX_AT + cb.HEADER_SIZE + n % cb.CAPACITY * cb.ENTRY_SIZE, cb.ENTRY_SIZE)
        out.append((raw[0] - 1, raw[4:4 + raw[1]].decode('utf-8')))
    return out


def module_reads(memory):
    """The module takes every entry: its read head catches up with the head."""
    head = fields(memory)['head']
    memory.map(TRACKER + MAILBOX_AT + cb.READ_HEAD, struct.pack('<I', head))


class Layout(unittest.TestCase):
    def test_the_layout_is_the_modules(self):
        text = MAILBOX_H.read_text(encoding='utf-8')
        defines = dict(re.findall(r'#define (MAILBOX_\w+)\s+(0x[0-9A-Fa-f]+|\d+)', text))
        expected = {'MAILBOX_VERSION': cb.VERSION, 'MAILBOX_HEADER_SIZE': cb.HEADER_SIZE,
                    'MAILBOX_CAPACITY': cb.CAPACITY, 'MAILBOX_ENTRY_SIZE': cb.ENTRY_SIZE,
                    'MAILBOX_TEXT_ROOM': cb.TEXT_ROOM, 'MAILBOX_STATUS_ROOM': cb.STATUS_ROOM,
                    'MAILBOX_SEED_ID_ROOM': cb.SEED_ID_ROOM}
        for name, value in expected.items():
            self.assertEqual(int(defines[name], 0), value, name)
        offsets = dict(re.findall(r'offsetof\(mailbox_t, (\w+)\) == (0x[0-9A-Fa-f]+)', text))
        for name, value in [('sequence', cb.SEQUENCE), ('head', cb.HEAD), ('heartbeat', cb.HEARTBEAT),
                            ('status', cb.STATUS), ('status_text', cb.STATUS_TEXT), ('seed_id', cb.SEED_ID),
                            ('read_head', cb.READ_HEAD), ('module_version', cb.MODULE_VERSION)]:
            self.assertEqual(int(offsets[name], 0), value, name)
        self.assertIn('MAILBOX_STATUS_NONE, MAILBOX_STATUS_DISCONNECTED, MAILBOX_STATUS_CONNECTING, '
                      'MAILBOX_STATUS_CONNECTED', text)
        self.assertIn(".magic = { 'O', 'O', 'T', 'R', 'C', 'O', 'N', '1' }",
                      (MAILBOX_H.parent / 'mailbox.c').read_text(encoding='utf-8'))
        console_h = (MAILBOX_H.parent / 'console.h').read_text(encoding='utf-8')
        self.assertIn('CONSOLE_RECEIVED, CONSOLE_SENT, CONSOLE_HINT, CONSOLE_CHAT, CONSOLE_SERVER, CONSOLE_OTHERS, '
                      'CONSOLE_KIND_COUNT', console_h)
        self.assertGreaterEqual(int(defines['MAILBOX_MODULE_VERSION'], 0), cb.OTHERS_MODULE_VERSION)
        kinds = re.search(r'typedef enum \{\s*(CONSOLE_RECEIVED[^}]*?),\s*CONSOLE_KIND_COUNT', console_h).group(1)
        self.assertEqual(len(kinds.split(',')), cb.KIND_COUNT)
        crt0 = (MAILBOX_H.parent / 'crt0.S').read_text(encoding='utf-8')
        self.assertIn('.ascii  "OOTRTRK\\0"', crt0)   # the signature at the module's start + 8

    def test_kinds_of_message(self):
        item = lambda finder, receiving: {'type': 'ItemSend', 'receiving': receiving, 'item': {'player': finder}}
        self.assertEqual(cb.classify(item(2, 1), 1), cb.KIND_RECEIVED)
        self.assertEqual(cb.classify(item(1, 1), 1), cb.KIND_RECEIVED)   # found in this world
        self.assertEqual(cb.classify(item(1, 3), 1), cb.KIND_SENT)
        self.assertEqual(cb.classify(item(2, 3), 1), cb.KIND_OTHERS)     # between two others
        self.assertEqual(cb.classify(item(2, 2), 1), cb.KIND_OTHERS)     # another found their own
        self.assertEqual(cb.classify({**item(2, 1), 'type': 'ItemCheat'}, 1), cb.KIND_RECEIVED)
        self.assertEqual(cb.classify({'type': 'Hint', 'receiving': 1, 'item': {'player': 2}}, 1), cb.KIND_HINT)
        for kind in ('Chat', 'ServerChat'):
            self.assertEqual(cb.classify({'type': kind}, 1), cb.KIND_CHAT)
        for kind in ('Join', 'Part', 'Goal', 'Release', 'Collect', 'Countdown', 'TagsChanged', 'Tutorial',
                     'CommandResult', 'AdminCommandResult', None):
            self.assertEqual(cb.classify({'type': kind} if kind else {}, 1), cb.KIND_SERVER)

    def test_text_is_one_line_of_whole_characters(self):
        self.assertEqual(cb.utf8_cut('a\nb\tc\0d  e', 64), b'a b cd e')
        cut = cb.utf8_cut('é' * 100, cb.TEXT_ROOM)
        self.assertEqual(len(cut), cb.TEXT_ROOM)
        cut = cb.utf8_cut('x' + '→' * 60, cb.TEXT_ROOM)   # 3 bytes each: 1 + 54 * 3 = 163
        self.assertEqual(len(cut), 163)
        cut.decode('utf-8')
        raw = cb.entry(cb.KIND_CHAT, 'Zelda: hi')
        self.assertEqual(len(raw), cb.ENTRY_SIZE)
        self.assertEqual(raw[:4], bytes([cb.KIND_CHAT + 1, 9, 0, 0]))


class Finding(unittest.TestCase):
    def test_the_tracker_modules_mailbox_is_found_after_main(self):
        memory = game()
        reader = lambda guest, size: _quiet(memory.read, guest, size)
        self.assertEqual(cb.modules_after(reader, MAIN), [MAIN, MAIN + 0x6000, TRACKER])
        self.assertEqual(cb.find_mailbox(reader, MAIN), TRACKER + MAILBOX_AT)
        self.assertEqual(cb.main_start(memory), MAIN)

    def test_no_mailbox_without_the_tracker_module(self):
        memory = game(tracker=False)
        self.assertIsNone(cb.find_mailbox(lambda guest, size: _quiet(memory.read, guest, size), MAIN))

    def test_a_header_of_another_version_is_not_one(self):
        box = bytearray(blank_mailbox())
        self.assertEqual(cb.header(bytes(box))['seed_id'], SEED)
        struct.pack_into('<H', box, 8, 2)
        self.assertIsNone(cb.header(bytes(box)))
        self.assertIsNone(cb.header(b''))


def _quiet(read, guest, size):
    try:
        return read(guest, size)
    except LiveUnavailable:
        return None


class Writing(unittest.TestCase):
    def test_lines_go_in_with_the_sequence_odd_meanwhile(self):
        memory = game()
        box = cb.ConsoleMailbox(SEED, memory)
        box.set_status(cb.STATUS_CONNECTED, 'archipelago.gg:38281 as Link')
        box.add(cb.KIND_RECEIVED, 'You received Bow from Zelda')
        box.add(cb.KIND_CHAT, 'Zelda: hi')
        self.assertTrue(box.step())
        address = TRACKER + MAILBOX_AT
        writes = memory.writes
        self.assertEqual(writes[0], (address + cb.SEQUENCE, struct.pack('<I', 1)))
        self.assertEqual(writes[-1], (address + cb.SEQUENCE, struct.pack('<I', 2)))
        self.assertEqual([w[0] for w in writes[1:3]], [address + cb.HEADER_SIZE, address + cb.HEADER_SIZE + 168])
        self.assertEqual(writes[3][0], address + cb.HEAD)
        after = fields(memory)
        self.assertEqual((after['sequence'], after['head'], after['heartbeat'], after['status']),
                         (2, 2, 1, cb.STATUS_CONNECTED))
        status_text = memory.read(address + cb.STATUS_TEXT, cb.STATUS_ROOM)
        self.assertEqual(status_text.rstrip(b'\0'), b'archipelago.gg:38281 as Link')
        self.assertEqual(entries(memory), [(cb.KIND_RECEIVED, 'You received Bow from Zelda'),
                                           (cb.KIND_CHAT, 'Zelda: hi')])
        self.assertEqual(box.waiting(), 0)
        self.assertEqual(box.state, 'writing to the in-game console')

    def test_nothing_new_only_beats_the_heart(self):
        memory = game()
        box = cb.ConsoleMailbox(SEED, memory)
        box.set_status(cb.STATUS_CONNECTED, 'x')
        box.step()
        memory.writes.clear()
        self.assertTrue(box.step())
        self.assertEqual(memory.writes, [(TRACKER + MAILBOX_AT + cb.HEARTBEAT, struct.pack('<I', 2))])
        box.set_status(cb.STATUS_DISCONNECTED)
        memory.writes.clear()
        box.step()
        self.assertEqual(len(memory.writes), 3)   # sequence, head and status, sequence
        self.assertEqual(fields(memory)['status'], cb.STATUS_DISCONNECTED)

    def test_no_more_than_the_module_has_room_for(self):
        memory = game()
        box = cb.ConsoleMailbox(SEED, memory)
        for n in range(cb.CAPACITY + 10):
            box.add(cb.KIND_SERVER, f'notice {n}')
        box.step()
        self.assertEqual(fields(memory)['head'], cb.CAPACITY)
        self.assertEqual(box.waiting(), 10)
        box.step()
        self.assertEqual(fields(memory)['head'], cb.CAPACITY)   # the module has read none
        module_reads(memory)
        box.step()
        self.assertEqual(fields(memory)['head'], cb.CAPACITY + 10)
        self.assertEqual(entries(memory)[-1], (cb.KIND_SERVER, f'notice {cb.CAPACITY + 9}'))
        self.assertEqual(box.waiting(), 0)

    def test_other_players_items_go_only_to_a_module_that_knows_them(self):
        for version, expected in ((0x000600, [(cb.KIND_CHAT, 'Zelda: hi'), (cb.KIND_OTHERS, 'Saria found her Bow'),
                                              (cb.KIND_SERVER, 'Saria joined')]),
                                  (0x000500, [(cb.KIND_CHAT, 'Zelda: hi'), (cb.KIND_SERVER, 'Saria joined')])):
            with self.subTest(hex(version)):
                memory = game(module_version=version)
                box = cb.ConsoleMailbox(SEED, memory)
                for kind, line in ((cb.KIND_CHAT, 'Zelda: hi'), (cb.KIND_OTHERS, 'Saria found her Bow'),
                                   (cb.KIND_SERVER, 'Saria joined')):
                    box.add(kind, line)
                self.assertTrue(box.step())
                self.assertEqual(entries(memory), expected)
                self.assertEqual(box.waiting(), 0)

    def test_another_seed_or_no_seed_yet_gets_nothing(self):
        for seed, state in (('0123456789abcdef', 'another seed'), ('', 'not read its seed')):
            memory = game(seed)
            box = cb.ConsoleMailbox(SEED, memory)
            box.add(cb.KIND_CHAT, 'hi')
            self.assertFalse(box.step())
            self.assertFalse(box.running_seed())
            self.assertIn(state, box.state)
            self.assertEqual(memory.writes, [])
            self.assertEqual(box.waiting(), 1)
        memory = game()
        self.assertTrue(cb.ConsoleMailbox(SEED, memory).running_seed())

    def test_a_game_not_running_or_without_the_console(self):
        memory = game()
        memory.reachable = False
        box = cb.ConsoleMailbox(SEED, memory)
        self.assertFalse(box.step())
        self.assertIn('not reachable', box.state)
        box = cb.ConsoleMailbox(SEED, game(tracker=False))
        self.assertFalse(box.step())
        self.assertIn('0.5.0', box.state)

    def test_a_game_started_again_is_found_again(self):
        memory = game()
        box = cb.ConsoleMailbox(SEED, memory)
        box.add(cb.KIND_CHAT, 'one')
        box.step()
        restarted = game()   # the module's mailbox blank again, the layout changed
        restarted.slot += 0
        restarted.base += PAGE
        box.memory = restarted
        box.add(cb.KIND_CHAT, 'two')
        self.assertTrue(box.step())
        self.assertEqual(entries(restarted), [(cb.KIND_CHAT, 'two')])
        self.assertEqual(fields(restarted)['sequence'], 2)

    def test_a_sequence_left_odd_is_closed(self):
        memory = game()
        memory.map(TRACKER + MAILBOX_AT + cb.SEQUENCE, struct.pack('<I', 5))
        box = cb.ConsoleMailbox(SEED, memory)
        box.add(cb.KIND_CHAT, 'hi')
        box.step()
        self.assertEqual(memory.writes[0][1], struct.pack('<I', 7))
        self.assertEqual(fields(memory)['sequence'], 8)


class FakeConsole:
    def __init__(self):
        self.lines, self.statuses, self.state = [], [], 'fake'

    def add(self, kind, text):
        self.lines.append((kind, text))

    def set_status(self, status, text=''):
        self.statuses.append((status, text))

    def step(self):
        return True


def wait(condition, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class ClientFeed(unittest.TestCase):
    def test_the_client_feeds_the_console(self):
        from test_ap_client import FakeSocket, MANIFEST, connected_packet
        from oot_rando.archipelago.bridge import GAME
        socket, console = FakeSocket(), FakeConsole()
        client = ap.ArchipelagoClient(MANIFEST, 'localhost:38281', connect=lambda url, **options: socket,
                                      console=console)
        self.addCleanup(client.stop)
        self.assertEqual(client.console_status(), (cb.STATUS_DISCONNECTED, ''))
        client.start()
        socket.push({'cmd': 'RoomInfo', 'seed_name': 'S', 'games': [GAME]})
        self.assertTrue(wait(lambda: socket.commands('Connect')))
        self.assertEqual(client.console_status(), (cb.STATUS_CONNECTING, 'localhost:38281 as Moi'))
        socket.push(connected_packet())
        self.assertTrue(wait(lambda: client.connected))
        self.assertEqual(client.console_status(), (cb.STATUS_CONNECTED, 'localhost:38281 as Moi'))
        socket.push({'cmd': 'PrintJSON', 'type': 'ItemSend', 'receiving': 1, 'item': {'player': 2, 'item': 7},
                     'data': [{'type': 'player_id', 'text': '2'}, {'text': ' sent you a Bow'}]},
                    {'cmd': 'PrintJSON', 'type': 'ItemSend', 'receiving': 3, 'item': {'player': 2, 'item': 7},
                     'data': [{'text': 'Ami sent Bow to Someone'}]},
                    {'cmd': 'PrintJSON', 'type': 'Chat', 'data': [{'text': 'Ami: hello'}]})
        self.assertTrue(wait(lambda: len(console.lines) == 3))
        self.assertEqual(console.lines, [(cb.KIND_RECEIVED, 'Ami sent you a Bow'), (cb.KIND_OTHERS, 'Ami sent Bow to Someone'),
                                         (cb.KIND_CHAT, 'Ami: hello')])
        self.assertTrue(wait(lambda: (cb.STATUS_CONNECTED, 'localhost:38281 as Moi') in console.statuses))
        client.stop()
        self.assertTrue(wait(lambda: console.statuses[-1] == (cb.STATUS_DISCONNECTED, '')))

    def test_a_seed_without_an_id_has_no_console(self):
        from test_ap_client import MANIFEST
        self.assertIsNone(ap.ArchipelagoClient(MANIFEST, 'localhost:1').console)
        self.assertIsNone(ap.ArchipelagoClient({**MANIFEST, 'seed_id': SEED * 4}, 'localhost:1',
                                               console=False).console)


class ConnectionFile(unittest.TestCase):
    def test_written_and_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(autoconnect.read(folder))
            autoconnect.write(folder, ' archipelago.gg:38281 ', 'Link ', 'pass word', True)
            self.assertEqual(json.loads((Path(folder) / autoconnect.FILE_NAME).read_text(encoding='utf-8')),
                             {'server': 'archipelago.gg:38281', 'slot': 'Link', 'password': 'pass word',
                              'auto_connect': True})
            self.assertEqual(autoconnect.read(folder)['password'], 'pass word')
            self.assertFalse((Path(folder) / (autoconnect.FILE_NAME + '.tmp')).exists())
            self.assertEqual(autoconnect.raw(folder), (Path(folder) / autoconnect.FILE_NAME).read_bytes())

    def test_a_file_edited_by_hand_badly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / autoconnect.FILE_NAME
            path.write_text('{"server": "host:1", "slot": 5, "auto_connect": "yes"}', encoding='utf-8')
            self.assertEqual(autoconnect.read(folder), {'server': 'host:1', 'slot': '', 'password': '',
                                                        'auto_connect': False})
            for text in ('not json', '[1, 2]', ''):
                path.write_text(text, encoding='utf-8')
                self.assertIsNone(autoconnect.read(folder))


if __name__ == '__main__':
    unittest.main()
