"""The module's logic on the PC (tests/module_host.c): the seed file's parser, the tracker's state, the game-data
reader over a fake GameData, the controls and the browsing. Needs a C compiler for the PC ($CC, cc, gcc or clang on the PATH, or
LLVM in its default place on Windows)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
REAL_SEED = FIXTURES / "real-seed.trk"
SOURCES = ["trkfile.c", "tracker.c", "gamedata.c", "grid.c", "text.c", "controls.c", "browse.c", "iconfile.c"]


def find_compiler():
    """A C compiler for the PC: $CC, else cc, gcc or clang on the PATH, else LLVM's default place on Windows."""
    candidates = [os.environ.get("CC"), shutil.which("cc"), shutil.which("gcc"), shutil.which("clang")]
    if os.name == "nt":
        candidates.append(str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LLVM" / "bin" / "clang.exe"))
    return next((c for c in candidates if c and shutil.which(c)), None)


class ModuleHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = find_compiler()
        if not compiler:
            raise unittest.SkipTest("no C compiler for the PC (set CC)")
        cls.folder = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.folder.name) / ("module_host.exe" if os.name == "nt" else "module_host")
        sources = [str(ROOT / "src" / name) for name in SOURCES]
        subprocess.run([compiler, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wno-unused-parameter", "-o", str(cls.exe),
                        str(ROOT / "tests" / "module_host.c"), str(ROOT / "tests" / "host_sys.c")] + sources, check=True)
        listing = subprocess.run([str(cls.exe), "--list"], capture_output=True, text=True, check=True).stdout
        cls.tests = [line.split() for line in listing.splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def run_test(self, name, *arguments):
        run = subprocess.run([str(self.exe), name, *arguments], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, f"{name}: {run.stderr.strip()}")

    def test_every_host_test(self):
        self.assertGreaterEqual(len(self.tests), 20)
        for name, *needs_file in self.tests:
            with self.subTest(name):
                if needs_file:
                    if not REAL_SEED.is_file():
                        self.skipTest("tests/fixtures/real-seed.trk is missing")
                    self.run_test(name, str(REAL_SEED))
                else:
                    self.run_test(name)


if __name__ == "__main__":
    unittest.main()
