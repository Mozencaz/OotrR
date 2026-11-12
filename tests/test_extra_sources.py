"""Skulltulas, shops, freestanding items, environment and NPC gifts mixed together.

Unit tests run everywhere; integration tests need OOT_NUP and the local
Archipelago OoT world (skipped otherwise).
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.logic import rando_options
from oot_rando.game.extra_sources import NPC_GIFTS, EXCLUDED_NPC_LOCATIONS, scan_map_sources
from oot_rando.randomizer.full_randomizer import enabled_sources, source_in_scope, tier_layout
from oot_rando.game.item_forms import can_take, form_actor, is_derived, canonical_of

NUP = os.environ.get('OOT_NUP')
NEW_SOURCES = {'tokensanity': 'all', 'shopsanity': '4', 'shuffle_freestanding_items': 'all',
               'shuffle_npc_gifts': True, 'shuffle_pots': 'all', 'shuffle_crates': 'all',
               'shuffle_beehives': True, 'shuffle_bushes': True, 'shuffle_rocks': True}


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
        self.assertEqual(form_actor('Item_Soul_Keese', 'world'), 'Obj_Rando_Item_Soul_Keese')
        self.assertTrue(can_take('Item_Longshot', 'world'))

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
        self.assertEqual(set(entries), {'HyruleField#rocks#1'})  # drop tables, no parameter, pots: untouched

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
            self.assertIn(source, ('boss', 'fairy', 'quest'))
            self.assertFalse(set(ap) & (npc | seen))
            seen.update(ap)
            # Every site of one reward gives the same AP item.
            self.assertEqual(len({actor_item(actor, '') for _, _, actor in sites}), 1, ap)
        self.assertEqual(sum(s == 'boss' for s, *_ in EVENT_GIFTS), 9)
        self.assertEqual(sum(s == 'fairy' for s, *_ in EVENT_GIFTS), 6)
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

    def test_tier_layout(self):
        chest = {'source': 'chest', 'ap': ['DC Bomb Bag Chest'], 'vanilla': 'Bomb Bag', 'before': 'Item_BombBag_Small'}
        goron = {'source': 'npc', 'ap': ['GC Rolling Goron as Child'], 'vanilla': 'Bomb Bag',
                 'before': 'Item_BombBag_Medium'}
        matches = {'c': chest, 'g': goron}
        # Chest only: the shuffled copy is the small bag, NPC upgrades stay dynamic.
        self.assertEqual(tier_layout(matches, {'c': chest}, ['Bomb Bag'])['Bomb Bag'], [0])
        # NPC only: the chest keeps the small bag, the NPC copy takes the next tier.
        self.assertEqual(tier_layout(matches, {'g': goron}, ['Bomb Bag'])['Bomb Bag'], [1])
        # Darunia unshuffled keeps the Goron bracelet.
        silver = {'source': 'chest', 'ap': ['x'], 'vanilla': 'Progressive Strength Upgrade',
                  'before': 'Item_Gauntlet_Silver'}
        layout = tier_layout({'s': silver}, {'s': silver}, ['Progressive Strength Upgrade'] * 2)
        self.assertEqual(layout['Progressive Strength Upgrade'], [1, 2])

    def test_options_and_yaml(self):
        values = rando_options.preset('everything')
        rando_options.validate(values, supported_only=True)
        imported, ignored = rando_options.from_ap_yaml(rando_options.to_ap_yaml(values))
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
        from oot_rando.game.extra_sources import scan_world
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.data = World()
        nup = Nup(NUP)
        try:
            _, cls.groups, cls.enemies, cls.extra = scan_world(nup, dictionaries(nup), effective_members(nup))
        finally:
            nup.stream.close()

    def plan(self, overrides, seed):
        from oot_rando.randomizer import full_randomizer
        options = dict(rando_options.defaults(), **overrides)
        return options, full_randomizer.plan(self.data, options, self.groups, self.enemies, seed, True,
                                             extra=self.extra)

    def test_inventory(self):
        counts = Counter(e['source'] for e in self.extra.values() if not e['reason'])
        self.assertEqual(counts['skulltula'], 100)
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
            for family, actors in PROGRESSIVE.items():
                spheres = {}
                for p in result['placements']:
                    if p['item'] == family:
                        base = next(a for a in actors if p['after'] in (a, 'Obj_Rando_' + a, 'Shop_Rando_' + a))
                        spheres[base] = p['sphere']
                ordered = [spheres[a] for a in actors if a in spheres]
                self.assertEqual(ordered, sorted(ordered), family)

    def test_shopsanity_keeps_logic_purchases(self):
        options, result = self.plan({'shopsanity': '4'}, 'shops')
        per_shop = Counter(p['folder'] for p in result['placements'] if p['source'] == 'shop')
        self.assertTrue(per_shop and all(count <= 4 for count in per_shop.values()), per_shop)
        shuffled = {p['id'] for p in result['placements']}
        referenced_kept = Counter(e['vanilla'] for gid, e in self.extra.items()
                                  if e['source'] == 'shop' and gid not in shuffled and not e['reason'])
        for name in ('Buy Deku Shield', 'Buy Hylian Shield', 'Buy Goron Tunic', 'Buy Zora Tunic'):
            self.assertGreaterEqual(referenced_kept[name], 1, name)


if __name__ == '__main__':
    unittest.main()
