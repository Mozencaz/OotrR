"""Kokiri Forest objects placed by position and Mido's house chests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.game.extra_sources import KF_ANCHOR_ADULT, KF_ANCHOR_BEAN, KF_ANCHOR_CHILD, kokiri_spot
from oot_rando.game.remake_world import KNOWN_CHEST_GROUPS

CHILD = 'Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs'
ADULT = 'Banc/KokiriForest/KokiriForest_Adult_Dynamic.bcett.byml.zs'


def entry(source, *variants, folder='KokiriForest'):
    return {'folder': folder, 'source': source,
            'variants': [{'resource': resource, 'position': position} for resource, position in variants]}


class KokiriSpotTests(unittest.TestCase):
    def test_village_pot_is_reachable_at_start(self):
        self.assertEqual(kokiri_spot(entry('pots', (CHILD, [6.0, 110.0, 21.0]))), KF_ANCHOR_CHILD)

    def test_child_copy_is_enough(self):
        self.assertEqual(kokiri_spot(entry('freestanding', (ADULT, [-87, 119, 19]), (CHILD, [-87, 119, 19]))),
                         KF_ANCHOR_CHILD)

    def test_adult_only_object_needs_time_travel(self):
        self.assertEqual(kokiri_spot(entry('freestanding', (ADULT, [-10, 112, 19]))), KF_ANCHOR_ADULT)

    def test_bean_platform_needs_the_platform(self):
        self.assertEqual(kokiri_spot(entry('freestanding', (ADULT, [21, 117, -14]))), KF_ANCHOR_BEAN)

    def test_grotto_beyond_mido_and_other_maps_stay_area_wide(self):
        self.assertIsNone(kokiri_spot(entry('pots', (CHILD, [-60, 104, -63]))))
        self.assertIsNone(kokiri_spot(entry('pots', (CHILD, [60, 110, -20]))))
        self.assertIsNone(kokiri_spot(entry('pots', (CHILD, [0, 110, 0]), folder='LostWood')))
        self.assertIsNone(kokiri_spot(entry('skulltula', (CHILD, [0, 110, 0]))))

    def test_mido_chests_are_the_four_ap_mido_chests(self):
        self.assertEqual(len(KNOWN_CHEST_GROUPS), 4)
        for locations in KNOWN_CHEST_GROUPS.values():
            self.assertEqual(len(locations), 4)
            self.assertTrue(all(l.startswith('KF Midos ') for l in locations))


if __name__ == '__main__':
    unittest.main()
