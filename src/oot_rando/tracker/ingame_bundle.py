"""In-game tracker of a seed: the data file it reads and the module that draws it.

A seed folder gets ``romfs/RandoTracker/seed.trk`` (spoiler-free: seed and goal markers,
region and check names and ids, the save flags to observe, where each check is in the game's maps) and
``exefs/subsdk7``, the prebuilt GPL-3 module that reads them while the game runs (R + right stick up), and,
made from the player's game, the items' icons (``romfs/RandoTracker/icons.bin``, ingame_icons.py). All are
listed in the manifest.
"""
import hashlib
import re

from oot_rando.game.tracking_metadata import inventory_rules
from oot_rando.patching.key_adapter import owned_key_flags
from oot_rando.paths import resource
from oot_rando.tracker.check_labels import check_labels
from oot_rando.tracker import ingame_format as fmt
from oot_rando.tracker.ingame_icons import ICON_FILE

SEED_FILE = 'RandoTracker/seed.trk'
MODULE_FILE = 'subsdk7'
MODULE_RESOURCE = ('resources', 'ingame_tracker', MODULE_FILE)
MODULE_NOTE = ('resources', 'ingame_tracker', 'SOURCE.md')
FIRST_MODULE_WITH_PLACES = (0, 7, 0)   # the module that reads seed files of version 4 (the checks' ids and places)
COLLECTION_KINDS = {'bool': fmt.KIND_BOOL, 'bool64': fmt.KIND_BOOL64}
SEED_ID_LENGTH = 16   # the length the seed folder name uses


def _regions(checks, tracking_rows, places=None):
    """Observable checks grouped by region, in catalogue order, named as the window's tracker names them, with
    their ids and their places in the game's maps (check_places.py; ``places``: by id)."""
    regions, labels, places = {}, check_labels(checks), places or {}
    for check in checks:
        reference = tracking_rows.get(check['id'], {}).get('collection')
        if reference:
            regions.setdefault(check['region'], []).append(
                (COLLECTION_KINDS[reference['type']], int(reference['hash']), labels[check['id']], check['id'],
                 places.get(check['id'], ())))
    return list(regions.items())


def _items(rules):
    items = {}
    for rule in rules:
        items.setdefault(rule['item'], []).append((int(rule['hash']), int(rule.get('count', 1))))
    return list(items.items())


def _keys(rows, key_actors=()):
    """The key rows, with the flags that say a key ring or boss key item is owned (owned_key_flags)."""
    result = []
    for row in rows or ():
        small, boss = row.get('small'), row.get('boss')
        ring, boss_flag = owned_key_flags(row, key_actors)
        flags = (fmt.KEY_SMALL if small else 0) | (fmt.KEY_BOSS if boss else 0)
        flags |= fmt.KEY_SMALL_ALL if small and small['all'] else 0
        flags |= fmt.KEY_BOSS_ALL if boss and boss['all'] else 0
        result.append({'name': row['dungeon'], 'flags': flags, 'total': small['total'] if small else 0,
                       'found': int(small['found']) if small else 0, 'held': int(small['held']) if small else 0,
                       'ring': int(ring or 0) if small else 0, 'boss': int(boss_flag) if boss else 0})
    return result


def is_archipelago(manifest):
    """Whether the seed comes from an Archipelago patch (the client's own test: client.archipelago_info)."""
    return bool((manifest.get('archipelago') or {}).get('location_ids'))


def seed_file(manifest, checks, tracking, key_actors=(), places=None):
    """Bytes of ``seed.trk`` from a seed's manifest, check catalogue and tracking data (``key_actors``:
    the seed's key ring and boss key actors, for seeds whose key rows predate owned_key_flags; ``places``: the
    checks' places by id, check_places.places), in the newest version the bundled module reads."""
    return fmt.build(manifest['seed_id'][:SEED_ID_LENGTH], int(tracking['seed_marker']),
                     int(tracking.get('goal_marker') or 0), _regions(checks, tracking['checks'], places),
                     _items(inventory_rules(tracking['inventory'])), _keys(tracking.get('keys'), key_actors),
                     flags=fmt.FLAG_ARCHIPELAGO if is_archipelago(manifest) else 0, version=seed_file_version())


def module_binary():
    return resource(*MODULE_RESOURCE).read_bytes()


def module_version():
    """The bundled module's version, as its source note gives it ((0, 0, 0) if it doesn't)."""
    note = resource(*MODULE_NOTE).read_text(encoding='utf-8')
    match = re.search(r'module version (\d+)\.(\d+)\.(\d+)', note)
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def seed_file_version():
    """The seed file version to write: 4 once the bundled module reads it, else 3 (an older module refuses a
    newer file, and the tracker would stay off), so the source can move ahead of the shipped binary."""
    return fmt.VERSION if module_version() >= FIRST_MODULE_WITH_PLACES else 3


def describe(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def attach(manifest, files, exefs, checks, tracking, icons=None, key_actors=(), places=None):
    """Add the tracker to a seed being generated: its data file (and the icons, if given) to
    ``files`` (RomFS), the module to ``exefs``, and all of them to the manifest."""
    data = seed_file(manifest, checks, tracking, key_actors, places)
    files[SEED_FILE] = data
    entries = {SEED_FILE: describe(data)}
    if icons:
        files[ICON_FILE] = icons
        entries[ICON_FILE] = describe(icons)
    manifest['files'] = dict(sorted({**manifest['files'], **entries}.items()))
    module = module_binary()
    exefs[MODULE_FILE] = module
    manifest['exefs'] = {MODULE_FILE: describe(module)}
