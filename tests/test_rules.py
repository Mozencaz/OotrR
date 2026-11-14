"""Rules the remake adds or that AP applies in Python (Rules.py), not in JSON."""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.logic.rules import Logic, shop_rule
from oot_rando.logic.world import World



class ShopRuleTests(unittest.TestCase):
    def test_ap_set_shop_rules(self):
        self.assertEqual(shop_rule('Buy Zora Tunic'), '(Progressive_Wallet, 2) and is_adult')
        self.assertEqual(shop_rule('Buy Goron Tunic'), 'Progressive_Wallet and is_adult')
        self.assertEqual(shop_rule('Buy Fish'), 'Progressive_Wallet and has_bottle')
        self.assertEqual(shop_rule('Buy Bombchu (5)'), 'found_bombchus')
        self.assertIsNone(shop_rule('Buy Deku Shield'))


class LogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = World()
        cls.logic = Logic(cls.data, {'open_forest': 'closed_deku'})

    def reachable(self, placements, counts=()):
        _, collected, _ = self.logic.sweep(placements, self.logic.new_state(Counter(counts)))
        return collected

    def test_links_pocket_needs_time_travel(self):
        # Rauru gives this reward after the first Master Sword pull: an ocarina
        # placed there must never be reachable at the start.
        self.assertNotIn('Links Pocket', self.reachable({'Links Pocket': 'Ocarina'}))
        self.assertIn('Links Pocket', self.reachable({'Links Pocket': None}, {'Time Travel': 1}))

    def test_night_tokens_need_suns_song_when_asked(self):
        class Night:
            tod = {'adult': True, 'child': True}
        hookshot = {'Progressive Hookshot': 1}
        song = dict(hookshot, **{'Ocarina': 1, 'Suns Song': 1})
        relaxed = dict(self.logic.location_rules)['SFM GS'][0][1]
        self.assertTrue(relaxed(Night, hookshot, 'adult'))
        strict = Logic(self.data, {'open_forest': 'closed_deku',
                                   'logic_no_night_tokens_without_suns_song': True})
        rule = dict(strict.location_rules)['SFM GS'][0][1]
        self.assertFalse(rule(Night, hookshot, 'adult'))
        self.assertTrue(rule(Night, song, 'adult'))
        # Other night locations keep waiting for the night.
        self.assertIs(dict(strict.location_rules)['Kak Anju as Adult'][0][1](Night, {}, 'adult'),
                      dict(self.logic.location_rules)['Kak Anju as Adult'][0][1](Night, {}, 'adult'))

    def test_saria_gift_waits_for_deku_tree(self):
        self.assertNotIn('LW Gift from Saria', self.reachable({'LW Gift from Saria': None}))
        self.assertIn('LW Gift from Saria', self.reachable({'LW Gift from Saria': None}, {'Deku Tree Clear': 1}))

    def test_saria_song_waits_for_darunia(self):
        # Remake: Saria teaches her song after Darunia (Fire Stone quest), not on
        # Zelda's letter alone: needs the child in Darunia's chamber (Zelda's Lullaby).
        song = 'Song from Saria'
        everything = {item: 9 for item in self.logic.referenced}
        self.assertNotIn(song, self.reachable({song: None}, {'Zeldas Letter': 1, 'Kokiri Sword': 1,
                                                             'Buy Deku Shield': 1, 'Deku Tree Clear': 1}))
        self.assertNotIn(song, self.reachable({song: None}, dict(everything, **{'Zeldas Lullaby': 0})))
        self.assertIn(song, self.reachable({song: None}, everything))

    def test_lost_dog_waits_for_kakariko_gate(self):
        # Remake: Richard only runs away once the Kakariko gate guard read Zelda's Letter.
        dog = 'Market Lost Dog'
        everything = {item: 9 for item in self.logic.referenced}
        no_letter = {dog: None, 'HC Zeldas Letter': None}
        without = dict(everything, **{'Zeldas Letter': 0, 'Kakariko Village Gate Open': 0})
        self.assertNotIn(dog, self.reachable(no_letter, without))
        self.assertIn(dog, self.reachable(no_letter, everything))

    def test_lost_woods_chest_needs_adult_bean_ride(self):
        # The remake's only Lost Woods chest stands on a ledge served by the
        # adult bean platform (soil near the bridge), not in a bombable grotto.
        chest = 'LW Near Shortcuts Grotto Chest'
        self.assertEqual(self.logic.location_region[chest], 'Lost Woods')
        self.assertNotIn(chest, self.reachable({chest: None}, {'Bomb Bag': 1, 'Progressive Strength Upgrade': 3}))
        self.assertNotIn(chest, self.reachable({chest: None}, {'Magic Bean': 1}))
        self.assertNotIn(chest, self.reachable({chest: None}, {'Time Travel': 1}))
        self.assertIn(chest, self.reachable({chest: None}, {'Time Travel': 1, 'Magic Bean': 1}))

    def test_shop_wallet_age_and_bottle(self):
        shops = {'ZD Shop Item 1': None, 'Market Potion Shop Item 8': None, 'KF Shop Item 1': None}
        everything_but = {item: 9 for item in self.logic.referenced}
        without_wallet = dict(everything_but, **{'Progressive Wallet': 0})
        reached = self.reachable(shops, without_wallet)
        self.assertNotIn('ZD Shop Item 1', reached)
        self.assertNotIn('Market Potion Shop Item 8', reached)
        self.assertIn('KF Shop Item 1', reached)
        self.assertIn('ZD Shop Item 1', self.reachable(shops, everything_but))

    def test_logic_bottles_match_ap_group(self):
        self.assertNotIn('Bottle with Big Poe', self.logic.bottles)
        self.assertIn('Deliver Letter', self.logic.bottles)


if __name__ == '__main__':
    unittest.main()


class GeneratedCodeTests(unittest.TestCase):
    """compile() only ever evaluates the shapes it generates."""

    def test_hostile_code_is_refused(self):
        from oot_rando.logic.rules import check_generated
        check_generated("lambda s,c,a:(c.get('Bow',0)>=1 and s.at('Root',lambda s,c,a:(a=='child')))")
        for source in ("lambda s,c,a:__import__('os').system('x')",
                       "lambda s,c,a:s.__class__",
                       "lambda s,c,a:c.get.__globals__",
                       "lambda s,c,a:open('x')",
                       "lambda s,c,a,b=print:b",
                       "lambda s,c,a:[x for x in c]",
                       "lambda s,c,a:c.get(key=1)",
                       "lambda s,c,a:c['x']",
                       "lambda s,c,a:1.5"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                check_generated(source)

    def test_seed_values_stay_quoted(self):
        # A seed's tracking.json gives the tracker its settings and extra requirements.
        from oot_rando.logic.rando_options import defaults
        from oot_rando.randomizer.full_randomizer import ap_settings
        settings = ap_settings(defaults(), True)
        settings['starting_age'] = "child')+__import__('os').system('echo pwned')#"
        hostile_item = "Bow',0)>=0 or __import__('os').system('x') or c.get('"
        logic = Logic(World(), settings, extra_location_requirements={'KF Kokiri Sword Chest': {hostile_item}})
        rule = logic.compile('True', {hostile_item})
        self.assertFalse(rule(None, {}, 'child'))      # the hostile name is only an item name
        self.assertTrue(rule(None, {hostile_item: 1}, 'child'))
