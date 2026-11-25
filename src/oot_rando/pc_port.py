"""Native PC ports of the game (Hookshot, its successor Longshot, and any later fork).

They all share one layout: ``<game>/<name>.exe`` next to ``image.bin`` and ``romfs/``, with the
mods in ``<game>/mods`` and the options in ``<game>/<name>_options.ini``. Longshot's launcher
builds (one folder per version, ``Games/Longshot/<version>``) keep the exe in ``<game>/bin/``. Nothing here depends on
the exe's name: a folder holding ``image.bin`` and ``romfs`` is a port, and a running process is
the port when its exe sits in such a folder (or carries one of the known names). Longshot also
has a native Linux build: the same folder, with ``bin/longshot`` (no '.exe').
"""
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


import os
import re

LONGSHOT_CHANNELS = ("stable", "release candidate", "nightly", "pull request")

_CHANNEL_ALIAS_MAP = {
    "stable": "stable",
    "nightly": "nightly",
    "release candidate": "release candidate",
    "release-candidate": "release candidate",
    "release_candidate": "release candidate",
    "releasecandidate": "release candidate",
    "rc": "release candidate",
    "pull request": "pull request",
    "pull requests": "pull request",
    "pull-request": "pull request",
    "pull-requests": "pull request",
    "pull_request": "pull request",
    "pull_requests": "pull request",
    "pullrequest": "pull request",
    "pullrequests": "pull request",
    "pr": "pull request",
    "prs": "pull request",
}

_CHANNEL_LABELS = {
    "stable": "Stable",
    "release candidate": "Release Candidate",
    "nightly": "Nightly",
    "pull request": "Pull Request",
}

_PRE_RANK = {"rc": 4, "beta": 3, "alpha": 2, "pre": 1, "dev": 0}
_SEMVER_RE = re.compile(
    r"^[vV]?(\d+(?:\.\d+)+)(?:[-_.]?(rc|beta|alpha|pre|dev)[-_.]?(\d*))?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?:[-_T]?(\d{2})(\d{2})?)?"
)
_PR_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:pr|pull[-_\s]?request)[-_#\s]?(\d+)",
    re.IGNORECASE,
)


def canonical_channel_name(dirname):
    """Return canonical Longshot channel key (stable / release candidate / nightly) or None."""
    if not dirname:
        return None
    norm = re.sub(r"\s+", " ", str(dirname).strip()).lower()
    return _CHANNEL_ALIAS_MAP.get(norm)


def channel_display_name(channel_key):
    """Human-friendly label for a canonical Longshot channel key."""
    return _CHANNEL_LABELS.get(str(channel_key or "").lower(), str(channel_key or ""))


def _port_mtime(folder):
    """Best-effort modification timestamp for ranking opaque nightly folders."""
    folder = Path(folder)
    candidates = []
    try:
        exe = port_exe(folder)
        if exe is not None:
            candidates.append(exe)
    except OSError:
        pass
    candidates.extend((folder / "image.bin", folder / "romfs", folder))
    for cand in candidates:
        try:
            if cand.exists():
                return cand.stat().st_mtime
        except OSError:
            continue
    return 0.0


def version_sort_key(path):
    """Sort key ranking Longshot version folders: semver > date > PR number > mtime/natural name."""
    folder = Path(path)
    name = folder.name
    mtime = _port_mtime(folder)
    m = _SEMVER_RE.match(name)
    if m:
        nums = tuple(int(p) for p in m.group(1).split("."))
        pre_tag = (m.group(2) or "").lower()
        pre_num = int(m.group(3)) if m.group(3) else 0
        is_release = 1 if not pre_tag else 0
        pre_rank = _PRE_RANK.get(pre_tag, 0) if pre_tag else 99
        return (3, nums, is_release, pre_rank, pre_num, mtime, name.lower())
    dm = _DATE_RE.search(name)
    if dm:
        y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        hh = int(dm.group(4)) if dm.group(4) else 0
        mm = int(dm.group(5)) if dm.group(5) else 0
        return (2, (y, mo, d, hh, mm), 0, 0, 0, mtime, name.lower())
    pm = _PR_RE.search(name)
    if pm:
        return (1, (int(pm.group(1)),), 0, 0, 0, mtime, name.lower())
    return (0, (), 0, 0, 0, mtime, name.lower())


def longshot_layout_root(path):
    """Locate (root_dir, current_channel_key, current_version_dir) from any Longshot path.

    Works even when the saved version folder (e.g. ``stable/v3.1.1/mods``) was deleted
    during a Longshot update, as long as the parent Longshot root still exists.
    """
    if not path:
        return None
    p = Path(os.path.abspath(os.path.expanduser(str(path).strip())))
    chain = [p, *p.parents]
    for idx, cand in enumerate(chain[:5]):
        chan = canonical_channel_name(cand.name)
        if chan is not None:
            root = cand.parent
            if root != cand and root.is_dir():
                ver_dir = chain[idx - 1] if idx > 0 else None
                return (root, chan, ver_dir)
    if p.is_dir():
        try:
            for entry in p.iterdir():
                if entry.is_dir() and canonical_channel_name(entry.name) is not None:
                    return (p, None, None)
        except OSError:
            pass
    return None


def discover_longshot_channels(root_dir, *, require_image_bin=True):
    """Scan a Longshot root for valid installations across stable, release candidate, and nightly."""
    root = Path(root_dir)
    if not root.is_dir():
        return []
    def _is_valid(cand):
        if is_port_folder(cand):
            return True
        if not require_image_bin:
            try:
                return (cand / "romfs").is_dir()
            except OSError:
                return False
        return False
    by_channel = {}
    try:
        entries = sorted(root.iterdir(), key=lambda e: e.name.lower())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir():
            continue
        chan = canonical_channel_name(entry.name)
        if chan is None:
            continue
        valid = []
        if _is_valid(entry):
            valid.append(entry)
        try:
            for sub in entry.iterdir():
                if sub.is_dir() and _is_valid(sub):
                    valid.append(sub)
        except OSError:
            continue
        if not valid:
            continue
        valid.sort(key=version_sort_key)
        newest = valid[-1]
        prev = by_channel.get(chan)
        if prev is None or version_sort_key(newest) > version_sort_key(prev["port_dir"]):
            by_channel[chan] = {
                "channel": chan,
                "label": channel_display_name(chan),
                "channel_dir": entry,
                "version_name": newest.name,
                "port_dir": newest,
                "mods_dir": newest / "mods",
                "all_versions": valid,
            }
    return [by_channel[c] for c in LONGSHOT_CHANNELS if c in by_channel]


def resolve_longshot_update(current_path):
    """Inspect a saved mods/port path for Longshot updates or multi-channel installations.

    Returns a dict with ``status`` in:
    - ``"not_longshot"``: not under a channelized Longshot directory (or no valid builds found)
    - ``"unchanged"``: single valid channel and already pointing at its newest build
    - ``"upgraded"``: single valid channel with a newer/replacement valid build available
    - ``"choose_channel"``: two or more valid channels installed side by side (always prompt user)
    """
    empty = {
        "status": "not_longshot",
        "root": None,
        "current_channel": None,
        "channels": [],
        "recommended": None,
    }
    if not current_path or not str(current_path).strip():
        return empty
    layout = longshot_layout_root(current_path)
    if layout is None:
        return empty
    root, cur_chan, _cur_ver = layout
    channels = discover_longshot_channels(root)
    if not channels:
        return empty
    if len(channels) >= 2:
        rec = next((c for c in channels if c["channel"] == cur_chan), channels[0])
        return {
            "status": "choose_channel",
            "root": root,
            "current_channel": cur_chan,
            "channels": channels,
            "recommended": rec,
        }
    best = channels[0]
    cur_norm = os.path.normcase(os.path.abspath(os.path.expanduser(str(current_path).strip())))
    best_norm = os.path.normcase(os.path.abspath(str(best["mods_dir"])))
    status = "unchanged" if cur_norm == best_norm else "upgraded"
    return {
        "status": status,
        "root": root,
        "current_channel": cur_chan,
        "channels": channels,
        "recommended": best,
    }


def normalize_port_mods_dir(path):
    """Strip trailing slashes and auto-resolve a picked PC port root (image.bin + romfs/) to <root>/mods."""
    raw = str(path or "").strip()
    if not raw:
        return ""
    norm = os.path.normpath(os.path.expanduser(raw))
    p = Path(norm)
    if is_port_folder(p):
        return str(p / "mods")
    return norm


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
