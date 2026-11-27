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
    'muted': '#5f6960',         # 4.9:1 on the page, 5.6:1 on cards (WCAG AA)
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
    'amber_text': '#8a5a12',    # amber readable as text (5.4:1 on cards)
    'amber_soft': '#fbf1dc',
    'red': '#a3412e',
    'red_soft': '#f8e6e1',
    'gold_soft': '#f8eecf',
    'hero_line': '#2c5a48',
}

# Tracker states, readable on the light cards.
CARD_PADDING = (24, 20, 24, 22)

# Each state is told by its shape and its word too, never by the colour alone.
STATE_COLORS = {'done': '#6b7368', 'available': '#2f7a55', 'partial': '#86691a',
                'blocked': '#a3562e', 'unknown': '#4d6c8c'}
STATE_MARKS = {'done': '\u2713', 'available': '\u25cf', 'partial': '\u25d0', 'blocked': '\u25c6', 'unknown': '?'}


# ------------------------------------------------------------------ images
# Tk on X11 (Linux, the Steam Deck) reports the wheel as buttons 4 and 5, not <MouseWheel>.
WHEEL_EVENTS = ('<MouseWheel>', '<Button-4>', '<Button-5>')


def wheel_units(num, delta):
    """Lines to scroll for a wheel event: button 4 up, 5 down; else 120 a notch, at least one."""
    if num == 4:
        return -1
    if num == 5:
        return 1
    if not delta:
        return 0
    return int(-delta / 120) or (-1 if delta > 0 else 1)


def keep_values_on_wheel(root):
    """The wheel scrolls the page, never the value under the pointer.

    Tk's own combobox and spinbox bindings step their value on a wheel turn: scrolling the
    settings with the pointer over one silently changed a setting. Without them the event
    reaches the page's scroll binding instead."""
    for widget_class in ('TCombobox', 'TSpinbox'):
        for sequence in WHEEL_EVENTS + ('<Shift-MouseWheel>',):
            root.unbind_class(widget_class, sequence)


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


def switch(on, disabled=False, margin=10):
    """Toggle switch indicator; ``margin`` is the gap before its label (0 when it has none)."""
    track = (COLORS['green'] if on else COLORS['track_off'])
    if disabled:
        track = '#b9cdbf' if on else '#e6e0d1'
    w, h = 38, 22
    knob_x = w - h / 2 if on else h / 2
    layers = [(lambda x, y: _box_distance(x, y, 0, 0, w, h, h / 2), track, 1.0),
              (lambda x, y: ((x - knob_x) ** 2 + (y - h / 2 + 0.6) ** 2) ** 0.5 - (h / 2 - 2.2), '#5b4f33', 0.18),
              (lambda x, y: ((x - knob_x) ** 2 + (y - h / 2) ** 2) ** 0.5 - (h / 2 - 3), '#ffffff', 1.0)]
    return _paint(w + margin, h, layers)


def progress_bar(filled, width=48, height=8):
    """Small rounded progress bar: ``filled`` pixels of gold on a parchment track."""
    c = COLORS
    radius = height / 2
    layers = [(lambda x, y: _box_distance(x, y, 0, 0, width, height, radius), c['line'], 1.0)]
    if filled:
        layers.append((lambda x, y: _box_distance(x, y, 0, 0, max(filled, height), height, radius), c['gold'], 1.0))
    return _paint(width + 6, height, layers)   # 6 px of air before the zone name


def disc(color, size, border=None, width=2.0):
    """Filled circle (status dot, step badge). With ``border``, an outlined circle."""
    half = size / 2
    layers = [(lambda x, y: ((x - half) ** 2 + (y - half) ** 2) ** 0.5 - half, border or color, 1.0)]
    if border:
        layers.append((lambda x, y: ((x - half) ** 2 + (y - half) ** 2) ** 0.5 - (half - width), color, 1.0))
    return _paint(size, size, layers)


def checkbox(state):
    """Tracker row box: 'off' empty, 'on' ticked by hand, 'locked' confirmed by the save."""
    c = COLORS
    size = 16
    box = lambda x, y: _box_distance(x, y, 0.5, 0.5, size - 0.5, size - 0.5, 3.5)
    inner = lambda x, y: _box_distance(x, y, 1.9, 1.9, size - 1.9, size - 1.9, 2.4)
    def tick(x, y):
        def seg(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            return ((x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2) ** 0.5
        return min(seg(4, 8.5, 7, 11.5), seg(7, 11.5, 12.5, 5)) - 1.0
    if state == 'off':
        layers = [(box, c['line_strong'], 1.0), (inner, c['surface'], 1.0)]
    elif state == 'on':
        layers = [(box, c['green'], 1.0), (tick, '#ffffff', 1.0)]
    else:
        layers = [(box, c['line'], 1.0), (inner, c['field'], 1.0), (tick, STATE_COLORS['done'], 1.0)]
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
        self.count = (strong, 15)   # lining figures: Georgia's old-style ones do not align
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
        'bare_off': switch(False, margin=0), 'bare_on': switch(True, margin=0),
        'bare_off_disabled': switch(False, True, 0), 'bare_on_disabled': switch(True, True, 0),
        'check_off': checkbox('off'), 'check_on': checkbox('on'), 'check_locked': checkbox('locked'),
        'chevron': chevron(c['muted']),
        'card_selected': rounded(c['surface'], c['gold'], radius=12, size=30, border_width=2.0, shadow=True, stretch=480),
        'hero': rounded(c['sidebar'], radius=13, size=30, stretch=480),
        'tab': rounded(c['surface'], c['line_strong'], radius=10, size=24),
        'tab_on': rounded(c['green_soft'], c['green'], radius=10, size=24, border_width=1.6),
        'badge_done': disc(c['green'], 28), 'badge_on': disc(c['gold'], 28),
        'badge_off': disc(c['surface'], 28, border=c['line_strong']),
        'dot_ok': disc(c['green'], 10), 'dot_warn': disc(c['amber'], 10), 'dot_off': disc(c['faint'], 10),
        'dot_error': disc(c['red'], 10),
        **{'state_' + key: disc(color, 9) for key, color in STATE_COLORS.items()},
    }
    root.configure(background=c['page'])
    keep_values_on_wheel(root)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=c['surface'], foreground=c['text'], font=f.body, bordercolor=c['line'],
                    lightcolor=c['line'], darkcolor=c['line'], troughcolor=c['field'], focuscolor=c['gold_pressed'],
                    selectbackground=c['green_soft'], selectforeground=c['text'], insertcolor=c['text'])

    style.element_create('Card.bg', 'image', images['card'], border=14, width=32, height=32, sticky='nsew')
    style.layout('Card.TFrame', [('Card.bg', {'sticky': 'nsew'})])
    style.configure('Card.TFrame', background=c['page'])
    style.layout('CoverCard.TFrame', [('Card.bg', {'sticky': 'nsew'})])   # a card drawn on a card
    style.configure('CoverCard.TFrame', background=c['surface'])
    style.configure('TFrame', background=c['surface'])
    style.configure('Page.TFrame', background=c['page'])

    style.configure('TLabel', background=c['surface'], foreground=c['text'])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Small.TLabel', foreground=c['muted'], font=f.small)
    style.configure('Field.TLabel', foreground=c['muted'], font=f.label)
    style.configure('Heading.TLabel', font=f.heading, padding=(0, 0, 0, 2))
    style.configure('Page.TLabel', background=c['page'], foreground=c['muted'])
    style.configure('PageField.TLabel', background=c['page'], foreground=c['muted'], font=f.label)
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
        style.layout(name, [(element, {'sticky': 'nsew', 'children': [('Button.focus', {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})]})])
    style.configure('TButton', background=c['surface'], foreground=c['text'], padding=(10, 3), anchor='center')
    style.map('TButton', foreground=[('disabled', c['faint'])], background=[('active', c['surface'])])
    style.configure('Accent.TButton', foreground=c['gold_text'], font=f.strong, padding=(14, 4))
    style.map('Accent.TButton', foreground=[('disabled', '#8c7a4a')])
    style.layout('Link.TButton', [('Button.focus', {'sticky': 'nsew', 'children': [
        ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
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
    style.layout('TSpinbox', [('Field.rounded', {'sticky': 'nsew', 'children': [
        ('null', {'side': 'right', 'sticky': 'ns', 'children': [
            ('Spinbox.uparrow', {'side': 'top', 'sticky': 'e'}),
            ('Spinbox.downarrow', {'side': 'bottom', 'sticky': 'e'})]}),
        ('Spinbox.padding', {'sticky': 'nsew', 'children': [('Spinbox.textarea', {'sticky': 'nsew'})]})]})])
    style.configure('TSpinbox', fieldbackground=c['field'], foreground=c['text'], arrowcolor=c['muted'],
                    padding=(6, 3, 2, 3), arrowsize=10, background=c['field'], bordercolor=c['field'],
                    lightcolor=c['field'], darkcolor=c['field'])
    style.map('TSpinbox', background=[('active', c['field_hover'])], foreground=[('disabled', c['faint'])])
    for key, value in [('background', c['surface']), ('foreground', c['text']), ('selectBackground', c['green_soft']),
                       ('selectForeground', c['text']), ('font', f.body)]:
        root.option_add('*TCombobox*Listbox.' + key, value)

    # Checkbuttons become switches.
    style.element_create('Switch.indicator', 'image', images['switch_off'],
                         ('disabled', 'selected', images['switch_on_disabled']), ('disabled', images['switch_off_disabled']),
                         ('selected', images['switch_on']), sticky='')
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nsew', 'children': [
        ('Switch.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.focus', {'side': 'left', 'sticky': 'nsew', 'children': [
            ('Checkbutton.label', {'sticky': 'nsew'})]})]})])
    style.configure('TCheckbutton', background=c['surface'], foreground=c['text'], padding=(0, 4))
    style.map('TCheckbutton', background=[('active', c['surface'])], foreground=[('disabled', c['faint'])])
    # A switch without a label, at the right edge of a settings row: no gap after it, so it
    # lines up with the fields of the other rows; its focus ring is drawn around it.
    style.element_create('BareSwitch.indicator', 'image', images['bare_off'],
                         ('disabled', 'selected', images['bare_on_disabled']), ('disabled', images['bare_off_disabled']),
                         ('selected', images['bare_on']), sticky='')
    style.layout('Bare.TCheckbutton', [('Checkbutton.padding', {'sticky': 'nsew', 'children': [
        ('Checkbutton.focus', {'sticky': 'nsew', 'children': [('BareSwitch.indicator', {'sticky': ''})]})]})])
    style.configure('Bare.TCheckbutton', background=c['surface'], padding=(0, 4))
    style.map('Bare.TCheckbutton', background=[('active', c['surface'])])

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
        style.configure(f'{name}Count.TLabel', background=background, foreground=foreground, font=f.count)
    # Notices (banners), the hero notice, hashes, inline validation.
    for name, background, foreground in [('Error', c['red_soft'], c['red']), ('Warn', c['amber_soft'], c['amber_text']),
                                         ('Info', c['green_soft'], c['green'])]:
        style.configure(f'{name}Notice.TFrame', background=background)
        style.configure(f'{name}Notice.TLabel', background=background, foreground=c['text'])
        style.configure(f'{name}NoticeTitle.TLabel', background=background, foreground=foreground, font=f.strong)
        style.configure(f'{name}Notice.Link.TButton', background=background, foreground=foreground)
        style.map(f'{name}Notice.Link.TButton', background=[('active', background)], foreground=[('active', c['text'])])
    style.configure('HeroNotice.TFrame', background=c['hero_line'])
    style.configure('HeroNotice.TLabel', background=c['hero_line'], foreground='#f4eedc')
    style.configure('HeroNoticeMuted.TLabel', background=c['hero_line'], foreground=c['sidebar_text'])
    style.configure('HeroNotice.TButton', background=c['hero_line'])
    style.map('HeroNotice.TButton', background=[('active', c['hero_line'])])
    style.configure('HeroNotice.Accent.TButton', background=c['hero_line'])
    style.map('HeroNotice.Accent.TButton', background=[('active', c['hero_line'])])
    style.configure('Hash.TLabel', foreground=c['muted'], font=f.mono)
    # New seed: a setting that differs from its preset, the counts in the group tabs.
    style.configure('Changed.TLabel', foreground=c['amber_text'], background=c['amber_soft'], font=f.label, padding=(6, 0))
    style.configure('TabBadge.TLabel', background=c['surface'], foreground=c['amber_text'], font=f.label)
    style.configure('TabOnBadge.TLabel', background=c['green_soft'], foreground=c['amber_text'], font=f.label)
    style.configure('TabHit.TLabel', background=c['surface'], foreground=c['green'], font=f.label)
    style.configure('TabOnHit.TLabel', background=c['green_soft'], foreground=c['green'], font=f.label)
    style.configure('Help.TLabel', foreground=c['muted'], background=c['field'], padding=(10, 6), font=f.small)
    style.configure('HeroHash.TLabel', background=c['sidebar'], foreground=c['sidebar_text'], font=f.mono)
    style.configure('Ok.TLabel', foreground=c['green'], font=f.small)
    style.configure('Bad.TLabel', foreground=c['red'], font=f.small)
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
NAV_ICONS = {'home': '', 'parties': '\ue8f1', 'newseed': '', 'setup': '', 'game': '', 'settings': '', 'tracker': '', 'multiworld': '',
             'spoiler': '', 'help': ''}


def nav_glyph(canvas, key, color):
    """Menu icon drawn with Tk alone, for systems without the Segoe icon font (Linux, Steam Deck)."""
    canvas.delete('all')
    line = {'fill': '', 'outline': color, 'width': 1.6}
    if key == 'home':
        canvas.create_polygon(2, 8, 9, 2, 16, 8, 16, 16, 2, 16, **line)
    elif key == 'parties':
        for y in (3, 8, 13):
            canvas.create_rectangle(3, y, 15, y + 3, **line)
    elif key == 'newseed':
        canvas.create_line(9, 2, 9, 16, fill=color, width=1.8)
        canvas.create_line(2, 9, 16, 9, fill=color, width=1.8)
    elif key == 'tracker':
        canvas.create_line(2, 9, 6, 13, 15, 4, fill=color, width=1.8)
    elif key == 'multiworld':
        canvas.create_oval(2, 2, 16, 16, **line)
        canvas.create_line(2, 9, 16, 9, fill=color, width=1.2)
        canvas.create_oval(6, 2, 12, 16, **line)
    elif key == 'setup':
        canvas.create_oval(4, 4, 14, 14, **line)
        canvas.create_oval(7, 7, 11, 11, fill=color, outline=color)
    elif key == 'spoiler':
        canvas.create_oval(1, 5, 17, 13, **line)
        canvas.create_oval(7, 7, 11, 11, fill=color, outline=color)
    else:
        canvas.create_oval(2, 2, 16, 16, **line)
        canvas.create_text(9, 9, text='?', fill=color, font=('TkDefaultFont', 8, 'bold'))


class Sidebar(tk.Frame):
    """Dark green navigation column with the Triforce mark.

    Each entry takes the keyboard focus (Tab, then Enter or Space) and shows a gold ring
    while focused. The current adventure sits at the bottom, on every page."""

    def __init__(self, parent, fonts, on_select, footer=''):
        c = COLORS
        super().__init__(parent, background=c['sidebar'], width=230)
        self.pack_propagate(False)
        self.fonts, self.on_select, self.items, self.current = fonts, on_select, {}, None
        self.order, self.hidden = [], set()
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
        self.footer.pack(side='bottom', anchor='w', padx=26, pady=(8, 18))
        # The current adventure: name, then the seed hash; a click opens Home.
        card = self.adventure = tk.Frame(self, background=c['sidebar_hover'], cursor='hand2', takefocus=1,
                                         highlightthickness=2, highlightbackground=c['sidebar_hover'],
                                         highlightcolor=c['gold'], padx=12, pady=10)
        card.pack(side='bottom', fill='x', padx=14, pady=(10, 0))
        self.adventure_title = tk.Label(card, text='NO ADVENTURE YET', font=(fonts.label[0], 8),
                                        foreground=c['sidebar_muted'], background=c['sidebar_hover'], anchor='w')
        self.adventure_title.pack(fill='x')
        self.adventure_name = tk.Label(card, text='Create a seed to start', font=fonts.strong, foreground='#f4eedc',
                                       background=c['sidebar_hover'], anchor='w', justify='left', wraplength=180)
        self.adventure_name.pack(fill='x', pady=(2, 0))
        self.adventure_detail = tk.Label(card, text='', font=fonts.mono, foreground=c['sidebar_text'],
                                         background=c['sidebar_hover'], anchor='w')
        self.adventure_detail.pack(fill='x')
        self.adventure_action = None
        for widget in (card, self.adventure_title, self.adventure_name, self.adventure_detail):
            widget.bind('<Button-1>', lambda event: self.adventure_action and self.adventure_action())
        for sequence in ('<Return>', '<space>'):
            card.bind(sequence, lambda event: self.adventure_action and self.adventure_action())

    def set_adventure(self, title, name, detail='', action=None):
        self.adventure_title.configure(text=title.upper())
        self.adventure_name.configure(text=name)
        self.adventure_detail.configure(text=detail)
        if detail and not self.adventure_detail.winfo_manager():
            self.adventure_detail.pack(fill='x')
        elif not detail:
            self.adventure_detail.pack_forget()
        self.adventure_action = action

    def add(self, key, text):
        c = COLORS
        row = tk.Frame(self, background=c['sidebar'], cursor='hand2', takefocus=1, highlightthickness=2,
                       highlightbackground=c['sidebar'], highlightcolor=c['gold'])
        row.pack(fill='x', padx=12, pady=1)
        bar = tk.Frame(row, background=c['sidebar'], width=3)
        bar.pack(side='left', fill='y', pady=7)
        if self.fonts.has_icons:
            icon = tk.Label(row, text=NAV_ICONS.get(key, ''), font=(self.fonts.icons, 12),
                            foreground=c['sidebar_text'], background=c['sidebar'], width=2)
            icon.pack(side='left', padx=(10, 6), pady=9)
        else:
            icon = tk.Canvas(row, width=18, height=18, background=c['sidebar'], highlightthickness=0)
            icon.pack(side='left', padx=(12, 8), pady=9)
            nav_glyph(icon, key, c['sidebar_text'])
        label = tk.Label(row, text=text, font=self.fonts.nav, foreground=c['sidebar_text'],
                         background=c['sidebar'], anchor='w')
        label.pack(side='left', fill='x', expand=True, pady=9)
        self.items[key] = (row, bar, icon, label)
        self.order.append(key)
        for widget in (row, icon, label):
            widget.bind('<Button-1>', lambda event, k=key: self.on_select(k))
            widget.bind('<Enter>', lambda event, k=key: self.paint(k, hover=True))
            widget.bind('<Leave>', lambda event, k=key: self.paint(k))
        for sequence in ('<Return>', '<space>'):
            row.bind(sequence, lambda event, k=key: self.on_select(k))
        row.bind('<Down>', lambda event, k=key: self.move_focus(k, 1))
        row.bind('<Up>', lambda event, k=key: self.move_focus(k, -1))

    def move_focus(self, key, step):
        shown = [k for k in self.order if k not in self.hidden]
        self.items[shown[(shown.index(key) + step) % len(shown)]][0].focus_set()

    def set_visible(self, key, visible):
        """Show or hide an entry (My Games appears only once enabled in Setup)."""
        row = self.items[key][0]
        if visible and key in self.hidden:
            self.hidden.discard(key)
            later = [k for k in self.order[self.order.index(key) + 1:] if k not in self.hidden]
            row.pack(fill='x', padx=12, pady=1, **({'before': self.items[later[0]][0]} if later else {}))
        elif not visible and key not in self.hidden:
            self.hidden.add(key)
            row.pack_forget()

    def gap(self):
        """Pushes the following entries to the bottom of the column."""
        spacer = tk.Frame(self, background=COLORS['sidebar'])
        spacer.pack(fill='both', expand=True)

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
        row.configure(highlightbackground=background)
        bar.configure(background=c['gold'] if active else background)
        color = '#fbf6e6' if active else c['sidebar_text']
        if isinstance(icon, tk.Canvas):
            nav_glyph(icon, key, c['gold'] if active else c['sidebar_text'])
        else:
            icon.configure(foreground=c['gold'] if active else c['sidebar_text'])
        label.configure(foreground=color, font=self.fonts.nav_active if active else self.fonts.nav)


# ------------------------------------------------------------------ notices
class Notice(ttk.Frame):
    """A banner inside a page: what happened, then the actions that help.

    ``kind`` is 'error', 'warn' or 'info'. ``actions`` is a list of (text, command); the
    banner can always be closed (×). Errors and warnings no longer open a window."""

    MARKS = {'error': '✕', 'warn': '!', 'info': 'i'}

    def __init__(self, parent, kind, title, text='', actions=(), on_close=None, wraplength=640):
        name = {'error': 'Error', 'warn': 'Warn', 'info': 'Info'}[kind]
        super().__init__(parent, style=f'{name}Notice.TFrame', padding=(14, 10, 10, 10))
        self.kind = kind
        ttk.Label(self, text=self.MARKS[kind], style=f'{name}NoticeTitle.TLabel', width=2,
                  anchor='center').pack(side='left', anchor='n', padx=(0, 8))
        body = ttk.Frame(self, style=f'{name}Notice.TFrame')
        body.pack(side='left', fill='x', expand=True)
        ttk.Label(body, text=title, style=f'{name}NoticeTitle.TLabel', wraplength=wraplength,
                  justify='left').pack(anchor='w')
        if text:
            ttk.Label(body, text=text, style=f'{name}Notice.TLabel', wraplength=wraplength,
                      justify='left').pack(anchor='w', pady=(2, 0))
        if actions:
            row = ttk.Frame(body, style=f'{name}Notice.TFrame')
            row.pack(anchor='w', pady=(6, 0))
            for label, command in actions:
                ttk.Button(row, text=label, style=f'{name}Notice.Link.TButton',
                           command=command).pack(side='left', padx=(0, 14))
        close = ttk.Button(self, text='×', width=2, style=f'{name}Notice.Link.TButton',
                           command=on_close or self.destroy)
        close.pack(side='right', anchor='n')


class Toast:
    """A short message at the bottom right of the window, closed after ``delay`` ms.

    Replaces the information windows: the work goes on, the message has one action."""

    def __init__(self, root, fonts):
        self.root, self.fonts, self.frame, self.pending = root, fonts, None, None

    def show(self, text, action=None, delay=6000):
        self.hide()
        c = COLORS
        frame = self.frame = tk.Frame(self.root, background=c['sidebar'], padx=16, pady=11)
        tk.Label(frame, text=text, font=self.fonts.body, foreground='#f4eedc', background=c['sidebar'],
                 justify='left', wraplength=460).pack(side='left')
        if action:
            label, command = action
            button = tk.Label(frame, text=label, font=self.fonts.strong, foreground=c['gold'],
                              background=c['sidebar'], cursor='hand2', padx=4)
            button.pack(side='left', padx=(16, 0))
            button.bind('<Button-1>', lambda event: (self.hide(), command()))
        close = tk.Label(frame, text='×', font=self.fonts.strong, foreground=c['sidebar_text'],
                         background=c['sidebar'], cursor='hand2', padx=4)
        close.pack(side='left', padx=(12, 0))
        close.bind('<Button-1>', lambda event: self.hide())
        frame.place(relx=1.0, rely=1.0, x=-24, y=-20, anchor='se')
        frame.lift()
        self.pending = self.root.after(delay, self.hide)

    def hide(self):
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        if self.frame is not None:
            self.frame.destroy()
            self.frame = None


def search_entry(parent, variable, placeholder, width=24):
    """An entry showing ``placeholder`` in grey while it is empty and not focused.

    The label lives inside the field, so every search box of the application looks the same."""
    entry = ttk.Entry(parent, width=width)
    showing = {'hint': False}
    def show_hint(event=None):
        if not variable.get() and entry.focus_get() is not entry:
            showing['hint'] = True
            entry.configure(foreground=COLORS['muted'])
            entry.delete(0, 'end')
            entry.insert(0, placeholder)
    def hide_hint(event=None):
        if showing['hint']:
            showing['hint'] = False
            entry.delete(0, 'end')
            entry.configure(foreground=COLORS['text'])
    def typed(event=None):
        if not showing['hint']:
            value = entry.get()
            if value != variable.get():
                variable.set(value)
    def follow(*args):
        if entry.focus_get() is not entry and not showing['hint'] and entry.get() != variable.get():
            entry.delete(0, 'end')
            entry.insert(0, variable.get())
        if not variable.get():
            show_hint()
    entry.bind('<FocusIn>', hide_hint, add='+')
    entry.bind('<FocusOut>', show_hint, add='+')
    entry.bind('<KeyRelease>', typed, add='+')
    entry.bind('<Escape>', lambda event: (variable.set(''), entry.delete(0, 'end')), add='+')
    variable.trace_add('write', follow)
    show_hint()
    return entry


class Segmented(ttk.Frame):
    """A row of mutually exclusive choices (views of a page), drawn like the tracker tabs."""

    def __init__(self, parent, choices, command, value=None):
        super().__init__(parent)
        self.command, self.parts = command, {}
        for key, text in choices:
            frame = ttk.Frame(self, style='Tab.TFrame', padding=(12, 5, 12, 6), cursor='hand2', takefocus=1)
            frame.pack(side='left', padx=(0, 4))
            label = ttk.Label(frame, text=text, style='Tab.TLabel')
            label.pack()
            for widget in (frame, label):
                widget.bind('<Button-1>', lambda event, k=key: self.command(k))
            for sequence in ('<Return>', '<space>'):
                frame.bind(sequence, lambda event, k=key: self.command(k))
            self.parts[key] = (frame, label)
        self.set(value or choices[0][0])

    def set(self, key):
        for name, (frame, label) in self.parts.items():
            prefix = 'TabOn' if name == key else 'Tab'
            frame.configure(style=prefix + '.TFrame')
            label.configure(style=prefix + '.TLabel')

    def show(self, key, visible):
        frame = self.parts[key][0]
        if visible and not frame.winfo_manager():
            keys = list(self.parts)
            later = [k for k in keys[keys.index(key) + 1:] if self.parts[k][0].winfo_manager()]
            frame.pack(side='left', padx=(0, 4), **({'before': self.parts[later[0]][0]} if later else {}))
        elif not visible and frame.winfo_manager():
            frame.pack_forget()


# ------------------------------------------------------------------ tooltips
class Tooltip:
    """A help bubble shown while the pointer rests on one of ``widgets``.

    ``text`` is a string or a function returning one (read at each showing, so a
    tooltip can follow the current value). Opens after ``delay`` ms, closes on leave,
    click or scroll; it stays inside the screen."""

    def __init__(self, widgets, text, fonts, delay=450, width=380):
        self.widgets = [w for w in widgets if w is not None]
        self.text, self.fonts, self.delay, self.width = text, fonts, delay, width
        self.window, self.pending = None, None
        for widget in self.widgets:
            widget.bind('<Enter>', self.schedule, add='+')
            widget.bind('<Leave>', self.hide, add='+')
            widget.bind('<ButtonPress>', self.hide, add='+')
            widget.bind('<MouseWheel>', self.hide, add='+')

    def schedule(self, event=None):
        self.cancel()
        self.pending = self.widgets[0].after(self.delay, lambda: self.show(event))

    def cancel(self):
        if self.pending is not None:
            self.widgets[0].after_cancel(self.pending)
            self.pending = None

    def show(self, event=None):
        self.pending = None
        text = self.text() if callable(self.text) else self.text
        if not text or self.window is not None:
            return
        c = COLORS
        anchor = event.widget if event is not None else self.widgets[0]
        window = self.window = tk.Toplevel(anchor)
        window.wm_overrideredirect(True)
        try:
            window.wm_attributes('-topmost', True)
        except tk.TclError:
            pass
        frame = tk.Frame(window, background=c['line_strong'], padx=1, pady=1)
        frame.pack()
        body = tk.Frame(frame, background=c['surface'], padx=12, pady=9)
        body.pack()
        title, _, rest = text.partition('\n')
        tk.Label(body, text=title, font=self.fonts.label, foreground=c['text'], background=c['surface'],
                 justify='left', anchor='w', wraplength=self.width).pack(anchor='w')
        if rest.strip():
            tk.Label(body, text=rest.strip(), font=self.fonts.small, foreground=c['muted'],
                     background=c['surface'], justify='left', anchor='w',
                     wraplength=self.width).pack(anchor='w', pady=(4, 0))
        window.update_idletasks()
        x = anchor.winfo_rootx() + 12
        y = anchor.winfo_rooty() + anchor.winfo_height() + 6
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
        x = max(4, min(x, screen_w - width - 4))
        if y + height > screen_h - 4:
            y = anchor.winfo_rooty() - height - 6
        window.wm_geometry(f'+{x}+{y}')

    def hide(self, event=None):
        self.cancel()
        if self.window is not None:
            self.window.destroy()
            self.window = None


def ellipsize(text, font, width):
    """``text`` cut to ``width`` pixels with an ellipsis: a cut word must not read as another one."""
    text = str(text)
    if width <= 0 or font.measure(text) <= width:
        return text
    low, high = 0, len(text)
    while low < high:   # longest prefix that fits with its ellipsis
        middle = (low + high + 1) // 2
        if font.measure(text[:middle].rstrip() + '…') <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + '…'


def fit_tree(tree, fonts, fresh=True):
    """Show every cell of ``tree`` cut with an ellipsis to its column width.

    With ``fresh`` the current texts are the full ones (call it right after filling the
    tree); the tree then refits itself from them whenever it or a column is resized."""
    if fresh or not hasattr(tree, 'full_text'):
        tree.full_text = {}
        stack = list(tree.get_children(''))
        while stack:
            iid = stack.pop()
            tree.full_text[iid] = (tree.item(iid, 'text'), tuple(tree.item(iid, 'values')))
            stack.extend(tree.get_children(iid))
    if not hasattr(tree, 'fit_fonts'):
        tree.fit_fonts = (tkfont.Font(root=tree, font=fonts.body), tkfont.Font(root=tree, font=fonts.strong))
        pending = {'id': None}
        def later(event=None):
            if pending['id'] is None:
                def run():
                    pending['id'] = None
                    if tree.winfo_exists():
                        fit_tree(tree, fonts, fresh=False)
                pending['id'] = tree.after_idle(run)
        tree.bind('<Configure>', later, add='+')
        tree.bind('<ButtonRelease-1>', later, add='+')   # a column dragged wider or narrower
    body, strong = tree.fit_fonts
    columns = list(tree['columns'])
    widths = [tree.column(column, 'width') - 14 for column in columns]
    tree_width = tree.column('#0', 'width')
    for iid, (text, values) in tree.full_text.items():
        if not tree.exists(iid):
            continue
        font = strong if 'zone' in tree.item(iid, 'tags') else body
        depth, parent = 0, tree.parent(iid)
        while parent:
            depth, parent = depth + 1, tree.parent(parent)
        image = tree.item(iid, 'image')
        room = tree_width - 20 * (depth + 1) - (int(tree.tk.call('image', 'width', image[0])) + 4 if image else 0) - 10
        tree.item(iid, text=ellipsize(text, font, room),
                  values=[ellipsize(value, font, width) for value, width in zip(values, widths)])


def info_icon(parent, fonts, background=None):
    """A small circled "i" placed after a label; its tooltip is attached by the caller."""
    c = COLORS
    return tk.Label(parent, text='\u24d8', font=(fonts.body[0], 11), foreground=c['green'],
                    background=background or c['surface'], cursor='question_arrow', padx=2)
