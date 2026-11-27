"""Area presentations (first visit of a zone: camera tour + area name) never play.

Always on. Two mechanisms, chosen per presentation from what its first visit does
(scan of 1.1.1, 19/11):

* **Pre-marked** (:data:`PREMARKED`): the presentation is gated by a saved
  ``HavePlayedEvent`` Bool that only chooses between it and the normal arrival:
  either the entrance's ``InitEventFlag`` (``FieldAndDungeonEntranceEventRequestActor``:
  ``InitEventName`` while the flag is false, else ``NextEventName``), where the first
  arrival does nothing the normal one does not; or an ``EventQueryHavePlayedEvent``
  switch in ``Dm_SY_BancChangeArrive`` whose two cases merge into the same arrival.
  The flag is written at the end of the new-game opening, with the area's
  ``IsVisitLocation`` (the presentation's name frame is what marks it visited: without
  it the map menu shows "???"). These areas are therefore known on the map from the start.
* **Skipped at the first frame** (every other presentation): the native skip window
  (:func:`oot_rando.patching.qol_patches.add_skip_window`) is entered and left at once,
  as if **+** were pressed on the first frame. The event itself still starts, so what
  its caller does around it (quest steps of the first arrival, Ganon's collapse...)
  is kept; quest steps found inside the window (``SageOfForest Step05`` in the Forest
  Temple presentation) run between the window's start and end. The area name frame
  still opens (the window was not skipped) and marks the area visited. These are:

  - first arrivals that move a quest or write data: Death Mountain Trail
    (``Get_StoneOfFire``), Zora's Domain (``Get_StoneOfWater``), Desert Colossus
    (``SageOfSpirit``), Market (``Goto_HyruleCastle``), Deku Tree (``Get_StoneOfForest``
    + action guide), Goron City (``Get_StoneOfFire``), Forest Temple (``SageOfForest``),
    Gerudo Training Ground (``SubEvent_GetIceArrow``), Death Mountain Crater
    (``DeathMtCrater_IsFirstEntry``);
  - gates that are BoolExp (not writable): Kakariko (``InitDemo_KakarikoVillage``),
    Lake Hylia (``InitDemo_LakeHylia``);
  - presentations started by an ``EventRequestActor`` (Dodongo's Cavern inside, Forest
    Temple inside, Gerudo Valley, Temple of Time x2, Water Temple) or inside a quest
    flow (Jabu-Jabu, Hyrule Field, Ganon's tower collapse): no flag gates them.

Not validated in game.
"""
from oot_rando.patching.qol_patches import AREA_PRESENTATIONS, SKIP_FADE_OUT_ACTIONS, add_skip_window, flow_path, skip_action_class
from oot_rando.formats.evfl_tools import next_events, params_by_event, parse_flow

# presentation -> (gating HavePlayedEvent flag, IsVisitLocation flag of its name frame)
PREMARKED = {
    'Dm_GanonCastle_0000': ('HavePlayedEvent.Dm_GanonCastle_0000', 'IsVisitLocation.GanonCastle'),
    'Dm_Gerudo_0000': ('HavePlayedEvent.Dm_Gerudo_0000', 'IsVisitLocation.GerudoFortress'),
    'Dm_Graveyard_0000': ('HavePlayedEvent.Dm_Graveyard_0000', 'IsVisitLocation.Graveyard'),
    'Dm_ZoraFountain_0000': ('HavePlayedEvent.Dm_ZoraFountain_0000', 'IsVisitLocation.ZoraFountain'),
    'Goto_FireTemple': ('HavePlayedEvent.Goto_FireTemple', 'IsVisitLocation.FireTemple'),
    'Goto_IceCave': ('HavePlayedEvent.Goto_IceCave', 'IsVisitLocation.IceCavern'),
    'Goto_KakarikoWells': ('HavePlayedEvent.Goto_KakarikoWells', 'IsVisitLocation.BottomOfTheWell'),
    'Goto_SacredForest': ('HavePlayedEvent.Goto_SacredForest', 'IsVisitLocation.SacredForestMeadow'),
    'Goto_ShadowTemple': ('HavePlayedEvent.Goto_ShadowTemple', 'IsVisitLocation.ShadowTemple'),
    # (the entrance's flag keeps the game's own spelling)
    'Goto_SpiritTemple': ('HavePlayedEvent.Goto_SpritTemple', 'IsVisitLocation.SpiritTemple'),
    'Goto_ZoraRiver': ('HavePlayedEvent.Goto_ZoraRiver', 'IsVisitLocation.ZoraRiver'),
}
AUTO_SKIPPED = tuple(name for name in AREA_PRESENTATIONS if name not in PREMARKED)
# Inside a window, these still run when it is left at once (in the window's order).
KEPT_ACTIONS = ('EventExecuteProgressChallengeStep',)
AUTO_PREFIX = 'RandoAutoSkip_'
# The presentations start while the loading screen is still up. Left at once, the
# event ended under it and the screen stayed black (19/11, 0.7.0). The game's own
# arrivals without a scene wait for that fade first (Dm_SY_BancChangeArrive), as the
# owl's Dream World skip does: every presentation entry now starts with that wait,
# before its skip window opens (the + windows too: the native ones, in the fairy
# fountains, never open under a loading screen).
LOADING_WAIT = 'RandoLoadingWait_'
LOADING_ACTOR, LOADING_ACTION = 'UISystemActor', 'EventWaitCloseLoadingFade'


# Every scene that marks an area visited: its area name frame
# (``EventTriggerOpenLocationUI``) sets ``IsVisitLocation.<area>`` (scan of 1.1.1, 27/11).
LOCATION_FRAMES = {
    'Dm_DeathMtCrater_0000': 'DeathMountainCrater', 'Dm_DeathMtTrail_0000': 'DeathMountainTrail',
    'Dm_Deku_0000': 'InsideTheDekuTree', 'Dm_DesertColossus_0000': 'DesertColossus',
    'Dm_DodongoCave_0000': 'DodongoCavern', 'Dm_ForestTemple_0000': 'ForestTemple',
    'Dm_GanonCastle_0000': 'GanonCastle', 'Dm_GerudoValley_0000': 'GerudoValley',
    'Dm_Gerudo_0000': 'GerudoFortress', 'Dm_Goron_0000': 'GoronCity', 'Dm_Graveyard_0000': 'Graveyard',
    'Dm_HrlCastle_0000': 'HyruleCastle', 'Dm_HrlCastle_0005': 'Market', 'Dm_HrlField_0000': 'HyruleField',
    'Dm_InsideGanonCastle_0003': 'InsideGanonCastle', 'Dm_InsideJabu_Jabu_0000': 'InsideJabuJabuBelly',
    'Dm_Kakariko_0000': 'KakarikoVillage', 'Dm_Kokiri_0045': 'KokiriForest', 'Dm_LakeHrl_0000': 'LakeHylia',
    'Dm_LakeHrl_0003': 'LakeHylia', 'Dm_LakeHrl_0005': 'LakeHylia', 'Dm_LonLon_0010': 'LonLonRanch',
    'Dm_TimeTemple_0000': 'TimeTemple', 'Dm_TimeTemple_0065': 'Market', 'Dm_ZoraFountain_0000': 'ZoraFountain',
    'Dm_Zora_0000': 'ZoraDomain', 'Goto_FireTemple': 'FireTemple',
    'Goto_GerudoTrainingGround': 'GerudoTrainingGround', 'Goto_IceCave': 'IceCavern',
    'Goto_KakarikoWells': 'BottomOfTheWell', 'Goto_SacredForest': 'SacredForestMeadow',
    'Goto_ShadowTemple': 'ShadowTemple', 'Goto_SpiritTemple': 'SpiritTemple', 'Goto_WaterTemple': 'WaterTemple',
    'Goto_ZoraRiver': 'ZoraRiver', 'Npc_Dream': 'DreamWorld',
}


def start_values():
    """GameData values written at the end of the new-game opening (full mode)."""
    values = {}
    for played, visit in PREMARKED.values():
        values[played] = True
        values[visit] = True
    return values


def with_area_visits(values):
    """``values`` plus the area visited by each scene it marks played without playing it.

    A scene marked played at the start never runs, so neither does its area name frame:
    the map menu then showed "???" there for the whole game (Hyrule Field and Hyrule
    Castle, marked played for Kaepora's first arrival, 27/11)."""
    out = dict(values)
    for scene, area in LOCATION_FRAMES.items():
        if out.get('HavePlayedEvent.' + scene) is True:
            out.setdefault('IsVisitLocation.' + area, True)
    return out


def auto_skip_presentation(raw, fade_in=True):
    """``raw`` with every presentation entry's skip window left on its first frame.

    ``fade_in`` (seeds from 19/11 on): the window is not entered at all. Opening and
    closing it on the same frame, under the loading screen, left the event stuck on a
    black screen with Link frozen (Longshot, Goron City and Kakariko, 19/11). The entry
    now goes straight to the kept quest steps, the window's fade-in (run every time)
    and the area name frame.

    Returns (bytes, report): the :func:`add_skip_window` records, each with ``auto``
    (the event jumped to) and ``kept`` (cloned quest steps)."""
    import copy
    import io
    from evfl.container import Container
    from evfl.event import ActionEvent, Event, SubFlowEvent
    from evfl.util import make_index
    windowed, records = add_skip_window(raw, fade_in)
    flow = parse_flow(windowed)
    chart = flow.flowchart
    events = {e.name: e for e in chart.events}
    entries = {e.name: e for e in chart.entry_points}
    expected = params_by_event(flow)

    def reachable(starts, stops=()):
        seen, stack, order = set(), list(starts), []
        while stack:
            event = stack.pop()
            if event is None or event.name in seen or event.name in stops:
                continue
            seen.add(event.name)
            order.append(event)
            if isinstance(event.data, SubFlowEvent) and not event.data.res_flowchart_name:
                sub = entries.get(event.data.entry_point_name)
                stack.append(sub.main_event.v if sub is not None else None)
            stack.extend(next_events(event))
        return order

    roots = lambda: [e.main_event.v for e in chart.entry_points]
    before = {e.name for e in reachable(roots())}
    by_entry = {}
    for record in records:
        by_entry.setdefault(record['entry'], []).append(record)
    windows = set()
    for entry_name, entry_records in by_entry.items():
        start = entries[entry_name].main_event.v
        ends = [events[r['end']] for r in entry_records]
        region = reachable([start.data.nxt.v], {e.name for e in ends})
        windows |= {e.name for e in region}
        order = {e.name: i for i, e in enumerate(chart.events)}
        kept = sorted((e for e in region if isinstance(e.data, ActionEvent)
                       and e.data.actor_action.v.v in KEPT_ACTIONS), key=lambda e: order[e.name])
        after = ends[0]
        if fade_in:
            fade = ends[0].data.nxt.v.data.cases[0].v   # (add_skip_window's fade check)
            shown = fade.data.nxt.v if fade.data.nxt is not None else None
            if shown is not None and shown.name.startswith('RandoLocationCheck_'):
                fade.data.nxt = shown.data.cases[1]   # the frame opens: not skipped
            after = fade
        clones = []
        for index, original in reversed(list(enumerate(kept))):
            clone = Event()
            clone.name, clone.data = f'{AUTO_PREFIX}{entry_name}_{index}', ActionEvent()
            clone.data.actor, clone.data.actor_action = original.data.actor, original.data.actor_action
            clone.data.params = Container()
            clone.data.params.data = copy.deepcopy(original.data.params.data)
            clone.data.nxt = make_index(after)
            chart.events.append(clone)
            expected[clone.name] = dict(clone.data.params.data)
            clones.insert(0, clone.name)
            after = clone
        if fade_in:
            entries[entry_name].main_event = make_index(after)
        else:
            start.data.nxt = make_index(after)
        for record in entry_records:
            record['auto'] = (fade if fade_in else ends[0]).name
            record['kept'] = [events[e.name].data.params.data.get('StepName') for e in kept]
    # What no longer runs outside the windows: the other branches' cleanup only.
    dropped = before - {e.name for e in reachable(roots())} - windows
    for name in sorted(dropped):
        data = events[name].data
        if name.startswith('Rando') or not isinstance(data, ActionEvent):
            continue
        action = data.actor_action.v.v
        actor = data.actor.v.identifier.name
        params = data.params.data if data.params is not None else {}
        if action not in SKIP_FADE_OUT_ACTIONS and skip_action_class(actor, action, params) != 'cosmetic':
            raise ValueError(f'Auto-skip drops a non-cosmetic action: {name} {action}')
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = parse_flow(result)
    if params_by_event(checked) != expected:
        raise ValueError('The presentation auto-skip changed other parameters.')
    checked_entries = {e.name: e for e in checked.flowchart.entry_points}
    checked_events = {e.name: e for e in checked.flowchart.events}
    for record in records:
        start = checked_entries[record['entry']].main_event.v
        nxt = start if fade_in else start.data.nxt.v
        while nxt.name.startswith(AUTO_PREFIX):
            nxt = nxt.data.nxt.v
        target = 'EventEventFadeIn' if fade_in else 'EventTriggerSkipEnd'
        if ((not fade_in and start.data.actor_action.v.v != 'EventTriggerSkipAcceptStart')
                or nxt.name != record['auto'] or checked_events[record['auto']].data.actor_action.v.v != target):
            raise ValueError('Presentation auto-skip misplaced: ' + record['entry'])
    return result, records


def add_loading_wait(raw, records):
    """``raw`` with each recorded entry waiting for the loading screen to close first.

    Marks each record with ``loading_wait``. Returns (bytes, records)."""
    import io
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import ActionEvent, Event
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
    flow = parse_flow(raw)
    chart = flow.flowchart
    expected = params_by_event(flow)
    actor = next((a for a in chart.actors if a.identifier.name == LOADING_ACTOR
                  and a.identifier.sub_name == ''), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier(LOADING_ACTOR)
        actor.concurrent_clips = 1
        actor.params = Container()
        actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        chart.actors.append(actor)
    action = next((a for a in actor.actions if a.v == LOADING_ACTION), None)
    if action is None:
        action = StringHolder(LOADING_ACTION)
        actor.actions.append(action)
    entries = {e.name: e for e in chart.entry_points}
    starts = {}
    for entry_name in sorted({r['entry'] for r in records}):
        entry = entries[entry_name]
        start = entry.main_event.v
        starts[entry_name] = start.name if start is not None else None
        if start is None or start.name.startswith(LOADING_WAIT):
            raise ValueError('Loading wait: unexpected entry start: ' + entry_name)
        wait = Event()
        wait.name, wait.data = LOADING_WAIT + entry_name, ActionEvent()
        wait.data.actor, wait.data.actor_action = make_rindex(actor), make_rindex(action)
        wait.data.params = Container()
        wait.data.params.data = {'IsWaitEnd': True}
        wait.data.nxt = make_index(start)
        chart.events.append(wait)
        expected[wait.name] = dict(wait.data.params.data)
        entry.main_event = make_index(wait)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = parse_flow(result)
    if params_by_event(checked) != expected:
        raise ValueError('The loading wait changed other parameters.')
    checked_entries = {e.name: e for e in checked.flowchart.entry_points}
    for record in records:
        wait = checked_entries[record['entry']].main_event.v
        if (wait.name != LOADING_WAIT + record['entry'] or wait.data.actor_action.v.v != LOADING_ACTION
                or wait.data.nxt.v.name != starts[record['entry']]):
            raise ValueError('Loading wait misplaced: ' + record['entry'])
        record['loading_wait'] = True
    return result, records


def presentation_files(read_flow, premarked=True):
    """``read_flow(path)`` returns a decompressed flow. Returns ({path: bytes}, report).

    ``premarked``: the :data:`PREMARKED` flags are written at the start (full mode);
    those presentations keep a plain **+** window. Otherwise every one is auto-skipped."""
    files, report = {}, {}
    for name in AREA_PRESENTATIONS:
        raw = read_flow(flow_path(name))
        if premarked and name in PREMARKED:
            patched, records = add_skip_window(raw)
        else:
            patched, records = auto_skip_presentation(raw)
        files[flow_path(name)], report[name] = add_loading_wait(patched, records)
    return files, report


def expected_flow(name, original, records):
    """The flow verification rebuilds from the original and its spoiler records."""
    import copy
    fade_in = any(record.get('fade_in') for record in records)   # (seeds before 19/11: none)
    if any(record.get('auto') for record in records):
        patched, rebuilt = auto_skip_presentation(original, fade_in)
    else:
        patched, rebuilt = add_skip_window(original, fade_in)
    if any(record.get('loading_wait') for record in records):   # (seeds before 19/11: none)
        patched = add_loading_wait(patched, copy.deepcopy(rebuilt))[0]
    return patched
