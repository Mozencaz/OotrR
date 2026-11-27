"""Static verification of a complete-randomizer seed (no game launch).

Usage: python -m oot_rando verify GAME.nup SEED_FOLDER

The generator's plan is not reused: placements are read back from the spoiler and the
produced files. Checks 1, 2 and 5 rebuild the expected files with the same patch
functions as the generator, and check 6 uses the same ``Logic``: they prove that the
seed is exactly what this version produces from its spoiler (reproducibility, scope of
every diff), not that a patch or a rule is right. ``output_invariants`` adds checks that
call no patch and no rule (RESTBL allocations, GameData names used by the flows).

Checks:
1. every map differs from the original NUP only by the spoiled rewards
   (``Drop__DropActor`` of chests, skulltulas and environment objects, ``Gyaml``
   of freestanding items and shop shelves), ``Presence`` blocks of soul enemies
   and the known QoL edits;
2. every event flow differs only by the spoiled gift parameters;
3. both age variants of a source carry the same reward;
4. every reward actor exists (game pack, generated soul or derived pack) and
   every generated actor has its RSDB rows and RESTBL entry (souls: saved flag);
5. every progressive copy, and every native source of a fixed level, gives its own
   token, converted to the next level by the item-get flow (or right after its gift);
6. a fresh sweep of the remake logic over the spoiled placements is beatable;
7. the output invariants (:func:`output_invariants`).
"""
from collections import Counter, defaultdict
import copy
import json
import struct
import sys
import zlib
from pathlib import Path

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries, sarc
from oot_rando.game.world_maps import effective_members
from oot_rando.randomizer.artifact import read_artifact
from oot_rando.patching.randomize_kokiri import RESTBL, MAP
from oot_rando.patching.qol_patches import (STATIC, KOKIRI_SHOP_MAPS, KOKIRI_SHOP_FLAG, shop_actor,
                                            NOCTURNAL_FIELD, is_nocturnal_skulltula)
from oot_rando.formats import byml_codec
from oot_rando.game.resource_allocations import allocation
from oot_rando.patching.soul_adapter import murmur3, RSDB_FILES, GAMEDATA, FLAG_PREFIX
from oot_rando.game.remake_world import PROGRESSIVE, item_actor, TREASURE_GAME_REWARD
from oot_rando.game.item_forms import is_derived, canonical_of
from oot_rando.patching.key_adapter import is_key_actor
from oot_rando.patching.progressive import applied_flag, is_token
from oot_rando.randomizer.randomizer_core import save_marker
from oot_rando.formats.evfl_tools import links_to, params_by_event, parse_flow
from oot_rando.game.extra_sources import scan_world
from oot_rando.logic.world import World
from oot_rando.patching import blue_fire_arrows
from oot_rando.patching import bomb_refills
from oot_rando.patching import cuccos
from oot_rando.patching import elemental_arrows
from oot_rando.patching import game_defaults
from oot_rando.patching import gerudo_fortress
from oot_rando.patching import link_goron
from oot_rando.patching import magic_capacity
from oot_rando.patching import special_item_shuffle
from oot_rando.patching.event_info import flow_path as event_flow_path
from oot_rando.patching.master_sword_item import MASTER_SWORD_ACTOR
from oot_rando.patching.progressive import ACTION_GUIDE
from oot_rando.patching.progressive import AFTER_PREFIX
from oot_rando.patching.progressive import CONVERTER_ENTRY
from oot_rando.patching.progressive import hook_sites
from oot_rando.patching.story_fixes import escape_stones

QOL_MAPS = {MAP, STATIC}



def _seed_lazy(actor):
    """IsCheckLazy of a once-only source: lazy since 0.5.3, immediate in earlier seeds."""
    value = ((actor or {}).get('Presence') or {}).get('IsCheckLazy')
    return value if isinstance(value, bool) else True


def _flow_events(raw):
    return parse_flow(raw).flowchart.events


def _event_snapshot(raw):
    return params_by_event(parse_flow(raw))


def output_invariants(nup, members, seed_dir, d):
    """Checks read from the produced files and the game only: no patch function and no
    logic is called, so a bug shared by the generator and the replay above cannot hide here.

    * every resource that grew has an allocation grown at least as much in the seed's
      RESTBL, and every new resource has an entry (a short allocation crashes the game);
      so does every grown file of a pack that has an entry of its own (a short one is not
      loaded: the actor is missing);
    * every GameData name that a changed event flow starts to use (``GameDataName``
      parameters absent from the game's flow) exists in the seed's GameData.
    """
    manifest = json.loads((Path(seed_dir) / 'manifest.json').read_text(encoding='utf-8'))
    romfs = Path(seed_dir) / 'romfs'

    def unpack(path, raw):
        return decompress(raw, d) if path.endswith('.zs') else raw

    seed_table, game_table = unpack(RESTBL, (romfs / RESTBL).read_bytes()), unpack(RESTBL, nup.read(members[RESTBL]))
    grown = new = 0
    for path in sorted(manifest['files']):
        if path == RESTBL:
            continue
        size, after = len(unpack(path, (romfs / path).read_bytes())), allocation(seed_table, path)
        if path not in members:
            new += 1
            if after is None:
                raise ValueError('New resource without a RESTBL entry: ' + path)
            continue
        source = unpack(path, nup.read(members[path]))
        checked = {path: size - len(source)}
        if path.endswith('.pack.zs'):   # each file of a pack has its own allocation
            produced = sarc(unpack(path, (romfs / path).read_bytes()))
            for member, raw in sarc(source).items():
                if member in produced:
                    checked[member] = max(checked.get(member, 0), len(produced[member]) - len(raw))
        for name, growth in checked.items():
            before = allocation(game_table, name)
            if before is not None and growth > 0:
                grown += 1
                after = allocation(seed_table, name)
                if after is None or after < before + growth:
                    raise ValueError(f'RESTBL allocation too small for {name}: {after} < {before} + {growth}')

    def names(raw):
        found = set()
        for event in parse_flow(raw).flowchart.events:
            params = getattr(event.data, 'params', None)
            value = dict(params.data).get('GameDataName') if params is not None else None
            if isinstance(value, str):
                found.add(value)
        return found
    data = byml_codec.load(unpack(GAMEDATA, (romfs / GAMEDATA).read_bytes()))['root']['Data']
    known = {int(e['Hash']) for table in data.values() for e in table if isinstance(e, dict) and 'Hash' in e}
    flags = 0
    for path in sorted(p for p in manifest['files'] if p.endswith('.bfevfl.zs')):
        vanilla = names(unpack(path, nup.read(members[path]))) if path in members else set()
        for name in sorted(names(unpack(path, (romfs / path).read_bytes())) - vanilla):
            flags += 1
            if murmur3(name) not in known:
                raise ValueError(f'{path} uses a GameData entry the seed does not declare: {name}')
    return {'grown_resources': grown, 'new_resources': new, 'new_flag_references': flags}


def verify(nup_path, seed_dir):
    seed_dir = Path(seed_dir)
    manifest, checks = read_artifact(seed_dir)
    spoiler = json.loads((seed_dir / 'spoiler.json').read_text(encoding='utf-8'))
    if 'full_randomizer' not in manifest:
        raise ValueError('Seed without the full randomizer.')
    from oot_rando.randomizer.randomizer_core import GENERATOR_VERSION
    if manifest.get('generator_version') != GENERATOR_VERSION:
        # The expected files are rebuilt with today's actor names and patches.
        raise ValueError(f'Only seeds of generator {GENERATOR_VERSION} can be replayed '
                         f'(this one: {manifest.get("generator_version")}).')
    nup = Nup(nup_path)
    d = dictionaries(nup)
    members = effective_members(nup)
    out = lambda path: decompress((seed_dir / 'romfs' / path).read_bytes(), d)
    invariants = output_invariants(nup, members, seed_dir, d)
    full = [p for p in spoiler['placements'] if str(p.get('category', '')).startswith('full_')]
    # Reconstruct both alternate-talk rewards from the spoiler, rather than
    # accepting the generator's fallback configuration as independent evidence.
    npc_gifts = {}
    for key, location in (('goron', 'GC Rolling Goron as Adult'), ('zora', 'ZD King Zora Thawed')):
        gid = 'npc#' + location
        placement = next((p for p in full if p['id'] == gid), None)
        if placement:
            npc_gifts[key] = {'actor': placement.get('reward_actor', placement['actor']),
                              'flag': 'RandoCheck.' + manifest['seed_id'][:16] + '.' + gid}
    if npc_gifts != (manifest.get('skips', {}).get('story_fixes') or {}).get('npc_gifts', {}):
        raise ValueError('Alternate NPC gifts differ from their shuffled rewards.')
    _, groups, enemies, extra = scan_world(nup, d, members)
    # Fresh logic sweep from the spoiler; it also names the progressive tokens.
    from oot_rando.randomizer import full_randomizer
    plan = full_randomizer.replay(World(), manifest['settings']['full'], copy.deepcopy(groups),
                                  copy.deepcopy(enemies), {p['id']: p['ap_item'] for p in full},
                                  manifest['settings']['open_forest'], extra=copy.deepcopy(extra),
                                  # options drawn from the seed key (random key rings) must match
                                  seed_key=(manifest['settings'].get('archipelago') or {}).get('seed_key')
                                  or manifest['seed_id'])
    tokens, natives = plan['progressive']['tokens'], plan['progressive']['natives']
    # Fake item traps: in chests and ground checks (never gifts or shops), as their own actor.
    from oot_rando.catalog.traps import is_trap_item, trap_actor
    from oot_rando.game.extra_sources import EVENT_SOURCES
    placed_trap_items = sorted({p['ap_item'] for p in full if is_trap_item(p['ap_item'])})
    for placement in full:
        if not is_trap_item(placement['ap_item']):
            continue
        reward = placement.get('reward_actor', placement['actor'])
        if (placement.get('source', 'chest') in EVENT_SOURCES + ('shop',)
                or (canonical_of(reward) if is_derived(reward) else reward) != trap_actor(placement['ap_item'])):
            raise ValueError('Fake item trap outside a chest or a pickup: ' + placement['id'])
    from oot_rando.logic import rando_options
    trap_level = rando_options.stored_value(manifest['settings']['full'] or {}, 'fake_item_traps')
    if placed_trap_items and trap_level == 'none':
        raise ValueError('Fake item traps without their option.')
    for placement in full:
        reward = placement.get('reward_actor', placement['actor'])
        canonical = canonical_of(reward) if is_derived(reward) else reward
        if canonical != tokens.get(placement['id'], canonical) or (is_token(canonical) and placement['id'] not in tokens):
            raise ValueError('Progressive copy without its own token: ' + placement['id'])
    # Expected edits, rebuilt from the original game and the spoiler only.
    map_edits = defaultdict(dict)     # resource -> actor index -> {field: actor}
    event_edits = defaultdict(dict)   # resource -> (event, param) -> actor
    for native in natives:
        for patch in native['patches']:
            if 'event' in patch:
                event_edits[patch['resource']][(patch['event'], patch['param'])] = native['after']
            else:
                field = 'Gyaml' if patch['path'][-1] == 'Gyaml' else 'Drop__DropActor'
                map_edits[patch['resource']].setdefault(patch['path'][1], {})[field] = native['after']
    for placement in full:
        gid, actor = placement['id'], placement['actor']
        if gid in groups:
            if actor != placement['before']:
                for variant in groups[gid]:
                    map_edits[variant['resource']].setdefault(variant['index'], {})['Drop__DropActor'] = actor
                    if gid == TREASURE_GAME_REWARD:
                        map_edits[variant['resource']][variant['index']]['DropViewActor'] = actor
            continue
        entry = extra.get(gid)
        if entry is None:
            raise ValueError('Location unknown to the game: ' + gid)
        if entry.get('source') == 'scrub':
            from oot_rando.game.extra_sources import scrub_price
            price = scrub_price(manifest['settings']['full']['shuffle_scrubs'], manifest['seed_id'], entry)
            for variant in entry['variants']:
                if price != variant['price']:
                    event_edits[variant['resource']][(variant['event'], 'Price')] = price
        if actor == entry['before']:
            continue
        for variant in entry['variants']:
            if 'event' in variant:
                event_edits[variant['resource']][(variant['event'], variant['param'])] = actor
            else:
                map_edits[variant['resource']].setdefault(variant['index'], {})[variant['field']] = actor
    tracking = json.loads((seed_dir / 'tracking.json').read_text(encoding='utf-8')) if manifest.get('tracking') else {}
    repeat_first, repeat_fallback = defaultdict(dict), defaultdict(list)
    textured_sources = defaultdict(dict)
    for record in tracking.get('repeatables', []):
        for variant in record['variants']:
            if variant.get('textured_actor'):
                textured_sources[variant['resource']][variant['index']] = variant
            # Seeds made before sources were left as they are: Presence and a vanilla copy.
            if not variant['native_once'] and 'fallback_hash' in variant:
                repeat_first[variant['resource']][variant['index']] = record
                repeat_fallback[variant['resource']].append((record, variant))
    repeat_boards = defaultdict(list)
    for record in tracking.get('repeatables', []):
        for shelf in record.get('shelves', []):
            repeat_boards[shelf['resource']].append(shelf)
    report ={'maps': 0, 'rewards': 0, 'presence': 0, 'events': 0}
    always_skulltulas = bool((manifest.get('settings') or {}).get('skulltulas_always_present'))
    # Per-chest opening flags: each chest's own event (chest_flags), rebuilt from the
    # spoiler's chests, the chests left in place and the original maps.
    chest_records = manifest.get('skips', {}).get('chest_flags', {}).get('records', [])
    if manifest.get('skips', {}).get('chest_flags') is not None:
        from oot_rando.patching import chest_flags
        settings_rows = {row['__RowId']: row for row in Byml(out(chest_flags.EVENT_SETTINGS)).root}
        original_rows = {row['__RowId']: row for row in Byml(decompress(nup.read(members[chest_flags.EVENT_SETTINGS]), d)).root}
        chest_spoiler = [{'id': p['id'], 'source': 'chest',
                          'variants': [(v['resource'], v['index']) for v in groups.get(p['id'], []) if 'index' in v]}
                         for p in full if p.get('source') == 'chest']
        chest_spoiler += chest_flags.vanilla_placements(plan['matches'], full)
        original_map = lambda path: Byml(decompress(nup.read(members[path]), d)).root
        expected_records, _ = chest_flags.plan_records(chest_spoiler, original_map, manifest['seed_id'], original_rows)
        if expected_records != chest_records:
            raise ValueError('Chest opening flags differ from the spoiler.')
        for record in chest_records:
            if settings_rows.get(record['event'], {}).get('EntryPointName') != record['event']:
                raise ValueError('Missing chest event row: ' + record['event'])
            for variant in record['variants']:
                map_edits[variant['resource']].setdefault(variant['index'], {})['GetEventName'] = record['event']
        report['chest_flags'] = len(chest_records)
    mailbox = manifest.get('skips', {}).get('ap_mailbox')
    if mailbox is not None:
        # Archipelago reception: the global sequence's watcher and its event row.
        from oot_rando.patching import ap_mailbox
        # Records rebuilt from the patch alone (the remote items of this world).
        expected = ap_mailbox.records((manifest.get('archipelago') or {}).get('remote', []))
        if expected != mailbox['items']:
            raise ValueError('Archipelago reception differs from the patch.')
        dispatch = 'signal' in mailbox
        if dispatch and mailbox['signal'] != ap_mailbox.SIGNAL:
            raise ValueError('Unexpected Archipelago mailbox signal.')
        main_update = ap_mailbox.patch_main_update(nup.read(members[ap_mailbox.MAIN_UPDATE]), expected,
                                                   dispatch=dispatch)
        watch = manifest.get('skips', {}).get('progressive_watch')
        if watch:
            from oot_rando.patching import progressive
            main_update = progressive.patch_main_update(main_update, watch['tokens'])
        if (seed_dir / 'romfs' / ap_mailbox.MAIN_UPDATE).read_bytes() != main_update:
            raise ValueError('Unexpected global sequence (Archipelago reception).')
        rows = {r['__RowId']: r for r in Byml(out(ap_mailbox.EVENT_SETTINGS)).root}
        flags = {entry['Hash'] for entry in byml_codec.load(out(GAMEDATA))['root']['Data']['Bool']}
        if dispatch and murmur3(ap_mailbox.SIGNAL) not in flags:
            raise ValueError('Missing Archipelago mailbox signal.')
        for record in expected:
            event = ap_mailbox.DISPATCH if dispatch else record['event']
            row = rows.get(event)
            if not row or row.get('EntryPointName') != event or not row.get(
                    'FlowchartFileName', '').endswith('/' + ap_mailbox.FLOW + '.evfc'):
                raise ValueError('Missing Archipelago reception event row: ' + record['event'])
            if murmur3(record['recv']) not in flags or murmur3(record['got']) not in flags:
                raise ValueError('Missing Archipelago reception flag: ' + record['key'])
        report['ap_reception'] = len(expected)
    watch = manifest.get('skips', {}).get('progressive_watch')
    if watch:
        # Safety net of the progressive tokens: its watchers, event row and dependencies.
        from oot_rando.patching import progressive
        all_tokens = sorted(set(plan['progressive']['tokens'].values()) | {n['token'] for n in plan['progressive']['natives']})
        if watch['tokens'] != all_tokens:
            raise ValueError('Progressive token watchers differ from the spoiler.')
        if mailbox is None:
            if (seed_dir / 'romfs' / progressive.MAIN_UPDATE).read_bytes() != progressive.patch_main_update(
                    nup.read(members[progressive.MAIN_UPDATE]), all_tokens):
                raise ValueError('Unexpected global sequence (progressive tokens).')
        row = {r['__RowId']: r for r in Byml(out(progressive.EVENT_SETTINGS)).root}.get(progressive.WATCH_EVENT)
        if not row or row.get('EntryPointName') != progressive.CONVERTER_ENTRY or not row.get(
                'FlowchartFileName', '').endswith('/' + progressive.ACTION_GUIDE + '.evfc'):
            raise ValueError('Missing progressive converter event row.')
        report['progressive_watch'] = len(all_tokens)
    blue_arrows = bool((manifest['settings'].get('full') or {}).get('blue_fire_arrows', False))
    if bool(manifest.get('skips', {}).get('blue_fire_arrows')) != blue_arrows:
        raise ValueError('Blue-fire arrow patch differs from the settings.')
    for path, fix in blue_fire_arrows.resource_fixes():
        source = decompress(nup.read(nup.latest('romfs/' + path)), d)
        destination = seed_dir / 'romfs' / path
        actual = decompress(destination.read_bytes(), d) if destination.exists() else source
        expected = fix(source) if blue_arrows else source
        if actual != expected:
            raise ValueError('Blue-fire arrow resource differs from the settings: ' + path)
    if blue_arrows:
        report['blue_fire_arrows'] = True
    if manifest.get('skips', {}).get('elemental_arrows'):
        for path, fix in elemental_arrows.resource_fixes():
            raw = (seed_dir / 'romfs' / path).read_bytes()
            raw = decompress(raw, d) if path.endswith('.zs') else raw
            # Seeds before 0.12.20 hold the private bow parameter (crashes the menu).
            old = path == elemental_arrows.PACK and elemental_arrows.OLD_PARAM in sarc(raw)
            if fix(raw) != raw and not old:
                raise ValueError('Elemental arrow protection missing: ' + path)
        report['elemental_arrows'] = True
    if 'bomb_refills' in manifest.get('skips', {}):
        recorded = manifest['skips']['bomb_refills']
        if not set(bomb_refills.NATIVE_PACKS) <= set(recorded):
            raise ValueError('Missing native bomb refill protection.')
        for path in sorted(set(bomb_refills.NATIVE_PACKS) | {
                p for p in manifest['files'] if p.startswith('Pack/Actor/')}):
            pack = sarc(out(path))
            for pouch in bomb_refills.POUCH_PATHS:
                if pouch in pack and byml_codec.load(pack[pouch])['root'].get('SmallBagActor'):
                    raise ValueError('Bomb refill still awards a bag: ' + path)
        report['bomb_refill_packs'] = len(recorded)
    if 'magic_capacity' in manifest.get('skips', {}):
        recorded = manifest['skips']['magic_capacity']
        if not set(magic_capacity.NATIVE_PACKS) <= set(recorded):
            raise ValueError('Missing native magic capacity protection.')
        for path in sorted(set(magic_capacity.NATIVE_PACKS) | {
                p for p in manifest['files'] if p.startswith('Pack/Actor/')}):
            raw = out(path)
            if magic_capacity.patch_pack(raw)[1]:
                raise ValueError('Item still awards magic capacity: ' + path)
        raw = out(magic_capacity.TABLE)
        if magic_capacity.patch_table(raw) != raw:
            raise ValueError('Pouch database still awards implicit magic capacity.')
        report['magic_capacity_packs'] = len(recorded)
    from oot_rando.patching import story_fixes
    openings = (manifest.get('skips', {}).get('story_fixes') or {}).get('openings') or {}
    gerudo_story = manifest.get('skips', {}).get('story_fixes') or {}
    if 'gerudo_membership' in gerudo_story:
        for path, fix in gerudo_fortress.resource_fixes():
            original = nup.read(members[path])
            expected, details = fix(decompress(original, d) if path.endswith('.zs') else original)
            if path == link_goron.SCHEDULES and 'link_goron_rolling' in gerudo_story:
                expected, _ = link_goron.stunnable_before_intro(expected)
            actual = (seed_dir / 'romfs' / path).read_bytes()
            actual = decompress(actual, d) if path.endswith('.zs') else actual
            if details != gerudo_story['gerudo_membership'].get(path) or actual != expected:
                raise ValueError('Unexpected Gerudo membership resource: ' + path)
        if not gerudo_fortress.expressions_applied(out(GAMEDATA)):
            raise ValueError('Unexpected Gerudo membership expressions.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    if 'link_goron_rolling' in gerudo_story:
        original = decompress(nup.read(members[link_goron.SCHEDULES]), d)
        if 'gerudo_membership' in gerudo_story:
            original, _ = gerudo_fortress.archery_schedule_pack(original)
        expected, details = link_goron.stunnable_before_intro(original)
        if (out(link_goron.SCHEDULES) != expected
                or details != gerudo_story['link_goron_rolling']):
            raise ValueError('Unexpected Darunia Jr. rolling schedule.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    if 'lost_dog_quest' in gerudo_story:
        from oot_rando.patching import lost_dog
        expected, details = lost_dog.quest_from_start(decompress(nup.read(members[lost_dog.CHALLENGES]), d))
        if out(lost_dog.CHALLENGES) != expected or gerudo_story['lost_dog_quest'] != details:
            raise ValueError('Unexpected lost dog quest dependency.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    if 'freed' in openings.get('gerudo_fortress', {}):
        path = gerudo_fortress.CELL_MODULE
        if (seed_dir / 'romfs' / path).read_bytes() != gerudo_fortress.open_completed_cells(nup.read(members[path])):
            raise ValueError('Unexpected completed fortress cell locks.')
        path = gerudo_fortress.UNLOCK_FLOW
        if (seed_dir / 'romfs' / path).read_bytes() != gerudo_fortress.skip_completed_unlocks(
                decompress(nup.read(members[path]), d))[0]:
            raise ValueError('Unexpected completed fortress cell unlocks.')
    for option, details in openings.items():
        defaults = details.get('defaults') or {}
        if game_defaults.read_defaults(out(GAMEDATA), defaults) != defaults:
            raise ValueError('World opening defaults differ from the spoiler: ' + option)
    for key, module, fix in (
            ('light_arrows_medallions', story_fixes.LIGHT_ARROWS_MODULE, story_fixes.light_arrows_on_medallions),
            ('prelude_medallion', story_fixes.PRELUDE_MODULE, story_fixes.prelude_on_forest_medallion)):
        details = (manifest.get('skips', {}).get('story_fixes') or {}).get(key)
        if details is not None:
            expected, report_expected = fix(nup.read(members[module]))
            if details != report_expected or (seed_dir / 'romfs' / module).read_bytes() != expected:
                raise ValueError('Unexpected medallion cutscene trigger: ' + module)
            report['story_fixes'] = report.get('story_fixes', 0) + 1
    if (manifest.get('skips', {}).get('story_fixes') or {}).get('kakariko_burning_medallions') is not None:
        if not story_fixes.kakariko_burning_applied(out(GAMEDATA)):
            raise ValueError('Unexpected Kakariko burning condition in the game data.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    # Cuccos to bring back: the pen's logic module and her lines (the flow is also checked below).
    unpack = lambda path, raw: decompress(raw, d) if path.endswith('.zs') else raw
    report.update(cuccos.check_seed(manifest, members, lambda path: unpack(path, nup.read(members[path])),
                                    lambda path: unpack(path, (seed_dir / 'romfs' / path).read_bytes())))
    if (manifest.get('skips', {}).get('story_fixes') or {}).get('door_song_condition') is not None:
        from oot_rando.logic import rando_options
        requirement = rando_options.stored_value(
            (manifest.get('settings') or {}).get('full') or {}, 'door_of_time_requirement')
        if not story_fixes.door_song_condition_applied(out(GAMEDATA), requirement):
            raise ValueError('Unexpected Door of Time ocarina condition in the game data.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    if (manifest.get('skips', {}).get('story_fixes') or {}).get('scene_conditions') is not None:
        if not story_fixes.scene_expressions_applied(out(GAMEDATA)):
            raise ValueError('Unexpected scene conditions in the game data.')
        opened = bool(((manifest.get('settings') or {}).get('full') or {}).get('open_door_of_time'))
        for module, key, fix in story_fixes.scene_module_fixes():
            # Earlier seeds did not patch these shop and child gate modules.
            if key in ('kakariko_gate_closed', 'kakariko_gate_open', 'bombchu_shop_open', 'link_goron_spawn') and key not in manifest['skips']['story_fixes']:
                continue
            expected, _ = fix(nup.read(members[module]))
            if module == story_fixes.DOOR_MODULE and opened:
                from oot_rando.patching.world_openings import door_always_open
                expected = door_always_open(expected)
            if (seed_dir / 'romfs' / module).read_bytes() != expected:
                raise ValueError('Unexpected scene condition module: ' + module)
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    if (manifest.get('skips', {}).get('story_fixes') or {}).get('sheik_temple') is not None:
        module = story_fixes.SHEIK_TEMPLE_MODULE
        expected, _ = story_fixes.sheik_leaves_the_pedestal(nup.read(members[module]))
        if (not story_fixes.sheik_temple_applied(out(GAMEDATA))
                or (seed_dir / 'romfs' / module).read_bytes() != expected):
            raise ValueError('Unexpected temple Sheik condition.')
        report['story_fixes'] = report.get('story_fixes', 0) + 1
    chest_flows = {}
    for record in chest_records:
        chest_flows.setdefault(record['flow'], []).append(record)
    # Token gifts outside any item get call the converter themselves (recomputed here).

    def produced_flow(name):
        path = event_flow_path(name)
        if path in manifest['files']:
            return out(path)
        return decompress(nup.read(members[path]), d) if path in members else None

    token_sources = [[(v['resource'], v['event']) for v in extra[p['id']]['variants'] if 'event' in v]
                     for p in full if p['id'] in tokens and p['id'] in extra]
    token_sources += [[(patch['resource'], patch['event']) for patch in native['patches'] if 'event' in patch]
                      for native in natives]
    progressive_skip = manifest.get('skips', {}).get('progressive') or {}
    hooks = hook_sites(token_sources, produced_flow, covered=manifest.get('skips', {}).get('gift_get', {}))
    if hooks != progressive_skip.get('hooks', {}):
        raise ValueError('Progressive token gifts differ from the spoiler.')
    soul_actors, soul_expressions_seen = set(), set()
    master_flows = special_item_shuffle.flow_paths(manifest['settings']['full'], members)
    stones = escape_stones(manifest['settings']['full'])
    if set(master_flows) - set(manifest['files']):
        raise ValueError('Missing Master Sword time travel flow.')
    if set(manifest.get('skips', {}).get('master_sword_flows', {})) != set(master_flows):
        raise ValueError('Master Sword flow reports differ from the settings.')
    window_context = [None, None]
    for path in sorted(manifest['files']):
        if path.startswith('Event/EventFlow/'):
            original = decompress(nup.read(members[path]), d)
            if path in master_flows:
                original, details = special_item_shuffle.patch_flow(path, original)
                if details != manifest['skips']['master_sword_flows'][path]:
                    raise ValueError('Unexpected Master Sword ownership guards: ' + path)
                report['master_sword_flows'] = report.get('master_sword_flows', 0) + 1
            # Comfort patches, re-applied independently to the original flow.
            from oot_rando.patching.qol_patches import AREA_PRESENTATIONS, CHEST_FLOW, flow_path, quick_chest
            skips = manifest.get('skips', {})
            if path in {flow_path(name) for name in skips.get('area_presentations', {})}:
                if path not in {flow_path(name) for name in AREA_PRESENTATIONS}:
                    raise ValueError('Unknown area presentation: ' + path)
                from oot_rando.patching.area_presentations import expected_flow
                name = path[len('Event/EventFlow/'):-len('.bfevfl.zs')]
                original = expected_flow(name, original, skips['area_presentations'][name])
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            if path == CHEST_FLOW and skips.get('quick_chest'):
                original = quick_chest(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            from oot_rando.patching.qol_patches import SMALL_CHEST_FLOW, quick_small_chest
            if path == SMALL_CHEST_FLOW and skips.get('quick_small_chest'):
                original = quick_small_chest(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            from oot_rando.patching.qol_patches import ACTION_GUIDE_FLOW, ocarina_guide_on_get, add_skip_windows_with_replay
            if path in {flow_path(name) for name in skips.get('cutscene_windows', {})}:
                if window_context[0] is None:
                    from oot_rando.patching.qol_patches import skip_window_context
                    names = {p[len('Event/EventFlow/'):-len('.bfevfl.zs')] for p in members
                             if p.startswith('Event/EventFlow/') and p.endswith('.bfevfl.zs')}
                    window_context[:] = skip_window_context(lambda p: decompress(nup.read(members[p]), d), names)
                name = path[len('Event/EventFlow/'):-len('.bfevfl.zs')]
                original, windows = add_skip_windows_with_replay(original, window_context[0],
                                                                 window_context[1].get(name, ()))
                if windows != skips['cutscene_windows'][name]:
                    raise ValueError('Different skip windows: ' + path)
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            if path == ACTION_GUIDE_FLOW and skips.get('ocarina_guide'):
                original = ocarina_guide_on_get(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            if path == ACTION_GUIDE_FLOW and skips.get('key_items'):
                # Key rings / dungeon boss keys, rebuilt from the spoiler alone.
                from oot_rando.patching.key_adapter import add_key_hook, key_records
                from oot_rando.patching.ap_mailbox import key_items as mailbox_key_items
                # Plus the keys received from other worlds (same actors, same hook).
                received = set(mailbox_key_items((skips.get('ap_mailbox') or {}).get('items', [])))
                placed = {p['ap_item'] for p in full
                          if p['ap_item'].startswith('Small Key Ring (')
                          or is_key_actor(p.get('reward_actor', p['actor']).removeprefix('Obj_Rando_').removeprefix('Obj_RandoWater_')
                                          .removeprefix('Shop_Rando_'))}
                records = key_records(received | placed)
                if records != skips['key_items']['records']:
                    raise ValueError('Dungeon keys differ from the spoiler.')
                original = add_key_hook(original, records)[0]
                report['key_items'] = len(records)
            if path == ACTION_GUIDE_FLOW and (placed_trap_items or skips.get('fake_traps')):
                # Fake item traps, rebuilt from the spoiler alone.
                from oot_rando.patching.fake_traps import add_trap_hook, trap_records
                records = trap_records(placed_trap_items)
                if records != (skips.get('fake_traps') or {}).get('records'):
                    raise ValueError('Fake item traps differ from the spoiler.')
                original = add_trap_hook(original, records)[0]
                report['fake_traps'] = len(records)
            all_tokens = sorted(set(tokens.values()) | {n['token'] for n in natives})
            if path == ACTION_GUIDE_FLOW and (all_tokens or skips.get('progressive')):
                # Progressive tokens: converted at the start of every item get.
                from oot_rando.patching.progressive import add_converter
                if (skips.get('progressive') or {}).get('converter', {}).get('tokens') != all_tokens:
                    raise ValueError('Progressive tokens differ from the spoiler.')
                original = add_converter(original, all_tokens)[0]
                report['progressive_tokens'] = len(all_tokens)
            if path == ACTION_GUIDE_FLOW and 'zelda_escape_item_get' in (skips.get('story_fixes') or {}):
                from oot_rando.patching.story_fixes import zelda_escape_on_item_get
                original = zelda_escape_on_item_get(original, stones)[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            from oot_rando.patching.qol_patches import SWORD_CHEST_FLOW, skip_kokiri_sword_cutscene
            if path == SWORD_CHEST_FLOW and skips.get('sword_chest'):
                original = skip_kokiri_sword_cutscene(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            from oot_rando.patching.shop_bottles import DISPLAY_SHOP_FLOW, patch_display_shop
            if path == DISPLAY_SHOP_FLOW and 'shop_full_bottles' in (skips.get('story_fixes') or {}):
                original = patch_display_shop(original)[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            from oot_rando.patching import owl_advice
            if path == owl_advice.ESCAPE_FLOW and 'owl_field_step' in (skips.get('story_fixes') or {}):
                from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
                original = owl_advice.field_step_after_escape(
                    original, challenge_steps(decompress(nup.read(members[CHALLENGES]), d)))[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            from oot_rando.patching import story_fixes
            for fixed_path, key, fix in story_fixes.flow_fixes(stones, npc_gifts):
                if path == fixed_path and key in (skips.get('story_fixes') or {}):
                    original = fix(original)[0]
                    report['story_fixes'] = report.get('story_fixes', 0) + 1
            if path in ((skips.get('story_fixes') or {}).get('child_castle') or {}):
                from oot_rando.patching import child_castle_skip
                from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
                if not child_castle_skip.enabled((manifest.get('settings') or {}).get('full')):
                    raise ValueError('Child castle guards without the option: ' + path)
                original = child_castle_skip.guard_flow(
                    path, original, challenge_steps(decompress(nup.read(members[CHALLENGES]), d)))[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            if path in ((skips.get('story_fixes') or {}).get('child_castle_kokiri') or {}):
                # Kokiri talks waiting for the Deku Tree, not for Zelda (child_castle_skip).
                from oot_rando.patching import child_castle_skip
                if not child_castle_skip.enabled((manifest.get('settings') or {}).get('full')):
                    raise ValueError('Kokiri castle state fix without the option: ' + path)
                original = child_castle_skip.kokiri_talk(original)[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            if (path in story_fixes.FIRST_ARRIVAL_REQUESTS
                    and path in ((skips.get('story_fixes') or {}).get('first_arrivals') or {})):
                from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
                original = story_fixes.first_arrival_forward(
                    path, original, challenge_steps(decompress(nup.read(members[CHALLENGES]), d)))[0]
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            # Opening floors are applied after the general story repairs by the
            # generator. Rebuild them too before comparing the event snapshot.
            from oot_rando.patching import quest_guard, world_openings
            if path == gerudo_fortress.SPIRIT_FLOW and 'freed' in openings.get('gerudo_fortress', {}):
                original = gerudo_fortress.free_remaining_carpenters(original)[0]
            for option, quest, floor, flows in (
                    ('zora_fountain', world_openings.ZORA_QUEST, world_openings.ZORA_FLOOR,
                     world_openings.ZORA_FLOWS),
                    ('open_kakariko', world_openings.KAKARIKO_QUEST, world_openings.KAKARIKO_FLOOR,
                     world_openings.KAKARIKO_FLOWS),
                    ('zelda_escape', world_openings.ESCAPE_QUEST, world_openings.ESCAPE_FLOOR,
                     world_openings.ESCAPE_FLOWS)):
                if option in openings and path in flows:
                    steps = quest_guard.challenge_steps(decompress(nup.read(members[quest_guard.CHALLENGES]), d))
                    original, guarded = quest_guard.guard_regressions(original, quest, steps, floor,
                        gamedata_raw=out(GAMEDATA),
                        prefix=openings[option].get('prefix', quest_guard.PREFIX))
                    expected = openings[option]['guarded'].get(path)
                    if json.loads(json.dumps(guarded['guarded'])) != expected:
                        raise ValueError('World opening guards differ from the spoiler: ' + path)
                    report['story_fixes'] = report.get('story_fixes', 0) + 1
            gifts = skips.get('gift_get', {})
            if path in gifts:
                # Cutscene whose own add is bypassed: never reached any more.
                from oot_rando.patching.qol_patches import GIFT_AFTER_CUTSCENE
                spec, gift = GIFT_AFTER_CUTSCENE.get(path), gifts[path]
                if spec is None or any(gift.get(key) != spec[key] for key in ('event', 'flow', 'after')):
                    raise ValueError('Unknown cutscene item hand-over: ' + path)
                chart = parse_flow(out(path)).flowchart
                bypassed = next(e for e in chart.events if e.name == spec['event'])
                if links_to(chart, bypassed):
                    raise ValueError('Cutscene item still added in the cutscene: ' + path)
                report['gift_get'] = report.get('gift_get', 0) + 1
            for cutscene, gift in sorted(gifts.items()):
                if gift.get('flow') != path:
                    continue
                # The item given back in game: the cutscene's shuffled item and its flag.
                from oot_rando.patching.qol_patches import give_gift_after
                actor = event_edits.get(cutscene, {}).get((gift['event'], 'ActorName'))
                flags = [m['flag'] for m in tracking.get('event_markers', {}).get(cutscene, [])
                         if m['event'] == gift['event']]
                if actor is None or actor != gift['actor'] or (manifest.get('tracking') and flags != [gift['flag']]):
                    raise ValueError('Item given after the cutscene differs from the spoiler: ' + path)
                original = give_gift_after(original, gift['after'], actor, gift['flag'])[0]
            from oot_rando.patching.qol_patches import SCRUB_FLOW, keep_one_scrub_good
            if path == SCRUB_FLOW and skips.get('scrub_goods'):
                original = keep_one_scrub_good(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            from oot_rando.patching import ap_mailbox
            if path == ap_mailbox.FLOW_PATH and skips.get('ap_mailbox'):
                # Archipelago reception: the item-get entry the global sequence starts.
                original = ap_mailbox.add_entries(original, skips['ap_mailbox']['items'],
                                                 dispatch='signal' in skips['ap_mailbox'])
            if skips.get('big_poes'):
                from oot_rando.patching import big_poes
                if path in {f'Event/EventFlow/{big_poes.FLOW}.bfevfl.zs', f'Event/EventFlow/{big_poes.FLOW}.110.bfevfl.zs'}:
                    if skips['big_poes'] != ((manifest.get('settings') or {}).get('full') or {}).get('big_poe_count'):
                        raise ValueError('Big Poe count differs from the settings.')
                    original = big_poes.patch_flow(original, skips['big_poes'])
                    report['big_poes'] = skips['big_poes']
            if skips.get('cuccos'):
                if path in {f'Event/EventFlow/{cuccos.FLOW}.bfevfl.zs', f'Event/EventFlow/{cuccos.FLOW}.110.bfevfl.zs'}:
                    original = cuccos.patch_flow(original, skips['cuccos'])
            song_flows = skips.get('songs') or {}
            from oot_rando.patching.song_adapter import TEACHING_FLOW_PATH, add_teaching_entries
            if path == TEACHING_FLOW_PATH and any(ops.get('teaching') for ops in song_flows.values()):
                original = add_teaching_entries(original)
                report['song_flows'] = report.get('song_flows', 0) + 1
            if path in song_flows:
                # Songs: text-only gets and cutscenes without their melody teaching.
                from oot_rando.patching.song_adapter import check_song_ops, patch_flow as patch_song_flow
                check_song_ops({path: song_flows[path]}, event_edits)
                original = patch_song_flow(original, song_flows[path])
                report['song_flows'] = report.get('song_flows', 0) + 1
            if path in chest_flows:
                from oot_rando.patching.chest_flags import add_entries
                original = add_entries(original, chest_flows[path])
            before = _event_snapshot(original)
            after = _event_snapshot(out(path))
            for (name, param), actor in event_edits.get(path, {}).items():
                before[name][param] = actor
                report['events'] += 1
            if manifest.get('tracking'):
                for marker in tracking.get('event_markers', {}).get(path, []):
                    if marker['event'] not in before or marker['marker'] in before:
                        raise ValueError('Inconsistent collection marker: ' + path)
                    before[marker['marker']] = {'GameDataName': marker['flag'], 'Index': -1, 'Value': True}
            if path in hooks:
                produced = {e.name: e for e in _flow_events(out(path))}
                for name in hooks[path]:
                    call = produced[name].data.nxt.v
                    if (call is None or call.name != AFTER_PREFIX + name or call.data.params is not None
                            or (call.data.res_flowchart_name, call.data.entry_point_name) != (ACTION_GUIDE,
                                                                                             CONVERTER_ENTRY)):
                        raise ValueError('Progressive token gift without its conversion: ' + path)
                    before[call.name] = None
                    report['progressive_gifts'] = report.get('progressive_gifts', 0) + 1
            if path == 'Event/EventFlow/OpeningEvent.bfevfl.zs':
                # Seed bag and quiver given silently at the end of the opening.
                from oot_rando.randomizer.randomizer_core import starting_pouch_items
                from oot_rando.patching.event_patch import starting_item_events
                given = starting_pouch_items({'archipelago': manifest.get('archipelago'),
                                              'starting': manifest.get('starting'),
                                              'options': (manifest.get('settings') or {}).get('full')})
                for item, name in zip(given, starting_item_events(given)):
                    before[name] = {'Num': 1, 'IsEquipDIrect': False,
                                                        'IsSetMessageTargetActorName': False,
                                                        'Actor': item, 'IsGetEvent': False}
                    report['starting_items'] = report.get('starting_items', 0) + 1
                from oot_rando.patching.event_patch import start_value_events
                from oot_rando.patching.key_adapter import start_dungeon_values
                values = start_dungeon_values((manifest.get('settings') or {}).get('full') or {})
                if 'clock' in (manifest.get('skips', {}).get('story_fixes') or {}):
                    from oot_rando.patching.story_fixes import story_start_values
                    values = dict(values, **story_start_values())
                presentation_flags = manifest.get('skips', {}).get('presentation_flags') or {}
                if presentation_flags:
                    from oot_rando.patching.area_presentations import start_values as presentation_start_values
                    if presentation_flags != presentation_start_values():
                        raise ValueError('Area presentation flags differ from the spoiler.')
                    values = dict(values, **presentation_flags)
                from oot_rando.patching import adult_start, child_castle_skip
                if adult_start.enabled((manifest.get('settings') or {}).get('full')):
                    # Adult start: era flag, then the banc change to the Temple of Time.
                    if (skips.get('story_fixes') or {}).get('adult_start', {}).get('events') != list(adult_start.event_params()):
                        raise ValueError('Adult start events differ from the settings.')
                    for name, params in adult_start.event_params().items():
                        before[name] = params
                        report['start_values'] = report.get('start_values', 0) + 1
                if child_castle_skip.enabled((manifest.get('settings') or {}).get('full')):
                    values = dict(values, **child_castle_skip.START_VALUES)
                area_visits = (skips.get('story_fixes') or {}).get('area_visits')
                if area_visits:   # (seeds from 0.12.22 on)
                    from oot_rando.patching.area_presentations import with_area_visits
                    visited = with_area_visits(values)
                    if sorted(set(visited) - set(values)) != area_visits:
                        raise ValueError('Area visits differ from the spoiler.')
                    values = visited
                if child_castle_skip.enabled((manifest.get('settings') or {}).get('full')):
                    # The castle quests replayed at the start (native requests, copied).
                    steps = child_castle_skip.start_step_params(
                        lambda p: decompress(nup.read(members[p]), d), door_ready=not stones)
                    if [name for name, _ in steps] != (skips.get('story_fixes') or {}).get('child_castle_start'):
                        raise ValueError('Child castle start requests differ from the settings.')
                    for name, params in steps:
                        before[name] = params
                        report['start_values'] = report.get('start_values', 0) + 1
                for (key, value), name in zip(sorted(values.items()), start_value_events(values)):
                    before[name] = {'GameDataName': key, 'Value': value, 'Index': -1}
                    report['start_values'] = report.get('start_values', 0) + 1
            if before != after:
                raise ValueError('Event modified outside the spoiler: ' + path)
            continue
        if not (path.startswith('Banc/') and path.endswith('.bcett.byml.zs')):
            continue
        before = Byml(decompress(nup.read(members[path]), d)).root
        after = Byml(out(path)).root
        shop_actors = (manifest.get('skips', {}).get('story_fixes') or {}).get('bombchu_shop_actors') or {}
        if path in shop_actors:
            from oot_rando.formats.byml_writer import patch_strings
            edits, details = story_fixes.bombchu_shop_actor_edits(before, path)
            if shop_actors[path] != details:
                raise ValueError('Unexpected Bombchu Shop actor report: ' + path)
            before = Byml(patch_strings(decompress(nup.read(members[path]), d), edits)).root
            report['story_fixes'] = report.get('story_fixes', 0) + len(details['actors'])
        if path in repeat_fallback:
            expected_fallbacks = {}
            for record, variant in repeat_fallback[path]:
                original = before['Actors'][variant['index']]
                fallback = __import__('copy').deepcopy(original)
                ident = variant['fallback_hash']
                fallback['Hash'] = ident
                for link in fallback.get('Links', []):
                    for key in ('Src', 'Dst'):
                        if link.get(key) == original['Hash']:
                            link[key] = ident
                if isinstance(fallback.get('Phive', {}).get('Placement'), dict):
                    fallback['Phive']['Placement']['ID'] = ident
                fallback['Presence'] = {'FlagName': record['flag'], 'IsNegation': False, 'IsCheckLazy': None}
                expected_fallbacks[ident] = fallback
            actual_fallbacks = {a['Hash']: a for a in after['Actors'] if a.get('Hash') in expected_fallbacks}
            for ident, fallback in expected_fallbacks.items():
                fallback['Presence']['IsCheckLazy'] = _seed_lazy(actual_fallbacks.get(ident))
            if actual_fallbacks != expected_fallbacks:
                raise ValueError('Return to the original loot does not match: ' + path)
            after = dict(after, Actors=[a for a in after['Actors'] if a.get('Hash') not in expected_fallbacks])
        if path in repeat_boards:
            # Shuffled shelves: a native sold out board linked behind each one.
            from oot_rando.patching.repeatable_adapter import add_sold_out_board
            actors = __import__('copy').deepcopy(before['Actors'])
            for shelf in repeat_boards[path]:
                if add_sold_out_board(actors, shelf['index'], shelf['board_hash']) is not None:
                    report['sold_out_boards'] = report.get('sold_out_boards', 0) + 1
            before = dict(before, Actors=json.loads(json.dumps(actors)))
        edits = map_edits.get(path, {})
        if path in QOL_MAPS:
            kept = {a.get('Hash') for a in after['Actors']}
            indices = {id(a): i for i, a in enumerate(before['Actors'])}
            before = dict(before, Actors=[a for a in before['Actors'] if a.get('Hash') in kept])
        else:
            indices = None
        if len(before['Actors']) != len(after['Actors']):
            raise ValueError('Actor count changed: ' + path)
        for position, (a, b) in enumerate(zip(before['Actors'], after['Actors'])):
            if a.get('Hash') != b.get('Hash'):
                raise ValueError('Actor order changed: ' + path)
            index = indices[id(a)] if indices is not None else position
            a2, b2 = json.loads(json.dumps(a)), json.loads(json.dumps(b))
            shop_presence = a2.get('Presence') or {}
            if path in KOKIRI_SHOP_MAPS and shop_presence.get('FlagName') == KOKIRI_SHOP_FLAG                     and shop_actor(a2.get('Gyaml', '')):
                # Kokiri shop opened from the start: full stock always, short stock hidden.
                if shop_presence.get('IsNegation'):
                    shop_presence['FlagName'] = save_marker(manifest)
                else:
                    del a2['Presence']
                report['kokiri_shop'] = report.get('kokiri_shop', 0) + 1
            if always_skulltulas and is_nocturnal_skulltula(a2):
                a2['Dynamic'][NOCTURNAL_FIELD] = False
                report['skulltulas_always_present'] = report.get('skulltulas_always_present', 0) + 1
            if index in repeat_first.get(path, {}):
                record = repeat_first[path][index]
                a2['Presence'] = {'FlagName': record['flag'], 'IsNegation': True, 'IsCheckLazy': _seed_lazy(b2)}
            if index in textured_sources.get(path, {}):
                variant = textured_sources[path][index]
                if a2['Gyaml'] != variant['source']:
                    raise ValueError('Unexpected original textured source: ' + path)
                a2['Gyaml'] = variant['textured_actor']
            for field, actor in edits.get(index, {}).items():
                if field == 'Gyaml':
                    from oot_rando.game.item_forms import ground_lift, lifted, world_scale
                    height = ground_lift(a2.get('Gyaml'), actor)
                    if height:
                        a2['Translate'][1] = lifted(a2['Translate'][1], height)
                    scale = world_scale(actor)
                    if scale != 1.0 and a2.get('Gyaml') != actor:
                        a2['Scale'] = [lifted(scale, 0.0)] * 3
                    a2['Gyaml'] = actor
                else:
                    a2.setdefault('Dynamic', {})[field] = actor
                report['rewards'] += 1
            sheik_fix = (manifest.get('skips', {}).get('story_fixes') or {}).get('sheik')
            if sheik_fix and path == sheik_fix['map'] and index == sheik_fix['actor'] and 'Presence' not in a2:
                # Seeds up to 0.6.5: Temple of Time Sheik only after the Forest Temple (fix withdrawn).
                from oot_rando.patching.story_fixes import SHEIK, SHEIK_PRESENCE_ENTRY
                if a2.get('Gyaml') != SHEIK or sheik_fix['presence'] != SHEIK_PRESENCE_ENTRY['FlagName']:
                    raise ValueError('Unexpected Sheik presence: ' + path)
                a2['Presence'] = dict(SHEIK_PRESENCE_ENTRY)
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            wall_fix = (manifest.get('skips', {}).get('story_fixes') or {}).get('zora_river_wall')
            if wall_fix and path == wall_fix['map'] and index in wall_fix['actors'] and 'Presence' not in a2:
                # Zora's River mouth walls only for child Link (patching/story_fixes.py).
                from oot_rando.patching.story_fixes import (ZORA_RIVER_WALL, ZORA_RIVER_WALLS,
                                                            ZORA_RIVER_WALL_PRESENCE_ENTRY)
                if (a2.get('Gyaml') != ZORA_RIVER_WALL or a2.get('Hash') not in ZORA_RIVER_WALLS
                        or wall_fix['presence'] != ZORA_RIVER_WALL_PRESENCE_ENTRY['FlagName']):
                    raise ValueError("Unexpected Zora's River wall presence: " + path)
                a2['Presence'] = dict(ZORA_RIVER_WALL_PRESENCE_ENTRY)
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            child_wall_fix = (manifest.get('skips', {}).get('story_fixes') or {}).get('zora_river_child_wall')
            if (child_wall_fix and path == child_wall_fix['map'] and index in child_wall_fix['actors']
                    and 'Presence' not in a2):
                # Child map's river mouth walls only for adult Link (patching/story_fixes.py).
                from oot_rando.patching.story_fixes import (ZORA_RIVER_WALL, ZORA_RIVER_CHILD_WALLS,
                                                            ZORA_RIVER_CHILD_WALL_PRESENCE_ENTRY)
                if (a2.get('Gyaml') != ZORA_RIVER_WALL or a2.get('Hash') not in ZORA_RIVER_CHILD_WALLS
                        or child_wall_fix['presence'] != ZORA_RIVER_CHILD_WALL_PRESENCE_ENTRY['FlagName']
                        or child_wall_fix.get('negation') is not True):
                    raise ValueError("Unexpected Zora's River wall presence: " + path)
                a2['Presence'] = dict(ZORA_RIVER_CHILD_WALL_PRESENCE_ENTRY)
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            tree_fix = (manifest.get('skips', {}).get('story_fixes') or {}).get('lake_tree_wall')
            if tree_fix and path == tree_fix['map'] and index == tree_fix['actor']:
                # Lake Hylia island tree wall only for child Link (patching/story_fixes.py).
                from oot_rando.patching.story_fixes import (LAKE_TREE_WALL, LAKE_TREE_WALL_HASH,
                                                            LAKE_TREE_WALL_VANILLA,
                                                            LAKE_TREE_WALL_PRESENCE_ENTRY)
                if (a2.get('Gyaml') != LAKE_TREE_WALL or a2.get('Hash') != LAKE_TREE_WALL_HASH
                        or a2.get('Presence') != LAKE_TREE_WALL_VANILLA
                        or tree_fix['presence'] != LAKE_TREE_WALL_PRESENCE_ENTRY['FlagName']):
                    raise ValueError('Unexpected Lake Hylia tree wall presence: ' + path)
                a2['Presence'] = dict(LAKE_TREE_WALL_PRESENCE_ENTRY)
                report['story_fixes'] = report.get('story_fixes', 0) + 1
            if 'Presence' in b2 and 'Presence' not in a2:
                flag = b2['Presence'].get('FlagName', '')
                from oot_rando.patching.soul_adapter import soul_presence
                key = flag[len(FLAG_PREFIX + 'Item_Soul_'):]
                if not flag.startswith(FLAG_PREFIX + 'Item_Soul_') or b2['Presence'] != soul_presence(flag, key):
                    raise ValueError('Unexpected presence: ' + path)
                soul_actors.add(flag[len(FLAG_PREFIX):])
                a2['Presence'] = b2['Presence']
                report['presence'] += 1
            elif 'Presence' in a2 and b2.get('Presence') != a2['Presence']:
                # An enemy with its own Presence reads "its soul AND that condition".
                from oot_rando.patching.soul_adapter import EXPRESSION_PREFIX, soul_presence
                flag = b2.get('Presence', {}).get('FlagName', '')
                soul = flag[len(EXPRESSION_PREFIX):].split('.', 1)[0]
                if (not flag.startswith(EXPRESSION_PREFIX + 'Item_Soul_')
                        or b2['Presence'] != soul_presence(FLAG_PREFIX + soul, soul[len('Item_Soul_'):],
                                                           a2['Presence'])):
                    raise ValueError('Unexpected presence: ' + path)
                soul_expressions_seen.add(flag)
                soul_actors.add(soul)
                a2['Presence'] = b2['Presence']
                report['presence'] += 1
            if a2 != b2 and not (path in QOL_MAPS and not edits.get(index)):
                raise ValueError(f'Unauthorised change: {path}#{a.get("Hash")}')
        report['maps'] += 1
    # Actors.
    derived = set()
    master_actors = {MASTER_SWORD_ACTOR} if manifest['settings']['full'].get('shuffle_master_sword') else set()
    once_actors = {r['actor']: r for r in tracking.get('repeatables', [])}
    for placement in full:
        actor = placement['actor']
        if actor in once_actors:
            derived.add(actor)
            canonical = once_actors[actor]['canonical']
            if canonical.startswith(('Item_Soul_', 'Item_AP_', 'Item_Trap_')) or is_key_actor(canonical) or is_token(canonical):
                soul_actors.add(canonical)
        elif actor.startswith(('Item_Soul_', 'Item_AP_', 'Item_Trap_')) or is_key_actor(actor) or is_token(actor):
            soul_actors.add(actor)
        elif is_derived(actor):
            derived.add(actor)
            canonical = canonical_of(actor)
            if canonical.startswith(('Item_Soul_', 'Item_AP_', 'Item_Trap_')) or is_key_actor(canonical) or is_token(canonical):
                soul_actors.add(canonical)  # derived soul/key/token: the generated item must exist too
        elif actor not in master_actors and 'Pack/Actor/' + actor + '.pack.zs' not in members:
            raise ValueError('Actor missing: ' + actor)
    for native in natives:
        soul_actors.add(native['token'])
        if is_derived(native['after']):
            derived.add(native['after'])
    source_actors = {variant['textured_actor'] for variants in textured_sources.values()
                     for variant in variants.values()}
    from oot_rando.catalog.traps import SENSOR_ACTOR, sprung_flag
    sensor_actors = {SENSOR_ACTOR} if placed_trap_items else set()
    generated = soul_actors | derived | master_actors | source_actors | sensor_actors
    if generated:
        rest = decompress((seed_dir / 'romfs' / RESTBL).read_bytes(), d)
        count = struct.unpack_from('<I', rest, 14)[0]
        crcs = {struct.unpack_from('<I', rest, 22 + i * 8)[0] for i in range(count)}
        tables = {name: {row['__RowId'] for row in byml_codec.load(out(path))['root']}
                  for name, path in RSDB_FILES.items()}
        flags = set()
        if soul_actors:
            gamedata = byml_codec.load(out(GAMEDATA))['root']['Data']
            flags = {entry['Hash'] for entry in gamedata['Bool']}
            expressions = {int(entry['Hash']) for entry in gamedata['BoolExp']}
            missing = sorted(n for n in soul_expressions_seen if murmur3(n) not in expressions)
            if missing:
                raise ValueError('Missing soul condition: ' + missing[0])
        for record in manifest.get('skips', {}).get('key_items', {}).get('records', []):
            if record['kind'] == 'ring' and murmur3(record['applied']) not in flags:
                raise ValueError('Missing key ring flag: ' + record['folder'])
        for item in placed_trap_items:
            if murmur3(sprung_flag(trap_actor(item))) not in flags:
                raise ValueError('Missing fake item trap flag: ' + item)
        for actor in sorted(a for a in soul_actors if is_token(a)):
            if murmur3(applied_flag(actor)) not in flags:
                raise ValueError('Missing progressive token flag: ' + actor)
        for actor in sorted(generated):
            pack_path = f'Pack/Actor/{actor}.pack.zs'
            pack = sarc(out(pack_path))
            Byml(pack[f'Actor/{actor}.engine__actor__ActorParam.bgyml'])
            if zlib.crc32(pack_path[:-3].encode()) not in crcs:
                raise ValueError('Missing RESTBL entry: ' + actor)
            required = ((tables['ActorInfo'], tables['GameActorInfo']) if actor in source_actors | sensor_actors
                        else tables.values())
            if any(actor not in rows for rows in required):
                raise ValueError('Missing RSDB row: ' + actor)
            if actor in soul_actors and murmur3(FLAG_PREFIX + actor) not in flags:
                raise ValueError('Missing save flag: ' + actor)
        report['textured_sources'] = len(source_actors)
    if placed_trap_items:
        # Fake item traps freeze child Link too (vanilla: adult only).
        from oot_rando.patching.fake_traps import CHILD_PACK, ELINK, child_ice_shell, enable_child_freeze
        if out(CHILD_PACK) != enable_child_freeze(decompress(nup.read(members[CHILD_PACK]), d)):
            raise ValueError('Child Link cannot be frozen by the fake item traps.')
        if out(ELINK) != child_ice_shell(decompress(nup.read(members[ELINK]), d)):
            raise ValueError('Child Link has no ice shell for the fake item traps.')
        report['child_freeze'] = True
    multiworld = manifest.get('archipelago')
    if multiworld is not None:
        # Placed by Archipelago: victory may need items of other worlds (checked by
        # Archipelago). Starting copies of a progressive family are its lowest levels.
        taken = Counter()
        for start in multiworld.get('starting', []):
            item, actor = start['item'], start['actor']
            if item in PROGRESSIVE:
                levels = PROGRESSIVE[item]
                if taken[item] >= len(levels) or actor != levels[taken[item]]:
                    raise ValueError(f'Starting {item} is not its next lowest level: {actor}')
                taken[item] += 1
            elif full_randomizer.starting_unsupported(item) or actor != item_actor(item, None):
                raise ValueError(f'Unexpected starting item: {item} → {actor}')
        report['invariants'] = invariants
        report.update(souls=len(soul_actors), derived=len(derived), beatable='checked by Archipelago',
                      spheres=plan['sphere_count'], unreachable_logic_locations=plan['unreachable'],
                      archipelago={'seed_name': multiworld.get('seed_name'), 'slot_name': multiworld.get('slot_name'),
                                   'items_in_other_worlds': len(multiworld.get('remote', []))})
        nup.stream.close()
        return report
    if plan.get('before_adult_missing'):
        raise ValueError('Logic replay: Door of Time items unavailable before adulthood: '
                         + ', '.join(plan['before_adult_missing']))
    if plan.get('unreachable_souls'):
        raise ValueError('Logic replay: unreachable enemy souls: ' + ', '.join(plan['unreachable_souls']))
    if not plan['beatable']:
        raise ValueError('Logic replay: victory not reached.')
    report['invariants'] = invariants
    report.update(souls=len(soul_actors), derived=len(derived), beatable=True, spheres=plan['sphere_count'],
                  unreachable_logic_locations=plan['unreachable'])
    nup.stream.close()
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    print(json.dumps(verify(*argv), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
