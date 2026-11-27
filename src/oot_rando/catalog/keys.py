
"""Dungeon keys, maps and compasses: AP item names and the names of their actors.

The actors themselves are built by ``patching/key_adapter.py``.
"""
from oot_rando.catalog.dungeons import FOLDER_DUNGEON

RING_PREFIX = 'Item_KeyRing_'
BOSS_PREFIX = 'Item_BossKey_'
MAP_PREFIX = 'Item_Map_'
COMPASS_PREFIX = 'Item_Compass_'
# Bool kinds of dungeon item actor: (AP item kind, DungeonInfo Bool it sets, model).
BOOL_KINDS = {'boss': ('Boss Key', 'IsGetBossKey', 'Item_Dungeon_BossKey'),
              'map': ('Map', 'IsGetMap', 'Item_Dungeon_Map'),
              'compass': ('Compass', 'IsGetCompass', 'Item_Dungeon_Compass')}
PREFIX_KIND = {RING_PREFIX: 'ring', BOSS_PREFIX: 'boss', MAP_PREFIX: 'map', COMPASS_PREFIX: 'compass'}
APPLIED_PREFIX = 'RandoKeyRing.'
SMALL_KEY_MODEL = 'Item_Dungeon_SmallKey'
BOSS_KEY_MODEL = 'Item_Dungeon_BossKey'
# Dungeons with small keys (AP vanilla count, Thieves' Hideout apart) and with a boss key.
RING_DUNGEONS = {
    'ForestTemple': 5, 'FireTemple': 8, 'WaterTemple': 6, 'ShadowTemple': 5, 'SpiritTemple': 5,
    'BottomOfTheWell': 3, 'GerudoTrainingGround': 9, 'InsideGanonCastle': 2,
}
BOSS_KEY_DUNGEONS = ('ForestTemple', 'FireTemple', 'WaterTemple', 'ShadowTemple', 'SpiritTemple')
# Dungeons with a map and a compass (AP items ``Map (…)``/``Compass (…)``).
MAP_DUNGEONS = ('InsideTheDekuTree', 'DodongoCavern', 'InsideJabuJabuBelly', 'ForestTemple', 'FireTemple',
                'WaterTemple', 'ShadowTemple', 'SpiritTemple', 'BottomOfTheWell', 'IceCavern')
DUNGEON_FOLDER = {dungeon: folder for folder, dungeon in FOLDER_DUNGEON.items()}
# In-game names for the French message files (EUfr / CAfr).
FRENCH_DUNGEONS = {
    'ForestTemple': 'Temple de la Forêt', 'FireTemple': 'Temple du Feu', 'WaterTemple': 'Temple de l’Eau',
    'ShadowTemple': 'Temple de l’Ombre', 'SpiritTemple': 'Temple de l’Esprit',
    'BottomOfTheWell': 'Puits de Cocorico', 'GerudoTrainingGround': 'Gymnase Gerudo',
    'InsideGanonCastle': 'Château de Ganon', 'InsideTheDekuTree': 'Arbre Mojo',
    'DodongoCavern': 'Caverne Dodongo', 'InsideJabuJabuBelly': 'Ventre de Jabu-Jabu', 'IceCavern': 'Caverne Polaire',
}
ENGLISH_DUNGEONS = {
    'ForestTemple': 'Forest Temple', 'FireTemple': 'Fire Temple', 'WaterTemple': 'Water Temple',
    'ShadowTemple': 'Shadow Temple', 'SpiritTemple': 'Spirit Temple', 'BottomOfTheWell': 'Bottom of the Well',
    'GerudoTrainingGround': 'Gerudo Training Ground', 'InsideGanonCastle': "Ganon's Castle",
    'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': "Dodongo's Cavern", 'InsideJabuJabuBelly': "Jabu-Jabu's Belly",
    'IceCavern': 'Ice Cavern',
}


def total_keys(held):
    """``DungeonInfo.<folder>.SmallKeyTotalNum`` (keys found) of a ``SmallKeyNum`` (keys held)."""
    if not held.endswith('.SmallKeyNum'):
        raise ValueError('Not a held key count: ' + held)
    return held[:-len('SmallKeyNum')] + 'SmallKeyTotalNum'


def ring_item(folder):
    return f'Small Key Ring ({FOLDER_DUNGEON[folder]})'


def small_key_item(folder):
    return f'Small Key ({FOLDER_DUNGEON[folder]})'


def is_ring(item):
    return item.startswith('Small Key Ring (')


def item_folder(item):
    """Dungeon folder of a key item (``Small Key Ring (X)``, ``Boss Key (X)``…)."""
    return DUNGEON_FOLDER[item[item.index('(') + 1:-1]]


# Actor names of the long dungeon folders. In-game test 13/11: the item get of a
# generated actor named Item_KeyRing_GerudoTrainingGround (33 characters) or
# Item_KeyRing_InsideGanonCastle (30) crashes the game (null read, Link holding
# nothing), while every generated actor of 25 characters or fewer is handed over
# (see soul_adapter.MAX_ACTOR_NAME).
SHORT_FOLDER = {'BottomOfTheWell': 'Well', 'GerudoTrainingGround': 'GTG', 'InsideGanonCastle': 'Ganon',
                'InsideTheDekuTree': 'Deku', 'DodongoCavern': 'Dodongo', 'InsideJabuJabuBelly': 'Jabu'}
FOLDER_OF_SHORT = {short: folder for folder, short in SHORT_FOLDER.items()}


def ring_actor(folder):
    return RING_PREFIX + SHORT_FOLDER.get(folder, folder)


def boss_actor(folder):
    return BOSS_PREFIX + SHORT_FOLDER.get(folder, folder)


def map_actor(folder):
    return MAP_PREFIX + SHORT_FOLDER.get(folder, folder)


def compass_actor(folder):
    return COMPASS_PREFIX + SHORT_FOLDER.get(folder, folder)


def dungeon_item_actor(item):
    """Own actor of a ``Map (X)``/``Compass (X)`` AP item, or None."""
    for kind, make in (('Map (', map_actor), ('Compass (', compass_actor)):
        folder = DUNGEON_FOLDER.get(item[len(kind):-1]) if item.startswith(kind) else None
        if folder in MAP_DUNGEONS:
            return make(folder)
    return None


def actor_kind(actor):
    """'ring', 'boss', 'map' or 'compass' of a dungeon item actor's name, else None."""
    return next((kind for prefix, kind in PREFIX_KIND.items() if actor.startswith(prefix)), None)


def specific_actor(item):
    """Dungeon-specific actor for experimental placement modes."""
    if is_ring(item):
        return ring_actor(item_folder(item))
    if item.startswith('Boss Key ('):
        return boss_actor(item_folder(item))
    actor = dungeon_item_actor(item)
    if actor is None:
        raise ValueError('Not a dungeon item: ' + item)
    return actor


def actor_folder(actor):
    """Dungeon folder of a key actor (``Item_KeyRing_GTG`` → ``GerudoTrainingGround``), or None."""
    for prefix in PREFIX_KIND:
        if actor.startswith(prefix):
            name = actor[len(prefix):]
            folder = FOLDER_OF_SHORT.get(name, name)
            return folder if folder in FOLDER_DUNGEON else None
    return None


def key_actor_item(actor):
    """AP item of a dungeon-specific key actor, or None."""
    folder = actor_folder(actor)
    if folder is None:
        return None
    kind = actor_kind(actor)
    name = 'Small Key Ring' if kind == 'ring' else BOOL_KINDS[kind][0]
    return f'{name} ({FOLDER_DUNGEON[folder]})'


def is_key_actor(actor):
    return key_actor_item(actor) is not None


# Tracker: Ganon's Castle boss key (Ganon's Tower) is shown with the temples' ones.
TRACKED_BOSS_KEYS = BOSS_KEY_DUNGEONS + ('InsideGanonCastle',)
