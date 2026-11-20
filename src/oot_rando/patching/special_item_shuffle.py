"""Master Sword shuffle: separate possession from the native time travel scenes.

Only used with shuffle_master_sword. Pedestal animation equipment in 0070/0088
is deliberately retained: those scenes wait for it, then era replacement restores
PlayerWeaponBeforeForceEquipMasterSword. No ownership is added by those scenes.
These resource checks are not an in-game validation of swordless time travel.
"""
from evfl.util import make_index

from oot_rando.patching.event_patch import _flow
from oot_rando.patching.qol_patches import _predecessors
from oot_rando.patching.story_fixes import _Chart, _params

SWORD = 'Weapon_Sword_Master'
PREFIX = 'Event/EventFlow/'
STEMS = ('DoorOfTime', 'Dm_TimeTemple_0030', 'ReplaceEquipmentForEraChange',
         'AllSage', 'Dm_SY_BancChangeArrive', 'Defeat_Ganon')
FLOWS = tuple(PREFIX + stem + '.bfevfl.zs' for stem in STEMS)


def flow_paths(options, members=None):
    """Required flows, with existing update variants; off requires no reads."""
    if not options.get('shuffle_master_sword'):
        return ()
    if members is None:
        return FLOWS
    paths = []
    for path in FLOWS:
        if path not in members:
            raise ValueError('Master Sword shuffle missing flow: ' + path)
        paths.append(path)
        update = path[:-len('.bfevfl.zs')] + '.110.bfevfl.zs'
        if update in members:
            paths.append(update)
    return tuple(paths)


def _redirect(links, target):
    for owner, kind, key in links:
        ref = make_index(target)
        if kind == 'entry':
            owner.main_event = ref
        elif kind == 'nxt':
            owner.data.nxt = ref
        elif kind == 'case':
            owner.data.cases[key] = ref
        elif kind == 'fork':
            owner.data.forks[key] = ref
        else:
            raise ValueError('Unsupported Master Sword incoming link: ' + kind)


def _action(chart, name, action, parameters=None, following=None):
    event = chart.event(name, 'ActionEvent')
    if event.data.actor_action.v.v != action:
        raise ValueError('Unexpected Master Sword action: ' + name)
    params = _params(event)
    if parameters and any(params.get(k) != v for k, v in parameters.items()):
        raise ValueError('Unexpected Master Sword parameters: ' + name)
    if following is not None and getattr(event.data.nxt.v, 'name', None) != following:
        raise ValueError('Unexpected Master Sword continuation: ' + name)
    return event


def _guard(chart, target, false, label):
    links = _predecessors(chart.chart, target)
    if not links:
        raise ValueError('Master Sword action is unreachable: ' + target.name)
    guard = chart.switch('RandoMasterSwordOwned_' + label, 'EventQueryIsExistInPouch',
                         {'Actor': SWORD, 'Num': 1}, target, false, actor='PouchSystemActor')
    _redirect(links, guard)
    return guard.name


def patch_flow(path, raw):
    """Patch one selected current flow after generic reward/collection edits.

    Returns (bytes, report). Deterministic on the same input; rejects repeated
    application and unexpected native actions. Verification can replay this over
    the original flow plus the same generic reward edits.
    """
    normalized = path.replace('.110.bfevfl.zs', '.bfevfl.zs')
    if normalized not in FLOWS:
        raise ValueError('Unknown Master Sword shuffle flow: ' + path)
    chart = _Chart(raw)
    if any(name.startswith('RandoMasterSword') for name in chart.events):
        raise ValueError('Master Sword shuffle already applied.')
    report = {'flow': path, 'guards': [], 'bypassed': []}
    if normalized == FLOWS[0]:
        # The generic source adapter has already replaced Actor; preserve it and
        # its collection marker. Arbitrary rewards must never be equipped.
        gift = _action(chart, 'Event115', 'EventTriggerAddOrRemovePouchContent',
                       {'Num': 1, 'IsEquipDIrect': True, 'IsGetEvent': False})
        if not isinstance(_params(gift).get('Actor'), str):
            raise ValueError('Missing pedestal reward actor.')
        gift.data.params.data['IsEquipDIrect'] = False
        chart.expected[gift.name]['IsEquipDIrect'] = False
        report['direct_equip'] = False
    elif normalized == FLOWS[1]:
        display = chart.event('Event117', 'SubFlowEvent')
        if (display.data.res_flowchart_name, display.data.entry_point_name, _params(display)) != (
                'GetPouchContent', 'DisplayGetByActorName', {'ActorName': SWORD}):
            raise ValueError('Unexpected pedestal sword display.')
        links = _predecessors(chart.chart, display)
        if [(owner.name, kind, key) for owner, kind, key in links] != [('Event136', 'nxt', None)]:
            raise ValueError('Unexpected pedestal display links.')
        # End only the display branch, retaining the timeline's sword animation.
        _redirect(links, display.data.nxt.v)
        report['bypassed'].append(display.name)
    elif normalized == FLOWS[2]:
        fallback = _action(chart, 'Event5', 'EventTriggerSetGameDataString64',
                           {'GameDataName': 'PlayerStatus.AnotherEraEquipWeapon', 'Value': SWORD}, 'Event13')
        report['guards'].append(_guard(chart, fallback, chart.events['Event13'], 'EraFallback'))
    elif normalized == FLOWS[3]:
        _action(chart, 'Event175', 'EventTriggerEquipmentUserRequestCreateStaticEquipment',
                {'EquipmentActorName': SWORD, 'DynamicEquipmentState': 2, 'IsActive': True}, 'Event12')
        unequip = _action(chart, 'Event165', 'EventPlayerUnequip', following='Event175')
        report['guards'].append(_guard(chart, unequip, chart.events['Event12'], 'AllSage'))
    elif normalized == FLOWS[4]:
        equip = _action(chart, 'Event37', 'EventTriggerEquipmentUserRequestCreateStaticEquipment',
                        {'EquipmentActorName': SWORD, 'DynamicEquipmentState': 2, 'IsActive': True}, 'Event484')
        report['guards'].append(_guard(chart, equip, chart.events['Event484'], 'Arrival'))
    else:
        # Dm_FinalBattle_0010 is intentionally untouched: Defeat_Ganon's native
        # Boss_GetMasterSword entry invokes it to recover the disarmed sword.
        # Its PlayerAddPouchAndEquip restores possession and deletes the ground
        # prop. The solver requires the shuffled sword before this battle.
        for name, resume, label in (('Event33', 'Event159', 'GanonIntro'),
                                    ('Event217', 'Event30', 'GanonExit')):
            equip = _action(chart, name, 'EventTriggerEquipmentUserRequestCreateStaticEquipment',
                            {'EquipmentActorName': SWORD, 'DynamicEquipmentState': 2, 'IsActive': True},
                            'Event66' if name == 'Event33' else 'Event30')
            # Event66 loops until the forced sword exists: missing ownership must
            # skip that wait and its RemoveWeaponKeepSheath as well.
            report['guards'].append(_guard(chart, equip, chart.events[resume], label))
    result, _ = chart.write()
    # Ensure every newly inserted ownership query survives writing with the
    # correct true/false polarity (native bool cases 0=true, 1=false).
    checked = _flow(result)
    guards = {e.name: e for e in checked.flowchart.events if e.name in report['guards']}
    if set(guards) != set(report['guards']) or any(
            e.data.actor_query.v.v != 'EventQueryIsExistInPouch' or
            _params(e) != {'Actor': SWORD, 'Num': 1} or set(e.data.cases) != {0, 1}
            for e in guards.values()):
        raise ValueError('Master Sword ownership guard failed serialization.')
    return result, report
