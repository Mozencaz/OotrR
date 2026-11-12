"""The logic world shipped with the application (no Archipelago installation)."""
import _src_path  # noqa: F401  (src on sys.path)
import builtins
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.logic import world as world_module
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World

PACKAGE = Path(world_module.__file__).resolve().parent


class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World()

    def test_tables_and_regions(self):
        self.assertEqual(len(self.world.location_table), 1706)
        self.assertEqual(len(self.world.item_table), 224)
        self.assertEqual(self.world.vanilla_item('GV Chest'), 'Rupees (50)')
        self.assertEqual(self.world.location_type('GV Chest'), 'Chest')
        self.assertEqual(self.world.location_areas('GV Chest'), ('Gerudo Valley', 'Gerudo'))
        self.assertEqual(self.world.location_areas('Links Pocket'), ())
        self.assertTrue(self.world.is_progression('Progressive Hookshot'))
        self.assertFalse(self.world.is_progression('Rupees (5)'))
        names = {r['region_name'] for r in self.world.regions}
        self.assertIn('Root', names)
        self.assertFalse(any('MQ' in n for n in names))

    def test_remake_layer(self):
        self.assertEqual(world_module.REMAKE_LOCATION_RULES['Links Pocket'], 'Time_Travel')
        self.assertEqual(world_module.REMAKE_LOCATION_REGIONS['LW Near Shortcuts Grotto Chest'],
                         ('LW Near Shortcuts Grotto', 'Lost Woods'))
        self.assertTrue((PACKAGE / 'world' / 'LICENSE-archipelago-oot.txt').is_file())

    def test_fingerprint_is_stable_and_content_based(self):
        self.assertEqual(World().fingerprint(), self.world.fingerprint())
        self.assertIn(self.world.fingerprint()[:12], self.world.version)

    def test_logic_compiles_and_reads_only_the_package(self):
        real_open = builtins.open
        outside = []

        def guarded(file, *args, **kwargs):
            path = Path(file).resolve() if isinstance(file, (str, Path)) else None
            if path is not None and PACKAGE not in path.parents:
                outside.append(path)
            return real_open(file, *args, **kwargs)

        with patch('builtins.open', guarded), patch('io.open', guarded):
            logic = Logic(World(), {'open_forest': 'closed_deku'})
        self.assertEqual(outside, [])
        self.assertIn('LW Near Shortcuts Grotto Chest', logic.location_names())


if __name__ == '__main__':
    unittest.main()
