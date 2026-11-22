"""Only Magic Meter upgrades may increase magic capacity.

Vanilla spells, elemental arrows and the Lens share the first meter's expansion
parameter. Detach it from their game tables without editing the shared parameter:
the real upgrade still needs it. Keep the flattened pouch database consistent.
"""
from oot_rando.formats import byml_codec as byml
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.soul_adapter import RSDB_FILES

TABLE = RSDB_FILES['PouchActorInfo']
MAGIC_REF = '?GameParameter/ExpansionAbilityActor/Item_FairyBless_MP.game__actor__ExpansionAbilityActor.bgyml'
ITEMS = ('Item_Arrow_Fire', 'Item_Arrow_Ice', 'Item_Arrow_Light',
         'Item_DinFire', 'Item_FaroreWind', 'Item_NayruLove', 'Item_GlassTruth')
GAME_TABLES = tuple(f'GameParameter/GameParameterTable/{actor}.engine__actor__GameParameterTable.bgyml'
                    for actor in ITEMS)
NATIVE_PACKS = tuple(f'Pack/Actor/{actor}.pack.zs' for actor in (
    *ITEMS, 'Armor_Adult_GlassTruth', 'Armor_Child_GlassTruth', 'Armor_GlassTruth',
    'Obj_Arrow_Fire', 'Pouch_Arrow_Fire', 'Pouch_Arrow_Ice', 'Pouch_Arrow_Light',
    'Pouch_DinFire', 'Pouch_FaroreWind', 'Pouch_NayruLove',
    'Pouch_Range_BowAndArrow_Fire', 'Pouch_Range_BowAndArrow_Ice',
    'Pouch_Range_BowAndArrow_Light', 'Pouch_Range_BowAndArrow_Normal'))


def patch_pack(raw):
    """Detach implicit meter upgrades, preserving shared data and other abilities."""
    files = dict(sarc(raw))
    changed = []
    for path in GAME_TABLES:
        if path not in files:
            continue
        doc = byml.load(files[path])
        components = doc['root'].get('Components', {})
        ref = components.get('ExpansionAbilityActor')
        if not ref:
            continue
        if ref != MAGIC_REF:
            raise ValueError('Unexpected magic capacity parameter: ' + path)
        del components['ExpansionAbilityActor']
        files[path] = byml.dump(doc)
        changed.append(path)
    return (byml.build_sarc(files) if changed else raw), changed


def patch_table(raw):
    doc = byml.load(raw)
    for row in doc['root']:
        if (row.get('ExpansionAvility') == 'MPMaxUP'
                and row.get('PouchSpecialDeal') not in ('FairyBlessMP', 'FairyBlessMPDouble')):
            row['ExpansionAvility'] = 'None'
            row.pop('MPMax', None)
    return byml.dump(doc)


def apply(existing, generated, read_raw):
    """Compose after all generated actor packs and pouch rows exist."""
    records = {}
    for path in sorted(set(NATIVE_PACKS) | {p for p in existing if p.startswith('Pack/Actor/')}):
        raw = existing[path] if path in existing else read_raw(path)
        patched, changed = patch_pack(raw)
        if changed:
            existing[path] = patched
            records[path] = changed
    for path, (raw, template) in list(generated.items()):
        if path.startswith('Pack/Actor/'):
            patched, changed = patch_pack(raw)
            if changed:
                generated[path] = patched, template
                records[path] = changed
    existing[TABLE] = patch_table(existing[TABLE] if TABLE in existing else read_raw(TABLE))
    return records
