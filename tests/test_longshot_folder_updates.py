"""Longshot launcher folders: channel discovery, vanished version folders, and My Games migration."""
import _src_path  # noqa: F401
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oot_rando import pc_port
from oot_rando.parties import PartyLibrary
from oot_rando.patching.randomize_kokiri import BUILD, TITLE
from oot_rando.randomizer.randomizer_core import ADAPTER_VERSION, GENERATOR_VERSION, Settings, settings_identity


def make_port(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'image.bin').write_bytes(b'img')
    (root / 'romfs').mkdir(parents=True, exist_ok=True)
    (root / 'mods').mkdir(parents=True, exist_ok=True)
    return root


def make_seed(seed_dir, label='testseed'):
    settings = Settings(seed=label)
    seed_id = settings_identity(settings)
    (seed_dir / 'romfs').mkdir(parents=True, exist_ok=True)
    data = label.encode('utf-8')
    (seed_dir / 'romfs' / 'resource').write_bytes(data)
    manifest = {
        'schema_version': 1, 'title_id': TITLE, 'build_id': BUILD, 'seed_id': seed_id,
        'generator_version': GENERATOR_VERSION, 'adapter_version': ADAPTER_VERSION,
        'settings': settings.to_dict(),
        'files': {'resource': {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}},
    }
    (seed_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (seed_dir / 'checks.json').write_text(json.dumps({'seed_id': seed_id, 'checks': []}), encoding='utf-8')
    return seed_dir


class ResolveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'Longshot'

    def test_vanished_folder_follows_the_newest_build_of_its_channel(self):
        v320 = make_port(self.root / 'stable' / 'v3.2.0')
        info = pc_port.resolve_longshot_update(self.root / 'stable' / 'v3.1.1' / 'mods')
        self.assertEqual(info['status'], 'upgraded')
        self.assertEqual(info['current_channel'], 'stable')
        self.assertEqual(info['recommended']['mods_dir'], v320 / 'mods')
        self.assertEqual(pc_port.resolve_longshot_update(v320 / 'mods')['status'], 'unchanged')

    def test_an_existing_older_build_is_kept(self):
        v311 = make_port(self.root / 'stable' / 'v3.1.1')
        make_port(self.root / 'stable' / 'v3.2.0')
        self.assertEqual(pc_port.resolve_longshot_update(v311 / 'mods')['status'], 'unchanged')

    def test_several_channels_ask_only_when_the_folder_vanished(self):
        stable = make_port(self.root / 'stable' / 'v3.2.0')
        make_port(self.root / 'release candidate' / 'v3.2.1-rc.2')
        make_port(self.root / 'release candidate' / 'v3.2.1-rc.1')
        make_port(self.root / 'nightly' / '2026-11-24')
        self.assertEqual(pc_port.resolve_longshot_update(stable / 'mods')['status'], 'unchanged')
        info = pc_port.resolve_longshot_update(self.root / 'stable' / 'v3.1.1' / 'mods')
        self.assertEqual(info['status'], 'choose_channel')
        self.assertEqual(info['recommended']['channel'], 'stable')
        self.assertEqual([(c['channel'], c['version_name']) for c in info['channels']],
                         [('stable', 'v3.2.0'), ('release candidate', 'v3.2.1-rc.2'), ('nightly', '2026-11-24')])

    def test_a_picked_root_or_channel_folder_resolves_to_a_build(self):
        v320 = make_port(self.root / 'stable' / 'v3.2.0')
        for picked in (self.root, self.root / 'stable'):
            info = pc_port.resolve_longshot_update(picked)
            self.assertEqual(info['status'], 'upgraded', picked)
            self.assertEqual(info['recommended']['mods_dir'], v320 / 'mods')

    def test_release_beats_its_candidates(self):
        names = ['v3.2.0-rc.1', 'v3.10.0', 'v3.2.0', 'v3.2.0-beta.3', 'v3.9.9']
        ranked = sorted((make_port(self.root / 'stable' / name) for name in names), key=pc_port.version_sort_key)
        self.assertEqual([p.name for p in ranked], ['v3.2.0-beta.3', 'v3.2.0-rc.1', 'v3.2.0', 'v3.9.9', 'v3.10.0'])

    def test_outside_longshot(self):
        port = make_port(self.root.parent / 'Hookshot')
        self.assertEqual(pc_port.resolve_longshot_update(port / 'mods')['status'], 'not_longshot')
        self.assertEqual(pc_port.resolve_longshot_update('')['status'], 'not_longshot')

    def test_normalize_port_mods_dir_resolves_port_root(self):
        v320 = make_port(self.root / 'stable' / 'v3.2.0')
        self.assertEqual(pc_port.normalize_port_mods_dir(str(v320) + os.sep), str(v320 / 'mods'))
        self.assertEqual(pc_port.normalize_port_mods_dir(str(v320 / 'mods') + os.sep), str(v320 / 'mods'))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        patcher = mock.patch('oot_rando.parties.running_game', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.base / 'Longshot'
        self.v311 = make_port(self.root / 'stable' / 'v3.1.1')
        self.v320 = make_port(self.root / 'stable' / 'v3.2.0')
        self.saves = self.base / 'saves' / 'account01'
        self.saves.mkdir(parents=True)
        self.library = PartyLibrary(self.base / 'Parties')
        self.old = self.library.create('OldParty', make_seed(self.base / 'seed1', 'old'), self.v311 / 'mods', self.saves)
        self.library.activate(self.old['id'])
        (self.saves / 'slot_00').mkdir()
        (self.saves / 'slot_00' / 'progress.sav').write_bytes(b'sav')

    def test_switching_away_from_a_deleted_port(self):
        shutil.rmtree(self.v311)
        new = self.library.create('NewParty', make_seed(self.base / 'seed2', 'new'), self.v320 / 'mods', self.saves)
        self.library.activate(new['id'])
        self.assertEqual(self.library.active_id, new['id'])
        moved = self.library.migrate_mods_directory(self.v320 / 'mods', old_mods=self.v311 / 'mods', root=self.root)
        self.assertEqual(moved, ['OldParty'])
        self.assertEqual(Path(self.library.get(self.old['id'])['mods']), (self.v320 / 'mods').resolve())

    def test_the_active_game_is_installed_again_in_the_new_build(self):
        shutil.rmtree(self.v311)
        moved = self.library.migrate_mods_directory(self.v320 / 'mods', old_mods=self.v311 / 'mods')
        self.assertEqual(moved, ['OldParty'])
        party = self.library.get(self.old['id'])
        self.assertTrue((self.v320 / 'mods' / party['mod_name'] / 'manifest.json').is_file())
        self.assertTrue(self.library.refresh())   # the active installation is complete again

    def test_a_folder_which_still_exists_is_never_moved(self):
        moved = self.library.migrate_mods_directory(self.v320 / 'mods', old_mods=self.v311 / 'mods', root=self.root)
        self.assertEqual(moved, [])
        self.assertEqual(Path(self.library.get(self.old['id'])['mods']), (self.v311 / 'mods').resolve())
        self.assertFalse(any((self.v320 / 'mods').iterdir()))


if __name__ == '__main__':
    unittest.main()
