"""Where the application keeps its files.

* From the sources: the project folder (``build/`` holds seeds and app state).
* Frozen (portable ``.exe`` / Linux binary): the folder of the executable
  (``data/`` next to it), so the application never writes elsewhere and needs
  no installation.
"""
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
PACKAGE_DIR = Path(__file__).resolve().parent


def app_dir():
    """Folder of the executable (frozen) or of the project (sources)."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parents[1]


def data_dir():
    """Writable data root: ``<exe>/data`` when frozen, ``<project>/build`` otherwise."""
    return app_dir() / ('data' if FROZEN else 'build')


def state_dir():
    return data_dir() / 'app'


def seeds_dir():
    return data_dir() / 'seeds'


def resource(*parts):
    """Read-only file shipped with the package (works frozen: PyInstaller ``_MEIPASS``)."""
    base = Path(getattr(sys, '_MEIPASS', PACKAGE_DIR.parent)) / 'oot_rando' if FROZEN else PACKAGE_DIR
    return base.joinpath(*parts)


def open_in_file_manager(target, env=None):
    """Open a folder or file in the OS file manager (Windows, Linux, macOS).

    On Linux, strips AppImage / PyInstaller / embedded-Qt environment overrides
    when ``env`` is not explicitly supplied so ``xdg-open`` launches cleanly.
    """
    import os
    import subprocess
    target_str = str(target)
    if sys.platform == "win32":
        os.startfile(target_str)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target_str], env=env)
    else:
        if env is None:
            from oot_rando.native_dialogs import _clean_native_env
            env = _clean_native_env()
        subprocess.Popen(["xdg-open", target_str], env=env)
