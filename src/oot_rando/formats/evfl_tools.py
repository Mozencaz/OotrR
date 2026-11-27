"""Event flow (evfl) helpers shared by the patches, the verification and the tests.

Every flow is read with :func:`parse_flow`; the other helpers walk its events.
"""


def parse_flow(raw):
    from evfl import EventFlow
    flow = EventFlow()
    flow.read(raw)
    return flow


def params_by_event(flow):
    result = {}
    for event in flow.flowchart.events:
        params = getattr(event.data, 'params', None)
        result[event.name] = dict(params.data) if params is not None else None
    return result


def event_params_of(event):
    return dict(event.data.params.data) if event.data.params is not None else {}


def case_target(event, key):
    case = event.data.cases.get(key)
    return case.v if case is not None else None


def next_events(event):
    from evfl.event import ForkEvent, SwitchEvent
    data = event.data
    if isinstance(data, SwitchEvent):
        return [c.v for c in data.cases.values() if c.v is not None]
    if isinstance(data, ForkEvent):
        return [f.v for f in data.forks] + [data.join.v]
    nxt = getattr(data, 'nxt', None)
    return [nxt.v] if nxt is not None and nxt.v is not None else []


def links_to(chart, target):
    """(event, kind, key) for every link to ``target`` (entry points as ('entry', ep))."""
    links = []
    for event in chart.events:
        data = event.data
        if getattr(data, 'nxt', None) is not None and data.nxt.v is target:
            links.append((event, 'nxt', None))
        for key, case in (getattr(data, 'cases', None) or {}).items():
            if case.v is target:
                links.append((event, 'case', key))
        for index, fork in enumerate(getattr(data, 'forks', None) or []):
            if fork.v is target:
                links.append((event, 'fork', index))
    for entry in chart.entry_points:
        if entry.main_event.v is target:
            links.append((entry, 'entry', None))
    return links
