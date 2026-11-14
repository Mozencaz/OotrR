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
Their behaviour is experimental until an in-game pilot confirms it.
"""
import copy

WORLD_PREFIX = 'Obj_Rando_'
SHOP_PREFIX = 'Shop_Rando_'
# Skulltula drop of a native world pickup; keeps the name within MAX_ACTOR_NAME
# (naming of REALAZK pickup_pack/kit.rs, MIT, ae9e4063).
KIT_SUFFIX = '_GS'
WORLD_TEMPLATE = 'Obj_Token_Gold'
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


def _kit_native(actor):
    """Native world pickup of a ``<native>_GS`` skulltula drop, else None."""
    native = actor.removesuffix(KIT_SUFFIX)
    return native if native != actor and native in WORLD_CANONICAL and native != WORLD_TEMPLATE else None


def is_world_derived(actor):
    return actor.startswith(WORLD_PREFIX) or _kit_native(actor) is not None


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


def can_take(canonical, form, ap=()):
    """Whether an item can be given by a location of ``form`` (statically).

    ``ap``: AP locations of the location (only needed for the ocarinas)."""
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
    for prefix in (WORLD_PREFIX, SHOP_PREFIX):
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


def _merge_game_parameters(derived, source, source_components, files, components, codec):
    """Give the derived actor the game parameters of the canonical item.

    The item's ``GameParameterTable`` carries what the get applies to the save:
    ``ExpansionMaxNumActor`` (bag/quiver/wallet capacity), ``ExpansionAbilityActor``
    (strength, magic…), ``PlayerEquipmentActor``, ``AssignableItemParam``… Without
    it a derived bomb bag is obtained with a capacity of 0 bombs. The template keeps
    its own pickup parameters (drop bounce, physics, menu) when both define a key.
    """
    source_table = _table_components(source, source_components.get('GameParameterTableRef'), codec)
    template_ref = components.get('GameParameterTableRef')
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
    template_name = WORLD_TEMPLATE if kind == 'world' else SHOP_TEMPLATE
    template = read_pack(template_name)
    source = read_pack(canonical)
    if template is None or source is None:
        raise ValueError('Model or object missing for ' + derived)
    source_components = resolve_components(source, canonical, codec)
    template_param = f'Actor/{template_name}.engine__actor__ActorParam.bgyml'
    files = {k: v for k, v in template.items() if k != template_param}
    document = codec.load(template[template_param])
    components = document['root'].setdefault('Components', {})
    # Model, animations, name and animation states of the item; behaviour
    # (AI, physics, pickup, ASInfo autoplay) of the template.
    for key in ('ModelInfoRef', 'AnimationRef', 'ActorNameRef', 'ASRef'):
        if key in source_components:
            components[key] = source_components[key]
            _copy_ref(source, source_components[key], files, codec)
    if kind == 'world':
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
    _merge_game_parameters(derived, source, source_components, files, components, codec)
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
        template = WORLD_TEMPLATE if is_world_derived(derived) else SHOP_TEMPLATE
        for name in RSDB_TABLES:
            rows = by_id[name]
            if derived in rows:
                raise ValueError(f'Row {name} already present: {derived}')
            if name == 'PouchActorInfo':
                base = rows.get(canonical) or rows.get(template)
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
                for key in MODEL_KEYS:
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
