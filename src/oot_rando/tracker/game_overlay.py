"""In-game HUD: a transparent window glued to Hookshot's game window, movable with the mouse.

Hookshot keeps the pad and the sound while the window in front of it is a tool or
no-activate window (host/nn_hid.c game_in_front), and its fullscreen is a borderless
window: a topmost layered window therefore stays visible in both modes without
taking the input.

overlay_model() is pure (testable anywhere); GameHud is Windows-only.
"""
import ctypes
import json
import os
import tkinter as tk
from pathlib import Path
from oot_rando.paths import resource, state_dir

# (AP item, abbreviation, label, levels shown, colour when owned)
EQUIPMENT, ITEMS, MAGIC = '#5f84b0', '#a9814a', '#8466b0'
GRID = [
    [('Kokiri Sword', 'KS', 'Kokiri Sword', 1, EQUIPMENT), ('Biggoron Sword', 'BS', 'Biggoron\'s Sword', 1, EQUIPMENT),
     ('Deku Shield', 'DS', 'Deku Shield', 1, EQUIPMENT), ('Hylian Shield', 'HS', 'Hylian Shield', 1, EQUIPMENT),
     ('Mirror Shield', 'MS', 'Mirror Shield', 1, EQUIPMENT), ('Iron Boots', 'IB', 'Iron Boots', 1, EQUIPMENT),
     ('Hover Boots', 'HB', 'Hover Boots', 1, EQUIPMENT), ('Progressive Strength Upgrade', 'St', 'Strength', 3, EQUIPMENT),
     ('Progressive Scale', 'Sc', 'Scale', 2, EQUIPMENT)],
    [('Slingshot', 'Sl', 'Slingshot', 3, ITEMS), ('Bow', 'Bow', 'Bow', 3, ITEMS),
     ('Bomb Bag', 'Bo', 'Bomb Bag', 3, ITEMS), ('Progressive Hookshot', 'Hk', 'Hookshot', 2, ITEMS),
     ('Boomerang', 'Bm', 'Boomerang', 1, ITEMS), ('Megaton Hammer', 'MH', 'Megaton Hammer', 1, ITEMS),
     ('Lens of Truth', 'LT', 'Lens of Truth', 1, ITEMS), ('Ocarina', 'Oc', 'Ocarina', 2, ITEMS),
     ('Bottle', 'Bt', 'Bottle', 1, ITEMS)],
    [('Magic Meter', 'Mg', 'Magic', 2, MAGIC), ('Dins Fire', 'Din', 'Din\'s Fire', 1, MAGIC),
     ('Farores Wind', 'Far', 'Farore\'s Wind', 1, MAGIC), ('Nayrus Love', 'Nay', 'Nayru\'s Love', 1, MAGIC),
     ('Fire Arrows', 'FA', 'Fire Arrows', 1, MAGIC), ('Ice Arrows', 'IA', 'Ice Arrows', 1, MAGIC),
     ('Light Arrows', 'LA', 'Light Arrows', 1, MAGIC), ('Zeldas Letter', 'ZL', 'Zelda\'s Letter', 1, ITEMS),
     ('Stone of Agony', 'SA', 'Stone of Agony', 1, ITEMS)],
    [('Kokiri Emerald', 'KE', 'Kokiri Emerald', 1, '#3c9a5c'), ('Goron Ruby', 'GR', 'Goron Ruby', 1, '#b8463c'),
     ('Zora Sapphire', 'ZS', 'Zora Sapphire', 1, '#3c6fb8'), ('Forest Medallion', 'Fo', 'Forest Medallion', 1, '#3c8f4a'),
     ('Fire Medallion', 'Fi', 'Fire Medallion', 1, '#b8553a'), ('Water Medallion', 'Wa', 'Water Medallion', 1, '#3a74b8'),
     ('Spirit Medallion', 'Sp', 'Spirit Medallion', 1, '#b8923a'), ('Shadow Medallion', 'Sh', 'Shadow Medallion', 1, '#744ca0'),
     ('Light Medallion', 'Li', 'Light Medallion', 1, '#b8a83e')],
]
# Game icons per level (RomFS UI/Tex/Icon/<name>.bntx.zs), extracted locally by icon_extract.py.
# Level 0 (missing) shows the first one, greyed. Stones and medallions have no 2D icon in the
# game (its menu shows models): they are drawn as shapes.
ICONS = {
    'Kokiri Sword': ['Weapon_Sword_Kokiri'], 'Biggoron Sword': ['Weapon_Sword_Biggoron'],
    'Deku Shield': ['Weapon_Shield_Deku'], 'Hylian Shield': ['Weapon_Shield_Hylian'],
    'Mirror Shield': ['Weapon_Shield_Mirror'], 'Iron Boots': ['Armor_Adult_HeavyBoot'],
    'Hover Boots': ['Armor_Adult_HoverBoot'],
    'Progressive Strength Upgrade': ['Armor_Child_Gauntlet_Goron', 'Armor_Adult_Gauntlet_Silver', 'Armor_Adult_Gauntlet_Gold'],
    'Progressive Scale': ['Item_Scale_Silver', 'Item_Scale_Gold'],
    'Slingshot': ['Weapon_Range_SlingShot', 'Item_BulletBag_Medium', 'Item_BulletBag_Large'],
    'Bow': ['Weapon_Range_Bow', 'Item_Quiver_Medium', 'Item_Quiver_Large'],
    'Bomb Bag': ['Item_BombBag_Small', 'Item_BombBag_Medium', 'Item_BombBag_Large'],
    'Progressive Hookshot': ['Item_Hookshot', 'Item_Longshot'], 'Boomerang': ['Item_Boomerang'],
    'Megaton Hammer': ['Item_Hammer'], 'Lens of Truth': ['Armor_GlassTruth'],
    'Ocarina': ['Item_Ocarina_Fairy', 'Item_Ocarina_Time'], 'Bottle': ['Item_Bottle'],
    'Magic Meter': ['Item_FairyBless_MP', 'Item_FairyBless_MPDouble'], 'Dins Fire': ['Item_DinFire'],
    'Farores Wind': ['Item_FaroreWind'], 'Nayrus Love': ['Item_NayruLove'], 'Fire Arrows': ['Item_Arrow_Fire'],
    'Ice Arrows': ['Item_Arrow_Ice'], 'Light Arrows': ['Item_Arrow_Light'], 'Zeldas Letter': ['Item_ZeldaLetter'],
    'Stone of Agony': ['Item_AgonyStone'],
}
SHAPES = {'Kokiri Emerald': 'stone', 'Goron Ruby': 'stone', 'Zora Sapphire': 'stone'}   # others in row 4: medallions
ICON_SIZE = 128   # cached PNG size; scaled down per cell


def icon_name(item, level):
    names = ICONS.get(item)
    if not names:
        return None
    return names[min(max(level, 1), len(names)) - 1]


def all_icon_names():
    return sorted({name for names in ICONS.values() for name in names})


def overlay_model(inventory, readable, tracked, checks, states):
    """Everything the HUD draws, from the tracker's observations only.

    inventory: {item: level} observed in the save; readable: items whose flag the save holds;
    tracked: items the seed has inventory rules for. An item outside both is 'unknown' (never
    shown as missing: the save simply does not tell).
    """
    cells = []
    for row in GRID:
        line = []
        for item, abbr, label, levels, colour in row:
            level = int(inventory.get(item, 0))
            if level:
                state = 'owned'
            elif item in tracked and item in readable:
                state = 'missing'
            else:
                state = 'unknown'
            line.append({'item': item, 'abbr': abbr, 'label': label, 'level': level,
                         'levels': levels, 'colour': colour, 'state': state,
                         'icon': icon_name(item, level),
                         'shape': SHAPES.get(item, 'medallion' if item.endswith('Medallion') else None)})
        cells.append(line)
    souls = sorted(item for item in tracked if item.startswith('Soul ('))
    soul_count = (sum(1 for item in souls if inventory.get(item)), len(souls)) if souls else None
    done = sum(1 for check in checks if states.get(check['id'], {}).get('completed'))
    return {'cells': cells, 'souls': soul_count, 'done': done, 'total': len(checks)}


# ---------------------------------------------------------------- Windows window
KEY = '#010203'          # transparent colour key: no background panel at all
SHADOW = '#000000'       # text outline, readable over the game without a panel
TEXT, ACCENT = '#e8edf2', '#a2e2b8'
MISSING_FG, UNKNOWN_FG = '#7a848e', '#5a636c'
GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x8, 0x20, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x8000000
# Not WS_EX_TRANSPARENT: the drawn pixels take the mouse (drag); colour-keyed pixels
# stay click-through, and NOACTIVATE keeps the game in front (pad and sound kept).
HUD_STYLE = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
POSITION_FILE = state_dir() / 'overlay_position.json'
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
HWND_TOPMOST = -1
GAME_EXE = 'hookshot.exe'


class _Win32:
    def __init__(self):
        from ctypes import wintypes
        self.wt = wintypes
        self.user32, self.kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        u = self.user32
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.GetForegroundWindow.restype = wintypes.HWND
        self.enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def pid(self, hwnd):
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(self.wt.HWND(hwnd), ctypes.byref(pid))
        return pid.value

    def exe(self, pid):
        handle = self.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ''
        try:
            size = self.wt.DWORD(520)
            buffer = ctypes.create_unicode_buffer(size.value)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value).name.lower()
            return ''
        finally:
            self.kernel32.CloseHandle(handle)

    def client_rect(self, hwnd):
        rect, origin = self.wt.RECT(), self.wt.POINT(0, 0)
        h = self.wt.HWND(hwnd)
        if not self.user32.GetClientRect(h, ctypes.byref(rect)) or not self.user32.ClientToScreen(h, ctypes.byref(origin)):
            return None
        return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top

    def find_game(self):
        """The largest visible top-level window of a hookshot.exe process."""
        found, names = [], {}

        def visit(hwnd, _):
            if self.user32.IsWindowVisible(hwnd):
                pid = self.pid(hwnd)
                if pid not in names:
                    names[pid] = self.exe(pid)
                if names[pid] == GAME_EXE:
                    rect = self.client_rect(hwnd)
                    if rect and rect[2] > 0 and rect[3] > 0:
                        found.append((rect[2] * rect[3], hwnd, pid))
            return True
        self.user32.EnumWindows(self.enum_proc(visit), 0)
        return max(found)[1:] if found else (None, None)


def decoder_pythons():
    """Interpreters able to run icon_extract.py: HookshotBuilder's bundled Python first."""
    import sys
    found = []
    base = Path(os.environ.get('LOCALAPPDATA', '')) / 'HookshotBuilder' / 'versions'
    if base.is_dir():
        found += sorted(base.glob('*/HookshotBuilder/tools/python/python.exe'), reverse=True)
    found.append(Path(sys.executable))
    return found


class IconCache:
    """Game icons as Tk images, extracted once from the player's RomFS into `folder`."""
    def __init__(self, folder, romfs=None):
        self.folder, self.romfs = Path(folder), Path(romfs) if romfs else None
        self.images, self.version, self.status = {}, 0, ''
        self._thread = None

    def missing(self):
        return [n for n in all_icon_names() if not (self.folder / f'{n}.png').is_file()]

    def ensure(self, done=None):
        """Extract missing icons in the background; `done()` is called from that thread."""
        import subprocess
        import threading
        names = self.missing()
        if not names or (self._thread and self._thread.is_alive()):
            return
        if not self.romfs or not (self.romfs / 'UI' / 'Tex' / 'Icon').is_dir():
            self.status = 'icons: RomFS not found'
            return
        script = resource('tracker', 'icon_extract.py')

        def work():
            for python in decoder_pythons():
                if not python.is_file():
                    continue
                try:
                    result = subprocess.run([str(python), '-I', str(script), str(self.romfs), str(self.folder),
                                             str(ICON_SIZE)] + names, capture_output=True, text=True, timeout=300,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except (OSError, subprocess.SubprocessError):
                    continue
                if 'ok ' in result.stdout:
                    self.status = f"icons: {result.stdout.count('ok ')} extracted"
                    break
                self.status = 'icons: ASTC decoder unavailable'
            self.version += 1
            if done:
                done()
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def get(self, name, size, owned):
        """A PhotoImage, or None (no file yet, or Pillow without Tk support)."""
        key = (name, size, owned)
        if key in self.images:
            return self.images[key]
        path = self.folder / f'{name}.png'
        image = None
        if path.is_file():
            try:
                from PIL import Image, ImageTk
                picture = Image.open(path).convert('RGBA')
                picture.thumbnail((size, size), Image.LANCZOS)
                if not owned:
                    grey = picture.convert('LA').convert('RGBA')
                    alpha = grey.getchannel('A').point(lambda a: a * 50 // 100)
                    grey.putalpha(alpha)
                    picture = grey
                image = ImageTk.PhotoImage(picture)
            except (ImportError, OSError, ValueError):
                image = None
        if image is not None:   # (a missing file may appear once extraction ends)
            self.images[key] = image
        return image


class GameHud:
    """Toggle with toggle(); feed with update(model). Follows the game window by itself."""
    TICK_MS = 250

    def __init__(self, root, preview=None, icons=None, position_file=POSITION_FILE):
        self.root = root
        self.position_file = Path(position_file) if position_file else None
        self.offset = self._load_offset()   # (x, y) from the game's client corner, None = default
        self.drag, self.client = None, None
        self.icons = icons
        self.preview = os.environ.get('OOT_HUD_PREVIEW') == '1' if preview is None else preview
        self.enabled, self.model, self.drawn = False, None, None
        self.game, self.game_pid, self.rescan = None, None, 0
        self.shown, self.status = False, 'Overlay hidden'
        self.win = _Win32()
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.configure(background=KEY)
        self.top.attributes('-topmost', True)
        self.top.attributes('-transparentcolor', KEY)
        self.top.attributes('-alpha', 0.9)
        self.canvas = tk.Canvas(self.top, background=KEY, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self._drag_start)
        self.canvas.bind('<B1-Motion>', self._drag_move)
        self.canvas.bind('<ButtonRelease-1>', self._drag_end)
        self.top.geometry('1x1+-32000+-32000')
        self.top.update_idletasks()
        self.hwnd = int(self.top.wm_frame(), 16)
        self._apply_style()
        self.win.user32.ShowWindow(self.hwnd, SW_HIDE)
        self.root.after(self.TICK_MS, self._tick)

    def _apply_style(self):
        u = self.win.user32
        style = u.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        wanted = (style | HUD_STYLE) & ~WS_EX_TRANSPARENT
        if style != wanted:
            u.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, wanted)

    # ------------------------------------------------------------ position
    def _load_offset(self):
        try:
            value = json.loads(self.position_file.read_text(encoding='utf-8'))
            return int(value['x']), int(value['y'])
        except Exception:
            return None

    def _save_offset(self):
        if not self.position_file or self.offset is None:
            return
        try:
            self.position_file.parent.mkdir(parents=True, exist_ok=True)
            self.position_file.write_text(json.dumps({'x': self.offset[0], 'y': self.offset[1]}), encoding='utf-8')
        except OSError:
            pass

    def _drag_start(self, event):
        self.drag = (event.x_root, event.y_root, self.top.winfo_x(), self.top.winfo_y())

    def _drag_move(self, event):
        if not self.drag:
            return
        sx, sy, wx, wy = self.drag
        self.top.geometry(f'+{wx + event.x_root - sx}+{wy + event.y_root - sy}')

    def _drag_end(self, event):
        if not self.drag:
            return
        self._drag_move(event)
        self.top.update_idletasks()
        self.drag = None
        if self.client:
            self.offset = (self.top.winfo_x() - self.client[0], self.top.winfo_y() - self.client[1])
            self._save_offset()

    def place(self, client, size, margin):
        """Top-left corner of the HUD: saved offset, kept inside the game's client area."""
        x, y, width, height = client
        w, h = size
        dx, dy = self.offset if self.offset is not None else (margin, margin)
        dx = max(0, min(dx, width - w)) if width > w else 0
        dy = max(0, min(dy, height - h)) if height > h else 0
        return x + dx, y + dy

    def toggle(self):
        self.enabled = not self.enabled
        self._tick(reschedule=False)
        return self.enabled

    def update(self, model):
        self.model = model   # drawn at the next tick (≤ 250 ms)

    def _target(self):
        """(x, y, width, height) of the game's client area when the HUD should show, else None."""
        if self.preview:
            return 0, 0, 1280, 720
        u = self.win.user32
        if self.game and not u.IsWindow(self.game):
            self.game = None
        if not self.game:
            self.rescan -= 1
            if self.rescan > 0:
                self.status = 'Overlay: game not found (hookshot.exe)'
                return None
            self.rescan = 8   # ~2 s between window scans
            self.game, self.game_pid = self.win.find_game()
            if not self.game:
                self.status = 'Overlay: game not found (hookshot.exe)'
                return None
        if u.IsIconic(self.game):
            self.status = 'Overlay: game minimised'
            return None
        foreground = u.GetForegroundWindow()
        if not foreground or self.win.pid(foreground) != self.game_pid:
            self.status = 'Overlay: waiting for the game in the foreground'
            return None
        self.status = 'Overlay on'
        return self.win.client_rect(self.game)

    def _tick(self, reschedule=True):
        try:
            target = self._target() if self.enabled else None
            if not self.enabled:
                self.status = 'Overlay hidden'
            if target and self.model:
                self.client = target
                scale = max(0.8, min(1.5, target[3] / 720))
                w, h = self._draw(scale)
                if not self.drag:   # never fight the mouse while dragging
                    left, top = self.place(target, (w, h), int(8 * scale))
                    self.top.geometry(f'{w}x{h}+{left}+{top}')
                self._apply_style()
                u = self.win.user32
                if not self.shown:
                    u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
                    self.shown = True
                u.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            elif self.shown:
                self.win.user32.ShowWindow(self.hwnd, SW_HIDE)
                self.shown = False
        except tk.TclError:
            return
        if reschedule:
            self.root.after(self.TICK_MS, self._tick)

    def _draw(self, scale):
        key = (id(self.model), scale, self.icons.version if self.icons else 0)
        if key == self.drawn:
            return self._size
        self.drawn = key
        m, c = self.model, self.canvas
        c.delete('all')
        s = lambda v: max(1, int(round(v * scale)))
        cell, gap, pad, line = s(22), s(2), s(2), s(13)
        cols = max(len(row) for row in m['cells'])
        width = 2 * pad + cols * cell + (cols - 1) * gap
        text_lines = 1 + bool(m['souls'])   # only the soul and check counts are written
        height = 2 * pad + len(m['cells']) * (cell + gap) + s(4) + text_lines * line
        abbr_font = ('Segoe UI', -s(9), 'bold')
        level_font = ('Segoe UI', -s(8), 'bold')
        bold = ('Segoe UI', -s(10), 'bold')

        def label(x, y, value, fill, font, anchor):
            # Dark outline instead of a background panel.
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
                c.create_text(x + ox, y + oy, text=value, fill=SHADOW, font=font, anchor=anchor)
            c.create_text(x, y, text=value, fill=fill, font=font, anchor=anchor)
        y = pad
        for row in m['cells']:
            x = pad
            for entry in row:
                state = entry['state']
                picture = (self.icons.get(entry['icon'], cell, state == 'owned')
                           if self.icons and entry['icon'] and state != 'unknown' else None)
                if picture:
                    c.create_image(x + cell / 2, y + cell / 2, image=picture)
                elif entry['shape'] and state != 'unknown':
                    colour = entry['colour'] if state == 'owned' else ''   # missing: outline only
                    edge = TEXT if state == 'owned' else MISSING_FG
                    inset = s(5)
                    if entry['shape'] == 'stone':
                        c.create_polygon(x + cell / 2, y + inset, x + cell - inset, y + cell / 2, x + cell / 2,
                                         y + cell - inset, x + inset, y + cell / 2, fill=colour, outline=edge,
                                         width=max(1, s(1.5)))
                    else:
                        c.create_oval(x + inset, y + inset, x + cell - inset, y + cell - inset, fill=colour,
                                      outline=edge, width=max(1, s(2)))
                else:
                    fg, text = {'owned': (TEXT, entry['abbr']), 'missing': (MISSING_FG, entry['abbr']),
                                'unknown': (UNKNOWN_FG, '?')}[state]
                    if state == 'owned':
                        c.create_rectangle(x, y, x + cell, y + cell, fill=entry['colour'], outline='')
                    label(x + cell / 2, y + cell / 2, text, fg, abbr_font, 'center')
                    # Fallback only: with game icons, each level already has its own picture.
                    if entry['levels'] > 1 and entry['level'] >= 1:
                        label(x + cell - s(1), y + cell, str(entry['level']), ACCENT, level_font, 'se')
                x += cell + gap
            y += cell + gap
        y += s(4)

        def count(name, done, total):
            nonlocal y
            label(pad, y, name, TEXT, bold, 'nw')
            label(width - pad, y, f'{done}/{total}', ACCENT, bold, 'ne')
            y += line
        if m['souls']:
            count('Souls', *m['souls'])
        count('Checks', m['done'], m['total'])
        self._size = (width, height)
        return self._size


def demo_model():
    """A plausible model for previews (OOT_HUD_PREVIEW=1 python game_overlay.py)."""
    owned = {'Kokiri Sword': 1, 'Deku Shield': 1, 'Slingshot': 1, 'Bomb Bag': 2, 'Progressive Hookshot': 1,
             'Ocarina': 1, 'Kokiri Emerald': 1, 'Forest Medallion': 1, 'Dins Fire': 1, 'Soul (Gohma)': 1}
    tracked = {entry[0] for row in GRID for entry in row} - {'Stone of Agony'}
    tracked |= {'Soul (Gohma)', 'Soul (Dodongo)', 'Soul (Keese)'}
    checks = [{'id': str(i), 'region': region} for i, region in enumerate(
        ['Kokiri Forest'] * 6 + ['Hyrule Field'] * 4 + ['Market'] * 3 + ['Kakariko Village'] * 2 + ['Lake Hylia'])]
    states = {str(i): {'completed': i < 3, 'access': 'available' if i % 2 else 'blocked'} for i in range(len(checks))}
    return overlay_model(owned, tracked, tracked, checks, states)


if __name__ == '__main__':
    app = tk.Tk()
    app.title('Overlay — demo')
    hookshot = os.environ.get('OOT_HOOKSHOT_DIR')   # Hookshot folder, for the game icons
    cache = IconCache(state_dir() / 'icons', Path(hookshot) / 'romfs' if hookshot else None)
    cache.ensure()
    hud = GameHud(app, icons=cache)
    hud.update(demo_model())
    hud.toggle()
    tk.Label(app, textvariable=tk.StringVar(value='Overlay demo: close this window to quit.')).pack(padx=20, pady=20)
    app.mainloop()
