import os
import tempfile
import unittest
from unittest import mock

from oot_rando import native_dialogs


class NativeDialogsTests(unittest.TestCase):
    def test_normalize_filters_tk_and_qt(self):
        tk_specs = native_dialogs.normalize_filters(
            filetypes=[("Archipelago YAML", "*.yaml *.yml"), ("JSON", "*.json")]
        )
        self.assertEqual(
            tk_specs,
            [("Archipelago YAML", ["*.yaml", "*.yml"]), ("JSON", ["*.json"])],
        )

        qt_specs = native_dialogs.normalize_filters(
            qt_filter="Mod Archives (*.zip *.7z *.rar);;ZIP (*.zip)"
        )
        self.assertEqual(
            qt_specs,
            [("Mod Archives", ["*.zip", "*.7z", "*.rar"]), ("ZIP", ["*.zip"])],
        )

    def test_clean_native_env_strips_appimage_paths(self):
        fake_env = {
            "APPDIR": "/tmp/.mount_OoTRan123456",
            "LD_LIBRARY_PATH": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/lib", "/usr/lib"]),
            "XDG_DATA_DIRS": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/share", "/usr/share"]),
            "PATH": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/bin", "/usr/bin", "/bin"]),
            "QT_PLUGIN_PATH": "/tmp/.mount_OoTRan123456/usr/plugins",
        }
        with mock.patch.dict(os.environ, fake_env, clear=True):
            cleaned = native_dialogs._clean_native_env()
            self.assertEqual(cleaned["LD_LIBRARY_PATH"], "/usr/lib")
            self.assertEqual(cleaned["XDG_DATA_DIRS"], "/usr/share")
            self.assertEqual(cleaned["PATH"], os.pathsep.join(["/usr/bin", "/bin"]))
            self.assertNotIn("QT_PLUGIN_PATH", cleaned)

    def test_kdialog_directory_and_cancel(self):
        fake_ok = mock.Mock(returncode=0, stdout="/tmp/my_mods\n")
        fake_cancel = mock.Mock(returncode=1, stdout="")
        with (
            mock.patch.object(native_dialogs, "_linux_backends", return_value=[("kdialog", "/usr/bin/kdialog")]),
            mock.patch("subprocess.run", side_effect=[fake_ok, fake_cancel]) as run_mock,
        ):
            self.assertEqual(native_dialogs.ask_directory("Pick Mods", "/tmp"), "/tmp/my_mods")
            self.assertEqual(native_dialogs.ask_directory("Pick Mods", "/tmp"), "")
            cmd0 = run_mock.call_args_list[0].args[0]
            self.assertEqual(cmd0[:4], ["/usr/bin/kdialog", "--title", "Pick Mods", "--getexistingdirectory"])

    def test_kdialog_save_appends_default_extension(self):
        fake_ok = mock.Mock(returncode=0, stdout="/tmp/my_settings\n")
        with (
            mock.patch.object(native_dialogs, "_linux_backends", return_value=[("kdialog", "/usr/bin/kdialog")]),
            mock.patch("subprocess.run", return_value=fake_ok),
        ):
            res = native_dialogs.ask_save_file(
                "Export",
                initialdir="/tmp",
                initialfile="out.json",
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
            )
            self.assertEqual(res, "/tmp/my_settings.json")


class MissingFoldersHelperTests(unittest.TestCase):
    def test_find_and_create_missing_folders(self):
        try:
            from oot_rando.midnas_devotion.ui.settings_dialog import (
                create_missing_folders_in_dir,
                find_missing_creatable_folders,
            )
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable in test environment: {exc}")

        with tempfile.TemporaryDirectory() as td:
            existing_mods = os.path.join(td, "mods")
            os.makedirs(existing_mods)
            existing_ws = os.path.join(td, "ws")
            os.makedirs(existing_ws)

            paths = {
                "live_mods_dir": existing_mods,
                "backup_dir": os.path.join(td, "nonexistent_backup"),
                "uninstalled_seeds_dir": "",
                "workspace_dir": existing_ws,
            }
            missing = find_missing_creatable_folders(paths)
            self.assertEqual([m[0] for m in missing], ["backup_dir", "uninstalled_seeds_dir"])

            chosen_root = os.path.join(td, "user_dir")
            created = create_missing_folders_in_dir(missing, chosen_root)
            self.assertEqual(created["backup_dir"], os.path.join(chosen_root, "UserModLibrary"))
            self.assertEqual(created["uninstalled_seeds_dir"], os.path.join(chosen_root, "ArchivedSeeds"))
            self.assertTrue(os.path.isdir(created["backup_dir"]))
            self.assertTrue(os.path.isdir(created["uninstalled_seeds_dir"]))

            # Single missing folder selected with matching basename should not double-nest
            single = [("uninstalled_seeds_dir", "Extra Seeds Folder", "seeds-uninstalled", "")]
            exact_dir = os.path.join(td, "seeds-uninstalled")
            created_exact = create_missing_folders_in_dir(single, exact_dir)
            self.assertEqual(created_exact["uninstalled_seeds_dir"], exact_dir)
            self.assertTrue(os.path.isdir(exact_dir))


if __name__ == "__main__":
    unittest.main()
