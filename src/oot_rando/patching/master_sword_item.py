"""Experimental Master Sword get actor, using the native sword-get contract.

The weapon itself is not a get-demo actor. Keep Kokiri's event-object ancestry,
common item AS and get-demo ASInfo, but grant the native Master Sword pouch
identity. Adult-only equipment mapping avoids replacing a child's Kokiri Sword.
Static pack checks cannot establish engine behaviour when received as a child.
"""
import copy

from oot_rando.formats import byml_codec as codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import copy_ref, pack_path, resolve_components

MASTER_SWORD_ACTOR = 'Item_Rando_MasterSword'
WEAPON = 'Weapon_Sword_Master'
TEMPLATE = 'Item_Sword_Kokiri'
PACK = f'Pack/Actor/{MASTER_SWORD_ACTOR}.pack.zs'
TEMPLATE_PACK = f'Pack/Actor/{TEMPLATE}.pack.zs'
RSDB_FILES = {name: f'RSDB/{name}.Product.111.rstbl.byml.zs'
              for name in ('ActorInfo', 'GameActorInfo', 'PouchActorInfo')}
ANIMATIONS = [{'ModelProjectName': 'Item_Common_Animation'}]

# Adult pedestal prompt. Its client param checks only adulthood and position, and
# Market_Adult_Prefab_89da gates it on AllSage (story_fixes): yet without the Master
# Sword owned no prompt shows (20/11), so the ``PutIn`` verb is refused outside the
# data. The child's ``PullOut`` verb works without owning the sword: the adult client
# now sends it. The attention still fires the same put-in event. Not validated in game.
PEDESTAL_PACK = 'Pack/Actor/Obj_TimeTemple_MasterSword_A_01.pack.zs'
PUT_IN_CLIENT = 'Attention/ClientParam/TimeTemple_MasterSwordAttention_PutIn.game__attention__ClientParam.bgyml'
PUT_IN = 2411603822     # murmur3('PutIn')
PULL_OUT = 1302650721   # murmur3('PullOut')


def _resource(kind, suffix):
    return f'{kind}/{MASTER_SWORD_ACTOR}.{suffix}.bgyml'


def _document(root):
    return codec.dump({'endian': '<', 'version': 7, 'root': root})


def build_pack(read_pack):
    """Return raw SARC bytes; ``read_pack(actor)`` returns a member→bytes dict."""
    template, source = read_pack(TEMPLATE), read_pack(WEAPON)
    components = resolve_components(template, TEMPLATE, codec)
    native = resolve_components(source, WEAPON, codec)
    old_actor = f'Actor/{TEMPLATE}.engine__actor__ActorParam.bgyml'
    document = codec.load(template[old_actor])
    if (document['root'].get('$parent') !=
            'Work/Actor/Item_EventObject_Base.engine__actor__ActorParam.gyml'
            or 'Item_GetDemo' not in components.get('ASInfoRef', '')
            or components.get('ASRef') != '?AS/Item_Common.root.asb'):
        raise ValueError('Unexpected native sword get template.')
    files = {path: raw for path, raw in template.items() if path != old_actor}
    edited = document['root']['Components']
    for key in ('ModelInfoRef', 'ActorNameRef'):
        edited[key] = native[key]
        copy_ref(source, native[key], files, codec)

    animation = _resource('Component/AnimationParam', 'engine__component__AnimationParam')
    # The Master model has no weapon animation resource. Biggoron/Kokiri's
    # model-specific resources and weapon AS are inappropriate for this model.
    files[animation] = _document({'AnimationResources': copy.deepcopy(ANIMATIONS)})
    edited['AnimationRef'] = '?' + animation
    pouch = _resource('Component/PouchContentParam', 'game__component__PouchContentParam')
    parent = pack_path(components['PouchContentRef'])
    copy_ref(template, components['PouchContentRef'], files, codec)
    files[pouch] = _document({
        '$parent': 'Work/' + parent[:-len('.bgyml')] + '.gyml',
        'PouchActor': f'Work/Actor/{WEAPON}.engine__actor__ActorParam.gyml',
        'GetDemoOffsetPos': {'X': 0.0, 'Y': 0.4, 'Z': 0.0}})
    edited['PouchContentRef'] = '?' + pouch
    equipment = _resource('GameParameter/PlayerEquipmentActor', 'game__actor__PlayerEquipmentActor')
    files[equipment] = _document({'Adult': f'Work/Actor/{WEAPON}.engine__actor__ActorParam.gyml'})
    table = _resource('GameParameter/GameParameterTable', 'engine__actor__GameParameterTable')
    files[table] = _document({'Components': {'PlayerEquipmentActor': '?' + equipment}})
    edited['GameParameterTableRef'] = '?' + table
    files[f'Actor/{MASTER_SWORD_ACTOR}.engine__actor__ActorParam.bgyml'] = codec.dump(document)
    return codec.build_sarc(files)


def add_rows(table, rows):
    """Append one get actor row while preserving native weapon and template rows."""
    by_id = {row['__RowId']: row for row in rows}
    if MASTER_SWORD_ACTOR in by_id:
        raise ValueError('Master Sword get actor already present: ' + table)
    row = copy.deepcopy(by_id[TEMPLATE])
    row['__RowId'] = MASTER_SWORD_ACTOR
    if table == 'ActorInfo':
        source = by_id[WEAPON]
        row['ActorName'] = WEAPON
        for key in ('FmdbName', 'ModelProjectName', 'ModelAabbMax', 'ModelAabbMin'):
            row[key] = copy.deepcopy(source[key])
        row['AnimationResources'] = copy.deepcopy(ANIMATIONS)
        for key in ('InstanceHeapSize', 'PreActorRenderInfoHeapSize'):
            row[key] = max(row[key], source[key])
    elif table == 'PouchActorInfo':
        row.pop('ChildEquipment', None)
        row['AdultEquipment'] = f'Work/Actor/{WEAPON}.engine__actor__ActorParam.gyml'
    elif table != 'GameActorInfo':
        raise ValueError('Unknown Master Sword get table: ' + table)
    rows.append(row)
    rows.sort(key=lambda entry: entry['__RowId'])


def pedestal_put_in_without_sword(raw_pack):
    """Raw pedestal pack whose adult put-in prompt uses the ``PullOut`` verb."""
    files = sarc(raw_pack)
    document = codec.load(files[PUT_IN_CLIENT])
    root = document['root']
    adult = root['CheckList'][0].get('CheckGameData', {})
    if (root.get('ActionType') != PUT_IN
            or (adult.get('GameDataPath'), adult.get('IsReverseCondition')) != ('Sequence_IsChildhood', True)):
        raise ValueError('Unexpected Master Sword put-in prompt (already patched?).')
    root['ActionType'] = PULL_OUT
    files[PUT_IN_CLIENT] = codec.dump(document)
    return codec.build_sarc(files)


def build_files(read_raw):
    """Return ``(modified, new)`` raw resources, like other item adapters.

    ``read_raw(path)`` reads decompressed game bytes. ``new`` values are
    ``(raw_bytes, compression_template_path)``. All three RSDB rows are included;
    no new flags or messages are needed because ActorName is the native weapon.
    """
    def read_pack(actor):
        return sarc(read_raw(f'Pack/Actor/{actor}.pack.zs'))

    new = {PACK: (build_pack(read_pack), TEMPLATE_PACK)}
    modified = {PEDESTAL_PACK: pedestal_put_in_without_sword(read_raw(PEDESTAL_PACK))}
    for table, path in RSDB_FILES.items():
        document = codec.load(read_raw(path))
        add_rows(table, document['root'])
        modified[path] = codec.dump(document)
    return modified, new
