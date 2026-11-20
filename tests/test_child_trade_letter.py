"""Zelda's Letter stays Zelda's gift while the child trade quest is vanilla."""
import _src_path  # noqa: F401  (src on sys.path)
from collections import Counter
import unittest

from oot_rando.game.extra_sources import _entry
from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer.full_randomizer import kept_for_child_trade, prepare, vname

LETTER, SARIA = 'quest#HC Zeldas Letter', 'quest#LW Gift from Saria'


def quest(gid, location, stem, actor, vanilla):
    entry = _entry('quest', 'event', gid, 'Npc', actor, vanilla)
    entry.update(kind='exact', ap=[location], actors=[actor],
                 variants=[{'resource': f'Event/EventFlow/{stem}.bfevfl.zs', 'event': 'Event1',
                            'param': 'ActorName', 'before': actor}])
    return entry


def quest_sources():
    return {LETTER: quest(LETTER, 'HC Zeldas Letter', 'Dm_HrlCastle_0050', 'Item_ZeldaLetter', 'Zeldas Letter'),
            SARIA: quest(SARIA, 'LW Gift from Saria', 'Dm_Kokiri_0155', 'Item_Ocarina_Fairy', 'Ocarina')}


class ChildTradeLetterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = World()
        options = dict(rando_options.defaults(), shuffle_quest_rewards=True)
        cls.c = prepare(cls.data, options, {}, [], 'child-trade', True, extra=quest_sources())

    def test_letter_stays_with_zelda(self):
        self.assertNotIn(LETTER, self.c.shuffled)
        self.assertIn(SARIA, self.c.shuffled)
        self.assertEqual(self.c.base[vname(LETTER)], 'Zeldas Letter')
        self.assertNotIn('Zeldas Letter', self.c.pool)

    def test_letter_reached_through_the_castle_garden(self):
        placements = dict(self.c.base)
        for gid in self.c.logic_locations:
            placements.setdefault(vname(gid), None)
        everything = Counter({item: 9 for item in self.c.relevant if item != 'Zeldas Letter'})
        state, found, _ = self.c.logic.sweep(placements, self.c.logic.new_state(everything))
        self.assertIn(vname(LETTER), found)
        self.assertTrue(state.has('Zeldas Letter'))
        without_egg = dict(placements, **{'HC Malon Egg': None})
        state, found, _ = self.c.logic.sweep(without_egg, self.c.logic.new_state(Counter(
            {item: n for item, n in everything.items() if item != 'Weird Egg'})))
        self.assertNotIn(vname(LETTER), found)

    def test_only_a_vanilla_child_trade_keeps_it(self):
        letter = quest_sources()[LETTER]
        self.assertTrue(kept_for_child_trade(letter, rando_options.defaults()))
        for value in ('shuffle', 'skip_child_zelda'):
            self.assertFalse(kept_for_child_trade(letter, dict(rando_options.defaults(), shuffle_child_trade=value)))
        self.assertFalse(kept_for_child_trade(quest_sources()[SARIA], rando_options.defaults()))



class LetterRemovedTests(unittest.TestCase):
    """Kakariko gate open: the letter has no use left and leaves the pool."""
    @classmethod
    def setUpClass(cls):
        cls.data = World()
        options = dict(rando_options.defaults(), shuffle_quest_rewards=True, open_kakariko='open')
        cls.options = options
        cls.c = prepare(cls.data, options, {}, [], 'letter-removed', True, extra=quest_sources())

    def test_zelda_gift_is_shuffled_and_the_letter_gone(self):
        self.assertFalse(kept_for_child_trade(quest_sources()[LETTER], self.options))
        self.assertIn(LETTER, self.c.shuffled)
        self.assertNotIn('Zeldas Letter', self.c.pool)

    def test_nothing_needs_the_letter(self):
        placements = dict(self.c.base)
        for gid in self.c.logic_locations:
            placements.setdefault(vname(gid), None)
        everything = Counter({item: 9 for item in self.c.relevant if item != 'Zeldas Letter'})
        state, found, _ = self.c.logic.sweep(placements, self.c.logic.new_state(everything))
        for location in ('Song from Saria', 'Song from Malon', 'LLR Talons Chickens'):
            with self.subTest(location=location):
                self.assertIn(location, found)
        self.assertTrue(state.has('Skull Mask'))
        self.assertFalse(state.has('Zeldas Letter'))


if __name__ == '__main__':
    unittest.main()
