"""Supported-game check of a NUP: by title ids and update version, not TOC layout (issue #4)."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.patching.randomize_kokiri import BUILD, TITLE, UPDATE_VERSION, check_supported_game

BASE, UPDATE = int(TITLE, 16), int(TITLE, 16) + 0x800
MAIN = b'NSO0' + bytes(0x3c) + bytes.fromhex(BUILD)


class FakeNup:
    def __init__(self, packages, main=MAIN):
        self.packages, self.main = packages, main

    def read(self, path):
        if path != '1/exefs/main' or self.main is None:
            raise KeyError(path)
        return self.main


class NupCheckTest(unittest.TestCase):
    def test_reference_layout(self):
        check_supported_game(FakeNup([(BASE, 0, 1, 2, 65536), (UPDATE, 598, 599, 600, UPDATE_VERSION)]))

    def test_other_dump_tool_layout(self):
        # Update first, other directory indices, an extra (DLC-like) package.
        check_supported_game(FakeNup([(UPDATE, 0, 1, 2, UPDATE_VERSION), (BASE + 0x1001, 7, 8, 9, 0),
                                      (BASE, 3, 4, 5, 0)]))

    def test_missing_update(self):
        with self.assertRaisesRegex(ValueError, 'update is missing'):
            check_supported_game(FakeNup([(BASE, 0, 1, 2, 0)], main=None))

    def test_other_update_version(self):
        with self.assertRaisesRegex(ValueError, 'update v196608'):
            check_supported_game(FakeNup([(BASE, 0, 1, 2, 0), (UPDATE, 5, 6, 7, 196608)]))

    def test_other_game(self):
        with self.assertRaisesRegex(ValueError, 'not Ocarina of Time'):
            check_supported_game(FakeNup([(0x0100000000010000, 0, 1, 2, 0)]))

    def test_other_build(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported game build'):
            check_supported_game(FakeNup([(BASE, 0, 1, 2, 0), (UPDATE, 5, 6, 7, UPDATE_VERSION)],
                                         main=b'NSO0' + bytes(0x5c)))


class EmulatorNamesTest(unittest.TestCase):
    def test_parse(self):
        from oot_rando.tracker.live_memory import EMULATOR_EXES, parse_exe_names
        self.assertIn('ryuchii.exe', EMULATOR_EXES)
        self.assertEqual(parse_exe_names(' MyFork, other.EXE;"C:\\Emu\\third.exe"\n\n'),
                         {'myfork.exe', 'other.exe', 'third.exe'})
        self.assertEqual(parse_exe_names(''), set())


if __name__ == '__main__':
    unittest.main()
