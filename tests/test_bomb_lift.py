import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.qol_patches import (BOMB_LIFTABLE, BOMB_LIFT_PACKS, BRACELET_LIFT_GRADE, FREE_LIFT_GRADE,
                         free_bomb_lift)

FLOWER_LIFTABLE = 'Component/LiftableParam/Obj_BombFlower_Fruit.game__component__LiftableParam.bgyml'


def pack(grade, extra=None):
    files = {BOMB_LIFTABLE: byml_codec.dump({'endian': '<', 'version': 7,
                                             'root': {'LiftGrade': byml_codec.U32(grade), 'WeightForCalcThrowPower': 18.0}})}
    files.update(extra or {})
    return byml_codec.build_sarc(files)


class BombLiftTests(unittest.TestCase):
    def test_bracelet_grade_becomes_free_and_rest_is_kept(self):
        flower = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'LiftGrade': byml_codec.U32(BRACELET_LIFT_GRADE)}})
        raw, changed = free_bomb_lift(pack(BRACELET_LIFT_GRADE, {FLOWER_LIFTABLE: flower}))
        self.assertEqual(changed, 1)
        files = sarc(raw)
        root = byml_codec.load(files[BOMB_LIFTABLE])['root']
        self.assertEqual(root['LiftGrade'], FREE_LIFT_GRADE)
        self.assertEqual(root['WeightForCalcThrowPower'], 18.0)
        self.assertEqual(files[FLOWER_LIFTABLE], flower)  # bomb flowers still need the bracelet

    def test_other_grades_and_missing_file_untouched(self):
        source = pack(FREE_LIFT_GRADE)
        self.assertEqual(free_bomb_lift(source), (source, 0))
        other = byml_codec.build_sarc({'x.bgyml': b'YB'})
        self.assertEqual(free_bomb_lift(other), (other, 0))

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_real_game_bracelet_grade_and_bomb_packs(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries, Byml
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        d, members = dictionaries(nup), effective_members(nup)

        def read(name):
            return decompress(nup.read(members[f'Pack/Actor/{name}.pack.zs']), d)

        bracelet = sarc(read('Item_Gauntlet_Goron'))
        ability = next(v for k, v in bracelet.items() if 'ExpansionAbilityActor' in k)
        self.assertEqual(Byml(ability).root['LiftableGrade'], BRACELET_LIFT_GRADE)
        for path in BOMB_LIFT_PACKS:
            with self.subTest(path=path):
                raw, changed = free_bomb_lift(decompress(nup.read(members[path]), d))
                self.assertEqual(changed, 1)
                files = sarc(raw)
                self.assertEqual(Byml(files[BOMB_LIFTABLE]).root['LiftGrade'], FREE_LIFT_GRADE)
                if FLOWER_LIFTABLE in files:
                    self.assertEqual(Byml(files[FLOWER_LIFTABLE]).root['LiftGrade'], BRACELET_LIFT_GRADE)


if __name__ == '__main__':
    unittest.main()
