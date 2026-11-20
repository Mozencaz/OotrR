"""NPC lines without a choice that are never shown (option ``skip_npc_dialogues``).

Only the flows listed in :data:`ZONES` change (a white list, grown zone by zone once
each zone is tried in game). In them, every line (``EventTalk``,
``EventTalkIgnoreSameTalkAS``) that offers no choice (``ChoiceNumber`` = 0) is taken
out of the flow: what led to it goes straight to what follows it. Kept:

* every line that offers a choice (``ChoiceNumber`` > 0, or given by an entry argument:
  the count is not known here), and every line reached after a choice or a
  ``EventQueryTalkChoice*`` (the answer to what the player asked);
* a line (or message box event below) with nothing after it that starts an entry or a
  fork branch (it would be left empty).

Message box: ``EventCloseMessageDialog`` that no kept line can reach is taken out too
(nothing to close), and so is ``EventTriggerBecomeSpeaker`` that leads to no kept line
(the 11/11 crash, ``MessageDialogStyle`` ``NoActor``, came with dialogue boxes left
without their speaker). A kept line that left its box open (``IsCloseDialog`` false) for
a line now taken out closes it itself.

Everything else runs as before: animations, camera, item gets (``Dm_SY_GetInEvent``, its
"You got X!" text is in that other flow), quest and GameData writes. Lines taken out stay
in the file, unreached (same technique as the timelines). Not validated in game.
"""
FLOWS = 'Event/EventFlow/'
TALK_ACTIONS = ('EventTalk', 'EventTalkIgnoreSameTalkAS')
CLOSE_ACTION = 'EventCloseMessageDialog'
SPEAKER_ACTION = 'EventTriggerBecomeSpeaker'
CHOICE_QUERY_PREFIX = 'EventQueryTalkChoice'

# zone -> NPC flows whose lines without a choice are taken out. Left out on purpose:
# shops (prices), minigames (rules), hint givers (gossip stones, Navi, Kaepora), the
# great fairies and song lessons (other options), cutscene flows (``Dm_*``).
ZONES = {
    'Kokiri Forest': (
        'Npc_DekuTreeChild',
        'Npc_Kokiri_002_Adult', 'Npc_Kokiri_002_Child', 'Npc_Kokiri_003_Adult', 'Npc_Kokiri_003_Child',
        'Npc_Kokiri_004_Adult', 'Npc_Kokiri_004_Child', 'Npc_Kokiri_005_Adult', 'Npc_Kokiri_005_Child',
        'Npc_Kokiri_006_Adult', 'Npc_Kokiri_006_Child', 'Npc_Kokiri_007_Adult', 'Npc_Kokiri_007_Child',
        'Npc_Kokiri_008_Adult', 'Npc_Kokiri_008_Child', 'Npc_Kokiri_009_Adult', 'Npc_Kokiri_009_Child',
        'Npc_Kokiri_010_Adult', 'Npc_Kokiri_010_Child', 'Npc_Kokiri_011_Adult', 'Npc_Kokiri_011_Child',
        'Npc_Kokiri_012_Adult', 'Npc_Kokiri_012_Child', 'Npc_Kokiri_013_Adult', 'Npc_Kokiri_013_Child',
        'Npc_Kokiri_Fado_Adult', 'Npc_Kokiri_Fado_Child', 'Npc_Kokiri_Mido_Adult', 'Npc_Kokiri_Mido_Child',
        'Npc_Kokiri_Saria_Child',
    ),
}


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def zone_flows(enabled):
    """Flows changed by the option (every zone of the white list)."""
    return tuple(sorted({n for names in ZONES.values() for n in names})) if enabled else ()


def _action(event):
    from evfl.event import ActionEvent
    data = event.data
    return data.actor_action.v.v if isinstance(data, ActionEvent) else None


def _params(event):
    params = getattr(event.data, 'params', None)
    return dict(params.data) if params is not None and params.data else {}


def _is_talk(event):
    return _action(event) in TALK_ACTIONS


def _offers_choice(event):
    """True unless ``ChoiceNumber`` is the integer 0 (an entry argument counts as a choice)."""
    count = _params(event).get('ChoiceNumber', 0)
    return not (isinstance(count, int) and not isinstance(count, bool) and count == 0)


def _is_choice_query(event):
    from evfl.event import SwitchEvent
    data = event.data
    return isinstance(data, SwitchEvent) and data.actor_query.v.v.startswith(CHOICE_QUERY_PREFIX)


def _reach(chart, starts, stops=()):
    """Events reachable from ``starts`` (not past ``stops``), local sub-flows entered and
    returned from: after a call, what follows the call is reached too, and when an entry
    called by this flow is reached, so is what follows each of its calls."""
    from evfl.event import SubFlowEvent
    from oot_rando.patching.skip_auto import _reach as forward, _successors
    entries = {e.name: e for e in chart.entry_points}
    calls = {}
    for event in chart.events:
        data = event.data
        if isinstance(data, SubFlowEvent) and not data.res_flowchart_name and data.entry_point_name in entries:
            calls.setdefault(data.entry_point_name, []).append(event)
    bodies = {name: {e.name for e in forward(chart, [entries[name].main_event.v], descend=False)}
              for name in calls if entries[name].main_event.v is not None}
    seen, todo, returned = {}, list(starts), set()
    while todo:
        for event in forward(chart, todo, stops):
            seen.setdefault(event.name, event)
        todo = []
        for name, body in bodies.items():
            if name not in returned and body & set(seen):
                returned.add(name)
                for call in calls[name]:
                    todo.extend(e for e in _successors(call) if e.name not in seen)
    return list(seen.values())


def plan(chart):
    """What changes in ``chart``: dict of event lists (``talks``, ``closes``, ``speakers``
    taken out; ``close_dialog``: kept lines that now close their box; ``alone``: lines
    kept because their entry would be empty)."""
    from oot_rando.patching.skip_auto import _roots, _successors
    reached = _reach(chart, _roots(chart))
    asked = [e for e in reached if (_is_talk(e) and _offers_choice(e)) or _is_choice_query(e)]
    answers = {e.name for e in _reach(chart, asked)}
    talks = [e for e in reached if _is_talk(e) and e.name not in answers]
    alone = [e for e in talks if not _removable(chart, e)]
    dropped = {e.name for e in talks} - {e.name for e in alone}
    kept = [e for e in reached if _is_talk(e) and e.name not in dropped]
    kept_names = {e.name for e in kept}
    after_kept = {e.name for e in _reach(chart, kept)}
    closes = [e for e in reached if _action(e) == CLOSE_ACTION and e.name not in after_kept
              and _removable(chart, e)]
    speakers = [e for e in reached if _action(e) == SPEAKER_ACTION and _removable(chart, e)
                and not kept_names & {f.name for f in _reach(chart, [e])}]
    close_dialog = []
    for talk in kept:
        if _params(talk).get('IsCloseDialog', True) is not False:
            continue
        if dropped & {e.name for e in _reach(chart, _successors(talk), kept_names)}:
            close_dialog.append(talk)
    by_name = lambda events: sorted(events, key=lambda e: e.name)
    return {'talks': by_name(e for e in talks if e.name in dropped), 'closes': by_name(closes),
            'speakers': by_name(speakers), 'close_dialog': by_name(close_dialog), 'alone': by_name(alone)}


def _following(event):
    return event.data.nxt.v if event.data.nxt is not None else None


def _removable(chart, event):
    """False when taking ``event`` out would leave an entry or a fork branch with nothing."""
    from oot_rando.patching.qol_patches import _predecessors
    return _following(event) is not None or not any(kind in ('entry', 'fork')
                                                    for _, kind, _ in _predecessors(chart, event))


def _take_out(chart, event):
    """Every link to ``event`` goes to what follows it (see :func:`_removable`)."""
    from evfl.util import Index, make_index
    from oot_rando.patching.qol_patches import _predecessors
    following = _following(event)
    for owner, kind, key in _predecessors(chart, event):
        if kind == 'nxt':
            owner.data.nxt = make_index(following) if following is not None else Index()
        elif kind == 'case':
            if following is None:
                del owner.data.cases[key]
            else:
                owner.data.cases[key] = make_index(following)
        elif kind == 'fork':
            owner.data.forks[key] = make_index(following)
        else:
            owner.main_event = make_index(following)


def mute(raw, flow):
    """Returns (bytes, report): ``flow``'s lines without a choice taken out.

    report = {'talks', 'closes', 'speakers', 'close_dialog', 'alone'}: sorted event names.
    Raises ValueError when there is nothing to take out."""
    from oot_rando.patching.progressive import FlowEditor
    editor = FlowEditor(raw, flow)
    chart = editor.chart
    changes = plan(chart)
    if not changes['talks']:
        raise ValueError('No NPC line to take out: ' + flow)
    report = {key: set() for key in changes}
    # Taking a line out can leave the next one starting an entry with nothing after it:
    # planned again until nothing moves (that one is then kept, ``alone``).
    for _ in range(len(chart.events)):
        for talk in changes['close_dialog']:
            talk.data.params.data['IsCloseDialog'] = True
            editor.expected[talk.name]['IsCloseDialog'] = True
        moved = False
        for event in changes['talks'] + changes['closes'] + changes['speakers']:
            if _removable(chart, event):
                _take_out(chart, event)
                moved = True
        for key, events in changes.items():
            report[key] |= {e.name for e in events}
        changes = plan(chart)
        if not moved or not any(changes[k] for k in ('talks', 'closes', 'speakers', 'close_dialog')):
            break
    report['alone'] = {e.name for e in changes['alone']}
    for key in ('talks', 'closes', 'speakers'):
        report[key] -= report['alone']
    report = {key: sorted(names) for key, names in report.items()}
    result, _ = editor.write('NPC dialogue skip')
    if not muted(result):
        raise ValueError('NPC lines still shown: ' + flow)
    return result, report


def muted(raw):
    """Whether every line without a choice still reached is one kept on purpose (alone)."""
    from oot_rando.patching.event_patch import _flow
    changes = plan(_flow(raw).flowchart)
    return not (changes['talks'] or changes['closes'] or changes['speakers'] or changes['close_dialog'])


def scan(read_flow, flow_names):
    """({flow: report}, {flow: reason}) for ``flow_names`` (vanilla flows)."""
    ok, kept = {}, {}
    for name in sorted(flow_names):
        raw = read_flow(flow_path(name))
        if raw is None:
            kept[name] = 'missing'
            continue
        try:
            ok[name] = mute(raw, name)[1]
        except ValueError as error:
            kept[name] = str(error)
    return ok, kept
