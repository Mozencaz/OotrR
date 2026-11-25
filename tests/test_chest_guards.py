"""Item guards of remake chests (invisible chests, chests behind destructible walls)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.game.remake_world import BOMBS_GUARD, LENS_GUARD, _behind_wall, chest_guards

NUP = os.environ.get('OOT_NUP')


def variant(actor='Obj_TBox_A_01', resource='Banc/F/F_Static.bcett.byml.zs', position=(0.0, 0.0, 0.0), **extra):
    return dict({'actor': actor, 'resource': resource, 'position': list(position) if position else None}, **extra)


class GuardTests(unittest.TestCase):
    def test_invisible_chest_needs_lens(self):
        self.assertEqual(chest_guards([variant('Obj_TBox_GlassTruth_A_01')]), [LENS_GUARD])
        self.assertEqual(chest_guards([variant()]), [])

    def test_chest_behind_wall_needs_bombs(self):
        self.assertEqual(chest_guards([variant(behind_wall=False), variant(behind_wall=True)]), [BOMBS_GUARD])

    def test_wall_distance_and_age(self):
        walls = [('adult', [2.0, 0.0, 0.0])]
        self.assertTrue(_behind_wall(variant(), walls))
        self.assertTrue(_behind_wall(variant(resource='F_Adult_Static'), walls))
        self.assertFalse(_behind_wall(variant(resource='F_Child_Static'), walls))
        self.assertFalse(_behind_wall(variant(position=(5.5, 0.0, 0.0)), walls))
        self.assertFalse(_behind_wall(variant(position=None), walls))


class SameChestTests(unittest.TestCase):
    def test_map_copy_joins_its_chest(self):
        # 20/11: KF_chest_1 was the Lost Woods ledge chest seen from the Kokiri Forest map.
        from oot_rando.game.remake_world import SAME_CHESTS, merge_same_chests
        copy_id, original_id = next(iter(SAME_CHESTS.items()))
        groups = {copy_id: [variant(resource='Banc/KokiriForest/K.bcett.byml.zs')],
                  original_id: [variant(resource='Banc/LostWood/L.bcett.byml.zs')], 'Other#1': [variant()]}
        merged = merge_same_chests(groups)
        self.assertNotIn(copy_id, merged)
        self.assertEqual([v['resource'] for v in merged[original_id]],
                         ['Banc/LostWood/L.bcett.byml.zs', 'Banc/KokiriForest/K.bcett.byml.zs'])
        self.assertEqual(merge_same_chests({copy_id: [variant()]}), {copy_id: [variant()]})  # original absent

    def test_kakariko_burnt_chest_joins_the_normal_one(self):
        from oot_rando.game.remake_world import SAME_CHESTS, merge_same_chests
        burnt, normal = 'KakarikoVillage#13080955777249750889', 'KakarikoVillage#11929552275106311978'
        self.assertEqual(SAME_CHESTS[burnt], normal)
        merged = merge_same_chests({burnt: [variant(resource='Alt')], normal: [variant(resource='Norm')]})
        self.assertEqual([v['resource'] for v in merged[normal]], ['Norm', 'Alt'])
        self.assertNotIn(burnt, merged)

    def test_rule_events_exist(self):
        # Each chest's own rule is a remake event of the logic.
        import json
        from oot_rando.game.remake_world import CHEST_RULE_EVENTS
        events = json.loads((Path(__file__).resolve().parents[1] / 'src/oot_rando/logic/world/remake.json')
                            .read_text(encoding='utf-8'))['events']
        names = {name for region in events.values() for name in region}
        self.assertLessEqual(set(CHEST_RULE_EVENTS.values()), names)
        self.assertEqual(events['Lon Lon Ranch']['LLR Ruins Hookshot Chest']['rule'], 'can_use(Hookshot)')


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class RealGameGuardTests(unittest.TestCase):
    def test_kokiri_copy_of_the_lost_woods_chest(self):
        from oot_rando.game.remake_world import SAME_CHESTS
        from game_fixture import scan_maps
        _, groups, _ = scan_maps()
        copy_id, original_id = next(iter(SAME_CHESTS.items()))
        self.assertNotIn(copy_id, groups)
        chest = groups[original_id]
        self.assertEqual(sorted(v['folder'] for v in chest), ['KokiriForest'] * 2 + ['LostWood'] * 2)
        # Same chest: the two maps are offset by one vector, the same for both ages.
        by_folder = {}
        for v in chest:
            by_folder.setdefault(v['folder'], []).append(v['position'])
        offset = [a - b for a, b in zip(by_folder['KokiriForest'][0], by_folder['LostWood'][0])]
        self.assertAlmostEqual(offset[0], -82.78, places=1)
        self.assertAlmostEqual(offset[2], -87.86, places=1)

    def test_guarded_chests(self):
        from game_fixture import scan_maps
        _, groups, _ = scan_maps()
        guarded = {gid: chest_guards(v) for gid, v in groups.items() if chest_guards(v)}
        bombs = [gid for gid, g in guarded.items() if BOMBS_GUARD in g]
        # Gerudo Training Ground like-like room: chest in the alcove of the cracked wall.
        self.assertEqual(bombs, ['GerudoTrainingGround#3750231902048775592'])
        lens = [gid for gid, g in guarded.items() if LENS_GUARD in g]
        # The child copy of GerudoValley#6205043616869463865 sits on the unreachable
        # fortress bank (remake_world.inaccessible_child_actor): no longer a candidate.
        self.assertEqual(len(lens), 9)
        self.assertEqual(sum(gid.startswith('GerudoValley#') for gid in lens), 1)


if __name__ == '__main__':
    unittest.main()
