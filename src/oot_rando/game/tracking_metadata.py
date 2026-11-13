"""Seed-bound collection references and observed-inventory rules, without game writes."""
from pathlib import PurePosixPath

from oot_rando.formats.inspect_resources import Byml, sarc
from oot_rando.game.remake_world import ACTOR_ITEMS, PROGRESSIVE
from oot_rando.patching.soul_adapter import murmur3, soul_actor, soul_item, soul_label
from oot_rando.game.item_forms import resolve_components, _pack_path
from oot_rando.formats import byml_codec
import copy

GAMEDATA = 'GameData/GameDataList.Product.110.byml.zs'


def add_saved_flags(raw, flags):
    """Register exact bools in progress.sav and account for their eight-byte records."""
    document = byml_codec.load(raw)
    data, meta = document['root']['Data'], document['root']['MetaData']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    template = next(e for e in data['Bool'] if e.get('SaveFileIndex') == 0 and e.get('ResetTypeValue') == 8)
    for name, default in sorted(flags.items()):
        key = murmur3(name)
        if key in known:
            raise ValueError('Tracking flag collision: ' + name)
        entry = copy.deepcopy(template)
        entry.update(Hash=byml_codec.U32(key), DefaultValue=bool(default))
        data['Bool'].append(entry)
        known.add(key)
    grown = 8 * len(flags)
    meta['SaveDataSize'][0] += grown
    meta['SaveDataOffsetPos'][0] += grown
    meta['AllDataSaveSize'] += grown
    meta['AllDataSaveOffset'] += grown
    return byml_codec.dump(document)

ITEM_LABELS = {
    'Rupee (1)': 'Green Rupee', 'Rupees (5)': 'Blue Rupee', 'Rupees (20)': 'Red Rupee',
    'Rupees (50)': 'Purple Rupee', 'Rupees (200)': 'Gold Rupee', 'Kokiri Sword': 'Kokiri Sword',
    'Deku Shield': 'Deku Shield', 'Hylian Shield': 'Hylian Shield', 'Mirror Shield': 'Mirror Shield',
    'Boomerang': 'Boomerang', 'Megaton Hammer': 'Megaton Hammer', 'Iron Boots': 'Iron Boots',
    'Hover Boots': 'Hover Boots', 'Lens of Truth': 'Lens of Truth',
    'Bomb Bag': 'Bomb Bag', 'Bow': 'Bow / Quiver', 'Slingshot': 'Slingshot / Bullet Bag',
    'Progressive Hookshot': 'Hookshot', 'Progressive Strength Upgrade': 'Strength Upgrade',
    'Progressive Scale': 'Scale', 'Progressive Wallet': 'Wallet', 'Magic Meter': 'Magic',
    'Ocarina': 'Ocarina', 'Bottle': 'Bottle', 'Bottle with Milk': 'Bottle with Milk',
    'Heart Container': 'Heart Container', 'Piece of Heart': 'Piece of Heart',
    'Gold Skulltula Token': 'Gold Skulltula Token', 'Recovery Heart': 'Recovery Heart',
    'Dins Fire': 'Din\'s Fire', 'Farores Wind': 'Farore\'s Wind', 'Nayrus Love': 'Nayru\'s Love',
    'Light Arrows': 'Light Arrows', 'Ice Arrows': 'Ice Arrows',
    'Zeldas Letter': 'Zelda\'s Letter', 'Biggoron Sword': 'Biggoron\'s Sword',
    'Fire Arrows': 'Fire Arrows', 'Stone of Agony': 'Stone of Agony',
    'Double Defense': 'Double Defense', 'Magic Jar': 'Magic Jar',
    'Deku Stick Capacity': 'Deku Stick Capacity', 'Deku Nut Capacity': 'Deku Nut Capacity',
    'Deku Stick (1)': 'Deku Stick', 'Deku Nuts (5)': 'Deku Nuts (5)', 'Deku Nuts (10)': 'Deku Nuts (10)',
    'Deku Seeds (30)': 'Deku Seeds (30)', 'Bombs (5)': 'Bombs (5)', 'Bombs (10)': 'Bombs (10)',
    'Bombs (20)': 'Bombs (20)', 'Bombchus (5)': 'Bombchus (5)',
    'Bombchus (10)': 'Bombchus (10)', 'Bombchus (20)': 'Bombchus (20)',
    'Arrows (5)': 'Arrows (5)', 'Arrows (10)': 'Arrows (10)', 'Arrows (30)': 'Arrows (30)',
    'Scrub Seed': 'Business Scrub Seed', 'Gerudo Membership Card': 'Gerudo Membership Card',
    'Kokiri Emerald': 'Kokiri Emerald', 'Goron Ruby': 'Goron Ruby', 'Zora Sapphire': 'Zora Sapphire',
    'Forest Medallion': 'Forest Medallion', 'Fire Medallion': 'Fire Medallion',
    'Water Medallion': 'Water Medallion', 'Spirit Medallion': 'Spirit Medallion',
    'Shadow Medallion': 'Shadow Medallion', 'Light Medallion': 'Light Medallion',
    'Rutos Letter': 'Ruto\'s Letter', 'Weird Egg': 'Weird Egg', 'Claim Check': 'Claim Check',
    'Goron Tunic': 'Goron Tunic', 'Zora Tunic': 'Zora Tunic', 'Fairy Ocarina': 'Fairy Ocarina',
    'Ocarina of Time': 'Ocarina of Time',
}


DUNGEON_ITEM_KINDS = {'Small Key Ring': 'Key Ring', 'Small Key': 'Small Key', 'Boss Key': 'Boss Key', 'Map': 'Map', 'Compass': 'Compass'}
DUNGEON_LABELS = {
    'Deku Tree': 'Deku Tree', 'Dodongos Cavern': 'Dodongo\'s Cavern', 'Jabu Jabus Belly': 'Jabu-Jabu\'s Belly',
    'Forest Temple': 'Forest Temple', 'Fire Temple': 'Fire Temple', 'Water Temple': 'Water Temple',
    'Shadow Temple': 'Shadow Temple', 'Spirit Temple': 'Spirit Temple',
    'Bottom of the Well': 'Bottom of the Well', 'Ice Cavern': 'Ice Cavern',
    'Gerudo Training Ground': 'Gerudo Training Ground', 'Ganons Castle': 'Ganon\'s Castle',
    'Thieves Hideout': 'Thieves\' Hideout',
}


def reward_label(item, actor=''):
    if item.startswith('Soul ('):
        return soul_label(item)
    canonical = actor.removeprefix('Obj_Rando_').removeprefix('Shop_Rando_')
    tiers = {'Item_Hookshot': 'Hookshot', 'Item_Longshot': 'Longshot',
             'Item_Gauntlet_Goron': 'Goron\'s Bracelet', 'Item_Gauntlet_Silver': 'Silver Gauntlets',
             'Item_Gauntlet_Gold': 'Golden Gauntlets', 'Item_Range_Bow': 'Fairy Bow',
             'Item_Quiver_Medium': 'Big Quiver', 'Item_Quiver_Large': 'Biggest Quiver',
             'Item_BombBag_Small': 'Bomb Bag', 'Item_BombBag_Medium': 'Big Bomb Bag',
             'Item_BombBag_Large': 'Biggest Bomb Bag',
             'Item_Ocarina_Fairy': 'Fairy Ocarina', 'Item_Ocarina_Time': 'Ocarina of Time',
             'Item_FairyBless_MPDouble': 'Double Magic', 'Item_Scale_Silver': 'Silver Scale',
             'Item_Scale_Gold': 'Golden Scale'}
    if canonical in tiers:
        return tiers[canonical]
    for kind, label in DUNGEON_ITEM_KINDS.items():
        if item.startswith(kind + ' (') and item.endswith(')'):
            dungeon = item[len(kind) + 2:-1]
            return label + ' — ' + DUNGEON_LABELS.get(dungeon, dungeon)
    plain = item.removeprefix('Remake: ')
    return ITEM_LABELS.get(item, ITEM_LABELS.get(plain, plain))


def build_tracking(seed_id, checks, full, read_raw):
    """Read only known, saved schema keys; never guess a collection from inventory."""
    schema = Byml(read_raw(GAMEDATA)).root['Data']
    keys = {typ: {int(e['Hash']) for e in entries
                  if e.get('SaveFileIndex') == 0 and 'Hash' in e}
            for typ, entries in schema.items()}
    placements = {p['id']: p for p in (full or {}).get('placements', [])}
    matches = (full or {}).get('matches', {})
    rows = {}
    for check in checks:
        gid = check['id']
        entry, placement = matches.get(gid, {}), placements.get(gid, {})
        ident = entry.get('hash') or (gid.rsplit('#', 1)[-1] if '#' in gid else gid)
        collection = None
        if str(ident).isdigit() and int(ident) in keys.get('Bool64bitKey', set()):
            if not check.get('repeatable'):
                collection = {'type': 'bool64', 'hash': str(ident)}
        if entry.get('tracking_flag'):
            collection = {'type': 'bool', 'hash': str(murmur3(entry['tracking_flag']))}
        item = placement.get('item', entry.get('vanilla', ''))
        actor = placement.get('reward_actor', placement.get('after', entry.get('before', '')))
        rows[gid] = {'collection': collection, 'reward': reward_label(item, actor) if item else '',
                     'item': item, 'actor': actor, 'logic': check.get('logic', 'unknown'),
                     'location': 'Remake|' + gid if entry else None}
    inventory = []
    actors = dict(ACTOR_ITEMS)
    for item in (full or {}).get('souls', {}).get('items', []):
        actors[soul_actor(item)] = item

    def pouch_actor(actor):
        """Follow real PouchContent inheritance, including shared component resources."""
        try:
            pack = sarc(read_raw(f'Pack/Actor/{actor}.pack.zs'))
            components = resolve_components(pack, actor, byml_codec)
            ref = components.get('PouchContentRef')
            merged, seen = {}, set()
            while ref:
                path = _pack_path(ref)
                if not path or path in seen:
                    break
                seen.add(path)
                document = Byml(pack[path] if path in pack else read_raw(path)).root
                merged = dict(document, **merged)
                ref = document.get('$parent')
            ref = merged.get('PouchActor', '')
            return PurePosixPath(ref).name.split('.')[0] if ref else actor
        except (KeyError, ValueError, FileNotFoundError):
            return actor

    counted = {'Gold Skulltula Token', 'Heart Container', 'Piece of Heart'}
    for actor, item in sorted(actors.items()):
        if item.startswith(('Rupee', 'Remake:')) or item in counted or item == 'Recovery Heart':
            continue
        canonical = pouch_actor(actor)
        aliases = {
            'Item_Sword_Kokiri': ['Weapon_Sword_Kokiri'],
            'Item_Sword_Biggoron': ['Weapon_Sword_Biggoron'],
            'TBox_Shield_Deku': ['Weapon_Shield_Deku'], 'TBox_Shield_Hylian': ['Weapon_Shield_Hylian'],
            'Item_Shield_Mirror': ['Weapon_Shield_Mirror'],
            'Item_Range_Bow': ['Weapon_Range_Bow'],
            # The seed bag is given at the start: it no longer proves the slingshot.
            'Item_Range_SlingShot': ['Weapon_Range_SlingShot'],
            'Item_HeavyBoot': ['Armor_Adult_HeavyBoot'], 'Item_HoverBoot': ['Armor_Adult_HoverBoot'],
            'Item_GlassTruth': ['Armor_Child_GlassTruth', 'Armor_Adult_GlassTruth'],
        }
        level = PROGRESSIVE[item].index(actor) + 1 if actor in PROGRESSIVE.get(item, []) else 1
        for candidate in set([canonical] + aliases.get(actor, [])):
            key = murmur3('IsGet.' + candidate)
            if key in keys.get('Bool', set()):
                inventory.append({'item': item, 'hash': str(key), 'count': level})
    # Zones (map folders) where the enemies of each soul appear, for the tracker.
    families = (full or {}).get('souls', {}).get('families', {})
    souls = [{'item': soul_item(key), 'zones': list(folders)} for key, folders in sorted(families.items())]
    # Dungeon keys (small keys found / total, boss key), read from DungeonInfo.<folder>.
    from oot_rando.patching.key_adapter import key_tracking
    dungeon_keys = key_tracking(full.get('options'), keys) if full else []
    return {'schema_version': 1, 'seed_id': seed_id, 'checks': rows, 'inventory': inventory, 'souls': souls,
            'keys': dungeon_keys,
            'logic': (full or {}).get('tracking_logic'),
            'event_markers': (full or {}).get('collection_markers', {}),
            'repeatables': (full or {}).get('repeatables', []),
            'logic_world_sha256': (full or {}).get('logic_world_sha256'),
            'known_bool64': [str(h) for h in sorted(keys.get('Bool64bitKey', set()))]}
