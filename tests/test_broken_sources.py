import _src_path  # noqa: F401
import unittest

from oot_rando.game.remake_world import BROKEN_SOURCES, inaccessible_child_actor
from oot_rando.randomizer.full_randomizer import UNTRACKED_LOCATIONS


class BrokenSourcesTest(unittest.TestCase):
    def test_reported_actors_are_excluded_whatever_the_map(self):
        self.assertEqual(len(BROKEN_SOURCES), 12)
        for ident in BROKEN_SOURCES:
            for path in ('Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs',
                         'Banc/FireTemple/FireTemple_Static.bcett.byml.zs',
                         'Banc/DeathMountainTrail/DeathMountainTrail_Adult_Static.bcett.byml.zs'):
                self.assertTrue(inaccessible_child_actor(path, {'Hash': ident}))

    def test_other_actors_stay(self):
        self.assertFalse(inaccessible_child_actor('Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs',
                                                  {'Hash': 9860797772243961676}))   # HF_tree_21

    def test_gift_from_sages_untracked(self):
        self.assertIn('Gift from Sages', UNTRACKED_LOCATIONS)


if __name__ == '__main__':
    unittest.main()
