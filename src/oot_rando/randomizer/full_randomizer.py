"""Complete glitchless randomizer: pool, assumed fill, verification, progressive tokens.

Placement only; writing game files is done by :func:`build` callers. The RNG is
SHA-256 counter based (rejection sampling), independent of Python's ``random``.
"""
from collections import Counter, defaultdict
import hashlib
from dataclasses import dataclass
from typing import Callable

from oot_rando.logic.rules import Logic, age_member, vanilla_placements
from oot_rando.logic import rando_options
from oot_rando.logic.rando_options import ap_settings  # noqa: F401  (moved to logic, re-exported)
from oot_rando.game.remake_world import (PROGRESSIVE, BASE_REQUIRED, STATIC_TIER_SOURCES, static_tier_gid, item_actor,
                          match_locations, coverage_summary, FOLDER_DUNGEON,
                          ZONE_LABELS, TRACKED_TYPES, location_zone, source_age, zone_label,
                          TREASURE_GAME_REWARD)
from oot_rando.game.item_forms import can_take, form_actor, underwater_actor
from oot_rando.game.extra_sources import match_sources, area_locations
from oot_rando.patching.soul_adapter import plan_souls, chest_requirements, soul_label
from oot_rando.patching.song_adapter import POSE_AFTER_CUTSCENE, is_song_actor, song_allowed
from oot_rando.game.extra_sources import BOSS_HEARTS
from oot_rando.game.extra_sources import CHILD_WALLET
from oot_rando.game.extra_sources import scrub_price
from oot_rando.game.remake_world import FOLDER_AP_DUNGEON as _AP_DUNGEON
from oot_rando.game.remake_world import rule_members
from oot_rando.patching.key_adapter import BOSS_KEY_DUNGEONS
from oot_rando.patching.key_adapter import RING_DUNGEONS
from oot_rando.patching.key_adapter import ring_item
from oot_rando.patching.key_adapter import small_key_item
from oot_rando.patching.key_adapter import small_key_item as _small_key
from oot_rando.patching.key_adapter import start_logic_items
from oot_rando.catalog.traps import is_trap_item, planned_traps

FILLER_PRIORITY = ('Rupee (1)', 'Rupees (5)', 'Deku Nuts (5)', 'Deku Stick (1)', 'Arrows (5)', 'Bombs (5)',
                   'Rupees (20)', 'Arrows (10)', 'Deku Seeds (30)', 'Bombchus (5)', 'Arrows (30)',
                   'Remake: Scrub Seed', 'Rupees (50)', 'Remake: Magic Jar', 'Rupees (200)')
MAX_ATTEMPTS = int(__import__("os").environ.get("OOT_MAX_ATTEMPTS", "300"))
# A crate deep under water (``underwater.mark_deep``): adult Link walks to it with
# the Iron Boots and breaks it with the Hookshot (AP's "LH GS Lab Crate" rule).
DEEP_GUARD = 'Souls|Iron Boots|Progressive Hookshot'
SHOP_FILLER = 'Rupees (5)'
POOL_FILLER = 'Rupees (5)'
EMPTY_BOTTLES = ('Bottle', 'Bottle with Milk')
HEARTS = ('Heart Container', 'Piece of Heart')
# Never needed to finish the game: removed by the minimal item pool.
MINIMAL_REMOVED = HEARTS + ('Double Defense', 'Deku Nut Capacity', 'Deku Stick Capacity')


def apply_item_pool(pool, value, relevant, never_extra=()):
    """OoTR-style item pool on the shuffled locations (their number never changes).

    * plentiful: one extra copy of each major non-progressive item, replacing filler;
    * scarce: at most 3 empty bottles, half the hearts;
    * minimal: one empty bottle, no hearts, no double defense or capacity upgrades.
    Removed copies become rupees.
    """
    pool = list(pool)
    if value == 'plentiful':
        for item in sorted(set(i for i in pool if i in relevant and i not in PROGRESSIVE and i not in never_extra)):
            fillers = [i for i in pool if i in FILLER_PRIORITY]
            if not fillers:
                break
            pool.remove(min(fillers, key=FILLER_PRIORITY.index))
            pool.append(item)
        return pool

    def keep_at_most(items, limit):
        held = 0
        for index, item in enumerate(pool):
            if item in items:
                held += 1
                if held > limit:
                    pool[index] = POOL_FILLER

    if value == 'scarce':
        keep_at_most(EMPTY_BOTTLES, 3)
        for heart in HEARTS:
            keep_at_most((heart,), pool.count(heart) // 2)
    elif value == 'minimal':
        keep_at_most(EMPTY_BOTTLES, 1)
        keep_at_most(MINIMAL_REMOVED, 0)
    return pool


def add_fake_traps(pool, spare, level='some'):
    """The traps of option value ``level`` (``catalog.traps.planned_traps``) in ``pool``.

    ``spare``: filler item -> copies that may be replaced. Each trap takes the place of
    one of them, lowest value first, so the number of items never changes; without
    filler left, the remaining traps are not added. Traps are not progression: the
    logic ignores them.
    """
    pool, spare = list(pool), Counter(spare)
    rank = {name: index for index, name in enumerate((GREEN_RUPEE,) + FILLER_PRIORITY)}
    for trap in planned_traps(pool, level):   # most important first, when filler runs out
        fillers = sorted(+spare, key=lambda i: (rank.get(i, len(rank)), i))
        if not fillers:
            break
        cheapest = fillers[0]
        spare[cheapest] -= 1
        # The last copy goes: the pool order stays stable (as in balance_pool).
        pool[len(pool) - 1 - pool[::-1].index(cheapest)] = trap
    return pool


GREEN_RUPEE = 'Rupee (1)'


def balance_pool(pool, slots, removable, keep=None):
    """Make the pool exactly ``slots`` items long (one per shuffled check).

    Too many items: green rupees leave the pool first, then the other filler
    (``removable(item)``), lowest value first (FILLER_PRIORITY). Too few: green
    rupees fill the free checks. ``keep``: item → copies that must stay (the
    green rupees reserved for the skipped castle checks).
    """
    pool = list(pool)
    keep = Counter(keep or {})
    excess = len(pool) - slots
    if excess > 0:
        held = Counter(pool)

        def rank(item):
            if item == GREEN_RUPEE:
                return -1
            return FILLER_PRIORITY.index(item) if item in FILLER_PRIORITY else len(FILLER_PRIORITY)

        candidates = sorted({i for i in pool if removable(i)}, key=rank)
        drop = Counter()
        for item in candidates:
            take = min(excess, held[item] - keep[item])
            if take > 0:
                drop[item] = take
                excess -= take
            if not excess:
                break
        if excess:
            raise FillError(f'{len(pool)} items for {slots} checks and only {len(pool) - slots - excess} '
                            'filler items to remove: enable more checks or reduce the options.')
        kept = []
        for item in reversed(pool):   # the last copies go: the pool order stays stable
            if drop[item]:
                drop[item] -= 1
            else:
                kept.append(item)
        pool = kept[::-1]
    elif excess < 0:
        pool.extend([GREEN_RUPEE] * -excess)
    return pool


# Junk reasons that still allow a source to receive filler.
SAFE_JUNK = ('no_reliable_ap_match', 'remake_only_area')


def enabled_sources(options):
    """Non-chest source families enabled by the options → scope (all/dungeons/overworld)."""
    result = {}
    for source, option, off in (('skulltula', 'tokensanity', 'off'), ('freestanding', 'shuffle_freestanding_items', 'off'),
                                ('shop', 'shopsanity', 'off'), ('pots', 'shuffle_pots', 'off'),
                                ('crates', 'shuffle_crates', 'off'), ('beehives', 'shuffle_beehives', False),
                                ('bushes', 'shuffle_bushes', False), ('rocks', 'shuffle_rocks', False),
                                ('trees', 'shuffle_trees', False),
                                ('npc', 'shuffle_npc_gifts', False), ('boss', 'shuffle_boss_rewards', False),
                                ('bossheart', 'shuffle_boss_rewards', False), ('fairy', 'shuffle_great_fairies', False),
                                ('quest', 'shuffle_quest_rewards', False), ('scrub', 'shuffle_scrubs', 'off'),
                                ('master_sword', 'shuffle_master_sword', False),
                                ('gerudo_card', 'shuffle_gerudo_card', False),
                                ('song', 'shuffle_song_items', 'song')):
        value = options.get(option, off)
        if value != off:
            result[source] = value if value in ('dungeons', 'overworld') else 'all'
    return result


def source_in_scope(entry, sources):
    scope = sources.get(entry.get('source', 'chest'))
    if scope is None:
        return False
    if scope == 'dungeons':
        return entry['folder'] in FOLDER_DUNGEON
    if scope == 'overworld':
        return entry['folder'] not in FOLDER_DUNGEON
    return True


# Zelda's Letter takes the pouch slot of the Weird Egg and the Cucco: found before
# Talon is woken, it replaces them and Zelda can never be reached. It stays
# Zelda's gift while the child trade quest is vanilla.
CHILD_TRADE_LOCKED = ('HC Zeldas Letter',)


def letter_removed(options):
    """With the Kakariko gate open the letter has no use left (only the gate guard
    reads it): it leaves the item pool and Zelda's gift is shuffled like the others."""
    return options.get('open_kakariko') == 'open'


def ruto_letter_removed(options):
    """With Zora's Fountain open King Zora already moved: Ruto's Letter can never be
    delivered and is never a bottle (patching/world_openings.py). It leaves the pool
    for an empty bottle, as OoTR/AP do (no Ruto bottle with the fountain open)."""
    return options.get('zora_fountain') == 'open'


# Child Hyrule Castle skipped (``skip_child_zelda``, patching/child_castle_skip.py):
# the castle's gifts never play, its shuffled checks hold this item (Great Fairy apart).
CASTLE_FOLDER = 'HyruleCastle'
CASTLE_GIFTS = ('HC Zeldas Letter', 'Song from Impa')
CASTLE_JUNK = 'Rupee (1)'
CASTLE_SONG = 'Zeldas Lullaby'


# Adult start (patching/adult_start.py): the first-adult cinematics never play (not at the start,
# nor when travelling back and forth later), so Rauru's Light Medallion and the Master Sword
# pull cannot be collected. Both checks hold a green rupee; their items are shuffled elsewhere
# (the Master Sword is the player's from the start unless it is shuffled).
ADULT_START_CHECKS = ('Links Pocket', 'ToT Master Sword')


def adult_start_check(entry, options):
    ap = list(entry.get('ap') or ())
    return (options.get('starting_age') == 'adult' and len(ap) == 1 and ap[0] in ADULT_START_CHECKS
            and entry.get('source') in ('boss', 'master_sword'))


def skipped_castle_check(entry):
    """True for a check of the child castle grounds or one of the castle's gifts."""
    ap = list(entry.get('ap') or ())
    return entry.get('folder') == CASTLE_FOLDER or (
        entry.get('source') in ('quest', 'song') and len(ap) == 1 and ap[0] in CASTLE_GIFTS)


def kept_for_child_trade(entry, options):
    return (options.get('shuffle_child_trade', 'vanilla') == 'vanilla' and not letter_removed(options)
            and entry.get('source') == 'quest' and entry.get('kind') == 'exact'
            and entry['ap'][0] in CHILD_TRADE_LOCKED)


class DetRandom:
    def __init__(self, key):
        self.key = key.encode('utf-8') if isinstance(key, str) else key
        self.counter = 0

    def below(self, n):
        if n <= 0:
            raise ValueError('Tirage vide.')
        limit = (1 << 256) - (1 << 256) % n
        while True:
            sample = int.from_bytes(hashlib.sha256(self.key + self.counter.to_bytes(8, 'big')).digest(), 'big')
            self.counter += 1
            if sample < limit:
                return sample % n

    def choice(self, values):
        return values[self.below(len(values))]

    def shuffle(self, values):
        values = list(values)
        for index in range(len(values) - 1, 0, -1):
            other = self.below(index + 1)
            values[index], values[other] = values[other], values[index]
        return values


def vname(group_id):
    return 'Remake|' + group_id


# Ring-dungeon spots checked in game as reachable without any key (remake_world.KNOWN_CHEST_GROUPS).
KEY_FREE_SPOTS = frozenset({'Fire Temple Near Boss Chest', 'Forest Temple First Room Chest'})


class FillError(ValueError):
    pass


@dataclass
class FillContext:
    """Everything :func:`prepare` derives from the options before a fill (read by ``plan``,
    ``plan_assigned``, the Archipelago bridge and the tests)."""
    data: object                  # logic.world.World
    options: dict                 # validated complete-mode options
    settings: dict                # settings of the AP rules (rando_options.ap_settings)
    logic: object                 # logic.rules.Logic, with the remake's extra requirements
    matches: dict                 # group id -> matched source entry (every source in scope)
    shuffled: dict                # group id -> entry of the sources that take a shuffled item
    pool: list                    # items to place, one per shuffled source
    relevant: set                 # items the logic can need
    progression: list             # relevant items of the pool, placed first
    logic_locations: list         # shuffled group ids that are locations of the logic (sorted)
    restricted_dungeon: dict      # dungeon-bound item -> (zone rule, dungeon)
    allowed: Callable             # allowed(item, group id): placement rule of a source
    sweep: Callable               # sweep(placements, extra items) -> (state, collected, spheres)
    base: dict                    # AP location -> vanilla item (logic.rules.vanilla_placements)
    souls: dict                   # soul plan (patching.soul_adapter.plan_souls)
    unmatched_ap: list            # AP locations without a remake source
    natives: dict                 # group id -> unshuffled source giving a fixed progressive level
    starting: object              # Counter of the items held at start (removed keys, starting items)
    report: Callable              # progress callback
    start_items: list
    start_actors: list
    castle_junk: list             # skipped child castle sources: always junk
    is_key: Callable
    is_mapcompass: Callable


def prepare(data, options, groups, enemies, seed_key, open_forest=True, progress=None, forced=None,
            extra=None):
    """Everything before the fill: matched sources, shuffled locations, item pool and rules.

    Shared by :func:`plan` (built-in fill) and the Archipelago world (AP fill).
    ``forced`` only selects the shop slots of a replay.
    """
    report = progress or (lambda message: None)
    options = rando_options.validate(options, supported_only=True)
    settings = ap_settings(options, open_forest)
    probe = Logic(data, settings)
    matches, unmatched_ap = match_locations(groups, data, probe, options['chest_matching'])
    for entry in matches.values():
        entry.setdefault('source', 'chest')
        entry.setdefault('form', 'chest')
        entry.setdefault('guards', [])
    sources = enabled_sources(options)
    if extra:
        import copy as _copy
        chosen = {gid: _copy.deepcopy(e) for gid, e in extra.items() if source_in_scope(e, sources) or adult_start_check(e, options)}
        used = {l for e in matches.values() if e['kind'] in ('exact', 'group') for l in e['ap']}
        match_sources(chosen, data, probe, used)
        for gid, entry in chosen.items():
            if entry['kind'] == 'area' and not entry.get('spot'):
                entry['ap'] = area_locations(data, probe, entry['folder'])
                if not entry['ap']:
                    entry.update(kind='junk', reason='no_reliable_ap_match')
            if any(v.get('deep') for v in entry['variants']) and DEEP_GUARD not in entry['guards']:
                entry['guards'] = list(entry['guards']) + [DEEP_GUARD]
        matches.update(chosen)
    souls = plan_souls(options['shuffle_enemy_spawns'], enemies, data.regions)
    location_requirements = {k: set(v) for k, v in souls['location_requirements'].items()}
    # Scrubs keep their remake price with 'regular': above the child wallet, buying
    # needs the first wallet upgrade (the AP rules do not know these prices).
    for gid, entry in matches.items():
        if entry['source'] == 'scrub' and entry['kind'] != 'junk':
            entry['price_after'] = scrub_price(options['shuffle_scrubs'], seed_key, entry)
            if entry['price_after'] > CHILD_WALLET:
                for location in entry['ap']:
                    location_requirements.setdefault(location, set()).add('Progressive Wallet')
    if options['shuffle_chests']:
        # Upgrades given by NPCs (bullet bag, bomb bag, quiver…) need the base
        # item in the remake: the logic must not treat them as the first copy.
        for family in BASE_REQUIRED:
            for location in sorted(probe.location_names()):
                if data.vanilla_item(location) == family and data.location_type(location) != 'Chest':
                    location_requirements.setdefault(location, set()).add(family)
    # A key ring may only land where its dungeon's doors cannot lock it in: the matching of
    # remake sources to AP locations never checked the remake's own chain locks, so every
    # location of a ring dungeon needs one key of it (the ring), except verified spots.
    for _folder in key_ring_folders(options, seed_key):
        for _region in data.regions:
            # Boss rooms carry no dungeon tag: they lie behind the dungeon's own doors too.
            if (_region.get('dungeon') == _AP_DUNGEON.get(_folder)
                    or (_region['region_name'].endswith('Boss Room')
                        and BOSS_HEARTS.get(_folder) in _region.get('locations', {}))):
                for _location in _region.get('locations', {}):
                    if _location not in KEY_FREE_SPOTS:
                        location_requirements.setdefault(_location, set()).add(_small_key(_folder))
    logic = Logic(data, settings, souls['exit_requirements'], location_requirements)
    relevant = set(logic.referenced) | set(souls['items'])

    def is_key(item):
        return item.startswith(('Small Key (', 'Boss Key ('))

    def is_mapcompass(item):
        return item.startswith(('Map (', 'Compass ('))

    # --- which dungeons can shuffle their keys inside themselves -----------
    key_dungeons = set()
    for kind_prefix, option in (('Small Key (', 'shuffle_smallkeys'), ('Boss Key (', 'shuffle_bosskeys')):
        if options[option] != 'dungeon':
            continue
        by_dungeon = defaultdict(list)
        for entry in matches.values():
            if entry['vanilla'].startswith(kind_prefix):
                by_dungeon[entry['vanilla']].append(entry)
        for item, entries in by_dungeon.items():
            ap_sources = [l for l in logic.location_names() if data.vanilla_item(l) == item]
            mapped = {l for e in entries for l in e['ap']}
            if all(e['kind'] != 'junk' for e in entries) and set(ap_sources) <= mapped:
                key_dungeons.add(item)

    # --- key rings and dungeon-specific boss keys (key_adapter) ---------------
    ring_folders = key_ring_folders(options, seed_key)
    ring_keys = {small_key_item(folder): ring_item(folder) for folder in ring_folders}
    specific_boss = options['shuffle_bosskeys'] in ('any_dungeon', 'keysanity')
    boss_keys = ({f'Boss Key ({FOLDER_DUNGEON[f]})' for f in BOSS_KEY_DUNGEONS} if specific_boss else set())
    # A ring counts as every small key of its dungeon (logic.bundles).
    logic.bundles.update({ring_item(f): (small_key_item(f), RING_DUNGEONS[f]) for f in ring_folders})
    relevant |= set(ring_keys.values())
    ring_dungeon_keys = {small_key_item(folder) for folder in RING_DUNGEONS}
    # "Removed" keys: every key is held from the start (start_dungeon_values), the
    # key chests hold filler instead.
    removed_keys = start_logic_items(options)

    def in_scope(entry):
        item = entry['vanilla']
        if entry['source'] != 'chest':
            if kept_for_child_trade(entry, options):
                return False
            return entry['kind'] != 'junk' or entry['reason'] in SAFE_JUNK
        if not options['shuffle_chests']:
            return False
        if item in ring_keys:
            return True       # the ring replaces every small key of the dungeon
        if item in ring_dungeon_keys:
            return item in removed_keys   # no ring for this dungeon: generic keys stay in place
        if item.startswith('Small Key ('):
            return item in key_dungeons or item in removed_keys
        if item in boss_keys:
            return True
        if item.startswith('Boss Key ('):
            return (item in key_dungeons or item in removed_keys) and 'Ganons Castle' not in item
        if is_mapcompass(item):
            return options['shuffle_mapcompass'] in ('dungeon', 'remove', 'startwith', 'any_dungeon',
                                                     'overworld', 'keysanity')
        if item == 'Kokiri Sword':
            return options['shuffle_kokiri_sword']
        if item.startswith('Remake: '):
            return options['shuffle_remake_items']
        return True

    shuffled = {gid: e for gid, e in matches.items() if in_scope(e)}
    # Shopsanity: N slots per shop; every purchase the logic uses keeps one vanilla copy
    # (a shuffled slot is sold once: refills such as Blue Fire must stay buyable), except
    # in the "all" mode, where the logic loses them and relies on their world sources.
    shop_rng = DetRandom(hashlib.sha256((seed_key + '\0shops-v2').encode()).digest())
    shop_slots = sorted(g for g in shuffled if shuffled[g]['source'] == 'shop')
    selected_shops = set()
    if shop_slots and forced is not None:
        selected_shops = {g for g in shop_slots if g in forced}  # replay: the spoiler decides
    elif shop_slots:
        keep_purchases = options['shopsanity'] != 'all'
        referenced = {shop_purchase(i) for i in probe.referenced}
        copies = Counter(shop_purchase(shuffled[g]['vanilla']) for g in shop_slots)
        # Counted per shop, not per map folder (the Market has three shops).
        from oot_rando.game.extra_sources import shop_groups
        shop_of = shop_groups({gid: shuffled[gid] for gid in shop_slots})
        by_shop = defaultdict(list)
        for gid in shop_slots:
            by_shop[shop_of[gid]].append(gid)
        for shop, slots in sorted(by_shop.items()):
            wanted = shop_count(options['shopsanity'], shop_rng)
            for gid in shop_rng.shuffle(slots):
                if wanted <= 0:
                    break
                purchase = shop_purchase(shuffled[gid]['vanilla'])
                if keep_purchases and purchase in referenced and copies[purchase] <= 1:
                    continue
                copies[purchase] -= 1
                selected_shops.add(gid)
                wanted -= 1
    for gid in shop_slots:
        if gid not in selected_shops:
            del shuffled[gid]
    report(f'Shuffled chests: {len(shuffled)} groups ({sum(e["kind"] != "junk" for e in shuffled.values())} in logic).')
    natives = native_sources(matches, shuffled, extra)

    # --- logic placements --------------------------------------------------
    base = vanilla_placements(data, logic)
    moved_boss = {e['vanilla'] for g, e in shuffled.items() if e['vanilla'] in boss_keys}
    for entry in matches.values():
        vanilla_key = is_key(entry['vanilla']) and entry['vanilla'] not in key_dungeons
        if entry['vanilla'] in ring_keys or entry['vanilla'] in moved_boss:
            vanilla_key = False   # mapped like any location: its key comes from the ring / own item
        if entry['kind'] == 'junk' or (vanilla_key and entry['kind'] == 'group'):
            continue  # invisible to the logic: the AP model keeps its own location(s)
        if entry['kind'] in ('exact', 'group'):
            for location in entry['ap']:
                base[location] = None
        logic.virtual[vname(entry['id'])] = rule_members(entry) + list(entry.get('guards', []))
        if entry['id'] not in shuffled:
            base[vname(entry['id'])] = entry['vanilla']
    for location in unmatched_ap:
        item = base.get(location)
        if item and item in relevant and not is_key(item):
            base[location] = None  # chest absent from the remake: no phantom progression
    for location in list(base):
        if base[location] in ring_keys or base[location] in moved_boss:
            # Rings: the remake's own small keys (unshuffled sources) only add spare keys.
            base[location] = None
    # Souls for conditional chests and named enemy checks.
    for gid, entry in matches.items():
        name = vname(gid)
        if name in logic.virtual:
            extra = chest_requirements(souls, entry, entry['ap'])
            if extra:
                logic.virtual[name] = logic.virtual[name] + ['Souls|' + '|'.join(sorted(extra))]

    # Area fallbacks only keep members the logic can reach with every item.
    everything = Counter({item: 9 for item in relevant})
    everything_state, reachable_all, _ = logic.sweep({l: None for l in logic.location_names()},
                                                     logic.new_state(everything))
    for gid, entry in matches.items():
        if entry['kind'] == 'area':
            members = [l for l in entry['ap'] if l in reachable_all]
            if members:
                entry['ap'] = members
                logic.virtual[vname(gid)] = members + [m for m in logic.virtual.get(vname(gid), [])
                                                       if m.startswith('Souls|')]
            else:
                entry.update(kind='junk', ap=[], reason='no_reliable_ap_match')
                logic.virtual.pop(vname(gid), None)
                base.pop(vname(gid), None)
        elif entry['kind'] in ('exact', 'group') and entry['source'] != 'chest':
            # A conjunction holding a check the AP rules never reach (bean
            # planting through ``here()``…) can never be in logic: filler only.
            members = list(entry['ap']) + list(entry.get('guards', []))
            if not all(l in reachable_all for l in members):
                # The AP members stay empty: the physical object is this remake
                # entry (filler once shuffled). Giving them back their vanilla
                # item credited phantom tokens/hearts (11/11: 2 Lost Woods
                # tokens made the 10-skulltula reward look reachable with 8).
                for location in entry['ap']:
                    base[location] = None
                entry.update(kind='junk', reason='no_reliable_ap_match')
                logic.virtual.pop(vname(gid), None)
                if gid not in shuffled:
                    base.pop(vname(gid), None)
    # A source found only on the child maps or only on the adult maps is collected at
    # that age: every member that age can ever do must be done at that age.
    for gid, entry in matches.items():
        age, name = source_age(entry['variants']), vname(gid)
        if age is None or name not in logic.virtual:
            continue
        members = [age_member(age, m) if not m.startswith('Souls|')
                   and logic.accessible(everything_state, age_member(age, m)) else m
                   for m in logic.virtual[name]]
        if members != logic.virtual[name]:
            logic.virtual[name] = members
            continue
        # Nothing of it is ever done at that age: no proof the age reaches it, filler only.
        if entry['kind'] == 'area':
            entry['ap'] = []
        else:
            for location in entry['ap']:
                base[location] = None
        entry.update(kind='junk', reason='no_reliable_ap_match')
        logic.virtual.pop(name, None)
        base.pop(name, None)
    # --- item pool ------------------------------------------------------------
    pool = []
    for gid, entry in shuffled.items():
        item = entry['vanilla']
        if is_mapcompass(item) and options['shuffle_mapcompass'] in ('remove', 'startwith'):
            item = 'Rupees (5)'
        if item in removed_keys:
            item = 'Rupees (5)'
        if entry['source'] == 'shop':
            item = SHOP_FILLER  # the displaced purchase stays sold in other slots
            # Full shopsanity removes even the last tunic shelf. Move those
            # equipment items into the pool instead of deleting their copies.
            if options['shopsanity'] == 'all':
                item = {'Buy Goron Tunic': 'Goron Tunic',
                        'Buy Zora Tunic': 'Zora Tunic'}.get(entry['vanilla'], SHOP_FILLER)
        if item in ring_keys:
            item = 'Rupees (5)'
        if item == 'Zeldas Letter' and letter_removed(options):
            item = POOL_FILLER
        if item == 'Rutos Letter' and ruto_letter_removed(options):
            item = 'Bottle'
        if item == 'Master Sword' and adult_start_check(entry, options) and not options.get('shuffle_master_sword'):
            item = POOL_FILLER   # held from the start (randomizer_core.starting_pouch_items)
        pool.append(item)

    def removable(item):
        return item not in relevant and not is_mapcompass(item) and not is_key(item)

    # Key rings and souls are added on top; balance_pool (below) takes green rupees
    # (then other filler) out so that the pool matches the shuffled checks.
    pool.extend(sorted(ring_keys.values()))
    pool.extend(souls['items'])
    pool = balance_pool(pool, len(shuffled), removable)
    pool = apply_item_pool(pool, options['item_pool_value'], relevant,
                           never_extra=set(ring_keys.values()) | set(souls['items']))
    # Starting inventory: each copy found in the pool is taken out of it (OoTR /
    # AP start_inventory_from_pool); progressive copies take the lowest levels.
    start_items = []
    from_pool = Counter()
    for item, count in sorted(options['start_inventory_from_pool'].items()):
        for _ in range(count):
            start_items.append(item)
            if item in pool:
                pool[pool.index(item)] = POOL_FILLER
                from_pool[item] += 1
    castle_junk = []
    if options.get('skip_child_zelda'):
        # The castle's gifts never play (patching/child_castle_skip.py): Zelda's Letter
        # and Lullaby leave their vanilla locations and are shuffled elsewhere.
        from oot_rando.patching.child_castle_skip import MOVED_ITEMS

        for location in CASTLE_GIFTS:
            base[location] = None
        for gid, entry in matches.items():
            if set(entry.get('ap', ())) & set(CASTLE_GIFTS):
                # Native quest rewards also have a virtual location, even when
                # child-trade protection keeps their source out of the shuffle.
                base[vname(gid)] = None
        for item in MOVED_ITEMS:
            if item == 'Zeldas Letter' and letter_removed(options):
                continue  # gate open: the letter left the pool, the skip must not add it back
            if item not in pool and item not in start_items:
                pool.append(item)
        # Every shuffled castle check holds a green rupee, reserved in the pool.
        castle_junk = sorted(g for g in shuffled if skipped_castle_check(shuffled[g]))
        pool.extend([CASTLE_JUNK] * len(castle_junk))
    adult_junk = sorted(g for g in shuffled if adult_start_check(shuffled[g], options))
    pool.extend([CASTLE_JUNK] * len(adult_junk))
    castle_junk = castle_junk + adult_junk
    # Whatever was added or replaced above: exactly one item per shuffled check.
    pool = balance_pool(pool, len(shuffled), removable, keep={CASTLE_JUNK: len(castle_junk)})
    if options.get('fake_item_traps', 'none') != 'none':
        # The castle junk stays reserved for its checks.
        # Only plain filler (rupees, ammunition…) leaves; the castle junk stays reserved.
        junk = {GREEN_RUPEE, *FILLER_PRIORITY}
        spare = Counter(i for i in pool if i in junk and removable(i)) - Counter({CASTLE_JUNK: len(castle_junk)})
        pool = add_fake_traps(pool, spare, options['fake_item_traps'])
    logic_locations =sorted(g for g in shuffled if vname(g) in logic.virtual)
    restricted_dungeon = {}   # item -> (zone rule, dungeon)
    for item in set(pool):
        if item in ring_keys.values():
            rule = options['shuffle_smallkeys']
        elif item in moved_boss:
            rule = options['shuffle_bosskeys']
        elif is_key(item) or (is_mapcompass(item) and options['shuffle_mapcompass'] == 'dungeon'):
            rule = 'dungeon'
        elif is_mapcompass(item) and options['shuffle_mapcompass'] in ('any_dungeon', 'overworld'):
            rule = options['shuffle_mapcompass']
        else:
            continue
        if rule != 'keysanity':
            restricted_dungeon[item] = (rule, item[item.index('(') + 1:-1])
    progression = [i for i in pool if i in relevant]
    if len(progression) > len(logic_locations):
        raise FillError(f'{len(progression)} progression items for {len(logic_locations)} chests in logic: '
                        'enable zone matching or reduce the options.')
    start_actors = starting_actors(start_items)
    folder_dungeon = {gid: _dungeon_name(e['folder']) for gid, e in shuffled.items()}

    canonical_cache = {}

    def canonical(item, gid):
        key = (item, shuffled[gid]['folder'])
        if key not in canonical_cache:
            canonical_cache[key] = item_actor(item, shuffled[gid]['folder'])
        return canonical_cache[key]

    castle_junk_set = set(castle_junk)
    castle_skipped = bool(options.get('skip_child_zelda'))

    def allowed(item, gid):
        if gid in castle_junk_set:
            return item == CASTLE_JUNK
        rule, dungeon = restricted_dungeon.get(item, (None, None))
        if rule == 'dungeon' and folder_dungeon[gid] != dungeon:
            return False
        if rule == 'any_dungeon' and folder_dungeon[gid] is None:
            return False
        if rule == 'overworld' and folder_dungeon[gid] is not None:
            return False
        actor = canonical(item, gid)
        song_mode = options.get('shuffle_song_items', 'song')
        if castle_skipped and item == CASTLE_SONG:
            # The castle skipped, Impa's song has no song location left: it goes
            # anywhere a song can be given, whatever the song mode.
            song_mode = 'everywhere'
        if not song_allowed(song_mode, shuffled[gid]['source'], actor, shuffled[gid]['form']):
            return False
        if is_song_actor(actor) and set(shuffled[gid].get('ap', ())) & set(POSE_AFTER_CUTSCENE):
            return False   # given back in game with a pose (qol_patches.give_gift_after), not text-only
        return can_take(actor, shuffled[gid]['form'], shuffled[gid].get('ap', ()),
                        shuffled[gid].get('actor', ''))

    # OoTR/AP vanilla-key compensation: with vanilla Fire Temple keys the logic
    # starts with one extra key (the vanilla layout expects the hammer door order).
    starting = Counter(removed_keys) + Counter(start_items)
    if ('Small Key (Fire Temple)' not in key_dungeons and 'Small Key (Fire Temple)' not in ring_keys
            and 'Small Key (Fire Temple)' not in removed_keys):
        starting['Small Key (Fire Temple)'] += 1

    def sweep(placed, counts=None, before_adult=False):
        placements = dict(base)
        for gid in logic_locations:
            placements.setdefault(vname(gid), None)
        for gid, item in placed.items():
            if vname(gid) in logic.virtual:
                placements[vname(gid)] = item
        inventory = Counter(counts or {}) + starting
        if before_adult:
            # Prove a child route from actual pickups, never from a first trip
            # through the pedestal (or an assumed Time Travel item).
            placements = {loc: None if item == 'Time Travel' else item
                          for loc, item in placements.items()}
            inventory.pop('Time Travel', None)
        state = logic.new_state(inventory)
        return _sweep_with_requirements(logic, placements, state)

    return FillContext(
        data=data, options=options, settings=settings, logic=logic, matches=matches, shuffled=shuffled,
        pool=pool, relevant=relevant, progression=progression, logic_locations=logic_locations,
        restricted_dungeon=restricted_dungeon, allowed=allowed, sweep=sweep, base=base, souls=souls,
        unmatched_ap=unmatched_ap, natives=natives, starting=starting, report=report,
        start_items=start_items, start_actors=start_actors, castle_junk=castle_junk,
        is_key=is_key, is_mapcompass=is_mapcompass)


def plan(data, options, groups, enemies, seed_key, open_forest=True, progress=None, forced=None, extra=None):
    """Return the complete placement plan. Raises if no beatable seed is found.

    With ``forced`` (group id → item), no fill is done: the given placements are
    swept from scratch and the sphere of every chest is returned (``replay``).
    """
    c = prepare(data, options, groups, enemies, seed_key, open_forest, progress, forced, extra)
    options, logic, matches, shuffled, pool = c.options, c.logic, c.matches, c.shuffled, c.pool
    relevant, progression, logic_locations = c.relevant, c.progression, c.logic_locations
    restricted_dungeon, allowed, sweep, base, souls = c.restricted_dungeon, c.allowed, c.sweep, c.base, c.souls
    unmatched_ap, report = c.unmatched_ap, c.report
    rng = DetRandom(hashlib.sha256((seed_key + '\0full-fill-v1').encode()).digest())
    if forced is not None:
        state, collected, spheres = sweep(forced)
        child_missing = child_door_missing(c, forced)
        soul_missing = sorted(item for item in souls['items'] if not state.has(item))
        sphere_of = {loc[len('Remake|'):]: index for index, sphere in enumerate(spheres)
                     for loc in sphere if loc.startswith('Remake|')}
        return {'beatable': state.has('Triforce') and not child_missing and not soul_missing,
                'before_adult_missing': child_missing, 'spheres': sphere_of, 'sphere_count': len(spheres),
                'unreachable_souls': soul_missing,
                'unreachable': sorted(g for g in logic_locations if vname(g) not in collected),
                'progressive': progressive_plan(forced, c.natives),
                # Read by verify: the chests left in place get their opening flag too.
                'matches': c.matches}

    last_error = 'no attempt'
    for attempt in range(MAX_ATTEMPTS):
        placed = {gid: CASTLE_JUNK for gid in c.castle_junk}
        failed = False
        rest = [i for i in pool if i not in relevant]
        rest_counter = Counter(rest)
        rest_counter[CASTLE_JUNK] -= len(c.castle_junk)
        # Dungeon-bound items outside the logic (maps, compasses) first, in
        # chests the logic cannot use whenever possible; then the fake item traps
        # (chests and ground checks, item_forms.can_take).
        for item in (rng.shuffle([i for i in rest if i in restricted_dungeon])
                     + rng.shuffle([i for i in rest if is_trap_item(i)])):
            free = [g for g in shuffled if g not in placed and allowed(item, g)]
            junk_free = [g for g in free if vname(g) not in logic.virtual]
            if not free:
                failed, last_error = True, f'no free dungeon chest for {item}'
                break
            placed[rng.choice(junk_free or free)] = item
            rest_counter[item] -= 1
        if failed:
            continue
        ordered = (rng.shuffle([i for i in progression if i in restricted_dungeon])
                   + rng.shuffle([i for i in progression if i not in restricted_dungeon]))
        remaining = Counter(ordered)
        for item in ordered:
            remaining[item] -= 1
            state, collected, _ = sweep(placed, +remaining)
            options_here = [g for g in logic_locations if g not in placed and allowed(item, g)
                            and vname(g) in collected]
            if not options_here:
                failed, last_error = True, f'no reachable chest for {item}'
                break
            # Keep early chests for the last items: prefer chests that need
            # some of the still unplaced items, unless the attempt is a fallback.
            if attempt % 4 != 3 and sum(remaining.values()):
                _, early, _ = sweep(placed)
                deep = [g for g in options_here if vname(g) not in early]
                if deep:
                    options_here = deep
            placed[rng.choice(options_here)] = item
        if failed:
            continue
        free = rng.shuffle([g for g in shuffled if g not in placed])
        filler = sorted((+rest_counter).elements())
        filler = rng.shuffle(filler)
        if len(free) != len(filler):
            raise FillError('Item and chest counts do not match.')
        placed.update(zip(free, filler))
        # --- independent verification -----------------------------------------
        child_missing = child_door_missing(c, placed)
        if child_missing:
            last_error = 'Door of Time items unavailable before adulthood: ' + ', '.join(child_missing)
            continue
        state, collected, spheres = sweep(placed)
        if not state.has('Triforce'):
            last_error = 'victory not guaranteed'
            continue
        soul_missing = sorted(item for item in souls['items'] if not state.has(item))
        if soul_missing:
            last_error = 'Unreachable enemy souls: ' + ', '.join(soul_missing)
            continue
        if options['accessibility'] == 'full':
            missing = [g for g in logic_locations if vname(g) not in collected]
            if missing:
                last_error = f'{len(missing)} unreachable chests: ' + ', '.join(
                    str(shuffled[g]['ap'][:1]) for g in missing[:3])
                continue
        sphere_of = {loc: index for index, sphere in enumerate(spheres) for loc in sphere}
        report(f'Beatable seed found (attempt {attempt + 1}, {len(spheres)} spheres).')
        result = _result(data, logic, options, matches, shuffled, placed, c.natives, sphere_of, spheres, souls,
                         unmatched_ap, attempt + 1, base)
        result['starting'] = [{'item': item, 'actor': actor} for item, actor in zip(c.start_items, c.start_actors)]
        return result
    raise FillError('No beatable seed in ' + str(MAX_ATTEMPTS) + ' attempts (' + last_error
                    + '). Change the seed or the options.')


def child_door_missing(c, placed):
    """Required door items the child cannot collect without ever becoming adult.

    One ocarina suffices; spare copies may remain on adult maps. A real sweep
    also rules out child pickups whose dependencies require an adult visit.
    """
    if c.settings['open_door_of_time'] or c.settings['starting_age'] != 'child':
        return []
    stones = {'song': (), 'vanilla': ('Goron Ruby', 'Zora Sapphire'),
              'all': ('Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire')}
    required = ('Ocarina', 'Song of Time') + stones[c.settings['door_of_time_requirement']]
    state, _, _ = c.sweep(placed, before_adult=True)
    return [item for item in required if not state.has(item)]


# Starting items that cannot be handed over silently at the end of the opening:
# dungeon items (generic actors, or a key count only applied at the next item get).
STARTING_UNSUPPORTED = ('Map (', 'Compass (', 'Small Key (', 'Boss Key (', 'Small Key Ring (', 'Remake: ')


def key_ring_folders(options, seed_key):
    """Dungeon folders whose small keys become a key ring."""
    folders = sorted(RING_DUNGEONS)
    mode = options['key_rings']
    if mode == 'all':
        return folders
    if mode == 'choose':
        return [f for f in folders if FOLDER_DUNGEON[f] in options['key_rings_list']]
    if mode == 'random':
        # Same draw in the Archipelago generation and in the application (same seed key).
        rng = DetRandom(hashlib.sha256((seed_key + '\0key-rings-v1').encode()).digest())
        chosen = [f for f in folders if rng.below(2)]
        return chosen or [rng.choice(folders)]
    return []


def covered_by_start_values(item, options):
    if item.startswith(('Map (', 'Compass (')):
        return options['shuffle_mapcompass'] == 'startwith'
    if item.startswith('Small Key ('):
        return options['shuffle_smallkeys'] == 'remove'
    if item.startswith('Boss Key (') and 'Ganons Castle' not in item:
        return options['shuffle_bosskeys'] == 'remove'
    return False


def starting_unsupported(item):
    return item.startswith(STARTING_UNSUPPORTED)


def starting_actors(starting):
    """Pouch actors of Archipelago starting items (AP names).

    Copies of a progressive family take its lowest levels; the copies found later
    give the next ones (``patching.progressive``).
    """
    bad = sorted({item for item in starting if starting_unsupported(item)})
    if bad:
        raise FillError('Starting items that cannot be given at the start of the game: ' + ', '.join(bad))
    actors, taken = [], Counter()
    for item in starting:
        if item in PROGRESSIVE:
            if taken[item] >= len(PROGRESSIVE[item]):
                raise FillError(f'Too many {item} (starting items included).')
            actors.append(PROGRESSIVE[item][taken[item]])
            taken[item] += 1
        else:
            actors.append(item_actor(item, None))
    return actors


def plan_assigned(data, options, groups, enemies, seed_key, assigned, open_forest=True, progress=None,
                  extra=None, labels=None, starting=()):
    """Plan with placements chosen elsewhere (Archipelago): gid → item, every shuffled gid.

    Items of other players are given as a stand-in by the caller. Victory is not
    required here: items may come from other worlds. ``starting``: Archipelago
    starting items (AP names), collected from the start; progressive copies among
    them take the lowest levels.
    """
    c = prepare(data, options, groups, enemies, seed_key, open_forest, progress, extra=extra)
    if set(assigned) != set(c.shuffled):
        extra_ids = sorted(set(assigned) - set(c.shuffled))[:3]
        missing = sorted(set(c.shuffled) - set(assigned))[:3]
        raise FillError('The Archipelago placements do not match this game and options '
                        f'(unknown: {extra_ids}, missing: {missing}).')
    for gid, item in assigned.items():
        if not c.allowed(item, gid):
            raise FillError(f'{item} cannot be placed at {gid}.')
    placed = dict(assigned)
    # Maps, compasses and keys of the "start with" / "removed" modes are written at
    # the start (key_adapter.start_dungeon_values), not handed over as pouch items.
    starting = [item for item in starting if not covered_by_start_values(item, c.options)]
    start_actors = starting_actors(starting)
    state, collected, spheres = c.sweep(placed, Counter(starting))
    sphere_of = {loc: index for index, sphere in enumerate(spheres) for loc in sphere}
    c.report(f'Archipelago placements applied ({len(spheres)} local spheres).')
    result = _result(data, c.logic, c.options, c.matches, c.shuffled, placed, c.natives, sphere_of, spheres,
                     c.souls, c.unmatched_ap, 0, c.base)
    for row in result['spoiler']:
        if labels and row['id'] in labels:
            row['item'] = labels[row['id']]
    result['starting'] = [{'item': item, 'actor': actor} for item, actor in zip(starting, start_actors)]
    return result


def _dungeon_name(folder):
    return FOLDER_DUNGEON.get(folder)


def _sweep_with_requirements(logic, placements, state):
    return logic.sweep(placements, state)


# Native sources that keep a fixed level once unshuffled: chests and freestanding
# items (their actor), and the gifts of STATIC_TIER_SOURCES. The other native sources
# of a family already give the level above the one Link holds.
FIXED_LEVEL_SOURCES = ('chest', 'freestanding')


# Purchases the logic accepts in any size (helpers.json: Nuts = Buy_Deku_Nut_5 or
# Buy_Deku_Nut_10, has_bombchus = any Bombchu pack...): one kept copy of the group is enough.
SHOP_EQUIVALENTS = (
    ('Buy Deku Nut', ('Buy Deku Nut (5)', 'Buy Deku Nut (10)')),
    ('Buy Bombchu', ('Buy Bombchu (5)', 'Buy Bombchu (10)', 'Buy Bombchu (20)')),
    ('Buy Bombs', ('Buy Bombs (5)', 'Buy Bombs (10)', 'Buy Bombs (20)', 'Buy Bombs (30)')),
    ('Buy Arrows', ('Buy Arrows (10)', 'Buy Arrows (30)', 'Buy Arrows (50)')),
)
SHOP_PURCHASE = {item: group for group, items in SHOP_EQUIVALENTS for item in items}


def shop_purchase(item):
    """What a shop slot's purchase counts as for the keep-one-copy rule."""
    return SHOP_PURCHASE.get(item, item)


def shop_count(value, rng):
    """Slots to shuffle in one shop for the ``shopsanity`` value."""
    if value == 'random':
        return rng.below(4) + 1
    return 8 if value == 'all' else int(value)


def native_sources(matches, shuffled, extra=None):
    """{gid: entry} of the unshuffled sources giving a fixed level of a progressive family.

    They give a progressive token instead (:func:`progressive_plan`): found after a
    shuffled copy, their own level could be lower than the one Link holds.
    """
    natives = {}
    for gid, entry in matches.items():
        tiers = PROGRESSIVE.get(entry['vanilla'])
        if (gid not in shuffled and tiers and entry['before'] in tiers
                and entry.get('source', 'chest') in FIXED_LEVEL_SOURCES and entry['variants']):
            natives[gid] = entry
    for location, (family, tier) in STATIC_TIER_SOURCES.items():
        gid = static_tier_gid(location)
        entry = (extra or {}).get(gid)
        if gid in shuffled or entry is None or entry['kind'] == 'junk':
            continue   # a junk gift has no reliable event to change: it stays native
        if entry['vanilla'] != family or entry['before'] != PROGRESSIVE[family][tier]:
            raise ValueError('Unexpected fixed-level gift: ' + location)
        natives[gid] = entry
    return natives


def progressive_plan(placed, natives):
    """Tokens of the progressive copies placed in this world and of the native fixed-level sources.

    ``{'tokens': {gid: token}, 'natives': [placement-like records]}``; each token gives,
    once found, the level above the one Link holds (``patching.progressive``).
    """
    from oot_rando.patching.progressive import assign_tokens
    copies = [(gid, item) for gid, item in sorted(placed.items()) if item in PROGRESSIVE]
    copies += [(gid, natives[gid]['vanilla']) for gid in sorted(natives)]
    tokens = assign_tokens(copies)
    records = []
    for gid in sorted(natives):
        entry = natives[gid]
        form = entry.get('form', 'chest')
        records.append({'id': gid, 'folder': entry['folder'], 'source': entry.get('source', 'chest'), 'form': form,
                        'item': entry['vanilla'], 'before': entry['before'], 'token': tokens[gid],
                        'after': _spot_actor(form_actor(tokens[gid], form), entry), 'patches': _patches(entry),
                        'resources': sorted({v['resource'] for v in entry['variants']})})
    return {'tokens': {gid: tokens[gid] for gid, _ in copies if gid in placed}, 'natives': records}


def _underwater(entry):
    return any(v.get('underwater') for v in entry['variants'])


def _spot_actor(actor, entry):
    """``actor``, in its glowing form when the spot lies under water (``game/underwater.py``)."""
    return underwater_actor(actor) if _underwater(entry) else actor


def _result(data, logic, options, matches, shuffled, placed, natives, sphere_of, spheres, souls,
            unmatched_ap, attempts, base):
    placements, checks, spoiler = [], [], []
    progressive = progressive_plan(placed, natives)
    tokens = progressive['tokens']
    for gid in sorted(shuffled):
        entry = shuffled[gid]
        item = placed[gid]
        source = entry.get('source', 'chest')
        canonical = tokens[gid] if gid in tokens else item_actor(item, entry['folder'])
        if (item.startswith('Boss Key (') and 'Ganons Castle' not in item
                and options['shuffle_bosskeys'] in ('any_dungeon', 'keysanity')):
            from oot_rando.patching.key_adapter import boss_actor, item_folder
            canonical = boss_actor(item_folder(item))   # opens its own dungeon's boss door anywhere
        if (item.startswith(('Map (', 'Compass (')) and 'Ganons Castle' not in item
                and options['shuffle_mapcompass'] in ('any_dungeon', 'overworld', 'keysanity')):
            from oot_rando.patching.key_adapter import specific_actor
            canonical = specific_actor(item)   # sets its own dungeon's map / compass anywhere
        actor = _spot_actor(form_actor(canonical, entry.get('form', 'chest'), skulltula_drop=source == 'skulltula'),
                            entry)
        name = check_name(entry, gid)
        placements.append({'id': gid, 'folder': entry['folder'], 'hash': entry['hash'], 'kind': entry['kind'],
                           'source': source, 'form': entry.get('form', 'chest'),
                           'before': entry['before'], 'after': actor, 'item': item,
                           'resources': sorted({v['resource'] for v in entry['variants']}),
                           'variants': [(v['resource'], v['index']) for v in entry['variants'] if 'index' in v],
                           'patches': _patches(entry), 'ap_locations': entry['ap'],
                           'sphere': sphere_of.get(vname(gid)), 'event': entry['event'],
                           'underwater': _underwater(entry)})
        spoiler.append({'id': gid, 'location': name, 'item': soul_label(item) if item.startswith('Soul (') else item,
                        'ap_item': item, 'actor': actor, 'before': entry['before'], 'source': source,
                        'sphere': sphere_of.get(vname(gid)), 'ap_locations': entry['ap']})
    location_names = {row['id']: row['location'] for row in spoiler}
    playthrough = []
    for index, sphere in enumerate(spheres):
        names = []
        for location in sphere:
            if location.startswith('Remake|'):
                gid = location[len('Remake|'):]
                item = placed.get(gid)
                if item and (item in logic.referenced | set(souls['items']) or item in logic.bundles):
                    # Same name as the spoiler row: an approximate entry's AP names are
                    # only candidates (one pot name could stand for many pots).
                    names.append(f'{location_names.get(gid, gid)} : {item}')
        if names:
            playthrough.append({'sphere': index, 'items': sorted(names)})
    checks = tracker_checks(data, matches, shuffled)
    return {'placements': placements, 'checks': checks, 'spoiler': spoiler, 'playthrough': playthrough,
            'progressive': progressive,
            'souls': souls, 'matches': matches, 'unmatched_ap': unmatched_ap, 'attempts': attempts,
            'coverage': dict(coverage_summary(matches), shuffled=len(shuffled),
                             in_logic=sum(1 for g in shuffled if shuffled[g]['kind'] != 'junk'),
                             souls=len(souls['items']), soul_enemies=len(souls['edits']),
                             soul_doors=len(souls.get('door_edits', []))),
            'options': options,
            'tracking_logic': {
                'settings': logic.settings,
                'exits': [[a, b, sorted(items)] for (a, b), items in logic.extra_exit_requirements.items()],
                # Sorted: the requirements are gathered from sets (no stable order across processes).
                'locations': {name: sorted(items)
                              for name, items in sorted(logic.extra_location_requirements.items())},
                'virtual': {name: list(members) for name, members in logic.virtual.items()}}}


REPEATABLE = ('pots', 'bushes', 'rocks', 'crates', 'beehives', 'trees')


def check_name(entry, gid, zone=None):
    """Name of a check: its AP location when it has its own, else where it stands
    (``game/check_names.py``: KF_sarias_house_heart_1), else its AP location (NPC gifts)."""
    from oot_rando.game.check_names import entry_label, _LABEL_OVERRIDES
    if entry['kind'] == 'exact' and entry['ap']:
        return _LABEL_OVERRIDES.get(entry['ap'][0], entry['ap'][0])
    label = entry_label(entry)
    if label:
        return label
    if gid.startswith('npc#'):
        return gid[len('npc#'):]
    if entry.get('hash'):
        kind = SOURCE_LABELS.get(entry.get('source', 'chest'), entry.get('source', 'chest'))
        return f'{zone or entry["folder"]} {kind} {str(entry["hash"])[-6:]}'
    return gid


def covered_locations(entry, gid):
    """AP locations a remake source stands for: its matched or candidate locations, and
    the AP location of an NPC gift (``npc#<location>``). They are not listed twice."""
    covered = set(entry['ap'] if entry['kind'] in ('exact', 'group', 'area') else ())
    if gid.startswith('npc#'):
        covered.add(gid[len('npc#'):])
    return covered


def entry_zone(data, entry, gid):
    if entry['ap'] and (entry['kind'] in ('exact', 'group') or entry['folder'] not in ZONE_LABELS):
        return location_zone(data, entry['ap'][0])
    if entry['folder'] in ZONE_LABELS:
        return entry['folder']
    return location_zone(data, gid.split('#', 1)[-1])  # npc#<AP location>


def tracker_checks(data, matches, shuffled):
    """Every check of the game for the manual tracker, with its zone.

    Remake sources known to this seed come first (shuffled or not), then every
    vanilla AP location none of them covers (songs, NPCs, skulltulas, pots…
    left in place). Rewards are never written here.
    """
    checks, covered = [], set()
    for gid in sorted(matches):
        entry = matches[gid]
        source = entry.get('source', 'chest')
        covered.update(covered_locations(entry, gid))
        zone = entry_zone(data, entry, gid)
        if entry['kind'] == 'exact' and entry['ap']:
            from oot_rando.game.check_names import _LABEL_OVERRIDES
            name = _LABEL_OVERRIDES.get(entry['ap'][0], entry['ap'][0])
        else:
            name = check_name(entry, gid, zone_label(zone))
            age = source_age(entry['variants'])
            if age:
                name += f' ({age})'   # only on that age's maps
        checks.append({'id': gid, 'zone': zone, 'region': zone_label(zone),
                       'category': 'full_' + ('chests' if source == 'chest' else source), 'name': name,
                       'randomized': gid in shuffled, 'repeatable': source in REPEATABLE,
                       'collection_state': 'unverified', 'logic': entry['kind']})
    for location in sorted(data.location_table):
        areas = data.location_areas(location)
        if location in covered or location in UNTRACKED_LOCATIONS or data.location_type(location) not in TRACKED_TYPES:
            continue
        if data.location_type(location) in ORIGINAL_ONLY_TYPES and not _is_reward(data.vanilla_item(location)):
            # Rupees, hearts and ammo of the original game's pots, crates, beehives
            # and loose items: the remake places its own (tracked above by map hash
            # when shuffled), most original spots do not exist (e.g. "KF Links House
            # Pot") and none can be ticked automatically (Discord 13/11).
            continue
        if 'Master Quest' in areas and 'Vanilla' not in areas:
            continue
        zone = location_zone(data, location)
        checks.append({'id': 'ap#' + location, 'zone': zone, 'region': zone_label(zone),
                       'category': 'vanilla_' + data.location_type(location).lower().replace(' ', '_'),
                       'name': location, 'randomized': False,
                       'repeatable': False, 'collection_state': 'unverified', 'logic': 'vanilla'})
    order = list(ZONE_LABELS)
    checks.sort(key=lambda c: (order.index(c['zone']) if c['zone'] in order else len(order), c['name']))
    return checks


# AP locations with no readable trace in the remake (absent from the spoiler, unticked by the tracker).
UNTRACKED_LOCATIONS = frozenset({'Gift from Sages'})
ORIGINAL_ONLY_TYPES = {'Freestanding', 'Pot', 'FlyingPot', 'Crate', 'SmallCrate', 'Beehive', 'RupeeTower'}
_JUNK_PREFIXES = ('Rupee', 'Rupees', 'Recovery Heart', 'Deku Nuts', 'Deku Stick', 'Deku Seeds', 'Arrows',
                  'Bombs', 'Bombchus', 'Fairy', 'Magic Jar')


def _is_reward(item):
    """Whether a vanilla item of the original game is worth a tracker line (heart pieces…)."""
    return bool(item) and not item.startswith(_JUNK_PREFIXES)


SOURCE_LABELS = {'chest': 'chest', 'skulltula': 'skulltula', 'shop': 'shop', 'freestanding': 'freestanding',
                 'npc': 'NPC', 'boss': 'dungeon reward', 'bossheart': 'boss heart container',
                 'fairy': 'great fairy', 'quest': 'quest reward', 'scrub': 'business scrub', 'pots': 'pot', 'bushes': 'bush', 'rocks': 'rock', 'crates': 'crate',
                 'beehives': 'beehive', 'song': 'song', 'trees': 'tree'}


def _patches(entry):
    """Write targets of an entry: BYML map paths or event parameters."""
    result = []
    for variant in entry['variants']:
        if 'event' in variant:
            result.append({'resource': variant['resource'], 'event': variant['event'],
                           'param': variant['param'], 'before': variant['before']})
            if 'price' in variant and entry.get('price_after', variant['price']) != variant['price']:
                result.append({'resource': variant['resource'], 'event': variant['event'], 'param': 'Price',
                               'before': variant['price'], 'after': entry['price_after']})
        elif variant.get('field', 'Drop__DropActor') == 'Gyaml':
            result.append({'resource': variant['resource'], 'path': ['Actors', variant['index'], 'Gyaml'],
                           'before': variant['before']})
        else:
            result.append({'resource': variant['resource'],
                           'path': ['Actors', variant['index'], 'Dynamic', 'Drop__DropActor'],
                           'before': variant['before']})
            if entry['id'] == TREASURE_GAME_REWARD:
                result.append({'resource': variant['resource'],
                               'path': ['Actors', variant['index'], 'Dynamic', 'DropViewActor'],
                               'before': variant['dynamic']['DropViewActor']})
    return result


def replay(data, options, groups, enemies, placements, open_forest=True, extra=None, seed_key='replay'):
    """Independent re-check of finished placements (used by verify_full).

    ``seed_key``: the generation's, when an option is drawn from it (random key rings).
    """
    return plan(data, options, groups, enemies, seed_key, open_forest, forced=placements, extra=extra)
