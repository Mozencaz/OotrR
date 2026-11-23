"""Explosive ammunition must never award a bomb bag as a side effect.

The engine's SmallBagActor pouch parameter automatically grants that actor on
the first refill. Both bombs and bombchus name the small bomb bag in vanilla.
Clear the optional actor reference, retaining ammunition counts and capacity.
Every embedded copy must agree, regardless of which pack loads it first.
"""
from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc

BAG_ACTOR = 'Work/Actor/Item_BombBag_Small.engine__actor__ActorParam.gyml'
POUCH_PATHS = tuple(f'Component/PouchContentParam/{actor}.game__component__PouchContentParam.bgyml'
                    for actor in ('Item_Bomb', 'Item_Bombchu'))
# Exhaustively checked against the supported game's actor packs (see tests).
NATIVE_PACKS = tuple(f'Pack/Actor/{actor}.pack.zs' for actor in (
    'Item_Bomb', 'Item_Bombchu', 'Npc_Hylia_ImperialSoldier_Bomb',
    'Obj_Bomb', 'Obj_Bombchu', 'Pouch_Bomb', 'Pouch_Bombchu',
    *(f'Shop_BombchuBundle_{i:02}' for i in range(1, 9))))


def patch_pack(raw):
    """Return (SARC bytes, changed pouch paths), including for derived packs."""
    files = dict(sarc(raw))
    changed = []
    for path in POUCH_PATHS:
        if path not in files:
            continue
        document = byml_codec.load(files[path])
        value = document['root'].get('SmallBagActor', '')
        if not value:
            continue
        if value != BAG_ACTOR:
            raise ValueError('Unexpected bomb refill bag actor: ' + path)
        # Empty references are the native representation of an absent actor.
        document['root']['SmallBagActor'] = ''
        files[path] = byml_codec.dump(document)
        changed.append(path)
    return (byml_codec.build_sarc(files) if changed else raw), changed


def apply(existing, generated, read_raw):
    """Compose native and generated packs after all other actor changes."""
    records = {}
    paths = set(NATIVE_PACKS) | {p for p in existing if p.startswith('Pack/Actor/')}
    for path in sorted(paths):
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
    return records
