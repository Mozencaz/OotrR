"""Newest progress.sav discovery across every save folder and slot."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.tracker import auto_tracker
from oot_rando.tracker.auto_tracker import find_save_slots, newest_save


class SaveDiscoveryTests(unittest.TestCase):
    def test_newest_written_slot_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Hookshot'
            paths = []
            for index in range(3):
                path = root / 'user' / 'save' / 'profile' / f'slot_0{index}' / 'progress.sav'
                path.parent.mkdir(parents=True)
                path.write_bytes(b'x')
                paths.append(path)
            now = time.time()
            for offset, path in zip((30, 10, 20), paths):
                os.utime(path, (now - offset, now - offset))
            self.assertTrue(set(paths) <= set(find_save_slots(root / 'mods')))
            self.assertEqual(newest_save(root / 'mods'), paths[1])
            os.utime(paths[2], (now + 5, now + 5))
            self.assertEqual(newest_save(root / 'mods'), paths[2])

    def test_portable_emulator_saves_next_to_its_mods(self):
        with tempfile.TemporaryDirectory() as temporary:
            user = Path(temporary) / 'Ryuchii' / 'user'
            seed = user / 'load' / '0400486024DEC000' / 'OoT_Randomizer_0123456789abcdef'
            seed.mkdir(parents=True)
            title_save = user / 'nand' / 'user' / 'save' / '0' / 'PROFILE' / '0400486024DEC000'
            ours = title_save / 'slot_00' / 'progress.sav'
            other = user / 'nand' / 'user' / 'save' / '0' / 'PROFILE' / '0100000000010000' / 'slot_00' / 'progress.sav'
            for path in (ours, other):
                path.parent.mkdir(parents=True)
                path.write_bytes(b'x')
            for mods in (seed, seed.parent):
                with self.subTest(mods=mods.name):
                    self.assertIn(ours, find_save_slots(title='0400486024DEC000', mods=mods))
                    self.assertNotIn(other, find_save_slots(title='0400486024DEC000', mods=mods))
            self.assertNotIn(ours, find_save_slots(title='0400486024DEC000', mods=Path(temporary) / 'elsewhere'))

    def test_longshot_saves_moved_to_appdata(self):
        # Longshot's save import renames <game>/user/save to save.moved-<date> and
        # writes the saves to %APPDATA%/Longshot/save/<account>/slot_*.
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / 'Games' / 'Longshot' / 'rc5'
            (game / 'mods').mkdir(parents=True)
            (game / 'longshot.exe').write_bytes(b'')
            old = game / 'user' / 'save.moved-20261116-112431' / 'acct' / 'slot_00' / 'progress.sav'
            appdata = Path(temporary) / 'AppData' / 'Roaming'
            moved = appdata / 'Longshot' / 'save' / '5a3c9e1f0b7d2468' / 'slot_02' / 'progress.sav'
            for path in (old, moved):
                path.parent.mkdir(parents=True)
                path.write_bytes(b'x')
            previous = os.environ.get('APPDATA')
            os.environ['APPDATA'] = str(appdata)
            try:
                self.assertIn(moved, find_save_slots(game / 'mods'))
                self.assertNotIn(old, find_save_slots(game / 'mods'))
                self.assertEqual(newest_save(game / 'mods'), moved)
                # An emulator setup (no PC port) never picks the port's saves.
                self.assertNotIn(moved, find_save_slots(title='0400486024DEC000', mods=Path(temporary) / 'emu'))
            finally:
                if previous is None:
                    os.environ.pop('APPDATA', None)
                else:
                    os.environ['APPDATA'] = previous

    def test_native_linux_longshot_saves_in_xdg_data(self):
        # Longshot's Linux build: ~/.local/share/longshot/save/<account>/slot_* (round of 18/11).
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / 'Recomp Library' / 'longshot' / 'Longshot'
            (game / 'mods').mkdir(parents=True)
            (game / 'bin').mkdir()
            (game / 'bin' / 'longshot').write_bytes(b'')
            data = Path(temporary) / 'share'
            save = data / 'longshot' / 'save' / '5a3c9e1f0b7d24680000000000000001' / 'slot_00' / 'progress.sav'
            save.parent.mkdir(parents=True)
            save.write_bytes(b'x')
            # Not os.name: patching it makes Path() build a PosixPath, which Windows refuses.
            with mock.patch.object(auto_tracker, 'linux_data_home', return_value=data):
                self.assertEqual(newest_save(game / 'mods'), save)
                self.assertNotIn(save, find_save_slots(title='0400486024DEC000', mods=Path(temporary) / 'emu'))

    @unittest.skipIf(os.name == 'nt', 'no XDG data folder on Windows')
    def test_linux_data_home(self):
        with mock.patch.dict(os.environ, {'XDG_DATA_HOME': '/xdg/data'}):
            self.assertEqual(auto_tracker.linux_data_home(), Path('/xdg/data'))
        with mock.patch.dict(os.environ, {'XDG_DATA_HOME': ''}):
            self.assertEqual(auto_tracker.linux_data_home(), Path.home() / '.local' / 'share')

    @unittest.skipUnless(os.name == 'nt', 'Windows')
    def test_no_linux_data_home_on_windows(self):
        self.assertIsNone(auto_tracker.linux_data_home())

    def test_files_outside_slots_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Hookshot'
            stray = root / 'user' / 'save' / 'backup' / 'progress.sav'
            stray.parent.mkdir(parents=True)
            stray.write_bytes(b'x')
            self.assertNotIn(stray, find_save_slots(root))


if __name__ == '__main__':
    unittest.main()
