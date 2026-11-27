"""Save migration: start values applied in place to a synthetic progress.sav."""
import _src_path  # noqa: F401  (src on sys.path)
from datetime import datetime
import struct
import tempfile
import unittest
from pathlib import Path

from oot_rando.patching.soul_adapter import murmur3
from oot_rando.randomizer import save_patch
from oot_rando.randomizer.save_patch import (GameRunning, SavePatchRefused, migration_candidates,
                                          migration_markers, patch_save, plan_patch, running_game)
from oot_rando.formats.save_file import decode_progress, MAGIC, FORMAT_VERSION, PROGRESS_TYPE_HASH

MANIFEST = {'seed_id': 'a' * 64, 'settings': {'seed': 'demo'},
            'start_values': {'HavePlayedEvent.Dm_HrlField_0000': True, 'NaviHint_Disp_FieldHint_01': False,
                             'HyruleField_ArriveEntrance': True, 'Not_In_This_Save': True,
                             'DungeonInfo.Dungeon001.SmallKeyNum': 3}}
MARKER = 'RandoSeed.' + 'a' * 64


def progress(bools, integers=()):
    """Minimal valid progress.sav: table 0 booleans (name -> 0/1), table 2 integers."""
    records = {0: [(murmur3(name), value) for name, value in bools.items()],
               2: [(murmur3(name), value) for name, value in integers],
               32: [(PROGRESS_TYPE_HASH, None)]}
    table_end = 32 + 8 * (33 + sum(map(len, records.values())))
    records[32] = [(PROGRESS_TYPE_HASH, table_end)]
    header = struct.pack('<III', MAGIC, FORMAT_VERSION, table_end) + bytes(20)
    table = b''
    for typ in range(33):
        table += struct.pack('<II', 0, typ)
        table += b''.join(struct.pack('<II', key, value) for key, value in records.get(typ, ()))
    return header + table + struct.pack('<Q', 7) + bytes(8)


def our_save(**overrides):
    bools = {MARKER: 1, 'HavePlayedEvent.Dm_HrlField_0000': 0, 'NaviHint_Disp_FieldHint_01': 1,
             'HyruleField_ArriveEntrance': 1, 'Unrelated_Flag': 0}
    bools.update(overrides)
    return progress(bools, integers=[('DungeonInfo.Dungeon001.SmallKeyNum', 0)])


class PlanTests(unittest.TestCase):
    def test_only_targeted_keys_change(self):
        data = our_save()
        patched, changes, missing = plan_patch(data, MANIFEST['start_values'], [MARKER])
        self.assertEqual(len(patched), len(data))
        self.assertEqual(changes, [('HavePlayedEvent.Dm_HrlField_0000', False, True),
                                   ('NaviHint_Disp_FieldHint_01', True, False)])
        before, after = decode_progress(data), decode_progress(patched)
        expected = {**before['bool'], murmur3('HavePlayedEvent.Dm_HrlField_0000'): True,
                    murmur3('NaviHint_Disp_FieldHint_01'): False}
        self.assertEqual(after['bool'], expected)
        self.assertEqual(after['int'], before['int'])   # integer start values are left alone
        differing = [i for i, (a, b) in enumerate(zip(data, patched)) if a != b]
        self.assertEqual(len(differing), 2)              # one byte per changed flag

    def test_absent_key_is_never_added(self):
        data = our_save()
        patched, _, missing = plan_patch(data, MANIFEST['start_values'], [MARKER])
        self.assertEqual(missing, ['Not_In_This_Save'])
        self.assertNotIn(murmur3('Not_In_This_Save'), decode_progress(patched)['bool'])
        self.assertEqual(set(decode_progress(patched)['bool']), set(decode_progress(data)['bool']))

    def test_save_of_another_seed_is_refused(self):
        data = progress({'RandoSeed.' + 'b' * 64: 1, 'HavePlayedEvent.Dm_HrlField_0000': 0})
        with self.assertRaises(SavePatchRefused):
            plan_patch(data, MANIFEST['start_values'], [MARKER])
        with self.assertRaises(SavePatchRefused):   # marker present but false
            plan_patch(our_save(**{MARKER: 0}), MANIFEST['start_values'], [MARKER])

    def test_up_to_date_save_needs_nothing(self):
        data = our_save(**{'HavePlayedEvent.Dm_HrlField_0000': 1, 'NaviHint_Disp_FieldHint_01': 0})
        patched, changes, _ = plan_patch(data, MANIFEST['start_values'], [MARKER])
        self.assertEqual((patched, changes), (data, []))


class PatchFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'slot_01' / 'progress.sav'
        self.path.parent.mkdir()
        self.path.write_bytes(our_save())

    def tearDown(self):
        self.folder.cleanup()

    def test_backup_then_in_place_rewrite(self):
        original = self.path.read_bytes()
        report = patch_save(self.path, MANIFEST['start_values'], [MARKER], processes=[],
                            now=datetime(2026, 11, 19, 20, 30, 0))
        backup = Path(report['backup'])
        self.assertEqual(backup.name, 'progress.sav.backup-20261119-203000')
        self.assertEqual(backup.read_bytes(), original)
        written = self.path.read_bytes()
        self.assertEqual(len(written), len(original))
        self.assertTrue(decode_progress(written)['bool'][murmur3('HavePlayedEvent.Dm_HrlField_0000')])
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                         ['progress.sav', 'progress.sav.backup-20261119-203000'])
        # A second pass has nothing to do and writes no new backup.
        again = patch_save(self.path, MANIFEST['start_values'], [MARKER], processes=[])
        self.assertEqual((again['changes'], again['backup']), ([], None))

    def test_running_game_or_emulator_blocks_the_write(self):
        original = self.path.read_bytes()
        for image in (r'C:\Games\Longshot\longshot.exe', 'hookshot.exe', r'D:\emu\lichii.exe', 'yuzu.exe'):
            with self.subTest(image=image), self.assertRaises(GameRunning):
                patch_save(self.path, MANIFEST['start_values'], [MARKER], processes=['explorer.exe', image])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)
        self.assertIsNone(running_game(['explorer.exe', r'C:\Windows\notepad.exe']))

    def test_other_seed_file_is_left_untouched(self):
        data = progress({'RandoSeed.' + 'b' * 64: 1, 'HavePlayedEvent.Dm_HrlField_0000': 0})
        self.path.write_bytes(data)
        with self.assertRaises(SavePatchRefused):
            patch_save(self.path, MANIFEST['start_values'], [MARKER], processes=[])
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_failed_read_back_restores_the_backup(self):
        original = self.path.read_bytes()
        real = save_patch.decode_progress
        calls = []

        def flaky(data):
            calls.append(1)
            if len(calls) == 2:   # first decode after the write
                raise save_patch.SaveFormatError('simulated')
            return real(data)
        save_patch.decode_progress = flaky
        try:
            with self.assertRaises(save_patch.SaveFormatError):
                patch_save(self.path, MANIFEST['start_values'], [MARKER], processes=[])
        finally:
            save_patch.decode_progress = real
        self.assertEqual(self.path.read_bytes(), original)


class MigrationTests(unittest.TestCase):
    def test_regenerated_seed_also_accepts_the_replaced_seeds_saves(self):
        new = dict(MANIFEST, seed_id='c' * 64)
        self.assertEqual(migration_markers(new, MANIFEST)[:2], ['RandoSeed.' + 'c' * 64, MARKER])
        other = dict(MANIFEST, settings={'seed': 'other'})
        self.assertNotIn(MARKER, migration_markers(new, other))
        self.assertEqual(migration_markers(dict(MANIFEST, save_seed_id='z'), None), ['RandoSeed.z'])

    def test_saves_of_the_same_settings_under_any_accepted_generator_are_recognized(self):
        # Several versions skipped, or several regenerations: the save holds the flag of
        # the seed it was started with, not necessarily of the one just replaced.
        from oot_rando.randomizer.randomizer_core import Settings, settings_identity
        from oot_rando.randomizer.artifact import ACCEPTED_GENERATORS
        settings = Settings('demo')
        manifest = dict(MANIFEST, settings=settings.to_dict())
        markers = migration_markers(manifest, None)
        for generator, adapter in (('0.11.4', 'ap-glitchless-v5'), ('0.12.0', 'ap-glitchless-v5')):
            self.assertIn((generator, adapter), ACCEPTED_GENERATORS)
            self.assertIn('RandoSeed.' + settings_identity(settings, generator, adapter), markers)
        self.assertNotIn('RandoSeed.' + settings_identity(Settings('other'), '0.12.0', 'ap-glitchless-v5'),
                         markers)

    def test_every_fix_newer_than_the_replaced_seed_is_applied_in_order(self):
        steps = (('0.8.0', lambda manifest: {'Fix_B': True, 'Fix_Shared': True}),
                 ('0.7.4', lambda manifest: {'Fix_A': True, 'Fix_Shared': False}),
                 ('0.9.0', lambda manifest: {'Fix_C': True}))
        real = save_patch.SAVE_FIXES
        save_patch.SAVE_FIXES = steps
        try:
            everything = save_patch.migration_values(MANIFEST, None)   # before 0.7.3: no version
            from_073 = save_patch.migration_values(MANIFEST, dict(MANIFEST, app_version='0.7.3'))
            from_080 = save_patch.migration_values(MANIFEST, dict(MANIFEST, app_version='0.8.0'))
        finally:
            save_patch.SAVE_FIXES = real
        self.assertEqual(everything, from_073)
        self.assertTrue(everything['Fix_A'] and everything['Fix_B'] and everything['Fix_C'])
        self.assertTrue(everything['Fix_Shared'])   # 0.8.0 applied after 0.7.4
        self.assertNotIn('Fix_A', from_080)
        self.assertNotIn('Fix_B', from_080)
        self.assertTrue(from_080['Fix_C'])
        # Start values (cumulative) always, and the new seed's own flag.
        for values in (everything, from_080):
            self.assertTrue(values['HyruleField_ArriveEntrance'])
            self.assertIs(values[MARKER], True)

    def test_the_recorded_origin_of_the_saves_wins_over_the_replaced_seed(self):
        # Made by 0.7.3, regenerated by 0.7.4 (save update declined), then by 0.8.0: the
        # 0.7.4 fix is still given, though the seed just replaced was made by 0.7.4.
        steps = (('0.7.4', lambda manifest: {'Fix_A': True}), ('0.8.0', lambda manifest: {'Fix_B': True}))
        real = save_patch.SAVE_FIXES
        save_patch.SAVE_FIXES = steps
        try:
            replaced = dict(MANIFEST, app_version='0.7.4', saves_from='0.7.3')
            chained = save_patch.migration_values(dict(MANIFEST, app_version='0.8.0', saves_from='0.7.3'), replaced)
            from_replaced = save_patch.migration_values(dict(MANIFEST, app_version='0.8.0'), replaced)
            unrecorded = save_patch.migration_values(dict(MANIFEST, app_version='0.8.0', saves_from='0.0.0'), None)
        finally:
            save_patch.SAVE_FIXES = real
        for values in (chained, from_replaced, unrecorded):
            self.assertTrue(values['Fix_A'] and values['Fix_B'])
        self.assertEqual(save_patch.saves_from(dict(MANIFEST, app_version='0.7.4')), '0.7.4')
        self.assertIsNone(save_patch.saves_from(None))

    def test_a_save_started_two_versions_ago_gets_the_fixes_and_the_new_seed_flag(self):
        from oot_rando.randomizer.randomizer_core import Settings, settings_identity
        settings = Settings('demo')
        started = 'RandoSeed.' + settings_identity(settings, '0.11.4', 'ap-glitchless-v5')
        new_flag = 'RandoSeed.' + 'c' * 64
        manifest = dict(MANIFEST, seed_id='c' * 64, settings=settings.to_dict(), app_version='0.7.3')
        replaced = dict(MANIFEST, seed_id='b' * 64, settings=settings.to_dict())   # made by 0.7.2
        data = progress({started: 1, new_flag: 0, 'HyruleField_ArriveEntrance': 0})
        patched, changes, _ = plan_patch(data, save_patch.migration_values(manifest, replaced),
                                         migration_markers(manifest, replaced))
        self.assertEqual(sorted(name for name, _, _ in changes), sorted(['HyruleField_ArriveEntrance', new_flag]))
        self.assertTrue(decode_progress(patched)['bool'][murmur3(new_flag)])

    def test_candidates_list_only_saves_of_the_seed_that_need_it(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for index, data in enumerate((our_save(), progress({'RandoSeed.x': 1}),
                                          our_save(**{'HavePlayedEvent.Dm_HrlField_0000': 1,
                                                      'NaviHint_Disp_FieldHint_01': 0}), b'garbage')):
                path = Path(folder) / f'slot_0{index}' / 'progress.sav'
                path.parent.mkdir()
                path.write_bytes(data)
                paths.append(path)
            self.assertEqual(migration_candidates(paths, MANIFEST),
                             [(paths[0], ['HavePlayedEvent.Dm_HrlField_0000', 'NaviHint_Disp_FieldHint_01'])])
            self.assertEqual(migration_candidates(paths, dict(MANIFEST, start_values={})), [])
            self.assertEqual(migration_candidates(paths, {k: v for k, v in MANIFEST.items()
                                                          if k != 'start_values'}), [])


if __name__ == '__main__':
    unittest.main()
