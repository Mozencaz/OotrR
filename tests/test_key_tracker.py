"""Dungeon keys shown in the tracker: small keys found / total, boss key."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.patching.key_adapter import (APPLIED_PREFIX, RING_DUNGEONS, TRACKED_BOSS_KEYS, dungeon_keys,
                                            key_tracking)
from oot_rando.patching.soul_adapter import murmur3


def h(folder, field):
    return murmur3(f'DungeonInfo.{folder}.{field}')


SAVED = {'Int': {h(f, n) for f in RING_DUNGEONS for n in ('SmallKeyNum', 'SmallKeyTotalNum')},
         'Bool': {h(f, 'IsGetBossKey') for f in TRACKED_BOSS_KEYS} | {murmur3(APPLIED_PREFIX + 'FireTemple')}}


class KeyTrackingTests(unittest.TestCase):
    def test_rows(self):
        rows = key_tracking({'shuffle_smallkeys': 'dungeon'}, SAVED)
        by = {r['folder']: r for r in rows}
        self.assertEqual(set(by), set(RING_DUNGEONS) | set(TRACKED_BOSS_KEYS))
        self.assertEqual(by['ForestTemple']['small']['total'], 5)
        self.assertIsNone(by['BottomOfTheWell']['boss'])           # no boss key there
        self.assertIsNotNone(by['InsideGanonCastle']['boss'])       # Ganon's tower key
        self.assertIsNone(by['ForestTemple']['small']['ring'])      # no ring flag in this seed
        self.assertIsNotNone(by['FireTemple']['small']['ring'])
        self.assertEqual(by['ForestTemple']['dungeon'], 'Forest Temple')

    def test_found_counts(self):
        rows = key_tracking({}, SAVED)
        snapshot = {'int': {h('ForestTemple', 'SmallKeyTotalNum'): 3, h('ForestTemple', 'SmallKeyNum'): 1,
                            h('WaterTemple', 'SmallKeyNum'): 2},   # held, total not counted yet
                    'bool': {h('ForestTemple', 'IsGetBossKey'): True, murmur3(APPLIED_PREFIX + 'FireTemple'): True}}
        keys = {name: (small, boss) for name, small, boss in dungeon_keys(rows, snapshot)}
        self.assertEqual(keys['Forest Temple'], ((3, 5), True))
        self.assertEqual(keys['Water Temple'], ((2, 6), False))
        self.assertEqual(keys['Fire Temple'], ((8, 8), False))     # key ring applied
        self.assertEqual(keys['Bottom of the Well'], ((0, 3), None))
        self.assertEqual(keys["Ganon's Castle"], ((0, 2), False))

    def test_removed_keys_and_no_save(self):
        rows = key_tracking({'shuffle_smallkeys': 'remove', 'shuffle_bosskeys': 'remove'}, SAVED)
        keys = {name: (small, boss) for name, small, boss in dungeon_keys(rows, None)}
        self.assertEqual(keys['Shadow Temple'], ((5, 5), True))
        self.assertEqual(keys["Ganon's Castle"], ((2, 2), False))  # Ganon's key is not a temple key

    def test_unknown_entries_skipped(self):
        self.assertEqual(key_tracking({}, {'Int': set(), 'Bool': set()}), [])


if __name__ == '__main__':
    unittest.main()
