"""Readable spoiler of a seed: rows for the GUI page and a plain-text spoiler file.

Built only from the seed's own spoiler.json and checks.json, never from the game.
"""
import json
from pathlib import Path

from oot_rando.game.remake_world import actor_item, zone_label
from oot_rando.game.tracking_metadata import reward_label

SPOILER_TEXT = 'spoiler.txt'
KIND_LABELS = {
    'chest': 'Chest', 'skulltula': 'Gold Skulltula', 'freestanding': 'Freestanding item', 'shop': 'Shop',
    'pots': 'Pot', 'crates': 'Crate', 'beehives': 'Beehive', 'bushes': 'Bush', 'rocks': 'Rock', 'trees': 'Tree',
    'npc': 'NPC', 'boss': 'Dungeon reward', 'bossheart': 'Boss heart container',
    'fairy': 'Great fairy', 'quest': 'Quest reward', 'scrub': 'Business scrub',
}


def find_spoiler(directory, extra_roots=()):
    """spoiler.json of a seed folder. An installed copy has none: look for its
    generated source (same folder name) under the given roots."""
    directory = Path(directory)
    candidates = [directory / 'spoiler.json'] + [Path(root) / directory.name / 'spoiler.json'
                                                 for root in extra_roots]
    for path in candidates:
        if path.is_file():
            return path
    return None


def item_label(item, actor=''):
    if not item:
        return ''
    return reward_label(item, actor or '')


EXTRA_ORIGINALS = {
    'Item_Dungeon_Compass': 'Compass', 'Item_Dungeon_Map': 'Dungeon Map',
    'Item_Dungeon_BossKey': 'Boss Key', 'Shop_Heart': 'Recovery Heart', 'Shop_DekuStick': 'Deku Stick',
    'Shop_Bottle_Fish': 'Bottled Fish', 'Shop_Bottle_RedPotion': 'Red Potion',
    'Shop_Weapon_Shield_Hylian': 'Hylian Shield', 'Shop_Weapon_Shield_Deku': 'Deku Shield',
}
SHOP_PREFIXES = {'Shop_BombBundle': 'Bombs', 'Shop_BombchuBundle': 'Bombchus',
                 'Shop_ArrowBundle': 'Arrows', 'Shop_DekuNutBundle': 'Deku Nuts',
                 'Shop_DekuSeedBundle': 'Deku Seeds', 'Shop_DekuStickBundle': 'Deku Sticks'}


def _original(before, zone):
    """Name of the vanilla reward a placement replaced."""
    if not before:
        return ''
    if before in EXTRA_ORIGINALS:
        return EXTRA_ORIGINALS[before]
    for prefix, label in SHOP_PREFIXES.items():
        if before.startswith(prefix):
            return label
    # World pickups (Obj_Rupee_Green, Obj_Token_Gold…) share their chest/item twin.
    for candidate in (before, before.replace('Obj_', 'TBox_', 1), before.replace('Obj_', 'Item_', 1)):
        item = actor_item(candidate, zone)
        if not item.startswith('Remake: '):
            return reward_label(item, candidate)
    return reward_label(actor_item(before, zone), before)


def _playthrough_entry(text):
    """'Location : AP item' → (location, French item label)."""
    location, sep, item = text.rpartition(' : ')
    if not sep:
        return '', text
    return location, item_label(item)


def load_report(directory, extra_roots=()):
    """Return {'seed_id', 'seed', 'rows', 'playthrough', 'path'} or raise FileNotFoundError."""
    directory = Path(directory)
    path = find_spoiler(directory, extra_roots)
    if path is None:
        raise FileNotFoundError('No spoiler.json for this seed (copy installed by an old version?). '
                                'Generate the seed again.')
    spoiler = json.loads(path.read_text(encoding='utf-8'))
    catalogue = {}
    for source in (path.parent, directory):
        checks = source / 'checks.json'
        if checks.is_file():
            catalogue = {c['id']: c for c in json.loads(checks.read_text(encoding='utf-8'))['checks']}
            break
    seed = ''
    manifest = path.parent / 'manifest.json'
    if manifest.is_file():
        seed = json.loads(manifest.read_text(encoding='utf-8')).get('settings', {}).get('seed', '')
    rows = []
    for placement in spoiler.get('placements', []):
        ident = str(placement.get('id', placement.get('hash', '')))
        check = catalogue.get(ident, {})
        zone = check.get('zone') or ident.split('#', 1)[0]
        region = check.get('region') or zone_label(zone) or 'Autres'
        if placement.get('category') == 'kokiri_chests' or 'item' not in placement:
            # Historical Kokiri/world chests: only the replaced actor is known.
            after = placement.get('after', '')
            item = reward_label(actor_item(after, zone or 'KokiriForest'), after) if after else ''
            source = 'chest'
        else:
            item = item_label(placement['item'], placement.get('reward_actor') or placement.get('actor'))
            source = placement.get('source', '')
        aps = placement.get('ap_locations') or []
        name = check.get('name') or placement.get('location') or ident
        rows.append({'id': ident, 'region': region, 'zone': zone, 'location': name,
                     'item': item, 'original': _original(placement.get('before', ''), zone),
                     'sphere': placement.get('sphere'), 'kind': KIND_LABELS.get(source, source or 'Chest'),
                     'ap_locations': aps})
    rows.sort(key=lambda r: (r['region'], r['location']))
    playthrough = []
    for sphere in spoiler.get('playthrough', []):
        playthrough.append({'sphere': sphere['sphere'],
                            'items': [_playthrough_entry(text) for text in sphere.get('items', [])]})
    return {'seed_id': spoiler.get('seed_id', ''), 'seed': seed, 'rows': rows,
            'playthrough': playthrough, 'path': str(path)}


def render_text(report):
    lines = ['OoT Randomizer — spoiler', '=' * 40,
             'Seed: ' + (report.get('seed') or '?'),
             'Identity: ' + report.get('seed_id', '')[:16],
             f'{len(report["rows"])} shuffled locations', '']
    if report['playthrough']:
        lines += ['PROGRESSION PLAYTHROUGH', '-' * 40]
        for sphere in report['playthrough']:
            lines.append(f'Sphere {sphere["sphere"]}')
            for location, item in sphere['items']:
                lines.append(f'    {location}: {item}' if location else f'    {item}')
        lines.append('')
    lines += ['LOCATIONS BY ZONE', '-' * 40]
    region = None
    for row in report['rows']:
        if row['region'] != region:
            region = row['region']
            lines += ['', f'[{region}]']
        sphere = '' if row['sphere'] is None else f'  (sphere {row["sphere"]})'
        original = f'  — originally: {row["original"]}' if row['original'] else ''
        lines.append(f'  {row["location"]} [{row["kind"]}]: {row["item"]}{sphere}{original}')
    return '\n'.join(lines) + '\n'


def write_text(report, destination):
    destination = Path(destination)
    destination.write_text(render_text(report), encoding='utf-8')
    return destination
