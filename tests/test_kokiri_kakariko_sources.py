"""Invisible Kokiri rocks and the Kakariko tree replaced by the burning banc."""
import _src_path  # noqa: F401
import copy
import os
import unittest
from unittest.mock import patch

from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import inaccessible_child_actor, source_age
from oot_rando.patching.repeatable_adapter import prepare_repeatables

KF = 'Banc/KokiriForest/KokiriForest_{}_Static.bcett.byml.zs'
KAK = 'Banc/KakarikoVillage/KakarikoVillage_Adult_{}Dynamic.bcett.byml.zs'
ROCKS = {
    'Child': {12: 16780156705177292663, 18: 4164292104786619976,
              24: 12045642716728132811, 30: 13219695470225186387},
    'Adult': {9: 10656348214587939196, 14: 5853846732169153879,
              16: 8931631613049749371, 19: 13164882936498639212,
              23: 802407974539353270, 26: 15388836867476865988,
              28: 2657789777104100407, 33: 5675403228854574159},
}
NORMAL, BURNT = 16206101463308204390, 17337529934879425827
TREE = f'KakarikoVillage#trees#{NORMAL}'


class KokiriKakarikoSources(unittest.TestCase):
    def test_rocks_excluded_only_on_their_own_age_and_map(self):
        for age, rocks in ROCKS.items():
            for ident in rocks.values():
                actor = {'Hash': ident, 'Gyaml': 'Obj_LiftRock_A_01'}
                self.assertTrue(inaccessible_child_actor(KF.format(age), actor))
                self.assertFalse(inaccessible_child_actor(
                    KF.format('Adult' if age == 'Child' else 'Child'), actor))
                self.assertFalse(inaccessible_child_actor(
                    KF.format(age).replace('KokiriForest', 'LostWood'), actor))
            self.assertFalse(inaccessible_child_actor(KF.format(age), {'Hash': 1}))

    def test_scan_removes_exactly_twelve_rocks_without_mutating_maps(self):
        maps = {KF.format(age): {'root': {'Actors': [
            {'Hash': ident, 'Gyaml': 'Obj_LiftRock_A_01'} for ident in (*rocks.values(), 1)]}}
                for age, rocks in ROCKS.items()}
        original = copy.deepcopy(maps)
        entries = scan_map_sources(maps, lambda *_: True)
        self.assertEqual(set(entries), {'KokiriForest#rocks#1'})
        self.assertEqual([v['index'] for v in entries['KokiriForest#rocks#1']['variants']], [8, 4])
        self.assertEqual(maps, original)

    def test_tree_variants_share_one_reward_and_saved_flag(self):
        maps = {KAK.format(suffix): {'root': {'Actors': [
            {'Hash': ident, 'Gyaml': 'Obj_Tree_A_01', 'Translate': [-73.6, 96.72, 43.48]}]}}
                for suffix, ident in (('', NORMAL), ('Alternative_', BURNT))}
        original = copy.deepcopy(maps)
        entries = scan_map_sources(maps, lambda *_: True)
        self.assertEqual(set(entries), {TREE})
        entry = entries[TREE]
        self.assertIsNone(entry['reason'])
        self.assertEqual(source_age(entry['variants']), 'adult')
        self.assertEqual({v['resource'] for v in entry['variants']}, set(maps))
        patches = [{'resource': v['resource'], 'path': ['Actors', v['index'], 'Dynamic', 'Drop__DropActor']}
                   for v in entry['variants']]
        plan = {'placements': [{'id': TREE, 'source': 'trees', 'before': None,
                                'after': 'Obj_Rupee_Blue', 'patches': patches}]}
        records = prepare_repeatables(plan, maps)
        self.assertEqual(len(records), 1)
        self.assertEqual({v['resource'] for v in records[0]['variants']}, set(maps))
        self.assertTrue(records[0]['flag'].startswith('Rando.Check.'))
        self.assertEqual(maps, original)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_native_maps_keep_all_other_rocks_and_merge_only_adult_tree(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.game.remake_world import scan_maps
        from oot_rando.game.extra_sources import collect
        nup = Nup(os.environ['OOT_NUP'])
        try:
            members = effective_members(nup)
            selected = {p: v for p, v in members.items()
                        if p.startswith(('Banc/KokiriForest/', 'Banc/KakarikoVillage/'))}
            maps, groups, _ = scan_maps(nup, dictionaries(nup), selected)
            entries = collect(nup, dictionaries(nup), members, maps)
            # Resolve the user's original labels before candidate exclusions.
            with patch('oot_rando.game.extra_sources.inaccessible_child_actor', return_value=False):
                unfiltered = collect(nup, dictionaries(nup), members, maps)
            from oot_rando.game.check_names import label_entries
            label_entries(maps, groups, unfiltered)
            for rocks in ROCKS.values():
                for number, ident in rocks.items():
                    self.assertEqual(unfiltered[f'KokiriForest#rocks#{ident}']['variants'][0]['label'],
                                     f'KF_rock_{number}')
        finally:
            nup.stream.close()
        excluded = {ident for rocks in ROCKS.values() for ident in rocks.values()}
        self.assertEqual(len(excluded), 12)
        for path, document in maps.items():
            for actor in document['root'].get('Actors', []):
                if actor['Gyaml'] != 'Obj_LiftRock_A_01' or '/KokiriForest/' not in path:
                    continue
                gid = f"KokiriForest#rocks#{actor['Hash']}"
                self.assertEqual(gid in entries, actor['Hash'] not in excluded)
        trees = [e for e in entries.values() if e['folder'] == 'KakarikoVillage' and e['source'] == 'trees']
        self.assertEqual(len(trees), 1)
        self.assertEqual({maps[v['resource']]['root']['Actors'][v['index']]['Hash']
                          for v in trees[0]['variants']}, {NORMAL, BURNT})
        self.assertEqual(source_age(trees[0]['variants']), 'adult')


if __name__ == '__main__':
    unittest.main()
