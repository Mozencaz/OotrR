"""Adult start: the two first-adult checks (Light Medallion, Master Sword) hold green rupees."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer.full_randomizer import CASTLE_JUNK, adult_start_check, prepare
from test_child_castle_skip import source, sources

POCKET, SWORD = 'boss#Links Pocket', 'master_sword#ToT Master Sword'


def extra():
    return {**sources(),
            POCKET: source('boss', POCKET, 'Npc', 'Links Pocket', 'Item_Medal_Light', 'Light Medallion',
                           'Event/EventFlow/Dm_SageRoom_0005.bfevfl.zs'),
            SWORD: source('master_sword', SWORD, 'Npc', 'ToT Master Sword', 'Weapon_Sword_Master',
                          'Master Sword', 'Event/EventFlow/DoorOfTime.bfevfl.zs')}


class AdultStartChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = World()

    def run_prepare(self, **values):
        options = dict(rando_options.defaults(), tokensanity='all', **values)
        return prepare(self.data, options, {}, [], 'adult-checks', True, extra=extra())

    def test_predicate(self):
        entry = {'ap': ['Links Pocket'], 'source': 'boss'}
        self.assertTrue(adult_start_check(entry, {'starting_age': 'adult'}))
        self.assertFalse(adult_start_check(entry, {'starting_age': 'child'}))
        self.assertFalse(adult_start_check({'ap': ['Queen Gohma'], 'source': 'boss'}, {'starting_age': 'adult'}))

    def test_checks_hold_green_rupees_even_unshuffled(self):
        c = self.run_prepare(starting_age='adult')
        self.assertEqual(sorted(c.castle_junk), sorted([POCKET, SWORD]))
        for gid in (POCKET, SWORD):
            self.assertTrue(c.allowed(CASTLE_JUNK, gid))
            self.assertFalse(c.allowed('Gold Skulltula Token', gid))
        self.assertEqual(c.pool.count('Light Medallion'), 1)       # shuffled elsewhere
        self.assertNotIn('Master Sword', c.pool)                     # held from the start
        self.assertEqual(len(c.pool), len(c.shuffled))

    def test_shuffled_master_sword_stays_in_the_pool(self):
        c = self.run_prepare(starting_age='adult', shuffle_master_sword=True, shuffle_boss_rewards=True)
        self.assertEqual(c.pool.count('Master Sword'), 1)
        self.assertEqual(sorted(c.castle_junk), sorted([POCKET, SWORD]))

    def test_child_start_untouched(self):
        c = self.run_prepare()
        self.assertEqual(c.castle_junk, [])
        self.assertNotIn(POCKET, c.shuffled)


if __name__ == '__main__':
    unittest.main()
