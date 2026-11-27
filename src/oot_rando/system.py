"""The emulators the application recognises among the running processes (for the game
closed checks and the live tracker). ``tracker/live_memory.py`` reads their memory.
"""
from pathlib import PureWindowsPath


EMULATOR_EXES = {'lichii.exe', 'ryuchii.exe', 'eden.exe', 'yuzu.exe', 'suyu.exe', 'citron.exe', 'sudachi.exe'}


EXTRA_EMULATORS_KEY = 'extra_emulators'   # gui_state.json: executables the player added (Setup page)


def parse_exe_names(text):
    """Executable names from a free list (commas, semicolons or lines): lower case, '.exe' added."""
    names = set()
    for part in text.replace(';', ',').replace('\n', ',').split(','):
        name = PureWindowsPath(part.strip().strip('"')).name.lower()
        if name:
            names.add(name if name.endswith('.exe') else name + '.exe')
    return names


_extra_emulators = None   # set by the application; None: read once from its saved state


def set_extra_emulators(text):
    """Executables the player listed (Setup page), used by the next process scan."""
    global _extra_emulators  # noqa: PLW0603  (one process-wide setting, written by the GUI)
    _extra_emulators = parse_exe_names(text or '')


def emulator_exes():
    """Known yuzu-family executables plus the ones the player listed in the application."""
    if _extra_emulators is None:
        import json
        from oot_rando.paths import state_dir
        try:
            extra = json.loads((state_dir() / 'gui_state.json').read_text(encoding='utf-8')).get(EXTRA_EMULATORS_KEY)
        except (OSError, ValueError, AttributeError):
            extra = ''
        set_extra_emulators(extra if isinstance(extra, str) else '')
    return EMULATOR_EXES | _extra_emulators


def plain_name(name):
    """Executable name without folder and '.exe', lower case: 'ryuchii.exe' matches the Linux 'ryuchii'."""
    name = PureWindowsPath(str(name).strip().strip('"')).name.lower()
    return name[:-4] if name.endswith('.exe') else name
