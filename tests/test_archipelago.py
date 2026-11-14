"""Archipelago bridge: options, IDs, patches; with OOT_NUP, the catalog, the
apworld contents and applying Archipelago placements."""
import _src_path  # noqa: F401  (src on sys.path)
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from oot_rando.archipelago import bridge
from oot_rando.logic import rando_options

NUP = os.environ.get('OOT_NUP')


def sample_patch(**changes):
    patch = {'format': bridge.PATCH_FORMAT, 'version': bridge.PATCH_VERSION, 'game_build': 'b', 'world': 'w',
             'scan': 's', 'seed_key': 'k', 'options': rando_options.defaults(), 'open_forest': True,
             'placements': {'A#1': {'item': 'Bow', 'own': True, 'sphere': 2},
                            'A#2': {'item': 'Sword', 'own': False, 'player': 'Ami', 'sphere': 1}},
             'remote': [], 'seed_name': '123', 'slot_name': 'Moi'}
    patch.update(changes)
    return patch


class Units(unittest.TestCase):
    def test_option_specs(self):
        specs = {spec['name']: spec for spec in bridge.ap_option_specs()}
        self.assertEqual(next(iter(specs)), 'open_forest')
        self.assertNotIn('accessibility', specs)
        self.assertNotIn('logic_rules', specs)          # a single supported value: not exposed
        for spec in specs.values():
            self.assertGreaterEqual(len(spec['values']), 2)
            if spec['kind'] == 'list':
                self.assertLessEqual(set(spec['default']), set(spec['values']))
            else:
                self.assertIn(spec['default'], spec['values'])
        self.assertIn('random', specs['shopsanity']['values'])

    def test_random_value_is_renamed(self):
        self.assertEqual(bridge.ap_value_name('random'), 'randomized')
        self.assertEqual(bridge.ap_value_name('4'), '4')

    def test_full_options_roundtrip(self):
        values = {'open_forest': False, 'shopsanity': '2', 'tokensanity': 'all'}
        options, open_forest = bridge.full_options(values)
        self.assertFalse(open_forest)
        self.assertEqual((options['shopsanity'], options['tokensanity'], options['accessibility']),
                         ('2', 'all', 'minimal'))
        with self.assertRaises(ValueError):
            bridge.full_options({'shuffle_smallkeys': 'keysanity'})   # needs key rings

    def test_player_yaml_quotes_choices(self):
        values = dict(rando_options.defaults(), shopsanity='random', key_rings='off')
        text = bridge.player_yaml(values, True, 'Moi !')
        self.assertIn('name: Moi\n', text)
        self.assertIn(f'game: {bridge.GAME}\n', text)
        self.assertIn("  shopsanity: 'randomized'\n", text)
        self.assertIn("  key_rings: 'off'\n", text)
        self.assertIn('  open_forest: true\n', text)

    def test_stable_ids(self):
        first = bridge.stable_id('location', 'KF Midos Top Left Chest')
        self.assertEqual(first, bridge.stable_id('location', 'KF Midos Top Left Chest'))
        self.assertNotEqual(first, bridge.stable_id('item', 'KF Midos Top Left Chest'))
        self.assertTrue(0 < first < 2 ** 53)

    def test_patch_helpers(self):
        patch = bridge.check_patch(sample_patch())
        self.assertEqual(bridge.assigned_items(patch), {'A#1': 'Bow', 'A#2': 'Archipelago: Sword (Ami)'})
        self.assertEqual(bridge.foreign_items(patch), {'Archipelago: Sword (Ami)': ('Sword', 'Ami')})
        self.assertEqual(bridge.foreign_labels(patch), {'A#2': 'Sword (Ami)'})
        self.assertEqual(bridge.patch_spheres(patch), {'A#1': 2, 'A#2': 1})
        old = sample_patch(placements={'A#1': {'item': 'Bow', 'own': True}})
        self.assertIsNone(bridge.patch_spheres(old))

    def test_patch_refused(self):
        for broken in (sample_patch(format='other'), sample_patch(version=99),
                       sample_patch(placements={'A#1': {'item': 'Bow'}})):
            with self.assertRaises(ValueError):
                bridge.check_patch(broken)
        broken = sample_patch()
        del broken['seed_key']
        with self.assertRaises(ValueError):
            bridge.check_patch(broken)

    def test_patch_shape_is_checked_in_full(self):
        good = {'item': 'Sword', 'location': 'Somewhere', 'player': 'Ami'}
        bridge.check_patch(sample_patch(remote=[good], precollected=['Bow'], location_ids={'A#1': 5}, player=2))
        hostile = (
            sample_patch(open_forest='yes'), sample_patch(options=[]), sample_patch(player='2'),
            sample_patch(game='Other Game'), sample_patch(seed_key=7),
            sample_patch(placements={'A#1': {'item': 'Bow\x0e\x00', 'own': True}}),     # control codes
            sample_patch(placements={'A#1': {'item': 'B' * 5000, 'own': True}}),         # oversized name
            sample_patch(placements={'A#1': {'item': 'Bow', 'own': True, 'sphere': '2'}}),
            sample_patch(placements={'A#1': {'item': 'Bow', 'own': False, 'player': ['x']}}),
            sample_patch(remote={'item': 'Sword'}), sample_patch(remote=[dict(good, location=None)]),
            sample_patch(remote=[dict(good, player='Ami\nRoot')]),
            sample_patch(precollected='Bow'), sample_patch(precollected=[1]),
            sample_patch(location_ids={'A#1': '5'}), sample_patch(location_ids={'A#1': -1}),
            sample_patch(slot_name='x' * 1000))
        for patch in hostile:
            with self.subTest(patch={k: v for k, v in patch.items() if k != 'options'}), self.assertRaises(ValueError):
                bridge.check_patch(patch)

    def test_settings_must_match_patch(self):
        from oot_rando.randomizer.randomizer_core import Settings
        settings = bridge.settings_from_patch(sample_patch())
        self.assertIsNotNone(settings.archipelago)
        self.assertIn('archipelago', settings.to_dict())
        self.assertNotIn('archipelago', Settings('x').to_dict())   # earlier seeds keep their identity
        with self.assertRaises(ValueError):
            Settings.from_dict(dict(settings.to_dict(), open_forest=False))
        with self.assertRaises(ValueError):
            Settings.from_dict(dict(settings.to_dict(), full=dict(settings.full, tokensanity='all')))

    def test_starting_actors(self):
        from oot_rando.randomizer.full_randomizer import FillError, starting_actors
        from oot_rando.patching.event_patch import starting_item_events
        tiers = {'Progressive Hookshot': [0, 1]}
        self.assertEqual(starting_actors(['Progressive Hookshot', 'Hover Boots'], tiers),
                         ['Item_Hookshot', 'Item_HoverBoot'])
        self.assertEqual(starting_actors(['Progressive Hookshot'] * 2, tiers), ['Item_Hookshot', 'Item_Longshot'])
        with self.assertRaises(FillError):
            starting_actors(['Progressive Hookshot'] * 3, tiers)
        with self.assertRaises(FillError):
            starting_actors(['Small Key (Forest Temple)'], tiers)
        self.assertEqual(starting_item_events(['Item_Bottle', 'Obj_Heart_Piece', 'Item_Bottle']),
                         ['RandoStartItem_Item_Bottle', 'RandoStartItem_Obj_Heart_Piece', 'RandoStartItem_Item_Bottle_2'])

    def test_starting_pouch_items(self):
        from oot_rando.randomizer.randomizer_core import STARTING_ITEMS, starting_pouch_items
        self.assertEqual(starting_pouch_items(None), list(STARTING_ITEMS))
        full = {'archipelago': {'starting': [{'item': 'Hover Boots', 'actor': 'Item_HoverBoot'}]}}
        self.assertEqual(starting_pouch_items(full), list(STARTING_ITEMS) + ['Item_HoverBoot'])

    def test_template_is_not_a_module(self):
        from oot_rando.archipelago import apworld_build
        from oot_rando.paths import resource
        self.assertTrue(resource(apworld_build.TEMPLATE).is_file())
        self.assertFalse(apworld_build.TEMPLATE.endswith('.py'))   # selftest imports every module
        for name, source in apworld_build.vendored_files():
            self.assertTrue(source.is_file(), name)


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.archipelago.apworld_build import scan_game
        from oot_rando.logic.world import World
        cls.build, cls.groups, cls.enemies, cls.extra = scan_game(NUP)
        cls.catalog = bridge.build_catalog(World(), cls.groups, cls.enemies, cls.extra, cls.build)
        cls.values = {'open_forest': True, 'tokensanity': 'all', 'shuffle_enemy_spawns': 'regional',
                      'shuffle_npc_gifts': True}

    def player(self, key='archipelago|test|1'):
        return bridge.PlayerWorld(self.catalog, self.values, key)

    def test_catalog_covers_player_worlds(self):
        world = self.player()
        self.assertTrue(set(world.names) <= set(self.catalog['locations']))
        self.assertTrue(set(world.pool) <= set(self.catalog['items']))
        self.assertEqual(len(world.pool), len(world.names))   # one item per location
        self.assertEqual(len(set(bridge.location_ids(self.catalog).values())), len(self.catalog['locations']))
        self.assertEqual(self.catalog['scan'], bridge.scan_fingerprint(self.groups, self.enemies, self.extra))

    def test_rules_and_victory(self):
        world = self.player()
        nothing, beaten = world.reach(Counter())
        self.assertFalse(beaten)
        everything, beaten = world.reach(Counter(i for i in world.pool if i in world.progression))
        self.assertTrue(beaten)
        self.assertLess(len(nothing), len(everything))
        logic = [g for g, inside in world.in_logic.items() if inside]
        self.assertTrue(any(world.reachable(g, Counter()) for g in logic))
        self.assertIs(world.reach(Counter()), world.reach(Counter()))   # cached

    def test_local_only_items(self):
        world = self.player()
        from oot_rando.game.remake_world import PROGRESSIVE
        progressive = set(PROGRESSIVE) & set(world.pool)
        # Every family is either handed over by the client (dynamic tiers) or kept here.
        self.assertEqual(progressive, (progressive & world.local_only) | world.dynamic)
        self.assertFalse(world.dynamic & world.local_only)
        self.assertTrue(world.dynamic, 'no progressive family can go to another world')
        self.assertTrue(world.restricted <= world.local_only)
        # A dynamic copy found here is an Archipelago item: same locations as one.
        for family in world.dynamic:
            self.assertEqual([g for g in world.names if world.can_hold(g, family)],
                             [g for g in world.names if world.can_hold(g)])

    def test_tier_conflict(self):
        world = self.player()
        wallets = [g for g in world.names][:2]
        from oot_rando.game.remake_world import PROGRESSIVE
        for family in sorted(PROGRESSIVE):
            items = {wallets[0]: family, wallets[1]: family}
            shared = world.tier_conflict(items, {wallets[0]: 1, wallets[1]: 1})
            # Fixed tiers need distinct spheres; dynamic ones are chosen in game.
            self.assertEqual(shared, None if family in world.dynamic else family)
            self.assertIsNone(world.tier_conflict(items, {wallets[0]: 1, wallets[1]: 3}))

    def test_assigned_plan_with_foreign_items(self):
        """Placements of the built-in fill, a few given to another player, rebuilt as a plan."""
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer
        key = 'archipelago|test|2'
        world = bridge.PlayerWorld(self.catalog, {'open_forest': True}, key)   # defaults: the built-in fill is quick
        reference = full_randomizer.plan(World(), world.options, copy.deepcopy(self.groups),
                                         copy.deepcopy(self.enemies), key, True, extra=copy.deepcopy(self.extra))
        placed = {p['id']: p['item'] for p in reference['placements']}
        self.assertEqual(set(placed), set(world.names))
        foreign = [g for g, item in sorted(placed.items())
                   if world.classification(item) == 'filler' and world.can_hold(g)
                   and item not in world.local_only][:3]
        placements = {g: {'item': 'Sword' if g in foreign else item, 'own': g not in foreign,
                          'player': 'Ami' if g in foreign else 'Moi', 'sphere': None}
                      for g, item in placed.items()}
        remote = [{'item': placed[g], 'location': f'Somewhere {i}', 'player': 'Ami'} for i, g in enumerate(foreign)]
        patch = world.patch(placements, remote, '1', 'Moi', 1, self.build)
        bridge.check_patch(json.loads(json.dumps(patch)))
        result = full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                               copy.deepcopy(self.enemies), key, bridge.assigned_items(patch),
                                               True, extra=copy.deepcopy(self.extra),
                                               labels=bridge.foreign_labels(patch))
        by_id = {p['id']: p for p in result['placements']}
        from oot_rando.patching.ap_item import ap_actor
        for gid in foreign:
            self.assertEqual(by_id[gid]['item'], 'Archipelago: Sword (Ami)')
            self.assertEqual(by_id[gid]['after'], ap_actor('Archipelago: Sword (Ami)'))
        labels = {row['id']: row['item'] for row in result['spoiler']}
        self.assertEqual(labels[foreign[0]], 'Sword (Ami)')
        with self.assertRaises(full_randomizer.FillError):
            full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                          copy.deepcopy(self.enemies), key, dict(list(placed.items())[1:]),
                                          True, extra=copy.deepcopy(self.extra))

    def test_starting_error(self):
        world = self.player()
        self.assertIsNone(world.starting_error({'Hover Boots': 1}, {'Progressive Hookshot': 1}))
        self.assertIn('start_inventory_from_pool', world.starting_error({'Progressive Hookshot': 1}, {}))
        self.assertIn('dungeon', world.starting_error({}, {'Boss Key (Forest Temple)': 1}))
        self.assertIn('more starting copies', world.starting_error({}, {'Progressive Hookshot': 9}))

    def test_assigned_plan_with_starting_items(self):
        """A progressive copy moved to the starting items takes the lowest level."""
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer
        key = 'archipelago|test|3'
        world = bridge.PlayerWorld(self.catalog, {'open_forest': True}, key)
        reference = full_randomizer.plan(World(), world.options, copy.deepcopy(self.groups),
                                         copy.deepcopy(self.enemies), key, True, extra=copy.deepcopy(self.extra))
        placed = {p['id']: p['item'] for p in reference['placements']}
        hookshots = sorted(g for g, item in placed.items() if item == 'Progressive Hookshot')
        self.assertEqual(len(hookshots), 2)
        placed[hookshots[0]] = 'Rupees (5)'
        result = full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                               copy.deepcopy(self.enemies), key, placed, True,
                                               extra=copy.deepcopy(self.extra),
                                               starting=['Progressive Hookshot', 'Hover Boots'])
        self.assertEqual(result['starting'], [{'item': 'Progressive Hookshot', 'actor': 'Item_Hookshot'},
                                              {'item': 'Hover Boots', 'actor': 'Item_HoverBoot'}])
        after = {p['id']: p['after'] for p in result['placements']}
        self.assertIn('Longshot', after[hookshots[1]])
        with self.assertRaises(full_randomizer.FillError):   # one copy too many
            full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                          copy.deepcopy(self.enemies), key, placed, True,
                                          extra=copy.deepcopy(self.extra),
                                          starting=['Progressive Hookshot'] * 2)

    def test_reload_test_variants(self):
        """Both board variants: one more event, same size once compressed."""
        from oot_rando.archipelago import reload_test
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            dicts, members = dictionaries(nup), effective_members(nup)
            source = nup.read(members[reload_test.FLOW])
            vanilla = decompress(source, dicts)
            sizes = {len(reload_test._compress(reload_test.variant_flow(vanilla, v), source, dicts, reload_test.LEVEL))
                     for v in reload_test.VARIANTS}
        finally:
            nup.stream.close()
        self.assertEqual(len(sizes), 1)

    def test_apworld_runs_without_the_application(self):
        """The vendored part imports and prepares a world with nothing but the standard library."""
        from oot_rando.archipelago.apworld_build import write_apworld
        with tempfile.TemporaryDirectory() as folder:
            path = write_apworld(self.catalog, Path(folder) / 'oot_remake.apworld')
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read('oot_remake/archipelago.json'))
            self.assertIn('oot_remake/__init__.py', names)
            self.assertIn('oot_remake/vendor/oot_rando/logic/world/items.json', names)
            self.assertNotIn('oot_remake/vendor/oot_rando/formats/inspect_resources.py', names)
            self.assertEqual(manifest['game'], bridge.GAME)
            script = (
                'import json, sys, zipfile\n'
                f'path = {str(path)!r}\n'
                "sys.path.insert(0, path + '/oot_remake/vendor')\n"
                'from oot_rando.archipelago import bridge\n'
                "catalog = json.loads(zipfile.ZipFile(path).read('oot_remake/catalog.json'))\n"
                f"world = bridge.PlayerWorld(catalog, {self.values!r}, 'k')\n"
                "assert world.reach({})[0] is not None\n"
                "assert 'zstandard' not in sys.modules and 'evfl' not in sys.modules\n"
                "print(len(world.names))\n")
            done = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True, text=True,
                                  timeout=300, cwd=folder)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(int(done.stdout.strip()), len(self.player('k').names))


    def test_apworld_module_loads_in_archipelago_and_refuses_another_copy(self):
        """Its __init__ imported as Archipelago does, with stand-ins for Archipelago's modules."""
        from oot_rando.archipelago.apworld_build import write_apworld
        stubs = {
            'BaseClasses.py': (
                'class Item:\n    def __init__(self, *a): pass\n'
                'class Location:\n    def __init__(self, *a): pass\n'
                'class Region:\n    def __init__(self, *a): pass\n'
                'class ItemClassification:\n    progression = useful = filler = 0\n'
                'class LocationProgressType:\n    EXCLUDED = 0\n'),
            'Options.py': (
                'class Toggle: pass\nclass DefaultOnToggle(Toggle): pass\nclass Choice: pass\n'
                'class OptionError(Exception): pass\nclass StartInventoryPool: pass\n'
                'class PerGameCommonOptions: pass\nclass OptionSet: pass\n'),
            'worlds/__init__.py': '',
            'worlds/AutoWorld.py': 'class World: pass\n',
        }
        with tempfile.TemporaryDirectory() as folder:
            path = write_apworld(self.catalog, Path(folder) / 'oot_remake.apworld')
            for name, text in stubs.items():
                target = Path(folder) / 'ap' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            other = Path(folder) / 'other' / 'oot_rando'
            other.mkdir(parents=True)
            (other / '__init__.py').write_text('')
            vendor = str(path).replace('\\', '/') + '/oot_remake/vendor/'
            script = (
                'import sys\n'
                f"sys.path[:0] = [{str(Path(folder) / 'ap')!r}, {str(path)!r}] + sys.argv[1:]\n"
                'import oot_remake, oot_rando\n'
                f"assert oot_rando.__file__.replace(chr(92), '/').startswith({vendor!r}), oot_rando.__file__\n"
                'print(len(oot_remake.OoTRemakeWorld.location_name_to_id))\n')
            done = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True, text=True,
                                  timeout=300, cwd=folder)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertGreater(int(done.stdout.strip()), 0)
            # Another oot_rando earlier on the path: the world refuses to load.
            done = subprocess.run([sys.executable, '-I', '-c', script, str(Path(folder) / 'other')],
                                  capture_output=True, text=True, timeout=300, cwd=folder)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn('another copy of oot_rando', done.stderr)

class ReloadTestIntegrity(unittest.TestCase):
    def test_backup_stands_only_for_the_table_the_test_installed(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from oot_rando.archipelago.reload_test import RESTBL, STATE, seed_original
        with tempfile.TemporaryDirectory() as folder:
            seed = Path(folder)
            installed = b'table written by the test'
            (seed / (STATE + '.restbl')).write_bytes(b'seed table')
            (seed / STATE).write_text(json.dumps({'restbl_sha256': hashlib.sha256(installed).hexdigest()}))
            self.assertEqual(seed_original(seed, RESTBL, installed), b'seed table')
            self.assertEqual(seed_original(seed, RESTBL, b'anything else'), b'anything else')
            self.assertEqual(seed_original(seed, 'other/file', installed), installed)
            (seed / STATE).write_text(json.dumps({'variant': 'a'}))      # older state: no hash
            self.assertEqual(seed_original(seed, RESTBL, installed), installed)


if __name__ == '__main__':
    unittest.main()
