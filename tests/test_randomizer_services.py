import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from oot_rando.randomizer.randomizer_core import Settings, CHECKS, settings_identity, GENERATOR_VERSION, ADAPTER_VERSION
from oot_rando.randomizer.randomizer_services import (ManualTracker, continued_save, generate_in_mods,
                                                        read_artifact, validate_mod_directory)
from oot_rando.patching.randomize_kokiri import TITLE, BUILD


class ServiceTests(unittest.TestCase):
    def make_artifact(self, root, seed):
        root.mkdir()
        (root / 'romfs').mkdir()
        data = seed.encode()
        (root / 'romfs' / 'resource').write_bytes(data)
        settings = Settings(seed)
        identity = settings_identity(settings)
        manifest = {'schema_version': 1, 'title_id': TITLE, 'build_id': BUILD,
                    'generator_version': GENERATOR_VERSION, 'adapter_version': ADAPTER_VERSION,
                    'seed_id': identity, 'settings': settings.to_dict(),
                    'files': {'resource': {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (root / 'checks.json').write_text(json.dumps({'seed_id': identity, 'checks': []}), encoding='utf-8')
        return root

    def make_hookshot(self, root):
        root.mkdir()
        (root / 'hookshot.exe').touch()
        (root / 'image.bin').touch()
        (root / 'romfs').mkdir()
        return root / 'mods'

    def test_mod_target_accepts_hookshot_and_emulator_but_rejects_original_romfs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mods = self.make_hookshot(base / 'Hookshot')
            self.assertEqual(validate_mod_directory(mods), mods.resolve())
            self.assertEqual(validate_mod_directory(base / TITLE), (base / TITLE).resolve())
            longshot = base / 'Longshot'
            longshot.mkdir()
            (longshot / 'longshot.exe').touch()
            (longshot / 'image.bin').touch()
            (longshot / 'romfs').mkdir()
            self.assertEqual(validate_mod_directory(longshot / 'mods'), (longshot / 'mods').resolve())
            for invalid in (mods.parent, mods.parent / 'romfs', base / 'mods'):
                with self.subTest(path=invalid), self.assertRaises(ValueError):
                    validate_mod_directory(invalid)
            self.assertFalse(mods.exists())

    def test_generate_in_mods_writes_the_seed_there_and_archives_the_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mods = self.make_hookshot(base / 'Hookshot')
            original = mods.parent / 'romfs' / 'resource'
            original.write_bytes(b'original')
            calls = []

            def fake_generate(nup, output, settings, progress):
                calls.append(output)
                self.make_artifact(output, settings.seed)
            archive = base / 'archive'
            first = generate_in_mods('game.nup', mods, Settings('first'), archive=archive, generate=fake_generate)
            self.assertEqual(first.parent, mods.resolve())
            self.assertEqual(first.name, 'OoT_Randomizer_' + settings_identity(Settings('first'))[:16])
            read_artifact(first)
            second = generate_in_mods('game.nup', mods, Settings('second'), archive=archive, generate=fake_generate)
            self.assertFalse(first.exists())
            read_artifact(archive / first.name)
            # Same settings again (e.g. after an update): always generated anew, the
            # installed copy is archived, never reused nor deleted.
            again = generate_in_mods('game.nup', mods, Settings('second'), archive=archive, generate=fake_generate)
            self.assertEqual(again, second)
            self.assertEqual(len(calls), 3)
            read_artifact(archive / (second.name + '-replaced'))
            self.assertEqual(sorted(p.name for p in mods.iterdir()), [second.name])
            self.assertEqual(original.read_bytes(), b'original')

    def test_archipelago_reinstall_keeps_the_save_binding(self):
        class ApSettings:
            def __init__(self, patch):
                self.archipelago = patch

            def to_dict(self):
                return {'archipelago': self.archipelago}

        def install(title, seed, patch, save_seed_id=None):
            folder = self.make_artifact(title / ('OoT_Randomizer_' + settings_identity(Settings(seed))[:16]), seed)
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            manifest['settings']['archipelago'] = patch
            if save_seed_id:
                manifest['save_seed_id'] = save_seed_id
            (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            return manifest['seed_id']

        slot, other = {'seed_name': 'S1', 'slot_name': 'P3'}, {'seed_name': 'S2', 'slot_name': 'P3'}
        with tempfile.TemporaryDirectory() as directory:
            title = Path(directory) / TITLE
            title.mkdir()
            self.assertIsNone(continued_save(title, ApSettings(slot)))
            install(title, 'other slot', other)
            self.assertIsNone(continued_save(title, ApSettings(slot)))
            old = install(title, 'old version', slot)
            self.assertEqual(continued_save(title, ApSettings(slot)), old)
            self.assertIsNone(continued_save(title, Settings('not archipelago')))
        with tempfile.TemporaryDirectory() as directory:
            title = Path(directory) / TITLE
            title.mkdir()
            install(title, 'reinstalled once', slot, save_seed_id='first-seed')
            self.assertEqual(continued_save(title, ApSettings(slot)), 'first-seed')

    def test_generate_in_mods_conflict_archives_the_new_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mods = self.make_hookshot(base / 'Hookshot')
            conflict = mods / 'other' / 'romfs'
            conflict.mkdir(parents=True)
            (conflict / 'resource').write_bytes(b'other')
            fake = lambda nup, output, settings, progress: self.make_artifact(output, settings.seed)
            with self.assertRaisesRegex(ValueError, 'Resources shared with'):
                generate_in_mods('game.nup', mods, Settings('first'), archive=base / 'archive', generate=fake)
            self.assertEqual(sorted(p.name for p in mods.iterdir()), ['other'])
            self.assertEqual(len(list((base / 'archive').iterdir())), 1)
            self.assertEqual((conflict / 'resource').read_bytes(), b'other')

    def test_noop_options_are_rejected(self):
        with self.assertRaises(ValueError):
            Settings('a', randomize_chests=False, open_forest=False).validate()
        with self.assertRaises(ValueError):
            Settings('a', excluded_checks=[c['id'] for c in CHECKS], open_forest=False).validate()

    def test_manual_tracker_persists_and_isolates_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = ManualTracker(directory, 'seed1', 'slot', ['chest'])
            tracker.set_completed('chest', True)
            self.assertEqual(ManualTracker(directory, 'seed1', 'slot', ['chest']).completed, {'chest'})
            self.assertFalse(ManualTracker(directory, 'seed2', 'slot', ['chest']).completed)
            self.assertFalse(ManualTracker(directory, 'seed1', 'other', ['chest']).completed)
            with self.assertRaises(ValueError):
                tracker.set_completed('unknown', True)
            tracker.set_completed('chest', False)
            self.assertFalse(ManualTracker(directory, 'seed1', 'slot', ['chest']).completed)
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
