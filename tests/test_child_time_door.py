"""Closed-door seeds must have a complete route before the first adult visit."""
import _src_path  # noqa: F401
import unittest
from unittest.mock import patch

from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer import full_randomizer as r
from test_map_ages import map_sources, KF_CHILD, KF_ADULT, KF_BOTH


ITEMS = ('Ocarina', 'Song of Time', 'Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire')


class ChildDoorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World()

    def prepared(self, **options):
        options = rando_options.validate(dict(shuffle_rocks=True, **options))
        c = r.prepare(self.world, options, {}, [], 'child-door', extra=map_sources())
        # Remove native gate rewards to model a seed where they were shuffled.
        # The real pedestal and its Time Travel grant are kept.
        for location, item in list(c.base.items()):
            if item in ITEMS:
                c.base[location] = None
        return c

    def test_song_and_one_ocarina_child_spare_ocarina_adult(self):
        c = self.prepared()
        placed = {KF_CHILD: 'Ocarina', KF_BOTH: 'Song of Time', KF_ADULT: 'Ocarina'}
        self.assertEqual(r.child_door_missing(c, placed), [])
        child, collected, _ = c.sweep(placed, before_adult=True)
        self.assertEqual(child.count('Ocarina'), 1)
        self.assertFalse(child.has('Time Travel'))
        self.assertNotIn(r.vname(KF_ADULT), collected)
        self.assertIn(r.vname(KF_ADULT), c.sweep(placed)[1])

    def test_each_required_item_on_an_adult_map_is_rejected(self):
        for mode, required in (('song', ITEMS[:2]), ('vanilla', ITEMS[:2] + ITEMS[3:]),
                               ('all', ITEMS)):
            for missing in required:
                with self.subTest(mode=mode, missing=missing):
                    c = self.prepared(door_of_time_requirement=mode,
                                      start_inventory_from_pool={i: 1 for i in required if i != missing})
                    self.assertEqual(r.child_door_missing(c, {KF_ADULT: missing}), [missing])

    def test_required_stones_and_escape_settings_are_independent(self):
        for mode, expected in (('song', []), ('vanilla', list(ITEMS[3:])), ('all', list(ITEMS[2:]))):
            for escape in ('all', 'vanilla'):
                c = self.prepared(door_of_time_requirement=mode, spiritual_stones=escape,
                                  start_inventory_from_pool={'Ocarina': 1, 'Song of Time': 1})
                self.assertEqual(r.child_door_missing(c, {}), expected)

    def test_all_items_in_starting_inventory_satisfy_the_gate(self):
        c = self.prepared(door_of_time_requirement='all',
                          start_inventory_from_pool=dict.fromkeys(ITEMS, 1))
        self.assertEqual(r.child_door_missing(c, {}), [])

    def test_child_pickup_needing_an_adult_item_is_rejected(self):
        c = self.prepared(start_inventory_from_pool={'Ocarina': 1})
        # Child-map reward, but its dependency can only be picked up as adult.
        c.logic.virtual[r.vname(KF_CHILD)].append('Souls|Progressive Hookshot')
        placed = {KF_CHILD: 'Song of Time', KF_ADULT: 'Progressive Hookshot'}
        self.assertEqual(r.child_door_missing(c, placed), ['Song of Time'])

    def test_assumed_time_travel_is_removed_from_child_sweep(self):
        c = self.prepared()
        state, collected, _ = c.sweep({KF_ADULT: 'Song of Time'}, {'Time Travel': 1}, before_adult=True)
        self.assertFalse(state.has('Time Travel'))
        self.assertNotIn(r.vname(KF_ADULT), collected)

    def test_open_door_does_not_restrict_gate_items(self):
        c = self.prepared(open_door_of_time=True, door_of_time_requirement='all')
        self.assertEqual(r.child_door_missing(c, {}), [])

    def test_shared_map_source_counts_as_child_access(self):
        c = self.prepared(start_inventory_from_pool={'Ocarina': 1})
        self.assertEqual(r.child_door_missing(c, {KF_BOTH: 'Song of Time'}), [])

    def test_replay_reports_the_missing_child_items_even_with_victory(self):
        c = self.prepared()
        # A victory shortcut must not let an invalid first age transition pass.
        c.starting['Triforce'] = 1
        with patch.object(r, 'prepare', return_value=c):
            result = r.plan(self.world, c.options, {}, [], 'replay', forced={KF_ADULT: 'Song of Time'})
        self.assertFalse(result['beatable'])
        self.assertEqual(result['before_adult_missing'], list(ITEMS[:2]))

    def test_generation_refuses_a_seed_missing_the_child_route(self):
        c = self.prepared()
        c.starting['Triforce'] = 1
        c.pool = ['Rupees (5)'] * len(c.shuffled)
        c.progression = []
        with patch.object(r, 'prepare', return_value=c), patch.object(r, 'MAX_ATTEMPTS', 1):
            with self.assertRaisesRegex(r.FillError, 'unavailable before adulthood: Ocarina, Song of Time'):
                r.plan(self.world, c.options, {}, [], 'invalid-child-route')


if __name__ == '__main__':
    unittest.main()
