from __future__ import annotations

import io
import os
import re
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import byml
import oead
import zstandard as zstd

BARS_EXTS = (".bars.zs", ".bars")


class CodecBundle:
    """Loads Longshot's ZsDic dictionaries once and provides raw/zs/pack codecs."""

    def __init__(self, romfs_dir: str) -> None:
        self.dctx_raw = zstd.ZstdDecompressor()
        self.cctx_raw = zstd.ZstdCompressor(level=19)

        zs_dic_path = os.path.join(romfs_dir, "Pack", "ZsDic.pack.zs")
        with open(zs_dic_path, "rb") as f:
            dic_sarc = oead.Sarc(self.dctx_raw.decompress(f.read()))

        pack_dict = zstd.ZstdCompressionDict(bytes(dic_sarc.get_file("pack.zsdic").data))
        zs_dict = zstd.ZstdCompressionDict(bytes(dic_sarc.get_file("zs.zsdic").data))

        self.dctx_pack = zstd.ZstdDecompressor(dict_data=pack_dict)
        self.cctx_pack = zstd.ZstdCompressor(level=19, dict_data=pack_dict)
        self.dctx_zs = zstd.ZstdDecompressor(dict_data=zs_dict)
        self.cctx_zs = zstd.ZstdCompressor(level=19, dict_data=zs_dict)

        self.codecs = [
            (self.dctx_raw, self.cctx_raw),
            (self.dctx_zs, self.cctx_zs),
            (self.dctx_pack, self.cctx_pack),
        ]

    def decompress_bytes(self, raw: bytes) -> Tuple[bytes, zstd.ZstdCompressor]:
        for dec, comp in self.codecs:
            try:
                return dec.decompress(raw), comp
            except zstd.ZstdError:
                try:
                    with dec.stream_reader(io.BytesIO(raw)) as reader:
                        return reader.read(), comp
                except zstd.ZstdError:
                    continue
        raise RuntimeError("Could not decompress Zstd buffer with raw, zs, or pack dictionary")

    def detect_zstd(self, path: str) -> Tuple[bytes, zstd.ZstdCompressor]:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            return self.decompress_bytes(raw)
        except RuntimeError as exc:
            raise RuntimeError(f"Could not decompress {path}") from exc


def patch_npc_cloth(pack_path: str, codecs: CodecBundle) -> bool:
    if not os.path.exists(pack_path):
        return False
    with open(pack_path, "rb") as f:
        m_sarc = oead.Sarc(codecs.dctx_pack.decompress(f.read()))
    writer = oead.SarcWriter.from_sarc(m_sarc)
    modified = False

    for key in list(writer.files.keys()):
        if key.startswith("Phive/ControllerSetParam/") and key.endswith(".bgyml"):
            csp_raw = bytes(writer.files[key])
            ver = int.from_bytes(csp_raw[2:4], "little")
            csp_doc = byml.Byml(csp_raw).parse()
            csp_changed = False
            for cloth_key in ("Cloth", "ClothAdvandecOption", "ClothList", "ClothReaction"):
                if cloth_key in csp_doc and len(csp_doc[cloth_key]) > 0:
                    csp_doc[cloth_key] = []
                    csp_changed = True
            if csp_changed:
                writer.files[key] = byml.Writer(csp_doc, be=False, version=ver).get_bytes()
                modified = True

    for internal_path in list(writer.files.keys()):
        if internal_path.startswith(("Phive/ClothParam/", "Phive/ClothReaction/")):
            del writer.files[internal_path]
            modified = True

    if modified:
        _, sarc_bytes = writer.write()
        with open(pack_path, "wb") as f_npc:
            f_npc.write(codecs.cctx_pack.compress(bytes(sarc_bytes)))
    return modified


def splice_non_overlapping_diffs(base_b: bytes, ui_b: bytes, rando_b: bytes) -> Tuple[bytes, int]:
    out = bytearray(rando_b)
    if len(base_b) != len(ui_b):
        return bytes(out), 0
    diffs = [i for i in range(len(base_b)) if base_b[i] != ui_b[i]]
    spans: List[List[int]] = []
    for idx in diffs:
        if spans and idx == spans[-1][1]:
            spans[-1][1] = idx + 1
        else:
            spans.append([idx, idx + 1])
    applied = 0
    for a, b in spans:
        pre = max(0, a - 8)
        if (
            b + 8 <= len(out)
            and out[a:b] == base_b[a:b]
            and out[pre:a] == base_b[pre:a]
            and out[b : b + 8] == base_b[b : b + 8]
        ):
            out[a:b] = ui_b[a:b]
            applied += b - a
    return bytes(out), applied


def merge_blarc(base_p: str, ui_p: str, rando_p: str, out_p: str, codecs: CodecBundle) -> Tuple[int, int, int]:
    base_raw, cctx = codecs.detect_zstd(base_p)
    ui_raw, _ = codecs.detect_zstd(ui_p)
    rando_raw, _ = codecs.detect_zstd(rando_p)

    base_map = {f.name: bytes(f.data) for f in oead.Sarc(base_raw).get_files()}
    ui_sarc = oead.Sarc(ui_raw)
    ui_map = {f.name: bytes(f.data) for f in ui_sarc.get_files()}
    writer = oead.SarcWriter.from_sarc(ui_sarc)
    spliced_bytes = 0

    for f in oead.Sarc(rando_raw).get_files():
        r_data = bytes(f.data)
        b_data = base_map.get(f.name)
        if r_data == b_data:
            continue
        u_data = ui_map.get(f.name)
        if b_data is not None and u_data is not None and u_data != b_data:
            merged_sub, applied = splice_non_overlapping_diffs(b_data, u_data, r_data)
            writer.files[f.name] = merged_sub
            spliced_bytes += applied
        else:
            writer.files[f.name] = r_data

    _, out_sarc = writer.write()
    out_bytes = bytes(out_sarc)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "wb") as f_out:
        f_out.write(cctx.compress(out_bytes))
    return len(out_bytes), max(len(ui_raw), len(rando_raw)), spliced_bytes


def parse_bntx(data: bytes) -> Dict[str, Tuple[int, int, bytes]]:
    cnt, ptrs_off = struct.unpack_from("<IQ", data, 0x24)
    out: Dict[str, Tuple[int, int, bytes]] = {}
    for i in range(cnt):
        p = struct.unpack_from("<Q", data, ptrs_off + i * 8)[0]
        sz = struct.unpack_from("<I", data, p + 0x50)[0]
        noff = struct.unpack_from("<Q", data, p + 0x60)[0]
        poff = struct.unpack_from("<Q", data, p + 0x70)[0]
        nlen = struct.unpack_from("<H", data, noff)[0]
        name = data[noff + 2 : noff + 2 + nlen].decode("utf-8", "replace")
        doff = struct.unpack_from("<Q", data, poff)[0]
        out[name] = (doff, sz, data[p : p + 0x54])
    return out


def merge_bntx(
    base_p: str,
    ui_p: str,
    rando_p: str,
    out_p: str,
    codecs: CodecBundle,
    prefer_rando_logo: bool = False,
) -> Tuple[int, List[str]]:
    base_raw, cctx = codecs.detect_zstd(base_p)
    ui_raw, _ = codecs.detect_zstd(ui_p)
    rando_raw, _ = codecs.detect_zstd(rando_p)

    b_tex, u_tex, r_tex = parse_bntx(base_raw), parse_bntx(ui_raw), parse_bntx(rando_raw)
    out = bytearray(ui_raw)
    patched: List[str] = []

    for name, (r_off, r_sz, r_hdr) in r_tex.items():
        r_px = rando_raw[r_off : r_off + r_sz]
        b_info = b_tex.get(name)
        if b_info and base_raw[b_info[0] : b_info[0] + b_info[1]] == r_px:
            continue
        u_info = u_tex.get(name)
        if not u_info or u_info[1] != r_sz or u_info[2] != r_hdr:
            continue
        u_px = ui_raw[u_info[0] : u_info[0] + u_info[1]]
        ui_changed = not (b_info and base_raw[b_info[0] : b_info[0] + b_info[1]] == u_px)
        if not ui_changed or prefer_rando_logo:
            out[u_info[0] : u_info[0] + r_sz] = r_px
            patched.append(name)

    out_bytes = bytes(out)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "wb") as f_out:
        f_out.write(cctx.compress(out_bytes))
    return len(out_bytes), patched


# --- BARS Audio Archive Parsing & 3-Way Merging ---

@dataclass
class BarsEntry:
    crc: int
    amta: bytes
    asset: Optional[bytes]  # None when asset_off == 0xFFFFFFFF


@dataclass
class BarsArchive:
    version: int
    bom: int
    entries: Dict[int, BarsEntry]


def extract_amta_name(amta: bytes, crc: int) -> str:
    """Extracts the trailing track name from an AMTA v4/v5 block, falling back to hex CRC."""
    m = re.search(rb"([A-Za-z][A-Za-z0-9_.\-]{2,})\x00+$", amta)
    if m:
        return m.group(1).decode("ascii", "replace")
    return f"track_{crc:08x}"


def parse_bars(data: bytes) -> BarsArchive:
    if len(data) < 0x10 or data[:4] != b"BARS":
        raise ValueError("Not a valid BARS archive")
    _magic, _fsize, bom, ver, count = struct.unpack_from("<4sIHHI", data, 0)
    if bom != 0xFEFF:
        raise ValueError(f"Unsupported BARS byte order: 0x{bom:04x}")

    crc_off = 0x10
    crcs = struct.unpack_from(f"<{count}I", data, crc_off)
    tbl_off = crc_off + count * 4
    pairs = [struct.unpack_from("<II", data, tbl_off + i * 8) for i in range(count)]

    valid_asset_offs = sorted({so for _, so in pairs if so != 0xFFFFFFFF})
    asset_bounds: Dict[int, int] = {}
    for idx, so in enumerate(valid_asset_offs):
        asset_bounds[so] = valid_asset_offs[idx + 1] if idx + 1 < len(valid_asset_offs) else len(data)

    entries: Dict[int, BarsEntry] = {}
    for crc, (amta_off, asset_off) in zip(crcs, pairs):
        if amta_off + 12 > len(data) or data[amta_off : amta_off + 4] != b"AMTA":
            raise ValueError(f"Invalid AMTA block at 0x{amta_off:x} for CRC 0x{crc:08x}")
        amta_sz = struct.unpack_from("<I", data, amta_off + 8)[0]
        amta_bytes = data[amta_off : amta_off + amta_sz]
        asset_bytes = None if asset_off == 0xFFFFFFFF else data[asset_off : asset_bounds[asset_off]]
        entries[crc] = BarsEntry(crc=crc, amta=amta_bytes, asset=asset_bytes)

    return BarsArchive(version=ver, bom=bom, entries=entries)


def build_bars(archive: BarsArchive) -> bytes:
    """Rebuilds a little-endian BARS archive with sorted CRCs, 4B AMTA alignment, and 64B asset alignment."""
    sorted_crcs = sorted(archive.entries.keys())
    count = len(sorted_crcs)
    header_size = 0x10 + count * 4 + count * 8

    out = bytearray(header_size)

    def _pad(align: int) -> None:
        rem = len(out) % align
        if rem:
            out.extend(b"\x00" * (align - rem))

    amta_offsets: List[int] = []
    for crc in sorted_crcs:
        _pad(4)
        amta_offsets.append(len(out))
        out.extend(archive.entries[crc].amta)

    asset_offset_cache: Dict[bytes, int] = {}
    asset_offsets: List[int] = []
    for crc in sorted_crcs:
        asset = archive.entries[crc].asset
        if asset is None:
            asset_offsets.append(0xFFFFFFFF)
        elif asset in asset_offset_cache:
            asset_offsets.append(asset_offset_cache[asset])
        else:
            _pad(0x40)
            off = len(out)
            asset_offset_cache[asset] = off
            asset_offsets.append(off)
            out.extend(asset)

    struct.pack_into("<4sIHHI", out, 0, b"BARS", len(out), archive.bom, archive.version, count)
    crc_off = 0x10
    for idx, crc in enumerate(sorted_crcs):
        struct.pack_into("<I", out, crc_off + idx * 4, crc)
    tbl_off = crc_off + count * 4
    for idx, (ao, so) in enumerate(zip(amta_offsets, asset_offsets)):
        struct.pack_into("<II", out, tbl_off + idx * 8, ao, so)

    return bytes(out)


def read_bars_raw(path: str, codecs: CodecBundle) -> Tuple[bytes, Optional[zstd.ZstdCompressor]]:
    if path.endswith(".zs"):
        return codecs.detect_zstd(path)
    with open(path, "rb") as f:
        return f.read(), None


def bars_changed_entries(van_arc: BarsArchive, mod_arc: BarsArchive) -> Dict[int, str]:
    """Returns {crc: track_name} for every entry modified or added in mod_arc vs. van_arc."""
    changed: Dict[int, str] = {}
    for crc, ment in mod_arc.entries.items():
        vent = van_arc.entries.get(crc)
        if vent is None or ment.amta != vent.amta or ment.asset != vent.asset:
            changed[crc] = extract_amta_name(ment.amta, crc)
    return changed


def analyze_bars_compatibility(
    base_raw: bytes,
    mod_blobs: List[Tuple[str, bytes]],
) -> Tuple[bool, List[str], List[str]]:
    """
    Compares 2+ BARS blobs against vanilla base_raw.
    Returns (is_cleanly_mergeable, merged_track_labels, conflicting_track_labels).
    """
    van_arc = parse_bars(base_raw)
    crc_owners: Dict[int, List[str]] = {}
    crc_names: Dict[int, str] = {}
    crc_payloads: Dict[int, List[Tuple[bytes, Optional[bytes]]]] = {}

    for mod_name, raw in mod_blobs:
        mod_arc = parse_bars(raw)
        changed = bars_changed_entries(van_arc, mod_arc)
        for crc, tname in changed.items():
            ent = mod_arc.entries[crc]
            crc_owners.setdefault(crc, []).append(mod_name)
            crc_names[crc] = tname
            crc_payloads.setdefault(crc, []).append((ent.amta, ent.asset))

    merged_labels: List[str] = []
    conflict_labels: List[str] = []
    for crc, owners in crc_owners.items():
        tname = crc_names[crc]
        if len(owners) > 1:
            # Identical edits by two mods don't actually conflict
            unique_payloads = set(crc_payloads[crc])
            if len(unique_payloads) > 1:
                conflict_labels.append(f"{tname} ({' vs '.join(owners)})")
                continue
        merged_labels.append(f"{tname} ({owners[-1]})")

    return (len(conflict_labels) == 0), merged_labels, conflict_labels


def merge_bars_files(
    base_p: str,
    mod_sources: List[Tuple[str, str]],
    out_p: str,
    codecs: CodecBundle,
) -> Tuple[int, int, List[str], List[str]]:
    """
    3-way merges multiple mods' BARS files against vanilla base_p.
    Returns (merged_size, vanilla_size, applied_tracks, overwritten_conflicts).
    """
    base_raw, cctx = read_bars_raw(base_p, codecs)
    van_arc = parse_bars(base_raw)
    merged_entries: Dict[int, BarsEntry] = dict(van_arc.entries)

    touched_by: Dict[int, Tuple[str, BarsEntry]] = {}
    applied_tracks: List[str] = []
    conflicts: List[str] = []

    for mod_name, mod_p in mod_sources:
        mod_raw, _ = read_bars_raw(mod_p, codecs)
        mod_arc = parse_bars(mod_raw)
        changed = bars_changed_entries(van_arc, mod_arc)
        for crc, tname in changed.items():
            ent = mod_arc.entries[crc]
            if crc in touched_by:
                prev_mod, prev_ent = touched_by[crc]
                if prev_ent.amta != ent.amta or prev_ent.asset != ent.asset:
                    conflicts.append(f"{tname}: {mod_name} overwrote {prev_mod}")
            touched_by[crc] = (mod_name, ent)
            merged_entries[crc] = ent
            applied_tracks.append(f"{tname} [{mod_name}]")

    merged_raw = build_bars(BarsArchive(version=van_arc.version, bom=van_arc.bom, entries=merged_entries))
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "wb") as f_out:
        if out_p.endswith(".zs") and cctx is not None:
            f_out.write(cctx.compress(merged_raw))
        else:
            f_out.write(merged_raw)

    return len(merged_raw), len(base_raw), applied_tracks, conflicts


def merge_restbl_from_mod(mod_romfs: str, t_src, t_dst, codecs: CodecBundle) -> int:
    count = 0
    for root, _, files in os.walk(mod_romfs):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, mod_romfs)
            if "ResourceSizeTable" in rel_path or rel_path.startswith("Mals/"):
                continue

            canon_paths = [rel_path[:-3] if rel_path.endswith(".zs") else rel_path]
            if rel_path.endswith((".pack.zs", ".sarc.zs", ".blarc.zs")):
                sarc_data, _ = codecs.detect_zstd(full_path)
                canon_paths.extend(
                    f.name[:-3] if f.name.endswith(".zs") else f.name
                    for f in oead.Sarc(sarc_data).get_files()
                )

            for cp in canon_paths:
                size = t_src.get_size(cp)
                if size is not None:
                    cur = t_dst.get_size(cp)
                    if cur is None or size > cur:
                        t_dst.set_size(cp, size)
                        count += 1
    return count


def merge_blarc_layers(
    base_p: str,
    ui_paths: List[str],
    rando_p: Optional[str],
    out_p: str,
    codecs: CodecBundle,
) -> Tuple[int, int, int]:
    """Stacks 1+ UI .blarc.zs mods in load order and splices Randomizer changes on top."""
    base_raw, cctx = codecs.detect_zstd(base_p)
    base_map = {f.name: bytes(f.data) for f in oead.Sarc(base_raw).get_files()}

    all_layers = [p for p in ui_paths if p and os.path.isfile(p)]
    if rando_p and os.path.isfile(rando_p):
        all_layers.append(rando_p)
    if not all_layers:
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        with open(out_p, "wb") as f_out:
            f_out.write(cctx.compress(base_raw))
        return len(base_raw), len(base_raw), 0

    cur_raw, _ = codecs.detect_zstd(all_layers[0])
    max_in = max(len(base_raw), len(cur_raw))
    spliced_bytes = 0

    for next_p in all_layers[1:]:
        next_raw, _ = codecs.detect_zstd(next_p)
        max_in = max(max_in, len(next_raw))
        cur_sarc = oead.Sarc(cur_raw)
        cur_map = {f.name: bytes(f.data) for f in cur_sarc.get_files()}
        writer = oead.SarcWriter.from_sarc(cur_sarc)

        for f in oead.Sarc(next_raw).get_files():
            n_data = bytes(f.data)
            b_data = base_map.get(f.name)
            if n_data == b_data:
                continue
            c_data = cur_map.get(f.name)
            if b_data is not None and c_data is not None and c_data != b_data:
                merged_sub, applied = splice_non_overlapping_diffs(b_data, c_data, n_data)
                writer.files[f.name] = merged_sub
                spliced_bytes += applied
            else:
                writer.files[f.name] = n_data

        _, out_sarc = writer.write()
        cur_raw = bytes(out_sarc)

    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "wb") as f_out:
        f_out.write(cctx.compress(cur_raw))
    return len(cur_raw), max_in, spliced_bytes


def merge_bntx_layers(
    base_p: str,
    ui_paths: List[str],
    rando_p: Optional[str],
    out_p: str,
    codecs: CodecBundle,
    prefer_rando_logo: bool = False,
) -> Tuple[int, List[str]]:
    """Stacks 1+ UI .bntx.zs texture archives in load order and applies Randomizer textures."""
    base_raw, cctx = codecs.detect_zstd(base_p)
    b_tex = parse_bntx(base_raw)

    valid_ui = [p for p in ui_paths if p and os.path.isfile(p)]
    if not valid_ui:
        src_raw = codecs.detect_zstd(rando_p)[0] if (rando_p and os.path.isfile(rando_p)) else base_raw
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        with open(out_p, "wb") as f_out:
            f_out.write(cctx.compress(src_raw))
        return len(src_raw), []

    first_raw, _ = codecs.detect_zstd(valid_ui[0])
    out = bytearray(first_raw)
    out_tex = parse_bntx(first_raw)
    ui_modified: set[str] = set()

    for name, (o_off, o_sz, _hdr) in out_tex.items():
        b_info = b_tex.get(name)
        if not (b_info and base_raw[b_info[0] : b_info[0] + b_info[1]] == first_raw[o_off : o_off + o_sz]):
            ui_modified.add(name)

    for next_p in valid_ui[1:]:
        n_raw, _ = codecs.detect_zstd(next_p)
        n_tex = parse_bntx(n_raw)
        for name, (n_off, n_sz, n_hdr) in n_tex.items():
            n_px = n_raw[n_off : n_off + n_sz]
            b_info = b_tex.get(name)
            if b_info and base_raw[b_info[0] : b_info[0] + b_info[1]] == n_px:
                continue
            o_info = out_tex.get(name)
            if o_info and o_info[1] == n_sz and o_info[2] == n_hdr:
                out[o_info[0] : o_info[0] + n_sz] = n_px
                ui_modified.add(name)

    patched: List[str] = []
    if rando_p and os.path.isfile(rando_p):
        r_raw, _ = codecs.detect_zstd(rando_p)
        r_tex = parse_bntx(r_raw)
        for name, (r_off, r_sz, r_hdr) in r_tex.items():
            r_px = r_raw[r_off : r_off + r_sz]
            b_info = b_tex.get(name)
            if b_info and base_raw[b_info[0] : b_info[0] + b_info[1]] == r_px:
                continue
            o_info = out_tex.get(name)
            if not o_info or o_info[1] != r_sz or o_info[2] != r_hdr:
                continue
            if name not in ui_modified or prefer_rando_logo:
                out[o_info[0] : o_info[0] + r_sz] = r_px
                patched.append(name)

    out_bytes = bytes(out)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "wb") as f_out:
        f_out.write(cctx.compress(out_bytes))
    return len(out_bytes), patched
