"""Where each check is in the game's world, for the in-game tracker's "show in the world" (seed.trk version 4).

A check's place is its own placed actor in the game's map layouts (``romfs/Banc/<Area>/<Map>_Static|_Dynamic
.bcett.byml.zs``): the map's name as the save's "map" string has it (the layout's name without ``_Static`` or
``_Dynamic``, the rule of sloperinaGZ's tools/airwalls.py and its FINDINGS 5.11), and the actor's ``Translate``,
in the world's metres. The actor is found by the instance ``Hash`` the check's id carries (``Area#hash``,
``Area#hash#field``, ``Area#<kind>#hash``; the first chests' ids are their bare hashes, in Kokiri Forest), a
shop's by its ``Gyaml`` and ``ShopItemIndex`` (``Area#shop#<Gyaml>#<slot>``). Only the game's own layouts are
read, never the seed's rewards. A check placed in both ages' maps has a place in each; a check whose id names no
placed actor (an NPC, an event, an Archipelago row) has none.
"""
import math

from oot_rando.game.remake_world import inaccessible_child_actor, zone_label

LAYOUT_PREFIX = 'Banc/'
LAYOUT_SUFFIX = '.bcett.byml.zs'
LAYOUT_PARTS = ('Static', 'Dynamic')
BARE_HASH_FOLDER = 'KokiriForest'


def map_name(path):
    """``Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs`` -> ``KokiriForest_Child``."""
    stem = path.rsplit('/', 1)[-1][:-len(LAYOUT_SUFFIX)]
    head, _, part = stem.rpartition('_')
    return head if head and part in LAYOUT_PARTS else stem


def _words(name):
    """``GohmaStage`` -> ``Gohma Stage``."""
    out = ''
    for i, char in enumerate(name):
        if i and char.isupper() and not name[i - 1].isupper():
            out += ' '
        out += char
    return out


def map_label(name):
    """``KokiriForest_Child`` -> ``Kokiri Forest (child)``; ``KakarikoVillage_Adult_Alternative`` -> ``Kakariko
    Village (adult, alternative)``; a map that isn't an area's (a boss room) is its name in words."""
    area, *rest = name.split('_')
    label = zone_label(area)
    label = _words(area) if label == area else label
    return label + (' (' + ', '.join(part.lower() for part in rest) + ')' if rest else '')


def _target(check_id):
    """(area folder, what finds its actor): ('hash', n) or ('shop', Gyaml, slot); None if the id names no actor."""
    if check_id.isdigit():
        return BARE_HASH_FOLDER, ('hash', int(check_id))
    parts = check_id.split('#')
    if len(parts) < 2:
        return None
    if len(parts) == 4 and parts[1] == 'shop' and parts[3].isdigit():
        return parts[0], ('shop', parts[2], int(parts[3]))
    for part in parts[1:3]:
        if part.isdigit():
            return parts[0], ('hash', int(part))
    return None


def _position(actor):
    translate = actor.get('Translate')
    if not isinstance(translate, list) or len(translate) != 3:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in translate):
        return None
    return tuple(float(v) for v in translate)


def _actor_keys(actor):
    """The keys an actor is found by: its hash, and a shop item's (Gyaml, slot)."""
    keys = [('hash', actor.get('Hash'))]
    if isinstance(actor.get('Gyaml'), str):
        dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
        keys.append(('shop', actor['Gyaml'], dynamic.get('ShopItemIndex', 0)))
    return keys


def folders(check_ids):
    """The area folders whose layouts hold these checks' actors."""
    return sorted({target[0] for target in map(_target, check_ids) if target})


def places(check_ids, maps):
    """``{check id: [(map, map label, x, y, z)]}`` for the checks found in ``maps`` (``{layout path: {'root': its
    decoded BYML}}``, scan_maps' and nup_maps' form), one place per map, in map order (a map's first matching
    actor). The child maps' actors the randomizer leaves out (inaccessible_child_actor) aren't places."""
    wanted = {}   # folder -> actor key -> check ids
    for ident in check_ids:
        target = _target(ident)
        if target:
            wanted.setdefault(target[0], {}).setdefault(target[1], []).append(ident)
    found = {}
    for path in sorted(maps):
        if not path.startswith(LAYOUT_PREFIX) or not path.endswith(LAYOUT_SUFFIX):
            continue
        targets = wanted.get(path.split('/')[1])
        if not targets:
            continue
        name = map_name(path)
        for actor in maps[path]['root'].get('Actors', []):
            if not isinstance(actor, dict) or inaccessible_child_actor(path, actor):
                continue
            idents = [ident for key in _actor_keys(actor) for ident in targets.get(key, ())]
            position = _position(actor) if idents else None
            for ident in idents if position else ():
                rows = found.setdefault(ident, [])
                if all(row[0] != name for row in rows):
                    rows.append((name, map_label(name)) + position)
    return {ident: sorted(rows) for ident, rows in found.items()}


def nup_maps(nup, dictionaries, area_folders):
    """The layouts of ``area_folders`` decoded from an open NUP, in places' form."""
    from oot_rando.formats.inspect_resources import Byml, decompress
    from oot_rando.game.world_maps import effective_members
    members = effective_members(nup)
    prefixes = tuple(LAYOUT_PREFIX + folder + '/' for folder in area_folders)
    return {path: {'root': Byml(decompress(nup.read(members[path]), dictionaries)).root}
            for path in sorted(members) if path.startswith(prefixes) and path.endswith(LAYOUT_SUFFIX)}
