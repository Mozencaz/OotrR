"""Readable names for the remake's own checks (pots, rocks, chests without an AP twin...).

Until 0.6.3 a check without its own Archipelago location was named after its map hash
("Kokiri Forest pot 055868"). It is now named after where it stands:

    <zone code>_<place>_<kind>_<n>        KF_saria_house_pot_1, DT_room3_chest_1, HF_rock_12

* zone code: the AP short codes (KF, LW, HF, Kak, DT...). Hyrule Field also holds
  Lake Hylia and Lon Lon Ranch, the Market the Temple of Time: the game's own
  ``LocationArea`` boxes give those (LH, LLR, ToT);
* place, in dungeons: the room (``DefaultDungeonRoomIndex`` of the object);
  elsewhere the landmark around it, read from the maps (:func:`landmarks`): a house
  (cluster of interior props, named after the character living there, its shop
  or its kind), else a named character, a shop, a grotto or an area entrance close
  by; none in open ground;
* kind: chest, pot, rock, crate, bush, tree, beehive, gs, heart_piece, rupee...;
* n: 1, 2... in that place, west to east.

Labels are computed once from the whole scan (:func:`label_entries`), stored in the
variants (``label``) and read back by :func:`entry_label`: the same check keeps the
same name in the tracker, the spoiler and the Archipelago catalog.
"""
from collections import defaultdict
import re

ZONE_CODES = {
    'KokiriForest': 'KF', 'LostWood': 'LW', 'SacredForestMeadow': 'SFM', 'HyruleField': 'HF',
    'Market': 'Market', 'HyruleCastle': 'HC', 'GanonCastle': 'OGC', 'KakarikoVillage': 'Kak',
    'Graveyard': 'Graveyard', 'DeathMountainTrail': 'DMT', 'GoronCity': 'GC', 'DeathMountainCrater': 'DMC',
    'ZoraRiver': 'ZR', 'ZoraDomain': 'ZD', 'ZoraFountain': 'ZF', 'LakeHylia': 'LH', 'GerudoValley': 'GV',
    'GerudoFortress': 'GF', 'HountedWasteland': 'Wasteland', 'DesertColossus': 'Colossus',
    'InsideTheDekuTree': 'DT', 'DodongoCavern': 'DC', 'InsideJabuJabuBelly': 'Jabu', 'ForestTemple': 'FoT',
    'FireTemple': 'FiT', 'WaterTemple': 'WT', 'ShadowTemple': 'ShT', 'SpiritTemple': 'SpT',
    'BottomOfTheWell': 'BotW', 'IceCavern': 'IC', 'GerudoTrainingGround': 'GTG', 'InsideGanonCastle': 'GCastle',
}
# LocationArea boxes inside a map that belong to another AP zone.
SUBZONE_CODES = {'LakeHylia': 'LH', 'LonLonRanch': 'LLR', 'TimeTemple': 'ToT'}
KIND_CODES = {'chest': 'chest', 'skulltula': 'gs', 'shop': 'shop', 'pots': 'pot', 'bushes': 'bush',
              'rocks': 'rock', 'crates': 'crate', 'beehives': 'beehive', 'trees': 'tree',
              'bossheart': 'heart_container'}
FREESTANDING_KINDS = {'Obj_Heart_Piece': 'heart_piece', 'Obj_Heart': 'heart'}

# Props whose clusters are rooms one can enter, and the place name of their kind.
INTERIOR_FAMILIES = (
    (r'^Land_Kokiri_(Interior|House_Inside)', 'house'),
    (r'^Land_LonLon_Interior', 'ranch_house'),
    (r'^Land_LakeHrl_HouseInside', 'lab'),
    (r'^Land_GerudoValley_Tent_Interior', 'tent'),
    (r'^Land_Kakariko_(House|WindmillHouse)(_|$)', 'house'),
    (r'^Land_Graveyard_Interior', 'house'),
    (r'^Land_DampeGrave_Room', 'dampe_grave'),
    (r'^Land_RoyalFamilyTomb_Room', 'royal_tomb'),
    (r'^Land_Zora_Shop', 'shop'),
    (r'^Land_HrlCity_Shop([A-Z][A-Za-z]*)_Inside', None),       # named from the prop itself
    (r'^Land_TempleOfTime_Inside', 'temple_of_time'),
    (r'^Land_Gerudo_Fortress(PotRoom|Room|HousePrison)', 'fortress_room'),
)
MARKET_SHOPS = {'TreasureBox': 'treasure_chest_game', 'Mask': 'mask_shop', 'Medicine': 'potion_shop',
                'Bombchu': 'bombchu_shop', 'Bazaar': 'bazaar', 'Shooting': 'shooting_gallery',
                'Bowling': 'bombchu_bowling', 'BombBoring': 'bombchu_bowling', 'Target': 'shooting_gallery'}
# Props telling whose room a cluster is.
OWNER_PROPS = {'Animal_Cow_LinkHouse': 'links_house'}
# Rooms numbered from the maps whose owner nothing in them tells (checked against their
# checks: Mido's four chests, Saria's hearts, the child and adult skulltulas on the
# Know-It-All Brothers' and the Twins' houses).
ROOM_NAMES = {('KokiriForest', 'house_1'): 'know_it_all_house', ('KokiriForest', 'house_2'): 'midos_house',
              ('KokiriForest', 'house_3'): 'sarias_house', ('KokiriForest', 'house_4'): 'twins_house'}
CLUSTER_LINK = 10.0    # props closer than this belong to the same room
CLUSTER_MARGIN = 1.5   # around the props' box
CLUSTER_HEIGHT = 5.0
NEAR = 10.0            # a point landmark names what lies within this distance
NAMED_NPC = re.compile(r'^Npc_[A-Za-z]+_([A-Z][a-z]+(?:[A-Z][a-z]+)*)_(Child|Adult)$')
NOT_A_NAME = {'RunningMan', 'Invisible', 'Shop'}


def snake(text):
    """'DodongoCavernSide' -> 'dodongo_cavern_side'."""
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', text)
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _clusters(points):
    """Single-linkage clusters of ``[(position, gyaml)]`` (lists of the same tuples)."""
    groups, left = [], list(points)
    while left:
        group, frontier = [left.pop()], None
        frontier = [group[0]]
        while frontier:
            current, frontier = frontier, []
            for point in current:
                near = [p for p in left if _distance(p[0], point[0]) <= CLUSTER_LINK]
                for p in near:
                    left.remove(p)
                group += near
                frontier += near
        groups.append(group)
    return groups


def _entrance_label(name):
    """'MountainTrail_DodongoCavernSide' -> 'dodongo_cavern_entrance'; None if unclear."""
    tail = name.split('_', 1)[-1] if '_' in name else name
    tail = re.sub(r'^(From|To)', '', tail)
    tail = re.sub(r'(Side|Entrance|_Under|UnderWater)$', '', tail)
    label = snake(tail)
    return label + '_entrance' if label else None


def landmarks(maps):
    """{folder: {'rooms': [...], 'points': [...], 'areas': [...]}} read from the maps.

    rooms: (label, low corner, high corner) of the enterable rooms; points: (label,
    position) of named characters, shops, grottos and entrances; areas: (zone code,
    centre, half size) of the LocationArea boxes of another AP zone.
    """
    by_folder = defaultdict(lambda: {'interior': defaultdict(list), 'points': [], 'areas': [], 'owners': []})
    for path in sorted(maps):
        folder = path.split('/')[1]
        found = by_folder[folder]
        for actor in maps[path]['root'].get('Actors', []):
            gyaml, position = actor.get('Gyaml', ''), actor.get('Translate')
            if not position:
                continue
            dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
            if gyaml == 'LocationArea' and dynamic.get('Location') in SUBZONE_CODES:
                scale = actor.get('Scale') or [1, 1, 1]
                scale = scale if isinstance(scale, list) else [scale] * 3
                found['areas'].append((SUBZONE_CODES[dynamic['Location']], position, list(scale)))   # half sizes
                continue
            for pattern, kind in INTERIOR_FAMILIES:
                match = re.match(pattern, gyaml)
                if match:
                    if kind is None:
                        kind = MARKET_SHOPS.get(match.group(1), snake(match.group(1)) + '_shop')
                    found['interior'][kind].append((position, gyaml))
                    break
            else:
                if gyaml in OWNER_PROPS:
                    found['owners'].append((OWNER_PROPS[gyaml], position))
                npc = NAMED_NPC.match(gyaml)
                if npc and npc.group(1) not in NOT_A_NAME and not actor.get('Name'):
                    found['points'].append((snake(npc.group(1)), position, 'npc'))
                elif gyaml.startswith('BGM_Shop'):
                    kind = gyaml.split('_')[3:] if len(gyaml.split('_')) > 3 else []
                    label = {'Medicine': 'potion_shop', 'Bombchu': 'bombchu_shop', 'Mask': 'mask_shop'}.get(
                        kind[0] if kind else '', 'shop')
                    found['points'].append((label, position, 'shop'))
                elif gyaml == 'Land_HidingHole_Base':
                    found['points'].append(('grotto', position, 'grotto'))
                elif gyaml == 'FieldAndDungeonEntranceEventRequestActor' and actor.get('Name'):
                    label = _entrance_label(actor['Name'])
                    if label:
                        found['points'].append((label, position, 'entrance'))
    result = {}
    for folder, found in by_folder.items():
        rooms = []
        for kind, props in sorted(found['interior'].items()):
            for cluster in _clusters(props):
                low = [min(p[0][i] for p in cluster) - CLUSTER_MARGIN for i in range(3)]
                high = [max(p[0][i] for p in cluster) + CLUSTER_MARGIN for i in range(3)]
                low[1], high[1] = low[1] - CLUSTER_HEIGHT, high[1] + CLUSTER_HEIGHT
                if len(cluster) < 3 and kind == 'house':
                    continue    # a lone prop is decoration, not a room
                inside = lambda p: all(low[i] <= p[i] <= high[i] for i in range(3))
                owner = next((label for label, pos in found['owners'] if inside(pos)), None)
                owner = owner or next((label + '_house' for label, pos, what in found['points']
                                       if what == 'npc' and inside(pos)), None)
                shop = next((label for label, pos, what in found['points'] if what == 'shop' and inside(pos)), None)
                rooms.append([owner or shop or kind, low, high, kind])
        # Rooms of one kind without their own name are numbered west to east.
        plain = defaultdict(list)
        for room in rooms:
            if room[0] == room[3]:
                plain[room[0]].append(room)
        for kind, same in plain.items():
            if len(same) > 1:
                for index, room in enumerate(sorted(same, key=lambda r: (r[1][0], r[1][2])), 1):
                    room[0] = f'{kind}_{index}'
        for room in rooms:
            room[0] = ROOM_NAMES.get((folder, room[0]), room[0])
        result[folder] = {'rooms': [tuple(r[:3]) for r in rooms],
                          'points': [(label, pos) for label, pos, _ in found['points']], 'areas': found['areas']}
    return result


def zone_code(folder, position, marks):
    """AP short code of the zone a point of ``folder``'s maps stands in."""
    for code, centre, half in (marks or {}).get('areas', ()):
        if all(abs(position[i] - centre[i]) <= half[i] for i in range(3)):
            return code
    return ZONE_CODES.get(folder, folder)


def place_of(position, marks, room=None):
    """Place label of a point: its dungeon room, the room it stands in, or a landmark near it."""
    if room is not None:
        return f'room{room}'
    marks = marks or {}
    for label, low, high in marks.get('rooms', ()):
        if all(low[i] <= position[i] <= high[i] for i in range(3)):
            return label
    best, best_distance = None, NEAR
    for label, point in marks.get('points', ()):
        distance = _distance(point, position)
        if distance <= best_distance:
            best, best_distance = label, distance
    return best


def _kind(source, before):
    if source == 'freestanding':
        if before in FREESTANDING_KINDS:
            return FREESTANDING_KINDS[before]
        return 'rupee' if (before or '').startswith('Obj_Rupee') else 'item'
    return KIND_CODES.get(source, snake(source or 'item'))


def label_entries(maps, groups, extra):
    """Set ``label`` on every variant of the positioned checks (chest groups and map sources).

    ``groups``: {gid: [variant]} (chests, source 'chest'); ``extra``: {gid: entry}. The
    numbering covers every scanned check, whatever the options of a seed.
    """
    marks = landmarks(maps)
    rows = []
    for gid, variants in groups.items():
        rows.append((gid, variants, 'chest', variants[0].get('before')))
    for gid, entry in extra.items():
        if entry['variants'] and 'position' in entry['variants'][0] and 'resource' in entry['variants'][0]:
            rows.append((gid, entry['variants'], entry.get('source'), entry.get('before')))
    named = defaultdict(list)
    for gid, variants, source, before in rows:
        first = variants[0]
        position = first.get('position')
        if not position:
            continue
        folder = first.get('folder') or first['resource'].split('/')[1]
        dynamic = first.get('dynamic')
        if dynamic is None:
            actor = maps.get(first['resource'], {}).get('root', {}).get('Actors', [])
            dynamic = actor[first['index']].get('Dynamic') if first.get('index') is not None \
                and first['index'] < len(actor) else None
        dynamic = dynamic if isinstance(dynamic, dict) else {}
        room = dynamic.get('DefaultDungeonRoomIndex')
        code = zone_code(folder, position, marks.get(folder))
        if source == 'shop':
            shop_item = gid.split('#')[2] if gid.count('#') >= 3 else (before or 'item')
            from oot_rando.game.extra_sources import SHOP_ITEMS
            item = SHOP_ITEMS.get(shop_item) or re.sub(r'_0?(\d)$', r'_\1', shop_item.removeprefix('Shop_'))
            item = item.removeprefix('Buy ')
            place = place_of(position, marks.get(folder), room) or 'shop'
            stem = f'{code}_{place}_{snake(item)}'
        else:
            place = place_of(position, marks.get(folder), room)
            stem = '_'.join(p for p in (code, place, _kind(source, before)) if p)
        named[stem].append((position[0], position[2], position[1], gid, variants))
    for stem, members in named.items():
        for index, (_, _, _, gid, variants) in enumerate(sorted(members, key=lambda m: m[:4]), 1):
            for variant in variants:
                variant['label'] = f'{stem}_{index}'
    return marks


def _load_overrides():
    """Load label_overrides.json once at import time. Missing or malformed file = no overrides."""
    import json
    from oot_rando.paths import resource
    try:
        return json.loads(resource('game', 'label_overrides.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


_LABEL_OVERRIDES = _load_overrides()


def entry_label(entry):
    """The readable name of a positioned check, or None (events, NPC gifts...)."""
    label = next((v['label'] for v in entry.get('variants', ()) if v.get('label')), None)
    if label is None:
        return None
    # Override keys come from the catalogue "name" field, which includes age suffixes
    # like " (child)" / " (adult)". Variant labels never have the suffix (tracker_checks
    # appends it separately). Try bare label first, then with each suffix.
    for key in (label, f'{label} (child)', f'{label} (adult)'):
        if key in _LABEL_OVERRIDES:
            return _LABEL_OVERRIDES[key]
    return label
