"""Deep underwater crates: never a child check, Iron Boots + Hookshot as adult."""
import _src_path  # noqa: F401
import unittest

from oot_rando.game.underwater import DEEP_DEPTH, drop_child_deep, mark_deep, mark_entries

# A 10 m x 10 m surface whose top is 1 m above its origin.
BOX = ({'X': -5.0, 'Y': -20.0, 'Z': -5.0}, {'X': 5.0, 'Y': 1.0, 'Z': 5.0})
STATIC = 'Banc/HyruleField/HyruleField_{}_Static.bcett.byml.zs'
DYNAMIC = 'Banc/HyruleField/HyruleField_{}_Dynamic.bcett.byml.zs'


def crate(ident, age, position, index=0):
    return {'id': f'HyruleField#crates#{ident}', 'source': 'crates', 'form': 'world', 'guards': [],
            'variants': [{'resource': DYNAMIC.format(age), 'index': index, 'position': position}]}


class DeepCrates(unittest.TestCase):
    def setUp(self):
        water = {'Gyaml': 'Obj_WaterPlane_A_01', 'Translate': [0.0, 128.5 - 1.0, 0.0]}
        self.maps = {}
        for age in ('Child', 'Adult'):
            # The water lives in the Static half, the crates in the Dynamic half.
            self.maps[STATIC.format(age)] = {'root': {'Actors': [water]}}
            self.maps[DYNAMIC.format(age)] = {'root': {'Actors': [
                {'Gyaml': 'Obj_BrokenBox_A_01', 'Translate': [0.0, 120.5, 0.0]},
                {'Gyaml': 'Obj_BrokenBox_A_01', 'Translate': [0.0, 128.0, 0.0]}]}}
        self.boxes = lambda name: BOX if 'WaterPlane' in name else None

    def entries(self):
        return {e['id']: e for e in (
            crate(1, 'Child', [0.0, 120.5, 0.0]), crate(2, 'Adult', [0.0, 120.5, 0.0]),
            crate(3, 'Child', [0.0, 128.0, 0.0], 1), crate(4, 'Child', [30.0, 120.5, 0.0]))}

    def test_water_of_the_static_map_covers_dynamic_crates(self):
        entries = self.entries()
        self.assertEqual(mark_deep(self.maps, entries, self.boxes), 2)
        self.assertTrue(entries['HyruleField#crates#1']['variants'][0].get('deep'))
        self.assertTrue(entries['HyruleField#crates#2']['variants'][0].get('deep'))
        # Shallow (0.5 m < DEEP_DEPTH) and dry crates stay reachable.
        self.assertLess(128.5 - 128.0, DEEP_DEPTH)
        self.assertFalse(entries['HyruleField#crates#3']['variants'][0].get('deep'))
        self.assertFalse(entries['HyruleField#crates#4']['variants'][0].get('deep'))
        # The glowing-form marking keeps its own per-map search.
        self.assertEqual(mark_entries(self.maps, entries, self.boxes), 0)

    def test_child_copies_leave_the_shuffle_adult_copies_stay(self):
        entries = self.entries()
        mark_deep(self.maps, entries, self.boxes)
        self.assertEqual(drop_child_deep(entries), ['HyruleField#crates#1'])
        self.assertEqual(sorted(entries), ['HyruleField#crates#2', 'HyruleField#crates#3',
                                           'HyruleField#crates#4'])

    def test_shared_source_keeps_only_its_adult_copy(self):
        entry = crate(5, 'Child', [0.0, 120.5, 0.0])
        entry['variants'].append({'resource': DYNAMIC.format('Adult'), 'index': 0, 'position': [0.0, 120.5, 0.0]})
        entries = {entry['id']: entry}
        mark_deep(self.maps, entries, self.boxes)
        self.assertEqual(drop_child_deep(entries), [])
        self.assertEqual([v['resource'] for v in entry['variants']], [DYNAMIC.format('Adult')])

    def test_only_crates_are_checked(self):
        entries = self.entries()
        entries['HyruleField#crates#1']['source'] = 'pots'
        mark_deep(self.maps, entries, self.boxes)
        self.assertFalse(entries['HyruleField#crates#1']['variants'][0].get('deep'))


class DeepCrateLogic(unittest.TestCase):
    def test_adult_deep_crate_needs_iron_boots_and_hookshot(self):
        from oot_rando.game.extra_sources import scan_map_sources
        from oot_rando.logic import rando_options
        from oot_rando.logic.world import World
        from oot_rando.randomizer.full_randomizer import DEEP_GUARD, prepare, vname
        actors = [{'Gyaml': 'Obj_BrokenBox_A_01', 'Hash': 7, 'Translate': [0.0, 120.5, 0.0]}]
        extra = scan_map_sources({DYNAMIC.format('Adult'): {'root': {'Actors': actors}}},
                                 lambda actor, field: True, lambda actor: False)
        gid = 'HyruleField#crates#7'
        extra[gid]['variants'][0]['deep'] = True
        options = dict(rando_options.defaults(), shuffle_crates='all')
        c = prepare(World(), options, {}, [], 'deep-crate', True, extra=extra)
        self.assertIn(DEEP_GUARD, c.logic.virtual[vname(gid)])


if __name__ == '__main__':
    unittest.main()
