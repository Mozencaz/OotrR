"""Child Death Mountain Crater actors never become shuffle or logic locations."""
import _src_path  # noqa: F401
import os
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import inaccessible_child_actor, scan_maps, source_age

CRATER = 'Banc/DeathMountainCrater/DeathMountainCrater_{}_Dynamic.bcett.byml.zs'


class CraterChildSources(unittest.TestCase):
    def test_logic_never_collects_the_excluded_child_crater_rewards(self):
        from oot_rando.logic import rando_options
        from oot_rando.logic.rules import Logic, vanilla_placements
        from oot_rando.logic.world import World
        from oot_rando.randomizer.full_randomizer import ap_settings
        data = World()
        logic = Logic(data, ap_settings(rando_options.defaults(), True))
        items = Counter({item: 9 for item in logic.referenced})
        state, collected, _ = logic.sweep(vanilla_placements(data, logic), logic.new_state(items))
        self.assertNotIn('DMC GS Crate', collected)
        self.assertNotIn('DMC GS Bean Patch', collected)
        self.assertNotIn('DMC Deku Scrub', collected)
        self.assertFalse([r for r in state.reached['child'] if r.startswith('DMC ')])
        self.assertIn('DMC Upper Nearby', state.reached['adult'])
        self.assertIn('DMC Wall Freestanding PoH', collected)

    def test_every_child_crater_actor_is_filtered(self):
        actor = {'Gyaml': 'Obj_Pot_A_05', 'Hash': 1, 'Translate': [0, 0, 0]}
        self.assertTrue(inaccessible_child_actor(CRATER.format('Child'), actor))
        self.assertTrue(inaccessible_child_actor(CRATER.format('Child').replace('Dynamic', 'Static'), actor))
        self.assertFalse(inaccessible_child_actor(CRATER.format('Adult'), actor))
        self.assertFalse(inaccessible_child_actor(
            'Banc/DeathMountainTrail/DeathMountainTrail_Child_Dynamic.bcett.byml.zs', actor))

    def test_shared_sources_keep_their_adult_copy_and_child_only_ones_vanish(self):
        shared = [
            {'Gyaml': 'Obj_TBox_A_01', 'Hash': 1, 'Translate': [5, 0, 5],
             'Dynamic': {'Drop__DropActor': 'TBox_Rupee_Green'}},
            {'Gyaml': 'Obj_Pot_A_05', 'Hash': 2, 'Translate': [6, 0, 6],
             'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}},
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 3, 'Translate': [7, 0, 7]},
        ]
        child_only = {'Gyaml': 'Obj_Pot_A_05', 'Hash': 4, 'Translate': [8, 0, 8],
                      'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}}
        maps = {CRATER.format('Adult'): {'root': {'Actors': shared}},
                CRATER.format('Child'): {'root': {'Actors': shared + [child_only]}}}
        sources = scan_map_sources(maps, lambda *_: True)
        for source in ('DeathMountainCrater#pots#2', 'DeathMountainCrater#gs#3'):
            self.assertEqual(source_age(sources[source]['variants']), 'adult')
        self.assertNotIn('DeathMountainCrater#pots#4', sources)
        with patch('oot_rando.formats.inspect_resources.decompress', side_effect=lambda raw, _: raw), \
                patch('oot_rando.formats.inspect_resources.Byml',
                      side_effect=lambda path: SimpleNamespace(root=maps[path]['root'])):
            decoded, groups, enemies = scan_maps(SimpleNamespace(read=lambda path: path), {},
                                                 {p: p for p in maps})
        self.assertEqual(source_age(groups['DeathMountainCrater#1']), 'adult')
        self.assertFalse(any('_Child_' in e['resource'] for e in enemies))
        self.assertEqual(len(decoded[CRATER.format('Child')]['root']['Actors']), 4)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_native_child_crater_has_no_candidate(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        try:
            members = {p: v for p, v in effective_members(nup).items()
                       if p.startswith('Banc/DeathMountainCrater/')}
            maps, groups, enemies = scan_maps(nup, dictionaries(nup), members)
            sources = scan_map_sources(maps, lambda *_: True)
        finally:
            nup.stream.close()
        variants = [v for g in groups.values() for v in g] + [v for s in sources.values() for v in s['variants']]
        self.assertTrue(variants)
        self.assertFalse([v for v in variants if '_Child_' in v['resource']])
        self.assertFalse([e for e in enemies if '_Child_' in e['resource']])


if __name__ == '__main__':
    unittest.main()
