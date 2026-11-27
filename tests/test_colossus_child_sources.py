"""The seven bean-plateau rocks are unreachable as child Link."""
import _src_path  # noqa: F401
import os
import unittest
from copy import deepcopy

from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import inaccessible_child_actor


COLOSSUS = 'Banc/DesertColossus/DesertColossus_{}_Dynamic.bcett.byml.zs'
CHILD_ROCKS = (17604351797179232812, 18089518693918851857, 2465861655194430312,
               16808421367294770117, 15615314528351978483, 12414690125675705208,
               352697202323389437)
ADULT_ROCKS = (14514022023330510682, 3068749159060442969, 6141646481426607938,
               2046759311695128505, 17813319975073074839, 9203224707045543681,
               4108432179731449070)


class ColossusChildSources(unittest.TestCase):
    def test_only_child_plateau_rocks_are_filtered(self):
        for ident in CHILD_ROCKS:
            actor = {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': ident}
            self.assertTrue(inaccessible_child_actor(COLOSSUS.format('Child'), actor))
            self.assertFalse(inaccessible_child_actor(COLOSSUS.format('Adult'), actor))
            self.assertFalse(inaccessible_child_actor(
                'Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs', actor))
        self.assertFalse(inaccessible_child_actor(COLOSSUS.format('Child'),
                         {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': 3794108288976088388}))

    def test_scanning_preserves_adult_and_other_child_rocks_and_map_indices(self):
        def rock(ident):
            return {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': ident,
                    'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}}
        maps = {
            COLOSSUS.format('Child'): {'root': {'Actors': [rock(i) for i in CHILD_ROCKS] + [rock(1)]}},
            COLOSSUS.format('Adult'): {'root': {'Actors': [rock(i) for i in ADULT_ROCKS]}},
        }
        original = deepcopy(maps)
        sources = scan_map_sources(maps, lambda *_: True)
        self.assertEqual(set(sources), {f'DesertColossus#rocks#{i}' for i in (*ADULT_ROCKS, 1)})
        self.assertEqual(sources['DesertColossus#rocks#1']['variants'][0]['index'], 7)
        self.assertEqual(maps, original)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_prudent_shuffle_leaves_child_plateau_drops_vanilla(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import Byml, dictionaries
        from oot_rando.game.world_maps import build_world
        nup = Nup(os.environ['OOT_NUP'])
        try:
            result = build_world(nup, dictionaries(nup), {'rocks': True},
                                 'colossus-child-plateau-regression')
        finally:
            nup.stream.close()
        placements = [p for p in result['placements']
                      if any('/DesertColossus/' in path for path in p['resources'])]
        self.assertTrue(placements)
        self.assertFalse(set(CHILD_ROCKS) & {int(p['hash']) for p in placements})
        self.assertTrue(set(ADULT_ROCKS) & {int(p['hash']) for p in placements})
        raw = result['raw_maps'].get(COLOSSUS.format('Child'))
        # This map may be omitted entirely when nothing else on it changes.
        if raw is not None:
            actors = {a['Hash']: a for a in Byml(raw).root['Actors']}
            for ident, drop in zip(CHILD_ROCKS, ('Obj_Rupee_Red', 'Obj_Rupee_Blue',
                                  'Obj_Rupee_Green', 'Obj_Rupee_Green', 'Obj_Rupee_Blue',
                                  'Obj_Rupee_Blue', 'Obj_Rupee_Green')):
                self.assertEqual(actors[ident]['Dynamic']['Drop__DropActor'], drop)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_native_plateau_excludes_exactly_seven_child_rocks(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.remake_world import scan_maps
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        try:
            members = {p: v for p, v in effective_members(nup).items()
                       if p.startswith(('Banc/DesertColossus/', 'Logic/'))}
            maps, _, _ = scan_maps(nup, dictionaries(nup), members)
        finally:
            nup.stream.close()
        original = deepcopy(maps)
        actors = maps[COLOSSUS.format('Child')]['root']['Actors']
        excluded = [a for a in actors if inaccessible_child_actor(COLOSSUS.format('Child'), a)]
        self.assertEqual({a['Hash'] for a in excluded}, set(CHILD_ROCKS))
        self.assertTrue(all(a['Gyaml'] == 'Obj_LiftRock_A_01' and
                            105 < a['Translate'][1] < 107 for a in excluded))
        sources = scan_map_sources(maps, lambda *_: True)
        for ident in CHILD_ROCKS:
            self.assertNotIn(f'DesertColossus#rocks#{ident}', sources)
        for ident in ADULT_ROCKS:
            entry = sources[f'DesertColossus#rocks#{ident}']
            self.assertIsNone(entry['reason'])
            self.assertEqual([v['resource'] for v in entry['variants']], [COLOSSUS.format('Adult')])
        for actor in actors:
            if actor['Gyaml'] == 'Obj_LiftRock_A_01' and actor['Hash'] not in CHILD_ROCKS:
                self.assertIn(f"DesertColossus#rocks#{actor['Hash']}", sources)
        self.assertEqual(maps, original)


if __name__ == '__main__':
    unittest.main()
