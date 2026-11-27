"""Real-directory tests of seed/save switching and crash recovery, without game assets."""
import _src_path  # noqa: F401
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oot_rando import parties
from oot_rando.parties import PartyLibrary, validate_save_root
from oot_rando.randomizer.randomizer_core import Settings, settings_identity, GENERATOR_VERSION, ADAPTER_VERSION
from oot_rando.patching.randomize_kokiri import TITLE, BUILD
from oot_rando.tracker.manual_tracker import ManualTracker
from oot_rando.randomizer.save_patch import GameRunning


def artifact(root, name):
    settings = Settings(name)
    identity = settings_identity(settings)
    folder = root / ('OoT_Randomizer_' + identity[:16])
    (folder / 'romfs').mkdir(parents=True)
    data = name.encode()
    (folder / 'romfs' / 'resource').write_bytes(data)
    manifest = {'schema_version': 1, 'title_id': TITLE, 'build_id': BUILD,
                'generator_version': GENERATOR_VERSION, 'adapter_version': ADAPTER_VERSION,
                'seed_id': identity, 'settings': settings.to_dict(),
                'files': {'resource': {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (folder / 'checks.json').write_text(json.dumps({'seed_id': identity, 'checks': []}), encoding='utf-8')
    return folder


class PartyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.processes = patch.object(parties, 'running_game', return_value=None)
        self.processes.start()
        self.addCleanup(self.processes.stop)
        self.library = PartyLibrary(self.base / 'Parties')
        self.mods = self.base / 'emulator' / 'load' / TITLE
        self.mods.mkdir(parents=True)
        self.saves = self.base / 'emulator' / 'nand' / 'profile' / TITLE
        self.saves.mkdir(parents=True)
        self.seed_a = artifact(self.base / 'seeds', 'A')
        self.seed_b = artifact(self.base / 'seeds', 'B')

    def create(self, name='A', seed=None, mods=None, saves=None, **kwargs):
        return self.library.create(name, seed or self.seed_a, mods or self.mods,
                                   saves or self.saves, **kwargs)

    def write_save(self, content, root=None):
        path = (root or self.saves) / 'slot_00' / 'progress.sav'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        (path.parent / 'screenshot.bin').write_bytes(b'picture-' + content)
        return path

    def test_round_trip_keeps_latest_save_and_ancillary_files(self):
        a = self.create('Aventure tranquille')
        b = self.create('Les amis', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A-progress')
        # A slot removed in game must not reappear when switching back.
        old = self.saves / 'slot_02'
        old.mkdir()
        (old / 'progress.sav').write_bytes(b'old')
        import shutil
        shutil.rmtree(old)
        self.library.activate(b['id'])
        self.assertFalse(any(self.saves.iterdir()), 'a fresh party must have no inherited save')
        self.assertFalse((self.mods / self.seed_a.name).exists())
        self.write_save(b'B-progress')
        self.library.activate(a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A-progress')
        self.assertEqual((self.saves / 'slot_00/screenshot.bin').read_bytes(), b'picture-A-progress')
        self.assertFalse((self.saves / 'slot_02').exists())
        self.library.activate(b['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'B-progress')
        self.assertEqual(self.library.active_id, b['id'])

    def test_cross_destination_empties_archived_destination_and_preserves_other_mods(self):
        other_mods = self.base / 'Longshot' / 'mods'
        other_mods.mkdir(parents=True)
        (other_mods.parent / 'longshot.exe').touch()
        (other_mods.parent / 'image.bin').touch()
        (other_mods.parent / 'romfs').mkdir()
        other_save = self.base / 'Longshot' / 'user' / 'save' / 'account'
        a = self.create()
        b = self.create('B', self.seed_b, other_mods, other_save)
        cosmetic = self.mods / 'Cosmetic' / 'romfs' / 'texture'
        cosmetic.parent.mkdir(parents=True)
        cosmetic.write_bytes(b'leave-me')
        self.library.activate(a['id'])
        self.write_save(b'A')
        self.library.activate(b['id'])
        self.assertFalse(self.saves.exists())
        self.assertEqual(cosmetic.read_bytes(), b'leave-me')
        self.library.activate(a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')

    def test_capture_installed_preserves_existing_files_and_tracker(self):
        import shutil
        installed = self.mods / self.seed_a.name
        shutil.copytree(self.seed_a, installed)
        self.write_save(b'existing')
        manual = ManualTracker(self.base / 'old-tracker', settings_identity(Settings('A')), 'My game', ['x'])
        manual.set_completed('x', True)
        party = self.create('Existante', installed, capture=True, tracker=manual.path)
        self.assertEqual(self.library.active_id, party['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'existing')
        self.assertTrue((self.library.bundle(party) / 'save/slot_00/screenshot.bin').exists())
        self.assertEqual(json.loads((self.library.folder(party['id']) / 'imported-tracker.json').read_text())['completed'], ['x'])

    def test_existing_unmanaged_seed_and_save_are_never_replaced(self):
        import shutil
        shutil.copytree(self.seed_a, self.mods / self.seed_a.name)
        save = self.write_save(b'precious')
        b = self.create('B', self.seed_b)
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            self.library.activate(b['id'])
        self.assertEqual(save.read_bytes(), b'precious')
        shutil.rmtree(self.mods / self.seed_a.name)
        with self.assertRaisesRegex(ValueError, 'already contains saves'):
            self.library.activate(b['id'])
        self.assertEqual(save.read_bytes(), b'precious')

    def test_running_game_blocks_capture_and_switch(self):
        party = self.create()
        with patch.object(parties, 'running_game', return_value='lichii.exe'):
            with self.assertRaises(GameRunning):
                self.library.activate(party['id'])
            with self.assertRaises(GameRunning):
                self.create('B')
        self.assertIsNone(self.library.active_id)

    def test_corrupt_seed_is_rejected_before_changing_active_installation(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        save = self.write_save(b'A')
        (self.library.bundle(b) / 'seed/romfs/resource').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Modified'):
            self.library.activate(b['id'])
        self.assertEqual(self.library.active_id, a['id'])
        self.assertEqual(save.read_bytes(), b'A')

    def test_rename_failure_rolls_back_seed_save_and_index(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        original = Path.rename
        failed = False
        def rename(path, target):
            nonlocal failed
            if path.name.startswith('.party-stage-') and Path(target) == self.saves and not failed:
                failed = True
                raise PermissionError('simulated locked save')
            return original(path, target)
        with patch.object(Path, 'rename', rename):
            with self.assertRaises(PermissionError):
                self.library.activate(b['id'])
        self.assertTrue(failed)
        self.assertEqual(self.library.active_id, a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')
        self.assertTrue((self.mods / self.seed_a.name).exists())
        self.assertFalse((self.mods / self.seed_b.name).exists())
        self.assertFalse(self.library.journal.exists())

    def test_crash_before_commit_recovers_on_next_start(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        write = parties._write
        def crash(path, value):
            if path == self.library.index_path:
                raise SystemExit('power loss')
            return write(path, value)
        with patch.object(parties, '_write', crash):
            with self.assertRaises(SystemExit):
                self.library.activate(b['id'])
        self.assertTrue(self.library.journal.exists())
        recovered = PartyLibrary(self.library.root)
        self.assertEqual(recovered.active_id, a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')
        self.assertFalse((self.mods / self.seed_b.name).exists())

    def test_crash_after_commit_keeps_new_party(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        with patch.object(self.library, 'recover', side_effect=SystemExit('power loss')):
            with self.assertRaises(SystemExit):
                self.library.activate(b['id'])
        recovered = PartyLibrary(self.library.root)
        self.assertEqual(recovered.active_id, b['id'])
        self.assertFalse(any(self.saves.iterdir()))
        recovered.activate(a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')

    def test_crash_during_staging_removes_partial_mod_on_restart(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        original = parties.copy_verified
        def crash(source, destination):
            if destination.name.startswith('.party-stage-'):
                destination.mkdir()
                (destination / 'partial').write_bytes(b'incomplete')
                raise SystemExit('power loss during copy')
            return original(source, destination)
        with patch.object(parties, 'copy_verified', crash):
            with self.assertRaises(SystemExit):
                self.library.activate(b['id'])
        recovered = PartyLibrary(self.library.root)
        self.assertEqual(recovered.active_id, a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')
        self.assertFalse(list(self.mods.glob('.party-*')))

    def test_copy_failure_preserves_current_installation(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        copy = parties.copy_verified
        def failing(source, destination):
            if destination.name.startswith('.party-stage-'):
                destination.mkdir()
                raise OSError('disk full')
            return copy(source, destination)
        with patch.object(parties, 'copy_verified', failing):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.library.activate(b['id'])
        self.assertEqual(self.library.active_id, a['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'A')
        self.assertFalse(list(self.mods.glob('.party-*')))

    def test_conflicting_mods_refuse_activation(self):
        p = self.create()
        conflict = self.mods / 'Other' / 'romfs' / 'resource'
        conflict.parent.mkdir(parents=True)
        conflict.write_bytes(b'precious')
        with self.assertRaisesRegex(ValueError, 'Conflicting mods'):
            self.library.activate(p['id'])
        self.assertEqual(conflict.read_bytes(), b'precious')

    def test_names_rename_delete_and_independent_tracker_profiles(self):
        a = self.create('  Ma partie  ')
        self.assertEqual(a['name'], 'Ma partie')
        for name in ('', 'ma PARTIE', 'bad\nname', 'x' * 101):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.create(name)
        b = self.create('Autre partie')
        identity = settings_identity(Settings('A'))
        first = ManualTracker(self.library.tracker_dir(a['id']), identity, 'party-' + a['id'], ['x'])
        second = ManualTracker(self.library.tracker_dir(b['id']), identity, 'party-' + b['id'], ['x'])
        first.set_completed('x', True)
        self.assertFalse(second.completed)
        self.library.rename(a['id'], 'Renommée')
        self.assertTrue(first.path.exists())
        self.library.activate(a['id'])
        with self.assertRaises(ValueError):
            self.library.delete(a['id'])
        self.library.delete(b['id'])
        self.assertEqual(len(self.library.list()), 1)
        self.assertTrue(list((self.library.root / '.deleted').iterdir()))

    def test_damaged_party_file_does_not_block_the_others(self):
        a = self.create('A')
        b = self.create('B', self.seed_b)
        (self.library.folder(b['id']) / 'party.json').write_text('{truncated', encoding='utf-8')
        self.assertEqual([p['id'] for p in self.library.list()], [a['id']])
        self.assertEqual([folder for folder, _ in self.library.unreadable], [b['id']])
        self.library.rename(a['id'], 'Still works')
        self.library.activate(a['id'])
        self.assertEqual(self.library.active_id, a['id'])

    def test_library_index_is_written_durably(self):
        synced = []
        real = parties.os.fsync
        with patch.object(parties.os, 'fsync', side_effect=lambda fd: (synced.append(fd), real(fd))):
            self.create('A', capture=False)
            a = self.library.list()[0]
            self.library.activate(a['id'])
        self.assertTrue(synced)
        self.assertEqual(json.loads(self.library.index_path.read_text(encoding='utf-8'))['active'], a['id'])
        self.assertFalse(self.library.index_path.with_suffix('.tmp').exists())

    def test_unsafe_and_overlapping_roots_are_refused(self):
        for bad in (self.base, self.base / 'mods', self.base / 'save', self.base / 'nand'):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                validate_save_root(bad)
        with self.assertRaisesRegex(ValueError, 'separate'):
            self.create(saves=self.mods / 'account')
        with self.assertRaises(ValueError):
            self.library.get('../escape')

    def test_missing_or_changed_outgoing_seed_blocks_switch(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        (self.mods / self.seed_a.name / 'romfs/resource').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.library.activate(b['id'])
        self.assertEqual(self.library.active_id, a['id'])

    def test_regeneration_can_continue_only_same_settings(self):
        a = self.create()
        self.library.activate(a['id'])
        self.write_save(b'keep-progress')
        updated = self.create('A mise à jour', continue_active=True)
        self.library.activate(updated['id'])
        self.assertEqual((self.saves / 'slot_00/progress.sav').read_bytes(), b'keep-progress')
        with self.assertRaisesRegex(ValueError, 'same settings'):
            self.create('Different', self.seed_b, continue_active=True)

    def test_snapshot_count_is_bounded(self):
        a = self.create()
        self.library.activate(a['id'])
        for index in range(4):
            self.write_save(str(index).encode())
            self.library.refresh()
        self.assertEqual(len(list((self.library.folder(a['id']) / 'snapshots').iterdir())), 2)

    def test_stored_save_corruption_is_rejected(self):
        a = self.create()
        b = self.create('B', self.seed_b)
        self.library.activate(a['id'])
        self.write_save(b'A')
        self.library.activate(b['id'])
        stored = self.library.bundle(self.library.get(a['id'])) / 'save/slot_00/progress.sav'
        stored.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'incomplete or modified'):
            self.library.activate(a['id'])
        self.assertEqual(self.library.active_id, b['id'])

    def test_second_instance_cannot_recover_an_in_progress_transaction(self):
        p = self.create()
        original = parties.copy_verified
        attempted = False
        def copying(source, destination):
            nonlocal attempted
            if destination.name.startswith('.party-stage-') and not attempted:
                attempted = True
                with self.assertRaisesRegex(ValueError, 'Another randomizer'):
                    PartyLibrary(self.library.root)
            return original(source, destination)
        with patch.object(parties, 'copy_verified', copying):
            self.library.activate(p['id'])
        self.assertTrue(attempted)
        self.assertEqual(self.library.active_id, p['id'])

    def test_capture_rejects_a_save_from_a_different_modern_seed(self):
        import shutil
        from test_save_reader import fixture
        installed = self.mods / self.seed_a.name
        shutil.copytree(self.seed_a, installed)
        manifest_path = installed / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        raw = json.dumps({'schema_version': 1, 'seed_id': manifest['seed_id'], 'seed_marker': 100}).encode()
        (installed / 'tracking.json').write_bytes(raw)
        manifest['tracking'] = {'sha256': hashlib.sha256(raw).hexdigest()}
        manifest_path.write_text(json.dumps(manifest))
        save = self.write_save(fixture(boolean=0))
        with self.assertRaisesRegex(ValueError, 'another seed'):
            self.create('Wrong', installed, capture=True)
        self.assertIsNone(self.library.active_id)
        save.write_bytes(fixture(boolean=1))
        adopted = self.create('Right', installed, capture=True)
        self.assertEqual(self.library.active_id, adopted['id'])


if __name__ == '__main__':
    unittest.main()
