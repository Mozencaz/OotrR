from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import oead
import restbl

from oot_rando.midnas_devotion.core.config import AppConfig, RSTB_REL, StandaloneMod, UI_MERGE_EXTS
from oot_rando.midnas_devotion.core.formats import (
    BARS_EXTS,
    CodecBundle,
    merge_bars_files,
    merge_blarc_layers,
    merge_bntx_layers,
    merge_restbl_from_mod,
    patch_npc_cloth,
)


@dataclass
class BuildOptions:
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
    enabled_set = set(standalone_enabled_names)
    os.makedirs(cfg.target_mods_dir, exist_ok=True)

    if cfg.sandbox_mode:
        for mod in all_mods:
            dst = os.path.join(cfg.sandbox_mods_dir, mod.name)
            if mod.name in enabled_set and mod.name not in core_merged_names:
                if os.path.exists(dst):
                    shutil.rmtree(dst)
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
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                    log(f"   [sandbox] Removed duplicate/disabled folder: {mod.name}")
        return

    os.makedirs(cfg.disabled_mods_dir, exist_ok=True)
    os.makedirs(cfg.staged_mods_dir, exist_ok=True)
    for mod in all_mods:
        if mod.origin == "linked":
            continue
        live_p = os.path.join(cfg.live_mods_dir, mod.name)
        dis_p = os.path.join(cfg.disabled_mods_dir, mod.name)

        # Core-merged mods live inside Merged_Zelda_Rando; don't leave a colliding duplicate folder in live mods/
        if mod.name in core_merged_names:
            if os.path.isdir(live_p):
                staged_p = os.path.join(cfg.staged_mods_dir, mod.name)
                if os.path.exists(staged_p):
                    shutil.rmtree(staged_p)
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
                if os.path.exists(dis_p):
                    shutil.rmtree(dis_p)
                shutil.move(live_p, dis_p)
                log(f"   [live] Moved disabled standalone mod to disabled_mods/: {mod.name}")


def _auto_merge_shared_bars(
    cfg: AppConfig,
    merged_dir: str,
    enabled_standalone_names: List[str],
    codecs: CodecBundle,
    log: Callable[[str], None],
) -> List[str]:
    """
    Finds any .bars / .bars.zs files shared by 2+ active mods in target_mods_dir,
    3-way merges them against vanilla into Merged_Zelda_Rando, updates RESTBL headroom,
    and cleanly stashes/removes duplicate files from individual standalone mods.
    """
    bars_owners: Dict[str, List[Tuple[str, str]]] = {}

    merged_romfs = os.path.join(merged_dir, "romfs")
    if os.path.isdir(merged_romfs):
        for rel in cfg._walk_romfs_rel(merged_dir):
            if rel.endswith(BARS_EXTS):
                bars_owners.setdefault(rel, []).append(("Merged_Zelda_Rando", os.path.join(merged_romfs, rel)))

    for mod_name in enabled_standalone_names:
        mod_dir = os.path.join(cfg.target_mods_dir, mod_name)
        if not os.path.isdir(os.path.join(mod_dir, "romfs")):
            continue
        for rel in cfg._walk_romfs_rel(mod_dir):
            if rel.endswith(BARS_EXTS):
                bars_owners.setdefault(rel, []).append((mod_name, os.path.join(mod_dir, "romfs", rel)))

    merged_bars_rels: List[str] = []
    restbl_bumps: Dict[str, Tuple[int, int]] = {}

    for rel, sources in sorted(bars_owners.items()):
        if len(sources) < 2:
            continue
        van_p = os.path.join(cfg.romfs_dir, rel)
        if not os.path.isfile(van_p):
            log(f"   - Skipping {rel} auto-merge (not found in vanilla romfs/)")
            continue

        out_p = os.path.join(merged_dir, "romfs", rel)
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        merged_sz, van_sz, applied, conflicts = merge_bars_files(van_p, sources, out_p, codecs)
        merged_bars_rels.append(rel)

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
                bkp_p = os.path.join(cfg.bars_originals_dir, mod_name, rel)
                os.makedirs(os.path.dirname(bkp_p), exist_ok=True)
                shutil.move(src_p, bkp_p)

    marker_p = os.path.join(merged_dir, ".ootmodman_merged_bars.json")
    if merged_bars_rels:
        with open(marker_p, "w", encoding="utf-8") as f:
            json.dump(merged_bars_rels, f, indent=2)

        out_rstb = os.path.join(merged_dir, RSTB_REL)
        van_rstb = os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :])
        if os.path.isfile(van_rstb):
            with open(van_rstb, "rb") as f:
                t_van = restbl.ResourceSizeTable.from_binary(codecs.dctx_raw.decompress(f.read()))
            rstb_src = out_rstb if os.path.isfile(out_rstb) else van_rstb
            with open(rstb_src, "rb") as f:
                t_dst = restbl.ResourceSizeTable.from_binary(codecs.dctx_raw.decompress(f.read()))

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
                os.makedirs(os.path.dirname(out_rstb), exist_ok=True)
                with open(out_rstb, "wb") as f_out:
                    f_out.write(codecs.cctx_raw.compress(t_dst.to_binary()))
                log(f"   + Updated RESTBL headroom for {bumped} merged .bars archive(s)")
    elif os.path.isfile(marker_p):
        os.remove(marker_p)

    return merged_bars_rels


def _discover_swapped_npc_packs(char_src: Optional[str]) -> List[str]:
    if not char_src:
        return []
    actor_dir = os.path.join(char_src, "romfs", "Pack", "Actor")
    if not os.path.isdir(actor_dir):
        return []
    return sorted(
        fn for fn in os.listdir(actor_dir)
        if fn.startswith("Npc_") and fn.endswith(".pack.zs")
    )


def run_build(
    cfg: AppConfig,
    opts: BuildOptions,
    log: Callable[[str], None] = print,
    progress: Optional[Callable[[int], None]] = None,
) -> None:
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

    # Resolve checked mods from the right-hand list in exact user priority order
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
    codecs = CodecBundle(cfg.romfs_dir)
    merged_dir = os.path.join(cfg.target_mods_dir, "Merged_Zelda_Rando")
    os.makedirs(cfg.target_mods_dir, exist_ok=True)
    emit_progress(5)

    has_core_layers = any((char_src, rando_src, core_merged_mods))
    if not has_core_layers:
        if os.path.exists(merged_dir):
            shutil.rmtree(merged_dir)
            log("Removed Merged_Zelda_Rando (no core merge layers selected).")
    else:
        log(f"Character    : {char_name}")
        log(f"Randomizer   : {os.path.basename(rando_src) if rando_src else '(None)'}")
        log(f"Merged Visual: {[m.name for m in core_merged_mods] or '(None)'}")
        if skipped_conflict_mods:
            log(f"Skipped NPC  : {skipped_conflict_mods} (incompatible with Playable Malon skeleton)")

        if os.path.exists(merged_dir):
            shutil.rmtree(merged_dir)
        os.makedirs(os.path.join(merged_dir, "romfs"), exist_ok=True)

        if char_src:
            log(f"1. Copying character mod ({char_name})...")
            shutil.copytree(char_src, merged_dir, dirs_exist_ok=True)
        else:
            log("1. Skipping character mod (Vanilla Link)")
        emit_progress(18)

        if rando_src:
            log(f"2. Overlaying {os.path.basename(rando_src)}...")
            shutil.copytree(rando_src, merged_dir, dirs_exist_ok=True)
        else:
            log("2. Skipping randomizer overlay (No Randomizer)")
        emit_progress(30)

        # 3. Integrate all checked visual / UI / model mods in load order
        blarc_headroom: Dict[str, tuple[int, int]] = {}
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
                    if rel_norm.startswith(("Mals/", "System/Resource/")):
                        continue
                    if rel_norm.endswith(".blarc.zs"):
                        blarc_layers.setdefault(rel_p, []).append(src_p)
                        continue
                    if rel_norm.endswith(".bntx.zs"):
                        bntx_layers.setdefault(rel_p, []).append(src_p)
                        continue
                    dst_p = os.path.join(merged_dir, "romfs", rel_p)
                    os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                    shutil.copy2(src_p, dst_p)
                    copied_visual += 1

        merged_ui_notes: List[str] = []
        for rel_p, layer_paths in sorted(blarc_layers.items()):
            dst_p = os.path.join(merged_dir, "romfs", rel_p)
            base_p = os.path.join(cfg.romfs_dir, rel_p)
            rando_p = os.path.join(rando_src, "romfs", rel_p) if rando_src else None
            has_rando = bool(rando_p and os.path.exists(rando_p))
            if os.path.exists(base_p) and (len(layer_paths) > 1 or has_rando):
                m_sz, max_in, spliced = merge_blarc_layers(
                    base_p, layer_paths, rando_p if has_rando else None, dst_p, codecs
                )
                blarc_headroom[rel_p[:-3]] = (m_sz, max(0, m_sz - max_in))
                merged_ui_notes.append(f"{os.path.basename(rel_p)} ({len(layer_paths)} layer(s), spliced {spliced}B)")
            else:
                os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                shutil.copy2(layer_paths[-1], dst_p)
                copied_visual += 1

        for rel_p, layer_paths in sorted(bntx_layers.items()):
            dst_p = os.path.join(merged_dir, "romfs", rel_p)
            base_p = os.path.join(cfg.romfs_dir, rel_p)
            rando_p = os.path.join(rando_src, "romfs", rel_p) if rando_src else None
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
                    f"{os.path.basename(rel_p)} ({len(layer_paths)} layer(s), rando tex: {patched_tex})"
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

        # 4. Patch Havok Cloth on swapped NPC packs from character mod
        patched_npcs = []
        for pack_name in _discover_swapped_npc_packs(char_src):
            pack_path = os.path.join(merged_dir, "romfs", "Pack", "Actor", pack_name)
            if patch_npc_cloth(pack_path, codecs):
                patched_npcs.append(pack_name)
        log(f"4. Patched Havok Cloth on {len(patched_npcs)} character-swapped NPC(s): {patched_npcs}")
        emit_progress(60)

        # 5. N-way Mals dialogue merge (Character + all merged visual mods in order + Randomizer hints on top)
        merged_mals_sizes: Dict[str, int] = {}
        for mal_name in ("USen.Product.110.sarc.zs", "EUen.Product.110.sarc.zs"):
            base_mal = os.path.join(cfg.romfs_dir, "Mals", mal_name)
            char_mal = os.path.join(char_src, "romfs", "Mals", mal_name) if char_src else None
            mod_mals = [
                os.path.join(m.source_path, "romfs", "Mals", mal_name)
                for m in core_merged_mods
                if os.path.exists(os.path.join(m.source_path, "romfs", "Mals", mal_name))
            ]
            rand_mal = os.path.join(rando_src, "romfs", "Mals", mal_name) if rando_src else None
            out_mal = os.path.join(merged_dir, "romfs", "Mals", mal_name)

            active_mals = [p for p in ([char_mal] + mod_mals + [rand_mal]) if p and os.path.exists(p)]
            if not active_mals:
                continue

            os.makedirs(os.path.dirname(out_mal), exist_ok=True)
            if len(active_mals) == 1:
                shutil.copy2(active_mals[0], out_mal)
                raw_m, _ = codecs.detect_zstd(out_mal)
                merged_mals_sizes[f"Mals/{mal_name[:-3]}"] = len(raw_m) + 8192
            elif os.path.exists(base_mal):
                with open(base_mal, "rb") as f:
                    s_base = oead.Sarc(codecs.dctx_zs.decompress(f.read()))
                base_map = {f.name: bytes(f.data) for f in s_base.get_files()}

                if char_mal and os.path.exists(char_mal):
                    with open(char_mal, "rb") as f:
                        w_mal = oead.SarcWriter.from_sarc(oead.Sarc(codecs.dctx_zs.decompress(f.read())))
                else:
                    w_mal = oead.SarcWriter.from_sarc(s_base)

                for mod_mal in mod_mals:
                    with open(mod_mal, "rb") as f:
                        s_mod = oead.Sarc(codecs.dctx_zs.decompress(f.read()))
                    for entry in s_mod.get_files():
                        if bytes(entry.data) != base_map.get(entry.name):
                            w_mal.files[entry.name] = bytes(entry.data)

                if rand_mal and os.path.exists(rand_mal):
                    with open(rand_mal, "rb") as f:
                        s_rand = oead.Sarc(codecs.dctx_zs.decompress(f.read()))
                    for entry in s_rand.get_files():
                        if bytes(entry.data) != base_map.get(entry.name):
                            w_mal.files[entry.name] = bytes(entry.data)

                _, mal_bytes = w_mal.write()
                with open(out_mal, "wb") as f_mal:
                    f_mal.write(codecs.cctx_zs.compress(bytes(mal_bytes)))
                merged_mals_sizes[f"Mals/{mal_name[:-3]}"] = len(mal_bytes) + 8192

        log(f"5. Processed {len(merged_mals_sizes)} Mals dialogue archive(s)")
        emit_progress(72)

        # 6. Merge RESTBL entries + headroom across character, all visual/model mods, and Mals/UI
        base_rstb_candidates = []
        if rando_src:
            base_rstb_candidates.append(os.path.join(rando_src, RSTB_REL))
        if char_src:
            base_rstb_candidates.append(os.path.join(char_src, RSTB_REL))
        base_rstb_candidates.append(os.path.join(cfg.romfs_dir, RSTB_REL[len("romfs") + 1 :]))

        base_rstb_path = next((p for p in base_rstb_candidates if os.path.exists(p)), None)
        if not base_rstb_path:
            raise RuntimeError("Could not locate any ResourceSizeTable to use as base")

        with open(base_rstb_path, "rb") as f:
            t_merged = restbl.ResourceSizeTable.from_binary(codecs.dctx_raw.decompress(f.read()))

        char_count = 0
        if char_src:
            char_rstb_path = os.path.join(char_src, RSTB_REL)
            if os.path.exists(char_rstb_path) and char_rstb_path != base_rstb_path:
                with open(char_rstb_path, "rb") as f:
                    t_char = restbl.ResourceSizeTable.from_binary(codecs.dctx_raw.decompress(f.read()))
                char_count = merge_restbl_from_mod(os.path.join(char_src, "romfs"), t_char, t_merged, codecs)

        visual_rstb_count = 0
        for mod in core_merged_mods:
            mod_rstb_path = os.path.join(mod.source_path, RSTB_REL)
            mod_romfs = os.path.join(mod.source_path, "romfs")
            if os.path.exists(mod_rstb_path):
                with open(mod_rstb_path, "rb") as f:
                    t_mod = restbl.ResourceSizeTable.from_binary(codecs.dctx_raw.decompress(f.read()))
                visual_rstb_count += merge_restbl_from_mod(mod_romfs, t_mod, t_merged, codecs)

            # Apply generous +20 MB headroom for any .bfres.zs model larger than vanilla (prevents N64 Malon-style crashes)
            for root, _, files in os.walk(mod_romfs):
                for filename in files:
                    if filename.endswith(".bfres.zs"):
                        full_p = os.path.join(root, filename)
                        rel_p = os.path.relpath(full_p, mod_romfs)
                        van_p = os.path.join(cfg.romfs_dir, rel_p)
                        raw_b, _ = codecs.detect_zstd(full_p)
                        van_sz = len(codecs.detect_zstd(van_p)[0]) if os.path.isfile(van_p) else 0
                        if len(raw_b) > van_sz:
                            cp = rel_p[:-3]
                            cur = t_merged.get_size(cp) or 0
                            t_merged.set_size(cp, max(cur, len(raw_b) + 20 * 1024 * 1024))
                            visual_rstb_count += 1

        for canon_blarc, (m_sz, delta) in blarc_headroom.items():
            cur = t_merged.get_size(canon_blarc) or 0
            t_merged.set_size(canon_blarc, max(cur + delta + 4096, m_sz + 8192))

        for canon_mal, sz in merged_mals_sizes.items():
            cur = t_merged.get_size(canon_mal) or 0
            t_merged.set_size(canon_mal, max(cur, sz))

        out_rstb = os.path.join(merged_dir, RSTB_REL)
        os.makedirs(os.path.dirname(out_rstb), exist_ok=True)
        with open(out_rstb, "wb") as f_out:
            f_out.write(codecs.cctx_raw.compress(t_merged.to_binary()))

        log(
            f"6. Merged RESTBL ({char_name}: {char_count}, "
            f"Visual/Model mods: {visual_rstb_count}) + Mals/UI headroom"
        )

        if (
            (not cfg.sandbox_mode)
            and rando_src
            and cfg.live_mods_dir
            and cfg.backup_dir
            and os.path.abspath(os.path.dirname(rando_src)) == os.path.abspath(cfg.live_mods_dir)
        ):
            os.makedirs(cfg.backup_dir, exist_ok=True)
            archived_rando = os.path.join(cfg.backup_dir, os.path.basename(rando_src))
            if os.path.exists(archived_rando):
                shutil.rmtree(archived_rando)
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
