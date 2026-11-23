"""Every **+** skip window taken on its own (option ``auto_skip_cutscenes``).

A flow-driven cutscene is skippable with **+** only inside a native window
(``EventSystemActor.EventTriggerSkipAcceptStart`` ... ``EventTriggerSkipEnd``): when
+ is pressed, the game fades out, jumps to ``SkipEnd`` and the flow usually asks
``EventQueryIsEventSkipedMostRecent`` to fix what was missed (case 0 = skipped).
With the option, the window is never entered: whatever led to ``SkipAcceptStart``
goes straight to what follows ``SkipEnd``, on the skipped case of the queries met
there. Exactly the path a + press on the first frame takes, without opening the
window (opened and closed on the same frame under a loading screen, it left the
event stuck on black: area presentations, 19/11).

Windows covered:

* the vanilla ones (:data:`NATIVE_FLOWS`, scan of 1.1.1, 20/11): five great fairy
  fountains (their gift is on both paths). Kept with their + window (:func:`scan`
  says why): Din's fountain (its shared recovery entry asks for the skip where no
  window led) and the Water Temple's three water-level scenes (two ``SkipEnd``, one
  per water state, or a ``SkipEnd`` reached outside the window: the water level
  depends on the answer);
* the windows the randomizer adds to cutscenes (``skip_locked_cutscenes``,
  :func:`oot_rando.patching.qol_patches.add_skip_windows_with_replay`): their state
  writes are replayed on the skipped case, so they still happen.

Not covered (no window to take): pure timelines (the engine skips them on +; see
``skip_story_timelines``), dialogues, the intro / title / credits.

Screen: when the window held a fade-in (the screen was black before it) or its
``SkipEnd`` fades in, an ``EventEventFadeIn`` runs in its place. When a window
opened an entry (arrival under a loading screen), the entry first waits for the
loading screen to close, as the area presentations do. Not validated in game.
"""
FLOWS = 'Event/EventFlow/'
PREFIX = 'RandoAutoWindow_'
START, END, QUERY = 'EventTriggerSkipAcceptStart', 'EventTriggerSkipEnd', 'EventQueryIsEventSkipedMostRecent'
FADE_IN_ACTION = 'EventEventFadeIn'
FADE_IN = {'Color': 0, 'IsNoPlayAnime': False, 'IsWaitEnd': True, 'Length': 1}
LOADING_ACTOR, LOADING_ACTION = 'UISystemActor', 'EventWaitCloseLoadingFade'
# Vanilla flows whose every + window is taken (:func:`scan` rebuilds it, tests compare).
NATIVE_FLOWS = ('Dm_FairyFountain_Courage', 'Dm_FairyFountain_Frore', 'Dm_FairyFountain_Nayru',
                'Dm_FairyFountain_Power', 'Dm_FairyFountain_Wisdom')


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def _action(event):
    from evfl.event import ActionEvent
    data = event.data
    return data.actor_action.v.v if isinstance(data, ActionEvent) else None


def _query(event):
    from evfl.event import SwitchEvent
    data = event.data
    return data.actor_query.v.v if isinstance(data, SwitchEvent) else None


def _params(event):
    params = getattr(event.data, 'params', None)
    return dict(params.data) if params is not None and params.data else {}


def _successors(event):
    data = event.data
    found = [c.v for c in (getattr(data, 'cases', None) or {}).values()]
    found += [f.v for f in (getattr(data, 'forks', None) or [])]
    for name in ('join', 'nxt'):
        link = getattr(data, name, None)
        if link is not None:
            found.append(link.v)
    return [e for e in found if e is not None]


def _reach(chart, starts, stops=(), descend=True):
    """Events reachable from ``starts``, not past ``stops`` (``descend``: local sub-flows)."""
    from evfl.event import SubFlowEvent
    entries = {e.name: e for e in chart.entry_points}
    seen, todo, order = set(), list(starts), []
    while todo:
        event = todo.pop()
        if event is None or event.name in seen:
            continue
        seen.add(event.name)
        order.append(event)
        if event.name in stops:
            continue
        data = event.data
        if descend and isinstance(data, SubFlowEvent) and not data.res_flowchart_name:
            called = entries.get(data.entry_point_name)
            if called is not None:
                todo.append(called.main_event.v)
        todo.extend(_successors(event))
    return order


def _local_calls(chart, entry_name):
    from evfl.event import SubFlowEvent
    return [e for e in chart.events if isinstance(e.data, SubFlowEvent) and not e.data.res_flowchart_name
            and e.data.entry_point_name == entry_name]


def _roots(chart):
    """Entries the event system starts (those only called by this flow are reached through their calls)."""
    from evfl.event import SubFlowEvent
    called = {e.data.entry_point_name for e in chart.events
              if isinstance(e.data, SubFlowEvent) and not e.data.res_flowchart_name}
    return [e.main_event.v for e in chart.entry_points if e.main_event.v is not None and e.name not in called]


def window_plan(chart, start):
    """How the window opened by ``start`` is taken: dict, or raises ValueError.

    ``from``: the event whose links move; ``to``: where they go (None: the flow ends);
    ``call``: the local sub-flow call kept when ``SkipEnd`` opens the called entry
    (``entry`` then starts at ``to``); ``fade``: a fade-in is needed; ``dropped``:
    the events no longer run."""
    first = start.data.nxt.v if start.data.nxt is not None else None
    if first is None:
        raise ValueError('Empty skip window: ' + start.name)
    all_ends = {e.name for e in chart.events if _action(e) == END}
    inside = _reach(chart, [first], all_ends, descend=True)   # (not past an end: later windows)
    ends = {e.name: e for e in inside if _action(e) == END}
    if len(ends) != 1:
        raise ValueError(f'Skip window with {len(ends)} ends: {start.name}')
    end = next(iter(ends.values()))
    if any(_action(e) == START for e in _reach(chart, [first], {end.name})):
        raise ValueError('Nested skip window: ' + start.name)
    top = _reach(chart, [first], {end.name}, descend=False)
    call = entry = None
    if end.name in {e.name for e in top}:
        dropped = [e for e in _reach(chart, [first], {end.name}) if e is not end]
    else:
        entry = next((ep for ep in chart.entry_points if ep.main_event.v is end), None)
        calls = [e for e in top if entry is not None
                 and getattr(e.data, 'entry_point_name', None) == entry.name
                 and not getattr(e.data, 'res_flowchart_name', '')] if entry is not None else []
        if entry is None or len(calls) != 1 or len(_local_calls(chart, entry.name)) != 1:
            raise ValueError('Skip window end out of reach: ' + start.name)
        call = calls[0]
        dropped = [e for e in _reach(chart, [first], {call.name}) if e is not call]
    target = end.data.nxt.v if end.data.nxt is not None else None
    while target is not None and _query(target) == QUERY:
        case = target.data.cases.get(0)
        target = case.v if case is not None else None
    fade = (_params(end).get('FadeInType', 0) != 0
            or any(_action(e) == FADE_IN_ACTION for e in dropped))
    opens = any(ep.main_event.v is start for ep in chart.entry_points)
    return {'start': start, 'end': end, 'call': call, 'entry': entry, 'to': target, 'fade': fade,
            'opens': opens, 'dropped': dropped}


def _system_actor(editor, identifier):
    """``identifier`` (a system actor) of the flow, added with the system parameters."""
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier
    from evfl.container import Container
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
    if not any(str(a.identifier) == identifier for a in editor.chart.actors):
        owner = Actor()
        owner.identifier = ActorIdentifier(identifier)
        owner.concurrent_clips = 1
        owner.params = Container()
        owner.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        editor.chart.actors.append(owner)


def _redirect(chart, event, head, name):
    """Every link to ``event`` goes to ``head`` (None: the flow ends there)."""
    from evfl.util import Index, make_index
    from oot_rando.patching.qol_patches import _predecessors
    links = _predecessors(chart, event)
    if not links:
        raise ValueError('Skip event never reached: ' + name)
    for owner, kind, key in links:
        if kind == 'nxt':
            owner.data.nxt = make_index(head) if head is not None else Index()
        elif kind == 'case':
            if head is None:
                del owner.data.cases[key]
            else:
                owner.data.cases[key] = make_index(head)
        elif head is None:
            raise ValueError('Skip window would leave nothing to run: ' + name)
        elif kind == 'fork':
            owner.data.forks[key] = make_index(head)
        else:
            owner.main_event = make_index(head)


def take_windows(raw, flow):
    """Returns (bytes, report): every reachable + window of ``flow`` taken at once.

    report = [{'start', 'end', 'to', 'fade', 'loading_wait'}] (+ {'queries'}: later
    skip queries answered "skipped"). Raises ValueError when
    the flow has no window or one cannot be taken safely (nothing is changed then)."""
    from evfl.util import make_index
    from oot_rando.patching.progressive import FlowEditor, link
    editor = FlowEditor(raw, flow)
    chart = editor.chart
    starts = [e for e in _reach(chart, _roots(chart)) if _action(e) == START]
    if not starts:
        raise ValueError('No skip window: ' + flow)
    plans = [window_plan(chart, start) for start in sorted(starts, key=lambda e: e.name)]
    # What runs without entering any window (vanilla answers there stay as they are).
    free = {e.name for e in _reach(chart, _roots(chart), {s.name for s in starts})}
    report, report_queries = [], []
    for plan in plans:
        start, name = plan['start'], plan['start'].name
        chain = []
        if plan['opens']:
            _system_actor(editor, LOADING_ACTOR)
            chain.append(editor.action(PREFIX + name + '_Loading', LOADING_ACTOR, LOADING_ACTION,
                                       {'IsWaitEnd': True}))
        if plan['fade']:
            _system_actor(editor, LOADING_ACTOR)
            chain.append(editor.action(PREFIX + name + '_FadeIn', LOADING_ACTOR, FADE_IN_ACTION, dict(FADE_IN)))
        if plan['call'] is not None:
            # The call stays (its return path runs as after a skip); its entry starts
            # past SkipEnd, on the skipped case.
            if plan['to'] is None:
                raise ValueError('Skip window ends its called entry: ' + name)
            plan['entry'].main_event = make_index(plan['to'])
            after = plan['call']
        else:
            after = plan['to']
        for current, nxt in zip(chain, chain[1:] + [after]):
            link(current, nxt)
        head = chain[0] if chain else after
        _redirect(chart, start, head, name)
        report.append({'start': name, 'end': plan['end'].name, 'to': plan['to'].name if plan['to'] else None,
                       'fade': plan['fade'], 'loading_wait': plan['opens']})
    # Skip queries asked later (a sub-flow after SkipEnd...): reached only past a
    # window, they answer "skipped" there.
    while True:
        later = [e for e in _reach(chart, _roots(chart)) if _query(e) == QUERY and e.name not in free]
        if not later:
            break
        for query in later:
            case = query.data.cases.get(0)
            _redirect(chart, query, case.v if case is not None else None, query.name)
            report_queries.append(query.name)
    reached = _reach(chart, _roots(chart))
    left = sorted(e.name for e in reached if _action(e) in (START, END) or _query(e) == QUERY)
    if left:
        raise ValueError(f'Skip handling still reached in {flow}: {left}')
    if report_queries:
        report.append({'queries': sorted(report_queries)})
    result, _ = editor.write('Skip window auto-take')
    if not taken(result):
        raise ValueError('Skip windows not taken: ' + flow)
    return result, report


def taken(raw):
    """Whether no entry of ``raw`` reaches a skip window or a skip query any more."""
    from oot_rando.patching.event_patch import _flow
    chart = _flow(raw).flowchart
    return not any(_action(e) in (START, END) or _query(e) == QUERY for e in _reach(chart, _roots(chart)))


def flows(enabled, cutscene_windows=()):
    """Flows changed by the option: the native ones and the randomizer's windows."""
    return tuple(sorted(set(NATIVE_FLOWS) | set(cutscene_windows))) if enabled else ()


def scan(read_flow, flow_names):
    """(flows whose every window can be taken, {flow: reason kept}) over vanilla flows."""
    from oot_rando.patching.event_patch import _flow
    ok, kept = [], {}
    for name in sorted(flow_names):
        raw = read_flow(flow_path(name))
        if raw is None:
            continue
        try:
            chart = _flow(raw).flowchart
        except ValueError:
            continue
        if chart is None or not any(_action(e) == START for e in chart.events):
            continue
        try:
            take_windows(raw, name)
        except ValueError as error:
            kept[name] = str(error)
            continue
        ok.append(name)
    return tuple(ok), kept
