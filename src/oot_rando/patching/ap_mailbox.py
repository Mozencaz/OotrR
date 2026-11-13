"""Archipelago item reception: global watchers that start item-get events.

The game re-reads none of its files during a session (in-game test 12/11: a flow
rewritten while the game runs is only taken at the next game start), so the only
instant signal from outside is a GameData Bool written in the game's memory by the
client. Everything else is in the mod, the same on Hookshot and on emulators.

The items other worlds can send are known when the mod is built (the patch's
``remote`` list; never a progressive item: those stay local). Each one, a *record*:

* ``RandoAP.Recv.<key>``: the client's signal (written in memory);
* ``RandoAP.Got.<key>``: saved, set once the item was handed over. The client reads it
  to know what the game already has (a reload of an older save gives it again);
* ``Sequence/MainUpdate.module.ainb`` (the global sequence, every frame of play) gets,
  per record, the pattern of ``Sequence/AfterEvent.module.ainb`` (nodes 36→37→38):
  Recv true → request the event ``RandoAP_<key>`` and set Recv back to false;
* the ``EventSetting`` row ``RandoAP_<key>`` (copied from a sequence-requested one:
  PlayerPos, FlowchartEvent) plays the entry point ``RandoAP_<key>`` added to
  ``Dm_SY_GetInEvent``: the vanilla item get with Link's pose
  (``GetInEvent_NotTurn_NotNpc``, as the Deku Tree gift) of the item's chest actor
  (one that is shown held up), then Got = true;
* its ``GameAnalyzedEventInfo`` row lists every flow that entry calls.

In-game test 12/11 (Hookshot): signal → pose and text at once. A consumable actor
(``Item_DekuNut``) showed no model and played its use effect: chest actors are used.
"""
import copy
import hashlib
import io

PREFIX = 'RandoAP_'
RECV, GOT = 'RandoAP.Recv.', 'RandoAP.Got.'
FLOW = 'Dm_SY_GetInEvent'
FLOW_PATH = 'Event/EventFlow/Dm_SY_GetInEvent.bfevfl.zs'
GET_ENTRY = 'GetInEvent_NotTurn_NotNpc'
MAIN_UPDATE = 'Sequence/MainUpdate.module.ainb'
EVENT_SETTINGS = 'RSDB/EventSetting.Product.111.rstbl.byml.zs'
ANALYZED = 'RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs'
TEMPLATE_ROW = 'CrumblingGanonCastle_Arrive'     # PlayerPos + FlowchartEvent, started without an actor
TEMPLATE_ANALYZED = 'NaviLockOnHint'             # requested by the sequence, no recorded camera


def record_key(player, location):
    """Stable key of an item found by ``player`` at ``location`` (their names)."""
    return hashlib.sha256(f'{player}\0{location}'.encode('utf-8')).hexdigest()[:12]


def records(remote):
    """One record per item of this game found in another world (the patch's ``remote``)."""
    from oot_rando.game.item_forms import form_actor
    from oot_rando.game.remake_world import PROGRESSIVE
    result, seen = [], set()
    for entry in remote:
        key = record_key(entry['player'], entry['location'])
        if key in seen:
            raise ValueError('Two remote items share a key: ' + key)
        seen.add(key)
        if entry['item'] in PROGRESSIVE:
            # Tier chosen in game: the one above the highest Link holds (see add_entries).
            tiers = list(PROGRESSIVE[entry['item']])
            result.append({'key': key, 'item': entry['item'], 'player': entry['player'],
                           'location': entry['location'], 'actor': tiers[0], 'tiers': tiers, 'style': 'progressive',
                           'event': PREFIX + key, 'recv': RECV + key, 'got': GOT + key})
            continue
        actor = form_actor(remote_actor(entry['item']), 'chest')
        result.append({'key': key, 'item': entry['item'], 'player': entry['player'], 'location': entry['location'],
                       'actor': actor, 'style': 'pickup' if is_consumable(entry['item']) else 'get',
                       'event': PREFIX + key, 'recv': RECV + key, 'got': GOT + key})
    return result


# Actors that cannot be held up by Link's item-get pose: the ocarinas are the
# accessory Link plays (no Item_EventObject_Base parent, in-game test 13/11: the
# get showed nothing and crashed, null read). They are handed over as Saria does
# (Dm_Kokiri_0155 Event68/Event77): added to the pouch, then the get display
# GetPouchContent/DisplayGetByActorName, without the pose.
DISPLAY_ONLY = ('Item_Ocarina_Fairy', 'Item_Ocarina_Time')
DISPLAY_FLOW, DISPLAY_ENTRY = 'GetPouchContent', 'DisplayGetByActorName'


def given_actor(event):
    """(actor, event after the hand-over) of a hand-over written by add_entries, or (None, None)."""
    params = event.data.params.data if event.data.params else {}
    if getattr(event.data, 'entry_point_name', None) == GET_ENTRY:
        return params.get('ActorName'), event.data.nxt.v
    show = event.data.nxt.v if getattr(event.data, 'nxt', None) is not None else None
    if (show is not None and getattr(show.data, 'entry_point_name', None) == DISPLAY_ENTRY
            and show.data.res_flowchart_name == DISPLAY_FLOW
            and show.data.params.data.get('ActorName') == params.get('Actor')):
        return params.get('Actor'), show.data.nxt.v
    return None, None


def tier_events(record):
    """(check event, held tier, given tier) of a progressive record, highest tier first.

    Link holding tier k gets tier k + 1; holding the last one, the last one again
    (the pool has no copy beyond its tiers: a harmless fallback, never an empty get).
    Holding none: the first tier (event ``<name>_Give0``).
    """
    tiers, name = record['tiers'], record['event']
    last = len(tiers) - 1
    return [(name if k == last else f'{name}_Has{k}', k, min(k + 1, last)) for k in range(last, -1, -1)]


def remote_actor(item):
    """Actor handed over for an item received from another world.

    Dungeon keys there are the seed's own key actors (``key_adapter``: built for the
    received ones too, see :func:`key_items`), never the generic remake keys, which the
    game credits to the dungeon Link stands in (none outside a dungeon).
    """
    from oot_rando.game.remake_world import item_actor
    from oot_rando.patching.key_adapter import BOSS_KEY_DUNGEONS, DUNGEON_FOLDER, boss_actor
    if item.startswith('Boss Key ('):
        folder = DUNGEON_FOLDER.get(item[len('Boss Key ('):-1])
        if folder in BOSS_KEY_DUNGEONS:
            return boss_actor(folder)
    try:
        actor = item_actor(item, None)
    except KeyError as error:   # a key ring of a dungeon without one in the remake
        raise ValueError('No remake actor for: ' + item) from error
    if actor.startswith('Item_Dungeon_'):
        raise ValueError('A dungeon item tied to its dungeon cannot come from another world: ' + item)
    return actor


def key_items(items):
    """AP names of the dungeon-specific keys among reception records (their actors must be built)."""
    from oot_rando.patching.key_adapter import is_key_actor
    return sorted({record['item'] for record in items if is_key_actor(record['actor'])})


# Consumables arrive as a ground pickup would (user request 12/11): no pose, no message,
# the count shown above Link (the pick-up window Dm_SY_Get/PouchAddItem opens).
CONSUMABLE_PREFIXES = ('Rupee (', 'Rupees (', 'Deku Nuts (', 'Deku Stick (', 'Deku Seeds (', 'Bombs (',
                       'Bombchus (', 'Arrows (')
CONSUMABLES = ('Recovery Heart', 'Remake: Magic Jar', 'Remake: Scrub Seed')


def is_consumable(item):
    return item.startswith(CONSUMABLE_PREFIXES) or item in CONSUMABLES


def add_entries(raw, items):
    """Entry point per record in Dm_SY_GetInEvent, then Got = true.

    ``get``: the item get of its actor (Link's pose, message). ``pickup``: the silent
    add a chest makes (GetPouchContent/GetPouchContent: ``EventTriggerAddOrRemovePouchContent``
    of the chest actor) and the pick-up window above Link (Dm_SY_Get/PouchAddItem Event45).
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.entry_point import EntryPoint
    from evfl.event import Event, ActionEvent, SubFlowEvent, SwitchEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    entries = {e.name for e in chart.entry_points}
    events = {e.name for e in chart.events}
    if GET_ENTRY not in entries:
        raise ValueError('Item get entry point missing: ' + GET_ENTRY)
    def action_of(identifier, name):
        owner = next((a for a in chart.actors if str(a.identifier) == identifier), None)
        if owner is None:
            if identifier != 'GameDataActor':
                raise ValueError(f'{FLOW} has no {identifier}.')
            owner = Actor()
            owner.identifier = ActorIdentifier('GameDataActor')
            owner.concurrent_clips = 1
            owner.params = Container()
            owner.params.data = dict(GAMEDATA_ACTOR_PARAMS)
            chart.actors.append(owner)
        found = next((a for a in owner.actions if a.v == name), None)
        if found is None:
            found = StringHolder(name)
            owner.actions.append(found)
        return owner, found

    def query_of(identifier, name):
        owner = next((a for a in chart.actors if str(a.identifier) == identifier), None)
        if owner is None:
            raise ValueError(f'{FLOW} has no {identifier}.')
        found = next((q for q in owner.queries if q.v == name), None)
        if found is None:
            found = StringHolder(name)
            owner.queries.append(found)
        return owner, found

    def subflow_event(name, flowchart, entry, params):
        event = Event()
        event.name, event.data = name, SubFlowEvent()
        event.data.res_flowchart_name = flowchart
        event.data.entry_point_name = entry
        event.data.params = Container()
        event.data.params.data = params
        chart.events.append(event)
        expected[name] = dict(params)
        return event

    def give_events(name, actor):
        """(first event, last event, sub-flow events) handing ``actor`` over."""
        if actor in DISPLAY_ONLY:
            add = action_event(name, 'PouchSystemActor', 'EventTriggerAddOrRemovePouchContent', {
                'Num': 1, 'IsEquipDIrect': False, 'IsSetMessageTargetActorName': True, 'Actor': actor,
                'IsGetEvent': False})
            show = subflow_event(name + '_Show', DISPLAY_FLOW, DISPLAY_ENTRY, {'ActorName': actor})
            add.data.nxt = make_index(show)
            return add, show, [show]
        event = subflow_event(name, '', GET_ENTRY, {'ActorName': actor, 'IsNpcEventStarter': False})
        return event, event, [event]

    def action_event(name, identifier, action, params):
        event = Event()
        event.name, event.data = name, ActionEvent()
        owner, found = action_of(identifier, action)
        event.data.actor, event.data.actor_action = make_rindex(owner), make_rindex(found)
        event.data.params = Container()
        event.data.params.data = params
        chart.events.append(event)
        expected[name] = dict(params)
        return event

    for record in items:
        name = record['event']
        if name in entries or {name, name + '_Show', name + '_Got'} & events:
            raise ValueError('Reception entry point already present: ' + name)
        if record['style'] == 'progressive':
            got = action_event(name + '_Got', 'GameDataActor', 'EventTriggerSetGameDataBool',
                               {'GameDataName': record['got'], 'Index': -1, 'Value': True})
            tiers = record['tiers']
            otherwise, last, gives = give_events(name + '_Give0', tiers[0])
            last.data.nxt = make_index(got)
            owner, query = query_of('PouchSystemActor', 'EventQueryIsExistInPouch')
            # Built from the lowest tier up: each check falls back to the one below it.
            for check_name, held, given in reversed(tier_events(record)):
                give, last, subs = give_events(f'{name}_Give{given}_From{held}', tiers[given])
                last.data.nxt = make_index(got)
                gives.extend(subs)
                check = Event()
                check.name, check.data = check_name, SwitchEvent()
                check.data.actor, check.data.actor_query = make_rindex(owner), make_rindex(query)
                check.data.params = Container()
                check.data.params.data = {'Actor': tiers[held], 'Num': 1}
                check.data.cases = {0: make_index(give), 1: make_index(otherwise)}   # case 0 = true
                chart.events.append(check)
                expected[check_name] = dict(check.data.params.data)
                otherwise = check
            entry = EntryPoint(name)
            entry.main_event = make_index(otherwise)
            entry._sub_flow_event_indices = [chart.events.index(g) for g in gives]
            chart.entry_points.append(entry)
            continue
        if record['style'] == 'pickup':
            first = action_event(name, 'PouchSystemActor', 'EventTriggerAddOrRemovePouchContent', {
                'Num': 1, 'IsEquipDIrect': False, 'IsSetMessageTargetActorName': False,
                'Actor': record['actor'], 'IsGetEvent': False})
            show = action_event(name + '_Show', 'UISystemActor', 'EventTriggerRequestOpenPickUpWindow',
                                {'ActorName': record['actor']})
            first.data.nxt = make_index(show)
            last, sub_flows = show, []
        else:
            first = Event()
            first.name, first.data = name, SubFlowEvent()
            first.data.entry_point_name = GET_ENTRY
            first.data.params = Container()
            first.data.params.data = {'ActorName': record['actor'], 'IsNpcEventStarter': False}
            chart.events.append(first)
            expected[name] = dict(first.data.params.data)
            last, sub_flows = first, [len(chart.events) - 1]
        got = action_event(name + '_Got', 'GameDataActor', 'EventTriggerSetGameDataBool',
                           {'GameDataName': record['got'], 'Index': -1, 'Value': True})
        last.data.nxt = make_index(got)
        entry = EntryPoint(name)
        entry.main_event = make_index(first)
        entry._sub_flow_event_indices = sub_flows
        chart.entry_points.append(entry)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The reception entries changed other parameters.')
    written = {e.name: e for e in checked.flowchart.entry_points}
    for record in items:
        if record['style'] == 'progressive':
            _check_tiers(written[record['event']], record)
            continue
        chain, event = [], written[record['event']].main_event.v
        while event is not None:
            chain.append(event.name)
            event = event.data.nxt.v if getattr(event.data, 'nxt', None) is not None else None
        name = record['event']
        wanted = [name, name + '_Show', name + '_Got'] if record['style'] == 'pickup' else [name, name + '_Got']
        if chain != wanted:
            raise ValueError('Reception entry wrongly chained: ' + name)
    return result


def _check_tiers(entry, record):
    """The written chain of a progressive record: each check, the tier it gives, then Got."""
    name, tiers = record['event'], record['tiers']
    event = entry.main_event.v
    for check_name, held, given in tier_events(record):
        if event is None or event.name != check_name or event.data.params.data.get('Actor') != tiers[held]:
            raise ValueError('Progressive reception wrongly chained: ' + name)
        actor, after = given_actor(event.data.cases[0].v)
        if actor != tiers[given] or after is None or after.name != name + '_Got':
            raise ValueError('Progressive reception gives the wrong tier: ' + name)
        event = event.data.cases[1].v
    if event is None:
        raise ValueError('Progressive reception without its first tier: ' + name)
    actor, after = given_actor(event)
    if event.name != name + '_Give0' or actor != tiers[0] or after is None or after.name != name + '_Got':
        raise ValueError('Progressive reception without its first tier: ' + name)


def add_event_rows(settings_raw, items):
    """EventSetting row per record, playing ``FLOW``/its entry."""
    from oot_rando.formats import byml_codec
    document = byml_codec.load(settings_raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    for record in items:
        if record['event'] in by_id:
            raise ValueError('EventSetting row already present: ' + record['event'])
        row = copy.deepcopy(by_id[TEMPLATE_ROW])
        row.pop('EventEffectSetting', None)
        row['__RowId'] = record['event']
        row['FlowchartFileName'] = f'Work/Event/EventFlow/{FLOW}.evfc'
        row['EntryPointName'] = record['event']
        rows.append(row)
        by_id[record['event']] = row
    rows.sort(key=lambda r: r['__RowId'])
    return byml_codec.dump(document)


def add_analyzed_rows(info_raw, items, current):
    """GameAnalyzedEventInfo row per record: every flow its entry calls, transitively.

    ``current(name)``: the flow as written in the seed. Events the entry starts by
    ``EventTransition`` (with the events they list) go to ``ChildEventList``. The item
    gets make the same calls (one analysis serves them all); a pick-up calls nothing.
    """
    from oot_rando.formats import byml_codec
    from oot_rando.patching.event_info import closure, reachable_transitions
    document = byml_codec.load(info_raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    template = copy.deepcopy(by_id[TEMPLATE_ANALYZED])
    plain = copy.deepcopy(template)
    gets = [record for record in items if record['style'] in ('get', 'progressive')]
    if gets:
        call = (FLOW, gets[0]['event'])
        flows = closure({call}, current) - {FLOW}
        if flows:
            template['SubFlowList'] = sorted(flows, key=str.lower)
        children = set(reachable_transitions(call, current))
        for child in list(children):
            children.update((by_id.get(child) or {}).get('ChildEventList') or [])
        if children:
            template['ChildEventList'] = sorted(children, key=str.lower)
    for record in items:
        if record['event'] in by_id:
            raise ValueError('GameAnalyzedEventInfo row already present: ' + record['event'])
        row = copy.deepcopy(plain if record['style'] == 'pickup' else template)
        row['__RowId'] = record['event']
        rows.append(row)
        by_id[record['event']] = row
    rows.sort(key=lambda r: r['__RowId'])
    return byml_codec.dump(document), {'subflows': template.get('SubFlowList', []),
                                       'children': template.get('ChildEventList', [])}


def ainb_to_binary(document):
    """Serialize with ``ainb`` 0.2.17, whose writer pads an empty blackboard to 0x30
    bytes (``AINB.write``) while format 0x408 needs 0x38, as its own offsets count:
    that one write is widened (checked: vanilla sequence modules come back byte for byte)."""
    import ainb
    from ainb.common import AINBWriter
    script = ainb.AINB.from_dict(document)
    writer = AINBWriter(io.BytesIO(), name='AINB Writer')
    plain, widened = writer.write, []

    def write(data):
        if not widened and not script.blackboard and script.version >= 0x408 and data == bytes(0x30):
            widened.append(True)
            data = bytes(0x38)
        return plain(data)
    writer.write = write
    script.write(writer)
    result = writer.get_buffer()
    ainb.AINB.from_binary(result)
    return result


def _input(name, value, output=False):
    return {'Name': name, 'Default Value': value, 'Node Index': -1, 'Output Index': 0,
            'Flags': ['Uses Default', 'Is Output'] if output else ['Uses Default']}


# A node lists at most 255 children (u8 count): the watchers hang under groups of
# this size, each group a child of the root (a seed may receive hundreds of items).
WATCHER_GROUP = 64
WATCHER = ['SeqQueryGetNonStructGameDataBool', 'Element_BoolSelector', 'Element_Simultaneous',
           'SeqOneShotRequestEvent', 'SeqOneShotSetNonStructGameDataBool', 'SeqExecuteGenericDummyAction']


def patch_main_update(raw, items):
    """MainUpdate with one watcher per record: Recv → request its event, Recv = false."""
    import ainb
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    root = nodes[0]
    if root['Node Type'] != 'Element_Simultaneous' or 'Is Root Node' not in root['Flags']:
        raise ValueError('Unexpected MainUpdate root.')
    dummy = next(n for n in nodes if n['Name'] == 'SeqExecuteGenericDummyAction')
    selector_model = next(n for n in nodes if n['Node Type'] == 'Element_BoolSelector')
    first = len(nodes)
    once = {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]}

    def guid(index):
        return f'0a9a9a00-0000-4000-8000-{index:012x}'

    def user(index, name, inputs, outputs=None, flags=(), properties=None):
        return {'Node Type': 'UserDefined', 'Node Index': index, 'Name': name, 'GUID': guid(index),
                'Flags': list(flags), 'Queries': [], 'Attachments': [], 'Properties': properties or {},
                'Parameters': {'Inputs': inputs, 'Outputs': outputs or {}}, 'XLink Actions': [], 'Plugs': {}}

    groups = []
    for position, record in enumerate(items):
        if position % WATCHER_GROUP == 0:
            group = copy.deepcopy(root)
            group.update({'Node Index': len(nodes), 'GUID': guid(len(nodes)), 'Flags': [], 'Plugs': {'Child': []}})
            nodes.append(group)
            root['Plugs']['Child'].append({'Node Index': group['Node Index'], 'Name': ''})
            groups.append(group)
        query_i, selector_i, both_i, request_i, clear_i, idle_i = range(len(nodes), len(nodes) + 6)
        query = user(query_i, 'SeqQueryGetNonStructGameDataBool', {
            'Int': [_input('GameDataIndex', -1, True)], 'Bool': [_input('IsDirect', True)],
            'String': [_input('GameDataFullName', record['recv'])]},
            {'Bool': [{'Name': 'Value', 'Is Output': True}]}, ['Is Query'],
            {'Bool': [{'Name': 'OutputOnlyOnEnter', 'Default Value': False, 'Flags': []}]})
        selector = copy.deepcopy(selector_model)
        selector.update({'Node Index': selector_i, 'GUID': guid(selector_i), 'Queries': [query_i],
                         'Flags': [f for f in selector['Flags'] if f != 'Is Root Node']})
        selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False, 'Node Index': query_i,
                                                        'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
        selector['Plugs'] = {'Generic': [{'Node Index': query_i, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                             'Child': [{'Node Index': both_i, 'Name': 'True'}, {'Node Index': idle_i, 'Name': 'False'}]}
        both = copy.deepcopy(root)
        both.update({'Node Index': both_i, 'GUID': guid(both_i), 'Flags': [],
                     'Plugs': {'Child': [{'Node Index': request_i, 'Name': ''}, {'Node Index': clear_i, 'Name': ''}]}})
        request = user(request_i, 'SeqOneShotRequestEvent', {
            'Bool': [_input('IsBancParamValue', False, True)], 'String': [_input('EventName', record['event'])]},
            properties=once)
        clear = user(clear_i, 'SeqOneShotSetNonStructGameDataBool', {
            'Int': [_input('GameDataIndex', -1, True)], 'Bool': [_input('Value', False)],
            'String': [_input('GameDataFullName', record['recv'])]}, properties=once)
        idle = copy.deepcopy(dummy)
        idle.update({'Node Index': idle_i, 'GUID': guid(idle_i)})
        nodes.extend([query, selector, both, request, clear, idle])
        groups[-1]['Plugs']['Child'].append({'Node Index': selector_i, 'Name': ''})
    result = ainb_to_binary(document)
    check = ainb.AINB.from_binary(result).as_dict()['Nodes']
    group_count = -(-len(items) // WATCHER_GROUP)
    group_nodes = [c['Node Index'] for c in check[0]['Plugs']['Child'][len(check[0]['Plugs']['Child']) - group_count:]]
    for index, record in enumerate(items):
        group_index, slot = divmod(index, WATCHER_GROUP)
        group = first + group_index * (1 + WATCHER_GROUP * 6)
        base = group + 1 + slot * 6
        if group_nodes[group_index] != group or check[group]['Node Type'] != 'Element_Simultaneous':
            raise ValueError('MainUpdate watcher group not attached: ' + record['key'])
        if [n['Name'] or n['Node Type'] for n in check[base:base + 6]] != WATCHER:
            raise ValueError('MainUpdate watcher not written as expected: ' + record['key'])
        events = check[base + 3]['Parameters']['Inputs']['String'][0]['Default Value']
        if events != record['event'] or check[group]['Plugs']['Child'][slot]['Node Index'] != base + 1:
            raise ValueError('MainUpdate watcher not attached: ' + record['key'])
    return result
