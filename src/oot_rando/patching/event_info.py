"""Sub-flow dependencies of events (``RSDB/GameAnalyzedEventInfo``).

The game does not find an event's external sub-flows (``SubFlowEvent`` with a
``res_flowchart_name``) by itself: each event row of ``GameAnalyzedEventInfo``
(row id = the ``EventSetting`` row id) lists them, transitively, in ``SubFlowList``,
and only those flowcharts are loaded when the event starts (``ChildEventList``
does the same for the events started by ``EventTransition``).

User test 11/11: the Deku Tree gift, moved after the cutscenes by a call to
``Dm_SY_GetInEvent`` in ``Dm_SY_BancChange_EscapeDungeon`` (entry Warp_Kokiri), left
the arrival in Kokiri Forest on a white screen: the row
``KokiriForest_WarpFromInsideTheDekuTree`` lists ``["NaviChat"]`` only, so the event
waited for a flowchart never loaded. Every vanilla caller of Dm_SY_GetInEvent lists
it with its own sub-flows (ActionGuide, GetPouchContent, Dm_SY_Get, NaviEventCommon…).

``add_subflow_dependencies`` adds, to every event row whose flowchart (or one of its
listed sub-flows) was changed to call a new external flowchart, that flowchart and
everything it calls in turn.

``add_child_events`` does the same for ``ChildEventList`` (user test 12/11: the Fairy
Ocarina found before Hyrule Field could be played only after reloading the save). The
ocarina guide added at the end of every item get (``ActionGuide``) goes on, when the
player asks for it, with ``EventTransition`` to ``Dm_SY_Ocarina``; only the Hyrule
Field arrival lists that event, so from an item get the transition never started and
``ActionGuide_IsRequestOcarina`` (not saved: cleared by a reload) stayed true.
"""
import copy

GAME_ANALYZED_EVENT_INFO = 'RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs'
FLOWS = 'Event/EventFlow/'


# A ``SubFlowSwitchEvent`` (``EventFlowMsg/<flow>:<label>`` sub-flows chosen by the
# message) brings in flowcharts this analysis does not follow (e.g. the boss room warp
# lists Common_Dungeon_WarpFromBossArea through them): a new call that reaches one
# cannot be listed completely, so it is refused.
SWITCH_CALL = ('<SubFlowSwitchEvent>', '')


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def flow_name(path):
    """'Event/EventFlow/X.bfevfl.zs' -> 'X' (None for another file)."""
    if path.startswith(FLOWS) and path.endswith('.bfevfl.zs'):
        return path[len(FLOWS):-len('.bfevfl.zs')]
    return None


def _chart(raw):
    from oot_rando.patching.event_patch import _flow
    return _flow(raw).flowchart


def _successors(event):
    data, out = event.data, []
    nxt = getattr(data, 'nxt', None)
    if nxt is not None and nxt.v is not None:
        out.append(nxt.v)
    out += [c.v for c in (getattr(data, 'cases', None) or {}).values() if c.v is not None]
    out += [f.v for f in (getattr(data, 'forks', None) or []) if f.v is not None]
    join = getattr(data, 'join', None)
    if join is not None and join.v is not None:
        out.append(join.v)
    return out


def entry_calls(raw, entry):
    """(flowchart, entry) of every external sub-flow reachable from ``entry``.

    Sub-flows of the same flowchart are followed; an unknown entry calls nothing.
    """
    return _entry_walk(raw, entry)[0]


def event_calls(raw, event):
    """(flowchart, entry) of every external sub-flow reachable from the event named ``event`` (included)."""
    return _entry_walk(raw, None, event)[0]


def reachable(event):
    """Events reachable from ``event`` (included) in its flowchart, without entering sub-flows."""
    seen, stack, found = set(), [event], []
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        stack.extend(_successors(current))
    return found


def entry_transitions(raw, entry):
    """``EventName`` of every ``EventTransition`` reachable from ``entry`` (same flowchart)."""
    return _entry_walk(raw, entry)[1]


def _entry_walk(raw, entry, start=None):
    """(external calls, transition events) reachable from ``entry`` (or from the event named ``start``)."""
    from evfl.event import ActionEvent, SubFlowEvent
    chart = _chart(raw) if raw is not None else None
    if chart is None:
        return set(), set()
    entries = {e.name: e for e in chart.entry_points}
    calls, transitions, seen_entries, seen = set(), set(), set(), set()
    stack = [entries[entry]] if entry in entries else []
    events = [e for e in chart.events if e.name == start] if start is not None else []
    while stack or events:
        if events:
            event = events.pop()
            if event is None or event.name in seen:
                continue
            seen.add(event.name)
            data = event.data
            if isinstance(data, ActionEvent) and data.actor_action.v.v == 'EventTransition':
                name = data.params.data.get('EventName') if data.params is not None else None
                if isinstance(name, str) and name:
                    transitions.add(name)
            if type(data).__name__ == 'SubFlowSwitchEvent':
                calls.add(SWITCH_CALL)   # (message flows: not followed, see SWITCH_CALL)
            if isinstance(data, SubFlowEvent):
                if data.res_flowchart_name:
                    calls.add((data.res_flowchart_name, data.entry_point_name))
                elif data.entry_point_name in entries:
                    stack.append(entries[data.entry_point_name])
            events.extend(_successors(event))
            continue
        point = stack.pop()
        if point.name not in seen_entries:
            seen_entries.add(point.name)
            events.append(point.main_event.v)
    return calls, transitions


def entry_names(raw):
    chart = _chart(raw) if raw is not None else None
    return [e.name for e in chart.entry_points] if chart is not None else []


def new_subflows(modified, original):
    """{(flow, entry): external (flowchart, entry) calls only its changed version makes}.

    ``modified``: {flow name: raw}; ``original(name)``: vanilla raw, or None (new flow).
    """
    added = {}
    for name, raw in modified.items():
        before = original(name)
        for entry in entry_names(raw):
            calls = entry_calls(raw, entry) - entry_calls(before, entry)
            if calls:
                added[(name, entry)] = calls
    return added


def closure(calls, current, memo=None):
    """Flowcharts of ``calls`` and of everything they call, transitively (per entry).

    ``current(name)``: the flow's raw, or None.
    """
    memo = {} if memo is None else memo
    seen, stack, flows = set(), list(calls), set()
    while stack:
        call = stack.pop()
        if call in seen:
            continue
        seen.add(call)
        flows.add(call[0])
        if call not in memo:
            memo[call] = entry_calls(current(call[0]), call[1])
        stack.extend(memo[call] - seen)
    return flows


def event_entries(event_settings_root, entries_of):
    """{EventSetting row id: (flowchart, entry)}. A row without entry plays the entry
    named like its flowchart, else ``EntryPoint0``, else the first one."""
    rows = {}
    for row in event_settings_root:
        path = row.get('FlowchartFileName', '')
        if not (row.get('__RowId') and path):
            continue
        flow = path.rsplit('/', 1)[-1].replace('.evfc', '')
        entry = row.get('EntryPointName') or ''
        if not entry:
            names = entries_of(flow)
            entry = flow if flow in names else 'EntryPoint0' if 'EntryPoint0' in names else (names[0] if names else '')
        rows[row['__RowId']] = (flow, entry)
    return rows


def add_subflow_dependencies(info_raw, event_settings_root, added, current):
    """Returns (patched GameAnalyzedEventInfo, {row id: [flowcharts added]}).

    ``added``: ``new_subflows``'s result; ``current(name)``: the flow as written in the
    seed (changed or vanilla), or None. A row is completed when the entry it plays
    makes a new call, or when it lists a changed flowchart that makes one (any entry).
    """
    from oot_rando.formats import byml_codec
    if not added:
        return info_raw, {}
    memo = {}
    by_entry = {key: closure(calls, current, memo) for key, calls in added.items()}
    for key, flows in by_entry.items():
        if SWITCH_CALL[0] in flows:
            raise ValueError('New sub-flow call through a message sub-flow switch: ' + '/'.join(key))
    by_flow = {}
    for (flow, _), flows in by_entry.items():
        by_flow.setdefault(flow, set()).update(flows)
    names = {}
    entries_of = lambda flow: names.setdefault(flow, entry_names(current(flow)))
    owners = event_entries(event_settings_root, entries_of)
    document = byml_codec.load(info_raw)
    expected = copy.deepcopy(document['root'])
    report = {}
    for index, row in enumerate(document['root']):
        own = owners.get(row.get('__RowId'))
        listed = list(row.get('SubFlowList') or [])
        wanted = set(by_entry.get(own, ()))
        for flow in set(listed) & by_flow.keys():
            wanted |= by_flow[flow]
        missing = sorted(wanted - set(listed) - ({own[0]} if own else set()))
        if not missing:
            continue
        row['SubFlowList'] = sorted(set(listed) | set(missing), key=str.lower)   # (vanilla order)
        expected[index]['SubFlowList'] = row['SubFlowList']
        report[row['__RowId']] = missing
    if not report:
        return info_raw, {}
    result = byml_codec.dump(document)
    if byml_codec.load(result)['root'] != expected:
        raise ValueError('Semantic check of the event sub-flows failed.')
    return result, report


def reachable_transitions(call, current, memo=None):
    """Events started by ``EventTransition`` from ``call`` = (flowchart, entry) and from
    every external sub-flow it calls, transitively. ``memo``: one per version of the flows."""
    memo = {} if memo is None else memo
    seen, stack, events = set(), [call], set()
    while stack:
        call = stack.pop()
        if call in seen or call == SWITCH_CALL:
            continue
        seen.add(call)
        if call not in memo:
            memo[call] = _entry_walk(current(call[0]), call[1])
        calls, transitions = memo[call]
        events |= transitions
        stack.extend(calls - seen)
    return events


def new_transitions(modified, original):
    """{(flow, entry): events only the changed version starts by ``EventTransition``}.

    ``modified``: {flow name: raw}; ``original(name)``: vanilla raw, or None. Through
    external sub-flows too.
    """
    now = lambda name: modified[name] if name in modified else original(name)
    memo_now, memo_before, added = {}, {}, {}
    for name, raw in modified.items():
        for entry in entry_names(raw):
            events = (reachable_transitions((name, entry), now, memo_now)
                      - reachable_transitions((name, entry), original, memo_before))
            if events:
                added[(name, entry)] = events
    return added


def add_child_events(info_raw, event_settings_root, added, current):
    """Returns (patched GameAnalyzedEventInfo, {row id: [events added]}).

    As ``add_subflow_dependencies``, for ``ChildEventList``: a row is completed when the
    entry it plays starts a new event, or when it lists (``SubFlowList``) a changed
    flowchart that does (any entry). Each new event comes with the events it lists in
    turn (the vanilla Hyrule Field arrival lists Dm_SY_Ocarina's own children too).
    """
    from oot_rando.formats import byml_codec
    if not added:
        return info_raw, {}
    document = byml_codec.load(info_raw)
    rows = {row.get('__RowId'): row for row in document['root']}
    unknown = sorted({event for events in added.values() for event in events} - rows.keys())
    if unknown:
        raise ValueError('New transition to an event without info row: ' + ', '.join(unknown))

    def with_children(events):
        seen, stack = set(), list(events)
        while stack:
            event = stack.pop()
            if event not in seen:
                seen.add(event)
                stack.extend(rows[event].get('ChildEventList') or [])
        return seen
    by_entry = {key: with_children(events) for key, events in added.items()}
    by_flow = {}
    for (flow, _), events in by_entry.items():
        by_flow.setdefault(flow, set()).update(events)
    names = {}
    entries_of = lambda flow: names.setdefault(flow, entry_names(current(flow)))
    owners = event_entries(event_settings_root, entries_of)
    expected = copy.deepcopy(document['root'])
    report = {}
    for index, row in enumerate(document['root']):
        row_id = row.get('__RowId')
        listed = list(row.get('ChildEventList') or [])
        wanted = set(by_entry.get(owners.get(row_id), ()))
        for flow in set(row.get('SubFlowList') or []) & by_flow.keys():
            wanted |= by_flow[flow]
        missing = sorted(wanted - set(listed) - {row_id})
        if not missing:
            continue
        row['ChildEventList'] = sorted(set(listed) | set(missing), key=str.lower)   # (vanilla order)
        expected[index]['ChildEventList'] = row['ChildEventList']
        report[row_id] = missing
    if not report:
        return info_raw, {}
    result = byml_codec.dump(document)
    if byml_codec.load(result)['root'] != expected:
        raise ValueError('Semantic check of the child events failed.')
    return result, report
