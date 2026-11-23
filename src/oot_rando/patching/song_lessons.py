"""Song lessons without their cutscene (option ``skip_song_lessons``).

A song lesson (``Dm_MelodyGet_*``) is started by an ``EventTransition`` in another
flow, its *trigger* (Malon: ``SubEvent_GetEponaSong``; Sheik: the sage quest flows).
With the option the transition never plays the lesson; in its place the trigger runs,
as OOTRR does (ootrando/ootrr, story_skip.rs ``patch_song_trigger``, reimplemented):

1. ``HavePlayedEvent.<lesson>`` = true (the lesson counts as seen);
2. after an arrival (``Dm_SY_BancChangeArrive``), a wait for the loading screen to close;
3. the vanilla item get with Link's pose (``Dm_SY_GetInEvent/GetInEvent_NotTurn_NotNpc``,
   as the Deku Tree gift and the Archipelago mailbox) of the item placed at the
   lesson's give event (read from the patched lesson flow, so whatever placement,
   song shuffle or Archipelago item it holds);
4. the check's collection marker (``RandoCheck.…``), when the lesson had one;
5. the lesson's own state, read from the vanilla lesson flow (:func:`scene_state`):
   every GameData and quest write it can run (but its song's ``IsGet``) and the calls
   that carry state (:data:`KEPT_CALLS`, Sheik's meeting counter).

Other scenes the trigger plays around the lesson (:attr:`Lesson.cut`: the Royal
Family's Tomb's teaching and sun movies) are replaced by their ``HavePlayedEvent``
alone. The music stop right before the lesson is bypassed: the area music goes on.

The talk, the ocarina minigame, the camera and the music stop never play. The
lesson flow itself is left as patched (never played any more).

Loading: every trigger entry that reaches a new call lists it among its sub-flow
events (``EntryPoint._sub_flow_event_indices``; OOTRR saw an unlisted call crash the
game), and ``randomizer_core.complete_event_info`` lists ``Dm_SY_GetInEvent`` and
what it calls in the event row's ``SubFlowList`` (``event_info``), which it does
for any changed flow calling a new external flow.

A song held up needs a model and animation: ``song_models`` supplies the coloured
harp, and ``story_shortcuts`` changes the held actor to its animated world form.

The ten adapters here are complemented by ``story_shortcuts.extra_song``:
the Time lesson has two rewards, and Requiem is started by the map. Those two
special cases stay outside this generic adapter's registry (:data:`NOT_SKIPPED`).
Not validated in game.
"""
from collections import namedtuple

Lesson = namedtuple('Lesson', 'ap stem grant actor trigger cut')
# AP location -> (trigger flow, other scenes of the trigger cut with the lesson).
TRIGGERS = {
    'Song from Impa': ('DoorOfTime', ()),
    'Song from Malon': ('SubEvent_GetEponaSong', ()),
    'Song from Saria': ('SacredForestMeadow', ()),
    'Song from Royal Familys Tomb': ('GimmickFlow_RoyalFamilyTomb', (
        'Dm_MelodyGet_Sun', 'Dm_MelodyGet_Sun_01', 'Dm_MelodyGet_Sun_04', 'Dm_MelodyGet_Sun_05',
        'Dm_MelodyGet_Sun_06', 'Dm_MelodyGet_Sun_07', 'Dm_MelodyGet_Sun_08', 'Dm_MelodyGet_Sun_09',
        'Dm_MelodyGet_Sun_10')),
    'Song from Windmill': ('Npc_Hylia_009_Adult', ()),
    'Sheik in Forest': ('SageOfForest', ()),
    'Sheik in Crater': ('SageOfFire', ()),
    'Sheik in Ice Cavern': ('SageOfWater', ()),
    'Sheik in Kakariko': ('Dm_SY_BancChangeArrive', ()),
    'Sheik at Temple': ('AllSage', ()),
}
NOT_SKIPPED = {
    'Song from Ocarina of Time': 'dedicated two-reward adapter in story_shortcuts',
    'Sheik at Colossus': 'dedicated map-entry adapter in story_shortcuts',
}


def _lessons():
    from oot_rando.patching.song_adapter import SONG_LOCATIONS
    found = []
    for ap, stem, grant, actor, _ in SONG_LOCATIONS:
        if ap in TRIGGERS:
            trigger, cut = TRIGGERS[ap]
            found.append(Lesson(ap, stem, grant, actor, trigger, cut))
    return tuple(found)


LESSONS = _lessons()
BY_AP = {lesson.ap: lesson for lesson in LESSONS}
GET_CALL = ('Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc')
# External calls of a lesson that carry state, replayed in the trigger.
KEPT_CALLS = (('AllSage', 'MeetSheik_And_Gone'),)
STATE_ACTORS = ('GameDataActor', 'ChallengeSystemActor')
STATE_ACTIONS = ('EventTriggerSetGameDataBool', 'EventTriggerSetGameDataInt', 'EventTriggerAddOrSubGameDataInt',
                 'EventExecuteProgressChallengeStep')
ARRIVAL_FLOWS = ('Dm_SY_BancChangeArrive',)
LOADING_WAIT = ('UISystemActor', 'EventWaitCloseLoadingFade', {'IsWaitEnd': True})
PREFIX = 'RandoLesson_'
MARKER_PREFIX = 'RandoCollected_'
FLOWS = 'Event/EventFlow/'


def lesson_locations(enabled):
    """AP locations whose lesson is skipped (empty when the option is off)."""
    return tuple(lesson.ap for lesson in LESSONS) if enabled else ()


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def _action(event):
    from evfl.event import ActionEvent
    data = event.data
    if not isinstance(data, ActionEvent):
        return None
    return str(data.actor.v.identifier), data.actor_action.v.v


def _params(event):
    params = getattr(event.data, 'params', None)
    return dict(params.data) if params is not None else {}


def _successors(event):
    data = event.data
    found = [c.v for c in (getattr(data, 'cases', None) or {}).values()]
    found += [f.v for f in (getattr(data, 'forks', None) or [])]
    for name in ('join', 'nxt'):
        link = getattr(data, name, None)
        if link is not None:
            found.append(link.v)
    return [e for e in found if e is not None]


def _reach(chart, starts, descend=True):
    """Events reachable from ``starts`` (``descend``: through local sub-flow calls)."""
    from evfl.event import SubFlowEvent
    entries = {e.name: e for e in chart.entry_points}
    seen, todo, order = set(), list(starts), []
    while todo:
        event = todo.pop()
        if event is None or event.name in seen:
            continue
        seen.add(event.name)
        order.append(event)
        data = event.data
        if descend and isinstance(data, SubFlowEvent) and not data.res_flowchart_name:
            called = entries.get(data.entry_point_name)
            if called is not None:
                todo.append(called.main_event.v)
        todo.extend(_successors(event))
    return order


def given_item(scene_raw, lesson):
    """{'actor', 'flag'}: what the (patched) lesson gives and its collection flag (or None)."""
    from evfl.event import SubFlowEvent
    from oot_rando.patching.event_patch import _flow
    events = {e.name: e for e in _flow(scene_raw).flowchart.events}
    grant = events.get(lesson.grant)
    if grant is None or not isinstance(grant.data, SubFlowEvent):
        raise ValueError('Unexpected song lesson give event: ' + lesson.stem + '/' + lesson.grant)
    actor = _params(grant).get('ActorName')
    if not isinstance(actor, str) or not actor:
        raise ValueError('Song lesson give without an item: ' + lesson.stem)
    from oot_rando.game.item_forms import OCARINAS
    if actor in OCARINAS:
        raise ValueError('An ocarina has no item-get pose: ' + lesson.ap)
    marker = events.get(MARKER_PREFIX + lesson.grant)
    flag = _params(marker).get('GameDataName') if marker is not None else None
    return {'actor': actor, 'flag': flag}


def scene_state(scene_raw, lesson):
    """The vanilla lesson's state: [('action', actor, action, params) | ('call', flow, entry, params)].

    Every GameData / quest write reachable from the lesson's start (file order), but
    the song flags (``IsGet.Item_Melody_*``, the item get sets its own) and
    ``HavePlayedEvent`` (written first), and the calls of :data:`KEPT_CALLS`."""
    from evfl.event import SubFlowEvent
    from oot_rando.patching.event_patch import _flow
    chart = _flow(scene_raw).flowchart
    start = next(e for e in chart.entry_points if e.name == 'EntryPoint0')
    reached = {e.name for e in _reach(chart, [start.main_event.v])}
    state = []
    for event in chart.events:
        if event.name not in reached:
            continue
        action = _action(event)
        if action is not None and action[0] == 'PouchSystemActor':
            raise ValueError('Song lesson adds another item: ' + lesson.stem)
        if action is not None and action[0] in STATE_ACTORS and action[1] in STATE_ACTIONS:
            params = _params(event)
            name = str(params.get('GameDataName', ''))
            if name.startswith(('IsGet.Item_Melody_', 'HavePlayedEvent.')):
                continue
            state.append(('action', action[0], action[1], params))
        elif isinstance(event.data, SubFlowEvent):
            call = (event.data.res_flowchart_name, event.data.entry_point_name)
            if call in KEPT_CALLS:
                state.append(('call', call[0], call[1], _params(event) or None))
    return state


def _transitions(chart, stem):
    return [e for e in chart.events if _action(e) == ('EventSystemActor', 'EventTransition')
            and _params(e).get('EventName') == stem]


def _redirect(chart, event, target):
    """Every link to ``event`` goes to ``target`` instead (raises when none)."""
    from evfl.util import make_index
    from oot_rando.patching.qol_patches import _predecessors
    links = _predecessors(chart, event)
    if not links:
        raise ValueError('Song lesson event never reached: ' + event.name)
    for owner, kind, key in links:
        if kind == 'nxt':
            owner.data.nxt = make_index(target)
        elif kind == 'case':
            owner.data.cases[key] = make_index(target)
        elif kind == 'fork':
            owner.data.forks[key] = make_index(target)
        else:
            owner.main_event = make_index(target)


def _music_stop(chart, transition):
    """The ``StopInGameBgm`` right before the transition (over Link joining), or None."""
    from oot_rando.patching.qol_patches import _predecessors
    current = transition
    for _ in range(2):
        links = _predecessors(chart, current)
        if len(links) != 1 or links[0][1] != 'nxt':
            return None
        current = links[0][0]
        action = _action(current)
        if action == ('SoundSystemActor', 'EventTriggerStopInGameBgm'):
            return current
        if action != ('Player_Event', 'EventTriggerParticipateEvent'):
            return None
    return None


def _names(site, state):
    base = PREFIX + site + '_'
    return {'played': base + 'Played', 'wait': base + 'LoadingWait', 'get': base + 'Get',
            'marker': base + 'Collected', 'state': [base + 'State%d' % i for i in range(len(state))]}


def give_in_trigger(trigger_raw, scene_raw, lesson, actor, flag):
    """Returns (bytes, report): the trigger gives ``actor`` with Link's pose instead of the lesson.

    ``scene_raw``: the vanilla lesson flow (its state and actor definitions)."""
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier
    from evfl.container import Container
    from oot_rando.patching.progressive import FlowEditor, link
    from oot_rando.patching.event_patch import _flow
    state = scene_state(scene_raw, lesson)
    scene_actors = {str(a.identifier): a for a in _flow(scene_raw).flowchart.actors}
    editor = FlowEditor(trigger_raw, lesson.trigger)
    chart = editor.chart
    events = {e.name: e for e in chart.events}
    if any(name.startswith(PREFIX) for name in events):
        raise ValueError('Song lesson already given in its trigger: ' + lesson.trigger)
    sites = _transitions(chart, lesson.stem)
    if not sites:
        raise ValueError('The song lesson trigger no longer plays ' + lesson.stem + ': ' + lesson.trigger)
    for kind, identifier, *_ in state:
        if kind == 'action' and not any(str(a.identifier) == identifier for a in chart.actors):
            # Same actor as in the lesson (a system actor and its parameters).
            source = scene_actors[identifier]
            owner = Actor()
            owner.identifier = ActorIdentifier(identifier)
            owner.concurrent_clips = source.concurrent_clips
            owner.params = Container()
            owner.params.data = dict(source.params.data) if source.params is not None else {}
            chart.actors.append(owner)
    report = {'trigger': lesson.trigger, 'sites': [], 'cut': [], 'music': []}
    calls = []
    for transition in sites:
        stop = _music_stop(chart, transition)
        if stop is not None:
            _redirect(chart, stop, stop.data.nxt.v)
            report['music'].append(stop.name)
        names = _names(transition.name, state)
        chain = [editor.action(names['played'], 'GameDataActor', 'EventTriggerSetGameDataBool',
                               {'GameDataName': 'HavePlayedEvent.' + lesson.stem, 'Value': True, 'Index': -1})]
        if lesson.trigger in ARRIVAL_FLOWS:
            chain.append(editor.action(names['wait'], *LOADING_WAIT))
        get = editor.subflow(names['get'], *GET_CALL, {'ActorName': actor, 'IsNpcEventStarter': False})
        chain.append(get)
        calls.append(get)
        if flag:
            chain.append(editor.action(names['marker'], 'GameDataActor', 'EventTriggerSetGameDataBool',
                                       {'GameDataName': flag, 'Value': True, 'Index': -1}))
        for name, (kind, first, second, params) in zip(names['state'], state):
            if kind == 'action':
                chain.append(editor.action(name, first, second, params))
            else:
                chain.append(editor.subflow(name, first, second, params))
                calls.append(chain[-1])
        following = transition.data.nxt.v if transition.data.nxt is not None else None
        for event, nxt in zip(chain, chain[1:] + [following]):
            link(event, nxt)
        _redirect(chart, transition, chain[0])
        report['sites'].append({'transition': transition.name, 'chain': [e.name for e in chain]})
    for scene in lesson.cut:
        for transition in _transitions(chart, scene):
            played = editor.action(PREFIX + transition.name + '_Played', 'GameDataActor',
                                   'EventTriggerSetGameDataBool',
                                   {'GameDataName': 'HavePlayedEvent.' + scene, 'Value': True, 'Index': -1})
            link(played, transition.data.nxt.v if transition.data.nxt is not None else None)
            stop = _music_stop(chart, transition)
            if stop is not None:
                _redirect(chart, stop, stop.data.nxt.v)
                report['music'].append(stop.name)
            _redirect(chart, transition, played)
            report['cut'].append({'transition': transition.name, 'scene': scene})
    # Every entry that reaches a new call lists it (the game prepares only those).
    for entry in chart.entry_points:
        reached = {e.name for e in _reach(chart, [entry.main_event.v], descend=False)}
        for call in calls:
            index = chart.events.index(call)
            if call.name in reached and index not in entry._sub_flow_event_indices:
                entry._sub_flow_event_indices.append(index)
    result, _ = editor.write('Song lesson trigger')
    if not trigger_applied(result, lesson, actor, flag):
        raise ValueError('Song lesson trigger not written: ' + lesson.trigger)
    return result, report


def trigger_applied(raw, lesson, actor, flag):
    """Whether ``raw`` gives ``actor`` with its pose wherever the lesson played and never plays it."""
    from evfl.event import SubFlowEvent
    from oot_rando.patching.event_patch import _flow
    chart = _flow(raw).flowchart
    events = {e.name: e for e in chart.events}
    sites = [e for e in _transitions(chart, lesson.stem)]
    reached = {e.name for e in _reach(chart, [e.main_event.v for e in chart.entry_points])}
    if not sites:
        return False
    for transition in sites:
        names = _names(transition.name, [])
        get = events.get(names['get'])
        if transition.name in reached or get is None or not isinstance(get.data, SubFlowEvent):
            return False
        from oot_rando.patching.cinematic_tools import held_actor
        if ((get.data.res_flowchart_name, get.data.entry_point_name) != GET_CALL
                or _params(get).get('ActorName') not in (actor, held_actor(actor))):
            return False
        if get.name not in reached:
            return False
        index = chart.events.index(get)
        for entry in chart.entry_points:
            direct = {e.name for e in _reach(chart, [entry.main_event.v], descend=False)}
            if get.name in direct and index not in entry._sub_flow_event_indices:
                return False
        marker = events.get(names['marker'])
        if flag and (marker is None or marker.name not in reached or _params(marker).get('GameDataName') != flag):
            return False
    for scene in lesson.cut:
        if any(t.name in reached for t in _transitions(chart, scene)):
            return False
    return True
