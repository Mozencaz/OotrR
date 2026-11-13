"""Native PC ports of the game (Hookshot, its successor Longshot, and any later fork).

They all share one layout: ``<game>/<name>.exe`` next to ``image.bin`` and ``romfs/``, with the
mods in ``<game>/mods`` and the options in ``<game>/<name>_options.ini``. Nothing here depends on
the exe's name: a folder holding ``image.bin`` and ``romfs`` is a port, and a running process is
the port when its exe sits in such a folder (or carries one of the known names).
"""
from pathlib import Path

KNOWN_EXES = ('hookshot.exe', 'longshot.exe')
DEFAULT_OPTIONS = 'hookshot_options.ini'


def is_port_folder(folder):
    """True when ``folder`` holds a built port: ``image.bin`` and ``romfs/``."""
    if not folder:
        return False
    folder = Path(folder)
    try:
        return (folder / 'image.bin').is_file() and (folder / 'romfs').is_dir()
    except OSError:
        return False


def port_exe(folder):
    """The game exe of a port folder: a known name first, else the only/first other ``*.exe``."""
    folder = Path(folder)
    for name in KNOWN_EXES:
        if (folder / name).is_file():
            return folder / name
    try:
        exes = sorted(p for p in folder.glob('*.exe') if p.is_file())
    except OSError:
        return None
    return exes[0] if exes else None


def is_port_process(image_path):
    """True when a process image (full path, or bare name) is a port's game exe."""
    if not image_path:
        return False
    path = Path(image_path)
    if path.suffix.lower() != '.exe':
        return False
    if path.name.lower() in KNOWN_EXES:
        return True
    return path.parent != Path('.') and is_port_folder(path.parent)


def options_ini(folder):
    """The port's options ini: ``<exe stem>_options.ini``, else any ``*_options.ini``, else Hookshot's."""
    folder = Path(folder)
    exe = port_exe(folder) if folder.is_dir() else None
    own = folder / (exe.stem.lower() + '_options.ini') if exe else folder / DEFAULT_OPTIONS
    if own.exists():
        return own
    try:
        found = sorted(folder.glob('*_options.ini'))
    except OSError:
        found = []
    return found[0] if found else own
