"""Fake item traps: planner names, pouch actors and saved flags.

With the ``fake_item_traps`` option, fake copies of items join the pool: each looks
like its item (model and name), its get text says it is a trap, and Link is frozen
once it is got. ``some``: one copy of each major progression item of the pool;
``plentiful``: two of them, plus one of each dungeon reward and song. Every copy has
its own actor (``Item_Trap_<code>``, ``<code>2`` for a second copy), so each freezes
once. The actors, texts and freeze are built by ``patching/fake_traps.py``.
"""
PREFIX = 'Trap: '
ACTOR_PREFIX = 'Item_Trap_'
# Saved Bool set once a trap has frozen Link (each trap freezes once).
SPRUNG_PREFIX = 'RandoTrap.'
# Sensor actor spawned around Link by the trap's hook (clone of the Sun's Song sensor
# carrying the vanilla ice-trap chest attack).
SENSOR_ACTOR = 'RandoIceTrapSensor'

# AP item -> (actor code, item actor lending its model, pose and name). Major items the
# logic needs; keys and souls are left out.
TRAPPED = {
    'Progressive Hookshot': ('Hookshot', 'Item_Hookshot'),
    'Bow': ('Bow', 'Item_Range_Bow'),
    'Slingshot': ('Slingshot', 'Item_Range_SlingShot'),
    'Boomerang': ('Boomerang', 'Item_Boomerang'),
    'Bomb Bag': ('BombBag', 'Item_BombBag_Small'),
    'Megaton Hammer': ('Hammer', 'Item_Hammer'),
    'Iron Boots': ('IronBoots', 'Item_HeavyBoot'),
    'Hover Boots': ('HoverBoots', 'Item_HoverBoot'),
    'Progressive Strength Upgrade': ('Strength', 'Item_Gauntlet_Goron'),
    'Progressive Scale': ('Scale', 'Item_Scale_Silver'),
    'Lens of Truth': ('Lens', 'Item_GlassTruth'),
    'Magic Meter': ('Magic', 'Item_FairyBless_MP'),
    'Fire Arrows': ('FireArrows', 'Item_Arrow_Fire'),
    'Ice Arrows': ('IceArrows', 'Item_Arrow_Ice'),
    'Light Arrows': ('LightArrows', 'Item_Arrow_Light'),
    'Dins Fire': ('DinsFire', 'Item_DinFire'),
    'Farores Wind': ('FaroresWind', 'Item_FaroreWind'),
    'Nayrus Love': ('NayrusLove', 'Item_NayruLove'),
    'Ocarina': ('Ocarina', 'Item_Ocarina_Fairy'),
    'Kokiri Sword': ('KokiriSword', 'Item_Sword_Kokiri'),
    'Mirror Shield': ('MirrorShield', 'Item_Shield_Mirror'),
    'Goron Tunic': ('GoronTunic', 'Obj_Armor_Goron'),
    'Zora Tunic': ('ZoraTunic', 'Obj_Armor_Zora'),
    'Stone of Agony': ('Agony', 'Item_AgonyStone'),
}
# ``plentiful`` only: dungeon rewards and songs (their models come from their pouch actors).
EXTRA_TRAPPED = {
    'Kokiri Emerald': ('KokiriEmerald', 'Item_Stone_Forest'),
    'Goron Ruby': ('GoronRuby', 'Item_Stone_Fire'),
    'Zora Sapphire': ('ZoraSapphire', 'Item_Stone_Water'),
    'Forest Medallion': ('ForestMedallion', 'Item_Medal_Forest'),
    'Fire Medallion': ('FireMedallion', 'Item_Medal_Fire'),
    'Water Medallion': ('WaterMedallion', 'Item_Medal_Water'),
    'Shadow Medallion': ('ShadowMedallion', 'Item_Medal_Shadow'),
    'Spirit Medallion': ('SpiritMedallion', 'Item_Medal_Spirit'),
    'Light Medallion': ('LightMedallion', 'Item_Medal_Light'),
    'Zeldas Lullaby': ('Lullaby', 'Item_Melody_ZeldaLullaby'),
    'Eponas Song': ('EponaSong', 'Item_Melody_EponaSong'),
    'Sarias Song': ('SariaSong', 'Item_Melody_SariaSong'),
    'Suns Song': ('SunSong', 'Item_Melody_SunSong'),
    'Song of Time': ('TimeSong', 'Item_Melody_TimeSong'),
    'Song of Storms': ('StormSong', 'Item_Melody_StormSong'),
    'Minuet of Forest': ('Minuet', 'Item_Melody_ForestMinuet'),
    'Bolero of Fire': ('Bolero', 'Item_Melody_FireBolero'),
    'Serenade of Water': ('Serenade', 'Item_Melody_WaterSerenade'),
    'Requiem of Spirit': ('Requiem', 'Item_Melody_SpiritRequiem'),
    'Nocturne of Shadow': ('Nocturne', 'Item_Melody_ShadowNocturne'),
    'Prelude of Light': ('Prelude', 'Item_Melody_LightPrelude'),
}
ALL_TRAPPED = {**TRAPPED, **EXTRA_TRAPPED}
# Option ``fake_item_traps`` -> copies of each major item; the extras come with ``plentiful``.
LEVELS = {'none': 0, 'some': 1, 'plentiful': 2}
COPY_MARK = ' #'


def trap_item(item, copy=1):
    """Planner name of fake copy number ``copy`` of ``item``."""
    if item not in ALL_TRAPPED or copy not in (1, 2) or (copy == 2 and item not in TRAPPED):
        raise ValueError(f'No trap for: {item} (copy {copy})')
    return PREFIX + item + ('' if copy == 1 else f'{COPY_MARK}{copy}')


def is_trap_item(item):
    return isinstance(item, str) and item.startswith(PREFIX)


def _split(trap):
    """(imitated item, copy number) of a planner trap name."""
    name = trap[len(PREFIX):] if is_trap_item(trap) else None
    copy = 1
    if name and name[-3:-1] == COPY_MARK and name[-1].isdigit():
        name, copy = name[:-3], int(name[-1])
    if name not in ALL_TRAPPED or trap != trap_item(name, copy):
        raise ValueError('Not a trap: ' + str(trap))
    return name, copy


def trapped_item(trap):
    """The item a trap imitates."""
    return _split(trap)[0]


def trap_actor(trap):
    item, copy = _split(trap)
    return ACTOR_PREFIX + ALL_TRAPPED[item][0] + ('' if copy == 1 else str(copy))


CODE_TRAP = {trap_actor(trap)[len(ACTOR_PREFIX):]: trap
             for trap in [trap_item(i) for i in ALL_TRAPPED] + [trap_item(i, 2) for i in TRAPPED]}


def is_trap_actor(actor):
    return isinstance(actor, str) and actor.startswith(ACTOR_PREFIX) and actor[len(ACTOR_PREFIX):] in CODE_TRAP


def actor_trap(actor):
    """Planner name of a trap actor."""
    if not is_trap_actor(actor):
        raise ValueError('Not a trap actor: ' + actor)
    return CODE_TRAP[actor[len(ACTOR_PREFIX):]]


def model_actor(trap):
    """Native item actor lending the trap its model, pose and name."""
    return ALL_TRAPPED[trapped_item(trap)][1]


def planned_traps(pool, level):
    """Traps of option value ``level`` for ``pool``, most important first.

    Major items need a real copy in the pool; dungeon rewards and songs do not (they
    may stay vanilla)."""
    copies = LEVELS[level]
    majors = [i for i in TRAPPED if i in pool]
    traps = [trap_item(i) for i in majors] if copies else []
    if copies >= 2:
        traps += [trap_item(i) for i in EXTRA_TRAPPED] + [trap_item(i, 2) for i in majors]
    return traps


def sprung_flag(actor):
    return SPRUNG_PREFIX + actor[len(ACTOR_PREFIX):]
