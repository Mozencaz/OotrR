"""Stringent 3-tier duplicate mod detector for Midna's Devotion.

Tier 1 — Exact Content Fingerprint (CRC32 per file + SHA-256 tree manifest hash)
Tier 2 — Normalized & Fuzzy Name / Version Matching
Tier 3 — High Asset-Overlap Detection (file-set Jaccard overlap + changed-file diff)
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from oot_rando.midnas_devotion.core.config import (
    AppConfig,
    MANAGED_MOD_NAMES,
    StandaloneMod,
    _norm_path_key,
)

DEFAULT_FUZZY_THRESHOLD = 0.82
DEFAULT_OVERLAP_THRESHOLD = 0.75

_STRIP_SUFFIX_TOKENS = {
    "v", "ver", "version", "rev", "r", "final", "fixed", "fix",
    "update", "updated", "repack", "longshot", "hookshot", "oot", "mod",
}
_VERSION_TOKEN_RE = re.compile(r"^(?:v|ver|rev|r)?[0-9]+(?:[.][0-9]+)*(?:[a-z])?$", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_DIR_FP_CACHE: Dict[Tuple[str, int, int, int], "ModFingerprint"] = {}


@dataclass(frozen=True)
class ModFingerprint:
    """Content & name signature of a mod folder or archive variant."""

    display_name: str
    normalized_name: str
    tree_sha256: str
    file_crcs: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    source_path: str = ""

    @property
    def file_count(self) -> int:
        return len(self.file_crcs)

    @property
    def total_bytes(self) -> int:
        return sum(sz for sz, _ in self.file_crcs.values())


@dataclass(frozen=True)
class ExistingModTarget:
    """An installed, staged, linked, or library mod to check candidates against."""

    name: str
    path: str
    origin: str


@dataclass(frozen=True)
class DuplicateMatch:
    """Structured match result from the 3-tier duplicate mod checker."""

    tier: int
    kind: str
    existing_name: str
    existing_path: str
    existing_origin: str
    name_similarity: float
    overlap_ratio: float
    shared_files: int
    identical_files: int
    changed_files: int
    candidate_files: int
    existing_files: int


def normalize_mod_name(raw_name: str) -> str:
    """Normalize a mod name by stripping separators, punctuation, and version/repack suffixes."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(raw_name or "").strip())
    s = _NON_ALNUM_RE.sub(" ", s.lower()).strip()
    if not s:
        return ""
    tokens = s.split()
    kept: List[str] = []
    for tok in tokens:
        if _VERSION_TOKEN_RE.match(tok):
            continue
        if tok in _STRIP_SUFFIX_TOKENS:
            continue
        kept.append(tok)
    return " ".join(kept) if kept else " ".join(tokens)


def name_similarity(name_a: str, name_b: str) -> float:
    """Compute normalized name similarity in [0.0, 1.0]."""
    na = normalize_mod_name(name_a)
    nb = normalize_mod_name(name_b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq_ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ta = set(na.split())
    tb = set(nb.split())
    tok_jaccard = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    return max(seq_ratio, tok_jaccard)


def _compute_tree_sha256(file_crcs: Dict[str, Tuple[int, int]]) -> str:
    h = hashlib.sha256()
    for rel in sorted(file_crcs.keys()):
        sz, crc = file_crcs[rel]
        h.update(f"{rel}|{sz}|{crc:08x}\n".encode("utf-8"))
    return h.hexdigest()


def _crc32_file(path: str, chunk_size: int = 131072) -> Tuple[int, int]:
    crc = 0
    total = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            total += len(buf)
            crc = zlib.crc32(buf, crc)
    return total, (crc & 0xFFFFFFFF)


def _locate_romfs_root(mod_dir: str) -> Optional[str]:
    if not mod_dir or not os.path.isdir(mod_dir):
        return None
    direct = os.path.join(mod_dir, "romfs")
    if os.path.isdir(direct):
        return direct
    try:
        for entry in os.listdir(mod_dir):
            if entry.lower() == "romfs" and os.path.isdir(os.path.join(mod_dir, entry)):
                return os.path.join(mod_dir, entry)
    except OSError:
        return None
    if os.path.basename(mod_dir).lower() == "romfs":
        return mod_dir
    return None


def fingerprint_mod_dir(mod_dir: str, *, display_name: Optional[str] = None) -> ModFingerprint:
    """Build (or retrieve cached) CRC32/SHA-256 fingerprint for a mod folder on disk."""
    abs_dir = os.path.abspath(os.path.expanduser(mod_dir))
    name = display_name if display_name is not None else os.path.basename(abs_dir)
    romfs_root = _locate_romfs_root(abs_dir)
    if not romfs_root:
        return ModFingerprint(
            display_name=name,
            normalized_name=normalize_mod_name(name),
            tree_sha256="",
            file_crcs={},
            source_path=abs_dir,
        )

    files: List[Tuple[str, str, int, int]] = []
    total_bytes = 0
    newest_mtime_ns = 0
    for root, _dirs, fns in os.walk(romfs_root):
        for fn in fns:
            full = os.path.join(root, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, romfs_root).replace(os.sep, "/").lower()
            total_bytes += st.st_size
            if st.st_mtime_ns > newest_mtime_ns:
                newest_mtime_ns = st.st_mtime_ns
            files.append((rel, full, st.st_size, st.st_mtime_ns))

    cache_key = (_norm_path_key(abs_dir), len(files), total_bytes, newest_mtime_ns)
    cached = _DIR_FP_CACHE.get(cache_key)
    if cached is not None:
        if cached.display_name == name:
            return cached
        return ModFingerprint(
            display_name=name,
            normalized_name=normalize_mod_name(name),
            tree_sha256=cached.tree_sha256,
            file_crcs=cached.file_crcs,
            source_path=abs_dir,
        )

    file_crcs: Dict[str, Tuple[int, int]] = {}
    for rel, full, _sz, _mt in files:
        try:
            file_crcs[rel] = _crc32_file(full)
        except OSError:
            continue

    fp = ModFingerprint(
        display_name=name,
        normalized_name=normalize_mod_name(name),
        tree_sha256=_compute_tree_sha256(file_crcs) if file_crcs else "",
        file_crcs=file_crcs,
        source_path=abs_dir,
    )
    _DIR_FP_CACHE[cache_key] = fp
    return fp


def fingerprint_archive_variant(
    archive,
    variant_prefix: str,
    *,
    display_name: str,
) -> ModFingerprint:
    """Compute CRC32/SHA-256 fingerprint directly from an open ArchiveHandle variant."""
    prefix_with_slash = f"{variant_prefix}/" if variant_prefix else ""
    prefix_low = prefix_with_slash.lower()
    file_crcs: Dict[str, Tuple[int, int]] = {}

    for norm in archive.list_files():
        if prefix_low and not norm.lower().startswith(prefix_low):
            continue
        rel_inside = norm[len(prefix_with_slash) :]
        parts = [p for p in rel_inside.split("/") if p]
        if len(parts) < 2 or parts[0].lower() != "romfs":
            continue
        rel_romfs = "/".join(parts[1:]).lower()
        data = archive.read_bytes(norm)
        file_crcs[rel_romfs] = (len(data), zlib.crc32(data) & 0xFFFFFFFF)

    return ModFingerprint(
        display_name=display_name,
        normalized_name=normalize_mod_name(display_name),
        tree_sha256=_compute_tree_sha256(file_crcs) if file_crcs else "",
        file_crcs=file_crcs,
        source_path="",
    )


def collect_existing_mod_targets(
    cfg: AppConfig,
    standalone_mods: Optional[Sequence[StandaloneMod]] = None,
) -> List[ExistingModTarget]:
    """Collect all known live, staged, linked, and library mods (deduplicated by path)."""
    targets: List[ExistingModTarget] = []
    seen: set[str] = set()

    def _add(name: str, path: str, origin: str) -> None:
        if not path or not os.path.isdir(path):
            return
        if name in MANAGED_MOD_NAMES or name.startswith("OoT_Randomizer_"):
            return
        key = _norm_path_key(path)
        if key in seen:
            return
        seen.add(key)
        targets.append(ExistingModTarget(name=name, path=os.path.abspath(path), origin=origin))

    mods_seq = standalone_mods if standalone_mods is not None else cfg.scan_standalone_mods()
    for m in mods_seq:
        _add(m.name, m.source_path, m.origin)

    if cfg.backup_dir and os.path.isdir(cfg.backup_dir):
        try:
            for entry in sorted(os.listdir(cfg.backup_dir)):
                full = os.path.join(cfg.backup_dir, entry)
                if os.path.isdir(full) and _locate_romfs_root(full):
                    _add(entry, full, "library")
        except OSError:
            pass

    return targets


def check_mod_duplicates(
    candidate: ModFingerprint,
    existing_targets: Iterable[ExistingModTarget],
    *,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> List[DuplicateMatch]:
    """Run all 3 duplicate checks against existing mods and return prioritized matches."""
    cand_key = _norm_path_key(candidate.source_path) if candidate.source_path else ""
    cand_files = set(candidate.file_crcs.keys())
    matches: List[DuplicateMatch] = []

    for tgt in existing_targets:
        if cand_key and _norm_path_key(tgt.path) == cand_key:
            continue
        efp = fingerprint_mod_dir(tgt.path, display_name=tgt.name)
        ex_files = set(efp.file_crcs.keys())

        nsim = name_similarity(candidate.display_name, tgt.name)
        union = cand_files | ex_files
        shared = cand_files & ex_files
        overlap = (len(shared) / len(union)) if union else 0.0
        identical = sum(1 for r in shared if candidate.file_crcs[r] == efp.file_crcs[r])
        changed = len(shared) - identical

        if candidate.tree_sha256 and efp.tree_sha256 and candidate.tree_sha256 == efp.tree_sha256:
            matches.append(
                DuplicateMatch(
                    tier=1,
                    kind="EXACT_CONTENT",
                    existing_name=tgt.name,
                    existing_path=tgt.path,
                    existing_origin=tgt.origin,
                    name_similarity=nsim,
                    overlap_ratio=1.0,
                    shared_files=len(shared),
                    identical_files=identical,
                    changed_files=0,
                    candidate_files=len(cand_files),
                    existing_files=len(ex_files),
                )
            )
            continue

        if cand_files and ex_files and overlap >= overlap_threshold:
            matches.append(
                DuplicateMatch(
                    tier=3,
                    kind="HIGH_OVERLAP",
                    existing_name=tgt.name,
                    existing_path=tgt.path,
                    existing_origin=tgt.origin,
                    name_similarity=nsim,
                    overlap_ratio=overlap,
                    shared_files=len(shared),
                    identical_files=identical,
                    changed_files=changed,
                    candidate_files=len(cand_files),
                    existing_files=len(ex_files),
                )
            )
            continue

        if nsim >= fuzzy_threshold:
            matches.append(
                DuplicateMatch(
                    tier=2,
                    kind="SIMILAR_NAME",
                    existing_name=tgt.name,
                    existing_path=tgt.path,
                    existing_origin=tgt.origin,
                    name_similarity=nsim,
                    overlap_ratio=overlap,
                    shared_files=len(shared),
                    identical_files=identical,
                    changed_files=changed,
                    candidate_files=len(cand_files),
                    existing_files=len(ex_files),
                )
            )

    priority = {"EXACT_CONTENT": 0, "HIGH_OVERLAP": 1, "SIMILAR_NAME": 2}
    matches.sort(
        key=lambda m: (priority.get(m.kind, 9), -m.overlap_ratio, -m.name_similarity, m.existing_name.lower())
    )
    return matches


def find_internal_duplicates(standalone_mods: Sequence[StandaloneMod]) -> Dict[str, List[str]]:
    """Return {mod_name: [other_mod_names]} for mods with identical CRC32/SHA-256 content trees."""
    by_hash: Dict[str, List[str]] = {}
    for m in standalone_mods:
        fp = fingerprint_mod_dir(m.source_path, display_name=m.name)
        if not fp.tree_sha256:
            continue
        by_hash.setdefault(fp.tree_sha256, []).append(m.name)

    dupes: Dict[str, List[str]] = {}
    for names in by_hash.values():
        if len(names) < 2:
            continue
        for n in names:
            dupes[n] = [o for o in names if o != n]
    return dupes


def format_duplicate_summary(matches: Sequence[DuplicateMatch], max_items: int = 4) -> str:
    """Format duplicate matches into concise bullet lines for dialogs."""
    origin_labels = {
        "live": "Live Mods",
        "staged": "Staged Mods",
        "linked": "Linked Folder",
        "library": "User Mod Library",
    }
    lines: List[str] = []
    for m in list(matches)[:max_items]:
        orig = origin_labels.get(m.existing_origin, m.existing_origin)
        if m.kind == "EXACT_CONTENT":
            tag = f"Exact Content Duplicate (CRC32/SHA-256 match, {m.existing_files} files)"
        elif m.kind == "HIGH_OVERLAP":
            pct = int(round(m.overlap_ratio * 100))
            tag = (
                f"Likely Update / Variant ({pct}% file overlap: "
                f"{m.identical_files} identical, {m.changed_files} changed; "
                f"new {m.candidate_files} vs existing {m.existing_files} files)"
            )
        else:
            pct = int(round(m.name_similarity * 100))
            tag = f"Similar Name ({pct}% match, {m.shared_files} shared file(s))"
        lines.append(f"• {m.existing_name}  [{orig}] — {tag}")
    if len(matches) > max_items:
        lines.append(f"… and {len(matches) - max_items} more match(es)")
    return "\n".join(lines)
