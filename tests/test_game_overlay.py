import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.tracker.game_overlay import GRID, overlay_model


def cell(model, item):
    return next(entry for row in model['cells'] for entry in row if entry['item'] == item)


class OverlayModelTests(unittest.TestCase):
    def test_item_states_never_claim_missing_without_a_readable_flag(self):
        tracked = {'Bow', 'Progressive Hookshot', 'Boomerang'}
        readable = {'Bow', 'Progressive Hookshot'}
        model = overlay_model({'Progressive Hookshot': 2}, readable, tracked, [], {})
        self.assertEqual(cell(model, 'Progressive Hookshot')['state'], 'owned')
        self.assertEqual(cell(model, 'Progressive Hookshot')['level'], 2)
        self.assertEqual(cell(model, 'Bow')['state'], 'missing')
        self.assertEqual(cell(model, 'Boomerang')['state'], 'unknown')      # tracked, not in the save
        self.assertEqual(cell(model, 'Iron Boots')['state'], 'unknown')     # not tracked by the seed

    def test_grid_rows_have_unique_items(self):
        items = [entry[0] for row in GRID for entry in row]
        self.assertEqual(len(items), len(set(items)))

    def test_souls_counted_only_when_the_seed_tracks_them(self):
        self.assertIsNone(overlay_model({}, set(), {'Bow'}, [], {})['souls'])
        souls = {'Soul (Gohma)', 'Soul (Keese)'}
        model = overlay_model({'Soul (Gohma)': 1}, souls, souls, [], {})
        self.assertEqual(model['souls'], (1, 2))

    def test_check_counts(self):
        checks = [{'id': str(i)} for i in range(4)]
        states = {'0': {'completed': True}, '1': {'access': 'available'}, '2': {'completed': True}}
        model = overlay_model({}, set(), set(), checks, states)
        self.assertEqual((model['done'], model['total']), (2, 4))

    def test_model_holds_only_the_grid_and_the_two_counts(self):
        self.assertEqual(set(overlay_model({}, set(), set(), [], {})), {'cells', 'souls', 'done', 'total'})


class ObservedInventoryTests(unittest.TestCase):
    def test_levels_take_the_highest_observed_tier(self):
        metadata = {'inventory': [{'item': 'Progressive Hookshot', 'hash': '1', 'count': 1},
                                  {'item': 'Progressive Hookshot', 'hash': '2', 'count': 2},
                                  {'item': 'Bow', 'hash': '3', 'count': 1},
                                  {'item': 'Boomerang', 'hash': '4', 'count': 1}]}
        snapshot = {'bool': {1: True, 2: True, 3: False}}
        counts, known = TrackerSession.observed_inventory(snapshot, metadata)
        self.assertEqual(dict(counts), {'Progressive Hookshot': 2})
        self.assertEqual(known, {'Progressive Hookshot', 'Bow'})


class PlacementTests(unittest.TestCase):
    def hud(self, offset):
        from oot_rando.tracker.game_overlay import GameHud
        hud = GameHud.__new__(GameHud)   # placement only: no window
        hud.offset = offset
        return hud

    def test_default_corner_then_saved_offset_kept_inside_the_game(self):
        client = (100, 50, 1280, 720)
        self.assertEqual(self.hud(None).place(client, (200, 150), 8), (108, 58))
        self.assertEqual(self.hud((900, 300)).place(client, (200, 150), 8), (1000, 350))
        self.assertEqual(self.hud((5000, -40)).place(client, (200, 150), 8), (100 + 1080, 50))


if __name__ == '__main__':
    unittest.main()
