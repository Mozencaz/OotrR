"""Remove shop opening hours without changing the world clock or NPC schedules."""
from functools import partial
from oot_rando.formats.evfl_tools import case_target, event_params_of


def module(name):
    return 'Logic/' + name + '.logic.module.ainb'


# Door input: (node, expected module, input, previous source node, output).
DOORS = {
    'Market_Child_Prefab_8c1c': ((1, 'Obj_Door_ShopAnything_657f.logic.module', 'EnableOpen', 0, 0),),
    'Market_Child_Prefab_971c': ((6, 'Obj_Door_ShopMedicine_9089.logic.module', 'EnableOpen', 5, 1),),
    'KakarikoVillage_Adult_Common_d447': ((1, 'Obj_Door_Shop_KakarikoNandemoya_4df6.logic.module', 'EnableOpen', 0, 0),),
    'KakarikoVillage_Adult_Common_426e': (
        (1, 'Obj_Door_Shop_KakarikoMedicine_67a6.logic.module', 'EnableOpen', 0, 0),
        (2, 'Obj_Door_Shop_KakarikoMedicine_67a6.logic.module', 'EnableOpen', 0, 0)),
    'MiniGame_SequentialChoiceTreasure_cbde': ((18, 'Obj_Door_ShopTreasureBox_0b42.logic.module', 'EnableOpen', 16, 1),),
    'Market_Child_Prefab_0c76': ((3, 'Obj_Door_ShopBombChu_26fc.logic.module', 'EnableOpen', 0, 1),),
}

# Remove only the time input of an AND, retaining its age/quest input.
GATES = {
    'Market_Child_Prefab_7c39': (2, [(0, 0), (4, 0)], 1),
    'MiniGame_HitTarget_cab0': (4, [(3, 1), (2, 0)], 0),
    'MiniGame_HitTarget_2921': (5, [(3, 0), (2, 0)], 0),
}


def doors_all_hours(raw, name):
    from oot_rando.patching.story_fixes import edit_ainb_module

    def check(nodes):
        for index, kind, param, source, output in DOORS.get(name, ()):
            node = nodes[index]
            entry = next(v for v in node['Parameters']['Inputs']['Bool'] if v['Name'] == param)
            if (node['Name'] != kind or entry.get('Node Index') != source
                    or entry.get('Output Index') != output or entry['Flags']):
                raise ValueError('Unexpected shop door: ' + name)
        if name in GATES:
            index, expected, _ = GATES[name]
            node = nodes[index]
            sources = node['Parameters']['Inputs']['Bool'][0]['Sources']
            if (node['Name'] != 'OperateAND'
                    or [(s['Node Index'], s['Output Index']) for s in sources] != expected):
                raise ValueError('Unexpected shop time gate: ' + name)

    def edit(nodes):
        for index, _, param, source, _ in DOORS.get(name, ()):
            node = nodes[index]
            entry = next(v for v in node['Parameters']['Inputs']['Bool'] if v['Name'] == param)
            entry.update({'Default Value': True, 'Node Index': -1, 'Output Index': 0,
                          'Flags': ['Uses Default', 'Is Output']})
            node['Plugs']['Generic'] = [p for p in node['Plugs'].get('Generic', []) if p['Name'] != param]
            if not node['Plugs']['Generic']:
                del node['Plugs']['Generic']
            # Other inputs can still need the same query.
            remaining = {v.get('Node Index') for values in node['Parameters']['Inputs'].values() for v in values}
            if source not in remaining:
                node['Queries'] = [q for q in node['Queries'] if q != source]
        if name in GATES:
            index, _, keep = GATES[name]
            node = nodes[index]
            entry = node['Parameters']['Inputs']['Bool'][0]
            retained = dict(entry['Sources'][keep])
            entry['Sources'] = [dict(retained), dict(retained)]
            node['Queries'] = [retained['Node Index']] * 2
            node['Plugs']['Generic'] = [{'Node Index': retained['Node Index'], 'Name': entry['Name']}]

    if name not in DOORS and name not in GATES:
        raise ValueError('Unknown shop door: ' + name)
    return edit_ainb_module(raw, check, edit), {'module': module(name), 'all_hours': True}


def bombchu_from_start(raw):
    from oot_rando.patching.story_fixes import bombchu_shop_open_from_start
    raw, report = bombchu_shop_open_from_start(raw)
    raw, _ = doors_all_hours(raw, 'Market_Child_Prefab_0c76')
    return raw, dict(report, all_hours=True)


def module_fixes():
    return tuple((module(name), 'shop_hours_' + name, partial(doors_all_hours, name=name))
                 for name in (*DOORS, *GATES) if name != 'Market_Child_Prefab_0c76')


# (flow, time switch, query, params, normal service case, normal destination, closed destination).
SERVICES = (
    ('MiniGame_HitTarget', 'Event209', 'EventQueryIsCurrentTimeInSpecifiedTimeRange',
     {'EndTme': 6, 'StartTime': 20}, 1, 'Event95', 'Event310'),
    ('MiniGame_SequentialChoiceTreasure', 'Event2', 'EventQueryIsCurrentTimeInSpecifiedTimeRange',
     {'EndTme': 6, 'StartTime': 20}, 0, 'Event68', 'Event216'),
    ('Npc_Hylia_020_Shop_Child', 'Event2', 'EventQueryTimeDivision', {}, 0, 'Event107', 'Event90'),
    ('Npc_Hylia_023_Shop_Child', 'Event36', 'EventQueryTimeDivision', {}, 0, 'Event134', 'Event69'),
    ('Npc_Hylia_021_Shop_Child', 'Event2', 'EventQueryTimeDivision', {}, 1, 'Event57', 'Event72'),
)


def service_all_hours(raw, spec):
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    name, event, query, params, normal, target, closed = spec
    flow = _Chart(raw)
    gate = flow.event(event, 'SwitchEvent')
    if (gate.data.actor_query.v.v != query or event_params_of(gate) != params
            or set(gate.data.cases) != {0, 1}
            or case_target(gate, normal).name != target or case_target(gate, 1 - normal).name != closed):
        raise ValueError('Unexpected shop service gate: ' + name)
    gate.data.cases[1 - normal] = make_index(case_target(gate, normal))
    raw, _ = flow.write()
    return raw, {'flow': 'Event/EventFlow/' + name + '.bfevfl.zs', 'all_hours': True}


def flow_fixes():
    return tuple(('Event/EventFlow/' + spec[0] + '.bfevfl.zs', 'shop_hours_' + spec[0],
                  partial(service_all_hours, spec=spec)) for spec in SERVICES)
