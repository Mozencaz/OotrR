"""Let ice-arrow hits enter red ice's native melt/persistence sequence."""
import copy
import hashlib
import json

from oot_rando.formats import byml_codec as byml
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.ap_mailbox import ainb_to_binary
from oot_rando.patching.repeatable_adapter import ainb_default, stable_guid
from oot_rando.patching.soul_adapter import murmur3

ARROW_PACK = 'Pack/Actor/NormalArrow.pack.zs'
ATTACK = 'GameBalance/AttackParam/NormalArrow.game__gamebalance__AttackParam.bgyml'
ICE_PACKS = tuple(f'Pack/Actor/Obj_RedIce_A_{v}.pack.zs'
                  for v in ('01', '02', '04', '06', '07', '08', '09'))
AI = 'AI/Obj_RedIce_A_01.root.ainb'
IDENTIFIER = 'Rando_BlueFireIceArrow'
NATIVE_AI = 'be78a6582365ec3a61304d85f18010932e96a3976a0d9f9c857ebcc96c234300'


def patch_arrow(raw):
    files = sarc(raw)
    document = byml.load(files[ATTACK])
    rows = [r for r in document['root']['AttackParams'] if r['AttackType'] == murmur3('IceArrow')]
    if len(rows) != 1:
        raise ValueError('Missing unique ice-arrow attack.')
    row = rows[0]
    if (row['AttackIdentifier'], row['AttackIdentifierHash']) == (IDENTIFIER, murmur3(IDENTIFIER)):
        return raw
    if row['AttackIdentifier'] or row['AttackIdentifierHash']:
        raise ValueError('Unexpected ice-arrow attack identifier.')
    row['AttackIdentifier'] = IDENTIFIER
    row['AttackIdentifierHash'] = byml.U32(murmur3(IDENTIFIER))
    files[ATTACK] = byml.dump(document)
    return byml.build_sarc(files)


def _selector_input(node, query, output=0):
    node['Queries'] = [query]
    node['Parameters']['Inputs']['Bool'][0].update({'Node Index': query, 'Output Index': output})
    node['Plugs']['Generic'][0]['Node Index'] = query


def _patched(document):
    result = copy.deepcopy(document)
    nodes = result['Nodes']

    def add(template, purpose):
        node = copy.deepcopy(nodes[template])
        node.update({'Node Index': len(nodes), 'GUID': stable_guid(IDENTIFIER + '/' + purpose)})
        nodes.append(node)
        return node

    # Same interface as the native query in _LocalModule_7498b5490eff, node 1.
    hit = add(3, 'hit')
    hit['Name'] = 'QuerySensorHitIsHitAttackIdentifier'
    hit['Parameters'] = {'Inputs': {'String': [ainb_default('AttackIdentifier', IDENTIFIER)]},
                         'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}}

    def disjunction(left, output, right, purpose):
        node = add(10, purpose)
        node['Queries'] = [left] + ([right] if right is not None else [])
        values = node['Parameters']['Inputs']['Bool']
        values[0].update({'Node Index': left, 'Output Index': output})
        values[1].update({'Node Index': right if right is not None else -1, 'Output Index': 0})
        if right is None:
            values[1]['Blackboard Index'] = 0  # native IsFireHit latch
        node['Plugs'] = {'Generic': [{'Node Index': left, 'Name': 'ValueA'}] +
                        ([{'Node Index': right, 'Name': 'ValueB'}] if right is not None else [])}
        return node['Node Index']

    latched = disjunction(hit['Node Index'], 0, None, 'latched')
    received = disjunction(51, 1, latched, 'received')
    targeted = disjunction(48, 0, latched, 'targeted')
    # The flame-position node must never consume an absent blue-flame message.
    position = add(45, 'position')
    _selector_input(position, latched)
    position['Plugs']['Child'] = [{'Node Index': 5, 'Name': 'True'},
                                 {'Node Index': 27, 'Name': 'False'}]
    nodes[31]['Plugs']['Child'][0]['Node Index'] = position['Node Index']
    _selector_input(nodes[28], received)
    _selector_input(nodes[45], targeted)
    return result


def patch_ai(raw):
    import ainb
    document = ainb.AINB.from_binary(raw).as_dict()
    native = copy.deepcopy(document)
    if len(native['Nodes']) == 67:
        native['Nodes'] = native['Nodes'][:62]
        _selector_input(native['Nodes'][28], 51, 1)
        _selector_input(native['Nodes'][45], 48)
        native['Nodes'][31]['Plugs']['Child'][0]['Node Index'] = 27
    digest = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
    if digest != NATIVE_AI:
        raise ValueError('Unexpected red-ice AI; refusing to replace native behavior.')
    expected = _patched(native)
    if document == expected:
        return raw
    if document != native:
        raise ValueError('Incomplete blue-fire arrow AI patch.')
    result = ainb_to_binary(expected)
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Blue-fire arrow AI failed readback.')
    return result


def patch_ice(raw):
    files = sarc(raw)
    result = patch_ai(files[AI])
    if result == files[AI]:
        return raw
    files[AI] = result
    return byml.build_sarc(files)


def resource_fixes():
    return ((ARROW_PACK, patch_arrow),) + tuple((p, patch_ice) for p in ICE_PACKS)
