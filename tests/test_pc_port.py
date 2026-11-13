import tempfile
import unittest
from pathlib import Path

from oot_rando.pc_port import is_port_folder, is_port_process, options_ini, port_exe


class PcPortTest(unittest.TestCase):
    def make_port(self, root, exe):
        root.mkdir()
        (root / exe).touch()
        (root / 'image.bin').touch()
        (root / 'romfs').mkdir()
        return root

    def test_any_exe_next_to_image_and_romfs_is_a_port(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for exe in ('hookshot.exe', 'longshot.exe', 'someport.exe'):
                with self.subTest(exe=exe):
                    root = self.make_port(base / exe.split('.')[0], exe)
                    self.assertTrue(is_port_folder(root))
                    self.assertEqual(port_exe(root), root / exe)
                    self.assertTrue(is_port_process(str(root / exe)))
            self.assertFalse(is_port_folder(base))
            self.assertFalse(is_port_process(str(base / 'other.exe')))
            self.assertTrue(is_port_process('Longshot.exe'))
            self.assertFalse(is_port_process(''))

    def test_options_ini_follows_the_exe_name(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            hook = self.make_port(base / 'h', 'hookshot.exe')
            self.assertEqual(options_ini(hook), hook / 'hookshot_options.ini')
            long = self.make_port(base / 'l', 'longshot.exe')
            self.assertEqual(options_ini(long), long / 'longshot_options.ini')
            (long / 'hookshot_options.ini').touch()   # fork still writing the old name
            self.assertEqual(options_ini(long), long / 'hookshot_options.ini')
            (long / 'longshot_options.ini').touch()
            self.assertEqual(options_ini(long), long / 'longshot_options.ini')
            self.assertEqual(options_ini(base / 'missing'), base / 'missing' / 'hookshot_options.ini')


if __name__ == '__main__':
    unittest.main()
