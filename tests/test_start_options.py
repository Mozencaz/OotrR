"""Starting inventory, item pool and the "start with" / "removed" dungeon modes.

NUP-dependent tests need OOT_NUP.
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.logic import rando_options
from oot_rando.patching.key_adapter import (BOSS_KEY_DUNGEONS, MAP_DUNGEONS, RING_DUNGEONS,
                                            start_dungeon_values, start_logic_items)
from oot_rando.randomizer.full_randomizer import apply_item_pool, covered_by_start_values

NUP = os.environ.get('OOT_NUP')
OPENING = 'Event/EventFlow/OpeningEvent.bfevfl.zs'


class OptionTests(unittest.TestCase):
    def test_parse_and_format_items(self):
        items = rando_options.parse_items('hover boots, Progressive Hookshot x2; heart container*3, Bow')
        self.assertEqual(items, {'Hover Boots': 1, 'Progressive Hookshot': 2, 'Heart Container': 3, 'Bow': 1})
        self.assertEqual(rando_options.parse_items(rando_options.format_items(items)), items)
        self.assertEqual(rando_options.parse_items('  '), {})
        with self.assertRaises(ValueError):
            rando_options.parse_items('Zeldas Lullaby')

    def test_validate_items(self):
        values = rando_options.validate({'start_inventory_from_pool': {'Bow': 2}}, supported_only=True)
        self.assertEqual(values['start_inventory_from_pool'], {'Bow': 2})
        for bad in ({'Bow': 0}, {'Minuet of Forest': 1}, ['Bow'], {'Bow': True}):
            with self.assertRaises(ValueError):
                rando_options.validate({'start_inventory_from_pool': bad})

    def test_defaults_are_not_shared(self):
        first = rando_options.defaults()
        first['start_inventory_from_pool']['Bow'] = 1
        self.assertEqual(rando_options.defaults()['start_inventory_from_pool'], {})

    def test_ap_yaml_round_trip(self):
        values = rando_options.validate({'start_inventory_from_pool': {'Hover Boots': 1, 'Bow': 2},
                                         'item_pool_value': 'scarce'})
        text = rando_options.to_ap_yaml(values)
        self.assertIn('game: OoT Remake', text)
        self.assertIn("  item_pool_value: 'scarce'", text.split('OoT Remake application:')[0])
        imported, ignored = rando_options.from_ap_yaml(text)
        self.assertEqual(imported['start_inventory_from_pool'], {'Bow': 2, 'Hover Boots': 1})
        self.assertEqual(imported['item_pool_value'], 'scarce')
        self.assertEqual(ignored, [])

    def test_ap_start_inventory_is_imported(self):
        imported, ignored = rando_options.from_ap_yaml(
            'game: Ocarina of Time\nOcarina of Time:\n  start_inventory:\n    Bow: 1\n    Minuet of Forest: 1\n')
        self.assertEqual(imported['start_inventory_from_pool'], {'Bow': 1})
        self.assertEqual(len(ignored), 1)

    def test_newly_supported_values(self):
        for name, value in (('shuffle_mapcompass', 'startwith'), ('shuffle_smallkeys', 'remove'),
                            ('shuffle_bosskeys', 'remove'), ('fast_chests', True),
                            ('logic_no_night_tokens_without_suns_song', True), ('item_pool_value', 'minimal')):
            with self.subTest(name=name):
                rando_options.validate({name: value}, supported_only=True)

    def test_apworld_specs_skip_the_inventory(self):
        from oot_rando.archipelago.bridge import ap_option_specs, player_yaml
        names = [spec['name'] for spec in ap_option_specs()]
        self.assertNotIn('start_inventory_from_pool', names)
        self.assertIn('item_pool_value', names)
        values = rando_options.validate({'start_inventory_from_pool': {'Bow': 1}}, supported_only=True)
        self.assertIn('  start_inventory_from_pool: {"Bow": 1}', player_yaml(values, True))


class GuiSourceTests(unittest.TestCase):
    def test_gui_module_compiles(self):
        # The GUI is not imported by the other tests (Tk): catch syntax errors here.
        from pathlib import Path
        source = Path(__file__).resolve().parents[1] / 'src' / 'oot_rando' / 'gui' / 'randomizer_gui.py'
        compile(source.read_text(encoding='utf-8'), str(source), 'exec')


class DungeonStartTests(unittest.TestCase):
    def test_start_values(self):
        values = start_dungeon_values(dict(rando_options.defaults(), shuffle_mapcompass='startwith',
                                           shuffle_smallkeys='remove', shuffle_bosskeys='remove'))
        self.assertEqual(len(values), 2 * len(MAP_DUNGEONS) + len(RING_DUNGEONS) + len(BOSS_KEY_DUNGEONS))
        self.assertIs(values['DungeonInfo.ForestTemple.IsGetMap'], True)
        self.assertEqual(values['DungeonInfo.FireTemple.SmallKeyNum'], 8)
        self.assertIs(values['DungeonInfo.SpiritTemple.IsGetBossKey'], True)
        self.assertNotIn('DungeonInfo.InsideGanonCastle.IsGetBossKey', values)
        self.assertEqual(start_dungeon_values(rando_options.defaults()), {})

    def test_logic_items(self):
        items = start_logic_items(dict(rando_options.defaults(), shuffle_smallkeys='remove', shuffle_bosskeys='remove'))
        self.assertEqual(items['Small Key (Fire Temple)'], 8)
        self.assertEqual(items['Boss Key (Water Temple)'], 1)
        self.assertNotIn('Boss Key (Ganons Castle)', items)

    def test_archipelago_starting_items_covered(self):
        options = dict(rando_options.defaults(), shuffle_mapcompass='startwith', shuffle_smallkeys='remove')
        self.assertTrue(covered_by_start_values('Map (Deku Tree)', options))
        self.assertTrue(covered_by_start_values('Small Key (Forest Temple)', options))
        self.assertFalse(covered_by_start_values('Boss Key (Forest Temple)', options))
        self.assertFalse(covered_by_start_values('Hover Boots', options))


class ItemPoolTests(unittest.TestCase):
    POOL = (['Bottle'] * 5 + ['Heart Container'] * 4 + ['Piece of Heart'] * 6 + ['Hover Boots', 'Double Defense',
            'Progressive Hookshot', 'Progressive Hookshot'] + ['Rupees (5)'] * 6 + ['Rupee (1)'] * 2)
    RELEVANT = {'Bottle', 'Hover Boots', 'Progressive Hookshot'}

    def test_count_never_changes(self):
        for value in ('balanced', 'plentiful', 'scarce', 'minimal'):
            with self.subTest(value=value):
                self.assertEqual(len(apply_item_pool(self.POOL, value, self.RELEVANT)), len(self.POOL))

    def test_balanced_is_identity(self):
        self.assertEqual(apply_item_pool(self.POOL, 'balanced', self.RELEVANT), self.POOL)

    def test_plentiful(self):
        pool = Counter(apply_item_pool(self.POOL, 'plentiful', self.RELEVANT))
        self.assertEqual(pool['Bottle'], 6)
        self.assertEqual(pool['Hover Boots'], 2)
        self.assertEqual(pool['Progressive Hookshot'], 2)   # tiers are fixed
        self.assertEqual(pool['Rupee (1)'], 0)              # cheapest filler first

    def test_scarce_and_minimal(self):
        scarce = Counter(apply_item_pool(self.POOL, 'scarce', self.RELEVANT))
        self.assertEqual((scarce['Bottle'], scarce['Heart Container'], scarce['Piece of Heart']), (3, 2, 3))
        minimal = Counter(apply_item_pool(self.POOL, 'minimal', self.RELEVANT))
        self.assertEqual((minimal['Bottle'], minimal['Heart Container'], minimal['Double Defense']), (1, 0, 0))
        self.assertEqual(minimal['Progressive Hookshot'], 2)


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.logic.world import World
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.remake_world import scan_maps
        from oot_rando.game.world_maps import effective_members
        cls.data = World()
        nup = Nup(NUP)
        try:
            dic, members = dictionaries(nup), effective_members(nup)
            _, cls.groups, cls.enemies = scan_maps(nup, dic, members)
            cls.opening = decompress(nup.read(members[OPENING]), dic)
            cls.gamedata = decompress(nup.read(members['GameData/GameDataList.Product.110.byml.zs']), dic)
        finally:
            nup.stream.close()

    def plan(self, overrides, seed='start'):
        from oot_rando.randomizer import full_randomizer
        options = dict(rando_options.defaults(), **overrides)
        return full_randomizer.plan(self.data, options, self.groups, self.enemies, seed, True)

    def test_start_values_written_after_the_seed_marker(self):
        from oot_rando.patching.event_patch import (_flow, add_collection_markers, add_pouch_items,
                                                    add_start_values, start_value_events)
        from oot_rando.patching.key_adapter import check_start_values
        values = start_dungeon_values(dict(rando_options.defaults(), shuffle_mapcompass='startwith',
                                           shuffle_smallkeys='remove', shuffle_bosskeys='remove'))
        check_start_values(self.gamedata, values)
        marked, _ = add_collection_markers(self.opening, {'Event3': 'RandoSeed.test'})
        marked = add_pouch_items(marked, 'RandoCollected_Event3', ('Item_BulletBag_Small',))
        patched = add_start_values(marked, 'RandoCollected_Event3', values)
        events = {e.name: e for e in _flow(patched).flowchart.events}
        event = events['RandoCollected_Event3']
        for name in start_value_events(values):
            event = event.data.nxt.v
            self.assertEqual(event.name, name)
        self.assertEqual(event.data.nxt.v.name, 'RandoStartItem_Item_BulletBag_Small')
        written = {e.data.params.data['GameDataName']: e.data.params.data['Value']
                   for name, e in events.items() if name.startswith('RandoStartValue_')}
        self.assertEqual(written, values)
        with self.assertRaises(ValueError):
            check_start_values(self.gamedata, {'DungeonInfo.Nowhere.IsGetMap': True})

    def test_starting_inventory_takes_lowest_tiers(self):
        result = self.plan({'start_inventory_from_pool': {'Progressive Hookshot': 1, 'Hover Boots': 1}})
        starting = {s['item']: s['actor'] for s in result['starting']}
        self.assertEqual(starting['Progressive Hookshot'], 'Item_Hookshot')
        placed = [p for p in result['placements'] if p['item'] == 'Progressive Hookshot']
        self.assertTrue(all(p['after'] == 'Item_Longshot' for p in placed))
        self.assertFalse([p for p in result['placements'] if p['item'] == 'Hover Boots'])

    def test_removed_keys_and_item_pools_beatable(self):
        from oot_rando.randomizer import full_randomizer
        for overrides in ({'shuffle_smallkeys': 'remove', 'shuffle_bosskeys': 'remove',
                           'shuffle_mapcompass': 'startwith'},
                          {'item_pool_value': 'plentiful'}, {'item_pool_value': 'minimal'},
                          {'logic_no_night_tokens_without_suns_song': True, 'tokensanity': 'all'}):
            with self.subTest(overrides=overrides):
                options = dict(rando_options.defaults(), **overrides)
                result = self.plan(overrides)
                items = {p['id']: p['item'] for p in result['placements']}
                replay = full_randomizer.replay(self.data, options, self.groups, self.enemies, items)
                self.assertTrue(replay['beatable'])
                self.assertFalse([i for i in items.values() if i.startswith(('Small Key (', 'Map ('))]
                                 if 'shuffle_smallkeys' in overrides else [])


if __name__ == '__main__':
    unittest.main()
