"""Replay King Zora's post-Morpha gift route from the native event files."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import decompress, dictionaries
from oot_rando.formats.evfl_tools import params_by_event, parse_flow
from oot_rando.patching import story_fixes as s

NUP = os.environ.get('OOT_NUP')
NPC = 'Event/EventFlow/Npc_Zora_KingZora_adult.bfevfl.zs'
WATER = s.SAGE_OF_WATER_FLOW
GIVEN = 'SageOfWater_KingZora_adult_Talk_Event198'


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class KingZoraGift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.sources = {p: decompress(cls.nup.read(cls.nup.latest('romfs/' + p)), cls.d)
                       for p in (NPC, WATER)}

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def patched(self):
        result = dict(self.sources)
        for path, _, fix in s.flow_fixes(s.STONE_SETS['all']):
            if path in result:
                result[path] = fix(result[path])[0]
        return result

    def replay(self, resources, entry, completed, given):
        charts = {p.split('/')[-1].split('.')[0]: parse_flow(raw).flowchart
                  for p, raw in resources.items()}
        flags = {GIVEN: given}
        rewards = []
        # Only the new fallback is under test; reaching a vanilla talk root ends
        # this replay. The native post-completion roots contain no tunic gift.
        roots = {'Event38', 'Event113'}
        def run(chart, event):
            for _ in range(100):
                if event is None:
                    return
                if chart is charts['Npc_Zora_KingZora_adult'] and event.name in roots:
                    return
                data = event.data
                params = getattr(getattr(data, 'params', None), 'data', None) or {}
                kind = type(data).__name__
                if kind == 'SwitchEvent':
                    query = str(data.actor_query.v)
                    if query == 'EventQueryIsGameDataBool':
                        value = flags.get(params['GameDataName'], False)
                    elif query == 'EventQueryIsGameDataBoolExp':
                        self.assertIn(params['GameDataName'],
                                      ('SageOfWater_IsCompleted_Exp', 'SageOfWater_IsAfter_Step05_Exp'))
                        value = completed
                    else:
                        self.fail('Unexpected query in gift route: ' + query)
                    target = data.cases.get(0 if value else 1)
                    event = target.v if target else None
                    continue
                if kind == 'SubFlowEvent':
                    if params.get('ActorName') == 'Obj_Armor_Zora':
                        rewards.append((chart.name, event.name))
                    elif data.res_flowchart_name in charts:
                        target_chart = charts[data.res_flowchart_name]
                        target = next(e for e in target_chart.entry_points
                                      if e.name == data.entry_point_name)
                        run(target_chart, target.main_event.v)
                elif kind == 'ActionEvent':
                    action = str(data.actor_action.v)
                    if action == 'EventTriggerSetGameDataBool':
                        flags[params['GameDataName']] = params['Value']
                    self.assertNotEqual(action, 'EventExecuteProgressChallengeStep',
                                        'Gift must not rewind the completed Water quest')
                else:
                    self.fail('Unexpected event: ' + kind)
                event = getattr(getattr(data, 'nxt', None), 'v', None)
            self.fail('Gift route did not terminate')
        chart = charts['Npc_Zora_KingZora_adult']
        run(chart, next(e for e in chart.entry_points if e.name == entry).main_event.v)
        return rewards, flags[GIVEN]

    def test_unclaimed_gift_survives_morpha_first_and_is_given_once(self):
        resources = self.patched()
        for entry in ('Talk', 'IrregularTalk'):
            with self.subTest(entry=entry):
                rewards, given = self.replay(resources, entry, completed=True, given=False)
                self.assertEqual(rewards, [('SageOfWater', 'Event242')])
                self.assertTrue(given)
                self.assertEqual(self.replay(resources, entry, True, given)[0], [])

    def test_before_morpha_and_claimed_gifts_keep_native_talk(self):
        resources = self.patched()
        for entry in ('Talk', 'IrregularTalk'):
            for completed, given in ((False, False), (False, True), (True, True)):
                with self.subTest(entry=entry, completed=completed, given=given):
                    self.assertEqual(self.replay(resources, entry, completed, given), ([], given))

    def test_native_reward_site_and_parameters_are_preserved(self):
        resources = self.patched()
        for path, original in self.sources.items():
            before, after = params_by_event(parse_flow(original)), params_by_event(parse_flow(resources[path]))
            # Serenade's existing patch adds guards but preserves native parameters.
            self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        water = parse_flow(resources[WATER]).flowchart
        gifts = [e.name for e in water.events
                 if (getattr(getattr(e.data, 'params', None), 'data', None) or {}).get('ActorName')
                 == 'Obj_Armor_Zora']
        self.assertEqual(gifts, ['Event242'])
        self.assertTrue(any(key == 'king_zora_gift' for _, key, _ in s.flow_fixes(s.STONE_SETS['all'])))

    def test_fix_rejects_a_second_application(self):
        for path, fix in ((NPC, s.king_zora_gift_after_morpha), (WATER, s.king_zora_gift_entry)):
            patched, _ = fix(self.sources[path])
            with self.subTest(path=path), self.assertRaises(ValueError):
                fix(patched)


if __name__ == '__main__':
    unittest.main()
