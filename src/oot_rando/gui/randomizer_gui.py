"""Desktop application (Tkinter). Run with ``python -m oot_rando``."""
import ctypes
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from oot_rando.randomizer.randomizer_core import Settings, CHECKS, GENERATOR_VERSION, generate
from oot_rando.randomizer.randomizer_services import (read_artifact, generate_in_mods, validate_mod_directory,
                                                      has_ingame_tracker, update_ingame_tracker)
from oot_rando.tracker.auto_tracker import TrackerSession, newest_save
from oot_rando.tracker import game_overlay
from oot_rando.tracker.check_labels import check_labels
from oot_rando.tracker import live_memory
from oot_rando.randomizer import spoiler_report
from oot_rando.tracker import turbo_a
from oot_rando.patching.randomize_kokiri import POOL, TITLE
from oot_rando.game.randomizer_categories import CATEGORIES
from oot_rando.game.world_maps import SAFE_CATEGORIES
from oot_rando.logic import rando_options
from oot_rando.paths import data_dir, seeds_dir, state_dir
from oot_rando.gui import theme
from oot_rando import __version__ as APP_VERSION, updater

STATE = state_dir()
LABELS = dict(zip(POOL, ('Green Rupee', 'Blue Rupee', 'Red Rupee', 'Purple Rupee',
                        'Gold Rupee', 'Deku Nuts', 'Deku Seeds', 'Arrows: small bundle',
                        'Arrows: medium bundle', 'Arrows: large bundle', 'Deku Shield', 'Hylian Shield')))
GAME_OPTIONS = [('randomize_chests', 'Randomize the four Kokiri chests (child and adult)'),
                ('avoid_vanilla', 'Avoid vanilla rewards when the pool allows it'),
                ('open_forest', 'Open the way from Kokiri Forest to Hyrule Field'),
                ('skulltulas_always_present', 'Night-only gold skulltulas present day and night')]
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
    'start_inventory_from_pool': ('Starting inventory', 'Items held from the start, separated by commas, '
                                  'with a count if needed: "Hover Boots, Progressive Hookshot x2, Heart Container x3". '
                                  'Songs and tunics are not available yet.'),
    'item_pool_value': ('Item pool', 'Plentiful: an extra copy of the major items. Scarce: at most 3 bottles '
                        'and half the hearts. Minimal: one bottle and no extra hearts.'),
    'logic_no_night_tokens_without_suns_song': ("Night skulltulas need Sun's Song",
                                                 'Waiting for the night is not expected by the logic.'),
}


class ItemsVar:
    """Text field holding a starting inventory (``"Hover Boots, Bow x2"``) as a dict."""

    def __init__(self):
        self.text = tk.StringVar(value='')

    def get(self):
        return rando_options.parse_items(self.text.get())

    def set(self, value):
        self.text.set(rando_options.format_items(value or {}))



def default_mods_dir():
    """The Eden emulator's mods folder for the game when it exists, else empty (to choose)."""
    appdata = os.environ.get('APPDATA')
    folder = Path(appdata) / 'eden' / 'load' / TITLE if appdata else None
    return str(folder) if folder and folder.is_dir() else ''

class Application:
    def __init__(self, root):
        self.root = root
        root.title('OoT Randomizer')
        root.geometry('1220x860')
        root.minsize(1040, 720)
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
        self.options['skulltulas_always_present'].set(False)
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
        self.ingame_tracker = tk.BooleanVar(value=self.app_state.get('ingame_tracker', True))
        self.ingame_tracker.trace_add('write', lambda *args: self.write_app_state(ingame_tracker=self.ingame_tracker.get()))
        self.mods.trace_add('write', lambda *args: self.write_app_state(mods_dir=self.mods.get()))
        self.check_updates = tk.BooleanVar(value=self.app_state.get('check_updates', True) is not False)
        self.check_updates.trace_add('write', lambda *args: self.write_app_state(check_updates=self.check_updates.get()))
        self.updating, self.update_silent = False, True   # False, 'check' or 'install'
        self.extra_emulators = tk.StringVar(value=self.app_state.get('extra_emulators') or '')
        live_memory.set_extra_emulators(self.extra_emulators.get())
        if isinstance(self.app_state.get('auto_save'), bool):
            self.auto_save.set(self.app_state['auto_save'])
        if self.app_state.get('save_path') and not self.auto_save.get():
            self.save_path.set(self.app_state['save_path'])
        self.turbo = None
        self.turbo_status = tk.StringVar(value='')
        self.ap_client, self.ap_manifest, self.ap_log_seen = None, None, 0
        self.ap_address = tk.StringVar(value=self.app_state.get('ap_address') or 'archipelago.gg:38281')
        self.ap_password, self.ap_slot, self.ap_chat = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.ap_status = tk.StringVar(value='Open a seed generated from an Archipelago patch to connect.')
        self.slot = tk.StringVar(value='My game')
        self.status = tk.StringVar(value='Choose your game, then prepare your run.')
        self.result = tk.StringVar(value='No seed open. Generate a game or open an existing folder.')
        self.connection_status = tk.StringVar(value='Tracker not connected')
        self.tracker_summary = tk.StringVar(value='Open a seed to show its locations.')
        self.seed_chip = tk.StringVar(value='No seed open')
        self.sidebar = theme.Sidebar(root, self.fonts, self.show_page, footer=f'Version {GENERATOR_VERSION}')
        self.sidebar.pack(side='left', fill='y')
        outer = ttk.Frame(root, padding=(34, 26, 34, 18), style='Page.TFrame')
        outer.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(outer, style='Page.TFrame')
        header.pack(fill='x', pady=(0, 18))
        self.page_title, self.page_subtitle = tk.StringVar(), tk.StringVar()
        titles = ttk.Frame(header, style='Page.TFrame')
        titles.pack(side='left', fill='x', expand=True)
        ttk.Label(titles, textvariable=self.page_title, style='PageTitle.TLabel').pack(anchor='w')
        ttk.Label(titles, textvariable=self.page_subtitle, style='PageSub.TLabel').pack(anchor='w', pady=(2, 0))
        ttk.Label(header, textvariable=self.seed_chip, style='Chip.TLabel').pack(side='right', anchor='n', pady=(8, 0))
        self.tabs = ttk.Notebook(outer, style='Pages.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.pages = {}
        self.seed_name, self.tracker_counts, self.tracker_filter = '', None, 'all'
        self.home_tab = self.tab('home', 'Home', 'Welcome', 'Your adventure at a glance.')
        self.settings_tab = self.tab('newseed', 'New seed', 'New seed', 'Pick an adventure, then generate it.')
        self.tracker_tab = self.tab('tracker', 'Tracker', 'Tracker', 'What you found, and what you can reach now.')
        self.multiworld_tab = self.tab('multiworld', 'Multiworld', 'Multiworld', 'Play with friends through Archipelago. Three steps.')
        self.sidebar.gap()
        self.setup_tab = self.tab('setup', 'Setup', 'Setup', 'Where your game lives. Set once.')
        self.spoiler_tab = self.tab('spoiler', 'Spoiler', 'Spoiler', 'Every reward of the open seed. Reveal only if you want to know.')
        self.help_tab = self.tab('help', 'Help', 'Help', 'How the application works, step by step.')
        self.tabs.bind('<<NotebookTabChanged>>', lambda event: self.page_changed())
        self.home_body, self.settings_body = self.scrollable(self.home_tab), self.scrollable(self.settings_tab)
        self.multiworld_body, self.setup_body = self.scrollable(self.multiworld_tab), self.scrollable(self.setup_tab)
        self.build_home()
        self.build_setup()
        self.build_categories()
        self.build_tracker()
        self.build_multiworld()
        self.build_spoiler()
        self.build_help()
        for variable in (self.nup, self.mods, self.save_path):
            variable.trace_add('write', lambda *args: self.update_home())
        self.update_home()
        bottom = ttk.Frame(outer, style='Page.TFrame')
        bottom.pack(side='bottom', fill='x', pady=(12, 0), before=self.tabs)
        self.progress = ttk.Progressbar(bottom, mode='indeterminate', length=120)
        ttk.Label(bottom, textvariable=self.status, style='Page.TLabel', wraplength=760).pack(side='left', fill='x')
        self.show_page('home')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.register_hotkey()
        self.tracker_search.trace_add('write', lambda *args: self.render_tracker())
        root.after(100, self.poll)
        updater.cleanup()
        if self.check_updates.get():
            root.after(2500, lambda: self.check_for_updates(silent=True))
        root.after(1800, self.tracker_tick)
        root.after(50, self.restore_last_artifact)
        root.after(60, self.start_turbo)

    def configure_theme(self):
        self.colors = dict(theme.COLORS, bg=theme.COLORS['surface'], accent=theme.COLORS['green'])
        self.fonts, self.images = theme.apply(self.root)

    # ------------------------------------------------------------ layout
    def scrollable(self, outer):
        canvas = tk.Canvas(outer, highlightthickness=0, background=self.colors['page'], borderwidth=0)
        bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview, style='Page.Vertical.TScrollbar')
        parent = ttk.Frame(canvas, padding=(0, 0, 16, 6), style='Page.TFrame')
        parent.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        window = canvas.create_window((0, 0), window=parent, anchor='nw')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        def autohide(first, last):
            # The bar keeps its place (no relayout, so no flicker) and is only painted when needed.
            needed = not (float(first) <= 0 and float(last) >= 1)
            bar.configure(style='Page.Vertical.TScrollbar' if needed else 'Hidden.Vertical.TScrollbar')
            bar.set(first, last)
        bar.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=autohide)
        canvas.pack(side='left', fill='both', expand=True)
        def wheel(event):
            if str(event.widget).startswith(str(outer)):
                canvas.yview_scroll(int(-event.delta / 120), 'units')
        self.root.bind_all('<MouseWheel>', wheel, add='+')
        return parent

    def card(self, parent, title=None, subtitle=None, fill='x', expand=False, side='top', padx=0):
        """A rounded white card. Returns the frame to fill."""
        frame = ttk.Frame(parent, style='Card.TFrame', padding=theme.CARD_PADDING)
        frame.pack(side=side, fill=fill, expand=expand, pady=(0, 14), padx=padx)
        if title:
            ttk.Label(frame, text=title, style='Heading.TLabel').pack(anchor='w')
        if subtitle:
            ttk.Label(frame, text=subtitle, style='Muted.TLabel', wraplength=780, justify='left').pack(anchor='w', pady=(2, 0))
        if title or subtitle:
            ttk.Frame(frame, height=12).pack(fill='x')
        return frame

    def buttons(self, parent, pady=(0, 0)):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=pady)
        return row

    def build_help(self):
        parent = self.scrollable(self.help_tab)
        sections = [
            ('Prepare a game', 'In Setup, choose your .nup file and the mods folder. In New seed, pick an adventure, then click Generate and install: the seed is written straight into the mods folder. Close the game during installation.'),
            ('Play on a PC port (Hookshot, Longshot...)', 'Choose the mods folder next to the game exe (hookshot.exe, longshot.exe...). Each seed is installed in its own sub-folder. Only one seed of this application stays active at a time; the previous one is archived.'),
            ('Track the exploration', 'The tracker follows the most recent save by itself. Locations are updated after the game saves. Rewards of completed checks appear next to their name.'),
            ('Understand the states', 'Available: the logic estimates you can get the reward with your inventory. Blocked: a known condition is missing. Unknown: the data does not allow a conclusion. These locations stay visible by default.'),
            ('Keep the right save', 'Generate a new seed, start a new game, then save after the intro. The tracker picks the newest save; choose another in Setup. An old save cannot be linked automatically. The tracker never changes its files.'),
            ('Repeatable sources', 'In a new seed, the shuffled reward can only be picked up once. Then pots, bushes, crates, beehives and rocks go back to their vanilla loot. Old seeds keep their rules.'),
            ('Compatibility', 'The glitchless logic is built in (remake world, derived from the Archipelago OoT rules). Some remake matches are approximate. Small keys stay in place. Only settings supported by the generator are offered.')]
        grid = ttk.Frame(parent, style='Page.TFrame')
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='help')
        for index, (heading, text) in enumerate(sections):
            box = ttk.Frame(grid, style='Card.TFrame', padding=theme.CARD_PADDING)
            box.grid(row=index // 2, column=index % 2, sticky='nsew', padx=(0, 7) if index % 2 == 0 else (7, 0), pady=(0, 14))
            ttk.Label(box, text=f'{index + 1:02d}', style='Field.TLabel').pack(anchor='w')
            ttk.Label(box, text=heading, style='Heading.TLabel').pack(anchor='w', pady=(2, 6))
            ttk.Label(box, text=text, style='Muted.TLabel', wraplength=360, justify='left').pack(anchor='w')
        ttk.Label(parent, text=f'Application version: {APP_VERSION} (generator {GENERATOR_VERSION})', style='Page.TLabel').pack(anchor='w', pady=(4, 8))
        row = self.buttons(parent, pady=(0, 8))
        ttk.Button(row, text='Check for updates', command=lambda: self.check_for_updates(silent=False)).pack(side='left')
        ttk.Checkbutton(row, text='Check at start-up', variable=self.check_updates).pack(side='left', padx=(12, 0))

    def tab(self, key, nav, title, subtitle):
        frame = ttk.Frame(self.tabs, style='Page.TFrame')
        self.tabs.add(frame, text=nav)
        self.pages[key] = (frame, title, subtitle)
        self.sidebar.add(key, nav)
        return frame

    def show_page(self, key):
        self.tabs.select(self.pages[key][0])
        self.page_changed()

    def page_changed(self):
        current = self.tabs.select()
        for key, (frame, title, subtitle) in self.pages.items():
            if str(frame) == current:
                self.sidebar.select(key)
                self.page_title.set(title)
                self.page_subtitle.set(subtitle)

    def path_row(self, parent, text, variable, kind):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=(0, 12))
        ttk.Label(frame, text=text, style='Field.TLabel').pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(5, 0))
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        def choose():
            value = filedialog.askopenfilename(filetypes=[('NUP game', '*.nup')]) if kind == 'file' else filedialog.askdirectory()
            if value:
                variable.set(value)
        ttk.Button(row, text='Browse…', command=choose).pack(side='right', padx=(8, 0))

    def build_setup(self):
        parent = self.setup_body
        box = self.card(parent, 'Game files', 'Seeds are generated straight into the mods folder. The original files stay in place.')
        self.path_row(box, 'GAME FILE (.NUP)', self.nup, 'file')
        self.path_row(box, 'MODS FOLDER — PC PORT (HOOKSHOT, LONGSHOT...) / MODS OR THE EMULATOR TITLE FOLDER', self.mods, 'directory')
        ttk.Label(box, text='PC port (Hookshot, Longshot...): choose the mods folder next to the game exe.', style='Small.TLabel').pack(anchor='w')
        ttk.Label(box, text='OTHER EMULATOR EXECUTABLES (OPTIONAL)', style='Field.TLabel').pack(anchor='w', pady=(12, 0))
        row = self.buttons(box, pady=(5, 4))
        entry = ttk.Entry(row, textvariable=self.extra_emulators)
        entry.pack(side='left', fill='x', expand=True)
        for event in ('<FocusOut>', '<Return>'):
            entry.bind(event, lambda e: self.save_extra_emulators())
        ttk.Label(box, text='Live tracking finds Hookshot, Longshot, Lichii, Ryuchii, Eden, yuzu, suyu, citron and sudachi. '
                  'Another yuzu-based emulator? Add its .exe name here (comma-separated).',
                  style='Small.TLabel', wraplength=780).pack(anchor='w')
        box = self.card(parent, 'Save', 'The tracker reads your progress.sav. It is found automatically; pick it by hand only if needed.')
        ttk.Checkbutton(box, text='Follow the most recent save (every slot)', variable=self.auto_save,
                        command=self.auto_save_toggled).pack(anchor='w', pady=(0, 12))
        ttk.Label(box, text='SAVE FILE', style='Field.TLabel').pack(anchor='w')
        row = self.buttons(box, pady=(5, 12))
        ttk.Entry(row, textvariable=self.save_path).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Choose…', command=self.choose_save).pack(side='left', padx=(8, 0))
        ttk.Button(row, text='Detect', command=self.detect_save).pack(side='left', padx=(8, 0))
        ttk.Label(box, text='PROFILE', style='Field.TLabel').pack(anchor='w')
        row = self.buttons(box, pady=(5, 12))
        ttk.Entry(row, textvariable=self.slot, width=22).pack(side='left')
        ttk.Button(row, text='Reload the tracker', command=self.load_tracker).pack(side='left', padx=(8, 0))
        ttk.Button(row, text='Update the in-game tracker', command=self.update_seed_tracker).pack(side='left', padx=(8, 0))
        ttk.Label(box, textvariable=self.connection_status, style='Small.TLabel', wraplength=780).pack(anchor='w')
        ttk.Label(box, textvariable=self.turbo_status, style='Small.TLabel').pack(anchor='w')

    def build_home(self):
        parent = self.home_body
        self.home_seed, self.home_progress, self.home_available = tk.StringVar(), tk.StringVar(), tk.StringVar()
        hero = ttk.Frame(parent, style='Hero.TFrame', padding=(28, 24, 28, 24))
        hero.pack(fill='x', pady=(0, 6))
        ttk.Label(hero, text='CURRENT ADVENTURE', style='HeroField.TLabel').pack(anchor='w')
        ttk.Label(hero, textvariable=self.home_seed, style='HeroTitle.TLabel').pack(anchor='w', pady=(4, 14))
        self.home_bar = ttk.Progressbar(hero, style='Hero.Horizontal.TProgressbar', maximum=1, value=0)
        self.home_bar.pack(fill='x')
        row = ttk.Frame(hero, style='HeroIn.TFrame')
        row.pack(fill='x', pady=(14, 0))
        ttk.Label(row, textvariable=self.home_progress, style='Hero.TLabel').pack(side='left')
        ttk.Label(row, textvariable=self.home_available, style='HeroMuted.TLabel').pack(side='left', padx=(8, 0))
        self.home_primary = ttk.Button(row, style='Hero.Accent.TButton')
        self.home_primary.pack(side='right')
        self.home_secondary = ttk.Button(row, style='Hero.TButton')
        self.home_secondary.pack(side='right', padx=(0, 10))
        links = ttk.Frame(parent, style='Page.TFrame')
        links.pack(fill='x', pady=(0, 12))
        for text, command in [('Open a seed…', self.open_artifact), ('Open the folder', self.open_folder),
                              ('Spoiler', self.show_spoilers)]:
            ttk.Button(links, text=text, style='Page.Link.TButton', command=command).pack(side='left', padx=(4, 14))
        tiles = ttk.Frame(parent, style='Page.TFrame')
        tiles.pack(fill='x', pady=(0, 14))
        self.home_tiles = {}
        for column, (key, title) in enumerate([('game', 'GAME FILE'), ('mods', 'MODS FOLDER'), ('save', 'SAVE'), ('live', 'LIVE TRACKING')]):
            tiles.columnconfigure(column, weight=1, uniform='tiles')
            box = ttk.Frame(tiles, style='Card.TFrame', padding=(18, 14, 18, 16))
            box.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            ttk.Label(box, text=title, style='Field.TLabel').pack(anchor='w')
            line = ttk.Frame(box)
            line.pack(anchor='w', pady=(7, 0))
            dot = ttk.Label(line)
            dot.pack(side='left', padx=(0, 7))
            value = ttk.Label(line, style='Value.TLabel')
            value.pack(side='left')
            self.home_tiles[key] = {'dot': dot, 'value': value, 'fix': ttk.Button(box, text='Fix ›', style='Link.TButton')}
        box = self.card(parent)
        row = self.buttons(box, pady=(0, 6))
        ttk.Label(row, text='Available now', style='Heading.TLabel').pack(side='left')
        self.home_see_all = ttk.Button(row, text='See all ›', style='Link.TButton',
                                       command=lambda: (self.set_tracker_filter('available'), self.show_page('tracker')))
        self.home_see_all.pack(side='right')
        self.home_list = ttk.Frame(box)
        self.home_list.pack(fill='x')
        self.render_home_list({})

    def set_tile(self, key, state, text, fix=None):
        tile = self.home_tiles[key]
        tile['dot'].configure(image=self.images['dot_' + state])
        tile['value'].configure(text=text)
        if fix:
            tile['fix'].configure(command=fix)
            if not tile['fix'].winfo_manager():
                tile['fix'].pack(anchor='w', pady=(4, 0))
        else:
            tile['fix'].pack_forget()

    def update_home(self):
        """Home shows the state of the adventure; only problems ask for an action."""
        if not hasattr(self, 'home_tiles'):
            return
        counts = self.tracker_counts if self.tracker else None
        self.home_seed.set(self.seed_name or 'No adventure yet')
        if counts:
            self.home_bar.configure(maximum=max(counts['total'], 1), value=counts['done'])
            self.home_progress.set(f'{counts["done"]} / {counts["total"]} found')
            self.home_available.set(f'·  {counts["available"]} available now')
        else:
            self.home_bar.configure(maximum=1, value=0)
            self.home_progress.set('Seed installed' if self.artifact else 'Create a seed to start playing.')
            self.home_available.set('')
        if self.artifact:
            self.home_primary.configure(text='Continue', command=lambda: self.show_page('tracker'))
            self.home_secondary.configure(text='New seed', command=lambda: self.show_page('newseed'))
        else:
            self.home_primary.configure(text='Create a seed', command=lambda: self.show_page('newseed'))
            self.home_secondary.configure(text='Open a seed…', command=self.open_artifact)
        setup = lambda: self.show_page('setup')
        if self.nup.get() and Path(self.nup.get()).is_file():
            self.set_tile('game', 'ok', 'Found')
        else:
            self.set_tile('game', 'warn', 'Missing', setup)
        if self.mods.get() and Path(self.mods.get()).is_dir():
            self.set_tile('mods', 'ok', 'PC port' if self.hookshot_root() else 'Emulator')
        else:
            self.set_tile('mods', 'warn', 'Missing', setup)
        linked = bool(self.save_path.get()) and Path(self.save_path.get()).is_file()
        if linked:
            self.set_tile('save', 'ok', 'Linked')
        else:
            self.set_tile('save', 'warn', 'Not linked', setup)
        if self.tracker and self.tracker.live and not self.tracker.live_status:
            self.set_tile('live', 'ok', 'On')
        else:
            self.set_tile('live', 'off', 'Game not running' if self.tracker else 'Waiting for a seed')
        if hasattr(self, 'sync_dot'):
            self.sync_dot.configure(image=self.images['dot_ok' if linked and self.tracker else 'dot_warn' if self.tracker else 'dot_off'])
        if self.pages['home'][1] != ('Welcome back' if self.artifact else 'Welcome'):
            frame, _, subtitle = self.pages['home']
            self.pages['home'] = (frame, 'Welcome back' if self.artifact else 'Welcome', subtitle)
            self.page_changed()

    def render_home_list(self, states):
        for child in self.home_list.winfo_children():
            child.destroy()
        reachable = [check for check in self.current_checks
                     if not states.get(check['id'], {}).get('completed') and states.get(check['id'], {}).get('access') == 'available']
        self.home_see_all.configure(text=f'See all {len(reachable)} ›' if reachable else 'Open the tracker ›')
        if not reachable:
            text = 'Nothing new in reach right now.' if self.tracker else 'Open or create a seed to see what you can reach.'
            ttk.Label(self.home_list, text=text, style='Muted.TLabel').pack(anchor='w', pady=(6, 0))
            return
        for index, check in enumerate(reachable[:5]):
            if index:
                theme.rule(self.home_list).pack(fill='x')
            row = ttk.Frame(self.home_list)
            row.pack(fill='x', pady=7)
            ttk.Label(row, image=self.images['dot_ok']).pack(side='left', padx=(0, 10))
            name = check['name'] if check.get('category') != 'world_chests' else 'Chest'
            ttk.Label(row, text=f'{check.get("region") or "Other"} — {name}').pack(side='left')
            ttk.Label(row, text=TRACKER_KINDS.get(check.get('category', ''), ''), style='Small.TLabel').pack(side='right')

    def build_seed_row(self, parent):
        box = self.card(parent, 'Seed name', 'The same seed name and settings reproduce the same game.')
        row = self.buttons(box)
        ttk.Entry(row, textvariable=self.seed).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Random', command=lambda: self.seed.set(secrets.token_hex(8))).pack(side='left', padx=(8, 0))

    def build_generate_section(self, parent):
        box = self.card(parent)
        row = self.buttons(box)
        self.generate_button = ttk.Button(row, text='Generate and install', style='Accent.TButton', command=self.generate)
        self.generate_button.pack(side='right')
        ttk.Label(row, text='Close the game first. The previous seed is archived.', style='Muted.TLabel').pack(side='right', padx=(0, 16))
        self.log = tk.Text(box, height=5, wrap='word', state='disabled', padx=12, pady=10)
        return box

    PRESET_CARDS = [('prudent', 'Chests only', 'A gentle first run: chests are shuffled, keys and enemies stay as usual.'),
                    ('ap_defaults', 'Classic', 'The standard Archipelago rules. The recommended balance.'),
                    ('everything', 'Everything', 'Shops, pots, crates, grass, rocks and enemy souls join in.')]

    def build_categories(self):
        parent = self.settings_body
        self.full_enabled = tk.BooleanVar(value=True)
        self.full_vars, self.category_controls = {}, {}
        self.full_reason = tk.StringVar(value='Select a setting to read what it does.')
        self.customize_label, self.customize_hint = tk.StringVar(value='Customize settings  ▸'), tk.StringVar()
        grid = ttk.Frame(parent, style='Page.TFrame')
        grid.pack(fill='x', pady=(0, 14))
        self.preset_cards = {}
        for column, (key, name, text) in enumerate(self.PRESET_CARDS):
            grid.columnconfigure(column, weight=1, uniform='presets')
            box = ttk.Frame(grid, style='Card.TFrame', padding=(18, 18, 18, 18), cursor='hand2')
            box.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
            art = tk.Canvas(box, width=180, height=76, highlightthickness=0, background=self.colors['green_soft'])
            art.pack(fill='x')
            art.bind('<Configure>', lambda event, a=art, k=key: theme.preset_art(a, k, self.colors))
            widgets = [box, art, ttk.Label(box, text=name, style='Preset.TLabel'),
                       ttk.Label(box, text=text, style='Small.TLabel', wraplength=200, justify='left')]
            widgets[2].pack(anchor='w', pady=(12, 2))
            widgets[3].pack(anchor='w')
            for widget in widgets:
                widget.bind('<Button-1>', lambda event, k=key: self.apply_full(rando_options.preset(k), enable=True))
            self.preset_cards[key] = (box, art)
        self.build_seed_row(parent)
        row = ttk.Frame(parent, style='Page.TFrame')
        row.pack(fill='x', pady=(0, 12))
        ttk.Button(row, textvariable=self.customize_label, style='Page.Link.TButton', command=self.toggle_details).pack(side='left', padx=(4, 12))
        ttk.Label(row, textvariable=self.customize_hint, style='Page.TLabel').pack(side='left')
        self.details = ttk.Frame(parent, style='Page.TFrame')
        details = self.details
        ttk.Label(details, textvariable=self.full_reason, style='Page.TLabel', wraplength=780, justify='left').pack(anchor='w', padx=4, pady=(0, 10))
        grouped = {}
        for option in rando_options.OPTIONS:
            if option.kind == 'items':
                supported = [None, None]  # free text: always shown
            elif option.kind == 'bool':
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
            frame = self.card(details, title)
            rows = ttk.Frame(frame)
            rows.pack(fill='x')
            rows.columnconfigure(0, weight=1)
            for index, option in enumerate(options):
                self.option_row(rows, index, option)
        box = self.card(details, 'Quality of life', 'Always on: skippable cutscenes (hold X, or Plus), chests without cutscene, turbo A (hold A in a dialogue).')
        rows = ttk.Frame(box)
        rows.pack(fill='x')
        rows.columnconfigure(0, weight=1)
        self.switch_row(rows, 0, 'Open the way from Kokiri Forest to Hyrule Field', self.options['open_forest'])
        self.switch_row(rows, 1, 'Night-only gold skulltulas present day and night (the logic does not change)',
                        self.options['skulltulas_always_present'])
        self.switch_row(rows, 2, 'In-game tracker: R + right stick up shows the items and checks found (GPL-3 module, '
                        'runs only while this seed is enabled)', self.ingame_tracker)
        box = self.card(details, 'Share these settings')
        row = self.buttons(box)
        ttk.Button(row, text='Import…', command=self.import_settings).pack(side='left')
        ttk.Button(row, text='Export…', command=self.export_settings).pack(side='left', padx=8)
        ttk.Button(row, text='Export an Archipelago YAML…', style='Link.TButton', command=self.export_ap_yaml).pack(side='right')
        ttk.Button(row, text='Import an Archipelago YAML…', style='Link.TButton', command=self.import_ap_yaml).pack(side='right', padx=14)
        self.generate_card = self.build_generate_section(parent)
        for name in {o for opts in rando_options.CATEGORY_OPTIONS.values() for o, _, _ in opts}:
            self.full_vars[name].trace_add('write', lambda *args: self.sync_categories())
        self.apply_full(rando_options.preset('ap_defaults'), enable=True)

    def toggle_details(self):
        if self.details.winfo_manager():
            self.details.pack_forget()
            self.customize_label.set('Customize settings  ▸')
        else:
            self.details.pack(fill='x', before=self.generate_card)
            self.customize_label.set('Customize settings  ▾')

    def update_presets(self):
        """Highlights the preset matching the current settings, if any."""
        if not hasattr(self, 'preset_cards') or len(self.full_vars) != len(rando_options.OPTIONS):
            return
        try:
            values = rando_options.validate(self.full_values())
        except Exception:
            return
        current = next((key for key in self.preset_cards
                        if rando_options.validate(rando_options.preset(key)) == values), None)
        for key, (box, art) in self.preset_cards.items():
            box.configure(style='CardSelected.TFrame' if key == current else 'Card.TFrame')
            art.configure(background=self.colors['gold_soft' if key == current else 'green_soft'])
        self.customize_hint.set('' if current else 'Custom settings')

    def switch_row(self, parent, index, text, variable, command=None):
        """Label on the left, switch on the right; clicking the label toggles too."""
        label = ttk.Label(parent, text=text, wraplength=560, justify='left', cursor='hand2')
        label.grid(row=index, column=0, sticky='w', pady=7)
        widget = ttk.Checkbutton(parent, variable=variable, command=command)
        widget.grid(row=index, column=1, sticky='e', pady=7)
        def click(event):
            if 'disabled' not in widget.state():
                widget.invoke()
                widget.focus_set()
        label.bind('<Button-1>', click)
        if index:
            theme.rule(parent).grid(row=index, column=0, columnspan=2, sticky='new')
        return widget

    def sync_categories(self):
        """Complete mode: each checkbox shows the state of its solver options."""
        if not self.full_enabled.get() or len(self.full_vars) != len(rando_options.OPTIONS):
            return
        try:
            values = self.full_values()
        except ValueError:
            return  # starting inventory being typed
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
        bar = ttk.Frame(parent, style='Page.TFrame')
        bar.pack(fill='x', pady=(0, 10))
        self.sync_dot = ttk.Label(bar, style='Page.TLabel', image=self.images['dot_off'])
        self.sync_dot.pack(side='left', padx=(4, 8))
        ttk.Label(bar, textvariable=self.connection_status, style='Page.TLabel', wraplength=470, justify='left').pack(side='left')
        ttk.Button(bar, text='Change', style='Page.Link.TButton', command=lambda: self.show_page('setup')).pack(side='left', padx=(10, 0))
        ttk.Button(bar, text='Pop-out window', style='Page.Link.TButton', command=self.toggle_overlay).pack(side='right')
        ttk.Button(bar, text='In-game overlay', style='Page.Link.TButton', command=self.toggle_hud).pack(side='right', padx=14)
        box = self.card(parent, fill='both', expand=True)
        self.tracker_box = box
        top = self.buttons(box, pady=(0, 12))
        self.counters = {}
        # Location filters, then two views of their own (shown when the seed has them):
        # dungeon keys and enemy souls, each replacing the location list.
        for key, label in [('available', 'Available'), ('blocked', 'Not yet'), ('done', 'Done'), ('all', 'All'),
                           ('keys', 'Keys'), ('souls', 'Souls')]:
            frame = ttk.Frame(top, padding=(12, 7, 12, 8), cursor='hand2')
            frame.pack(side='left', padx=(0, 6))
            count = ttk.Label(frame, text='–', width=5)
            count.pack(anchor='w')
            name = ttk.Label(frame, text=label)
            name.pack(anchor='w')
            for widget in (frame, count, name):
                widget.bind('<Button-1>', lambda event, k=key: self.set_tracker_filter(k))
            self.counters[key] = (frame, count, name)
        ttk.Entry(top, textvariable=self.tracker_search, width=18).pack(side='right')
        ttk.Label(top, text='Search', style='Small.TLabel').pack(side='right', padx=(0, 8))
        self.tracker_rows = ttk.Frame(box)
        self.tracker_rows.pack(fill='both', expand=True)
        self.keys_rows = ttk.Frame(box)
        self.souls_rows = ttk.Frame(box)
        self.keys_tree, self.keys_shown = None, None
        self.souls_tree, self.souls_open, self.souls_shown = None, {}, None
        footer = ttk.Frame(box)
        footer.pack(side='bottom', fill='x', before=self.tracker_rows)
        row = ttk.Frame(footer)
        row.pack(fill='x', pady=(10, 0))
        ttk.Label(row, textvariable=self.tracker_summary, wraplength=600, style='Small.TLabel').pack(side='left')
        ttk.Button(row, text='Collapse all', style='Link.TButton', command=lambda: self.set_all_zones(False)).pack(side='right')
        ttk.Button(row, text='Expand all', style='Link.TButton', command=lambda: self.set_all_zones(True)).pack(side='right', padx=12)
        self.hotkey_label = ttk.Label(footer, style='Small.TLabel')
        self.hotkey_label.pack(anchor='w', pady=(2, 0))
        ttk.Label(footer, textvariable=self.hud_status, style='Small.TLabel').pack(anchor='w')
        self.set_tracker_filter('all')

    def set_tracker_filter(self, key):
        """The counters above the list are also its filter; Keys and Souls show their own view."""
        self.tracker_filter = key
        for name, (frame, count, label) in self.counters.items():
            prefix = 'TabOn' if name == key else 'Tab'
            frame.configure(style=prefix + '.TFrame')
            count.configure(style=prefix + 'Count.TLabel')
            label.configure(style=prefix + '.TLabel')
        shown = {'keys': self.keys_rows, 'souls': self.souls_rows}.get(key, self.tracker_rows)
        for view in (self.tracker_rows, self.keys_rows, self.souls_rows):
            if view is not shown and view.winfo_manager():
                view.pack_forget()
        if not shown.winfo_manager():
            shown.pack(fill='both', expand=True)
        self.render_tracker()

    def build_multiworld(self):
        parent = self.multiworld_body
        self.ap_steps = []
        def step(title, text):
            box = ttk.Frame(parent, style='Card.TFrame', padding=theme.CARD_PADDING)
            box.pack(fill='x', pady=(0, 12))
            mark = theme.badge(box, self.images)
            mark.pack(side='left', anchor='n', padx=(0, 16))
            body = ttk.Frame(box)
            body.pack(side='left', fill='x', expand=True)
            ttk.Label(body, text=title, style='Heading.TLabel').pack(anchor='w')
            ttk.Label(body, text=text, style='Muted.TLabel', wraplength=640, justify='left').pack(anchor='w', pady=(2, 10))
            self.ap_steps.append((box, mark))
            return body
        body = step('Send your settings to the host', 'Export your YAML and send it to whoever hosts the multiworld.')
        row = self.buttons(body)
        self.ap_export_button = ttk.Button(row, text='Export my YAML…', command=self.export_multiworld_yaml)
        self.ap_export_button.pack(side='left')
        ttk.Button(row, text='Host needs the apworld?', style='Link.TButton', command=self.build_apworld).pack(side='left', padx=16)
        body = step('Add the patch the host sent back', 'The .aprmk file from the zip Archipelago produced. The seed is generated and installed right away.')
        self.ap_patch_button = ttk.Button(body, text='Choose the patch…', command=self.generate_from_patch)
        self.ap_patch_button.pack(anchor='w')
        body = step('Connect to the server', 'Checks you find in game are sent to the server.')
        row = self.buttons(body)
        for label, variable, width, extra in [('SERVER', self.ap_address, 26, {}), ('SLOT', self.ap_slot, 16, {}),
                                              ('PASSWORD', self.ap_password, 12, {'show': '•'})]:
            field = ttk.Frame(row)
            field.pack(side='left', fill='x', expand=label == 'SERVER', padx=(0, 10))
            ttk.Label(field, text=label, style='Field.TLabel').pack(anchor='w')
            ttk.Entry(field, textvariable=variable, width=width, **extra).pack(fill='x', pady=(5, 0))
        self.ap_button = ttk.Button(row, text='Connect', style='Accent.TButton', command=self.toggle_archipelago)
        self.ap_button.pack(side='left', anchor='s')
        ttk.Label(body, textvariable=self.ap_status, style='Small.TLabel', wraplength=640).pack(anchor='w', pady=(10, 8))
        self.ap_log = tk.Text(body, height=8, wrap='word', state='disabled', padx=12, pady=10)
        self.ap_log.pack(fill='x')
        row = self.buttons(body, pady=(8, 0))
        chat = ttk.Entry(row, textvariable=self.ap_chat)
        chat.pack(side='left', fill='x', expand=True)
        chat.bind('<Return>', lambda event: self.send_archipelago_chat())
        ttk.Button(row, text='Send', command=self.send_archipelago_chat).pack(side='left', padx=(8, 0))
        self.update_archipelago_controls()

    def update_archipelago_controls(self):
        self.ap_button.state(['!disabled'] if self.ap_manifest or self.ap_client else ['disabled'])
        self.ap_button.configure(text='Disconnect' if self.ap_client else 'Connect')
        # The three steps: done ones are checked, the next one is highlighted.
        done = [bool(self.app_state.get('ap_yaml_exported') or self.ap_manifest), bool(self.ap_manifest), bool(self.ap_client)]
        current = next((index for index, value in enumerate(done) if not value), None)
        for index, (box, mark) in enumerate(self.ap_steps):
            mark.set('done' if done[index] else 'on' if index == current else 'off', str(index + 1))
            box.configure(style='CardSelected.TFrame' if index == current else 'Card.TFrame')
        self.ap_export_button.configure(style='Accent.TButton' if current == 0 else 'TButton')
        self.ap_patch_button.configure(style='Accent.TButton' if current == 1 else 'TButton')

    def set_archipelago_seed(self, manifest):
        """A seed was opened: the client follows it only when it comes from an Archipelago patch."""
        from oot_rando.archipelago.client import ClientError, archipelago_info
        self.stop_archipelago()
        try:
            slot, _, _ = archipelago_info(manifest)
            self.ap_manifest = manifest
            self.ap_slot.set(slot)
            self.ap_status.set('Ready to connect: checks found in game are sent to the server.')
        except ClientError as error:
            self.ap_manifest = None
            self.ap_status.set(str(error))
        self.update_archipelago_controls()

    def toggle_archipelago(self):
        from oot_rando.archipelago.client import ArchipelagoClient, ClientError
        if self.ap_client:
            self.stop_archipelago()
            self.ap_status.set('Disconnected.')
            return
        if not self.ap_manifest:
            return
        try:
            client = ArchipelagoClient(self.ap_manifest, self.ap_address.get(), self.ap_password.get(),
                                       self.ap_slot.get().strip(),
                                       on_change=lambda: self.events.put(('ap-change', None)))
        except ClientError as error:
            self.ap_status.set(str(error))
            return
        self.write_app_state(ap_address=self.ap_address.get().strip())
        self.ap_client, self.ap_log_seen = client, 0
        self.ap_log.configure(state='normal')
        self.ap_log.delete('1.0', 'end')
        self.ap_log.configure(state='disabled')
        if self.tracker:
            client.update(self.tracker.completed, self.tracker.goal_reached)
        client.start()
        self.update_archipelago_controls()

    def stop_archipelago(self):
        client, self.ap_client = self.ap_client, None
        if client:
            threading.Thread(target=client.stop, daemon=True).start()
        self.update_archipelago_controls()

    def send_archipelago_chat(self):
        if self.ap_client and self.ap_chat.get().strip():
            self.ap_client.say(self.ap_chat.get())
            self.ap_chat.set('')

    def render_archipelago(self):
        client = self.ap_client
        if not client:
            return
        info = client.summary()
        text = f'{info["status"]} • {info["checks"]}/{info["total"]} checks known to the server'
        if info['received']:
            text += f' • {info["received"]} items received'
            if info['from_other_worlds']:
                text += f' • in game: {info["delivery"]}'
        if info['goal']:
            text += ' • goal sent'
        self.ap_status.set(text)
        lines, count = list(client.log), client.log_count
        new = lines[max(0, len(lines) - (count - self.ap_log_seen)):]
        self.ap_log_seen = count
        if new:
            self.ap_log.configure(state='normal')
            self.ap_log.insert('end', ''.join(line + '\n' for line in new))
            self.ap_log.delete('1.0', 'end-301l')
            self.ap_log.see('end')
            self.ap_log.configure(state='disabled')
        if client.fatal:
            self.ap_client = None
            self.update_archipelago_controls()

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
        return newest_save(self.hookshot_root(), TITLE, self.mods.get() or None)

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
            self.update_presets()
        if option.kind == 'items':
            variable = ItemsVar()
            widget = ttk.Entry(parent, textvariable=variable.text, width=40) if parent else None
            if widget:
                widget.bind('<FocusOut>', lambda event: describe(), add='+')
        elif option.kind == 'bool':
            variable = tk.BooleanVar(value=option.default)
            widget = self.switch_row(parent, index, label, variable, command=describe) if parent else None
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
            widget = ttk.Combobox(parent, state='readonly', values=allowed, textvariable=display, width=30) if parent else None
            if widget:
                def selected(event=None):
                    variable.set(option.values[labels.index(display.get())][0])
                    describe()
                widget.bind('<<ComboboxSelected>>', selected)
        self.full_vars[option.name] = variable
        if widget:
            if option.kind != 'bool':
                ttk.Label(parent, text=label, wraplength=480).grid(row=index, column=0, sticky='w', padx=(0, 18), pady=7)
                widget.grid(row=index, column=1, sticky='e', pady=7)
                if index:
                    theme.rule(parent).grid(row=index, column=0, columnspan=2, sticky='new')
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
        self.update_presets()

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
                self.write_app_state(ap_yaml_exported=True)
                self.update_archipelago_controls()
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
            settings = bridge.settings_from_patch(
                bridge.load_patch(name), self.options['skulltulas_always_present'].get()).validate_supported()
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            mods = validate_mod_directory(self.mods.get())
            ingame_tracker = self.ingame_tracker.get()

            def job(progress):
                installed = generate_in_mods(nup, mods, settings, progress, archive=ARCHIVE, generate=generate,
                                             ingame_tracker=ingame_tracker)
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
        self.progress.pack(side='right', padx=(12, 0))
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
            ingame_tracker = self.ingame_tracker.get()
            def job(progress):
                installed = generate_in_mods(nup, mods, settings, progress, archive=ARCHIVE, generate=generate,
                                             ingame_tracker=ingame_tracker)
                return installed, installed
            self.run_job(job, self.generated_and_installed)
        except Exception as error:
            self.error(error)

    def generated_and_installed(self, result):
        directory, installed = result
        self.use_artifact(directory)
        self.show_page('tracker')
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
        self.seed_name = (manifest['settings']['seed'] or manifest['seed_id'][:12])[:28]
        self.seed_chip.set('Seed  ' + self.seed_name)
        self.write_app_state(last_artifact=str(Path(directory).resolve()))
        if self.auto_save.get():
            self.follow_newest_save()
        self.load_tracker()
        self.set_archipelago_seed(manifest)
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
        self.show_page('spoiler')
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
        box = self.card(parent)
        row = self.buttons(box)
        ttk.Button(row, text='Open spoiler.txt', style='Link.TButton', command=self.open_spoiler_text).pack(side='right')
        ttk.Button(row, text='Export as text…', style='Link.TButton', command=self.export_spoiler).pack(side='right', padx=12)
        ttk.Button(row, text='Hide', command=self.reset_spoiler).pack(side='right', padx=(8, 12))
        ttk.Button(row, text='Reveal the spoiler', style='Accent.TButton', command=self.reveal_spoiler).pack(side='right')
        info = ttk.Frame(row)
        info.pack(side='left', fill='x', expand=True, padx=(0, 16))
        ttk.Label(info, text='Seed spoiler', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(info, textvariable=self.spoiler_info, style='Small.TLabel', wraplength=300, justify='left').pack(anchor='w', pady=(2, 0))
        parent = self.card(parent, fill='both', expand=True)
        filters = self.buttons(parent, pady=(0, 8))
        ttk.Entry(filters, textvariable=self.spoiler_search, width=30).pack(side='left')
        ttk.Label(filters, text='Search', style='Small.TLabel').pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filters, text='Minor items (rupees, hearts, ammo, tokens)',
                        variable=self.spoiler_minor, command=self.render_spoiler).pack(side='right')
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
            tree.heading('#0', text=heading, anchor='w')
            tree.column('#0', width=360, minwidth=200, stretch=True)
            for column, text, width in columns:
                tree.heading(column, text=text, anchor='w')
                tree.column(column, width=width, minwidth=60, stretch=(column == 'item'))
            tree.tag_configure('major', foreground=self.colors['text'])
            tree.tag_configure('minor', foreground=self.colors['muted'])
            bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=bar.set)
            bar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            self.spoiler_trees[key] = tree
        self.spoiler_summary = tk.StringVar()
        ttk.Label(parent, textvariable=self.spoiler_summary, style='Small.TLabel').pack(anchor='w', pady=(8, 0))

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
            self.spoiler_info.set('First open a seed from Home.')
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

    def update_seed_tracker(self):
        """Give the open seed this version's in-game tracker (its data file and module, nothing else)."""
        if not self.artifact:
            self.status.set('Open a seed first.')
            return
        try:
            manifest, _ = read_artifact(self.artifact)
            add = not has_ingame_tracker(manifest)
            if add and not messagebox.askyesno('In-game tracker', 'This seed was made without the in-game tracker. Add it?'):
                return
            directory = self.artifact
            self.run_job(lambda progress: update_ingame_tracker(directory, add=add), self.ingame_tracker_updated)
        except Exception as error:
            self.error(error)

    def ingame_tracker_updated(self, written):
        self.status.set('In-game tracker updated (' + ', '.join(written) + '): it applies the next time the game starts.'
                        if written else 'The in-game tracker is already up to date.')
        self.load_tracker()

    def render_tracker(self):
        if not hasattr(self, 'tracker_rows') or not hasattr(self, 'home_list'):
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
                empty = ttk.Frame(container)
                empty.pack(expand=True, pady=40)
                mark = tk.Canvas(empty, width=46, height=42, background=self.colors['surface'], highlightthickness=0)
                theme.triforce(mark, 2, 2, 42, self.colors['line_strong'])
                mark.pack()
                ttk.Label(empty, text='No game open', style='Heading.TLabel').pack(pady=(12, 2))
                ttk.Label(empty, text='Create a seed in New seed, or open one from Home.', style='Muted.TLabel').pack()
                continue
            tree_frame = ttk.Frame(container)
            tree_frame.pack(fill='both', expand=True)
            tree = ttk.Treeview(tree_frame, columns=('state', 'reward', 'kind'), show='tree headings', selectmode='browse', height=9)
            self.tracker_trees[container] = tree
            tree.heading('#0', text='Zone / location', anchor='w')
            tree.column('#0', width=350, minwidth=200, stretch=True)
            for key, title, width in [('state', 'State', 125), ('reward', 'Reward', 210), ('kind', 'Type', 120)]:
                tree.heading(key, text=title, anchor='w')
                tree.column(key, width=width, minwidth=80, stretch=(key == 'reward'))
            for tag, color in theme.STATE_COLORS.items():
                tree.tag_configure(tag, foreground=color)
            tree.tag_configure('zone', font=self.fonts.strong)
            scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            zones, visible, labels = {}, 0, check_labels(self.current_checks)
            for check in self.current_checks:
                state = states[check['id']]
                completed, access = state.get('completed', False), state.get('access', 'unknown')
                region = check.get('region') or 'Other'
                bucket = 'done' if completed else 'available' if access == 'available' else 'blocked'
                if self.tracker_filter != 'all' and bucket != self.tracker_filter:
                    continue
                if completed and not self.show_completed.get():
                    continue
                if not completed and access == 'blocked' and not self.show_blocked.get():
                    continue
                name = labels[check['id']]
                reward = state.get('reward', '') if completed else ''
                kind = TRACKER_KINDS.get(check.get('category', ''), check.get('category', ''))
                if query and query not in (region + ' ' + name + ' ' + kind + ' ' + reward).casefold():
                    continue
                if region not in zones:
                    zones[region] = tree.insert('', 'end', iid='zone::' + region, open=self.zone_open.get(region, bool(query)), text=region, values=(f'{done[region]} / {totals[region]}', f'{available[region]} available' if available[region] else '', ''), tags=('zone',))
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
            tree.bind('<Double-1>', toggle)
            if not visible:
                ttk.Label(container, text='No location matches the filters.', style='Muted.TLabel').pack(anchor='w', pady=(5, 0))
        if self.tracker:
            count_done = sum(bool(state.get('completed')) for state in states.values())
            count_access = sum(not state.get('completed') and state.get('access') == 'available' for state in states.values())
            count_unknown = sum(not state.get('completed') and state.get('access', 'unknown') == 'unknown' for state in states.values())
            count_partial = sum(not state.get('completed') and state.get('access') == 'partial' for state in states.values())
            total = len(self.current_checks)
            self.tracker_counts = {'done': count_done, 'total': total, 'available': count_access}
            for key, value in [('available', count_access), ('blocked', total - count_done - count_access), ('done', count_done), ('all', total)]:
                self.counters[key][1].configure(text=str(value))
            self.tracker_summary.set({
                'keys': 'Small keys: found / total, updated when the game saves. Boss key: real time.',
                'souls': 'A family soul is listed in every zone where its enemies appear.',
            }.get(self.tracker_filter, f'Double-click a location to mark it by hand.   {count_partial} in a partial zone · {count_unknown} unknown'))
        else:
            self.tracker_counts = None
            for frame, count, label in self.counters.values():
                count.configure(text='–')
        self.render_keys()
        self.render_souls()
        self.place_view_tabs()
        self.render_home_list(states)
        self.update_home()
        self.update_hud(states)

    def render_souls(self):
        """The enemy souls card: one row per zone (owned / total), each soul found or missing."""
        if not hasattr(self, 'souls_rows'):
            return
        zones = self.tracker.souls() if self.tracker else []
        owned = {name for _, entries in zones for name, has in entries if has}
        names = {name for _, entries in zones for name, _ in entries}
        self.counters['souls'][1].configure(text=f'{len(owned)}/{len(names)}' if names else '–')
        if not zones:
            self.souls_shown = None
            return
        if zones == self.souls_shown and self.souls_tree and self.souls_tree.winfo_exists():
            return   # refreshed every second: rebuild only on a change
        self.souls_shown = zones
        old, scroll = self.souls_tree, 0.0
        if old and old.winfo_exists():
            scroll = old.yview()[0]
            for item in old.get_children(''):
                self.souls_open[item] = old.item(item, 'open')
        for child in self.souls_rows.winfo_children():
            child.destroy()
        tree = ttk.Treeview(self.souls_rows, columns=('state',), show='tree headings', selectmode='browse', height=9)
        tree.heading('#0', text='Zone / soul', anchor='w')
        tree.heading('state', text='State', anchor='w')
        self.souls_tree = tree
        tree.column('#0', width=350, minwidth=200, stretch=True)
        tree.column('state', width=160, minwidth=80, stretch=False)
        tree.tag_configure('owned', foreground=theme.STATE_COLORS['available'])
        tree.tag_configure('missing', foreground=theme.STATE_COLORS['blocked'])
        tree.tag_configure('zone', font=self.fonts.strong)
        scrollbar = ttk.Scrollbar(self.souls_rows, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        for zone, entries in zones:
            iid = 'souls::' + zone
            count = sum(has for _, has in entries)
            tree.insert('', 'end', iid=iid, text=zone, open=self.souls_open.get(iid, False),
                        values=(f'{count} / {len(entries)}',), tags=('zone',))
            for position, (name, has) in enumerate(entries):
                tree.insert(iid, 'end', iid=f'{iid}::{position}', text=name,
                            values=('Found' if has else 'Missing',), tags=('owned' if has else 'missing',))
        tree.update_idletasks()
        tree.yview_moveto(scroll)

    def place_view_tabs(self):
        """The Keys and Souls tabs exist only when the seed has keys / souls to show."""
        has = {'keys': bool(self.keys_shown), 'souls': bool(self.souls_shown)}
        previous = self.counters['all'][0]
        for key in ('keys', 'souls'):
            frame = self.counters[key][0]
            if has[key] and not frame.winfo_manager():
                frame.pack(side='left', padx=(0, 6), after=previous)
            elif not has[key] and frame.winfo_manager():
                frame.pack_forget()
            if has[key]:
                previous = frame
        if self.tracker_filter in has and not has[self.tracker_filter]:
            self.set_tracker_filter('all')

    def render_keys(self):
        """The dungeon keys card: small keys found / total and the boss key, per dungeon."""
        if not hasattr(self, 'keys_rows'):
            return
        rows = self.tracker.keys() if self.tracker else []
        small = [s for _, s, _ in rows if s]
        found, total = sum(s[0] for s in small), sum(s[1] for s in small)
        self.counters['keys'][1].configure(text=f'{found}/{total}' if small else '–')
        if not rows:
            self.keys_shown = None
            return
        if rows == self.keys_shown and self.keys_tree and self.keys_tree.winfo_exists():
            return   # refreshed every second: rebuild only on a change
        self.keys_shown = rows
        for child in self.keys_rows.winfo_children():
            child.destroy()
        tree = ttk.Treeview(self.keys_rows, columns=('small', 'boss'), show='tree headings', selectmode='none',
                            height=9)
        self.keys_tree = tree
        tree.heading('#0', text='Dungeon', anchor='w')
        tree.heading('small', text='Small keys', anchor='w')
        tree.heading('boss', text='Boss key', anchor='w')
        tree.column('#0', width=350, minwidth=200, stretch=True)
        tree.column('small', width=160, minwidth=80, stretch=False)
        tree.column('boss', width=160, minwidth=80, stretch=False)
        tree.tag_configure('done', foreground=theme.STATE_COLORS['available'])
        tree.pack(fill='both', expand=True)
        for dungeon, small, boss in rows:
            complete = (small is None or small[0] >= small[1]) and boss is not False
            tree.insert('', 'end', text=dungeon, tags=('done',) if complete else (),
                        values=(f'{small[0]} / {small[1]}' if small else '',
                                '' if boss is None else 'Yes' if boss else 'No'))

    def update_hud(self, states=None):
        if not self.hud:
            return
        if not self.tracker:
            self.hud.update(game_overlay.overlay_model({}, set(), set(), [], {}))
            return
        if states is None:
            states = {check['id']: self.tracker.check_state(check['id']) for check in self.current_checks}
        inventory, readable, tracked = self.tracker.inventory()
        self.hud.update(game_overlay.overlay_model(inventory, readable, tracked, self.current_checks, states,
                                                   self.tracker.keys()))

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
        if self.tracker_filter == 'souls':
            for zone, _ in (self.tracker.souls() if self.tracker else []):
                self.souls_open['souls::' + zone] = value
            if self.souls_tree and self.souls_tree.winfo_exists():
                for item in self.souls_tree.get_children(''):
                    self.souls_tree.item(item, open=value)
            return
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
        self.overlay.configure(background=self.colors['page'])
        self.overlay.attributes('-topmost', True)
        self.overlay.geometry('930x470')
        self.overlay.minsize(640, 330)
        frame = ttk.Frame(self.overlay, style='Card.TFrame', padding=theme.CARD_PADDING)
        frame.pack(fill='both', expand=True, padx=12, pady=12)
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
                    if self.ap_client:
                        self.ap_client.update(self.tracker.completed, self.tracker.goal_reached)
                    label = self.tracker_details.get('status', 'At the latest save')
                    when = self.tracker_details.get('updated_at', '')
                    self.connection_status.set(label + (' · ' + str(when) if when else ''))
                    signature = tuple((check['id'], tuple(sorted(self.tracker.check_state(check['id']).items()))) for check in self.current_checks)
                    if signature != self.tracker_signature:
                        self.tracker_signature = signature
                        self.render_tracker()
                    else:
                        self.update_hud()   # inventory and save time change without check changes
                elif kind == 'update-found':
                    self.update_found(*payload)
                elif kind == 'update-installed':
                    self.update_installed(payload)
                elif kind == 'update-error':
                    silent = payload[1] and self.update_silent
                    self.updating = False
                    if not silent:
                        messagebox.showerror('Update', str(payload[0]))
                elif kind == 'ap-change':
                    self.render_archipelago()
                elif kind == 'progress':
                    self.status.set(payload)
                    self.log.configure(state='normal')
                    self.log.insert('end', payload + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                else:
                    self.busy = False
                    self.progress.stop()
                    self.progress.pack_forget()
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

    def save_extra_emulators(self):
        text = self.extra_emulators.get().strip()
        live_memory.set_extra_emulators(text)
        if text != (self.app_state.get('extra_emulators') or ''):
            self.write_app_state(extra_emulators=text)

    # ------------------------------------------------------- updates
    def check_for_updates(self, silent):
        if self.updating == 'install':
            if not silent:
                messagebox.showinfo('Update', 'The update is being downloaded.')
            return
        if self.updating == 'check':
            self.update_silent = self.update_silent and silent   # a click shows the running check's answer
            return
        self.updating, self.update_silent = 'check', silent

        def worker():
            try:
                self.events.put(('update-found', (updater.latest_release(), silent)))
            except updater.UpdateError as error:
                self.events.put(('update-error', (error, silent)))
        threading.Thread(target=worker, daemon=True).start()

    def update_found(self, release, silent):
        silent = silent and self.update_silent
        self.updating = False
        if release is None:
            if not silent:
                messagebox.showinfo('Update', f'You have the latest version ({APP_VERSION}).')
            return
        notes = release.notes.strip()
        notes = ('\n\n' + (notes[:600] + '…' if len(notes) > 600 else notes)) if notes else ''
        if not updater.can_self_update():
            if messagebox.askyesno('Update available', f'Version {release.version} is available (you have '
                                   f'{APP_VERSION}).{notes}\n\nOpen the release page?'):
                webbrowser.open(release.page)
            return
        if not messagebox.askyesno('Update available', f'Version {release.version} is available (you have '
                                   f'{APP_VERSION}).{notes}\n\nDownload and install it now? The application '
                                   'restarts; your seeds and settings are kept.'):
            return
        if self.busy:
            messagebox.showinfo('Operation running', 'Wait for the generation or analysis to finish, then check again.')
            return
        self.updating = 'install'
        self.status.set(f'Downloading version {release.version}…')

        def worker():
            try:
                self.events.put(('update-installed', updater.install(release, lambda m: self.events.put(('progress', m)))))
            except updater.UpdateError as error:
                self.events.put(('update-error', (error, False)))
        threading.Thread(target=worker, daemon=True).start()

    def update_installed(self, target):
        self.updating = False
        self.status.set('Update installed.')
        if messagebox.askyesno('Update installed', 'The new version is installed. Restart now?') and self.close():
            updater.restart(target)   # only once this instance is gone: never two running

    def error(self, error):
        self.status.set(str(error))
        messagebox.showerror('Operation failed', str(error))

    def close(self):
        """Close the application; False when the player kept it open."""
        if self.busy:
            messagebox.showinfo('Operation running', 'Wait for the generation or analysis to finish before closing.')
            return False
        if self.hotkey_thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, 0x0012, 0, 0)
            self.hotkey_thread.join(timeout=1)
        if self.turbo:
            if (self.turbo.remapped and self.turbo.game_is_running() and not messagebox.askyesno(
                    'Game running',
                    'Turbo A plays the A button for the game. Closing now leaves A without effect until '
                    'the game is restarted. Close anyway?')):
                return False
            self.turbo.stop()
        if self.ap_client:
            self.ap_client.stop()
        self.save_extra_emulators()
        self.closed = True
        self.root.destroy()
        return True


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
