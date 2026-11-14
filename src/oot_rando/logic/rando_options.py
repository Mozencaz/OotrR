"""Archipelago-style options of the complete randomizer.

Each option keeps its AP OoT name and values so that an AP YAML can be imported.
A value is *supported* only when the generator changes the game **and** the
solver consistently. Unsupported values stay visible in the interface, greyed,
with their reason, and the backend refuses them.
"""
from dataclasses import dataclass

OK = None  # marker: supported value


@dataclass(frozen=True)
class Option:
    name: str
    tab: str
    label: str
    values: tuple            # ((value, label, reason_or_None), …) or None for bool
    default: object
    help: str = ''
    kind: str = 'choice'     # choice | bool | int | items (AP item name -> count)
    minimum: int = 0
    maximum: int = 0
    supported_ints: tuple = ()
    experimental: tuple = ()  # supported values requiring an in-game pilot

    def supported(self, value):
        if self.kind == 'items':
            return True
        if self.kind == 'bool':
            return dict(self.values)[value] is OK
        if self.kind == 'int':
            return value in self.supported_ints
        return any(v == value and reason is OK for v, _, reason in self.values)

    def reason(self, value):
        if self.kind == 'items':
            return None
        if self.kind == 'bool':
            return dict(self.values).get(value)
        if self.kind == 'int':
            return None if value in self.supported_ints else 'Value differs from the vanilla game: no adapter.'
        for v, _, reason in self.values:
            if v == value:
                return reason
        return 'Unknown value.'

    def allowed(self):
        if self.kind == 'items':
            return ()
        if self.kind == 'bool':
            return (False, True)
        if self.kind == 'int':
            return tuple(range(self.minimum, self.maximum + 1))
        return tuple(v for v, _, _ in self.values)


NO_ADAPTER = 'No proven game adapter for this value.'
PILOT = ('Adapter built and checked statically; in-game behaviour still to be confirmed by a pilot. '
         'Every ticked category is shuffled together.')
NO_EVENT = 'Event or NPC: reward adapter still to be written and proven in game.'
GENERIC_KEYS = 'Remake keys are generic (credited to the current dungeon): impossible outside the dungeon.'
# Items that can be held from the start (silent pouch add at the end of the opening).
# Songs, tunics, trade items and dungeon items have no pouch actor of their own yet.
STARTABLE_ITEMS = (
    'Kokiri Sword', 'Biggoron Sword', 'Deku Shield', 'Hylian Shield', 'Mirror Shield',
    'Slingshot', 'Bow', 'Boomerang', 'Progressive Hookshot', 'Megaton Hammer', 'Lens of Truth',
    'Bomb Bag', 'Bombchus (10)', 'Ice Arrows', 'Light Arrows', 'Dins Fire', 'Farores Wind', 'Nayrus Love',
    'Iron Boots', 'Hover Boots', 'Progressive Strength Upgrade', 'Progressive Scale', 'Progressive Wallet',
    'Deku Nut Capacity', 'Deku Stick Capacity', 'Magic Meter', 'Double Defense', 'Ocarina', 'Bottle',
    'Bottle with Milk', 'Zeldas Letter', 'Stone of Agony', 'Heart Container', 'Piece of Heart',
    'Gold Skulltula Token', 'Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire', 'Forest Medallion',
    'Fire Medallion', 'Water Medallion', 'Spirit Medallion', 'Shadow Medallion', 'Light Medallion',
)
MAX_START_COUNT = 100

OPTIONS = [
    # ------------------------------------------------------------------ Logic
    Option('logic_rules', 'Logic', 'Logic rules',
           (('glitchless', 'Glitchless (AP glitchless)', OK),
            ('glitched', 'Glitched', 'The N64 glitched rules do not describe the remake.'),
            ('no_logic', 'No logic', 'Refused: may block the game.')), 'glitchless',
           'Built-in glitchless logic (remake world).'),
    Option('logic_tricks', 'Logic', 'Tricks',
           (('none', 'None (AP default)', OK),
            ('custom', 'Custom list', 'N64 tricks are not checked in the remake.')), 'none'),
    Option('accessibility', 'Logic', 'Accessibility',
           (('full', 'Every location reachable', OK),
            ('minimal', 'Only victory guaranteed', OK)), 'full',
           'Always checked by a second, independent solver after placement.'),
    Option('logic_no_night_tokens_without_suns_song', 'Logic',
           'Night skulltulas without Sun\'s Song out of logic',
           ((False, OK), (True, OK)), False, "Night skulltulas count only with the Ocarina and Sun's Song.",
           kind='bool'),
    # ------------------------------------------------------------------ World
    Option('open_kakariko', 'World', 'Kakariko gate',
           (('closed', 'Closed (Zelda\'s Letter)', OK), ('zelda', 'Open after the letter', NO_ADAPTER),
            ('open', 'Open', NO_ADAPTER)), 'closed'),
    Option('open_door_of_time', 'World', 'Door of Time open',
           ((False, OK), (True, NO_ADAPTER)), False, kind='bool'),
    Option('zora_fountain', 'World', 'King Zora',
           (('closed', 'Ruto\'s Letter required', OK), ('adult', 'Moved for adult', NO_ADAPTER),
            ('open', 'Always moved', NO_ADAPTER)), 'closed'),
    Option('gerudo_fortress', 'World', 'Gerudo Fortress',
           (('normal', 'Four carpenters', OK), ('fast', 'One carpenter', NO_ADAPTER),
            ('open', 'Open', NO_ADAPTER)), 'normal'),
    Option('starting_age', 'World', 'Starting age',
           (('child', 'Child', OK), ('adult', 'Adult', NO_ADAPTER), ('random', 'Random', NO_ADAPTER)), 'child'),
    # ------------------------------------------------------------------- Goal
    Option('bridge', 'Goal', 'Rainbow Bridge',
           (('vanilla', 'Shadow and Spirit medallions (vanilla)', OK), ('open', 'Open', NO_ADAPTER),
            ('stones', 'Stones', NO_ADAPTER), ('medallions', 'Medallions', NO_ADAPTER),
            ('dungeons', 'Dungeons', NO_ADAPTER), ('tokens', 'Skulltulas', NO_ADAPTER),
            ('hearts', 'Hearts', NO_ADAPTER)), 'vanilla'),
    Option('trials', 'Goal', 'Ganon\'s Castle trials', None, 6, kind='int',
           minimum=0, maximum=6, supported_ints=(6,), help='The remake keeps all six trials.'),
    Option('shuffle_ganon_bosskey', 'Goal', 'Ganon\'s Boss Key',
           (('vanilla', 'Vanilla', OK), ('remove', 'Removed', NO_ADAPTER), ('dungeon', 'In the castle', NO_ADAPTER),
            ('medallions', 'Medallions', NO_ADAPTER), ('stones', 'Stones', NO_ADAPTER),
            ('dungeons', 'Dungeons', NO_ADAPTER), ('tokens', 'Skulltulas', NO_ADAPTER)), 'vanilla'),
    Option('triforce_hunt', 'Goal', 'Triforce hunt', ((False, OK), (True, NO_ADAPTER)), False, kind='bool'),
    # ------------------------------------------------------------------ Items
    Option('shuffle_chests', 'Items', 'Content of every chest (major items included)',
           ((False, OK), (True, OK)), True, 'Drop__DropActor mechanism already validated in game on four chests.',
           kind='bool', experimental=(True,)),
    Option('chest_matching', 'Items', 'Remake ↔ AP chest matching',
           (('strict', 'Strict (safe)', OK), ('scene', 'By zone (heuristic)', OK)), 'strict',
           'Strict: progression only goes into identified chests. By zone: more chests, '
           'with the strictest access rule of the zone.', experimental=('scene',)),
    Option('shuffle_kokiri_sword', 'Items', 'Shuffle the Kokiri Sword', ((False, OK), (True, OK)), True,
           kind='bool', experimental=(True,)),
    Option('shuffle_remake_items', 'Items', 'Shuffle remake-only Deku seeds and jars',
           ((False, OK), (True, OK)), True, 'Items absent from the AP logic: moved as filler.', kind='bool'),
    Option('progressive_order', 'Items', 'Progressive items in order (hookshot before longshot…)',
           ((False, OK), (True, OK)), True,
           'Always the case: each copy found gives the level above the one held. No effect, kept for '
           'older settings.', kind='bool'),
    Option('progressive_strict', 'Items', 'Strict order: the higher level requires the previous one',
           ((False, OK), (True, OK)), False,
           'Always the case: a level is only given above the previous one. No effect, kept for older '
           'settings.', kind='bool'),
    Option('shuffle_song_items', 'Items', 'Songs',
           (('song', 'Vanilla', OK), ('dungeon', 'Dungeon rewards', NO_EVENT), ('any', 'Anywhere', NO_EVENT)), 'song'),
    Option('shopsanity', 'Items', 'Shops (items shuffled per shop)',
           (('off', 'Vanilla', OK), ('1', '1 item per shop', OK), ('2', '2 items', OK),
            ('3', '3 items', OK), ('4', '4 items', OK), ('random', '1 to 4 random items', OK)), 'off',
           PILOT + ' Fixed price of 10 rupees; at least one copy of each purchase useful to the logic stays on sale. '
           'Masks not included.', experimental=('1', '2', '3', '4', 'random')),
    Option('tokensanity', 'Items', 'Gold Skulltulas',
           (('off', 'Vanilla', OK), ('dungeons', 'Dungeons', OK), ('overworld', 'Overworld', OK),
            ('all', 'All', OK)), 'off',
           PILOT + ' The skulltula drops the placed item; tokens may come from other sources.',
           experimental=('dungeons', 'overworld', 'all')),
    Option('shuffle_scrubs', 'Items', 'Business Scrubs',
           (('off', 'Vanilla', OK), ('low', 'Low price (10 rupees)', OK), ('regular', 'Remake price', OK),
            ('random', 'Random prices (10 to 99 rupees)', OK)), 'off',
           PILOT + ' Single-sale remake scrubs: stick upgrade (Lost Woods bridge), nut upgrade '
           '(Lost Woods), field and crater heart pieces. "Remake price": 40 and 100 rupees '
           '(100 needs the Adult\'s Wallet). The scrub still announces its vanilla item; the item given '
           'is the placed one. Refill scrubs (3 items) and Dream World scrubs not included.',
           experimental=('low', 'regular', 'random')),
    Option('shuffle_cows', 'Items', 'Cows', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_ocarinas', 'Items', 'Ocarinas', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_child_trade', 'Items', 'Child trade quest',
           (('vanilla', 'Vanilla', OK), ('shuffle', 'Shuffled', NO_EVENT), ('skip_child_zelda', 'Skip Zelda', NO_EVENT)), 'vanilla'),
    Option('shuffle_gerudo_card', 'Items', 'Gerudo Card', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_beans', 'Items', 'Magic beans', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_medigoron_carpet_salesman', 'Items', 'Medigoron and carpet salesman',
           ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_freestanding_items', 'Items', 'Freestanding items (heart pieces, rupees, hearts)',
           (('off', 'Vanilla', OK), ('dungeons', 'Dungeons', OK), ('overworld', 'Overworld', OK),
            ('all', 'All', OK)), 'off', PILOT, experimental=('dungeons', 'overworld', 'all')),
    Option('shuffle_npc_gifts', 'Items', 'NPC gifts and minigames',
           ((False, OK), (True, OK)), False,
           PILOT + ' Out of scope: trades up to the Biggoron Sword, songs, boss rewards, '
           'child trade, cows, masks, great fairies.', kind='bool', experimental=(True,)),
    Option('shuffle_boss_rewards', 'Items', 'Bosses and dungeon rewards',
           ((False, OK), (True, OK)), False,
           'Spiritual stones, medallions (Rauru\'s included) and boss heart containers. Vanilla cutscene kept, only the item given changes. To be validated in game. '
           'The shuffled heart container is placed as soon as the boss room is entered.', kind='bool', experimental=(True,)),
    Option('shuffle_great_fairies', 'Items', 'Great Fairies',
           ((False, OK), (True, OK)), False,
           'Spells (Din, Farore, Nayru), magic, double magic and double defense. Vanilla cutscene kept, only the item given changes. To be validated in game.',
           kind='bool', experimental=(True,)),
    Option('shuffle_quest_rewards', 'Items', 'Quest rewards',
           ((False, OK), (True, OK)), False,
           'Fairy Ocarina (Saria), Ocarina of Time, Zelda\'s Letter, Light Arrows, Biggoron Sword. '
           'Vanilla cutscene kept, only the item given changes. To be validated in game. Out of scope: trade items, songs.', kind='bool', experimental=(True,)),
    Option('shuffle_pots', 'Items', 'Pots (as checks)',
           (('off', 'Vanilla', OK), ('all', 'All', OK)), 'off',
           PILOT + ' Only pots with an explicit drop; a pot respawns: its item can be picked up again.',
           experimental=('all',)),
    Option('shuffle_crates', 'Items', 'Crates (as checks)',
           (('off', 'Vanilla', OK), ('all', 'All', OK)), 'off', PILOT, experimental=('all',)),
    Option('shuffle_beehives', 'Items', 'Beehives', ((False, OK), (True, OK)), False, PILOT, kind='bool',
           experimental=(True,)),
    Option('shuffle_bushes', 'Items', 'Bushes and grass (as checks)', ((False, OK), (True, OK)), False,
           PILOT + ' Only grass with an explicit drop; regrowing variants excluded.', kind='bool',
           experimental=(True,)),
    Option('shuffle_rocks', 'Items', 'Rocks and stones (as checks)', ((False, OK), (True, OK)), False,
           PILOT, kind='bool', experimental=(True,)),
    Option('shuffle_frog_song_rupees', 'Items', 'Frog song rupees', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('start_inventory_from_pool', 'Items', 'Starting inventory',
           None, {}, 'Items held from the start (copies taken out of the item pool). Hearts: '
           '"Heart Container" or "Piece of Heart". Songs and tunics are not available yet.', kind='items'),
    Option('item_pool_value', 'Items', 'Item pool',
           (('balanced', 'Balanced', OK), ('plentiful', 'Plentiful (one extra copy of the major items)', OK),
            ('scarce', 'Scarce (fewer bottles and hearts)', OK),
            ('minimal', 'Minimal (one bottle, no extra hearts)', OK)), 'balanced',
           'Applies to the shuffled locations only (their count never changes): extra copies '
           'replace rupees and other filler, removed copies become rupees.'),
    # --------------------------------------------------------------- Dungeons
    Option('shuffle_mapcompass', 'Dungeons', 'Maps and compasses',
           (('vanilla', 'Vanilla', OK), ('dungeon', 'In their dungeon', OK), ('remove', 'Removed', OK),
            ('startwith', 'Start with', OK), ('any_dungeon', 'Any dungeon', GENERIC_KEYS),
            ('overworld', 'Overworld', GENERIC_KEYS), ('keysanity', 'Anywhere', GENERIC_KEYS)), 'dungeon',
           '"Start with": every map and compass is held from the start; their chests hold other items.',
           experimental=('startwith',)),
    Option('shuffle_smallkeys', 'Dungeons', 'Small keys',
           (('vanilla', 'Vanilla', OK),
            ('dungeon', 'In their dungeon (key rings)', OK),
            ('remove', 'Removed (all keys from the start)', OK),
            ('any_dungeon', 'Any dungeon (key rings)', OK), ('overworld', 'Overworld (key rings)', OK),
            ('keysanity', 'Anywhere (key rings)', OK)), 'vanilla',
           'Except for "Vanilla", small keys become one key ring per dungeon (Key rings option '
           '= All dungeons): remake keys are generic, only a dungeon-specific key ring '
           'can be placed elsewhere. Small key chests receive other items.',
           experimental=('dungeon', 'remove', 'any_dungeon', 'overworld', 'keysanity')),
    Option('shuffle_hideoutkeys', 'Dungeons', 'Gerudo hideout keys',
           (('vanilla', 'Guards', OK), ('overworld', 'Overworld', NO_EVENT), ('keysanity', 'Anywhere', NO_EVENT)), 'vanilla'),
    Option('shuffle_bosskeys', 'Dungeons', 'Boss keys',
           (('vanilla', 'Vanilla', OK), ('dungeon', 'In their dungeon', OK),
            ('remove', 'Removed (boss keys from the start)', OK),
            ('any_dungeon', 'Any dungeon', OK), ('keysanity', 'Anywhere', OK)), 'vanilla',
           'Outside their dungeon, each boss key becomes a dungeon-specific item ("Boss Key: …") '
           'that opens the boss door of that dungeon wherever it is found. Ganon\'s key: option of the Goal tab.',
           experimental=('dungeon', 'remove', 'any_dungeon', 'keysanity')),
    Option('key_rings', 'Dungeons', 'Key rings',
           (('off', 'None', OK), ('all', 'All dungeons', OK), ('choose', 'Chosen', NO_ADAPTER),
            ('random', 'Random', NO_ADAPTER)), 'off',
           'One key ring per dungeon (Forest, Fire, Water, Shadow, Spirit, Well, Gerudo Training Ground, Ganon\'s Castle): '
           'all its small keys at once, wherever it is found. Required as soon as small '
           'keys leave their place.', experimental=('all',)),
    Option('dungeon_shortcuts', 'Dungeons', 'Dungeon shortcuts', (('off', 'None', OK), ('all', 'All', NO_ADAPTER)), 'off'),
    # ------------------------------------------------------------------ Souls
    Option('shuffle_enemy_spawns', 'Souls', 'Enemy souls',
           (('off', 'Off', OK), ('bosses', 'Bosses only', OK), ('regional', 'One soul per region', OK),
            ('all', 'One soul per enemy type', OK)), 'off',
           'An enemy only appears once its soul is obtained (OoTR Dev-Rob). Logic: each dungeon or boss '
           'room requires the souls present there. A new save is required.',
           experimental=('bosses', 'regional', 'all')),
    # -------------------------------------------------------- Quality of life
    Option('skip_child_zelda', 'Quality of life', 'Skip meeting child Zelda', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('no_escape_sequence', 'Quality of life', 'Skip the castle escape', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('no_guard_stealth', 'Quality of life', 'Skip the castle stealth section', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('no_epona_race', 'Quality of life', 'Epona without the race', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('fast_chests', 'Quality of life', 'Fast chest opening', ((False, OK), (True, OK)), False,
           'Same patch as "Chests without cutscene" in the setup: the lid opens and Link holds the item up.',
           kind='bool'),
    Option('free_scarecrow', 'Quality of life', 'Free scarecrow', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('big_poe_count', 'Quality of life', 'Big Poes to bring back', None, 10, kind='int', minimum=1, maximum=10,
           supported_ints=(10,)),
    Option('chicken_count', 'Quality of life', 'Cuccos to bring back', None, 7, kind='int', minimum=0, maximum=7,
           supported_ints=(7,)),
]
BY_NAME = {option.name: option for option in OPTIONS}
TABS = ('Logic', 'World', 'Goal', 'Items', 'Dungeons', 'Souls', 'Quality of life')
OUT_OF_SCOPE = ('Entrance shuffle, Master Quest, multiworld and gossip stone hints: out of scope '
                'for this version, AP default values enforced (no shuffling).')


def defaults():
    return {option.name: (dict(option.default) if isinstance(option.default, dict) else option.default)
            for option in OPTIONS}


def parse_items(text):
    """``"Hover Boots, Progressive Hookshot x2"`` → ``{'Hover Boots': 1, 'Progressive Hookshot': 2}``."""
    import re
    result = {}
    for part in (p.strip() for p in str(text).replace(';', ',').split(',')):
        if not part:
            continue
        match = re.fullmatch(r'(.+?)\s*(?:[x×*]\s*(\d+))?', part, re.IGNORECASE)
        name, count = match.group(1).strip(), int(match.group(2) or 1)
        canonical = next((i for i in STARTABLE_ITEMS if i.casefold() == name.casefold()), None)
        if canonical is None:
            raise ValueError(f'Unknown or unavailable starting item: {name}')
        result[canonical] = result.get(canonical, 0) + count
    return result


def format_items(items):
    return ', '.join(name if count == 1 else f'{name} x{count}' for name, count in sorted(items.items()))


def validate(values, supported_only=False):
    if not isinstance(values, dict):
        raise ValueError('Invalid full randomizer options.')
    unknown = set(values) - set(BY_NAME)
    if unknown:
        raise ValueError('Unknown options: ' + ', '.join(sorted(unknown)))
    result = defaults()
    result.update(values)
    for name, value in result.items():
        option = BY_NAME[name]
        if option.kind == 'items':
            if (not isinstance(value, dict) or any(item not in STARTABLE_ITEMS for item in value)
                    or any(type(n) is not int or not 1 <= n <= MAX_START_COUNT for n in value.values())):
                raise ValueError(f'{name}: unknown item or invalid count.')
            result[name] = dict(sorted(value.items()))
        elif option.kind == 'bool':
            if type(value) is not bool:
                raise ValueError(f'{name} must be a boolean.')
        elif option.kind == 'int':
            if type(value) is not int or not option.minimum <= value <= option.maximum:
                raise ValueError(f'{name} must be an integer between {option.minimum} and {option.maximum}.')
        elif value not in option.allowed():
            raise ValueError(f'Unknown value for {name}: {value!r}')
        if supported_only and not option.supported(value):
            raise ValueError(f'{option.label} = {value!r}: {option.reason(value)}')
    if supported_only:
        moved = result['shuffle_smallkeys'] not in ('vanilla', 'remove')
        if moved and result['key_rings'] != 'all':
            raise ValueError('Small keys out of their place: set "Key rings" to "All '
                             'dungeons" (remake keys are generic).')
        if result['key_rings'] == 'all' and not moved:
            raise ValueError('Key rings: choose where the small keys go (not "Vanilla").')
    return result


def experimental_choices(values):
    return sorted(f'{BY_NAME[n].label} = {v}' for n, v in values.items() if v in BY_NAME[n].experimental)


PRESETS = {
    'ap_defaults': {'label': 'AP glitchless — defaults', 'values': {}},
    'everything': {'label': 'Everything shuffled (available values)', 'values': {
        'shuffle_chests': True, 'shuffle_kokiri_sword': True, 'shuffle_remake_items': True,
        'shuffle_mapcompass': 'dungeon', 'shuffle_smallkeys': 'vanilla', 'shuffle_bosskeys': 'dungeon',
        'shuffle_enemy_spawns': 'all', 'chest_matching': 'scene', 'progressive_order': True,
        'tokensanity': 'all', 'shopsanity': '4', 'shuffle_freestanding_items': 'all', 'shuffle_npc_gifts': True,
        'shuffle_boss_rewards': True, 'shuffle_great_fairies': True, 'shuffle_quest_rewards': True,
        'shuffle_pots': 'all', 'shuffle_crates': 'all', 'shuffle_beehives': True, 'shuffle_bushes': True,
        'shuffle_rocks': True, 'shuffle_scrubs': 'low'}},
    'prudent': {'label': 'Prudent (chests except keys, no souls)', 'values': {
        'shuffle_chests': True, 'shuffle_kokiri_sword': False, 'shuffle_mapcompass': 'vanilla',
        'shuffle_smallkeys': 'vanilla', 'shuffle_bosskeys': 'vanilla', 'shuffle_enemy_spawns': 'off'}},
}


def preset(name):
    values = defaults()
    values.update(PRESETS[name]['values'])
    return values


def from_ap_yaml(text):
    """Import the OoT section of an AP YAML. Returns (values, ignored_messages)."""
    try:
        import yaml
    except ImportError as error:
        raise ValueError('PyYAML is needed to import an Archipelago YAML.') from error
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError('Invalid Archipelago YAML.')
    section = document.get('Ocarina of Time') or document.get('oot')
    if not isinstance(section, dict):
        raise ValueError('"Ocarina of Time" section missing from the YAML.')
    values, ignored = defaults(), []
    extra = document.get('OoT Remake')
    items = list(section.items()) + (list(extra.items()) if isinstance(extra, dict) else [])
    for key, raw in items:
        if key == 'open_forest':
            ignored.append('open_forest: set by "Open the way" in the setup')
            continue
        if key == 'start_inventory':
            key = 'start_inventory_from_pool'
        if key not in BY_NAME:
            ignored.append(f'{key}: option not carried over in this version')
            continue
        if BY_NAME[key].kind == 'items':
            kept = {}
            for item, count in (raw or {}).items() if isinstance(raw, dict) else ():
                if item in STARTABLE_ITEMS and type(count) is int and 1 <= count <= MAX_START_COUNT:
                    kept[item] = kept.get(item, 0) + count
                else:
                    ignored.append(f'{key}: {item} not available as a starting item')
            values[key] = dict(sorted(kept.items()))
            continue
        if isinstance(raw, dict):
            weighted = [(k, w) for k, w in raw.items() if isinstance(w, (int, float)) and w > 0]
            if len(weighted) != 1:
                ignored.append(f'{key}: several weighted values not supported')
                continue
            raw = weighted[0][0]
        option = BY_NAME[key]
        if option.kind == 'bool':
            raw = raw if isinstance(raw, bool) else str(raw).lower() in ('true', 'on', '1')
        elif option.kind == 'int':
            try:
                raw = int(raw)
            except (TypeError, ValueError):
                ignored.append(f'{key}: integer expected')
                continue
        elif key == 'logic_tricks':
            raw = 'none' if not raw else 'custom'
        elif isinstance(raw, bool):
            # YAML 1.1 reads ``off``/``on`` as booleans.
            raw = 'off' if raw is False else 'on'
        elif isinstance(raw, int):
            raw = str(raw)
        if raw not in option.allowed():
            ignored.append(f'{key}: unknown value {raw!r}')
            continue
        values[key] = raw
        if not option.supported(raw):
            ignored.append(f'{key} = {raw!r}: {option.reason(raw)}')
    return values, ignored


REMAKE_ONLY = ('shuffle_chests', 'chest_matching', 'shuffle_remake_items', 'progressive_order',
               'progressive_strict', 'shuffle_enemy_spawns', 'shuffle_npc_gifts', 'shuffle_bushes', 'shuffle_rocks',
               'shuffle_boss_rewards', 'shuffle_great_fairies', 'shuffle_quest_rewards')


def to_ap_yaml(values, name='Player'):
    lines = ['name: ' + name, 'game: Ocarina of Time', 'Ocarina of Time:']
    for option in OPTIONS:
        if option.name in REMAKE_ONLY:
            continue
        value = values[option.name]
        if option.name == 'logic_tricks':
            value = '[]'
        elif option.kind == 'items':
            import json
            value = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            value = 'true' if value else 'false'
        lines.append(f'  {option.name}: {value}')
    lines.append('# Remake-only options, read by this application only:')
    lines.append('OoT Remake:')
    for name in REMAKE_ONLY:
        value = values[name]
        lines.append(f'  {name}: {str(value).lower() if isinstance(value, bool) else value}')
    return '\n'.join(lines) + '\n'


# Randomization tab: each category checkbox drives these complete-mode options
# ((option, value when checked, value when unchecked), …). Categories absent
# here have no proven adapter and stay greyed in complete mode.
CATEGORY_OPTIONS = {
    'world_chests': (('shuffle_chests', True, False),),
    'pots': (('shuffle_pots', 'all', 'off'),),
    'bushes': (('shuffle_bushes', True, False),),
    'crates': (('shuffle_crates', 'all', 'off'),),
    'rocks': (('shuffle_rocks', True, False),),
    'beehives': (('shuffle_beehives', True, False),),
    'npc_gifts': (('shuffle_npc_gifts', True, False),),
    'minigames': (('shuffle_npc_gifts', True, False),),
    'quest_rewards': (('shuffle_quest_rewards', True, False),),
    'boss_rewards': (('shuffle_boss_rewards', True, False),),
    'fairies': (('shuffle_great_fairies', True, False),),
    'skulltulas': (('tokensanity', 'all', 'off'),),
    'shops': (('shopsanity', '4', 'off'),),
    'loose_items': (('shuffle_freestanding_items', 'all', 'off'),),
    'dungeon_items': (('shuffle_mapcompass', 'dungeon', 'vanilla'), ('shuffle_bosskeys', 'dungeon', 'vanilla')),
    'scrubs': (('shuffle_scrubs', 'low', 'off'),),
}


def category_checked(values, category):
    return any(values[option] != off for option, _, off in CATEGORY_OPTIONS[category])


def set_category(values, category, checked):
    """Return a copy of ``values`` with the options of ``category`` switched."""
    result = dict(values)
    for option, on, off in CATEGORY_OPTIONS[category]:
        result[option] = on if checked else off
    return result
