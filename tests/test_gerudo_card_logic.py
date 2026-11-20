"""Shuffled Gerudo card: membership also needs the carpenters freed.

No native flow or logic module reads the card in the pouch: the fortress's
peace may follow the carpenters' quest (SageOfSpirit) instead of the card. Until
checked in game, the logic asks for both when the card is shuffled.
"""
import unittest

import _src_path  # noqa: F401
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World

CARPENTERS = ('Hideout 1 Torch Jail Carpenter', 'Hideout 2 Torches Jail Carpenter',
              'Hideout 3 Torches Jail Carpenter', 'Hideout 4 Torches Jail Carpenter')


class GerudoCardLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = World()
        cls.shuffled = Logic(world, {'shuffle_gerudo_card': True})
        cls.vanilla = Logic(world)

    def rule(self, logic, counts=None, events=()):
        state = logic.new_state(dict(counts or {}, **{e: 1 for e in events}))
        return logic.compile('has_gerudo_membership')(state, state.counts, 'adult')

    def test_vanilla_card_alone_gives_membership(self):
        self.assertTrue(self.rule(self.vanilla, {'Gerudo Membership Card': 1}))
        self.assertFalse(self.rule(self.vanilla))

    def test_shuffled_card_needs_the_carpenters_freed(self):
        card = {'Gerudo Membership Card': 1}
        self.assertFalse(self.rule(self.shuffled, card))
        self.assertFalse(self.rule(self.shuffled, events=CARPENTERS))
        self.assertTrue(self.rule(self.shuffled, card, CARPENTERS))

    def test_no_gerudo_rule_reads_the_card_directly(self):
        import json
        from pathlib import Path
        regions = Path(_src_path.__file__).resolve().parent.parent / 'src/oot_rando/logic/world/regions'
        for path in regions.glob('*.json'):
            with self.subTest(path=path.name):
                self.assertNotIn('Gerudo_Membership_Card', json.dumps(json.loads(path.read_text('utf-8'))))


if __name__ == '__main__':
    unittest.main()
