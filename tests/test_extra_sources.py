"""Skulltulas, shops, freestanding items, environment and NPC gifts mixed together.

Unit tests run everywhere; integration tests need OOT_NUP and the local
Archipelago OoT world (skipped otherwise).
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.logic import rando_options
from oot_rando.game.extra_sources import NPC_GIFTS, EXCLUDED_NPC_LOCATIONS, scan_map_sources
from oot_rando.randomizer.full_randomizer import enabled_sources, source_in_scope
from oot_rando.game.item_forms import can_take, form_actor, is_derived, is_world_derived, canonical_of

NUP = os.environ.get('OOT_NUP')
NEW_SOURCES = {'tokensanity': 'all', 'shopsanity': '4', 'shuffle_freestanding_items': 'all',
               'shuffle_npc_gifts': True, 'shuffle_pots': 'all', 'shuffle_crates': 'all',
               'shuffle_beehives': True, 'shuffle_bushes': True, 'shuffle_rocks': True,
               'shuffle_trees': True}


class Units(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(form_actor('Item_Hookshot', 'chest'), 'Item_Hookshot')
        self.assertEqual(form_actor('Item_Hookshot', 'event'), 'Item_Hookshot')
        self.assertEqual(form_actor('Item_Hookshot', 'world'), 'Obj_Rando_Item_Hookshot')
        self.assertEqual(form_actor('Item_Hookshot', 'shop'), 'Shop_Rando_Item_Hookshot')
        self.assertEqual(form_actor('Item_Token_Gold', 'world'), 'Obj_Token_Gold')
        self.assertEqual(form_actor('TBox_Rupee_Red', 'world'), 'Obj_Rupee_Red')
        self.assertEqual(form_actor('Obj_Heart_Piece', 'world'), 'Obj_Heart_Piece')
        self.assertTrue(is_derived('Shop_Rando_Item_Bottle'))
        self.assertEqual(canonical_of('Obj_Rando_Item_Bottle'), 'Item_Bottle')
        self.assertTrue(can_take('Shop_Bottle_Bug', 'shop'))
        self.assertFalse(can_take('Shop_Bottle_Bug', 'chest'))
        self.assertTrue(can_take('Item_Soul_Keese', 'world'))   # cross-category souls
        self.assertFalse(can_take('Item_Soul_Keese', 'shop'))   # purchase may skip the soul get event
        self.assertFalse(can_take('Item_Soul_Keese', 'event'))
        self.assertTrue(can_take('Item_Soul_Keese', 'chest'))
        # The native boss key: only the big chest sequence credits it.
        self.assertTrue(can_take('Item_Dungeon_BossKey', 'chest', actor='Obj_TBox_A_02_NoBake'))
        self.assertTrue(can_take('Item_Dungeon_BossKey', 'chest', actor='Obj_TBox_A_03'))
        self.assertFalse(can_take('Item_Dungeon_BossKey', 'chest', actor='Obj_TBox_A_01'))
        self.assertFalse(can_take('Item_Dungeon_BossKey', 'world'))
        self.assertTrue(can_take('Item_Dungeon_Map', 'chest', actor='Obj_TBox_A_01'))   # never needed
        self.assertTrue(can_take('Item_Dungeon_SmallKey', 'chest', actor='Obj_TBox_A_01'))
        self.assertEqual(form_actor('Item_Soul_Keese', 'world'), 'Obj_Rando_Item_Soul_Keese')
        self.assertTrue(can_take('Item_Longshot', 'world'))

    def test_ocarinas_never_get_the_hold_up_pose(self):
        # Chests, NPC hand-overs and shops play the item-get pose: it crashes with an ocarina.
        for ocarina in ('Item_Ocarina_Fairy', 'Item_Ocarina_Time'):
            self.assertFalse(can_take(ocarina, 'chest'))
            self.assertFalse(can_take(ocarina, 'shop'))
            self.assertFalse(can_take(ocarina, 'event', ['GC Rolling Goron as Child']))
            self.assertTrue(can_take(ocarina, 'event', ['LW Gift from Saria']))
            self.assertTrue(can_take(ocarina, 'event', ['HF Ocarina of Time Item']))
            self.assertTrue(can_take(ocarina, 'world'))

    def test_scan_map_sources(self):
        maps = {'Banc/KokiriForest/KokiriForest_Child_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 1},
            {'Gyaml': 'Obj_Heart_Piece', 'Hash': 2},
            {'Gyaml': 'Shop_DekuStick', 'Hash': 3, 'Dynamic': {'ShopItemIndex': 7}},
            {'Gyaml': 'Shop_Mask_Bunny', 'Hash': 4, 'Dynamic': {'ShopItemIndex': 2}},
            {'Gyaml': 'Obj_Pot_A_01', 'Hash': 5, 'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Blue'}},
            {'Gyaml': 'Obj_Plant_Grass_A_01_Respawn', 'Hash': 6, 'Dynamic': {'Drop__DropActor': 'Obj_Heart'}},
            {'Gyaml': 'Obj_Pot_A_01', 'Hash': 7, 'Dynamic': {'Drop__DropActor': 'Animal_Insect'}},
            {'Gyaml': 'Obj_Rupee_Green', 'Hash': 8, 'Presence': {'FlagName': 'x'}}]}}}
        entries = scan_map_sources(maps, lambda actor, field: True, lambda actor: False)
        by_source = {e['source']: e for e in entries.values()}
        gs = by_source['skulltula']
        self.assertEqual((gs['vanilla'], gs['form'], gs['variants'][0]['field'], gs['variants'][0]['before']),
                         ('Gold Skulltula Token', 'world', 'Drop__DropActor', None))
        shop = by_source['shop']
        self.assertEqual((shop['vanilla'], shop['form']), ('Buy Deku Stick (1)', 'shop'))
        self.assertNotIn('Shop_Mask_Bunny', {e['before'] for e in entries.values()})  # masks: child trade
        self.assertEqual(entries['KokiriForest#pots#5']['vanilla'], 'Rupees (5)')
        self.assertEqual(entries['KokiriForest#bushes#6']['reason'], 'drop_table_or_respawn_variant')
        self.assertNotIn('KokiriForest#pots#7', entries)  # bugs are not items
        self.assertEqual(entries['KokiriForest#free#8']['reason'], 'conditional_presence')
        self.assertEqual(entries['KokiriForest#free#2']['vanilla'], 'Piece of Heart')

    def test_rutos_letter_is_a_quest_reward(self):
        maps = {'Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Obj_Bottle_Letter', 'Hash': 9, 'Translate': [-151.6, 125.0, 461.0]}]}}}
        entry = scan_map_sources(maps)['HyruleField#letter#9']
        self.assertEqual((entry['source'], entry['form'], entry['kind'], entry['ap'], entry['vanilla']),
                         ('quest', 'world', 'exact', ['LH Underwater Item'], 'Rutos Letter'))
        self.assertEqual(entry['variants'][0]['field'], 'Gyaml')
        self.assertIsNone(entry['reason'])
        self.assertNotIn('LH Underwater Item', EXCLUDED_NPC_LOCATIONS)
        self.assertTrue(source_in_scope(entry, enabled_sources(
            rando_options.validate({'shuffle_quest_rewards': True}, supported_only=True))))
        self.assertFalse(source_in_scope(entry, enabled_sources(
            rando_options.validate({}, supported_only=True))))
        from oot_rando.game.remake_world import item_actor
        self.assertEqual(item_actor('Rutos Letter', ''), 'Item_Bottle_Letter')
        self.assertEqual(form_actor('Item_Bottle_Letter', 'world'), 'Obj_Rando_Item_Bottle_Letter')

    def test_empty_rocks_receive_a_drop(self):
        maps = {'Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': 1},
            {'Gyaml': 'Obj_BrokenRock_A_01', 'Hash': 2, 'Dynamic': {'Drop__DropTable': 'DropTable_Obj_Bomb'}},
            {'Gyaml': 'Obj_LiftRock_B_01', 'Hash': 3},
            {'Gyaml': 'Obj_Pot_A_01', 'Hash': 4}]}}}
        entries = scan_map_sources(maps, lambda actor, field: actor != 'Obj_LiftRock_B_01', lambda actor: False)
        rock = entries['HyruleField#rocks#1']
        self.assertEqual((rock['before'], rock['vanilla'], rock['form'], rock['reason']),
                         (None, 'Rupee (1)', 'world', None))
        self.assertEqual(rock['variants'][0]['before'], None)
        # Empty pots and crates take a drop too (Discord 14/11); drop tables and
        # actors without the instance parameter stay untouched.
        self.assertEqual(set(entries), {'HyruleField#rocks#1', 'HyruleField#pots#4'})
        self.assertEqual(entries['HyruleField#pots#4']['vanilla'], 'Rupee (1)')

    def test_trees_receive_a_drop(self):
        maps = {'Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Obj_Tree_A_01', 'Hash': 1},
            {'Gyaml': 'Obj_Tree_A_01', 'Hash': 2, 'Dynamic': {'Drop__DropTable': 'None'}},
            {'Gyaml': 'Obj_Tree_A_02', 'Hash': 3, 'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Blue'}},
            {'Gyaml': 'Obj_Tree_Tutorial_A_01', 'Hash': 4, 'Dynamic': {'DropDirRotateOffset': 65.0}},
            {'Gyaml': 'Land_Tree_A_01', 'Hash': 5}]}}}
        entries = scan_map_sources(maps, lambda actor, field: actor.startswith('Obj_'), lambda actor: False)
        # Explicit "None" drop table stays vanilla; scenery trees have no drop parameter.
        self.assertEqual(set(entries), {'HyruleField#trees#1', 'HyruleField#trees#3', 'HyruleField#trees#4'})
        self.assertEqual((entries['HyruleField#trees#1']['vanilla'], entries['HyruleField#trees#1']['reason']),
                         ('Rupee (1)', None))
        self.assertEqual(entries['HyruleField#trees#3']['vanilla'], 'Rupees (5)')
        self.assertEqual(enabled_sources({'shuffle_trees': True}).get('trees'), 'all')
        from oot_rando.patching.repeatable_adapter import REPEATABLE
        self.assertIn('trees', REPEATABLE)

    def test_fire_arrows_are_a_quest_reward(self):
        maps = {'Banc/HyruleField/HyruleField_Adult_Static.bcett.byml.zs': {'root': {'Actors': [
            {'Gyaml': 'Obj_Arrow_Fire', 'Hash': 7, 'Name': 'Item', 'Translate': [-158.1, 131.5, 523.4]}]}}}
        entry = scan_map_sources(maps)['HyruleField#firearrow#7']
        self.assertEqual((entry['source'], entry['form'], entry['kind'], entry['ap'], entry['vanilla']),
                         ('quest', 'world', 'exact', ['LH Sun'], 'Fire Arrows'))
        self.assertEqual(entry['variants'][0]['field'], 'Gyaml')
        self.assertIsNone(entry['reason'])
        self.assertNotIn('LH Sun', EXCLUDED_NPC_LOCATIONS)
        self.assertTrue(source_in_scope(entry, enabled_sources(
            rando_options.validate({'shuffle_quest_rewards': True}, supported_only=True))))
        from oot_rando.game.remake_world import actor_item, item_actor
        # Both magic arrows can be placed anywhere (Fire Arrows had no remake actor).
        for item, actor in (('Fire Arrows', 'Item_Arrow_Fire'), ('Ice Arrows', 'Item_Arrow_Ice')):
            self.assertEqual(item_actor(item, ''), actor)
            self.assertEqual(actor_item(actor, ''), item)
            self.assertEqual(form_actor(actor, 'world'), 'Obj_Rando_' + actor)
        self.assertIn('Fire Arrows', rando_options.STARTABLE_ITEMS)
        from oot_rando.patching.fire_arrows import placed_actor
        self.assertEqual(placed_actor([{'source': 'quest', 'before': 'Obj_Arrow_Fire',
                                        'after': 'Obj_Rando_Item_Hookshot'}]), 'Obj_Rando_Item_Hookshot')
        self.assertIsNone(placed_actor([{'source': 'quest', 'before': 'Obj_Arrow_Fire', 'after': 'Obj_Arrow_Fire'}]))
        self.assertIsNone(placed_actor([]))

    def test_category_options(self):
        values = rando_options.defaults()
        self.assertFalse(rando_options.category_checked(values, 'rocks'))
        values = rando_options.set_category(values, 'rocks', True)
        self.assertTrue(values['shuffle_rocks'])
        values = rando_options.set_category(values, 'dungeon_items', False)
        self.assertEqual((values['shuffle_mapcompass'], values['shuffle_bosskeys']), ('vanilla', 'vanilla'))
        for category, options in rando_options.CATEGORY_OPTIONS.items():
            for option, on, off in options:
                self.assertTrue(rando_options.BY_NAME[option].supported(on), option)
                self.assertTrue(rando_options.BY_NAME[option].supported(off), option)

    def test_biggoron_chain_excluded(self):
        locations = {l for ap, guards, _, _ in NPC_GIFTS for l in ap}
        self.assertFalse(locations & set(EXCLUDED_NPC_LOCATIONS))
        stems = {stem for _, _, stem, _ in NPC_GIFTS}
        for stem in ('Npc_Goron_Biggoron_Adult', 'SubEvent_GetSwordBigGoron', 'Npc_Hylia_017_Adult',
                     'Npc_Hylia_053_Adult', 'Npc_Kokiri_Fado_Adult', 'Npc_Hylia_012_Adult', 'Npc_Zora_KingZora_adult',
                     'Npc_Hylia_045_Adult', 'Dm_DeathMtTrail_0050', 'Npc_Hylia_049_Adult'):
            self.assertNotIn(stem, stems)

    def test_cutscene_rewards(self):
        from oot_rando.game.extra_sources import EVENT_GIFTS, BOSS_HEARTS
        from oot_rando.game.remake_world import actor_item
        npc = {l for ap, _, _, _ in NPC_GIFTS for l in ap}
        seen = set()
        for source, ap, _, sites in EVENT_GIFTS:
            self.assertIn(source, ('boss', 'fairy', 'quest', 'song', 'master_sword', 'gerudo_card'))
            self.assertFalse(set(ap) & (npc | seen))
            seen.update(ap)
            # Every site of one reward gives the same AP item.
            self.assertEqual(len({actor_item(actor, '') for _, _, actor in sites}), 1, ap)
        self.assertEqual(sum(s == 'boss' for s, *_ in EVENT_GIFTS), 9)
        self.assertEqual(sum(s == 'fairy' for s, *_ in EVENT_GIFTS), 6)
        self.assertEqual(sum(s == 'song' for s, *_ in EVENT_GIFTS), 12)
        self.assertEqual(len(BOSS_HEARTS), 8)
        for category, option in (('boss_rewards', 'shuffle_boss_rewards'), ('fairies', 'shuffle_great_fairies'),
                                 ('quest_rewards', 'shuffle_quest_rewards')):
            self.assertEqual(rando_options.CATEGORY_OPTIONS[category][0][0], option)

    def test_enabled_sources_and_scope(self):
        values = dict(rando_options.defaults(), tokensanity='dungeons', shuffle_npc_gifts=True)
        sources = enabled_sources(values)
        self.assertEqual(sources, {'skulltula': 'dungeons', 'npc': 'all'})
        self.assertTrue(source_in_scope({'source': 'skulltula', 'folder': 'ForestTemple'}, sources))
        self.assertFalse(source_in_scope({'source': 'skulltula', 'folder': 'KokiriForest'}, sources))
        self.assertFalse(source_in_scope({'source': 'shop', 'folder': 'Market'}, sources))
        self.assertEqual(enabled_sources(rando_options.defaults()), {})

    def test_options_and_yaml(self):
        values = rando_options.preset('everything')
        rando_options.validate(values, supported_only=True)
        imported, ignored = rando_options.from_ap_yaml(to_ap_yaml(values))
        self.assertEqual(imported, values)
        self.assertEqual(ignored, [])
        imported, _ = rando_options.from_ap_yaml('Ocarina of Time:\n  shopsanity: 3\n  tokensanity: all\n')
        self.assertEqual((imported['shopsanity'], imported['tokensanity']), ('3', 'all'))

    def test_full_mode_refuses_overlapping_categories(self):
        from oot_rando.randomizer.randomizer_core import Settings
        categories = dict.fromkeys(rando_options.defaults(), False)
        from oot_rando.game.randomizer_categories import CATEGORIES
        categories = dict.fromkeys(CATEGORIES, False)
        categories['pots'] = True
        with self.assertRaises(ValueError):
            Settings('s', randomize_chests=False, categories=categories,
                     full=dict(rando_options.defaults(), shuffle_pots='all')).validate()
        Settings('s', randomize_chests=False, categories=categories, full=rando_options.defaults()).validate()


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.logic.world import World
        from game_fixture import scan_world
        cls.data = World()
        _, cls.groups, cls.enemies, cls.extra = scan_world()

    def plan(self, overrides, seed):
        from oot_rando.randomizer import full_randomizer
        options = dict(rando_options.defaults(), **overrides)
        return options, full_randomizer.plan(self.data, options, self.groups, self.enemies, seed, True,
                                             extra=self.extra)

    def test_inventory(self):
        counts = Counter(e['source'] for e in self.extra.values() if not e['reason'])
        # 100 tokens minus the two child-only Death Mountain Crater ones
        # (remake_world.inaccessible_child_actor).
        self.assertEqual(counts['skulltula'], 98)
        self.assertFalse([e['id'] for e in self.extra.values()
                          if e['source'] == 'skulltula' and e['id'].startswith('DeathMountainCrater#')])
        self.assertEqual(counts['npc'], len(NPC_GIFTS))
        self.assertGreaterEqual(counts['shop'], 50)
        self.assertGreaterEqual(counts['freestanding'], 24)
        for entry in self.extra.values():
            if entry['source'] == 'npc':
                self.assertEqual(self.data.vanilla_item(entry['ap'][0]), entry['vanilla'], entry['id'])

    def test_everything_mixed_beatable(self):
        from oot_rando.randomizer import full_randomizer
        from oot_rando.game.remake_world import PROGRESSIVE
        for seed in ('x1', 'x2'):
            options, result = self.plan(dict(NEW_SOURCES, shuffle_enemy_spawns='bosses'), seed)
            items = {p['id']: p['item'] for p in result['placements']}
            replay = full_randomizer.replay(self.data, options, self.groups, self.enemies, items, True,
                                            extra=self.extra)
            self.assertTrue(replay['beatable'])
            self.assertEqual(replay['unreachable'], [])
            # The playthrough names each location as its spoiler row does (not an
            # approximate entry's first AP candidate, such as one pot name for many pots).
            rows = {row['id']: row['location'] for row in result['spoiler']}
            shown = [text.rpartition(' : ')[0] for sphere in result['playthrough'] for text in sphere['items']]
            self.assertTrue(shown)
            self.assertTrue(set(shown) <= set(rows.values()), set(shown) - set(rows.values()))
            approximate = {p['id'] for p in result['placements'] if p['kind'] != 'exact'}
            self.assertTrue(any(rows[gid] in shown for gid in approximate))
            sources = Counter(p['source'] for p in result['placements'])
            for source in ('chest', 'skulltula', 'shop', 'freestanding', 'npc', 'pots'):
                self.assertGreater(sources[source], 0, source)
            # Every category can receive anything: progression outside chests.
            progression = {'Progressive Hookshot', 'Bow', 'Bomb Bag', 'Megaton Hammer', 'Hover Boots', 'Iron Boots',
                           'Progressive Strength Upgrade', 'Gold Skulltula Token', 'Slingshot', 'Boomerang'}
            outside = {p['source'] for p in result['placements'] if p['item'] in progression}
            self.assertGreaterEqual(len(outside), 4, outside)
            for p in result['placements']:
                self.assertFalse(p['item'].startswith('Buy '))  # purchases never leave shops
                if p['form'] == 'world':
                    self.assertFalse(p['after'].startswith(('Item_', 'TBox_')), p)
                if p['form'] == 'shop':
                    self.assertTrue(p['after'].startswith('Shop_'), p)
                if p['source'] == 'skulltula':   # only the token's behaviour saves the skulltula
                    self.assertTrue(p['after'] == 'Obj_Token_Gold' or is_world_derived(p['after']), p)
            # Every progressive copy, whatever its source, is its own token (next level in game).
            from oot_rando.patching.progressive import token_family
            tokens = result['progressive']['tokens']
            self.assertEqual(replay['progressive'], result['progressive'])
            for p in result['placements']:
                canonical = canonical_of(p['after']) if is_derived(p['after']) else p['after']
                if p['item'] in PROGRESSIVE:
                    self.assertEqual((canonical, token_family(canonical)), (tokens[p['id']], p['item']), p)
            self.assertEqual(len(set(tokens.values())), len(tokens))

    def test_adult_map_sources_wait_for_adult_access(self):
        from oot_rando.randomizer import full_randomizer
        from oot_rando.game.remake_world import source_age
        for seed in ('age1', 'age2'):
            options, result = self.plan(NEW_SOURCES, seed)
            c = full_randomizer.prepare(self.data, options, self.groups, self.enemies, seed, True, extra=self.extra)
            _, _, spheres = c.sweep({p['id']: p['item'] for p in result['placements']})
            # Time Travel is collected with the pedestal: the adult moves from the next sphere on.
            adult_from = next(i for i, sphere in enumerate(spheres) if 'Master Sword Pedestal' in sphere) + 1
            adult = [p for p in result['placements']
                     if p['sphere'] is not None and source_age(c.matches[p['id']]['variants']) == 'adult']
            self.assertTrue(adult)
            for p in adult:
                self.assertGreaterEqual(p['sphere'], adult_from, (seed, p['id'], p['item']))

    def test_shops_counted_one_by_one(self):
        # Discord 16/11: the Market's three shops shared the count of one shop.
        from oot_rando.game.extra_sources import shop_groups
        shops = shop_groups({g: e for g, e in self.extra.items() if e['source'] == 'shop' and not e['reason']})
        per_folder = Counter(key.split('#', 1)[0] for key in set(shops.values()))
        self.assertEqual(per_folder['Market'], 3)              # bazaar, potion shop, bombchu shop
        self.assertEqual(per_folder['KakarikoVillage'], 2)     # bazaar, potion shop
        for folder in ('KokiriForest', 'GoronCity', 'ZoraDomain'):
            self.assertEqual(per_folder[folder], 1, folder)
        self.assertTrue(all(n == 8 for n in Counter(shops.values()).values()), Counter(shops.values()))
        options, result = self.plan({'shopsanity': '8'}, 'shops8')
        placed = Counter(shops[p['id']] for p in result['placements'] if p['source'] == 'shop')
        self.assertEqual(set(placed), set(shops.values()))      # every shop, the potion shops too
        # One copy of each purchase the logic uses stays on sale (11 on 17/11: shields, tunics,
        # bottle contents, one bombchu pack, nuts, sticks); every other slot is shuffled.
        kept = sorted(self.extra[g]['vanilla'] for g in shops if g not in {p['id'] for p in result['placements']})
        self.assertEqual(sum('Bombchu' in k for k in kept), 1, kept)      # any pack does (has_bombchus)
        self.assertEqual(sum('Deku Nut' in k for k in kept), 1, kept)
        self.assertLessEqual(len(kept), 11, kept)
        options, result = self.plan({'shopsanity': 'all'}, 'shops8')
        self.assertEqual(sum(p['source'] == 'shop' for p in result['placements']), len(shops))
        rewards = Counter(p['item'] for p in result['placements'])
        self.assertEqual(rewards['Goron Tunic'], 1)
        self.assertEqual(rewards['Zora Tunic'], 1)

    def test_shopsanity_keeps_logic_purchases(self):
        options, result = self.plan({'shopsanity': '4'}, 'shops')
        from oot_rando.game.extra_sources import shop_groups
        shops = shop_groups({g: e for g, e in self.extra.items() if e['source'] == 'shop'})
        per_shop = Counter(shops[p['id']] for p in result['placements'] if p['source'] == 'shop')
        self.assertEqual(set(per_shop), set(shops.values()))
        self.assertTrue(all(count <= 4 for count in per_shop.values()), per_shop)
        shuffled = {p['id'] for p in result['placements']}
        referenced_kept = Counter(e['vanilla'] for gid, e in self.extra.items()
                                  if e['source'] == 'shop' and gid not in shuffled and not e['reason'])
        for name in ('Buy Deku Shield', 'Buy Hylian Shield', 'Buy Goron Tunic', 'Buy Zora Tunic'):
            self.assertGreaterEqual(referenced_kept[name], 1, name)


if __name__ == '__main__':
    unittest.main()
