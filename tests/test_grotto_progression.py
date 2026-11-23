"""Remake age restrictions must not put the first adult visit behind itself."""
import _src_path  # noqa: F401
import unittest
from collections import Counter

from oot_rando.game.extra_sources import match_sources, scan_map_sources
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World


class GrottoProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World()

    def test_cemetery_skulltulas_keep_their_own_rules(self):
        maps = {'Banc/Graveyard/Graveyard_Child_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 229475726653285413},
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 16798263777516949500},
        ]}}, 'Banc/Graveyard/Graveyard_Adult_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 229475726653285413},
        ]}}}
        entries = scan_map_sources(maps, lambda actor, field: True, lambda actor: False)
        logic = Logic(self.world)
        match_sources(entries, self.world, logic)
        self.assertEqual(entries['Graveyard#gs#229475726653285413']['ap'], ['Graveyard GS Wall'])
        self.assertEqual(entries['Graveyard#gs#16798263777516949500']['ap'], ['Graveyard GS Bean Patch'])
        logic.virtual = {gid: entry['ap'] for gid, entry in entries.items()}
        child = Counter({item: 9 for item in logic.referenced if item != 'Time Travel'})
        _, collected, _ = logic.sweep(dict.fromkeys(entries), logic.new_state(child))
        self.assertIn('Graveyard#gs#16798263777516949500', collected)
        self.assertNotIn('Graveyard#gs#229475726653285413', collected)

    def test_lullaby_on_adult_skulltula_cannot_unlock_its_own_stone(self):
        logic = Logic(self.world, {'open_forest': 'open', 'open_kakariko': 'open',
                                   'door_of_time_requirement': 'all', 'open_door_of_time': False})
        logic.virtual = {'wall': ['Graveyard GS Wall'],
                         'well': ['Bottom of the Well Underwater Left Chest']}
        placements = {'wall': 'Zeldas Lullaby', 'well': 'Goron Ruby',
                      'Master Sword Pedestal': 'Time Travel'}
        counts = Counter({item: 9 for item in logic.referenced
                          if item not in ('Time Travel', 'Goron Ruby', 'Zeldas Lullaby')})
        state, collected, _ = logic.sweep(placements, logic.new_state(counts))
        self.assertNotIn('wall', collected)
        self.assertNotIn('well', collected)
        self.assertFalse(state.has('Time Travel'))
        # Breaking the dependency on either side restores the route.
        for supplied in ('Zeldas Lullaby', 'Goron Ruby'):
            with self.subTest(supplied=supplied):
                state, collected, _ = logic.sweep(placements, logic.new_state(counts + Counter({supplied: 1})))
                self.assertIn('wall', collected)
                self.assertIn('well', collected)
                self.assertTrue(state.has('Time Travel'))

    def test_wall_drop_needs_adult_hookshot(self):
        logic = Logic(self.world)
        rule = dict(logic.location_rules)['Graveyard GS Wall'][0][1]
        state = logic.new_state()
        state.tod = {'child': True, 'adult': True}
        self.assertFalse(rule(state, {'Boomerang': 1}, 'child'))
        self.assertFalse(rule(state, {'Progressive Hookshot': 1}, 'child'))
        self.assertFalse(rule(state, {}, 'adult'))
        self.assertTrue(rule(state, {'Progressive Hookshot': 1}, 'adult'))

    def test_fairy_memory_chest_requires_a_prior_adult_visit(self):
        from oot_rando.game.remake_world import rule_members
        logic = Logic(self.world)
        logic.virtual = {'memory_chest': rule_members({
            'id': 'HyruleField#2967378296224661060', 'ap': ['HF Open Grotto Chest']})}
        counts = Counter({item: 9 for item in logic.referenced
                          if item not in ('Time Travel', 'HF Fairy Memory Chest')})
        _, collected, _ = logic.sweep({'memory_chest': None}, logic.new_state(counts))
        self.assertNotIn('memory_chest', collected)
        state, collected, _ = logic.sweep({'memory_chest': None},
                                         logic.new_state(counts + Counter({'Time Travel': 1})))
        self.assertIn('memory_chest', collected)
        rule = dict(logic.regions['Hyrule Field']['events'])['HF Fairy Memory Chest']
        self.assertTrue(rule(state, state.counts, 'child'))
        self.assertFalse(rule(state, state.counts, 'adult'))

    def test_field_scrub_is_only_accessible_as_adult(self):
        logic = Logic(self.world)
        rule = dict(logic.location_rules)['HF Deku Scrub Grotto'][0][1]
        state = logic.new_state()
        self.assertFalse(rule(state, {'Deku Shield': 1}, 'child'))
        self.assertTrue(rule(state, {'Progressive Hookshot': 1}, 'adult'))


if __name__ == '__main__':
    unittest.main()
