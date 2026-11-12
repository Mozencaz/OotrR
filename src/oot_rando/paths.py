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
