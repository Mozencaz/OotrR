"""The one-time Treasure Chest Game prize is a shuffled chest, not a repeat payout."""
import _src_path  # noqa: F401
import copy
import json
import os
import unittest

from oot_rando.game.remake_world import junk_reason, match_locations
from oot_rando.logic.world import World
from oot_rando.logic.rules import Logic
from oot_rando.logic import rando_options
from oot_rando.randomizer import full_randomizer
from oot_rando.formats.evfl_tools import parse_flow

GID = 'Market#16881481538337649070'
LOCATION = 'Market Treasure Chest Game Reward'
MAP = 'Banc/Market/Market_Child_Static.bcett.byml.zs'
EVENT = 'MiniGame_ChoiceTreasure_OpenClearTreasureBox'
FLOW = 'Event/EventFlow/MiniGame_SequentialChoiceTreasure.bfevfl.zs'


def prize_variant():
    return {'resource': MAP, 'index': 0, 'actor': 'Obj_HrlCity_Shop_TBox_A_02',
            'folder': 'Market', 'hash': GID.split('#')[1], 'before': 'Obj_Heart_Piece',
            'dynamic': {'Drop__DropActor': 'Obj_Heart_Piece', 'IsEnableRepeatOpen': True,
                        'GetEventName': EVENT, 'DropViewActor': 'Obj_Heart_Piece_MiniGame'},
            'position': [-131.578, 97.891, 12.671]}


class Units(unittest.TestCase):
    def test_only_identified_first_prize_is_safe_to_shuffle(self):
        prize = prize_variant()
        self.assertIsNone(junk_reason([prize]))
        repeat = copy.deepcopy(prize)
        repeat.update(hash='6781536951709667179', before='TBox_Rupee_Red')
        repeat['dynamic']['Drop__DropActor'] = 'TBox_Rupee_Red'
        self.assertEqual(junk_reason([repeat]), 'repeatable')
        ordinary = copy.deepcopy(prize)
        ordinary['actor'] = 'Obj_TBox_A_02'
        self.assertEqual(junk_reason([ordinary]), 'repeatable')

    def test_prize_uses_its_own_lens_rule_and_regular_heart_pool_item(self):
        data = World()
        logic = Logic(data, full_randomizer.ap_settings(rando_options.defaults(), True))
        matches, unmatched = match_locations({GID: [prize_variant()]}, data, logic)
        entry = matches[GID]
        self.assertEqual((entry['kind'], entry['ap'], entry['vanilla']),
                         ('exact', [LOCATION], 'Piece of Heart'))
        self.assertNotIn(LOCATION, unmatched)
        context = full_randomizer.prepare(data, rando_options.defaults(),
                                          {GID: [prize_variant()]}, [], 'prize')
        self.assertIn(GID, context.shuffled)
        self.assertEqual(context.pool.count('Piece of Heart'), 1)
        from collections import Counter
        inventory = Counter({item: 99 for item in context.relevant if item != 'Lens of Truth'})
        state, _, _ = context.logic.sweep({}, context.logic.new_state(inventory))
        self.assertFalse(context.logic.accessible(state, LOCATION))
        inventory['Lens of Truth'] = 1
        state, _, _ = context.logic.sweep({}, context.logic.new_state(inventory))
        self.assertTrue(context.logic.accessible(state, LOCATION))
        off = dict(rando_options.defaults(), shuffle_chests=False)
        self.assertNotIn(GID, full_randomizer.prepare(
            data, off, {GID: [prize_variant()]}, [], 'prize').shuffled)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class GameData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        from game_fixture import scan_world
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)
        cls.maps, cls.groups, cls.enemies, cls.extra = scan_world()

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        from oot_rando.formats.inspect_resources import decompress
        return decompress(self.nup.read(self.members[path]), self.d)

    def test_scan_includes_only_first_prize_and_patches_content_and_preview(self):
        from oot_rando.formats.byml_writer import patch_strings
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching import chest_flags
        self.assertIn(GID, self.groups)
        self.assertEqual([g for g in self.groups if g.startswith('Market#')], [GID])
        data = World()
        matches, _ = match_locations(self.groups, data, Logic(data))
        entry = matches[GID]
        patches = full_randomizer._patches(entry)
        edits = [{'path': tuple(p['path']), 'before': p['before'], 'after': 'Item_Hookshot'}
                 for p in patches]
        patched = Byml(patch_strings(self.maps[MAP]['raw'], edits)).root
        index = entry['variants'][0]['index']
        dynamic = patched['Actors'][index]['Dynamic']
        self.assertEqual(dynamic['Drop__DropActor'], 'Item_Hookshot')
        self.assertEqual(dynamic['DropViewActor'], 'Item_Hookshot')
        self.assertTrue(dynamic['IsEnableRepeatOpen'])
        for i, actor in enumerate(self.maps[MAP]['root']['Actors']):
            if i != index:
                self.assertEqual(patched['Actors'][i], actor)
        rows = {r['__RowId']: r for r in Byml(self.read(chest_flags.EVENT_SETTINGS)).root}
        records, skipped = chest_flags.plan_records(
            [{'id': GID, 'source': 'chest', 'variants': [(MAP, index)]}],
            lambda _: patched, 'f' * 64, rows)
        self.assertEqual(skipped, {})
        self.assertEqual((records[0]['base'], records[0]['flow']), (EVENT, FLOW))
        raw = chest_flags.add_entries(self.read(FLOW), records)
        chart = parse_flow(raw).flowchart
        wrapper = next(e for e in chart.entry_points if e.name == records[0]['event'])
        self.assertEqual(wrapper.main_event.v.data.nxt.v.data.entry_point_name,
                         'MiniGame_SequentialChoiceTreasure_OpenClearTreasureBox')
        # Native completion still selects a distinct rupee chest on subsequent wins.
        import ainb
        module = ainb.AINB.from_binary(self.nup.read(self.members[
            'Logic/MiniGame_SequentialChoiceTreasure_cbde.logic.module.ainb'])).as_dict()
        self.assertIn('MiniGame_ChoiceTreasure_IsClear', json.dumps(module))
        repeat = next(a for a in patched['Actors'] if a.get('Hash') == 6781536951709667179)
        self.assertEqual(repeat['Dynamic']['Drop__DropActor'], 'TBox_Rupee_Red')

    def test_shuffled_prize_is_reachable_in_a_verified_seed(self):
        data = World()
        options = rando_options.preset('everything')
        result = full_randomizer.plan(data, options, self.groups, self.enemies,
                                     'treasure-game-regression', extra=self.extra)
        placed = {p['id']: p['item'] for p in result['placements']}
        self.assertIn(GID, placed)
        self.assertIsNotNone(next(p['sphere'] for p in result['placements'] if p['id'] == GID))
        replay = full_randomizer.replay(data, options, self.groups, self.enemies,
                                        placed, extra=self.extra, seed_key='treasure-game-regression')
        self.assertTrue(replay['beatable'])
        self.assertEqual(replay['unreachable'], [])


if __name__ == '__main__':
    unittest.main()
