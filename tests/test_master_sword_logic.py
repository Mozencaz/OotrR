"""Shuffled adult swords do not gate age travel or grant implicit combat."""
import unittest

import _src_path  # noqa: F401
from oot_rando.logic.rules import Logic, vanilla_placements
from oot_rando.logic.world import World


class MasterSwordLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World()
        cls.shuffled = Logic(cls.world, {'shuffle_master_sword': True,
                                        'open_forest': 'open', 'open_door_of_time': True})
        cls.vanilla = Logic(cls.world)

    def rule(self, expression, counts=None, age='adult', logic=None):
        logic = logic or self.shuffled
        state = logic.new_state(counts)
        return logic.compile(expression)(state, state.counts, age)

    def location(self, location, region, counts=None, logic=None):
        logic = logic or self.shuffled
        state = logic.new_state(counts)
        state.reached['adult'].add(region)
        return logic.accessible(state, 'Adult|' + location)

    def test_adult_needs_a_usable_sword_for_sword_actions(self):
        for expression in ('has_adult_sword', 'can_jumpslash', 'can_cut_shrubs'):
            with self.subTest(expression=expression):
                self.assertFalse(self.rule(expression))
                self.assertFalse(self.rule(expression, {'Kokiri Sword': 1, 'Buy Deku Stick (1)': 1}))
                for sword in ('Master Sword', 'Biggoron Sword'):
                    self.assertTrue(self.rule(expression, {sword: 1}))
                    self.assertFalse(self.rule('has_adult_sword', {sword: 1}, age='child'))
                self.assertTrue(self.rule(expression, logic=self.vanilla))

    def test_adult_tools_remain_available_without_sword(self):
        for item, expression in (('Bow', 'can_use(Bow)'),
                                 ('Progressive Hookshot', 'can_use(Hookshot)'),
                                 ('Megaton Hammer', 'can_use(Megaton_Hammer)')):
            with self.subTest(item=item):
                self.assertTrue(self.rule(expression, {item: 1}))
                self.assertFalse(self.rule(expression, {item: 1}, age='child'))
        self.assertTrue(self.rule('can_use_projectile', {'Bow': 1}))
        self.assertTrue(self.rule('can_cut_shrubs', {'Bomb Bag': 1}))
        self.assertTrue(self.location('GC GS Center Platform', 'Goron City', {'Bow': 1}))
        self.assertFalse(self.location('GC GS Center Platform', 'Goron City'))

    def test_time_travel_can_unlock_an_adult_sword_location(self):
        logic = self.shuffled
        placements = {'Master Sword Pedestal': 'Time Travel',
                      'ToT Master Sword': 'Rupees (5)',
                      'Sheik at Temple': 'Master Sword'}
        # The Door of Time opens after Zelda's escape (three stones, Zelda met) and the Song of Time.
        start = {'Forest Medallion': 1, 'Kokiri Emerald': 1, 'Goron Ruby': 1, 'Zora Sapphire': 1,
                 'Met Zelda': 1, 'Ocarina': 1, 'Song of Time': 1}
        state, collected, spheres = logic.sweep(placements, logic.new_state(start), record_spheres=True)
        self.assertEqual(collected, set(placements))
        self.assertTrue(state.has('Time Travel'))
        self.assertTrue(state.has('Master Sword'))
        self.assertLess(next(i for i, s in enumerate(spheres) if 'Master Sword Pedestal' in s),
                        next(i for i, s in enumerate(spheres) if 'Sheik at Temple' in s))

    def test_new_reward_has_same_effective_pedestal_requirement(self):
        logic = Logic(self.world, {'shuffle_master_sword': True})
        state = logic.new_state({'Ocarina': 1, 'Song of Time': 1})
        state.reached['child'].add('Beyond Door of Time')
        for location in ('ToT Master Sword', 'Master Sword Pedestal'):
            self.assertFalse(logic.accessible(state, location))
        state.counts.update({'Kokiri Emerald': 1, 'Goron Ruby': 1, 'Zora Sapphire': 1,
                             'Met Zelda': 1})
        for location in ('ToT Master Sword', 'Master Sword Pedestal'):
            self.assertTrue(logic.accessible(state, location))
        placements = vanilla_placements(self.world, logic)
        self.assertEqual(placements['Master Sword Pedestal'], 'Time Travel')
        self.assertEqual(placements['ToT Master Sword'], 'Master Sword')
        self.assertTrue(self.world.is_progression('Master Sword'))

    def test_stalfos_and_gerudo_no_longer_assume_adult_sword(self):
        self.assertFalse(self.location('Forest Temple First Stalfos Chest',
                                       'Forest Temple Central Area'))
        self.assertTrue(self.location('Forest Temple First Stalfos Chest',
                                      'Forest Temple Central Area', {'Biggoron Sword': 1}))
        state = self.shuffled.new_state()
        state.reached['adult'].add('Hideout 1 Torch Jail')
        self.shuffled._expand_regions(state)
        self.assertFalse(state.has('Hideout 1 Torch Jail Gerudo'))
        state.add('Master Sword')
        self.shuffled._expand_regions(state)
        self.assertTrue(state.has('Hideout 1 Torch Jail Gerudo'))

    def test_boss_rewards_and_clear_events_require_sword(self):
        cases = [('Phantom Ganon', 'Phantom Ganon Boss Room', 'Forest Temple Clear',
                  {'Bow': 1}),
                 ('Morpha', 'Morpha Boss Room', 'Water Temple Clear',
                  {'Progressive Hookshot': 1}),
                 ('Twinrova', 'Twinrova Boss Room', 'Spirit Temple Clear',
                  {'Mirror Shield': 1}),
                 ('Bongo Bongo', 'Bongo Bongo Boss Room', 'Shadow Temple Clear',
                  {'Progressive Hookshot': 1, 'Lens of Truth': 1, 'Magic Meter': 1})]
        for location, region, event, tools in cases:
            with self.subTest(boss=location):
                self.assertFalse(self.location(location, region, tools))
                self.assertTrue(self.location(location, region, tools, logic=self.vanilla))
                state = self.shuffled.new_state(tools)
                state.reached['adult'].add(region)
                self.shuffled._expand_regions(state)
                self.assertFalse(state.has(event))
                state.add('Biggoron Sword')
                self.shuffled._expand_regions(state)
                self.assertTrue(state.has(event))
                self.assertTrue(self.shuffled.accessible(state, location))

    def test_ganon_requires_master_sword_instead_of_biggoron(self):
        tools = {'Bow': 1, 'Light Arrows': 1, 'Magic Meter': 1}
        self.assertFalse(self.location('Ganon', 'Ganondorf Boss Room', tools))
        self.assertFalse(self.location('Ganon', 'Ganondorf Boss Room',
                                       dict(tools, **{'Biggoron Sword': 1})))
        self.assertTrue(self.location('Ganon', 'Ganondorf Boss Room',
                                      dict(tools, **{'Master Sword': 1})))
        self.assertTrue(self.location('Ganon', 'Ganondorf Boss Room', tools, logic=self.vanilla))

    def test_gerudo_card_reward_and_access_are_independent(self):
        logic = Logic(self.world, {'shuffle_gerudo_card': True, 'gerudo_fortress': 'fast'})
        state = logic.new_state({'Small Key (Thieves Hideout)': 4})
        state.reached['adult'].add('Gerudo Fortress')
        logic._expand_regions(state)
        self.assertTrue(logic.accessible(state, 'Hideout Gerudo Membership Card'))
        self.assertNotIn('Gerudo Training Ground Lobby', state.reached['adult'])
        self.assertFalse(state.has('GF Gate Open'))
        state.add('Gerudo Membership Card')
        logic._expand_regions(state)
        self.assertIn('Gerudo Training Ground Lobby', state.reached['adult'])
        self.assertTrue(state.has('GF Gate Open'))


if __name__ == '__main__':
    unittest.main()
