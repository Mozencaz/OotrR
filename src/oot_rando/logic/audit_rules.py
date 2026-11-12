"""Audit of the AP rules against clues read from the remake maps (read-only).

For every remake location matched to AP locations (chests, skulltulas, heart
pieces…), the audit collects *clues* from the game data:

* obstacles placed near the object (hookshot target, cracked wall, spider web,
  Song of Time block, magic bean soil…). Links are followed one step, so a bean
  soil counts at the rail stop it references, next to the reachable ledge;
* the age of the maps holding the object (``*_Child_*`` / ``*_Adult_*``);
* the event a chest is tied to (``GetEventName``).

Each clue is then checked against the compiled AP logic with a *necessity
test*: everything is given, the clue's items are removed (region events that
give them too), and the location is tested again. When AP still allows it, AP
does not require what the game suggests: the location is reported, ranked by
confidence and distance. Clues are hints, never proofs: the report is a review
list, nothing is changed in the logic.

Usage: ``python -m oot_rando audit [game.nup] [--no-fixes] [--output folder]``.
``--no-fixes`` ignores the remake layer (``logic/world/remake.json``) (checks that
the audit finds the already known divergences again).
"""
import argparse
import json
import math
import re
import os
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from oot_rando.paths import data_dir

AGES = ('child', 'adult')
AGE_LABELS = {'child': 'child', 'adult': 'adult'}

_EXPLOSIVES = ('Bomb Bag', 'Bombchus', 'Bombchus (5)', 'Bombchus (10)', 'Bombchus (20)', 'Bombchu Drop',
               'Buy Bombchu (5)', 'Buy Bombchu (10)', 'Buy Bombchu (20)')
# Requirement token → (label, AP items and events removed by the test).
TOKENS = {
    'hookshot': ('Hookshot', ('Progressive Hookshot',)),
    'blast_or_smash': ('Explosives or hammer', _EXPLOSIVES + ('Megaton Hammer',)),
    'hammer': ('Megaton Hammer', ('Megaton Hammer',)),
    'fire': ('Fire (Din\'s Fire, Fire Arrows, Deku Stick)',
             ('Dins Fire', 'Fire Arrows', 'Deku Stick Drop', 'Buy Deku Stick (1)')),
    'song_of_time': ('Song of Time', ('Song of Time',)),
    'lens': ('Lens of Truth', ('Lens of Truth',)),
    'bean': ('Magic bean', ('Magic Bean', 'Magic Bean Pack', 'Buy Magic Bean')),
    'strength': ('Strength (gauntlets)', ('Progressive Strength Upgrade',)),
    'blue_fire': ('Blue fire', ('Blue Fire', 'Buy Blue Fire', 'Bottle with Blue Fire')),
    'ranged': ('Ranged (slingshot or bow)', ('Slingshot', 'Bow')),
    'dive': ('Diving (scale or iron boots)', ('Progressive Scale', 'Iron Boots')),
    'mirror': ('Mirror Shield', ('Mirror Shield',)),
    'sarias_song': ('Saria\'s Song', ('Sarias Song',)),
    'storms': ('Song of Storms', ('Song of Storms',)),
    'scarecrow': ('Scarecrow\'s Song', ('Scarecrow Song',)),
}
# Remake actor name pattern → (token, radius in metres, confidence).
HINTS = (
    (r'HookShotTarget(?!Decoration)', 'hookshot', 12.0, 'medium'),
    (r'CrackWall|WallCrack|CrackFloor', 'blast_or_smash', 8.0, 'strong'),
    (r'^Obj_(DeathMtTrail_|Goron_)?BrokenRock_A', 'blast_or_smash', 6.0, 'medium'),
    (r'^Obj_.*SpiderWeb(?!Parts)', 'fire', 6.0, 'medium'),
    (r'SongOfTimeBlock', 'song_of_time', 6.0, 'strong'),
    (r'^Obj_TBox_GlassTruth', 'lens', 0.5, 'strong'),
    (r'GlassTruth', 'lens', 6.0, 'weak'),
    (r'^Obj_SmallFarm|MagicBean', 'bean', 4.0, 'strong'),
    (r'Hammer(Switch|DropFloor|DropPillar|SlipPillar|Stair)', 'hammer', 8.0, 'strong'),
    (r'RedIce', 'blue_fire', 6.0, 'strong'),
    (r'EyeSwitch', 'ranged', 10.0, 'medium'),
    (r'DiveSwitch', 'dive', 8.0, 'medium'),
    (r'SolarSwitch|CapstanMirror', 'mirror', 10.0, 'weak'),
    (r'^Obj_LiftRock_[BC]', 'strength', 5.0, 'weak'),
    (r'^OcarinaPoint_.*(Saria|SkullKid)', 'sarias_song', 8.0, 'medium'),
    (r'^OcarinaPoint_.*Windmill', 'storms', 8.0, 'weak'),
    (r'ScarecrowMarker', 'scarecrow', 10.0, 'weak'),
    # Helpers, not obstacles: only used to recognise AP alternatives (bomb
    # flowers lifted with the bracelet instead of bombs), never reported alone.
    (r'^Obj_BombFlower', 'strength', 20.0, 'helper'),
)
_HINTS = tuple((re.compile(pattern), token, radius, confidence) for pattern, token, radius, confidence in HINTS)
CONFIDENCE_WEIGHT = {'strong': 3, 'medium': 2, 'weak': 1, 'helper': 0}
# Findings already checked by hand: (AP location, token) → verdict. They are
# listed apart in the report instead of being ranked again.
REVIEWED = {
    ('Dodongos Cavern Map Chest', 'blast_or_smash'):
        'consistent: AP also accepts strength, bomb flowers are 13.8 m away (2026-11-11)',
    ('Colossus GS Hill', 'bean'):
        'consistent: AP accepts bean or longshot at night; adult bean soil linked to the zone (2026-11-11)',
}
# Map-based sources audited besides chests (others have no position).
POSITIONED_SOURCES = ('chest', 'skulltula', 'freestanding', 'bossheart')


def resource_age(resource):
    """Age of a remake map file (None: both ages share it)."""
    if '_Child_' in resource:
        return 'child'
    if '_Adult_' in resource:
        return 'adult'
    return None


def remake_ages(variants):
    """Ages in which the object exists, from the maps of its variants."""
    ages = {resource_age(v['resource']) for v in variants}
    return set(AGES) if None in ages or not ages else ages


def _point(value):
    if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
        return tuple(float(v) for v in value)
    return None


def hint_points(maps):
    """Folder → clue points ``{'token', 'radius', 'confidence', 'actor', 'via', 'point', 'age'}``.

    A clue also counts at the actors it links to (one step: a bean soil links
    to the rail stops of its flying platform).
    """
    points = defaultdict(list)
    for resource, info in sorted(maps.items()):
        folder = resource.split('/')[1]
        actors = [a for a in info['root'].get('Actors', []) or [] if isinstance(a, dict)]
        by_hash = {a['Hash']: a for a in actors if type(a.get('Hash')) is int}
        for actor in actors:
            name = actor.get('Gyaml', '')
            for pattern, token, radius, confidence in _HINTS:
                if not pattern.search(name):
                    continue
                if token == 'bean' and resource_age(resource) == 'child':
                    break  # Child soil: bug patch of a gold skulltula, beans are for the adult.
                spots = [(actor.get('Translate'), None)]
                for link in actor.get('Links', []) or []:
                    target = by_hash.get(link.get('Dst')) if isinstance(link, dict) else None
                    if target is not None and not target.get('Gyaml', '').startswith('Enemy_'):
                        spots.append((target.get('Translate'), target.get('Gyaml', '')))
                for value, via in spots:
                    point = _point(value)
                    if point:
                        points[folder].append({'token': token, 'radius': radius, 'confidence': confidence,
                                               'actor': name, 'via': via, 'point': point,
                                               'age': resource_age(resource)})
                break
    return dict(points)


def entry_clues(entry, points):
    """Clues near an entry: the closest point of every (token, actor) pair."""
    best = {}
    for variant in entry['variants']:
        position = _point(variant.get('position'))
        if position is None:
            continue
        age = resource_age(variant['resource'])
        for clue in points.get(entry['folder'], ()):
            if clue['age'] is not None and age is not None and clue['age'] != age:
                continue
            distance = math.dist(position, clue['point'])
            if distance > clue['radius']:
                continue
            key = (clue['token'], clue['actor'])
            if key not in best or distance < best[key]['distance']:
                best[key] = dict(clue, distance=round(distance, 1))
    return sorted(best.values(), key=lambda c: (-CONFIDENCE_WEIGHT[c['confidence']], c['distance']))


class _BlockedCounts(dict):
    """State counts where region events can never give the removed items."""

    def __init__(self, counts, blocked):
        super().__init__(counts)
        self.blocked = frozenset(blocked)

    def __setitem__(self, key, value):
        if key not in self.blocked:
            super().__setitem__(key, value)


class Oracle:
    """Necessity tests on a compiled :class:`oot_rando.logic.rules.Logic` (cached per token)."""

    def __init__(self, data, logic, full_count=100):
        self.logic = logic
        events = {e for region in data.regions for e in region.get('events', {})}
        # Every progression item, region events left to the logic itself.
        self.full = {item: full_count for item in data.item_table
                     if data.is_progression(item) and item not in events}
        self._states = {}

    def state(self, token=None):
        """Expanded full state without the items of ``token`` (a token or a tuple of tokens)."""
        if token not in self._states:
            tokens = (token,) if isinstance(token, str) else tuple(token or ())
            removed = {item for t in tokens for item in TOKENS[t][1]}
            counts = {k: v for k, v in self.full.items() if k not in removed}
            state = self.logic.new_state()
            state.counts = _BlockedCounts(counts, removed)
            self.logic._expand_regions(state)
            self._states[token] = state
        return self._states[token]

    def ages(self, location, token=None):
        """Ages for which ``location`` is reachable without ``token`` (empty: never)."""
        state = self.state(token)
        return {age for age in AGES
                if any(region in state.reached[age] and rule(state, state.counts, age)
                       for region, rule in self.logic.location_rules.get(location, ()))}


def audit_entry(entry, clues, ages_of):
    """Findings for one entry. ``ages_of(location, token)`` = AP ages (:meth:`Oracle.ages`).

    A ``group`` entry needs all its AP locations (conjunction), each one with
    its own ages: a clue is a finding only if every member stays reachable
    without it, in an age where the remake has the object.
    """
    locations = entry['ap']
    findings = []
    in_game = remake_ages(entry['variants'])
    ap_ages = {location: ages_of(location, None) for location in locations}
    never = [l for l, ages in ap_ages.items() if not ages]
    if never:
        return [{'kind': 'unreachable', 'confidence': 'medium', 'score': 1.0,
                 'text': 'Never reachable for the compiled logic, even with every item: '
                         + ', '.join(never) + ' (matching, or engine limit: here() folded onto age).'}]
    outside = [l for l, ages in ap_ages.items() if not ages & in_game]
    extra_ages = set().union(*ap_ages.values()) - in_game
    game_ages = ' and '.join(AGE_LABELS[a] for a in sorted(in_game))
    if len(outside) == len(locations):
        findings.append({'kind': 'age', 'confidence': 'strong', 'score': 3.0,
                         'text': 'AP never reaches it in the age of the remake maps (' + game_ages + ') : '
                                 + ', '.join(outside) + ' (doubtful matching, or item easier in game).'})
    elif extra_ages and len(locations) == 1:
        findings.append({'kind': 'age', 'confidence': 'medium', 'score': 2.0,
                         'text': 'AP also allows it as ' + ' and '.join(AGE_LABELS[a] for a in sorted(extra_ages))
                                 + '; the remake only places it in the ' + game_ages
                                 + ' maps (the logic may count it too early).'})
    def without(tokens):
        """Remake ages still allowed by AP for every member without ``tokens`` (None: blocked)."""
        still = [ages_of(location, tokens) & in_game for location in locations]
        return set().union(*still) if all(still) else None

    # Item guards of the entry (``Souls|item|…``, e.g. the Lens for invisible chests).
    guarded = {item for guard in entry.get('guards', ()) if guard.startswith('Souls|')
               for item in guard.split('|')[1:]}
    first, helpers = {}, set()
    for clue in clues:
        if set(TOKENS[clue['token']][1]) & guarded:
            continue
        if clue['confidence'] == 'helper':
            helpers.add(clue['token'])
        else:
            first.setdefault(clue['token'], clue)
    loose = {token: without(token) for token in first}
    loose = {token: ages for token, ages in loose.items() if ages}
    if loose and (len(loose) > 1 or helpers) and without(tuple(sorted(set(loose) | helpers))) is None:
        # Alternatives (explosives or strength…): AP needs one of them, as the clues say.
        loose = {}
    for token, still in loose.items():
        clue = first[token]
        weight = CONFIDENCE_WEIGHT[clue['confidence']]
        via = f' (link to {clue["via"]})' if clue['via'] else ''
        verdict = next((REVIEWED[(l, token)] for l in locations if (l, token) in REVIEWED), None)
        if verdict:
            findings.append({'kind': 'reviewed', 'token': token, 'confidence': 'weak', 'score': 0.1,
                             'text': f'{clue["actor"]}: "{TOKENS[token][0]}" — {verdict}.'})
            continue
        findings.append({'kind': 'obstacle', 'token': token, 'confidence': clue['confidence'],
                         'score': round(weight / (1 + clue['distance'] / 10), 2), 'distance': clue['distance'],
                         'actor': clue['actor'],
                         'text': f'{clue["actor"]}{via} at {clue["distance"]} m: AP does not require '
                                 f'"{TOKENS[token][0]}" (reachable without it, as '
                                 + ' and '.join(AGE_LABELS[a] for a in sorted(still)) + ').'})
    event = entry.get('event')
    if event:
        findings.append({'kind': 'event', 'confidence': 'weak', 'score': 0.3,
                         'text': f'Chest tied to the event {event} (story prerequisite to check).'})
    return findings


@contextmanager
def _without_remake_fixes(enabled):
    from oot_rando.logic import world
    if not enabled:
        yield
        return
    rules, regions = dict(world.REMAKE_LOCATION_RULES), dict(world.REMAKE_LOCATION_REGIONS)
    world.REMAKE_LOCATION_RULES.clear()
    world.REMAKE_LOCATION_REGIONS.clear()
    try:
        yield
    finally:
        world.REMAKE_LOCATION_RULES.update(rules)
        world.REMAKE_LOCATION_REGIONS.update(regions)


def matched_entries(data, logic, groups, extra, options):
    """Chest groups and positioned sources matched to AP locations (exact or group)."""
    import copy
    from oot_rando.game.remake_world import match_locations
    from oot_rando.game.extra_sources import match_sources
    matches, _ = match_locations(groups, data, logic, options['chest_matching'])
    for entry in matches.values():
        entry.setdefault('source', 'chest')
    used = {l for e in matches.values() if e['kind'] in ('exact', 'group') for l in e['ap']}
    sources = {gid: copy.deepcopy(e) for gid, e in extra.items() if e['source'] in POSITIONED_SOURCES}
    match_sources(sources, data, logic, used)
    entries = dict(matches)
    entries.update(sources)
    return {gid: e for gid, e in entries.items() if e['kind'] in ('exact', 'group') and e['ap']}


def run_audit(data, maps, groups, extra, options=None, without_fixes=False, matching='scene'):
    """Audit report: ``{'entries': [...], 'summary': {...}}`` sorted by score.

    ``matching`` is the chest matching mode; ``scene`` (default) also audits the
    chests only matched by area, the most exposed ones.
    """
    from oot_rando.logic import rando_options
    from oot_rando.logic.rules import Logic
    from oot_rando.randomizer.full_randomizer import ap_settings
    options = dict(options or rando_options.defaults(), chest_matching=matching)
    options = rando_options.validate(options, supported_only=True)
    with _without_remake_fixes(without_fixes):
        logic = Logic(data, ap_settings(options, True))
    oracle = Oracle(data, logic)
    points = hint_points(maps)
    report = []
    for gid, entry in sorted(matched_entries(data, logic, groups, extra, options).items()):
        findings = audit_entry(entry, entry_clues(entry, points), oracle.ages)
        if findings:
            report.append({'id': gid, 'folder': entry['folder'], 'source': entry['source'],
                           'kind': entry['kind'], 'ap': list(entry['ap']), 'vanilla': entry.get('vanilla'),
                           'ages': sorted(remake_ages(entry['variants'])),
                           'positions': sorted({tuple(round(c, 1) for c in _point(v['position']))
                                                for v in entry['variants'] if _point(v.get('position'))}),
                           'score': max(f['score'] for f in findings), 'findings': findings})
    report.sort(key=lambda r: (-r['score'], r['id']))
    counts = defaultdict(int)
    for row in report:
        for finding in row['findings']:
            counts[finding['kind']] += 1
    return {'entries': report, 'summary': {'flagged': len(report), 'findings': dict(sorted(counts.items())),
                                           'without_fixes': without_fixes, 'matching': matching}}


def to_markdown(result):
    from oot_rando.game.remake_world import zone_label
    summary = result['summary']
    lines = ['# Audit of the AP rules against the remake data', '',
             'Clues read from the maps, tested against the AP logic (necessity test). '
             'A clue is not a proof: each line is to be checked (in game or in the maps).', '',
             f'- Flagged locations: {summary["flagged"]}',
             '- Findings: ' + ', '.join(f'{k} {v}' for k, v in summary['findings'].items()),
             f'- Remake fixes (REMAKE_LOCATION_RULES): {"ignored" if summary["without_fixes"] else "applied"}',
             f'- Chest matching: {summary["matching"]}', '']

    def header(row):
        return (f'{zone_label(row["folder"])} · {row["source"]} · matching {row["kind"]} · '
                f'vanilla item {row["vanilla"]} · maps {"/".join(AGE_LABELS[a] for a in row["ages"])}')

    pending = lambda f: f['kind'] not in ('event', 'reviewed')
    sections = (('Check first', lambda f: pending(f) and f['score'] >= 2),
                ('To check', lambda f: pending(f) and f['score'] < 2),
                ('Already reviewed', lambda f: f['kind'] == 'reviewed'))
    for title, keep in sections:
        rows = [(row, [f for f in row['findings'] if keep(f)]) for row in result['entries']]
        rows = [(row, found) for row, found in rows if found]
        lines += [f'## {title} ({len(rows)})', '']
        for row, found in rows:
            lines.append(f'### {", ".join(row["ap"][:4])}{" …" if len(row["ap"]) > 4 else ""}')
            lines.append(header(row) + (' · position ' + str(list(row['positions'][0])) if row['positions'] else ''))
            lines += [f'- [{f["confidence"]}] {f["text"]}' for f in found]
            lines.append('')
    events = [(row, f) for row in result['entries'] for f in row['findings'] if f['kind'] == 'event']
    lines += [f'## Chests tied to an event ({len(events)})', '',
              'Possible story prerequisites (like Saria\'s Song): compare the event with the AP rule.', '']
    lines += [f'- {", ".join(row["ap"][:3])} — {f["text"].split("event ")[1].split(" ")[0]}' for row, f in events]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit of the AP rules against the remake data.')
    parser.add_argument('nup', nargs='?', help='game .nup file (default: $OOT_NUP)')
    parser.add_argument('--no-fixes', action='store_true', help='ignore REMAKE_LOCATION_RULES')
    parser.add_argument('--matching', choices=('scene', 'strict'), default='scene',
                        help='chest matching mode (default: scene)')
    parser.add_argument('--output', default=None, help='report folder')
    args = parser.parse_args(argv)
    from oot_rando.logic.world import World
    from oot_rando.game.extra_sources import scan_world
    from oot_rando.formats.inspect_nup import Nup
    from oot_rando.formats.inspect_resources import dictionaries
    from oot_rando.game.world_maps import effective_members
    nup_path = Path(args.nup or os.environ.get('OOT_NUP', ''))
    if not nup_path.is_file():
        parser.error('game .nup file not found')
    nup = Nup(nup_path)
    maps, groups, _, extra = scan_world(nup, dictionaries(nup), effective_members(nup))
    data = World()
    result = run_audit(data, maps, groups, extra, without_fixes=args.no_fixes, matching=args.matching)
    out = Path(args.output) if args.output else data_dir() / 'audit'
    out.mkdir(parents=True, exist_ok=True)
    stem = 'rules_audit_without_fixes' if args.no_fixes else 'rules_audit'
    (out / (stem + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=list),
                                        encoding='utf-8')
    (out / (stem + '.md')).write_text(to_markdown(result), encoding='utf-8')
    print(f'{result["summary"]["flagged"]} flagged locations -> {out / (stem + ".md")}')


if __name__ == '__main__':
    main()
