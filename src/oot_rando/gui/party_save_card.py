"""Compact OoT file-select style save summary card with real game item icons."""
import base64
from collections import Counter
import io
import json
import math
from pathlib import Path
import tkinter as tk

from oot_rando.paths import resource, state_dir
from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.tracker import game_overlay
from oot_rando.formats.save_file import load_snapshot

_SAVE_SUMMARY_CACHE = {}

STONES = [
    ("Kokiri Emerald", "KE", "#3fb950", "#1f6f31"),
    ("Goron Ruby", "GR", "#d9434e", "#821f27"),
    ("Zora Sapphire", "ZS", "#3b86e0", "#1c4d8c"),
]

# Clockwise starting at top (12 o-clock) to match the OoT medallion ring
MEDALLIONS = [
    ("Light Medallion", "Li", "#d9c241", "#8c7a1a"),
    ("Forest Medallion", "Fo", "#44b54d", "#226b28"),
    ("Fire Medallion", "Fi", "#d65238", "#822918"),
    ("Water Medallion", "Wa", "#3b80d9", "#1d4b8a"),
    ("Spirit Medallion", "Sp", "#de9331", "#8c5712"),
    ("Shadow Medallion", "Sh", "#8e55c9", "#52287d"),
]

SONGS_TOP = [
    ("Zeldas Lullaby", "ZL", "#d8c448"),
    ("Eponas Song", "Ep", "#d67b38"),
    ("Sarias Song", "Sa", "#46b34f"),
    ("Suns Song", "Su", "#e0a938"),
    ("Song of Time", "SoT", "#5ca8d6"),
    ("Song of Storms", "SoS", "#8e9aa6"),
]

SONGS_WARP = [
    ("Minuet of Forest", "Min", "#46b34f"),
    ("Bolero of Fire", "Bol", "#d45538"),
    ("Serenade of Water", "Ser", "#3b7ed6"),
    ("Requiem of Spirit", "Req", "#d99436"),
    ("Nocturne of Shadow", "Noc", "#8c56c4"),
    ("Prelude of Light", "Pre", "#d8c448"),
]

SONGS_EXTRA = [
    ("Scarecrows Song", "Sc", "#9a9588"),
]

_STONE_TOKEN_MAP = {
    "Item_Stone_Forest": "Kokiri Emerald",
    "Item_Stone_Fire": "Goron Ruby",
    "Item_Stone_Water": "Zora Sapphire",
}

_MEDALLION_TOKEN_MAP = {
    "Item_Medal_Forest": "Forest Medallion",
    "Item_Medal_Fire": "Fire Medallion",
    "Item_Medal_Water": "Water Medallion",
    "Item_Medal_Spirit": "Spirit Medallion",
    "Item_Medal_Shadow": "Shadow Medallion",
    "Item_Medal_Light": "Light Medallion",
    "Item_Medallion_Forest": "Forest Medallion",
    "Item_Medallion_Fire": "Fire Medallion",
    "Item_Medallion_Water": "Water Medallion",
    "Item_Medallion_Spirit": "Spirit Medallion",
    "Item_Medallion_Shadow": "Shadow Medallion",
    "Item_Medallion_Light": "Light Medallion",
}

_SONG_TOKEN_MAP = {
    "Song_Lullaby": "Zeldas Lullaby",
    "Song_Epona": "Eponas Song",
    "Song_Saria": "Sarias Song",
    "Song_Sun": "Suns Song",
    "Song_Time": "Song of Time",
    "Song_Storms": "Song of Storms",
    "Song_Minuet": "Minuet of Forest",
    "Song_Bolero": "Bolero of Fire",
    "Song_Serenade": "Serenade of Water",
    "Song_Requiem": "Requiem of Spirit",
    "Song_Nocturne": "Nocturne of Shadow",
    "Song_Prelude": "Prelude of Light",
    "Song_Scarecrow": "Scarecrows Song",
    "Item_Melody_Lullaby": "Zeldas Lullaby",
    "Item_Melody_EponaSong": "Eponas Song",
    "Item_Melody_SariaSong": "Sarias Song",
    "Item_Melody_SunSong": "Suns Song",
    "Item_Melody_TimeSong": "Song of Time",
    "Item_Melody_StormSong": "Song of Storms",
}

_SONG_ICON_TOKENS = {
    "Zeldas Lullaby": "Song_Lullaby",
    "Eponas Song": "Song_Epona",
    "Sarias Song": "Song_Saria",
    "Suns Song": "Song_Sun",
    "Song of Time": "Song_Time",
    "Song of Storms": "Song_Storms",
    "Minuet of Forest": "Song_Minuet",
    "Bolero of Fire": "Song_Bolero",
    "Serenade of Water": "Song_Serenade",
    "Requiem of Spirit": "Song_Requiem",
    "Nocturne of Shadow": "Song_Nocturne",
    "Prelude of Light": "Song_Prelude",
    "Scarecrows Song": "Song_Scarecrow",
    "Scarecrow Song": "Song_Scarecrow",
}


def _apply_string_snapshot_items(snapshot, counts):
    strings_map = snapshot.get("strings") if isinstance(snapshot, dict) else None
    if not isinstance(strings_map, dict) or not strings_map:
        return
    present = {str(v) for v in strings_map.values() if v}
    if not present:
        return

    token_to_item = {}
    for item_name, tokens in getattr(game_overlay, "ICONS", {}).items():
        for idx, tok in enumerate(tokens, start=1):
            token_to_item.setdefault(tok, []).append((item_name, idx))

    for tok in present:
        for item_name, lvl in token_to_item.get(tok, ()):
            counts[item_name] = max(int(counts.get(item_name, 0)), lvl)
        if tok in _STONE_TOKEN_MAP:
            s_name = _STONE_TOKEN_MAP[tok]
            counts[s_name] = max(int(counts.get(s_name, 0)), 1)
        if tok in _MEDALLION_TOKEN_MAP:
            m_name = _MEDALLION_TOKEN_MAP[tok]
            counts[m_name] = max(int(counts.get(m_name, 0)), 1)
        if tok in _SONG_TOKEN_MAP:
            sg_name = _SONG_TOKEN_MAP[tok]
            counts[sg_name] = max(int(counts.get(sg_name, 0)), 1)


def _list_party_saves(saves_dir):
    root = Path(saves_dir)
    if not root.is_dir():
        return []
    found = []
    for sav in root.rglob("progress.sav"):
        try:
            st = sav.stat()
        except OSError:
            continue
        found.append((st.st_mtime_ns, st.st_size, sav))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def _select_party_save(saves_dir, seed_marker=None):
    """Pick the newest save matching seed_marker when available, else the newest save."""
    candidates = _list_party_saves(saves_dir)
    if not candidates:
        return None, None, None
    if seed_marker is not None:
        try:
            marker_int = int(seed_marker)
        except (TypeError, ValueError):
            marker_int = None
        if marker_int is not None:
            for mt_ns, sz, sav in candidates:
                try:
                    snap = load_snapshot(sav)
                except Exception:
                    continue
                if isinstance(snap, dict) and snap.get("bool", {}).get(marker_int) is True:
                    return sav, (mt_ns, sz), snap
    mt_ns, sz, sav = candidates[0]
    return sav, (mt_ns, sz), None


def _load_tracking_metadata(seed_path):
    """Prefer tracking.json (full inventory/check flags/seed_marker), falling back to checks.json."""
    for fname in ("tracking.json", "checks.json"):
        meta_path = seed_path / fname
        if not meta_path.is_file():
            continue
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = raw.get("tracker") if isinstance(raw.get("tracker"), dict) else raw
            if isinstance(meta, dict):
                return meta, meta_path
        except Exception:
            continue
    return {}, seed_path / "tracking.json"


def _build_grid_and_badges(counts, known, tracked):
    items_grid = []
    for row in game_overlay.GRID[:3]:
        line = []
        for item, abbr, label, levels, colour in row:
            if item == "Bottle":
                continue
            level = int(counts.get(item, 0))
            state = "owned" if level else ("missing" if (item in tracked and item in known) else "unknown")
            line.append({
                "item": item,
                "abbr": abbr,
                "label": label,
                "level": level,
                "levels": levels,
                "colour": colour,
                "state": state,
                "icon": game_overlay.icon_name(item, level),
            })
        items_grid.append(line)

    stones = [
        {"item": it, "abbr": ab, "colour": col, "border": brd, "owned": bool(counts.get(it, 0))}
        for it, ab, col, brd in STONES
    ]
    medallions = [
        {"item": it, "abbr": ab, "colour": col, "border": brd, "owned": bool(counts.get(it, 0))}
        for it, ab, col, brd in MEDALLIONS
    ]

    def _song_owned(name):
        if counts.get(name, 0):
            return True
        alt = name.replace("s ", chr(39) + "s ")
        if counts.get(alt, 0):
            return True
        if name == "Scarecrows Song":
            return bool(counts.get("Scarecrow Song", 0) or counts.get("Scarecrow" + chr(39) + "s Song", 0))
        return False

    songs_top = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_TOP]
    songs_warp = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_WARP]
    songs_extra = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_EXTRA]
    return items_grid, stones, medallions, songs_top, songs_warp, songs_extra


def _empty_summary(total, tracked):
    items_grid, stones, medallions, songs_top, songs_warp, songs_extra = _build_grid_and_badges(Counter(), set(), tracked)
    return {
        "started": False,
        "slot": "New File",
        "hearts": 3,
        "skulltulas": 0,
        "rupees": 0,
        "done": 0,
        "total": total,
        "stones": stones,
        "medallions": medallions,
        "items": items_grid,
        "songs_top": songs_top,
        "songs_warp": songs_warp,
        "songs_extra": songs_extra,
    }


def summarize_party_save(seed_dir, saves_dir):
    """Return an OoT file-select summary dict for a party seed + save folder."""
    seed_path = Path(seed_dir)
    metadata, meta_path = _load_tracking_metadata(seed_path)
    checks_map = metadata.get("checks") if isinstance(metadata.get("checks"), dict) else {}
    total = len(checks_map)
    tracked = {r.get("item") for r in metadata.get("inventory", []) if isinstance(r, dict) and r.get("item")}
    seed_marker = metadata.get("seed_marker")

    sav, stat_pair, preloaded_snap = _select_party_save(saves_dir, seed_marker=seed_marker)
    if sav is None or stat_pair is None:
        return _empty_summary(total, tracked)

    mt_ns, sz = stat_pair
    try:
        meta_mtime = meta_path.stat().st_mtime_ns if meta_path.is_file() else 0
    except OSError:
        meta_mtime = 0

    cache_key = (str(sav), mt_ns, sz, str(meta_path), meta_mtime)
    cached = _SAVE_SUMMARY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if preloaded_snap is not None:
        snapshot = preloaded_snap
    else:
        try:
            snapshot = load_snapshot(sav)
        except Exception:
            return _empty_summary(total, tracked)

    counts, known = TrackerSession.observed_inventory(snapshot, metadata)
    _apply_string_snapshot_items(snapshot, counts)
    done = 0
    observed_counts = Counter()
    for _gid, row in checks_map.items():
        ref = row.get("collection") if isinstance(row, dict) else None
        if ref and TrackerSession._collected(ref, snapshot, metadata) is True:
            done += 1
            if row.get("item"):
                observed_counts[row["item"]] += 1

    song_names = {s[0] for s in SONGS_TOP + SONGS_WARP + SONGS_EXTRA}
    for item, amount in observed_counts.items():
        if item in ("Gold Skulltula Token", "Heart Container", "Piece of Heart"):
            counts[item] = max(counts[item], amount)
        elif item in tracked or item in song_names:
            counts[item] = max(counts[item], amount)

    hearts = 3 + int(counts.get("Heart Container", 0)) + (int(counts.get("Piece of Heart", 0)) // 4)
    skulltulas = int(counts.get("Gold Skulltula Token", 0))
    rupees = int(counts.get("Rupees", counts.get("Rupee", 0)))
    items_grid, stones, medallions, songs_top, songs_warp, songs_extra = _build_grid_and_badges(counts, known, tracked)

    bottle_count = int(counts.get("Bottle", 0))
    bottles = [
        {"slot": f"B{i + 1}", "owned": bottle_count > i, "icon": game_overlay.icon_name("Bottle", 1)}
        for i in range(5)
    ]

    # Normalize remake Echo Gem alias alongside Stone of Agony without duplicating
    # the 3x9 inventory grid slot in the UPGRADES panel.
    echo_gem_lvl = max(int(counts.get("Echo Gem", 0)), int(counts.get("Stone of Agony", 0)))
    if echo_gem_lvl:
        counts["Stone of Agony"] = max(int(counts.get("Stone of Agony", 0)), echo_gem_lvl)

    str_lvl = int(counts.get("Progressive Strength Upgrade", 0))
    scl_lvl = int(counts.get("Progressive Scale", 0))
    z_letter_lvl = 1 if counts.get("Zeldas Letter", 0) else 0
    r_letter_lvl = 1 if counts.get("Rutos Letter", 0) else 0
    letter_lvl = 1 if (z_letter_lvl or r_letter_lvl) else 0
    letter_item = "Rutos Letter" if (r_letter_lvl and not z_letter_lvl) else "Zeldas Letter"

    quest_items = [
        {
            "label": "Strength",
            "level": str_lvl,
            "max": 3,
            "colour": "#5f84b0",
            "icon": game_overlay.icon_name("Progressive Strength Upgrade", max(1, str_lvl)),
        },
        {
            "label": "Scale",
            "level": scl_lvl,
            "max": 2,
            "colour": "#5f84b0",
            "icon": game_overlay.icon_name("Progressive Scale", max(1, scl_lvl)),
        },
        {
            "label": "Letter",
            "level": letter_lvl,
            "max": 1,
            "colour": "#a9814a",
            "icon": game_overlay.icon_name(letter_item, 1),
        },
    ]

    result = {
        "started": True,
        "slot": sav.parent.name,
        "hearts": hearts,
        "skulltulas": skulltulas,
        "rupees": rupees,
        "done": done,
        "total": total,
        "stones": stones,
        "medallions": medallions,
        "items": items_grid,
        "bottles": bottles,
        "quest_items": quest_items,
        "songs_top": songs_top,
        "songs_warp": songs_warp,
        "songs_extra": songs_extra,
    }
    if len(_SAVE_SUMMARY_CACHE) > 64:
        _SAVE_SUMMARY_CACHE.clear()
    _SAVE_SUMMARY_CACHE[cache_key] = result
    return result


def _load_tk_icon(icon_path: Path, size: int, owned: bool):
    """Load a cached game icon PNG resized cleanly, desaturated & dimmed when unowned."""
    try:
        from PIL import Image, ImageEnhance
        img = Image.open(icon_path).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        if not owned:
            r, g, b, a = img.split()
            gray = Image.merge("RGB", (r, g, b)).convert("L")
            gray = ImageEnhance.Brightness(gray).enhance(0.50)
            alpha = a.point(lambda px: int(px * 0.36))
            img = Image.merge("RGBA", (gray, gray, gray, alpha))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
    except Exception:
        try:
            raw = tk.PhotoImage(file=str(icon_path))
            factor = max(1, raw.width() // size)
            return raw.subsample(factor, factor) if factor > 1 else raw
        except Exception:
            return None


def _is_dark_hex(hex_col: str) -> bool:
    s = str(hex_col or "").lstrip("#")
    if len(s) != 6:
        return False
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 128
    except ValueError:
        return False


def _icon_search_dirs(icon_dir=None):
    dirs = []
    if icon_dir:
        dirs.append(Path(icon_dir))
    for cand in (
        state_dir() / "icons",
        resource("gui", "icons"),
        Path(__file__).resolve().parent / "icons",
        Path(__file__).resolve().parent.parent / "assets" / "icons",
        Path(__file__).resolve().parent.parent / "tracker" / "icons",
    ):
        if cand and cand not in dirs:
            dirs.append(cand)
    return dirs


def render_party_save_card(parent, summary, colors, icon_dir=None):
    bg = colors.get("panel_bg", "#f7f3e8")
    card_bg = colors.get("card_bg", "#fffdf7")
    line = colors.get("line", "#d7cfb8")
    ink = colors.get("ink", "#2b261d")
    muted = colors.get("muted", "#736a58")
    dark = _is_dark_hex(bg)

    slot_bg = "#252932" if dark else "#f2ede0"
    slot_border = "#3d4452" if dark else "#d4cbb4"
    unowned_fill = "#2d323d" if dark else "#ebe5d5"
    unowned_outline = "#485060" if dark else "#c2b89f"
    unowned_ink = "#7c8596" if dark else "#8c826e"
    sep_col = "#363c48" if dark else line
    ring_guide = "#3a404d" if dark else "#ded6c1"

    W, H = 844, 206
    canvas = tk.Canvas(
        parent,
        width=W,
        height=H,
        background=bg,
        highlightthickness=1,
        highlightbackground=line,
        borderwidth=0,
    )
    canvas.pack(anchor="w", pady=(6, 0))

    icon_cache = {}
    search_dirs = _icon_search_dirs(icon_dir)

    def _resolve_icon_file(token):
        if not token:
            return None
        tok = str(token)
        candidates = [tok] if tok.lower().endswith(".png") else [tok + ".png", tok]
        for base in search_dirs:
            if not base.is_dir():
                continue
            for name in candidates:
                p = base / name
                if p.is_file():
                    return p
        return None

    def get_icon(token, owned=True, size=24):
        key = (token, bool(owned), int(size))
        if key in icon_cache:
            return icon_cache[key]
        icon_file = _resolve_icon_file(token)
        img = _load_tk_icon(icon_file, size=size, owned=bool(owned)) if icon_file else None
        icon_cache[key] = img
        return img

    canvas._icon_cache = icon_cache

    if not summary or not summary.get("started"):
        canvas.create_text(
            24,
            H // 2,
            text="No save file detected yet — start a new game in the port and save.",
            anchor="w",
            fill=muted,
            font=("TkDefaultFont", 10, "italic"),
        )
        return canvas

    # =========================================================================
    # COLUMN 1: VITAL STATS (x = 0 .. 110)
    # =========================================================================
    done = int(summary.get("done", 0))
    total = int(summary.get("total", 0))
    chk_txt = f"{done}/{total}" if total > 0 else "—"
    hearts_val = int(summary.get("hearts", 3))
    skulls_val = int(summary.get("skulltulas", 0))
    rupee_val = int(summary.get("rupees", 0))
    rupee_owned = rupee_val > 0
    skull_owned = skulls_val > 0

    canvas.create_text(16, 16, text="PROGRESS", anchor="w", fill=muted, font=("TkDefaultFont", 7, "bold"))

    # Row 1: Hearts (y = 42)
    canvas.create_text(24, 42, text="♥", anchor="center", fill="#d13b47", font=("TkDefaultFont", 12, "bold"))
    canvas.create_text(40, 42, text=str(hearts_val), anchor="w", fill="#d13b47", font=("TkDefaultFont", 10, "bold"))

    # Row 2: Gold Skulltulas (y = 74)
    skull_img = get_icon("Item_Token_Gold", skull_owned, size=18)
    if skull_img is not None:
        canvas.create_image(24, 74, image=skull_img)
    else:
        canvas.create_text(24, 74, text="☠", anchor="center", fill="#c49421" if skull_owned else unowned_ink, font=("TkDefaultFont", 11, "bold"))
    canvas.create_text(
        40, 74, text=str(skulls_val), anchor="w",
        fill="#c49421" if skull_owned else unowned_ink,
        font=("TkDefaultFont", 10, "bold" if skull_owned else "normal"),
    )

    # Row 3: Rupees (y = 106)
    rupee_img = (
        get_icon("Obj_Rupee_Green", rupee_owned, size=18)
        or get_icon("Item_Rupee_Green", rupee_owned, size=18)
        or get_icon("Rupee", rupee_owned, size=18)
    )
    if rupee_img is not None:
        canvas.create_image(24, 106, image=rupee_img)
    else:
        gem_pts = [24, 98, 29, 103, 27, 113, 21, 113, 19, 103]
        canvas.create_polygon(
            gem_pts,
            fill="#2e9b5c" if rupee_owned else unowned_fill,
            outline="#1e6b3f" if rupee_owned else unowned_outline,
            width=1.2,
        )
    canvas.create_text(
        40, 106, text=str(rupee_val), anchor="w",
        fill="#2e9b5c" if rupee_owned else unowned_ink,
        font=("TkDefaultFont", 10, "bold" if rupee_owned else "normal"),
    )

    # Row 4: Checks (y = 138)
    canvas.create_text(24, 138, text="✓", anchor="center", fill=ink, font=("TkDefaultFont", 10, "bold"))
    canvas.create_text(40, 138, text=chk_txt, anchor="w", fill=ink, font=("TkDefaultFont", 9, "bold"))

    # Bottom: Save Slot Badge (y = 164 .. 188)
    canvas.create_rectangle(14, 164, 96, 188, fill=slot_bg, outline=slot_border, width=1)
    canvas.create_text(55, 176, text=str(summary.get("slot", "New File")), anchor="center", fill=muted, font=("TkDefaultFont", 8, "bold"))

    canvas.create_line(110, 14, 110, H - 14, fill=sep_col)

    # =========================================================================
    # COLUMN 2: MEDALLION RING & SPIRITUAL STONES (x = 110 .. 250, cx = 180)
    # =========================================================================
    cx = 180
    canvas.create_text(cx, 16, text="QUEST STATUS", anchor="center", fill=muted, font=("TkDefaultFont", 7, "bold"))

    # Medallion Ring (cy = 82, r = 40 -> outer bounds y = 30 .. 134, x = 128 .. 232)
    cy, ring_r = 82, 40
    canvas.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, outline=ring_guide, width=1.2)
    for idx, med in enumerate(summary.get("medallions") or []):
        angle = math.radians(-90 + idx * 60)
        mx = cx + ring_r * math.cos(angle)
        my = cy + ring_r * math.sin(angle)
        owned = bool(med.get("owned"))
        m_item = med.get("item") or ""
        m_icon = (
            get_icon(med.get("icon"), owned, size=22)
            or get_icon(m_item.replace(" ", "_"), owned, size=22)
            or get_icon("Item_" + m_item.replace(" ", "_"), owned, size=22)
        )
        if m_icon is not None:
            canvas.create_image(mx, my, image=m_icon)
        else:
            fill = med["colour"] if owned else unowned_fill
            outline = med.get("border", med["colour"]) if owned else unowned_outline
            canvas.create_oval(mx - 12, my - 12, mx + 12, my + 12, fill=fill, outline=outline, width=1.6)
            if owned:
                canvas.create_oval(mx - 9, my - 9, mx + 9, my + 9, outline="#ffffff", width=0.8)
            canvas.create_text(mx, my, text=med["abbr"], fill="#ffffff" if owned else unowned_ink, font=("TkDefaultFont", 7, "bold"))

    # Subtle separator between Medallion ring and Spiritual Stones
    canvas.create_line(132, 144, 228, 144, fill=ring_guide)

    # 3 Spiritual Stones cleanly centered below the ring (y = 170)
    stone_xs = [142, 180, 218]
    sy = 170
    for sx, st in zip(stone_xs, summary.get("stones") or []):
        owned = bool(st.get("owned"))
        s_item = st.get("item") or ""
        s_icon = (
            get_icon(st.get("icon"), owned, size=22)
            or get_icon(s_item.replace(" ", "_"), owned, size=22)
            or get_icon("Item_" + s_item.replace(" ", "_"), owned, size=22)
        )
        if s_icon is not None:
            canvas.create_image(sx, sy, image=s_icon)
        else:
            fill = st["colour"] if owned else unowned_fill
            outline = st.get("border", st["colour"]) if owned else unowned_outline
            pts = [sx, sy - 12, sx + 11, sy - 2, sx + 7, sy + 11, sx - 7, sy + 11, sx - 11, sy - 2]
            canvas.create_polygon(pts, fill=fill, outline=outline, width=1.5)
            canvas.create_text(sx, sy + 1, text=st["abbr"], fill="#ffffff" if owned else unowned_ink, font=("TkDefaultFont", 7, "bold"))

    canvas.create_line(250, 14, 250, H - 14, fill=sep_col)

    # =========================================================================
    # COLUMN 3: 3x9 INVENTORY GRID & OCARINA SONGS (x = 250 .. 614)
    # =========================================================================
    grid_x0, grid_y0 = 266, 14
    cell_box = 32
    cell_pitch = 37
    for r_idx, row in enumerate(summary.get("items") or []):
        for c_idx, cell in enumerate(row):
            x = grid_x0 + c_idx * cell_pitch
            y = grid_y0 + r_idx * cell_pitch
            owned = cell.get("state") == "owned"
            box_fill = card_bg if owned else slot_bg
            box_out = cell.get("colour", line) if owned else slot_border
            canvas.create_rectangle(x, y, x + cell_box, y + cell_box, fill=box_fill, outline=box_out, width=1.5 if owned else 1)
            img = get_icon(cell.get("icon"), owned, size=24)
            if img is not None:
                canvas.create_image(x + cell_box // 2, y + cell_box // 2, image=img)
                lvl = int(cell.get("level", 0))
                if lvl > 1:
                    bx2, by2 = x + cell_box - 1, y + cell_box - 1
                    canvas.create_rectangle(bx2 - 10, by2 - 10, bx2, by2, fill=cell.get("colour", ink), outline="")
                    canvas.create_text(bx2 - 5, by2 - 5, text=str(lvl), anchor="center", fill="#ffffff", font=("TkDefaultFont", 7, "bold"))
            else:
                canvas.create_text(
                    x + cell_box // 2,
                    y + cell_box // 2,
                    text=cell.get("abbr", ""),
                    fill=box_out if owned else unowned_ink,
                    font=("TkDefaultFont", 8, "bold" if owned else "normal"),
                )

    # Horizontal divider separating Inventory Grid and Songs
    canvas.create_line(266, 130, 598, 130, fill=sep_col)

    # 2 rows of 6 Song PNG icons + Scarecrow Song PNG on right
    song_x0 = 278
    song_pitch = 50
    for s_row_idx, s_row in enumerate((summary.get("songs_top") or [], summary.get("songs_warp") or [])):
        sy_row = 149 + s_row_idx * 30
        for idx, song in enumerate(s_row):
            sx = song_x0 + idx * song_pitch
            owned = bool(song.get("owned"))
            col = song["colour"] if owned else unowned_ink
            song_name = song.get("item", "")
            token = _SONG_ICON_TOKENS.get(song_name) or _SONG_ICON_TOKENS.get(song_name.replace(chr(39), ""))
            icon_img = get_icon(token, owned=owned, size=24) if token else None
            if icon_img is not None:
                canvas.create_image(sx, sy_row, image=icon_img, anchor="center")
            else:
                canvas.create_oval(sx - 11, sy_row - 11, sx + 11, sy_row + 11, fill=card_bg if owned else slot_bg, outline=col if owned else slot_border, width=1.4 if owned else 1)
                canvas.create_text(sx, sy_row, text=song.get("abbr", ""), fill=col, font=("TkDefaultFont", 7, "bold" if owned else "normal"))

    extra_songs = summary.get("songs_extra") or []
    for idx, song in enumerate(extra_songs):
        sx = 582 + idx * 28
        sy_ex = 164
        owned = bool(song.get("owned"))
        col = song["colour"] if owned else unowned_ink
        ex_tok = "Song_Scarecrow" if owned else ("Song_Scarecrow_Empty" if _resolve_icon_file("Song_Scarecrow_Empty") else "Song_Scarecrow")
        ex_img = get_icon(ex_tok, owned=owned, size=24)
        if ex_img is not None:
            canvas.create_image(sx, sy_ex, image=ex_img, anchor="center")
        else:
            canvas.create_oval(sx - 11, sy_ex - 11, sx + 11, sy_ex + 11, fill=card_bg if owned else slot_bg, outline=col if owned else slot_border, width=1.4 if owned else 1)
            canvas.create_text(sx, sy_ex, text=song.get("abbr", "Sc"), fill=col, font=("TkDefaultFont", 7, "bold" if owned else "normal"))

    canvas.create_line(614, 14, 614, H - 14, fill=sep_col)

    # =========================================================================
    # COLUMN 4: BOTTLES (1 ROW OF 5) & KEY UPGRADES (x = 614 .. 844)
    # =========================================================================
    rx0 = 628
    bottles_list = summary.get("bottles") or []
    b_owned_cnt = sum(1 for b in bottles_list if b.get("owned"))
    canvas.create_text(rx0, 16, text=f"BOTTLES ({b_owned_cnt}/5)", anchor="w", fill=muted, font=("TkDefaultFont", 7, "bold"))

    b_w, b_h, b_gap = 36, 48, 5
    for b_idx, b in enumerate(bottles_list):
        bx = rx0 + b_idx * (b_w + b_gap)
        by = 30
        owned = bool(b.get("owned"))
        b_out = "#a9814a" if owned else slot_border
        canvas.create_rectangle(bx, by, bx + b_w, by + b_h, fill=card_bg if owned else slot_bg, outline=b_out, width=1.5 if owned else 1)
        b_img = get_icon(b.get("icon"), owned, size=22)
        if b_img is not None:
            canvas.create_image(bx + b_w // 2, by + 16, image=b_img)
            canvas.create_text(bx + b_w // 2, by + 38, text=b["slot"], fill="#a9814a" if owned else unowned_ink, font=("TkDefaultFont", 7, "bold" if owned else "normal"))
        else:
            canvas.create_text(bx + b_w // 2, by + b_h // 2, text=b["slot"], fill="#a9814a" if owned else unowned_ink, font=("TkDefaultFont", 8, "bold" if owned else "normal"))

    canvas.create_line(rx0, 92, 828, 92, fill=sep_col)

    canvas.create_text(rx0, 106, text="UPGRADES", anchor="w", fill=muted, font=("TkDefaultFont", 7, "bold"))
    q_w, q_h, q_gx, q_gy = 97, 34, 6, 8
    for q_idx, q in enumerate(summary.get("quest_items") or []):
        qx = rx0 + (q_idx % 2) * (q_w + q_gx)
        qy = 118 + (q_idx // 2) * (q_h + q_gy)
        lvl = int(q.get("level", 0))
        owned = lvl > 0
        q_col = q.get("colour", ink) if owned else unowned_ink
        q_out = q.get("colour", line) if owned else slot_border
        canvas.create_rectangle(qx, qy, qx + q_w, qy + q_h, fill=card_bg if owned else slot_bg, outline=q_out, width=1.4 if owned else 1)
        q_img = get_icon(q.get("icon"), owned, size=20)
        txt_x = qx + 8
        if q_img is not None:
            canvas.create_image(qx + 15, qy + q_h // 2, image=q_img)
            txt_x = qx + 29
        lbl = f"{q['label']} {lvl}/{q.get('max', 1)}" if q.get("max", 1) > 1 else q["label"]
        canvas.create_text(txt_x, qy + q_h // 2, text=lbl, anchor="w", fill=q_col, font=("TkDefaultFont", 7, "bold" if owned else "normal"))

    return canvas
