"""Native PC ports of the game (Hookshot, its successor Longshot, and any later fork).

They all share one layout: ``<game>/<name>.exe`` next to ``image.bin`` and ``romfs/``, with the
mods in ``<game>/mods`` and the options in ``<game>/<name>_options.ini``. Longshot's launcher
builds (one folder per version, ``Games/Longshot/<version>``) keep the exe in ``<game>/bin/``. Nothing here depends on
the exe's name: a folder holding ``image.bin`` and ``romfs`` is a port, and a running process is
the port when its exe sits in such a folder (or carries one of the known names). Longshot also
has a native Linux build: the same folder, with ``bin/longshot`` (no '.exe').
"""
import os
import re
from pathlib import Path

KNOWN_EXES = ('hookshot.exe', 'longshot.exe', 'impshot.exe')
KNOWN_NAMES = tuple(Path(exe).stem for exe in KNOWN_EXES)   # native Linux builds: no '.exe'
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


EXE_FOLDERS = ('.', 'bin')   # where a port keeps its exe, relative to the game folder


def port_exe(folder):
    """The game exe of a port folder (or its ``bin/``): a known name first (Windows, then native
    Linux), else the first other ``*.exe``."""
    folder = Path(folder)
    places = [folder / sub for sub in EXE_FOLDERS]
    for place in places:
        for name in KNOWN_EXES + KNOWN_NAMES:
            if (place / name).is_file():
                return place / name
    for place in places:
        try:
            exes = sorted(p for p in place.glob('*.exe') if p.is_file())
        except OSError:
            continue
        if exes:
            return exes[0]
    return None


def game_folder(image_path):
    """The port folder of a running exe: its own folder, or the one above ``bin/``; else None."""
    if not image_path:
        return None
    parent = Path(image_path).parent
    for folder in (parent, parent.parent if parent.name.lower() == 'bin' else None):
        if folder is not None and folder != Path('.') and is_port_folder(folder):
            return folder
    return None


def is_port_process(image_path):
    """True when a process image (full path, or bare name) is a port's game exe: a Windows
    ``.exe``, or a native Linux executable (no suffix)."""
    if not image_path:
        return False
    path = Path(image_path)
    if path.suffix.lower() not in ('.exe', ''):
        return False
    if path.name.lower() in KNOWN_EXES + KNOWN_NAMES:
        return True
    return path.parent != Path('.') and game_folder(path) is not None


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


# Longshot's launcher keeps one folder per release channel, each with one folder per build:
# ``<root>/<channel>/<version>`` (the port itself: image.bin, romfs/, mods/). An update installs
# a new version folder and may delete the old one, which leaves saved mods paths pointing nowhere.
LONGSHOT_CHANNELS = ('stable', 'release candidate', 'nightly', 'pull request')

_CHANNEL_ALIASES = {
    'stable': 'stable',
    'nightly': 'nightly',
    'release candidate': 'release candidate',
    'release-candidate': 'release candidate',
    'release_candidate': 'release candidate',
    'releasecandidate': 'release candidate',
    'rc': 'release candidate',
    'pull request': 'pull request',
    'pull requests': 'pull request',
    'pull-request': 'pull request',
    'pull-requests': 'pull request',
    'pull_request': 'pull request',
    'pull_requests': 'pull request',
    'pullrequest': 'pull request',
    'pullrequests': 'pull request',
    'pr': 'pull request',
    'prs': 'pull request',
}

_CHANNEL_LABELS = {
    'stable': 'Stable',
    'release candidate': 'Release Candidate',
    'nightly': 'Nightly',
    'pull request': 'Pull Request',
}

_PRE_RANK = {'rc': 4, 'beta': 3, 'alpha': 2, 'pre': 1, 'dev': 0}
_SEMVER_RE = re.compile(r'^[vV]?(\d+(?:\.\d+)+)(?:[-_.]?(rc|beta|alpha|pre|dev)[-_.]?(\d*))?', re.IGNORECASE)
_DATE_RE = re.compile(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?:[-_T]?(\d{2})(\d{2})?)?')
_PR_RE = re.compile(r'(?:^|[^a-z0-9])(?:pr|pull[-_\s]?request)[-_#\s]?(\d+)', re.IGNORECASE)


def canonical_channel_name(dirname):
    """The Longshot channel key (stable / release candidate / nightly / pull request) of a folder name, else None."""
    if not dirname:
        return None
    return _CHANNEL_ALIASES.get(re.sub(r'\s+', ' ', str(dirname).strip()).lower())


def channel_display_name(channel_key):
    """Human-friendly label for a Longshot channel key."""
    return _CHANNEL_LABELS.get(str(channel_key or '').lower(), str(channel_key or ''))


def is_port_mods_dir(path):
    """True when ``path`` is the ``mods`` folder of a built port."""
    path = Path(path)
    return path.name.lower() == 'mods' and is_port_folder(path.parent)


def _port_mtime(folder):
    """Modification time used to rank version folders whose names carry no version."""
    folder = Path(folder)
    candidates = []
    exe = port_exe(folder)
    if exe is not None:
        candidates.append(exe)
    candidates.extend((folder / 'image.bin', folder / 'romfs', folder))
    for candidate in candidates:
        try:
            return candidate.stat().st_mtime
        except OSError:
            continue
    return 0.0


def version_sort_key(path):
    """Sort key of a Longshot version folder: semver names, then dated names, then pull request
    numbers, then the rest."""
    folder = Path(path)
    name = folder.name
    mtime = _port_mtime(folder)
    semver = _SEMVER_RE.match(name)
    if semver:
        numbers = tuple(int(part) for part in semver.group(1).split('.'))
        pre_tag = (semver.group(2) or '').lower()
        pre_number = int(semver.group(3)) if semver.group(3) else 0
        is_release = 0 if pre_tag else 1
        pre_rank = _PRE_RANK.get(pre_tag, 0) if pre_tag else 99
        return (3, numbers, is_release, pre_rank, pre_number, mtime, name.lower())
    date = _DATE_RE.search(name)
    if date:
        stamp = tuple(int(group) if group else 0 for group in date.groups())
        return (2, stamp, 0, 0, 0, mtime, name.lower())
    pull = _PR_RE.search(name)
    if pull:
        return (1, (int(pull.group(1)),), 0, 0, 0, mtime, name.lower())
    return (0, (), 0, 0, 0, mtime, name.lower())


def longshot_layout_root(path):
    """``(root, channel, version_dir)`` of any path inside a Longshot launcher tree, else None.

    Works when the saved version folder (``stable/v3.1.1/mods``) was deleted by an update, as
    long as the Longshot root still exists. ``channel`` and ``version_dir`` are None when
    ``path`` is the root itself.
    """
    if not path or not str(path).strip():
        return None
    path = Path(os.path.abspath(os.path.expanduser(str(path).strip())))
    chain = [path, *path.parents]
    for index, candidate in enumerate(chain[:5]):
        channel = canonical_channel_name(candidate.name)
        if channel is not None:
            root = candidate.parent
            if root != candidate and root.is_dir():
                return (root, channel, chain[index - 1] if index > 0 else None)
    if path.is_dir():
        try:
            if any(entry.is_dir() and canonical_channel_name(entry.name) for entry in path.iterdir()):
                return (path, None, None)
        except OSError:
            pass
    return None


def discover_longshot_channels(root_dir, *, require_image_bin=True):
    """The newest built port of each channel under a Longshot root, in LONGSHOT_CHANNELS order.
    With ``require_image_bin`` False, a folder with only ``romfs/`` counts as a build."""
    root = Path(root_dir)

    def is_build(folder):
        if is_port_folder(folder):
            return True
        if require_image_bin:
            return False
        try:
            return (folder / 'romfs').is_dir()
        except OSError:
            return False

    try:
        entries = sorted((entry for entry in root.iterdir() if entry.is_dir()), key=lambda e: e.name.lower())
    except OSError:
        return []
    by_channel = {}
    for entry in entries:
        channel = canonical_channel_name(entry.name)
        if channel is None:
            continue
        builds = [entry] if is_build(entry) else []
        try:
            builds.extend(sub for sub in entry.iterdir() if sub.is_dir() and is_build(sub))
        except OSError:
            continue
        if not builds:
            continue
        builds.sort(key=version_sort_key)
        newest = builds[-1]
        previous = by_channel.get(channel)
        if previous is None or version_sort_key(newest) > version_sort_key(previous['port_dir']):
            by_channel[channel] = {
                'channel': channel,
                'label': channel_display_name(channel),
                'channel_dir': entry,
                'version_name': newest.name,
                'port_dir': newest,
                'mods_dir': newest / 'mods',
                'all_versions': builds,
            }
    return [by_channel[channel] for channel in LONGSHOT_CHANNELS if channel in by_channel]


def resolve_longshot_update(current_path):
    """Where a saved mods (or Longshot) path should point now. Returns a dict whose ``status`` is:

    - ``'not_longshot'``: not inside a Longshot launcher tree, or no built port found there;
    - ``'unchanged'``: the path is still the mods folder of a built port, whatever newer builds
      or other channels exist (the player chose it: it is never replaced behind their back);
    - ``'upgraded'``: the path is gone or not a mods folder, and one channel is installed:
      ``recommended`` is its newest build;
    - ``'choose_channel'``: the path is gone or not a mods folder, and several channels are
      installed: the player must choose (``recommended`` is the current channel's build).
    """
    result = {'status': 'not_longshot', 'root': None, 'current_channel': None, 'channels': [], 'recommended': None}
    layout = longshot_layout_root(current_path)
    if layout is None:
        return result
    root, channel, _version = layout
    channels = discover_longshot_channels(root)
    if not channels:
        return result
    result.update(root=root, current_channel=channel, channels=channels)
    current = Path(os.path.abspath(os.path.expanduser(str(current_path).strip())))
    if is_port_mods_dir(current):
        result['status'] = 'unchanged'
    elif len(channels) >= 2:
        result.update(status='choose_channel',
                      recommended=next((c for c in channels if c['channel'] == channel), channels[0]))
    else:
        result.update(status='upgraded', recommended=channels[0])
    return result


def normalize_port_mods_dir(path):
    """A picked folder, cleaned; a picked port folder (image.bin + romfs/) becomes its ``mods``."""
    raw = str(path or '').strip()
    if not raw:
        return ''
    folder = Path(os.path.normpath(os.path.expanduser(raw)))
    return str(folder / 'mods') if is_port_folder(folder) else str(folder)


def resolve_stale_port_subpath(stale_path, old_mods, new_mods):
    """Relocate a missing path (such as save_path) from an old port folder to the new port folder."""
    raw = str(stale_path or "").strip()
    if not raw or not new_mods:
        return None
    p = Path(raw)
    if p.exists():
        return p
    new_port = Path(new_mods).parent if Path(new_mods).name.lower() == "mods" else Path(new_mods)
    if old_mods:
        old_port = Path(old_mods).parent if Path(old_mods).name.lower() == "mods" else Path(old_mods)
        try:
            rel = p.relative_to(old_port)
            cand = new_port / rel
            if cand.exists():
                return cand
        except ValueError:
            pass
    # Also relocate portable emulator load/<title> or nand/user/save paths if the emulator moved.
    for anc in (Path(new_mods), *Path(new_mods).parents):
        if anc.name.lower() == "load" and (anc.parent / "nand").is_dir():
            emu_user = anc.parent
            for marker in ("load", "nand"):
                parts_low = [x.lower() for x in p.parts]
                if marker in parts_low:
                    idx = parts_low.index(marker)
                    rel_emu = Path(*p.parts[idx:])
                    cand = emu_user / rel_emu
                    if cand.exists():
                        return cand
    return None


def resolve_stale_nup_path(nup_path, new_mods, longshot_root=None):
    """Locate a moved .nup game file under a new port folder or Longshot root when stale."""
    raw = str(nup_path or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    search_dirs = []
    if new_mods:
        nm = Path(new_mods)
        port_dir = nm.parent if nm.name.lower() == "mods" else nm
        search_dirs.extend([port_dir, port_dir.parent])
    if longshot_root:
        search_dirs.append(Path(longshot_root))
    target_name = p.name.casefold()
    seen = set()
    fallback_nups = []
    for d in search_dirs:
        if not d or not d.is_dir():
            continue
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            for entry in d.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".nup":
                    if entry.name.casefold() == target_name:
                        return entry
                    fallback_nups.append(entry)
        except OSError:
            continue
    if len(fallback_nups) == 1:
        return fallback_nups[0]
    return None
