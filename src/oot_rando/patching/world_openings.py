"""World openings: zones open from the start of a new game.

Each opening is the pair of building blocks of the remake's story:

* new-game defaults in the GameData list (:mod:`oot_rando.patching.game_defaults`),
  read by the game before any flow runs. A quest's current step is the saved enum
  ``Step_<Challenge>`` (every quest starts at ``NotReady``);
* a quest floor guard (:mod:`oot_rando.patching.quest_guard`) on every flow that
  would request an earlier step of the same quest, so the opening cannot close again.
  The flows listed for each opening are the only ones of the 914 flows of 1.1.1 that
  request such a step (checked by the tests against the dump).

**Zora's Fountain open** (``zora_fountain`` = ``open``). King Zora's position follows
``Get_StoneOfWater``. ``Step07`` is the step after he read Ruto's Letter (moved
aside). The quest is requested from ``Get_StoneOfWater`` (the diving game, the letter
found and read, the quest scenes) and ``Dm_SY_BancChangeArrive`` (the first arrival
in Zora's Domain, ``Step03`` / ``Step03_Impa``). Later steps (Jabu-Jabu, the Zora
Sapphire) are untouched. Ruto's Letter can no longer be delivered: the logic never
counts it as a bottle.
The invisible wall behind the king separately reads
``HavePlayedEvent.Dm_Zora_0010`` (the moving-aside scene), so that saved flag also
starts true. Moving the quest alone leaves the wall in place.

**Kakariko gate open** (``open_kakariko`` = ``open``). The guard
(``Npc_Hylia_Soldier_003``) reads ``Npc_Hylia_Soldier_003_GateOpen``, set when the
guard reads Zelda's Letter. Every seed patches the child gate to follow that flag
too, so later Goron quest progress cannot open a closed gate. The same scene moves ``Get_StoneOfFire`` to
``KakarikoVillageLetter``, the step from which the Death Mountain Trail, Goron City,
Darunia and Saria's Song steps follow: both start set. The quest is only requested
back from ``DoorOfTime`` (``KakarikoVillageNpc`` after Impa's send-off). The castle
and Door of Time quests are untouched: Zelda's Letter and the Song of Time keep
their own checks. Not validated in game.
"""
from oot_rando.patching import game_defaults, quest_guard
from oot_rando.logic.rando_options import escape_requirement

ZORA_QUEST = 'Get_StoneOfWater'
ZORA_STEP = 'Step_Get_StoneOfWater'
ZORA_FLOOR = 'Step07'
ZORA_MOVED = 'HavePlayedEvent.Dm_Zora_0010'
ZORA_FLOWS = ('Event/EventFlow/Get_StoneOfWater.bfevfl.zs',
              'Event/EventFlow/Dm_SY_BancChangeArrive.bfevfl.zs')

KAKARIKO_QUEST = 'Get_StoneOfFire'
KAKARIKO_FLOOR = 'KakarikoVillageLetter'
KAKARIKO_GATE = 'Npc_Hylia_Soldier_003_GateOpen'
KAKARIKO_FLOWS = ('Event/EventFlow/DoorOfTime.bfevfl.zs',)


def step_enum(challenge):
    return 'Step_' + challenge


def open_quest(read_flow, gamedata_raw, challenges_raw, quest, floor, flows, defaults=None,
               prefix=quest_guard.PREFIX):
    """Start ``quest`` at ``floor`` (plus ``defaults``) and guard ``flows`` against going back.

    ``read_flow(path)`` returns the current bytes of a flow (an earlier edit or the
    game's). Returns (gamedata bytes, {flow path: bytes}, report).
    A custom ``prefix`` is recorded so verification can reconstruct the same guards.
    """
    steps = quest_guard.challenge_steps(challenges_raw)
    values = dict(defaults or {}, **{step_enum(quest): floor})
    gamedata = game_defaults.set_new_game_defaults(gamedata_raw, values)
    edited, guarded = {}, {}
    for path in flows:
        edited[path], report = quest_guard.guard_regressions(read_flow(path), quest, steps, floor,
                                                             gamedata_raw=gamedata, prefix=prefix)
        if not report['guarded']:
            raise ValueError(f'{quest} guard: no request to guard in {path}')
        guarded[path] = report['guarded']
    expression = quest_guard.floor_expression(steps, quest, floor)
    report = {'defaults': values, 'expression': expression, 'guarded': guarded}
    if prefix != quest_guard.PREFIX:
        report['prefix'] = prefix
    return gamedata, edited, report


def zora_fountain_open(read_flow, gamedata_raw, challenges_raw):
    """King Zora moved from the start (see module doc)."""
    return open_quest(read_flow, gamedata_raw, challenges_raw, ZORA_QUEST, ZORA_FLOOR,
                      ZORA_FLOWS, {ZORA_MOVED: True})


def kakariko_gate_open(read_flow, gamedata_raw, challenges_raw):
    """The Kakariko gate open from the start (see module doc)."""
    return open_quest(read_flow, gamedata_raw, challenges_raw, KAKARIKO_QUEST, KAKARIKO_FLOOR,
                      KAKARIKO_FLOWS, {KAKARIKO_GATE: True})


KAKARIKO_CLOSED_MODULE = 'Logic/KakarikoVillage_Child_OpenGate_Prefab_1fcc.logic.module.ainb'
KAKARIKO_OPEN_MODULE = 'Logic/KakarikoVillage_Child_GateClose_Prefab_6b8b.logic.module.ainb'


def kakariko_gate_on_letter(raw, opened):
    """Choose the child gate's position by letter delivery, independently of quest steps.

    Despite the prefab names, OpenGate contains the initially closed, moving gate;
    GateClose contains the gate at its open position. Keep their movement logic.
    The guard and Dm_Kakariko_0010 already set KAKARIKO_GATE during delivery.
    """
    import copy
    import uuid

    def edit(nodes):
        if len(nodes) != 3:
            raise ValueError('Unexpected Kakariko gate node count')
        check = _node(nodes, 2, 'HoldChallengeCurrentStepCheckOrder')
        strings = {i['Name']: i['Default Value'] for i in check['Parameters']['Inputs']['String']}
        step = 'KakarikoVillageLetter' if opened else 'DeathMtTrailIn'
        if strings != {'ChallengeName': 'Work/Challenge/Get_StoneOfFire.game__challenge__Challenge.gyml',
                       'ChallengeStepName': step}:
            raise ValueError('Unexpected Kakariko gate quest condition')
        actor = _node(nodes, 1, 'ActorLogicAttackBootUpActor')
        entry = _bool_input(actor, 'Logic_Create')
        if (entry['Node Index'], entry['Output Index']) != (2, 0 if opened else 1):
            raise ValueError('Unexpected Kakariko gate wiring')
        flag = copy.deepcopy(check)
        flag.update({'Node Index': 3, 'Name': 'HoldGameDataGetBoolSimple',
                     'GUID': str(uuid.uuid5(uuid.NAMESPACE_URL, 'oot-rando/kakariko-gate/' + step)),
                     'Queries': [], 'Plugs': {},
                     'Parameters': {
                         'Inputs': {
                             'Int': [{'Name': 'GameDataArrayIndex', 'Default Value': -1, 'Node Index': -1,
                                      'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}],
                             'String': [{'Name': 'GameDataNameBool', 'Default Value': KAKARIKO_GATE,
                                         'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default']}]},
                         'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}}})
        nodes.append(flag)
        check.update({'Name': 'OperateAND', 'Queries': [3],
                      'Plugs': {'Generic': [{'Node Index': 3, 'Name': 'BoolMulti'}]},
                      'Parameters': {
                          'Inputs': {'Bool': [
                              {'Name': 'BoolMulti', 'Default Value': False, 'Node Index': 3,
                               'Output Index': 0, 'Flags': []},
                              {'Name': 'UpdateOnce', 'Default Value': False, 'Node Index': -1,
                               'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}]},
                          'Outputs': {'Bool': [{'Name': 'False', 'Is Output': not opened},
                                               {'Name': 'True', 'Is Output': opened}]}}})
        entry['Output Index'] = 1 if opened else 0
    result = _ainb_edit(raw, edit)
    return result, {'flag': KAKARIKO_GATE, 'opened_position': opened}


DOOR_MODULE = 'Logic/Market_Common_f252.logic.module.ainb'
PEDESTAL_MODULE = 'Logic/Market_Child_Prefab_e700.logic.module.ainb'
DOOR_FLOW = 'Event/EventFlow/DoorOfTime.bfevfl.zs'
DOOR_QUEST = 'DoorOfTime'
DOOR_COMPLETE_ONLY_AFTER = 'DoorOfTime_IsAfter_Step05_Exp'
DOOR_PREFIX = 'RandoDoorComplete_'


def _ainb_edit(raw, edit):
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    edit(document['Nodes'])
    return ainb_to_binary(document)


def _node(nodes, index, name):
    node = next((n for n in nodes if n.get('Node Index') == index), None)
    if node is None or node.get('Name') != name:
        raise ValueError(f'Unexpected logic module: node {index} is not {name}')
    return node


def _bool_input(node, name):
    found = [i for i in node['Parameters']['Inputs']['Bool'] if i['Name'] == name]
    if len(found) != 1:
        raise ValueError(f'Unexpected logic module: no single input {name} on {node["Name"]}')
    return found[0]


def door_always_open(raw):
    """``Market_Common_f252``: the Door of Time stays open (no opening scene).

    The ``ActorLogicGateDoor`` (node 3) opens when its ``isOpen`` input is true:
    vanilla wires it to an OR of the opening scene and ``DoorOfTime`` at ``Step06``
    (the Song of Time played at the door). ``isOpen`` and ``IsSkipAnim`` now use a
    true default, like the node's own ``isClose``."""
    def edit(nodes):
        door = _node(nodes, 3, 'ActorLogicGateDoor')
        _node(nodes, 5, 'OperateORFixInputTrue')
        flags = list(_bool_input(door, 'isClose')['Flags'])
        for name in ('isOpen', 'IsSkipAnim'):
            entry = _bool_input(door, name)
            if (entry['Node Index'], entry['Output Index']) != (5, 1):
                raise ValueError('Unexpected Door of Time wiring: ' + name)
            entry.update({'Default Value': True, 'Node Index': -1, 'Output Index': 0, 'Flags': list(flags)})
    return _ainb_edit(raw, edit)


def pedestal_before_sages(raw):
    """``Market_Child_Prefab_e700``: the first sword pull no longer waits for ``Step06``.

    The child pulls the sword (event request, node 0) when he acts on the pedestal
    and ``DoorOfTime`` is at ``Step06``; a second request (node 3) takes over when
    node 5 reports ``AllSage IsAfter Ready``. The first request now uses the exact
    inverse of that same output. ``IsBefore Ready`` previously left a gap at Ready:
    the prompt appeared, but neither event was requested on pressing the action.
    Reusing node 2 as the native InvBool module makes both branches complementary,
    including an inactive quest, without assuming strict/inclusive step semantics.
    Physical in-game validation remains necessary."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    def edit(nodes):
        gate = _node(nodes, 1, 'OperateAND')
        _node(nodes, 2, 'HoldChallengeCurrentStepCheckOrder')
        sages = _node(nodes, 5, 'HoldChallengeCurrentStepCheckOrder')
        if 'AllSage' not in sages['Parameters']['Inputs']['String'][0]['Default Value']:
            raise ValueError('Unexpected pedestal module: node 5 is not AllSage')
        sources = _bool_input(gate, 'BoolMulti')['Sources']
        if [(s['Node Index'], s['Output Index']) for s in sources] != [(2, 2), (6, 2)]:
            raise ValueError('Unexpected pedestal module wiring')
        outputs = sages['Parameters']['Outputs']['Bool']
        if [o['Name'] for o in outputs] != ['IsAfter', 'IsBefore', 'IsEqual']:
            raise ValueError('Unexpected pedestal module: AllSage outputs')
        plugs = gate.get('Plugs', {}).get('Generic', [])
        if [(p['Node Index'], p['Name']) for p in plugs] != [(2, 'BoolMulti')] or gate.get('Queries') != [2, 6]:
            raise ValueError('Unexpected pedestal module: gate plugs')
        repeat = _node(nodes, 4, 'OperateAND')
        if [(s['Node Index'], s['Output Index']) for s in _bool_input(repeat, 'BoolMulti')['Sources']] != [
                (5, 0), (6, 2)] or not outputs[0]['Is Output']:
            raise ValueError('Unexpected repeat pedestal module wiring')
        inverse = nodes[2]
        inverse['Name'] = 'InvBool.module'
        inverse['Flags'] = ['Is Query', 'Is Module']
        inverse['Queries'] = [5]
        inverse['Parameters'] = {
            'Inputs': {'Bool': [
                {'Name': 'BoolMulti', 'Default Value': False, 'Node Index': 5, 'Output Index': 0, 'Flags': []},
                {'Name': 'UpdateOnce', 'Default Value': False, 'Node Index': -1, 'Output Index': 0,
                 'Flags': ['Uses Default', 'Is Output']}]},
            'Outputs': {'Bool': [{'Name': 'InvBool', 'Is Output': True}]}}
        inverse['Plugs'] = {'Generic': [{'Node Index': 5, 'Name': 'BoolMulti'}]}
        sources[0]['Output Index'] = 0
    edit(document['Nodes'])
    document['Modules'].append({'Path': 'InvBool.module.ainb', 'Category': 'Logic', 'Instance Count': 1})
    result = ainb_to_binary(copy.deepcopy(document))
    if ainb.AINB.from_binary(result).as_dict() != document:
        raise ValueError('Child pedestal module wrongly rewritten.')
    return result


def door_of_time_open(read_flow, gamedata_raw, challenges_raw, read_module):
    """The Door of Time open from the start.

    Every seed already lets the Song of Time open the door before Zelda's escape, frees
    the first sword pull and keeps ``DoorOfTime`` from completing before ``Step05``
    (:func:`oot_rando.patching.story_fixes.door_song_before_escape`, applied before the
    openings). Here the door module is freed too and a new game starts with the door
    saved as opened (``Market_Child_TimeTempleDoor_Opened``): the song scene is not
    asked for, and ``Step06`` follows the escape at once. Returns (gamedata bytes,
    {path: bytes}, report)."""
    from oot_rando.patching.story_fixes import DOOR_OPENED
    values = {DOOR_OPENED: True}
    gamedata = game_defaults.set_new_game_defaults(gamedata_raw, values)
    files = {DOOR_MODULE: door_always_open(read_module(DOOR_MODULE))}
    return gamedata, files, {'modules': [DOOR_MODULE], 'defaults': values, 'guarded': {}}


CARPENTERS_HELPED = 'GerudoFortress_Meet_FourCarpenter_NumOfCarpenterHelped'
CARPENTERS_LEFT = 'GerudoFortress_Meet_FourCarpenter_NumOfCarpenterHelped_02'


def gerudo_fortress_fast(read_flow, gamedata_raw, challenges_raw, read_module=None):
    """One carpenter to rescue (``gerudo_fortress`` = ``fast``).

    ``SageOfSpirit_RescueCarpenter`` adds one to ``…_NumOfCarpenterHelped`` at each
    rescue and plays ``Meet_FourCarpenter_ClearEvent`` (the Gerudo Membership Card,
    the fortress at peace) once it passes 3; ``…_Helped_02`` counts the carpenters
    left. A new game starts with three helped and one left, so the first rescue,
    whichever cell, ends the fortress. Completion releases the other carpenters
    and opens all cell locks so their jars remain reachable; their thieves
    count as defeated so that each key (a check) lies in its cell."""
    from oot_rando.patching import gerudo_fortress as g
    values = {CARPENTERS_HELPED: 3, CARPENTERS_LEFT: 1}
    flow, freed = g.free_remaining_carpenters(read_flow(g.SPIRIT_FLOW))
    unlock, _ = g.skip_completed_unlocks(read_flow(g.UNLOCK_FLOW))
    files = {g.SPIRIT_FLOW: flow, g.UNLOCK_FLOW: unlock, g.CELL_MODULE: g.open_completed_cells((read_module or read_flow)(g.CELL_MODULE))}
    return game_defaults.set_new_game_defaults(gamedata_raw, values), files, {
        'defaults': values, 'guarded': {}, 'freed': freed, 'modules': [g.CELL_MODULE], 'unlock_flow': g.UNLOCK_FLOW}


BRIDGE_MODULE = 'Logic/GerudoValley_Adult_Prefab_9e43.logic.module.ainb'


def gerudo_valley_bridge(read_flow, gamedata_raw, challenges_raw, read_module):
    """The Gerudo Valley bridge repaired from the start (``open_gerudo_valley_bridge``).

    Select the repaired actor and disable the broken actor and horse jumps directly.
    A quest default alone does not repair existing saves, and Step01 is the very
    threshold tested by the native bridge. Leave the carpenter quest unchanged.
    """
    def edit(nodes):
        query = _node(nodes, 2, 'HoldGameDataGetBoolExpSimple')
        if query['Parameters']['Inputs']['String'][0]['Default Value'] != 'SageOfSpirit_IsAfter_Step01_Exp':
            raise ValueError('Unexpected Gerudo bridge quest condition')
        selector = _node(nodes, 3, 'OperateAND')
        entry = _bool_input(selector, 'BoolMulti')
        if (entry['Node Index'], entry['Output Index']) != (2, 0):
            raise ValueError('Unexpected Gerudo bridge selector')
        for index, output in ((0, 0), (1, 1), (4, 0), (5, 0)):
            actor = _node(nodes, index, 'ActorLogicSimpleActor')
            if (_bool_input(actor, 'Logic_Create')['Node Index'],
                    _bool_input(actor, 'Logic_Create')['Output Index']) != (3, output):
                raise ValueError('Unexpected Gerudo bridge actor wiring')
        entry.update({'Default Value': True, 'Node Index': -1, 'Output Index': 0,
                      'Flags': ['Uses Default', 'Is Output']})
        selector['Queries'] = []
        selector['Plugs'] = {}
    raw = _ainb_edit(read_module(BRIDGE_MODULE), edit)
    return gamedata_raw, {BRIDGE_MODULE: raw}, {'modules': [BRIDGE_MODULE], 'defaults': {}, 'guarded': {}}


# The native castle-bridge area exists exactly at DoorOfTime Step03. No-stone
# seeds start there; later castle visits must not move the quest backwards.
ESCAPE_QUEST = 'DoorOfTime'
ESCAPE_FLOOR = 'Step03'
# DoorOfTime also carries the Kakariko floor guards. Keep their names distinct.
ESCAPE_PREFIX = 'RandoZeldaEscapeFloor_'
ESCAPE_FLOWS = ('Event/EventFlow/Goto_HyruleCastle.bfevfl.zs',
                'Event/EventFlow/DoorOfTime.bfevfl.zs',
                'Event/EventFlow/Npc_Hylia_Zelda_Child.bfevfl.zs',
                'Event/EventFlow/Dm_SY_Ocarina_SariaSong.bfevfl.zs')


def zelda_escape_ready(read_flow, gamedata_raw, challenges_raw):
    """Make the native bridge escape available on a new game's first visit."""
    from oot_rando.patching.story_fixes import BRIDGE_CLOSED
    return open_quest(read_flow, gamedata_raw, challenges_raw, ESCAPE_QUEST, ESCAPE_FLOOR,
                      ESCAPE_FLOWS, {BRIDGE_CLOSED: True, 'DoorOfTime_GetStoneCount': 0},
                      prefix=ESCAPE_PREFIX)


# option name, value -> opening (applied in this order by the seed build).
OPENINGS = (('zora_fountain', 'open', zora_fountain_open),
            ('open_kakariko', 'open', kakariko_gate_open),
            ('open_door_of_time', True, door_of_time_open),
            ('gerudo_fortress', 'fast', gerudo_fortress_fast),
            ('open_gerudo_valley_bridge', True, gerudo_valley_bridge))


def apply_openings(options, read_flow, gamedata_raw, challenges_raw, read_module=None):
    """Every opening the options ask for.

    ``read_module(path)`` returns the bytes of a logic module (AINB, not compressed).
    Returns (gamedata bytes, {path: bytes}, {option: report})."""
    files, reports, gamedata = {}, {}, gamedata_raw
    for option, value, opening in OPENINGS:
        if options.get(option) != value:
            continue
        current = lambda p: files.get(p) or read_flow(p)
        extra = ((lambda p: files.get(p) or read_module(p),)
                 if opening in (door_of_time_open, gerudo_valley_bridge, gerudo_fortress_fast) else ())
        gamedata, edited, reports[option] = opening(current, gamedata, challenges_raw, *extra)
        files.update(edited)
    if escape_requirement(options) == 'song':
        current = lambda p: files.get(p) or read_flow(p)
        gamedata, edited, reports['zelda_escape'] = zelda_escape_ready(current, gamedata, challenges_raw)
        files.update(edited)
    return gamedata, files, reports
