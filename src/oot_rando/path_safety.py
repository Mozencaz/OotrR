from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

MAX_COMPONENT_BYTES = 255
MAX_MOD_FOLDER_LEN = 64
WIN_MAX_PATH = 259
POSIX_MAX_PATH_BYTES = 4096

# Headroom budgets for files created underneath user-chosen live game directories:
# e.g. OoT_Randomizer_<16>/romfs/System/Resource/ResourceSizeTable.product.110.rsizetable.zs
SEED_ROMFS_HEADROOM = 98
SAVE_ACCOUNT_HEADROOM = 48
ARCHIVE_HEADROOM = 104
MOD_ROMFS_HEADROOM = 98

WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})
WINDOWS_FORBIDDEN_CHARS = frozenset("<>:|?*" + chr(34) + chr(0))

_WIN_LONG_PATHS_CACHE = {}   # 'enabled': the registry policy, read once


def windows_long_paths_enabled(*, _override=None) -> bool:
    "Return True on POSIX or when Windows LongPathsEnabled registry policy is active."
    if _override is not None:
        return bool(_override)
    if os.name != "nt":
        return True
    if 'enabled' in _WIN_LONG_PATHS_CACHE:
        return _WIN_LONG_PATHS_CACHE['enabled']
    enabled = False
    try:
        import winreg
        sep = chr(92)
        reg_path = sep.join(("SYSTEM", "CurrentControlSet", "Control", "FileSystem"))
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            val, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            enabled = bool(int(val) == 1)
    except Exception:
        enabled = False
    _WIN_LONG_PATHS_CACHE['enabled'] = enabled
    return enabled


def fs_path(path) -> str:
    "Return an OS path string, adding extended-length prefix on Windows for deep internal paths."
    raw = os.fspath(path)
    if os.name != "nt":
        return raw
    bs = chr(92)
    ext_prefix = bs + bs + "?" + bs
    if raw.startswith(ext_prefix):
        return raw
    abs_p = os.path.abspath(raw)
    if len(abs_p) < 240:
        return raw
    if abs_p.startswith(bs + bs):
        return ext_prefix + "UNC" + bs + abs_p[2:]
    return ext_prefix + abs_p


def validate_component_name(
    name: str,
    *,
    label: str = "Name",
    max_chars: int = 255,
    max_bytes: int = MAX_COMPONENT_BYTES,
    portable: bool = False,
) -> str:
    "Validate a single file or directory name across Windows, Linux, and macOS."
    if not isinstance(name, str) or not name or name in (".", ".."):
        raise ValueError(f"{label} cannot be empty.")
    sep_chars = ("/", chr(92))
    if any(sep in name for sep in sep_chars) or any(ord(c) < 32 for c in name):
        raise ValueError(f"{label} contains invalid path or control characters: {name!r}")
    encoded_len = len(name.encode("utf-8"))
    if len(name) > max_chars or encoded_len > max_bytes:
        preview = name[:40] + "…" if len(name) > 40 else name
        raise ValueError(
            f"{label} is too long ({encoded_len} UTF-8 bytes / {len(name)} characters; "
            f"maximum is {max_bytes} bytes and {max_chars} characters): {preview}"
        )
    if portable or os.name == "nt":
        if any(c in WINDOWS_FORBIDDEN_CHARS for c in name):
            raise ValueError(f"{label} contains characters not allowed on Windows (<>:|?* or quotes): {name!r}")
        if name[-1] in (" ", "."):
            raise ValueError(f"{label} cannot end with a space or period: {name!r}")
        stem = name.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"{label} uses a reserved Windows device name ({stem}). Choose a different name.")
    return name


def sanitize_portable_name(
    raw_name: str,
    *,
    default: str = "Imported_Mod",
    max_len: int = MAX_MOD_FOLDER_LEN,
) -> str:
    "Convert an arbitrary mod/preset string into a safe, bounded cross-platform folder name."
    ws = "[ " + chr(9) + chr(10) + chr(13) + "]+"
    s = re.sub(ws + "[-–—]" + ws, "_", (raw_name or "").strip())
    s = re.sub("[^A-Za-z0-9._-]+", "_", s)
    s = re.sub("_+", "_", s).strip("_.- ")
    if not s:
        s = default
    stem = s.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        s = "Mod_" + s
    if len(s) > max_len or len(s.encode("utf-8")) > max_len:
        digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
        keep = max(4, max_len - 9)
        prefix = s[:keep].rstrip("_.- ") or "Mod"
        s = f"{prefix}_{digest}"
    return s


def _iter_non_anchor_parts(path_obj: Path):
    anchor = path_obj.anchor
    for idx, part in enumerate(path_obj.parts):
        if idx == 0 and anchor and part == anchor:
            continue
        if part in ("/", chr(92)):
            continue
        yield part


def validate_path_headroom(
    base_path,
    *,
    max_relative_len: int = SEED_ROMFS_HEADROOM,
    label: str = "Folder",
    enforce_win_classic: bool = True,
    _win_long_paths_override=None,
    _simulate_win32: bool = False,
) -> Path:
    "Ensure base_path + generated relative paths fit OS component and total path limits."
    raw_str = os.path.expanduser(str(base_path))
    abs_str = os.path.abspath(raw_str)
    p = Path(abs_str)
    is_win = (os.name == "nt") or bool(_simulate_win32)
    for part in _iter_non_anchor_parts(p):
        validate_component_name(part, label=f"{label} path segment", portable=is_win)

    enc_len = len(abs_str.encode("utf-8"))
    utf8_total = enc_len + 1 + max(0, int(max_relative_len))
    if utf8_total > POSIX_MAX_PATH_BYTES:
        raise ValueError(
            f"{label} path is too deep ({enc_len} bytes). Move the folder closer to the drive root."
        )

    if is_win and enforce_win_classic and not windows_long_paths_enabled(_override=_win_long_paths_override):
        char_total = len(abs_str) + 1 + max(0, int(max_relative_len))
        if char_total > WIN_MAX_PATH:
            max_base = max(1, WIN_MAX_PATH - 1 - max(0, int(max_relative_len)))
            example_path = "C:" + chr(92) + "Games" + chr(92) + "Longshot"
            raise ValueError(
                f"{label} path is too long ({len(abs_str)} characters; maximum safe folder length is "
                f"{max_base} characters so game files inside it stay under the 260-character Windows limit): "
                f"{abs_str}. Move it to a shorter path (such as {example_path}) or enable Windows Long Paths."
            )
    return p


def validate_file_path(
    file_path,
    *,
    label: str = "File path",
    enforce_win_classic: bool = False,
    _win_long_paths_override=None,
    _simulate_win32: bool = False,
) -> Path:
    "Ensure an individual file path respects OS component (255-byte) and path limits."
    abs_str = os.path.abspath(os.path.expanduser(str(file_path)))
    p = Path(abs_str)
    is_win = (os.name == "nt") or bool(_simulate_win32)
    for part in _iter_non_anchor_parts(p):
        validate_component_name(part, label=label, portable=is_win)
    if len(abs_str.encode("utf-8")) > POSIX_MAX_PATH_BYTES:
        raise ValueError(f"{label} exceeds the maximum operating system path length: {abs_str[:80]}…")
    if is_win and enforce_win_classic and not windows_long_paths_enabled(_override=_win_long_paths_override):
        if len(abs_str) > WIN_MAX_PATH:
            raise ValueError(
                f"{label} exceeds the 260-character Windows path limit ({len(abs_str)} characters): {abs_str}"
            )
    return p


def safe_archive_target(archive_dir: Path, base_name: str, suffix: str = "") -> Path:
    "Return a non-existing archive target path whose filename stays within 255 UTF-8 bytes."
    archive_dir = Path(archive_dir)

    def _fit_component(stem: str, tail: str) -> str:
        cand = stem + tail
        if len(cand.encode("utf-8")) <= MAX_COMPONENT_BYTES and len(cand) <= 120:
            return cand
        digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]
        budget = max(8, 120 - len(tail) - 9)
        trimmed = stem[:budget].rstrip("_.- ") or "Seed"
        return f"{trimmed}_{digest}{tail}"

    first_name = _fit_component(base_name, suffix)
    target = archive_dir / first_name
    index = 1
    while target.exists():
        index += 1
        target = archive_dir / _fit_component(base_name, f"{suffix}-{index}")
    return target
