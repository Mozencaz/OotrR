"""Chests placed by the zone heuristic also need what the gimmick next to them asks."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.game import remake_world as rw
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World

TIME = 'Souls|Ocarina|Song of Time'
HOOK = 'Souls|Progressive Hookshot'


def chest(folder, ident, item, position, resource, near=()):
    return {'resource': resource, 'index': 0, 'actor': 'Obj_TBox_A_01', 'folder': folder, 'hash': ident,
            'before': item, 'dynamic': {}, 'position': position, 'behind_wall': False, 'near_guards': list(near)}


class NearGuardTests(unittest.TestCase):
    def test_gimmick_radius_and_age(self):
        gimmicks = [('adult', TIME, 10.0, [0.0, 0.0, 0.0]), (None, HOOK, 10.0, [30.0, 0.0, 0.0])]
        adult = {'resource': 'Banc/IceCavern/X_Adult_Static.bcett.byml.zs', 'position': [5.0, 0.0, 0.0]}
        child = dict(adult, resource='Banc/IceCavern/X_Child_Static.bcett.byml.zs')
        self.assertEqual(rw._near_guards(adult, gimmicks), [TIME])
        self.assertEqual(rw._near_guards(child, gimmicks), [])
        self.assertEqual(rw._near_guards(dict(adult, position=None), gimmicks), [])

    def test_only_the_zone_heuristic_adds_them(self):
        data = World()
        logic = Logic(data, {'open_forest': 'closed_deku'})
        resource = 'Banc/IceCavern/IceCavern_Dynamic.bcett.byml.zs'
        groups = {'IceCavern#1': [chest('IceCavern', '1', 'TBox_Rupee_Red', [0, 0, 0], resource, [TIME])]}
        strict, _ = rw.match_locations(groups, data, logic, 'strict')
        self.assertEqual(strict['IceCavern#1']['kind'], 'junk')
        self.assertNotIn(TIME, strict['IceCavern#1']['guards'])
        scene, _ = rw.match_locations(groups, data, logic, 'scene')
        self.assertIn(scene['IceCavern#1']['kind'], ('group', 'area'))
        self.assertIn(TIME, scene['IceCavern#1']['guards'])

    def test_patterns(self):
        names = {'Obj_SongOfTimeBlock_A_01': TIME, 'Obj_FireTemple_HookShotTarget_A_01': HOOK,
                 'Obj_HookShotTarget_A_01': HOOK, 'Obj_ScarecrowMarker_B_01': 'Souls|Progressive Hookshot|Ocarina',
                 'Obj_Well_GlassTruth_A_01': rw.LENS_GUARD, 'WallCrack_0a1b': rw.BOMBS_GUARD,
                 'Obj_CandleStick_TimeExtinguish_A_01': 'Souls|Dins Fire|Magic Meter'}
        for name, guard in names.items():
            with self.subTest(name=name):
                self.assertEqual([g for p, _, g in rw.NEAR_GUARDS if p.match(name)], [guard])
        self.assertFalse(any(p.match('Obj_TBox_A_01') for p, _, _ in rw.NEAR_GUARDS))


if __name__ == '__main__':
    unittest.main()
