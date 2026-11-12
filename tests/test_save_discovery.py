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

    def test_files_outside_slots_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Hookshot'
            stray = root / 'user' / 'save' / 'backup' / 'progress.sav'
            stray.parent.mkdir(parents=True)
            stray.write_bytes(b'x')
            self.assertNotIn(stray, find_save_slots(root))


if __name__ == '__main__':
    unittest.main()
