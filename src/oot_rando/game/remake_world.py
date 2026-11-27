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


TREASURE_GAME_REWARD = 'Market#16881481538337649070'
TREASURE_GAME_LOCATION = 'Market Treasure Chest Game Reward'
TREASURE_GAME_EVENT = 'MiniGame_ChoiceTreasure_OpenClearTreasureBox'


def is_treasure_game_reward(actor, ident):
    """The first-prize chest; the minigame's keys and repeat rupees stay native."""
    return (actor == 'Obj_HrlCity_Shop_TBox_A_02'
            and str(ident) == TREASURE_GAME_REWARD.split('#')[1])


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


from oot_rando.catalog.dungeons import (  # noqa: F401  (moved to oot_rando.catalog.dungeons, re-exported)
    FOLDER_DUNGEON,
    FOLDER_AP_DUNGEON,
)

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
    'Item_GlassTruth': 'Lens of Truth', 'Item_Arrow_Ice': 'Ice Arrows', 'Item_Arrow_Fire': 'Fire Arrows', 'Item_Sword_Kokiri': 'Kokiri Sword',
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
    'Item_Bottle_Letter': 'Rutos Letter',
    'Obj_Armor_Goron': 'Goron Tunic', 'Obj_Armor_Zora': 'Zora Tunic',
    'Item_Sword_Biggoron': 'Biggoron Sword',
    'Weapon_Sword_Master': 'Master Sword', 'Item_Rando_MasterSword': 'Master Sword',
    'Item_Token_Gerudo': 'Gerudo Membership Card',
    # Songs (pouch actors given by the song cutscenes, see patching/song_adapter.py).
    'Item_Melody_ZeldaLullaby': 'Zeldas Lullaby', 'Item_Melody_EponaSong': 'Eponas Song',
    'Item_Melody_SariaSong': 'Sarias Song', 'Item_Melody_SunSong': 'Suns Song',
    'Item_Melody_TimeSong': 'Song of Time', 'Item_Melody_StormSong': 'Song of Storms',
    'Item_Melody_ForestMinuet': 'Minuet of Forest', 'Item_Melody_FireBolero': 'Bolero of Fire',
    'Item_Melody_WaterSerenade': 'Serenade of Water', 'Item_Melody_SpiritRequiem': 'Requiem of Spirit',
    'Item_Melody_ShadowNocturne': 'Nocturne of Shadow', 'Item_Melody_LightPrelude': 'Prelude of Light',
    # Remake-only items with no AP equivalent: never part of the logic.
    'Tbox_MagicJar_Large': 'Remake: Magic Jar', 'Item_ScrubBusinessSeed': 'Remake: Scrub Seed',
}
DUNGEON_ACTORS = {'Item_Dungeon_Map': 'Map', 'Item_Dungeon_Compass': 'Compass',
                  'Item_Dungeon_SmallKey': 'Small Key', 'Item_Dungeon_BossKey': 'Boss Key'}

from oot_rando.catalog.tokens import (  # noqa: F401  (moved to oot_rando.catalog.tokens, re-exported)
    PROGRESSIVE,
)
from oot_rando.catalog.ap_items import ap_actor
from oot_rando.catalog.ap_items import is_ap_item
from oot_rando.catalog.traps import actor_trap, is_trap_actor, is_trap_item, trap_actor
# Families whose NPC upgrades need the base item (chest) in the remake.
BASE_REQUIRED = ('Bomb Bag', 'Bow', 'Slingshot')
# Unshuffled sources giving a fixed tier (others upgrade dynamically).
STATIC_TIER_SOURCES = {
    'GC Darunias Joy': ('Progressive Strength Upgrade', 0),
    # Unshuffled Great Fairies set the meter outright (24 / 48): found before the shuffled
    # copy, the double fairy made the single one useless (user report, 0.8.0).
    'HC Great Fairy Reward': ('Magic Meter', 0),
    'DMC Great Fairy Reward': ('Magic Meter', 1),
}


def static_tier_gid(location):
    """Source id of a STATIC_TIER_SOURCES location (fairies are ``fairy#``, NPC gifts ``npc#``)."""
    return ('fairy#' if location.endswith('Great Fairy Reward') else 'npc#') + location


def actor_item(actor, folder):
    if actor.startswith('Item_Prog_'):
        from oot_rando.catalog.tokens import token_family
        family = token_family(actor)
        if family:
            return family
    if actor.startswith(('Item_KeyRing_', 'Item_BossKey_', 'Item_Map_', 'Item_Compass_')):
        from oot_rando.catalog.keys import key_actor_item
        item = key_actor_item(actor)
        if item:
            return item
    if is_trap_actor(actor):
        return actor_trap(actor)
    if actor in DUNGEON_ACTORS:
        dungeon = FOLDER_DUNGEON.get(folder)
        if not dungeon:
            return 'Remake: ' + actor
        kind = DUNGEON_ACTORS[actor]
        if dungeon == 'Ganons Castle' and kind in ('Map', 'Compass'):
            return 'Remake: ' + actor
        return f'{kind} ({dungeon})'
    return ACTOR_ITEMS.get(actor, 'Remake: ' + actor)


def item_actor(item, folder):
    """Remake actor for an AP item placed in ``folder`` (dungeon items stay generic)."""
    if is_ap_item(item):
        return ap_actor(item)
    if is_trap_item(item):
        return trap_actor(item)
    if item.startswith('Small Key Ring ('):
        from oot_rando.catalog.keys import item_folder, ring_actor
        return ring_actor(item_folder(item))
    if item.startswith(('Map (', 'Compass (')):
        # Their own actor, credited wherever it is found (key_adapter).
        from oot_rando.catalog.keys import dungeon_item_actor
        actor = dungeon_item_actor(item)
        if actor:
            return actor
    if item.startswith('Remake: '):
        name = item[len('Remake: '):]
        return {'Magic Jar': 'Tbox_MagicJar_Large', 'Scrub Seed': 'Item_ScrubBusinessSeed'}.get(name, name)
    for prefix, actor in (('Map (', 'Item_Dungeon_Map'), ('Compass (', 'Item_Dungeon_Compass'),
                          ('Small Key (', 'Item_Dungeon_SmallKey'), ('Boss Key (', 'Item_Dungeon_BossKey')):
        if item.startswith(prefix):
            return actor
    if item.startswith('Soul ('):
        from oot_rando.catalog.souls import soul_actor
        return soul_actor(item)
    if item in PROGRESSIVE:
        return PROGRESSIVE[item][0]   # its first level (forms the family's copies may take)
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
    # Enemy linked straight to its shutters, without a counter (Deku Tree scrubs,
    # the 2-3-1 scrub brothers, a Forest Temple Stalfos): defeating it opens them.
    for enemy in actors:
        if not enemy.get('Gyaml', '').startswith('Enemy_') or type(enemy.get('Hash')) is not int:
            continue
        doors = {door['Hash']: door for door in links_of(enemy) + incoming[enemy['Hash']] if is_door(door)}
        if doors:
            locks[enemy['Hash']].append({'counter': path + '#' + str(enemy['Hash']), 'direct': True, 'doors': [
                {'resource': path, 'index': index_of[h], 'hash': str(h), 'actor': doors[h]['Gyaml'],
                 'presence': doors[h].get('Presence')} for h in sorted(doors)]})
    return locks


# Actors an enemy may be linked to without its defeat doing anything: movement
# paths, camera/start anchors, map icons, entrance cutscenes. Shutters are the
# room locks (``enemy_counter_locks``), handled by soul door edits.
INERT_LINKS = ('DestinationAnchor', 'StartPos', 'MapIconOffsetAnchor', 'AnchorAction',
               'FieldAndDungeonEntranceEventRequestActor')
# Dynamic parameters of an enemy that tie it to a scripted sequence: appears for
# an event (minibosses, bosses), takes part in an ordered puzzle (Deku 2-3-1).
MECHANIC_PARAMS = ('IsIntendedForEventAppear', 'DefeatedOrder', 'ShootOrder', 'TalkEventName')


def enemy_mechanics(root):
    """Enemy hash → what its defeat (or presence) drives besides room locks.

    An enemy is *mechanical* when it is linked (directly, or through an
    ``EventRequestActor``/``Obj_EnemyCounter``) to an actor that is neither
    another enemy, a shutter nor an inert anchor (a chest, a switch, a platform,
    a fuse…), or carries one of ``MECHANIC_PARAMS``. Without its soul such an
    enemy is absent and what it drives may never happen; any other enemy only
    makes its room harder, so its absence never blocks the player.
    """
    actors = root.get('Actors', [])
    by_hash = {a['Hash']: a for a in actors if type(a.get('Hash')) is int}
    incoming = defaultdict(list)
    for actor in actors:
        for link in actor.get('Links', []) or []:
            if isinstance(link, dict) and link.get('Dst') in by_hash:
                incoming[link['Dst']].append(actor)

    def neighbours(actor):
        return [by_hash[l['Dst']] for l in actor.get('Links', []) or []
                if isinstance(l, dict) and l.get('Dst') in by_hash] + incoming[actor['Hash']]

    def meaningful(actor):
        name = actor.get('Gyaml', '')
        return not (name.startswith('Enemy_') or 'Shutter' in name or name.startswith(INERT_LINKS))

    result = {}
    for enemy in actors:
        if not enemy.get('Gyaml', '').startswith('Enemy_') or type(enemy.get('Hash')) is not int:
            continue
        dynamic = enemy.get('Dynamic') if isinstance(enemy.get('Dynamic'), dict) else {}
        reasons = {'param:' + key for key in MECHANIC_PARAMS if dynamic.get(key) not in (None, False, '')}
        for other in neighbours(enemy):
            name = other.get('Gyaml', '')
            if name == 'EventRequestActor' or name.startswith('Obj_EnemyCounter'):
                hops = [other]
                if name.startswith('Obj_EnemyCounter'):
                    hops += [a for a in incoming[other['Hash']] if a.get('Gyaml') == 'EventRequestActor']
                for hop in hops:
                    reasons |= {a['Gyaml'] for a in neighbours(hop) if meaningful(a)
                                and a.get('Gyaml') != 'EventRequestActor'
                                and not a.get('Gyaml', '').startswith('Obj_EnemyCounter')}
            elif meaningful(other):
                reasons.add(name)
        result[enemy['Hash']] = sorted(reasons)
    return result


def scan_maps(nup, dictionaries, members, progress=None):
    """Return decoded maps, chest groups and enemy instances (read-only)."""
    from oot_rando.formats.inspect_resources import Byml, decompress  # zstd: not needed by the logic
    report = progress or (lambda message: None)
    maps, groups, enemies = {}, defaultdict(list), []
    from oot_rando.game.combat import combat_dependencies
    import ainb
    modules = {}

    def read_module(path):
        if path not in modules:
            if path not in members:
                raise ValueError('Missing combat logic module: ' + path)
            modules[path] = ainb.AINB.from_binary(nup.read(members[path])).as_dict()
        return modules[path]
    walls = defaultdict(list)  # folder -> (age, position) of destructible walls
    gimmicks = defaultdict(list)  # folder -> (age, guard, radius, position) of NEAR_GUARDS actors
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
        mechanics = enemy_mechanics(root)
        combat = combat_dependencies(path, root, read_module)
        for actor_index, actor in enumerate(root.get('Actors', [])):
            if inaccessible_child_actor(path, actor):
                continue
            name = actor.get('Gyaml', '')
            if BLAST_WALL.match(name) and isinstance(actor.get('Translate'), list):
                walls[folder].append((map_age(path), actor['Translate']))
            for pattern, radius, guard in NEAR_GUARDS:
                if pattern.match(name) and isinstance(actor.get('Translate'), list):
                    gimmicks[folder].append((map_age(path), guard, radius, actor['Translate']))
            if type(actor.get('Hash')) is not int:
                continue
            dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
            if ((name.startswith('Obj_TBox')
                 or (folder == 'Market' and is_treasure_game_reward(name, actor['Hash'])))
                    and isinstance(dynamic.get('Drop__DropActor'), str)):
                groups[folder + '#' + str(actor['Hash'])].append({
                    'resource': path, 'index': actor_index, 'actor': name, 'folder': folder,
                    'hash': str(actor['Hash']), 'before': dynamic['Drop__DropActor'],
                    'dynamic': dynamic, 'position': actor.get('Translate')})
            elif name.startswith('Enemy_'):
                enemies.append({'resource': path, 'index': actor_index, 'actor': name, 'folder': folder,
                                'hash': str(actor['Hash']), 'presence': actor.get('Presence'),
                                'locks': room_locks.get(actor['Hash'], []),
                                'mechanics': mechanics.get(actor['Hash'], []),
                                'combat': combat.get(actor['Hash'], [])})
    merge_same_chests(groups)
    for variants in groups.values():
        for variant in variants:
            variant['behind_wall'] = _behind_wall(variant, walls[variant['folder']])
            variant['near_guards'] = _near_guards(variant, gimmicks[variant['folder']])
    return maps, dict(groups), enemies


def map_age(path):
    """Age of a remake map file (None: a map both ages share)."""
    return 'child' if '_Child_' in path else 'adult' if '_Adult_' in path else None


# Native child copies of the seven rocks around (-99, 106, 44), on the
# Colossus bean plateau. Adult rocks have separate hashes; ground-level rocks
# and the bean soil must remain candidates. Use exact IDs to limit this exclusion.
COLOSSUS_CHILD_PLATEAU_ROCKS = frozenset({
    17604351797179232812, 18089518693918851857, 2465861655194430312,
    16808421367294770117, 15615314528351978483, 12414690125675705208,
    352697202323389437,
})


# Invisible, inaccessible Kokiri rocks reported in game. Labels are from the
# native scan before exclusions; filter by stable actor ID, never renumbered labels.
KOKIRI_INACCESSIBLE_ROCKS = {
    'child': frozenset({16780156705177292663, 4164292104786619976,
                        12045642716728132811, 13219695470225186387}),  # 12,18,24,30
    'adult': frozenset({10656348214587939196, 5853846732169153879,
                        8931631613049749371, 13164882936498639212,
                        802407974539353270, 15388836867476865988,
                        2657789777104100407, 5675403228854574159}),  # 9,14,16,19,23,26,28,33
}


# Checks reported in game as unusable (labels at report time; filtered by stable actor ID):
# a tree sharing its spot with another, crates/rocks hiding a Skulltula whose drop is not
# the randomized item, invisible or unbreakable crates, a pot behind silver boulders.
BROKEN_SOURCES = frozenset({
    11354987278416404894,   # HF_tree_19 (child; shares its tree with HF_tree_21)
    16274291912323313727,   # LH_crate_1 (adult; Skulltula overrides)
    14951295602089760727,   # Market_crate_2 (Skulltula crate)
    5803622411498968148,    # DMT_rock_17 (megaton rock hiding a Skulltula)
    8694345348366441423,    # GC_crate_1 (Skulltula crate)
    14131098108744088630,   # ZF_pot_6 (child; behind silver boulders)
    6542764537258522428, 15851182856759542692, 1454416379990914625, 4199675919137048754,   # FiT room10 crates 1-4
    16293430382336788523, 621843243819307036,   # Jabu room17 crates 1-2
})


def inaccessible_child_actor(path, actor):
    """Inaccessible actors kept out of the shuffle and the logic.

    * Every actor of the child Death Mountain Crater maps: they stay vanilla,
      and a source shared by both ages keeps only its adult copy.
    * The unreachable fortress bank of Gerudo Valley, including its buried
      grotto: the child map contains these actors despite the bridge being
      impassable. The far plateau is west of x=-15 at y~100; its grotto is at
      y~84. Keep the lower river ledges (y~48) and crate/heart ledge (x~-9, y~90).
    * The seven child Desert Colossus bean-plateau rocks: only adult Link can
      ride the planted bean to that plateau. Their adult copies stay eligible.
    * Twelve invisible Kokiri Forest rocks, with distinct child/adult IDs.

    Filter candidates only: decoded maps and original actor indices stay intact.
    """
    if actor.get('Hash') in BROKEN_SOURCES:
        return True
    if path.startswith('Banc/KokiriForest/'):
        return actor.get('Hash') in KOKIRI_INACCESSIBLE_ROCKS.get(map_age(path), ())
    if map_age(path) != 'child':
        return False
    if path.startswith('Banc/DeathMountainCrater/'):
        return True
    if path.startswith('Banc/DesertColossus/'):
        return actor.get('Hash') in COLOSSUS_CHILD_PLATEAU_ROCKS
    position = actor.get('Translate')
    return (path.startswith('Banc/GerudoValley/')
            and isinstance(position, list) and len(position) == 3
            and position[0] < -15 and position[1] >= 80)


def source_age(variants):
    """'child' or 'adult' when every copy of a source is on that age's maps, else None.

    Event flows (NPC gifts) are not maps, even when named after a child or adult NPC."""
    ages = {map_age(v['resource']) if v['resource'].startswith('Banc/') else None for v in variants}
    return ages.pop() if len(ages) == 1 else None


def _behind_wall(variant, walls):
    position, age = variant.get('position'), map_age(variant['resource'])
    if not isinstance(position, list) or len(position) != 3:
        return False
    return any((wall_age is None or age is None or wall_age == age) and len(point) == 3
               and sum((a - b) ** 2 for a, b in zip(position, point)) <= BLAST_WALL_RADIUS ** 2
               for wall_age, point in walls)


def _near_guards(variant, gimmicks):
    position, age = variant.get('position'), map_age(variant['resource'])
    if not isinstance(position, list) or len(position) != 3:
        return []
    return sorted({guard for gimmick_age, guard, radius, point in gimmicks
                   if (gimmick_age is None or age is None or gimmick_age == age) and len(point) == 3
                   and sum((a - b) ** 2 for a, b in zip(position, point)) <= radius ** 2})


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
        # This actor respawns for each game, but only exists until the first win:
        # the native IsClear flag selects a separate red-rupee chest thereafter.
        first_prize = (variant['folder'] == 'Market'
                       and is_treasure_game_reward(variant['actor'], variant.get('hash'))
                       and variant['before'] == 'Obj_Heart_Piece'
                       and dynamic.get('GetEventName') == TREASURE_GAME_EVENT)
        if dynamic.get('IsEnableRepeatOpen') and not first_prize:
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
# Small key chests reached before any locked door of their dungeon. Their eight-way
# group gave them the rule of the deepest key chest, so with key rings in their
# dungeon nothing of the Fire Temple was open without keys (16/11): the ring could
# only go behind its own doors.
# * Fire Temple: the entrance (y = 100) opens on the left (x = -6, no chain) into the
#   boss door room (boss door chain at x = -39); its key chest FiT_room2_chest_1
#   (-39, 105, 25) is the Near Boss Chest. The chained right door (x = +6) leads to
#   the big lava room (FiT_room1/22).
# * Forest Temple: FoT_room0_chest_1, the chest up the tree of the first room
#   (vanilla first small key, checked in game 16/11).
KNOWN_CHEST_GROUPS.update({
    'FireTemple#5634724236470386190': ('Fire Temple Near Boss Chest',),
    'ForestTemple#1171460703078800858': ('Forest Temple First Room Chest',),
})


# Chests whose rule is a remake event of their own (``remake.json`` events), not the
# rules of the AP chests they share an item with. Goron City has six chests where AP
# has three maze chests: matched by item, GC_chest_6 (behind the silver boulder) got
# the bombs-only rule of the center and right chests and held the Kokiri Emerald in
# logic (Discord 16/11). The matching (pool, tracker, names) is unchanged.
CHEST_RULE_EVENTS = {
    # Read the fairy's memory as adult, then return as child to open its chest.
    'HyruleField#2967378296224661060': 'HF Fairy Memory Chest',  # Obj_TBox_A_01_memo11
    # Kakariko's two freestanding heart pieces, told apart by position (17/11).
    'KakarikoVillage#free#13389209437182306002': 'Kak Windmill Heart Piece',     # Kak_heart_piece_2
    'KakarikoVillage#free#17926402522258180222': 'Kak Impas House Heart Piece',  # Kak_heart_piece_1
    'GoronCity#10944569637726152230': 'GC Lower Ledge Chests',   # GC_chest_1 (-52, 95, 26)
    'GoronCity#9159710900681116662': 'GC Lower Ledge Chests',    # GC_chest_2 (-52, 95, 32)
    'GoronCity#4402942101476009858': 'GC Hammer Rock Chest',     # GC_chest_3 (-48, 114, 2)
    'GoronCity#14647422914070455120': 'GC Maze Rocks',           # GC_chest_4 (-47, 114, -5)
    'GoronCity#1176975953041865014': 'GC Maze Rocks',            # GC_chest_5 (-47, 114, -2)
    'GoronCity#3870071239709713434': 'GC Silver Rock Chest',     # GC_chest_6 (-43, 114, -8)
    'HyruleField#17445672702269453589': 'LLR Ruins Hookshot Chest',  # LLR_chest_1 (-152, 162, 265)
}

# One chest placed in two maps. The Kokiri Forest map holds a copy of the Lost Woods
# ledge around the bridge, chest included: KokiriForest#4349272251343787229 at
# (-132.2, 123.9, -16.0) is LostWood#17479747339356189279 at (-49.4, 104.5, 71.9),
# moved by the offset between the two maps (every prop around them matches). Shuffled
# apart, the one chest in game had two items (KF_chest_1 and LW_chest_1, 20/11), one of
# them under the rule of the storms grotto chest. The copy joins the group of the
# chest it copies: one item, one opening flag, the Lost Woods rule (adult bean ledge).
# Kakariko's rooftop chest has one hash per adult banc (before / after the fire): the
# burnt copy joins the normal one, so a single item and opening flag span the fire.
SAME_CHESTS = {'KokiriForest#4349272251343787229': 'LostWood#17479747339356189279',
               'KakarikoVillage#13080955777249750889': 'KakarikoVillage#11929552275106311978'}


def merge_same_chests(groups):
    """Move the variants of each map copy (:data:`SAME_CHESTS`) into its original group."""
    for copy_id, original_id in SAME_CHESTS.items():
        if copy_id in groups and original_id in groups:
            groups[original_id].extend(groups.pop(copy_id))
    return groups


def rule_members(entry):
    """Members of the logic rule of a matched chest: its own event, else its AP locations."""
    event = CHEST_RULE_EVENTS.get(entry['id'])
    return ['Souls|' + event] if event else list(entry['ap'])


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
# Chests the zone heuristic (``scene`` mode) places have no AP rule of their own:
# they inherit the rules of every other chest of the area, which says nothing of
# the gimmick standing next to them. A chest close to one of these actors also
# needs what the gimmick asks (stricter than needed at worst). Found by a scan of
# the remake-only chests of 1.1.1 (15/11): time blocks (Ice Cavern, Sacred Forest
# Meadow, Gerudo Training Ground), hookshot targets (Fire and Water Temples),
# the Zora's Fountain scarecrow ledge, Lens walls, timed torches, cracked walls.
NEAR_GUARDS = (
    (re.compile(r'^(Obj_SongOfTime(Block|Sign)|CheckAttentionActor_TimeBlock)'), 10.0, 'Souls|Ocarina|Song of Time'),
    (re.compile(r'^Obj_(.*_)?HookShotTarget'), 10.0, 'Souls|Progressive Hookshot'),
    (re.compile(r'^Obj_ScarecrowMarker'), 10.0, 'Souls|Progressive Hookshot|Ocarina'),
    (re.compile(r'^Obj_.*GlassTruth'), 8.0, LENS_GUARD),
    (re.compile(r'^Obj_CandleStick_TimeExtinguish'), 10.0, 'Souls|Dins Fire|Magic Meter'),
    (re.compile(r'^(Obj_.*Crack(Wall|Floor)|WallCrack_)'), 6.0, BOMBS_GUARD),
)


def chest_guards(variants):
    guards = []
    if variants[0]['actor'].startswith('Obj_TBox_GlassTruth'):
        guards.append(LENS_GUARD)
    if any(v.get('behind_wall') for v in variants):
        guards.append(BOMBS_GUARD)
    return guards


def _add_near_guards(entry):
    for variant in entry['variants']:
        for guard in variant.get('near_guards', ()):
            if guard not in entry['guards']:
                entry['guards'].append(guard)


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
        if not reason and group_id == TREASURE_GAME_REWARD and TREASURE_GAME_LOCATION in ap_chests:
            # AP calls this heart piece a special item; the remake uses an ordinary
            # heart piece. Match by physical identity, keeping the Lens access rule.
            entry.update(kind='exact', ap=[TREASURE_GAME_LOCATION])
            used.add(TREASURE_GAME_LOCATION)
        elif not reason:
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
                    _add_near_guards(entry)
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
                        _add_near_guards(entry)
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
