import _src_path  # noqa: F401
import os
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

    def testclean_native_env_strips_appimage_paths(self):
        fake_env = {
            "APPDIR": "/tmp/.mount_OoTRan123456",
            "LD_LIBRARY_PATH": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/lib", "/usr/lib"]),
            "XDG_DATA_DIRS": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/share", "/usr/share"]),
            "PATH": os.pathsep.join(["/tmp/.mount_OoTRan123456/usr/bin", "/usr/bin", "/bin"]),
            "QT_PLUGIN_PATH": "/tmp/.mount_OoTRan123456/usr/plugins",
            "QT_QPA_PLATFORM": "xcb",
            "QT_ENABLE_HIGHDPI_SCALING": "0",
        }
        with mock.patch.dict(os.environ, fake_env, clear=True):
            cleaned = native_dialogs.clean_native_env()
            self.assertEqual(cleaned["LD_LIBRARY_PATH"], "/usr/lib")
            self.assertEqual(cleaned["XDG_DATA_DIRS"], "/usr/share")
            self.assertEqual(cleaned["PATH"], os.pathsep.join(["/usr/bin", "/bin"]))
            self.assertNotIn("QT_PLUGIN_PATH", cleaned)
            self.assertNotIn("QT_QPA_PLATFORM", cleaned)
            self.assertNotIn("QT_ENABLE_HIGHDPI_SCALING", cleaned)

    def test_kdialog_directory_and_cancel(self):
        fake_ok = mock.Mock(returncode=0, stdout="/tmp/my_mods\n")
        fake_trailing = mock.Mock(returncode=0, stdout="/tmp/my_mods/\n")
        fake_cancel = mock.Mock(returncode=1, stdout="")
        with (
            mock.patch.object(native_dialogs, "_linux_backends", return_value=[("kdialog", "/usr/bin/kdialog")]),
            mock.patch("subprocess.run", side_effect=[fake_ok, fake_trailing, fake_cancel]) as run_mock,
        ):
            self.assertEqual(native_dialogs.ask_directory("Pick Mods", "/tmp"), "/tmp/my_mods")
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


class FileManagerHelperTests(unittest.TestCase):
    def test_open_in_file_manager_linux_uses_clean_env(self):
        with (
            mock.patch.object(native_dialogs.sys, "platform", "linux"),
            mock.patch.object(native_dialogs, "clean_native_env", return_value={"PATH": "/usr/bin"}) as clean_mock,
            mock.patch("subprocess.Popen") as popen_mock,
        ):
            native_dialogs.open_in_file_manager("/tmp/example")
            clean_mock.assert_called_once()
            popen_mock.assert_called_once_with(["xdg-open", "/tmp/example"], env={"PATH": "/usr/bin"})

    def test_randomizer_gui_exports_open_in_file_manager_and_docstring(self):
        from oot_rando.gui import randomizer_gui

        self.assertTrue(callable(randomizer_gui.open_in_file_manager))
        self.assertIsNotNone(randomizer_gui.__doc__)


if __name__ == "__main__":
    unittest.main()
