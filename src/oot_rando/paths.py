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


def error_log():
    """Last unexpected error with its traceback, for bug reports (``data/last-error.log``)."""
    return data_dir() / 'last-error.log'


def write_error_log(trace):
    """Record ``trace`` (``traceback.format_exc()``) in :func:`error_log`; never raises."""
    try:
        from datetime import datetime
        from oot_rando import __version__
        path = error_log()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec='seconds')
        path.write_text(f'{stamp} - version {__version__}\n\n{trace}', encoding='utf-8')
    except Exception:
        pass
