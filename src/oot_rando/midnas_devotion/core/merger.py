"""Build orchestrator for assembling ``Merged_Zelda_Rando`` and syncing standalone mods.

Executes an 8-stage pipeline:
  1. Character mod base layer
  2. Randomizer seed overlay
  3. Ordered visual / UI / model integration (BLARC + BNTX N-way merges)
  4. Havok cloth stripping for character-swapped NPCs
  5. N-way Mals dialogue archive merging across all present locales
  6. RESTBL merging and safety headroom bumps (+20 MB for oversized BFRES models)
  7. Standalone drop-in mod sync (Sandbox copy vs. Live move)
  8. Shared BGM / ``.bars`` 3-way auto-merging with original-file stashing
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import oead
import restbl

from oot_rando.midnas_devotion.core.config import (
    AppConfig,
    RSTB_REL,
    StandaloneMod,
    UI_MERGE_EXTS,
    _norm_path_key,
)
from oot_rando.midnas_devotion.core.formats import (
    BARS_EXTS,
    CodecBundle,
    merge_bars_files,
    merge_blarc_layers,
    merge_bntx_layers,
    merge_restbl_from_mod,
    patch_npc_cloth,
    read_maybe_zstd,
    write_maybe_zstd,
)

_LOG = logging.getLogger(__name__)


def _remove_path(path: str) -> None:
    "Remove a directory, file, or symlink (including broken symlinks) safely."
    from oot_rando.path_safety import fs_path
    fp = fs_path(path)
    if os.path.islink(path) or os.path.islink(fp) or os.path.isfile(fp):
        os.unlink(fp)
    elif os.path.isdir(fp):
        shutil.rmtree(fp)


@dataclass
class BuildOptions:
    """User-selected layers and feature toggles for a single ``run_build`` pass."""

    char_path: Optional[str] = None
    rando_path: Optional[str] = None
    prefer_rando_logo: bool = False
    enabled_standalone_names: List[str] = field(default_factory=list)
    auto_merge_bars: bool = True


def _sync_standalone_mods(
    cfg: AppConfig,
    all_mods: List[StandaloneMod],
    standalone_enabled_names: List[str],
    core_merged_names: set[str],
    log: Callable[[str], None],
) -> None:
    """Mirror enabled pure-standalone mods into Sandbox or move them between Live/Staged/Disabled."""
    enabled_set = set(standalone_enabled_names)
    os.makedirs(cfg.target_mods_dir, exist_ok=True)

    if cfg.sandbox_mode:
        for mod in all_mods:
            dst = os.path.join(cfg.sandbox_mods_dir, mod.name)
            if mod.name in enabled_set and mod.name not in core_merged_names:
                _remove_path(dst)
                shutil.copytree(mod.source_path, dst)
                bkp_dir = os.path.join(cfg.bars_originals_dir, mod.name)
                if os.path.isdir(bkp_dir):
                    for root, _, files in os.walk(bkp_dir):
                        for fn in files:
                            src_b = os.path.join(root, fn)
                            rel_b = os.path.relpath(src_b, bkp_dir)
                            dst_b = os.path.join(dst, "romfs", rel_b)
                            os.makedirs(os.path.dirname(dst_b), exist_ok=True)
                            shutil.copy2(src_b, dst_b)
                log(f"   [sandbox] Enabled standalone mod: {mod.name}")
            else:
                if os.path.exists(dst) or os.path.islink(dst):
                    _remove_path(dst)
                    log(f"   [sandbox] Removed duplicate/disabled folder: {mod.name}")
        return

    os.makedirs(cfg.disabled_mods_dir, exist_ok=True)
    os.makedirs(cfg.staged_mods_dir, exist_ok=True)
    for mod in all_mods:
        if mod.origin == "linked":
            continue
        live_p = os.path.join(cfg.live_mods_dir, mod.name)
        dis_p = os.path.join(cfg.disabled_mods_dir, mod.name)

        # Core-merged mods live inside Merged_Zelda_Rando; don't leave a colliding duplicate folder in live mods/.
        if mod.name in core_merged_names:
            if os.path.isdir(live_p):
                staged_p = os.path.join(cfg.staged_mods_dir, mod.name)
                _remove_path(staged_p)
                shutil.move(live_p, staged_p)
                log(f"   [live] Moved core-merged mod out of live mods/ -> staged_mods/: {mod.name}")
            continue

        if mod.name in enabled_set:
            if os.path.isdir(live_p):
                log(f"   [live] Kept active standalone mod: {mod.name}")
            elif os.path.isdir(dis_p):
                shutil.move(dis_p, live_p)
                log(f"   [live] Re-enabled standalone mod: {mod.name}")
            else:
                shutil.copytree(mod.source_path, live_p)
                log(f"   [live] Installed staged standalone mod: {mod.name}")
        else:
            if os.path.isdir(live_p):
                _remove_path(dis_p)
                shutil.move(live_p, dis_p)
                log(f"   [live] Moved disabled standalone mod to disabled_mods/: {mod.name}")


def _auto_merge_shared_bars(
    cfg: AppConfig,
    merged_dir: str,
    enabled_standalone_names: List[str],
    codecs: CodecBundle,
    log: Callable[[str], None],
) -> List[str]:
    """3-way merge any ``.bars``/``.bars.zs`` files shared by 2+ active mods into ``Merged_Zelda_Rando``.

    Updates RESTBL headroom for each merged archive and stashes (Live) or removes (Sandbox)
    duplicate ``.bars`` files from individual standalone mods so the merged table takes effect.
    """
    bars_owners: Dict[str, List[Tuple[str, str]]] = {}

    merged_romfs = os.path.join(merged_dir, "romfs")
    if os.path.isdir(merged_romfs):
        for rel in cfg._walk_romfs_rel(merged_dir):
            if rel.endswith(BARS_EXTS):
                bars_owners.setdefault(rel, []).append(("Merged_Zelda_Rando", os.path.join(merged_romfs, *rel.split("/"))))

    for mod_name in enabled_standalone_names:
        mod_dir = os.path.join(cfg.target_mods_dir, mod_name)
        if not os.path.isdir(os.path.join(mod_dir, "romfs")):
            continue
        for rel in cfg._walk_romfs_rel(mod_dir):
            if rel.endswith(BARS_EXTS):
                bars_owners.setdefault(rel, []).append((mod_name, os.path.join(mod_dir, "romfs", *rel.split("/"))))

    merged_bars_rels: List[str] = []
    restbl_bumps: Dict[str, Tuple[int, int]] = {}

    for rel, sources in sorted(bars_owners.items()):
        if len(sources) < 2:
            continue
        rel_parts = rel.split("/")
        van_p = os.path.join(cfg.romfs_dir, *rel_parts)
        if not os.path.isfile(van_p):
            log(f"   - Skipping {rel} auto-merge (not found in vanilla romfs/)")
            continue

        out_p = os.path.join(merged_dir, "romfs", *rel_parts)
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        merged_sz, van_sz, applied, conflicts = merge_bars_files(van_p, sources, out_p, codecs)
        merged_bars_rels.append(rel)

        # Canonical RESTBL keys use forward slashes without the .zs suffix.
        canon_key = rel[:-3] if rel.endswith(".zs") else rel
        restbl_bumps[canon_key] = (merged_sz, van_sz)

        mod_list_str = " + ".join(name for name, _ in sources)
        log(f"   + Merged {os.path.basename(rel)} from [{mod_list_str}] ({len(applied)} track edit(s), {merged_sz:,} B)")
        if conflicts:
            log(f"     Note: overlapping track edit(s): {', '.join(conflicts[:5])}")

        for mod_name, src_p in sources:
            if mod_name == "Merged_Zelda_Rando":
                continue
            if not os.path.isfile(src_p):
                continue
            if cfg.sandbox_mode:
                os.remove(src_p)
            else:
                bkp_p = os.path.join(cfg.bars_originals_dir, mod_name, *rel_parts)
                os.makedirs(os.path.dirname(bkp_p), exist_ok=True)
                shutil.move(src_p, bkp_p)

    marker_p = os.path.join(merged_dir, ".ootmodman_merged_bars.json")
    if merged_bars_rels:
        with open(marker_p, "w", encoding="utf-8") as f:
            json.dump(merged_bars_rels, f, indent=2)

        out_rstb = os.path.join(merged_dir, RSTB_REL)
        van_rstb = os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :])
        if os.path.isfile(van_rstb):
            van_raw, _ = read_maybe_zstd(van_rstb, codecs)
            t_van = restbl.ResourceSizeTable.from_binary(van_raw)
            rstb_src = out_rstb if os.path.isfile(out_rstb) else van_rstb
            dst_raw, dst_cctx = read_maybe_zstd(rstb_src, codecs)
            t_dst = restbl.ResourceSizeTable.from_binary(dst_raw)

            bumped = 0
            for canon_key, (m_sz, v_sz) in restbl_bumps.items():
                van_entry = t_van.get_size(canon_key)
                van_margin = max(8192, (van_entry - v_sz)) if (van_entry and van_entry > v_sz) else 8192
                cur = t_dst.get_size(canon_key) or 0
                needed = m_sz + van_margin
                if needed > cur:
                    t_dst.set_size(canon_key, needed)
                    bumped += 1

            if bumped > 0:
                write_maybe_zstd(out_rstb, t_dst.to_binary(), dst_cctx, codecs)
                log(f"   + Updated RESTBL headroom for {bumped} merged .bars archive(s)")
    elif os.path.isfile(marker_p):
        os.remove(marker_p)

    return merged_bars_rels


def _discover_swapped_npc_packs(char_src: Optional[str]) -> List[str]:
    """Return sorted ``Npc_*.pack.zs`` filenames bundled inside a playable character mod."""
    if not char_src:
        return []
    actor_dir = os.path.join(char_src, "romfs", "Pack", "Actor")
    if not os.path.isdir(actor_dir):
        return []
    return sorted(
        fn for fn in os.listdir(actor_dir)
        if fn.startswith("Npc_") and fn.endswith(".pack.zs")
    )


def _discover_mals_archives(
    char_src: Optional[str],
    core_merged_mods: List[StandaloneMod],
    rando_src: Optional[str],
) -> List[str]:
    """Discover all ``Mals/*.sarc*`` locale archives touched by any active core layer."""
    names: set[str] = set()
    roots = []
    if char_src:
        roots.append(char_src)
    roots.extend(m.source_path for m in core_merged_mods)
    if rando_src:
        roots.append(rando_src)
    for root in roots:
        mals_dir = os.path.join(root, "romfs", "Mals")
        if not os.path.isdir(mals_dir):
            continue
        for fn in os.listdir(mals_dir):
            low = fn.lower()
            if (low.endswith(".sarc.zs") or low.endswith(".sarc")) and os.path.isfile(os.path.join(mals_dir, fn)):
                names.add(fn)
    return sorted(names)


def _swap_in_directory(stage_dir: str, final_dir: str) -> None:
    """Atomically replace ``final_dir`` with ``stage_dir``, rolling back if the swap fails."""
    backup_dir = final_dir + ".old_backup"
    _remove_path(backup_dir)
    had_existing = os.path.exists(final_dir) or os.path.islink(final_dir)
    if had_existing:
        os.rename(final_dir, backup_dir)
    try:
        os.rename(stage_dir, final_dir)
    except Exception:
        if had_existing and os.path.exists(backup_dir) and not os.path.exists(final_dir):
            try:
                os.rename(backup_dir, final_dir)
            except Exception:
                _LOG.error("Rollback failed restoring %s from %s", final_dir, backup_dir, exc_info=True)
        raise
    if had_existing:
        _remove_path(backup_dir)


def run_build(
    cfg: AppConfig,
    opts: BuildOptions,
    log: Callable[[str], None] = print,
    progress: Optional[Callable[[int], None]] = None,
) -> None:
    """Build ``Merged_Zelda_Rando``, sync standalone mods, and auto-merge shared ``.bars`` files."""
    def emit_progress(pct: int) -> None:
        if progress:
            progress(pct)

    ok, issues = cfg.validate_paths()
    if not ok:
        raise RuntimeError("Invalid folder configuration:\n• " + "\n• ".join(issues))

    mode_tag = "SANDBOX" if cfg.sandbox_mode else "LIVE"
    log(f"=== Starting {mode_tag} build ===")
    log(f"Base romfs/  : {cfg.romfs_dir}")
    log(f"Target mods/ : {cfg.target_mods_dir}")

    if not cfg.sandbox_mode:
        cfg.restore_bars_originals(log=log)

    char_src = opts.char_path
    if char_src and not os.path.isdir(os.path.join(char_src, "romfs")):
        raise RuntimeError(f"Selected character mod not found: {char_src}")

    rando_src = opts.rando_path
    if rando_src and not os.path.isdir(os.path.join(rando_src, "romfs")):
        raise RuntimeError(f"Selected randomizer seed not found: {rando_src}")

    # Resolve checked mods from the right-hand list in exact user priority order.
    all_list_mods = cfg.find_standalone_mods()
    by_name = {m.name: m for m in all_list_mods}
    ordered_enabled = [by_name[n] for n in opts.enabled_standalone_names if n in by_name]

    core_merged_mods: List[StandaloneMod] = []
    pure_standalone_mods: List[StandaloneMod] = []
    skipped_conflict_mods: List[str] = []

    for mod in ordered_enabled:
        if cfg.is_malon_skeleton_conflict(char_src, mod.source_path):
            skipped_conflict_mods.append(mod.name)
            continue
        if cfg.mod_merge_kind(mod) != "standalone":
            core_merged_mods.append(mod)
        else:
            pure_standalone_mods.append(mod)

    char_name = os.path.basename(char_src) if char_src else "Vanilla Link"
    codecs = cfg.get_codecs() or CodecBundle(cfg.romfs_dir)
    merged_dir = os.path.join(cfg.target_mods_dir, "Merged_Zelda_Rando")
    os.makedirs(cfg.target_mods_dir, exist_ok=True)
    emit_progress(5)

    has_core_layers = any((char_src, rando_src, core_merged_mods))
    if not has_core_layers:
        if os.path.exists(merged_dir) or os.path.islink(merged_dir):
            _remove_path(merged_dir)
            log("Removed Merged_Zelda_Rando (no core merge layers selected).")
    else:
        log(f"Character    : {char_name}")
        log(f"Randomizer   : {os.path.basename(rando_src) if rando_src else '(None)'}")
        log(f"Merged Visual: {[m.name for m in core_merged_mods] or '(None)'}")
        if skipped_conflict_mods:
            log(f"Skipped NPC  : {skipped_conflict_mods} (incompatible with Playable Malon skeleton)")

        # Stage the entire core merge into a sibling directory so mid-build failures never wipe a working build.
        stage_dir = os.path.join(cfg.target_mods_dir, ".Merged_Zelda_Rando.building")
        _remove_path(stage_dir)
        os.makedirs(os.path.join(stage_dir, "romfs"), exist_ok=True)

        try:
            if char_src:
                log(f"1. Copying character mod ({char_name})...")
                shutil.copytree(char_src, stage_dir, dirs_exist_ok=True)
            else:
                log("1. Skipping character mod (Vanilla Link)")
            emit_progress(18)

            if rando_src:
                log(f"2. Overlaying {os.path.basename(rando_src)}...")
                shutil.copytree(rando_src, stage_dir, dirs_exist_ok=True)
            else:
                log("2. Skipping randomizer overlay (No Randomizer)")
            emit_progress(30)

            # 3. Integrate all checked visual / UI / model mods in load order.
            blarc_headroom: Dict[str, Tuple[int, int]] = {}
            blarc_layers: Dict[str, List[str]] = {}
            bntx_layers: Dict[str, List[str]] = {}
            copied_visual = 0

            for mod in core_merged_mods:
                mod_romfs = os.path.join(mod.source_path, "romfs")
                for root, _, files in os.walk(mod_romfs):
                    for filename in files:
                        src_p = os.path.join(root, filename)
                        rel_p = os.path.relpath(src_p, mod_romfs)
                        rel_norm = rel_p.replace("\\", "/")
                        low_norm = rel_norm.lower()
                        if rel_norm.startswith(("Mals/", "System/Resource/")):
                            continue
                        if low_norm.endswith((".blarc.zs", ".blarc")):
                            blarc_layers.setdefault(rel_norm, []).append(src_p)
                            continue
                        if low_norm.endswith((".bntx.zs", ".bntx")):
                            bntx_layers.setdefault(rel_norm, []).append(src_p)
                            continue
                        dst_p = os.path.join(stage_dir, "romfs", *rel_norm.split("/"))
                        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                        shutil.copy2(src_p, dst_p)
                        copied_visual += 1

            merged_ui_notes: List[str] = []
            for rel_norm, layer_paths in sorted(blarc_layers.items()):
                parts = rel_norm.split("/")
                dst_p = os.path.join(stage_dir, "romfs", *parts)
                base_p = os.path.join(cfg.romfs_dir, *parts)
                rando_p = os.path.join(rando_src, "romfs", *parts) if rando_src else None
                has_rando = bool(rando_p and os.path.exists(rando_p))
                if os.path.exists(base_p) and (len(layer_paths) > 1 or has_rando):
                    m_sz, max_in, spliced = merge_blarc_layers(
                        base_p, layer_paths, rando_p if has_rando else None, dst_p, codecs
                    )
                    canon_blarc = rel_norm[:-3] if rel_norm.lower().endswith(".zs") else rel_norm
                    blarc_headroom[canon_blarc] = (m_sz, max(0, m_sz - max_in))
                    merged_ui_notes.append(f"{os.path.basename(rel_norm)} ({len(layer_paths)} layer(s), spliced {spliced}B)")
                else:
                    os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                    shutil.copy2(layer_paths[-1], dst_p)
                    copied_visual += 1

            for rel_norm, layer_paths in sorted(bntx_layers.items()):
                parts = rel_norm.split("/")
                dst_p = os.path.join(stage_dir, "romfs", *parts)
                base_p = os.path.join(cfg.romfs_dir, *parts)
                rando_p = os.path.join(rando_src, "romfs", *parts) if rando_src else None
                has_rando = bool(rando_p and os.path.exists(rando_p))
                if os.path.exists(base_p) and (len(layer_paths) > 1 or has_rando):
                    _, patched_tex = merge_bntx_layers(
                        base_p,
                        layer_paths,
                        rando_p if has_rando else None,
                        dst_p,
                        codecs,
                        prefer_rando_logo=opts.prefer_rando_logo,
                    )
                    merged_ui_notes.append(
                        f"{os.path.basename(rel_norm)} ({len(layer_paths)} layer(s), rando tex: {patched_tex})"
                    )
                else:
                    os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                    shutil.copy2(layer_paths[-1], dst_p)
                    copied_visual += 1

            if core_merged_mods:
                log(f"3. Integrated {len(core_merged_mods)} visual/model mod(s) ({copied_visual} copied, merged: {merged_ui_notes})")
            else:
                log("3. No visual/UI/model core layers to merge")
            emit_progress(50)

            # 4. Patch Havok Cloth on swapped NPC packs from character mod.
            patched_npcs = []
            for pack_name in _discover_swapped_npc_packs(char_src):
                pack_path = os.path.join(stage_dir, "romfs", "Pack", "Actor", pack_name)
                if patch_npc_cloth(pack_path, codecs):
                    patched_npcs.append(pack_name)
            log(f"4. Patched Havok Cloth on {len(patched_npcs)} character-swapped NPC(s): {patched_npcs}")
            emit_progress(60)

            # 5. N-way Mals dialogue merge across all present locale archives.
            merged_mals_sizes: Dict[str, int] = {}
            for mal_name in _discover_mals_archives(char_src, core_merged_mods, rando_src):
                base_mal = os.path.join(cfg.romfs_dir, "Mals", mal_name)
                char_mal = os.path.join(char_src, "romfs", "Mals", mal_name) if char_src else None
                mod_mals = [
                    os.path.join(m.source_path, "romfs", "Mals", mal_name)
                    for m in core_merged_mods
                    if os.path.exists(os.path.join(m.source_path, "romfs", "Mals", mal_name))
                ]
                rand_mal = os.path.join(rando_src, "romfs", "Mals", mal_name) if rando_src else None
                out_mal = os.path.join(stage_dir, "romfs", "Mals", mal_name)

                active_mals = [p for p in ([char_mal] + mod_mals + [rand_mal]) if p and os.path.exists(p)]
                if not active_mals:
                    continue

                canon_mal = f"Mals/{mal_name[:-3]}" if mal_name.lower().endswith(".zs") else f"Mals/{mal_name}"
                os.makedirs(os.path.dirname(out_mal), exist_ok=True)
                if len(active_mals) == 1 or not os.path.exists(base_mal):
                    shutil.copy2(active_mals[-1], out_mal)
                    raw_m, _ = read_maybe_zstd(out_mal, codecs)
                    merged_mals_sizes[canon_mal] = len(raw_m) + 8192
                else:
                    base_raw, base_cctx = read_maybe_zstd(base_mal, codecs)
                    s_base = oead.Sarc(base_raw)
                    base_map = {f.name: bytes(f.data) for f in s_base.get_files()}

                    if char_mal and os.path.exists(char_mal):
                        char_raw, _ = read_maybe_zstd(char_mal, codecs)
                        w_mal = oead.SarcWriter.from_sarc(oead.Sarc(char_raw))
                    else:
                        w_mal = oead.SarcWriter.from_sarc(s_base)

                    for mod_mal in mod_mals:
                        mod_raw, _ = read_maybe_zstd(mod_mal, codecs)
                        s_mod = oead.Sarc(mod_raw)
                        for entry in s_mod.get_files():
                            if bytes(entry.data) != base_map.get(entry.name):
                                w_mal.files[entry.name] = bytes(entry.data)

                    if rand_mal and os.path.exists(rand_mal):
                        rand_raw, _ = read_maybe_zstd(rand_mal, codecs)
                        s_rand = oead.Sarc(rand_raw)
                        for entry in s_rand.get_files():
                            if bytes(entry.data) != base_map.get(entry.name):
                                w_mal.files[entry.name] = bytes(entry.data)

                    _, mal_bytes = w_mal.write()
                    write_maybe_zstd(out_mal, bytes(mal_bytes), base_cctx or codecs.cctx_zs, codecs)
                    merged_mals_sizes[canon_mal] = len(mal_bytes) + 8192

            log(f"5. Processed {len(merged_mals_sizes)} Mals dialogue archive(s)")
            emit_progress(72)

            # 6. Merge RESTBL entries + headroom across character, all visual/model mods, and Mals/UI.
            base_rstb_candidates = []
            if rando_src:
                base_rstb_candidates.append(os.path.join(rando_src, RSTB_REL))
            if char_src:
                base_rstb_candidates.append(os.path.join(char_src, RSTB_REL))
            base_rstb_candidates.append(os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :]))

            base_rstb_path = next((p for p in base_rstb_candidates if os.path.exists(p)), None)
            if not base_rstb_path:
                raise RuntimeError("Could not locate any ResourceSizeTable to use as base")

            base_rstb_raw, base_rstb_cctx = read_maybe_zstd(base_rstb_path, codecs)
            t_merged = restbl.ResourceSizeTable.from_binary(base_rstb_raw)

            char_count = 0
            if char_src:
                char_rstb_path = os.path.join(char_src, RSTB_REL)
                if os.path.exists(char_rstb_path) and _norm_path_key(char_rstb_path) != _norm_path_key(base_rstb_path):
                    char_rstb_raw, _ = read_maybe_zstd(char_rstb_path, codecs)
                    t_char = restbl.ResourceSizeTable.from_binary(char_rstb_raw)
                    char_count = merge_restbl_from_mod(os.path.join(char_src, "romfs"), t_char, t_merged, codecs)

            visual_rstb_count = 0
            for mod in core_merged_mods:
                mod_rstb_path = os.path.join(mod.source_path, RSTB_REL)
                mod_romfs = os.path.join(mod.source_path, "romfs")
                if os.path.exists(mod_rstb_path):
                    mod_rstb_raw, _ = read_maybe_zstd(mod_rstb_path, codecs)
                    t_mod = restbl.ResourceSizeTable.from_binary(mod_rstb_raw)
                    visual_rstb_count += merge_restbl_from_mod(mod_romfs, t_mod, t_merged, codecs)

                # Apply generous +20 MB headroom for any .bfres.zs model larger than vanilla (prevents N64 Malon-style crashes).
                for root, _, files in os.walk(mod_romfs):
                    for filename in files:
                        if filename.lower().endswith(".bfres.zs"):
                            full_p = os.path.join(root, filename)
                            rel_norm = os.path.relpath(full_p, mod_romfs).replace("\\", "/")
                            van_p = os.path.join(cfg.romfs_dir, *rel_norm.split("/"))
                            raw_b, _ = codecs.detect_zstd(full_p)
                            van_sz = len(codecs.detect_zstd(van_p)[0]) if os.path.isfile(van_p) else 0
                            if len(raw_b) > van_sz:
                                cp = rel_norm[:-3]
                                cur = t_merged.get_size(cp) or 0
                                t_merged.set_size(cp, max(cur, len(raw_b) + 20 * 1024 * 1024))
                                visual_rstb_count += 1

            for canon_blarc, (m_sz, delta) in blarc_headroom.items():
                cur = t_merged.get_size(canon_blarc) or 0
                t_merged.set_size(canon_blarc, max(cur + delta + 4096, m_sz + 8192))

            for canon_mal, sz in merged_mals_sizes.items():
                cur = t_merged.get_size(canon_mal) or 0
                t_merged.set_size(canon_mal, max(cur, sz))

            out_rstb = os.path.join(stage_dir, RSTB_REL)
            write_maybe_zstd(out_rstb, t_merged.to_binary(), base_rstb_cctx, codecs)

            _swap_in_directory(stage_dir, merged_dir)
        except Exception:
            _remove_path(stage_dir)
            raise

        log(
            f"6. Merged RESTBL ({char_name}: {char_count}, "
            f"Visual/Model mods: {visual_rstb_count}) + Mals/UI headroom"
        )

        if (
            (not cfg.sandbox_mode)
            and rando_src
            and cfg.live_mods_dir
            and cfg.backup_dir
            and _norm_path_key(os.path.dirname(rando_src)) == _norm_path_key(cfg.live_mods_dir)
        ):
            os.makedirs(cfg.backup_dir, exist_ok=True)
            archived_rando = os.path.join(cfg.backup_dir, os.path.basename(rando_src))
            _remove_path(archived_rando)
            shutil.move(rando_src, archived_rando)
            log(f"   Archived seed out of live mods/ -> {archived_rando}")

    emit_progress(82)
    log("7. Syncing standalone drop-in mods...")
    core_merged_names = {m.name for m in core_merged_mods}
    standalone_names = [m.name for m in pure_standalone_mods]
    _sync_standalone_mods(cfg, all_list_mods, standalone_names, core_merged_names, log)

    emit_progress(92)
    if opts.auto_merge_bars:
        log("8. Checking for shared BGM / .bars audio archives...")
        merged_bars = _auto_merge_shared_bars(cfg, merged_dir, standalone_names, codecs, log)
        if not merged_bars:
            log("   No shared .bars archives needed merging.")

    emit_progress(100)
    log(f"Done! {mode_tag} build ready in: {cfg.target_mods_dir}")
