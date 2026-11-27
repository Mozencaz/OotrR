"""The committed ``apworld/oot_remake.apworld`` matches the sources it is built from.

Everything but ``catalog.json`` comes from the sources (checked without the game);
the catalog is rebuilt from the game when ``OOT_NUP`` is set. A failure means:
rebuild it with ``python -m oot_rando apworld GAME.nup apworld/oot_remake.apworld``.
"""
import _src_path  # noqa: F401
import json
import os
from pathlib import Path
import unittest
import zipfile

from oot_rando.archipelago import apworld_build

COMMITTED = Path(__file__).resolve().parents[1] / 'apworld' / 'oot_remake.apworld'
NUP = os.environ.get('OOT_NUP')
REBUILD = 'apworld/oot_remake.apworld is out of date: rebuild it (python -m oot_rando apworld GAME.nup apworld/oot_remake.apworld).'


def _text(data):
    return data.replace(b'\r\n', b'\n')   # git may check sources out with CRLF


class ApworldDriftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = zipfile.ZipFile(COMMITTED)
        cls.addClassCleanup(cls.archive.close)

    def expected_sources(self):
        package = apworld_build.PACKAGE
        from oot_rando.paths import resource
        expected = {f'{package}/vendor/{name}': source for name, source in apworld_build.vendored_files()}
        expected[f'{package}/__init__.py'] = resource(apworld_build.TEMPLATE)
        return expected

    def test_members(self):
        package = apworld_build.PACKAGE
        expected = set(self.expected_sources()) | {f'{package}/archipelago.json', f'{package}/catalog.json'}
        self.assertEqual(sorted(set(self.archive.namelist()) ^ expected), [], REBUILD)

    def test_sources_match(self):
        stale = [name for name, source in self.expected_sources().items()
                 if name in self.archive.namelist()
                 and _text(self.archive.read(name)) != _text(source.read_bytes())]
        self.assertEqual(stale, [], REBUILD)

    def test_manifest_matches(self):
        stored = json.loads(self.archive.read(f'{apworld_build.PACKAGE}/archipelago.json'))
        self.assertEqual(stored, apworld_build.manifest(), REBUILD)

    def test_vendored_modules_import_without_the_native_packages(self):
        # Archipelago runs the apworld without zstandard/evfl/ainb: a vendored module
        # importing a game-file module at load time breaks every multiworld generation.
        # Only the vendored files are copied: a module they import but the apworld lacks fails too.
        import shutil
        import subprocess
        import sys
        import tempfile
        names = [name[:-3].replace('/', '.') for name in apworld_build.VENDORED
                 if name.endswith('.py') and not name.endswith('__init__.py')]
        with tempfile.TemporaryDirectory() as folder:
            for name, source in apworld_build.vendored_files():
                destination = Path(folder) / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            script = '\n'.join([
                'import importlib, sys',
                'for blocked in ("zstandard", "evfl", "ainb"): sys.modules[blocked] = None',
                f'sys.path.insert(0, {folder!r})',
                f'for name in {names!r}: importlib.import_module("oot_rando." + name)',
            ])
            result = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])

    @unittest.skipUnless(NUP, 'OOT_NUP not set')
    def test_catalog_matches_the_game(self):
        from oot_rando.archipelago.bridge import build_catalog
        from oot_rando.logic.world import World
        build, groups, enemies, extra = apworld_build.scan_game(NUP)
        catalog = json.loads(json.dumps(build_catalog(World(), groups, enemies, extra, build)))
        stored = json.loads(self.archive.read(f'{apworld_build.PACKAGE}/catalog.json'))
        self.assertTrue(stored == catalog, REBUILD)


if __name__ == '__main__':
    unittest.main()
