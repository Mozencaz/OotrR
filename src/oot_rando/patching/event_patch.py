"""Exact edits of item parameters in BFEVFL event flows (NPC gifts).

Uses ``evfl`` (ZeldaMods, GPL-2.0-or-later, installed separately) to read and
write the flow; the writer reproduces the original bytes when nothing changes.
Only string parameters whose current value matches ``before`` are changed, and
the result is re-read to check that no other parameter moved.
"""
import io

# Parameters of GameDataActor in 896 of the 900 vanilla flows that declare it.
GAMEDATA_ACTOR_PARAMS = {
    'EventMemberCreateMethod': 0, 'IsBindNearestActor': False, 'IsGrounding': False,
    'IsWorld': False, 'UseEventModelAnime': '使用しない', 'UseEventAS': '使用しない',
}


def _flow(raw):
    from evfl import EventFlow
    flow = EventFlow()
    flow.read(raw)
    return flow


def _snapshot(flow):
    result = {}
    for event in flow.flowchart.events:
        params = getattr(event.data, 'params', None)
        result[event.name] = dict(params.data) if params is not None else None
    return result


def patch_event_params(raw, edits):
    """``edits``: list of ``(event name, parameter, before, after)``. Returns new bytes."""
    flow = _flow(raw)
    events = {event.name: event for event in flow.flowchart.events}
    expected = _snapshot(flow)
    seen = set()
    for name, param, before, after in edits:
        if (name, param) in seen:
            raise ValueError(f'Duplicate event change: {name}.{param}')
        seen.add((name, param))
        if isinstance(before, int) and not isinstance(before, bool):
            if type(after) is not int or after < 0:   # numeric parameter (scrub price)
                raise ValueError('Invalid parameter value.')
        elif not isinstance(after, str) or not after or '\0' in after:
            raise ValueError('Invalid parameter value.')
        event = events.get(name)
        params = getattr(event.data, 'params', None) if event else None
        if params is None or params.data.get(param) != before:
            raise ValueError(f'Unexpected event parameter: {name}.{param}')
        params.data[param] = after
        expected[name][param] = after
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    if _snapshot(_flow(result)) != expected:
        raise ValueError('Semantic check of the event failed.')
    return result


def add_collection_markers(raw, markers):
    """Append a native saved-flag action after each completed gift, keeping its continuation.

    ``markers`` maps original gift event names to dedicated GameData flag names.
    A flag is set after the reward subflow/action returns, never before it starts.
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent
    from evfl.util import make_index, make_rindex
    flow = _flow(raw)
    chart = flow.flowchart
    events = {e.name: e for e in chart.events}
    expected = _snapshot(flow)
    actor = next((a for a in chart.actors if str(a.identifier) == 'GameDataActor'), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier('GameDataActor')
        actor.concurrent_clips = 1
        # The game dereferences every named actor's parameter container when the
        # actor is first used: a missing one crashes at the first marker (seen on
        # Hookshot at the end of the new-game intro). Use the vanilla definition.
        actor.params = Container()
        actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        chart.actors.append(actor)
    action = next((a for a in actor.actions if a.v == 'EventTriggerSetGameDataBool'), None)
    if action is None:
        action = StringHolder('EventTriggerSetGameDataBool')
        actor.actions.append(action)
    records = []
    for name, flag in sorted(markers.items()):
        original = events.get(name)
        if original is None or not hasattr(original.data, 'nxt'):
            raise ValueError('Reward event without continuation: ' + name)
        marker_name = 'RandoCollected_' + name
        if marker_name in events:
            raise ValueError('Duplicate collection marker: ' + name)
        event = Event()
        event.name, event.data = marker_name, ActionEvent()
        event.data.actor, event.data.actor_action = make_rindex(actor), make_rindex(action)
        event.data.params = Container()
        event.data.params.data = {'GameDataName': flag, 'Index': -1, 'Value': True}
        event.data.nxt = original.data.nxt
        original.data.nxt = make_index(event)
        chart.events.append(event)
        events[marker_name] = event
        expected[marker_name] = dict(event.data.params.data)
        records.append({'event': name, 'marker': marker_name, 'flag': flag})
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The marker changed parameters unrelated to collection.')
    written = next(a for a in checked.flowchart.actors if str(a.identifier) == 'GameDataActor')
    if written.params is None or not set(GAMEDATA_ACTOR_PARAMS) <= set(written.params.data):
        raise ValueError('GameDataActor actor without native parameters.')
    actual = {e.name: e for e in checked.flowchart.events}
    for record in records:
        if actual[record['event']].data.nxt.v is not actual[record['marker']]:
            raise ValueError('Invalid collection marker continuation.')
    return result, records


# PouchSystemActor parameters, identical in all 110 vanilla flows declaring it.
POUCH_ACTOR_PARAMS = GAMEDATA_ACTOR_PARAMS


def add_pouch_items(raw, after, actors):
    """Silently add pouch contents after event ``after`` (native cutscene action).

    Uses ``PouchSystemActor.EventTriggerAddOrRemovePouchContent`` exactly as the
    vanilla cutscenes do (e.g. Saria's ocarina), without a "get" message.
    Returns new bytes; the original continuation of ``after`` is preserved.
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent
    from evfl.util import make_index, make_rindex
    flow = _flow(raw)
    chart = flow.flowchart
    events = {e.name: e for e in chart.events}
    expected = _snapshot(flow)
    anchor = events.get(after)
    if anchor is None or not hasattr(anchor.data, 'nxt'):
        raise ValueError('Anchor event without continuation: ' + after)
    actor = next((a for a in chart.actors if str(a.identifier) == 'PouchSystemActor'), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier('PouchSystemActor')
        actor.concurrent_clips = 1
        actor.params = Container()
        actor.params.data = dict(POUCH_ACTOR_PARAMS)
        chart.actors.append(actor)
    action = next((a for a in actor.actions if a.v == 'EventTriggerAddOrRemovePouchContent'), None)
    if action is None:
        action = StringHolder('EventTriggerAddOrRemovePouchContent')
        actor.actions.append(action)
    previous = anchor
    names = []
    for item in actors:
        name = 'RandoStartItem_' + item
        if name in events:
            raise ValueError('Duplicate starting item: ' + item)
        event = Event()
        event.name, event.data = name, ActionEvent()
        event.data.actor, event.data.actor_action = make_rindex(actor), make_rindex(action)
        event.data.params = Container()
        event.data.params.data = {'Num': 1, 'IsEquipDIrect': False, 'IsSetMessageTargetActorName': False,
                                  'Actor': item, 'IsGetEvent': False}
        event.data.nxt = previous.data.nxt
        previous.data.nxt = make_index(event)
        chart.events.append(event)
        events[name] = event
        expected[name] = dict(event.data.params.data)
        previous = event
        names.append(name)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Adding starting items changed other parameters.')
    actual = {e.name: e for e in checked.flowchart.events}
    chain = actual[after]
    for name in names:
        if chain.data.nxt.v is not actual[name]:
            raise ValueError('Invalid starting item chain.')
        chain = actual[name]
    written = next(a for a in checked.flowchart.actors if str(a.identifier) == 'PouchSystemActor')
    if written.params is None or not set(POUCH_ACTOR_PARAMS) <= set(written.params.data):
        raise ValueError('PouchSystemActor actor without native parameters.')
    return result
