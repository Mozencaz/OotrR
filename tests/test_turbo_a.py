"""Turbo A (hold A), skip with X, Hookshot bindings and the press rhythm."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.tracker import turbo_a
from oot_rando.tracker.turbo_a import (ATurbo, EventGate, SkipWithX, TurboClock, VIRTUAL_A, describe_hold, describe_skip,
                                       is_remapped, parse_binds, remap_ini, set_ini_lines, PAD_TO_XINPUT)
from oot_rando.tracker import live_memory

USER_INI = 'fullscreen=0\npad_a=0\nkey_a=69,0\npad_b=1\npad_x=2\nkey_x=32,0\npad_plus=6\nkey_plus=9,13\n'


class BindTests(unittest.TestCase):
    def test_user_ini_layout(self):
        binds = parse_binds(USER_INI)
        self.assertEqual(binds['pad_a'], 0)
        self.assertEqual(PAD_TO_XINPUT[binds['pad_x']], 0x4000)   # the pad's X (west) button
        self.assertEqual(binds['key_x'], (32, 0))
        self.assertEqual(binds['key_a'], (69, 0))
        self.assertEqual(binds['key_plus'], (9, 13))

    def test_defaults_without_ini(self):
        binds = parse_binds('')
        self.assertEqual(binds['pad_a'], 1)                 # Hookshot default: east button
        self.assertEqual(binds['pad_x'], 3)                 # Hookshot default: north button
        self.assertEqual(binds['key_a'], (ord('E'), 0))
        self.assertEqual(binds['key_move_up'], (ord('W'), 0))

    def test_unbound_and_garbage(self):
        binds = parse_binds('pad_x=-1\nkey_a=abc\nkey_x=300,32\n')
        self.assertIsNone(binds['pad_x'])
        self.assertEqual(binds['key_a'], (ord('E'), 0))     # unreadable line keeps the default
        self.assertEqual(binds['key_x'], (0, 32))


class RemapTests(unittest.TestCase):
    def test_a_goes_to_the_virtual_key_and_the_player_a_is_kept(self):
        text, player = remap_ini(USER_INI)
        self.assertEqual(player, {'pad_a': '0', 'key_a': '69,0'})
        binds = parse_binds(text)
        self.assertIsNone(binds['pad_a'])
        self.assertEqual(binds['key_a'], (VIRTUAL_A, 0))
        self.assertTrue(is_remapped(text))
        self.assertEqual(binds['pad_x'], 2)                  # nothing else changes
        self.assertIn('fullscreen=0', text)
        self.assertEqual(text.count('pad_a='), 1)

    def test_already_remapped_uses_the_saved_a(self):
        text, _ = remap_ini(USER_INI)
        again, player = remap_ini(text, {'pad_a': '0', 'key_a': '69,0'})
        self.assertEqual(again, text)
        self.assertEqual(player, {'pad_a': '0', 'key_a': '69,0'})
        _, fallback = remap_ini(text)                         # nothing saved: Hookshot's default A
        self.assertEqual(fallback, {'pad_a': '1', 'key_a': '69,0'})

    def test_missing_lines_are_added(self):
        text, player = remap_ini('fullscreen=1\n')
        self.assertTrue(is_remapped(text))
        self.assertEqual(player, {'pad_a': '1', 'key_a': '69,0'})

    def test_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'hookshot_options.ini').write_text(USER_INI, encoding='utf-8')
            turbo = turbo_a.TurboA(root, log_path=root / 't.log', state_path=root / 'app' / 'b.json',
                                   game_running=lambda: False)
            player = turbo.remap()
            self.assertEqual(player['pad_a'], 0)
            self.assertTrue(is_remapped((root / 'hookshot_options.ini').read_text(encoding='utf-8')))
            self.assertEqual(json.loads((root / 'app' / 'b.json').read_text(encoding='utf-8'))['key_a'], '69,0')
            # the app did not close: the next run still knows the player's A
            again = turbo_a.TurboA(root, log_path=root / 't.log', state_path=root / 'app' / 'b.json')
            self.assertEqual(again.remap()['key_a'], (69, 0))
            again.restore()
            self.assertEqual(parse_binds((root / 'hookshot_options.ini').read_text(encoding='utf-8'))['pad_a'], 0)
            self.assertEqual(set_ini_lines('pad_a=-1\n', {'pad_a': '0'}), 'pad_a=0\n')


class ClockTests(unittest.TestCase):
    def test_short_press_is_one_press(self):
        clock = TurboClock(press=0.05, release=0.05, delay=0.3)
        self.assertFalse(clock.a_down(False, 0.0))
        self.assertTrue(clock.a_down(True, 1.00))      # pressed at once
        self.assertTrue(clock.a_down(True, 1.29))      # still held before the turbo
        self.assertFalse(clock.a_down(False, 1.30))    # let go: up

    def test_taps_after_the_delay(self):
        clock = TurboClock(press=0.05, release=0.05, delay=0.3)
        self.assertTrue(clock.a_down(True, 1.00))
        self.assertTrue(clock.a_down(True, 1.31))      # first tap
        self.assertFalse(clock.a_down(True, 1.36))     # released between taps
        self.assertTrue(clock.a_down(True, 1.41))      # next tap
        self.assertTrue(clock.a_down(True, 1.46, turbo=False))   # plain hold asked: down

    def test_taps_are_long_enough_for_the_game(self):
        # 60 fps: both the press and the release must last more than one frame.
        self.assertGreater(turbo_a.PRESS_S, 1 / 60 * 2)
        self.assertGreater(turbo_a.RELEASE_S, 1 / 60 * 2)


class ATurboTests(unittest.TestCase):
    def run_hold(self, turbo, start, end, stick_from=None, step=0.01, event_of=lambda t: True):
        ups, now, down = 0, start, False
        while now < end:
            want = turbo.step(True, stick_from is not None and now >= stick_from, now, event_of(now))
            if down and not want:
                ups += 1
            down, now = want, now + step
        turbo.step(False, False, now)
        return ups

    def test_dialogue_hold_taps(self):
        turbo = ATurbo(delay=0.3)
        self.assertGreater(self.run_hold(turbo, 0.0, 1.3), 5)
        self.assertIn('taps', describe_hold(turbo.finished[0]))

    def test_short_press_never_taps(self):
        turbo = ATurbo(delay=0.3)
        self.assertEqual(self.run_hold(turbo, 0.0, 0.2), 0)

    def test_stick_moved_keeps_a_held(self):
        turbo = ATurbo(delay=0.3)
        self.assertEqual(self.run_hold(turbo, 0.0, 1.3, stick_from=0.1), 0)   # grab then pull a block
        self.assertIn('stick moved', describe_hold(turbo.finished[0]))
        self.assertGreater(self.run_hold(turbo, 2.0, 3.3), 5)                 # next hold: turbo again

    def test_free_play_hold_stays_held(self):
        turbo = ATurbo(delay=0.3)
        self.assertEqual(self.run_hold(turbo, 0.0, 2.0, event_of=lambda t: False), 0)   # diving
        self.assertIn('no event', describe_hold(turbo.finished[0]))
        self.assertEqual(self.run_hold(turbo, 3.0, 5.0, event_of=lambda t: None), 0)    # unreadable

    def test_flickering_event_keeps_the_turbo(self):
        turbo = ATurbo(delay=0.3, grace=0.5)
        self.assertGreater(self.run_hold(turbo, 0.0, 2.0, event_of=lambda t: t % 0.4 < 0.1), 10)

    def test_turbo_stops_once_the_event_is_over(self):
        turbo = ATurbo(delay=0.3, grace=0.5)
        self.run_hold(turbo, 0.0, 1.0)
        self.assertEqual(self.run_hold(turbo, 1.6, 3.0, event_of=lambda t: False), 0)   # (past the grace)


def run_press(skip, x_of, event_of, until, note_of=lambda t: False, dt=0.01):
    """(Plus presses, Plus time held) over [0, until)."""
    now, prev, edges, held = 0.0, False, 0, 0.0
    while now < until:
        plus = skip.step(x_of(now), note_of(now), event_of(now), now)
        edges += plus and not prev
        held += dt if plus else 0
        prev, now = plus, now + dt
    return edges, held


class SkipTests(unittest.TestCase):
    def test_x_tap_in_an_event_sends_one_plus_after_the_prompt(self):
        skip = SkipWithX(delay=0.25, hold=0.12)
        plus, held = run_press(skip, lambda t: t < 0.08, lambda t: True, 1.0)
        self.assertEqual(plus, 1)                        # a tap is enough (no hold)
        self.assertAlmostEqual(held, 0.12, delta=0.02)   # several frames
        self.assertIn('Plus sent', describe_skip(skip.finished[-1]))

    def test_plus_comes_after_the_delay(self):
        skip = SkipWithX(delay=0.25, hold=0.12)
        out = [skip.step(t < 5, False, True, t / 100) for t in range(60)]
        self.assertFalse(any(out[:25]))
        self.assertTrue(out[25])

    def test_x_held_is_still_one_plus(self):
        skip = SkipWithX()
        plus, _ = run_press(skip, lambda t: True, lambda t: True, 3.0)
        self.assertEqual(plus, 1)

    def test_each_press_sends_its_plus(self):
        skip = SkipWithX(delay=0.25, hold=0.12)
        plus, _ = run_press(skip, lambda t: t % 1.0 < 0.05, lambda t: True, 3.0)
        self.assertEqual(plus, 3)

    def test_free_play_or_unreadable_never_presses_plus(self):
        skip = SkipWithX()
        self.assertEqual(run_press(skip, lambda t: t < 0.05, lambda t: False, 1.0)[0], 0)   # an item
        self.assertIn('no event seen', describe_skip(skip.finished[-1]))
        skip = SkipWithX()
        self.assertEqual(run_press(skip, lambda t: t < 0.05, lambda t: None, 1.0)[0], 0)
        self.assertIn('unreadable', describe_skip(skip.finished[-1]))

    def test_a_flicker_after_the_press_still_skips(self):
        skip = SkipWithX(delay=0.25, decide=0.25)
        plus, _ = run_press(skip, lambda t: t < 0.05, lambda t: t > 0.1, 1.0)
        self.assertEqual(plus, 1)

    def test_ocarina_notes_cancel_and_latch_until_the_event_ends(self):
        skip = SkipWithX(delay=0.25, grace=0.5)
        def notes_of(t):
            note = t < 2.0 and t % 0.4 < 0.05
            return note and t % 0.8 >= 0.4, note and t % 0.8 < 0.4      # Y, X, Y, X…: a melody
        now, plus, prev = 0.0, 0, False
        while now < 3.5:
            x, y = notes_of(now)
            out = skip.step(x, y, now < 2.5, now, y=y)
            plus += out and not prev
            prev, now = out, now + 0.01
        self.assertEqual(plus, 0)
        self.assertTrue(any('ocarina' in describe_skip(r) for r in skip.finished))
        # The melody's event over: a later cutscene skips again.
        self.assertFalse(skip.latched)
        plus, _ = run_press(skip, lambda t: t < 0.05, lambda t: True, 1.0)
        self.assertEqual(plus, 1)

    def test_y_cancels(self):
        skip = SkipWithX(delay=0.25)
        now, plus = 0.0, 0
        while now < 1.0:
            y = 0.1 < now < 0.15
            plus += skip.step(now < 0.05, y, True, now, y=y)
            now += 0.01
        self.assertEqual(plus, 0)

    def test_x_again_or_a_still_skips(self):
        # 12/11 log: X tapped twice, or A between, latched "ocarina notes" and never skipped.
        skip = SkipWithX(delay=0.25, hold=0.12)
        plus, _ = run_press(skip, lambda t: t < 0.05 or 0.1 < t < 0.15, lambda t: True, 1.0)
        self.assertEqual(plus, 1)
        plus, _ = run_press(skip, lambda t: t < 0.05, lambda t: True, 1.0, note_of=lambda t: 0.1 < t < 0.15)
        self.assertEqual(plus, 1)
        self.assertFalse(skip.latched)

    def test_latch_ends_without_notes_even_if_the_event_stays(self):
        skip = SkipWithX(delay=0.25, idle=4.0)
        skip.step(False, True, True, 0.0, y=True)
        self.assertTrue(skip.latched)
        plus, _ = run_press(skip, lambda t: 5.0 <= t < 5.05, lambda t: True, 6.0)
        self.assertEqual(plus, 1)

    def test_event_read_only_around_a_press(self):
        skip = SkipWithX()
        self.assertFalse(skip.needs_event(False, 0.0))
        self.assertTrue(skip.needs_event(True, 0.0))      # the press itself
        skip.step(True, False, True, 0.0)
        self.assertTrue(skip.needs_event(True, 0.1))      # waiting for its Plus
        for t in range(1, 60):
            skip.step(True, False, True, t / 100)
        self.assertFalse(skip.needs_event(True, 0.7))     # held, Plus sent: nothing more to read


class EventGateTests(unittest.TestCase):
    def test_cached(self):
        calls, state = [], {'playing': False}
        gate = EventGate(lambda: calls.append(1) or state['playing'], ttl=0.1)
        self.assertFalse(gate.open(0.0))
        state['playing'] = True
        self.assertFalse(gate.open(0.05))           # cached
        self.assertTrue(gate.open(0.11))
        self.assertEqual(len(calls), 2)

    def test_unreadable_memory_is_unknown(self):
        def fail():
            raise live_memory.LiveUnavailable('game not running')
        gate = EventGate(fail)
        self.assertIsNone(gate.open(0.0))
        self.assertEqual(gate.error, 'game not running')


class LogTests(unittest.TestCase):
    def test_log_line_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            turbo = turbo_a.TurboA(folder, log_path=Path(folder) / 'turbo.log', state_path=Path(folder) / 'b.json')
            turbo._log('A held 1.00 s: 9 taps')
            self.assertIn('9 taps', (Path(folder) / 'turbo.log').read_text(encoding='utf-8'))
            self.assertIn('9 taps', turbo.last_hold)


class EventStateTests(unittest.TestCase):
    def test_event_word(self):
        self.assertTrue(live_memory.event_playing_from(0x10, 0x20, 0x8a000000))
        self.assertFalse(live_memory.event_playing_from(0x10, 0x20, 0))
        with self.assertRaises(live_memory.LiveUnavailable):
            live_memory.event_playing_from(0, 0, 0)

    def test_reads_the_manager_word_through_the_holder(self):
        import struct
        words = {live_memory.EVENTMGR_SLOT: 0x1000, 0x1000: 0x2000, 0x2000 + live_memory.EVENT_PLAYING_OFFSET: 7}

        class Memory:
            def attach(self):
                pass

            def close(self):
                pass

            def read(self, guest, size):
                return struct.pack('<Q', words.get(guest, 0))
        self.assertTrue(live_memory.LiveEventState(Memory()).playing())
        words[0x2000 + live_memory.EVENT_PLAYING_OFFSET] = 0
        self.assertFalse(live_memory.LiveEventState(Memory()).playing())


if __name__ == '__main__':
    unittest.main()
