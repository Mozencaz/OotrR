"""Inventory EVERY map enemy, combat AI group and counter against soul logic.

python tools/audit_soul_combat.py GAME.nup --output docs
Reads the game only. Outputs extracted facts, not game assets. Room membership
is conservative; a native AI group is not necessarily one architectural room.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import dictionaries
from oot_rando.game.combat import module_path
from oot_rando.game.remake_world import scan_maps, FOLDER_AP_DUNGEON, map_age, match_locations
from oot_rando.game.world_maps import effective_members
from oot_rando.logic.world import World
from oot_rando.logic.rules import Logic
from oot_rando.patching.soul_adapter import (plan_souls, family_of, BY_ID, is_mechanical,
                                            EXCLUDED_FOLDERS, chest_requirements)


def audit(nup_path):
    nup = Nup(nup_path)
    try:
        maps, groups, enemies = scan_maps(nup, dictionaries(nup), effective_members(nup))
    finally:
        nup.stream.close()
    world = World()
    matches, _ = match_locations(groups, world, Logic(world), 'scene')
    plans = {mode: plan_souls(mode, enemies, world.regions) for mode in ('bosses', 'regional', 'all')}
    rows = {}
    enemy_rows = []
    unresolved = []
    # Inventory all map AI modules referring to enemies, even optional enemies.
    modules = set()
    ai_groups = 0
    for path, value in maps.items():
        actors = {a.get('Hash'): a for a in value['root'].get('Actors', [])}
        for group in value['root'].get('AiGroups', []):
            if any(actors.get(ref.get('Reference'), {}).get('Gyaml', '').startswith(('Enemy_', 'Obj_EnemyCounter'))
                   for ref in group.get('References', [])):
                ai_groups += 1
                modules.add(module_path(group['Logic']))
    for enemy in enemies:
        path, hash_ = enemy['resource'], enemy['hash']
        folder = enemy['folder']
        family = family_of(enemy['actor'])
        native = maps[path]['root']['Actors'][enemy['index']]
        position = native.get('Translate')
        evidence = list(enemy.get('combat', ()))
        for lock in enemy.get('locks', ()):
            evidence.append({'id': lock['counter'], 'logic': 'direct lock' if lock.get('direct') else 'enemy counter',
                             'regions': [], 'signals': [], 'targets': [d['hash'] for d in lock['doors']]})
        if not evidence and (is_mechanical(enemy) or (family and BY_ID[family][2])):
            evidence.append({'id': path + '#' + hash_, 'logic': 'actor links / parameters / boss',
                             'regions': [], 'signals': enemy.get('mechanics', []), 'targets': []})
        policies = {}
        for mode, plan in plans.items():
            edit = next((e for e in plan['edits'] if e['resource'] == path and e['hash'] == hash_), None)
            policies[mode] = edit['soul'] if edit else None
        enemy_rows.append({'resource': path, 'hash': hash_, 'actor': enemy['actor'], 'family': family,
                           'position': position,
                           'age': map_age(path) or 'both', 'mechanical': is_mechanical(enemy),
                           'policies': policies, 'encounters': [e['id'] for e in evidence]})
        for entry in evidence:
            key = entry['id']
            row = rows.setdefault(key, {'id': key, 'resource': path, 'age': map_age(path) or 'both',
                                        'logic': entry['logic'], 'regions': entry['regions'],
                                        'signals': entry['signals'], 'enemies': [], 'targets': set(),
                                        'logic_modules': entry.get('logic_modules', []),
                                        'requirements': defaultdict(set), 'coverage': set()})
            row['enemies'].append({'actor': enemy['actor'], 'hash': hash_})
            row['targets'].update(entry['targets'])
            if folder in EXCLUDED_FOLDERS or family is None:
                row['coverage'].add('excluded from soul patch; native enemy remains')
            elif policies['all'] is None:
                row['coverage'].add('unpatchable/mixed counter; native enemy remains')
            else:
                if BY_ID[family][2]:
                    row['coverage'].add('boss-room entrance')
                elif folder in FOLDER_AP_DUNGEON:
                    row['coverage'].add('conservative dungeon entrance')
                elif entry['regions'] or (folder == 'Graveyard' and family == 'Keese'):
                    row['coverage'].add('overworld passage region and its rewards')
                else:
                    physical = [g for gid, g in groups.items()
                                if any(v['hash'] in row['targets'] for v in g if v['resource'] == path)]
                    if physical:
                        row['coverage'].add('physical reward actor')
                    elif enemy['actor'] == 'Enemy_Scrub_Deku_Leaf' and folder == 'LostWood':
                        row['coverage'].add('Lost Woods target-practice reward')
                    else:
                        # A used Dead output may only record a lore encounter;
                        # bare links can be scene references, not defeat gates.
                        row['coverage'].add('no reward/barrier dependency found')
                for mode, soul in policies.items():
                    if soul:
                        row['requirements'][mode].add('Soul (' + soul + ')')
    results = []
    for row in sorted(rows.values(), key=lambda r: r['id']):
        actor_index = {str(a.get('Hash')): a for a in maps[row['resource']]['root'].get('Actors', ())}
        for enemy in row['enemies']:
            enemy['position'] = actor_index[enemy['hash']].get('Translate')
        row['outcome_events'] = sorted({actor_index[h]['Dynamic']['RequestEventName'] for h in row['targets']
                                       if h in actor_index and actor_index[h].get('Dynamic', {}).get('RequestEventName')})
        row['reward_checks'] = {gid: {'kind': match['kind'], 'ap': match['ap']}
                                for gid, match in matches.items()
                                if any(v['resource'] == row['resource'] and v['hash'] in row['targets']
                                       for v in match['variants'])}
        row['targets'] = sorted(row['targets'])
        row['coverage'] = sorted(row['coverage'])
        row['requirements'] = {k: sorted(v) for k, v in row['requirements'].items()}
        results.append(row)
    # Check the actual rule plan, not just the inventory labels, for every
    # bound mechanical enemy and every physical chest in a native combat group.
    for mode, plan in plans.items():
        kept = {(e['resource'], e['hash']): e for e in plan['edits']}
        for enemy in enemies:
            edit = kept.get((enemy['resource'], enemy['hash']))
            if not edit or not is_mechanical(enemy):
                continue
            item = 'Soul (' + edit['soul'] + ')'
            dungeon = FOLDER_AP_DUNGEON.get(enemy['folder'])
            if dungeon and not BY_ID[family_of(enemy['actor'])][2]:
                entrances = [(r['region_name'], t) for r in world.regions for t in r.get('exits', {})
                             if r.get('dungeon') != dungeon
                             and any(tr['region_name'] == t and tr.get('dungeon') == dungeon for tr in world.regions)]
                if not entrances or any(item not in plan['exit_requirements'].get(edge, ()) for edge in entrances):
                    unresolved.append([mode, enemy['resource'], enemy['hash'], 'missing dungeon entrance rule'])
            for combat in enemy.get('combat', ()):
                for gid, variants in groups.items():
                    if any(v['resource'] == enemy['resource'] and v['hash'] in combat['targets'] for v in variants):
                        group = {'id': gid, 'folder': enemy['folder'], 'variants': variants}
                        if item not in chest_requirements(plan, group, ()):
                            unresolved.append([mode, gid, 'missing native combat reward rule'])
    return {'schema': 1, 'world': world.fingerprint(),
            'summary': {'maps': len(maps), 'enemy_instances': len(enemies), 'enemy_ai_groups': ai_groups,
                        'enemy_ai_modules': len(modules), 'encounter_records': len(results),
                        'combat_module_closure': len({m for r in results for m in r['logic_modules']}),
                        'soul_items': {mode: len(p['items']) for mode, p in plans.items()},
                        'uncovered_dependencies': len(unresolved)},
            'uncovered_dependencies': unresolved, 'encounters': results, 'enemies': enemy_rows}


def markdown(report):
    summary = report['summary']
    lines = ['# Native combat and soul audit', '',
             'Generated by `tools/audit_soul_combat.py` from the supported local game build.', '',
             '## Scope and interpretation', '',
             f"Scanned **{summary['maps']} maps**, **{summary['enemy_instances']} enemy instances**, "
             f"**{summary['enemy_ai_groups']} enemy AI groups** and **{summary['enemy_ai_modules']} distinct modules**.", '',
             'Every enemy is listed in `soul_combat_audit.json`, including optional enemies, excluded families, '
             'dream battles and the escape sequence. The table below lists native fight controllers, '
             'counter locks, scripted mechanics and bosses. Overlapping rows can describe the same battle; '
             'the record count is not a count of distinct architectural rooms.', '',
             'Used death outputs, including generic actor controllers, identify scripted dependencies. '
             'A group containing enemies and a chest or shutter is treated conservatively as a fight. '
             'This may require more souls than the shortest playable route. Dungeon fights gate every '
             'entrance to that dungeon, rather than claiming an exact AP/remake room correspondence. '
             'Overworld chests use their native actor IDs, including merged child/adult copies. '
             'The Royal Tomb also gates its whole AP region, including the song.', '',
             'Enemies excluded by `resolve_room_locks` remain present without a soul. Their fights still '
             'exist, but cannot create a missing-soul deadlock. A hidden shutter is never accepted as proof '
             'that its scripted collision or other barriers are gone.', '',
             'A defeat signal with no reward/barrier dependency can be a lore flag or scene bookkeeping; '
             'these records are explicitly labelled, not presented as compulsory fights. This is a static '
             'data audit, not a playtest of every physical collision or undocumented engine behavior.', '',
             f"Uncovered dependencies in generated soul rules: **{summary['uncovered_dependencies']}**.", '',
             'The JSON supplies stable actor and group IDs, enemy positions, requested outcome events, '
             'and matched AP reward checks for each controller.', '',
             '## Native encounter inventory', '',
             '| Map / age | Native controller | Enemies | Required souls (all) | AP reward checks | Coverage |',
             '|---|---|---|---|---|---|']
    for row in report['encounters']:
        counts = Counter(e['actor'].removeprefix('Enemy_') for e in row['enemies'])
        enemies = ', '.join(f'{k} ×{v}' for k, v in sorted(counts.items()))
        lines.append('| ' + ' | '.join((row['resource'].split('/')[1] + ' / ' + row['age'],
                     '`' + row['logic'].removeprefix('Logic/').split('.logic.')[0] + '`', enemies,
                     ', '.join(row['requirements'].get('all', ())) or 'native',
                     '; '.join(sorted({loc for m in row['reward_checks'].values() for loc in m['ap']})) or '—',
                     '; '.join(row['coverage']))) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'soul_combat_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (args.output / 'SOUL_COMBAT_AUDIT.md').write_text(markdown(report), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    if report['uncovered_dependencies']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
