import _src_path  # noqa: F401  (src on sys.path)
import math
import os
import unittest

from oot_rando.game.underwater import covered, mark_entries, water_planes

BOX = ({'X': -5.0, 'Y': 0.0, 'Z': -5.0}, {'X': 5.0, 'Y': 0.0, 'Z': 5.0})


def plane(name='Obj_WaterPlane_A_01', at=(0.0, 100.0, 0.0), scale=None, rotate=None):
    actor = {'Gyaml': name, 'Translate': list(at)}
    if scale is not None:
        actor['Scale'] = scale
    if rotate is not None:
        actor['Rotate'] = rotate
    return actor


class CoveredTests(unittest.TestCase):
    def planes(self, *actors):
        return water_planes({'Actors': list(actors)}, lambda name: BOX)

    def test_spot_below_the_surface(self):
        planes = self.planes(plane())
        self.assertTrue(covered((1.0, 95.0, 1.0), planes))
        self.assertFalse(covered((1.0, 100.1, 1.0), planes))     # above
        self.assertFalse(covered((1.0, 99.9, 1.0), planes))      # at the surface
        self.assertFalse(covered((6.0, 95.0, 1.0), planes))      # beside
        self.assertFalse(covered((1.0, 50.0, 1.0), planes))      # far below: another floor

    def test_scale_and_rotation(self):
        planes = self.planes(plane(scale=[2.0, 1.0, 1.0], rotate=[0.0, math.pi / 2, 0.0]))
        # Turned a quarter: 10 m long along Z, 5 m along X.
        self.assertTrue(covered((0.0, 95.0, 9.0), planes))
        self.assertFalse(covered((9.0, 95.0, 0.0), planes))

    def test_flipped_plane_keeps_its_top(self):
        # Rotate [pi, 0, pi] (the Zora's Fountain plane): a half turn about Y.
        box = ({'X': -103.0, 'Y': -31.7, 'Z': -43.1}, {'X': 39.0, 'Y': 0.0, 'Z': 61.3})
        planes = water_planes({'Actors': [plane('Land_ZoraFountain_WaterPlane_Field_A_01', (0.0, 101.9, 0.0),
                                                rotate=[math.pi, 0.0, math.pi])]}, lambda name: box)
        self.assertTrue(covered((56.9, 70.9, -27.4), planes))     # bottom heart piece
        self.assertFalse(covered((85.0, 103.1, -34.8), planes))   # heart piece on the ice

    def test_shallow_water_counts_other_actors_ignored(self):
        self.assertEqual(len(self.planes(plane('Land_ShallowWaterPlane_A_02'))), 1)
        self.assertEqual(self.planes(plane('Obj_Rupee_Green')), [])


class MarkTests(unittest.TestCase):
    def test_marks_world_variants_only(self):
        maps = {'map': {'root': {'Actors': [
            plane(),
            {'Gyaml': 'Obj_Rupee_Green', 'Translate': [0.0, 95.0, 0.0]},
            {'Gyaml': 'Obj_Rupee_Green', 'Translate': [0.0, 120.0, 0.0]},
            {'Gyaml': 'Obj_Rupee_Green', 'Translate': [80.0, 95.0, 0.0], 'Dynamic': {'IsInZoraRiver': True}},
            {'Gyaml': 'TBox', 'Translate': [0.0, 95.0, 0.0]}]}}}
        entries = {gid: {'form': form, 'variants': [{'resource': 'map', 'index': index}]}
                   for gid, form, index in (('wet', 'world', 1), ('dry', 'world', 2), ('river', 'world', 3),
                                            ('chest', 'chest', 4))}
        self.assertEqual(mark_entries(maps, entries, lambda name: BOX), 2)
        self.assertEqual({gid for gid, e in entries.items() if e['variants'][0].get('underwater')}, {'wet', 'river'})


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class GameMapTests(unittest.TestCase):
    """On the game: Ruto's bottle and the Lake Hylia / Zora's Fountain bottoms are under water."""

    def test_known_spots(self):
        from game_fixture import scan_world
        _, _, _, extra = scan_world()
        wet = {gid for gid, entry in extra.items() if any(v.get('underwater') for v in entry['variants'])}
        letter = [gid for gid in extra if '#letter#' in gid]
        self.assertTrue(letter and set(letter) <= wet)
        for folder in ('ZoraFountain', 'ZoraRiver', 'HyruleField'):
            self.assertTrue(any(gid.startswith(folder + '#') for gid in wet), folder)
        # Most of the world spots are dry.
        world = [gid for gid, entry in extra.items() if entry.get('form') == 'world']
        self.assertLess(len(wet), len(world) / 5)
        self.assertFalse(any(gid.startswith(('DeathMountainTrail#', 'GoronCity#', 'DesertColossus#'))
                             for gid in wet))


if __name__ == '__main__':
    unittest.main()
