"""Complete glitchless randomizer: pool, assumed fill, verification, tiers.

Placement only; writing game files is done by :func:`build` callers. The RNG is
SHA-256 counter based (rejection sampling), independent of Python's ``random``.
"""
from collections import Counter, defaultdict
import hashlib
from types import SimpleNamespace

from oot_rando.logic.rules import Logic, vanilla_placements
from oot_rando.logic import rando_options
from oot_rando.game.remake_world import (PROGRESSIVE, BASE_REQUIRED, STATIC_TIER_SOURCES, item_actor,
                          match_locations, coverage_summary, FOLDER_DUNGEON,
                          ZONE_LABELS, TRACKED_TYPES, location_zone, zone_label)
from oot_rando.game.item_forms import can_take, form_actor
from oot_rando.game.extra_sources import match_sources, area_locations
from oot_rando.patching.soul_adapter import plan_souls, chest_requirements, soul_label

FILLER_PRIORITY = ('Rupee (1)', 'Rupees (5)', 'Deku Nuts (5)', 'Deku Stick (1)', 'Arrows (5)', 'Bombs (5)',
                   'Rupees (20)', 'Arrows (10)', 'Deku Seeds (30)', 'Bombchus (5)', 'Arrows (30)',
                   'Remake: Scrub Seed', 'Rupees (50)', 'Remake: Magic Jar', 'Rupees (200)')
MAX_ATTEMPTS = int(__import__("os").environ.get("OOT_MAX_ATTEMPTS", "300"))
SHOP_FILLER = 'Rupees (5)'
# Junk reasons that still allow a source to receive filler.
SAFE_JUNK = ('no_reliable_ap_match', 'remake_only_area')


def enabled_sources(options):
    """Non-chest source families enabled by the options → scope (all/dungeons/overworld)."""
    result = {}
    for source, option, off in (('skulltula', 'tokensanity', 'off'), ('freestanding', 'shuffle_freestanding_items', 'off'),
                                ('shop', 'shopsanity', 'off'), ('pots', 'shuffle_pots', 'off'),
                                ('crates', 'shuffle_crates', 'off'), ('beehives', 'shuffle_beehives', False),
                                ('bushes', 'shuffle_bushes', False), ('rocks', 'shuffle_rocks', False),
                                ('npc', 'shuffle_npc_gifts', False), ('boss', 'shuffle_boss_rewards', False),
                                ('bossheart', 'shuffle_boss_rewards', False), ('fairy', 'shuffle_great_fairies', False),
                                ('quest', 'shuffle_quest_rewards', False), ('scrub', 'shuffle_scrubs', 'off')):
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


def ap_settings(options, open_forest):
    values = {name: options[name] for name in ('open_kakariko', 'open_door_of_time', 'zora_fountain',
                                               'gerudo_fortress', 'starting_age', 'bridge', 'trials',
                                               'shuffle_ganon_bosskey', 'big_poe_count', 'chicken_count',
                                               'free_scarecrow', 'shuffle_child_trade', 'logic_rules')}
    values['open_forest'] = 'closed_deku' if open_forest else 'closed'
    values['keysanity'] = False
    return values


class FillError(ValueError):
    pass


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
        chosen = {gid: _copy.deepcopy(e) for gid, e in extra.items() if source_in_scope(e, sources)}
        used = {l for e in matches.values() if e['kind'] in ('exact', 'group') for l in e['ap']}
        match_sources(chosen, data, probe, used)
        for gid, entry in chosen.items():
            if entry['kind'] == 'area' and not entry.get('spot'):
                entry['ap'] = area_locations(data, probe, entry['folder'])
                if not entry['ap']:
                    entry.update(kind='junk', reason='no_reliable_ap_match')
        matches.update(chosen)
    souls = plan_souls(options['shuffle_enemy_spawns'], enemies, data.regions)
    location_requirements = {k: set(v) for k, v in souls['location_requirements'].items()}
    # Scrubs keep their remake price with 'regular': above the child wallet, buying
    # needs the first wallet upgrade (the AP rules do not know these prices).
    from oot_rando.game.extra_sources import scrub_price, CHILD_WALLET
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
            for location in probe.location_names():
                if data.vanilla_item(location) == family and data.location_type(location) != 'Chest':
                    location_requirements.setdefault(location, set()).add(family)
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
    from oot_rando.patching.key_adapter import RING_DUNGEONS, BOSS_KEY_DUNGEONS, ring_item, small_key_item
    ring_folders = sorted(RING_DUNGEONS) if options['key_rings'] == 'all' else []
    ring_keys = {small_key_item(folder): ring_item(folder) for folder in ring_folders}
    specific_boss = options['shuffle_bosskeys'] in ('any_dungeon', 'keysanity')
    boss_keys = ({f'Boss Key ({FOLDER_DUNGEON[f]})' for f in BOSS_KEY_DUNGEONS} if specific_boss else set())
    # A ring counts as every small key of its dungeon (logic.bundles).
    logic.bundles.update({ring_item(f): (small_key_item(f), RING_DUNGEONS[f]) for f in ring_folders})
    relevant |= set(ring_keys.values())

    def in_scope(entry):
        item = entry['vanilla']
        if entry['source'] != 'chest':
            return entry['kind'] != 'junk' or entry['reason'] in SAFE_JUNK
        if not options['shuffle_chests']:
            return False
        if item in ring_keys:
            return True       # the ring replaces every small key of the dungeon
        if item.startswith('Small Key ('):
            return item in key_dungeons
        if item in boss_keys:
            return True
        if item.startswith('Boss Key ('):
            return item in key_dungeons and 'Ganons Castle' not in item
        if is_mapcompass(item):
            return options['shuffle_mapcompass'] in ('dungeon', 'remove')
        if item == 'Kokiri Sword':
            return options['shuffle_kokiri_sword']
        if item.startswith('Remake: '):
            return options['shuffle_remake_items']
        return True

    shuffled = {gid: e for gid, e in matches.items() if in_scope(e)}
    # Shopsanity: N slots per shop; every purchase the logic uses keeps one vanilla copy.
    shop_rng = DetRandom(hashlib.sha256((seed_key + '\0shops-v1').encode()).digest())
    shop_slots = sorted(g for g in shuffled if shuffled[g]['source'] == 'shop')
    selected_shops = set()
    if shop_slots and forced is not None:
        selected_shops = {g for g in shop_slots if g in forced}  # replay: the spoiler decides
    elif shop_slots:
        referenced = set(probe.referenced)
        copies = Counter(shuffled[g]['vanilla'] for g in shop_slots)
        by_folder = defaultdict(list)
        for gid in shop_slots:
            by_folder[shuffled[gid]['folder']].append(gid)
        for folder, slots in sorted(by_folder.items()):
            wanted = (shop_rng.below(4) + 1 if options['shopsanity'] == 'random' else int(options['shopsanity']))
            for gid in shop_rng.shuffle(slots):
                if wanted <= 0:
                    break
                item = shuffled[gid]['vanilla']
                if item in referenced and copies[item] <= 1:
                    continue
                copies[item] -= 1
                selected_shops.add(gid)
                wanted -= 1
    for gid in shop_slots:
        if gid not in selected_shops:
            del shuffled[gid]
    report(f'Shuffled chests: {len(shuffled)} groups ({sum(e["kind"] != "junk" for e in shuffled.values())} in logic).')

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
        logic.virtual[vname(entry['id'])] = list(entry['ap']) + list(entry.get('guards', []))
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
    _, reachable_all, _ = logic.sweep({l: None for l in logic.location_names()}, logic.new_state(everything))
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
    # --- item pool ------------------------------------------------------------
    pool = []
    for gid, entry in shuffled.items():
        item = entry['vanilla']
        if is_mapcompass(item) and options['shuffle_mapcompass'] == 'remove':
            item = 'Rupees (5)'
        if entry['source'] == 'shop':
            item = SHOP_FILLER  # the displaced purchase stays sold in other slots
        if item in ring_keys:
            item = 'Rupees (5)'
        pool.append(item)
    for ring in sorted(ring_keys.values()):
        fillers = [i for i in pool if i not in relevant and not is_mapcompass(i) and not is_key(i)]
        if not fillers:
            raise FillError('Not enough filler locations for the key rings.')
        pool.remove(min(fillers, key=lambda i: FILLER_PRIORITY.index(i) if i in FILLER_PRIORITY else 99))
        pool.append(ring)
    for soul in souls['items']:
        fillers = [i for i in pool if i not in relevant and not is_mapcompass(i) and not is_key(i)]
        if not fillers:
            raise FillError('Not enough filler chests for every soul.')
        victim = min(fillers, key=lambda i: FILLER_PRIORITY.index(i) if i in FILLER_PRIORITY else 99)
        pool.remove(victim)
        pool.append(soul)
    logic_locations = sorted(g for g in shuffled if vname(g) in logic.virtual)
    restricted_dungeon = {}   # item -> (zone rule, dungeon)
    for item in set(pool):
        if item in ring_keys.values():
            rule = options['shuffle_smallkeys']
        elif item in moved_boss:
            rule = options['shuffle_bosskeys']
        elif is_key(item) or (is_mapcompass(item) and options['shuffle_mapcompass'] == 'dungeon'):
            rule = 'dungeon'
        else:
            continue
        if rule != 'keysanity':
            restricted_dungeon[item] = (rule, item[item.index('(') + 1:-1])
    progression = [i for i in pool if i in relevant]
    if len(progression) > len(logic_locations):
        raise FillError(f'{len(progression)} progression items for {len(logic_locations)} chests in logic: '
                        'enable zone matching or reduce the options.')
    family_tiers = tier_layout(matches, shuffled, pool)
    folder_dungeon = {gid: _dungeon_name(e['folder']) for gid, e in shuffled.items()}

    canonical_cache = {}

    def canonical(item, gid):
        key = (item, shuffled[gid]['folder'])
        if key not in canonical_cache:
            canonical_cache[key] = item_actor(item, shuffled[gid]['folder'])
        return canonical_cache[key]

    def allowed(item, gid):
        rule, dungeon = restricted_dungeon.get(item, (None, None))
        if rule == 'dungeon' and folder_dungeon[gid] != dungeon:
            return False
        if rule == 'any_dungeon' and folder_dungeon[gid] is None:
            return False
        if rule == 'overworld' and folder_dungeon[gid] is not None:
            return False
        return can_take(canonical(item, gid), shuffled[gid]['form'])

    # OoTR/AP vanilla-key compensation: with vanilla Fire Temple keys the logic
    # starts with one extra key (the vanilla layout expects the hammer door order).
    starting = Counter()
    if 'Small Key (Fire Temple)' not in key_dungeons and 'Small Key (Fire Temple)' not in ring_keys:
        starting['Small Key (Fire Temple)'] += 1

    def sweep(placed, counts=None):
        placements = dict(base)
        for gid in logic_locations:
            placements.setdefault(vname(gid), None)
        for gid, item in placed.items():
            if vname(gid) in logic.virtual:
                placements[vname(gid)] = item
        state = logic.new_state(Counter(counts or {}) + starting)
        return _sweep_with_requirements(logic, placements, state)

    return SimpleNamespace(
        data=data, options=options, settings=settings, logic=logic, matches=matches, shuffled=shuffled,
        pool=pool, relevant=relevant, progression=progression, logic_locations=logic_locations,
        restricted_dungeon=restricted_dungeon, allowed=allowed, sweep=sweep, base=base, souls=souls,
        unmatched_ap=unmatched_ap, family_tiers=family_tiers, starting=starting, report=report,
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
    unmatched_ap, family_tiers, report = c.unmatched_ap, c.family_tiers, c.report
    rng = DetRandom(hashlib.sha256((seed_key + '\0full-fill-v1').encode()).digest())
    if forced is not None:
        state, collected, spheres = sweep(forced)
        sphere_of = {loc[len('Remake|'):]: index for index, sphere in enumerate(spheres)
                     for loc in sphere if loc.startswith('Remake|')}
        return {'beatable': state.has('Triforce'), 'spheres': sphere_of, 'sphere_count': len(spheres),
                'unreachable': sorted(g for g in logic_locations if vname(g) not in collected)}

    last_error = 'no attempt'
    for attempt in range(MAX_ATTEMPTS):
        placed = {}
        failed = False
        rest = [i for i in pool if i not in relevant]
        rest_counter = Counter(rest)
        # Dungeon-bound items outside the logic (maps, compasses) first, in
        # chests the logic cannot use whenever possible.
        for item in rng.shuffle([i for i in rest if i in restricted_dungeon]):
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
        # --- independent verification and progressive-order repair ----------
        def verify(candidate):
            state, collected, spheres = sweep(candidate)
            if not state.has('Triforce'):
                return None, 'victory not guaranteed'
            if options['accessibility'] == 'full':
                missing = [g for g in logic_locations if vname(g) not in collected]
                if missing:
                    return None, f'{len(missing)} unreachable chests: ' + ', '.join(
                        str(shuffled[g]['ap'][:1]) for g in missing[:3])
            return spheres, None

        spheres, error = verify(placed)
        if error:
            last_error = error
            continue
        tiers = None
        for repair in range(400):
            sphere_of = {loc: index for index, sphere in enumerate(spheres) for loc in sphere}
            tiers, error, family = assign_tiers(placed, base, sphere_of, options, rng, logic, sweep, shuffled,
                                                family_tiers)
            if not error:
                break
            # Swap one copy of the offending family with another logic chest.
            sources = [g for g, item in placed.items() if item == family]
            source = rng.choice(sources)
            targets = [g for g in logic_locations if placed[g] != family
                       and allowed(placed[g], source) and allowed(family, g)]
            if not targets:
                break
            target = rng.choice(targets)
            candidate = dict(placed)
            candidate[source], candidate[target] = placed[target], placed[source]
            new_spheres, problem = verify(candidate)
            if problem is None:
                placed, spheres = candidate, new_spheres
        if error:
            last_error = error
            continue
        sphere_of = {loc: index for index, sphere in enumerate(spheres) for loc in sphere}
        report(f'Beatable seed found (attempt {attempt + 1}, {len(spheres)} spheres).')
        return _result(data, logic, options, matches, shuffled, placed, tiers, sphere_of, spheres, souls,
                       unmatched_ap, attempt + 1, base)
    raise FillError('No beatable seed in ' + str(MAX_ATTEMPTS) + ' attempts (' + last_error
                    + '). Change the seed or the options.')


def plan_assigned(data, options, groups, enemies, seed_key, assigned, open_forest=True, progress=None,
                  extra=None, labels=None, order=None):
    """Plan with placements chosen elsewhere (Archipelago): gid → item, every shuffled gid.

    Items of other players are given as a stand-in by the caller. Progressive
    tiers follow ``order`` (gid → sphere of the multiworld playthrough) when
    given, else the local sweep (every copy of a family is local). Victory is
    not required here: items may come from other worlds.
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
    state, collected, spheres = c.sweep(placed)
    sphere_of = {loc: index for index, sphere in enumerate(spheres) for loc in sphere}
    tiers = {}
    for family in PROGRESSIVE:
        rank = ((lambda g: order.get(g) if order.get(g) is not None else 10 ** 6) if order is not None
                else (lambda g: sphere_of.get(vname(g), 10 ** 6)))
        sources = sorted((g for g, item in placed.items() if item == family), key=lambda g: (rank(g), g))
        if not sources:
            continue
        layout = c.family_tiers.get(family)
        if layout is None or len(layout) != len(sources):
            raise FillError(f'Unexpected number of {family}: every copy must stay in this world.')
        tiers.update(zip(sources, layout))
    c.report(f'Archipelago placements applied ({len(spheres)} local spheres).')
    result = _result(data, c.logic, c.options, c.matches, c.shuffled, placed, tiers, sphere_of, spheres, c.souls,
                     c.unmatched_ap, 0, c.base)
    for row in result['spoiler']:
        if labels and row['id'] in labels:
            row['item'] = labels[row['id']]
    return result


def _dungeon_name(folder):
    from oot_rando.game.remake_world import FOLDER_DUNGEON
    return FOLDER_DUNGEON.get(folder)


def _sweep_with_requirements(logic, placements, state):
    return logic.sweep(placements, state)


def tier_layout(matches, shuffled, pool):
    """Tiers given by shuffled copies of each progressive family.

    Unshuffled sources keep their native behaviour: a chest or a static gift
    (Darunia) keeps its own tier, the other sources upgrade dynamically and are
    counted as the highest tiers. Shuffled copies take the lowest free tiers.
    """
    layout = {}
    covered = {l for gid in shuffled for l in matches[gid]['ap']}
    for family, actors in PROGRESSIVE.items():
        count = pool.count(family)
        if not count:
            continue
        static = set()
        for gid, entry in matches.items():
            if gid not in shuffled and entry['vanilla'] == family and entry['before'] in actors \
                    and entry['source'] in ('chest', 'freestanding'):
                static.add(actors.index(entry['before']))
        for location, (tier_family, tier) in STATIC_TIER_SOURCES.items():
            if tier_family == family and location not in covered:
                static.add(tier)
        free = [index for index in range(len(actors)) if index not in static]
        layout[family] = free[:count] if len(free) >= count else None
    return layout


def assign_tiers(placed, base, sphere_of, options, rng, logic, sweep, shuffled, family_tiers=None):
    """Give each progressive copy its remake tier actor (lowest tier first)."""
    tiers = {}
    for family, actors in PROGRESSIVE.items():
        sources = sorted((g for g, item in placed.items() if item == family),
                         key=lambda g: (sphere_of.get(vname(g), 10 ** 6), rng.below(1 << 30)))
        if not sources:
            continue
        shuffled_tiers = (family_tiers or {}).get(family)
        if shuffled_tiers is None:
            return None, f'unexpected number of {family}', family
        if len(sources) != len(shuffled_tiers):
            return None, f'unexpected number of {family}', family
        if not options['progressive_order']:
            sources = rng.shuffle(sources)
        for gid, tier in zip(sources, shuffled_tiers):
            tiers[gid] = tier
        if not options['progressive_order']:
            continue
        spheres = [sphere_of.get(vname(g), 10 ** 6) for g in sources]
        if len(set(spheres)) != len(spheres):
            return None, f'two {family} levels in the same sphere', family
        fixed = [loc for loc, item in base.items() if item == family and not loc.startswith('Remake|')]
        fixed_spheres = [sphere_of[loc] for loc in fixed if loc in sphere_of]
        low = min(shuffled_tiers)
        dynamic = len(shuffled_tiers) < len(actors) and max(shuffled_tiers) < len(actors) - 1
        if fixed_spheres:
            if low > 0 and min(spheres) <= max(fixed_spheres):
                return None, f'{family}: higher level reachable before the original item', family
            if low == 0 and dynamic and family in BASE_REQUIRED and min(fixed_spheres) <= max(spheres):
                return None, f'{family}: original upgrade reachable before the shuffled item', family
        if options['progressive_strict'] and len(sources) > 1:
            for index in range(1, len(sources)):
                trimmed = {g: (None if g in sources[index - 1:] else item) for g, item in placed.items()}
                _, collected, _ = sweep(trimmed)
                if vname(sources[index]) in collected:
                    return None, f'{family}: level {index + 1} reachable without level {index}', family
    return tiers, None, None


def _result(data, logic, options, matches, shuffled, placed, tiers, sphere_of, spheres, souls,
            unmatched_ap, attempts, base):
    placements, checks, spoiler = [], [], []
    for gid in sorted(shuffled):
        entry = shuffled[gid]
        item = placed[gid]
        source = entry.get('source', 'chest')
        canonical = item_actor(item, entry['folder'], tiers.get(gid))
        if (item.startswith('Boss Key (') and 'Ganons Castle' not in item
                and options['shuffle_bosskeys'] in ('any_dungeon', 'keysanity')):
            from oot_rando.patching.key_adapter import boss_actor, item_folder
            canonical = boss_actor(item_folder(item))   # opens its own dungeon's boss door anywhere
        actor = form_actor(canonical, entry.get('form', 'chest'), airborne=source == 'skulltula')
        label = SOURCE_LABELS.get(source, source)
        name = entry['ap'][0] if entry['kind'] == 'exact' else (
            f'{entry["folder"]} — {label} {str(entry["hash"])[-6:]}' if entry['hash'] else gid)
        placements.append({'id': gid, 'folder': entry['folder'], 'hash': entry['hash'], 'kind': entry['kind'],
                           'source': source, 'form': entry.get('form', 'chest'),
                           'before': entry['before'], 'after': actor, 'item': item,
                           'resources': sorted({v['resource'] for v in entry['variants']}),
                           'variants': [(v['resource'], v['index']) for v in entry['variants'] if 'index' in v],
                           'patches': _patches(entry), 'ap_locations': entry['ap'],
                           'sphere': sphere_of.get(vname(gid)), 'event': entry['event']})
        spoiler.append({'id': gid, 'location': name, 'item': soul_label(item) if item.startswith('Soul (') else item,
                        'ap_item': item, 'actor': actor, 'before': entry['before'], 'source': source,
                        'sphere': sphere_of.get(vname(gid)), 'ap_locations': entry['ap']})
    playthrough = []
    for index, sphere in enumerate(spheres):
        names = []
        for location in sphere:
            if location.startswith('Remake|'):
                gid = location[len('Remake|'):]
                item = placed.get(gid)
                if item and (item in logic.referenced | set(souls['items']) or item in logic.bundles):
                    names.append(f'{shuffled[gid]["ap"][0] if shuffled[gid]["ap"] else gid} : {item}')
        if names:
            playthrough.append({'sphere': index, 'items': sorted(names)})
    checks = tracker_checks(data, matches, shuffled)
    return {'placements': placements, 'checks': checks, 'spoiler': spoiler, 'playthrough': playthrough,
            'souls': souls, 'matches': matches, 'unmatched_ap': unmatched_ap, 'attempts': attempts,
            'coverage': dict(coverage_summary(matches), shuffled=len(shuffled),
                             in_logic=sum(1 for g in shuffled if shuffled[g]['kind'] != 'junk'),
                             souls=len(souls['items']), soul_enemies=len(souls['edits']),
                             soul_doors=len(souls.get('door_edits', []))),
            'options': options,
            'tracking_logic': {
                'settings': logic.settings,
                'exits': [[a, b, sorted(items)] for (a, b), items in logic.extra_exit_requirements.items()],
                'locations': {name: sorted(items) for name, items in logic.extra_location_requirements.items()},
                'virtual': {name: list(members) for name, members in logic.virtual.items()}}}


REPEATABLE = ('pots', 'bushes', 'rocks', 'crates', 'beehives')


def _entry_zone(data, entry, gid):
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
        if entry['kind'] in ('exact', 'group'):
            covered.update(entry['ap'])
        label = SOURCE_LABELS.get(source, source)
        name = entry['ap'][0] if entry['kind'] == 'exact' and entry['ap'] else (
            f'{label.capitalize()} {str(entry["hash"])[-6:]}' if entry.get('hash') else gid)
        zone = _entry_zone(data, entry, gid)
        checks.append({'id': gid, 'zone': zone, 'region': zone_label(zone),
                       'category': 'full_' + ('chests' if source == 'chest' else source), 'name': name,
                       'randomized': gid in shuffled, 'repeatable': source in REPEATABLE,
                       'collection_state': 'unverified', 'logic': entry['kind']})
    for location in sorted(data.location_table):
        areas = data.location_areas(location)
        if location in covered or data.location_type(location) not in TRACKED_TYPES:
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


SOURCE_LABELS = {'chest': 'chest', 'skulltula': 'skulltula', 'shop': 'shop', 'freestanding': 'freestanding',
                 'npc': 'NPC', 'boss': 'dungeon reward', 'bossheart': 'boss heart container',
                 'fairy': 'great fairy', 'quest': 'quest reward', 'scrub': 'business scrub', 'pots': 'pot', 'bushes': 'bush', 'rocks': 'rock', 'crates': 'crate',
                 'beehives': 'beehive'}


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
    return result


def replay(data, options, groups, enemies, placements, open_forest=True, extra=None):
    """Independent re-check of finished placements (used by verify_full)."""
    return plan(data, options, groups, enemies, 'replay', open_forest, forced=placements, extra=extra)
