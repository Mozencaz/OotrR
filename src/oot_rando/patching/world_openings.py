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

**Kakariko gate open** (``open_kakariko`` = ``open``). The gate and its guard
(``Npc_Hylia_Soldier_003``) read ``Npc_Hylia_Soldier_003_GateOpen``, set when the
guard reads Zelda's Letter. The same scene moves ``Get_StoneOfFire`` to
``KakarikoVillageLetter``, the step from which the Death Mountain Trail, Goron City,
Darunia and Saria's Song steps follow: both start set. The quest is only requested
back from ``DoorOfTime`` (``KakarikoVillageNpc`` after Impa's send-off). The castle
and Door of Time quests are untouched: Zelda's Letter and the Song of Time keep
their own checks. Not validated in game.
"""
from oot_rando.patching import game_defaults, quest_guard

ZORA_QUEST = 'Get_StoneOfWater'
ZORA_STEP = 'Step_Get_StoneOfWater'
ZORA_FLOOR = 'Step07'
ZORA_FLOWS = ('Event/EventFlow/Get_StoneOfWater.bfevfl.zs',
              'Event/EventFlow/Dm_SY_BancChangeArrive.bfevfl.zs')

KAKARIKO_QUEST = 'Get_StoneOfFire'
KAKARIKO_FLOOR = 'KakarikoVillageLetter'
KAKARIKO_GATE = 'Npc_Hylia_Soldier_003_GateOpen'
KAKARIKO_FLOWS = ('Event/EventFlow/DoorOfTime.bfevfl.zs',)


def step_enum(challenge):
    return 'Step_' + challenge


def open_quest(read_flow, gamedata_raw, challenges_raw, quest, floor, flows, defaults=None):
    """Start ``quest`` at ``floor`` (plus ``defaults``) and guard ``flows`` against going back.

    ``read_flow(path)`` returns the current bytes of a flow (an earlier edit or the
    game's). Returns (gamedata bytes, {flow path: bytes}, report).
    """
    steps = quest_guard.challenge_steps(challenges_raw)
    values = dict(defaults or {}, **{step_enum(quest): floor})
    gamedata = game_defaults.set_new_game_defaults(gamedata_raw, values)
    edited, guarded = {}, {}
    for path in flows:
        edited[path], report = quest_guard.guard_regressions(read_flow(path), quest, steps, floor,
                                                             gamedata_raw=gamedata)
        if not report['guarded']:
            raise ValueError(f'{quest} guard: no request to guard in {path}')
        guarded[path] = report['guarded']
    expression = quest_guard.floor_expression(steps, quest, floor)
    return gamedata, edited, {'defaults': values, 'expression': expression, 'guarded': guarded}


def zora_fountain_open(read_flow, gamedata_raw, challenges_raw):
    """King Zora moved from the start (see module doc)."""
    return open_quest(read_flow, gamedata_raw, challenges_raw, ZORA_QUEST, ZORA_FLOOR, ZORA_FLOWS)


def kakariko_gate_open(read_flow, gamedata_raw, challenges_raw):
    """The Kakariko gate open from the start (see module doc)."""
    return open_quest(read_flow, gamedata_raw, challenges_raw, KAKARIKO_QUEST, KAKARIKO_FLOOR,
                      KAKARIKO_FLOWS, {KAKARIKO_GATE: True})


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
    and ``DoorOfTime`` is at ``Step06``; once ``AllSage`` has started a second request
    (node 3) takes over. The first one now runs while ``AllSage`` is before ``Ready``
    instead, so it works at any Door of Time step and both never run together.

    A node only computes the outputs flagged ``Is Output`` (every link of the vanilla
    modules reads one): node 5 flagged ``IsAfter`` alone, so ``IsBefore`` stayed false
    and the sword could still not be pulled before the stones (20/11). It is flagged
    too (several flagged outputs on one node are common in vanilla), and the gate's
    ``Queries`` and plug follow its new source. Not validated in game."""
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
        sources[0].update({'Node Index': 5, 'Output Index': 1})    # AllSage IsBefore Ready
        outputs[1]['Is Output'] = True
        # The node's query list and plug name the nodes it reads: node 5, no longer 2.
        plugs[0]['Node Index'] = 5
        gate['Queries'] = [5, 6]
    return _ainb_edit(raw, edit)


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


def gerudo_fortress_fast(read_flow, gamedata_raw, challenges_raw):
    """One carpenter to rescue (``gerudo_fortress`` = ``fast``).

    ``SageOfSpirit_RescueCarpenter`` adds one to ``…_NumOfCarpenterHelped`` at each
    rescue and plays ``Meet_FourCarpenter_ClearEvent`` (the Gerudo Membership Card,
    the fortress at peace) once it passes 3; ``…_Helped_02`` counts the carpenters
    left. A new game starts with three helped and one left, so the first rescue,
    whichever cell, ends the fortress. No flow is changed."""
    values = {CARPENTERS_HELPED: 3, CARPENTERS_LEFT: 1}
    return game_defaults.set_new_game_defaults(gamedata_raw, values), {}, {'defaults': values, 'guarded': {}}


SPIRIT_QUEST = 'SageOfSpirit'
BRIDGE_MODULE = 'Logic/GerudoValley_Adult_Prefab_9e43.logic.module.ainb'
BRIDGE_FLOOR = 'Step01'


def gerudo_valley_bridge(read_flow, gamedata_raw, challenges_raw):
    """The Gerudo Valley bridge repaired from the start (``open_gerudo_valley_bridge``).

    ``GerudoValley_Adult_Prefab_9e43`` shows the repaired bridge (and removes the two
    horse jumps) once ``SageOfSpirit`` is past ``Ready``: the head carpenter moves it
    to ``Step01`` when he stops the adult in front of the fortress, a talk with no
    item. A new game starts there. The carpenters, their cells and the card are not
    touched. No flow requests ``Ready``, so there is nothing to guard."""
    return open_quest(read_flow, gamedata_raw, challenges_raw, SPIRIT_QUEST, BRIDGE_FLOOR, ())


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
        extra = (lambda p: files.get(p) or read_module(p),) if opening is door_of_time_open else ()
        gamedata, edited, reports[option] = opening(current, gamedata, challenges_raw, *extra)
        files.update(edited)
    return gamedata, files, reports
