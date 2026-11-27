"""Keep the normal bow distinct from elemental arrows in the item menu.

Vanilla's normal bow presentation inherits IceArrow's assignable parameter.
Point it at the game's own bow parameter (``Weapon_Range_Bow``, the one the bow and
normal arrows use) so loading this pack cannot overwrite the real ice arrow. A file
name of our own inside the pack made the game crash on opening the inventory with
the bow, even with a resource table entry: only native resources are referenced.
Preserve native adult selection of elemental arrows: disabling their standalone
menu entries also blocks selection with a bow.
"""
from oot_rando.formats import byml_codec as byml
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.soul_adapter import RSDB_FILES, murmur3

PACK = 'Pack/Actor/Pouch_Range_BowAndArrow_Normal.pack.zs'
TABLE = RSDB_FILES['PouchActorInfo']
UI = 'UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml'
ACTOR = 'Pouch_Range_BowAndArrow_Normal'
PARAM = 'GameParameter/AssginableItemParam/Weapon_Range_Bow.game__actor__AssginableItemParam.bgyml'
OLD_PARAM = 'GameParameter/AssginableItemParam/Rando_NormalBow.game__actor__AssginableItemParam.bgyml'
SOURCE_PARAM = 'GameParameter/AssginableItemParam/Item_Arrow_Ice.game__actor__AssginableItemParam.bgyml'
GAME_TABLE = 'GameParameter/GameParameterTable/Pouch_Range_Bow.engine__actor__GameParameterTable.bgyml'
ELEMENTS = ('Fire', 'Ice', 'Light')


def bow_param(ice_param):
    """The native bow parameter: the ice arrow one with the Bow item (same fields)."""
    param = byml.load(ice_param)
    param['root']['AssignableItem'] = byml.U32(murmur3('Bow'))
    return byml.dump(param)


def patch_pack(raw):
    files = dict(sarc(raw))
    doc = byml.load(files[GAME_TABLE])
    doc['root']['Components']['AssignableItemParam'] = '?' + PARAM
    files[GAME_TABLE] = byml.dump(doc)
    files.pop(OLD_PARAM, None)
    files[PARAM] = bow_param(files[SOURCE_PARAM])
    return byml.build_sarc(files)


def patch_table(raw):
    doc = byml.load(raw)
    row = next(r for r in doc['root'] if r['__RowId'] == ACTOR)
    if row.get('AssignableItem') not in ('IceArrow', 'Bow'):
        raise ValueError('Unexpected normal bow assignable item.')
    row['AssignableItem'] = 'Bow'
    return byml.dump(doc)


def patch_ui(raw):
    """Keep native selection enabled, also repairing UI data from the old patch."""
    doc = byml.load(raw)
    found = set()
    for slot in doc['root']['ItemArray']:
        for row in slot['Actor']:
            for element in ELEMENTS:
                if row['ActorShort'] == 'Item_Arrow_' + element:
                    row['IsUsableAdult'] = True
                    found.add(element)
    if found != set(ELEMENTS):
        raise ValueError('Missing standalone elemental arrow menu entry.')
    return byml.dump(doc)


def resource_fixes():
    return ((PACK, patch_pack), (TABLE, patch_table), (UI, patch_ui))
