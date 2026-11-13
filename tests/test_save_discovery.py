"""Newest progress.sav discovery across every save folder and slot."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
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

    def test_files_outside_slots_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Hookshot'
            stray = root / 'user' / 'save' / 'backup' / 'progress.sav'
            stray.parent.mkdir(parents=True)
            stray.write_bytes(b'x')
            self.assertNotIn(stray, find_save_slots(root))


if __name__ == '__main__':
    unittest.main()
