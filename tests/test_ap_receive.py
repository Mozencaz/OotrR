"""Handing received items to the game: which one to signal, when to signal again."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.archipelago.receive import ASIDE_SECONDS, MAX_SIGNALS, RETRY_SECONDS, Deliverer, received_keys

RECORDS = [{'key': k, 'recv': 'RandoAP.Recv.' + k, 'got': 'RandoAP.Got.' + k, 'item': k, 'player': 'Ami'}
           for k in ('a', 'b')]
H = {'RandoAP.Recv.a': 1, 'RandoAP.Got.a': 2, 'RandoAP.Recv.b': 3, 'RandoAP.Got.b': 4}


class DelivererTests(unittest.TestCase):
    def setUp(self):
        self.d = Deliverer(RECORDS, H.__getitem__)

    def test_one_at_a_time_then_retry(self):
        bools = {1: False, 2: False, 3: False, 4: False}
        self.assertEqual(self.d.step(['a', 'b'], bools, 0.0), 'a')
        self.assertIsNone(self.d.step(['a', 'b'], bools, 1.0))            # waiting for the game
        self.assertEqual(self.d.step(['a', 'b'], bools, RETRY_SECONDS + 0.1), 'a')   # signal lost: again
        bools[2] = True                                                     # a handed over
        self.assertEqual(self.d.step(['a', 'b'], bools, RETRY_SECONDS + 0.2), 'b')

    def test_an_item_never_taken_does_not_block_the_next(self):
        bools = {1: False, 2: False, 3: False, 4: False}
        now = 0.0
        for _ in range(MAX_SIGNALS):
            self.assertEqual(self.d.step(['a', 'b'], bools, now), 'a')
            now += RETRY_SECONDS + 0.1
        self.assertEqual(self.d.step(['a', 'b'], bools, now), 'b')        # a set aside
        self.assertEqual([r['key'] for r in self.d.take_stuck()], ['a'])
        self.assertEqual(self.d.take_stuck(), [])                           # reported once
        bools[4] = True                                                     # b handed over
        self.assertIsNone(self.d.step(['a', 'b'], bools, now + RETRY_SECONDS + 1))   # a waits its pause
        later = now + ASIDE_SECONDS + 1
        self.assertEqual(self.d.step(['a', 'b'], bools, later), 'a')       # then is tried again
        for _ in range(MAX_SIGNALS - 1):
            later += RETRY_SECONDS + 0.1
            self.assertEqual(self.d.step(['a', 'b'], bools, later), 'a')   # with a fresh count
        bools[2] = True
        self.assertIsNone(self.d.step(['a', 'b'], bools, later + RETRY_SECONDS + 1))
        self.assertEqual(self.d.aside, {})

    def test_no_second_signal_while_one_is_unconsumed(self):
        bools = {1: False, 2: False, 3: False, 4: False}
        self.assertEqual(self.d.step(['a', 'b'], bools, 0.0), 'a')
        bools[1] = True                                                     # game paused: Recv kept
        self.assertIsNone(self.d.step(['a', 'b'], bools, 1000.0))           # never races it with b
        bools[1], bools[2] = False, True                                    # unpaused, a taken
        self.assertEqual(self.d.step(['a', 'b'], bools, 1001.0), 'b')

    def test_nothing_without_the_flags_or_when_held(self):
        self.assertIsNone(self.d.step(['a'], {}, 0.0))                       # another seed / no save
        self.assertIsNone(self.d.step(['a'], {1: False, 2: True}, 0.0))      # already in game
        self.assertIsNone(self.d.step(['x'], {1: False, 2: False}, 0.0))     # unknown item
        self.assertIsNone(self.d.step(['a'], {1: True, 2: False}, 0.0))      # signal not consumed yet

    def test_received_keys(self):
        from oot_rando.patching.ap_mailbox import record_key
        entries = [{'item': 1, 'location': 5, 'player': 2}, {'item': 1, 'location': 6, 'player': 1},
                   {'item': 1, 'location': -2, 'player': 0}]
        keys = received_keys(entries, 1, lambda s: {1: 'Moi', 2: 'Ami'}[s], lambda loc, s: f'L{loc}')
        self.assertEqual(keys, [record_key('Ami', 'L5'), record_key('Moi', 'L6')])   # server items: none


class SharedMailboxTests(unittest.TestCase):
    def delivery(self, shared=True):
        from oot_rando.archipelago.receive import LiveDelivery
        from oot_rando.patching.ap_mailbox import SIGNAL
        from oot_rando.patching.soul_adapter import murmur3
        from types import SimpleNamespace
        mailbox = {'items': RECORDS}
        if shared:
            mailbox['signal'] = SIGNAL
        delivery = LiveDelivery({'seed_id': 'test', 'skips': {'ap_mailbox': mailbox}}, clock=lambda: self.now)
        self.now = 0
        self.bools = {delivery.marker: True}
        for record in RECORDS:
            self.bools.update({murmur3(record['recv']): False, murmur3(record['got']): False})
        self.bools[murmur3(SIGNAL)] = False
        delivery.live = SimpleNamespace(snapshot=lambda: {'bool': dict(self.bools)})
        return delivery

    def test_signal_order_pause_dropped_event_retry_and_receipt(self):
        from unittest.mock import patch
        d = self.delivery()
        writes = []
        def write(live, key, value):
            writes.append(key)
            self.bools[key] = value
        with patch('oot_rando.tracker.live_memory.set_bool_in', side_effect=write):
            self.assertEqual(d.step(['a', 'b'])['key'], 'a')
            self.assertEqual(writes, [d.deliverer.recv['a'], d.signal])
            self.now += RETRY_SECONDS + 1
            self.assertIsNone(d.step(['a', 'b']))  # game paused: request not consumed
            self.bools[d.signal] = False  # request consumed, event dropped; Recv stays true
            self.assertEqual(d.step(['a', 'b'])['key'], 'a')
            self.bools[d.signal] = False
            self.bools[d.deliverer.got['a']] = True
            self.assertEqual(d.step(['a', 'b'])['key'], 'b')
            self.bools[d.signal] = False
            self.bools[d.deliverer.got['b']] = True
            self.assertIsNone(d.step(['a', 'b']))

    def test_partial_write_failure_can_be_retried(self):
        from unittest.mock import patch
        from oot_rando.tracker.live_memory import LiveUnavailable
        d = self.delivery()
        def write(live, key, value):
            if key == d.signal:
                raise LiveUnavailable('interrupted')
            self.bools[key] = value
        with patch('oot_rando.tracker.live_memory.set_bool_in', side_effect=write):
            self.assertIsNone(d.step(['a']))
        self.now += RETRY_SECONDS + 1
        with patch('oot_rando.tracker.live_memory.set_bool_in') as write:
            self.assertEqual(d.step(['a'])['key'], 'a')
            self.assertEqual(write.call_count, 2)

    def test_old_seed_still_uses_only_the_item_flag(self):
        from unittest.mock import patch
        d = self.delivery(shared=False)
        with patch('oot_rando.tracker.live_memory.set_bool_in') as write:
            self.assertEqual(d.step(['a'])['key'], 'a')
            write.assert_called_once_with(d.live, d.deliverer.recv['a'], True)


if __name__ == '__main__':
    unittest.main()
