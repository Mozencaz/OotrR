"""Mod archive inspection, RESTBL headroom preflight checks, and safe archive extraction.

Supports ``.zip``, ``.7z``, and ``.rar`` mod packages across Linux, Windows, and macOS,
normalizing ``RomFS/`` casing and checking loose files plus internal SARC subfiles
against both the active merged RESTBL and vanilla RESTBL headroom.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import oead
import restbl

from oot_rando.midnas_devotion.core.config import (
    AppConfig,
    RSTB_REL,
    StandaloneMod,
    _is_within_dir,
    clean_subprocess_env,
)
from oot_rando.midnas_devotion.core.formats import (
    BARS_EXTS,
    CodecBundle,
    analyze_bars_compatibility,
    read_bars_raw,
    read_maybe_zstd,
)

_LOG = logging.getLogger(__name__)

SUPPORTED_ARCHIVE_EXTS = (".zip", ".7z", ".rar")
SARC_EXTS = (".pack.zs", ".sarc.zs", ".blarc.zs", ".pack", ".sarc", ".blarc")


def _remove_path(path: str) -> None:
    """Remove a file, symlink, or directory safely."""
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def _find_bundled_7zip() -> Optional[str]:
    """Return path to bundled 7-Zip CLI (7z.exe + 7z.dll on Windows) if shipped with the package."""
    exe_name = "7z.exe" if sys.platform == "win32" else "7zz"
    candidates: List[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "oot_rando", "midnas_devotion", "vendor", "7zip", exe_name))
        candidates.append(os.path.join(meipass, "vendor", "7zip", exe_name))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "vendor", "7zip", exe_name))
        candidates.append(os.path.join(exe_dir, exe_name))
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(pkg_root, "vendor", "7zip", exe_name))
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return None


def _find_windows_system_tar() -> Optional[str]:
    """Locate Windows 11 native bsdtar (System32/tar.exe) which supports .7z and .rar via libarchive."""
    if sys.platform != "win32":
        return None
    sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or ("C:" + os.sep + "Windows")
    cand = os.path.join(sys_root, "System32", "tar.exe")
    return cand if os.path.isfile(cand) else None


def _find_extractor_tool(name: str, clean_path: Optional[str]) -> Optional[str]:
    """Locate an external archive extractor: bundled 7-Zip, PATH, or Windows install folders."""
    if name == "7z":
        bundled = _find_bundled_7zip()
        if bundled:
            return bundled
    found = shutil.which(name, path=clean_path)
    if found:
        return found
    if sys.platform == "win32":
        prog_files = [
            os.environ.get("ProgramFiles", "C:" + os.sep + "Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:" + os.sep + "Program Files (x86)"),
        ]
        win_candidates = {
            "7z": [os.path.join(pf, "7-Zip", "7z.exe") for pf in prog_files if pf],
            "7zz": [os.path.join(pf, "7-Zip", "7zz.exe") for pf in prog_files if pf],
            "unrar": [os.path.join(pf, "WinRAR", "UnRAR.exe") for pf in prog_files if pf],
        }
        for cand in win_candidates.get(name, ()):
            if os.path.isfile(cand):
                return cand
    return None


def _missing_extractor_hint(ext: str) -> str:
    """Return an OS-appropriate installation hint when no ``.7z``/``.rar`` CLI extractor is found."""
    if sys.platform == "win32":
        return "Install 7-Zip (https://www.7-zip.org/ or: winget install 7zip.7zip)"
    if sys.platform == "darwin":
        return "brew install p7zip" if ext == ".7z" else "brew install p7zip unrar"
    return "Install 7zip/p7zip (e.g. sudo pacman -S 7zip  or  sudo apt install p7zip-full)"


class ArchiveHandle:
    """Unified read-only interface for ``.zip``, ``.7z``, and ``.rar`` mod archives."""

    def __init__(self, archive_path: str) -> None:
        self.path = archive_path
        self.ext = os.path.splitext(archive_path)[1].lower()
        self._zf: Optional[zipfile.ZipFile] = None
        self._tmpdir: Optional[str] = None
        self._zip_map: Dict[str, str] = {}
        self._disk_map: Dict[str, str] = {}
        self._open()

    def _open(self) -> None:
        if self.ext == ".zip":
            self._zf = zipfile.ZipFile(self.path, "r")
            for info in self._zf.infolist():
                if info.is_dir():
                    continue
                norm = info.filename.replace("\\", "/").lstrip("/")
                if norm:
                    self._zip_map[norm] = info.filename
            return

        if self.ext in (".7z", ".rar"):
            self._tmpdir = tempfile.mkdtemp(prefix="midna_arc_")
            try:
                self._extract_external(self._tmpdir)
            except Exception:
                self.close()
                raise
            for root, _, files in os.walk(self._tmpdir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self._tmpdir).replace("\\", "/")
                    self._disk_map[rel] = full
            return

        raise RuntimeError(f"Unsupported archive format: {self.ext} (supported: .zip, .7z, .rar)")

    def _extract_external(self, dst_dir: str) -> None:
        clean_env = clean_subprocess_env()
        clean_path = clean_env.get("PATH")
        candidates: List[Tuple[str, List[str]]] = []

        seen_exes: set[str] = set()

        def _push(label: str, exe_path: Optional[str], cmd: List[str]) -> None:
            if not exe_path:
                return
            key = os.path.normcase(os.path.abspath(exe_path))
            if key in seen_exes:
                return
            seen_exes.add(key)
            candidates.append((label, cmd))

        bundled_7z = _find_bundled_7zip()
        if bundled_7z:
            _push("bundled-7z", bundled_7z, [bundled_7z, "x", "-y", f"-o{dst_dir}", self.path])

        if self.ext == ".7z":
            for tool in ("7z", "7zz"):
                exe = _find_extractor_tool(tool, clean_path)
                if exe:
                    _push(tool, exe, [exe, "x", "-y", f"-o{dst_dir}", self.path])
            bsdtar = _find_extractor_tool("bsdtar", clean_path)
            if bsdtar:
                _push("bsdtar", bsdtar, [bsdtar, "-xf", self.path, "-C", dst_dir])
        elif self.ext == ".rar":
            unrar = _find_extractor_tool("unrar", clean_path)
            if unrar:
                _push("unrar", unrar, [unrar, "x", "-y", "-o+", self.path, dst_dir + os.sep])
            bsdtar = _find_extractor_tool("bsdtar", clean_path)
            if bsdtar:
                _push("bsdtar", bsdtar, [bsdtar, "-xf", self.path, "-C", dst_dir])
            for tool in ("7z", "7zz"):
                exe = _find_extractor_tool(tool, clean_path)
                if exe:
                    _push(tool, exe, [exe, "x", "-y", f"-o{dst_dir}", self.path])

        win_tar = _find_windows_system_tar()
        if win_tar:
            _push("windows-tar", win_tar, [win_tar, "-xf", self.path, "-C", dst_dir])

        if not candidates:
            hint = _missing_extractor_hint(self.ext)
            raise RuntimeError(f"No extractor found for {self.ext} archives.\n{hint}")

        errors: List[str] = []
        for tool_name, cmd in candidates:
            for entry in os.listdir(dst_dir):
                _remove_path(os.path.join(dst_dir, entry))
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
            if proc.returncode == 0:
                return
            err_msg = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["unknown error"]
            errors.append(f"{tool_name}: {err_msg[0]}")

        raise RuntimeError(f"Failed to extract {os.path.basename(self.path)}:\n" + "\n".join(errors))

    def list_files(self) -> List[str]:
        """Return sorted POSIX ``/``-delimited file paths inside the archive."""
        if self._zf is not None:
            return sorted(self._zip_map.keys())
        return sorted(self._disk_map.keys())

    def read_bytes(self, norm_path: str) -> bytes:
        """Read the raw bytes of a normalized entry path from the archive."""
        if self._zf is not None:
            return self._zf.read(self._zip_map[norm_path])
        with open(self._disk_map[norm_path], "rb") as f:
            return f.read()

    def close(self) -> None:
        """Close any open archive handle and remove temporary extraction directories."""
        if self._zf is not None:
            try:
                self._zf.close()
            finally:
                self._zf = None
        if self._tmpdir and os.path.isdir(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    def __enter__(self) -> "ArchiveHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@dataclass
class FileCheckRow:
    """Per-file (or SARC subfile) preflight audit result."""

    status: str  # OK | OVERLAP | OVER_RESTBL | RESTBL_111 | RESTBL_OLD | DECOMPRESS_ERR | EXEFS | TIGHT_MARGIN | SUB_* | stacked
    rel_path: str
    mod_size: int
    van_size: int
    restbl_size: Optional[int]
    overlap_with: List[str] = field(default_factory=list)
    margin_mod: Optional[int] = None
    margin_van: Optional[int] = None
    is_subfile: bool = False


@dataclass
class PreflightReport:
    """Aggregated compatibility verdict, warnings, and per-file rows for an inspected archive variant."""

    archive_path: str
    variant_prefix: str
    verdict: str  # "DROP_IN_SAFE" | "NEEDS_ATTENTION" | "UNSUPPORTED"
    warnings: List[str] = field(default_factory=list)
    advanced_warnings: List[str] = field(default_factory=list)
    rows: List[FileCheckRow] = field(default_factory=list)
    advanced_ran: bool = False
    subfiles_scanned: int = 0


def list_archive_variants(archive: ArchiveHandle) -> Tuple[List[str], List[str]]:
    """Return ``(variant_prefixes, exefs_entries)``. Each variant prefix ends before ``romfs/``."""
    variants = set()
    exefs_hits: List[str] = []
    for name in archive.list_files():
        parts = name.split("/")
        for idx, part in enumerate(parts):
            low = part.lower()
            if low == "exefs" and idx + 1 < len(parts):
                exefs_hits.append(name)
            if low == "romfs" and idx + 1 < len(parts):
                variants.add("/".join(parts[:idx]))
    return sorted(variants), sorted(set(exefs_hits))


def _load_active_restbl(cfg: AppConfig, codecs: CodecBundle):
    """Load the highest-priority active ``ResourceSizeTable`` (Merged -> Live Merged -> Vanilla)."""
    candidates = []
    if cfg.target_mods_dir:
        candidates.append(os.path.join(cfg.target_mods_dir, "Merged_Zelda_Rando", RSTB_REL))
    if cfg.live_mods_dir:
        candidates.append(os.path.join(cfg.live_mods_dir, "Merged_Zelda_Rando", RSTB_REL))
    if cfg.romfs_dir:
        candidates.append(os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :]))
    rstb_path = next((p for p in candidates if os.path.exists(p)), None)
    if not rstb_path:
        return None
    raw, _ = read_maybe_zstd(rstb_path, codecs)
    return restbl.ResourceSizeTable.from_binary(raw)


def _load_vanilla_restbl(cfg: AppConfig, codecs: CodecBundle):
    """Load the base game's vanilla ``ResourceSizeTable`` for baseline margin comparisons."""
    van_rstb = os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :])
    if not os.path.exists(van_rstb):
        return None
    raw, _ = read_maybe_zstd(van_rstb, codecs)
    return restbl.ResourceSizeTable.from_binary(raw)


def _is_tight_margin(mod_sz: int, van_sz: int, margin_mod: Optional[int], margin_van: Optional[int]) -> bool:
    """Flag headroom tighter than vanilla when a file grows, without false-positiving exact-size swaps."""
    if margin_mod is None or margin_mod <= 0:
        return False
    if van_sz > 0 and mod_sz <= van_sz:
        return False
    if van_sz > 0 and margin_van is not None and margin_van > 0 and margin_mod < margin_van:
        return True
    if van_sz > 0 and mod_sz > int(van_sz * 1.5) and margin_mod < 512 * 1024:
        return True
    if (van_sz == 0 or mod_sz > van_sz) and margin_mod < 16 * 1024:
        return True
    return False


def inspect_archive(
    archive: ArchiveHandle,
    cfg: AppConfig,
    variant_prefix: str,
    enabled_standalone: List[StandaloneMod],
) -> PreflightReport:
    """Fast standard preflight check (exefs, versioned RESTBL, file overlaps, raw RESTBL overflow)."""
    _, exefs_hits = list_archive_variants(archive)
    report = PreflightReport(archive_path=archive.path, variant_prefix=variant_prefix, verdict="DROP_IN_SAFE")

    if exefs_hits:
        report.verdict = "UNSUPPORTED"
        report.warnings.append(
            f"Contains {len(exefs_hits)} exefs/ file(s) (subsdk / IPS code mod) — unsupported on stock Longshot."
        )
        for hit in exefs_hits:
            report.rows.append(FileCheckRow("EXEFS", hit, 0, 0, None, []))

    if not cfg.is_configured:
        raise RuntimeError("Base game romfs/ folder is not configured yet. Click 'Configure Folders' first.")
    codecs = cfg.get_codecs() or CodecBundle(cfg.romfs_dir)
    t_active = _load_active_restbl(cfg, codecs)

    existing_owners: Dict[str, List[str]] = {}
    existing_paths: Dict[str, List[Tuple[str, str]]] = {}
    merged_cands = []
    if cfg.target_mods_dir:
        merged_cands.append(os.path.join(cfg.target_mods_dir, "Merged_Zelda_Rando"))
    if cfg.live_mods_dir:
        merged_cands.append(os.path.join(cfg.live_mods_dir, "Merged_Zelda_Rando"))
    merged_dir = next((d for d in merged_cands if os.path.isdir(os.path.join(d, "romfs"))), "")
    if merged_dir:
        auto_marker_p = os.path.join(merged_dir, ".ootmodman_merged_bars.json")
        auto_marked: set[str] = set()
        if os.path.isfile(auto_marker_p):
            try:
                with open(auto_marker_p, "r", encoding="utf-8") as mf:
                    loaded = json.load(mf)
                if isinstance(loaded, list):
                    auto_marked = {str(p).replace("\\", "/") for p in loaded}
            except Exception:
                _LOG.debug("Could not parse %s", auto_marker_p, exc_info=True)
                auto_marked = set()
        for rel in cfg._walk_romfs_rel(merged_dir):
            rel_norm = rel.replace("\\", "/")
            if rel_norm in auto_marked:
                continue
            existing_owners.setdefault(rel_norm, []).append("Merged_Zelda_Rando")
            existing_paths.setdefault(rel_norm, []).append(
                ("Merged_Zelda_Rando", os.path.join(merged_dir, "romfs", *rel_norm.split("/")))
            )
    for mod in enabled_standalone:
        for rel in mod.rel_files:
            rel_norm = rel.replace("\\", "/")
            existing_owners.setdefault(rel_norm, []).append(mod.name)
            existing_paths.setdefault(rel_norm, []).append((mod.name, cfg.resolve_mod_file_path(mod, rel_norm)))

    romfs_prefix = f"{variant_prefix}/romfs/" if variant_prefix else "romfs/"
    has_rstb_111 = False
    has_rstb_old = False
    has_overlap = False
    has_over_restbl = False
    has_dec_err = False

    for norm in archive.list_files():
        if not norm.lower().startswith(romfs_prefix.lower()):
            continue
        rel = norm[len(romfs_prefix) :]
        if not rel:
            continue

        raw_bytes = archive.read_bytes(norm)
        decompress_err = False
        dec_bytes = raw_bytes
        if rel.endswith(".zs"):
            try:
                dec_bytes, _ = codecs.decompress_bytes(raw_bytes)
                msz = len(dec_bytes)
            except Exception:
                msz = len(raw_bytes)
                decompress_err = True
            canon_key = rel[:-3]
        else:
            msz = len(raw_bytes)
            canon_key = rel

        van_p = os.path.join(cfg.romfs_dir, *rel.split("/"))
        vsz = 0
        if os.path.isfile(van_p):
            if van_p.endswith(".zs"):
                try:
                    vsz = len(codecs.detect_zstd(van_p)[0])
                except Exception:
                    vsz = os.path.getsize(van_p)
            else:
                vsz = os.path.getsize(van_p)

        rsz = t_active.get_size(canon_key) if t_active else None
        overlaps = list(existing_owners.get(rel, []))
        margin_mod = (rsz - msz) if (rsz is not None and not decompress_err) else None

        if "ResourceSizeTable" in rel:
            if "Product.111" in rel:
                status = "RESTBL_111"
                has_rstb_111 = True
            else:
                status = "RESTBL_OLD"
                has_rstb_old = True
        else:
            flags: List[str] = []
            bars_auto_mergeable = False
            if overlaps and (not decompress_err) and rel.endswith(BARS_EXTS) and os.path.isfile(van_p):
                try:
                    base_raw, _ = read_bars_raw(van_p, codecs)
                    cand_raw = dec_bytes if rel.endswith(".zs") else raw_bytes
                    blobs = [("This Archive", cand_raw)]
                    for owner_name, owner_p in existing_paths.get(rel, []):
                        if os.path.isfile(owner_p):
                            blobs.append((owner_name, read_bars_raw(owner_p, codecs)[0]))
                    if len(blobs) >= 2:
                        ok_merge, _, _ = analyze_bars_compatibility(base_raw, blobs)
                        bars_auto_mergeable = ok_merge
                except Exception:
                    bars_auto_mergeable = False

            if decompress_err:
                flags.append("DECOMPRESS_ERR")
                has_dec_err = True
            if overlaps:
                if bars_auto_mergeable:
                    flags.append("AUTO_MERGE_BARS")
                else:
                    flags.append("OVERLAP")
                    has_overlap = True
            if (not decompress_err) and rsz is not None and rsz <= msz:
                flags.append("OVER_RESTBL")
                has_over_restbl = True
            status = "+".join(flags) if flags else "OK"

        report.rows.append(
            FileCheckRow(
                status=status,
                rel_path=rel,
                mod_size=msz,
                van_size=vsz,
                restbl_size=rsz,
                overlap_with=overlaps,
                margin_mod=margin_mod,
                margin_van=None,
                is_subfile=False,
            )
        )

    if has_rstb_111:
        report.warnings.append(
            "Ships a v1.1.1 ResourceSizeTable — dropping directly into mods/ will clobber Merged_Zelda_Rando's RESTBL."
        )
    if has_rstb_old:
        report.warnings.append(
            "Ships a non-1.1.1 ResourceSizeTable (e.g. Product.100) — ignored by Longshot 1.1.1, so its size bumps will not apply."
        )
    if has_dec_err:
        report.warnings.append(
            "Failed to decompress one or more .zs files — reported size is raw compressed bytes and RESTBL checks are unreliable."
        )
    if has_overlap:
        report.warnings.append(
            "Overlaps one or more files in Merged_Zelda_Rando or an enabled standalone mod."
        )
    if has_over_restbl:
        report.warnings.append(
            "One or more files exceed the active RESTBL allocation and risk crashing without a RESTBL bump."
        )

    if report.verdict != "UNSUPPORTED":
        if has_rstb_111 or has_rstb_old or has_dec_err or has_overlap or has_over_restbl:
            report.verdict = "NEEDS_ATTENTION"
        elif not report.rows:
            report.verdict = "NEEDS_ATTENTION"
            report.warnings.append("No romfs/ files found under the selected variant.")

    return report


def run_advanced_checks(
    archive: ArchiveHandle,
    cfg: AppConfig,
    variant_prefix: str,
    report: PreflightReport,
) -> PreflightReport:
    """Deep preflight pass checking tight margins, internal SARC subfiles, and bundled v1.1.1 RESTBLs."""
    if report.advanced_ran:
        return report

    if not cfg.is_configured:
        raise RuntimeError("Base game romfs/ folder is not configured yet. Click 'Configure Folders' first.")
    codecs = cfg.get_codecs() or CodecBundle(cfg.romfs_dir)
    t_active = _load_active_restbl(cfg, codecs)
    t_van = _load_vanilla_restbl(cfg, codecs)
    romfs_prefix = f"{variant_prefix}/romfs/" if variant_prefix else "romfs/"

    archive_rel_map: Dict[str, str] = {}
    bundled_rstb_entry: Optional[str] = None
    for norm in archive.list_files():
        if norm.lower().startswith(romfs_prefix.lower()):
            rel = norm[len(romfs_prefix) :]
            archive_rel_map[rel] = norm
            if "ResourceSizeTable.Product.111" in rel and rel.endswith(".rsizetable.zs"):
                bundled_rstb_entry = norm

    t_bundled = None
    if bundled_rstb_entry:
        try:
            t_bundled = restbl.ResourceSizeTable.from_binary(
                codecs.decompress_bytes(archive.read_bytes(bundled_rstb_entry))[0]
            )
        except Exception:
            _LOG.debug("Could not parse bundled RESTBL %s", bundled_rstb_entry, exc_info=True)
            t_bundled = None

    tight_loose = 0
    bundled_tight = 0
    sub_over = 0
    sub_tight = 0
    subfile_rows: List[FileCheckRow] = []

    for row in list(report.rows):
        if row.is_subfile or row.status in ("EXEFS", "RESTBL_111", "RESTBL_OLD") or "DECOMPRESS_ERR" in row.status:
            continue

        canon_key = row.rel_path[:-3] if row.rel_path.endswith(".zs") else row.rel_path
        van_rsz = t_van.get_size(canon_key) if t_van else None
        row.margin_van = (van_rsz - row.van_size) if (van_rsz is not None and row.van_size > 0) else None
        row.margin_mod = (row.restbl_size - row.mod_size) if row.restbl_size is not None else None

        # 1. Loose file tight-margin check (also stacks onto OVERLAP rows).
        if "OVER_RESTBL" not in row.status and _is_tight_margin(row.mod_size, row.van_size, row.margin_mod, row.margin_van):
            row.status = "TIGHT_MARGIN" if row.status == "OK" else f"{row.status}+TIGHT"
            tight_loose += 1

        if t_bundled is not None:
            b_rsz = t_bundled.get_size(canon_key)
            if b_rsz is not None:
                b_margin = b_rsz - row.mod_size
                if b_margin <= 0 or _is_tight_margin(row.mod_size, row.van_size, b_margin, row.margin_van):
                    bundled_tight += 1

        # 2. Deep SARC inspection for .pack / .sarc / .blarc containers.
        if row.rel_path.endswith(SARC_EXTS) and row.rel_path in archive_rel_map:
            try:
                raw_arc = archive.read_bytes(archive_rel_map[row.rel_path])
                if row.rel_path.endswith(".zs"):
                    sarc_bytes, _ = codecs.decompress_bytes(raw_arc)
                else:
                    sarc_bytes = raw_arc
                mod_sarc = oead.Sarc(sarc_bytes)
            except Exception:
                _LOG.debug("Could not inspect SARC %s", row.rel_path, exc_info=True)
                continue

            van_sub_sizes: Dict[str, int] = {}
            van_arc_p = os.path.join(cfg.romfs_dir, *row.rel_path.split("/"))
            if os.path.isfile(van_arc_p):
                try:
                    van_sarc_bytes, _ = read_maybe_zstd(van_arc_p, codecs)
                    for vf in oead.Sarc(van_sarc_bytes).get_files():
                        vdata = bytes(vf.data)
                        if vf.name.endswith(".zs"):
                            try:
                                vdata, _ = codecs.decompress_bytes(vdata)
                            except Exception:
                                _LOG.debug("Could not decompress vanilla subfile %s", vf.name, exc_info=True)
                        van_sub_sizes[vf.name] = len(vdata)
                except Exception:
                    _LOG.debug("Could not read vanilla SARC %s", van_arc_p, exc_info=True)

            for entry in mod_sarc.get_files():
                report.subfiles_scanned += 1
                mdata = bytes(entry.data)
                if entry.name.endswith(".zs"):
                    try:
                        mdata, _ = codecs.decompress_bytes(mdata)
                    except Exception:
                        _LOG.debug("Could not decompress mod subfile %s", entry.name, exc_info=True)
                    sub_key = entry.name[:-3]
                else:
                    sub_key = entry.name

                sub_msz = len(mdata)
                sub_vsz = van_sub_sizes.get(entry.name, 0)
                sub_rsz = t_active.get_size(sub_key) if t_active else None
                sub_v_rsz = t_van.get_size(sub_key) if t_van else None
                sub_m_mod = (sub_rsz - sub_msz) if sub_rsz is not None else None
                sub_m_van = (sub_v_rsz - sub_vsz) if (sub_v_rsz is not None and sub_vsz > 0) else None

                if sub_rsz is not None and sub_rsz <= sub_msz:
                    sub_status = "SUB_OVER"
                    sub_over += 1
                elif _is_tight_margin(sub_msz, sub_vsz, sub_m_mod, sub_m_van):
                    sub_status = "SUB_TIGHT"
                    sub_tight += 1
                else:
                    sub_status = "SUB_OK"

                if sub_status != "SUB_OK" or (sub_msz != sub_vsz and sub_rsz is not None):
                    subfile_rows.append(
                        FileCheckRow(
                            status=sub_status,
                            rel_path=f"{row.rel_path} :: {entry.name}",
                            mod_size=sub_msz,
                            van_size=sub_vsz,
                            restbl_size=sub_rsz,
                            overlap_with=[],
                            margin_mod=sub_m_mod,
                            margin_van=sub_m_van,
                            is_subfile=True,
                        )
                    )

    report.rows.extend(subfile_rows)

    if tight_loose:
        report.advanced_warnings.append(
            f"{tight_loose} loose file(s) have tighter RESTBL headroom than vanilla (risk of crash without headroom bump)."
        )
    if sub_over:
        report.advanced_warnings.append(
            f"{sub_over} SARC internal subfile(s) exceed active RESTBL limits."
        )
    if sub_tight:
        report.advanced_warnings.append(
            f"{sub_tight} SARC internal subfile(s) have tighter RESTBL headroom than vanilla."
        )
    if bundled_tight:
        report.advanced_warnings.append(
            f"Archive's own bundled v1.1.1 RESTBL under-allocates {bundled_tight} modified file(s) compared to vanilla headroom."
        )

    if report.verdict == "DROP_IN_SAFE" and (tight_loose or sub_over or sub_tight):
        report.verdict = "NEEDS_ATTENTION"

    report.advanced_ran = True
    return report


def sanitize_mod_name(raw_name: str, *, max_len: int = 64) -> str:
    "Sanitize an archive-derived mod name into a safe, bounded cross-platform folder name."
    from oot_rando.path_safety import sanitize_portable_name
    return sanitize_portable_name(raw_name, default="Imported_Mod", max_len=max_len)


def install_archive_to_dir(
    archive: ArchiveHandle,
    variant_prefix: str,
    mod_name: str,
    parent_dir: str,
) -> str:
    """Extract the chosen archive variant cleanly into ``parent_dir/<safe_name>/``.

    Normalizes any ``RomFS/`` casing to lowercase ``romfs/`` (preventing split folders
    on case-sensitive Linux filesystems) and rejects archive path-traversal entries.
    """
    from oot_rando.path_safety import MOD_ROMFS_HEADROOM, fs_path, validate_file_path, validate_path_headroom
    safe_name = sanitize_mod_name(mod_name)
    validate_path_headroom(parent_dir, max_relative_len=MOD_ROMFS_HEADROOM, label="Mod destination folder", enforce_win_classic=False)
    dst_root = os.path.abspath(os.path.join(parent_dir, safe_name))
    _remove_path(dst_root)
    os.makedirs(fs_path(os.path.join(dst_root, "romfs")), exist_ok=True)

    prefix_with_slash = f"{variant_prefix}/" if variant_prefix else ""
    prefix_low = prefix_with_slash.lower()

    for norm in archive.list_files():
        if prefix_low and not norm.lower().startswith(prefix_low):
            continue
        rel_inside = norm[len(prefix_with_slash) :]
        if not rel_inside:
            continue
        parts = [p for p in rel_inside.split("/") if p]
        if not parts or any(p in (".", "..") or ":" in p for p in parts):
            continue

        # Normalize RomFS/ROMFS top-level folder casing to lowercase romfs/ on Linux.
        if parts[0].lower() == "romfs" and len(parts) > 1:
            parts[0] = "romfs"
        elif len(parts) > 1:
            continue

        target = os.path.abspath(os.path.join(dst_root, *parts))
        if not _is_within_dir(dst_root, target):
            continue
        validate_file_path(target, label="Extracted mod file")
        os.makedirs(fs_path(os.path.dirname(target)), exist_ok=True)
        with open(fs_path(target), "wb") as f_out:
            f_out.write(archive.read_bytes(norm))
    return dst_root


def install_archive_variant(
    archive: ArchiveHandle,
    variant_prefix: str,
    mod_name: str,
    cfg: AppConfig,
) -> str:
    """Extract the chosen archive variant into ``cfg.staged_mods_dir/<safe_name>/``."""
    return install_archive_to_dir(archive, variant_prefix, mod_name, cfg.staged_mods_dir)
