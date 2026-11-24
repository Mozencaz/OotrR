"""Configuration, path discovery, migration, and mod-overlap classification for Midna's Devotion."""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from oot_rando.midnas_devotion.core.formats import BARS_EXTS, CodecBundle, analyze_bars_compatibility, read_bars_raw

_LOG = logging.getLogger(__name__)

RSTB_REL = os.path.join(
    "romfs", "System", "Resource",
    "ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs",
)

MANAGED_MOD_NAMES = {
    "Merged_Zelda_Rando",
}

UI_MERGE_EXTS = (".blarc.zs", ".blarc", ".bntx.zs", ".bntx")


def _norm_path_key(path: str) -> str:
    """Normalize a filesystem path for cross-platform equality checks (case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def _is_within_dir(parent_dir: str, child_path: str) -> bool:
    """Return True when ``child_path`` resides inside ``parent_dir`` (safe across Windows drive letters)."""
    parent_key = _norm_path_key(parent_dir)
    child_key = _norm_path_key(child_path)
    try:
        return os.path.commonpath([parent_key, child_key]) == parent_key
    except ValueError:
        return False


def _version_sort_key(path: str) -> Tuple[Tuple[int, ...], str]:
    """Natural numeric sort key for ``vX.Y.Z`` release folders so ``v0.10`` sorts after ``v0.9``."""
    base = os.path.basename(path)
    nums = tuple(int(tok) for tok in re.findall(r"\d+", base))
    return (nums, base.lower())


def sanitize_folder_name(raw_name: str) -> str:
    """Convert an arbitrary mod name into a safe single-segment directory name."""
    s = re.sub(r"\s+[-–—]\s+", "_", raw_name.strip())
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_.-")
    return s


def clean_subprocess_env() -> Dict[str, str]:
    """Return a sanitized environment safe for spawning external system executables.

    Delegates to ``oot_rando.native_dialogs._clean_native_env()`` so PyInstaller,
    AppImage, and embedded-Qt overrides (``LD_LIBRARY_PATH``, ``QT_QPA_PLATFORM``,
    ``QT_ENABLE_HIGHDPI_SCALING``, etc.) never leak into ``longshot``, ``xdg-open``,
    ``7z``, ``unrar``, or ``bsdtar``.
    """
    try:
        from oot_rando.native_dialogs import _clean_native_env
        return _clean_native_env()
    except Exception:
        env = os.environ.copy()
        orig_ld = env.get("LD_LIBRARY_PATH_ORIG")
        if orig_ld is not None:
            env["LD_LIBRARY_PATH"] = orig_ld
        elif getattr(sys, "frozen", False):
            env.pop("LD_LIBRARY_PATH", None)
        for var in (
            "QT_QPA_PLATFORM",
            "QT_ENABLE_HIGHDPI_SCALING",
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QML_IMPORT_PATH",
            "PYTHONHOME",
            "PYTHONPATH",
        ):
            env.pop(var, None)
        return env


_STARTUP_MIGRATION_NOTICES: List[str] = []


def _try_migrate_dir(old_path: str, new_path: str, label: str) -> str:
    """Rename a legacy directory to its new name if safe; return the active path."""
    old_abs = os.path.abspath(os.path.expanduser(old_path))
    new_abs = os.path.abspath(os.path.expanduser(new_path))
    if os.path.normcase(old_abs) == os.path.normcase(new_abs):
        return new_abs
    if os.path.isdir(new_abs):
        return new_abs
    if os.path.isdir(old_abs):
        try:
            os.makedirs(os.path.dirname(new_abs), exist_ok=True)
            shutil.move(old_abs, new_abs)
            msg = f"{label}: {old_abs}  →  {new_abs}"
            if msg not in _STARTUP_MIGRATION_NOTICES:
                _STARTUP_MIGRATION_NOTICES.append(msg)
            return new_abs
        except Exception:
            return old_abs
    return new_abs


def default_config_dir() -> str:
    """Return the OS-appropriate config directory, migrating legacy ``ootmodman`` folders if found."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        new_dir = os.path.join(base, "midnas_devotion")
        for legacy in (
            os.path.join(base, "ootmodman"),
            os.path.join(os.path.expanduser("~"), ".config", "ootmodman"),
        ):
            if os.path.isdir(legacy) and not os.path.isdir(new_dir):
                return _try_migrate_dir(legacy, new_dir, "Settings Folder")
        return new_dir
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    new_dir = os.path.join(xdg, "midnas_devotion")
    legacy = os.path.join(xdg, "ootmodman")
    return _try_migrate_dir(legacy, new_dir, "Settings Folder")


def default_workspace_dir() -> str:
    """Return the OS-appropriate workspace directory for sandbox/staged/disabled mod folders."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        new_dir = os.path.join(base, "midnas_devotion")
        for legacy in (
            os.path.join(base, "ootmodman"),
            os.path.join(os.path.expanduser("~"), ".local", "share", "ootmodman"),
        ):
            if os.path.isdir(legacy) and not os.path.isdir(new_dir):
                return _try_migrate_dir(legacy, new_dir, "Midna's Devotion Workspace")
        return new_dir
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    new_dir = os.path.join(xdg, "midnas_devotion")
    legacy = os.path.join(xdg, "ootmodman")
    return _try_migrate_dir(legacy, new_dir, "Midna's Devotion Workspace")


def read_randomizer_state() -> Dict:
    """Read the main randomizer GUI state (gui_state.json) if present."""
    try:
        from oot_rando.paths import state_dir as _rando_state_dir
        st_file = _rando_state_dir() / "gui_state.json"
        if st_file.is_file():
            data = json.loads(st_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        _LOG.debug("Could not read randomizer gui_state.json", exc_info=True)
    return {}


def auto_detect_from_folder(folder: str) -> Dict[str, str]:
    """Infer romfs, live mods, library, archived seeds, and port executable from any port subfolder."""
    folder = os.path.abspath(os.path.expanduser(folder))
    root_dir = folder
    ver_dir = folder

    # If pointed directly at a mods/ or romfs/ subfolder, step up to the port root
    base_low = os.path.basename(folder).lower()
    if base_low == "mods":
        parent = os.path.dirname(folder)
        if os.path.isdir(os.path.join(parent, "romfs")) or os.path.isfile(os.path.join(parent, "image.bin")):
            ver_dir = parent
            root_dir = parent
    elif base_low == "romfs" and os.path.isdir(os.path.join(folder, "Pack")):
        ver_dir = os.path.dirname(folder)
        root_dir = ver_dir

    stable_dir = os.path.join(ver_dir, "stable")
    if os.path.isdir(stable_dir):
        ver_dirs = sorted(glob.glob(os.path.join(stable_dir, "v*")), key=_version_sort_key)
        valid_vers = [d for d in ver_dirs if os.path.isdir(d)]
        if valid_vers:
            ver_dir = valid_vers[-1]
    elif os.path.basename(os.path.dirname(ver_dir)) == "stable":
        root_dir = os.path.dirname(os.path.dirname(ver_dir))

    result: Dict[str, str] = {
        "romfs_dir": "",
        "live_mods_dir": "",
        "backup_dir": "",
        "uninstalled_seeds_dir": "",
        "longshot_binary": "",
    }

    cand_romfs = os.path.join(ver_dir, "romfs")
    if os.path.isdir(cand_romfs):
        result["romfs_dir"] = cand_romfs
    elif os.path.isdir(os.path.join(folder, "Pack")):
        result["romfs_dir"] = folder
        ver_dir = os.path.dirname(folder)

    cand_mods = os.path.join(ver_dir, "mods")
    if os.path.isdir(cand_mods) or os.path.isdir(result["romfs_dir"]):
        result["live_mods_dir"] = cand_mods

    cand_lib = os.path.join(ver_dir, "UserModLibrary")
    cand_legacy_backup = os.path.join(ver_dir, "mods_backup")
    if os.path.isdir(cand_lib):
        result["backup_dir"] = cand_lib
    elif os.path.isdir(cand_legacy_backup):
        result["backup_dir"] = cand_legacy_backup
    elif os.path.isdir(result["romfs_dir"]):
        result["backup_dir"] = cand_lib

    for seeds_cand in (
        os.path.join(ver_dir, "ArchivedSeeds"),
        os.path.join(root_dir, "OoT-Randomizer-linux", "data", "seeds-uninstalled"),
        os.path.join(ver_dir, "seeds-uninstalled"),
    ):
        if os.path.isdir(seeds_cand):
            result["uninstalled_seeds_dir"] = seeds_cand
            break

    # Cross-platform binary detection via oot_rando.pc_port (Windows .exe + native Linux)
    try:
        from oot_rando.pc_port import port_exe
        for cand_root in (ver_dir, root_dir):
            exe = port_exe(cand_root)
            if exe is not None and exe.is_file():
                result["longshot_binary"] = str(exe)
                break
    except Exception:
        _LOG.debug("Failed to detect port executable under %s", folder, exc_info=True)

    return result


def pretty_mod_name(raw_name: str) -> str:
    """Format a raw mod folder name into a readable title by splitting underscores, dashes, and CamelCase."""
    cleaned = raw_name.replace("_", " ").replace("-", " ").strip()
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip() or raw_name


@dataclass
class SeedInfo:
    name: str
    path: str
    source_label: str
    mtime: float

    @property
    def display_label(self) -> str:
        ts = datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")
        return f"{self.name}  [{self.source_label} · {ts}]"


@dataclass
class CoreModEntry:
    name: str
    path: str
    slot: str          # "character" | "visual"
    source_label: str  # "Library" | "Imported" | "Custom"

    @property
    def display_label(self) -> str:
        return f"{pretty_mod_name(self.name)}   [{self.source_label}]"


@dataclass
class StandaloneMod:
    name: str
    source_path: str
    origin: str  # "live" | "staged" | "disabled" | "linked"
    file_count: int
    rel_files: List[str] = field(default_factory=list)


def _is_character_mod_dir(mod_dir: str) -> bool:
    """Heuristic check for playable character replacement mods (player actor/model files)."""
    romfs = os.path.join(mod_dir, "romfs")
    for root, _, files in os.walk(romfs):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), romfs).replace("\\", "/").lower()
            if "player" in rel and (rel.startswith("pack/actor/") or rel.startswith("model/")):
                return True
    return False


class AppConfig:
    """Persistent settings, folder discovery, library management, and overlap engine for Midna's Devotion."""

    def __init__(self, settings_path: Optional[str] = None) -> None:
        """Load saved settings, run legacy folder migrations, and sync active paths from the randomizer."""
        self.config_dir = default_config_dir()
        self.settings_path = settings_path or os.path.join(self.config_dir, "settings.json")

        self.romfs_dir: str = ""
        self.live_mods_dir: str = ""
        self.backup_dir: str = ""
        self.uninstalled_seeds_dir: str = ""
        self.longshot_binary: str = ""
        self.workspace_dir: str = default_workspace_dir()

        self.ui_theme: str = ""
        self.sandbox_mode: bool = True
        self.saved_state: Dict = {}
        self.rando_synced_keys: set[str] = set()
        self.migration_notices: List[str] = list(_STARTUP_MIGRATION_NOTICES)
        _STARTUP_MIGRATION_NOTICES.clear()
        self._codec_cache: Tuple[str, Optional[CodecBundle]] = ("", None)
        self.load_settings()

    @property
    def sandbox_mods_dir(self) -> str:
        return os.path.join(self.workspace_dir, "sandbox", "mods")

    @property
    def staged_mods_dir(self) -> str:
        return os.path.join(self.workspace_dir, "staged_mods")

    @property
    def disabled_mods_dir(self) -> str:
        return os.path.join(self.workspace_dir, "disabled_mods")

    @property
    def bars_originals_dir(self) -> str:
        return os.path.join(self.workspace_dir, "bars_originals")

    @property
    def core_mods_dir(self) -> str:
        return os.path.join(self.workspace_dir, "core_mods")

    def core_slot_dir(self, slot: str) -> str:
        return os.path.join(self.core_mods_dir, slot)

    @property
    def target_mods_dir(self) -> str:
        return self.sandbox_mods_dir if self.sandbox_mode else self.live_mods_dir

    @property
    def launch_cwd(self) -> str:
        if self.longshot_binary:
            bin_dir = os.path.dirname(self.longshot_binary)
            if os.path.basename(bin_dir) == "bin":
                return os.path.dirname(bin_dir)
            return bin_dir
        if self.romfs_dir:
            return os.path.dirname(self.romfs_dir)
        return os.path.expanduser("~")

    @property
    def has_ui_theme_choice(self) -> bool:
        return self.ui_theme in ("mozencaz", "araragi")

    @property
    def effective_ui_theme(self) -> str:
        return self.ui_theme if self.ui_theme in ("mozencaz", "araragi") else "mozencaz"

    @property
    def is_configured(self) -> bool:
        return bool(
            self.romfs_dir
            and os.path.isfile(os.path.join(self.romfs_dir, "Pack", "ZsDic.pack.zs"))
            and self.workspace_dir
        )

    def get_codecs(self) -> Optional[CodecBundle]:
        if not self.is_configured:
            return None
        if self._codec_cache[0] != self.romfs_dir or self._codec_cache[1] is None:
            self._codec_cache = (self.romfs_dir, CodecBundle(self.romfs_dir))
        return self._codec_cache[1]

    def validate_paths(self) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not self.romfs_dir or not os.path.isdir(self.romfs_dir):
            issues.append("Base game romfs/ folder is not set or does not exist.")
        elif not os.path.isfile(os.path.join(self.romfs_dir, "Pack", "ZsDic.pack.zs")):
            issues.append("Selected romfs/ folder is missing Pack/ZsDic.pack.zs.")
        if not self.sandbox_mode and not self.live_mods_dir:
            issues.append("Live mods/ folder is not set.")
        if not self.workspace_dir:
            issues.append("Manager workspace folder is not set.")
        return (len(issues) == 0), issues

    def load_settings(self) -> None:
        if not os.path.isfile(self.settings_path):
            self.sync_from_randomizer(persist=False)
            return
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            self.saved_state = data
            self.romfs_dir = str(data.get("romfs_dir", "") or "")
            self.live_mods_dir = str(data.get("live_mods_dir", "") or "")
            self.backup_dir = str(data.get("backup_dir", "") or "")
            self.uninstalled_seeds_dir = str(data.get("uninstalled_seeds_dir", "") or "")
            self.longshot_binary = str(data.get("longshot_binary", "") or "")
            ws = str(data.get("workspace_dir", "") or "")
            self.workspace_dir = ws if ws else default_workspace_dir()
            raw_theme = str(data.get("ui_theme", "") or "").strip().lower()
            self.ui_theme = raw_theme if raw_theme in ("mozencaz", "araragi") else ""
        except Exception:
            self.saved_state = {}
        self._migrate_legacy_folders()
        self.sync_from_randomizer(persist=False)

    @staticmethod
    def _rewrite_path_prefix(value, old_prefix: str, new_prefix: str):
        """Recursively rewrite saved path strings that begin with ``old_prefix`` to ``new_prefix``."""
        old_abs = os.path.abspath(os.path.expanduser(old_prefix))
        new_abs = os.path.abspath(os.path.expanduser(new_prefix))
        old_norm = os.path.normcase(old_abs)
        if isinstance(value, str) and value:
            cand = os.path.abspath(os.path.expanduser(value))
            cand_norm = os.path.normcase(cand)
            if cand_norm == old_norm:
                return new_abs
            if cand_norm.startswith(old_norm + os.sep):
                return new_abs + cand[len(old_abs):]
            return value
        if isinstance(value, list):
            return [AppConfig._rewrite_path_prefix(v, old_prefix, new_prefix) for v in value]
        if isinstance(value, dict):
            return {k: AppConfig._rewrite_path_prefix(v, old_prefix, new_prefix) for k, v in value.items()}
        return value

    def _migrate_legacy_folders(self) -> None:
        """Gracefully rename legacy ootmodman / mods_backup folders and update saved references."""
        migrated_pairs: List[Tuple[str, str, str]] = []

        if self.workspace_dir:
            ws_abs = os.path.abspath(os.path.expanduser(self.workspace_dir))
            if os.path.basename(ws_abs).lower() == "ootmodman":
                new_ws = os.path.join(os.path.dirname(ws_abs), "midnas_devotion")
                if os.path.isdir(ws_abs) and not os.path.isdir(new_ws):
                    try:
                        shutil.move(ws_abs, new_ws)
                        migrated_pairs.append(("Midna's Devotion Workspace", ws_abs, new_ws))
                        self.workspace_dir = new_ws
                    except Exception:
                        _LOG.debug("Could not migrate legacy workspace %s -> %s", ws_abs, new_ws, exc_info=True)
                elif os.path.isdir(new_ws) and not os.path.isdir(ws_abs):
                    self.workspace_dir = new_ws
                    migrated_pairs.append(("Midna's Devotion Workspace", ws_abs, new_ws))

        if self.backup_dir:
            bk_abs = os.path.abspath(os.path.expanduser(self.backup_dir))
            if os.path.basename(bk_abs).lower() == "mods_backup":
                new_bk = os.path.join(os.path.dirname(bk_abs), "UserModLibrary")
                if os.path.isdir(bk_abs) and not os.path.isdir(new_bk):
                    try:
                        shutil.move(bk_abs, new_bk)
                        migrated_pairs.append(("User Mod Library", bk_abs, new_bk))
                        self.backup_dir = new_bk
                    except Exception:
                        _LOG.debug("Could not migrate legacy library %s -> %s", bk_abs, new_bk, exc_info=True)
                elif os.path.isdir(new_bk) and not os.path.isdir(bk_abs):
                    self.backup_dir = new_bk
                    migrated_pairs.append(("User Mod Library", bk_abs, new_bk))

        if not migrated_pairs:
            return

        for label, old_p, new_p in migrated_pairs:
            msg = f"{label}: {old_p}  →  {new_p}"
            if msg not in self.migration_notices:
                self.migration_notices.append(msg)
            self.saved_state = self._rewrite_path_prefix(self.saved_state, old_p, new_p)
            if self.uninstalled_seeds_dir:
                self.uninstalled_seeds_dir = self._rewrite_path_prefix(self.uninstalled_seeds_dir, old_p, new_p)
        try:
            self.save_settings()
        except Exception:
            _LOG.debug("Could not persist migrated settings to %s", self.settings_path, exc_info=True)

    def sync_from_randomizer(self, mods_dir: Optional[str] = None, *, persist: bool = False) -> bool:
        """Prioritize the main randomizer's Setup mods/port paths over Midna's local settings."""
        if mods_dir is None:
            rando_mods = str(read_randomizer_state().get("mods_dir") or "").strip()
        else:
            rando_mods = str(mods_dir or "").strip()

        self.rando_synced_keys = set()
        if not rando_mods:
            return False

        abs_mods = os.path.abspath(os.path.expanduser(rando_mods))
        changed = False

        if abs_mods and self.live_mods_dir != abs_mods:
            self.live_mods_dir = abs_mods
            changed = True
        self.rando_synced_keys.add("live_mods_dir")

        detected = auto_detect_from_folder(abs_mods)

        det_romfs = detected.get("romfs_dir") or ""
        if det_romfs and os.path.isfile(os.path.join(det_romfs, "Pack", "ZsDic.pack.zs")):
            if self.romfs_dir != det_romfs:
                self.romfs_dir = det_romfs
                changed = True
            self.rando_synced_keys.add("romfs_dir")

        det_bin = detected.get("longshot_binary") or ""
        if det_bin and os.path.isfile(det_bin):
            if self.longshot_binary != det_bin:
                self.longshot_binary = det_bin
                changed = True
            self.rando_synced_keys.add("longshot_binary")

        # Only fill optional folders if blank/missing so custom library paths stay intact
        det_bkp = detected.get("backup_dir") or ""
        if det_bkp and (not self.backup_dir or not os.path.isdir(self.backup_dir)):
            if os.path.isdir(det_bkp) and self.backup_dir != det_bkp:
                self.backup_dir = det_bkp
                changed = True

        det_seeds = detected.get("uninstalled_seeds_dir") or ""
        if det_seeds and not self.uninstalled_seeds_dir and os.path.isdir(det_seeds):
            self.uninstalled_seeds_dir = det_seeds
            changed = True

        if persist and changed:
            self.save_settings()
        return changed

    def save_settings(self, state_updates: Optional[Dict] = None) -> None:
        """Atomically persist configuration and UI state to ``settings.json``."""
        if state_updates:
            self.saved_state.update(state_updates)
        self.saved_state["romfs_dir"] = self.romfs_dir
        self.saved_state["live_mods_dir"] = self.live_mods_dir
        self.saved_state["backup_dir"] = self.backup_dir
        self.saved_state["uninstalled_seeds_dir"] = self.uninstalled_seeds_dir
        self.saved_state["longshot_binary"] = self.longshot_binary
        self.saved_state["workspace_dir"] = self.workspace_dir
        if self.ui_theme in ("mozencaz", "araragi"):
            self.saved_state["ui_theme"] = self.ui_theme
        settings_dir = os.path.dirname(os.path.abspath(self.settings_path))
        os.makedirs(settings_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".settings_", suffix=".tmp", dir=settings_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.saved_state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.settings_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise

    # --- Character Slot Discovery & Management ---
    def _custom_core_map(self) -> Dict[str, List[str]]:
        raw = self.saved_state.get("custom_core_paths")
        if not isinstance(raw, dict):
            return {"character": []}
        vals = raw.get("character", [])
        return {"character": [str(p) for p in vals if isinstance(p, str)] if isinstance(vals, list) else []}

    def find_core_mods(self, slot: str = "character") -> List[CoreModEntry]:
        """Lists all available Playable Character mods."""
        entries: List[CoreModEntry] = []
        seen_paths: set[str] = set()

        def add_entry(path: str, source_label: str) -> None:
            abs_p = os.path.abspath(path)
            norm_k = os.path.normcase(abs_p)
            if norm_k in seen_paths or not os.path.isdir(os.path.join(abs_p, "romfs")):
                return
            seen_paths.add(norm_k)
            entries.append(
                CoreModEntry(name=os.path.basename(abs_p), path=abs_p, slot=slot, source_label=source_label)
            )

        if self.backup_dir and os.path.isdir(self.backup_dir):
            for entry in sorted(os.listdir(self.backup_dir)):
                if entry == "Merged_Zelda_Rando" or entry.startswith("OoT_Randomizer_"):
                    continue
                full = os.path.join(self.backup_dir, entry)
                if os.path.isdir(os.path.join(full, "romfs")) and _is_character_mod_dir(full):
                    add_entry(full, "Library")

        slot_dir = self.core_slot_dir(slot)
        if os.path.isdir(slot_dir):
            for entry in sorted(os.listdir(slot_dir)):
                full = os.path.join(slot_dir, entry)
                if os.path.isdir(os.path.join(full, "romfs")):
                    add_entry(full, "Imported")

        for custom_p in self._custom_core_map().get(slot, []):
            if os.path.isdir(os.path.join(custom_p, "romfs")):
                add_entry(custom_p, "Custom")

        entries.sort(key=lambda e: e.display_label.lower())
        return entries

    def link_custom_core_mod(self, slot: str, folder_path: str) -> CoreModEntry:
        p = os.path.abspath(os.path.expanduser(folder_path))
        if os.path.basename(p).lower() == "romfs":
            p = os.path.dirname(p)
        if not os.path.isdir(os.path.join(p, "romfs")):
            raise RuntimeError(
                f"Selected folder does not contain a 'romfs' subfolder:\n{p}\n\n"
                "Choose the mod's main folder (the one right above romfs/)."
            )
        cmap = self._custom_core_map()
        existing_keys = {_norm_path_key(x) for x in cmap[slot]}
        if _norm_path_key(p) not in existing_keys:
            cmap[slot].append(p)
            self.save_settings({"custom_core_paths": cmap})
        return CoreModEntry(name=os.path.basename(p), path=p, slot=slot, source_label="Custom")

    def remove_core_mod(self, entry: CoreModEntry) -> None:
        """Unlink a custom character mod or delete an imported workspace character mod."""
        if entry.source_label == "Library":
            raise RuntimeError(
                f"'{entry.name}' comes from your User Mod Library (UserModLibrary/) and is protected from deletion here."
            )
        if entry.source_label == "Custom":
            cmap = self._custom_core_map()
            target_key = _norm_path_key(entry.path)
            cmap[entry.slot] = [p for p in cmap[entry.slot] if _norm_path_key(p) != target_key]
            self.save_settings({"custom_core_paths": cmap})
            return
        if entry.source_label == "Imported":
            slot_root = os.path.abspath(self.core_slot_dir(entry.slot))
            target = os.path.abspath(entry.path)
            # Guard against cross-drive ValueError on Windows and prevent deleting outside core_slot_dir.
            if _is_within_dir(slot_root, target) and _norm_path_key(target) != _norm_path_key(slot_root) and os.path.isdir(target):
                shutil.rmtree(target)

    # --- Step 2 Visual Mod Library Picker + Linked Mods for the Right-Hand List ---
    def find_library_visual_mods(self) -> List[CoreModEntry]:
        """List non-character visual/UI/model mods available in ``UserModLibrary``."""
        entries: List[CoreModEntry] = []
        if not self.backup_dir or not os.path.isdir(self.backup_dir):
            return entries
        for entry in sorted(os.listdir(self.backup_dir)):
            if entry in MANAGED_MOD_NAMES or entry.startswith("OoT_Randomizer_"):
                continue
            full = os.path.abspath(os.path.join(self.backup_dir, entry))
            if not os.path.isdir(os.path.join(full, "romfs")):
                continue
            if _is_character_mod_dir(full):
                continue
            entries.append(CoreModEntry(name=entry, path=full, slot="visual", source_label="Library"))
        entries.sort(key=lambda e: e.name.lower())
        return entries

    def _migrate_legacy_visual_mods(self) -> List[str]:
        """One-time migration so previously enabled Classic_UI / Malon_N64 / custom UI/NPC slots appear in the right list."""
        if "added_list_mod_paths" in self.saved_state:
            raw = self.saved_state.get("added_list_mod_paths")
            return [str(p) for p in raw if isinstance(p, str)] if isinstance(raw, list) else []

        migrated: List[str] = []
        auto_enable_names: List[str] = []
        st = self.saved_state

        def maybe_add(path: Optional[str], enable: bool = True) -> None:
            if not path:
                return
            abs_p = os.path.abspath(path)
            if os.path.isdir(os.path.join(abs_p, "romfs")) and abs_p not in migrated:
                migrated.append(abs_p)
                if enable:
                    auto_enable_names.append(os.path.basename(abs_p))

        if "selected_ui_path" in st:
            maybe_add(st.get("selected_ui_path"), enable=True)

        if "selected_npc_path" in st:
            maybe_add(st.get("selected_npc_path"), enable=True)

        # Also preserve any previously linked custom UI/NPC paths or imported workspace core_mods
        raw_core = st.get("custom_core_paths")
        if isinstance(raw_core, dict):
            for old_slot in ("ui", "npc"):
                for p in raw_core.get(old_slot, []) or []:
                    if isinstance(p, str):
                        maybe_add(p, enable=False)

        for old_slot in ("ui", "npc"):
            sdir = self.core_slot_dir(old_slot)
            if os.path.isdir(sdir):
                for name in sorted(os.listdir(sdir)):
                    maybe_add(os.path.join(sdir, name), enable=False)

        updates: Dict = {"added_list_mod_paths": migrated}
        saved_en = st.get("enabled_standalone")
        if isinstance(saved_en, list):
            merged_en = list(saved_en)
            for n in auto_enable_names:
                if n not in merged_en:
                    merged_en.append(n)
            updates["enabled_standalone"] = merged_en

        if self.romfs_dir or migrated:
            self.save_settings(updates)
        else:
            self.saved_state.update(updates)
        return migrated

    def add_mod_folder_to_list(self, folder_path: str) -> str:
        """Link any visual/UI/model mod folder (from ``UserModLibrary`` or elsewhere) into the right-hand list."""
        p = os.path.abspath(os.path.expanduser(folder_path))
        if os.path.basename(p).lower() == "romfs":
            p = os.path.dirname(p)
        if not os.path.isdir(os.path.join(p, "romfs")):
            raise RuntimeError(
                f"Selected folder does not contain a 'romfs' subfolder:\n{p}\n\n"
                "Choose the mod's main folder (the one right above romfs/)."
            )
        paths = self._migrate_legacy_visual_mods()
        if _norm_path_key(p) not in {_norm_path_key(x) for x in paths}:
            paths.append(p)
            self.save_settings({"added_list_mod_paths": paths})
        return os.path.basename(p)

    def set_mod_order(self, ordered_names: List[str]) -> None:
        """Persist the user-defined priority order for the right-hand mod list."""
        self.save_settings({"mod_order": list(ordered_names)})

    def add_custom_seed_folder(self, folder_path: str) -> str:
        """Register an external randomizer seed folder containing ``romfs/``."""
        p = os.path.abspath(os.path.expanduser(folder_path))
        if os.path.basename(p).lower() == "romfs":
            p = os.path.dirname(p)
        if not os.path.isdir(os.path.join(p, "romfs")):
            raise RuntimeError(f"Selected seed folder does not contain a 'romfs' subfolder:\n{p}")
        raw = self.saved_state.get("custom_seed_paths")
        seeds = [str(x) for x in raw if isinstance(x, str)] if isinstance(raw, list) else []
        if _norm_path_key(p) not in {_norm_path_key(x) for x in seeds}:
            seeds.append(p)
            self.save_settings({"custom_seed_paths": seeds})
        return p

    @staticmethod
    def is_malon_skeleton_conflict(char_path: Optional[str], mod_path: Optional[str]) -> bool:
        """Detects the known Playable Malon + Adult Malon N64 NPC skeleton conflict."""
        if not char_path or not mod_path:
            return False
        c_name = os.path.basename(char_path).lower()
        if "malon" not in c_name:
            return False
        m_name = os.path.basename(mod_path).lower()
        if "malon" in m_name and ("n64" in m_name or "proportion" in m_name):
            return True
        mod_romfs = os.path.join(mod_path, "romfs")
        if os.path.isdir(mod_romfs):
            for root, _, files in os.walk(mod_romfs):
                for fn in files:
                    if "malon_adult" in fn.lower() and fn.lower().endswith(".bfres.zs"):
                        return True
        return False

    def mod_merge_kind(self, mod: StandaloneMod) -> str:
        """
        Determines how a checked mod in the right-hand list should be integrated:
        - 'ui_merge': touches .blarc/.bntx or Mals/ (3-way merged into Merged_Zelda_Rando)
        - 'model_merge': ships RESTBL, is linked from Library/custom folder, or has oversized .bfres.zs
        - 'standalone': clean drop-in folder in mods/ (still participates in .bars auto-merging)
        """
        has_ui_or_mals = False
        has_rstb = False
        has_bfres = False
        for rel in mod.rel_files:
            low = rel.replace("\\", "/").lower()
            if low.endswith(UI_MERGE_EXTS) or low.startswith("mals/"):
                has_ui_or_mals = True
            if "resourcesizetable" in low:
                has_rstb = True
            if low.endswith(".bfres.zs"):
                has_bfres = True

        if has_ui_or_mals:
            return "ui_merge"
        if has_rstb or mod.origin == "linked":
            return "model_merge"
        if has_bfres and self.romfs_dir:
            # Check if any .bfres.zs grew larger than vanilla (needs RESTBL headroom inside Merged_Zelda_Rando)
            for rel in mod.rel_files:
                if rel.lower().endswith(".bfres.zs"):
                    mod_p = os.path.join(mod.source_path, "romfs", rel)
                    van_p = os.path.join(self.romfs_dir, rel)
                    if os.path.isfile(mod_p) and os.path.isfile(van_p):
                        if os.path.getsize(mod_p) > int(os.path.getsize(van_p) * 1.15):
                            return "model_merge"
        return "standalone"

    def find_seeds(self) -> List[SeedInfo]:
        seeds: List[SeedInfo] = []
        rando_seeds_dir = ''
        rando_archive_dir = ''
        try:
            from oot_rando.paths import data_dir as _rando_data_dir, seeds_dir as _rando_seeds_dir
            rando_seeds_dir = str(_rando_seeds_dir())
            rando_archive_dir = str(_rando_data_dir() / 'seeds-uninstalled')
        except Exception:
            _LOG.debug("Could not query randomizer seed/archive paths", exc_info=True)
        sources = (
            (self.live_mods_dir, 'mods'),
            (rando_seeds_dir, 'randomizer seeds'),
            (rando_archive_dir, 'uninstalled'),
            (self.uninstalled_seeds_dir, 'uninstalled'),
            (self.backup_dir, 'backup'),
        )
        seen_paths = set()
        for root_dir, label in sources:
            if not root_dir or not os.path.isdir(root_dir):
                continue
            for cand in glob.glob(os.path.join(root_dir, 'OoT_Randomizer_*')):
                abs_c = os.path.abspath(cand)
                norm_k = os.path.normcase(abs_c)
                if norm_k in seen_paths:
                    continue
                if os.path.isdir(os.path.join(cand, 'romfs')):
                    seen_paths.add(norm_k)
                    seeds.append(
                        SeedInfo(
                            name=os.path.basename(cand),
                            path=abs_c,
                            source_label=label,
                            mtime=os.path.getmtime(cand),
                        )
                    )

        raw_custom = self.saved_state.get('custom_seed_paths')
        if isinstance(raw_custom, list):
            for cand in raw_custom:
                if not isinstance(cand, str):
                    continue
                abs_c = os.path.abspath(cand)
                norm_k = os.path.normcase(abs_c)
                if norm_k not in seen_paths and os.path.isdir(os.path.join(abs_c, 'romfs')):
                    seen_paths.add(norm_k)
                    seeds.append(
                        SeedInfo(
                            name=os.path.basename(cand),
                            path=abs_c,
                            source_label='custom',
                            mtime=os.path.getmtime(abs_c),
                        )
                    )
        seeds.sort(key=lambda s: s.mtime, reverse=True)
        return seeds

    @staticmethod
    def _walk_romfs_rel(mod_dir: str) -> List[str]:
        """Return sorted POSIX ``/``-delimited paths of all files under ``mod_dir/romfs``."""
        romfs = os.path.join(mod_dir, "romfs")
        rels: List[str] = []
        if not os.path.isdir(romfs):
            return rels
        for root, _, files in os.walk(romfs):
            for fn in files:
                # Always normalize to forward slashes so RESTBL keys and archive overlap checks match on Windows.
                rels.append(os.path.relpath(os.path.join(root, fn), romfs).replace("\\", "/"))
        rels.sort()
        return rels

    def _walk_bars_backup_rel(self, mod_name: str) -> List[str]:
        """Return POSIX ``/``-delimited paths of stashed original ``.bars`` files for ``mod_name``."""
        bdir = os.path.join(self.bars_originals_dir, mod_name)
        if not os.path.isdir(bdir):
            return []
        rels: List[str] = []
        for root, _, files in os.walk(bdir):
            for fn in files:
                rels.append(os.path.relpath(os.path.join(root, fn), bdir).replace("\\", "/"))
        return rels

    def resolve_mod_file_path(self, mod: StandaloneMod, rel_path: str) -> str:
        """Resolve a mod's canonical relative path to disk, preferring stashed original ``.bars`` copies."""
        parts = rel_path.replace("\\", "/").split("/")
        bkp = os.path.join(self.bars_originals_dir, mod.name, *parts)
        if os.path.isfile(bkp):
            return bkp
        return os.path.join(mod.source_path, "romfs", *parts)

    def restore_bars_originals(self, log=None) -> int:
        if not os.path.isdir(self.bars_originals_dir):
            return 0
        restored = 0
        for mod_name in sorted(os.listdir(self.bars_originals_dir)):
            mod_bkp_dir = os.path.join(self.bars_originals_dir, mod_name)
            if not os.path.isdir(mod_bkp_dir):
                continue
            dest_mod_root = None
            for cand_root in (self.live_mods_dir, self.disabled_mods_dir, self.staged_mods_dir):
                if cand_root and os.path.isdir(os.path.join(cand_root, mod_name)):
                    dest_mod_root = os.path.join(cand_root, mod_name)
                    break
            if not dest_mod_root:
                continue
            for root, _, files in os.walk(mod_bkp_dir):
                for fn in files:
                    src = os.path.join(root, fn)
                    rel = os.path.relpath(src, mod_bkp_dir)
                    dst = os.path.join(dest_mod_root, "romfs", rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                    restored += 1
            shutil.rmtree(mod_bkp_dir, ignore_errors=True)
            if log:
                log(f"   Restored original .bars file(s) for {mod_name}")
        return restored

    def find_standalone_mods(self) -> List[StandaloneMod]:
        """Returns all mods managed in the unified right-hand list (live, staged, disabled, and linked visuals)."""
        found: Dict[str, StandaloneMod] = {}

        # 1. Linked visual/UI/model mods added via Step 2 (e.g., Classic_UI, Malon_N64_Proportions, custom folders)
        for linked_p in self._migrate_legacy_visual_mods():
            abs_p = os.path.abspath(linked_p)
            if not os.path.isdir(os.path.join(abs_p, "romfs")):
                continue
            name = os.path.basename(abs_p)
            if name in MANAGED_MOD_NAMES or name.startswith("OoT_Randomizer_") or name in found:
                continue
            rels = self._walk_romfs_rel(abs_p)
            found[name] = StandaloneMod(
                name=name,
                source_path=abs_p,
                origin="linked",
                file_count=len(rels),
                rel_files=rels,
            )

        # 2. Live, staged, and disabled mods
        scan_order = (
            (self.live_mods_dir, "live"),
            (self.staged_mods_dir, "staged"),
            (self.disabled_mods_dir, "disabled"),
        )
        for directory, origin in scan_order:
            if not directory or not os.path.isdir(directory):
                continue
            for entry in sorted(os.listdir(directory)):
                if entry in MANAGED_MOD_NAMES or entry.startswith("OoT_Randomizer_"):
                    continue
                if entry in found:
                    continue
                full = os.path.join(directory, entry)
                if not os.path.isdir(os.path.join(full, "romfs")):
                    continue
                rels = sorted(set(self._walk_romfs_rel(full) + self._walk_bars_backup_rel(entry)))
                found[entry] = StandaloneMod(
                    name=entry,
                    source_path=full,
                    origin=origin,
                    file_count=len(rels),
                    rel_files=rels,
                )

        # Respect saved user load order
        saved_order = self.saved_state.get("mod_order")
        order_idx = {name: i for i, name in enumerate(saved_order)} if isinstance(saved_order, list) else {}
        return sorted(
            found.values(),
            key=lambda m: (order_idx.get(m.name, 10000), 0 if m.origin == "linked" else 1, m.name.lower()),
        )

    def _active_merged_dir(self) -> Optional[str]:
        cands = []
        if self.target_mods_dir:
            cands.append(os.path.join(self.target_mods_dir, "Merged_Zelda_Rando"))
        if self.live_mods_dir:
            cands.append(os.path.join(self.live_mods_dir, "Merged_Zelda_Rando"))
        return next((p for p in cands if os.path.isdir(os.path.join(p, "romfs"))), None)

    def classify_overlaps(
        self,
        enabled_mods: List[StandaloneMod],
        char_path: Optional[str] = None,
        rando_path: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, Tuple[List[str], List[str]]]]:
        """
        Separates overlapping files into:
          - real_conflicts: {rel: [owners]} (true file conflicts or same-track BARS edits)
          - auto_merged: {rel: ([owners], [reason_tags])} (UI .blarc/.bntx, Mals, RESTBL, or disjoint .bars)
        """
        file_owners: Dict[str, List[str]] = {}
        bars_sources_by_rel: Dict[str, List[Tuple[str, str]]] = {}

        # Compare against the currently selected Step 1 Character + Randomizer seed directly
        if char_path and os.path.isdir(os.path.join(char_path, "romfs")):
            c_label = pretty_mod_name(os.path.basename(char_path))
            for rel in self._walk_romfs_rel(char_path):
                file_owners.setdefault(rel, []).append(c_label)
                if rel.endswith(BARS_EXTS):
                    bars_sources_by_rel.setdefault(rel, []).append((c_label, os.path.join(char_path, "romfs", rel)))

        if rando_path and os.path.isdir(os.path.join(rando_path, "romfs")):
            r_label = "Randomizer Seed"
            for rel in self._walk_romfs_rel(rando_path):
                file_owners.setdefault(rel, []).append(r_label)
                if rel.endswith(BARS_EXTS):
                    bars_sources_by_rel.setdefault(rel, []).append((r_label, os.path.join(rando_path, "romfs", rel)))

        for mod in enabled_mods:
            if self.is_malon_skeleton_conflict(char_path, mod.source_path):
                continue
            for rel in mod.rel_files:
                file_owners.setdefault(rel, []).append(mod.name)
                if rel.endswith(BARS_EXTS):
                    p = self.resolve_mod_file_path(mod, rel)
                    if os.path.isfile(p):
                        bars_sources_by_rel.setdefault(rel, []).append((mod.name, p))

        real_conflicts: Dict[str, List[str]] = {}
        auto_merged: Dict[str, Tuple[List[str], List[str]]] = {}
        codecs = self.get_codecs()

        for rel, owners in sorted(file_owners.items()):
            if len(owners) < 2:
                continue
            low = rel.replace("\\", "/").lower()

            if "resourcesizetable" in low:
                auto_merged[rel] = (owners, ["Memory table (RESTBL)"])
                continue
            if low.startswith("mals/") and low.endswith(".sarc.zs"):
                auto_merged[rel] = (owners, ["Dialogue (Mals)"])
                continue
            if low.endswith(UI_MERGE_EXTS):
                auto_merged[rel] = (owners, ["UI archive"])
                continue
            if rel.endswith(BARS_EXTS) and codecs is not None:
                van_p = os.path.join(self.romfs_dir, rel)
                sources = bars_sources_by_rel.get(rel, [])
                if os.path.isfile(van_p) and len(sources) >= 2:
                    try:
                        base_raw, _ = read_bars_raw(van_p, codecs)
                        blobs = [(name, read_bars_raw(p, codecs)[0]) for name, p in sources]
                        ok, merged_tracks, _conf_tracks = analyze_bars_compatibility(base_raw, blobs)
                        if ok:
                            auto_merged[rel] = ([n for n, _ in blobs], merged_tracks or ["Audio table"])
                            continue
                    except Exception:
                        _LOG.debug("BARS compatibility analysis failed for %s", rel, exc_info=True)

            real_conflicts[rel] = owners

        return real_conflicts, auto_merged

    def detect_overlaps(
        self,
        enabled_mods: List[StandaloneMod],
        char_path: Optional[str] = None,
        rando_path: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        real_conflicts, _ = self.classify_overlaps(enabled_mods, char_path=char_path, rando_path=rando_path)
        return real_conflicts

    def mod_conflict_map(
        self,
        target_mod: StandaloneMod,
        enabled_mods: List[StandaloneMod],
        char_path: Optional[str] = None,
        rando_path: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        check_list = list(enabled_mods)
        if all(m.name != target_mod.name for m in check_list):
            check_list.append(target_mod)
        real_conflicts, auto_merge = self.classify_overlaps(check_list, char_path=char_path, rando_path=rando_path)

        conflicts_out: Dict[str, List[str]] = {}
        auto_out: Dict[str, List[str]] = {}
        for rel in target_mod.rel_files:
            if rel in real_conflicts and target_mod.name in real_conflicts[rel]:
                conflicts_out[rel] = [o for o in real_conflicts[rel] if o != target_mod.name]
            elif rel in auto_merge and target_mod.name in auto_merge[rel][0]:
                auto_out[rel] = [o for o in auto_merge[rel][0] if o != target_mod.name]
        return conflicts_out, auto_out

    def rename_standalone_mod(self, mod: StandaloneMod, raw_new_name: str) -> str:
        if mod.origin == "linked":
            raise RuntimeError(
                f"'{mod.name}' is linked from an external or Mod Library folder and cannot be renamed on disk from here."
            )
        if mod.origin == "live" and self.sandbox_mode:
            raise RuntimeError(
                f"'{mod.name}' is in your live game folder.\n\n"
                "Test Mode never modifies your live game. Switch to Live Mode at the top to rename it."
            )

        new_name = sanitize_folder_name(raw_new_name)
        if not new_name:
            raise RuntimeError("Please enter a valid folder name (letters, numbers, dashes, or underscores).")
        if new_name in MANAGED_MOD_NAMES or new_name.startswith("OoT_Randomizer_"):
            raise RuntimeError(f"'{new_name}' is a reserved system mod name. Please pick a different name.")
        if new_name == mod.name:
            return new_name

        check_dirs = [self.staged_mods_dir, self.disabled_mods_dir]
        if self.live_mods_dir:
            check_dirs.append(self.live_mods_dir)
        for d in check_dirs:
            if d and os.path.exists(os.path.join(d, new_name)):
                raise RuntimeError(f"A mod named '{new_name}' already exists in:\n{d}")

        rename_roots = [self.staged_mods_dir, self.disabled_mods_dir, self.sandbox_mods_dir, self.bars_originals_dir]
        if not self.sandbox_mode and self.live_mods_dir:
            rename_roots.append(self.live_mods_dir)

        renamed_any = False
        seen_parents = set()
        for root_dir in rename_roots:
            if not root_dir:
                continue
            abs_root = os.path.abspath(root_dir)
            if abs_root in seen_parents:
                continue
            seen_parents.add(abs_root)
            old_p = os.path.join(root_dir, mod.name)
            new_p = os.path.join(root_dir, new_name)
            if os.path.isdir(old_p):
                if os.path.exists(new_p):
                    shutil.rmtree(new_p)
                os.rename(old_p, new_p)
                renamed_any = True

        if not renamed_any:
            raise RuntimeError(f"Could not find mod folder to rename: {mod.source_path}")

        updates: Dict = {}
        saved_enabled = self.saved_state.get("enabled_standalone")
        if isinstance(saved_enabled, list):
            updates["enabled_standalone"] = [new_name if n == mod.name else n for n in saved_enabled]
        saved_order = self.saved_state.get("mod_order")
        if isinstance(saved_order, list):
            updates["mod_order"] = [new_name if n == mod.name else n for n in saved_order]
        if updates:
            self.save_settings(updates)

        return new_name

    def delete_standalone_mod(self, mod: StandaloneMod) -> List[str]:
        """Unlink a library/external mod or delete a workspace/live standalone mod folder."""
        if mod.origin == "linked":
            # Only unlink from the right-hand list; never delete files in UserModLibrary/ or user folders.
            paths = self._migrate_legacy_visual_mods()
            target_key = _norm_path_key(mod.source_path)
            new_paths = [p for p in paths if _norm_path_key(p) != target_key]
            updates: Dict = {"added_list_mod_paths": new_paths}
            saved_enabled = self.saved_state.get("enabled_standalone")
            if isinstance(saved_enabled, list) and mod.name in saved_enabled:
                updates["enabled_standalone"] = [n for n in saved_enabled if n != mod.name]
            saved_order = self.saved_state.get("mod_order")
            if isinstance(saved_order, list) and mod.name in saved_order:
                updates["mod_order"] = [n for n in saved_order if n != mod.name]
            self.save_settings(updates)
            return []

        if mod.origin == "live" and self.sandbox_mode:
            raise RuntimeError(
                f"'{mod.name}' is in your live game folder.\n\n"
                "Test Mode never modifies your live game. Uncheck it to test without it, "
                "or switch to Live Mode at the top to permanently delete it."
            )

        remove_roots = [self.staged_mods_dir, self.disabled_mods_dir, self.sandbox_mods_dir, self.bars_originals_dir]
        if not self.sandbox_mode and self.live_mods_dir:
            remove_roots.append(self.live_mods_dir)

        removed: List[str] = []
        seen_paths = set()
        for root_dir in remove_roots:
            if not root_dir:
                continue
            cand = os.path.abspath(os.path.join(root_dir, mod.name))
            norm_k = os.path.normcase(cand)
            if norm_k in seen_paths:
                continue
            if os.path.isdir(cand):
                seen_paths.add(norm_k)
                shutil.rmtree(cand)
                removed.append(cand)

        updates: Dict = {}
        saved_enabled = self.saved_state.get("enabled_standalone")
        if isinstance(saved_enabled, list) and mod.name in saved_enabled:
            updates["enabled_standalone"] = [n for n in saved_enabled if n != mod.name]
        saved_order = self.saved_state.get("mod_order")
        if isinstance(saved_order, list) and mod.name in saved_order:
            updates["mod_order"] = [n for n in saved_order if n != mod.name]
        if updates:
            self.save_settings(updates)

        return removed
