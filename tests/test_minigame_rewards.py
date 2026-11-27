"""First-success rewards of the multi-level mini-games (patching/minigame_rewards.py). Needs OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import minigame_rewards as m
from oot_rando.patching import story_fixes
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class MinigameRewards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.nup.latest('romfs/' + path)), self.d)

    @staticmethod
    def chart(raw):
        return {e.name: e for e in parse_flow(raw).flowchart.events}

    def check_kept(self, source, raw, changed=()):
        before, after = params_by_event(parse_flow(source)), params_by_event(parse_flow(raw))
        for name in changed:
            before[name] = after[name]
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    @staticmethod
    def follow(events, name, steps=12):
        """Names met from ``name`` along single continuations."""
        seen = []
        event = events[name]
        for _ in range(steps):
            seen.append(event.name)
            following = getattr(event.data, 'nxt', None)
            if following is None or following.v is None:
                break
            event = following.v
        return seen

    def test_bowling_first_win_gives_the_three_prizes(self):
        source = self.read(m.BOWLING_FLOW)
        raw, report = m.bowling_all_prizes(source)
        events = self.chart(raw)
        self.assertEqual(self.follow(events, 'Event309'), ['Event309', 'Event76'])
        self.assertEqual({c.v.name for c in events['Event76'].data.cases.values()}, {'Event304', 'Event306'})
        self.assertEqual(self.follow(events, 'Event304')[:3], ['Event304', 'Event143', 'Event93'])
        self.assertEqual(self.follow(events, 'Event306')[:3], ['Event306', 'Event143', 'Event93'])
        self.assertEqual(self.follow(events, 'Event143')[:2], ['Event143', 'Event93'])
        self.assertEqual(self.follow(events, 'Event89'),
                         ['Event89', 'RandoBowlingClearSecond', 'RandoBowlingClearThird', 'Event92'])
        for name, flag in (('RandoBowlingClearSecond', m.BOWLING_FLAGS[1]), ('RandoBowlingClearThird', m.BOWLING_FLAGS[2])):
            self.assertEqual(events[name].data.params.data, {'GameDataName': flag, 'Index': -1, 'Value': True})
        self.assertEqual(report['chain'], ['Event309', 'Event76', 'Event143'])
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):    # never applied twice
            m.bowling_all_prizes(raw)

    def test_memory_game_first_session_gives_both_rupees_and_the_heart_piece(self):
        source = self.read(m.SKULL_KID_FLOW)
        raw, _ = m.skull_kid_all_rewards(source)
        events = self.chart(raw)
        self.assertEqual(self.follow(events, 'Event22')[:5], ['Event22', 'Event204', 'Event23', 'Event202', 'Event64'])
        self.assertEqual(events['Event64'].data.cases[1].v.name, 'Event24')     # heart piece not got yet
        self.assertEqual(events['Event64'].data.cases[0].v.name, 'Event154')    # repeat: blue rupee
        self.assertEqual(self.follow(events, 'Event24')[:2], ['Event24', 'Event58'])
        # The next session is the last grade: its win only pays the repeat reward.
        self.assertEqual(events['Event11'].data.params.data['Value'], m.SKULL_KID_LAST_GRADE)
        self.check_kept(source, raw, changed=('Event11',))
        with self.assertRaises(ValueError):
            m.skull_kid_all_rewards(raw)

    def test_archery_heart_piece_also_gives_the_quiver(self):
        source = self.read(m.ARCHERY_FLOW)
        raw, _ = m.archery_all_prizes(source)
        events = self.chart(raw)
        self.assertEqual(self.follow(events, 'Event117')[:3], ['Event117', 'Event110', 'Event297'])
        self.assertEqual(events['Event119'].data.nxt.v.name, 'Event110')    # 1400 points: unchanged
        self.check_kept(source, raw)
        again, _ = m.archery_all_prizes(raw)     # the wiring is idempotent
        self.assertEqual(self.follow(self.chart(again), 'Event117')[:2], ['Event117', 'Event110'])

    def test_gifts_followed_through_collection_markers(self):
        """The item edit and the collection markers run first: a marker after a gift is kept."""
        from oot_rando.patching.event_patch import add_collection_markers
        source = self.read(m.BOWLING_FLOW)
        marked, _ = add_collection_markers(source, {'Event304': 'RandoTest_Bag', 'Event306': 'RandoTest_Bag',
                                                    'Event143': 'RandoTest_Heart'})
        raw, _ = m.bowling_all_prizes(marked)
        events = self.chart(raw)
        self.assertEqual(self.follow(events, 'Event304')[:4],
                         ['Event304', 'RandoCollected_Event304', 'Event143', 'RandoCollected_Event143'])
        self.assertEqual(self.follow(events, 'Event306')[:3],
                         ['Event306', 'RandoCollected_Event306', 'Event143'])
        self.assertIn('Event93', self.follow(events, 'Event143'))    # still ends in the clear count

    def test_registered_as_story_fixes(self):
        keys = {key: path for path, key, _ in story_fixes.flow_fixes(story_fixes.escape_stones({}))}
        for path, key, _ in m.FIXES:
            self.assertEqual(keys[key], path)


if __name__ == '__main__':
    unittest.main()
