import _src_path  # noqa: F401  (src on sys.path)
import json
from pathlib import Path
import tempfile
import unittest

from oot_rando.randomizer import spoiler_report


class SpoilerReportTests(unittest.TestCase):
    def make_seed(self, root):
        root.mkdir(parents=True)
        spoiler = {'schema_version': 1, 'seed_id': 'a' * 64, 'placements': [
            {'id': 'KokiriForest#1', 'location': 'KokiriForest — chest 1', 'item': 'Progressive Hookshot',
             'actor': 'Item_Hookshot', 'before': 'TBox_Rupee_Green', 'source': 'chest', 'sphere': 2,
             'ap_locations': ['KF Midos Top Left Chest'], 'category': 'full_chests'},
            {'id': 'boss#Barinade', 'location': 'Barinade', 'item': 'Boss Key (Forest Temple)',
             'actor': 'Item_Dungeon_BossKey', 'before': 'Item_Stone_Water', 'source': 'boss', 'sphere': None,
             'category': 'full_boss'}],
            'playthrough': [{'sphere': 0, 'items': ['KF Midos Top Left Chest : Progressive Hookshot']}]}
        checks = {'checks': [{'id': 'KokiriForest#1', 'zone': 'KokiriForest', 'region': 'Kokiri Forest',
                              'name': 'KF Midos Top Left Chest'}]}
        (root / 'spoiler.json').write_text(json.dumps(spoiler), encoding='utf-8')
        (root / 'checks.json').write_text(json.dumps(checks), encoding='utf-8')
        (root / 'manifest.json').write_text(json.dumps({'settings': {'seed': 'seedname'}}), encoding='utf-8')

    def test_report_translates_items_and_groups_by_zone(self):
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / 'OoT_Randomizer_x'
            self.make_seed(seed)
            report = spoiler_report.load_report(seed)
            rows = {r['id']: r for r in report['rows']}
            self.assertEqual(rows['KokiriForest#1']['item'], 'Hookshot')
            self.assertEqual(rows['KokiriForest#1']['original'], 'Green Rupee')
            self.assertEqual(rows['KokiriForest#1']['region'], 'Kokiri Forest')
            self.assertEqual(rows['boss#Barinade']['item'], 'Boss Key — Forest Temple')
            self.assertEqual(report['playthrough'][0]['items'], [('KF Midos Top Left Chest', 'Hookshot')])
            text = spoiler_report.render_text(report)
            self.assertIn('Seed: seedname', text)
            self.assertIn('[Kokiri Forest]', text)
            self.assertIn('KF Midos Top Left Chest [Chest]: Hookshot  (sphere 2)', text)

    def test_installed_copy_finds_generated_spoiler(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / 'seeds' / 'OoT_Randomizer_x'
            self.make_seed(generated)
            installed = Path(directory) / 'mods' / 'OoT_Randomizer_x'
            installed.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                spoiler_report.load_report(installed)
            report = spoiler_report.load_report(installed, [Path(directory) / 'seeds'])
            self.assertEqual(len(report['rows']), 2)


if __name__ == '__main__':
    unittest.main()
