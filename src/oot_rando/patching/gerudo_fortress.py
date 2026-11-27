"""Keep fortress membership separate from the carpenter quest.

Native schedules, guard parameters and prison dialogue use the Spirit quest's
Step01 as a proxy for the card. Only those membership checks are replaced; the
quest itself still controls rescues, the bridge and the reward scene.
"""
import copy
import uuid

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.soul_adapter import murmur3
from oot_rando.patching.story_fixes import _Chart
from oot_rando.formats.evfl_tools import event_params_of

CARD = 'IsGet.Item_Token_Gerudo'
RESCUED = 'SageOfSpirit_IsAfter_Step01_Exp'
# Fast completion saves every carpenter; before it, this carpenter's own rescue is
# what completes the fortress. Unlike the Spirit quest step, it cannot become true
# merely by visiting the Colossus with the Requiem. (``WarpPointXX_ClearEvent`` is
# not a release flag: it places the leader, Npc_Gerudo_001, at the last cell.)
CELLS_RELEASED = 'GerudoFortress_Saved_Npc_Hylia_013_Adult'
CARPENTERS = tuple(f'Npc_Hylia_{i:03}_Adult' for i in range(13, 17))
NOT_STARTED = 'SageOfSpirit_IsNotAfter_Ready_EXP'
STEP_CHALLENGE = 'Work/Challenge/SageOfSpirit.game__challenge__Challenge.gyml'
SPIRIT_FLOW = 'Event/EventFlow/SageOfSpirit.bfevfl.zs'
# Logic modules of the fortress that read the Spirit quest's step (the card's proxy).
MEMBERSHIP_MODULES = (
    'GerudoFortress_Common_178b', 'GerudoFortress_Common_1d80', 'GerudoFortress_Common_58a8',
    'GerudoFortress_Common_Level_CarpenterSet_01_e139', 'GerudoFortress_Common_Level_CarpenterSet_02_9477',
    'GerudoFortress_Common_Level_CarpenterSet_03_c7f2', 'GerudoFortress_Common_Level_CarpenterSet_04_e9a4',
    'GerudoFortress_Level_Exterior_01_a401', 'GerudoFortress_Level_Room_02_5d06',
    'GerudoFortress_Level_Room_05_ee1c', 'GerudoFortress_Level_Room_06_1561',
    'GerudoFortress_Level_Room_06_ade9', 'MiniGame_HorsebackArchery_8380')
GUARD_FLOW = 'Event/EventFlow/Npc_Gerudo_013.bfevfl.zs'
UNLOCK_FLOW = 'Event/EventFlow/Common_Dungeon_OpenDoorChainLockMove.bfevfl.zs'
UNLOCK_ENTRIES = {f'GerudoFortress_OpenDoorChainLock_Npc_Hylia_{i}': f'Event{e}'
                  for i, e in (('013', 41), ('014', 42), ('015', 43), ('016', 44))}
CELL_MODULE = 'Logic/GerudoFortress_SwitchShutterSet_CarpenterSet_03_a01a.logic.module.ainb'
# Nodes of the cell module: the added CELLS_RELEASED read, and the chain lock and
# the shutter it deletes.
RELEASED, DELETED_ON_RELEASE = 10, (0, 3)
SCHEDULE_PACK = 'Pack/AIScheduleParam.pack.zs'
SCHEDULE_IDS = ('003_Adult', '004', '006', '007', '009', '010', '011', '012',
                '013', '014', '015', '016', '017', '018')
GUARD_IDS = ('001', '002', '002_Adult', '003_Adult', '004', '005', '006', '007',
             '008', '009', '010', '011', '012', '013', '014', '015', '016',
             '017', '018', '020', 'FortressGuard', 'GEN_SecurityGuard')
COMPOUNDS = ('GerudoFortress_GoToPrison_AND_Step01_Exp',
             'GerudoFortress_Npc_Gerudo_018_LookPrison_After_Step01')


def _compound_programs():
    # Preserve the native prison-state operands and the first expression's NOT.
    return {COMPOUNDS[0]: ([[0, 1034948124], [10, murmur3(RESCUED)], [5], [3]],
                           [[0, 1034948124], [0, murmur3(CARD)], [5], [3]]),
            COMPOUNDS[1]: ([[0, 1816465633], [10, murmur3(RESCUED)], [3]],
                           [[0, 1816465633], [0, murmur3(CARD)], [3]])}


def schedule_path(identifier):
    return f'Component/AIScheduleParam/Npc_Gerudo_{identifier}.game__component__AIScheduleParam.bgyml'


def membership_schedule(raw):
    doc = byml_codec.load(raw)
    changed = 0
    for schedule in doc['root'].get('ConditionalSchedule', ()):
        if schedule.get('ConditionFlag') == RESCUED:
            schedule['ConditionFlag'] = CARD
            changed += 1
    if changed != 1:
        raise ValueError('Unexpected Gerudo membership schedule (already patched?).')
    return byml_codec.dump(doc), {'conditions': changed}


def archery_schedule_pack(raw):
    files = sarc(raw)
    path = ('Component/AIScheduleParam/Minigame_HorsebackArchery_Ready_Npc_Gerudo_008'
            '.game__component__AIScheduleParam.bgyml')
    files[path], report = membership_schedule(files[path])
    return byml_codec.build_sarc(files), report


def guard_pack(raw):
    files = sarc(raw)
    base = 'GameParameter/SecurityGuardParam/Npc_Gerudo_W_Normal_SecurityGuard.game__npc__SecurityGuardParam.bgyml'
    reference = f'Work/GameData/Entity/{CARD}.gmdentity.json?{CARD}'
    if base in files:
        doc = byml_codec.load(files[base])
        alert = doc['root']['AlertMode']
        if alert.get('FoundPlayerWhenSmallHitGDName', '').split('?')[-1] != RESCUED:
            raise ValueError('Unexpected Gerudo guard card condition (already patched?).')
        alert['FoundPlayerWhenSmallHitGDName'] = reference
        files[base] = byml_codec.dump(doc)
    # Threats are ignored before the boss is spoken to (``Ready``): they must react until
    # the card is held instead. Several guards carry their own copy of the interests.
    changed = 0
    for path in sorted(files):
        if '/InterestReceiveParam/' not in path or NOT_STARTED.encode() not in files[path]:
            continue
        doc = byml_codec.load(files[path])
        count = 0
        for entry in doc['root']['StrongInterests']:
            if entry.get('ExcludeConditionGdName', '').split('?')[-1] == NOT_STARTED:
                entry['ExcludeConditionGdName'] = reference
                count += 1
        if count != 11:
            raise ValueError('Unexpected Gerudo guard interests.')
        files[path] = byml_codec.dump(doc)
        changed += count
    if base not in files and not changed:
        raise ValueError('Unexpected Gerudo guard pack (already patched?).')
    return byml_codec.build_sarc(files), {'card': CARD, 'interests': changed}


def _card_node(index, parent, inputs, outputs, queries, name):
    guid = str(uuid.uuid5(uuid.UUID(parent['GUID']), f'fortress-card-{index}'))
    return {'Node Type': 'UserDefined', 'Node Index': index, 'Name': name, 'GUID': guid,
            'Flags': ['Is Query'], 'Queries': queries, 'Attachments': [], 'Properties': {},
            'Parameters': {'Inputs': inputs, 'Outputs': outputs}, 'XLink Actions': [], 'Plugs': {}}


def membership_module(raw):
    """A fortress logic module asking the Spirit quest step asks for the card instead.

    ``IsAfter`` of ``Step01`` becomes the card; ``IsBefore`` / ``IsEqual`` (fortress
    still hostile, boss spoken to or not) become its negation, an ``OperateOR`` whose
    first output is the inverse. Returns (bytes, report)."""
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    doc = ainb.AINB.from_binary(raw).as_dict()
    nodes = doc['Nodes']

    def strings(node):
        return {p['Name']: p['Default Value'] for p in node.get('Parameters', {}).get('Inputs', {}).get('String', ())}
    targets = [n['Node Index'] for n in nodes if
               (n['Name'] == 'HoldChallengeCurrentStepCheckOrder'
                and strings(n) == {'ChallengeName': STEP_CHALLENGE, 'ChallengeStepName': 'Step01'})
               or (n['Name'] == 'HoldGameDataGetBoolExpSimple' and strings(n) == {'GameDataNameBoolExp': RESCUED})]
    if not targets:
        raise ValueError('Unexpected Gerudo membership module (already patched?).')
    for index in targets:
        target = nodes[index]
        steps = target['Name'] == 'HoldChallengeCurrentStepCheckOrder'
        readers = [(node, entry, source) for node in nodes
                   for inputs in node.get('Parameters', {}).get('Inputs', {}).values()
                   for entry in inputs for source in entry.get('Sources') or [entry]
                   if source.get('Node Index') == index]
        negated = [r for r in readers if steps and r[2].get('Output Index') in (1, 2)]
        target['Name'] = 'HoldGameDataGetBoolSimple'
        target['Parameters'] = {'Inputs': {
            'Int': [{'Name': 'GameDataArrayIndex', 'Default Value': -1, 'Node Index': -1,
                     'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}],
            'String': [{'Name': 'GameDataNameBool', 'Default Value': CARD, 'Node Index': -1,
                        'Output Index': 0, 'Flags': ['Uses Default']}]},
            'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}}
        if not negated:
            continue
        inverse = len(nodes)
        nodes.append(_card_node(inverse, target, {'Bool': [
            {'Name': 'BoolMulti', 'Default Value': False,
             'Sources': [{'Node Index': index, 'Output Index': 0, 'Flags': []}]},
            {'Name': 'UpdateOnce', 'Default Value': False, 'Node Index': -1, 'Output Index': 0,
             'Flags': ['Uses Default', 'Is Output']}]},
            {'Bool': [{'Name': 'False', 'Is Output': True}, {'Name': 'True', 'Is Output': False}]},
            [index], 'OperateOR'))
        nodes[-1]['Plugs'] = {'Generic': [{'Node Index': index, 'Name': 'BoolMulti'}]}
        for node, entry, source in negated:
            source.update({'Node Index': inverse, 'Output Index': 0})
        for node in {id(r[0]): r[0] for r in negated}.values():
            if any(s.get('Node Index') == index
                   for inputs in node['Parameters']['Inputs'].values() for e in inputs
                   for s in e.get('Sources') or [e]):
                raise ValueError('Unexpected Gerudo membership wiring.')
            node['Queries'] = [inverse if q == index else q for q in node['Queries']]
            node['Plugs'] = {kind: [dict(plug, **{'Node Index': inverse}) if plug['Node Index'] == index else plug
                                    for plug in plugs]
                             for kind, plugs in node.get('Plugs', {}).items()}
    result = ainb_to_binary(copy.deepcopy(doc))
    if ainb.AINB.from_binary(result).as_dict() != doc:
        raise ValueError('Fortress membership module wrongly rewritten.')
    return result, {'checks': targets, 'card': CARD}


def resource_fixes():
    return (*((schedule_path(i), membership_schedule) for i in SCHEDULE_IDS),
            (SCHEDULE_PACK, archery_schedule_pack),
            *((f'Pack/Actor/Npc_Gerudo_{i}.pack.zs', guard_pack) for i in GUARD_IDS),
            *((f'Logic/{m}.logic.module.ainb', membership_module) for m in MEMBERSHIP_MODULES))


def membership_expressions(raw):
    doc = byml_codec.load(raw)
    entries = {int(e['Hash']): e for e in doc['root']['Data']['BoolExp']}
    if murmur3(CARD) not in {int(e['Hash']) for e in doc['root']['Data']['Bool']}:
        raise ValueError('Gerudo Membership Card flag missing.')
    for name, (original, patched) in _compound_programs().items():
        entry = entries.get(murmur3(name))
        if entry is None or entry['Values'] != original:
            raise ValueError('Unexpected Gerudo prison expression: ' + name)
        entry['Values'] = [[byml_codec.U64(v) for v in op] for op in patched]
    return byml_codec.dump(doc), {'expressions': list(COMPOUNDS), 'card': CARD}


def expressions_applied(raw):
    entries = {int(e['Hash']): e for e in byml_codec.load(raw)['root']['Data']['BoolExp']}
    return all(entries.get(murmur3(name), {}).get('Values') == patched
               for name, (_, patched) in _compound_programs().items())


def membership_flow(raw, names):
    from evfl.util import make_rindex
    flow = _Chart(raw)
    for name in names:
        event = flow.event(name, 'SwitchEvent')
        if (event_params_of(event) != {'GameDataName': RESCUED}
                or event.data.actor_query.v.v != 'EventQueryIsGameDataBoolExp'):
            raise ValueError('Unexpected Gerudo membership dialogue: ' + name)
        event.data.actor_query = make_rindex(
            flow.holder(event.data.actor.v.queries, 'EventQueryIsGameDataBool'))
        event.data.params.data = {'GameDataName': CARD, 'Index': -1}
        flow.expected[name] = dict(event.data.params.data)
    result, _ = flow.write()
    return result, {'checks': list(names), 'card': CARD}


def free_remaining_carpenters(raw):
    """Run after the reward cutscene, before advancing the quest to Step02."""
    from evfl.util import make_index
    flow = _Chart(raw)
    before = flow.event('Event192', 'ActionEvent')
    step = flow.event('Event146', 'ActionEvent')
    if before.data.nxt.v is not step or event_params_of(step).get('StepName') != 'Step02':
        raise ValueError('Unexpected fortress completion sequence.')
    following = step
    # ``Saved`` is what a native rescue writes (``StepCheck_Clear``): the cell's
    # carpenter is deleted by it and his escaped copy appears outside. Without it
    # the other carpenters stayed behind their opened cells.
    flags = [f'GerudoFortress_Saved_{c}' for c in CARPENTERS]
    flags += [f'GerudoFortress_IsAfterHelpCarpenter_{c}' for c in CARPENTERS]
    # A cell's thief only appears in an event played with its carpenter, who is
    # gone now: her key (a check) would be lost. Defeated, the key lies in the
    # cell until picked up (``Destroy`` and not ``IsGet_SmallKey…``), and
    # neither the thief nor her battle event is created any more.
    flags += [f'GerudoFortress_DestroyGerudoThief_{c}' for c in CARPENTERS]
    # ``WarpPointXX_ClearEvent`` stays native (the cell rescued last): each one
    # creates the leader at its cell and places the reward cutscene there.
    for i, flag in reversed(list(enumerate(flags))):
        following = flow.set_bool(f'RandoFreeCarpenters{i}', flag, True, following)
    before.data.nxt = make_index(following)
    result, _ = flow.write()
    return result, {'freed': flags}


def skip_completed_unlocks(raw):
    """A released cell must not replay its rescue.

    The cell shutter plays its unlock entry (``OpenChainEvent``) when asked to
    open. Once the fortress is released the event ends at once: its native part
    is the rescue and the reward. The released cells themselves lose their lock
    and door (``open_completed_cells``), so nothing asks for the event any more."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entries = {e.name: e for e in flow.chart.entry_points}
    for index, (entry, first) in enumerate(sorted(UNLOCK_ENTRIES.items())):
        point = entries.get(entry)
        if point is None or point.main_event.v is not flow.event(first, 'ActionEvent'):
            raise ValueError('Unexpected cell unlock flow (already patched?).')
        # Flag true (case 0): end the flow; flag false: the native unlock and rescue.
        guard = flow.switch(f'RandoSkipUnlock{index}', 'EventQueryIsGameDataBool',
                            {'GameDataName': CELLS_RELEASED, 'Index': -1}, None, point.main_event.v)
        point.main_event = make_index(guard)
    result, _ = flow.write()
    return result, {'entries': sorted(UNLOCK_ENTRIES)}


def open_completed_cells(raw):
    """Remove the chain lock and the door of every cell once the fortress is released.

    Natively a cell only opens through its unlock event, which the shutter plays
    when the player works the chain of a cell whose thief is defeated
    (``OpenKey`` is that one-frame request): neither a held nor a pulsed key
    opened the cell. ``Logic_Delete`` is a held state, the input this module
    already uses for its navmesh cut, so released cells are open at every load
    without an event or a key."""
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    doc = ainb.AINB.from_binary(raw).as_dict()
    nodes = doc['Nodes']
    if len(nodes) != 10 or nodes[0]['Name'] != 'ActorLogicDoorChainLock' or nodes[3]['Name'] != 'ActorLogicSwitchShutter':
        raise ValueError('Unexpected fortress cell lock module (already patched?).')
    guid = str(uuid.uuid5(uuid.UUID(nodes[0]['GUID']), f'completed-cell-{RELEASED}'))
    nodes.append({'Node Type': 'UserDefined', 'Node Index': RELEASED, 'Name': 'HoldGameDataGetBoolSimple',
                  'GUID': guid, 'Flags': ['Is Query'], 'Queries': [], 'Attachments': [], 'Properties': {},
                  'Parameters': {'Inputs': {
                      'Int': [{'Name': 'GameDataArrayIndex', 'Default Value': -1, 'Node Index': -1,
                               'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}],
                      'String': [{'Name': 'GameDataNameBool', 'Default Value': CELLS_RELEASED,
                                  'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default']}]},
                      'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}},
                  'XLink Actions': [], 'Plugs': {}})
    for target in DELETED_ON_RELEASE:
        actor = nodes[target]
        entry = next(v for v in actor['Parameters']['Inputs']['Bool'] if v['Name'] == 'Logic_Delete')
        if entry['Node Index'] != -1:
            raise ValueError('Unexpected cell Logic_Delete wiring.')
        # Linked as the navmesh cut's own Logic_Delete (node 4) is.
        entry.update({'Node Index': RELEASED, 'Output Index': 0, 'Flags': []})
        actor['Queries'].append(RELEASED)
        actor['Plugs']['Generic'].append({'Node Index': RELEASED, 'Name': 'Logic_Delete'})
    result = ainb_to_binary(copy.deepcopy(doc))
    if ainb.AINB.from_binary(result).as_dict() != doc:
        raise ValueError('Fortress cell lock module wrongly rewritten.')
    return result
