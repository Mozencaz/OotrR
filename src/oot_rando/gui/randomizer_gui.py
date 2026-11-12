"""Desktop application (Tkinter). Run with ``python -m oot_rando``."""
import ctypes
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from oot_rando.randomizer.randomizer_core import Settings, CHECKS, GENERATOR_VERSION, generate
from oot_rando.randomizer.randomizer_services import read_artifact, generate_in_mods, validate_mod_directory
from oot_rando.tracker.auto_tracker import TrackerSession, newest_save
from oot_rando.tracker import game_overlay
from oot_rando.tracker import live_memory
from oot_rando.randomizer import spoiler_report
from oot_rando.tracker import turbo_a
from oot_rando.patching.randomize_kokiri import POOL, TITLE
from oot_rando.game.randomizer_categories import CATEGORIES
from oot_rando.game.world_maps import SAFE_CATEGORIES
from oot_rando.logic import rando_options
from oot_rando.paths import data_dir, seeds_dir, state_dir

STATE = state_dir()
LABELS = dict(zip(POOL, ('Green Rupee', 'Blue Rupee', 'Red Rupee', 'Purple Rupee',
                        'Gold Rupee', 'Deku Nuts', 'Deku Seeds', 'Arrows: small bundle',
                        'Arrows: medium bundle', 'Arrows: large bundle', 'Deku Shield', 'Hylian Shield')))
GAME_OPTIONS = [('randomize_chests', 'Randomize the four Kokiri chests (child and adult)'),
                ('avoid_vanilla', 'Avoid vanilla rewards when the pool allows it'),
                ('open_forest', 'Open the way from Kokiri Forest to Hyrule Field')]
SKIP_OPTIONS = [('skip_locked_cutscenes', 'Skippable cutscenes: intro, title screen demo, end credits and area presentations'),
                ('skip_auto_dialogues', 'Automatic dialogues skippable with + (minigames, Navi: 12 sequences)'),
                ('skip_chest_cutscenes', 'Chests (big and small) without cutscene: the lid opens and the item is obtained')]
OPTIONS = GAME_OPTIONS + SKIP_OPTIONS
ARCHIVE = data_dir() / 'seeds-uninstalled'
TRACKER_KINDS = {
    'full_chests': 'Chest', 'full_skulltula': 'Gold Skulltula', 'full_freestanding': 'Freestanding item',
    'full_shop': 'Shop', 'full_pots': 'Pot', 'full_crates': 'Crate', 'full_beehives': 'Beehive',
    'full_bushes': 'Bush', 'full_rocks': 'Rock', 'full_npc': 'NPC', 'full_scrub': 'Business scrub', 'kokiri_chests': 'Chest',
    'world_chests': 'Chest', 'vanilla_chest': 'Chest', 'vanilla_freestanding': 'Freestanding item',
    'vanilla_gs_token': 'Gold Skulltula', 'vanilla_shop': 'Shop', 'vanilla_npc': 'NPC',
    'vanilla_collectable': 'Item', 'vanilla_beehive': 'Beehive', 'vanilla_scrub': 'Deku Scrub',
    'vanilla_grottoscrub': 'Deku Scrub (grotto)', 'vanilla_song': 'Song', 'vanilla_crate': 'Crate',
    'vanilla_smallcrate': 'Small crate', 'vanilla_pot': 'Pot', 'vanilla_flyingpot': 'Flying pot',
    'vanilla_boss': 'Boss', 'vanilla_bossheart': 'Heart Container', 'vanilla_cutscene': 'Cutscene',
    'vanilla_rupeetower': 'Rupee tower', 'full_boss': 'Dungeon reward', 'full_bossheart': 'Boss heart container',
    'full_fairy': 'Great fairy', 'full_quest': 'Quest reward',
}

OPTION_COPY = {
    'accessibility': ('Accessibility goal', 'Choose whether every location must be reachable or finishing the game is enough.'),
    'shuffle_chests': ('Shuffle chest contents', 'Important items can be in any selected chest.'),
    'chest_matching': ('Locations used for progression', 'Identified chests: exact matches. By zone: more chests, with the most cautious access conditions of the zone.'),
    'shuffle_remake_items': ('Include remake-only items', 'Adds the items specific to this version of the game to the shuffle, without making them required for progression.'),
    'progressive_order': ('Find upgrades in order', 'For example: get the Hookshot before the Longshot.'),
    'progressive_strict': ('Require the previous level for each upgrade', 'Reaching an upgrade requires owning its previous level.'),
    'shopsanity': ('Items shuffled per shop', 'Shuffled items cost 10 rupees. One copy of the required purchases stays available; masks are kept.'),
    'tokensanity': ('Gold Skulltulas', 'Skulltulas give a shuffled reward; their tokens can be elsewhere.'),
    'shuffle_freestanding_items': ('Freestanding items', 'Includes rupees, hearts and heart pieces lying in the world.'),
    'shuffle_npc_gifts': ('Character gifts and minigames', 'Shuffles the supported rewards of characters and minigames.'),
    'shuffle_boss_rewards': ('Boss and dungeon rewards', 'Shuffles spiritual stones, medallions and heart containers. The game scenes are kept.'),
    'shuffle_great_fairies': ('Great fairy rewards', 'Shuffles spells, magic and defense upgrades.'),
    'shuffle_quest_rewards': ('Main quest rewards', 'Includes the ocarinas, Zelda\'s Letter, the Light Arrows and the Biggoron Sword. Songs stay in place.'),
    'shuffle_pots': ('Pots', 'The first reward is shuffled. Once picked up, the pot goes back to its vanilla loot.'),
    'shuffle_crates': ('Crates', 'The first reward is shuffled. Later pickups use the vanilla loot.'),
    'shuffle_beehives': ('Beehives', 'The first reward is shuffled. Later pickups use the vanilla loot.'),
    'shuffle_bushes': ('Bushes and grass', 'Shuffles the first reward of supported sources, then restores their vanilla loot.'),
    'shuffle_rocks': ('Rocks and stones', 'The first reward is shuffled. Then the rock goes back to its vanilla behaviour, even if it gave no item.'),
    'shuffle_enemy_spawns': ('Enemy souls', 'Find souls to make the matching enemies appear. A new game is required.'),
}



def default_mods_dir():
    """The Eden emulator's mods folder for the game when it exists, else empty (to choose)."""
    appdata = os.environ.get('APPDATA')
    folder = Path(appdata) / 'eden' / 'load' / TITLE if appdata else None
    return str(folder) if folder and folder.is_dir() else ''

class Application:
    def __init__(self, root):
        self.root = root
        root.title('OoT Randomizer')
        root.geometry('1140x850')
        root.minsize(940, 720)
        self.configure_theme()
        self.events, self.busy = queue.Queue(), False
        self.artifact, self.tracker, self.overlay, self.hud = None, None, None, None
        self.hud_status = tk.StringVar(value='')
        self.zone_open, self.tracker_scroll, self.tracker_trees = {}, {}, {}
        self.current_checks = []
        self.tracker_refreshing, self.closed = False, False
        self.tracker_details, self.tracker_signature = {}, None
        self.hotkey_thread_id = None
        self.seed = tk.StringVar(value=secrets.token_hex(8))
        self.nup, self.mods = tk.StringVar(), tk.StringVar()
        self.options = {name: tk.BooleanVar(value=True) for name, _ in OPTIONS}
        self.options['randomize_chests'].set(False)
        self.pool = {name: tk.BooleanVar(value=name.startswith('TBox_Rupee_')) for name in POOL}
        self.categories = {name: tk.BooleanVar(value=False) for name in CATEGORIES}
        self.excluded = {check['id']: tk.BooleanVar(value=False) for check in CHECKS}
        self.show_completed = tk.BooleanVar(value=True)
        self.show_blocked = tk.BooleanVar(value=True)
        self.tracker_search, self.save_path = tk.StringVar(), tk.StringVar()
        self.auto_save = tk.BooleanVar(value=True)
        self.app_state = self.read_app_state()
        # Game file and mods folder: chosen once by the player, then remembered.
        self.nup.set(self.app_state.get('game_file') or '')
        self.mods.set(self.app_state.get('mods_dir') or default_mods_dir())
        self.nup.trace_add('write', lambda *args: self.write_app_state(game_file=self.nup.get()))
        self.mods.trace_add('write', lambda *args: self.write_app_state(mods_dir=self.mods.get()))
        if isinstance(self.app_state.get('auto_save'), bool):
            self.auto_save.set(self.app_state['auto_save'])
        if self.app_state.get('save_path') and not self.auto_save.get():
            self.save_path.set(self.app_state['save_path'])
        self.turbo = None
        self.turbo_status = tk.StringVar(value='')
        self.slot = tk.StringVar(value='My game')
        self.status = tk.StringVar(value='Choose your game, then prepare your run.')
        self.result = tk.StringVar(value='No seed open. Generate a game or open an existing folder.')
        self.connection_status = tk.StringVar(value='Tracker not connected')
        self.tracker_summary = tk.StringVar(value='Open a seed to show its locations.')
        outer = ttk.Frame(root, padding=(28, 22))
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x', pady=(0, 18))
        ttk.Label(header, text='OoT Randomizer', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='Prepare your run. Explore Hyrule.', style='Muted.TLabel').pack(side='left', padx=22, pady=(8, 0))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True)
        self.party_tab, self.settings_tab = self.tab('Game'), self.tab('Settings')
        self.tracker_tab, self.spoiler_tab = self.tab('Tracker'), self.tab('Spoiler')
        self.help_tab = self.tab('Help')
        self.party_body, self.settings_body = self.scrollable(self.party_tab), self.scrollable(self.settings_tab)
        self.build_config()
        self.build_categories()
        self.build_generation()
        self.build_tracker()
        self.build_spoiler()
        self.build_help()
        bottom = ttk.Frame(outer)
        bottom.pack(side='bottom', fill='x', pady=(16, 0), before=self.tabs)
        self.progress = ttk.Progressbar(bottom, mode='indeterminate', length=110)
        self.progress.pack(side='right', padx=(12, 0))
        ttk.Label(bottom, textvariable=self.status, style='Muted.TLabel', wraplength=850).pack(side='left', fill='x')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.register_hotkey()
        self.tracker_search.trace_add('write', lambda *args: self.render_tracker())
        root.after(100, self.poll)
        root.after(1800, self.tracker_tick)
        root.after(50, self.restore_last_artifact)
        root.after(60, self.start_turbo)

    def configure_theme(self):
        self.colors = c = {'bg': '#111b18', 'panel': '#182720', 'field': '#20332a', 'text': '#edf4ef', 'muted': '#b0c6b8', 'accent': '#91d9b0', 'selected': '#315c44', 'line': '#3e5649'}
        self.root.configure(background=c['bg'])
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=c['bg'], foreground=c['text'], font=('Segoe UI', 10), bordercolor=c['line'], lightcolor=c['line'], darkcolor=c['line'], troughcolor=c['panel'])
        style.configure('TFrame', background=c['bg'])
        style.configure('TLabel', background=c['bg'], foreground=c['text'])
        style.configure('Muted.TLabel', foreground=c['muted'])
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'))
        style.configure('Heading.TLabel', font=('Segoe UI', 13, 'bold'), padding=(0, 0, 0, 5))
        style.configure('TButton', background=c['field'], foreground=c['text'], padding=(13, 8), borderwidth=1, focuscolor=c['accent'])
        style.map('TButton', background=[('active', '#2a4435'), ('disabled', c['panel'])], foreground=[('disabled', '#82968a')], bordercolor=[('focus', c['accent'])])
        style.configure('Accent.TButton', background=c['accent'], foreground='#10251a', font=('Segoe UI', 10, 'bold'))
        style.map('Accent.TButton', background=[('active', '#b1e9c8'), ('disabled', '#4b715b')], foreground=[('disabled', '#d1dfd5')])
        style.configure('TCheckbutton', background=c['bg'], foreground=c['text'], focuscolor=c['accent'], padding=(0, 5))
        style.map('TCheckbutton', background=[('active', c['bg'])], indicatorcolor=[('selected', c['accent']), ('!selected', c['field'])])
        style.configure('TEntry', fieldbackground=c['field'], foreground=c['text'], insertcolor=c['text'], padding=7)
        style.configure('TCombobox', fieldbackground=c['field'], foreground=c['text'], arrowcolor=c['accent'], padding=6)
        style.map('TCombobox', fieldbackground=[('readonly', c['field'])], selectbackground=[('readonly', c['field'])], selectforeground=[('readonly', c['text'])])
        style.configure('TSpinbox', fieldbackground=c['field'], foreground=c['text'], arrowcolor=c['accent'], padding=5)
        style.configure('TNotebook', background=c['bg'], borderwidth=0, tabmargins=(0, 0, 0, 12))
        style.configure('TNotebook.Tab', background=c['bg'], foreground=c['muted'], padding=(22, 10), borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected', c['field'])], foreground=[('selected', c['accent'])])
        style.configure('Treeview', background=c['panel'], fieldbackground=c['panel'], foreground=c['text'], rowheight=31, borderwidth=0, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', background=c['field'], foreground=c['muted'], padding=(8, 8), font=('Segoe UI', 10, 'bold'), relief='flat')
        style.map('Treeview', background=[('selected', c['selected'])], foreground=[('selected', '#ffffff')])
        style.configure('Vertical.TScrollbar', background=c['field'], arrowcolor=c['muted'], borderwidth=0)
        for key, value in [('background', c['field']), ('foreground', c['text']), ('selectBackground', c['selected'])]:
            self.root.option_add('*TCombobox*Listbox.' + key, value)
        for key, value in [('background', c['panel']), ('foreground', c['text']), ('insertBackground', c['text']), ('selectBackground', c['selected']), ('highlightBackground', c['line']), ('highlightColor', c['accent'])]:
            self.root.option_add('*Text.' + key, value)

    def scrollable(self, outer):
        canvas = tk.Canvas(outer, highlightthickness=0, background=self.colors['bg'])
        bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        parent = ttk.Frame(canvas, padding=(0, 0, 14, 0))
        parent.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        window = canvas.create_window((0, 0), window=parent, anchor='nw')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        def wheel(event):
            if str(event.widget).startswith(str(outer)):
                canvas.yview_scroll(int(-event.delta / 120), 'units')
        self.root.bind_all('<MouseWheel>', wheel, add='+')
        return parent

    def build_help(self):
        parent = self.scrollable(self.help_tab)
        sections = [
            ('Prepare a game', 'In Game, choose your .nup file and the mods folder. In Settings, name the seed, adjust the settings, then click Generate and install at the bottom of the page: the seed is written straight into the mods folder. Close the game during installation.'),
            ('Play on Hookshot', 'Choose the mods folder next to hookshot.exe. Each seed is installed in its own sub-folder. Only one seed of this application stays active at a time; the previous one is archived.'),
            ('Track the exploration', 'Open the seed being played, then select its progress.sav file in Tracker. Locations are updated after the game saves. Rewards of completed checks appear next to their name.'),
            ('Understand the states', 'Available: the logic estimates you can get the reward with your inventory. Blocked: a known condition is missing. Unknown: the data does not allow a conclusion. These locations stay visible by default.'),
            ('Keep the right save', 'Generate a new seed, start a new game, then save after the intro. Choose the matching slot in Tracker. An old save cannot be linked automatically. The tracker never changes its files.'),
            ('Repeatable sources', 'In a new seed, the shuffled reward can only be picked up once. Then pots, bushes, crates, beehives and rocks go back to their vanilla loot. Old seeds keep their rules.'),
            ('Compatibility', 'The glitchless logic is built in (remake world, derived from the Archipelago OoT rules). Some remake matches are approximate. Small keys stay in place. Only settings supported by the generator are offered.')]
        for heading, text in sections:
            ttk.Label(parent, text=heading, style='Heading.TLabel').pack(anchor='w', pady=(14, 4))
            ttk.Label(parent, text=text, style='Muted.TLabel', wraplength=900, justify='left').pack(anchor='w', pady=(0, 8))
        ttk.Label(parent, text=f'Application version: {GENERATOR_VERSION}', style='Muted.TLabel').pack(anchor='w', pady=(18, 8))

    def tab(self, name):
        frame = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(frame, text=name)
        return frame

    def path_row(self, parent, text, variable, kind):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=(0, 10))
        ttk.Label(frame, text=text).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(4, 0))
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        def choose():
            value = filedialog.askopenfilename(filetypes=[('NUP game', '*.nup')]) if kind == 'file' else filedialog.askdirectory()
            if value:
                variable.set(value)
        ttk.Button(row, text='Browse…', command=choose).pack(side='right', padx=(8, 0))

    def build_config(self):
        parent = self.party_body
        ttk.Label(parent, text='Your game', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, text='Seeds are generated straight into the mods folder.', style='Muted.TLabel').pack(anchor='w', pady=(0, 14))
        self.path_row(parent, 'Game file (.nup)', self.nup, 'file')
        self.path_row(parent, 'Mods folder — Hookshot / mods or the emulator title folder', self.mods, 'directory')
        ttk.Label(parent, text='Hookshot: choose the mods folder next to hookshot.exe. The original files stay in place.', style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(0, 14))

    def build_seed_row(self, parent):
        """Top of Settings: the seed name."""
        ttk.Label(parent, text='A new adventure', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, text='The same seed name and settings reproduce the same game.', style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 20))
        ttk.Label(row, text='Seed name', width=17).pack(side='left')
        ttk.Entry(row, textvariable=self.seed).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Random', command=lambda: self.seed.set(secrets.token_hex(8))).pack(side='left', padx=(10, 0))

    def build_generate_section(self, parent):
        """Bottom of Settings: generate button and generation log."""
        ttk.Separator(parent).pack(fill='x', pady=(4, 16))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 8))
        self.generate_button = ttk.Button(row, text='Generate and install', style='Accent.TButton', command=self.generate)
        self.generate_button.pack(side='left')
        ttk.Label(row, text='Close the game before installing. The previous seed is archived automatically.', style='Muted.TLabel', wraplength=700).pack(side='left', padx=(14, 0))
        ttk.Label(parent, text='Activity', style='Heading.TLabel').pack(anchor='w', pady=(10, 0))
        self.log = tk.Text(parent, height=8, wrap='word', font=('Segoe UI', 9), state='disabled', relief='flat', padx=12, pady=10)
        self.log.pack(fill='x', pady=(3, 10))

    def build_generation(self):
        parent = self.party_body
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(4, 12))
        ttk.Button(row, text='Open a seed…', command=self.open_artifact).pack(side='left')
        ttk.Button(row, text='Prepare a new seed', command=lambda: self.tabs.select(self.settings_tab)).pack(side='left', padx=(10, 0))
        ttk.Separator(parent).pack(fill='x', pady=(8, 18))
        ttk.Label(parent, text='Open game', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, textvariable=self.result, wraplength=940).pack(anchor='w', pady=(4, 10))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 16))
        ttk.Button(row, text='Show the tracker', command=lambda: self.tabs.select(self.tracker_tab)).pack(side='left')
        ttk.Button(row, text='Open the folder', command=self.open_folder).pack(side='left', padx=8)
        ttk.Button(row, text='Reveal the rewards…', command=self.show_spoilers).pack(side='left')

    def build_categories(self):
        parent = self.settings_body
        self.full_enabled = tk.BooleanVar(value=True)
        self.full_vars, self.category_controls = {}, {}
        self.full_reason = tk.StringVar(value='Select a setting to read what it does.')
        self.build_seed_row(parent)
        ttk.Label(parent, text='A game made for you', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, text='Only available settings are shown. Locations are checked by the glitchless logic.', style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(0, 12))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 16))
        for key, label in [('ap_defaults', 'Classic'), ('everything', 'Shuffle everything'), ('prudent', 'Chests only')]:
            ttk.Button(row, text=label, command=lambda k=key: self.apply_full(rando_options.preset(k), enable=True)).pack(side='left', padx=(0, 8))
        ttk.Button(row, text='Import…', command=self.import_settings).pack(side='right')
        ttk.Button(row, text='Export…', command=self.export_settings).pack(side='right', padx=8)
        ttk.Label(parent, textvariable=self.full_reason, style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(0, 8))
        grouped = {}
        for option in rando_options.OPTIONS:
            if option.kind == 'bool':
                supported = [v for v in (False, True) if option.supported(v)]
            elif option.kind == 'int':
                supported = list(option.supported_ints)
            else:
                supported = [v for v, label, reason in option.values if reason is None]
            if len(supported) > 1:
                grouped.setdefault(option.tab, []).append(option)
            else:
                self.option_row(None, 0, option)
        for group in rando_options.TABS:
            options = grouped.get(group, [])
            if not options:
                continue
            title = {'Logic': 'Logic and accessibility', 'Items': 'Items and locations', 'Dungeons': 'Dungeon contents', 'Souls': 'Enemy souls'}.get(group, group)
            ttk.Label(parent, text=title, style='Heading.TLabel').pack(anchor='w', pady=(18, 6))
            frame = ttk.Frame(parent)
            frame.pack(fill='x')
            frame.columnconfigure(0, weight=1)
            for index, option in enumerate(options):
                self.option_row(frame, index, option)
        ttk.Label(parent, text='Quality of life', style='Heading.TLabel').pack(anchor='w', pady=(20, 4))
        ttk.Checkbutton(parent, text='Open the way from Kokiri Forest to Hyrule Field', variable=self.options['open_forest']).pack(anchor='w')
        ttk.Label(parent, text='Always on: skippable cutscenes (hold X, or Plus), chests without cutscene, turbo A (hold A in a dialogue).',
                  style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(2, 0))
        ttk.Separator(parent).pack(fill='x', pady=(12, 16))
        ttk.Label(parent, text='Settings in Archipelago format (YAML)', style='Heading.TLabel').pack(anchor='w')
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 18))
        ttk.Button(row, text='Import a YAML…', command=self.import_ap_yaml).pack(side='left')
        ttk.Button(row, text='Export a YAML…', command=self.export_ap_yaml).pack(side='left', padx=8)
        ttk.Label(parent, text='Archipelago multiworld', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, text='Send your multiworld YAML to the host; the host puts the apworld in the '
                  'custom_worlds folder of Archipelago and generates. Then generate here from your .aprmk patch '
                  '(in the zip produced by Archipelago). Items of other players show as green rupees; '
                  'sending and receiving items in game needs the Archipelago client (not available yet).',
                  style='Muted.TLabel', wraplength=940).pack(anchor='w')
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(4, 18))
        ttk.Button(row, text='Export my multiworld YAML…', command=self.export_multiworld_yaml).pack(side='left')
        ttk.Button(row, text='Build the apworld…', command=self.build_apworld).pack(side='left', padx=8)
        ttk.Button(row, text='Generate from a patch (.aprmk)…', command=self.generate_from_patch).pack(side='left')
        self.build_generate_section(parent)
        for name in {o for opts in rando_options.CATEGORY_OPTIONS.values() for o, _, _ in opts}:
            self.full_vars[name].trace_add('write', lambda *args: self.sync_categories())
        self.apply_full(rando_options.preset('ap_defaults'), enable=True)

    def sync_categories(self):
        """Complete mode: each checkbox shows the state of its solver options."""
        if not self.full_enabled.get() or len(self.full_vars) != len(rando_options.OPTIONS):
            return
        values = self.full_values()
        for name, variable in self.categories.items():
            checked = name in rando_options.CATEGORY_OPTIONS and rando_options.category_checked(values, name)
            if variable.get() != checked:
                variable.set(checked)

    def update_category_states(self):
        full = self.full_enabled.get()
        for name, control in self.category_controls.items():
            enabled = name in rando_options.CATEGORY_OPTIONS if full else name in SAFE_CATEGORIES
            control.state(['!disabled'] if enabled else ['disabled'])
            if not enabled:
                self.categories[name].set(False)
        self.sync_categories()

    def build_tracker(self):
        parent = self.tracker_tab
        ttk.Label(parent, text='Your exploration', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, text='The tracker rereads the most recently written progress.sav (every slot) every 2 seconds: it updates as soon as the game writes its save. Rewards stay hidden until the checks are done.', style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(0, 12))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 10))
        ttk.Label(row, text='Profile').pack(side='left')
        ttk.Entry(row, textvariable=self.slot, width=20).pack(side='left', padx=(8, 12))
        ttk.Button(row, text='Load the tracker', command=self.load_tracker).pack(side='left')
        ttk.Button(row, text='Game window', command=self.toggle_overlay).pack(side='right')
        ttk.Button(row, text='In-game overlay', command=self.toggle_hud).pack(side='right', padx=(0, 8))
        ttk.Label(row, textvariable=self.hud_status, style='Muted.TLabel').pack(side='right', padx=(0, 10))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 8))
        ttk.Label(row, text='Save').pack(side='left')
        ttk.Entry(row, textvariable=self.save_path).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(row, text='Choose…', command=self.choose_save).pack(side='left')
        ttk.Button(row, text='Detect', command=self.detect_save).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(parent, text='Automatically follow the most recent save (every slot)', variable=self.auto_save, command=self.auto_save_toggled).pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 8))
        ttk.Label(row, textvariable=self.turbo_status, style='Muted.TLabel').pack(side='left')
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, textvariable=self.connection_status, style='Muted.TLabel', wraplength=760).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Refresh', command=self.refresh_tracker).pack(side='right')
        filters = ttk.Frame(parent)
        filters.pack(fill='x', pady=(0, 12))
        ttk.Label(filters, text='Search').pack(side='left')
        ttk.Entry(filters, textvariable=self.tracker_search, width=24).pack(side='left', padx=(8, 18))
        ttk.Checkbutton(filters, text='Show blocked', variable=self.show_blocked, command=self.render_tracker).pack(side='left')
        ttk.Checkbutton(filters, text='Show completed', variable=self.show_completed, command=self.render_tracker).pack(side='left', padx=(14, 0))
        self.tracker_rows = ttk.Frame(parent)
        self.tracker_rows.pack(fill='both', expand=True)
        footer = ttk.Frame(parent)
        footer.pack(side='bottom', fill='x', before=self.tracker_rows)
        row = ttk.Frame(footer)
        row.pack(fill='x', pady=(8, 0))
        ttk.Button(row, text='Expand all', command=lambda: self.set_all_zones(True)).pack(side='left')
        ttk.Button(row, text='Collapse all', command=lambda: self.set_all_zones(False)).pack(side='left', padx=8)
        ttk.Label(footer, textvariable=self.tracker_summary, wraplength=820).pack(anchor='w', pady=(10, 3))
        self.hotkey_label = ttk.Label(footer, style='Muted.TLabel')
        self.hotkey_label.pack(anchor='w')
        self.render_tracker()

    # ------------------------------------------------------- app state
    @staticmethod
    def read_app_state():
        try:
            value = json.loads((STATE / 'gui_state.json').read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def write_app_state(self, **values):
        self.app_state.update(values)
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            (STATE / 'gui_state.json').write_text(json.dumps(self.app_state, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            pass

    def restore_last_artifact(self):
        last = self.app_state.get('last_artifact')
        if not last or self.artifact or not (Path(last) / 'manifest.json').is_file():
            return
        try:
            self.use_artifact(last)
            self.status.set('Last seed reloaded: ' + Path(last).name)
        except Exception as error:
            self.status.set('Last seed not reloaded: ' + str(error))

    # ---------------------------------------------------------- saves
    def hookshot_root(self):
        """Hookshot folder when the mods folder is ``<Hookshot>/mods``, else None (emulator)."""
        mods = Path(self.mods.get()) if self.mods.get() else None
        return mods.parent if mods and mods.name.lower() == 'mods' else None

    def newest_save(self):
        """progress.sav most recently written, across every save and slot folder."""
        return newest_save(self.hookshot_root(), TITLE)

    def follow_newest_save(self):
        newest = self.newest_save()
        if newest is None:
            if not self.save_path.get():
                self.connection_status.set('No save found. Start a game and save, or choose progress.sav.')
            return False
        if self.save_path.get() and Path(self.save_path.get()) == newest:
            return False
        self.save_path.set(str(newest))
        return True

    def start_turbo(self):
        """Turbo A is always on (no option): started once the window is up."""
        if self.turbo:
            self.turbo.stop()
        self.turbo = turbo_a.TurboA(self.hookshot_root() or '')
        self.turbo.start()
        self.turbo_status.set(self.turbo.status)

    def auto_save_toggled(self):
        self.write_app_state(auto_save=self.auto_save.get())
        if self.auto_save.get() and self.follow_newest_save() and self.tracker:
            self.refresh_tracker()

    def choose_save(self):
        value = filedialog.askopenfilename(title='Choose the save of this game', filetypes=[('Hookshot progress', 'progress.sav'), ('Saves', '*.sav')])
        if value:
            # A save picked by hand is kept: stop following the newest one.
            self.auto_save.set(False)
            self.save_path.set(value)
            self.write_app_state(auto_save=False, save_path=value)
            if self.artifact:
                self.load_tracker()

    def detect_save(self):
        try:
            self.auto_save.set(True)
            self.write_app_state(auto_save=True)
            self.follow_newest_save()
            if self.save_path.get():
                self.connection_status.set('Most recent save: ' + Path(self.save_path.get()).parent.name
                                           + ' — ' + Path(self.save_path.get()).parent.parent.name)
                if self.artifact:
                    self.load_tracker()
        except Exception as error:
            self.connection_status.set('Detection failed: ' + str(error))

    def tracker_tick(self):
        if self.closed:
            return
        try:
            if self.auto_save.get():
                self.follow_newest_save()
        except Exception as error:
            self.connection_status.set('Detection failed: ' + str(error))
        if self.tracker and self.save_path.get():
            self.refresh_tracker()
        if self.turbo and self.turbo.last_hold:
            self.turbo_status.set(self.turbo.status + ' — last: ' + self.turbo.last_hold)
        self.root.after(1000, self.tracker_tick)   # live memory: ~1 s; the save path is cheap to stat

    def refresh_tracker(self):
        if not self.tracker or self.tracker_refreshing:
            return
        tracker = self.tracker
        tracker.save_path = self.save_path.get()
        self.tracker_refreshing = True
        def worker():
            try:
                self.events.put(('tracker-update', (tracker, tracker.refresh(), None)))
            except Exception as error:
                self.events.put(('tracker-update', (tracker, None, str(error))))
        threading.Thread(target=worker, daemon=True).start()


    # ------------------------------------------------------- complete mode
    def option_row(self, parent, index, option):
        label, help_text = OPTION_COPY.get(option.name, (option.label, option.help))
        def describe():
            self.full_reason.set(label + ' — ' + (help_text or 'Choose the value that suits your game.'))
        if option.kind == 'bool':
            variable = tk.BooleanVar(value=option.default)
            widget = ttk.Checkbutton(parent, text=label, variable=variable, command=describe) if parent else None
        elif option.kind == 'int':
            variable = tk.IntVar(value=option.default)
            widget = ttk.Spinbox(parent, from_=min(option.supported_ints), to=max(option.supported_ints), textvariable=variable, width=8, command=describe) if parent else None
        else:
            def choice_label(value, text):
                if option.name == 'chest_matching':
                    return 'Identified chests' if value == 'strict' else 'Access by zone'
                return text
            labels = [choice_label(value, text) for value, text, reason in option.values]
            variable = tk.StringVar(value=option.default)
            display = tk.StringVar(value=labels[[v for v, label, reason in option.values].index(option.default)])
            variable.display, variable.labels = display, labels
            allowed = [choice_label(value, text) for value, text, reason in option.values if reason is None]
            widget = ttk.Combobox(parent, state='readonly', values=allowed, textvariable=display, width=35) if parent else None
            if widget:
                def selected(event=None):
                    variable.set(option.values[labels.index(display.get())][0])
                    describe()
                widget.bind('<<ComboboxSelected>>', selected)
        self.full_vars[option.name] = variable
        if widget:
            if option.kind == 'bool':
                widget.grid(row=index, column=0, columnspan=2, sticky='w', pady=3)
            else:
                ttk.Label(parent, text=label, wraplength=480).grid(row=index, column=0, sticky='w', padx=(0, 18), pady=6)
                widget.grid(row=index, column=1, sticky='e', pady=6)
            widget.bind('<FocusIn>', lambda event: describe(), add='+')

    def full_value(self, option):
        return self.full_vars[option.name].get()

    def full_values(self):
        return {option.name: self.full_value(option) for option in rando_options.OPTIONS
                if option.name in self.full_vars}

    def apply_full(self, values, enable=None):
        values = rando_options.validate(values)
        for option in rando_options.OPTIONS:
            variable = self.full_vars[option.name]
            variable.set(values[option.name])
            if option.kind == 'choice':
                variable.display.set(variable.labels[[v for v, _, _ in option.values].index(values[option.name])])
        if enable is not None:
            self.full_enabled.set(enable)
            self.full_toggled()

    def full_toggled(self):
        if self.full_enabled.get():
            self.options['randomize_chests'].set(False)
            self.status.set('Settings applied. You can generate your game.')
        else:
            for variable in self.categories.values():
                variable.set(False)
            self.categories['world_chests'].set(True)
            self.status.set('Legacy settings loaded. Choose a preset to create a new full game.')
        self.update_category_states()

    def import_ap_yaml(self):
        name = filedialog.askopenfilename(filetypes=[('Archipelago YAML', '*.yaml *.yml')])
        if name:
            try:
                values, ignored = rando_options.from_ap_yaml(Path(name).read_text(encoding='utf-8'))
                supported = {k: (v if rando_options.BY_NAME[k].supported(v) else rando_options.BY_NAME[k].default)
                             for k, v in values.items()}
                self.apply_full(supported, enable=True)
                message = 'YAML imported.'
                if ignored:
                    message += '\n\nValues ignored or replaced by the supported value:\n• ' + '\n• '.join(ignored)
                messagebox.showinfo('Archipelago YAML import', message)
            except Exception as error:
                self.error(error)

    def export_ap_yaml(self):
        try:
            values = rando_options.validate(self.full_values())
            name = filedialog.asksaveasfilename(defaultextension='.yaml', filetypes=[('Archipelago YAML', '*.yaml')])
            if name:
                Path(name).write_text(rando_options.to_ap_yaml(values), encoding='utf-8')
                self.status.set('Archipelago YAML exported.')
        except Exception as error:
            self.error(error)

    def export_multiworld_yaml(self):
        from oot_rando.archipelago import bridge
        try:
            if not self.full_enabled.get():
                raise ValueError('Enable the full randomizer: the multiworld uses its options.')
            values = self.full_values()
            player = simpledialog.askstring('Multiworld YAML', 'Your player name in the multiworld (16 characters):',
                                            parent=self.root)
            if not player:
                return
            text = bridge.player_yaml(values, self.options['open_forest'].get(), player)
            name = filedialog.asksaveasfilename(defaultextension='.yaml', initialfile=f'{player}.yaml',
                                                filetypes=[('Archipelago YAML', '*.yaml')])
            if name:
                Path(name).write_text(text, encoding='utf-8')
                self.status.set('Multiworld YAML exported.')
        except Exception as error:
            self.error(error)

    def build_apworld(self):
        from oot_rando.archipelago.apworld_build import build_apworld
        try:
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            name = filedialog.asksaveasfilename(defaultextension='.apworld', initialfile='oot_remake.apworld',
                                                filetypes=[('Archipelago world', '*.apworld')])
            if not name:
                return

            def done(path):
                self.status.set('apworld written: ' + str(path))
                messagebox.showinfo('apworld ready', str(path) + '\n\nCopy it into the custom_worlds folder of '
                                    'Archipelago on the computer that generates the multiworld.')
            self.run_job(lambda progress: build_apworld(nup, name, progress), done)
        except Exception as error:
            self.error(error)

    def generate_from_patch(self):
        from oot_rando.archipelago import bridge
        try:
            name = filedialog.askopenfilename(filetypes=[('Archipelago patch', '*' + bridge.PATCH_SUFFIX)])
            if not name:
                return
            settings = bridge.settings_from_patch(bridge.load_patch(name)).validate_supported()
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            mods = validate_mod_directory(self.mods.get())

            def job(progress):
                installed = generate_in_mods(nup, mods, settings, progress, archive=ARCHIVE, generate=generate)
                return installed, installed
            self.run_job(job, self.generated_and_installed)
        except Exception as error:
            self.error(error)

    def get_settings(self):
        full = self.full_values() if self.full_enabled.get() else None
        options = {n: v.get() for n, v in self.options.items()}
        options.update({name: True for name, _ in SKIP_OPTIONS})   # always on, no option
        categories = {n: v.get() for n, v in self.categories.items()}
        if full is not None:
            options['randomize_chests'] = False
            categories = dict.fromkeys(categories, False)  # carried by the complete-mode options
        return Settings(seed=self.seed.get(), pool=[n for n, v in self.pool.items() if v.get()],
                        excluded_checks=[n for n, v in self.excluded.items() if v.get()],
                        categories=categories, full=full, **options).validate()

    def apply_settings(self, settings):
        self.seed.set(settings.seed)
        for name, variable in self.options.items():
            variable.set(True if name in dict(SKIP_OPTIONS) else getattr(settings, name))
        for name, variable in self.pool.items():
            variable.set(name in settings.pool and name.startswith('TBox_Rupee_'))
        for name, variable in self.excluded.items():
            variable.set(name in settings.excluded_checks)
        for name, variable in self.categories.items():
            variable.set(settings.categories.get(name, False) and name in SAFE_CATEGORIES)
        if settings.full is not None:
            self.apply_full(settings.full, enable=True)
        else:
            self.full_enabled.set(False)
            self.update_category_states()

    def import_settings(self):
        name = filedialog.askopenfilename(filetypes=[('JSON settings', '*.json')])
        if name:
            try:
                value = json.loads(Path(name).read_text(encoding='utf-8'))
                if value.get('format') != 'oot-remake-settings-v1':
                    raise ValueError('Unsupported settings format.')
                self.apply_settings(Settings.from_dict(value['settings']))
                self.status.set('Settings imported.')
            except Exception as error:
                self.error(error)

    def export_settings(self):
        try:
            settings = self.get_settings()
            name = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON settings', '*.json')])
            if name:
                Path(name).write_text(json.dumps({'format': 'oot-remake-settings-v1', 'settings': settings.to_dict()}, ensure_ascii=False, indent=2), encoding='utf-8')
                self.status.set('Settings exported.')
        except Exception as error:
            self.error(error)

    def run_job(self, function, done):
        if self.busy:
            self.status.set('An operation is already running.')
            return
        self.busy = True
        self.progress.start()
        self.generate_button.state(['disabled'])
        def worker():
            try:
                result = function(lambda text: self.events.put(('progress', text)))
                self.events.put(('done', (done, result)))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def generate(self):
        try:
            settings = self.get_settings()
            settings.validate_supported()
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            mods = validate_mod_directory(self.mods.get())
            def job(progress):
                installed = generate_in_mods(nup, mods, settings, progress, archive=ARCHIVE, generate=generate)
                return installed, installed
            self.run_job(job, self.generated_and_installed)
        except Exception as error:
            self.error(error)

    def generated_and_installed(self, result):
        directory, installed = result
        self.use_artifact(directory)
        self.tabs.select(self.tracker_tab)
        self.status.set('Seed generated and installed: ' + str(installed))
        messagebox.showinfo('Seed ready', 'Seed installed in:\n' + str(installed)
                            + '\n\nStart a new game to enable automatic tracking and first collections.')

    def use_artifact(self, directory):
        manifest, _ = read_artifact(directory)
        self.artifact = Path(directory)
        self.result.set('Seed: ' + manifest['settings']['seed'] + '\nIdentity: ' + manifest['seed_id'][:16]
                        + f' • {len(manifest["files"])} resources checked\n' + str(directory))
        complete = manifest.get('full_randomizer')
        if complete:
            cov = complete['coverage']
            self.result.set(self.result.get() + f'\n{cov["shuffled"]} shuffled locations • {cov["souls"]} souls to find.')
            if complete.get('new_save_required'):
                self.result.set(self.result.get() + '\nSouls on: start a NEW save.')
        coverage = manifest.get('coverage', {}).get('world_chests')
        if coverage:
            self.result.set(self.result.get() + f'\n{coverage["changed_groups"]} ordinary chests changed, '
                            f'{coverage["changed_instances"]} physical variants; vanilla progression.')
        self.apply_settings(Settings.from_dict(manifest['settings']))
        if manifest.get('tracking', {}).get('new_save_required'):
            self.result.set(self.result.get() + '\nA new game is needed for automatic tracking.')
        self.write_app_state(last_artifact=str(Path(directory).resolve()))
        if self.auto_save.get():
            self.follow_newest_save()
        self.load_tracker()
        self.reset_spoiler()
        self.status.set('Seed opened.')

    def open_artifact(self):
        directory = filedialog.askdirectory(title='Choose the folder holding manifest.json')
        if directory:
            try:
                self.use_artifact(directory)
            except Exception as error:
                self.error(error)

    def open_folder(self):
        if self.artifact:
            os.startfile(str(self.artifact))

    def show_spoilers(self):
        self.tabs.select(self.spoiler_tab)
        if self.artifact and not self.spoiler:
            self.reveal_spoiler()

    # ------------------------------------------------------------ spoiler
    MINOR_ITEMS = ('Green Rupee', 'Blue Rupee', 'Red Rupee', 'Purple Rupee', 'Gold Rupee', 'Recovery Heart',
                   'Gold Skulltula Token', 'Bombs (', 'Bombchus (', 'Arrows (', 'Deku Nuts', 'Deku Seeds',
                   'Business Scrub Seed', 'Magic Jar')

    def spoiler_roots(self):
        return [seeds_dir(), ARCHIVE]

    def build_spoiler(self):
        parent = self.spoiler_tab
        self.spoiler = None
        self.spoiler_search = tk.StringVar()
        self.spoiler_minor = tk.BooleanVar(value=True)
        self.spoiler_info = tk.StringVar(value='Open a seed to read its spoiler.')
        ttk.Label(parent, text='Seed spoiler', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent, textvariable=self.spoiler_info, style='Muted.TLabel', wraplength=940).pack(anchor='w', pady=(0, 10))
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 10))
        ttk.Button(row, text='Reveal the spoiler', style='Accent.TButton', command=self.reveal_spoiler).pack(side='left')
        ttk.Button(row, text='Hide', command=self.reset_spoiler).pack(side='left', padx=8)
        ttk.Button(row, text='Open spoiler.txt', command=self.open_spoiler_text).pack(side='right')
        ttk.Button(row, text='Export as text…', command=self.export_spoiler).pack(side='right', padx=8)
        filters = ttk.Frame(parent)
        filters.pack(fill='x', pady=(0, 10))
        ttk.Label(filters, text='Search').pack(side='left')
        ttk.Entry(filters, textvariable=self.spoiler_search, width=30).pack(side='left', padx=(8, 18))
        ttk.Checkbutton(filters, text='Show minor items (rupees, hearts, ammo, tokens)',
                        variable=self.spoiler_minor, command=self.render_spoiler).pack(side='left')
        self.spoiler_search.trace_add('write', lambda *args: self.render_spoiler())
        self.spoiler_views = ttk.Notebook(parent)
        self.spoiler_views.pack(fill='both', expand=True)
        self.spoiler_trees = {}
        views = [('zones', 'By zone', 'Zone / location',
                  [('item', 'Reward', 240), ('original', 'Originally', 180), ('sphere', 'Sphere', 70), ('kind', 'Type', 140)]),
                 ('playthrough', 'Progression playthrough', 'Sphere / location', [('item', 'Reward', 300)])]
        for key, title, heading, columns in views:
            frame = ttk.Frame(self.spoiler_views)
            self.spoiler_views.add(frame, text=title)
            tree = ttk.Treeview(frame, columns=[c for c, _, _ in columns], show='tree headings', selectmode='browse')
            tree.heading('#0', text=heading)
            tree.column('#0', width=360, minwidth=200, stretch=True)
            for column, text, width in columns:
                tree.heading(column, text=text)
                tree.column(column, width=width, minwidth=60, stretch=(column == 'item'))
            tree.tag_configure('major', foreground=self.colors['accent'])
            tree.tag_configure('minor', foreground=self.colors['muted'])
            bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=bar.set)
            bar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            self.spoiler_trees[key] = tree
        self.spoiler_summary = tk.StringVar()
        ttk.Label(parent, textvariable=self.spoiler_summary, style='Muted.TLabel').pack(anchor='w', pady=(8, 0))

    def reset_spoiler(self):
        """Hide the spoiler again (new seed opened, or the player asked)."""
        self.spoiler = None
        self.spoiler_info.set('Spoiler hidden. Click "Reveal the spoiler" to show every reward of this seed.'
                              if self.artifact else 'Open a seed to read its spoiler.')
        self.render_spoiler()

    def load_spoiler_report(self):
        if not self.artifact:
            raise ValueError('No seed open. Generate a game or open a seed folder.')
        return spoiler_report.load_report(self.artifact, self.spoiler_roots())

    def reveal_spoiler(self):
        if not self.artifact:
            self.spoiler_info.set('First open a seed in the Game tab.')
            return
        if not messagebox.askyesno('Reveal the spoiler', 'Show every randomized reward of this seed?'):
            return
        try:
            self.spoiler = self.load_spoiler_report()
            self.spoiler_info.set(f'Seed {self.spoiler["seed"] or "?"} · identity {self.spoiler["seed_id"][:16]} · '
                                  f'{len(self.spoiler["rows"])} shuffled locations · {self.spoiler["path"]}')
            self.render_spoiler()
        except Exception as error:
            self.error(error)

    def spoiler_minor_item(self, label):
        return label.startswith(self.MINOR_ITEMS) or label == 'Deku Stick'

    def render_spoiler(self):
        if not hasattr(self, 'spoiler_trees'):
            return
        for tree in self.spoiler_trees.values():
            tree.delete(*tree.get_children(''))
        if not self.spoiler:
            self.spoiler_summary.set('')
            return
        query = self.spoiler_search.get().strip().casefold()
        minor = self.spoiler_minor.get()
        tree, zones, shown, counts = self.spoiler_trees['zones'], {}, 0, {}
        for row in self.spoiler['rows']:
            counts[row['region']] = counts.get(row['region'], 0) + 1
        for index, row in enumerate(self.spoiler['rows']):
            is_minor = self.spoiler_minor_item(row['item'])
            if is_minor and not minor:
                continue
            text = ' '.join((row['region'], row['location'], row['item'], row['original'], row['kind'])).casefold()
            if query and query not in text:
                continue
            region = row['region']
            if region not in zones:
                zones[region] = tree.insert('', 'end', text=f'{region}   ({counts[region]})', open=bool(query), values=('', '', '', ''))
            sphere = '' if row['sphere'] is None else str(row['sphere'])
            tree.insert(zones[region], 'end', iid=f'row{index}', text=row['location'],
                        values=(row['item'], row['original'], sphere, row['kind']),
                        tags=('minor' if is_minor else 'major',))
            shown += 1
        tree = self.spoiler_trees['playthrough']
        for sphere in self.spoiler['playthrough']:
            entries = [(location, item) for location, item in sphere['items']
                       if (minor or not self.spoiler_minor_item(item))
                       and (not query or query in (location + ' ' + item).casefold())]
            if not entries:
                continue
            node = tree.insert('', 'end', text=f'Sphere {sphere["sphere"]}   ({len(entries)})', open=True, values=('',))
            for location, item in entries:
                tree.insert(node, 'end', text=location, values=(item,),
                            tags=('minor' if self.spoiler_minor_item(item) else 'major',))
        self.spoiler_summary.set(f'{shown} of {len(self.spoiler["rows"])} locations shown · '
                                 f'{len(self.spoiler["playthrough"])} progression spheres')

    def export_spoiler(self):
        try:
            report = self.load_spoiler_report()
            name = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text', '*.txt')],
                                                initialfile='spoiler_' + (report['seed'] or report['seed_id'][:16]) + '.txt')
            if name:
                spoiler_report.write_text(report, name)
                self.status.set('Spoiler exported: ' + name)
        except Exception as error:
            self.error(error)

    def open_spoiler_text(self):
        try:
            report = self.load_spoiler_report()
            path = Path(report['path']).with_name(spoiler_report.SPOILER_TEXT)
            if not path.is_file():
                # Seeds generated before spoiler.txt existed: create it next to spoiler.json.
                spoiler_report.write_text(report, path)
            os.startfile(str(path))
        except Exception as error:
            self.error(error)

    def load_tracker(self):
        self.tracker, self.current_checks = None, []
        self.tracker_details, self.tracker_signature = {}, None
        self.tracker_summary.set('Open a seed to show its locations.')
        self.tracker_scroll = {}
        self.render_tracker()
        if not self.artifact:
            return
        try:
            manifest, catalogue = read_artifact(self.artifact)
            self.current_checks = catalogue['checks']
            live = live_memory.LiveGameData() if os.name == 'nt' else None
            self.tracker = TrackerSession(self.artifact, self.slot.get(), save_path=self.save_path.get(), live=live)
            self.connection_status.set('Reading at the latest save' if self.save_path.get() else 'Choose a progress.sav file to enable automatic tracking.')
            self.render_tracker()
            self.refresh_tracker()
        except Exception as error:
            self.error(error)

    def render_tracker(self):
        if not hasattr(self, 'tracker_rows'):
            return
        containers = [self.tracker_rows]
        if self.overlay and self.overlay.winfo_exists():
            containers.append(self.overlay_rows)
        states = {check['id']: self.tracker.check_state(check['id']) for check in self.current_checks} if self.tracker else {}
        query = self.tracker_search.get().strip().casefold()
        totals, done, available = {}, {}, {}
        for check in self.current_checks:
            region = check.get('region') or 'Other'
            state = states.get(check['id'], {})
            totals[region] = totals.get(region, 0) + 1
            done[region] = done.get(region, 0) + bool(state.get('completed'))
            available[region] = available.get(region, 0) + bool(not state.get('completed') and state.get('access') == 'available')
        for container in containers:
            old = self.tracker_trees.get(container)
            selected = ()
            had_focus = bool(old and old.winfo_exists() and self.root.focus_get() == old)
            if old and old.winfo_exists():
                self.tracker_scroll[container] = old.yview()[0]
                selected = old.selection()
                for item in old.get_children(''):
                    if item.startswith('zone::'):
                        self.zone_open[item[len('zone::'):]] = old.item(item, 'open')
            for child in container.winfo_children():
                child.destroy()
            if not self.tracker:
                ttk.Label(container, text='No game open', style='Heading.TLabel').pack(anchor='w', pady=(22, 4))
                ttk.Label(container, text='Generate a seed in Settings or open an existing seed folder in Game.', style='Muted.TLabel').pack(anchor='w')
                continue
            tree_frame = ttk.Frame(container)
            tree_frame.pack(fill='both', expand=True)
            tree = ttk.Treeview(tree_frame, columns=('state', 'reward', 'kind'), show='tree headings', selectmode='browse', height=9)
            self.tracker_trees[container] = tree
            tree.heading('#0', text='Zone / location')
            tree.column('#0', width=350, minwidth=200, stretch=True)
            for key, title, width in [('state', 'State', 125), ('reward', 'Reward obtained', 210), ('kind', 'Type', 120)]:
                tree.heading(key, text=title)
                tree.column(key, width=width, minwidth=80, stretch=(key == 'reward'))
            for tag, color in [('done', '#b0c6b8'), ('available', '#a2e2b8'), ('partial', '#d6dc9c'), ('blocked', '#c1b49a'), ('unknown', '#b6c5cf')]:
                tree.tag_configure(tag, foreground=color)
            scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
            horizontal = ttk.Scrollbar(tree_frame, orient='horizontal', command=tree.xview)
            tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
            horizontal.pack(side='bottom', fill='x')
            scrollbar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            zones, visible, region_numbers = {}, 0, {}
            for check in self.current_checks:
                state = states[check['id']]
                completed, access = state.get('completed', False), state.get('access', 'unknown')
                region = check.get('region') or 'Other'
                region_numbers[region] = region_numbers.get(region, 0) + 1
                if completed and not self.show_completed.get():
                    continue
                if not completed and access == 'blocked' and not self.show_blocked.get():
                    continue
                name = check['name'] if check.get('category') != 'world_chests' else f'Chest {region_numbers[region]}'
                reward = state.get('reward', '') if completed else ''
                kind = TRACKER_KINDS.get(check.get('category', ''), check.get('category', ''))
                if query and query not in (region + ' ' + name + ' ' + kind + ' ' + reward).casefold():
                    continue
                if region not in zones:
                    zones[region] = tree.insert('', 'end', iid='zone::' + region, open=self.zone_open.get(region, bool(query)), text=f'{region}   {done[region]}/{totals[region]} done · {available[region]} available', values=('', '', ''))
                label = 'Done' if completed else {'available': 'Available', 'partial': 'Partial zone', 'blocked': 'Blocked', 'unknown': 'Unknown'}.get(access, 'Unknown')
                if completed and state.get('source') == 'manual':
                    label += ' (manual)'
                tree.insert(zones[region], 'end', iid=check['id'], text=name, values=(label, reward, kind), tags=('done' if completed else access,))
                visible += 1
            tree.bind('<<TreeviewOpen>>', lambda event, widget=tree: self.remember_zone(widget, True))
            tree.bind('<<TreeviewClose>>', lambda event, widget=tree: self.remember_zone(widget, False))
            if selected and tree.exists(selected[0]):
                tree.selection_set(selected[0])
                tree.focus(selected[0])
            if had_focus:
                tree.focus_set()
            if container in self.tracker_scroll:
                tree.update_idletasks()
                tree.yview_moveto(self.tracker_scroll[container])
            def toggle(event=None, widget=tree):
                selection = widget.selection()
                if selection and not selection[0].startswith('zone::'):
                    ident = selection[0]
                    try:
                        if self.tracker.check_state(ident).get('observed'):
                            self.status.set('This collection is confirmed by the save; its state updates automatically.')
                            return 'break'
                        self.tracker.set_completed(ident, not self.tracker.check_state(ident).get('completed', False))
                        self.render_tracker()
                    except Exception as error:
                        self.error(error)
                    return 'break'
            tree.bind('<space>', toggle)
            ttk.Button(container, text='Mark / unmark an undetected check', command=toggle).pack(
                side='bottom', anchor='w', pady=(6, 0), before=tree_frame)
            if not visible:
                ttk.Label(container, text='No location matches the filters.', style='Muted.TLabel').pack(anchor='w', pady=(5, 0))
        if self.tracker:
            count_done = sum(bool(state.get('completed')) for state in states.values())
            count_access = sum(not state.get('completed') and state.get('access') == 'available' for state in states.values())
            count_unknown = sum(not state.get('completed') and state.get('access', 'unknown') == 'unknown' for state in states.values())
            count_partial = sum(not state.get('completed') and state.get('access') == 'partial' for state in states.values())
            self.tracker_summary.set(f'{count_done}/{len(self.current_checks)} done · {count_access} available · {count_partial} in a partial zone · {count_unknown} unknown' + f'   —   {self.tracker.slot} · seed {self.tracker.seed_id[:16]}')
        self.update_hud(states)

    def update_hud(self, states=None):
        if not self.hud:
            return
        if not self.tracker:
            self.hud.update(game_overlay.overlay_model({}, set(), set(), [], {}))
            return
        if states is None:
            states = {check['id']: self.tracker.check_state(check['id']) for check in self.current_checks}
        inventory, readable, tracked = self.tracker.inventory()
        self.hud.update(game_overlay.overlay_model(inventory, readable, tracked, self.current_checks, states))

    def toggle_hud(self):
        if os.name != 'nt':
            self.status.set('The in-game overlay only exists on Windows.')
            return
        try:
            if not self.hud:
                hookshot = self.hookshot_root()
                romfs = hookshot / 'romfs' if hookshot else None
                icons = game_overlay.IconCache(STATE / 'icons', romfs)
                icons.ensure()
                self.hud = game_overlay.GameHud(self.root, icons=icons)
                self.update_hud()
                self.watch_hud()
            self.hud.toggle()
        except Exception as error:
            self.error(error)

    def watch_hud(self):
        if self.closed or not self.hud:
            return
        extra = [self.hud.icons.status] if self.hud.icons and self.hud.icons.status else []
        if self.tracker and self.tracker.live_status:
            extra.append('real time: ' + self.tracker.live_status)
        self.hud_status.set(' · '.join([self.hud.status] + extra))
        self.root.after(500, self.watch_hud)

    def remember_zone(self, tree, value, item=None):
        item = item or tree.focus()
        if item and item.startswith('zone::'):
            self.zone_open[item[len('zone::'):]] = value

    def set_all_zones(self, value):
        for check in self.current_checks:
            self.zone_open[check.get('region') or 'Other'] = value
        self.render_tracker()

    def toggle_overlay(self):
        if self.overlay and self.overlay.winfo_exists():
            if self.overlay.state() == 'withdrawn':
                self.overlay.deiconify()
            else:
                self.overlay.withdraw()
            return
        self.overlay = tk.Toplevel(self.root)
        self.overlay.title('OoT — Game tracker')
        self.overlay.configure(background=self.colors['bg'])
        self.overlay.attributes('-topmost', True)
        self.overlay.geometry('930x470')
        self.overlay.minsize(640, 330)
        frame = ttk.Frame(self.overlay, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Exploration in progress', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, textvariable=self.connection_status, style='Muted.TLabel', wraplength=850).pack(anchor='w', pady=(0, 8))
        filters = ttk.Frame(frame)
        filters.pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(filters, text='Show blocked', variable=self.show_blocked, command=self.render_tracker).pack(side='left')
        ttk.Checkbutton(filters, text='Show completed', variable=self.show_completed, command=self.render_tracker).pack(side='left', padx=14)
        self.overlay_rows = ttk.Frame(frame)
        self.overlay_rows.pack(fill='both', expand=True)
        self.overlay.protocol('WM_DELETE_WINDOW', self.overlay.withdraw)
        self.render_tracker()

    def register_hotkey(self):
        self.hotkey_label.configure(text='Global shortcut: starting…')
        if os.name != 'nt':
            self.events.put(('hotkey-ready', False))
            return
        def listen():
            from ctypes.wintypes import MSG
            user32 = ctypes.windll.user32
            message = MSG()
            # A dedicated message pump prevents Tk from consuming WM_HOTKEY.
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            self.hotkey_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            registered = bool(user32.RegisterHotKey(None, 0x0A71, 0x4006, ord('T')))
            hud_key = bool(user32.RegisterHotKey(None, 0x0A72, 0x4006, ord('O')))
            self.events.put(('hotkey-ready', (registered, hud_key)))
            if not (registered or hud_key):
                return
            try:
                while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    if message.message == 0x0312 and message.wParam == 0x0A71:
                        self.events.put(('toggle-overlay', None))
                    elif message.message == 0x0312 and message.wParam == 0x0A72:
                        self.events.put(('toggle-hud', None))
            finally:
                user32.UnregisterHotKey(None, 0x0A71)
                user32.UnregisterHotKey(None, 0x0A72)
        self.hotkey_thread = threading.Thread(target=listen, daemon=True)
        self.hotkey_thread.start()


    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'hotkey-ready':
                    window_key, hud_key = payload if isinstance(payload, tuple) else (payload, False)
                    parts = []
                    parts.append('Ctrl + Shift + T: tracker window' if window_key else 'Use Game window to keep the tracker in front')
                    if hud_key:
                        parts.append('Ctrl + Shift + O: transparent overlay on the game')
                    self.hotkey_label.configure(text=' · '.join(parts) + '.')
                elif kind == 'toggle-overlay':
                    self.toggle_overlay()
                elif kind == 'toggle-hud':
                    self.toggle_hud()
                elif kind == 'tracker-update':
                    tracker, details, error = payload
                    self.tracker_refreshing = False
                    if tracker is not self.tracker:
                        continue
                    if error:
                        self.connection_status.set('Reading paused: ' + error + ' — retrying automatically.')
                        continue
                    self.tracker_details = details or {}
                    label = self.tracker_details.get('status', 'At the latest save')
                    when = self.tracker_details.get('updated_at', '')
                    self.connection_status.set(label + (' · ' + str(when) if when else ''))
                    signature = tuple((check['id'], tuple(sorted(self.tracker.check_state(check['id']).items()))) for check in self.current_checks)
                    if signature != self.tracker_signature:
                        self.tracker_signature = signature
                        self.render_tracker()
                    else:
                        self.update_hud()   # inventory and save time change without check changes
                elif kind == 'progress':
                    self.status.set(payload)
                    self.log.configure(state='normal')
                    self.log.insert('end', payload + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                else:
                    self.busy = False
                    self.progress.stop()
                    self.generate_button.state(['!disabled'])
                    if kind == 'error':
                        self.error(payload)
                    else:
                        callback, value = payload
                        try:
                            callback(value)
                        except Exception as error:
                            self.error(error)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def error(self, error):
        self.status.set(str(error))
        messagebox.showerror('Operation failed', str(error))

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation running', 'Wait for the generation or analysis to finish before closing.')
            return
        if self.hotkey_thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, 0x0012, 0, 0)
            self.hotkey_thread.join(timeout=1)
        if self.turbo:
            if (self.turbo.remapped and self.turbo.game_is_running() and not messagebox.askyesno(
                    'Game running',
                    'Turbo A plays the A button for the game. Closing now leaves A without effect until '
                    'the game is restarted. Close anyway?')):
                return
            self.turbo.stop()
        self.closed = True
        self.root.destroy()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open-mod', type=Path)
    args = parser.parse_args([] if argv is None else argv)
    root = tk.Tk()
    app = Application(root)
    if args.open_mod:
        try:
            app.use_artifact(args.open_mod)
        except Exception as error:
            app.error(error)
    root.mainloop()


if __name__ == '__main__':
    main()
