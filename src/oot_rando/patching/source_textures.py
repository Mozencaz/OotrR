"""Per-check gold source models, with vanilla appearance after collection.

Only the shuffled instance changes actor type. Its hash, Presence, physics,
native AI and drop fields remain intact. Two model accesses share the original
geometry: native materials at access 0, gold at access 1. A parallel AI branch
selects their visibility from the existing saved collection flag. No additional
physical actor or Presence condition is introduced (both would change respawns).
"""
import copy
import hashlib
import struct
from pathlib import Path

from oot_rando.formats import byml_codec as codec
from oot_rando.game.item_forms import resolve_components, pack_path
from oot_rando.patching.repeatable_adapter import EVENT_PACK, EVENT_MEMBER, ainb_default, stable_guid
from oot_rando.patching.song_models import read_pointer, read_u16, read_u32, read_name
from oot_rando.formats.inspect_resources import decompress
from oot_rando.formats.inspect_resources import sarc

ASSETS = Path(__file__).with_name('source_textures')
REMAPS = {
    'Rock_Pot_A_Alb': 'random_pot_Alb',
    **{f'Rock_Pot_A_{i:02}_Alb': 'random_pot_Alb' for i in range(2, 9)},
    'Plant_LiftGrass_A_02_Alb': 'random_bush_00000010_Alb',
    'Obj_Plant_Grass_A_03_Alb': 'random_grass_0000004_Alb',
    'MT_Rock_LiftRock_A_01_Alb': 'random_rock_000000002_Alb',
    'Obj_BrokenRock_A_01_A_Alb': 'random_rock_000000002_Alb',
    'Obj_BrokenRock_A_02_A_Alb': 'random_rock_000000002_Alb',
    'Obj_BrokenBox_A_04_Alb': 'random_crate_gold2_Alb',
    'Stone_BrokenBox_A_Alb': 'random_crate_gold_Alb',
    'Obj_HidingHole_Beehive_A_Alb': 'random_beehive_000000001_Alb',
    'Tree_SpruceTrunk_B_01_Alb': 'random_tree_trunk_v01_Alb',
    'Obj_Tree_A_Billboard_01_Alb': 'random_tree_billboard01_Alb',
}


def material_names(raw):
    """Every material, including LOD/billboard/shadow materials of a BFRES."""
    if raw[:4] != b'FRES':
        raise ValueError('Expected a native BFRES source model.')
    names = []
    models = read_pointer(raw, 0x28)
    for i in range(read_u16(raw, 0xdc)):
        model = models + i * 0x78
        materials = read_pointer(raw, model + 0x38)
        count = read_u32(raw, read_pointer(raw, model + 0x40) + 4)
        names.extend(read_name(raw, read_pointer(raw, materials + j * 0xb0 + 8)) for j in range(count))
    return sorted(set(names))


def gold_model(raw):
    """Remap albedo strings in place; preserve every geometry/shader offset."""
    result = bytearray(raw)
    used = {}
    for old, new in REMAPS.items():
        needle = struct.pack('<H', len(old)) + old.encode() + b'\0'
        offset = raw.find(needle)
        if offset < 0:
            continue
        if len(new) > len(old) or raw.find(needle, offset + 1) >= 0:
            raise ValueError('Unexpected source texture string: ' + old)
        result[offset:offset + len(needle)] = (struct.pack('<H', len(new)) + new.encode()
                                              + bytes(len(old) - len(new) + 1))
        used[old] = new
    return bytes(result), used


def _merged(pack, ref):
    chain = []
    while ref:
        root = codec.load(pack[pack_path(ref)])['root']
        chain.append(root)
        ref = root.get('$parent')
    merged = {}
    for root in reversed(chain):
        merged.update({k: copy.deepcopy(v) for k, v in root.items() if k != '$parent'})
    return merged


def visibility_ai(raw, flag, filename, materials, templates):
    """Run the native graph and a flag-driven model visibility branch together."""
    import ainb
    if raw is None:
        script = ainb.AINB()
        script.version, script.category = 0x408, 'AI'
        document = script.as_dict()
        document['Has Section 0x6C'] = True
        hold = copy.deepcopy(templates['hold'])
        hold.update({'Node Index': 0, 'Flags': ['Is Root Node']})
        document['Nodes'] = [hold]
        document['Commands'] = [{'Name': 'Root', 'GUID': stable_guid(flag + '/texture/command'),
                                 'Root Node Index': 0}]
    else:
        document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    if len(document['Commands']) != 1 or document['Commands'][0]['Name'] != 'Root':
        raise ValueError('Unexpected source AI commands.')
    old_root = document['Commands'][0]['Root Node Index']
    nodes[old_root]['Flags'] = [f for f in nodes[old_root]['Flags'] if f != 'Is Root Node']

    def add(template, purpose):
        node = copy.deepcopy(template)
        node.update({'Node Index': len(nodes), 'GUID': stable_guid(flag + '/texture/' + purpose),
                     'Flags': [], 'Queries': [], 'Attachments': [], 'XLink Actions': [], 'Plugs': {}})
        nodes.append(node)
        return node

    query = add(templates['query'], 'query')
    query['Flags'] = ['Is Query']
    query['Parameters']['Inputs']['String'] = [ainb_default('GameDataFullName', flag)]
    for prop in query['Properties'].get('Bool', []):
        if prop['Name'] == 'OutputOnlyOnEnter':
            prop['Default Value'] = False
    inverse = add(templates['invert'], 'inverse')
    inverse['Flags'] = ['Is Query']
    inverse['Queries'] = [query['Node Index']]
    inverse['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Bool', 'Default Value': False,
        'Node Index': query['Node Index'], 'Output Index': 0, 'Flags': []}]},
        'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}}
    inverse['Plugs'] = {'Generic': [{'Node Index': query['Node Index'], 'Name': 'Bool'}]}
    for prop in inverse['Properties'].get('Bool', []):
        if prop['Name'] == 'OutputOnlyOnEnter':
            prop['Default Value'] = False
    children = [{'Node Index': old_root, 'Name': ''}]
    for access, signal in ((0, query), (1, inverse)):
        for material in materials:
            action = add(templates['visible'], f'{access}/{material}')
            for prop in action['Properties']['Bool']:
                if prop['Name'] == 'ExecuteEveryFrame':
                    prop['Default Value'] = True
            action['Queries'] = [signal['Node Index']]
            action['Parameters'] = {'Inputs': {
                'Int': [ainb_default('ModelAccessIndex', access)],
                'Bool': [{'Name': 'IsVisible', 'Default Value': False,
                          'Node Index': signal['Node Index'], 'Output Index': 0, 'Flags': []}],
                'String': [ainb_default('MaterialName', material)]}, 'Outputs': {}}
            action['Plugs'] = {'Generic': [{'Node Index': signal['Node Index'], 'Name': 'IsVisible'}]}
            children.append({'Node Index': action['Node Index'], 'Name': ''})
    root = add(templates['parallel'], 'root')
    root['Flags'] = ['Is Root Node']
    root['Parameters'] = {'Inputs': {}, 'Outputs': {}}
    root['Plugs'] = {'Child': children}
    document['Commands'][0]['Root Node Index'] = root['Node Index']
    document['Filename'] = filename
    script = ainb.AINB.from_dict(document)
    # ainb 0.2.17 otherwise writes a 0x30-byte empty blackboard for v0x408,
    # while its offsets reserve 0x38 bytes (the native beehive has no entries).
    if script.blackboard is None:
        from ainb.blackboard import Blackboard
        script.blackboard = Blackboard()
    result = script.to_binary()
    if ainb.AINB.from_binary(result).as_dict() != document:
        raise ValueError('Source visibility AI failed readback.')
    return result


def build_files(records, maps, raw_maps, read_pack, read_raw, tables):
    """Build source packs/models/textures and repoint only shuffled map instances."""
    import ainb
    if not any(r['kind'] == 'pickup' and r.get('variants') for r in records):
        return {}
    global_ai = sarc(read_raw(EVENT_PACK))
    event = ainb.AINB.from_binary(global_ai[EVENT_MEMBER]).as_dict()['Nodes']
    stalchild = ainb.AINB.from_binary(global_ai['AI/Enemy_Stalchild.utility.root.ainb']).as_dict()['Nodes']
    def find(nodes, name):
        return next(n for n in nodes if n['Name'] == name or n['Node Type'] == name)
    templates = {k: find(event, v) for k, v in {
        'query': 'QueryGetNonStructGameDataBool', 'invert': 'QueryInvertBool',
        'parallel': 'Element_Simultaneous',
        'hold': 'ExecuteGenericDummyAction'}.items()}
    templates['visible'] = find(stalchild, 'OneshotModelSetMaterialVisible')
    files, documents, model_cache = {}, {}, {}
    row_index = {name: {r['__RowId']: r for r in rows} for name, rows in tables.items()}
    for record in records:
        for variant in record.get('variants', []):
            source = variant.get('source')
            if not source or record['kind'] != 'pickup':
                continue
            pack = read_pack(source)
            components = resolve_components(pack, source, codec)
            model = _merged(pack, components['ModelInfoRef'])
            project, fmdb = model['ModelProjectName'], model['FmdbName']
            model_path = f'Model/{project}.{fmdb}.bfres.zs'
            if model_path not in model_cache:
                raw = read_raw(model_path)
                gold, remaps = gold_model(raw)
                model_cache[model_path] = (gold, remaps, material_names(raw))
            gold, remaps, materials = model_cache[model_path]
            if not remaps:
                variant['texture_skip'] = 'No compatible supplied texture for ' + fmdb
                continue
            if model.get('SubModels'):
                raise ValueError('Source already has submodels: ' + source)
            gold_project = 'Rando_' + project
            files[f'Model/{gold_project}.{fmdb}.bfres.zs'] = (gold, model_path)
            for old, new in remaps.items():
                dest = f'Tex/{new}.bntx.zs'
                if dest not in files:
                    files[dest] = (decompress((ASSETS / (new + '.bntx.zstd')).read_bytes(), {}),
                                   f'Tex/{old}.bntx.zs')
            key = hashlib.sha256((record['flag'] + '/' + source).encode()).hexdigest()[:16]
            actor = 'Obj_RandoSource_' + key
            path = f'Pack/Actor/{actor}.pack.zs'
            if path not in files:
                cloned = dict(pack)
                model['SubModels'] = [{'FmdbName': fmdb, 'ModelProjectName': gold_project}]
                model['IsExclusiveControl'] = False
                model_ref = f'Component/ModelInfo/{actor}.engine__component__ModelInfo.bgyml'
                cloned[model_ref] = codec.dump({'endian': '<', 'version': 7, 'root': model})
                info = _merged(pack, components['AIInfoRef']) if components.get('AIInfoRef') else {}
                native_ai = 'AI/' + info['RootAIRef'].split('/')[-1] + 'b' if info.get('RootAIRef') else None
                filename = actor + '.root'
                try:
                    cloned['AI/' + filename + '.ainb'] = visibility_ai(
                        (pack.get(native_ai) or global_ai[native_ai]) if native_ai else None,
                        record['flag'], filename, materials, templates)
                except Exception as error:
                    raise ValueError('Cannot build source texture AI for ' + source) from error
                info['RootAIRef'] = f'Work/AI/Root/{filename}.ain'
                info_ref = f'AI/AIInfo/{actor}.engine__actor__AIInfo.bgyml'
                cloned[info_ref] = codec.dump({'endian': '<', 'version': 7, 'root': info})
                # Disable pre-rendering: material selection must run before this source is drawn.
                override = {'ModelInfoRef': '?' + model_ref, 'AIInfoRef': '?' + info_ref}
                override['PreActorSettingRef'] = (
                    '?ActorSystem/PreActorSetting/ActorOnly.game__actor__PreActorSetting.bgyml')
                cloned[f'Actor/{actor}.engine__actor__ActorParam.bgyml'] = codec.dump({
                    'endian': '<', 'version': 7, 'root': {
                        '$parent': f'Work/Actor/{source}.engine__actor__ActorParam.gyml', 'Components': override}})
                files[path] = (codec.build_sarc(cloned), f'Pack/Actor/{source}.pack.zs')
                for name in ('ActorInfo', 'GameActorInfo'):
                    row = copy.deepcopy(row_index[name][source])
                    row['__RowId'] = actor
                    # The second model and extra AI nodes need their own instance allocation.
                    if name == 'ActorInfo':
                        row['InstanceHeapSize'] = row.get('InstanceHeapSize', 0) * 2 + 0x10000
                        row['ModelProjectName'] = project
                        row['UsePreActorRenderer'] = False
                    tables[name].append(row)
                    row_index[name][actor] = row
            resource, index = variant['resource'], variant['index']
            if resource not in documents:
                documents[resource] = codec.load(raw_maps.get(resource, maps[resource]['raw']))
            original = documents[resource]['root']['Actors'][index]
            if original['Gyaml'] != source:
                raise ValueError('Source actor changed before texture selection.')
            original['Gyaml'] = actor
            variant['textured_actor'] = actor
    for resource, document in documents.items():
        raw_maps[resource] = codec.dump(document)
    for rows in tables.values():
        rows.sort(key=lambda r: r['__RowId'])
    return files
