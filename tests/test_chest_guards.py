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


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class RealGameGuardTests(unittest.TestCase):
    def test_guarded_chests(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.remake_world import scan_maps
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        _, groups, _ = scan_maps(nup, dictionaries(nup), effective_members(nup))
        guarded = {gid: chest_guards(v) for gid, v in groups.items() if chest_guards(v)}
        bombs = [gid for gid, g in guarded.items() if BOMBS_GUARD in g]
        # Gerudo Training Ground like-like room: chest in the alcove of the cracked wall.
        self.assertEqual(bombs, ['GerudoTrainingGround#3750231902048775592'])
        lens = [gid for gid, g in guarded.items() if LENS_GUARD in g]
        self.assertEqual(len(lens), 10)
        self.assertEqual(sum(gid.startswith('GerudoValley#') for gid in lens), 2)


if __name__ == '__main__':
    unittest.main()
