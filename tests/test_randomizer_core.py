import _src_path  # noqa: F401  (src on sys.path)
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.logic import rando_options
from oot_rando.randomizer.randomizer_core import Settings, settings_identity, placements_for, generate, CHESTS

# Identity of the settings below, made by the release before the ``spiritual_stones`` option (generator 0.12.0).
BEFORE_SPIRITUAL_STONES = 'e8e5d7d3189491d841fbf79c3618318f456ea443a7755c5544c238466fc1df02'


def full_settings(**options):
    full = dict(rando_options.preset('ap_defaults'), shuffle_rocks=True, open_kakariko='open', **options)
    return Settings.from_dict({'seed': 'golden-seed', 'randomize_chests': False, 'full': full})


class SettingsTests(unittest.TestCase):
    def test_strict_import(self):
        for data in ({}, {'seed': 5}, {'seed': 'a', 'open_forest': 1},
                     {'seed': 'a', 'pool': ['unknown']}, {'seed': 'a', 'extra': True},
                     {'seed': 'a', 'excluded_checks': [str(next(iter(CHESTS)))] * 2}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Settings.from_dict(data)

    def test_canonical_identity_and_reproducible_placements(self):
        a = Settings('text é 123')
        b = Settings.from_dict(json.loads(json.dumps(a.to_dict())))
        b.pool.reverse()
        self.assertEqual(settings_identity(a), settings_identity(b))
        self.assertEqual(placements_for(a), placements_for(b))
        self.assertNotEqual(settings_identity(a), settings_identity(Settings('text é 124')))
        self.assertNotEqual(settings_identity(a), settings_identity(Settings(a.seed, open_forest=False)))
        self.assertTrue(all(placements_for(a)[h] != old for h, old in CHESTS.items()))

    def test_require_all_keeps_the_identity_of_seeds_made_before_the_option(self):
        settings = full_settings()
        self.assertEqual(settings.full['spiritual_stones'], 'all')
        self.assertNotIn('spiritual_stones', settings.to_dict()['full'])
        self.assertEqual(settings_identity(settings, generator_version='0.12.0'), BEFORE_SPIRITUAL_STONES)
        stored = settings.to_dict()                 # what such a seed stored: no ``spiritual_stones``
        restored = Settings.from_dict(json.loads(json.dumps(stored)))
        self.assertEqual(restored.full['spiritual_stones'], 'all')
        self.assertEqual(settings_identity(restored, generator_version='0.12.0'), BEFORE_SPIRITUAL_STONES)

    def test_vanilla_stones_are_stored_and_make_another_seed(self):
        vanilla = full_settings(spiritual_stones='vanilla')
        self.assertEqual(vanilla.to_dict()['full']['spiritual_stones'], 'vanilla')
        self.assertNotEqual(settings_identity(vanilla, generator_version='0.12.0'), BEFORE_SPIRITUAL_STONES)
        restored = Settings.from_dict(json.loads(json.dumps(vanilla.to_dict())))
        self.assertEqual(restored.full['spiritual_stones'], 'vanilla')
        self.assertEqual(settings_identity(restored), settings_identity(vanilla))
        with self.assertRaises(ValueError):
            full_settings(spiritual_stones='emerald')

    def test_exclusions_and_disabled_randomization(self):
        ident = next(iter(CHESTS))
        self.assertEqual(placements_for(Settings('a', excluded_checks=[str(ident)]))[ident], CHESTS[ident])
        self.assertEqual(placements_for(Settings('a', randomize_chests=False, pool=[])), CHESTS)
        self.assertEqual(placements_for(Settings('a', pool=['TBox_Shield_Deku'])), dict.fromkeys(CHESTS, 'TBox_Shield_Deku'))
        with self.assertRaises(ValueError):
            Settings('a', pool=['TBox_Rupee_Blue']).validate()

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'marker').write_text('keep')
            with patch('oot_rando.randomizer.randomizer_core.Nup') as nup, self.assertRaises(ValueError):
                generate('unused', target, Settings('a'))
            nup.assert_not_called()
            self.assertEqual((target / 'marker').read_text(), 'keep')

    def test_environment_categories_are_independent_supported_and_roundtrip(self):
        for category in ('pots', 'bushes', 'rocks'):
            settings = Settings('environment', randomize_chests=False, open_forest=False,
                                categories={category: True})
            restored = Settings.from_dict(settings.to_dict()).validate_supported()
            self.assertEqual([k for k, v in restored.categories.items() if v], [category])

    def test_categories_are_saved_and_unsupported_adapters_fail_before_io(self):
        settings = Settings('all-sources', categories={'pots': True, 'quest_rewards': True})
        restored = Settings.from_dict(settings.to_dict())
        self.assertTrue(restored.categories['pots'])
        self.assertFalse(restored.categories['trees'])
        self.assertEqual(settings_identity(settings), settings_identity(restored))
        with patch('oot_rando.randomizer.randomizer_core.Nup') as nup, self.assertRaisesRegex(ValueError, 'Adapters'):
            generate('unused', Path('unused'), settings)
        nup.assert_not_called()
        with self.assertRaises(ValueError):
            Settings('bad', categories={'pots': 1}).validate()
        with self.assertRaises(ValueError):
            Settings('bad', categories={'unknown': False}).validate()


if __name__ == '__main__':
    unittest.main()


class GeneratorNamesTests(unittest.TestCase):
    def test_every_name_the_generator_reads_is_defined(self):
        """A name read in generate() is imported or assigned in it, or exists at module level.
        Branches no seed test reaches (Archipelago item reception) must not fail with NameError."""
        import ast
        import builtins
        import inspect
        from oot_rando.randomizer import randomizer_core
        function = ast.parse(inspect.getsource(randomizer_core.generate)).body[0]
        defined = set(dir(builtins)) | set(vars(randomizer_core))
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                defined.add(node.id)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                defined.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
            elif isinstance(node, (ast.FunctionDef, ast.Lambda, ast.comprehension, ast.ExceptHandler)):
                name = getattr(node, 'name', None)
                if isinstance(name, str):
                    defined.add(name)
        read = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
        self.assertEqual(sorted(read - defined), [])
