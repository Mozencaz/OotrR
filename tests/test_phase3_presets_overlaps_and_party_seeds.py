# Unit tests for Midna loadout presets, overlap breakdown, and party titles in seed labels.
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oot_rando.midnas_devotion.core.config import AppConfig, StandaloneMod
from oot_rando.midnas_devotion.ui.main_window import MainWindow


class Phase3MidnaTests(unittest.TestCase):
    def test_presets_crud_and_overlap_breakdown(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg = AppConfig()
            cfg.workspace_dir = str(base / "ws")
            cfg.settings_path = str(base / "ws" / "settings.json")
            cfg.saved_state = {}

            cfg.save_preset("QoL Run", {"enabled_standalone": ["HUD"], "mod_order": ["HUD"], "prefer_rando_logo": True})
            self.assertIn("QoL Run", cfg.list_presets())
            self.assertEqual(cfg.get_preset("QoL Run")["enabled_standalone"], ["HUD"])
            self.assertTrue(cfg.delete_preset("QoL Run"))
            self.assertIsNone(cfg.get_preset("QoL Run"))

            m1 = base / "ModA"
            m2 = base / "ModB"
            (m1 / "romfs" / "UI").mkdir(parents=True)
            (m2 / "romfs" / "UI").mkdir(parents=True)
            (m1 / "romfs" / "UI" / "hud.blarc.zs").write_bytes(b"a")
            (m2 / "romfs" / "UI" / "hud.blarc.zs").write_bytes(b"b")
            (m1 / "romfs" / "Model.bfres.zs").write_bytes(b"1")
            (m2 / "romfs" / "Model.bfres.zs").write_bytes(b"2")

            mods = [
                StandaloneMod(name="ModA", source_path=str(m1), origin="library", file_count=2),
                StandaloneMod(name="ModB", source_path=str(m2), origin="library", file_count=2),
            ]
            with mock.patch.object(
                cfg,
                "classify_overlaps",
                return_value=(
                    {"romfs/Model.bfres.zs": ["ModA", "ModB"]},
                    {"romfs/UI/hud.blarc.zs": (["ModA", "ModB"], ["BLARC diff merge"])},
                ),
            ):
                rows = cfg.build_overlap_breakdown(mods)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["status"], "Conflict")
            self.assertEqual(rows[0]["category"], "Model / Scene (.bfres)")
            self.assertEqual(rows[0]["winner"], "ModB")
            self.assertEqual(rows[1]["status"], "Auto-Merged")
            self.assertEqual(rows[1]["category"], "UI Layout (.blarc)")

    def test_party_title_lookup_matches_seed_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pdir = base / "parties" / ("1" * 32)
            pdir.mkdir(parents=True)
            (pdir / "party.json").write_text(
                json.dumps({"id": "1" * 32, "name": "Co-op Hero Run", "seed_id": "abc123", "mod_name": "OoT_Rando_abc"}),
                encoding="utf-8",
            )
            seed_dir = base / "mods" / "OoT_Rando_abc"
            seed_dir.mkdir(parents=True)
            (seed_dir / "manifest.json").write_text(json.dumps({"seed_id": "abc123"}), encoding="utf-8")

            win = MainWindow.__new__(MainWindow)
            with mock.patch("oot_rando.paths.data_dir", return_value=base), mock.patch("oot_rando.paths.state_dir", return_value=base):
                title = win._party_title_for_seed(str(seed_dir))
            self.assertEqual(title, "Co-op Hero Run")


if __name__ == "__main__":
    unittest.main()
