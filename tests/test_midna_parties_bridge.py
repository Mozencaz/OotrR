import hashlib
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oot_rando import pc_port
from oot_rando.gui.parties_page import PartiesPage
from oot_rando.parties import PartyLibrary
from oot_rando.patching.randomize_kokiri import TITLE, BUILD
from oot_rando.randomizer.randomizer_core import (
    Settings,
    settings_identity,
    GENERATOR_VERSION,
    ADAPTER_VERSION,
)
from oot_rando.tracker.save_patch import running_game


def _make_seed(parent: Path, seed_name: str, extra_files=()):
    settings = Settings(seed_name)
    sid = settings_identity(settings)
    folder = parent / ("OoT_Randomizer_" + sid[:16])
    (folder / "romfs").mkdir(parents=True, exist_ok=True)
    files = {}
    for rel in ["shared/test.bin"] + list(extra_files):
        data = seed_name.encode("utf-8")
        fp = folder / "romfs" / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
        files[rel] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {
        "schema_version": 1,
        "title_id": TITLE,
        "build_id": BUILD,
        "generator_version": GENERATOR_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "seed_id": sid,
        "settings": settings.to_dict(),
        "files": files,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "checks.json").write_text(
        json.dumps({"seed_id": sid, "checks": []}), encoding="utf-8"
    )
    return folder, manifest


class _BridgeHarness(PartiesPage):
    def __init__(self, library: PartyLibrary, stage_root: Path):
        self.party_library = library
        self._stage_root = stage_root
        self._last_midna_switch_note = ""

    def _midna_stage_root(self):
        return self._stage_root


class MidnaPartiesBridgeTests(unittest.TestCase):
    def test_impshot_detected_on_windows_and_linux(self):
        self.assertIn("impshot.exe", pc_port.KNOWN_EXES)
        self.assertIn("impshot", pc_port.KNOWN_NAMES)
        self.assertTrue(pc_port.is_port_process("impshot"))
        self.assertTrue(pc_port.is_port_process("C:/Games/ImpShot/impshot.exe"))
        self.assertEqual(running_game(["bash", "impshot"]), "impshot")
        self.assertEqual(running_game(["explorer.exe", "ImpShot.exe"]), "impshot.exe")

    def test_switch_from_midna_merged_party_saves_progress_clears_merged_and_stages_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            lib = PartyLibrary(root / "Parties")
            mods = root / TITLE
            mods.mkdir()
            saves = root / "account_01"
            saves.mkdir(parents=True)
            stage_root = root / "midna_staged"

            seed_a, _ = _make_seed(root / "src_a", "SeedAlpha")
            seed_b, manifest_b = _make_seed(root / "src_b", "SeedBeta")

            with patch("oot_rando.parties.running_game", return_value=None):
                a = lib.create("Party A", seed_a, mods, saves)
                b = lib.create("Party B", seed_b, mods, saves)
                lib.activate(a["id"])

                # Simulate player progress on Party A + Midna building Merged_Zelda_Rando
                (saves / "slot_00").mkdir(parents=True, exist_ok=True)
                (saves / "slot_00" / "progress.sav").write_bytes(b"progress-a-v2")
                # Midna archives live seed out of mods/ and writes Merged_Zelda_Rando
                import shutil
                shutil.rmtree(mods / a["mod_name"])
                merged = mods / "Merged_Zelda_Rando" / "romfs" / "shared"
                merged.mkdir(parents=True)
                (merged / "test.bin").write_bytes(b"merged-a")

                # Add a conflicting drop-in mod
                dropin = mods / "CustomHUD" / "romfs" / "shared"
                dropin.mkdir(parents=True)
                (dropin / "test.bin").write_bytes(b"hud")

                harness = _BridgeHarness(lib, stage_root)
                # Startup / tracker fallback should point to stored snapshot while merged
                self.assertEqual(harness._party_seed_dir(a), lib.bundle(a) / "seed")

                # Switch from merged Party A to Party B via bridge
                harness._run_with_midna_bridge(
                    mods, manifest_b, lambda: lib.activate(b["id"])
                )

                self.assertEqual(lib.active_id, b["id"])
                self.assertFalse((mods / "Merged_Zelda_Rando").exists())
                self.assertTrue((mods / b["mod_name"]).is_dir())
                self.assertFalse((mods / "CustomHUD").exists())
                self.assertTrue((stage_root / "CustomHUD").is_dir())
                self.assertIn("Merged_Zelda_Rando", harness._last_midna_switch_note)
                self.assertIn("CustomHUD", harness._last_midna_switch_note)

                # Party A progress was preserved in its snapshot before switching!
                a_after = lib.get(a["id"])
                self.assertEqual(
                    (lib.bundle(a_after) / "save" / "slot_00" / "progress.sav").read_bytes(),
                    b"progress-a-v2",
                )

    def test_bridge_rolls_back_merged_and_staged_mods_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            lib = PartyLibrary(root / "Parties")
            mods = root / TITLE
            mods.mkdir()
            saves = root / "account_01"
            saves.mkdir(parents=True)
            stage_root = root / "midna_staged"

            seed_a, _ = _make_seed(root / "src_a", "SeedAlpha")
            seed_b, manifest_b = _make_seed(root / "src_b", "SeedBeta")

            with patch("oot_rando.parties.running_game", return_value=None):
                a = lib.create("Party A", seed_a, mods, saves)
                lib.create("Party B", seed_b, mods, saves)
                lib.activate(a["id"])

                import shutil
                shutil.rmtree(mods / a["mod_name"])
                merged = mods / "Merged_Zelda_Rando" / "romfs" / "shared"
                merged.mkdir(parents=True)
                (merged / "test.bin").write_bytes(b"merged-a")

                dropin = mods / "CustomHUD" / "romfs" / "shared"
                dropin.mkdir(parents=True)
                (dropin / "test.bin").write_bytes(b"hud")

                harness = _BridgeHarness(lib, stage_root)

                def boom():
                    raise RuntimeError("simulated switch failure")

                with self.assertRaisesRegex(RuntimeError, "simulated switch failure"):
                    harness._run_with_midna_bridge(mods, manifest_b, boom)

                # Everything rolled back cleanly
                self.assertTrue((mods / "Merged_Zelda_Rando" / "romfs" / "shared" / "test.bin").is_file())
                self.assertTrue((mods / "CustomHUD" / "romfs" / "shared" / "test.bin").is_file())
                self.assertFalse((mods / a["mod_name"]).exists())
                self.assertFalse((stage_root / "CustomHUD").exists())


if __name__ == "__main__":
    unittest.main()
