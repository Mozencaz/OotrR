"""Which map spots lie under water.

The maps say nothing about water on a pickup, except for the Zora's River current
(``IsInZoraRiver``). A spot counts as under water when a water surface of its map
covers it: an actor whose name holds ``WaterPlane`` (shallow planes included), its model box (RSDB ``ActorInfo`` ``ModelAabbMin``/``ModelAabbMax``) placed by
its ``Translate``, ``Rotate`` and ``Scale``, its top more than :data:`MIN_DEPTH` above
the spot and no more than :data:`MAX_DEPTH`. On the game maps this finds Ruto's
bottle and the rupees of Lake Hylia, the Zora's Fountain bottom, the Deku Tree
basement water, the streams of Kokiri Forest and Hyrule Field, the Bottom of the Well
and the Water Temple; not the land spots.
"""
import math
import re

WATER_NAME = re.compile(r'WaterPlane')
MIN_DEPTH = 0.3
MAX_DEPTH = 40.0
RIVER_FLAG = 'IsInZoraRiver'


def _rotation(rotate):
    """Matrix of the engine's Euler angles (radians, X then Y then Z)."""
    x, y, z = (rotate or (0.0, 0.0, 0.0))[:3]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = ((1, 0, 0), (0, cx, -sx), (0, sx, cx))
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rz = ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(rz, mul(ry, rx))


def _scale(value):
    if isinstance(value, (int, float)):
        return (float(value),) * 3
    return tuple(value[:3]) if value else (1.0, 1.0, 1.0)


def water_planes(root, boxes):
    """[(translate, rotation, scale, low, high)] of the water surfaces of a map root.

    ``boxes(gyaml)``: (low, high) model box of an actor ({'X','Y','Z'} each), or None."""
    planes = []
    for actor in root.get('Actors', []):
        name = actor.get('Gyaml', '')
        if not WATER_NAME.search(name):
            continue
        box = boxes(name)
        if not box or not actor.get('Translate'):
            continue
        low, high = box
        planes.append((actor['Translate'], _rotation(actor.get('Rotate')), _scale(actor.get('Scale')),
                       (low['X'], low['Y'], low['Z']), (high['X'], high['Y'], high['Z'])))
    return planes


def water_depth(position, planes):
    """Deepest water surface of ``planes`` above ``position`` (metres), or None."""
    deepest = None
    for translate, rotation, scale, low, high in planes:
        delta = [position[i] - translate[i] for i in range(3)]
        # World → plane frame: transposed rotation, then the scale.
        local = [sum(rotation[k][i] * delta[k] for k in range(3)) / (scale[i] or 1.0) for i in range(3)]
        if not (low[0] <= local[0] <= high[0] and low[2] <= local[2] <= high[2]):
            continue
        depth = (high[1] - local[1]) * abs(scale[1] or 1.0)
        if MIN_DEPTH < depth <= MAX_DEPTH and (deepest is None or depth > deepest):
            deepest = depth
    return deepest


def covered(position, planes):
    """Whether a water surface of ``planes`` lies above ``position``."""
    return water_depth(position, planes) is not None


def mark_entries(maps, entries, boxes):
    """Set ``underwater`` on the world-form variants of ``entries`` lying under water.

    ``maps``: resource → {'root': …}; a variant names its map actor by
    (``resource``, ``index``). Returns the number of marked variants."""
    planes, marked = {}, 0
    for entry in entries.values():
        if entry.get('form') != 'world':
            continue
        for variant in entry['variants']:
            resource, index = variant.get('resource'), variant.get('index')
            root = (maps.get(resource) or {}).get('root')
            if root is None or not isinstance(index, int):
                continue
            actors = root.get('Actors', [])
            if not 0 <= index < len(actors):
                continue
            actor = actors[index]
            dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
            if resource not in planes:
                planes[resource] = water_planes(root, boxes)
            position = actor.get('Translate')
            if dynamic.get(RIVER_FLAG) is True or (position and covered(position, planes[resource])):
                variant['underwater'] = True
                marked += 1
    return marked


# Breakable sources Link must reach on the bottom: only adult Link with the Iron
# Boots stands there, and the Hookshot breaks them (AP: "LH GS Lab Crate"). Child
# Link only swims. Crates only: the deep pots and rocks found by the scan are in
# dungeons whose water level changes (Bottom of the Well, Water Temple, Jabu).
DEEP_SOURCES = ('crates',)
DEEP_DEPTH = 2.0


def _layer(resource):
    """(folder, age) of a map: its water surfaces are shared by its Static and Dynamic halves."""
    from oot_rando.game.remake_world import map_age
    parts = resource.split('/')
    return (parts[1] if len(parts) > 1 else resource), map_age(resource)


def mark_deep(maps, entries, boxes):
    """Set ``deep`` on the variants of :data:`DEEP_SOURCES` lying at least
    :data:`DEEP_DEPTH` under water.

    Water surfaces sit in the ``*_Static`` maps and most crates in the ``*_Dynamic``
    ones (Lake Hylia lab, Hyrule Field storms grotto): every map of the same folder
    and age is searched, unlike ``mark_entries``. Returns the number of marked variants."""
    layers, marked = {}, 0
    for resource, data in maps.items():
        root = (data or {}).get('root')
        if root is not None:
            layers.setdefault(_layer(resource), []).extend(water_planes(root, boxes))
    for entry in entries.values():
        if entry.get('source') not in DEEP_SOURCES:
            continue
        for variant in entry['variants']:
            position, resource = variant.get('position'), variant.get('resource')
            if not resource or not isinstance(position, (list, tuple)) or len(position) != 3:
                continue
            depth = water_depth(position, layers.get(_layer(resource), ()))
            if depth is not None and depth >= DEEP_DEPTH:
                variant['deep'] = True
                marked += 1
    return marked


def drop_child_deep(entries):
    """Remove the deep child copies (child Link cannot break them); a source left
    without copies leaves the shuffle (it stays vanilla). Returns the removed ids."""
    from oot_rando.game.remake_world import map_age
    removed = []
    for gid in list(entries):
        entry = entries[gid]
        kept = [v for v in entry['variants']
                if not (v.get('deep') and map_age(v.get('resource', '')) == 'child')]
        if len(kept) == len(entry['variants']):
            continue
        if kept:
            entry['variants'] = kept
        else:
            del entries[gid]
            removed.append(gid)
    return removed
