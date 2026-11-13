"""Every application module compiles (some are only imported by commands no test runs)."""
import _src_path  # noqa: F401  (src on sys.path)
import py_compile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src' / 'oot_rando'


class CompileAll(unittest.TestCase):
    def test_every_module_compiles(self):
        modules = sorted(SRC.rglob('*.py'))
        self.assertTrue(modules)
        for module in modules:
            with self.subTest(module=module.relative_to(SRC).as_posix()):
                py_compile.compile(str(module), doraise=True, cfile=None, optimize=-1,
                                   invalidation_mode=None)


if __name__ == '__main__':
    unittest.main()
