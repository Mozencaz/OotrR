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

    def test_goron_city_chests_follow_their_own_gimmick(self):
        # 16/11: GC_chest_6 (silver boulder) was in logic with bombs only.
        from oot_rando.game.remake_world import CHEST_RULE_EVENTS, rule_members
        self.assertEqual(sorted(set(CHEST_RULE_EVENTS.values())),
                         ['GC Hammer Rock Chest', 'GC Lower Ledge Chests', 'GC Maze Rocks', 'GC Silver Rock Chest',
                          'Kak Impas House Heart Piece', 'Kak Windmill Heart Piece'])
        self.logic.virtual = {'chest_6': rule_members({'id': 'GoronCity#3870071239709713434',
                                                       'ap': ['GC Maze Center Chest']}),
                              'chest_4': rule_members({'id': 'GoronCity#14647422914070455120', 'ap': []})}
        try:
            # Necro's inventory: bombs and one strength upgrade, child and adult.
            necro = {'Bomb Bag': 1, 'Progressive Strength Upgrade': 1, 'Ocarina': 1, 'Time Travel': 1}
            got = self.reachable({'chest_6': None, 'chest_4': None}, necro)
            self.assertIn('chest_4', got)
            self.assertNotIn('chest_6', got)
            silver = dict(necro, **{'Progressive Strength Upgrade': 2})
            self.assertIn('chest_6', self.reachable({'chest_6': None}, silver))
        finally:
            self.logic.virtual = {}
        self.assertEqual(rule_members({'id': 'Other#1', 'ap': ['KF Kokiri Sword Chest']}), ['KF Kokiri Sword Chest'])

    def test_kakariko_windmill_heart_piece_needs_adult_hookshot(self):
        # 17/11: Kak_heart_piece_2 (windmill) is reached as adult with the Hookshot.
        from oot_rando.game.remake_world import rule_members
        ap = ['Kak Impas House Freestanding PoH', 'Kak Windmill Freestanding PoH']
        self.logic.virtual = {
            'windmill': rule_members({'id': 'KakarikoVillage#free#13389209437182306002', 'ap': ap}),
            'impa': rule_members({'id': 'KakarikoVillage#free#17926402522258180222', 'ap': ap})}
        try:
            boomerang = {'Boomerang': 1, 'Ocarina': 1, 'Time Travel': 1}
            self.assertNotIn('windmill', self.reachable({'windmill': None}, boomerang))
            hookshot = dict(boomerang, **{'Progressive Hookshot': 1})
            self.assertIn('windmill', self.reachable({'windmill': None}, hookshot))
            self.assertIn('impa', self.reachable({'impa': None}, hookshot))
        finally:
            self.logic.virtual = {}

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

    def test_fire_temple_locked_door_needs_the_ring_once_keys_are_shuffled(self):
        # AP's "not keysanity" exception opens one Fire Temple door without its key
        # (a vanilla key may sit behind it). A key ring there locks itself in
        # (Discord 16/11: Fire Temple ring on Volvagia, boss key past that door).
        from oot_rando.logic.rando_options import defaults
        from oot_rando.randomizer.full_randomizer import ap_settings
        inventory = Counter({'Time Travel': 1, 'Megaton Hammer': 1, 'Goron Tunic': 1, 'Hover Boots': 1,
                             'Progressive Hookshot': 2, 'Bow': 1, 'Bomb Bag': 1,
                             'Progressive Strength Upgrade': 3, 'Ocarina': 1, 'Song of Time': 1,
                             'Bolero of Fire': 1, 'Kokiri Sword': 1, 'Hylian Shield': 1})
        chest = {'Fire Temple Boss Key Chest': None}
        for mode, locked in (('vanilla', False), ('dungeon', True)):
            options = defaults()
            options['shuffle_smallkeys'] = mode
            settings = ap_settings(options, True)
            self.assertIs(settings['keysanity'], locked)
            logic = Logic(self.data, settings)
            _, without, _ = logic.sweep(chest, logic.new_state(Counter(inventory)))
            self.assertEqual('Fire Temple Boss Key Chest' not in without, locked, mode)
            _, ring, _ = logic.sweep(chest, logic.new_state(inventory + Counter({'Small Key (Fire Temple)': 8})))
            self.assertIn('Fire Temple Boss Key Chest', ring, mode)

    def test_song_of_time_and_door_wait_for_zelda_and_stones(self):
        # Zelda's escape and the Door of Time (DoorOfTime) follow Zelda and the
        # three stones (the game checks the stones held: patching/story_fixes.py).
        for location in ('Song from Ocarina of Time', 'Master Sword Pedestal'):
            rule = self.data.remake['location_rules'][location]
            self.assertIn("'Met Zelda'", rule, location)
            self.assertIn('has_all_stones', rule, location)
            self.assertNotIn('Clear', rule, location)
        self.assertNotIn('Master Sword Pedestal', self.reachable(
            {'Master Sword Pedestal': None}, {'Ocarina': 1, 'Song of Time': 1}))

    def test_remake_events_compiled(self):
        events = {e for r in self.logic.regions.values() for e, _ in r['events']}
        self.assertIn('Met Zelda', events)

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

    def exit_rule(self, region, target):
        return dict(self.logic.regions[region]['exits'])[target]

    def test_remake_exit_rules_replace_base_exits(self):
        class Day:
            tod = {'adult': True, 'child': True}
        river = self.exit_rule('ZR Front', 'Zora River')
        self.assertFalse(river(Day, {}, 'adult'))
        self.assertTrue(river(Day, {'Megaton Hammer': 1}, 'adult'))
        self.assertTrue(river(Day, {'Bomb Bag': 1}, 'child'))
        shop = self.exit_rule('Market Back Alley', 'Market Bombchu Shop')
        self.assertFalse(shop(Day, {}, 'child'))

    def test_water_temple_gate_needs_iron_boots_or_thawed_king(self):
        class Day:
            tod = {'adult': True, 'child': True}
        gate = self.exit_rule('Lake Hylia', 'Water Temple Lobby')
        dive = {'Progressive Hookshot': 2, 'Progressive Scale': 2}
        self.assertFalse(gate(Day, dive, 'adult'))
        self.assertTrue(gate(Day, dict(dive, **{'King Zora Thawed': 1}), 'adult'))
        self.assertTrue(gate(Day, {'Progressive Hookshot': 1, 'Iron Boots': 1}, 'adult'))

    def test_unknown_remake_exit_is_refused(self):
        from oot_rando.logic import world
        world.REMAKE_EXIT_RULES['Nowhere -> Elsewhere'] = 'True'
        try:
            with self.assertRaises(ValueError):
                Logic(self.data, {'open_forest': 'closed_deku'})
        finally:
            del world.REMAKE_EXIT_RULES['Nowhere -> Elsewhere']

    def test_sheik_and_light_arrows_follow_bosses_not_medallions(self):
        # A starting medallion only fills the pouch: the sage scenes follow the boss.
        class Day:
            tod = {'adult': True, 'child': True}
        rules = dict(self.logic.location_rules)
        sheik = rules['Sheik at Temple'][0][1]
        self.assertFalse(sheik(Day, {'Forest Medallion': 1}, 'adult'))
        self.assertTrue(sheik(Day, {'Forest Temple Clear': 1}, 'adult'))
        lacs = rules['ToT Light Arrows Cutscene'][0][1]
        medals = {'Shadow Medallion': 1, 'Spirit Medallion': 1}
        self.assertFalse(lacs(Day, medals, 'adult'))
        self.assertTrue(lacs(Day, dict(medals, **{'Shadow Temple Clear': 1, 'Spirit Temple Clear': 1}), 'adult'))

    def test_stricter_rules_stay_reachable_with_open_zones(self):
        # The stricter remake rules must not cut a check off once a zone starts
        # open; the boss events come from the boss rooms, never from the pouch.
        checks = ['Gerudo Training Ground Heavy Block First Chest', 'GC Maze Center Chest', 'GC Maze Right Chest',
                  'LH Sun', 'Big Poe Kill', 'Colossus Great Fairy Reward', 'OGC Great Fairy Reward',
                  'Sheik at Temple', 'Sheik in Kakariko', 'ToT Light Arrows Cutscene']
        events = {'Dodongos Cavern Clear', 'Forest Temple Clear', 'Fire Temple Clear', 'Water Temple Clear',
                  'Shadow Temple Clear', 'Spirit Temple Clear'}
        for options in ({'open_forest': 'closed_deku'}, {'open_forest': 'open'},
                        {'open_forest': 'open', 'open_kakariko': 'open'},
                        {'open_forest': 'open', 'open_door_of_time': True},
                        {'open_forest': 'open', 'zora_fountain': 'open', 'gerudo_fortress': 'open'}):
            logic = Logic(self.data, options)
            items = Counter({item: 9 for item in logic.referenced if item not in events})
            _, collected, _ = logic.sweep({check: None for check in checks}, logic.new_state(items))
            for check in checks:
                self.assertIn(check, collected, f'{check} with {options}')

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
