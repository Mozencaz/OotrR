"""Remake ↔ Archipelago correspondence for chests and items.

A physical remake chest is one logical location: child/adult variants with the
same ``Hash`` in the same region folder are grouped. Each group is matched to the
AP OoT location(s) it most plausibly corresponds to:

* ``exact``: one AP location (unique item in the area, or unique in the game);
* ``group``: the chest is one of k interchangeable AP locations with the same
  vanilla item in the same area; its access rule is the conjunction of all k
  rules (conservative: it is reachable only when all candidates are);
* ``junk``: no reliable correspondence (remake-only chest, repeatable chest,
  chest with a substitution rule). Only items never required by the logic may
  be placed there, so a wrong guess can never block the game.
"""
import re
from collections import Counter, defaultdict

from oot_rando.formats.inspect_resources import Byml, decompress

# Remake region folder → AP hint areas (first element of LocationList categories).
FOLDER_AREAS = {
    'KokiriForest': ('Kokiri Forest',), 'LostWood': ('the Lost Woods',),
    'SacredForestMeadow': ('Sacred Forest Meadow',),
    # The remake merges Lon Lon Ranch and Lake Hylia into the Hyrule Field maps.
    'HyruleField': ('Hyrule Field', 'Lon Lon Ranch', 'Lake Hylia'),
    'GanonCastle': ("Outside Ganon's Castle",),
    'Market': ('the Market',), 'HyruleCastle': ('Hyrule Castle',),
    'KakarikoVillage': ('Kakariko Village',), 'Graveyard': ('the Graveyard',),
    'DeathMountainTrail': ('Death Mountain Trail',), 'DeathMountainCrater': ('Death Mountain Crater',),
    'GoronCity': ('Goron City',), 'ZoraRiver': ("Zora's River",), 'ZoraDomain': ("Zora's Domain",),
    'ZoraFountain': ("Zora's Fountain",), 'LakeHylia': ('Lake Hylia',), 'GerudoValley': ('Gerudo Valley',),
    'GerudoFortress': ("Gerudo's Fortress", 'Thieves Hideout'), 'HountedWasteland': ('Haunted Wasteland',),
    'DesertColossus': ('Desert Colossus',),
    'InsideTheDekuTree': ('Deku Tree',), 'DodongoCavern': ("Dodongo's Cavern",),
    'InsideJabuJabuBelly': ("Jabu Jabu's Belly",), 'ForestTemple': ('Forest Temple',),
    'FireTemple': ('Fire Temple',), 'WaterTemple': ('Water Temple',), 'ShadowTemple': ('Shadow Temple',),
    'SpiritTemple': ('Spirit Temple',), 'BottomOfTheWell': ('Bottom of the Well',),
    'IceCavern': ('Ice Cavern',), 'GerudoTrainingGround': ('Gerudo Training Ground',),
    'InsideGanonCastle': ("Ganon's Castle",),
}
# Tracker zones, in rough game order.
ZONE_LABELS = {
    'KokiriForest': 'Kokiri Forest', 'LostWood': 'Lost Woods', 'SacredForestMeadow': 'Sacred Forest Meadow',
    'HyruleField': 'Hyrule Field', 'LonLonRanch': 'Lon Lon Ranch', 'Market': 'Market',
    'TempleOfTime': 'Temple of Time', 'HyruleCastle': 'Hyrule Castle', 'KakarikoVillage': 'Kakariko Village',
    'Graveyard': 'Graveyard', 'DeathMountainTrail': 'Death Mountain Trail', 'GoronCity': 'Goron City',
    'DeathMountainCrater': 'Death Mountain Crater', 'ZoraRiver': 'Zora River', 'ZoraDomain': 'Zora Domain',
    'ZoraFountain': 'Zora Fountain', 'LakeHylia': 'Lake Hylia', 'GerudoValley': 'Gerudo Valley',
    'GerudoFortress': 'Gerudo Fortress', 'HountedWasteland': 'Haunted Wasteland', 'DesertColossus': 'Desert Colossus',
    'GanonCastle': 'Outside Ganon\'s Castle',
    'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': 'Dodongo\'s Cavern', 'InsideJabuJabuBelly': 'Jabu-Jabu\'s Belly',
    'ForestTemple': 'Forest Temple', 'FireTemple': 'Fire Temple', 'WaterTemple': 'Water Temple',
    'ShadowTemple': 'Shadow Temple', 'SpiritTemple': 'Spirit Temple', 'BottomOfTheWell': 'Bottom of the Well',
    'IceCavern': 'Ice Cavern', 'GerudoTrainingGround': 'Gerudo Training Ground', 'InsideGanonCastle': 'Ganon\'s Castle',
    'DreamWorld': 'Dream World (remake)', 'Other': 'Other',
}
_AREA_ZONE = {'Lon Lon Ranch': 'LonLonRanch', 'Lake Hylia': 'LakeHylia', 'Temple of Time': 'TempleOfTime',
              "Thieves' Hideout": 'GerudoFortress', "Ganon's Tower": 'InsideGanonCastle'}
_PREFIX_ZONE = (('KF ', 'KokiriForest'), ('LW ', 'LostWood'), ('SFM ', 'SacredForestMeadow'), ('HF ', 'HyruleField'),
                ('LLR ', 'LonLonRanch'), ('Market ', 'Market'), ('ToT ', 'TempleOfTime'), ('HC ', 'HyruleCastle'),
                ('OGC ', 'GanonCastle'), ('Kak ', 'KakarikoVillage'), ('Graveyard ', 'Graveyard'),
                ('DMT ', 'DeathMountainTrail'), ('DMC ', 'DeathMountainCrater'), ('GC ', 'GoronCity'),
                ('ZR ', 'ZoraRiver'), ('ZD ', 'ZoraDomain'), ('ZF ', 'ZoraFountain'), ('LH ', 'LakeHylia'),
                ('GV ', 'GerudoValley'), ('GF ', 'GerudoFortress'), ('Hideout ', 'GerudoFortress'),
                ('Wasteland ', 'HountedWasteland'), ('Colossus ', 'DesertColossus'), ('Deku Tree ', 'InsideTheDekuTree'),
                ('Dodongos Cavern ', 'DodongoCavern'), ('Jabu Jabus Belly ', 'InsideJabuJabuBelly'),
                ('Forest Temple ', 'ForestTemple'), ('Fire Temple ', 'FireTemple'), ('Water Temple ', 'WaterTemple'),
                ('Shadow Temple ', 'ShadowTemple'), ('Spirit Temple ', 'SpiritTemple'),
                ('Bottom of the Well ', 'BottomOfTheWell'), ('Ice Cavern ', 'IceCavern'),
                ('Gerudo Training Ground ', 'GerudoTrainingGround'), ('Ganons Castle ', 'InsideGanonCastle'),
                ('Ganons Tower ', 'InsideGanonCastle'))
_BOSS_ZONE = {'Queen Gohma': 'InsideTheDekuTree', 'King Dodongo': 'DodongoCavern', 'Barinade': 'InsideJabuJabuBelly',
              'Phantom Ganon': 'ForestTemple', 'Volvagia': 'FireTemple', 'Morpha': 'WaterTemple',
              'Bongo Bongo': 'ShadowTemple', 'Twinrova': 'SpiritTemple', 'Links Pocket': 'TempleOfTime',
              'Gift from Sages': 'TempleOfTime'}
# AP location types shown in the tracker (events, hints and drops are not checks).
TRACKED_TYPES = {'Chest', 'Freestanding', 'GS Token', 'Shop', 'NPC', 'Collectable', 'Beehive', 'Scrub',
                 'GrottoScrub', 'Song', 'Crate', 'SmallCrate', 'Pot', 'FlyingPot', 'Boss', 'BossHeart',
                 'Cutscene', 'RupeeTower'}


def location_zone(data, location):
    """Tracker zone key of an AP location."""
    if location in _BOSS_ZONE:
        return _BOSS_ZONE[location]
    for prefix, zone in _PREFIX_ZONE:
        if location.startswith(prefix):
            return zone
    areas = data.location_areas(location)
    for area in areas:
        if area in _AREA_ZONE:
            return _AREA_ZONE[area]
    for area in areas:
        for folder, names in FOLDER_AREAS.items():
            if area in names:
                return folder
    return 'Other'


def zone_label(zone):
    return ZONE_LABELS.get(zone, zone)


# Dungeon name used by AP item names, e.g. "Small Key (Forest Temple)".
FOLDER_DUNGEON = {
    'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': 'Dodongos Cavern',
    'InsideJabuJabuBelly': 'Jabu Jabus Belly', 'ForestTemple': 'Forest Temple',
    'FireTemple': 'Fire Temple', 'WaterTemple': 'Water Temple', 'ShadowTemple': 'Shadow Temple',
    'SpiritTemple': 'Spirit Temple', 'BottomOfTheWell': 'Bottom of the Well',
    'IceCavern': 'Ice Cavern', 'GerudoTrainingGround': 'Gerudo Training Ground',
    'InsideGanonCastle': 'Ganons Castle',
}
# AP region "dungeon" field for each dungeon folder.
FOLDER_AP_DUNGEON = {
    'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': 'Dodongos Cavern',
    'InsideJabuJabuBelly': 'Jabu Jabus Belly', 'ForestTemple': 'Forest Temple',
    'FireTemple': 'Fire Temple', 'WaterTemple': 'Water Temple', 'ShadowTemple': 'Shadow Temple',
    'SpiritTemple': 'Spirit Temple', 'BottomOfTheWell': 'Bottom of the Well',
    'IceCavern': 'Ice Cavern', 'GerudoTrainingGround': 'Gerudo Training Ground',
    'InsideGanonCastle': 'Ganons Castle',
}

ACTOR_ITEMS = {
    'TBox_Rupee_Green': 'Rupee (1)', 'TBox_Rupee_Blue': 'Rupees (5)', 'TBox_Rupee_Red': 'Rupees (20)',
    'TBox_Rupee_Purple': 'Rupees (50)', 'TBox_Rupee_Gold': 'Rupees (200)',
    'TBox_DekuNutBundle': 'Deku Nuts (5)', 'TBox_DekuSeedBundle': 'Deku Seeds (30)',
    'Item_DekuStickBundle_Small': 'Deku Stick (1)', 'TBox_ArrowBundle_Small': 'Arrows (5)',
    'TBox_ArrowBundle_Medium': 'Arrows (10)', 'TBox_ArrowBundle_Large': 'Arrows (30)',
    'TBox_Shield_Deku': 'Deku Shield', 'TBox_Shield_Hylian': 'Hylian Shield',
    'Item_Shield_Mirror': 'Mirror Shield', 'Item_Range_SlingShot': 'Slingshot', 'Item_Range_Bow': 'Bow',
    'Item_Boomerang': 'Boomerang', 'Item_Hookshot': 'Progressive Hookshot',
    'Item_Longshot': 'Progressive Hookshot', 'Item_Hammer': 'Megaton Hammer',
    'Item_HeavyBoot': 'Iron Boots', 'Item_HoverBoot': 'Hover Boots',
    'Item_Gauntlet_Silver': 'Progressive Strength Upgrade', 'Item_Gauntlet_Gold': 'Progressive Strength Upgrade',
    'Item_GlassTruth': 'Lens of Truth', 'Item_Arrow_Ice': 'Ice Arrows', 'Item_Sword_Kokiri': 'Kokiri Sword',
    'Item_BombBag_Small': 'Bomb Bag', 'Obj_Heart_Piece': 'Piece of Heart',
    'Item_BombBundle_Small': 'Bombs (5)', 'Item_BombchuBundle_Small': 'Bombchus (5)',
    'Item_BombchuBundle_Large': 'Bombchus (10)', 'Item_Token_Gold': 'Gold Skulltula Token',
    'Item_Wallet_Medium': 'Progressive Wallet', 'Item_Wallet_Large': 'Progressive Wallet',
    'Item_Scale_Silver': 'Progressive Scale', 'Item_Scale_Gold': 'Progressive Scale',
    'Item_BombBag_Medium': 'Bomb Bag', 'Item_BombBag_Large': 'Bomb Bag',
    'Item_Quiver_Medium': 'Bow', 'Item_Quiver_Large': 'Bow',
    'Item_BulletBag_Medium': 'Slingshot', 'Item_BulletBag_Large': 'Slingshot',
    'Item_StickBag_Medium': 'Deku Stick Capacity', 'Item_StickBag_Large': 'Deku Stick Capacity',
    'Item_NutBag_Medium': 'Deku Nut Capacity', 'Item_NutBag_Large': 'Deku Nut Capacity',
    'Item_Gauntlet_Goron': 'Progressive Strength Upgrade', 'Item_AgonyStone': 'Stone of Agony',
    'Item_Bottle': 'Bottle', 'Item_Bottle_Milk': 'Bottle with Milk', 'Obj_Heart': 'Recovery Heart',
    # Dungeon rewards, boss hearts, great fairies and story rewards.
    'Item_Stone_Forest': 'Kokiri Emerald', 'Item_Stone_Fire': 'Goron Ruby', 'Item_Stone_Water': 'Zora Sapphire',
    'Item_Medal_Forest': 'Forest Medallion', 'Item_Medal_Fire': 'Fire Medallion',
    'Item_Medal_Water': 'Water Medallion', 'Item_Medal_Shadow': 'Shadow Medallion',
    'Item_Medal_Spirit': 'Spirit Medallion', 'Item_Medal_Light': 'Light Medallion',
    'Obj_Heart_Container': 'Heart Container',
    'Item_DinFire': 'Dins Fire', 'Item_FaroreWind': 'Farores Wind', 'Item_NayruLove': 'Nayrus Love',
    'Item_FairyBless_MP': 'Magic Meter', 'Item_FairyBless_MPDouble': 'Magic Meter',
    'Item_FairyBless_DefenseDouble': 'Double Defense',
    'Item_Ocarina_Fairy': 'Ocarina', 'Item_Ocarina_Time': 'Ocarina',
    'Item_ZeldaLetter': 'Zeldas Letter', 'Item_Arrow_Light': 'Light Arrows',
    'Item_Sword_Biggoron': 'Biggoron Sword',
    # Remake-only items with no AP equivalent: never part of the logic.
    'Tbox_MagicJar_Large': 'Remake: Magic Jar', 'Item_ScrubBusinessSeed': 'Remake: Scrub Seed',
}
DUNGEON_ACTORS = {'Item_Dungeon_Map': 'Map', 'Item_Dungeon_Compass': 'Compass',
                  'Item_Dungeon_SmallKey': 'Small Key', 'Item_Dungeon_BossKey': 'Boss Key'}

# Progressive families: remake actors in upgrade order. A copy whose source is
# not shuffled keeps its native behaviour; see ``full_randomizer.family_tiers``.
PROGRESSIVE = {
    'Progressive Hookshot': ['Item_Hookshot', 'Item_Longshot'],
    'Progressive Strength Upgrade': ['Item_Gauntlet_Goron', 'Item_Gauntlet_Silver', 'Item_Gauntlet_Gold'],
    'Bomb Bag': ['Item_BombBag_Small', 'Item_BombBag_Medium', 'Item_BombBag_Large'],
    'Bow': ['Item_Range_Bow', 'Item_Quiver_Medium', 'Item_Quiver_Large'],
    'Slingshot': ['Item_Range_SlingShot', 'Item_BulletBag_Medium', 'Item_BulletBag_Large'],
    'Progressive Scale': ['Item_Scale_Silver', 'Item_Scale_Gold'],
    'Progressive Wallet': ['Item_Wallet_Medium', 'Item_Wallet_Large'],
    'Deku Stick Capacity': ['Item_StickBag_Medium', 'Item_StickBag_Large'],
    'Deku Nut Capacity': ['Item_NutBag_Medium', 'Item_NutBag_Large'],
    'Magic Meter': ['Item_FairyBless_MP', 'Item_FairyBless_MPDouble'],
    'Ocarina': ['Item_Ocarina_Fairy', 'Item_Ocarina_Time'],
}
# Families whose NPC upgrades need the base item (chest) in the remake.
BASE_REQUIRED = ('Bomb Bag', 'Bow', 'Slingshot')
# Unshuffled sources giving a fixed tier (others upgrade dynamically).
STATIC_TIER_SOURCES = {'GC Darunias Joy': ('Progressive Strength Upgrade', 0)}


def actor_item(actor, folder):
    if actor.startswith(('Item_KeyRing_', 'Item_BossKey_')):
        from oot_rando.patching.key_adapter import key_actor_item
        item = key_actor_item(actor)
        if item:
            return item
    if actor in DUNGEON_ACTORS:
        dungeon = FOLDER_DUNGEON.get(folder)
        if not dungeon:
            return 'Remake: ' + actor
        kind = DUNGEON_ACTORS[actor]
        if dungeon == 'Ganons Castle' and kind in ('Map', 'Compass'):
            return 'Remake: ' + actor
        return f'{kind} ({dungeon})'
    return ACTOR_ITEMS.get(actor, 'Remake: ' + actor)


def item_actor(item, folder, tier=None):
    """Remake actor for an AP item placed in ``folder`` (dungeon items stay generic)."""
    if item.startswith('Small Key Ring ('):
        from oot_rando.patching.key_adapter import item_folder, ring_actor
        return ring_actor(item_folder(item))
    if item.startswith('Remake: '):
        name = item[len('Remake: '):]
        return {'Magic Jar': 'Tbox_MagicJar_Large', 'Scrub Seed': 'Item_ScrubBusinessSeed'}.get(name, name)
    for prefix, actor in (('Map (', 'Item_Dungeon_Map'), ('Compass (', 'Item_Dungeon_Compass'),
                          ('Small Key (', 'Item_Dungeon_SmallKey'), ('Boss Key (', 'Item_Dungeon_BossKey')):
        if item.startswith(prefix):
            return actor
    if item.startswith('Soul ('):
        from oot_rando.patching.soul_adapter import soul_actor
        return soul_actor(item)
    if item in PROGRESSIVE and tier is not None:
        return PROGRESSIVE[item][tier]
    if item in PROGRESSIVE:
        return PROGRESSIVE[item][0]
    candidates = [a for a, i in ACTOR_ITEMS.items() if i == item]
    if not candidates:
        raise ValueError('No remake actor for: ' + item)
    return sorted(candidates)[0]


def enemy_counter_locks(path, root):
    """Enemy hash → room locks opened by defeating it.

    A room lock is an ``Obj_EnemyCounter_*`` (it ``Reference``-links the enemies
    to defeat) and the ``Obj_*Shutter*`` actors it opens: shutters linking to
    the counter, or linked to/from an ``EventRequestActor`` that links to it.
    Each lock: ``{'counter', 'doors': [{'resource', 'index', 'hash', 'actor', 'presence'}]}``.
    """
    actors = root.get('Actors', [])
    index_of = {a['Hash']: i for i, a in enumerate(actors) if type(a.get('Hash')) is int}
    incoming = defaultdict(list)
    for actor in actors:
        for link in actor.get('Links', []) or []:
            if isinstance(link, dict) and link.get('Dst') in index_of:
                incoming[link['Dst']].append(actor)

    def is_door(actor):
        return actor.get('Gyaml', '').startswith('Obj_') and 'Shutter' in actor.get('Gyaml', '')

    def links_of(actor):
        return [actors[index_of[l['Dst']]] for l in actor.get('Links', []) or []
                if isinstance(l, dict) and l.get('Dst') in index_of]

    locks = defaultdict(list)
    for counter in actors:
        if not counter.get('Gyaml', '').startswith('Obj_EnemyCounter') or type(counter.get('Hash')) is not int:
            continue
        doors = [a for a in incoming[counter['Hash']] if is_door(a)]
        for event in incoming[counter['Hash']]:
            if event.get('Gyaml') == 'EventRequestActor':
                doors += [a for a in links_of(event) + incoming[event['Hash']] if is_door(a)]
        unique = {}
        for door in doors:
            unique[door['Hash']] = {'resource': path, 'index': index_of[door['Hash']], 'hash': str(door['Hash']),
                                    'actor': door['Gyaml'], 'presence': door.get('Presence')}
        lock = {'counter': path + '#' + str(counter['Hash']), 'doors': [unique[h] for h in sorted(unique)]}
        for target in links_of(counter):
            if target.get('Gyaml', '').startswith('Enemy_'):
                locks[target['Hash']].append(lock)
    return locks


def scan_maps(nup, dictionaries, members, progress=None):
    """Return decoded maps, chest groups and enemy instances (read-only)."""
    report = progress or (lambda message: None)
    maps, groups, enemies = {}, defaultdict(list), []
    walls = defaultdict(list)  # folder -> (age, position) of destructible walls
    names = sorted(p for p in members if p.startswith('Banc/') and p.endswith('.bcett.byml.zs'))
    for index, path in enumerate(names):
        if index % 20 == 0:
            report(f'Reading maps: {index + 1}/{len(names)}')
        compressed = nup.read(members[path])
        raw = decompress(compressed, dictionaries)
        root = Byml(raw).root
        maps[path] = {'raw': raw, 'root': root, 'compressed': compressed}
        folder = path.split('/')[1]
        room_locks = enemy_counter_locks(path, root)
        for actor_index, actor in enumerate(root.get('Actors', [])):
            name = actor.get('Gyaml', '')
            if BLAST_WALL.match(name) and isinstance(actor.get('Translate'), list):
                walls[folder].append((_map_age(path), actor['Translate']))
            if type(actor.get('Hash')) is not int:
                continue
            dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
            if name.startswith('Obj_TBox') and isinstance(dynamic.get('Drop__DropActor'), str):
                groups[folder + '#' + str(actor['Hash'])].append({
                    'resource': path, 'index': actor_index, 'actor': name, 'folder': folder,
                    'hash': str(actor['Hash']), 'before': dynamic['Drop__DropActor'],
                    'dynamic': dynamic, 'position': actor.get('Translate')})
            elif name.startswith('Enemy_'):
                enemies.append({'resource': path, 'index': actor_index, 'actor': name, 'folder': folder,
                                'hash': str(actor['Hash']), 'presence': actor.get('Presence'),
                                'locks': room_locks.get(actor['Hash'], [])})
    for variants in groups.values():
        for variant in variants:
            variant['behind_wall'] = _behind_wall(variant, walls[variant['folder']])
    return maps, dict(groups), enemies


def _map_age(path):
    return 'child' if '_Child_' in path else 'adult' if '_Adult_' in path else None


def _behind_wall(variant, walls):
    position, age = variant.get('position'), _map_age(variant['resource'])
    if not isinstance(position, list) or len(position) != 3:
        return False
    return any((wall_age is None or age is None or wall_age == age) and len(point) == 3
               and sum((a - b) ** 2 for a, b in zip(position, point)) <= BLAST_WALL_RADIUS ** 2
               for wall_age, point in walls)


def junk_reason(variants):
    first = variants[0]
    if first['folder'] not in FOLDER_AREAS:
        return 'remake_only_area'
    if len({v['before'] for v in variants}) != 1 or len({v['actor'] for v in variants}) != 1:
        return 'variant_mismatch'
    if len({v['resource'] for v in variants}) != len(variants):
        return 'ambiguous_hash'
    for variant in variants:
        dynamic = variant['dynamic']
        if dynamic.get('IsEnableRepeatOpen'):
            return 'repeatable'
        if 'Drop__CheckActor' in dynamic or 'Drop__DropActor_Substitute' in dynamic:
            return 'substitution_rule'
    return None


# Chest groups placed by their position in the remake map. Mido's house holds
# four chests clustered around (-51, 112, -41) in KokiriForest (also the four
# chests of the original Kokiri pilot): they are the four AP Mido chests, all
# reachable at the start, never the storms grotto chest (y = 104, underground).
_MIDO_CHESTS = ('KF Midos Bottom Left Chest', 'KF Midos Bottom Right Chest', 'KF Midos Top Left Chest',
                'KF Midos Top Right Chest')
KNOWN_CHEST_GROUPS = {f'KokiriForest#{ident}': _MIDO_CHESTS for ident in
                      (10831981390482426294, 4555665598794293658, 9725242744547055868, 12786193094758345086)}


# Invisible chests (``Obj_TBox_GlassTruth*``) only show with the Lens of Truth.
# The guard is added whatever the matching: in ``scene`` mode such a chest may
# inherit the rule of another chest of the area (Gerudo Valley: the hammer rocks
# chest), and AP's own invisible-chest rules depend on ``logic_lens`` tricks.
# ``Souls|`` members of a virtual location are plain item requirements.
LENS_GUARD = 'Souls|Lens of Truth|Magic Meter'
# A chest standing against a destructible wall (``Obj_*CrackWall``) sits in an
# alcove the wall hides: Gerudo Training Ground like-like room (11/11 audit),
# where AP has no such wall. Bombs are required (stricter than AP's
# ``can_blast_or_smash``, never looser).
BLAST_WALL = re.compile(r'^Obj_.*Crack(Wall|Floor)')
BLAST_WALL_RADIUS = 3.0
BOMBS_GUARD = 'Souls|Bomb Bag'


def chest_guards(variants):
    guards = []
    if variants[0]['actor'].startswith('Obj_TBox_GlassTruth'):
        guards.append(LENS_GUARD)
    if any(v.get('behind_wall') for v in variants):
        guards.append(BOMBS_GUARD)
    return guards


def match_locations(groups, data, logic, mode='strict'):
    """Map every chest group to AP locations. ``mode`` is strict or scene."""
    ap_chests = {}
    for location in logic.location_names():
        if data.location_type(location) != 'Chest':
            continue
        areas = data.location_areas(location)
        if 'Master Quest' in areas and 'Vanilla' not in areas:
            continue
        ap_chests[location] = (data.vanilla_item(location), areas)
    used = set()
    result = {}
    pending = {}
    for group_id, variants in sorted(groups.items()):
        reason = junk_reason(variants)
        folder = variants[0]['folder']
        item = actor_item(variants[0]['before'], folder)
        entry = {'id': group_id, 'folder': folder, 'hash': variants[0]['hash'], 'actor': variants[0]['actor'],
                 'before': variants[0]['before'], 'vanilla': item, 'variants': variants,
                 'event': variants[0]['dynamic'].get('GetEventName'),
                 'dungeon': FOLDER_AP_DUNGEON.get(folder), 'kind': 'junk', 'ap': [], 'reason': reason,
                 'guards': chest_guards(variants)}
        result[group_id] = entry
        if not reason:
            pending[group_id] = entry

    def candidates(item, areas):
        return sorted(l for l, (v, cats) in ap_chests.items()
                      if l not in used and v == item and (areas is None or set(areas) & set(cats)))

    # 0. Chests identified physically (remake coordinates), whatever their item.
    for group_id, locations in KNOWN_CHEST_GROUPS.items():
        entry = pending.get(group_id)
        options = [l for l in locations if l in ap_chests and l not in used]
        if entry and entry['kind'] == 'junk' and len(options) == len(locations):
            members = [g for g, ls in KNOWN_CHEST_GROUPS.items() if ls == locations and g in pending]
            if len(members) == len(locations):
                entry.update(kind='group', ap=list(locations), reason=None)
    for entry in pending.values():
        if entry['id'] in KNOWN_CHEST_GROUPS and entry['kind'] == 'group':
            used.update(entry['ap'])
    # 1. Same item in the same area, 1 ↔ 1; then a unique game-wide match.
    by_key = defaultdict(list)
    for entry in pending.values():
        by_key[(entry['vanilla'], entry['folder'])].append(entry)
    for (item, folder), entries in sorted(by_key.items()):
        options = candidates(item, FOLDER_AREAS[folder])
        if len(entries) == 1 and len(options) == 1:
            entries[0].update(kind='exact', ap=options, reason=None)
            used.add(options[0])
    for (item, folder), entries in sorted(by_key.items()):
        if any(e['kind'] != 'junk' for e in entries) or item.startswith('Remake: '):
            continue
        options = candidates(item, None)
        same_item_groups = [e for e in pending.values() if e['vanilla'] == item and e['kind'] == 'junk']
        if len(entries) == 1 and len(options) == 1 and len(same_item_groups) == 1:
            entries[0].update(kind='exact', ap=options, reason=None)
            used.add(options[0])
    # 2. k interchangeable chests with the same item in the same area.
    for (item, folder), entries in sorted(by_key.items()):
        entries = [e for e in entries if e['kind'] == 'junk']
        if not entries:
            continue
        options = candidates(item, FOLDER_AREAS[folder])
        if len(entries) == len(options) and len(options) > 1:
            for entry in entries:
                entry.update(kind='group', ap=options, reason=None)
            used.update(options)
    # 3. Optional heuristic: remaining chests ↔ remaining chests of the area.
    if mode == 'scene':
        by_folder = defaultdict(list)
        for entry in pending.values():
            if entry['kind'] == 'junk':
                by_folder[entry['folder']].append(entry)
        for folder, entries in sorted(by_folder.items()):
            options = sorted(l for l, (v, cats) in ap_chests.items()
                             if l not in used and set(FOLDER_AREAS[folder]) & set(cats)
                             and not v.startswith(('Small Key', 'Boss Key')))
            if options:
                for entry in entries:
                    entry.update(kind='group', ap=options, reason=None)
                used.update(options)
            else:
                # No chest left in the area: require every AP check of the area.
                area = sorted(l for l in logic.location_names()
                              if set(FOLDER_AREAS[folder]) & set(data.location_areas(l))
                              and not ('Master Quest' in data.location_areas(l) and 'Vanilla' not in data.location_areas(l))
                              and data.location_type(l) not in ('HintStone', 'Hint', 'Drop', 'Event'))
                if area:
                    for entry in entries:
                        entry.update(kind='area', ap=area, reason=None)
    for entry in pending.values():
        if entry['kind'] == 'junk' and not entry['reason']:
            entry['reason'] = 'no_reliable_ap_match'
    unmatched_ap = sorted(set(ap_chests) - used)
    return result, unmatched_ap


def coverage_summary(matches):
    counts = Counter(entry['kind'] for entry in matches.values())
    reasons = Counter(entry['reason'] for entry in matches.values() if entry['kind'] == 'junk')
    return {'groups': len(matches), 'exact': counts['exact'], 'group': counts['group'], 'area': counts['area'],
            'junk_only': counts['junk'], 'junk_reasons': dict(sorted(reasons.items()))}
