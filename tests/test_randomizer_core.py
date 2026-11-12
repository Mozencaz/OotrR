import _src_path  # noqa: F401  (src on sys.path)
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.randomizer.randomizer_core import Settings, settings_identity, placements_for, generate, CHESTS


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
