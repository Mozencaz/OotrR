"""Item forms of the remake and derived actors for cross-category placement.

The remake gives an item through three kinds of actors:

* ``chest``/``event`` form: the canonical "get demo" actor (``Item_*``,
  ``TBox_*`` or ``Obj_Heart_Piece``) used by chests (``Drop__DropActor``) and by
  event parameters (``ActorName``, ``ReveiveItem``…);
* ``world`` form: a pickup that exists in the world (``Obj_*``), used by
  freestanding items and by drops (gold skulltulas, pots, bushes…);
* ``shop`` form: a shelf actor (``Shop_*``) bought in a shop.

When the game has no native actor of the required form, a derived actor is
fabricated from a native template (``Obj_Rando_<canonical>`` from the gold
token pickup, ``Shop_Rando_<canonical>`` from a shop bundle) with the model and
pouch content of the canonical item. A gold skulltula drop is always built on
the token, as ``<native pickup>_GS`` when the item has a native world pickup.
Drops of pots, trees and other environment sources are built on a native
falling pickup instead (``Obj_RandoDrop_<canonical>``, see ``DROP_TEMPLATE``).
Their behaviour is experimental until an in-game pilot confirms it.
"""
import copy

WORLD_PREFIX = 'Obj_Rando_'
SHOP_PREFIX = 'Shop_Rando_'
# Skulltula drop of a native world pickup; keeps the name within MAX_ACTOR_NAME
# (naming of REALAZK pickup_pack/kit.rs, MIT, ae9e4063).
KIT_SUFFIX = '_GS'
WORLD_TEMPLATE = 'Obj_Token_Gold'
# Environment drops (pots, trees, rocks…). The token's AI keeps it standing where
# it spawns (ExecuteKeepStandingPosture), so a drop built on it hangs in the air.
# Native drops share Obj_Item_Base's DropItem AI (ExecuteDropBound: fall, bounce,
# land), DropItem physics, blackboard and death; the deku nut is one of them with
# the generic DropItem controller set and the token's own get event performer.
DROP_PREFIX = 'Obj_RandoDrop_'
DROP_TEMPLATE = 'Obj_DekuNut'
# Template components that only describe the deku nut itself (its UI icon capture).
DROP_TEMPLATE_DROPPED = ('CaptureRef',)
SHOP_TEMPLATE = 'Shop_ArrowBundle_01'
SHOP_PRICE = 10  # affordable without any wallet upgrade: the logic ignores prices
LINK_KEYS = ('ELinkRef', 'SLinkRef')   # effect / sound users of the actor (not XLink: shared ActorBasic)
RSDB_TABLES = ('ActorInfo', 'GameActorInfo', 'PouchActorInfo')
MODEL_KEYS = ('FmdbName', 'ModelProjectName', 'ModelAabbMax', 'ModelAabbMin', 'ModelVariationFmabName',
              'AnimationResources', 'ASInfoAutoPlayMaterials', 'ELinkUserName')

# Canonical actor → native world pickup.
NATIVE_WORLD = {
    'TBox_Rupee_Green': 'Obj_Rupee_Green', 'TBox_Rupee_Blue': 'Obj_Rupee_Blue', 'TBox_Rupee_Red': 'Obj_Rupee_Red',
    'TBox_Rupee_Purple': 'Obj_Rupee_Purple', 'TBox_Rupee_Gold': 'Obj_Rupee_Gold',
    'Obj_Heart_Piece': 'Obj_Heart_Piece', 'Obj_Heart_Container': 'Obj_Heart_Container', 'Obj_Heart': 'Obj_Heart', 'Item_Token_Gold': 'Obj_Token_Gold',
    'TBox_Shield_Deku': 'Obj_Shield_Deku', 'TBox_Shield_Hylian': 'Obj_Shield_Hylian',
    'Item_BombBundle_Small': 'Obj_Bomb', 'Item_DekuStickBundle_Small': 'Obj_DekuStick',
    'TBox_DekuNutBundle': 'Obj_DekuNut', 'TBox_DekuSeedBundle': 'Obj_DekuSeed',
    'TBox_ArrowBundle_Small': 'Obj_ArrowBundle_Small', 'TBox_ArrowBundle_Medium': 'Obj_ArrowBundle_Medium',
    'TBox_ArrowBundle_Large': 'Obj_ArrowBundle_Large', 'Item_BombchuBundle_Small': 'Obj_Bombchu',
    'Tbox_MagicJar_Large': 'Obj_MagicJar_Large', 'Item_ScrubBusinessSeed': 'Obj_ScrubBusinessSeed',
}
# Native world pickups found in maps or drop fields → canonical actor.
WORLD_CANONICAL = {world: canonical for canonical, world in NATIVE_WORLD.items()}
# Pouch settings of a derived world pickup. The token's AI saves the gold
# skulltula that dropped it (its Bool64bitKey rows) only when the get event
# ends, so the event must play on every pickup, even at full capacity.
WORLD_POUCH_FLAGS = {'PlayGetEventManyTimes': True, 'IsPlayGetEventPouchMax': True}


# Height (metres) added to a ground spot whose new pickup has its origin at its
# centre: the gold token stands where it spawns (ExecuteKeepStandingPosture) and its
# model reaches 0.14 below its origin (ActorInfo ModelAabbMin.Y), where the ground
# pickups start at 0, so on the spot of a heart piece or rupee it was half sunk.
GROUND_LIFT = {WORLD_TEMPLATE: 0.25}
# Pickups built on the token (Obj_Rando_*) stand the same way with the item's model:
# the Hookshot reaches 0.15 below its origin, the Light Arrow 0.38: sunk into the
# ground, some could not be picked up (Discord #issues, 17/11). Their spot is raised by how far the model hangs below its origin,
# plus LIFT_MARGIN. Lowest point (ActorInfo ModelAabbMin.Y) of the item models
# reaching more than 0.02 below their origin; any other starts at the ground.
LIFT_MARGIN = 0.05
MODEL_BOTTOM = {
    'Item_AgonyStone': -0.046, 'Item_Arrow_Fire': -0.235, 'Item_Arrow_Ice': -0.228, 'Item_Arrow_Light': -0.377,
    'Item_Arrow_Normal': -0.043, 'Item_Bomb': -0.120, 'Item_Boomerang': -0.031, 'Item_Bottle': -0.088,
    'Item_Bottle_BigPoe': -0.088, 'Item_Bottle_BlueFire': -0.088, 'Item_Bottle_BluePotion': -0.088,
    'Item_Bottle_Bug': -0.088, 'Item_Bottle_Fairy': -0.088, 'Item_Bottle_Fish': -0.088,
    'Item_Bottle_GreenPotion': -0.088, 'Item_Bottle_HalfMilk': -0.088, 'Item_Bottle_Letter': -0.088,
    'Item_Bottle_Milk': -0.088, 'Item_Bottle_Poe': -0.088, 'Item_Bottle_RedPotion': -0.088,
    'Item_BrokenSword': -0.067, 'Item_BulletBag_Large': -0.099, 'Item_BulletBag_Medium': -0.042,
    'Item_BulletBag_Small': -0.022, 'Item_ClaimCheck': -0.225, 'Item_DekuSeed': -0.130, 'Item_DekuStick': -0.382,
    'Item_DekuStickBundle_Small': -0.382, 'Item_DinFire': -0.333, 'Item_Dungeon_Compass': -0.033,
    'Item_Dungeon_Map': -0.213, 'Item_EyeDrop': -0.109, 'Item_EyeballFrog': -0.112,
    'Item_FairyBless_DefenseDouble': -0.285, 'Item_FairyBless_MP': -0.285, 'Item_FairyBless_MPDouble': -0.285,
    'Item_FaroreWind': -0.333, 'Item_FishingRod': -0.187, 'Item_Gauntlet_Goron': -0.034, 'Item_Hammer': -0.276,
    'Item_Hookshot': -0.152, 'Item_Longshot': -0.152, 'Item_MagicBean': -0.108, 'Item_Mask_Bunny': -0.056,
    'Item_Mask_Gerudo': -0.091, 'Item_Mask_Goron': -0.084, 'Item_Mask_Keaton': -0.087, 'Item_Mask_Skull': -0.074,
    'Item_Mask_Spooky': -0.099, 'Item_Mask_Truth': -0.080, 'Item_Mask_Zora': -0.113, 'Item_Medal_Fire': -0.183,
    'Item_Medal_Forest': -0.183, 'Item_Medal_Light': -0.183, 'Item_Medal_Shadow': -0.183,
    'Item_Medal_Spirit': -0.183, 'Item_Medal_Water': -0.181, 'Item_NayruLove': -0.333,
    'Item_Ocarina_Fairy': -0.046, 'Item_Ocarina_Time': -0.048, 'Item_OddMushroom': -0.129,
    'Item_PoacherSaw': -0.031, 'Item_Prescription': -0.210, 'Item_Quiver_Large': -0.064, 'Item_Range_Bow': -0.056,
    'Item_Range_SlingShot': -0.090, 'Item_Shield_Mirror': -0.057, 'Item_StickBag_Large': -0.037,
    'Item_Sword_Biggoron': -0.067, 'Item_Sword_BrokenGiant': -0.067, 'Item_Sword_Giant': -0.262,
    'Item_Sword_Kokiri': -0.040, 'Item_Token_Gerudo': -0.268, 'Item_Wallet_Medium': -0.037,
    'TBox_ArrowBundle_Large': -0.164, 'TBox_ArrowBundle_Medium': -0.093, 'TBox_ArrowBundle_Small': -0.102,
    'TBox_DekuSeedBundle': -0.130, 'TBox_Shield_Deku': -0.036, 'TBox_Shield_Hylian': -0.078,
}
# Rando items drawn with a game model (their ActorInfo row copies its model box):
# progressive tokens with their family's first level (progressive.FAMILIES), souls
# with the Poe spirit, Archipelago items with a Fire Medallion copy, key rings,
# boss keys, maps and compasses with the native dungeon items.
MODEL_PREFIXES = (('Item_Soul_', 'Obj_Spirit_Poe'), ('Item_AP_', 'Item_Medal_Fire'),
                  ('Item_KeyRing_', 'Item_Dungeon_SmallKey'), ('Item_BossKey_', 'Item_Dungeon_BossKey'),
                  ('Item_Map_', 'Item_Dungeon_Map'), ('Item_Compass_', 'Item_Dungeon_Compass'))
# Pouch-named models of the same mesh as the item's.
SAME_MODEL = {'Weapon_Range_SlingShot': 'Item_Range_SlingShot', 'Weapon_Range_Bow': 'Item_Range_Bow'}


def model_of(canonical):
    """Game item whose model (and model box) ``canonical`` is drawn with."""
    from oot_rando.patching.progressive import FAMILIES, token_family
    family = token_family(canonical)
    if family is not None:
        model = FAMILIES[family][3]
        return SAME_MODEL.get(model, model)
    for prefix, model in MODEL_PREFIXES:
        if canonical.startswith(prefix):
            return model
    return canonical


def ground_lift(before, after):
    """Height to add to a freestanding spot whose ``before`` pickup becomes ``after``."""
    if before == after:
        return 0.0
    if after in GROUND_LIFT:
        return GROUND_LIFT[after]
    if not after.startswith(WORLD_PREFIX):
        return 0.0
    bottom = MODEL_BOTTOM.get(model_of(canonical_of(after)))
    # Scaled about its origin (world_scale), the model reaches lower still.
    return 0.0 if bottom is None else round(-bottom * world_scale(after) + LIFT_MARGIN, 3)


# Some key items placed in the world on the gold token are much smaller than it
# (0.39 m): the Goron Bracelet (also the Strength token's model) is 0.11 m, the Stone of Agony 0.08 m, hard to see
# (Discord 17/11). Their spot gets a map ``Scale`` (a runtime actor field: scaled
# flags, the market drawbridge...) bringing them up to WORLD_SIZE, at most
# MAX_WORLD_SCALE times. Largest extent (metres, ActorInfo ModelAabbMax - Min) of
# the item models below that size whose box holds their origin.
WORLD_SIZE = 0.35
MAX_WORLD_SCALE = 3.0
SMALL_MODELS = {
    'Item_AgonyStone': 0.078, 'Item_Gauntlet_Goron': 0.108, 'Item_Dungeon_Compass': 0.170,
    'Item_Ocarina_Fairy': 0.235, 'Item_Ocarina_Time': 0.245, 'Item_Stone_Water': 0.246, 'Item_Bottle': 0.259,
    'Item_Bottle_Letter': 0.259, 'Item_Bottle_Milk': 0.260, 'Item_Stone_Fire': 0.259, 'Item_Stone_Forest': 0.261,
    'Item_BombBag_Small': 0.261, 'Item_ZeldaLetter': 0.267, 'Item_Range_SlingShot': 0.302,
}


def world_scale(actor):
    """Uniform map scale of a spot holding ``actor`` (1.0: none)."""
    if not actor.startswith(WORLD_PREFIX):
        return 1.0
    extent = SMALL_MODELS.get(model_of(canonical_of(actor)))
    return 1.0 if extent is None else round(min(MAX_WORLD_SCALE, WORLD_SIZE / extent), 2)


def lifted(y, height):
    """``y + height`` rounded as the map's 32-bit float stores it."""
    import struct
    return struct.unpack('<f', struct.pack('<f', y + height))[0]


# A key item (``Item_*``: Hookshot, boots, progressive tokens...) has no pickup sound
# or effect of its own (no SLink user; the Forest Medallion template of the tokens only
# has an effect bound to its own model). Placed in the world on the gold token, it
# shone with nothing and made no sound: a progressive Slingshot under Zora's River
# water was only found with debug flight (Discord 17/11). Such a pickup now keeps the
# token's golden aura and hum; an item with its own pickup sound keeps its own links.
def keeps_token_links(template, source_has_sound):
    """A derived world pickup keeps the gold token's ELink/SLink (glow and hum)."""
    return template == WORLD_TEMPLATE and not source_has_sound


def _kit_native(actor):
    """Native world pickup of a ``<native>_GS`` skulltula drop, else None."""
    native = actor.removesuffix(KIT_SUFFIX)
    return native if native != actor and native in WORLD_CANONICAL and native != WORLD_TEMPLATE else None


def is_world_derived(actor):
    return actor.startswith((WORLD_PREFIX, DROP_PREFIX)) or _kit_native(actor) is not None


def world_template(derived):
    """Native pickup whose behaviour a derived world actor takes."""
    return DROP_TEMPLATE if derived.startswith(DROP_PREFIX) else WORLD_TEMPLATE


def is_derived(actor):
    return actor.startswith(SHOP_PREFIX) or is_world_derived(actor)


def form_actor(canonical, form, skulltula_drop=False):
    """Actor giving ``canonical`` through a location of the given form.

    ``skulltula_drop``: a gold skulltula drops the pickup. Only the token's AI
    saves the skulltula when its drop is collected; the native pickups (rupees,
    ammo, hearts…) never do, so the skulltula and its check came back. Every
    other item is dropped by a derived pickup built on the token, which is also
    collected on contact where Link hangs on vines or walls.
    """
    if form in ('chest', 'event'):
        return canonical
    if form == 'world':
        native = NATIVE_WORLD.get(canonical)
        if native == WORLD_TEMPLATE or (native and not skulltula_drop):
            return native
        if native:
            return native + KIT_SUFFIX
        return WORLD_PREFIX + canonical
    if form == 'shop':
        return canonical if canonical.startswith('Shop_') else SHOP_PREFIX + canonical
    raise ValueError('Forme inconnue : ' + form)


# The ocarinas are the accessory Link plays, not a holdable reward: their packs have
# no Item_EventObject_Base parent, ASInfo/Item_GetDemo or AnimationParam, so the
# item-get pose of chests, NPC hand-overs and shops crashes the game (issue #15:
# rolling Goron; Discord 14/11: Dodongo's Cavern compass chest; AP test 13/11).
# Vanilla only hands them out in cutscenes, through the get display without pose
# (Dm_Kokiri_0155, Dm_MelodyGet_Time): those two sites, and world pickups (own
# Obj_Rando_ get event, validated 11/11), are the only places they may go.
OCARINAS = ('Item_Ocarina_Fairy', 'Item_Ocarina_Time')
OCARINA_SITES = ('LW Gift from Saria', 'HF Ocarina of Time Item')


# The native boss key is credited only by the big chest sequence (Dm_SY_Treasurebox:
# EventGetDungeonBossKey, like the map and compass). The small chest sequence only
# knows the small key: anywhere else the boss key would be shown and lost, and the
# boss door would stay shut. Every remake boss key stands in a big chest. Maps and
# compasses have the same limit but are never needed to finish: they stay free, as
# keeping them in big chests too leaves too few reachable chests early in a dungeon.
BIG_CHEST_ONLY = ('Item_Dungeon_BossKey',)
BIG_CHEST_ACTORS = ('Obj_TBox_A_02', 'Obj_TBox_A_03')


def can_take(canonical, form, ap=(), actor=''):
    """Whether an item can be given by a location of ``form`` (statically).

    ``ap``: AP locations of the location (only needed for the ocarinas);
    ``actor``: the chest actor (only needed for the dungeon items)."""
    if canonical in BIG_CHEST_ONLY:
        return form == 'chest' and str(actor).startswith(BIG_CHEST_ACTORS)
    if canonical in OCARINAS:
        return form == 'world' or (form == 'event' and any(l in OCARINA_SITES for l in ap))
    if canonical.startswith('Shop_'):
        return form == 'shop'           # shop-only purchases (bottle contents, refills…)
    if canonical.startswith('Item_AP_'):
        # Another player's item (Archipelago medallion): forms proven for new pouch actors.
        return form in ('chest', 'world')
    if canonical.startswith('Item_Soul_'):
        # The soul flag is written by the soul's own get event: proven for pickups
        # (world) and planned for chests; shop purchases and NPC/cutscene gifts may
        # add the item without that event, leaving the enemies absent forever.
        return form in ('chest', 'world')
    return True


def derived_actors(actors):
    return sorted({a for a in actors if is_derived(a)})


def canonical_of(derived):
    native = _kit_native(derived)
    if native:
        return WORLD_CANONICAL[native]
    for prefix in (WORLD_PREFIX, DROP_PREFIX, SHOP_PREFIX):
        if derived.startswith(prefix):
            return derived[len(prefix):]
    raise ValueError('Not a derived actor: ' + derived)


# ------------------------------------------------------------------ packs
def _pack_path(ref):
    """``?Component/X.bgyml`` or ``Work/Component/X.gyml`` → path inside a pack."""
    if ref.startswith('?'):
        return ref[1:]
    if ref.startswith('Work/') and ref.endswith('.gyml'):
        return ref[len('Work/'):-len('.gyml')] + '.bgyml'
    return None


def _copy_ref(source, ref, files, codec):
    """Copy a pack-local resource and its ``$parent`` chain from ``source``."""
    path = _pack_path(ref) if isinstance(ref, str) else None
    while path and path in source:
        files[path] = source[path]
        if not path.endswith('.bgyml'):
            return
        parent = codec.load(source[path])['root']
        parent = parent.get('$parent') if isinstance(parent, dict) else None
        path = _pack_path(parent) if isinstance(parent, str) else None


def resolve_components(pack, actor, codec):
    """Components of an actor, ``$parent`` chain merged (child wins)."""
    path = f'Actor/{actor}.engine__actor__ActorParam.bgyml'
    chain = []
    while path:
        if path not in pack:
            raise ValueError('Actor parameters not found: ' + path)
        document = codec.load(pack[path])['root']
        chain.append(document)
        parent = document.get('$parent')
        path = _pack_path(parent) if isinstance(parent, str) else None
    components = {}
    for document in reversed(chain):
        components.update(document.get('Components', {}))
    return components


def _table_components(pack, ref, codec):
    """Components of a GameParameterTable, ``$parent`` chain merged (child wins)."""
    chain, path = [], _pack_path(ref) if isinstance(ref, str) else None
    while path and path in pack:
        document = codec.load(pack[path])['root']
        chain.append(document)
        parent = document.get('$parent')
        path = _pack_path(parent) if isinstance(parent, str) else None
    merged = {}
    for document in reversed(chain):
        merged.update(document.get('Components', {}))
    return merged


def _merge_game_parameters(derived, source, source_components, files, components, codec, inherited=None):
    """Give the derived actor the game parameters of the canonical item.

    The item's ``GameParameterTable`` carries what the get applies to the save:
    ``ExpansionMaxNumActor`` (bag/quiver/wallet capacity), ``ExpansionAbilityActor``
    (strength, magic…), ``PlayerEquipmentActor``, ``AssignableItemParam``… Without
    it a derived bomb bag is obtained with a capacity of 0 bombs. The template keeps
    its own pickup parameters (drop bounce, physics, menu) when both define a key.
    """
    source_table = _table_components(source, source_components.get('GameParameterTableRef'), codec)
    # A template may inherit its table from its ``$parent`` (Obj_Item_Base).
    template_ref = components.get('GameParameterTableRef') or (inherited or {}).get('GameParameterTableRef')
    template_path = _pack_path(template_ref) if isinstance(template_ref, str) else None
    if template_path not in files:
        raise ValueError('Model parameter table not found for ' + derived)
    template_table = _table_components(files, template_ref, codec)
    added = {k: v for k, v in source_table.items() if k not in template_table}
    if not added:
        return
    table = codec.load(files[template_path])
    table['root'].setdefault('Components', {}).update(added)
    for ref in added.values():
        _copy_ref(source, ref, files, codec)
    new_table = f'GameParameter/GameParameterTable/{derived}.engine__actor__GameParameterTable.bgyml'
    files[new_table] = codec.dump(table)
    components['GameParameterTableRef'] = '?' + new_table


def build_pack(derived, read_pack, codec):
    """Return the SARC bytes of a derived actor and its template pack path."""
    canonical = canonical_of(derived)
    kind = 'world' if is_world_derived(derived) else 'shop'
    template_name = world_template(derived) if kind == 'world' else SHOP_TEMPLATE
    template = read_pack(template_name)
    source = read_pack(canonical)
    if template is None or source is None:
        raise ValueError('Model or object missing for ' + derived)
    source_components = resolve_components(source, canonical, codec)
    template_param = f'Actor/{template_name}.engine__actor__ActorParam.bgyml'
    files = {k: v for k, v in template.items() if k != template_param}
    document = codec.load(template[template_param])
    components = document['root'].setdefault('Components', {})
    if template_name == DROP_TEMPLATE:
        for key in DROP_TEMPLATE_DROPPED:
            components.pop(key, None)
    # Model, animations, name and animation states of the item; behaviour
    # (AI, physics, pickup, ASInfo autoplay) of the template.
    for key in ('ModelInfoRef', 'AnimationRef', 'ActorNameRef', 'ASRef'):
        if key in source_components:
            components[key] = source_components[key]
            _copy_ref(source, source_components[key], files, codec)
    if kind == 'world' and not keeps_token_links(template_name, 'SLinkRef' in source_components):
        # Effects and sounds: the gold token's ELink user draws its golden
        # token-shaped aura (and SLink its hum) around any model. Use the item's
        # own ones, or none (Obj_Item_Base defines neither).
        for key in LINK_KEYS:
            if key in source_components:
                components[key] = source_components[key]
                _copy_ref(source, source_components[key], files, codec)
            else:
                components.pop(key, None)
    pouch_ref = source_components.get('PouchContentRef')
    if not isinstance(pouch_ref, str) or _pack_path(pouch_ref) not in source:
        raise ValueError('Pouch content not found for ' + canonical)
    _copy_ref(source, pouch_ref, files, codec)
    pouch_path = f'Component/PouchContentParam/{derived}.game__component__PouchContentParam.bgyml'
    pouch = {'$parent': 'Work/' + _pack_path(pouch_ref)[:-len('.bgyml')] + '.gyml',
             'PouchActor': f'Work/Actor/{canonical}.engine__actor__ActorParam.gyml', 'DefaultAutoGet': True}
    if kind == 'world':
        pouch.update(WORLD_POUCH_FLAGS)
    files[pouch_path] = codec.dump({'endian': '<', 'version': 7, 'root': pouch})
    components['PouchContentRef'] = '?' + pouch_path
    _merge_game_parameters(derived, source, source_components, files, components, codec,
                           resolve_components(template, template_name, codec))
    if canonical.startswith('Item_Soul_'):
        if kind != 'world':
            raise ValueError('Soul in a shop not supported: ' + derived)
        # The soul's get event writes its IsGet flag: the pickup runs that clone
        # instead of the template's native event (first-collection technique).
        from oot_rando.patching.soul_adapter import soul_event_ain, soul_event_member
        member = soul_event_member(canonical)
        if member not in source:
            raise ValueError('Soul get event missing: ' + canonical)
        files[member] = source[member]
        event_param = f'Component/EventPerformerParam/{derived}.engine__component__EventPerformerParam.bgyml'
        files[event_param] = codec.dump({'endian': '<', 'version': 7, 'root': {
            '$parent': 'Work/Component/EventPerformerParam/PouchContent_PickUpItem.engine__component__EventPerformerParam.gyml',
            'AlwaysEventMember': True, 'UseEventUniqueAin': True, 'EventUniqueAin': soul_event_ain(canonical)}})
        components['EventPerformerRef'] = '?' + event_param
    if kind == 'shop':
        # Bought once: the world pickup setting (shared resource, not in the pack).
        setting = resolve_components(read_pack(WORLD_TEMPLATE), WORLD_TEMPLATE, codec).get('ActorGameDataSetting')
        if not isinstance(setting, str) or 'NoRespawn' not in setting:
            raise ValueError('NoRespawn setting not found.')
        components['ActorGameDataSetting'] = setting
        price_path = f'GameParameter/PriceParam/{derived}.game__pouchcontent__PriceParam.bgyml'
        files[price_path] = codec.dump({'endian': '<', 'version': 7,
                                        'root': {'BuyingPrice': SHOP_PRICE, 'SellingPrice': 1}})
        table_ref = components.get('GameParameterTableRef')
        table_path = _pack_path(table_ref) if isinstance(table_ref, str) else None
        if table_path not in files:
            raise ValueError('Shop parameter table not found.')
        table = codec.load(files[table_path])
        table['root'].setdefault('Components', {})['PriceParam'] = '?' + price_path
        new_table = f'GameParameter/GameParameterTable/{derived}.engine__actor__GameParameterTable.bgyml'
        files[new_table] = codec.dump(table)
        components['GameParameterTableRef'] = '?' + new_table
    files[f'Actor/{derived}.engine__actor__ActorParam.bgyml'] = codec.dump(document)
    return codec.build_sarc(files), f'Pack/Actor/{template_name}.pack.zs'


def add_rsdb_rows(tables, derived_list):
    """Append RSDB rows of derived actors. ``tables`` maps name → row list (sorted after)."""
    by_id = {name: {row['__RowId']: row for row in rows} for name, rows in tables.items()}
    for derived in derived_list:
        canonical = canonical_of(derived)
        world = is_world_derived(derived)
        template = world_template(derived) if world else SHOP_TEMPLATE
        for name in RSDB_TABLES:
            rows = by_id[name]
            if derived in rows:
                raise ValueError(f'Row {name} already present: {derived}')
            if name == 'PouchActorInfo':
                # Pouch rows describe the item, not the pickup: drops fall back on the token's too.
                base = rows.get(canonical) or rows.get(WORLD_TEMPLATE if world else SHOP_TEMPLATE)
            else:
                base = rows.get(template)
            if base is None:
                raise ValueError(f'Template row {name} missing for {derived}')
            row = copy.deepcopy(base)
            row['__RowId'] = derived
            source = rows.get(canonical)
            if name == 'ActorInfo':
                if source is None:
                    raise ValueError('Ligne ActorInfo absente : ' + canonical)
                row['ActorName'] = source.get('ActorName', canonical)
                keep_links = world and keeps_token_links(template, 'SLinkUserName' in source)
                for key in MODEL_KEYS:
                    if keep_links and key == 'ELinkUserName' and key in base:
                        continue      # the token's glow (keeps_token_links)
                    if key in source:
                        row[key] = copy.deepcopy(source[key])
                    else:
                        row.pop(key, None)
                if 'InstanceHeapSize' in source:
                    row['InstanceHeapSize'] = max(row.get('InstanceHeapSize', 0), source['InstanceHeapSize'])
            elif name == 'GameActorInfo' and source and 'ModelVariationAnims' in source:
                row['ModelVariationAnims'] = copy.deepcopy(source['ModelVariationAnims'])
            elif name == 'PouchActorInfo' and derived.startswith(SHOP_PREFIX):
                row['BuyingPrice'], row['SellingPrice'] = SHOP_PRICE, 1
            tables[name].append(row)
            rows[derived] = row
    for rows in tables.values():
        rows.sort(key=lambda row: row['__RowId'])
    return tables
