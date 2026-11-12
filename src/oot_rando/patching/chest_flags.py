"""Per-chest opening flags (tracking and Archipelago).

Save tests (12/11, Hookshot): opening a chest writes no flag of its own to
``progress.sav`` (its ``Bool64bitKey`` hash never appears, even for an ordinary
item); only the content's ``IsGet.*`` changes. So a chest gets its own saved Bool:

* its ``Dynamic.GetEventName`` (the ``EventSetting`` row run on opening; default
  ``Dm_SY_TreasureboxSmall``, ``Dm_SY_Treasurebox`` for the big chests) is replaced
  by a new row ``RandoChest_<hash>``, a copy of the original row with a new entry point;
* that entry point, added to the row's own flowchart, sets the flag
  (``GameDataActor.EventTriggerSetGameDataBool``) then runs the original entry
  point as a local sub-flow (same flowchart: no new dependency);
* the ``GameAnalyzedEventInfo`` row is copied from the original one, once every
  other patch has completed it (sub-flow and child event lists).

A Bool is also read live from the running game's memory (real-time tracking).
"""
import copy
import io

from oot_rando.formats import byml_codec

EVENT_SETTINGS = 'RSDB/EventSetting.Product.111.rstbl.byml.zs'
ANALYZED = 'RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs'
PREFIX = 'RandoChest_'
FLOWS = 'Event/EventFlow/'
BIG_CHESTS = ('Obj_TBox_A_02', 'Obj_TBox_A_03')


def default_event(gyaml):
    """Blackboard default of ``GetEventName`` (Obj_TBox_A_02 table for the big chests)."""
    return 'Dm_SY_Treasurebox' if gyaml.startswith(BIG_CHESTS) else 'Dm_SY_TreasureboxSmall'


def flag_name(identity, gid):
    return 'RandoCheck.' + identity[:16] + '.' + gid


def plan_records(placements, map_root, identity, settings_rows):
    """One record per shuffled chest whose opening event can be wrapped.

    ``map_root(resource)`` → current map root; ``settings_rows``: EventSetting rows by id.
    Returns (records, skipped gids with a reason).
    """
    records, skipped = [], {}
    for placement in placements:
        if placement.get('source') != 'chest' or not placement.get('variants'):
            continue
        gid = placement['id']
        variants, bases = [], set()
        for resource, index in placement['variants']:
            actor = map_root(resource)['Actors'][index]
            if not str(actor.get('Gyaml', '')).startswith('Obj_TBox'):
                bases.add(None)
                continue
            current = (actor.get('Dynamic') or {}).get('GetEventName')
            bases.add(current or default_event(actor['Gyaml']))
            variants.append({'resource': resource, 'index': index, 'before': current})
        if len(bases) != 1 or None in bases:
            skipped[gid] = 'variants without one chest event'
            continue
        base = bases.pop()
        row = settings_rows.get(base)
        if row is None or not str(row.get('FlowchartFileName', '')).endswith('.evfc'):
            skipped[gid] = 'unknown event ' + base
            continue
        flow = row['FlowchartFileName'].rsplit('/', 1)[-1][:-len('.evfc')]
        records.append({'id': gid, 'event': PREFIX + gid.rsplit('#', 1)[-1],
                        'base': base, 'entry': row['EntryPointName'], 'flow': FLOWS + flow + '.bfevfl.zs',
                        'flag': flag_name(identity, gid), 'variants': variants})
    names = [r['event'] for r in records]
    if len(names) != len(set(names)) or set(names) & set(settings_rows):
        raise ValueError('Chest event name collision.')
    return records, skipped


def map_edits(records):
    """resource → patch_strings edits pointing each chest variant at its own event."""
    edits = {}
    for record in records:
        for variant in record['variants']:
            edits.setdefault(variant['resource'], []).append(
                {'path': ('Actors', variant['index'], 'Dynamic', 'GetEventName'),
                 'before': variant['before'], 'after': record['event']})
    return edits


def add_rows(raw, records, rows_key='EntryPointName'):
    """EventSetting rows: copies of the original rows with the new entry point."""
    document = byml_codec.load(raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    for record in records:
        if record['event'] in by_id:
            raise ValueError('EventSetting row already present: ' + record['event'])
        row = copy.deepcopy(by_id[record['base']])
        row['__RowId'] = record['event']
        row[rows_key] = record['event']
        rows.append(row)
        by_id[record['event']] = row
    rows.sort(key=lambda row: row['__RowId'])
    return byml_codec.dump(document)


def add_analyzed_rows(raw, records):
    """GameAnalyzedEventInfo rows copied from the original events (when they have one)."""
    document = byml_codec.load(raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    added = 0
    for record in records:
        if record['event'] in by_id:
            raise ValueError('GameAnalyzedEventInfo row already present: ' + record['event'])
        base = by_id.get(record['base'])
        if base is None:
            continue
        row = copy.deepcopy(base)
        row['__RowId'] = record['event']
        rows.append(row)
        by_id[record['event']] = row
        added += 1
    rows.sort(key=lambda row: row['__RowId'])
    return byml_codec.dump(document), added


def add_entries(raw, records):
    """New entry points ``record['event']``: set ``record['flag']``, then run ``record['entry']``."""
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.entry_point import EntryPoint
    from evfl.event import Event, ActionEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    entries = {e.name for e in chart.entry_points}
    events = {e.name for e in chart.events}
    actor = next((a for a in chart.actors if str(a.identifier) == 'GameDataActor'), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier('GameDataActor')
        actor.concurrent_clips = 1
        actor.params = Container()
        actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        chart.actors.append(actor)
    action = next((a for a in actor.actions if a.v == 'EventTriggerSetGameDataBool'), None)
    if action is None:
        action = StringHolder('EventTriggerSetGameDataBool')
        actor.actions.append(action)
    for record in records:
        name, base = record['event'], record['entry']
        if base not in entries:
            raise ValueError(f'Chest entry point missing: {record["flow"]}/{base}')
        if name in entries or name in events or name + '_Run' in events:
            raise ValueError('Chest entry point already present: ' + name)
        mark = Event()
        mark.name, mark.data = name, ActionEvent()
        mark.data.actor, mark.data.actor_action = make_rindex(actor), make_rindex(action)
        mark.data.params = Container()
        mark.data.params.data = {'GameDataName': record['flag'], 'Index': -1, 'Value': True}
        run = Event()
        run.name, run.data = name + '_Run', SubFlowEvent()
        run.data.entry_point_name = base
        chart.events.append(mark)
        chart.events.append(run)
        mark.data.nxt = make_index(run)
        entry = EntryPoint(name)
        entry.main_event = make_index(mark)
        entry._sub_flow_event_indices = [len(chart.events) - 1]
        chart.entry_points.append(entry)
        expected[name] = dict(mark.data.params.data)
        expected[name + '_Run'] = None
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Chest flags changed unrelated parameters.')
    written = {e.name: e for e in checked.flowchart.entry_points}
    for record in records:
        mark = written[record['event']].main_event.v
        if (mark.name != record['event'] or mark.data.nxt.v.name != record['event'] + '_Run'
                or mark.data.nxt.v.data.entry_point_name != record['entry']):
            raise ValueError('Chest entry point wrongly chained: ' + record['event'])
    return result


def by_flow(records):
    flows = {}
    for record in records:
        flows.setdefault(record['flow'], []).append(record)
    return flows
