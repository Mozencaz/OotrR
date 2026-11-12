"""First-collection rewards for repeatable physical sources.

Generated pickups retain the real item's PouchActor. Their private event AINB
sets a saved check flag only after the native add-to-pouch action. Complementary
Presence conditions select the randomized source before that flag and a clone
of the untouched vanilla source afterwards. Gameplay validation remains required.
"""
import copy
import hashlib
import uuid

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import (WORLD_CANONICAL, WORLD_PREFIX, build_pack, canonical_of,
                        is_derived, add_rsdb_rows)
from oot_rando.patching.soul_adapter import FLAG_PREFIX as SOUL_FLAG_PREFIX, murmur3

REPEATABLE = frozenset(('pots', 'bushes', 'rocks', 'crates', 'beehives'))
EVENT_PACK = 'Pack/AI.Global.Product.111.pack.zs'
EVENT_MEMBER = 'AI/PouchContent.event.root.ainb'
LARGE_GET_TYPE = 1746592023


def _guid(text):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'oot-randomizer/' + text))


def instrument_pickup_event(raw, flag, filename, canonical=None, also_set=()):
    """Clone an event AI and sequence a GameData write AFTER native pouch push.

    All commands and original nodes are retained. No setter is attached to actor
    death, jar destruction, event entry, animation completion or item possession.
    ``also_set`` lists further saved Bool flags written after ``flag`` (a soul
    picked from a pot also sets its ``IsGet.Item_Soul_*`` flag).
    """
    try:
        import ainb
    except ImportError as error:
        raise ValueError('Install ainb==0.2.17 for first-collection rewards.') from error
    script = ainb.AINB.from_binary(raw)
    original = script.as_dict()
    document = copy.deepcopy(original)
    if document['Version'] != 0x408:
        raise ValueError('Unexpected AINB version for first collection.')
    nodes = document['Nodes']
    pushes = [n for n in nodes if n['Name'] == 'OneShotPouchContentPushToPouchOwnInEvent']
    if len(pushes) != 1:
        raise ValueError('Native pickup action ambiguous or missing.')
    push = pushes[0]['Node Index']
    parents = [(n, plug) for n in nodes for plug in n.get('Plugs', {}).get('Child', [])
               if plug['Node Index'] == push]
    if not parents:
        raise ValueError('Pickup action without an executable parent.')
    # A native sequential template from this very graph preserves its policies.
    sequential = next((copy.deepcopy(n) for n in nodes if n['Node Type'] == 'Element_Sequential'), None)
    if sequential is None:
        raise ValueError('Sequential template missing from the get graph.')
    sequence_index, setter_index = len(nodes), len(nodes) + 1
    query_index, selector_index = len(nodes) + 2, len(nodes) + 3
    for _, plug in parents:
        plug['Node Index'] = selector_index if canonical else sequence_index
    sequential.update({'Node Index': sequence_index, 'GUID': _guid(flag + '/sequence'),
                       'Queries': [], 'Attachments': [], 'Flags': [],
                       'Parameters': {'Inputs': {}, 'Outputs': {}}, 'XLink Actions': [],
                       'Plugs': {'Child': [{'Node Index': push, 'Name': ''},
                                           {'Node Index': setter_index, 'Name': ''}]}})
    for prop in sequential.get('Properties', {}).get('Bool', []):
        if prop['Name'] == 'IsLoop':
            prop['Default Value'] = False
    def default(name, value):
        return {'Name': name, 'Default Value': value, 'Node Index': -1,
                'Output Index': 0, 'Flags': ['Uses Default']}
    setter = {'Node Type': 'UserDefined', 'Node Index': setter_index,
              'Name': 'OneShotSetNonStructGameDataBool', 'GUID': _guid(flag + '/setter'),
              'Flags': [], 'Queries': [], 'Attachments': [],
              'Properties': {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]},
              'Parameters': {'Inputs': {'Int': [default('GameDataIndex', -1)],
                                        'Bool': [default('Value', True)],
                                        'String': [default('GameDataFullName', flag)]}, 'Outputs': {}},
              'XLink Actions': [], 'Plugs': {}}
    document['Filename'] = filename
    nodes.extend([sequential, setter])
    if canonical:
        query = copy.deepcopy(next(n for n in nodes[:sequence_index] if n['Name'] == 'QueryPouchMgrIsEnablePushToPouch'))
        query.update({'Node Index': query_index, 'GUID': _guid(flag + '/can-add'), 'Queries': [], 'Plugs': {}})
        query['Parameters']['Inputs'] = {'String': [default('ActorName', canonical)]}
        selector = copy.deepcopy(next(n for n in nodes[:sequence_index] if n['Node Type'] == 'Element_BoolSelector'))
        noop = next(n['Node Index'] for n in nodes[:sequence_index] if n['Name'] == 'OneshotDoNothing')
        selector.update({'Node Index': selector_index, 'GUID': _guid(flag + '/guard'), 'Queries': [query_index],
                         'Attachments': [], 'Flags': [], 'XLink Actions': []})
        selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False,
                                 'Node Index': query_index, 'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
        selector['Plugs'] = {'Generic': [{'Node Index': query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                             'Child': [{'Node Index': sequence_index, 'Name': 'True'}, {'Node Index': noop, 'Name': 'False'}]}
        nodes.extend([query, selector])
    # A drop may already exist when another copy of the same location is
    # collected. Recheck the saved per-check flag at native pickup execution,
    # rather than relying only on the source actor's Presence condition.
    flag_query_index, flag_selector_index = len(nodes), len(nodes) + 1
    flag_query = copy.deepcopy(next(n for n in nodes[:sequence_index]
                                   if n['Name'] == 'QueryGetNonStructGameDataBool'))
    flag_query.update({'Node Index': flag_query_index, 'GUID': _guid(flag + '/already-collected'),
                       'Queries': [], 'Plugs': {}})
    flag_query['Parameters']['Inputs']['String'] = [default('GameDataFullName', flag)]
    flag_selector = copy.deepcopy(next(n for n in nodes[:sequence_index]
                                      if n['Node Type'] == 'Element_BoolSelector'))
    noop = next(n['Node Index'] for n in nodes[:sequence_index] if n['Name'] == 'OneshotDoNothing')
    eligible = selector_index if canonical else sequence_index
    flag_selector.update({'Node Index': flag_selector_index, 'GUID': _guid(flag + '/first-only'),
                          'Queries': [flag_query_index], 'Attachments': [], 'Flags': [], 'XLink Actions': []})
    flag_selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False,
                                      'Node Index': flag_query_index, 'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
    flag_selector['Plugs'] = {
        'Generic': [{'Node Index': flag_query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
        'Child': [{'Node Index': noop, 'Name': 'True'}, {'Node Index': eligible, 'Name': 'False'}]}
    for _, plug in parents:
        plug['Node Index'] = flag_selector_index
    nodes.extend([flag_query, flag_selector])
    for extra in also_set:
        extra_setter = copy.deepcopy(setter)
        extra_setter.update({'Node Index': len(nodes), 'GUID': _guid(flag + '/also/' + extra)})
        extra_setter['Parameters']['Inputs']['String'] = [default('GameDataFullName', extra)]
        sequential['Plugs']['Child'].append({'Node Index': len(nodes), 'Name': ''})
        nodes.append(extra_setter)
    result = ainb.AINB.from_dict(document).to_binary()
    checked = ainb.AINB.from_binary(result).as_dict()
    if checked != document:
        raise ValueError('The modified get graph does not read back identically.')
    # Strong invariant: every original command is untouched and additions occur
    # only at child references to the native pouch-push action.
    if checked['Commands'] != original['Commands']:
        raise ValueError('Get commands changed unexpectedly.')
    return result


def prepare_repeatables(plan, maps):
    """Rename selected repeatable world rewards; return generation descriptors.

    Must run BEFORE the normal placement map patches are composed. Original
    placements keep their AP item/spoiler actor; only the physical pickup changes.
    """
    records = []
    for placement in plan['placements']:
        if placement.get('source') not in REPEATABLE:
            continue
        previous = placement['after']
        canonical = canonical_of(previous) if is_derived(previous) else WORLD_CANONICAL.get(previous)
        if canonical is None:
            raise ValueError('Repeatable reward without a known native form: ' + previous)
        key = hashlib.sha256(placement['id'].encode('utf-8')).hexdigest()[:16]
        actor = 'Obj_RandoOnce_' + key
        flag = 'Rando.Check.' + key
        variants = []
        for patch in placement['patches']:
            if 'event' in patch or tuple(patch['path'][:1]) != ('Actors',):
                raise ValueError('Repeatable source without a proven physical actor.')
            resource, index = patch['resource'], patch['path'][1]
            original = maps[resource]['root']['Actors'][index]
            # An existing Presence cannot be overwritten by a new condition.
            # The only currently supported special case is a native one-shot
            # jar, already removed by its own persistent IsCrushed condition.
            presence = original.get('Presence')
            native_once = bool(presence and presence.get('IsNegation') is True
                               and presence.get('FlagName', '').endswith('_IsCrushed'))
            if presence and not native_once:
                raise ValueError('Conditional presence cannot be combined for ' + placement['id'])
            fallback_hash = int.from_bytes(hashlib.sha256((placement['id'] + '/vanilla-source').encode()).digest()[:8], 'little')
            variants.append({'resource': resource, 'index': index, 'native_once': native_once,
                             'original_hash': int(original['Hash']), 'fallback_hash': fallback_hash})
        record = {'id': placement['id'], 'actor': actor, 'canonical': canonical,
                  'original_reward_actor': previous, 'flag': flag, 'flag_hash': murmur3(flag),
                  'event_filename': 'RandoOnce_' + key + '.event.root', 'variants': variants}
        placement['after'] = actor
        placement['reward_actor'] = previous
        placement['first_collect_flag'] = flag
        records.append(record)
        match = plan.get('matches', {}).get(placement['id'])
        if match is not None:
            match['first_collect_flag'] = flag
    return records


def build_repeatable_packs(records, read_pack, read_raw, tables):
    """Build unique pickups and event graphs, and append their RSDB rows.

    ``read_pack`` sees normal/generated soul packs. ``read_raw`` returns raw
    game resources. ``tables`` are current RSDB row arrays, edited in place.
    Returns new-resource mapping of path -> (raw, compression_template_path).
    Saved Bool flags must be added separately by the caller (8 bytes each).
    """
    if not records:
        return {}
    global_ai = sarc(read_raw(EVENT_PACK))
    event = global_ai[EVENT_MEMBER]
    new = {}
    for record in records:
        standard = WORLD_PREFIX + record['canonical']
        raw, template = build_pack(standard, read_pack, byml_codec)
        files = sarc(raw)
        old_path = f'Actor/{standard}.engine__actor__ActorParam.bgyml'
        document = byml_codec.load(files.pop(old_path))
        components = document['root']['Components']
        pouch_path = components['PouchContentRef'][1:]
        pouch = byml_codec.load(files[pouch_path])
        pouch['root'].update({'PlayGetEventManyTimes': True, 'GetType': byml_codec.U32(LARGE_GET_TYPE),
                              'IsAutoSaveAfterPlayGet': True})
        # The PouchActor remains the canonical reward: no unique inventory item
        # or duplicate bundle is introduced just to track a check.
        files[pouch_path] = byml_codec.dump(pouch)
        event_name = record['event_filename']
        event_member = 'AI/' + event_name + '.ainb'
        event_param = f'Component/EventPerformerParam/{record["actor"]}.engine__component__EventPerformerParam.bgyml'
        files[event_param] = byml_codec.dump({'endian': '<', 'version': 7, 'root': {
            '$parent': 'Work/Component/EventPerformerParam/PouchContent_PickUpItem.engine__component__EventPerformerParam.gyml',
            'AlwaysEventMember': True, 'UseEventUniqueAin': True,
            'EventUniqueAin': 'Work/AI/Root/Event/' + event_name + '.ain'}})
        components['EventPerformerRef'] = '?' + event_param
        also = (SOUL_FLAG_PREFIX + record['canonical'],) if record['canonical'].startswith('Item_Soul_') else ()
        files[event_member] = instrument_pickup_event(event, record['flag'], event_name, record['canonical'], also)
        files[f'Actor/{record["actor"]}.engine__actor__ActorParam.bgyml'] = byml_codec.dump(document)
        new['Pack/Actor/' + record['actor'] + '.pack.zs'] = (byml_codec.build_sarc(files), template)
        # Reuse the existing derived-row builder under a temporary name, then
        # rename only those freshly appended rows. Their reward metadata stays.
        existing = {name: {row['__RowId'] for row in rows} for name, rows in tables.items()}
        if any(standard in ids for ids in existing.values()):
            # A standard derived reward might already be needed by another
            # location. Build rows in an isolated copy and copy only the alias.
            scratch = {name: [copy.deepcopy(row) for row in rows if row['__RowId'] != standard]
                       for name, rows in tables.items()}
            add_rsdb_rows(scratch, [standard])
            for name, rows in scratch.items():
                row = copy.deepcopy(next(row for row in rows if row['__RowId'] == standard))
                row['__RowId'] = record['actor']
                tables[name].append(row)
        else:
            add_rsdb_rows(tables, [standard])
            for rows in tables.values():
                row = next(row for row in rows if row['__RowId'] == standard)
                row['__RowId'] = record['actor']
        for rows in tables.values():
            rows.sort(key=lambda row: row['__RowId'])
    return new


def patch_repeatable_sources(records, maps, raw_maps):
    """Select first/randomized and subsequent/vanilla sources with saved flags.

    Call AFTER normal map reward patches. The original actor and its links/hash
    remain the first source. The fallback is a full copy of vanilla data,
    including absence of an explicit drop and native drop-table settings.
    """
    documents, originals, seen = {}, {}, set()
    for record in records:
        for variant in record['variants']:
            resource, index = variant['resource'], variant['index']
            if (resource, index) in seen:
                continue
            seen.add((resource, index))
            if resource not in documents:
                documents[resource] = byml_codec.load(raw_maps.get(resource, maps[resource]['raw']))
                originals[resource] = byml_codec.load(maps[resource]['raw'])['root']['Actors']
            actors = documents[resource]['root']['Actors']
            first = actors[index]
            original = originals[resource][index]
            if variant['native_once']:
                continue
            if first.get('Presence') or original.get('Presence'):
                raise ValueError('Presence already modified on a repeatable source.')
            first['Presence'] = {'FlagName': record['flag'], 'IsNegation': True, 'IsCheckLazy': False}
            fallback = copy.deepcopy(original)
            used = {int(actor['Hash']) for actor in actors if 'Hash' in actor}
            ident = variant['fallback_hash']
            if ident in used:
                raise ValueError('Source hash collision for the return to the original loot.')
            fallback['Hash'] = byml_codec.U64(ident)
            for link in fallback.get('Links', []):
                for key in ('Src', 'Dst'):
                    if link.get(key) == original['Hash']:
                        link[key] = byml_codec.U64(ident)
            if isinstance(fallback.get('Phive', {}).get('Placement'), dict):
                fallback['Phive']['Placement']['ID'] = byml_codec.U64(ident)
            fallback['Presence'] = {'FlagName': record['flag'], 'IsNegation': False, 'IsCheckLazy': False}
            actors.append(fallback)
    for resource, document in documents.items():
        raw_maps[resource] = byml_codec.dump(document)
    return sorted(documents)



def register_repeatable_flags(raw, records):
    """Add saved collection flags and registered fallback actor keys.

    Bool64bitKey is one shared sparse set of true uint64 keys in progress.sav:
    each additional possible key reserves 8 payload bytes, with no new typed
    hash/value-table record. Ordinary Bool reserves an 8-byte typed record.
    Returns (raw_GameData, summary). No names or rewards are stored in saves.
    """
    if not records:
        return raw, {'bools': [], 'bool64': [], 'saved_bytes_added': 0}
    document = byml_codec.load(raw)
    data, meta = document['root']['Data'], document['root']['MetaData']
    previous_saved_size = meta['AllDataSaveSize']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    bool_template = next((e for e in data['Bool'] if e.get('SaveFileIndex') == 0
                          and e.get('ResetTypeValue') == 8 and e.get('DefaultValue') is False), None)
    if bool_template is None:
        raise ValueError('Saved collection flag template missing.')
    key_templates = {int(e['Hash']): e for e in data['Bool64bitKey']}
    added_bool, added_key = [], []
    for record in records:
        value = int(record['flag_hash'])
        if value != murmur3(record['flag']) or value in known:
            raise ValueError('Collection flag collision: ' + record['flag'])
        entry = copy.deepcopy(bool_template)
        entry['Hash'] = byml_codec.U32(value)
        data['Bool'].append(entry)
        known.add(value)
        index = entry['SaveFileIndex']
        meta['SaveDataSize'][index] += 8
        meta['SaveDataOffsetPos'][index] += 8
        meta['AllDataSaveSize'] += 8
        meta['AllDataSaveOffset'] += 8
        added_bool.append(value)
        for variant in record['variants']:
            if variant['native_once']:
                continue
            original = key_templates.get(variant['original_hash'])
            if original is None:
                continue
            key = int(variant['fallback_hash'])
            if key in added_key:
                continue
            if key in known:
                raise ValueError('Source key collision for the return to the original loot.')
            entry = copy.deepcopy(original)
            entry['Hash'] = byml_codec.U64(key)
            data['Bool64bitKey'].append(entry)
            known.add(key)
            index = entry.get('SaveFileIndex', -1)
            if index >= 0:
                meta['SaveDataSize'][index] += 8
                meta['AllDataSaveSize'] += 8
            added_key.append(key)
    return byml_codec.dump(document), {'bools': added_bool, 'bool64': added_key,
                                       'saved_bytes_added': meta['AllDataSaveSize'] - previous_saved_size}
