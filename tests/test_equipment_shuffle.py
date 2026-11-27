"""Dedicated sword/card options select only their own native reward sources."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.logic import rando_options
from oot_rando.randomizer.full_randomizer import enabled_sources
from oot_rando.game.remake_world import actor_item, item_actor


class EquipmentOptions(unittest.TestCase):
    def test_options_are_independent_and_round_trip(self):
        for name, source in [('shuffle_master_sword', 'master_sword'),
                             ('shuffle_gerudo_card', 'gerudo_card')]:
            with self.subTest(name=name):
                self.assertFalse(rando_options.defaults()[name])
                options = rando_options.validate({name: True}, supported_only=True)
                self.assertEqual(enabled_sources(options), {source: 'all'})
                restored, ignored = rando_options.from_ap_yaml(to_ap_yaml(options))
                self.assertEqual(ignored, [])
                self.assertEqual(restored, options)
                self.assertTrue(rando_options.preset('everything')[name])

    def test_native_items_have_canonical_mappings(self):
        for actor, item in [('Item_Rando_MasterSword', 'Master Sword'),
                            ('Item_Token_Gerudo', 'Gerudo Membership Card')]:
            self.assertEqual(actor_item(actor, ''), item)
            self.assertEqual(item_actor(item, ''), actor)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class EquipmentSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from game_fixture import scan_world
        from oot_rando.logic.world import World
        _, cls.groups, cls.enemies, cls.extra = scan_world()
        cls.data = World()

    def test_native_reward_sites_and_option_scopes(self):
        from oot_rando.randomizer.full_randomizer import prepare
        cases = [('shuffle_master_sword', 'master_sword#ToT Master Sword', 'Master Sword'),
                 ('shuffle_gerudo_card', 'gerudo_card#Hideout Gerudo Membership Card',
                  'Gerudo Membership Card')]
        for option, gid, item in cases:
            with self.subTest(option=option):
                entry = self.extra[gid]
                self.assertIsNone(entry['reason'])
                self.assertEqual(entry['vanilla'], item)
                self.assertEqual(entry['kind'], 'exact')
                options = rando_options.validate({option: True}, supported_only=True)
                prepared = prepare(self.data, options, self.groups, self.enemies,
                                   'equipment-options', extra=self.extra)
                self.assertIn(gid, prepared.shuffled)
                self.assertIn(item, prepared.pool)
                self.assertEqual(prepared.base['Master Sword Pedestal'], 'Time Travel')
                for other, other_gid, _ in cases:
                    if other != option:
                        self.assertNotIn(other_gid, prepared.shuffled)

    def test_both_items_fill_and_replay(self):
        from oot_rando.randomizer.full_randomizer import plan, replay
        options = rando_options.validate({'shuffle_master_sword': True, 'shuffle_gerudo_card': True},
                                        supported_only=True)
        result = plan(self.data, options, self.groups, self.enemies, 'equipment-both', extra=self.extra)
        self.assertEqual(sum(p['item'] == 'Master Sword' for p in result['placements']), 1)
        self.assertEqual(sum(p['item'] == 'Gerudo Membership Card' for p in result['placements']), 1)
        checked = replay(self.data, options, self.groups, self.enemies,
                         {p['id']: p['item'] for p in result['placements']}, extra=self.extra)
        self.assertTrue(checked['beatable'])
        self.assertEqual(checked['unreachable'], [])
