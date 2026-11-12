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
        self.assertEqual(bridge.assigned_items(patch), {'A#1': 'Bow', 'A#2': bridge.FOREIGN_STANDIN})
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
        self.assertTrue(set(PROGRESSIVE) & set(world.pool) <= world.local_only)
        self.assertTrue(world.restricted <= world.local_only)

    def test_tier_conflict(self):
        world = self.player()
        wallets = [g for g in world.names][:2]
        items = {wallets[0]: 'Progressive Wallet', wallets[1]: 'Progressive Wallet'}
        self.assertEqual(world.tier_conflict(items, {wallets[0]: 1, wallets[1]: 1}), 'Progressive Wallet')
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
        foreign = [g for g, item in sorted(placed.items()) if world.classification(item) == 'filler'][:3]
        placements = {g: {'item': 'Sword' if g in foreign else item, 'own': g not in foreign,
                          'player': 'Ami' if g in foreign else 'Moi', 'sphere': None}
                      for g, item in placed.items()}
        remote = [{'item': placed[g], 'location': 'Somewhere', 'player': 'Ami'} for g in foreign]
        patch = world.patch(placements, remote, '1', 'Moi', 1, self.build)
        bridge.check_patch(json.loads(json.dumps(patch)))
        result = full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                               copy.deepcopy(self.enemies), key, bridge.assigned_items(patch),
                                               True, extra=copy.deepcopy(self.extra),
                                               labels=bridge.foreign_labels(patch))
        by_id = {p['id']: p for p in result['placements']}
        for gid in foreign:
            self.assertEqual(by_id[gid]['item'], bridge.FOREIGN_STANDIN)
        labels = {row['id']: row['item'] for row in result['spoiler']}
        self.assertEqual(labels[foreign[0]], 'Sword (Ami)')
        with self.assertRaises(full_randomizer.FillError):
            full_randomizer.plan_assigned(World(), world.options, copy.deepcopy(self.groups),
                                          copy.deepcopy(self.enemies), key, dict(list(placed.items())[1:]),
                                          True, extra=copy.deepcopy(self.extra))

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


if __name__ == '__main__':
    unittest.main()
