"""Starting inventory, item pool and the "start with" / "removed" dungeon modes.

NUP-dependent tests need OOT_NUP.
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.logic import rando_options
from oot_rando.patching.key_adapter import (BOSS_KEY_DUNGEONS, MAP_DUNGEONS, RING_DUNGEONS,
                                            start_dungeon_values, start_logic_items)
from oot_rando.randomizer.full_randomizer import apply_item_pool, covered_by_start_values
from oot_rando.formats.evfl_tools import parse_flow

NUP = os.environ.get('OOT_NUP')
OPENING = 'Event/EventFlow/OpeningEvent.bfevfl.zs'


class OptionTests(unittest.TestCase):
    def test_parse_and_format_items(self):
        items = rando_options.parse_items('hover boots, Progressive Hookshot x2; heart container*3, Bow')
        self.assertEqual(items, {'Hover Boots': 1, 'Progressive Hookshot': 2, 'Heart Container': 3, 'Bow': 1})
        self.assertEqual(rando_options.parse_items(rando_options.format_items(items)), items)
        self.assertEqual(rando_options.parse_items('  '), {})
        self.assertEqual(rando_options.parse_items('zeldas lullaby'), {'Zeldas Lullaby': 1})
        with self.assertRaises(ValueError):
            rando_options.parse_items('Goron Tunic')

    def test_validate_items(self):
        values = rando_options.validate({'start_inventory_from_pool': {'Bow': 2}}, supported_only=True)
        self.assertEqual(values['start_inventory_from_pool'], {'Bow': 2})
        for bad in ({'Bow': 0}, {'Goron Tunic': 1}, ['Bow'], {'Bow': True}):
            with self.assertRaises(ValueError):
                rando_options.validate({'start_inventory_from_pool': bad})

    def test_defaults_are_not_shared(self):
        first = rando_options.defaults()
        first['start_inventory_from_pool']['Bow'] = 1
        self.assertEqual(rando_options.defaults()['start_inventory_from_pool'], {})

    def test_ap_yaml_round_trip(self):
        values = rando_options.validate({'start_inventory_from_pool': {'Hover Boots': 1, 'Bow': 2},
                                         'item_pool_value': 'scarce'})
        text = to_ap_yaml(values)
        self.assertIn('game: OoT Remake', text)
        self.assertIn("  item_pool_value: 'scarce'", text.split('OoT Remake application:')[0])
        imported, ignored = rando_options.from_ap_yaml(text)
        self.assertEqual(imported['start_inventory_from_pool'], {'Bow': 2, 'Hover Boots': 1})
        self.assertEqual(imported['item_pool_value'], 'scarce')
        self.assertEqual(ignored, [])

    def test_ap_start_inventory_is_imported(self):
        imported, ignored = rando_options.from_ap_yaml(
            'game: Ocarina of Time\nOcarina of Time:\n  start_inventory:\n    Bow: 1\n    Minuet of Forest: 1\n'
            '    Goron Tunic: 1\n')
        self.assertEqual(imported['start_inventory_from_pool'], {'Bow': 1, 'Minuet of Forest': 1})
        self.assertEqual(len(ignored), 1)

    def test_newly_supported_values(self):
        for name, value in (('shuffle_mapcompass', 'startwith'), ('shuffle_smallkeys', 'remove'),
                            ('shuffle_bosskeys', 'remove'), ('fast_chests', True),
                            ('logic_no_night_tokens_without_suns_song', True), ('item_pool_value', 'minimal')):
            with self.subTest(name=name):
                rando_options.validate({name: value}, supported_only=True)

    def test_spiritual_stones_option(self):
        from oot_rando.archipelago.bridge import ap_option_specs
        from oot_rando.randomizer.full_randomizer import ap_settings
        option = rando_options.BY_NAME['spiritual_stones']
        self.assertEqual((option.label, option.tab, option.default), ('Require Spiritual Stones', 'World', 'all'))
        self.assertEqual(option.allowed(), ('door', 'all', 'vanilla'))
        self.assertEqual(rando_options.defaults()['spiritual_stones'], 'all')
        for value in option.allowed():
            values = rando_options.validate({'spiritual_stones': value}, supported_only=True)
            self.assertEqual(ap_settings(values, True)['spiritual_stones'], value)
        with self.assertRaises(ValueError):
            rando_options.validate({'spiritual_stones': 'emerald'})
        spec = next(s for s in ap_option_specs() if s['name'] == 'spiritual_stones')
        self.assertEqual((spec['values'], spec['default']), (['door', 'all', 'vanilla'], 'all'))
        imported, ignored = rando_options.from_ap_yaml(to_ap_yaml(
            rando_options.validate({'spiritual_stones': 'vanilla'})))
        self.assertEqual((imported['spiritual_stones'], ignored), ('vanilla', []))
        older, _ = rando_options.from_ap_yaml('game: OoT Remake\nOoT Remake:\n  open_kakariko: open\n')
        self.assertEqual(older['spiritual_stones'], 'all')

    def test_recorded_options_leave_out_the_unrecorded_value(self):
        values = rando_options.defaults()
        self.assertNotIn('spiritual_stones', rando_options.recorded(values))
        self.assertNotIn('spiritual_stones', rando_options.recorded(dict(values, spiritual_stones='all')))
        self.assertEqual(rando_options.recorded(dict(values, spiritual_stones='vanilla'))['spiritual_stones'], 'vanilla')
        self.assertEqual(rando_options.stored_value({}, 'spiritual_stones'), 'all')
        self.assertEqual(rando_options.stored_value({'spiritual_stones': 'vanilla'}, 'spiritual_stones'), 'vanilla')
        self.assertEqual(rando_options.stored_value({}, 'open_kakariko'), 'closed')

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

    def test_escape_stones_and_door_requirements_have_separate_controls(self):
        from oot_rando.gui import randomizer_gui as g
        card = next(names for title, _, names in g.SETTING_GROUPS if title == 'Open world')
        self.assertNotIn('spiritual_stones', g.HIDDEN_OPTIONS)
        self.assertIn('spiritual_stones', card)
        self.assertIn('door_of_time_requirement', card)
        self.assertNotIn('door_of_time_requirement', g.HIDDEN_OPTIONS)

    def test_gui_values_preserve_the_separate_escape_choice(self):
        from types import SimpleNamespace
        from oot_rando.gui import randomizer_gui as g
        for mode in ('all', 'vanilla', 'song'):
            values = rando_options.validate({'door_of_time_requirement': mode, 'spiritual_stones': 'all'})
            fake = SimpleNamespace(full_vars=values, full_value=lambda option: values[option.name],
                                   options={'skip_chest_cutscenes': SimpleNamespace(get=lambda: False)})
            result = g.Application.full_values(fake)
            self.assertEqual(rando_options.escape_requirement(result), 'all')

    def test_every_setting_has_a_tooltip_and_a_place(self):
        from oot_rando.gui import randomizer_gui as g
        names = {o.name: o for o in rando_options.OPTIONS}
        placed = [n for _, _, group in g.SETTING_GROUPS for n in group]
        self.assertEqual(len(placed), len(set(placed)))
        for name in placed:
            if name.startswith('game:'):
                key = name[len('game:'):]
                self.assertIn(key, g.GAME_OPTION_COPY)
                self.assertTrue(g.OPTION_TIPS.get(key), key)
        shown_names = set()
        # Every option the page shows has its card (names of options absent from this
        # version are skipped by the layout).
        for option in rando_options.OPTIONS:
            if option.kind in ('items', 'list'):
                shown = True
            elif option.kind == 'bool':
                shown = len([v for v in (False, True) if option.supported(v)]) > 1
            elif option.kind == 'int':
                shown = len(option.supported_ints) > 1
            else:
                shown = len([v for v, _, reason in option.values if reason is None]) > 1
            if shown and option.name not in g.HIDDEN_OPTIONS:
                self.assertIn(option.name, placed, option.name)
                shown_names.add(option.name)
        self.assertTrue(set(g.HIDDEN_OPTIONS) <= set(names))
        for option in rando_options.OPTIONS:
            label, help_text = g.OPTION_COPY.get(option.name, (option.label, option.help))
            tip = g.option_tip(option, label, help_text)
            title, _, body = tip.partition('\n')
            self.assertEqual(title, label)
            if option.name in shown_names:
                self.assertTrue(body.strip(), option.name)   # every shown setting is explained


class DungeonStartTests(unittest.TestCase):
    def test_start_values(self):
        values = start_dungeon_values(dict(rando_options.defaults(), shuffle_mapcompass='startwith',
                                           shuffle_smallkeys='remove', shuffle_bosskeys='remove'))
        # Small keys: held and found counts.
        self.assertEqual(len(values), 2 * len(MAP_DUNGEONS) + 2 * len(RING_DUNGEONS) + len(BOSS_KEY_DUNGEONS))
        self.assertIs(values['DungeonInfo.ForestTemple.IsGetMap'], True)
        self.assertEqual(values['DungeonInfo.FireTemple.SmallKeyNum'], 8)
        self.assertEqual(values['DungeonInfo.FireTemple.SmallKeyTotalNum'], 8)
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
        self.assertEqual(pool['Progressive Hookshot'], 2)   # one copy per level
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
        from oot_rando.game.world_maps import effective_members
        from game_fixture import scan_maps
        cls.data = World()
        _, cls.groups, cls.enemies = scan_maps()
        nup = Nup(NUP)
        try:
            dic, members = dictionaries(nup), effective_members(nup)
            cls.opening = decompress(nup.read(members[OPENING]), dic)
            cls.gamedata = decompress(nup.read(members['GameData/GameDataList.Product.110.byml.zs']), dic)
        finally:
            nup.stream.close()

    def plan(self, overrides, seed='start'):
        from oot_rando.randomizer import full_randomizer
        options = dict(rando_options.defaults(), **overrides)
        return full_randomizer.plan(self.data, options, self.groups, self.enemies, seed, True)

    def test_start_values_written_after_the_seed_marker(self):
        from oot_rando.patching.event_patch import add_collection_markers, add_pouch_items, add_start_values, start_value_events
        from oot_rando.patching.key_adapter import check_start_values
        values = start_dungeon_values(dict(rando_options.defaults(), shuffle_mapcompass='startwith',
                                           shuffle_smallkeys='remove', shuffle_bosskeys='remove'))
        check_start_values(self.gamedata, values)
        marked, _ = add_collection_markers(self.opening, {'Event3': 'RandoSeed.test'})
        marked = add_pouch_items(marked, 'RandoCollected_Event3', ('Item_BulletBag_Small',))
        patched = add_start_values(marked, 'RandoCollected_Event3', values)
        events = {e.name: e for e in parse_flow(patched).flowchart.events}
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

    def test_starting_inventory_takes_lowest_levels(self):
        from oot_rando.game.item_forms import canonical_of, is_derived
        from oot_rando.patching.progressive import token_family
        result = self.plan({'start_inventory_from_pool': {'Progressive Hookshot': 1, 'Hover Boots': 1}})
        starting = {s['item']: s['actor'] for s in result['starting']}
        self.assertEqual(starting['Progressive Hookshot'], 'Item_Hookshot')
        # The copy left in the pool is a token: in game, the level above the hookshot held.
        placed = [p['after'] for p in result['placements'] if p['item'] == 'Progressive Hookshot']
        self.assertEqual(len(placed), 1)
        self.assertEqual(token_family(canonical_of(placed[0]) if is_derived(placed[0]) else placed[0]),
                         'Progressive Hookshot')
        self.assertFalse([p for p in result['placements'] if p['item'] == 'Hover Boots'])

    def test_chosen_key_rings(self):
        from oot_rando.randomizer import full_randomizer
        overrides = {'shuffle_smallkeys': 'keysanity', 'key_rings': 'choose',
                     'key_rings_list': ('Forest Temple', 'Bottom of the Well')}
        result = self.plan(overrides, 'rings')
        items = {p['id']: p['item'] for p in result['placements']}
        rings = sorted({i for i in items.values() if i.startswith('Small Key Ring (')})
        self.assertEqual(rings, ['Small Key Ring (Bottom of the Well)', 'Small Key Ring (Forest Temple)'])
        self.assertFalse([i for i in items.values() if i.startswith('Small Key (')])
        options = dict(rando_options.defaults(), **overrides)
        self.assertTrue(full_randomizer.replay(self.data, options, self.groups, self.enemies, items)['beatable'])

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


class KeyRingChoiceTests(unittest.TestCase):
    def test_folders(self):
        from oot_rando.randomizer.full_randomizer import key_ring_folders
        base = rando_options.defaults()
        self.assertEqual(key_ring_folders(base, 's'), [])
        self.assertEqual(len(key_ring_folders(dict(base, key_rings='all'), 's')), 8)
        chosen = dict(base, key_rings='choose', key_rings_list=('Fire Temple', 'Ganons Castle'))
        self.assertEqual(key_ring_folders(chosen, 's'), ['FireTemple', 'InsideGanonCastle'])
        draws = {tuple(key_ring_folders(dict(base, key_rings='random'), f'seed{i}')) for i in range(20)}
        self.assertGreater(len(draws), 5)
        self.assertTrue(all(draws))
        self.assertEqual(key_ring_folders(dict(base, key_rings='random'), 'x'),
                         key_ring_folders(dict(base, key_rings='random'), 'x'))

    def test_validation(self):
        base = dict(rando_options.defaults(), shuffle_smallkeys='keysanity')
        rando_options.validate(dict(base, key_rings='random'), supported_only=True)
        values = rando_options.validate(dict(base, key_rings='choose', key_rings_list=['Water Temple', 'Fire Temple']),
                                        supported_only=True)
        self.assertEqual(values['key_rings_list'], ('Fire Temple', 'Water Temple'))
        for bad in ({'key_rings': 'choose'}, {'key_rings': 'choose', 'key_rings_list': ['Deku Tree']},
                    {'key_rings': 'off'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rando_options.validate(dict(base, **bad), supported_only=True)

    def test_yaml_round_trips(self):
        from oot_rando.archipelago.bridge import ap_option_specs, player_yaml
        values = rando_options.validate(dict(rando_options.defaults(), shuffle_smallkeys='keysanity',
                                             key_rings='choose', key_rings_list=['Spirit Temple']))
        imported, ignored = rando_options.from_ap_yaml(to_ap_yaml(values))
        self.assertEqual(imported['key_rings_list'], ('Spirit Temple',))
        self.assertEqual(ignored, [])
        spec = next(s for s in ap_option_specs() if s['name'] == 'key_rings_list')
        self.assertEqual(spec['kind'], 'list')
        self.assertIn('  key_rings_list: ["Spirit Temple"]', player_yaml(values, True))


class DungeonItemTests(unittest.TestCase):
    def test_specific_actors_round_trip(self):
        from oot_rando.patching.key_adapter import key_actor_item, key_records, key_texts, specific_actor
        for item in ('Map (Deku Tree)', 'Compass (Ice Cavern)', 'Boss Key (Fire Temple)',
                     'Small Key Ring (Ganons Castle)'):
            with self.subTest(item=item):
                self.assertEqual(key_actor_item(specific_actor(item)), item)
                texts = key_texts(specific_actor(item), 'USen')
                self.assertTrue(texts['Name'] and texts['GetMessage'])
                self.assertTrue(key_texts(specific_actor(item), 'EUfr')['Name'])
        records = {r['actor']: r for r in key_records(['Map (Water Temple)', 'Compass (Jabu Jabus Belly)'])}
        self.assertEqual(records['Item_Map_WaterTemple']['gamedata'], 'DungeonInfo.WaterTemple.IsGetMap')
        self.assertEqual(records['Item_Compass_Jabu']['kind'], 'compass')

    def test_outside_modes_supported(self):
        for mode in ('any_dungeon', 'overworld', 'keysanity'):
            rando_options.validate({'shuffle_mapcompass': mode}, supported_only=True)
