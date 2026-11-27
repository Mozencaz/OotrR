from oot_rando.formats.evfl_tools import event_params_of, params_by_event, parse_flow
"""Child Hyrule Castle made optional (``skip_child_zelda``).

A new game starts in the state the castle leaves behind in vanilla: Malon met,
Talon woken, Zelda met, Impa's send-off done.

* **Quests.** The opening (right after its own ``Meet_DekuTree`` request, see
  :data:`OPENING_ANCHOR`) replays, in the vanilla order, the native requests that
  move them. ``Goto_HyruleCastle`` goes to ``Step01`` (Deku Tree escape) and then to
  ``Complete`` (Zelda). ``DoorOfTime`` goes to ``Step01`` (Zelda) and then to
  ``Step02`` (Impa's send-off). ``Get_StoneOfFire`` goes to ``KakarikoVillageNpc``
  (the send-off too). Each request is a copy of its native event, parameter for
  parameter, with the progress banner hidden.
* **Saved flags.** ``Talon_AfterWakeUp`` and ``HavePlayedEvent.Dm_HrlCastle_0020`` are
  set by Talon's wake-up scene. That scene also clears ``HyruleCastle_IsMalonAppear``,
  so the first Malon is gone. ``HavePlayedEvent.Dm_MelodyGet_Zelda`` is set by
  Impa's song. Impa's send-off flag (``Dm_HrlField_0020``) is already set at the start
  of every seed (:data:`oot_rando.patching.story_fixes.CLOCK_FLAG`).
* **Nothing goes back.** The castle flows still request earlier steps: Kaepora's
  first field talk (``Step02``), the castle scenes (``Step03``, ``Step03_02``) and
  Talon's wake-up (``Step04``). Each of these requests is now skipped once
  ``Goto_HyruleCastle`` is complete. Zelda's ``DoorOfTime`` ``Step01`` is skipped once
  the quest is past it. The market arrival's ``Step02_01`` already has its guard
  (:func:`oot_rando.patching.story_fixes.first_arrival_forward`).

The castle's own checks never play any more: Zelda's Letter and Zelda's Lullaby are
shuffled elsewhere, the lullaby anywhere a song can be given (whatever the song mode).
The Weird Egg stays with the first Malon, who never comes: Talon is already awake, and
the egg can no longer take the letter's pouch slot. Everything that follows the castle
keeps its own checks: Saria waits for ``DoorOfTime`` ``Step02`` and Darunia (whose
quest goes through the Kakariko gate guard reading the letter), the Kokiri guard and Mido for the Deku Tree
(:func:`oot_rando.patching.story_fixes.kokiri_exit_guard_steps_aside`,
:func:`oot_rando.patching.qol_patches.keep_mido_at_post`), the Kakariko gate guard for
Zelda's Letter, and Malon's Epona's Song for the Lon Lon Ranch arrival. Not validated
in game.
"""
OPTION = 'skip_child_zelda'
OPENING_FLOW = 'Event/EventFlow/OpeningEvent.bfevfl.zs'
# After the opening's own quest request (``Meet_DekuTree`` ``Step01``, in
# ``Opening_Introduction``): the forest is loaded and Link takes part in the event.
# Not in ``Opening_LoadingKokiriForest`` (after ``Event3``): there the forest is still
# behind the loading screen, and the requests (each waiting for its end) kept it
# black forever.
OPENING_ANCHOR = 'Event8'
CASTLE_FLOW = 'Event/EventFlow/Goto_HyruleCastle.bfevfl.zs'
DOOR_FLOW = 'Event/EventFlow/DoorOfTime.bfevfl.zs'
ESCAPE_FLOW = 'Event/EventFlow/Dm_SY_BancChange_EscapeDungeon.bfevfl.zs'
TALON_FLOWS = ('Event/EventFlow/Dm_HrlCastle_0020.bfevfl.zs', 'Event/EventFlow/Dm_HrlCastle_0020.110.bfevfl.zs')
STEP_ACTOR, STEP_ACTION = 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep'
# (native flow, event, challenge, step): replayed at the start, in this order.
START_STEPS = (
    (ESCAPE_FLOW, 'Event4', 'Goto_HyruleCastle', 'Step01'),
    (CASTLE_FLOW, 'Event30', 'Goto_HyruleCastle', 'Complete'),
    (CASTLE_FLOW, 'Event32', 'DoorOfTime', 'Step01'),
    (DOOR_FLOW, 'Event7', 'DoorOfTime', 'Step02'),
    (DOOR_FLOW, 'Event62', 'Get_StoneOfFire', 'KakarikoVillageNpc'),
)
START_VALUES = {
    'Talon_AfterWakeUp': True,
    'HavePlayedEvent.Dm_HrlCastle_0020': True,
    'HyruleCastle_IsMalonAppear': False,
    'HavePlayedEvent.Dm_MelodyGet_Zelda': True,
}
# Items the castle hands over (AP names), shuffled elsewhere instead.
MOVED_ITEMS = ('Zeldas Letter', 'Zeldas Lullaby')
STEP_PREFIX = 'RandoCastleSkip_'
CASTLE_DONE = 'Goto_HyruleCastle_IsCompleted_Exp'
DOOR_PAST_STEP01 = 'DoorOfTime_IsAfter_Step01_Exp'
# (flow, challenge, steps, expression, guard prefix): requests skipped while the
# expression is true.
GUARDS = (
    (CASTLE_FLOW, 'Goto_HyruleCastle', ('Step01', 'Step02', 'Step03', 'Step03_01', 'Step03_02', 'Step04'),
     CASTLE_DONE, 'RandoCastleDone_'),
    (CASTLE_FLOW, 'DoorOfTime', ('Ready', 'Step01'), DOOR_PAST_STEP01, 'RandoCastleDoor_'),
    *((path, 'Goto_HyruleCastle', ('Step04',), CASTLE_DONE, 'RandoCastleDone_') for path in TALON_FLOWS),
)
GUARDED_FLOWS = tuple(dict.fromkeys(path for path, *_ in GUARDS))


def enabled(options):
    return bool((options or {}).get(OPTION))


def step_event_names():
    return [f'{STEP_PREFIX}{index}' for index in range(len(START_STEPS))]


def start_step_params(read_flow, door_ready=False):
    """[(event name, params)] of the requests replayed at the start (see module doc).

    ``read_flow(path)``: the game's bytes of a flow. Each params dict is the native
    event's, with ``IsIgnoreChallengeProgressUI`` true. ``door_ready`` keeps the
    no-stone escape at Step03 instead of replaying earlier DoorOfTime requests."""
    from oot_rando.patching.story_fixes import _Chart
    charts, result = {}, []
    for name, (path, event, challenge, step) in zip(step_event_names(), START_STEPS):
        if door_ready and challenge == 'DoorOfTime':
            continue  # No-stone escape already starts at Step03; never reset it.
        if path not in charts:
            charts[path] = _Chart(read_flow(path))
        native = charts[path].event(event, 'ActionEvent')
        params = event_params_of(native)
        if (native.data.actor_action.v.v != STEP_ACTION or str(native.data.actor.v.identifier) != STEP_ACTOR
                or params.get('ChallengeName') != challenge or params.get('StepName') != step):
            raise ValueError(f'Unexpected native quest request: {path} {event}')
        result.append((name, dict(params, IsIgnoreChallengeProgressUI=True)))
    return result


def add_start_steps(raw, steps, after=OPENING_ANCHOR):
    """Opening flow bytes where the ``steps`` requests run, in order, right after ``after``.

    Returns (bytes, [event names])."""
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    anchor = flow.events.get(after)
    if anchor is None or not hasattr(anchor.data, 'nxt'):
        raise ValueError('Anchor event without continuation: ' + after)
    following = anchor.data.nxt.v
    for name, params in reversed(steps):
        following = flow.action(name, STEP_ACTOR, STEP_ACTION, params, following)
    anchor.data.nxt = make_index(following)
    result, events = flow.write()
    chain = events[after].data.nxt.v
    for name, params in steps:
        if chain is None or chain.name != name or event_params_of(chain) != params:
            raise ValueError('Castle skip requests wrongly chained.')
        chain = chain.data.nxt.v
    return result, [name for name, _ in steps]


def guard_flow(path, raw, steps):
    """``raw`` (the flow at ``path``) with its castle requests guarded (:data:`GUARDS`).

    ``steps``: the challenge table (:func:`oot_rando.patching.quest_guard.challenge_steps`).
    Returns (bytes, [(event, step, expression)])."""
    from oot_rando.patching import quest_guard
    guarded = []
    for flow, challenge, wanted, expression, prefix in GUARDS:
        if flow != path:
            continue
        raw, report = quest_guard.guard_requests(raw, challenge, steps, wanted, expression, prefix=prefix)
        if not report['guarded']:
            raise ValueError(f'Castle skip guard: no {challenge} request to guard in {path}')
        guarded += [(event, step, expression) for event, step, _ in report['guarded']]
    return raw, guarded


# --- Kokiri Forest before the Deku Tree -------------------------------------------
# The Kokiri (and Mido) pick their state, last true wins, from their AIScheduleParam
# (``ConditionalSchedule`` ``ConditionFlag``) and branch their talks on the same
# expressions. ``Goto_HyruleCastle_IsCompleted_Exp`` (Zelda met) comes last: vanilla
# only reaches it after the Deku Tree's death. Completed from the start here, it put
# the whole forest in its after-death state at once (user report 19/11). Their
# castle state and talks now wait for the Deku Tree itself
# (``Get_StoneOfForest_IsCompleted_Exp``).
CASTLE_DONE_STATE = 'Goto_HyruleCastle_IsCompleted_Exp'
DEKU_TREE_DONE_STATE = 'Get_StoneOfForest_IsCompleted_Exp'
KOKIRI_SCHEDULE_PREFIX = 'Component/AIScheduleParam/Npc_Kokiri_'
KOKIRI_FLOW_PREFIX = 'Event/EventFlow/Npc_Kokiri_'


# Saria herself is not only scheduled: the map module of the village Saria
# (``KokiriForest_Child_Level_Npc_Kokiri_Saria_Child_a766``) deletes her (node 11,
# ``Logic_Delete`` = node 14, an OR) once ``Goto_HyruleCastle_IsCompleted_Exp`` (node
# 15) holds, as she then waits in the Sacred Forest Meadow. With the castle complete
# from the start she was gone from the village at once, and only the meadow Saria
# was left (20/11). Node 15 now reads the Deku Tree's end too. The other inputs of the
# OR are kept: after the Deku Tree she stands on the bridge (node 13) until her
# farewell. The bridge scene itself (``KokiriForest_ArriveLostWood``, module ``_ddcd``)
# reads no castle state. Not validated in game.
SARIA_MODULE = 'Logic/KokiriForest_Child_Level_Npc_Kokiri_Saria_Child_a766.logic.module.ainb'


def saria_waits_for_deku_tree(raw):
    """``_a766`` bytes: the village Saria leaves on the Deku Tree's end, not on Zelda's.

    Returns (bytes, report)."""
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = {node['Node Index']: node for node in document['Nodes']}
    gate, either, saria = nodes.get(15), nodes.get(14), nodes.get(11)
    if not gate or not either or not saria or (gate['Name'], either['Name'], saria['Name']) != (
            'HoldGameDataGetBoolExpSimple', 'OperateOR', 'ActorLogicNpc'):
        raise ValueError('Unexpected Saria logic module.')
    name = gate['Parameters']['Inputs']['String'][0]
    delete = next(p for p in saria['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete')
    sources = [(s['Node Index'], s['Output Index']) for s in either['Parameters']['Inputs']['Bool'][0]['Sources']]
    if ((name['Name'], name['Default Value']) != ('GameDataNameBoolExp', CASTLE_DONE_STATE)
            or (delete['Node Index'], delete['Output Index']) != (14, 1) or (15, 0) not in sources):
        raise ValueError('Unexpected Saria castle state (already patched?).')
    name['Default Value'] = DEKU_TREE_DONE_STATE
    result = ainb_to_binary(document)
    check = {n['Node Index']: n for n in ainb.AINB.from_binary(result).as_dict()['Nodes']}
    if check[15]['Parameters']['Inputs']['String'][0]['Default Value'] != DEKU_TREE_DONE_STATE:
        raise ValueError('Saria castle state wrongly rewritten.')
    return result, {'module': SARIA_MODULE, 'before': CASTLE_DONE_STATE, 'after': DEKU_TREE_DONE_STATE}


def kokiri_paths(members):
    """(schedules, flows) of the child Kokiri, Mido and Saria included."""
    schedules = sorted(p for p in members if p.startswith(KOKIRI_SCHEDULE_PREFIX) and '_Child' in p
                       and p.endswith('.bgyml'))
    flows = sorted(p for p in members if p.startswith(KOKIRI_FLOW_PREFIX) and '_Child' in p
                   and p.endswith('.bfevfl.zs'))
    return schedules, flows


def kokiri_schedule(raw):
    """Schedule bytes whose castle state waits for the Deku Tree. Returns (bytes, count)."""
    from oot_rando.formats import byml_codec
    document = byml_codec.load(raw)
    count = 0
    for entry in document['root'].get('ConditionalSchedule', []) or []:
        if entry.get('ConditionFlag') == CASTLE_DONE_STATE:
            entry['ConditionFlag'] = DEKU_TREE_DONE_STATE
            count += 1
    if not count:
        return raw, 0
    result = byml_codec.dump(document)
    if CASTLE_DONE_STATE in str(byml_codec.load(result)['root'].get('ConditionalSchedule')):
        raise ValueError('Kokiri schedule still waits for Zelda.')
    return result, count


def kokiri_talk(raw):
    """Talk flow bytes whose castle branches wait for the Deku Tree. Returns (bytes, [events])."""
    flow = parse_flow(raw)
    expected = params_by_event(flow)
    changed = []
    for event in flow.flowchart.events:
        params = getattr(getattr(event, 'data', None), 'params', None)
        if params is not None and params.data.get('GameDataName') == CASTLE_DONE_STATE \
                and getattr(event.data, 'actor_query', None) is not None \
                and event.data.actor_query.v.v == 'EventQueryIsGameDataBoolExp':
            params.data['GameDataName'] = DEKU_TREE_DONE_STATE
            expected[event.name]['GameDataName'] = DEKU_TREE_DONE_STATE
            changed.append(event.name)
    if not changed:
        return raw, []
    import io
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    if params_by_event(parse_flow(result)) != expected:
        raise ValueError('Kokiri talk patch changed other parameters.')
    return result, changed
