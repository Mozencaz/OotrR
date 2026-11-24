"""Regression tests for 3-channel Longshot updates, party migration, 3-tier dedupe, and 7-Zip fallbacks."""
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from oot_rando import pc_port
from oot_rando.midnas_devotion.core.config import AppConfig, StandaloneMod
from oot_rando.midnas_devotion.core.dedupe import (
    ExistingModTarget,
    check_mod_duplicates,
    find_internal_duplicates,
    fingerprint_archive_variant,
    fingerprint_mod_dir,
    normalize_mod_name,
)
from oot_rando.midnas_devotion.core.preflight import ArchiveHandle, _find_bundled_7zip, _find_windows_system_tar
from oot_rando.parties import PartyLibrary
from oot_rando.patching.randomize_kokiri import TITLE, BUILD


def _make_port(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "image.bin").write_bytes(b"img")
    (root / "romfs" / "Pack").mkdir(parents=True, exist_ok=True)
    (root / "romfs" / "Pack" / "ZsDic.pack.zs").write_bytes(b"zsdic")
    (root / "mods").mkdir(parents=True, exist_ok=True)
    return root


def _make_fake_seed(seed_dir: Path, seed_label: str = "testseed") -> str:
    import hashlib
    from oot_rando.randomizer.randomizer_core import (
        ADAPTER_VERSION,
        GENERATOR_VERSION,
        Settings,
        settings_identity,
    )
    settings = Settings(seed=seed_label)
    seed_id = settings_identity(settings)
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "romfs").mkdir(exist_ok=True)
    data = seed_label.encode("utf-8")
    (seed_dir / "romfs" / "resource").write_bytes(data)
    manifest = {
        "schema_version": 1,
        "title_id": TITLE,
        "build_id": BUILD,
        "seed_id": seed_id,
        "generator_version": GENERATOR_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "settings": settings.to_dict(),
        "files": {
            "resource": {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        },
    }
    (seed_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (seed_dir / "checks.json").write_text(
        json.dumps({"seed_id": seed_id, "checks": []}), encoding="utf-8"
    )
    return seed_id


class LongshotChannelAndMigrationTests(unittest.TestCase):
    def test_single_channel_upgrade_from_deleted_v3_1_1_to_v3_2_0(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            v320 = _make_port(ls_root / "stable" / "v3.2.0")
            stale_mods = ls_root / "stable" / "v3.1.1" / "mods"

            info = pc_port.resolve_longshot_update(stale_mods)
            self.assertEqual(info["status"], "upgraded")
            self.assertEqual(info["current_channel"], "stable")
            self.assertEqual(info["recommended"]["port_dir"], v320)
            self.assertEqual(info["recommended"]["mods_dir"], v320 / "mods")

            same = pc_port.resolve_longshot_update(v320 / "mods")
            self.assertEqual(same["status"], "unchanged")

    def test_multi_channel_always_prompts_with_all_three_channels(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            _make_port(ls_root / "stable" / "v3.2.0")
            _make_port(ls_root / "release candidate" / "v3.2.1-rc.2")
            _make_port(ls_root / "release candidate" / "v3.2.1-rc.1")
            _make_port(ls_root / "nightly" / "2026-11-24")
            _make_port(ls_root / "nightly" / "2026-11-20")

            info = pc_port.resolve_longshot_update(ls_root / "stable" / "v3.1.1" / "mods")
            self.assertEqual(info["status"], "choose_channel")
            names = [(c["channel"], c["version_name"]) for c in info["channels"]]
            self.assertEqual(
                names,
                [
                    ("stable", "v3.2.0"),
                    ("release candidate", "v3.2.1-rc.2"),
                    ("nightly", "2026-11-24"),
                ],
            )
            self.assertEqual(info["recommended"]["channel"], "stable")

    def test_normalize_port_mods_dir_resolves_port_root(self):
        with tempfile.TemporaryDirectory() as td:
            v320 = _make_port(Path(td) / "Longshot" / "stable" / "v3.2.0")
            self.assertEqual(pc_port.normalize_port_mods_dir(str(v320) + os.sep), str(v320 / "mods"))
            self.assertEqual(pc_port.normalize_port_mods_dir(str(v320 / "mods") + os.sep), str(v320 / "mods"))

    def test_party_library_migrates_stale_parties_and_activates_when_outgoing_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ls_root = base / "Longshot"
            v311 = _make_port(ls_root / "stable" / "v3.1.1")
            v320 = _make_port(ls_root / "stable" / "v3.2.0")
            saves = base / "saves" / "account01"
            saves.mkdir(parents=True)

            lib = PartyLibrary(base / "Parties")
            seed1 = base / "tmp_seed1"
            _make_fake_seed(seed1, "oldpartyseed")
            with mock.patch.object(lib, "_closed"):
                p1 = lib.create("OldParty", seed1, v311 / "mods", saves)
                lib.activate(p1["id"])
            (saves / "slot_00").mkdir(parents=True)
            (saves / "slot_00" / "progress.sav").write_bytes(b"sav")

            # Simulate Longshot deleting v3.1.1 on update to v3.2.0
            import shutil
            shutil.rmtree(v311)

            # Activating a new party on v3.2.0 must succeed even when outgoing v3.1.1/mods is gone
            seed2 = base / "tmp_seed2"
            _make_fake_seed(seed2, "newpartyseed")
            p2 = lib.create("NewParty", seed2, v320 / "mods", saves)
            with mock.patch.object(lib, "_closed"):
                lib.activate(p2["id"])
            self.assertEqual(lib.active_id, p2["id"])

            # Migrating remaining stale v3.1.1 parties updates OldParty to v3.2.0/mods
            migrated = lib.migrate_mods_directory(v320 / "mods", old_mods=v311 / "mods", root=ls_root)
            self.assertEqual(migrated, ["OldParty"])
            p1_after = lib.get(p1["id"])
            self.assertEqual(Path(p1_after["mods"]), (v320 / "mods").resolve())

    def test_config_sync_rewrites_old_port_prefix_and_updates_library(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            v311 = _make_port(base / "Longshot" / "stable" / "v3.1.1")
            v320 = _make_port(base / "Longshot" / "stable" / "v3.2.0")
            (v311 / "UserModLibrary" / "Classic_UI").mkdir(parents=True)
            (v320 / "UserModLibrary" / "Classic_UI").mkdir(parents=True)

            cfg_path = base / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "live_mods_dir": str(v311 / "mods"),
                        "romfs_dir": str(v311 / "romfs"),
                        "backup_dir": str(v311 / "UserModLibrary"),
                        "added_list_mod_paths": [str(v311 / "UserModLibrary" / "Classic_UI")],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("oot_rando.midnas_devotion.core.config.read_randomizer_state", return_value={}):
                cfg = AppConfig(settings_path=str(cfg_path))
            changed = cfg.sync_from_randomizer(str(v320 / "mods"), persist=True)
            self.assertTrue(changed)
            self.assertEqual(cfg.live_mods_dir, str(v320 / "mods"))
            self.assertEqual(cfg.romfs_dir, str(v320 / "romfs"))
            self.assertEqual(cfg.backup_dir, str(v320 / "UserModLibrary"))
            self.assertEqual(
                cfg.saved_state["added_list_mod_paths"],
                [str(v320 / "UserModLibrary" / "Classic_UI")],
            )


class ThreeTierDedupeTests(unittest.TestCase):
    def _write_mod(self, root: Path, files: dict) -> Path:
        for rel, data in files.items():
            target = root / "romfs" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return root

    def test_tier1_exact_content_detects_renamed_folder_and_archive(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            existing = self._write_mod(
                base / "Classic_UI",
                {"UI/Layout/Hud.blarc.zs": b"hud-bytes-123", "Tex/Icon.bntx": b"icon-456"},
            )
            renamed = self._write_mod(
                base / "Completely_Different_Name",
                {"UI/Layout/Hud.blarc.zs": b"hud-bytes-123", "Tex/Icon.bntx": b"icon-456"},
            )
            targets = [ExistingModTarget(name="Classic_UI", path=str(existing), origin="staged")]
            matches = check_mod_duplicates(fingerprint_mod_dir(str(renamed)), targets)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].tier, 1)
            self.assertEqual(matches[0].kind, "EXACT_CONTENT")

            # Also verify direct ZIP archive fingerprinting matches Tier 1 before extraction
            zpath = base / "repack.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("MyVariant/RomFS/UI/Layout/Hud.blarc.zs", b"hud-bytes-123")
                zf.writestr("MyVariant/RomFS/Tex/Icon.bntx", b"icon-456")
            with ArchiveHandle(str(zpath)) as arc:
                afp = fingerprint_archive_variant(arc, "MyVariant", display_name="MyVariant")
            amatches = check_mod_duplicates(afp, targets)
            self.assertEqual(len(amatches), 1)
            self.assertEqual(amatches[0].kind, "EXACT_CONTENT")

    def test_tier2_fuzzy_and_version_stripped_name_matching(self):
        self.assertEqual(normalize_mod_name("Classic_UI_v1.2.3_Fixed"), "classic ui")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            existing = self._write_mod(base / "Original_Mirror_Shield_v1.0", {"Model/ShieldA.bfres": b"aaa"})
            cand = self._write_mod(base / "Original-Mirror-Shield-v2.1", {"Model/ShieldB.bfres": b"bbb"})
            targets = [ExistingModTarget(name=existing.name, path=str(existing), origin="library")]
            matches = check_mod_duplicates(fingerprint_mod_dir(str(cand)), targets)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].tier, 2)
            self.assertEqual(matches[0].kind, "SIMILAR_NAME")
            self.assertGreaterEqual(matches[0].name_similarity, 0.99)

    def test_tier3_high_asset_overlap_flags_updated_variant(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            existing = self._write_mod(
                base / "Temple_Audio_Old",
                {
                    "Sound/a.bars": b"1",
                    "Sound/b.bars": b"2",
                    "Sound/c.bars": b"3",
                    "Sound/d.bars": b"4",
                },
            )
            updated = self._write_mod(
                base / "BrandNewRenamedPack",
                {
                    "Sound/a.bars": b"1",
                    "Sound/b.bars": b"2",
                    "Sound/c.bars": b"3",
                    "Sound/d.bars": b"4-UPDATED",
                },
            )
            targets = [ExistingModTarget(name=existing.name, path=str(existing), origin="staged")]
            matches = check_mod_duplicates(fingerprint_mod_dir(str(updated)), targets)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].tier, 3)
            self.assertEqual(matches[0].kind, "HIGH_OVERLAP")
            self.assertEqual(matches[0].identical_files, 3)
            self.assertEqual(matches[0].changed_files, 1)

    def test_internal_duplicates_detection(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            a = self._write_mod(base / "ModA", {"Tex/a.bntx": b"same"})
            b = self._write_mod(base / "ModB", {"Tex/a.bntx": b"same"})
            c = self._write_mod(base / "ModC", {"Tex/c.bntx": b"other"})
            mods = [
                StandaloneMod(name="ModA", source_path=str(a), origin="live", file_count=1),
                StandaloneMod(name="ModB", source_path=str(b), origin="staged", file_count=1),
                StandaloneMod(name="ModC", source_path=str(c), origin="staged", file_count=1),
            ]
            dupes = find_internal_duplicates(mods)
            self.assertEqual(dupes, {"ModA": ["ModB"], "ModB": ["ModA"]})


class ExtractorFallbackTests(unittest.TestCase):
    def test_bundled_7zip_and_windows_tar_order(self):
        with tempfile.TemporaryDirectory() as td:
            fake_7z = Path(td) / "oot_rando" / "midnas_devotion" / "vendor" / "7zip" / "7z.exe"
            fake_7z.parent.mkdir(parents=True)
            fake_7z.write_bytes(b"MZ")
            fake_tar = Path(td) / "Windows" / "System32" / "tar.exe"
            fake_tar.parent.mkdir(parents=True)
            fake_tar.write_bytes(b"MZ")

            with mock.patch("oot_rando.midnas_devotion.core.preflight.sys.platform", "win32"),                  mock.patch("oot_rando.midnas_devotion.core.preflight.sys._MEIPASS", td, create=True),                  mock.patch.dict(os.environ, {"SystemRoot": str(Path(td) / "Windows")}):
                self.assertEqual(_find_bundled_7zip(), str(fake_7z))
                self.assertEqual(_find_windows_system_tar(), str(fake_tar))


if __name__ == "__main__":
    unittest.main()
