"""Regression tests for Midna's Devotion core modules (config, formats, merger, preflight)."""
import json
import os
import struct
import tempfile
import unittest
import zipfile
from unittest import mock

from oot_rando.midnas_devotion.core import config, formats, merger, preflight


class ConfigCoreTests(unittest.TestCase):
    def test_version_sort_prefers_v0_10_over_v0_9(self):
        with tempfile.TemporaryDirectory() as td:
            stable = os.path.join(td, "stable")
            for ver in ("v0.9", "v0.10", "v0.2"):
                os.makedirs(os.path.join(stable, ver, "romfs"))
            detected = config.auto_detect_from_folder(td)
            self.assertEqual(detected["romfs_dir"], os.path.join(stable, "v0.10", "romfs"))

    def test_rewrite_path_prefix_handles_tilde_and_subpaths(self):
        with tempfile.TemporaryDirectory() as td:
            old_root = os.path.join(td, "mods_backup")
            new_root = os.path.join(td, "UserModLibrary")
            payload = {
                "single": old_root,
                "nested": [os.path.join(old_root, "Classic_UI")],
                "other": os.path.join(td, "unrelated"),
            }
            rewritten = config.AppConfig._rewrite_path_prefix(payload, old_root, new_root)
            self.assertEqual(rewritten["single"], new_root)
            self.assertEqual(rewritten["nested"], [os.path.join(new_root, "Classic_UI")])
            self.assertEqual(rewritten["other"], payload["other"])

    def test_save_settings_is_atomic_and_unlink_cleans_mod_order(self):
        with tempfile.TemporaryDirectory() as td:
            settings_p = os.path.join(td, "settings.json")
            mod_dir = os.path.join(td, "Classic_UI")
            os.makedirs(os.path.join(mod_dir, "romfs"))
            cfg = config.AppConfig(settings_path=settings_p)
            cfg.workspace_dir = os.path.join(td, "ws")
            cfg.add_mod_folder_to_list(mod_dir)
            cfg.set_mod_order(["Classic_UI", "OtherMod"])
            cfg.save_settings({"enabled_standalone": ["Classic_UI"]})

            mod = config.StandaloneMod(name="Classic_UI", source_path=mod_dir, origin="linked", file_count=0)
            cfg.delete_standalone_mod(mod)

            with open(settings_p, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["added_list_mod_paths"], [])
            self.assertEqual(saved["enabled_standalone"], [])
            self.assertEqual(saved["mod_order"], ["OtherMod"])

    def test_clean_subprocess_env_strips_qt_reparenting_vars(self):
        with mock.patch.dict(
            os.environ,
            {"QT_QPA_PLATFORM": "xcb", "QT_ENABLE_HIGHDPI_SCALING": "0", "PATH": "/usr/bin"},
            clear=True,
        ):
            cleaned = config.clean_subprocess_env()
            self.assertNotIn("QT_QPA_PLATFORM", cleaned)
            self.assertNotIn("QT_ENABLE_HIGHDPI_SCALING", cleaned)


class FormatsCoreTests(unittest.TestCase):
    def test_parse_bntx_rejects_bad_magic_and_truncated_data(self):
        with self.assertRaises(ValueError):
            formats.parse_bntx(b"NOPE" + b"\x00" * 64)
        with self.assertRaises(ValueError):
            formats.parse_bntx(b"BNTX" + b"\x00" * 10)

    def test_parse_and_build_bars_roundtrip_and_bounds_check(self):
        amta = b"AMTA" + b"\xff\xfe\x00\x04" + struct.pack("<I", 20) + b"SongA\x00\x00\x00"
        arc = formats.BarsArchive(
            version=0x0101,
            bom=0xFEFF,
            entries={0x12345678: formats.BarsEntry(crc=0x12345678, amta=amta, asset=b"WAVEDATA")},
        )
        raw = formats.build_bars(arc)
        parsed = formats.parse_bars(raw)
        self.assertIn(0x12345678, parsed.entries)
        self.assertEqual(formats.extract_amta_name(parsed.entries[0x12345678].amta, 0x12345678), "SongA")

        bad_header = struct.pack("<4sIHHI", b"BARS", 16, 0xFEFF, 0x0101, 999)
        with self.assertRaises(ValueError):
            formats.parse_bars(bad_header)


class MergerAndPreflightTests(unittest.TestCase):
    def test_swap_in_directory_replaces_atomically_and_rolls_back_on_error(self):
        with tempfile.TemporaryDirectory() as td:
            final_dir = os.path.join(td, "Merged_Zelda_Rando")
            stage_dir = os.path.join(td, ".Merged_Zelda_Rando.building")
            os.makedirs(final_dir)
            with open(os.path.join(final_dir, "marker.txt"), "w", encoding="utf-8") as f:
                f.write("old")
            os.makedirs(stage_dir)
            with open(os.path.join(stage_dir, "marker.txt"), "w", encoding="utf-8") as f:
                f.write("new")

            merger._swap_in_directory(stage_dir, final_dir)
            with open(os.path.join(final_dir, "marker.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "new")
            self.assertFalse(os.path.exists(stage_dir))
            self.assertFalse(os.path.exists(final_dir + ".old_backup"))

    def test_install_archive_normalizes_romfs_casing_and_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = os.path.join(td, "UpperRomfsMod.zip")
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("PackA/RomFS/Model/Link.bfres.zs", b"model-bytes")
                zf.writestr("PackA/README.txt", b"hello")
                zf.writestr("PackA/../../escape.txt", b"nope")

            out_parent = os.path.join(td, "staged")
            with preflight.ArchiveHandle(zpath) as arc:
                variants, exefs = preflight.list_archive_variants(arc)
                self.assertEqual(variants, ["PackA"])
                self.assertEqual(exefs, [])
                installed = preflight.install_archive_to_dir(arc, "PackA", "UpperMod", out_parent)

            self.assertTrue(os.path.isfile(os.path.join(installed, "romfs", "Model", "Link.bfres.zs")))
            self.assertTrue(os.path.isfile(os.path.join(installed, "README.txt")))
            self.assertFalse(os.path.exists(os.path.join(td, "escape.txt")))


if __name__ == "__main__":
    unittest.main()
