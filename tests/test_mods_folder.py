import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from oot_rando.randomizer.randomizer_core import Settings, CHECKS, settings_identity, GENERATOR_VERSION, ADAPTER_VERSION
from oot_rando.randomizer.artifact import installed_regeneration, read_artifact, regeneration_settings
from oot_rando.randomizer.mods_folder import continued_save, generate_in_mods, validate_mod_directory
from oot_rando.tracker.manual_tracker import ManualTracker
from oot_rando.patching.randomize_kokiri import TITLE, BUILD
from oot_rando import __version__ as APP_VERSION


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
                    'app_version': APP_VERSION, 'seed_id': identity, 'settings': settings.to_dict(),
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

    def test_previous_generator_seed_still_opens_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            for version in ('0.9.0', '0.10.0', '0.11.0', '0.11.1', '0.11.2', '0.11.3', '0.11.4', '0.10.1'):
                with self.subTest(version=version):
                    root = self.make_artifact(Path(directory) / version, 'same-settings')
                    path = root / 'manifest.json'
                    manifest = json.loads(path.read_text(encoding='utf-8'))
                    old_identity = settings_identity(Settings('same-settings'), version, ADAPTER_VERSION)
                    self.assertNotEqual(old_identity, manifest['seed_id'])
                    manifest.update(generator_version=version, seed_id=old_identity)
                    path.write_text(json.dumps(manifest), encoding='utf-8')
                    (root / 'checks.json').write_text(json.dumps({'seed_id': old_identity, 'checks': []}), encoding='utf-8')
                    self.assertEqual(read_artifact(root)[0]['seed_id'], old_identity)

    def test_stable_full_seed_identity_uses_its_historical_option_defaults(self):
        from oot_rando.logic import rando_options
        with tempfile.TemporaryDirectory() as directory:
            for version in ('0.9.0', '0.10.0'):
                with self.subTest(version=version):
                    root = self.make_artifact(Path(directory) / version, 'historical-full')
                    path = root / 'manifest.json'
                    manifest = json.loads(path.read_text(encoding='utf-8'))
                    historical = rando_options.defaults()
                    for name in ('key_rings_list', 'open_gerudo_valley_bridge', 'shuffle_trees',
                                 'shuffle_master_sword'):
                        historical.pop(name)
                    manifest['settings'].update(randomize_chests=False, full=historical)
                    identity = hashlib.sha256(json.dumps(
                        {'generator': version, 'adapter': ADAPTER_VERSION, 'settings': manifest['settings']},
                        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    manifest.update(generator_version=version, seed_id=identity)
                    path.write_text(json.dumps(manifest), encoding='utf-8')
                    (root / 'checks.json').write_text(json.dumps({'seed_id': identity, 'checks': []}), encoding='utf-8')
                    self.assertEqual(read_artifact(root)[0]['seed_id'], identity)

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

            def fake_generate(nup, output, settings, progress, **options):
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

    def test_regeneration_keeps_the_oldest_origin_of_the_saves(self):
        # A save update declined after a regeneration must not be taken as done: the
        # regenerated seed records the origin of the game, not the version it replaced.
        cases = [({'app_version': '0.7.1'}, '0.7.1'),
                 ({'app_version': '0.7.2', 'saves_from': '0.7.0'}, '0.7.0'),
                 ({}, '0.0.0'),                                  # made before 0.7.3
                 ({'app_version': 'not a version'}, '0.0.0'),
                 ({'app_version': APP_VERSION}, None),           # same version: nothing older
                 ({'app_version': '99.0.0'}, None)]
        for fields, expected in cases:
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                mods = self.make_hookshot(base / 'Hookshot')
                mods.mkdir()
                settings = Settings('kept')
                installed = self.make_artifact(mods / ('OoT_Randomizer_' + settings_identity(settings)[:16]), 'kept')
                manifest = json.loads((installed / 'manifest.json').read_text(encoding='utf-8'))
                manifest.pop('app_version')
                manifest.update(fields)
                (installed / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                received = []

                def fake_generate(nup, output, settings, progress, **options):
                    received.append(options)
                    self.make_artifact(output, settings.seed)
                generate_in_mods('game.nup', mods, settings, archive=base / 'archive', generate=fake_generate)
                self.assertEqual(received, [{'saves_from': expected} if expected else {}])

    def test_a_new_seed_records_no_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mods = self.make_hookshot(base / 'Hookshot')
            received = []

            def fake_generate(nup, output, settings, progress, **options):
                received.append(options)
                self.make_artifact(output, settings.seed)
            generate_in_mods('game.nup', mods, Settings('fresh'), archive=base / 'archive', generate=fake_generate)
            self.assertEqual(received, [{}])

    def make_old_artifact(self, root, settings, version='0.10.0'):
        """Seed folder as an older generator wrote it (identity bound to that version)."""
        self.make_artifact(root, settings.seed)
        identity = settings_identity(settings, version, ADAPTER_VERSION)
        path = root / 'manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest.update(generator_version=version, seed_id=identity, settings=settings.to_dict())
        manifest.pop('app_version')   # not recorded before 0.7.3
        path.write_text(json.dumps(manifest), encoding='utf-8')
        (root / 'checks.json').write_text(json.dumps({'seed_id': identity, 'checks': []}), encoding='utf-8')
        return root

    def test_regeneration_offered_only_for_an_accepted_seed_of_an_older_application(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            current = self.make_artifact(base / 'current', 'up-to-date')
            self.assertIsNone(installed_regeneration(current))
            old = self.make_old_artifact(base / 'old', Settings('old-seed'))
            self.assertEqual(installed_regeneration(old).seed, 'old-seed')
            # Seeds made before 0.7.3 record no application version: always older.
            manifest = read_artifact(old)[0]
            self.assertNotIn('app_version', manifest)
            self.assertIsNotNone(regeneration_settings(manifest, '0.7.3'))
            # The application version decides, even when the generator did not change.
            made = dict(read_artifact(current)[0], app_version='0.7.3')
            self.assertIsNone(regeneration_settings(made, '0.7.3'))
            self.assertIsNone(regeneration_settings(made, '0.7.2'))   # older application
            self.assertIsNone(regeneration_settings(made, '0.7.3-beta.1'))
            self.assertIsNotNone(regeneration_settings(made, '0.7.4'))
            self.assertIsNotNone(regeneration_settings(made, '0.9.0'))
            self.assertIsNone(regeneration_settings(dict(made, app_version='not a version'), '0.9.0'))
            # A version the generator no longer accepts: refused by read_artifact, no button.
            refused = self.make_old_artifact(base / 'refused', Settings('refused'), version='0.0.1')
            with self.assertRaises(ValueError):
                read_artifact(refused)
            self.assertIsNone(installed_regeneration(refused))
            # Tampered or missing seeds are not offered either.
            (old / 'romfs' / 'resource').write_bytes(b'modified')
            self.assertIsNone(installed_regeneration(old))
            self.assertIsNone(installed_regeneration(base / 'missing'))
            self.assertIsNone(regeneration_settings(None))
            self.assertIsNone(regeneration_settings({'generator_version': '0.10.0', 'settings': {'bad': 1}}))

    def test_regeneration_rebuilds_the_same_settings_from_the_manifest(self):
        from oot_rando.logic import rando_options
        full = rando_options.defaults()
        settings = Settings('My adventure', randomize_chests=False, open_forest=False,
                            skip_locked_cutscenes=True, full=full)
        with tempfile.TemporaryDirectory() as directory:
            old = self.make_old_artifact(Path(directory) / 'old', settings)
            rebuilt = installed_regeneration(old)
        self.assertEqual(rebuilt.to_dict(), settings.to_dict())
        self.assertEqual(rebuilt.seed, 'My adventure')
        self.assertEqual(rebuilt.full, settings.full)
        self.assertEqual(rebuilt.categories, settings.categories)
        # Only the identity follows the new generator; the name and settings stay.
        self.assertNotEqual(settings_identity(rebuilt), settings_identity(settings, '0.10.0', ADAPTER_VERSION))

    def test_regeneration_installs_in_the_same_mods_folder_and_archives_the_old_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mods = self.make_hookshot(base / 'Hookshot')
            mods.mkdir()
            settings = Settings('kept-name')
            old = self.make_old_artifact(
                mods / ('OoT_Randomizer_' + settings_identity(settings, '0.10.0', ADAPTER_VERSION)[:16]), settings)

            def fake_generate(nup, output, settings, progress, **options):
                self.make_artifact(output, settings.seed)
            archive = base / 'archive'
            new = generate_in_mods('game.nup', old.parent, installed_regeneration(old), archive=archive,
                                   generate=fake_generate)
            manifest = read_artifact(new)[0]
            self.assertEqual(manifest['settings'], settings.to_dict())
            self.assertEqual(manifest['generator_version'], GENERATOR_VERSION)
            self.assertIsNone(installed_regeneration(new))
            self.assertEqual([p.name for p in mods.iterdir()], [new.name])
            read_artifact(archive / old.name)

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
