import _src_path  # noqa: F401
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from oot_rando.parties import PartyLibrary
from oot_rando.path_safety import (
    MAX_COMPONENT_BYTES,
    SEED_ROMFS_HEADROOM,
    safe_archive_target,
    sanitize_portable_name,
    validate_component_name,
    validate_file_path,
    validate_path_headroom,
)
import hashlib
from oot_rando.patching.randomize_kokiri import BUILD, TITLE
from oot_rando.randomizer.randomizer_core import ADAPTER_VERSION, GENERATOR_VERSION, Settings, settings_identity
from oot_rando.randomizer.artifact import QOL_FOLDER, QOL_KIND, is_qol_install
from oot_rando.randomizer.mods_folder import preflight_plain_generation


def _make_fake_seed(root: Path, settings: Settings) -> Path:
    sid = settings_identity(settings)
    mod_dir = root / ("OoT_Randomizer_" + sid[:16])
    (mod_dir / "romfs").mkdir(parents=True, exist_ok=True)
    data = settings.seed.encode("utf-8")
    (mod_dir / "romfs" / "resource").write_bytes(data)
    manifest = {
        "schema_version": 1,
        "title_id": TITLE,
        "build_id": BUILD,
        "generator_version": GENERATOR_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "seed_id": sid,
        "settings": settings.to_dict(),
        "files": {"resource": {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}},
    }
    (mod_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (mod_dir / "checks.json").write_text(json.dumps({"seed_id": sid, "checks": []}), encoding="utf-8")
    return mod_dir


class PathSafetyAndHeadroomTests(unittest.TestCase):
    def test_component_rejects_over_255_utf8_bytes_including_multibyte_unicode(self):
        cjk_name = "ゼルダの伝説" * 16
        self.assertLess(len(cjk_name), 255)
        self.assertGreater(len(cjk_name.encode("utf-8")), MAX_COMPONENT_BYTES)
        with self.assertRaisesRegex(ValueError, "too long"):
            validate_component_name(cjk_name, label="Mod folder")

    def test_windows_reserved_names_and_trailing_dots_rejected_in_portable_mode(self):
        for bad in ("CON", "nul", "COM1.txt", "TrailingDot.", "TrailingSpace "):
            with self.assertRaises(ValueError):
                validate_component_name(bad, label="Mod folder", portable=True)

    def test_sanitize_portable_name_bounds_length_and_avoids_reserved_names(self):
        self.assertEqual(sanitize_portable_name("Playable_Zelda"), "Playable_Zelda")
        self.assertEqual(sanitize_portable_name("CON"), "Mod_CON")
        huge = "Playable_Zelda_Complete_Overhaul_Pack_With_All_Costumes_And_UI_Icons_v3_2_0_Final_Release"
        bounded = sanitize_portable_name(huge, max_len=64)
        self.assertLessEqual(len(bounded), 64)
        self.assertLessEqual(len(bounded.encode("utf-8")), 64)
        self.assertEqual(bounded, sanitize_portable_name(huge, max_len=64))

    def test_windows_max_path_headroom_blocks_deep_folder_when_long_paths_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / ("a" * 70) / ("b" * 70) / ("c" * 50)
            with self.assertRaisesRegex(ValueError, "260-character Windows limit"):
                validate_path_headroom(
                    deep,
                    max_relative_len=SEED_ROMFS_HEADROOM,
                    label="Mods folder",
                    _simulate_win32=True,
                    _win_long_paths_override=False,
                )
            ok_path = validate_path_headroom(
                deep,
                max_relative_len=SEED_ROMFS_HEADROOM,
                label="Mods folder",
                _simulate_win32=True,
                _win_long_paths_override=True,
            )
            self.assertTrue(str(ok_path).endswith("c" * 50))

    def test_safe_archive_target_bounds_filename_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            arch = Path(tmp)
            long_base = "Mod_" + ("x" * 250)
            t1 = safe_archive_target(arch, long_base, "-replaced")
            self.assertLessEqual(len(t1.name.encode("utf-8")), MAX_COMPONENT_BYTES)
            t1.mkdir()
            t2 = safe_archive_target(arch, long_base, "-replaced")
            self.assertNotEqual(t1, t2)
            self.assertLessEqual(len(t2.name.encode("utf-8")), MAX_COMPONENT_BYTES)

    def test_validate_file_path_catches_260_char_win_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / ("dir_" + "x" * 90) / ("sub_" + "y" * 90) / ("file_" + "z" * 80 + ".zs")
            with self.assertRaisesRegex(ValueError, "260-character"):
                validate_file_path(
                    f,
                    enforce_win_classic=True,
                    _simulate_win32=True,
                    _win_long_paths_override=False,
                )


class EarlyPreGenerationChecksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.lib_root = self.base / "Parties"
        self.mods = self.base / TITLE
        self.mods.mkdir(parents=True)
        self.saves_a = self.base / "saves" / "account_a"
        self.saves_b = self.base / "saves" / "account_b"
        self.saves_a.mkdir(parents=True)
        self.saves_b.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    @mock.patch("oot_rando.parties.running_game", return_value=None)
    def test_party_preflight_catches_qol_unmanaged_seed_and_foreign_saves_before_generation(self, _mock_game):
        lib = PartyLibrary(self.lib_root)
        s1 = Settings("seed-one")
        staged = self.base / "staged"
        seed1 = _make_fake_seed(staged, s1)
        p1 = lib.create("Adventure 1", seed1, self.mods, self.saves_a)
        lib.activate(p1["id"])

        (self.saves_b / "slot_00").mkdir(parents=True)
        (self.saves_b / "slot_00" / "progress.sav").write_bytes(b"save")
        with self.assertRaisesRegex(ValueError, "already contains saves"):
            lib.preflight_generation("Adventure 2", self.mods, self.saves_b, Settings("seed-two"))

        saves_empty = self.base / "saves" / "account_c"
        saves_empty.mkdir(parents=True)
        _make_fake_seed(self.mods, Settings("rogue-unmanaged"))
        with self.assertRaisesRegex(ValueError, "unmanaged seed"):
            lib.preflight_generation("Adventure 2", self.mods, saves_empty, Settings("seed-two"))
        for rogue in list(self.mods.glob("OoT_Randomizer_*")):
            if rogue.name != p1["mod_name"]:
                shutil.rmtree(rogue)

        qol_dir = self.mods / QOL_FOLDER
        qol_dir.mkdir()
        (qol_dir / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": QOL_KIND, "title_id": TITLE, "build_id": BUILD}),
            encoding="utf-8",
        )
        self.assertTrue(is_qol_install(qol_dir))
        with self.assertRaisesRegex(ValueError, "OoT_QoL"):
            lib.preflight_generation("Adventure 2", self.mods, saves_empty, Settings("seed-two"))

    def test_plain_preflight_rejects_colliding_non_seed_folder_upfront(self):
        s = Settings("plain-check")
        sid = settings_identity(s)[:16]
        blocker = self.mods / ("OoT_Randomizer_" + sid)
        blocker.mkdir()
        (blocker / "not_a_seed.txt").write_text("custom", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists in the mods"):
            preflight_plain_generation(
                "dummy.nup", self.mods, s, archive=self.base / "archive",
                check_nup=False, check_game_closed=False,
            )


if __name__ == "__main__":
    unittest.main()
