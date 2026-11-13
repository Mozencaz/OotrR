"""Enemy souls shown by zone in the tracker."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.tracker.auto_tracker import soul_zones


class SoulZonesTests(unittest.TestCase):
    def test_family_soul_listed_in_each_of_its_zones(self):
        metadata = {'souls': [{'item': 'Soul (Keese)', 'zones': ['InsideTheDekuTree', 'KokiriForest']},
                              {'item': 'Soul (DekuScrub)', 'zones': ['InsideTheDekuTree']}]}
        zones = soul_zones(metadata, {'Soul (Keese)': 1})
        # Map order of the zone labels (Kokiri Forest before the Deku Tree), souls sorted by name.
        self.assertEqual(zones, [('Kokiri Forest', [('Keese', True)]),
                                 ('Deku Tree', [('Deku Scrub', False), ('Keese', True)])])

    def test_regional_soul_and_unknown_zone(self):
        metadata = {'souls': [{'item': 'Soul (Region:DodongoCavern)', 'zones': ['DodongoCavern']},
                              {'item': 'Soul (Gohma)', 'zones': []}]}
        self.assertEqual(soul_zones(metadata, {}), [("Dodongo's Cavern", [("Dodongo's Cavern", False)]),
                                                    ('Other', [('Queen Gohma', False)])])

    def test_older_seed_without_zones(self):
        metadata = {'inventory': [{'item': 'Soul (Keese)', 'hash': '1'}, {'item': 'Bow', 'hash': '2'},
                                  {'item': 'Soul (Keese)', 'hash': '3'}]}
        self.assertEqual(soul_zones(metadata, {'Soul (Keese)': 1}), [('All zones', [('Keese', True)])])

    def test_no_souls(self):
        self.assertEqual(soul_zones({'souls': []}, {}), [])
        self.assertEqual(soul_zones(None, {}), [])


if __name__ == '__main__':
    unittest.main()
