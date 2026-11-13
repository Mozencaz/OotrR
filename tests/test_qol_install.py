"""Quality-of-life install (intro skip, fast chests) without randomization. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from oot_rando.patching.qol_patches import INTRO
from oot_rando.patching.randomize_kokiri import BUILD, TITLE
from oot_rando.randomizer import qol_install
from oot_rando.randomizer.randomizer_services import (QOL_FOLDER, archive_previous_seeds, conflicting_mods,
                                                      generate_in_mods, is_qol_install, is_randomizer_seed,
                                                      qol_seed_warning, read_artifact)

NUP = os.environ.get('OOT_NUP')
SEED_ID = 'a' * 64


def write_manifest(folder, **fields):
    (folder / 'romfs').mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({'title_id': TITLE, **fields}), encoding='utf-8')
    return folder


class FolderRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.mods = Path(self.temporary.name) / TITLE
        self.mods.mkdir()

    def qol(self):
        return write_manifest(self.mods / QOL_FOLDER, kind='qol', files={})

    def seed(self):
        return write_manifest(self.mods / ('OoT_Randomizer_' + SEED_ID[:16]), seed_id=SEED_ID)

    def test_qol_folder_is_recognised_and_is_not_a_seed(self):
        folder = self.qol()
        self.assertTrue(is_qol_install(folder))
        self.assertFalse(is_randomizer_seed(folder))

    def test_only_the_named_folder_with_the_qol_kind_counts(self):
        self.assertFalse(is_qol_install(self.mods / QOL_FOLDER))
        write_manifest(self.mods / QOL_FOLDER, files={})
        self.assertFalse(is_qol_install(self.mods / QOL_FOLDER))
        other = write_manifest(self.mods / 'Other', kind='qol')
        self.assertFalse(is_qol_install(other))

    def test_the_qol_folder_is_not_opened_as_a_seed(self):
        with self.assertRaisesRegex(ValueError, 'quality-of-life'):
            read_artifact(self.qol())

    def test_seed_archiving_leaves_the_qol_folder(self):
        qol, seed = self.qol(), self.seed()
        moved = archive_previous_seeds(self.mods, Path(self.temporary.name) / 'archive')
        self.assertEqual([p.name for p in moved], [seed.name])
        self.assertTrue(qol.exists())

    def test_seed_install_does_not_see_the_qol_folder_as_a_conflict(self):
        qol = self.qol()
        (qol / 'romfs' / 'shared.bin').write_bytes(b'x')
        foreign = write_manifest(self.mods / 'Foreign', files={})
        (foreign / 'romfs' / 'shared.bin').write_bytes(b'y')
        self.assertEqual(conflicting_mods(self.mods, {'files': {'shared.bin': {}}}, 'new'), ['Foreign'])


class SeedInstallWarningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.mods = Path(self.temporary.name) / TITLE
        self.mods.mkdir()

    def test_no_warning_without_the_qol_folder(self):
        self.assertIsNone(qol_seed_warning(self.mods))

    def test_warning_names_the_folder_and_what_to_do(self):
        write_manifest(self.mods / QOL_FOLDER, kind='qol', files={})
        warning = qol_seed_warning(self.mods)
        self.assertIn(QOL_FOLDER + ' is installed in this mods folder', warning)
        self.assertIn('Turn it off', warning)

    def test_a_seed_install_goes_ahead_and_warns(self):
        from unittest import mock
        from oot_rando.randomizer.randomizer_core import Settings

        def fake_generate(nup, destination, settings, report, **options):
            (destination / 'romfs').mkdir(parents=True)
        qol = write_manifest(self.mods / QOL_FOLDER, kind='qol', files={})
        (qol / 'romfs' / 'shared.bin').write_bytes(b'x')
        messages = []
        manifest = {'files': {'shared.bin': {}}}
        with mock.patch('oot_rando.randomizer.randomizer_services.read_artifact', return_value=(manifest, {})):
            folder = generate_in_mods('game.nup', self.mods, Settings('warn'), messages.append,
                                      generate=fake_generate)
        self.assertTrue(folder.is_dir() and qol.is_dir())
        self.assertIn('Warning: ' + qol_seed_warning(self.mods), messages)


class InstallWarningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.mods = Path(self.temporary.name) / TITLE
        self.mods.mkdir()
        self.manifest = {'files': {'Event/EventFlow/Dm_SY_Treasurebox.bfevfl.zs': {}}}

    def test_no_warning_in_a_clean_folder(self):
        self.assertEqual(qol_install.install_warnings(self.mods, self.manifest), [])
        self.assertEqual(qol_install.install_warnings(self.mods / 'missing', self.manifest), [])

    def test_a_seed_in_the_folder_is_warned_about_not_refused(self):
        write_manifest(self.mods / ('OoT_Randomizer_' + SEED_ID[:16]), seed_id=SEED_ID)
        warnings = qol_install.install_warnings(self.mods, self.manifest)
        self.assertEqual(len(warnings), 1)
        self.assertIn('OoT_Randomizer_' + SEED_ID[:16], warnings[0])
        self.assertIn('turns ' + QOL_FOLDER + ' off', warnings[0])

    def test_a_mod_changing_the_same_resource_is_warned_about(self):
        other = write_manifest(self.mods / 'Other', files={})
        target = other / 'romfs' / 'Event' / 'EventFlow'
        target.mkdir(parents=True)
        (target / 'Dm_SY_Treasurebox.bfevfl.zs').write_bytes(b'x')
        warnings = qol_install.install_warnings(self.mods, self.manifest)
        self.assertEqual(len(warnings), 1)
        self.assertIn('Other', warnings[0])


class CommandTests(unittest.TestCase):
    def test_one_option_at_least(self):
        with self.assertRaises(ValueError):
            qol_install.generate_qol_files('missing.nup', intro_skip=False, fast_chests=False)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            qol_install.main(['game.nup', 'mods', '--no-intro-skip', '--no-fast-chests'])

    def test_a_foreign_folder_of_that_name_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory) / TITLE
            foreign = mods / QOL_FOLDER
            foreign.mkdir(parents=True)
            (foreign / 'keep.txt').write_text('mine')
            with self.assertRaisesRegex(ValueError, 'not a quality-of-life install'):
                qol_install.install_qol('missing.nup', mods)
            self.assertEqual((foreign / 'keep.txt').read_text(), 'mine')


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class NupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.decompress = staticmethod(decompress)
        cls.nup = Nup(NUP)
        cls.members = effective_members(cls.nup)
        cls.dictionaries = dictionaries(cls.nup)
        cls.files, cls.manifest = qol_install.generate_qol_files(NUP)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def original(self, path):
        return self.nup.read(self.members[path])

    def test_manifest_is_a_qol_manifest_without_seed(self):
        self.assertEqual((self.manifest['kind'], self.manifest['title_id'], self.manifest['build_id']),
                         ('qol', TITLE, BUILD))
        self.assertNotIn('seed_id', self.manifest)
        self.assertEqual(self.manifest['options'], {'intro_skip': True, 'fast_chests': True})
        self.assertIn('Mozencaz', self.manifest['credit'])

    def test_both_patches_write_exactly_their_files(self):
        from oot_rando.patching import qol_patches as q
        from oot_rando.patching.event_info import GAME_ANALYZED_EVENT_INFO
        self.assertEqual(set(self.files) - {GAME_ANALYZED_EVENT_INFO},
                         {q.INTRO, q.CHEST_FLOW, q.SMALL_CHEST_FLOW,
                          'System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs'})
        self.assertEqual(set(self.manifest['files']), set(self.files))
        for path, info in self.manifest['files'].items():
            self.assertEqual((info['size'], q.sha256(self.files[path])), (len(self.files[path]), info['sha256']))

    def test_intro_is_the_randomizers_patch(self):
        from oot_rando.patching import qol_patches as q
        randomizer_files, _ = q.cutscene_files(self.original)
        self.assertEqual(self.files[q.INTRO], randomizer_files[q.INTRO])
        self.assertEqual(len(self.files[q.INTRO]), len(self.original(q.INTRO)))

    def test_chest_flows_are_the_randomizers_patches(self):
        from oot_rando.patching import qol_patches as q
        for path, patch in ((q.CHEST_FLOW, q.quick_chest), (q.SMALL_CHEST_FLOW, q.quick_small_chest)):
            expected, _ = patch(self.decompress(self.original(path), self.dictionaries))
            self.assertEqual(self.decompress(self.files[path], self.dictionaries), expected)

    def test_grown_flows_get_room_in_the_resource_table(self):
        grown = {a['path'] for a in self.manifest['resource_allocations']}
        self.assertEqual(grown, {'Event/EventFlow/Dm_SY_Treasurebox.bfevfl', 'Event/EventFlow/Dm_SY_TreasureboxSmall.bfevfl'})
        for allocation in self.manifest['resource_allocations']:
            self.assertGreater(allocation['after'], allocation['before'])

    def test_each_option_alone_writes_only_its_files(self):
        from oot_rando.patching import qol_patches as q
        intro_only, manifest = qol_install.generate_qol_files(NUP, fast_chests=False)
        self.assertEqual(set(intro_only), {q.INTRO})
        self.assertEqual(manifest['resource_allocations'], [])
        chests_only, manifest = qol_install.generate_qol_files(NUP, intro_skip=False)
        self.assertNotIn(q.INTRO, chests_only)
        self.assertIn(q.CHEST_FLOW, chests_only)
        self.assertEqual(manifest['options'], {'intro_skip': False, 'fast_chests': True})

    def test_chest_flows_match_a_randomizer_seed_with_fast_chests(self):
        from oot_rando.patching import qol_patches as q
        from oot_rando.randomizer.randomizer_core import Settings, generate
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / 'seed'
            settings = Settings('qol-parity', randomize_chests=False, open_forest=False, skip_chest_cutscenes=True)
            generated = generate(NUP, seed, settings)
        for path in (q.CHEST_FLOW, q.SMALL_CHEST_FLOW):
            self.assertEqual(generated['files'][path]['sha256'], self.manifest['files'][path]['sha256'])

    def test_install_writes_the_folder_and_a_reinstall_replaces_it(self):
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory) / TITLE
            seed = write_manifest(mods / ('OoT_Randomizer_' + SEED_ID[:16]), seed_id=SEED_ID)
            messages = []
            first = qol_install.install_qol(NUP, mods, progress=messages.append)
            self.assertEqual(first.folder, mods / QOL_FOLDER)
            self.assertEqual(len(first.warnings), 1)
            self.assertTrue(any(m.startswith('Warning: ') for m in messages))
            written = {p.relative_to(first.folder / 'romfs').as_posix() for p in (first.folder / 'romfs').rglob('*')
                       if p.is_file()}
            installed = json.loads((first.folder / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(written, set(installed['files']))
            self.assertTrue(is_qol_install(first.folder))
            self.assertTrue(seed.exists())
            (first.folder / 'stale.txt').write_text('left over')
            (first.folder / 'romfs' / 'stale.bin').write_bytes(b'x')
            second = qol_install.install_qol(NUP, mods, intro_skip=False)
            self.assertFalse((second.folder / 'stale.txt').exists() or (second.folder / 'romfs' / 'stale.bin').exists())
            reinstalled = json.loads((second.folder / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(reinstalled['options'], {'intro_skip': False, 'fast_chests': True})
            self.assertFalse((second.folder / 'romfs' / INTRO).exists())
            self.assertEqual([p.name for p in mods.iterdir() if p.name.startswith('.')], [])


if __name__ == '__main__':
    unittest.main()
