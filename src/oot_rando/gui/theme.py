"""Visual theme of the desktop application: Hyrule palette, rounded ttk elements, sidebar.

Everything is drawn with Tk alone (no image files, no extra dependency): rounded shapes
are rendered once into small PNG images, then stretched by ttk as nine-slice elements.
"""
import base64
import struct
import tkinter as tk
import zlib
from tkinter import font as tkfont
from tkinter import ttk

# Forest green, Triforce gold, Hylian blue, on parchment.
COLORS = {
    'page': '#f2eee3',          # parchment behind the cards
    'surface': '#fffdf8',       # cards
    'field': '#f7f3ea',         # inputs, secondary buttons, logs
    'field_hover': '#efe9db',
    'line': '#e3dccb',
    'line_strong': '#cfc5ad',
    'text': '#1f2a24',
    'muted': '#6c766d',
    'faint': '#a3a99f',
    'green': '#2f7a55',
    'green_soft': '#e4efe7',
    'gold': '#d5a62b',
    'gold_hover': '#e2b746',
    'gold_pressed': '#c0921c',
    'gold_text': '#2b2108',
    'blue': '#2f5f8f',
    'sidebar': '#163a2d',
    'sidebar_hover': '#1e4a3a',
    'sidebar_active': '#245a45',
    'sidebar_text': '#b9d2c2',
    'sidebar_muted': '#7f9e8d',
    'track_off': '#d8d0bd',
    'amber': '#b3741a',
    'gold_soft': '#f8eecf',
    'hero_line': '#2c5a48',
}

# Tracker states, readable on the light cards.
CARD_PADDING = (24, 20, 24, 22)

STATE_COLORS = {'done': '#9aa197', 'available': '#2f7a55', 'partial': '#9a7412',
                'blocked': '#a3562e', 'unknown': '#4d6c8c'}


# ------------------------------------------------------------------ images
def _png(width, height, pixels):
    """Encode RGBA rows (list of bytearrays) as a PNG, base64 for tk.PhotoImage."""
    raw = b''.join(b'\x00' + bytes(row) for row in pixels)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    return base64.b64encode(data)


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _box_distance(px, py, x0, y0, x1, y1, radius):
    """Signed distance from a point to a rounded rectangle (negative inside)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - radius)
    qy = abs(py - cy) - ((y1 - y0) / 2 - radius)
    outside = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** 0.5
    return outside + min(max(qx, qy), 0) - radius


def _paint(width, height, layers, stretch=0):
    """Composite anti-aliased layers. Each layer: (distance function, colour, alpha).

    ``stretch`` widens and heightens the image by repeating its middle column and row:
    ttk tiles the centre of a nine-slice image, and a tiny centre means thousands of
    alpha-blended tiles per card (seconds of redraw). A large centre needs a handful.
    """
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r = g = b = a = 0.0
            for distance, color, alpha in layers:
                coverage = min(max(0.5 - distance(x + 0.5, y + 0.5), 0.0), 1.0) * alpha
                if coverage <= 0:
                    continue
                cr, cg, cb = _rgb(color)
                out = coverage + a * (1 - coverage)
                if out > 0:
                    r = (cr * coverage + r * a * (1 - coverage)) / out
                    g = (cg * coverage + g * a * (1 - coverage)) / out
                    b = (cb * coverage + b * a * (1 - coverage)) / out
                a = out
            row += bytes((int(r + 0.5), int(g + 0.5), int(b + 0.5), int(a * 255 + 0.5)))
        rows.append(row)
    if stretch:
        mx, my = (width // 2) * 4, height // 2
        rows = [row[:mx] + row[mx:mx + 4] * (stretch + 1) + row[mx + 4:] for row in rows]
        rows = rows[:my] + [rows[my]] * (stretch + 1) + rows[my + 1:]
        width, height = width + stretch, height + stretch
    return tk.PhotoImage(data=_png(width, height, rows), format='png')


def rounded(fill, border=None, radius=8, size=None, border_width=1.0, shadow=False, stretch=160):
    """Rounded rectangle image for a nine-slice element (give the element its own width/height:
    by default ttk would request the stretched image size)."""
    size = size or radius * 2 + 4
    pad = 2 if shadow else 0
    w = h = size + pad
    layers = []
    if shadow:
        layers.append((lambda x, y: _box_distance(x, y, 0, 1.5, size, size + 1.5, radius) + 0.6, '#5b4f33', 0.10))
    if border:
        layers.append((lambda x, y: _box_distance(x, y, 0, 0, size, size, radius), border, 1.0))
        layers.append((lambda x, y: _box_distance(x, y, border_width, border_width, size - border_width,
                                                  size - border_width, radius - border_width), fill, 1.0))
    else:
        layers.append((lambda x, y: _box_distance(x, y, 0, 0, size, size, radius), fill, 1.0))
    return _paint(w, h, layers, stretch)


def switch(on, disabled=False):
    """Toggle switch indicator (with a right margin before the label)."""
    track = (COLORS['green'] if on else COLORS['track_off'])
    if disabled:
        track = '#b9cdbf' if on else '#e6e0d1'
    w, h, margin = 38, 22, 10
    knob_x = w - h / 2 if on else h / 2
    layers = [(lambda x, y: _box_distance(x, y, 0, 0, w, h, h / 2), track, 1.0),
              (lambda x, y: ((x - knob_x) ** 2 + (y - h / 2 + 0.6) ** 2) ** 0.5 - (h / 2 - 2.2), '#5b4f33', 0.18),
              (lambda x, y: ((x - knob_x) ** 2 + (y - h / 2) ** 2) ** 0.5 - (h / 2 - 3), '#ffffff', 1.0)]
    return _paint(w + margin, h, layers)


def disc(color, size, border=None, width=2.0):
    """Filled circle (status dot, step badge). With ``border``, an outlined circle."""
    half = size / 2
    layers = [(lambda x, y: ((x - half) ** 2 + (y - half) ** 2) ** 0.5 - half, border or color, 1.0)]
    if border:
        layers.append((lambda x, y: ((x - half) ** 2 + (y - half) ** 2) ** 0.5 - (half - width), color, 1.0))
    return _paint(size, size, layers)


def chevron(color):
    """Small down chevron for combobox arrows."""
    def stroke(x, y):
        # Distance to the polyline (3,5)-(7,9)-(11,5), thickness 1.6.
        def seg(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            return ((x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2) ** 0.5
        return min(seg(3, 5.5, 7, 9.5), seg(7, 9.5, 11, 5.5)) - 0.8
    return _paint(14, 14, [(stroke, color, 1.0)])


def triforce(canvas, x, y, size, color):
    """Three golden triangles: the application mark."""
    h = size * 0.866
    half, quarter = size / 2, size / 4
    for ox, oy in [(quarter, 0), (0, h / 2), (half, h / 2)]:
        canvas.create_polygon(x + ox + quarter, y + oy, x + ox + half, y + oy + h / 2, x + ox, y + oy + h / 2,
                              fill=color, outline=color)


# ------------------------------------------------------------------ fonts
def pick_font(root, *names):
    available = set(tkfont.families(root))
    return next((name for name in names if name in available), 'TkDefaultFont')


class Fonts:
    def __init__(self, root):
        ui = pick_font(root, 'Segoe UI', 'Noto Sans', 'DejaVu Sans', 'Helvetica')
        strong = pick_font(root, 'Segoe UI Semibold', ui)
        display = pick_font(root, 'Georgia', 'Cambria', 'DejaVu Serif', 'Times New Roman', ui)
        mono = pick_font(root, 'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', 'Courier New')
        self.icons = pick_font(root, 'Segoe Fluent Icons', 'Segoe MDL2 Assets')
        self.has_icons = self.icons != 'TkDefaultFont'
        self.body = (ui, 10)
        self.small = (ui, 9)
        self.strong = (strong, 10)
        self.label = (strong, 9)
        self.heading = (strong, 12)
        self.title = (display, 24, 'bold')
        self.brand = (display, 12, 'bold')
        self.mono = (mono, 9)
        self.nav = (ui, 10)
        self.nav_active = (strong, 10)


# ------------------------------------------------------------------ ttk style
def apply(root):
    """Configure every ttk style used by the application. Returns (fonts, images)."""
    c, f = COLORS, Fonts(root)
    images = {
        'card': rounded(c['surface'], c['line'], radius=12, size=30, shadow=True, stretch=480),
        'field': rounded(c['field'], c['line_strong'], radius=7, size=20),
        'field_focus': rounded(c['surface'], c['green'], radius=7, size=20, border_width=1.6),
        'field_disabled': rounded(c['page'], c['line'], radius=7, size=20),
        'button': rounded(c['field'], c['line_strong'], radius=8, size=20),
        'button_hover': rounded(c['field_hover'], c['line_strong'], radius=8, size=20),
        'button_pressed': rounded('#e6dfcd', c['line_strong'], radius=8, size=20),
        'button_disabled': rounded(c['page'], c['line'], radius=8, size=20),
        'accent': rounded(c['gold'], radius=8, size=20),
        'accent_hover': rounded(c['gold_hover'], radius=8, size=20),
        'accent_pressed': rounded(c['gold_pressed'], radius=8, size=20),
        'accent_disabled': rounded('#e8d9a9', radius=8, size=20),
        'chip': rounded(c['green_soft'], radius=11, size=24),
        'switch_off': switch(False), 'switch_on': switch(True),
        'switch_off_disabled': switch(False, True), 'switch_on_disabled': switch(True, True),
        'chevron': chevron(c['muted']),
        'card_selected': rounded(c['surface'], c['gold'], radius=12, size=30, border_width=2.0, shadow=True, stretch=480),
        'hero': rounded(c['sidebar'], radius=13, size=30, stretch=480),
        'tab': rounded(c['surface'], c['line_strong'], radius=10, size=24),
        'tab_on': rounded(c['green_soft'], c['green'], radius=10, size=24, border_width=1.6),
        'badge_done': disc(c['green'], 28), 'badge_on': disc(c['gold'], 28),
        'badge_off': disc(c['surface'], 28, border=c['line_strong']),
        'dot_ok': disc(c['green'], 10), 'dot_warn': disc(c['amber'], 10), 'dot_off': disc(c['faint'], 10),
    }
    root.configure(background=c['page'])
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=c['surface'], foreground=c['text'], font=f.body, bordercolor=c['line'],
                    lightcolor=c['line'], darkcolor=c['line'], troughcolor=c['field'], focuscolor=c['green'],
                    selectbackground=c['green_soft'], selectforeground=c['text'], insertcolor=c['text'])

    style.element_create('Card.bg', 'image', images['card'], border=14, width=32, height=32, sticky='nsew')
    style.layout('Card.TFrame', [('Card.bg', {'sticky': 'nsew'})])
    style.configure('Card.TFrame', background=c['page'])
    style.configure('TFrame', background=c['surface'])
    style.configure('Page.TFrame', background=c['page'])

    style.configure('TLabel', background=c['surface'], foreground=c['text'])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Small.TLabel', foreground=c['muted'], font=f.small)
    style.configure('Field.TLabel', foreground=c['muted'], font=f.label)
    style.configure('Heading.TLabel', font=f.heading, padding=(0, 0, 0, 2))
    style.configure('Page.TLabel', background=c['page'], foreground=c['muted'])
    style.configure('PageTitle.TLabel', background=c['page'], foreground=c['text'], font=f.title)
    style.configure('PageSub.TLabel', background=c['page'], foreground=c['muted'])
    style.element_create('Chip.bg', 'image', images['chip'], border=11, width=26, height=26, sticky='nsew')
    style.layout('Chip.TLabel', [('Chip.bg', {'sticky': 'nsew', 'children': [
        ('Label.padding', {'sticky': 'nsew', 'children': [('Label.label', {'sticky': 'nsew'})]})]})])
    style.configure('Chip.TLabel', background=c['green_soft'], foreground=c['green'], font=f.label, padding=(12, 4))

    # Buttons: soft secondary, golden primary.
    style.element_create('Button.rounded', 'image', images['button'], ('disabled', images['button_disabled']),
                         ('pressed', images['button_pressed']), ('active', images['button_hover']),
                         border=8, padding=(6, 4), width=20, height=20, sticky='nsew')
    style.element_create('Accent.rounded', 'image', images['accent'], ('disabled', images['accent_disabled']),
                         ('pressed', images['accent_pressed']), ('active', images['accent_hover']),
                         border=8, padding=(6, 4), width=20, height=20, sticky='nsew')
    for name, element in [('TButton', 'Button.rounded'), ('Accent.TButton', 'Accent.rounded')]:
        style.layout(name, [(element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
    style.configure('TButton', background=c['surface'], foreground=c['text'], padding=(10, 3), anchor='center')
    style.map('TButton', foreground=[('disabled', c['faint'])], background=[('active', c['surface'])])
    style.configure('Accent.TButton', foreground=c['gold_text'], font=f.strong, padding=(14, 4))
    style.map('Accent.TButton', foreground=[('disabled', '#8c7a4a')])
    style.layout('Link.TButton', [('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})])
    style.configure('Link.TButton', foreground=c['green'], font=f.strong, padding=(2, 2), background=c['surface'])
    style.map('Link.TButton', foreground=[('active', c['text']), ('disabled', c['faint'])], background=[('active', c['surface'])])

    # Fields.
    style.element_create('Field.rounded', 'image', images['field'], ('disabled', images['field_disabled']),
                         ('focus', images['field_focus']), border=8, padding=(6, 4), width=20, height=20, sticky='nsew')
    style.layout('TEntry', [('Field.rounded', {'sticky': 'nsew', 'children': [
        ('Entry.padding', {'sticky': 'nsew', 'children': [('Entry.textarea', {'sticky': 'nsew'})]})]})])
    style.configure('TEntry', padding=(6, 3), foreground=c['text'])
    style.map('TEntry', foreground=[('disabled', c['faint'])])
    style.element_create('Chevron.arrow', 'image', images['chevron'], sticky='')
    style.layout('TCombobox', [('Field.rounded', {'sticky': 'nsew', 'children': [
        ('Chevron.arrow', {'side': 'right', 'sticky': 'ns'}),
        ('Combobox.padding', {'expand': '1', 'sticky': 'nsew', 'children': [('Combobox.textarea', {'sticky': 'nsew'})]})]})])
    style.configure('TCombobox', padding=(6, 2, 4, 2), foreground=c['text'], arrowsize=14)
    style.map('TCombobox', fieldbackground=[('readonly', c['field'])], foreground=[('disabled', c['faint'])],
              selectbackground=[('readonly', c['field'])], selectforeground=[('readonly', c['text'])])
    style.configure('TSpinbox', fieldbackground=c['field'], foreground=c['text'], arrowcolor=c['muted'],
                    padding=(8, 5), bordercolor=c['line_strong'], lightcolor=c['field'], darkcolor=c['field'],
                    background=c['field'])
    for key, value in [('background', c['surface']), ('foreground', c['text']), ('selectBackground', c['green_soft']),
                       ('selectForeground', c['text']), ('font', f.body)]:
        root.option_add('*TCombobox*Listbox.' + key, value)

    # Checkbuttons become switches.
    style.element_create('Switch.indicator', 'image', images['switch_off'],
                         ('disabled', 'selected', images['switch_on_disabled']), ('disabled', images['switch_off_disabled']),
                         ('selected', images['switch_on']), sticky='')
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nsew', 'children': [
        ('Switch.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.label', {'side': 'left', 'sticky': 'nsew'})]})])
    style.configure('TCheckbutton', background=c['surface'], foreground=c['text'], padding=(0, 4))
    style.map('TCheckbutton', background=[('active', c['surface'])], foreground=[('disabled', c['faint'])])

    # Pages are a notebook without visible tabs: the sidebar selects them.
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('Pages.TNotebook', background=c['page'], borderwidth=0, padding=0, tabmargins=0,
                    bordercolor=c['page'], lightcolor=c['page'], darkcolor=c['page'])
    style.layout('Pages.TNotebook', [('Notebook.client', {'sticky': 'nsew'})])
    # Inner notebooks (spoiler views): underlined text tabs.
    style.configure('TNotebook', background=c['surface'], borderwidth=0, tabmargins=(0, 0, 0, 8),
                    bordercolor=c['surface'], lightcolor=c['surface'], darkcolor=c['surface'])
    style.layout('TNotebook', [('Notebook.client', {'sticky': 'nsew'})])
    style.configure('TNotebook.Tab', background=c['surface'], foreground=c['muted'], padding=(0, 6, 22, 6),
                    borderwidth=0, font=f.strong)
    style.layout('TNotebook.Tab', [('Notebook.padding', {'side': 'top', 'sticky': 'nsew', 'children': [
        ('Notebook.label', {'side': 'top', 'sticky': ''})]})])
    style.map('TNotebook.Tab', foreground=[('selected', c['green']), ('active', c['text'])],
              background=[('selected', c['surface'])], expand=[('selected', (0, 0, 0, 0))])

    style.configure('Treeview', background=c['surface'], fieldbackground=c['surface'], foreground=c['text'],
                    rowheight=30, borderwidth=0, font=f.body, relief='flat')
    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nsew'})])
    style.configure('Treeview', bordercolor=c['surface'], lightcolor=c['surface'], darkcolor=c['surface'])
    style.configure('Treeview.Heading', background=c['field'], foreground=c['muted'], font=f.label,
                    padding=(10, 8), relief='flat', borderwidth=0)
    style.map('Treeview.Heading', background=[('active', c['field_hover'])])
    style.map('Treeview', background=[('selected', c['green_soft'])], foreground=[('selected', c['text'])])

    for orient in ('Vertical', 'Horizontal'):
        style.layout(f'{orient}.TScrollbar', [(f'{orient}.Scrollbar.trough', {'sticky': 'nsew', 'children': [
            (f'{orient}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nsew'})]})])
        style.configure(f'{orient}.TScrollbar', troughcolor=c['surface'], background=c['line_strong'],
                        bordercolor=c['surface'], lightcolor=c['line_strong'], darkcolor=c['line_strong'],
                        arrowsize=8, gripcount=0, relief='flat')
        style.map(f'{orient}.TScrollbar', background=[('active', c['faint'])])
        style.configure(f'Page.{orient}.TScrollbar', troughcolor=c['page'], bordercolor=c['page'], background=c['line'], lightcolor=c['line'], darkcolor=c['line'], arrowsize=6)
    style.configure('Hidden.Vertical.TScrollbar', troughcolor=c['page'], bordercolor=c['page'], background=c['page'],
                    lightcolor=c['page'], darkcolor=c['page'], arrowsize=6)
    style.map('Hidden.Vertical.TScrollbar', background=[('active', c['page'])])
    style.configure('TProgressbar', troughcolor=c['line'], background=c['gold'], bordercolor=c['page'],
                    lightcolor=c['gold'], darkcolor=c['gold'], thickness=6)
    style.configure('TSeparator', background=c['line'])

    # Home hero, selectable cards, counters, step badges.
    style.element_create('CardSelected.bg', 'image', images['card_selected'], border=14, width=32, height=32, sticky='nsew')
    style.layout('CardSelected.TFrame', [('CardSelected.bg', {'sticky': 'nsew'})])
    style.configure('CardSelected.TFrame', background=c['page'])
    style.element_create('Hero.bg', 'image', images['hero'], border=14, width=32, height=32, sticky='nsew')
    style.layout('Hero.TFrame', [('Hero.bg', {'sticky': 'nsew'})])
    style.configure('Hero.TFrame', background=c['page'])
    style.configure('HeroIn.TFrame', background=c['sidebar'])
    style.configure('Hero.TLabel', background=c['sidebar'], foreground='#f4eedc', font=f.strong)
    style.configure('HeroMuted.TLabel', background=c['sidebar'], foreground=c['sidebar_text'])
    style.configure('HeroField.TLabel', background=c['sidebar'], foreground=c['sidebar_text'], font=f.label)
    style.configure('HeroTitle.TLabel', background=c['sidebar'], foreground='#f4eedc', font=(f.title[0], 19, 'bold'))
    style.configure('Hero.TButton', background=c['sidebar'])
    style.map('Hero.TButton', background=[('active', c['sidebar'])])
    style.configure('Hero.Accent.TButton', background=c['sidebar'], padding=(22, 7))
    style.map('Hero.Accent.TButton', background=[('active', c['sidebar'])])
    style.configure('Hero.Horizontal.TProgressbar', troughcolor=c['hero_line'], background=c['gold'],
                    bordercolor=c['sidebar'], lightcolor=c['gold'], darkcolor=c['gold'], thickness=8)
    style.configure('Page.Link.TButton', background=c['page'])
    style.map('Page.Link.TButton', background=[('active', c['page'])])
    style.configure('PageHeading.TLabel', background=c['page'], foreground=c['text'], font=f.heading)
    style.configure('Value.TLabel', font=f.strong)
    style.configure('Preset.TLabel', font=(f.strong[0], 12))
    for name, image, background, foreground in [('Tab', 'tab', c['surface'], c['text']),
                                                ('TabOn', 'tab_on', c['green_soft'], c['green'])]:
        style.element_create(f'{name}.bg', 'image', images[image], border=11, width=26, height=26, sticky='nsew')
        style.layout(f'{name}.TFrame', [(f'{name}.bg', {'sticky': 'nsew'})])
        style.configure(f'{name}.TFrame', background=c['surface'])
        style.configure(f'{name}.TLabel', background=background, foreground=foreground)
        style.configure(f'{name}Count.TLabel', background=background, foreground=foreground, font=(f.title[0], 16, 'bold'))
    style.configure('BadgeDone.TLabel', foreground='#ffffff', font=f.strong)
    style.configure('BadgeOn.TLabel', foreground=c['gold_text'], font=f.strong)
    style.configure('BadgeOff.TLabel', foreground=c['muted'], font=f.strong)

    for key, value in [('background', c['field']), ('foreground', c['text']), ('insertBackground', c['text']),
                       ('selectBackground', c['green_soft']), ('selectForeground', c['text']),
                       ('highlightBackground', c['line']), ('highlightColor', c['line_strong']),
                       ('font', f.mono), ('relief', 'flat'), ('borderWidth', 0), ('highlightThickness', 1)]:
        root.option_add('*Text.' + key, value)
    return f, images


def badge(parent, images):
    """Round step marker: number, or a check once done. ``set(state, text)`` to update."""
    label = ttk.Label(parent, compound='center')
    def update(state, text=''):
        label.configure(image=images['badge_' + state], text='\u2713' if state == 'done' else text,
                        style={'done': 'BadgeDone.TLabel', 'on': 'BadgeOn.TLabel', 'off': 'BadgeOff.TLabel'}[state])
    label.set = update
    return label


def preset_art(canvas, kind, colors):
    """Tiny flat illustration of what a preset shuffles."""
    def chest(x):
        canvas.create_rectangle(x, 30, x + 30, 52, fill='#9a6b34', outline='')
        canvas.create_rectangle(x, 22, x + 30, 31, fill='#7a4f22', outline='')
        canvas.create_rectangle(x + 11, 27, x + 19, 35, fill=colors['gold'], outline='')
    canvas.delete('all')
    width = canvas.winfo_width() if canvas.winfo_width() > 1 else int(canvas.cget('width'))
    shapes = {'prudent': ['chest'], 'ap_defaults': ['chest', 'chest', 'coin'],
              'everything': ['chest', 'pot', 'bush', 'rock', 'coin']}[kind]
    x = (width - (len(shapes) * 38 - 8)) / 2
    for shape in shapes:
        if shape == 'chest':
            chest(x)
        elif shape == 'coin':
            canvas.create_oval(x + 4, 28, x + 28, 52, fill=colors['gold'], outline='')
        elif shape == 'pot':
            canvas.create_oval(x + 4, 26, x + 28, 54, fill='#b9674a', outline='')
            canvas.create_rectangle(x + 9, 22, x + 23, 30, fill='#a25538', outline='')
        elif shape == 'bush':
            canvas.create_arc(x + 2, 24, x + 30, 80, start=0, extent=180, fill='#4c9a6b', outline='')
        elif shape == 'rock':
            canvas.create_polygon(x + 4, 52, x + 8, 32, x + 20, 26, x + 28, 38, x + 30, 52, fill='#8a8f93', outline='')
        x += 38


def rule(parent):
    """Hairline divider between rows of a card."""
    return tk.Frame(parent, height=1, background=COLORS['line'])


# ------------------------------------------------------------------ sidebar
NAV_ICONS = {'home': '', 'newseed': '', 'setup': '', 'game': '', 'settings': '', 'tracker': '', 'multiworld': '',
             'spoiler': '', 'help': ''}


class Sidebar(tk.Frame):
    """Dark green navigation column with the Triforce mark."""

    def __init__(self, parent, fonts, on_select, footer=''):
        c = COLORS
        super().__init__(parent, background=c['sidebar'], width=230)
        self.pack_propagate(False)
        self.fonts, self.on_select, self.items, self.current = fonts, on_select, {}, None
        brand = tk.Frame(self, background=c['sidebar'])
        brand.pack(fill='x', padx=20, pady=(28, 32))
        mark = tk.Canvas(brand, width=30, height=27, background=c['sidebar'], highlightthickness=0)
        triforce(mark, 1, 1, 28, c['gold'])
        mark.pack(side='left')
        names = tk.Frame(brand, background=c['sidebar'])
        names.pack(side='left', padx=(12, 0))
        tk.Label(names, text='OoT Randomizer', font=fonts.brand, foreground='#f4eedc',
                 background=c['sidebar']).pack(anchor='w')
        tk.Label(names, text='Remake edition', font=fonts.small, foreground=c['sidebar_muted'],
                 background=c['sidebar']).pack(anchor='w')
        tk.Label(self, text='MENU', font=(fonts.label[0], 8), foreground=c['sidebar_muted'],
                 background=c['sidebar']).pack(anchor='w', padx=26, pady=(0, 6))
        self.footer = tk.Label(self, text=footer, font=fonts.small, foreground=c['sidebar_muted'],
                               background=c['sidebar'], justify='left', wraplength=170)
        self.footer.pack(side='bottom', anchor='w', padx=26, pady=20)

    def add(self, key, text):
        c = COLORS
        row = tk.Frame(self, background=c['sidebar'], cursor='hand2')
        row.pack(fill='x', padx=12, pady=1)
        bar = tk.Frame(row, background=c['sidebar'], width=3)
        bar.pack(side='left', fill='y', pady=7)
        icon = tk.Label(row, text=NAV_ICONS.get(key, '') if self.fonts.has_icons else '',
                        font=(self.fonts.icons, 12), foreground=c['sidebar_text'], background=c['sidebar'], width=2)
        icon.pack(side='left', padx=(10, 6), pady=9)
        label = tk.Label(row, text=text, font=self.fonts.nav, foreground=c['sidebar_text'],
                         background=c['sidebar'], anchor='w')
        label.pack(side='left', fill='x', expand=True, pady=9)
        parts = (row, icon, label)
        self.items[key] = (row, bar, icon, label)
        for widget in parts:
            widget.bind('<Button-1>', lambda event, k=key: self.on_select(k))
            widget.bind('<Enter>', lambda event, k=key: self.paint(k, hover=True))
            widget.bind('<Leave>', lambda event, k=key: self.paint(k))

    def gap(self):
        """Pushes the following entries to the bottom of the column."""
        tk.Frame(self, background=COLORS['sidebar']).pack(fill='both', expand=True)

    def select(self, key):
        previous, self.current = self.current, key
        if previous:
            self.paint(previous)
        self.paint(key)

    def paint(self, key, hover=False):
        c = COLORS
        row, bar, icon, label = self.items[key]
        active = key == self.current
        background = c['sidebar_active'] if active else c['sidebar_hover'] if hover else c['sidebar']
        for widget in (row, icon, label):
            widget.configure(background=background)
        bar.configure(background=c['gold'] if active else background)
        color = '#fbf6e6' if active else c['sidebar_text']
        icon.configure(foreground=c['gold'] if active else c['sidebar_text'])
        label.configure(foreground=color, font=self.fonts.nav_active if active else self.fonts.nav)
