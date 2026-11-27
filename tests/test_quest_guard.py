"""Quest floor guard (patching/quest_guard.py). Flow tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching import quest_guard as q
from oot_rando.patching.story_fixes import _Chart
from oot_rando.formats.evfl_tools import event_params_of

NUP = os.environ.get('OOT_NUP')
STEPS = {'Quest': ['Ready', 'Step01', 'Step02', 'Step03']}


class Units(unittest.TestCase):
    def test_challenge_table(self):
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': [
            {'__RowId': 'Work/Challenge/Quest.game__challenge__Challenge.gyml',
             'Steps': [{'Name': s} for s in STEPS['Quest']]}]})
        self.assertEqual(q.challenge_steps(raw), STEPS)

    def test_floor_reads_the_step_before(self):
        self.assertEqual(q.floor_expression(STEPS, 'Quest', 'Step02'), 'Quest_IsAfter_Step01_Exp')
        for challenge, floor in (('Quest', 'Ready'), ('Quest', 'Step09'), ('Other', 'Step01')):
            with self.subTest(floor=floor), self.assertRaises(ValueError):
                q.floor_expression(STEPS, challenge, floor)


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup, d = Nup(NUP), None
        d = dictionaries(nup)
        cls.read = staticmethod(lambda path: decompress(nup.read(nup.latest('romfs/' + path)), d))
        cls.steps = q.challenge_steps(cls.read(q.CHALLENGES))
        cls.gamedata = cls.read('GameData/GameDataList.Product.110.byml.zs')

    def test_story_quest_expressions_exist(self):
        # The main story quests have an IsAfter expression for every step, so any
        # of their steps can be a floor (several mini-games and side quests do not).
        for challenge in ('Meet_DekuTree', 'Get_StoneOfForest', 'Get_StoneOfFire', 'Get_StoneOfWater',
                          'Goto_HyruleCastle', 'DoorOfTime', 'SageOfForest'):
            with self.subTest(challenge=challenge):
                q.check_expressions(self.gamedata, [q.after_expression(challenge, s)
                                                    for s in self.steps[challenge]])
        with self.assertRaises(ValueError):
            q.check_expressions(self.gamedata, ['SubEvent_MaskSalesman_IsAfter_UntilRentMaskOfKeaton_Exp'])

    def test_missing_expression_refused(self):
        raw = self.read('Event/EventFlow/Get_Epona.bfevfl.zs')
        order = self.steps['Get_Epona']
        floor = order[order.index('GuideToLonLonRanch') + 1]
        with self.assertRaises(ValueError):
            q.guard_regressions(raw, 'Get_Epona', self.steps, floor, gamedata_raw=self.gamedata)

    def test_zora_quest_kept_at_king_zora_moved(self):
        path = 'Event/EventFlow/Get_StoneOfWater.bfevfl.zs'
        raw = self.read(path)
        before = {name: step for name, step in q.step_requests(raw, 'Get_StoneOfWater')}
        out, report = q.guard_regressions(raw, 'Get_StoneOfWater', self.steps, 'Step07', self.gamedata)
        self.assertEqual(report['expression'], 'Get_StoneOfWater_IsAfter_Step06_Exp')
        order = self.steps['Get_StoneOfWater']
        early = {n for n, s in before.items() if order.index(s) < order.index('Step07')}
        self.assertEqual({event for event, _, _ in report['guarded']}, early)
        chart = _Chart(out).chart
        events = {e.name: e for e in chart.events}
        for event, step, resume in report['guarded']:
            guard = next(e for e in chart.events if e.name.startswith(q.PREFIX)
                         and e.data.cases[1].v.name == event)
            self.assertEqual(event_params_of(guard), {'GameDataName': report['expression']})
            # Nothing reaches the request without passing the guard.
            for other in chart.events:
                if other is not guard and getattr(other.data, 'nxt', None) is not None:
                    self.assertIsNot(other.data.nxt.v, events[event], other.name)
        # Later steps (the floor and beyond) are left alone.
        late = set(before) - early
        self.assertTrue(late)
        self.assertFalse(late & {event for event, _, _ in report['guarded']})
        with self.assertRaises(ValueError):
            q.guard_regressions(out, 'Get_StoneOfWater', self.steps, 'Step07')

    def test_flow_without_early_request_unchanged(self):
        raw = self.read('Event/EventFlow/Get_StoneOfWater.bfevfl.zs')
        out, report = q.guard_regressions(raw, 'Get_StoneOfWater', self.steps, 'Step02')
        self.assertTrue(report['guarded'])          # Step01 requests exist
        raw = self.read('Event/EventFlow/MiniGame_Diving.bfevfl.zs')
        out, report = q.guard_regressions(raw, 'Get_StoneOfWater', self.steps, 'Step07')
        self.assertIs(out, raw)
        self.assertEqual(report['guarded'], [])


if __name__ == '__main__':
    unittest.main()
