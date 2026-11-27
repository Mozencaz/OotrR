import _src_path  # noqa: F401
import unittest
from collections import Counter
from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import item_actor, actor_item
from oot_rando.logic.world import World
from oot_rando.logic import rando_options
from oot_rando.randomizer.full_randomizer import prepare


class ShopPoolTests(unittest.TestCase):
    def prepare(self, shopsanity):
        maps = {}
        for folder, tunic in (('GoronCity', 'Goron'), ('ZoraDomain', 'Zora')):
            maps[f'Banc/{folder}/{folder}_Adult_Static.bcett.byml.zs'] = {'root': {'Actors': [
                {'Gyaml': f'Shop_Armor_{tunic}', 'Hash': 1, 'Translate': [0., 0., 0.], 'Dynamic': {'ShopItemIndex': 0}},
                *[{'Gyaml': 'Shop_DekuStick', 'Hash': i + 2, 'Translate': [float(i), 0., 0.], 'Dynamic': {'ShopItemIndex': i + 1}}
                  for i in range(7)]]}}
        options = dict(rando_options.defaults(), shopsanity=shopsanity)
        return prepare(World(), options, {}, [], 'shop-tunics', extra=scan_map_sources(maps))

    def test_all_shops_add_one_of_each_tunic_to_pool(self):
        c = self.prepare('all')
        self.assertEqual(len(c.shuffled), 16)
        self.assertEqual(len(c.pool), len(c.shuffled))
        for tunic in ('Goron Tunic', 'Zora Tunic'):
            self.assertEqual(Counter(c.pool)[tunic], 1, tunic)
        self.assertFalse(any(i.startswith('Buy ') for i in c.pool))

    def test_partial_shops_keep_tunics_on_sale(self):
        c = self.prepare('8')
        for tunic in ('Goron Tunic', 'Zora Tunic'):
            self.assertNotIn(tunic, c.pool)
            self.assertIn('Buy ' + tunic, c.base.values())

    def test_tunics_have_reward_actors(self):
        for tunic, actor in (('Goron Tunic', 'Obj_Armor_Goron'), ('Zora Tunic', 'Obj_Armor_Zora')):
            self.assertEqual(item_actor(tunic, ''), actor)
            self.assertEqual(actor_item(actor, ''), tunic)


if __name__ == '__main__':
    unittest.main()
