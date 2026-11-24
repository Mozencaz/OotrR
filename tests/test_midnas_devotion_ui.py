"""Regression tests for Midna's Devotion UI helper logic (themes, preflight rows, mod file labels)."""
import unittest


class MidnaUiHelpersTests(unittest.TestCase):
    def test_preflight_classify_row_flags_exefs_and_decompress_err_as_danger(self):
        try:
            from oot_rando.midnas_devotion.ui.preflight_dialog import _classify_row
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        for plain in (True, False):
            sev_exefs, lbl_exefs, _, _ = _classify_row("EXEFS", plain=plain)
            self.assertEqual(sev_exefs, "danger")
            self.assertIn("Code Mod", lbl_exefs)

            sev_dec, lbl_dec, _, _ = _classify_row("DECOMPRESS_ERR", plain=plain)
            self.assertEqual(sev_dec, "danger")
            self.assertIn("Unreadable", lbl_dec)

            sev_combo, lbl_combo, _, _ = _classify_row("DECOMPRESS_ERR+OVERLAP", plain=plain)
            self.assertEqual(sev_combo, "danger")
            self.assertIn("Overlap", lbl_combo)

            sev_ok, _, _, _ = _classify_row("OK", plain=plain)
            self.assertEqual(sev_ok, "ok")

    def test_mod_files_auto_merge_label_matches_asset_type(self):
        try:
            from oot_rando.midnas_devotion.ui.mod_files_dialog import _auto_merge_label
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        self.assertIn("Audio", _auto_merge_label("Sound/Resource/Bgm.bars.zs"))
        self.assertIn("UI", _auto_merge_label("UI/LayoutArchive/Title.blarc.zs"))
        self.assertIn("Dialogue", _auto_merge_label("Mals/USen.Product.110.sarc.zs"))
        self.assertIn("Table", _auto_merge_label("System/Resource/ResourceSizeTable.Product.111.rsizetable.zs"))

    def test_central_stylesheet_preserves_both_themes_without_duplicate_label_rule(self):
        try:
            from oot_rando.midnas_devotion.ui.ui_theme import central_stylesheet
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        light_ss = central_stylesheet(plain=True)
        dark_ss = central_stylesheet(plain=False)
        self.assertIn("#f2eee3", light_ss)
        self.assertEqual(light_ss.count("QWidget#backdropCentral .QLabel"), 1)
        self.assertIn("QProgressBar::chunk", dark_ss)
        self.assertIn("QScrollBar::handle:vertical", dark_ss)
        self.assertEqual(dark_ss.count("QWidget#backdropCentral .QLabel"), 1)


    def test_main_window_friendly_step_parser_and_clean_imports(self):
        try:
            from oot_rando.midnas_devotion.ui import main_window
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        self.assertIsNotNone(main_window.__doc__)
        self.assertEqual(
            main_window._friendly_step_from_log("6. Merged RESTBL (Zelda: 3)"),
            "Updating game memory table…",
        )
        self.assertEqual(
            main_window._friendly_step_from_log("Done! LIVE build ready"),
            "All done — your mod setup is ready!",
        )
        self.assertIsNone(main_window._friendly_step_from_log("   + Merged Bgm.bars.zs"))
        self.assertTrue(callable(main_window.open_in_file_manager))


if __name__ == "__main__":
    unittest.main()
