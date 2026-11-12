"""Independent static verification of a complete-randomizer seed (no game launch).

Usage: python -m oot_rando verify GAME.nup SEED_FOLDER

Checks, from the produced files only (the generator's plan is not reused):
1. every map differs from the original NUP only by the spoiled rewards
   (``Drop__DropActor`` of chests, skulltulas and environment objects, ``Gyaml``
   of freestanding items and shop shelves), ``Presence`` blocks of soul enemies
   and the known QoL edits;
2. every event flow differs only by the spoiled gift parameters;
3. both age variants of a source carry the same reward;
4. every reward actor exists (game pack, generated soul or derived pack) and
   every generated actor has its RSDB rows and RESTBL entry (souls: saved flag);
5. a fresh sweep of the remake logic over the spoiled placements is beatable and,
   with progressive order on, lower tiers are found in strictly earlier spheres.
"""
from collections import defaultdict
import json
import struct
import sys
import zlib
from pathlib import Path

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries, sarc
from oot_rando.game.world_maps import effective_members
from oot_rando.randomizer.randomizer_services import read_artifact
from oot_rando.patching.randomize_kokiri import RESTBL, MAP
from oot_rando.patching.qol_patches import STATIC, KOKIRI_SHOP_MAPS, KOKIRI_SHOP_FLAG, _shop_actor
from oot_rando.formats import byml_codec
from oot_rando.patching.soul_adapter import murmur3, RSDB_FILES, GAMEDATA, FLAG_PREFIX
from oot_rando.game.remake_world import PROGRESSIVE
from oot_rando.game.item_forms import is_derived, canonical_of
from oot_rando.patching.key_adapter import is_key_actor

QOL_MAPS = {MAP, STATIC}


def _flow_events(raw):
    from oot_rando.patching.event_patch import _flow
    return _flow(raw).flowchart.events


def _event_snapshot(raw):
    from oot_rando.patching.event_patch import _flow, _snapshot
    return _snapshot(_flow(raw))


def verify(nup_path, seed_dir):
    from oot_rando.game.extra_sources import scan_world
    seed_dir = Path(seed_dir)
    manifest, checks = read_artifact(seed_dir)
    spoiler = json.loads((seed_dir / 'spoiler.json').read_text(encoding='utf-8'))
    if 'full_randomizer' not in manifest:
        raise ValueError('Seed without the full randomizer.')
    nup = Nup(nup_path)
    d = dictionaries(nup)
    members = effective_members(nup)
    out = lambda path: decompress((seed_dir / 'romfs' / path).read_bytes(), d)
    full = [p for p in spoiler['placements'] if str(p.get('category', '')).startswith('full_')]
    _, groups, enemies, extra = scan_world(nup, d, members)
    # Expected edits, rebuilt from the original game and the spoiler only.
    map_edits = defaultdict(dict)     # resource -> actor index -> {field: actor}
    event_edits = defaultdict(dict)   # resource -> (event, param) -> actor
    for placement in full:
        gid, actor = placement['id'], placement['actor']
        if gid in groups:
            if actor != placement['before']:
                for variant in groups[gid]:
                    map_edits[variant['resource']].setdefault(variant['index'], {})['Drop__DropActor'] = actor
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
    for record in tracking.get('repeatables', []):
        for variant in record['variants']:
            if not variant['native_once']:
                repeat_first[variant['resource']][variant['index']] = record
                repeat_fallback[variant['resource']].append((record, variant))
    report = {'maps': 0, 'rewards': 0, 'presence': 0, 'events': 0}
    soul_actors = set()
    window_context = [None, None]
    for path in sorted(manifest['files']):
        if path.startswith('Event/EventFlow/'):
            original = decompress(nup.read(members[path]), d)
            # Comfort patches, re-applied independently to the original flow.
            from oot_rando.patching.qol_patches import AREA_PRESENTATIONS, CHEST_FLOW, add_skip_window, flow_path, quick_chest
            skips = manifest.get('skips', {})
            if path in {flow_path(name) for name in skips.get('area_presentations', {})}:
                if path not in {flow_path(name) for name in AREA_PRESENTATIONS}:
                    raise ValueError('Unknown area presentation: ' + path)
                original = add_skip_window(original)[0]
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
                records = key_records(p['ap_item'] for p in full if p['ap_item'].startswith(('Small Key Ring (',))
                                      or (p['ap_item'].startswith('Boss Key (')
                                          and p.get('reward_actor', p['actor']).removeprefix('Obj_Rando_').removeprefix('Shop_Rando_')
                                          .startswith('Item_BossKey_')))
                if records != skips['key_items']['records']:
                    raise ValueError('Dungeon keys differ from the spoiler.')
                original = add_key_hook(original, records)[0]
                report['key_items'] = len(records)
            from oot_rando.patching.qol_patches import SWORD_CHEST_FLOW, skip_kokiri_sword_cutscene
            if path == SWORD_CHEST_FLOW and skips.get('sword_chest'):
                original = skip_kokiri_sword_cutscene(original)[0]
                report['comfort_flows'] = report.get('comfort_flows', 0) + 1
            gifts = skips.get('gift_get', {})
            if path in gifts:
                # Cutscene whose own add is bypassed: never reached any more.
                from oot_rando.patching.event_patch import _flow
                from oot_rando.patching.qol_patches import GIFT_AFTER_CUTSCENE, _predecessors
                spec, gift = GIFT_AFTER_CUTSCENE.get(path), gifts[path]
                if spec is None or any(gift.get(key) != spec[key] for key in ('event', 'flow', 'after')):
                    raise ValueError('Unknown cutscene item hand-over: ' + path)
                chart = _flow(out(path)).flowchart
                bypassed = next(e for e in chart.events if e.name == spec['event'])
                if _predecessors(chart, bypassed):
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
            if path == 'Event/EventFlow/OpeningEvent.bfevfl.zs':
                # Seed bag and quiver given silently at the end of the opening.
                from oot_rando.randomizer.randomizer_core import STARTING_ITEMS
                for item in STARTING_ITEMS:
                    before['RandoStartItem_' + item] = {'Num': 1, 'IsEquipDIrect': False,
                                                        'IsSetMessageTargetActorName': False,
                                                        'Actor': item, 'IsGetEvent': False}
                    report['starting_items'] = report.get('starting_items', 0) + 1
            if before != after:
                raise ValueError('Event modified outside the spoiler: ' + path)
            continue
        if not (path.startswith('Banc/') and path.endswith('.bcett.byml.zs')):
            continue
        before = Byml(decompress(nup.read(members[path]), d)).root
        after = Byml(out(path)).root
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
                fallback['Presence'] = {'FlagName': record['flag'], 'IsNegation': False, 'IsCheckLazy': False}
                expected_fallbacks[ident] = fallback
            actual_fallbacks = {a['Hash']: a for a in after['Actors'] if a.get('Hash') in expected_fallbacks}
            if actual_fallbacks != expected_fallbacks:
                raise ValueError('Return to the original loot does not match: ' + path)
            after = dict(after, Actors=[a for a in after['Actors'] if a.get('Hash') not in expected_fallbacks])
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
            if path in KOKIRI_SHOP_MAPS and shop_presence.get('FlagName') == KOKIRI_SHOP_FLAG                     and _shop_actor(a2.get('Gyaml', '')):
                # Kokiri shop opened from the start: full stock always, short stock hidden.
                if shop_presence.get('IsNegation'):
                    shop_presence['FlagName'] = 'RandoSeed.' + manifest['seed_id']
                else:
                    del a2['Presence']
                report['kokiri_shop'] = report.get('kokiri_shop', 0) + 1
            if index in repeat_first.get(path, {}):
                record = repeat_first[path][index]
                a2['Presence'] = {'FlagName': record['flag'], 'IsNegation': True, 'IsCheckLazy': False}
            for field, actor in edits.get(index, {}).items():
                if field == 'Gyaml':
                    a2['Gyaml'] = actor
                else:
                    a2.setdefault('Dynamic', {})[field] = actor
                report['rewards'] += 1
            if 'Presence' in b2 and 'Presence' not in a2:
                flag = b2['Presence'].get('FlagName', '')
                if not flag.startswith(FLAG_PREFIX + 'Item_Soul_') or b2['Presence'] != {
                        'FlagName': flag, 'IsNegation': False, 'IsCheckLazy': False}:
                    raise ValueError('Unexpected presence: ' + path)
                soul_actors.add(flag[len(FLAG_PREFIX):])
                a2['Presence'] = b2['Presence']
                report['presence'] += 1
            if a2 != b2 and not (path in QOL_MAPS and not edits.get(index)):
                raise ValueError(f'Unauthorised change: {path}#{a.get("Hash")}')
        report['maps'] += 1
    # Actors.
    derived = set()
    once_actors = {r['actor']: r for r in tracking.get('repeatables', [])}
    for placement in full:
        actor = placement['actor']
        if actor in once_actors:
            derived.add(actor)
            canonical = once_actors[actor]['canonical']
            if canonical.startswith('Item_Soul_') or is_key_actor(canonical):
                soul_actors.add(canonical)
        elif actor.startswith('Item_Soul_') or is_key_actor(actor):
            soul_actors.add(actor)
        elif is_derived(actor):
            derived.add(actor)
            canonical = canonical_of(actor)
            if canonical.startswith('Item_Soul_') or is_key_actor(canonical):
                soul_actors.add(canonical)  # derived soul/key: the generated item must exist too
        elif 'Pack/Actor/' + actor + '.pack.zs' not in members:
            raise ValueError('Actor missing: ' + actor)
    generated = soul_actors | derived
    if generated:
        rest = decompress((seed_dir / 'romfs' / RESTBL).read_bytes(), d)
        count = struct.unpack_from('<I', rest, 14)[0]
        crcs = {struct.unpack_from('<I', rest, 22 + i * 8)[0] for i in range(count)}
        tables = {name: {row['__RowId'] for row in byml_codec.load(out(path))['root']}
                  for name, path in RSDB_FILES.items()}
        flags = set()
        if soul_actors:
            flags = {entry['Hash'] for entry in byml_codec.load(out(GAMEDATA))['root']['Data']['Bool']}
        for record in manifest.get('skips', {}).get('key_items', {}).get('records', []):
            if record['kind'] == 'ring' and murmur3(record['applied']) not in flags:
                raise ValueError('Missing key ring flag: ' + record['folder'])
        for actor in sorted(generated):
            pack_path = f'Pack/Actor/{actor}.pack.zs'
            pack = sarc(out(pack_path))
            Byml(pack[f'Actor/{actor}.engine__actor__ActorParam.bgyml'])
            if zlib.crc32(pack_path[:-3].encode()) not in crcs:
                raise ValueError('Missing RESTBL entry: ' + actor)
            if any(actor not in rows for rows in tables.values()):
                raise ValueError('Missing RSDB row: ' + actor)
            if actor in soul_actors and murmur3(FLAG_PREFIX + actor) not in flags:
                raise ValueError('Missing save flag: ' + actor)
    # Fresh logic sweep from the spoiler.
    from oot_rando.logic.world import World
    from oot_rando.randomizer import full_randomizer
    data = World()
    plan = full_randomizer.replay(data, manifest['settings']['full'], groups, enemies,
                                  {p['id']: p['ap_item'] for p in full}, manifest['settings']['open_forest'],
                                  extra=extra)
    multiworld = manifest.get('archipelago')
    warnings = []
    if multiworld is not None:
        # Placed by Archipelago: victory may need items of other worlds (checked by
        # Archipelago); the tier order follows the multiworld playthrough.
        order = multiworld.get('spheres') or {}
        if manifest['settings']['full'].get('progressive_order', True):
            for family, actors in PROGRESSIVE.items():
                spheres = {}
                for p in full:
                    if p['ap_item'] == family:
                        reward_actor = p.get('reward_actor', p['actor'])
                        base = next((a for a in actors if reward_actor in (a, 'Obj_Rando_' + a, 'Shop_Rando_' + a)),
                                    None)
                        spheres[base] = order.get(p['id'])
                ordered = [spheres[a] for a in actors if a in spheres]
                pairs = list(zip(ordered, ordered[1:]))
                if any(x is not None and y is not None and x > y for x, y in pairs):
                    raise ValueError(f'Level order not respected for {family}: {spheres}')
                if any(x is None or y is None or x == y for x, y in pairs):
                    warnings.append(f'{family}: levels in the same multiworld sphere {spheres}')
        report.update(souls=len(soul_actors), derived=len(derived), beatable='checked by Archipelago',
                      spheres=plan['sphere_count'], unreachable_logic_locations=plan['unreachable'],
                      archipelago={'seed_name': multiworld.get('seed_name'), 'slot_name': multiworld.get('slot_name'),
                                   'items_in_other_worlds': len(multiworld.get('remote', []))},
                      warnings=warnings)
        nup.stream.close()
        return report
    if not plan['beatable']:
        raise ValueError('Logic replay: victory not reached.')
    if manifest['settings']['full'].get('progressive_order', True):
        for family, actors in PROGRESSIVE.items():
            spheres = {}
            for p in full:
                if p['ap_item'] == family:
                    reward_actor = p.get('reward_actor', p['actor'])
                    base = next((a for a in actors if reward_actor in (a, 'Obj_Rando_' + a, 'Shop_Rando_' + a)), None)
                    spheres[base] = plan['spheres'].get(p['id'])
            ordered = [spheres[a] for a in actors if a in spheres]
            if any(x is None or y is None or x >= y for x, y in zip(ordered, ordered[1:])):
                raise ValueError(f'Level order not respected for {family}: {spheres}')
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
