"""Archipelago client: protocol flow against a scripted server (no network)."""
import _src_path  # noqa: F401  (src on sys.path)
import json
import queue
import threading
import time
import unittest

from oot_rando.archipelago import client as ap
from oot_rando.archipelago.bridge import GAME

MANIFEST = {'archipelago': {'slot_name': 'Moi', 'location_ids': {'A#1': 11, 'A#2': 12, 'A#3': 13}},
            'settings': {'archipelago': {'seed_key': 'key-1'}}}


class FakeSocket:
    """Server side scripted by the test: ``push`` packets, read what the client ``sent``."""

    def __init__(self):
        self.inbox, self.sent, self.closed = queue.Queue(), [], False
        self.lock = threading.Lock()

    def push(self, *packets):
        self.inbox.put(json.dumps(list(packets)))

    def recv(self, timeout=None):
        try:
            return self.inbox.get(timeout=min(timeout or 0.05, 0.05))
        except queue.Empty:
            raise TimeoutError from None

    def send(self, text):
        with self.lock:
            self.sent.extend(json.loads(text))

    def close(self):
        self.closed = True

    def commands(self, cmd):
        with self.lock:
            return [p for p in self.sent if p['cmd'] == cmd]


def wait(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def connected_packet(**changes):
    packet = {'cmd': 'Connected', 'team': 0, 'slot': 1, 'checked_locations': [11],
              'missing_locations': [12, 13], 'slot_data': {'seed_key': 'key-1'},
              'players': [{'team': 0, 'slot': 1, 'alias': 'Moi', 'name': 'Moi'},
                          {'team': 0, 'slot': 2, 'alias': 'Ami', 'name': 'Ami'}],
              'slot_info': {'1': {'name': 'Moi', 'game': GAME, 'type': 1},
                            '2': {'name': 'Ami', 'game': 'APQuest', 'type': 1}}}
    packet.update(changes)
    return packet


class Units(unittest.TestCase):
    def test_server_urls(self):
        self.assertEqual(ap.server_urls('archipelago.gg:38281'),
                         ['wss://archipelago.gg:38281', 'ws://archipelago.gg:38281'])
        self.assertEqual(ap.server_urls('localhost'), ['wss://localhost:38281', 'ws://localhost:38281'])
        self.assertEqual(ap.server_urls('/connect host:1234'), ['wss://host:1234', 'ws://host:1234'])
        self.assertEqual(ap.server_urls('ws://h:1'), ['ws://h:1'])
        with self.assertRaises(ap.ClientError):
            ap.server_urls('  ')

    def test_plain_fallback_only_for_a_server_without_tls(self):
        import ssl
        attempts = []

        def failing(error):
            def connect(url, **options):
                attempts.append((url, options.get('max_size')))
                if url.startswith('wss://'):
                    raise error
                return object()
            return connect
        # Certificate that does not verify: never retried unencrypted.
        client = ap.ArchipelagoClient(MANIFEST, 'host:1', connect=failing(ssl.SSLCertVerificationError('bad')))
        with self.assertRaisesRegex(ap.ClientError, 'certificate'):
            client._open()
        self.assertEqual([u for u, _ in attempts], ['wss://host:1'])
        # Server without TLS: plain WebSocket, marked unencrypted...
        attempts.clear()
        client = ap.ArchipelagoClient(MANIFEST, 'host:1', connect=failing(ssl.SSLError('wrong version number')))
        client._open()
        self.assertEqual([u for u, _ in attempts], ['wss://host:1', 'ws://host:1'])
        self.assertIs(client.encrypted, False)
        self.assertTrue(all(size == ap.MAX_MESSAGE for _, size in attempts))
        # ...but never with a password unless ws:// was typed.
        attempts.clear()
        client = ap.ArchipelagoClient(MANIFEST, 'host:1', 'secret', connect=failing(ssl.SSLError('wrong version')))
        with self.assertRaisesRegex(ap.ClientError, 'ws://host:1'):
            client._open()
        self.assertEqual([u for u, _ in attempts], ['wss://host:1'])
        client = ap.ArchipelagoClient(MANIFEST, 'ws://host:1', 'secret', connect=failing(AssertionError()))
        client._open()
        self.assertIs(client.encrypted, False)
        # Other failures (refused, timeout) are not a reason to go unencrypted.
        client = ap.ArchipelagoClient(MANIFEST, 'host:1', connect=failing(TimeoutError('timed out')))
        with self.assertRaises(TimeoutError):
            client._open()

    def test_reporter_sends_each_new_check_once(self):
        reporter = ap.LocationReporter({'A#1': 11, 'A#2': 12, 'B': 99})
        reporter.reset_connection([11])
        self.assertEqual(reporter.pending({'A#1', 'A#2', 'not-ap'}), [12])
        reporter.sent.add(12)
        self.assertEqual(reporter.pending({'A#1', 'A#2'}), [])
        self.assertEqual(reporter.counts({'A#2'}), (2, 3))

    def test_not_an_archipelago_seed(self):
        with self.assertRaises(ap.ClientError):
            ap.archipelago_info({'settings': {}})

    def test_render(self):
        names = lambda kind, value, player: f'<{kind}:{value}:{player}>'
        parts = [{'type': 'player_id', 'text': '2'}, {'text': ' found '},
                 {'type': 'item_id', 'text': '5', 'player': 1}]
        self.assertEqual(ap.render(parts, names), '<player:2:None> found <item:5:1>')


class Flow(unittest.TestCase):
    def start(self, **kwargs):
        self.socket = FakeSocket()
        self.urls = []

        def connect(url, **options):
            self.urls.append(url)
            return self.socket
        self.client = ap.ArchipelagoClient(MANIFEST, 'localhost:38281', connect=connect, **kwargs)
        self.addCleanup(self.client.stop)
        self.client.start()
        self.socket.push({'cmd': 'RoomInfo', 'seed_name': 'S', 'games': ['APQuest', GAME]})
        self.assertTrue(wait(lambda: self.socket.commands('Connect')))

    def test_connect_checks_and_goal(self):
        self.start()
        connect = self.socket.commands('Connect')[0]
        self.assertEqual((connect['game'], connect['name'], connect['items_handling']), (GAME, 'Moi', 0b111))
        self.assertEqual(self.socket.commands('GetDataPackage')[0]['games'], sorted(['APQuest', GAME]))
        self.client.update({'A#1', 'A#2'}, False)
        self.socket.push(connected_packet())
        self.assertTrue(wait(lambda: self.socket.commands('LocationChecks')))
        self.assertEqual(self.socket.commands('LocationChecks')[0]['locations'], [12])   # 11: server had it
        self.client.update({'A#1', 'A#2', 'A#3'}, True)
        self.assertTrue(wait(lambda: len(self.socket.commands('LocationChecks')) == 2
                             and self.socket.commands('StatusUpdate')))
        self.assertEqual(self.socket.commands('LocationChecks')[1]['locations'], [13])
        self.client.update({'A#1', 'A#2', 'A#3'}, True)
        time.sleep(0.3)
        self.assertEqual(len(self.socket.commands('StatusUpdate')), 1)
        self.assertEqual(self.socket.commands('StatusUpdate')[0]['status'], ap.CLIENT_GOAL)
        summary = self.client.summary()
        self.assertEqual((summary['checks'], summary['total'], summary['goal']), (3, 3, True))

    def test_received_items_and_resync(self):
        self.start()
        self.socket.push(connected_packet(),
                         {'cmd': 'DataPackage', 'data': {'games': {
                             GAME: {'item_name_to_id': {'Bow': 7}, 'location_name_to_id': {'Mido': 11}},
                             'APQuest': {'item_name_to_id': {}, 'location_name_to_id': {'Chest': 50}}}}},
                         {'cmd': 'ReceivedItems', 'index': 0, 'items': [
                             {'item': 7, 'location': 50, 'player': 2, 'flags': 1},
                             {'item': 7, 'location': 11, 'player': 1, 'flags': 1}]})
        self.assertTrue(wait(lambda: len(self.client.received) == 2))
        self.assertEqual(self.client.received_rows()[0], ('Bow', 'Ami', 'Chest', True))
        self.assertEqual(self.client.received_rows()[1][3], False)    # found in this game
        self.assertEqual(self.client.summary()['from_other_worlds'], 1)
        from oot_rando.patching.ap_mailbox import record_key
        # Items found in this world have keys too (dynamic progressive copies).
        own = self.client.received_keys()[1]
        self.assertEqual(self.client.received_keys()[0], record_key('Ami', 'Chest'))
        self.assertEqual(len(self.client.received_keys()), 2)
        self.assertNotEqual(own, record_key('Ami', 'Chest'))
        self.socket.push({'cmd': 'ReceivedItems', 'index': 5, 'items': [{'item': 7, 'location': 1, 'player': 2}]})
        self.assertTrue(wait(lambda: self.socket.commands('Sync')))
        self.assertEqual(len(self.client.received), 2)

    def test_chat_and_messages(self):
        self.start()
        self.socket.push(connected_packet())
        self.client.say('!hint Bow')
        self.assertTrue(wait(lambda: self.socket.commands('Say')))
        self.assertEqual(self.socket.commands('Say')[0]['text'], '!hint Bow')
        self.socket.push({'cmd': 'PrintJSON', 'data': [{'type': 'player_id', 'text': '2'}, {'text': ' joined'}]})
        self.assertTrue(wait(lambda: 'Ami joined' in self.client.log))

    def test_wrong_slot_is_fatal(self):
        self.start()
        self.socket.push({'cmd': 'ConnectionRefused', 'errors': ['InvalidSlot']})
        self.assertTrue(wait(lambda: self.client.fatal))
        self.assertIn('slot name unknown', self.client.status)

    def test_other_multiworld_is_fatal(self):
        self.start()
        self.socket.push(connected_packet(slot_data={'seed_key': 'other'}))
        self.assertTrue(wait(lambda: self.client.fatal))
        self.assertFalse(self.client.connected)

    def test_disconnect_retries_and_resends(self):
        self.start()
        self.client.update({'A#2'}, False)
        self.socket.push(connected_packet())
        self.assertTrue(wait(lambda: self.socket.commands('LocationChecks')))
        # The server dropped: a new session resends what it does not confirm.
        old = self.socket
        self.socket = FakeSocket()
        old.inbox.put('not json')            # parse error ends the session
        self.client_retry = ap.RETRY_SECONDS
        ap.RETRY_SECONDS = 0.05
        self.addCleanup(setattr, ap, 'RETRY_SECONDS', self.client_retry)
        self.assertTrue(wait(lambda: len(self.urls) >= 2))
        self.socket.push({'cmd': 'RoomInfo', 'games': [GAME]}, connected_packet())
        self.assertTrue(wait(lambda: self.socket.commands('LocationChecks')))
        self.assertEqual(self.socket.commands('LocationChecks')[0]['locations'], [12])


if __name__ == '__main__':
    unittest.main()
