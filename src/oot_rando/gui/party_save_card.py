"""Compact OoT file-select style save summary card with real game item icons."""
import base64
from collections import Counter
import io
import json
import math
from pathlib import Path
import tkinter as tk

from oot_rando.paths import state_dir
from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.tracker import game_overlay
from oot_rando.tracker.save_reader import load_snapshot

_SAVE_SUMMARY_CACHE = {}

STONES = [
    ("Kokiri Emerald", "KE", "#45b854"),
    ("Goron Ruby", "GR", "#d13b47"),
    ("Zora Sapphire", "ZS", "#3982d6"),
]

# Clockwise starting at top (12 o'clock) to match the OoT medallion ring
MEDALLIONS = [
    ("Light Medallion", "Li", "#d8c448"),
    ("Forest Medallion", "Fo", "#46b34f"),
    ("Fire Medallion", "Fi", "#d45538"),
    ("Water Medallion", "Wa", "#3b7ed6"),
    ("Spirit Medallion", "Sp", "#d99436"),
    ("Shadow Medallion", "Sh", "#8c56c4"),
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


def _newest_party_save(saves_dir):
    root = Path(saves_dir)
    if not root.is_dir():
        return None
    best = None
    best_mtime = -1.0
    for sav in root.rglob("progress.sav"):
        try:
            mt = sav.stat().st_mtime
        except OSError:
            continue
        if mt > best_mtime:
            best_mtime = mt
            best = sav
    return best


def _build_grid_and_badges(counts, known, tracked):
    items_grid = []
    for row in game_overlay.GRID[:3]:
        line = []
        for item, abbr, label, levels, colour in row:
            level = int(counts.get(item, 0))
            state = "owned" if level else ("missing" if (item in tracked and item in known) else "unknown")
            line.append({
                "item": item,
                "abbr": abbr,
                "label": label,
                "level": level,
                "colour": colour,
                "state": state,
                "icon": game_overlay.icon_name(item, level),
            })
        items_grid.append(line)

    stones = [{"item": it, "abbr": ab, "colour": col, "owned": bool(counts.get(it, 0))} for it, ab, col in STONES]
    medallions = [{"item": it, "abbr": ab, "colour": col, "owned": bool(counts.get(it, 0))} for it, ab, col in MEDALLIONS]

    def _song_owned(name):
        if counts.get(name, 0):
            return True
        alt = name.replace("s ", chr(39) + "s ")
        return bool(counts.get(alt, 0))

    songs_top = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_TOP]
    songs_warp = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_WARP]
    songs_extra = [{"item": it, "abbr": ab, "colour": col, "owned": _song_owned(it)} for it, ab, col in SONGS_EXTRA]
    return items_grid, stones, medallions, songs_top, songs_warp, songs_extra


def summarize_party_save(seed_dir, saves_dir):
    """Return an OoT file-select summary dict for a party seed + save folder."""
    seed_path = Path(seed_dir)
    checks_path = seed_path / "checks.json"
    metadata = {}
    if checks_path.is_file():
        try:
            data = json.loads(checks_path.read_text(encoding="utf-8"))
            metadata = data.get("tracker") or data
        except Exception:
            metadata = {}

    checks_map = metadata.get("checks") if isinstance(metadata.get("checks"), dict) else {}
    total = len(checks_map)
    tracked = {r.get("item") for r in metadata.get("inventory", []) if r.get("item")}

    sav = _newest_party_save(saves_dir)
    if sav is None:
        items_grid, stones, medallions, songs_top, songs_warp, songs_extra = _build_grid_and_badges(Counter(), set(), tracked)
        return {
            "started": False,
            "slot": "New File",
            "hearts": 3,
            "skulltulas": 0,
            "done": 0,
            "total": total,
            "stones": stones,
            "medallions": medallions,
            "items": items_grid,
            "songs_top": songs_top,
            "songs_warp": songs_warp,
            "songs_extra": songs_extra,
        }

    try:
        st = sav.stat()
        ck_mtime = checks_path.stat().st_mtime_ns if checks_path.is_file() else 0
    except OSError:
        items_grid, stones, medallions, songs_top, songs_warp, songs_extra = _build_grid_and_badges(Counter(), set(), tracked)
        return {
            "started": False,
            "slot": "New File",
            "hearts": 3,
            "skulltulas": 0,
            "done": 0,
            "total": total,
            "stones": stones,
            "medallions": medallions,
            "items": items_grid,
            "songs_top": songs_top,
            "songs_warp": songs_warp,
            "songs_extra": songs_extra,
        }

    cache_key = (str(sav), st.st_mtime_ns, st.st_size, str(checks_path), ck_mtime)
    cached = _SAVE_SUMMARY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        snapshot = load_snapshot(sav)
    except Exception:
        items_grid, stones, medallions, songs_top, songs_warp, songs_extra = _build_grid_and_badges(Counter(), set(), tracked)
        return {
            "started": False,
            "slot": "New File",
            "hearts": 3,
            "skulltulas": 0,
            "done": 0,
            "total": total,
            "stones": stones,
            "medallions": medallions,
            "items": items_grid,
            "songs_top": songs_top,
            "songs_warp": songs_warp,
            "songs_extra": songs_extra,
        }

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

    for item, amount in observed_counts.items():
        if item in ("Gold Skulltula Token", "Heart Container", "Piece of Heart"):
            counts[item] = max(counts[item], amount)
        elif item in tracked or any(item == s[0] for s in SONGS_TOP + SONGS_WARP):
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

    str_lvl = int(counts.get("Progressive Strength Upgrade", 0))
    scl_lvl = int(counts.get("Progressive Scale", 0))
    agony_lvl = 1 if counts.get("Stone of Agony", 0) else 0
    letter_lvl = 1 if counts.get("Zeldas Letter", 0) else 0

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
            "label": "Agony Stone",
            "level": agony_lvl,
            "max": 1,
            "colour": "#a9814a",
            "icon": game_overlay.icon_name("Stone of Agony", 1),
        },
        {
            "label": "Zelda Letter",
            "level": letter_lvl,
            "max": 1,
            "colour": "#a9814a",
            "icon": game_overlay.icon_name("Zeldas Letter", 1),
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
    """Load a cached game icon PNG resized cleanly, dimmed when unowned."""
    try:
        from PIL import Image, ImageEnhance
        img = Image.open(icon_path).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        if not owned:
            r, g, b, a = img.split()
            gray = Image.merge("RGB", (r, g, b)).convert("L")
            gray = ImageEnhance.Brightness(gray).enhance(0.45)
            alpha = a.point(lambda px: int(px * 0.42))
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
    "Scarecrow Song": "Song_Scarecrow",
}

def render_party_save_card(parent, summary, colors, icon_dir=None):
    bg = colors.get("panel_bg", "#f7f3e8")
    card_bg = colors.get("card_bg", "#fffdf7")
    line = colors.get("line", "#d7cfb8")
    ink = colors.get("ink", "#2b261d")
    muted = colors.get("muted", "#736a58")

    canvas = tk.Canvas(
        parent,
        width=860,
        height=204,
        background=bg,
        highlightthickness=1,
        highlightbackground=line,
        borderwidth=0,
    )
    canvas.pack(anchor="w", pady=(2, 0))

    icon_cache = {}
    search_dirs = []
    if icon_dir:
        search_dirs.append(Path(icon_dir))
    repo_root = Path(__file__).resolve().parents[3]
    for cand in (
        repo_root / "build" / "app" / "icons",
        Path(__file__).resolve().parent / "icons",
        Path(__file__).resolve().parent.parent / "assets" / "icons",
        Path(__file__).resolve().parent.parent / "tracker" / "icons",
        state_dir() / "icons",
    ):
        if cand not in search_dirs:
            search_dirs.append(cand)

    def _resolve_icon_file(token):
        if not token:
            return None
        candidates = [token] if str(token).lower().endswith(".png") else [f"{token}.png", str(token)]
        for base in search_dirs:
            if not base.is_dir():
                continue
            for name in candidates:
                p = base / name
                if p.is_file():
                    return p
        return None

    def get_icon(token, owned=True):
        key = (token, bool(owned))
        if key in icon_cache:
            return icon_cache[key]
        icon_file = _resolve_icon_file(token)
        img = _load_tk_icon(icon_file, size=24, owned=bool(owned)) if icon_file else None
        icon_cache[key] = img
        return img

    canvas._icon_cache = icon_cache

    if not summary or not summary.get("started"):
        canvas.create_text(
            18,
            92,
            text="No save file detected yet — start a new game in the port and save.",
            anchor="w",
            fill=muted,
            font=("TkDefaultFont", 10, "italic"),
        )
        return canvas

    # Left column: Hearts, Skulls, Checks, Save slot
    done = int(summary.get("done", 0))
    total = int(summary.get("total", 0))
    chk_txt = f"{done}/{total}" if total > 0 else "—"
    rupee_val = int(summary.get("rupees", 0))
    rupee_owned = rupee_val > 0
    grey_fill = "#ebe6d8"
    grey_outline = "#bdb49f"
    grey_ink = "#8a816e"

    canvas.create_text(14, 24, text="♥ " + str(summary.get("hearts", 3)), anchor="w", fill="#c93b3b", font=("TkDefaultFont", 11, "bold"))
    canvas.create_text(14, 52, text="☠ " + str(summary.get("skulltulas", 0)), anchor="w", fill="#b5891e", font=("TkDefaultFont", 11, "bold"))

    rupee_img = get_icon("Item_Rupee_Green", rupee_owned) or get_icon("Rupee", rupee_owned)
    if rupee_img is not None:
        canvas.create_image(22, 80, image=rupee_img)
    else:
        gem_pts = [22, 72, 28, 77, 26, 87, 18, 87, 16, 77]
        gem_fill = "#2e8b57" if rupee_owned else grey_fill
        gem_out = "#1f663e" if rupee_owned else grey_outline
        canvas.create_polygon(gem_pts, fill=gem_fill, outline=gem_out, width=1.2)
    canvas.create_text(35, 80, text=str(rupee_val), anchor="w", fill="#2e8b57" if rupee_owned else grey_ink, font=("TkDefaultFont", 10, "bold" if rupee_owned else "normal"))

    canvas.create_text(14, 108, text="✓ " + chk_txt, anchor="w", fill=ink, font=("TkDefaultFont", 10, "bold"))
    canvas.create_text(14, 140, text=summary.get("slot", "New File"), anchor="w", fill=muted, font=("TkDefaultFont", 9, "bold"))

    canvas.create_line(618, 14, 618, 190, fill=line)

    # Medallion ring (clockwise from 12 o'clock) + 3 Spiritual Stones across center
    cx, cy, ring_r = 150, 92, 46
    for idx, med in enumerate(summary.get("medallions") or []):
        angle = math.radians(-90 + idx * 60)
        mx = cx + ring_r * math.cos(angle)
        my = cy + ring_r * math.sin(angle)
        owned = bool(med.get("owned"))
        m_name = med.get("name") or med.get("label") or med.get("abbr") or ""
        m_icon = get_icon(med.get("icon") or m_name.replace(" ", "_"), owned)
        if m_icon is not None:
            canvas.create_image(mx, my, image=m_icon)
        else:
            fill = med["colour"] if owned else grey_fill
            outline = med["colour"] if owned else grey_outline
            canvas.create_oval(mx - 12, my - 12, mx + 12, my + 12, fill=fill, outline=outline, width=1.5)
            canvas.create_text(mx, my, text=med["abbr"], fill="#ffffff" if owned else grey_ink, font=("TkDefaultFont", 8, "bold"))

    stone_xs = [122, 150, 178]
    sy = cy
    for sx, st in zip(stone_xs, summary.get("stones") or []):
        owned = bool(st.get("owned"))
        s_name = st.get("name") or st.get("label") or st.get("abbr") or ""
        s_icon = get_icon(st.get("icon") or s_name.replace(" ", "_"), owned)
        if s_icon is not None:
            canvas.create_image(sx, sy, image=s_icon)
        else:
            fill = st["colour"] if owned else grey_fill
            outline = st["colour"] if owned else grey_outline
            pts = [sx, sy - 10, sx + 10, sy, sx, sy + 10, sx - 10, sy]
            canvas.create_polygon(pts, fill=fill, outline=outline, width=1.5)
            canvas.create_text(sx, sy, text=st["abbr"], fill="#ffffff" if owned else grey_ink, font=("TkDefaultFont", 7, "bold"))

    canvas.create_line(214, 12, 214, 172, fill=line)

    # Center: 3x9 Item & Equipment grid
    grid_x0, grid_y0 = 254, 14
    cell_w, cell_h = 35, 35
    for r_idx, row in enumerate(summary.get("items") or []):
        for c_idx, cell in enumerate(row):
            x = grid_x0 + c_idx * cell_w
            y = grid_y0 + r_idx * cell_h
            owned = cell.get("state") == "owned"
            box_fill = card_bg
            box_out = cell.get("colour", line) if owned else line
            canvas.create_rectangle(x, y, x + 30, y + 30, fill=box_fill, outline=box_out, width=1.5 if owned else 1)
            img = get_icon(cell.get("icon"), owned)
            if img is not None:
                canvas.create_image(x + 15, y + 15, image=img)
                if cell.get("level", 0) > 1:
                    canvas.create_text(
                        x + 26,
                        y + 25,
                        text=str(cell["level"]),
                        anchor="se",
                        fill=ink if owned else muted,
                        font=("TkDefaultFont", 7, "bold"),
                    )
            else:
                canvas.create_text(
                    x + 15,
                    y + 15,
                    text=cell.get("abbr", ""),
                    fill=box_out if owned else muted,
                    font=("TkDefaultFont", 8, "bold" if owned else "normal"),
                )

    # Bottom center: 2 rows of 6 Song PNG icons only + 13th Scarecrow's Song badge
    song_x0 = 254
    for s_row_idx, s_row in enumerate((summary.get("songs_top") or [], summary.get("songs_warp") or [])):
        sy_row = 132 + s_row_idx * 30
        for idx, song in enumerate(s_row):
            sx = song_x0 + idx * 55
            owned = bool(song.get("owned"))
            col = song["colour"] if owned else muted
            song_name = song.get("item", "")
            token = _SONG_ICON_TOKENS.get(song_name) or _SONG_ICON_TOKENS.get(song_name.replace("'", ""))
            icon_img = get_icon(token, owned=owned) if token else None
            if icon_img is not None:
                canvas.create_image(sx + 12, sy_row, image=icon_img, anchor="center")
            else:
                canvas.create_oval(sx + 2, sy_row - 10, sx + 22, sy_row + 10, fill=card_bg, outline=col if owned else line, width=1.5 if owned else 1)

    extra_songs = summary.get("songs_extra") or []
    for idx, song in enumerate(extra_songs):
        sx = song_x0 + 6 * 55 + 6 + idx * 24
        col = song["colour"] if song["owned"] else muted
        canvas.create_oval(sx - 9, 138, sx + 9, 156, fill=card_bg, outline=col if song["owned"] else line, width=1.5 if song["owned"] else 1)
        canvas.create_text(sx, 147, text=song["abbr"], fill=col, font=("TkDefaultFont", 7, "bold" if song["owned"] else "normal"))
    canvas.create_line(616, 12, 616, 172, fill=line)

    # Right column: 5 Bottle slots (B1..B5) + Quest upgrades
    bx0, by0 = 630, 14
    canvas.create_text(bx0, by0 + 8, text="Bottles (5)", anchor="w", fill=muted, font=("TkDefaultFont", 8, "bold"))
    for b_idx, b in enumerate(summary.get("bottles") or []):
        bx = bx0 + (b_idx % 3) * 66
        by = by0 + 22 + (b_idx // 3) * 28
        owned = bool(b.get("owned"))
        b_col = "#a9814a" if owned else line
        canvas.create_rectangle(bx, by, bx + 58, by + 24, fill=card_bg, outline=b_col, width=1.5 if owned else 1)
        b_img = get_icon(b.get("icon"), owned)
        if b_img is not None:
            canvas.create_image(bx + 13, by + 12, image=b_img)
            canvas.create_text(bx + 39, by + 12, text=b["slot"], fill="#a9814a" if owned else muted, font=("TkDefaultFont", 8, "bold" if owned else "normal"))
        else:
            canvas.create_text(bx + 29, by + 12, text=b["slot"], fill="#a9814a" if owned else muted, font=("TkDefaultFont", 8, "bold" if owned else "normal"))

    qx0, qy0 = 630, 96
    canvas.create_text(qx0, qy0 + 7, text="Quest", anchor="w", fill=muted, font=("TkDefaultFont", 8, "bold"))
    for q_idx, q in enumerate(summary.get("quest_items") or []):
        qx = qx0 + (q_idx % 2) * 102
        qy = qy0 + 28 + (q_idx // 2) * 28
        lvl = int(q.get("level", 0))
        owned = lvl > 0
        q_col = q.get("colour", ink) if owned else muted
        q_img = get_icon(q.get("icon"), owned)
        txt_x = qx
        if q_img is not None:
            canvas.create_image(qx + 10, qy, image=q_img)
            txt_x = qx + 24
        lbl = f"{q['label']} ({lvl}/{q.get('max', 1)})" if q.get("max", 1) > 1 else q["label"]
        canvas.create_text(txt_x, qy, text=lbl, anchor="w", fill=q_col, font=("TkDefaultFont", 7, "bold" if owned else "normal"))

    return canvas
