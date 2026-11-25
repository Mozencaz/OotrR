"""Seed/party health diagnostics and non-destructive preflight checks for mods/ operations."""
import json
import logging
import os
from pathlib import Path
import shutil
import uuid

from oot_rando.randomizer.randomizer_services import read_artifact

_LOG = logging.getLogger(__name__)


def preflight_mods_operation(
    target_mods,
    *,
    required_bytes=256 * 1024 * 1024,
    min_error_bytes=32 * 1024 * 1024,
    source_paths=(),
):
    """Verify write access, free disk space, source archives, and read-only locks before modifying mods/."""
    target = Path(target_mods)
    warnings = []
    errors = []
    free_bytes = None

    check_dir = target if target.exists() else target.parent
    if not check_dir.exists():
        errors.append("Target directory does not exist: " + str(target))
    else:
        try:
            usage = shutil.disk_usage(check_dir)
            free_bytes = int(usage.free)
            if free_bytes < min_error_bytes:
                errors.append(
                    "Critically low disk space (" + str(free_bytes // (1024 * 1024)) + " MB free) at " + str(check_dir)
                )
            elif free_bytes < required_bytes:
                warnings.append(
                    "Low disk space (" + str(free_bytes // (1024 * 1024)) + " MB free; recommended "
                    + str(required_bytes // (1024 * 1024)) + " MB)"
                )
        except OSError as exc:
            warnings.append("Unable to check disk space: " + str(exc))

        if target.is_dir():
            probe = target / (".oot-preflight-" + uuid.uuid4().hex + ".tmp")
            try:
                probe.write_bytes(b"ok")
                probe.unlink(missing_ok=True)
            except OSError as exc:
                errors.append("Mods directory is not writable: " + str(exc))

            merged = target / "Merged_Zelda_Rando"
            if merged.is_dir():
                try:
                    for entry in list(merged.iterdir())[:20]:
                        if not os.access(entry, os.W_OK):
                            warnings.append("Read-only item inside Merged_Zelda_Rando: " + entry.name)
                            break
                except OSError as exc:
                    warnings.append("Cannot inspect Merged_Zelda_Rando: " + str(exc))

    for src in source_paths:
        p = Path(src)
        if not p.exists():
            errors.append("Missing source archive or folder: " + str(p))
        elif not os.access(p, os.R_OK):
            errors.append("Unreadable source archive or folder: " + str(p))

    ok = len(errors) == 0
    summary = (
        "Preflight " + ("OK" if ok else "FAILED")
        + " for " + str(target)
        + " (errors=" + str(len(errors))
        + ", warnings=" + str(len(warnings))
        + (", free_mb=" + str(free_bytes // (1024 * 1024)) if free_bytes is not None else "")
        + ")"
    )
    _LOG.info("%s", summary)
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "free_bytes": free_bytes,
        "summary": summary,
    }


def check_party_health(library, ident, *, stage_root=None):
    """Inspect a party bundle, manifest, checks, saves, archived merge, and live mods state."""
    checks = []

    def add(level, code, message):
        checks.append({"level": level, "code": code, "message": message})

    try:
        party = library.get(ident)
    except Exception as exc:
        add("error", "party_meta", "Cannot load party metadata: " + str(exc))
        return {"ok": False, "party_id": ident, "name": "", "active": False, "checks": checks}

    active = getattr(library, "active_id", None) == ident
    seed_dir = library.bundle(party) / "seed"
    if not seed_dir.is_dir():
        add("error", "seed_missing", "Party seed snapshot folder is missing.")
    else:
        try:
            manifest, _ = read_artifact(seed_dir)
            if manifest.get("seed_id") != party.get("seed_id"):
                add("error", "seed_mismatch", "Snapshot manifest seed_id does not match party.json.")
            else:
                add("ok", "manifest", "Manifest verified (" + str(party.get("seed_id"))[:12] + ").")
        except Exception as exc:
            add("error", "manifest_invalid", "Invalid seed manifest: " + str(exc))
        if (seed_dir / "tracking.json").is_file():
            add("ok", "tracking_file", "tracking.json present.")
        elif (seed_dir / "checks.json").is_file():
            add("ok", "checks_file", "checks.json present.")
        else:
            add("warn", "checks_missing", "tracking.json / checks.json missing from seed snapshot.")

    mods_dir = Path(party["mods"])
    if not mods_dir.is_dir():
        add("warn", "mods_missing", "Target mods folder not found: " + str(mods_dir))
    elif not os.access(mods_dir, os.W_OK):
        add("error", "mods_readonly", "Target mods folder is not writable: " + str(mods_dir))
    else:
        add("ok", "mods_dir", "Target mods folder available.")
        if active:
            live_merged = mods_dir / "Merged_Zelda_Rando"
            live_seed = mods_dir / party["mod_name"]
            if live_merged.is_dir():
                add("ok", "live_merged", "Merged_Zelda_Rando is active in mods/.")
            elif live_seed.is_dir():
                add("ok", "live_seed", "Raw seed folder is active in mods/.")
            else:
                add("warn", "live_missing", "Neither Merged_Zelda_Rando nor raw seed folder is in mods/.")

    live_saves = Path(party["saves"])
    snap_saves = library.bundle(party) / "save"
    if active:
        if not live_saves.is_dir():
            add("warn", "saves_missing", "Active save folder not found: " + str(live_saves))
        else:
            sav_files = list(live_saves.rglob("*.sav"))
            if sav_files:
                add("ok", "saves_present", "Found " + str(len(sav_files)) + " live save file(s).")
            elif snap_saves.is_dir() and list(snap_saves.rglob("*.sav")):
                add("warn", "saves_snapshot_only", "Live save folder is empty (snapshot backup still has saves).")
            else:
                add("ok", "saves_empty", "Live save folder exists (no .sav written yet).")
    else:
        if not snap_saves.is_dir():
            add("warn", "saves_missing", "Party snapshot save folder missing.")
        else:
            sav_files = list(snap_saves.rglob("*.sav"))
            if sav_files:
                add("ok", "saves_present", "Found " + str(len(sav_files)) + " archived save file(s).")
            else:
                add("ok", "saves_empty", "Archived save folder exists (not started yet).")

    arch_root = library.folder(ident) / "midna_merged"
    arch_merged = arch_root / "Merged_Zelda_Rando"
    arch_meta = arch_root / "meta.json"
    if arch_merged.is_dir():
        try:
            meta = json.loads(arch_meta.read_text(encoding="utf-8")) if arch_meta.is_file() else {}
            if meta.get("seed_id") == party.get("seed_id"):
                add("ok", "archived_merge", "Archived Merged_Zelda_Rando ready for auto-restore.")
            else:
                add("warn", "archived_merge_stale", "Archived Merged_Zelda_Rando seed_id does not match party.")
        except Exception:
            add("warn", "archived_merge_corrupt", "Archived Merged_Zelda_Rando metadata is unreadable.")

    if stage_root is not None:
        sr = Path(stage_root)
        if sr.is_dir():
            leftover = [p.name for p in sr.iterdir() if p.is_dir() and not p.name.startswith(".")]
            if leftover:
                add("warn", "staged_leftovers", "Staged mods awaiting re-merge: " + ", ".join(sorted(leftover)))

    ok = not any(c["level"] == "error" for c in checks)
    return {
        "ok": ok,
        "party_id": ident,
        "name": party.get("name") or "",
        "active": active,
        "checks": checks,
    }
