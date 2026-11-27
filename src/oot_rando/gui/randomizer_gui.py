"""Desktop application (Tkinter). Run with ``python -m oot_rando``."""
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import secrets
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter import font as tkfont

from oot_rando import native_dialogs as filedialog

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.randomizer.randomizer_core import Settings, CHECKS, GENERATOR_VERSION, settings_from_patch
from oot_rando.randomizer.artifact import read_artifact, regeneration_settings
from oot_rando.randomizer.mods_folder import validate_mod_directory
from oot_rando.randomizer.qol_install import install_qol
from oot_rando.tracker.auto_tracker import TrackerSession, find_save_slots, newest_save
from oot_rando.tracker import game_overlay
from oot_rando.tracker import live_memory
from oot_rando.randomizer import spoiler_report
from oot_rando.randomizer import settings_string
from oot_rando.tracker import turbo_a
from oot_rando.patching.randomize_kokiri import POOL, TITLE
from oot_rando.game.randomizer_categories import CATEGORIES
from oot_rando.game.world_maps import SAFE_CATEGORIES
from oot_rando.logic import rando_options
from oot_rando.logic.rando_options import STARTABLE_ITEMS
from oot_rando.native_dialogs import open_in_file_manager
from oot_rando.paths import data_dir, error_log, seeds_dir, state_dir, write_error_log
from oot_rando.gui import theme
from oot_rando.gui.parties_page import PartiesPage
from oot_rando import __version__ as APP_VERSION, updater
from oot_rando import pc_port

STATE = state_dir()
LABELS = dict(zip(POOL, ('Green Rupee', 'Blue Rupee', 'Red Rupee', 'Purple Rupee',
                        'Gold Rupee', 'Deku Nuts', 'Deku Seeds', 'Arrows: small bundle',
                        'Arrows: medium bundle', 'Arrows: large bundle', 'Deku Shield', 'Hylian Shield')))
GAME_OPTIONS = [('randomize_chests', 'Randomize the four Kokiri chests (child and adult)'),
                ('avoid_vanilla', 'Avoid vanilla rewards when the pool allows it'),
                ('open_forest', 'Open the way from Kokiri Forest to Hyrule Field'),
                ('skulltulas_always_present', 'Night-only gold skulltulas present day and night')]
SKIP_OPTIONS = [('skip_locked_cutscenes', 'Skippable cutscenes: intro, title screen demo and end credits'),
                ('skip_auto_dialogues', 'Automatic dialogues skippable with + (minigames, Navi: 12 sequences)'),
                ('skip_chest_cutscenes', 'Chests (big and small) without cutscene: the lid opens and the item is obtained')]
OPTIONS = GAME_OPTIONS + SKIP_OPTIONS
ARCHIVE = data_dir() / 'seeds-uninstalled'
TRACKER_KINDS = {
    'full_chests': 'Chest', 'full_skulltula': 'Gold Skulltula', 'full_freestanding': 'Freestanding item',
    'full_shop': 'Shop', 'full_pots': 'Pot', 'full_crates': 'Crate', 'full_beehives': 'Beehive',
    'full_bushes': 'Bush', 'full_rocks': 'Rock', 'full_trees': 'Tree', 'full_npc': 'NPC', 'full_scrub': 'Business scrub', 'kokiri_chests': 'Chest',
    'world_chests': 'Chest', 'vanilla_chest': 'Chest', 'vanilla_freestanding': 'Freestanding item',
    'vanilla_gs_token': 'Gold Skulltula', 'vanilla_shop': 'Shop', 'vanilla_npc': 'NPC',
    'vanilla_collectable': 'Item', 'vanilla_beehive': 'Beehive', 'vanilla_scrub': 'Deku Scrub',
    'vanilla_grottoscrub': 'Deku Scrub (grotto)', 'vanilla_song': 'Song', 'vanilla_crate': 'Crate',
    'vanilla_smallcrate': 'Small crate', 'vanilla_pot': 'Pot', 'vanilla_flyingpot': 'Flying pot',
    'vanilla_boss': 'Boss', 'vanilla_bossheart': 'Heart Container', 'vanilla_cutscene': 'Cutscene',
    'vanilla_rupeetower': 'Rupee tower', 'full_boss': 'Dungeon reward', 'full_bossheart': 'Boss heart container',
    'full_fairy': 'Great fairy', 'full_quest': 'Quest reward',
    'full_master_sword': 'Master Sword', 'full_gerudo_card': 'Gerudo Membership Card',
}

OPTION_COPY = {
    'accessibility': ('Accessibility goal', 'Choose whether every location must be reachable or finishing the game is enough.'),
    'shuffle_chests': ('Shuffle chest contents', 'Important items can be in any selected chest.'),
    'chest_matching': ('Locations used for progression', 'Identified chests: exact matches. By zone: more chests, with the most cautious access conditions of the zone.'),
    'shuffle_remake_items': ('Include remake-only items', 'Adds the items specific to this version of the game to the shuffle, without making them required for progression.'),
    'progressive_order': ('Find upgrades in order', 'Always on: each upgrade found gives the next level (Hookshot, then Longshot), whatever the order. Kept for older settings.'),
    'progressive_strict': ('Require the previous level for each upgrade', 'Always on: an upgrade never skips a level. Kept for older settings.'),
    'shopsanity': ('Items shuffled per shop', 'Shuffled items cost 10 rupees. One copy of the required purchases stays available; masks are kept.'),
    'tokensanity': ('Gold Skulltulas', 'Skulltulas give a shuffled reward; their tokens can be elsewhere.'),
    'shuffle_freestanding_items': ('Freestanding items', 'Includes rupees, hearts and heart pieces lying in the world.'),
    'shuffle_npc_gifts': ('Character gifts and minigames', 'Shuffles the supported rewards of characters and minigames.'),
    'shuffle_boss_rewards': ('Boss and dungeon rewards', 'Shuffles spiritual stones, medallions and heart containers. The game scenes are kept.'),
    'shuffle_great_fairies': ('Great fairy rewards', 'Shuffles spells, magic and defense upgrades.'),
    'shuffle_quest_rewards': ('Main quest rewards', 'Includes the ocarinas, Zelda\'s Letter (with a shuffled child trade quest), the Light Arrows, the Biggoron Sword and Ruto\'s Letter. Songs follow the Songs setting.'),
    'shuffle_pots': ('Pots', 'The first reward is shuffled. Once picked up, the pot goes back to its vanilla loot.'),
    'shuffle_crates': ('Crates', 'The first reward is shuffled. Later pickups use the vanilla loot.'),
    'shuffle_beehives': ('Beehives', 'The first reward is shuffled. Later pickups use the vanilla loot.'),
    'shuffle_bushes': ('Bushes and grass', 'Shuffles the first reward of supported sources, then restores their vanilla loot.'),
    'shuffle_rocks': ('Rocks and stones', 'The first reward is shuffled. Then the rock goes back to its vanilla behaviour, even if it gave no item.'),
    'shuffle_trees': ('Trees', 'Roll into a tree: the first reward is shuffled. Then the tree goes back to its vanilla loot.'),
    'shuffle_enemy_spawns': ('Enemy souls', 'Find souls to make the matching enemies appear. A new game is required.'),
    'start_inventory_from_pool': ('Starting inventory', 'Items held from the start, separated by commas, '
                                  'with a count if needed: "Hover Boots, Progressive Hookshot x2, Heart Container x3". '
                                  'Songs by name ("Sarias Song"). Tunics are not available yet.'),
    'item_pool_value': ('Item pool', 'Plentiful: an extra copy of the major items. Scarce: at most 3 bottles '
                        'and half the hearts. Minimal: one bottle and no extra hearts.'),
    'fake_item_traps': ('Fake item traps', 'Fake copies of items hide in chests and on the ground. They look '
                        'real, but Link is frozen. Some: one per major item. Plentiful: two per major item, '
                        'plus the medallions, spiritual stones and songs. Not tested in game yet.'),
    'logic_no_night_tokens_without_suns_song': ("Night skulltulas need Sun's Song",
                                                 'Waiting for the night is not expected by the logic.'),
}
# Longer explanations, shown in the tooltip of each setting (hover the label or the ⓘ).
# Missing entries use the short text above (OPTION_COPY) or the option's own help.
OPTION_TIPS = {
    'accessibility': 'Every location reachable: the logic guarantees that you can open every check of the seed. '
                     'Only victory guaranteed: some useless locations may stay out of reach, which allows more '
                     'varied placements.',
    'logic_no_night_tokens_without_suns_song': "On: gold skulltulas that only come out at night are expected only "
                                               "once you have Sun's Song. Off: the logic may ask you to wait for "
                                               "the night (or use the day/night option below).",
    'skulltulas_always_present': 'Night-only gold skulltulas are also there during the day. Purely a comfort '
                                 'setting: the logic does not change.',
    'open_forest': 'The Kokiri Forest exit to Hyrule Field is open from the start: its guard and invisible wall '
                   'are gone.',
    'open_kakariko': 'Closed: the guard opens the gate to Death Mountain once he has read Zelda\'s Letter, as in '
                     'the vanilla game. Open: the gate is open from the start and the Death Mountain part of the '
                     'Fire Stone quest starts at once. Zelda\'s Letter has no use left: with the quest rewards '
                     'shuffled, Zelda gives a shuffled item instead. To be confirmed in game.',
    'open_door_of_time': 'The Door of Time is open from the start and the Master Sword can be pulled without the '
                         'Spiritual Stones or the Song of Time. Zelda\'s escape still gives the Ocarina of Time '
                         'and the Song of Time. To be confirmed in game.',
    'starting_age': 'Child: the usual start in Kokiri Forest. Adult: a new game begins as adult Link in the '
                    'Temple of Time, the Door of Time open (forced on) and time travel possible both ways at the '
                    'pedestal. Link holds the Master Sword, needed to travel back, plus the starting inventory '
                    'you choose below, nothing else. New save required. To be confirmed in game.',
    'door_of_time_requirement': 'Play the Song of Time with an ocarina at the door. Choose whether this also '
                                'needs all three Spiritual Stones, only the Goron Ruby and Zora Sapphire, or '
                                'no stones. Door of Time open overrides this choice. The stones for Zelda\'s '
                                'escape are a separate setting. To be confirmed in game.',
    'spiritual_stones': 'The stones Zelda\'s escape asks for to give the Ocarina of Time and the Song of Time. '
                        'Require all: Kokiri Emerald, Goron Ruby and Zora Sapphire. Vanilla: Goron Ruby and '
                        'Zora Sapphire only. Door of Time requirements are separate.',
    'zora_fountain': 'Ruto\'s Letter required: King Zora blocks the way to Zora\'s Fountain until he reads the '
                     'letter, as in the vanilla game. Always moved: he stands aside from the start and stays '
                     'there; the letter can no longer be delivered, so it never becomes a bottle. '
                     'To be confirmed in game.',
    'gerudo_fortress': 'Four carpenters: free the four carpenters to get the Gerudo Membership Card, as in the '
                       'vanilla game. One carpenter: the first one freed, in any cell, ends the fortress and '
                       'gives the rescue reward, frees the remaining carpenters and opens all cells (the keys of '
                       'the thieves not yet defeated lie in their cells). '
                       'To be confirmed in game.',
    'open_gerudo_valley_bridge': 'The broken bridge of Gerudo Valley is repaired from the start: the adult '
                                 'crosses it on foot without Epona or the Longshot. The carpenters stay in their '
                                 'cells; the last rescue still gives the Gerudo Membership Card. '
                                 'To be confirmed in game.',
    'shuffle_chests': 'On: every chest of the game (big and small, major items included) gets an item of the '
                      'shuffle. Off: chests keep their vanilla content.',
    'chest_matching': 'How chests are tied to the logic. Identified chests: only chests matched one to one with '
                      'the logic hold progression items (safest). Access by zone: more chests are used, each '
                      'with the most cautious access conditions of its zone.',
    'shuffle_kokiri_sword': 'The Kokiri Sword leaves its chest and can be anywhere; its chest holds another item. '
                            'Experimental: to be confirmed in game.',
    'shuffle_remake_items': 'The remake adds a few items of its own (Deku seed and jar upgrades). On: they join '
                            'the shuffle as filler, never required to finish.',
    'tokensanity': 'Each gold skulltula gives a shuffled item instead of its token, and the tokens are placed '
                   'elsewhere. Dungeons / Overworld: only the skulltulas of that part of the world.',
    'shuffle_freestanding_items': 'Rupees, hearts and heart pieces lying on the ground give shuffled items. '
                                  'Dungeons / Overworld: only those of that part of the world.',
    'shuffle_scrubs': 'Business scrubs that sell one item (stick and nut upgrades, two heart pieces) sell a '
                      'shuffled item. The scrub still announces its vanilla item; you get the placed one. '
                      'Low price: 10 rupees. Remake price: 40 and 100 rupees (100 needs the Adult\'s Wallet). '
                      'Refill scrubs and Dream World scrubs are not included. To be confirmed in game.',
    'shopsanity': 'Up to 8 slots of each shop sell shuffled items for 10 rupees (the Market bazaar, potion '
                  'shop and bombchu shop count as three shops). One copy of every purchase required by '
                  'the logic stays on sale, except with "Whole shops": every slot is shuffled and refills '
                  'come from the world. The mask shop is kept.',
    'shuffle_npc_gifts': 'Rewards given by characters and minigames (the supported ones) are shuffled.',
    'shuffle_quest_rewards': 'The big story rewards are shuffled: ocarinas, Zelda\'s Letter (the child trade '
                             'quest is shuffled with it), the Light Arrows, the Biggoron Sword and Ruto\'s Letter (the bottle in Lake Hylia).',
    'shuffle_boss_rewards': 'Spiritual stones, medallions and boss heart containers are shuffled. The scenes '
                            'still play.',
    'shuffle_great_fairies': 'The great fairies give shuffled items instead of spells, magic and defense.',
    'shuffle_pots': 'The first item of each pot is shuffled. Once picked up, the pot gives its vanilla loot again.',
    'shuffle_crates': 'The first item of each crate is shuffled, then its vanilla loot.',
    'shuffle_beehives': 'The first item of each beehive is shuffled, then its vanilla loot.',
    'shuffle_bushes': 'The first item of each supported bush and grass tuft is shuffled, then its vanilla loot.',
    'shuffle_rocks': 'The first item of each rock is shuffled. Afterwards the rock behaves as in the vanilla game.',
    'shuffle_trees': 'Roll into a tree: its first item is shuffled, then its vanilla loot.',
    'item_pool_value': 'How many items are in the shuffle. Balanced: as in the vanilla game. Plentiful: one extra '
                       'copy of the major items. Scarce: at most 3 bottles and half the hearts. Minimal: one '
                       'bottle and no extra hearts.',
    'start_inventory_from_pool': 'Items held from the start, separated by commas, with a count if needed: '
                                 '"Hover Boots, Progressive Hookshot x2, Heart Container x3". Songs by name '
                                 '("Sarias Song"). They are taken out of the shuffle. Tunics are not available yet.',
    'key_rings_list': 'Only used when "Key rings" is "Chosen dungeons": the dungeons that get a key ring, '
                      'separated by commas (for example "Forest Temple, Fire Temple").',
    'shuffle_enemy_spawns': 'Enemies only appear once you have found their soul. Bosses only: one soul per boss. '
                            'One soul per region: all enemies of a region at once. One soul per enemy type: '
                            'every kind of enemy has its own soul. A new game is required.',
    'big_poe_count': 'The Poe collector gives his reward after this many Big Poes (vanilla: 10). '
                     'To be confirmed in game.',
    'chicken_count': 'The cucco lady in Kakariko gives her reward once this many of her cuccos are back in the '
                     'pen (vanilla: 7). Her lines name the new number. To be confirmed in game.',
    'skip_child_zelda': 'Start as if Malon, Talon, Zelda and Impa had been met: Zelda\'s Letter and Lullaby '
                        'are shuffled elsewhere. The child castle grounds become optional: their shuffled checks hold '
                        'green rupees, except the Great Fairy. Later events keep their conditions (Kokiri '
                        'Forest exit after the Deku Tree...). New save required. To be confirmed in game.',
}
# Settings page layout: (card title, card note, [option names]). "game:" names are the
# general settings of the application (Settings fields), the others complete-mode options.
# A visible option missing here is shown at the end, in a card named after its tab.
SETTING_GROUPS = (
    ('Open world', 'Zones and quests open from the start.',
     ['game:open_forest', 'starting_age', 'open_kakariko', 'open_door_of_time', 'door_of_time_requirement', 'spiritual_stones', 'zora_fountain', 'gerudo_fortress',
      'open_gerudo_valley_bridge', 'skip_child_zelda']),
    ('Logic and accessibility', '',
     ['accessibility', 'logic_no_night_tokens_without_suns_song', 'game:skulltulas_always_present']),
    ('Item pool', 'What is shuffled and what you start with.',
     ['item_pool_value', 'start_inventory_from_pool', 'shuffle_kokiri_sword',
      'shuffle_master_sword', 'shuffle_gerudo_card', 'shuffle_remake_items', 'blue_fire_arrows',
      'fake_item_traps']),
    ('Shuffled locations', 'Where items can be found.',
     ['shuffle_chests', 'chest_matching', 'tokensanity', 'shuffle_freestanding_items', 'shuffle_npc_gifts',
      'shuffle_quest_rewards', 'shuffle_boss_rewards', 'shuffle_great_fairies', 'shuffle_song_items',
      'shopsanity', 'shuffle_scrubs']),
    ('Pots, crates and scenery', 'The first item of each source is shuffled, then the vanilla loot.',
     ['shuffle_pots', 'shuffle_crates', 'shuffle_beehives', 'shuffle_bushes', 'shuffle_rocks', 'shuffle_trees']),
    ('Dungeon contents', '',
     ['shuffle_mapcompass', 'shuffle_smallkeys', 'key_rings', 'key_rings_list', 'shuffle_bosskeys']),
    ('Enemy souls', '', ['shuffle_enemy_spawns']),
    ('Minigames', '', ['big_poe_count', 'chicken_count']),
)
# Kept in settings files (older seeds, AP YAML), but never shown.
HIDDEN_OPTIONS = ('progressive_order', 'progressive_strict', 'fast_chests')
GAME_OPTION_COPY = {'open_forest': 'Open the way from Kokiri Forest to Hyrule Field',
                    'skulltulas_always_present': 'Night-only gold skulltulas present day and night'}
UNTESTED_WORDS = ('confirm', 'validated', 'pilot', 'experimental')
# Pages without their own scroll area keep the same right margin as the scrolled ones.
PAGE_GUTTER = 22
RANDOM_SEED = re.compile(r'[0-9a-f]{16}')   # a name from the Random button, not chosen by the player


def option_tip(option, label, help_text):
    """Tooltip text of a complete-mode option: title line, then explanation and values."""
    body = OPTION_TIPS.get(option.name) or help_text or ''
    parts = [body] if body else []
    if option.kind == 'choice':
        supported = [(value, text) for value, text, reason in option.values if reason is None
                       and not (option.name == 'spiritual_stones' and value == 'door')]
        if len(supported) > 1:
            lines = []
            for value, text in supported:
                mark = ' (experimental)' if value in option.experimental else ''
                default = ' (default)' if value == option.default else ''
                lines.append(f'• {text}{default}{mark}')
            parts.append('Values:\n' + '\n'.join(lines))
    elif option.experimental and not any(word in body.lower() for word in UNTESTED_WORDS):
        parts.append('Experimental: to be confirmed in game.')
    return label + '\n' + '\n\n'.join(parts)


class ListVar:
    """Text field holding a subset of an option's values (``"Forest Temple, Fire Temple"``)."""

    def __init__(self, option):
        self.option = option
        self.text = tk.StringVar(value='')

    def get(self):
        chosen = []
        for part in (p.strip() for p in self.text.get().split(',')):
            if not part:
                continue
            match = next((v for v in self.option.allowed() if v.casefold() == part.casefold()), None)
            if match is None:
                raise ValueError(f'{self.option.label}: unknown value {part!r} '
                                 f'(choose among {", ".join(self.option.allowed())}).')
            chosen.append(match)
        return tuple(v for v in self.option.allowed() if v in chosen)

    def set(self, value):
        self.text.set(', '.join(value or ()))


class ItemsVar:
    """A starting inventory (``{'Hover Boots': 1, 'Bow': 2}``), shown as removable tags."""

    def __init__(self):
        self.items, self.listeners = {}, []

    def get(self):
        return dict(self.items)

    def set(self, value):
        self.items = dict(value or {})
        for listener in self.listeners:
            listener()



def default_mods_dir():
    """The Eden emulator's mods folder for the game when it exists, else empty (to choose)."""
    appdata = os.environ.get('APPDATA')
    folder = Path(appdata) / 'eden' / 'load' / TITLE if appdata else None
    return str(folder) if folder and folder.is_dir() else ''

class Application(PartiesPage):
    def __init__(self, root):
        self.root = root
        root.title('OoT Randomizer')
        root.geometry('1220x860')
        root.minsize(1040, 720)
        self.configure_theme()
        self.events, self.busy = queue.Queue(), False
        self.artifact, self.tracker, self.overlay, self.hud = None, None, None, None
        self.regen_settings = None   # settings of an installed seed made by an older generator
        self.artifact_manifest = None   # manifest of self.artifact (set by use_artifact)
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
        self.qol_options = {'intro_skip': tk.BooleanVar(value=True), 'fast_chests': tk.BooleanVar(value=True)}
        self.show_completed = tk.BooleanVar(value=True)
        self.show_blocked = tk.BooleanVar(value=True)
        self.tracker_search, self.save_path = tk.StringVar(), tk.StringVar()
        self.auto_save = tk.BooleanVar(value=True)
        self.app_state = self.read_app_state()
        self.init_parties()
        self.turbo_enabled = tk.BooleanVar(value=self.app_state.get('turbo_a', True) is not False)
        # Remembered between app starts (it was off again at every start: 15/11 report, issue #39).
        self.options['skulltulas_always_present'].set(self.app_state.get('skulltulas_always_present') is True)
        self.options['skulltulas_always_present'].trace_add(
            'write', lambda *args: self.write_app_state(
                skulltulas_always_present=self.options['skulltulas_always_present'].get()))
        # Game file and mods folder: chosen once by the player, then remembered.
        self.nup.set(self.app_state.get('game_file') or '')
        self.mods.set(self.app_state.get('mods_dir') or default_mods_dir())
        self.nup.trace_add('write', lambda *args: self.write_app_state(game_file=self.nup.get()))
        self.mods.trace_add('write', self._on_mods_dir_changed)
        self.check_updates = tk.BooleanVar(value=self.app_state.get('check_updates', True) is not False)
        self.check_updates.trace_add('write', lambda *args: self.write_app_state(check_updates=self.check_updates.get()))
        # Opt-in: also offer the GitHub pre-releases (vX.Y.Z-beta.N) when checking for updates.
        self.experimental_updates = tk.BooleanVar(value=self.app_state.get('experimental_updates') is True)
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
        self.seed_chip = tk.StringVar(value='No seed open')   # name of the open adventure (sidebar card)
        self.sidebar = theme.Sidebar(root, self.fonts, self.show_page, footer=f'Version {APP_VERSION}')
        self.sidebar.pack(side='left', fill='y')
        outer = ttk.Frame(root, padding=(34, 26, 34, 18), style='Page.TFrame')
        outer.pack(side='left', fill='both', expand=True)
        self._outer = outer
        header = ttk.Frame(outer, style='Page.TFrame')
        header.pack(fill='x', pady=(0, 18))
        self._header = header
        self.page_title, self.page_subtitle = tk.StringVar(), tk.StringVar()
        titles = ttk.Frame(header, style='Page.TFrame')
        titles.pack(side='left', fill='x', expand=True)
        ttk.Label(titles, textvariable=self.page_title, style='PageTitle.TLabel').pack(anchor='w')
        ttk.Label(titles, textvariable=self.page_subtitle, style='PageSub.TLabel').pack(anchor='w', pady=(2, 0))
        # Errors and warnings of the current page: banners here, never a window.
        self.notice_area = ttk.Frame(outer, style='Page.TFrame')
        self.notices, self.current_page = [], None
        self.toast = theme.Toast(root, self.fonts)
        self.tabs = ttk.Notebook(outer, style='Pages.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.pages = {}
        self.seed_name, self.tracker_counts, self.tracker_filter = '', None, 'all'
        self.current_preset = None
        self.home_tab = self.tab('home', 'Home', 'Welcome', 'Your adventure at a glance.')
        self.parties_tab = self.tab('parties', 'My Games', 'My Games',
                                   'Find each adventure with its seed and its save.')
        self.settings_tab = self.tab('newseed', 'New seed', 'New seed', 'Pick an adventure, then generate it.')
        self.tracker_tab = self.tab('tracker', 'Tracker', 'Tracker', 'What you found, and what you can reach now.')
        self.multiworld_tab = self.tab('multiworld', 'Multiworld', 'Multiworld', 'Play with friends through Archipelago. Three steps.')
        self.sidebar.set_visible('parties', self.parties_enabled.get())
        self.sidebar.gap()
        self.setup_tab = self.tab('setup', 'Setup', 'Setup', 'Where your game lives. Set once.')
        self.spoiler_tab = self.tab('spoiler', 'Spoiler', 'Spoiler', 'Every reward of the open seed. Reveal only if you want to know.')
        self.help_tab = self.tab('help', 'Help', 'Help', 'How the application works, step by step.')
        self.tabs.bind('<<NotebookTabChanged>>', lambda event: self.page_changed())
        # Without a seed, Home fits on one screen: nothing to scroll to.
        self.home_body = self.scrollable(self.home_tab, locked=lambda: not self.artifact)
        self.build_action_bar()   # under the settings, never scrolled away
        self.settings_body = self.scrollable(self.settings_tab)
        self.multiworld_body, self.setup_body = self.scrollable(self.multiworld_tab), self.scrollable(self.setup_tab)
        self.build_home()
        self.build_parties()
        self.build_setup()
        self.build_categories()
        self.build_tracker()
        self.build_multiworld()
        self.build_spoiler()
        self.build_help()
        for variable in (self.nup, self.mods, self.save_path):
            variable.trace_add('write', lambda *args: self.update_home())
        self.update_home()
        # Shown only while a long job runs: its current step and a progress bar.
        bottom = self.status_bar = ttk.Frame(outer, style='Page.TFrame')
        self.status_parent = outer
        self.progress = ttk.Progressbar(bottom, mode='indeterminate', length=120)
        ttk.Label(bottom, textvariable=self.status, style='PageHeading.TLabel', wraplength=760).pack(side='left', fill='x')
        self.show_page('home')
        for number in range(1, 10):
            root.bind_all(f'<Control-Key-{number}>', lambda event, n=number: self.shortcut_page(n))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.register_hotkey()
        self.tracker_search.trace_add('write', lambda *args: self.render_tracker())
        self.seed_chip.trace_add('write', lambda *args: self.update_adventure())
        self._after_ids = set()
        self.root.bind('<Destroy>', self._on_root_destroy, add='+')
        self._schedule_after(100, self.poll)
        updater.cleanup()
        if self.check_updates.get():
            self._schedule_after(2500, lambda: self.check_for_updates(silent=True))
        self._schedule_after(1800, self.tracker_tick)
        self._schedule_after(50, self.restore_last_artifact)
        self._schedule_after(60, self.start_turbo)

    def _schedule_after(self, delay_ms, callback):
        if getattr(self, 'closed', False):
            return None
        ids = getattr(self, '_after_ids', None)
        if ids is None:
            ids = set()
            self._after_ids = ids
        box = [None]
        def _wrapped():
            if box[0] is not None:
                ids.discard(box[0])
            if getattr(self, 'closed', False):
                return
            callback()
        aid = self.root.after(delay_ms, _wrapped)
        box[0] = aid
        ids.add(aid)
        return aid

    def _on_root_destroy(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        self.closed = True
        self._cancel_all_after()

    def _cancel_all_after(self):
        ids = getattr(self, '_after_ids', None)
        if not ids:
            return
        for aid in list(ids):
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        ids.clear()

    def configure_theme(self):
        self.colors = dict(theme.COLORS, bg=theme.COLORS['surface'], accent=theme.COLORS['green'])
        self.fonts, self.images = theme.apply(self.root)

    # ------------------------------------------------------------ layout
    def scrollable(self, outer, locked=None):
        """A vertically scrolled page. ``locked()`` true: the page stays at its top, without a bar."""
        canvas = tk.Canvas(outer, highlightthickness=0, background=self.colors['page'], borderwidth=0)
        bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview, style='Page.Vertical.TScrollbar')
        parent = ttk.Frame(canvas, padding=(0, 0, 16, 6), style='Page.TFrame')
        parent.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        window = canvas.create_window((0, 0), window=parent, anchor='nw')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        def autohide(first, last):
            # The bar keeps its place (no relayout, so no flicker) and is only painted when needed.
            if locked and locked():
                if float(first) > 0:   # dragged through the hidden bar: back to the top
                    canvas.after_idle(lambda: canvas.yview_moveto(0))
                bar.configure(style='Hidden.Vertical.TScrollbar')
                bar.set(first, last)
                return
            needed = not (float(first) <= 0 and float(last) >= 1)
            bar.configure(style='Page.Vertical.TScrollbar' if needed else 'Hidden.Vertical.TScrollbar')
            bar.set(first, last)
        bar.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=autohide)
        canvas.pack(side='left', fill='both', expand=True)
        def wheel(event):
            if locked and locked():
                return
            if str(event.widget).startswith(str(outer)):
                units = theme.wheel_units(event.num, event.delta)
                if units:
                    canvas.yview_scroll(units, 'units')
        for sequence in theme.WHEEL_EVENTS:
            self.root.bind_all(sequence, wheel, add='+')
        parent.canvas = canvas
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
        self.build_tutorial(parent)
        ttk.Label(parent, text='MORE DETAILS', style='PageField.TLabel').pack(anchor='w', pady=(10, 8))
        sections = [
            ('Prepare a game', 'In Setup, choose your .nup file and the mods folder. In New seed, pick an adventure, then click Generate and install: the seed is written straight into the mods folder. Close the game during installation.'),
            ('Play on a PC port (Hookshot, Longshot...)', 'Choose the mods folder next to the game exe (hookshot.exe, longshot.exe...). Each seed is installed in its own sub-folder. Only one seed of this application stays active at a time; the previous one is archived.'),
            ('Track the exploration', 'The tracker follows the most recent save by itself. Locations are updated after the game saves. Rewards of completed checks appear next to their name.'),
            ('Understand the states', 'Available: the logic estimates you can get the reward with your inventory. Blocked: a known condition is missing. Unknown: the data does not allow a conclusion. These locations stay visible by default.'),
            ('Keep the right save', 'Generate a new seed, start a new game, then save after the intro. The tracker picks the newest save; choose another in Setup. An old save cannot be linked automatically. The tracker never changes its files.'),
            ('Repeatable sources', 'In a new seed, the shuffled reward can only be picked up once. Then pots, bushes, crates, beehives, rocks and trees go back to their vanilla loot. Old seeds keep their rules.'),
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
        row = ttk.Frame(parent, style='Page.TFrame')
        row.pack(fill='x', pady=(4, 8))
        ttk.Label(row, text=f'Application version: {APP_VERSION} (generator {GENERATOR_VERSION}).',
                  style='Page.TLabel').pack(side='left')
        ttk.Button(row, text='Updates are in Setup ›', style='Page.Link.TButton',
                   command=lambda: self.show_page('setup')).pack(side='left', padx=(8, 0))

    TUTORIAL = [
        ('setup', 'Tell the app where your game is',
         'Open Setup and choose two things: your game file (.nup) and the mods folder. On a PC port '
         '(Hookshot, Longshot…), the mods folder sits next to the game exe. On an emulator, it is the title '
         f'folder {TITLE} in the emulator\'s load folder. A green tick under each field means it was recognised. '
         'You only do this once.', 'Open Setup ›', 'setup'),
        ('seed', 'Create your first seed',
         'Open New seed and pick an adventure: each card is a ready-made set of settings, so you can '
         'generate right away and change details later. Close the game, then click Generate and install: '
         'the seed is written straight into the mods folder.', 'Create a seed ›', 'newseed'),
        ('save', 'Start a new game and save once',
         'Launch the game and start a new file (an old save belongs to another seed). Play past the intro, '
         'then save: the tracker finds the newest save by itself and links it to this seed.', None, None),
        ('play', 'Play and follow your progress',
         'Home shows how many locations you found and what is in reach now. The Tracker lists every location: '
         'Available means your items let you get it. It updates each time the game saves, and live while '
         'the game runs.', 'Open the tracker ›', 'tracker')]

    def build_tutorial(self, parent):
        """First-time guide at the top of Help: four steps, ticked as the player completes them."""
        box = self.card(parent, 'First time here? Start in 4 steps',
                        'Follow these steps in order. Each one is ticked as soon as the app sees it done.')
        self.tutorial_marks = {}
        for index, (key, title, text, button, page) in enumerate(self.TUTORIAL):
            if index:
                theme.rule(box).pack(fill='x', pady=(2, 12))
            row = ttk.Frame(box)
            row.pack(fill='x', pady=(0, 10))
            mark = theme.badge(row, self.images)
            mark.pack(side='left', anchor='n', padx=(0, 16))
            body = ttk.Frame(row)
            body.pack(side='left', fill='x', expand=True)
            ttk.Label(body, text=title, style='Heading.TLabel').pack(anchor='w')
            ttk.Label(body, text=text, style='Muted.TLabel', wraplength=640, justify='left').pack(anchor='w', pady=(2, 0))
            if button:
                ttk.Button(body, text=button, style='Link.TButton',
                           command=lambda page=page: self.show_page(page)).pack(anchor='w', pady=(6, 0))
            self.tutorial_marks[key] = mark
        theme.rule(box).pack(fill='x', pady=(2, 12))
        ttk.Label(box, text='Going further: play with friends in Multiworld, keep several adventures side by side '
                  'with My Games (turn it on in Setup), or look up where every item is in Spoiler.',
                  style='Small.TLabel', wraplength=720, justify='left').pack(anchor='w')
        self.update_tutorial()

    def update_tutorial(self):
        if not hasattr(self, 'tutorial_marks'):
            return
        nup = self.nup.get().strip()
        mods = self.mods.get().strip()
        done = {'setup': bool(nup) and Path(nup).is_file() and bool(mods) and Path(mods).is_dir(),
                'seed': bool(self.artifact),
                'save': bool(self.tracker) and self.tracker.link == 'linked'}
        done['play'] = done['save'] and bool(self.tracker_counts) and self.tracker_counts.get('done', 0) > 0
        current = next((key for key, *_ in self.TUTORIAL if not done[key]), None)
        for index, (key, *_) in enumerate(self.TUTORIAL):
            self.tutorial_marks[key].set('done' if done[key] else 'on' if key == current else 'off', str(index + 1))

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
                if key != self.current_page:
                    self.current_page = key
                    self.clear_notices()
                    if self.busy:
                        self.show_status_bar()

    def shortcut_page(self, number):
        """Ctrl+1 … Ctrl+9: the menu entries, in their order on screen."""
        shown = [key for key in self.sidebar.order if key not in self.sidebar.hidden]
        if number <= len(shown):
            self.show_page(shown[number - 1])
        return 'break'

    # ------------------------------------------------------------ feedback
    def notify(self, text, action=None):
        """A success or a hint: a toast for a few seconds, the work goes on."""
        self.toast.show(text, action)

    def show_notice(self, kind, title, text='', actions=()):
        """A banner at the top of the current page ('error', 'warn' or 'info')."""
        self.clear_notices()
        notice = theme.Notice(self.notice_area, kind, title, text, actions, on_close=self.clear_notices,
                              wraplength=720)
        notice.pack(fill='x')
        self.notices.append(notice)
        if not self.notice_area.winfo_manager():
            self.notice_area.pack(fill='x', pady=(0, 14), padx=(0, PAGE_GUTTER), before=self.tabs)
        if kind == 'error':
            self.root.bell()

    def clear_notices(self):
        for notice in self.notices:
            notice.destroy()
        self.notices = []
        if self.notice_area.winfo_manager():
            self.notice_area.pack_forget()

    def show_status_bar(self, shown=None):
        """The step of a long job (generation, download) and a moving bar; hidden otherwise.
        On New seed the action bar shows the step instead."""
        working = self.busy or self.updating == 'install'
        visible = working and not (self.busy and self.current_page == 'newseed')
        if visible and not self.status_bar.winfo_manager():
            self.status_bar.pack(side='bottom', fill='x', pady=(12, 0), padx=(0, PAGE_GUTTER), before=self.tabs)
            self.progress.pack(side='right', padx=(12, 0))
            self.progress.start()
        elif not visible and self.status_bar.winfo_manager():
            self.progress.stop()
            self.progress.pack_forget()
            self.status_bar.pack_forget()
        self.update_action_bar()


    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.notify('Copied to the clipboard.')


    def path_row(self, parent, text, variable, kind):
        """A labelled path field; returns the label under it that says what was recognised."""
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=(0, 12))
        ttk.Label(frame, text=text, style='Field.TLabel').pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(5, 0))
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        def choose():
            current = variable.get().strip()
            value = (
                filedialog.askopenfilename(
                    title='Choose Game File (.nup)',
                    initialdir=current,
                    filetypes=[('NUP game', '*.nup')],
                    parent=self.root,
                )
                if kind == 'file'
                else filedialog.askdirectory(
                    title='Choose Folder',
                    initialdir=current,
                    parent=self.root,
                )
            )
            if value:
                if kind == 'directory' and variable is self.mods:
                    value = self.normalize_chosen_mods_dir(value)
                if value:
                    variable.set(value)
        ttk.Button(row, text='Browse…', command=choose).pack(side='right', padx=(8, 0))
        check = ttk.Label(frame, style='Small.TLabel', wraplength=760, justify='left')
        check.pack(anchor='w', pady=(5, 0))
        return check


    def build_setup(self):
        parent = self.setup_body
        box = self.card(parent, 'Game files', 'Seeds are generated straight into the mods folder. The original files stay in place.')
        self.nup_check = self.path_row(box, 'GAME FILE (.NUP)', self.nup, 'file')
        self.mods_check = self.path_row(box, 'MODS FOLDER', self.mods, 'directory')
        for variable in (self.nup, self.mods):
            variable.trace_add('write', lambda *args: self.check_paths())
        self.check_paths()
        advanced = ttk.Frame(box)
        self.advanced_label = tk.StringVar(value='Advanced  ▸')
        ttk.Button(box, textvariable=self.advanced_label, style='Link.TButton',
                   command=lambda: self.toggle_advanced(advanced)).pack(anchor='w')
        ttk.Label(advanced, text='OTHER EMULATOR EXECUTABLES (OPTIONAL)', style='Field.TLabel').pack(anchor='w', pady=(8, 0))
        row = self.buttons(advanced, pady=(5, 4))
        entry = ttk.Entry(row, textvariable=self.extra_emulators)
        entry.pack(side='left', fill='x', expand=True)
        for event in ('<FocusOut>', '<Return>'):
            entry.bind(event, lambda e: self.save_extra_emulators())
        ttk.Label(advanced, text='Live tracking finds Hookshot, Longshot, Lichii, Ryuchii, Eden, yuzu, suyu, citron and sudachi. '
                  'Another yuzu-based emulator? Add its executable name here (comma-separated; on Linux, with or without .exe).',
                  style='Small.TLabel', wraplength=760).pack(anchor='w')
        self.build_qol_card(parent)
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
        ttk.Label(box, textvariable=self.connection_status, style='Small.TLabel', wraplength=760).pack(anchor='w')
        ttk.Label(box, textvariable=self.turbo_status, style='Small.TLabel').pack(anchor='w')
        box = self.card(parent, 'My Games', 'Optional. When on, every generated seed is kept with its own save in a '
                        'named game that you can switch between. When off, seeds are installed directly in the '
                        'mods folder.')
        ttk.Checkbutton(box, text='Keep each adventure with its save (adds My Games to the menu)',
                        variable=self.parties_enabled, command=self.toggle_parties).pack(anchor='w')
        box = self.card(parent, 'Updates', f'Installed version: {APP_VERSION}'
                        + (' (experimental)' if updater.is_prerelease(APP_VERSION) else '')
                        + f' · generator {GENERATOR_VERSION}.')
        row = self.buttons(box, pady=(0, 6))
        ttk.Button(row, text='Check now', command=lambda: self.check_for_updates(silent=False)).pack(side='left')
        ttk.Checkbutton(row, text='Check at start-up', variable=self.check_updates).pack(side='left', padx=(16, 0))
        ttk.Checkbutton(box, text='Use experimental versions (pre-releases)', variable=self.experimental_updates,
                        command=self.experimental_toggled).pack(anchor='w')
        ttk.Label(box, text='Experimental versions get new features first, but may contain bugs or break a seed in progress. '
                  'Untick to go back to the latest stable version: it is offered for download, then the application restarts.',
                  style='Small.TLabel', wraplength=760).pack(anchor='w', pady=(4, 0))

    def toggle_advanced(self, frame):
        if frame.winfo_manager():
            frame.pack_forget()
            self.advanced_label.set('Advanced  ▸')
        else:
            frame.pack(fill='x')
            self.advanced_label.set('Advanced  ▾')

    def check_paths(self):
        """Say under each path what was recognised, or what to choose instead."""
        if not hasattr(self, 'nup_check'):
            return
        nup = self.nup.get().strip()
        if not nup:
            ok, text = False, 'Choose your game file (.nup).'
        elif not Path(nup).is_file():
            ok, text = False, 'No file at this path. Choose the .nup file of the game.'
        elif Path(nup).suffix.lower() != '.nup':
            ok, text = False, 'This is not a .nup file. Choose the .nup file of the game.'
        else:
            size = Path(nup).stat().st_size / 1e9
            ok, text = True, f'Game file found ({size:.1f} GB).'
        self.nup_check.configure(text=('\u2713 ' if ok else '\u2715 ') + text, style='Ok.TLabel' if ok else 'Bad.TLabel')
        mods = self.mods.get().strip()
        where = ('PC port: the mods folder next to the game exe (Hookshot, Longshot…). Emulator: the title '
                 f'folder {TITLE} in its load folder.')
        if not mods:
            ok, text = False, 'Choose where seeds go. ' + where
        else:
            try:
                folder = validate_mod_directory(mods)
                ok = True
                text = (f'PC port: {folder.parent.name}/mods. Each seed gets its own sub-folder.'
                        if folder.name.lower() == 'mods' else f'Emulator title folder ({TITLE}).')
                if not folder.exists():
                    text += ' The folder is created at the first installation.'
            except ValueError:
                ok, text = False, 'Not a mods folder. ' + where
        self.mods_check.configure(text=('\u2713 ' if ok else '\u2715 ') + text, style='Ok.TLabel' if ok else 'Bad.TLabel')


    def experimental_toggled(self):
        enabled = self.experimental_updates.get()
        self.write_app_state(experimental_updates=enabled)
        if enabled or updater.leaving_prereleases(enabled, APP_VERSION):
            self.check_for_updates(silent=False)

    def build_qol_card(self, parent):
        box = self.card(parent, 'Quality of life only', 'No randomization: only the options below, in their own folder (OoT_QoL).')
        ttk.Checkbutton(box, text='Skip the introduction cutscene', variable=self.qol_options['intro_skip']).pack(anchor='w')
        ttk.Checkbutton(box, text='Chests (big and small) without cutscene', variable=self.qol_options['fast_chests']).pack(anchor='w')
        row = self.buttons(box, pady=(8, 0))
        self.qol_button = ttk.Button(row, text='Install quality of life only', command=self.install_qol_only)
        self.qol_button.pack(side='right')
        ttk.Label(row, text='Close the game first. A randomizer seed in the same folder turns it off.',
                  style='Muted.TLabel').pack(side='right', padx=(0, 16))

    def install_qol_only(self):
        try:
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            mods = validate_mod_directory(self.mods.get())
            options = {name: variable.get() for name, variable in self.qol_options.items()}
            if not any(options.values()):
                raise ValueError('Tick at least one quality-of-life option.')
            self.run_job(lambda progress: install_qol(nup, mods, progress=progress, **options), self.qol_installed)
        except Exception as error:
            self.error(error)

    def qol_installed(self, result):
        if result.warnings:
            self.show_notice('warn', 'Quality of life installed in ' + str(result.folder), '\n\n'.join(result.warnings))
        else:
            self.notify('Quality of life installed in ' + str(result.folder) + '.')

    def build_home(self):
        parent = self.home_body
        self.home_seed, self.home_progress, self.home_available = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.home_hash = tk.StringVar()
        hero = ttk.Frame(parent, style='Hero.TFrame', padding=(28, 24, 28, 24))
        hero.pack(fill='x', pady=(0, 6))
        ttk.Label(hero, text='CURRENT ADVENTURE', style='HeroField.TLabel').pack(anchor='w')
        ttk.Label(hero, textvariable=self.home_seed, style='HeroTitle.TLabel', wraplength=650).pack(anchor='w', pady=(4, 0))
        self.home_hash_label = ttk.Label(hero, textvariable=self.home_hash, style='HeroHash.TLabel')
        self.home_hash_label.pack(anchor='w', pady=(2, 0))
        ttk.Frame(hero, style='HeroIn.TFrame', height=12).pack(fill='x')
        # Regeneration offered by an older seed: why, and what it changes.
        self.home_regen = ttk.Frame(hero, style='HeroNotice.TFrame', padding=(14, 10, 14, 10))
        self.home_regen_text = tk.StringVar()
        ttk.Label(self.home_regen, text='A newer version of this seed can be made', style='HeroNotice.TLabel',
                  font=self.fonts.strong).pack(anchor='w')
        ttk.Label(self.home_regen, textvariable=self.home_regen_text, style='HeroNoticeMuted.TLabel',
                  wraplength=640, justify='left').pack(anchor='w', pady=(2, 8))
        row = ttk.Frame(self.home_regen, style='HeroNotice.TFrame')
        row.pack(anchor='w')
        ttk.Button(row, text='Regenerate', style='HeroNotice.Accent.TButton', command=self.regenerate).pack(side='left')
        ttk.Button(row, text='Not now', style='HeroNotice.TButton', command=self.dismiss_regeneration).pack(side='left', padx=(8, 0))
        self.home_bar = ttk.Progressbar(hero, style='Hero.Horizontal.TProgressbar', maximum=1, value=0)
        self.home_bar.pack(fill='x')
        self.home_hint = ttk.Label(hero, style='HeroMuted.TLabel', wraplength=650, justify='left')
        row = self.home_row = ttk.Frame(hero, style='HeroIn.TFrame')
        row.pack(fill='x', pady=(14, 0))
        ttk.Label(row, textvariable=self.home_progress, style='Hero.TLabel').pack(side='left')
        ttk.Label(row, textvariable=self.home_available, style='HeroMuted.TLabel').pack(side='left', padx=(8, 0))
        self.home_primary = ttk.Button(row, style='Hero.Accent.TButton')
        self.home_primary.pack(side='right')
        self.home_secondary = ttk.Button(row, style='Hero.TButton')
        self.home_secondary.pack(side='right', padx=(0, 10))
        links = ttk.Frame(parent, style='Page.TFrame')
        links.pack(fill='x', pady=(0, 12))
        # The spoiler is not offered here: one click too close to the adventure.
        for text, command in [('Open a seed…', self.open_artifact), ('Open the folder', self.open_folder)]:
            ttk.Button(links, text=text, style='Page.Link.TButton', command=command).pack(side='left', padx=(4, 14))
        ttk.Button(links, text='Need help?  ›', style='Page.Link.TButton',
                   command=lambda: self.show_page('help')).pack(side='right', padx=(14, 4))
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
            detail = ttk.Label(box, style='Small.TLabel', wraplength=190, justify='left')
            detail.pack(anchor='w', pady=(3, 0))
            self.home_tiles[key] = {'dot': dot, 'value': value, 'detail': detail,
                                    'fix': ttk.Button(box, text='Fix ›', style='Link.TButton')}
        box = self.home_reach = self.card(parent)
        row = self.buttons(box, pady=(0, 6))
        ttk.Label(row, text='Available now', style='Heading.TLabel').pack(side='left')
        self.home_see_all = ttk.Button(row, text='See all ›', style='Link.TButton',
                                       command=lambda: (self.set_tracker_filter('available'), self.show_page('tracker')))
        self.home_see_all.pack(side='right')
        self.home_list = ttk.Frame(box)
        self.home_list.pack(fill='x')
        self.render_home_list({})


    def set_tile(self, key, state, text, fix=None, detail=''):
        tile = self.home_tiles[key]
        tile['dot'].configure(image=self.images['dot_' + state])
        tile['value'].configure(text=text, foreground=self.colors['amber_text'] if state == 'warn' else self.colors['text'])
        tile['detail'].configure(text=detail)
        if fix:
            tile['fix'].configure(command=fix)
            if not tile['fix'].winfo_manager():
                tile['fix'].pack(anchor='w', pady=(4, 0))
        else:
            tile['fix'].pack_forget()


    def adventure_name(self):
        """(name, hash) of the open adventure: the party name, or the seed name the player chose;
        a random seed name is shown as its date, with the name itself as the hash."""
        if self.party_context:
            return self.party_context['name'], self.seed_name if RANDOM_SEED.fullmatch(self.seed_name) else ''
        if not self.artifact:
            return '', ''
        if RANDOM_SEED.fullmatch(self.seed_name):
            try:
                made = datetime.fromtimestamp((self.artifact / 'manifest.json').stat().st_mtime)
                name = f'Game of {made.day} {made:%b}'
            except OSError:
                name = 'Seed'
            return name, self.seed_name
        return self.seed_name, ''

    @staticmethod
    def grouped(seed_hash):
        return ' '.join(seed_hash[i:i + 4] for i in range(0, len(seed_hash), 4))

    def update_adventure(self):
        name, seed_hash = self.adventure_name()
        if name:
            self.sidebar.set_adventure('Current adventure', name, self.grouped(seed_hash),
                                       action=lambda: self.show_page('home'))
        else:
            self.sidebar.set_adventure('No adventure yet', 'Create a seed to start',
                                       action=lambda: self.show_page('newseed'))

    def save_tile(self):
        """(state, value, detail, fix) of the Save tile: the same verdict as the tracker."""
        path = Path(self.save_path.get()) if self.save_path.get() else None
        found = bool(path) and path.is_file()
        detail = ''
        if found:
            try:
                stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime('%H:%M')
                detail = f'{path.parent.name} · saved at {stamp}'
            except OSError:
                pass
        if not found:
            return 'warn', 'Not found', 'Start a game and save once.', lambda: self.show_page('setup')
        link = self.tracker.link if self.tracker else None
        if link == 'other':
            return 'warn', 'Other seed', detail, lambda: self.show_page('tracker')
        if link == 'linked':
            return 'ok', 'Linked', detail, None
        return 'off', 'Found', detail, None

    def update_home(self):
        """Home shows the state of the adventure; only problems ask for an action."""
        if not hasattr(self, 'home_tiles'):
            return
        counts = self.tracker_counts if self.tracker else None
        name, seed_hash = self.adventure_name()
        self.home_seed.set(name or 'No adventure yet')
        self.home_hash.set(('Seed ' + self.grouped(seed_hash)) if seed_hash else '')
        self.update_adventure()
        other_save = bool(self.tracker) and self.tracker.link != 'linked'
        if counts and not other_save:
            self.home_bar.configure(maximum=max(counts['total'], 1), value=counts['done'])
            self.home_progress.set(f'{counts["done"]} / {counts["total"]} found')
            self.home_available.set(f'·  {counts["available"]} available now')
        else:
            self.home_bar.configure(maximum=1, value=0)
            self.home_progress.set('Seed installed' if self.artifact else 'Create a seed to start playing.')
            self.home_available.set('')
        # Until a save of this seed is read, the bar would say 0 %: say what to do instead.
        if other_save:
            self.home_hint.configure(text='Start a new game with this seed, then save once: the tracker links '
                                     'itself to that save.' if self.tracker.link == 'other' else
                                     'No save of this seed yet. Start a new game, then save once.')
            if self.home_bar.winfo_manager():
                self.home_bar.pack_forget()
            if not self.home_hint.winfo_manager():
                self.home_hint.pack(anchor='w', before=self.home_row)
        else:
            self.home_hint.pack_forget()
            if not self.home_bar.winfo_manager():
                self.home_bar.pack(fill='x', before=self.home_row)
        if self.artifact:
            self.home_primary.configure(text='Continue', command=lambda: self.show_page('tracker'))
            self.home_secondary.configure(text='New seed', command=lambda: self.show_page('newseed'))
        else:
            self.regen_settings = None
            self.home_primary.configure(text='Create a seed', command=lambda: self.show_page('newseed'))
            self.home_secondary.configure(text='Open a seed…', command=self.open_artifact)
        manifest = self.artifact_manifest or {}
        dismissed = manifest.get('seed_id') and self.app_state.get('regen_dismissed') == manifest.get('seed_id')
        if self.regen_settings is not None and not dismissed:
            made_by = manifest.get('app_version')
            self.home_regen_text.set(
                f'This seed was made by version {made_by or "older than 0.7.3"}; this is {APP_VERSION}. '
                'Regenerating applies the fixes made since, with the same name and settings. Items may be '
                'placed differently, so a new game may be needed'
                + ('; the original game stays in My Games.' if self.party_context else '.'))
            if not self.home_regen.winfo_manager():
                self.home_regen.pack(fill='x', pady=(0, 14), before=self.home_bar if self.home_bar.winfo_manager()
                                     else self.home_hint if self.home_hint.winfo_manager() else self.home_row)
        else:
            self.home_regen.pack_forget()
        setup = lambda: self.show_page('setup')
        if self.nup.get() and Path(self.nup.get()).is_file():
            self.set_tile('game', 'ok', 'Found')
        else:
            self.set_tile('game', 'warn', 'Missing', setup)
        if self.mods.get() and Path(self.mods.get()).is_dir():
            self.set_tile('mods', 'ok', 'PC port' if self.hookshot_root() else 'Emulator')
        else:
            self.set_tile('mods', 'warn', 'Missing', setup)
        state, value, detail, fix = self.save_tile()
        self.set_tile('save', state, value, fix, detail)
        if self.tracker and self.tracker.live and not self.tracker.live_status:
            self.set_tile('live', 'ok', 'On')
        else:
            self.set_tile('live', 'off', 'Game not running' if self.tracker else 'Waiting for a seed')
        if hasattr(self, 'sync_dot'):
            linked = bool(self.tracker) and self.tracker.link == 'linked'
            self.sync_dot.configure(image=self.images['dot_ok' if linked else 'dot_warn' if self.tracker else 'dot_off'])
        # Without a seed the list could only say "create a seed": the hero already does.
        if self.artifact and not self.home_reach.winfo_manager():
            self.home_reach.pack(fill='x', pady=(0, 14))
        elif not self.artifact:
            self.home_reach.pack_forget()
            self.home_body.canvas.yview_moveto(0)
        self.update_tutorial()
        if self.pages['home'][1] != ('Welcome back' if self.artifact else 'Welcome'):
            frame, _, subtitle = self.pages['home']
            self.pages['home'] = (frame, 'Welcome back' if self.artifact else 'Welcome', subtitle)
            self.page_changed()

    def dismiss_regeneration(self):
        self.write_app_state(regen_dismissed=(self.artifact_manifest or {}).get('seed_id'))
        self.update_home()


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
        box = ttk.Frame(parent, style='Card.TFrame', padding=(20, 12, 20, 12))
        box.pack(fill='x', pady=(0, 14))
        row = self.buttons(box)
        ttk.Label(row, text='SEED NAME', style='Field.TLabel').pack(side='left', padx=(0, 12))
        ttk.Entry(row, textvariable=self.seed).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Random', command=lambda: self.seed.set(secrets.token_hex(8))).pack(side='left', padx=(8, 0))
        ttk.Button(row, text='Paste a seed string…', command=self.import_seed_string).pack(side='left', padx=(8, 0))


    def build_action_bar(self):
        """New seed: the adventure, its changes and Generate, always in view under the settings."""
        bar = self.action_bar = ttk.Frame(self.settings_tab, style='Card.TFrame', padding=(22, 12, 22, 12))
        bar.pack(side='bottom', fill='x', padx=(0, PAGE_GUTTER), pady=(10, 0))
        left = ttk.Frame(bar)
        left.pack(side='left', fill='x', expand=True)
        top = ttk.Frame(left)
        top.pack(anchor='w')
        self.action_preset = ttk.Label(top, style='Value.TLabel')
        self.action_preset.pack(side='left')
        self.action_changes = ttk.Label(top, style='Changed.TLabel')
        self.action_reset = ttk.Button(top, style='Link.TButton', command=self.reset_to_preset)
        self.action_note = ttk.Label(left, style='Small.TLabel', wraplength=360, justify='left')
        self.action_note.pack(anchor='w', pady=(2, 0))
        self.action_progress = ttk.Progressbar(left, mode='indeterminate', length=280)
        self.generate_button = ttk.Button(bar, text='Generate and install', style='Accent.TButton', command=self.generate)
        self.generate_button.pack(side='right')
        ttk.Button(bar, text='Copy seed string', command=self.copy_seed_string).pack(side='right', padx=(0, 8))
        self.log = tk.Text(bar, height=5, wrap='word', state='disabled', padx=12, pady=10)   # job steps, kept off screen
        self.status.trace_add('write', lambda *args: self.update_action_bar())
        self.seed.trace_add('write', lambda *args: self.update_action_bar())

    def update_action_bar(self):
        if not hasattr(self, 'action_bar') or not hasattr(self, 'setting_rows'):
            return
        names = dict((key, title) for key, title, _ in self.PRESET_CARDS)
        base = names.get(self.base_preset, 'Custom')
        changed = sum(self.changed_count.values()) if hasattr(self, 'changed_count') else 0
        self.action_preset.configure(text=base)
        if changed:
            self.action_changes.configure(text=f'+ {changed} change' + ('s' if changed > 1 else ''))
            self.action_reset.configure(text=f'Reset to {base}')
            if not self.action_changes.winfo_manager():
                self.action_changes.pack(side='left', padx=(8, 0))
                self.action_reset.pack(side='left', padx=(8, 0))
        else:
            self.action_changes.pack_forget()
            self.action_reset.pack_forget()
        if self.busy and self.current_page == 'newseed':
            self.action_note.configure(text=self.status.get())
            if not self.action_progress.winfo_manager():
                self.action_progress.pack(anchor='w', pady=(4, 0))
                self.action_progress.start()
            self.generate_button.configure(text='Generating…')
        else:
            seed = self.seed.get().strip() or '?'
            self.action_note.configure(text=f'Seed {seed} · Close the game first; the previous seed is archived.')
            if self.action_progress.winfo_manager():
                self.action_progress.stop()
                self.action_progress.pack_forget()
            self.generate_button.configure(text='Generate and install')


    PRESET_CARDS = [('prudent', 'Chests only', 'A gentle first run: chests are shuffled, keys and enemies stay as usual.'),
                    ('ap_defaults', 'Classic', 'The standard Archipelago rules. The recommended balance.'),
                    ('everything', 'Everything', 'Shops, songs, pots, crates, grass, rocks and enemy souls join in.')]

    def build_categories(self):
        parent = self.settings_body
        self.full_enabled = tk.BooleanVar(value=True)
        self.full_vars, self.category_controls = {}, {}
        self.base_preset = 'ap_defaults'   # the preset the "changed" marks compare with
        self.setting_rows, self.setting_cards, self.setting_nav = {}, {}, {}
        self.help_rows, self.changed_count = {}, {}
        self.setting_query = tk.StringVar()
        self.setting_group = None
        # Presets: a radio group (Tab to reach it, arrows to move, Enter or Space to choose).
        grid = ttk.Frame(parent, style='Page.TFrame')
        grid.pack(fill='x', pady=(0, 14))
        self.preset_cards = {}
        keys = [key for key, _, _ in self.PRESET_CARDS]
        for column, (key, name, text) in enumerate(self.PRESET_CARDS):
            grid.columnconfigure(column, weight=1, uniform='presets')
            ring = tk.Frame(grid, background=self.colors['page'], highlightthickness=2, takefocus=1,
                            highlightbackground=self.colors['page'], highlightcolor=self.colors['gold'])
            ring.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 4, 0 if column == 2 else 4))
            box = ttk.Frame(ring, style='Card.TFrame', padding=(16, 14, 16, 14), cursor='hand2')
            box.pack(fill='both', expand=True)
            art = tk.Canvas(box, width=150, height=58, highlightthickness=0, background=self.colors['green_soft'])
            art.pack(fill='x')
            art.bind('<Configure>', lambda event, a=art, k=key: theme.preset_art(a, k, self.colors))
            widgets = [ring, box, art, ttk.Label(box, text=name, style='Preset.TLabel'),
                       ttk.Label(box, text=text, style='Small.TLabel', wraplength=200, justify='left')]
            widgets[3].pack(anchor='w', pady=(8, 2))
            widgets[4].pack(anchor='w')
            for widget in widgets:
                widget.bind('<Button-1>', lambda event, k=key: self.choose_preset(k))
            for sequence in ('<Return>', '<space>'):
                ring.bind(sequence, lambda event, k=key: self.choose_preset(k))
            for sequence, step in (('<Left>', -1), ('<Right>', 1), ('<Up>', -1), ('<Down>', 1)):
                ring.bind(sequence, lambda event, i=column, s=step: self.preset_cards[keys[(i + s) % len(keys)]][2].focus_set())
            self.preset_cards[key] = (box, art, ring)
        self.build_seed_row(parent)
        visible = {}
        for option in rando_options.OPTIONS:
            if option.kind in ('items', 'list'):
                supported = [None, None]  # free text: always shown
            elif option.kind == 'bool':
                supported = [v for v in (False, True) if option.supported(v)]
            elif option.kind == 'int':
                supported = list(option.supported_ints)
            else:
                supported = [v for v, label, reason in option.values if reason is None]
            if len(supported) > 1 and option.name not in HIDDEN_OPTIONS:
                visible[option.name] = option
            else:
                self.option_row(None, 0, option)
        placed = {name for _, _, names in SETTING_GROUPS for name in names}
        groups = [(title, note, [n for n in names if n.startswith('game:') or n in visible])
                  for title, note, names in SETTING_GROUPS]
        leftovers = {}
        for name, option in visible.items():   # options added later and not placed yet
            if name not in placed:
                leftovers.setdefault(option.tab, []).append(name)
        groups += [(tab, '', names) for tab, names in leftovers.items()]
        groups = [group for group in groups if group[2]]
        # The groups are tabs on the left: one group shown at a time, the first one at first.
        area = ttk.Frame(parent, style='Page.TFrame')
        area.pack(fill='x')
        nav = ttk.Frame(area, style='Page.TFrame')
        nav.pack(side='left', fill='y', anchor='n', padx=(0, 14))
        self.setting_search = theme.search_entry(nav, self.setting_query, 'Find a setting   /', width=22)
        self.setting_search.pack(fill='x', pady=(0, 8))
        content = ttk.Frame(area, style='Page.TFrame')
        content.pack(side='left', fill='both', expand=True)
        def tab(title):
            item = ttk.Frame(nav, style='Tab.TFrame', padding=(10, 6, 10, 6), cursor='hand2', takefocus=1)
            item.pack(fill='x', pady=(0, 3))
            label = ttk.Label(item, text=title, style='Tab.TLabel')
            label.pack(side='left')
            count = ttk.Label(item, style='TabBadge.TLabel')
            count.pack(side='right', padx=(8, 0))
            for widget in (item, label, count):
                widget.bind('<Button-1>', lambda event, t=title: self.show_setting_group(t))
            for sequence in ('<Return>', '<space>'):
                item.bind(sequence, lambda event, t=title: self.show_setting_group(t))
            item.bind('<Up>', lambda event, t=title: self.step_setting_group(t, -1))
            item.bind('<Down>', lambda event, t=title: self.step_setting_group(t, 1))
            self.setting_nav[title] = (item, label, count)
        for title, note, names in groups:
            tab(title)
            frame = self.card(content, title, note or None)
            frame.pack_forget()
            self.setting_cards[title] = frame
            rows = ttk.Frame(frame)
            rows.pack(fill='x')
            rows.columnconfigure(0, weight=1)
            self.setting_group = title
            for index, name in enumerate(names):
                if name.startswith('game:'):
                    key = name[len('game:'):]
                    text = GAME_OPTION_COPY[key]
                    self.switch_row(rows, index, text, self.options[key], tip=text + '\n' + OPTION_TIPS[key])
                else:
                    self.option_row(rows, index, visible[name])
        ttk.Frame(nav, style='Page.TFrame', height=1).pack(fill='x', pady=6)
        title = 'Quality of life'
        tab(title)
        box = self.setting_cards[title] = self.card(content, title, 'Choose each option for your game. Turbo A applies to this app.')
        box.pack_forget()
        rows = ttk.Frame(box)
        rows.pack(fill='x')
        rows.columnconfigure(0, weight=1)
        self.setting_group = title
        for index, (name, text) in enumerate(SKIP_OPTIONS):
            self.switch_row(rows, index, text, self.options[name],
                            tip=text + '\nApplies when you generate a game. Turn off to keep the original behaviour.')
        self.switch_row(rows, len(SKIP_OPTIONS), 'Turbo A: hold A in a dialogue', self.turbo_enabled,
                        command=self.turbo_toggled,
                        tip='Turbo A\nPC port: repeat A while held in a dialogue. Remembered between app starts; takes effect immediately.')
        title = 'Share these settings'
        tab(title)
        box = self.setting_cards[title] = self.card(content, title, 'A file of these settings, or an Archipelago YAML.')
        box.pack_forget()
        row = self.buttons(box)
        ttk.Button(row, text='Import…', command=self.import_settings).pack(side='left')
        ttk.Button(row, text='Export…', command=self.export_settings).pack(side='left', padx=8)
        ttk.Button(row, text='Export an Archipelago YAML…', style='Link.TButton', command=self.export_ap_yaml).pack(side='right')
        ttk.Button(row, text='Import an Archipelago YAML…', style='Link.TButton', command=self.import_ap_yaml).pack(side='right', padx=14)
        self.setting_group = None
        self.setting_query.trace_add('write', lambda *args: self.show_setting_group())
        self.root.bind_all('<Key-slash>', self.focus_setting_search, add='+')
        for name in {o for opts in rando_options.CATEGORY_OPTIONS.values() for o, _, _ in opts}:
            self.full_vars[name].trace_add('write', lambda *args: self.sync_categories())
        self.show_setting_group(groups[0][0])
        self.apply_full(rando_options.preset('ap_defaults'), enable=True)

    def focus_setting_search(self, event):
        """/ jumps to the setting search, unless a field is being typed in."""
        if self.current_page != 'newseed' or isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Spinbox)):
            return None
        self.setting_search.focus_set()
        return 'break'

    def step_setting_group(self, title, step):
        titles = list(self.setting_nav)
        target = titles[(titles.index(title) + step) % len(titles)]
        self.show_setting_group(target)
        self.setting_nav[target][0].focus_set()
        return 'break'

    def show_setting_group(self, title=None):
        """One group at a time; while searching, the matching settings of every group."""
        if title is not None:
            self.setting_group = title
            if self.setting_query.get():
                self.setting_query.set('')   # calls back here
                return
        query = self.setting_query.get().strip().casefold()
        hits = {}
        for name, record in self.setting_rows.items():
            match = not query or query in record['search']
            if match:
                hits[record['group']] = hits.get(record['group'], 0) + 1
            # grid_remove() keeps each widget's place; removed ones are no longer grid slaves.
            if match:
                for widget in record.pop('removed', ()):
                    if widget.winfo_exists():
                        widget.grid()
            elif 'removed' not in record:
                record['removed'] = (record['parent'].grid_slaves(row=record['row'])
                                     + record['parent'].grid_slaves(row=record['row'] + 1))
                for widget in record['removed']:
                    widget.grid_remove()
        for group, card in self.setting_cards.items():
            shown = (bool(hits.get(group)) or query in group.casefold()) if query else group == self.setting_group
            if shown and not card.winfo_manager():
                card.pack(fill='x', pady=(0, 14))
            elif not shown and card.winfo_manager():
                card.pack_forget()
        # Keep the cards in the order of the tabs.
        for group, card in self.setting_cards.items():
            if card.winfo_manager():
                card.pack_forget()
                card.pack(fill='x', pady=(0, 14))
        for group, (item, label, count) in self.setting_nav.items():
            on = not query and group == self.setting_group
            prefix = 'TabOn' if on else 'Tab'
            item.configure(style=prefix + '.TFrame')
            label.configure(style=prefix + '.TLabel')
            if query:
                count.configure(text=str(hits.get(group, '')), style=prefix + 'Hit.TLabel')
            else:
                changed = self.changed_count.get(group, 0)
                count.configure(text=f'{changed} changed' if changed else '', style=prefix + 'Badge.TLabel')

    def choose_preset(self, key):
        self.base_preset = key
        self.apply_full(rando_options.preset(key), enable=True)

    def reset_to_preset(self):
        self.apply_full(rando_options.preset(self.base_preset), enable=True)

    def set_full_value(self, name, value):
        option, variable = rando_options.BY_NAME[name], self.full_vars[name]
        variable.set(value)
        if option.kind == 'choice':
            variable.display.set(variable.labels[[v for v, _, _ in option.values].index(value)])

    def reset_option(self, name):
        self.set_full_value(name, rando_options.validate(rando_options.preset(self.base_preset))[name])
        self.update_presets()

    def update_changes(self):
        """Mark each setting that differs from the chosen preset, and count them per group."""
        if not hasattr(self, 'setting_rows'):
            return
        base = rando_options.validate(rando_options.preset(self.base_preset))
        counts = {}
        for name, record in self.setting_rows.items():
            if name not in base or name == 'fast_chests':
                continue
            try:
                changed = self.full_value(rando_options.BY_NAME[name]) != base[name]
            except Exception:
                changed = True
            marks = record['marks'][0]
            marks.shown = changed
            if changed:
                counts[record['group']] = counts.get(record['group'], 0) + 1
            elif marks.winfo_manager():
                marks.pack_forget()
        self.changed_count = counts
        for parent in {record['parent'] for record in self.setting_rows.values()}:
            self.fit_labels(parent, parent.winfo_width())
        if self.setting_cards:
            self.show_setting_group()
        self.update_action_bar()


    def toggle_details(self):
        """Kept for older scripts: the settings are always shown now, one group at a time."""


    def update_presets(self):
        """Highlights the preset matching the current settings, if any."""
        if not hasattr(self, 'preset_cards') or len(self.full_vars) != len(rando_options.OPTIONS):
            return
        try:
            values = rando_options.validate(self.full_values())
        except Exception:
            return
        current = next((key for key in self.preset_cards
                        if dict(rando_options.validate(rando_options.preset(key)),
                                fast_chests=values['fast_chests']) == values), None)
        self.current_preset = current
        if current:
            self.base_preset = current
        for key, (box, art, ring) in self.preset_cards.items():
            box.configure(style='CardSelected.TFrame' if key == self.base_preset else 'Card.TFrame')
            art.configure(background=self.colors['gold_soft' if key == self.base_preset else 'green_soft'])
        self.update_changes()
        self.update_archipelago_controls()

    def label_cell(self, parent, index, text, tip=None, wraplength=460, cursor=''):
        """Column 0 of a settings row: the label, an ⓘ button that unfolds ``tip`` under the row
        (click, Enter or Space; hovering still shows it), then the "changed" mark and its ↺."""
        row = index * 2
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=0, sticky='w', padx=(0, 18), pady=7)
        line = ttk.Frame(cell)
        line.pack(anchor='w')
        label = ttk.Label(line, text=text, wraplength=wraplength, justify='left', cursor=cursor)
        label.pack(side='left')
        icon = None
        if tip:
            icon = theme.info_icon(line, self.fonts, background=self.colors['surface'])
            icon.configure(takefocus=1, cursor='hand2', highlightthickness=1, highlightcolor=self.colors['gold'],
                           highlightbackground=self.colors['surface'])
            icon.pack(side='left', padx=(4, 0))
            for sequence in ('<Button-1>', '<Return>', '<space>'):
                icon.bind(sequence, lambda event: self.toggle_help(parent, row, tip))
        # "changed" and its reset: on the label's line when there is room, else under it.
        marks = ttk.Frame(cell)
        marks.shown = False
        ttk.Label(marks, text='changed', style='Changed.TLabel').pack(side='left')
        reset = ttk.Button(marks, text='↺', width=2, style='Link.TButton')
        reset.pack(side='left', padx=(2, 0))
        if parent is not None:
            # The label wraps in the room the control leaves: nothing is cut at 1040 px.
            if not hasattr(parent, 'fit_rows'):
                parent.fit_rows = []
                parent.bind('<Configure>', lambda event: self.fit_labels(parent, event.width), add='+')
            parent.fit_rows.append((cell, line, label, marks))
        if parent is not None and getattr(self, 'setting_group', None):
            self.current_row = {'group': self.setting_group, 'parent': parent, 'row': row,
                                'search': (text + ' ' + (tip or '')).casefold(), 'marks': (marks, reset)}
        return label, icon

    def fit_labels(self, parent, width):
        if width <= 1:
            return   # not laid out yet: done again at its first <Configure>
        if not hasattr(self, 'label_font'):
            self.label_font = tkfont.Font(root=self.root, font=self.fonts.body)
        # The control column is as wide as its widest control, whatever the row.
        controls = max((w.winfo_reqwidth() for w in parent.grid_slaves(column=1)), default=0)
        space = width - controls - 40
        for cell, line, label, marks in parent.fit_rows:
            icon = sum(w.winfo_reqwidth() + 4 for w in line.winfo_children() if w is not label and w is not marks)
            needed = marks.winfo_reqwidth() + 8 if marks.shown else 0
            inline = self.label_font.measure(label.cget('text')) + icon + needed <= space
            label.configure(wraplength=max(120, min(460, space - icon - (needed if inline else 0))))
            if not marks.shown:
                if marks.winfo_manager():
                    marks.pack_forget()
                continue
            where = str(line if inline else cell)
            if marks.winfo_manager() and marks.pack_info().get('in') is not None and str(marks.pack_info()['in']) == where:
                continue
            marks.pack_forget()
            if inline:
                marks.pack(in_=line, side='left', padx=(8, 0))
            else:
                marks.pack(in_=cell, anchor='w', pady=(2, 0))

    def register_row(self, name):
        record = getattr(self, 'current_row', None)
        if record is not None:
            self.setting_rows[name] = record
            record['marks'][1].configure(command=lambda: self.reset_option(name))
            self.current_row = None

    def toggle_help(self, parent, row, tip):
        key = (str(parent), row)
        if key in self.help_rows:
            self.help_rows.pop(key).destroy()
            return 'break'
        body = tip.partition('\n')[2].strip() or tip
        help_label = ttk.Label(parent, text=body, style='Help.TLabel', wraplength=620, justify='left')
        help_label.grid(row=row + 1, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        self.help_rows[key] = help_label
        return 'break'


    def switch_row(self, parent, index, text, variable, command=None, tip=None):
        """Label on the left, switch on the right; clicking the label toggles too."""
        label, icon = self.label_cell(parent, index, text, tip, cursor='hand2')
        row = index * 2
        widget = ttk.Checkbutton(parent, variable=variable, command=command, style='Bare.TCheckbutton')
        widget.grid(row=row, column=1, sticky='e', pady=7)
        def click(event):
            if 'disabled' not in widget.state():
                widget.invoke()
                widget.focus_set()
        label.bind('<Button-1>', click)
        if tip:
            theme.Tooltip((label, widget), tip, self.fonts)
        if index:
            theme.rule(parent).grid(row=row, column=0, columnspan=2, sticky='new')
        self.register_row(f'switch:{str(parent)}:{row}')
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
        parent = ttk.Frame(self.tracker_tab, style='Page.TFrame', padding=(0, 0, PAGE_GUTTER, 0))
        parent.pack(fill='both', expand=True)
        bar = ttk.Frame(parent, style='Page.TFrame')
        bar.pack(fill='x', pady=(0, 10))
        self.sync_dot = ttk.Label(bar, style='Page.TLabel', image=self.images['dot_off'])
        self.sync_dot.pack(side='left', padx=(4, 8))
        ttk.Label(bar, textvariable=self.connection_status, style='Page.TLabel', wraplength=340, justify='left').pack(side='left')
        ttk.Button(bar, text='Change', style='Page.Link.TButton', command=lambda: self.show_page('setup')).pack(side='left', padx=(10, 0))
        ttk.Button(bar, text='Pop-out window', style='Page.Link.TButton', command=self.toggle_overlay).pack(side='right')
        ttk.Button(bar, text='In-game overlay', style='Page.Link.TButton', command=self.toggle_hud).pack(side='right', padx=14)
        box = self.card(parent, fill='both', expand=True)
        self.tracker_box = box
        # Why every location is Unknown, when the save is not one of this seed.
        self.tracker_notice, self.tracker_notice_key = ttk.Frame(box), None
        top = self.tracker_top = self.buttons(box, pady=(0, 10))
        self.tracker_view = 'locations'
        self.view_switch = theme.Segmented(top, [('locations', 'Locations'), ('keys', 'Keys'), ('souls', 'Souls')],
                                           self.set_tracker_view)
        self.view_switch.pack(side='left')
        theme.search_entry(top, self.tracker_search, 'Search a location, a reward…', width=28).pack(side='right')
        filters = self.tracker_filters = self.buttons(box, pady=(0, 12))
        self.counters = {}
        # The counters are the filters of the location list; each wears the mark of its rows.
        for key, label in [('available', 'Available'), ('blocked', 'Blocked'), ('unknown', 'Unknown'),
                           ('done', 'Done'), ('all', 'All')]:
            frame = ttk.Frame(filters, padding=(12, 7, 12, 8), cursor='hand2', takefocus=1)
            frame.pack(side='left', padx=(0, 6))
            count = ttk.Label(frame, text='–', width=5)
            count.pack(anchor='w')
            name = ttk.Label(frame, text=(' ' + label) if key != 'all' else label, compound='left',
                             image=self.images['state_' + key] if key != 'all' else '')
            name.pack(anchor='w')
            for widget in (frame, count, name):
                widget.bind('<Button-1>', lambda event, k=key: self.set_tracker_filter(k))
            for sequence in ('<Return>', '<space>'):
                frame.bind(sequence, lambda event, k=key: self.set_tracker_filter(k))
            self.counters[key] = (frame, count, name)
        self.tracker_views = ttk.Frame(box)
        self.tracker_views.pack(fill='both', expand=True)
        self.tracker_rows = ttk.Frame(self.tracker_views)
        self.tracker_rows.pack(fill='both', expand=True)
        self.keys_rows = ttk.Frame(self.tracker_views)
        self.souls_rows = ttk.Frame(self.tracker_views)
        self.keys_tree, self.keys_shown = None, None
        self.souls_tree, self.souls_open, self.souls_shown = None, {}, None
        footer = ttk.Frame(box)
        footer.pack(side='bottom', fill='x', before=self.tracker_views)
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
        """The counters above the list are its filter; Keys and Souls are views of their own."""
        if key in ('keys', 'souls'):
            self.set_tracker_view(key)
            return
        self.tracker_filter = key
        for name, (frame, count, label) in self.counters.items():
            prefix = 'TabOn' if name == key else 'Tab'
            frame.configure(style=prefix + '.TFrame')
            count.configure(style=prefix + 'Count.TLabel')
            label.configure(style=prefix + '.TLabel')
        self.set_tracker_view('locations')

    def set_tracker_view(self, view):
        self.tracker_view = view
        self.view_switch.set(view)
        if view == 'locations' and not self.tracker_filters.winfo_manager():
            self.tracker_filters.pack(fill='x', pady=(0, 12), before=self.tracker_views)
        elif view != 'locations' and self.tracker_filters.winfo_manager():
            self.tracker_filters.pack_forget()
        shown = {'keys': self.keys_rows, 'souls': self.souls_rows}.get(view, self.tracker_rows)
        for frame in (self.tracker_rows, self.keys_rows, self.souls_rows):
            if frame is not shown and frame.winfo_manager():
                frame.pack_forget()
        if not shown.winfo_manager():
            shown.pack(fill='both', expand=True)
        self.render_tracker()

    def update_tracker_notice(self):
        """A banner over the list while the save read is not one of this seed."""
        link = self.tracker.link if self.tracker else None
        key = 'other' if link == 'other' else 'none' if link == 'none' and not self.save_path.get() else None
        if key == self.tracker_notice_key:
            return
        self.tracker_notice_key = key
        for child in self.tracker_notice.winfo_children():
            child.destroy()
        if key is None:
            self.tracker_notice.pack_forget()
            return
        if key == 'other':
            title = 'This save belongs to another seed'
            text = ('Every location stays Unknown until the tracker reads a save of this seed. Start a new game '
                    'with this seed and save once, or pick the right save.')
        else:
            title = 'No save of this seed yet'
            text = 'Start a new game with this seed and save once: the tracker finds the save by itself.'
        theme.Notice(self.tracker_notice, 'warn', title, text,
                     [('Pick another save…', self.choose_save), ('Open Setup', lambda: self.show_page('setup'))],
                     on_close=lambda: self.tracker_notice.pack_forget(), wraplength=620).pack(fill='x')
        self.tracker_notice.pack(fill='x', pady=(0, 12), before=self.tracker_top)


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
        self.ap_export_info = ttk.Label(body, style='Small.TLabel', wraplength=640, justify='left')
        body = step('Add the patch the host sent back', 'The .aprmk file from the zip Archipelago produced. The seed is generated and installed right away.')
        self.ap_patch_button = ttk.Button(body, text='Choose the patch…', command=self.generate_from_patch)
        self.ap_patch_button.pack(anchor='w')
        body = step('Connect to the server', 'Checks you find in game are sent to the server.')
        # Locked until a seed of an Archipelago patch is open: only the reason is shown.
        self.ap_lock = ttk.Label(body, text='Locked until the seed of the patch is installed (step 2).',
                                 style='Muted.TLabel')
        connect = self.ap_connect = ttk.Frame(body)
        status = ttk.Frame(connect)
        status.pack(fill='x', pady=(0, 10))
        self.ap_dot = ttk.Label(status, image=self.images['dot_off'])
        self.ap_dot.pack(side='left', padx=(0, 8))
        ttk.Label(status, textvariable=self.ap_status, style='Value.TLabel', wraplength=600,
                  justify='left').pack(side='left', fill='x')
        row = self.buttons(connect)
        for label, variable, width, extra in [('SERVER', self.ap_address, 26, {}), ('SLOT', self.ap_slot, 16, {}),
                                              ('PASSWORD', self.ap_password, 12, {'show': '•'})]:
            field = ttk.Frame(row)
            field.pack(side='left', fill='x', expand=label == 'SERVER', padx=(0, 10))
            ttk.Label(field, text=label, style='Field.TLabel').pack(anchor='w')
            ttk.Entry(field, textvariable=variable, width=width, **extra).pack(fill='x', pady=(5, 0))
        self.ap_button = ttk.Button(row, text='Connect', style='Accent.TButton', command=self.toggle_archipelago)
        self.ap_button.pack(side='left', anchor='s')
        # The log and the chat only exist once connected.
        live = self.ap_live = ttk.Frame(connect)
        self.ap_log = tk.Text(live, height=8, wrap='word', state='disabled', padx=12, pady=10)
        self.ap_log.pack(fill='x', pady=(12, 0))
        row = self.buttons(live, pady=(8, 0))
        chat = ttk.Entry(row, textvariable=self.ap_chat)
        chat.pack(side='left', fill='x', expand=True)
        chat.bind('<Return>', lambda event: self.send_archipelago_chat())
        ttk.Button(row, text='Send', command=self.send_archipelago_chat).pack(side='left', padx=(8, 0))
        self.update_archipelago_controls()


    def multiworld_signature(self):
        """The settings a multiworld YAML carries: an export stays valid while they do not change."""
        import hashlib
        try:
            values = rando_options.validate(self.full_values())
        except Exception:
            return None
        text = json.dumps([values, self.options['open_forest'].get()], sort_keys=True, default=str)
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def update_archipelago_controls(self):
        if not hasattr(self, 'ap_steps'):
            return
        self.ap_button.state(['!disabled'] if self.ap_manifest or self.ap_client else ['disabled'])
        self.ap_button.configure(text='Disconnect' if self.ap_client else 'Connect')
        record = self.app_state.get('ap_yaml_export')
        record = record if isinstance(record, dict) else None
        exported = bool(record) and record.get('settings') == self.multiworld_signature()
        if record:
            self.ap_export_info.configure(
                text=f'\u2713 Exported for {record.get("player", "?")} · {record.get("preset", "")} · {record.get("date", "")}'
                if exported else f'Settings changed since the export of {record.get("date", "")}: export again.',
                style='Ok.TLabel' if exported else 'Small.TLabel')
        elif self.app_state.get('ap_yaml_exported'):
            # Exports made by older versions kept no record of their settings: they cannot be checked.
            self.ap_export_info.configure(text='A YAML was exported before this version, without a record of its '
                                          'settings: export again to keep track of them.', style='Small.TLabel')
        shown = bool(record or self.app_state.get('ap_yaml_exported'))
        if shown and not self.ap_export_info.winfo_manager():
            self.ap_export_info.pack(anchor='w', pady=(8, 0))
        elif not shown:
            self.ap_export_info.pack_forget()
        # The three steps: done ones are checked, the next one is highlighted.
        done = [exported or bool(self.ap_manifest), bool(self.ap_manifest), bool(self.ap_client)]
        current = next((index for index, value in enumerate(done) if not value), None)
        for index, (box, mark) in enumerate(self.ap_steps):
            mark.set('done' if done[index] else 'on' if index == current else 'off', str(index + 1))
            box.configure(style='CardSelected.TFrame' if index == current else 'Card.TFrame')
        self.ap_export_button.configure(style='Accent.TButton' if current == 0 else 'TButton')
        self.ap_patch_button.configure(style='Accent.TButton' if current == 1 else 'TButton')
        unlocked = bool(self.ap_manifest or self.ap_client)
        if unlocked:
            self.ap_lock.pack_forget()
            if not self.ap_connect.winfo_manager():
                self.ap_connect.pack(fill='x')
        else:
            self.ap_connect.pack_forget()
            if not self.ap_lock.winfo_manager():
                self.ap_lock.pack(anchor='w')
        if self.ap_client and not self.ap_live.winfo_manager():
            self.ap_live.pack(fill='x')
        elif not self.ap_client and self.ap_live.winfo_manager():
            self.ap_live.pack_forget()
        self.ap_dot.configure(image=self.images['dot_ok' if self.ap_client else 'dot_off'])


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
        if self.busy:
            return
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
        if self.party_context:
            self.party_library.set_address(self.party_context['id'], self.ap_address.get())
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
            self.ap_dot.configure(image=self.images['dot_error'])

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

    def prompt_longshot_channel(self, channels, default_channel=None):
        """Ask which Longshot channel to use; the chosen channel entry, or None when cancelled."""
        if not channels:
            return None
        dialog = tk.Toplevel(self.root)
        dialog.title('Choose Longshot channel')
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background=self.colors['page'])
        frame = ttk.Frame(dialog, padding=(22, 18), style='Page.TFrame')
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Your Longshot folder moved', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='The saved mods folder no longer exists and several Longshot channels are '
                              'installed. Choose the one to use:',
                  style='Muted.TLabel', wraplength=460, justify='left').pack(anchor='w', pady=(4, 12))
        known = any(c['channel'] == default_channel for c in channels)
        selected = tk.StringVar(value=default_channel if known else channels[0]['channel'])
        for channel in channels:
            ttk.Radiobutton(frame, text=f"{channel['label']}  —  {channel['version_name']}",
                            value=channel['channel'], variable=selected).pack(anchor='w', pady=3)
            ttk.Label(frame, text='    ' + str(channel['mods_dir']), style='Small.TLabel',
                      wraplength=460).pack(anchor='w', pady=(0, 6))
        chosen = []

        def confirm(_event=None):
            chosen.append(next((c for c in channels if c['channel'] == selected.get()), channels[0]))
            dialog.destroy()

        buttons = ttk.Frame(frame, style='Page.TFrame')
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Cancel', command=dialog.destroy).pack(side='right', padx=(8, 0))
        ttk.Button(buttons, text='Use this channel', style='Accent.TButton', command=confirm).pack(side='right')
        dialog.bind('<Return>', confirm)
        dialog.bind('<Escape>', lambda _event: dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()
        self.root.wait_window(dialog)
        return chosen[0] if chosen else None

    def resolve_longshot_mods(self, path):
        """The mods folder a saved or picked Longshot path stands for now ('' when none was chosen).

        A path which is still a port's mods folder is kept as it is: an older build or another
        channel is the player's choice. Only a vanished path (or a Longshot root or channel folder
        picked by hand) is replaced: by the newest build of its only channel, else by the
        channel the player chooses."""
        info = pc_port.resolve_longshot_update(path)
        if info['status'] == 'upgraded':
            return str(info['recommended']['mods_dir'])
        if info['status'] == 'choose_channel':
            chosen = self.prompt_longshot_channel(info['channels'], default_channel=info['current_channel'])
            return str(chosen['mods_dir']) if chosen is not None else ''
        return ''

    def normalize_chosen_mods_dir(self, raw_path):
        """A folder picked with Browse…: a port folder becomes its mods, a Longshot root or channel
        folder becomes the mods of the build to use; anything else is kept."""
        folder = pc_port.normalize_port_mods_dir(raw_path)
        if not folder or Path(folder).name.upper() == TITLE or pc_port.is_port_mods_dir(folder):
            return folder
        return self.resolve_longshot_mods(folder) or folder

    def reconcile_longshot_installation(self):
        """Follow a Longshot update which deleted the saved mods folder. Returns a status notice."""
        candidates = [self.mods.get().strip()]
        if self.party_library is not None and self.party_library.active_id:
            try:
                candidates.append(self.party_library.get(self.party_library.active_id)['mods'])
            except (OSError, ValueError, KeyError):
                pass
        for source in dict.fromkeys(c for c in candidates if c):
            info = pc_port.resolve_longshot_update(source)
            if info['status'] != 'not_longshot':
                break
        else:
            return ''
        if info['status'] == 'unchanged':
            # The saved folder is fine; still move parties whose own (older) folder vanished.
            new_mods = source
        else:
            new_mods = self.resolve_longshot_mods(source)
            if not new_mods:
                return ''
        migrated = []
        notice = ''
        if self.party_library is not None:
            try:
                migrated = self.party_library.migrate_mods_directory(new_mods, old_mods=source, root=info['root'])
            except (OSError, ValueError) as error:
                notice = f' My Games not updated: {error}'
            if migrated:
                self.render_parties()
        if new_mods == source:
            if not migrated:
                return notice.strip()
            return f'Longshot: {len(migrated)} game(s) moved to {Path(new_mods).parent.name}.' + notice
        self.mods.set(new_mods)
        # The game file and the save folder may have lived in the vanished build too.
        nup = self.nup.get().strip()
        if nup and not Path(nup).is_file():
            found = pc_port.resolve_stale_nup_path(nup, new_mods, longshot_root=info['root'])
            if found is not None:
                self.nup.set(str(found))
        save = self.save_path.get().strip()
        if save and not Path(save).exists():
            found = pc_port.resolve_stale_port_subpath(save, source, new_mods)
            if found is not None:
                self.save_path.set(str(found))
            elif self.auto_save.get():
                self.save_path.set('')
        moved = f' ({len(migrated)} game(s) moved)' if migrated else ''
        return f'Longshot updated: now using {Path(new_mods).parent.name}{moved}.' + notice

    def restore_last_artifact(self):
        notice = self.reconcile_longshot_installation()
        if self.restore_party():
            if notice:
                current = self.status.get()
                self.status.set(notice + ('  ' + current if current else ''))
            return
        if notice:
            self.status.set(notice)
        last = self.app_state.get('last_artifact')
        if not last or self.artifact or not (Path(last) / 'manifest.json').is_file():
            return
        prefix = (notice + '  ') if notice else ''
        try:
            self.use_artifact(last)
            self.status.set(prefix + 'Last seed reloaded: ' + Path(last).name)
        except Exception as error:
            self.show_notice('warn', 'The last seed was not reloaded', str(error),
                             [('Open a seed…', self.open_artifact)])

    # ---------------------------------------------------------- saves
    def hookshot_root(self):
        """Hookshot folder when the mods folder is ``<Hookshot>/mods``, else None (emulator)."""
        mods = Path(self.mods.get()) if self.mods.get() else None
        return mods.parent if mods and mods.name.lower() == 'mods' else None

    def newest_save(self):
        """progress.sav most recently written, across every save and slot folder."""
        if self.party_context:
            saves = Path(self.party_context['saves'])
            candidates = list(saves.glob('slot_*/progress.sav'))
            return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
        return newest_save(self.hookshot_root(), TITLE, self.mods.get() or None)

    def follow_newest_save(self):
        newest = self.newest_save()
        if newest is None:
            if self.party_context:
                self.save_path.set('')
            if not self.save_path.get():
                self.connection_status.set('No save found. Start a game and save, or choose progress.sav.')
            return False
        if self.save_path.get() and Path(self.save_path.get()) == newest:
            return False
        self.save_path.set(str(newest))
        return True

    def start_turbo(self):
        """Keep the A forwarding service alive even when repetition is disabled."""
        if self.turbo:
            self.turbo.stop()
        self.turbo = turbo_a.TurboA(self.hookshot_root() or '')
        self.turbo.enabled = self.turbo_enabled.get()
        self.turbo.start()
        self.turbo_status.set(self.turbo.status)

    def turbo_toggled(self):
        enabled = self.turbo_enabled.get()
        self.write_app_state(turbo_a=enabled)
        if self.turbo:
            # Stopping the service would remove A from a running remapped game.
            self.turbo.enabled = enabled
            if self.turbo.running:
                self.turbo.status = ('Turbo A on' if enabled else 'Turbo A off') + '; press X to skip a cutscene'
        self.turbo_status.set('Turbo A on' if enabled else 'Turbo A off')

    def auto_save_toggled(self):
        self.write_app_state(auto_save=self.auto_save.get())
        if self.auto_save.get() and self.follow_newest_save() and self.tracker:
            self.refresh_tracker()

    def choose_save(self):
        value = filedialog.askopenfilename(title='Choose the save of this game', initialdir=self.save_path.get().strip(), filetypes=[('Hookshot progress', 'progress.sav'), ('Saves', '*.sav')], parent=getattr(self, 'root', None))
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
        if self.busy:
            self._schedule_after(1000, self.tracker_tick)
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
        self._schedule_after(1000, self.tracker_tick)   # live memory: ~1 s; the save path is cheap to stat

    def refresh_tracker(self):
        if self.busy or not self.tracker or self.tracker_refreshing:
            return
        if self.party_context and self.save_path.get() and not Path(self.save_path.get()).resolve().is_relative_to(
                Path(self.party_context['saves'])):
            self.save_path.set('')
            self.follow_newest_save()
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
        tip = option_tip(option, label, help_text)
        row = index * 2
        def describe():
            self.update_presets()
        if option.kind == 'items':
            variable = ItemsVar()
            widget = self.items_field(parent, variable, describe) if parent else None
        elif option.kind == 'list':
            variable = ListVar(option)
            widget = ttk.Entry(parent, textvariable=variable.text, width=40) if parent else None
            if widget:
                error = ttk.Label(parent, style='Bad.TLabel')
                def check(event=None):
                    # A typing error is said at once, under the field, not at generation.
                    try:
                        variable.get()
                        error.grid_remove()
                    except ValueError as problem:
                        error.configure(text='\u2715 ' + str(problem))
                        error.grid(row=row + 1, column=0, columnspan=2, sticky='w', pady=(0, 6))
                    describe()
                widget.bind('<FocusOut>', check, add='+')
                widget.bind('<Return>', check, add='+')
        elif option.kind == 'bool':
            variable = tk.BooleanVar(value=option.default)
            if parent:
                widget = self.switch_row(parent, index, label, variable, command=describe, tip=tip)
                self.setting_rows[option.name] = self.setting_rows.pop(f'switch:{str(parent)}:{row}', None) or {}
                if not self.setting_rows[option.name]:
                    del self.setting_rows[option.name]
                else:
                    self.setting_rows[option.name]['marks'][1].configure(command=lambda: self.reset_option(option.name))
            else:
                widget = None
        elif option.kind == 'int':
            variable = tk.IntVar(value=option.default)
            widget = ttk.Spinbox(parent, from_=min(option.supported_ints), to=max(option.supported_ints), textvariable=variable, width=8, command=describe) if parent else None
            if widget:
                widget.bind('<KeyRelease>', lambda event: describe(), add='+')
        else:
            def choice_label(value, text):
                if option.name == 'chest_matching':
                    return 'Identified chests' if value == 'strict' else 'Access by zone'
                return text
            labels = [choice_label(value, text) for value, text, reason in option.values]
            variable = tk.StringVar(value=option.default)
            display = tk.StringVar(value=labels[[v for v, label, reason in option.values].index(option.default)])
            variable.display, variable.labels = display, labels
            allowed = [choice_label(value, text) for value, text, reason in option.values if reason is None
                       and not (option.name == 'spiritual_stones' and value == 'door')]
            # Wide enough for the longest choice: a truncated value reads as another one.
            width = max(16, min(44, max(len(text) for text in allowed) + 3))
            widget = ttk.Combobox(parent, state='readonly', values=allowed, textvariable=display, width=width) if parent else None
            if widget:
                def selected(event=None):
                    variable.set(option.values[labels.index(display.get())][0])
                    describe()
                widget.bind('<<ComboboxSelected>>', selected)
        self.full_vars[option.name] = variable
        if widget:
            if option.kind != 'bool':
                text_label, icon = self.label_cell(parent, index, label, tip, wraplength=420)
                self.register_row(option.name)
                widget.grid(row=row, column=1, sticky='e', pady=7)
                theme.Tooltip((text_label,), tip, self.fonts)
                if index:
                    theme.rule(parent).grid(row=row, column=0, columnspan=2, sticky='new')
            widget.bind('<FocusIn>', lambda event: describe(), add='+')

    def items_field(self, parent, variable, changed):
        """Starting inventory: one tag per item (× removes it), a field with suggestions to add one;
        an unknown name is said at once under the field."""
        frame = ttk.Frame(parent)
        tags = ttk.Frame(frame)
        tags.pack(anchor='e')
        names = sorted(STARTABLE_ITEMS)
        entry = ttk.Combobox(frame, values=names, width=30)
        entry.pack(anchor='e', pady=(4, 0))
        error = ttk.Label(frame, style='Bad.TLabel', wraplength=300, justify='right')
        def redraw():
            for child in tags.winfo_children():
                child.destroy()
            for position, (name, count) in enumerate(sorted(variable.items.items())):
                tag = ttk.Frame(tags, style='Tab.TFrame', padding=(8, 2, 4, 2))
                tag.grid(row=position // 2, column=position % 2, sticky='e', padx=(4, 0), pady=(0, 4))
                ttk.Label(tag, text=name + (f' \u00d7{count}' if count > 1 else ''), style='Tab.TLabel').pack(side='left')
                ttk.Button(tag, text='\u00d7', width=2, style='Link.TButton',
                           command=lambda n=name: remove(n)).pack(side='left')
        def remove(name):
            items = variable.get()
            items.pop(name, None)
            variable.set(items)
            changed()
        def add(event=None):
            text = entry.get().strip()
            if not text:
                return 'break'
            try:
                parsed = rando_options.parse_items(text)
            except ValueError as problem:
                error.configure(text='\u2715 ' + str(problem) + '. Pick a name from the list.')
                error.pack(anchor='e', pady=(4, 0))
                return 'break'
            error.pack_forget()
            items = variable.get()
            for name, count in parsed.items():
                items[name] = items.get(name, 0) + count
            entry.set('')
            entry.configure(values=names)
            variable.set(items)
            changed()
            return 'break'
        def suggest(event):
            if event.keysym in ('Return', 'Up', 'Down', 'Escape'):
                return
            typed = entry.get().strip().casefold()
            entry.configure(values=[n for n in names if typed in n.casefold()] if typed else names)
        entry.bind('<Return>', add)
        entry.bind('<<ComboboxSelected>>', add)
        entry.bind('<KeyRelease>', suggest, add='+')
        variable.listeners.append(redraw)
        return frame


    def full_value(self, option):
        return self.full_vars[option.name].get()

    def full_values(self):
        values = {option.name: self.full_value(option) for option in rando_options.OPTIONS
                  if option.name in self.full_vars}
        if 'fast_chests' in values:
            values['fast_chests'] = self.options['skip_chest_cutscenes'].get()
        return values

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
        name = filedialog.askopenfilename(title='Import Archipelago YAML', filetypes=[('Archipelago YAML', '*.yaml *.yml')], parent=getattr(self, 'root', None))
        if name:
            try:
                values, ignored = rando_options.from_ap_yaml(Path(name).read_text(encoding='utf-8'))
                supported = {k: (v if rando_options.BY_NAME[k].supported(v) else rando_options.BY_NAME[k].default)
                             for k, v in values.items()}
                self.options['skip_chest_cutscenes'].set(supported['fast_chests'])
                self.apply_full(supported, enable=True)
                if ignored:
                    self.show_notice('info', 'YAML imported. Some values were ignored or replaced by the supported value',
                                     '• ' + '\n• '.join(ignored))
                else:
                    self.notify('YAML imported.')
            except Exception as error:
                self.error(error)

    def export_ap_yaml(self):
        try:
            values = rando_options.validate(self.full_values())
            name = filedialog.asksaveasfilename(title='Export Archipelago YAML', defaultextension='.yaml', filetypes=[('Archipelago YAML', '*.yaml')], parent=getattr(self, 'root', None))
            if name:
                Path(name).write_text(to_ap_yaml(values, open_forest=self.options['open_forest'].get()),
                                      encoding='utf-8')
                self.notify('Archipelago YAML exported.')
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
            name = filedialog.asksaveasfilename(title='Export Multiworld YAML', defaultextension='.yaml', initialfile=f'{player}.yaml',
                                                filetypes=[('Archipelago YAML', '*.yaml')], parent=getattr(self, 'root', None))
            if name:
                Path(name).write_text(text, encoding='utf-8')
                preset = dict((key, title) for key, title, _ in self.PRESET_CARDS).get(self.current_preset, 'Custom settings')
                self.write_app_state(ap_yaml_export={'player': player, 'preset': preset,
                                                     'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                                     'settings': self.multiworld_signature()})
                self.update_archipelago_controls()
                self.notify('Multiworld YAML exported. Send it to the host.')
        except Exception as error:
            self.error(error)

    def build_apworld(self):
        from oot_rando.archipelago.apworld_build import build_apworld
        try:
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            name = filedialog.asksaveasfilename(title='Export Archipelago World', defaultextension='.apworld', initialfile='oot_remake.apworld',
                                                filetypes=[('Archipelago world', '*.apworld')], parent=getattr(self, 'root', None))
            if not name:
                return

            def done(path):
                self.show_notice('info', 'apworld ready: ' + str(path), 'Copy it into the custom_worlds folder of '
                                 'Archipelago on the computer that generates the multiworld.',
                                 [('Open the folder', lambda: self.open_path(Path(path).parent))])
            self.run_job(lambda progress: build_apworld(nup, name, progress), done)
        except Exception as error:
            self.error(error)

    def generate_from_patch(self):
        from oot_rando.archipelago import bridge
        try:
            name = filedialog.askopenfilename(title='Choose Archipelago Patch', filetypes=[('Archipelago patch', '*' + bridge.PATCH_SUFFIX)], parent=getattr(self, 'root', None))
            if not name:
                return
            settings = settings_from_patch(
                bridge.load_patch(name), self.options['skulltulas_always_present'].get()).validate_supported()
            self.party_name.set('')
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError('Select the local NUP file.')
            mods = validate_mod_directory(self.mods.get())

            self.start_generation(nup, mods, settings)
        except Exception as error:
            self.error(error)

    def get_settings(self):
        full = self.full_values() if self.full_enabled.get() else None
        options = {n: v.get() for n, v in self.options.items()}
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
            variable.set(getattr(settings, name))
        # The old complete-mode alias and the general setting share one control.
        self.options['skip_chest_cutscenes'].set(
            settings.skip_chest_cutscenes or bool((settings.full or {}).get('fast_chests')))
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

    def copy_seed_string(self):
        try:
            text = settings_string.encode(self.get_settings())
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.notify(f'Seed string copied ({len(text)} characters). Share it with the same version '
                        f'of the randomizer ({APP_VERSION}).')
        except Exception as error:
            self.error(error)

    def import_seed_string(self):
        try:
            clipboard = self.root.clipboard_get().strip()
        except tk.TclError:
            clipboard = ''
        initial = clipboard if clipboard.upper().startswith(settings_string.PREFIX) else ''
        text = simpledialog.askstring('Paste a seed string', 'Seed string (starts with '
                                      + settings_string.PREFIX + '):', initialvalue=initial, parent=self.root)
        if not text or not text.strip():
            return
        try:
            settings, version = settings_string.decode(text)
        except Exception as error:
            self.error(error)
            return
        def apply():
            try:
                self.apply_settings(settings)
                self.clear_notices()
                self.notify('Seed string imported: seed "' + settings.seed + '".')
            except Exception as error:
                self.error(error)
        if version == GENERATOR_VERSION:
            apply()
            return
        self.show_notice('warn', f'This seed string comes from generator {version}',
                         f'This application uses {GENERATOR_VERSION}: the same settings may give a different game.',
                         [('Import anyway', apply), ('Cancel', self.clear_notices)])

    def import_settings(self):
        name = filedialog.askopenfilename(title='Import Settings', filetypes=[('JSON settings', '*.json')], parent=getattr(self, 'root', None))
        if name:
            try:
                value = json.loads(Path(name).read_text(encoding='utf-8'))
                if value.get('format') != 'oot-remake-settings-v1':
                    raise ValueError('Unsupported settings format.')
                self.apply_settings(Settings.from_dict(value['settings']))
                self.notify('Settings imported.')
            except Exception as error:
                self.error(error)

    def export_settings(self):
        try:
            settings = self.get_settings()
            name = filedialog.asksaveasfilename(title='Export Settings', defaultextension='.json', filetypes=[('JSON settings', '*.json')], parent=getattr(self, 'root', None))
            if name:
                Path(name).write_text(json.dumps({'format': 'oot-remake-settings-v1', 'settings': settings.to_dict()}, ensure_ascii=False, indent=2), encoding='utf-8')
                self.notify('Settings exported.')
        except Exception as error:
            self.error(error)

    def run_job(self, function, done):
        if self.busy:
            self.notify('An operation is already running.')
            return
        self.busy = True
        self.clear_notices()
        self.status.set('Working…')
        self.show_status_bar(True)
        for button in (self.generate_button, self.qol_button):
            button.state(['disabled'])
        def worker():
            try:
                result = function(lambda text: self.events.put(('progress', text)))
                self.events.put(('done', (done, result)))
            except Exception as error:
                import traceback
                # A worker process failure carries the traceback of where it really failed.
                write_error_log(getattr(error, 'trace', '') or traceback.format_exc())
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def generate(self):
        try:
            settings = self.get_settings()
            settings.validate_supported()
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError("Select the local NUP file.")
            if self._using_real_generator():
                from oot_rando.randomizer.mods_folder import validate_nup_file
                validate_nup_file(nup)
            mods = validate_mod_directory(self.mods.get())
            self.start_generation(nup, mods, settings)
        except Exception as error:
            self.error(error)

    def regenerate(self):
        """Generate the installed seed again with this version: same name, same settings."""
        try:
            settings = self.regen_settings
            if settings is None or self.artifact is None:
                raise ValueError("This seed is already up to date.")
            settings.validate_supported()
            nup = Path(self.nup.get())
            if not nup.is_file():
                raise ValueError("Select the local NUP file.")
            if self._using_real_generator():
                from oot_rando.randomizer.mods_folder import validate_nup_file
                validate_nup_file(nup)
            mods = validate_mod_directory(self.artifact.parent)
            # The banner on Home said why and what changes: the click is the answer.
            self.generate_party(nup, mods, settings, continuing=self.party_context)
        except Exception as error:
            self.error(error)

    def start_generation(self, nup, mods, settings):
        self.generate_party(nup, mods, settings)

    def offer_save_migration(self, manifest, previous=None):
        """Offer to give the saves of this seed the start values they never received.

        A fix written by the new-game opening only reaches games started after it. Saves
        of this seed (or of the one it regenerates) are listed; nothing is written unless
        the player agrees, and each save is backed up first (randomizer/save_patch.py)."""
        from oot_rando.randomizer import save_patch
        try:
            from oot_rando.tracker.auto_tracker import resolve_party_save_root
            party_saves = None
            if self.party_context:
                rec_saves = Path(self.party_context["saves"])
                party_saves = (
                    rec_saves
                    if rec_saves.is_dir()
                    else resolve_party_save_root(rec_saves, mods=self.party_context.get("mods"))
                )
            paths = (list(party_saves.glob("slot_*/progress.sav")) if party_saves is not None
                     else find_save_slots(self.hookshot_root(), TITLE, self.mods.get() or None))
            candidates = save_patch.migration_candidates(paths, manifest, previous)
        except Exception as error:   # never block the installation on a save scan
            self.show_notice('warn', 'The saves of this seed were not checked', str(error))
            return
        if not candidates:
            return
        names = sorted({name for _, changed in candidates for name in changed})
        listing = '\n'.join('• ' + str(path) for path, _ in candidates[:6])
        if len(candidates) > 6:
            listing += f'\n• … and {len(candidates) - 6} more'
        self.show_notice(
            'warn', f'{len(candidates)} save(s) of this seed miss fixes of this version',
            f'They were started before these fixes and miss {len(names)} start value(s) ('
            + ', '.join(names[:4]) + (', …' if len(names) > 4 else '') + ').\n' + listing
            + '\nClose the game first. Each save is backed up next to it (progress.sav'
            + save_patch.BACKUP_SUFFIX + '<date>) and only flags it already holds are changed.',
            [('Update the saves', lambda: self.migrate_saves(manifest, previous, candidates)),
             ('Not now', self.clear_notices)])

    def migrate_saves(self, manifest, previous, candidates):
        from oot_rando.randomizer import save_patch
        self.clear_notices()
        markers = save_patch.migration_markers(manifest, previous)
        values = save_patch.migration_values(manifest, previous)
        done, failed = [], []
        for path, _ in candidates:
            try:
                done.append(save_patch.patch_save(path, values, markers))
            except save_patch.GameRunning as error:
                failed.append(str(error))
                break
            except Exception as error:
                failed.append(f'{path}: {error}')
        text = f'{len(done)} save(s) updated.'
        backups = [report['backup'] for report in done if report['backup']]
        if backups:
            text += '\nBackups:\n' + '\n'.join(backups)
        if failed:
            self.show_notice('warn', f'{len(done)} save(s) updated, {len(failed)} not',
                             text.partition('\n')[2].strip() + '\n\nNot updated:\n' + '\n'.join(failed))
        else:
            self.notify(text.splitlines()[0] + ' A backup sits next to each one.')

    def use_artifact(self, directory):
        if self.busy:
            return
        manifest, _ = read_artifact(directory)
        self.match_party(directory)
        self.artifact, self.artifact_manifest = Path(directory), manifest
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
        # The New seed form is left alone: it starts on the Classic preset, unchanged, instead of
        # showing the loaded seed's settings as changes (a seed string or settings file restores them).
        self.regen_settings = regeneration_settings(manifest)
        if manifest.get('tracking', {}).get('new_save_required'):
            self.result.set(self.result.get() + '\nA new game is needed for automatic tracking.')
        self.seed_name = (manifest['settings']['seed'] or manifest['seed_id'][:12])[:28]
        self.seed_chip.set(self.party_chip() if self.party_context else 'Seed  ' + self.seed_name)
        self.write_app_state(last_artifact=str(Path(directory).resolve()))
        if self.auto_save.get():
            self.follow_newest_save()
        self.load_tracker()
        self.set_archipelago_seed(manifest)
        self.reset_spoiler()
        self.status.set('Seed opened.')

    def _on_mods_dir_changed(self, *_args) -> None:
        """Persist mods_dir edits."""
        self.write_app_state(mods_dir=self.mods.get())

    def open_artifact(self):
        if self.busy:
            return
        directory = filedialog.askdirectory(
            title="Choose the folder holding manifest.json",
            initialdir=self.mods.get().strip(),
            parent=getattr(self, "root", None),
        )
        if directory:
            try:
                self.use_artifact(directory)
            except Exception as error:
                self.error(error)

    def open_folder(self):
        if self.artifact:
            open_in_file_manager(self.artifact)

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
        page = ttk.Frame(self.spoiler_tab, style='Page.TFrame', padding=(0, 0, PAGE_GUTTER, 0))
        page.pack(fill='both', expand=True)
        self.spoiler = None
        self.spoiler_search = tk.StringVar()
        self.spoiler_minor = tk.BooleanVar(value=True)
        self.spoiler_info = tk.StringVar(value='Open a seed to read its spoiler.')
        box = self.card(page)
        row = self.buttons(box)
        info = ttk.Frame(row)
        info.pack(side='left', fill='x', expand=True, padx=(0, 16))
        ttk.Label(info, text='Seed spoiler', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(info, textvariable=self.spoiler_info, style='Small.TLabel', wraplength=420, justify='left').pack(anchor='w', pady=(2, 0))
        files = ttk.Frame(row)
        files.pack(side='right')
        ttk.Button(files, text='Open spoiler.txt', command=self.open_spoiler_text).pack(side='left')
        ttk.Button(files, text='Export…', command=self.export_spoiler).pack(side='left', padx=(8, 0))
        self.spoiler_hide = ttk.Button(row, text='Hide again', style='Link.TButton', command=self.reset_spoiler)
        parent = self.card(page, fill='both', expand=True)
        filters = self.buttons(parent, pady=(0, 10))
        self.spoiler_switch = theme.Segmented(filters, [('zones', 'By zone'), ('playthrough', 'Progression playthrough')],
                                              self.set_spoiler_view)
        self.spoiler_switch.pack(side='left')
        theme.search_entry(filters, self.spoiler_search, 'Search a location, a reward…', width=30).pack(side='left', padx=(12, 0))
        ttk.Checkbutton(filters, text='Minor items', variable=self.spoiler_minor,
                        command=self.render_spoiler).pack(side='right')
        self.spoiler_search.trace_add('write', lambda *args: self.render_spoiler())
        # Views without visible tabs: the segmented switch above selects them.
        self.spoiler_views = ttk.Notebook(parent, style='Pages.TNotebook')
        self.spoiler_views.pack(fill='both', expand=True)
        self.spoiler_trees = {}
        # Widths that fit the minimum window (1040 px); the first two columns take the rest.
        views = [('zones', 'By zone', 'Zone / location',
                  [('item', 'Reward', 170), ('original', 'Originally', 130), ('sphere', 'Sphere', 66), ('kind', 'Type', 100)]),
                 ('playthrough', 'Progression playthrough', 'Sphere / location', [('item', 'Reward', 260)])]
        for key, title, heading, columns in views:
            frame = ttk.Frame(self.spoiler_views)
            self.spoiler_views.add(frame, text=title)
            tree = ttk.Treeview(frame, columns=[c for c, _, _ in columns], show='tree headings', selectmode='browse')
            tree.heading('#0', text=heading, anchor='w')
            tree.column('#0', width=220, minwidth=140, stretch=True)
            for column, text, width in columns:
                tree.heading(column, text=text, anchor='w')
                tree.column(column, width=width, minwidth=50, stretch=(column == 'item'))
            tree.tag_configure('major', foreground=self.colors['text'])
            tree.tag_configure('minor', foreground=self.colors['muted'])
            bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=bar.set)
            bar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            self.spoiler_trees[key] = tree
        self.spoiler_summary = tk.StringVar()
        ttk.Label(parent, textvariable=self.spoiler_summary, style='Small.TLabel').pack(anchor='w', pady=(8, 0))
        # While hidden, a blurred table and the reveal card cover the views.
        cover = self.spoiler_cover = tk.Canvas(parent, highlightthickness=0, background=self.colors['surface'])
        cover.bind('<Configure>', lambda event: self.draw_spoiler_cover())
        card = self.spoiler_card = ttk.Frame(cover, style='CoverCard.TFrame', padding=theme.CARD_PADDING)
        self.spoiler_card_title, self.spoiler_card_text = tk.StringVar(), tk.StringVar()
        ttk.Label(card, textvariable=self.spoiler_card_title, style='Heading.TLabel').pack(anchor='w')
        ttk.Label(card, textvariable=self.spoiler_card_text, style='Muted.TLabel', wraplength=360,
                  justify='left').pack(anchor='w', pady=(4, 12))
        self.spoiler_card_buttons = ttk.Frame(card)
        self.spoiler_card_buttons.pack(anchor='w')
        cover.create_window(0, 0, window=card, anchor='center', tags='card')
        self.set_spoiler_cover('none')

    def set_spoiler_view(self, key):
        self.spoiler_switch.set(key)
        self.spoiler_views.select(list(self.spoiler_trees).index(key))

    def draw_spoiler_cover(self):
        """Grey bars where the rows would be: the table is there, its words are not."""
        cover = self.spoiler_cover
        width, height = cover.winfo_width(), cover.winfo_height()
        cover.delete('rows')
        widths = (0.46, 0.31, 0.38, 0.27, 0.42, 0.35, 0.29, 0.44, 0.33, 0.4)
        for index, y in enumerate(range(14, height, 30)):
            fraction = widths[index % len(widths)]
            for x0, part in ((16, fraction * 0.55), (width * 0.48, fraction * 0.6), (width * 0.82, 0.1)):
                color = self.colors['line'] if index % 4 else self.colors['field_hover']
                cover.create_rectangle(x0, y, x0 + width * part, y + 9, fill=color, outline='', tags='rows')
        cover.tag_lower('rows')
        cover.coords('card', width / 2, min(height / 2, 190))

    def set_spoiler_cover(self, state):
        """'none' (no seed), 'hidden', 'confirm' (asked once, in place) or None (revealed)."""
        for child in self.spoiler_card_buttons.winfo_children():
            child.destroy()
        if state is None:
            self.spoiler_cover.place_forget()
            if not self.spoiler_hide.winfo_manager():
                self.spoiler_hide.pack(side='right', padx=(0, 12))
            return
        self.spoiler_hide.pack_forget()
        buttons = self.spoiler_card_buttons
        if state == 'none':
            self.spoiler_card_title.set('No seed open')
            self.spoiler_card_text.set('Open or create a seed: its spoiler lists every reward and where it is.')
        elif state == 'hidden':
            self.spoiler_card_title.set('The spoiler is hidden')
            self.spoiler_card_text.set('It shows every reward of this seed and where it is. Reveal it only if you want to know.')
            ttk.Button(buttons, text='Reveal the spoiler…', style='Accent.TButton',
                       command=self.reveal_spoiler).pack(side='left')
        else:
            seed = (self.artifact_manifest or {}).get('settings', {}).get('seed') or 'this seed'
            self.spoiler_card_title.set('Show every reward?')
            self.spoiler_card_text.set(f'Every randomized reward of seed {seed} will be listed. You can hide it again, '
                                       'but not forget it.')
            ttk.Button(buttons, text='Yes, reveal', style='Accent.TButton', command=self.confirm_spoiler).pack(side='left')
            ttk.Button(buttons, text='Cancel', command=lambda: self.set_spoiler_cover('hidden')).pack(side='left', padx=(8, 0))
        self.spoiler_cover.place(in_=self.spoiler_views, relx=0, rely=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.spoiler_cover)


    def reset_spoiler(self):
        """Hide the spoiler again (new seed opened, or the player asked)."""
        self.spoiler = None
        self.spoiler_info.set('Hidden until you reveal it.' if self.artifact else 'Open a seed to read its spoiler.')
        self.set_spoiler_cover('hidden' if self.artifact else 'none')
        self.render_spoiler()


    def load_spoiler_report(self):
        if not self.artifact:
            raise ValueError('No seed open. Generate a game or open a seed folder.')
        return spoiler_report.load_report(self.artifact, self.spoiler_roots())

    def reveal_spoiler(self):
        """Ask once, inside the page (no window)."""
        self.set_spoiler_cover('confirm' if self.artifact else 'none')

    def confirm_spoiler(self):
        try:
            self.spoiler = self.load_spoiler_report()
            self.spoiler_info.set(f'Seed {self.spoiler["seed"] or "?"} · identity {self.spoiler["seed_id"][:16]} · '
                                  f'{len(self.spoiler["rows"])} shuffled locations')
            self.set_spoiler_cover(None)
            self.render_spoiler()
        except Exception as error:
            self.set_spoiler_cover('hidden')
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
        for tree in self.spoiler_trees.values():
            theme.fit_tree(tree, self.fonts)
        self.spoiler_summary.set(f'{shown} of {len(self.spoiler["rows"])} locations shown · '
                                 f'{len(self.spoiler["playthrough"])} progression spheres')

    def export_spoiler(self):
        try:
            report = self.load_spoiler_report()
            name = filedialog.asksaveasfilename(title='Export Spoiler Log', defaultextension='.txt', filetypes=[('Text', '*.txt')],
                                                initialfile='spoiler_' + (report['seed'] or report['seed_id'][:16]) + '.txt', parent=getattr(self, 'root', None))
            if name:
                spoiler_report.write_text(report, name)
                self.notify('Spoiler exported: ' + name)
        except Exception as error:
            self.error(error)

    def open_spoiler_text(self):
        try:
            report = self.load_spoiler_report()
            path = Path(report['path']).with_name(spoiler_report.SPOILER_TEXT)
            if not path.is_file():
                # Seeds generated before spoiler.txt existed: create it next to spoiler.json.
                spoiler_report.write_text(report, path)
            open_in_file_manager(path)
        except Exception as error:
            self.error(error)

    def load_tracker(self):
        if self.busy:
            return
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
            live = live_memory.LiveGameData() if live_memory.supported() else None
            manual_directory = None
            if self.party_context:
                ident = self.party_context['id']
                self.slot.set('party-' + ident)
                manual_directory = self.party_library.tracker_dir(ident)
                # A save chosen manually must stay inside the active party's account.
                if self.save_path.get() and not Path(self.save_path.get()).resolve().is_relative_to(
                        Path(self.party_context['saves'])):
                    self.save_path.set('')
                    self.follow_newest_save()
            self.tracker = TrackerSession(self.artifact, self.slot.get(), save_path=self.save_path.get(),
                                          live=live, manual_directory=manual_directory)
            if self.party_context:
                imported = self.party_library.folder(self.party_context['id']) / 'imported-tracker.json'
                if imported.is_file() and not self.tracker.manual.path.exists():
                    checks = json.loads(imported.read_text(encoding='utf-8'))
                    if checks.get('seed_id') == self.tracker.seed_id:
                        for check in set(checks.get('completed', [])) & self.tracker.manual.allowed:
                            self.tracker.manual.set_completed(check, True)
                    imported.rename(imported.with_suffix('.imported'))
            self.connection_status.set('Reading at the latest save' if self.save_path.get() else 'Choose a progress.sav file to enable automatic tracking.')
            self.render_tracker()
            self.refresh_tracker()
        except Exception as error:
            self.error(error)

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
            # Widths that fit the minimum window (1040 px); the name and the reward take the rest.
            tree.column('#0', width=250, minwidth=160, stretch=True)
            for key, title, width in [('state', 'State', 130), ('reward', 'Reward', 150), ('kind', 'Type', 100)]:
                tree.heading(key, text=title, anchor='w')
                tree.column(key, width=width, minwidth=70, stretch=(key == 'reward'))
            for tag, color in theme.STATE_COLORS.items():
                tree.tag_configure(tag, foreground=color)
            tree.tag_configure('zone', font=self.fonts.strong)
            scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            tree.pack(side='left', fill='both', expand=True)
            zones, visible, region_numbers = {}, 0, {}
            for check in self.current_checks:
                state = states[check['id']]
                completed, access = state.get('completed', False), state.get('access', 'unknown')
                region = check.get('region') or 'Other'
                region_numbers[region] = region_numbers.get(region, 0) + 1
                bucket = 'done' if completed else access if access in ('available', 'blocked') else 'unknown'
                if self.tracker_filter != 'all' and bucket != self.tracker_filter:
                    continue
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
                    zones[region] = tree.insert('', 'end', iid='zone::' + region, open=self.zone_open.get(region, bool(query)), text=' ' + region, image=self.zone_bar(done[region], totals[region]), values=(f'{done[region]} / {totals[region]}', f'{available[region]} available' if available[region] else '', ''), tags=('zone',))
                state_key = 'done' if completed else access if access in theme.STATE_MARKS else 'unknown'
                label = theme.STATE_MARKS[state_key] + '  ' + {'done': 'Done', 'available': 'Available', 'partial': 'Partial zone',
                                                            'blocked': 'Blocked', 'unknown': 'Unknown'}[state_key]
                if completed and state.get('source') == 'manual':
                    label += ' (manual)'
                elif not completed and state.get('missing_souls'):
                    from oot_rando.patching.soul_adapter import soul_name
                    label += ' • soul: ' + ', '.join(soul_name(s, False) for s in state['missing_souls'])
                if not completed and state.get('untracked'):
                    label += ' • not tracked'
                box = 'check_locked' if state.get('observed') else 'check_on' if completed else 'check_off'
                tree.insert(zones[region], 'end', iid=check['id'], text=' ' + name, image=self.images[box],
                            values=(label, reward, kind), tags=(state_key,))
                visible += 1
            theme.fit_tree(tree, self.fonts)
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
                if self.busy or self.tracker is None:
                    return 'break'
                selection = widget.selection()
                if selection and not selection[0].startswith('zone::'):
                    ident = selection[0]
                    try:
                        if self.tracker.check_state(ident).get('observed'):
                            self.notify('The save confirms this location: its box follows the game.')
                            return 'break'
                        self.tracker.set_completed(ident, not self.tracker.check_state(ident).get('completed', False))
                        self.render_tracker()
                    except Exception as error:
                        self.error(error)
                    return 'break'
            def click(event, widget=tree):
                # The box at the start of a row marks it; the rest of the row only selects it.
                ident = widget.identify_row(event.y)
                if not ident or ident.startswith('zone::') or not widget.identify_element(event.x, event.y).endswith('image'):
                    return None
                widget.selection_set(ident)
                widget.focus(ident)
                return toggle(widget=widget)
            tree.bind('<Button-1>', click)
            tree.bind('<space>', toggle)
            if not visible:
                ttk.Label(container, text='No location matches the filters.', style='Muted.TLabel').pack(anchor='w', pady=(5, 0))
        if self.tracker:
            count_done = sum(bool(state.get('completed')) for state in states.values())
            count_access = sum(not state.get('completed') and state.get('access') == 'available' for state in states.values())
            count_unknown = sum(not state.get('completed') and state.get('access', 'unknown') == 'unknown' for state in states.values())
            count_partial = sum(not state.get('completed') and state.get('access') == 'partial' for state in states.values())
            count_blocked = sum(not state.get('completed') and state.get('access') == 'blocked' for state in states.values())
            total = len(self.current_checks)
            self.tracker_counts = {'done': count_done, 'total': total, 'available': count_access}
            for key, value in [('available', count_access), ('blocked', count_blocked),
                               ('unknown', count_unknown + count_partial), ('done', count_done), ('all', total)]:
                self.counters[key][1].configure(text=str(value))
            self.tracker_summary.set({
                'keys': 'Small keys: found / total, updated when the game saves. Boss key: real time.',
                'souls': 'A family soul is listed in every zone where its enemies appear.',
            }.get(self.tracker_view, 'Tick the box of a location to mark it by hand; a greyed box is confirmed by the save.'
                  + (f'   Unknown includes {count_partial} in a partly reachable zone.' if count_partial else '')))
        else:
            self.tracker_counts = None
            for frame, count, label in self.counters.values():
                count.configure(text='–')
        self.render_keys()
        self.render_souls()
        self.place_view_tabs()
        self.update_tracker_notice()
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
        self.view_switch.parts['souls'][1].configure(text=f'Souls  {len(owned)}/{len(names)}' if names else 'Souls')
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
        """The Keys and Souls views exist only when the seed has keys / souls to show."""
        has = {'keys': bool(self.keys_shown), 'souls': bool(self.souls_shown)}
        for key, present in has.items():
            self.view_switch.show(key, present)
        if self.tracker_view in has and not has[self.tracker_view]:
            self.set_tracker_view('locations')

    def zone_bar(self, done, total, width=48):
        """Progress image drawn before a zone name (one image per filled width, kept)."""
        filled = round(width * done / total) if total else 0
        if done and not filled:
            filled = 1   # something found shows
        cache = self.__dict__.setdefault('zone_bars', {})
        if filled not in cache:
            cache[filled] = theme.progress_bar(filled, width)
        return cache[filled]


    def render_keys(self):
        """The dungeon keys card: small keys found / total and the boss key, per dungeon."""
        if not hasattr(self, 'keys_rows'):
            return
        rows = self.tracker.keys() if self.tracker else []
        small = [s for _, s, _ in rows if s]
        found, total = sum(s[0] for s in small), sum(s[1] for s in small)
        self.view_switch.parts['keys'][1].configure(text=f'Keys  {found}/{total}' if small else 'Keys')
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
            self.notify('The in-game overlay only exists on Windows.')
            return
        try:
            if not self.hud:
                hookshot = self.hookshot_root()
                romfs = hookshot / 'romfs' if hookshot else None
                icons = game_overlay.IconCache(STATE / 'icons', romfs, self.nup.get() or None)
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
        if self.tracker_view == 'souls':
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
                    self.show_status_bar(False)
                    if not silent:
                        self.error('Update failed: ' + str(payload[0]))
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
                    self.show_status_bar(False)
                    for button in (self.generate_button, self.qol_button):
                        button.state(['!disabled'])
                    if kind == 'error':
                        self.render_parties()
                        if self.party_job_paused:
                            self.party_job_paused = False
                            if not self.restore_party():
                                self.load_tracker()
                                self.start_turbo()
                        self.error(payload)
                    else:
                        callback, value = payload
                        try:
                            callback(value)
                        except Exception as error:
                            self.error(error)
        except queue.Empty:
            pass
        self._schedule_after(100, self.poll)

    def save_extra_emulators(self):
        text = self.extra_emulators.get().strip()
        live_memory.set_extra_emulators(text)
        if text != (self.app_state.get('extra_emulators') or ''):
            self.write_app_state(extra_emulators=text)

    # ------------------------------------------------------- updates
    def check_for_updates(self, silent):
        if self.updating == 'install':
            if not silent:
                self.notify('The update is being downloaded.')
            return
        if self.updating == 'check':
            self.update_silent = self.update_silent and silent   # a click shows the running check's answer
            return
        self.updating, self.update_silent = 'check', silent
        experimental = self.experimental_updates.get()

        def worker():
            try:
                self.events.put(('update-found', (updater.latest_release(experimental=experimental), silent)))
            except Exception as error:   # any failure must release ``self.updating``
                self.events.put(('update-error', (error, silent)))
        threading.Thread(target=worker, daemon=True).start()

    def update_found(self, release, silent):
        silent = silent and self.update_silent
        self.updating = False
        if release is None:
            if not silent:
                self.notify(f'You have the latest version ({APP_VERSION}).')
            return
        notes = release.notes.strip()
        notes = ('\n\n' + (notes[:600] + '…' if len(notes) > 600 else notes)) if notes else ''
        if updater.is_prerelease(release.version):
            notes = '\n\nExperimental version: it may contain bugs.' + notes
        elif not updater.is_newer(release.version, APP_VERSION):
            notes = ('\n\nThis is the latest stable version: it replaces the experimental version you have. '
                     'A seed made with the experimental version may not work with it.') + notes
        title = f'Version {release.version} is available (you have {APP_VERSION})'
        if not updater.can_self_update():
            self.show_notice('info', title, notes.strip(), [('Open the release page', lambda: webbrowser.open(release.page)),
                                                             ('Not now', self.clear_notices)])
            return
        self.show_notice('info', title, (notes.strip() + '\n\n' if notes.strip() else '')
                         + 'The application restarts after the installation; your seeds and settings are kept.',
                         [('Download and install', lambda: self.install_update(release)), ('Not now', self.clear_notices)])

    def install_update(self, release):
        self.clear_notices()
        if self.busy:
            self.notify('Wait for the generation to finish, then check again.')
            return
        self.updating = 'install'
        self.status.set(f'Downloading version {release.version}…')
        self.show_status_bar(True)

        def worker():
            try:
                self.events.put(('update-installed', updater.install(release, lambda m: self.events.put(('progress', m)))))
            except Exception as error:   # any failure must release ``self.updating``
                self.events.put(('update-error', (error, False)))
        threading.Thread(target=worker, daemon=True).start()

    def update_installed(self, target):
        self.updating = False
        self.show_status_bar(False)
        def restart():
            if self.close():
                updater.restart(target)   # only once this instance is gone: never two running
        self.show_notice('info', 'The new version is installed', 'Restart to use it.',
                         [('Restart now', restart), ('Later', self.clear_notices)])

    def error(self, error):
        """A banner in the current page: the problem, then what helps (no window)."""
        text = str(error)
        title, _, rest = text.partition('\n')
        actions = []
        if any(word in text for word in ('NUP', 'mods folder', 'Setup')):
            actions.append(('Open Setup', lambda: self.show_page('setup')))
        actions.append(('Copy the details', lambda: self.copy_text(text)))
        log = error_log()
        try:
            recent = log.is_file() and datetime.now().timestamp() - log.stat().st_mtime < 120
        except OSError:
            recent = False
        if recent:
            actions.append(('Open the error log', lambda: self.open_path(log)))
        self.show_notice('error', title, rest.strip(), actions)

    def open_path(self, path):
        try:
            if os.name == 'nt':
                os.startfile(str(path))
            else:
                webbrowser.open(Path(path).resolve().as_uri())
        except OSError as error:
            self.show_notice('error', 'Could not open ' + str(path), str(error))


    def close(self):
        """Close the application; False when the player kept it open."""
        if self.busy:
            self.notify('Wait for the generation to finish before closing.')
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
        self._cancel_all_after()
        self.root.destroy()
        return True


def main(argv=None):
    from multiprocessing import freeze_support
    freeze_support()
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
