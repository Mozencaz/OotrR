"""Check native adult map sources against the final rules used by the fill.

Requires OOT_NUP. This deliberately tests prepared rules, including source
matching and age prefixes, rather than just the upstream AP location rules.
"""
import _src_path  # noqa: F401
import os
import unittest
from collections import Counter
from unittest.mock import patch

from oot_rando.game.remake_world import source_age
from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer.full_randomizer import child_door_missing, prepare, vname


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class NativeAgeAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from game_fixture import scan_world

        _, groups, enemies, extra = scan_world()
        options = dict(rando_options.preset('everything'), door_of_time_requirement='all')
        cls.prepared = prepare(World(), options, groups, enemies,
                               'native-age-audit', extra=extra)
        counts = Counter({item: 99 for item in cls.prepared.relevant if item != 'Time Travel'})
        for members in cls.prepared.logic.virtual.values():
            for member in members:
                if member.startswith('Souls|'):
                    counts.update(dict.fromkeys(member.split('|')[1:], 99))
        counts.pop('Time Travel', None)
        cls.state, cls.collected, _ = cls.prepared.sweep({}, counts, before_adult=True)
        _, cls.adult_collected, _ = cls.prepared.sweep({}, counts + Counter({'Time Travel': 1}))

    def assert_adult_sources_blocked(self, skulltulas):
        sources = {gid: entry for gid, entry in self.prepared.matches.items()
                   if (entry['source'] == 'skulltula') == skulltulas
                   and source_age(entry['variants']) == 'adult'}
        self.assertGreater(len(sources), 0)
        self.assertFalse(self.state.has('Time Travel'))
        for gid, entry in sources.items():
            with self.subTest(source=gid, matching=entry['kind']):
                self.assertNotIn(vname(gid), self.collected)
                if vname(gid) in self.prepared.logic.virtual:
                    self.assertIn(vname(gid), self.adult_collected)

    def test_all_native_adult_skulltulas_wait_for_adulthood(self):
        self.assert_adult_sources_blocked(skulltulas=True)

    def test_all_other_native_adult_sources_wait_for_adulthood(self):
        self.assert_adult_sources_blocked(skulltulas=False)

    def test_dmc_rupee_and_fairy_memory_cannot_hold_a_required_door_stone(self):
        c = self.prepared
        sources = ('DeathMountainCrater#free#17524442172396680694',  # DMC_rupee_7
                   'HyruleField#2967378296224661060')  # fairy-memory chest
        for source in sources:
            self.assertIn(vname(source), c.logic.virtual)
            for stone in ('Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire'):
                with self.subTest(source=source, stone=stone):
                    # All other prerequisites are available; the only copy of
                    # this required stone is the reported physical pickup.
                    inventory = dict.fromkeys(c.relevant - {'Time Travel', stone, 'HF Fairy Memory Chest'}, 99)
                    native = {location: item for location, item in c.base.items() if item != stone}
                    with patch.dict(c.starting, inventory, clear=True), patch.dict(c.base, native, clear=True):
                        self.assertEqual(child_door_missing(c, {source: stone}), [stone])


if __name__ == '__main__':
    unittest.main()
