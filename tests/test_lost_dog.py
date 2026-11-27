"""Market lost dog: early access and receipt-based one-time reward."""
import _src_path  # noqa: F401
import copy
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching.event_patch import add_collection_markers
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class LostDog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(NUP)
        cls.addClassCleanup(cls.nup.stream.close)
        cls.dicts = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    def read(self, path):
        raw = self.nup.read(self.nup.latest('romfs/' + path))
        return self.decompress(raw, self.dicts) if path.endswith('.zs') else raw

    def test_quest_is_enabled_for_child_without_opening_kakariko(self):
        from oot_rando.patching import lost_dog as dog
        source = byml_codec.load(self.read(dog.CHALLENGES))
        expected = copy.deepcopy(source)
        row = next(r for r in expected['root'] if 'SubEvent_FindRichard.' in r['__RowId'])
        self.assertEqual(row['DependFlagName'], dog.KAKARIKO_GATE)
        row['DependFlagName'] = dog.CHILDHOOD
        result, _ = dog.quest_from_start(byml_codec.dump(source))
        self.assertEqual(byml_codec.load(result), expected)

    def test_map_keeps_native_time_and_return_conditions_without_gate(self):
        import ainb
        from oot_rando.patching import lost_dog as dog
        source = self.read(dog.MODULE)
        expected = ainb.AINB.from_binary(source).as_dict()
        for i in (7, 14):
            expected['Nodes'][i]['Parameters']['Inputs']['String'][0]['Default Value'] = dog.CHILDHOOD
        result, _ = dog.map_from_start(source)
        self.assertEqual(ainb.AINB.from_binary(result).as_dict(), expected)
        with self.assertRaises(ValueError):
            dog.map_from_start(result)

    def test_random_appear_dog_pool_ignores_kakariko_gate(self):
        import ainb
        from oot_rando.patching import lost_dog as dog
        source = self.read(dog.POOL_MODULE)
        expected = ainb.AINB.from_binary(source).as_dict()
        expected['Nodes'][dog.POOL_GATE_NODE]['Parameters']['Inputs']['String'][0]['Default Value'] = dog.CHILDHOOD
        result, _ = dog.pool_from_start(source)
        self.assertEqual(ainb.AINB.from_binary(result).as_dict(), expected)
        with self.assertRaises(ValueError):
            dog.pool_from_start(result)

    def test_first_reward_depends_only_on_receipt_not_quest_or_inventory(self):
        from oot_rando.patching import lost_dog as dog
        source = self.read(dog.FLOW)
        result, _ = dog.reward_until_received(source)
        events = {e.name: e for e in parse_flow(result).flowchart.events}
        check = events['Event50'].data
        self.assertEqual(check.actor_query.v.v, 'EventQueryIsGameDataBool')
        self.assertEqual(check.params.data, {'GameDataName': dog.RECEIPT, 'Index': -1})
        for quest_done in (False, True):
            for received in (False, True):
                flags = {'SubEvent_FindRichard_IsCompleted_Exp': quest_done, dog.RECEIPT: received}
                self.assertEqual(check.cases[0 if flags[check.params.data['GameDataName']] else 1].v.name,
                                 'Event73' if received else 'Event16')
        self.assertEqual(events['Event55'].data.params.data,
                         {'GameDataName': dog.RECEIPT, 'Index': -1, 'Value': True})
        expected = params_by_event(parse_flow(source))
        expected['Event50'] = dict(check.params.data)
        self.assertEqual(params_by_event(parse_flow(result)), expected)
        with self.assertRaises(ValueError):
            dog.reward_until_received(result)

    def test_shuffled_collection_marker_still_runs_only_after_reward(self):
        from oot_rando.patching import lost_dog as dog
        source, _ = add_collection_markers(self.read(dog.FLOW), {'Event16': 'RandoCheck_LostDog'})
        result, _ = dog.reward_until_received(source)
        events = {e.name: e for e in parse_flow(result).flowchart.events}
        self.assertEqual(events['Event16'].data.nxt.v.name, 'RandoCollected_Event16')
        self.assertEqual(events['RandoCollected_Event16'].data.nxt.v.name, 'Event55')
        self.assertEqual(events['RandoCollected_Event16'].data.params.data['GameDataName'], 'RandoCheck_LostDog')
        self.assertNotEqual(events['Event73'].data.nxt.v.name, 'RandoCollected_Event16')

    def test_generation_hooks_include_all_three_resources(self):
        from oot_rando.patching import lost_dog as dog, story_fixes
        self.assertIn((dog.FLOW, 'lost_dog_reward', dog.reward_until_received), story_fixes.flow_fixes(()))
        self.assertIn((dog.MODULE, 'lost_dog_map', dog.map_from_start), story_fixes.scene_module_fixes())
        self.assertIn((dog.POOL_MODULE, 'lost_dog_pool', dog.pool_from_start), story_fixes.scene_module_fixes())

    def test_new_save_has_no_reward_or_return_receipt(self):
        from oot_rando.patching import lost_dog as dog
        from oot_rando.patching.game_defaults import GAMEDATA, read_defaults
        names = (dog.RECEIPT, 'Market_Npc_Hylia_052_Child_RichardGoHome',
                 'SubEvent_FindRichard_RichardRivival')
        self.assertEqual(read_defaults(self.read(GAMEDATA), names), dict.fromkeys(names, False))
