"""Progressive items: every copy gives the level above the one Link holds.

A copy of a progressive family placed in this world is a *token*, a key item of its
own (``Item_Prog_<family>_<n>``, built like the souls and key rings with the model of
the family's first level). Unshuffled sources that give a fixed level (a chest left in
place, Darunia's bracelet) give a token too, so that no source hands out a lower level
than the one Link holds: bags, quivers, wallets, scales, strength and magic set their
value, so a lower level would take capacity away.

Every item get ends in ``ActionGuide/ActionGuide`` (chests, pickups, NPC gifts, great
fairies, scrubs, the Archipelago mailbox) or ``ActionGuide/ActionGuideForShop``
(shops). Both now first run ``ActionGuide/RandoProgressive``: for each token got
(``IsGet.<token>``, written by the pouch as for the souls) and not yet converted
(saved Bool ``RandoProg.<token>``), it marks it, takes it out of the pouch as the trade
items are, and gives the level above the highest one Link holds, with the get window
and without the pose (``GetPouchContent/GetPouchContentByActorName``, as the vanilla
NPC gifts). Holding the last level, the last one is given again. Gifts whose flow never
reaches ``ActionGuide`` (boss rewards, Saria, Darunia) call ``RandoProgressive`` right
after the gift. A token got another way is converted at the next item get.

Held levels are tested as the vanilla flows test them: ``EventQueryIsExistInPouch`` on
the pouch name (``ActorInfo.ActorName``: ``Weapon_Range_Bow`` for ``Item_Range_Bow``;
the actor name never matches), and the saved ``IsGet.<name>`` for the magic meter
(the great fairy flows test it so; it is never queried in the pouch).
"""
import io

from oot_rando.game.remake_world import PROGRESSIVE

from oot_rando.catalog.tokens import (  # noqa: F401  (moved to oot_rando.catalog.tokens, re-exported)
    TOKEN_PREFIX,
    APPLIED_PREFIX,
    FAMILIES,
    FAMILY_OF_CODE,
    token_actor,
    token_family,
    is_token,
    applied_flag,
    got_flag,
)
from oot_rando.formats.evfl_tools import case_target, params_by_event, parse_flow
from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import SAME_MODEL
from oot_rando.game.item_forms import copy_ref
from oot_rando.game.item_forms import pack_path
from oot_rando.game.item_forms import resolve_components
from oot_rando.game.tracking_metadata import add_saved_flags
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
ACTION_GUIDE = 'ActionGuide'
GUIDE_ENTRIES = ('ActionGuide', 'ActionGuideForShop')
CONVERTER_ENTRY = 'RandoProgressive'
GIVE_CALL = ('GetPouchContent', 'GetPouchContentByActorName')
AFTER_PREFIX = 'RandoProgAfter_'
# Pouch names (ActorInfo.ActorName) that differ from the level's actor; checked
# against the game by check_pouch_names.
POUCH_NAMES = {
    'Item_Range_Bow': 'Weapon_Range_Bow', 'Item_Range_SlingShot': 'Weapon_Range_SlingShot',
    'Item_Gauntlet_Goron': 'Armor_Child_Gauntlet_Goron', 'Item_Gauntlet_Silver': 'Armor_Adult_Gauntlet_Silver',
    'Item_Gauntlet_Gold': 'Armor_Adult_Gauntlet_Gold',
}
HELD_BY_FLAG = ('Item_FairyBless_MP', 'Item_FairyBless_MPDouble')


def assign_tokens(copies):
    """{key: token}: ``copies`` lists (key, family) in a stable order; tokens are numbered from 1 per family."""
    numbers, tokens = {}, {}
    for key, family in copies:
        if key in tokens:
            raise ValueError('Two progressive copies share a source: ' + str(key))
        numbers[family] = numbers.get(family, 0) + 1
        tokens[key] = token_actor(family, numbers[family])
    return tokens


def pouch_name(actor):
    return POUCH_NAMES.get(actor, actor)


def held_query(actor):
    """(system actor, query, parameters) true once Link holds the level ``actor``."""
    if actor in HELD_BY_FLAG:
        return 'GameDataActor', 'EventQueryIsGameDataBool', {'GameDataName': 'IsGet.' + pouch_name(actor), 'Index': -1}
    return 'PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': pouch_name(actor), 'Num': 1}


def check_pouch_names(actor_info_raw, gamedata_raw):
    """Every level's pouch name is the one the game uses (and its magic flag a saved Bool)."""
    from oot_rando.patching.soul_adapter import murmur3
    rows = {row['__RowId']: row for row in byml_codec.load(actor_info_raw)['root']}
    saved = {int(e['Hash']) for e in byml_codec.load(gamedata_raw)['root']['Data']['Bool']
             if e.get('SaveFileIndex') == 0}
    for tiers in PROGRESSIVE.values():
        for actor in tiers:
            if actor not in rows or rows[actor].get('ActorName', actor) != pouch_name(actor):
                raise ValueError('Pouch name differs from the game: ' + actor)
            if actor in HELD_BY_FLAG and murmur3('IsGet.' + pouch_name(actor)) not in saved:
                raise ValueError('Saved get flag missing: ' + actor)


# ---------------------------------------------------------------- flow editing
class FlowEditor:
    """New events in one flow, checked after writing: no existing parameter may change."""

    def __init__(self, raw, flow_name):
        self.flow = parse_flow(raw)
        self.chart = self.flow.flowchart
        self.name = flow_name
        self.expected = params_by_event(self.flow)

    def actor(self, identifier):
        """A system actor of the flow, added with its vanilla parameters when missing."""
        from evfl.actor import Actor
        from evfl.common import ActorIdentifier
        from evfl.container import Container
        from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, POUCH_ACTOR_PARAMS
        owner = next((a for a in self.chart.actors if str(a.identifier) == identifier), None)
        if owner is None:
            params = {'GameDataActor': GAMEDATA_ACTOR_PARAMS, 'PouchSystemActor': POUCH_ACTOR_PARAMS}.get(identifier)
            if params is None:
                raise ValueError(f'{self.name} has no {identifier}.')
            # A named actor without its parameter container crashes the game.
            owner = Actor()
            owner.identifier = ActorIdentifier(identifier)
            owner.concurrent_clips = 1
            owner.params = Container()
            owner.params.data = dict(params)
            self.chart.actors.append(owner)
        return owner

    @staticmethod
    def _holder(collection, name):
        from evfl.common import StringHolder
        found = next((h for h in collection if h.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found

    def _event(self, name, data, params):
        from evfl.container import Container
        from evfl.event import Event
        if params is not None:
            data.params = Container()
            data.params.data = dict(params)
        event = Event()
        event.name, event.data = name, data
        self.chart.events.append(event)
        self.expected[name] = None if params is None else dict(params)
        return event

    def action(self, name, identifier, action, params):
        from evfl.event import ActionEvent
        from evfl.util import make_rindex
        owner = self.actor(identifier)
        data = ActionEvent()
        data.actor, data.actor_action = make_rindex(owner), make_rindex(self._holder(owner.actions, action))
        return self._event(name, data, params)

    def switch(self, name, identifier, query, params, true, false):
        """Bool switch (case 0 = true, as the vanilla flows); a None branch ends the flow."""
        from evfl.event import SwitchEvent
        from evfl.util import make_index, make_rindex
        owner = self.actor(identifier)
        data = SwitchEvent()
        data.actor, data.actor_query = make_rindex(owner), make_rindex(self._holder(owner.queries, query))
        data.cases = {key: make_index(target) for key, target in ((0, true), (1, false)) if target is not None}
        return self._event(name, data, params)

    def subflow(self, name, flowchart, entry, params):
        """Call of ``flowchart``/``entry`` ('' = this flow); ``params`` None: no parameters."""
        from evfl.event import SubFlowEvent
        data = SubFlowEvent()
        data.res_flowchart_name, data.entry_point_name = flowchart, entry
        return self._event(name, data, params)

    def write(self, what):
        """(bytes, re-read flow) once no parameter but the new ones changed."""
        stream = io.BytesIO()
        self.flow.write(stream)
        result = stream.getvalue()
        checked = parse_flow(result)
        if params_by_event(checked) != self.expected:
            raise ValueError(what + ' changed other parameters.')
        return result, checked


def link(event, target):
    """``event`` goes on with ``target`` (None: the flow ends there)."""
    from evfl.util import make_index
    if target is not None:
        event.data.nxt = make_index(target)


def _named(event):
    return None if event is None else event.name


def tier_events(name, count):
    """(check event, held level, given level) of a tier chain, highest level first.

    Link holding level k gets level k + 1; holding the last one, the last one again
    (the pool has no copy beyond its levels: a harmless fallback, never an empty get).
    Holding none: the first level (event ``<name>_Give0``).
    """
    last = count - 1
    return [(name if k == last else f'{name}_Has{k}', k, min(k + 1, last)) for k in range(last, -1, -1)]


def add_tier_chain(editor, name, tiers, give, done):
    """Events giving the level above the highest of ``tiers`` Link holds, then ``done``.

    ``give(event name, actor)`` -> (first event, last event, its sub-flow events).
    Returns (first event, sub-flow events).
    """
    otherwise, last, subflows = give(name + '_Give0', tiers[0])
    link(last, done)
    # Built from the lowest level up: each check falls back to the one below it.
    for check_name, held, given in reversed(tier_events(name, len(tiers))):
        first, last, subs = give(f'{name}_Give{given}_From{held}', tiers[given])
        link(last, done)
        subflows.extend(subs)
        otherwise = editor.switch(check_name, *held_query(tiers[held]), first, otherwise)
    return otherwise, subflows


def _is_query(event, actor):
    identifier, query, params = held_query(actor)
    data = event.data
    return (type(data).__name__ == 'SwitchEvent' and str(data.actor.v.identifier) == identifier
            and data.actor_query.v.v == query and data.params is not None and dict(data.params.data) == params)


def check_tier_chain(start, name, tiers, given, done):
    """Raise unless the chain written by add_tier_chain starts at ``start``.

    ``given(event)`` -> (actor, event after the hand-over); ``done``: name of the event
    each hand-over goes on with (None: the flow ends).
    """
    event = start
    for check_name, held, give in tier_events(name, len(tiers)):
        if event is None or event.name != check_name or not _is_query(event, tiers[held]):
            raise ValueError('Progressive levels wrongly chained: ' + name)
        actor, after = given(case_target(event, 0))
        if actor != tiers[give] or _named(after) != done:
            raise ValueError('Progressive chain gives the wrong level: ' + name)
        event = case_target(event, 1)
    actor, after = given(event) if event is not None else (None, None)
    if _named(event) != name + '_Give0' or actor != tiers[0] or _named(after) != done:
        raise ValueError('Progressive chain without its first level: ' + name)


# ---------------------------------------------------------------- lift grade
# Link's strength is the saved ``PlayerStatus.LiftGrade`` (None/Low/Middle/High), not
# the pouch: the game sets it from the ExpansionAbilityActor of the actor Link picks
# up, and a token has none. A player's save held the three levels with the grade
# still None (golden rock of the Ganon's Castle fairy, user report, 0.8.3). The
# converter therefore ends by setting the grade of the highest level held; it runs on
# every item get, so a save already stuck is repaired at its next item.
STRENGTH = 'Progressive Strength Upgrade'
LIFT_GRADE = 'PlayerStatus.LiftGrade'
LIFT_GRADES = ('Low', 'Middle', 'High')
LIFT_PREFIX = 'RandoProgLift_'


def add_lift_grade(editor):
    """Events setting the lift grade of the highest strength level held. Returns the first."""
    tiers = PROGRESSIVE[STRENGTH]
    otherwise = None
    # Built from the lowest level up: each check falls back to the one below it.
    for level, actor in enumerate(tiers):
        grade = editor.action(f'{LIFT_PREFIX}Set{level}', 'GameDataActor', 'EventTriggerSetGameDataEnum',
                              {'GameDataName': LIFT_GRADE, 'Value': LIFT_GRADES[level], 'Index': -1})
        otherwise = editor.switch(f'{LIFT_PREFIX}Has{level}', *held_query(actor), grade, otherwise)
    return otherwise


def check_lift_grade(event):
    """Raise unless ``event`` starts the chain written by add_lift_grade."""
    tiers = PROGRESSIVE[STRENGTH]
    for level in reversed(range(len(tiers))):
        if event is None or event.name != f'{LIFT_PREFIX}Has{level}' or not _is_query(event, tiers[level]):
            raise ValueError('Lift grade wrongly checked.')
        grade = case_target(event, 0)
        if (_named(grade) != f'{LIFT_PREFIX}Set{level}' or getattr(grade.data.nxt, 'v', None) is not None
                or grade.data.actor_action.v.v != 'EventTriggerSetGameDataEnum'
                or dict(grade.data.params.data) != {'GameDataName': LIFT_GRADE, 'Value': LIFT_GRADES[level],
                                                    'Index': -1}):
            raise ValueError('Lift grade wrongly set.')
        event = case_target(event, 1)
    if event is not None:
        raise ValueError('Unexpected end of the lift grade.')


# ---------------------------------------------------------------- converter
def _stem(token):
    return token[len('Item_'):]


def _given_by_window(event):
    """(actor, next event) of a GetPouchContentByActorName call, else (None, None)."""
    data = event.data
    if (type(data).__name__ == 'SubFlowEvent' and (data.res_flowchart_name, data.entry_point_name) == GIVE_CALL
            and data.params is not None):
        return data.params.data.get('ActorName'), data.nxt.v if data.nxt is not None else None
    return None, None


def add_converter(raw, tokens):
    """ActionGuide whose item-get entries first convert the tokens. Returns (bytes, report)."""
    from evfl.entry_point import EntryPoint
    from evfl.util import make_index
    tokens = sorted(tokens)
    bad = [t for t in tokens if not is_token(t)]
    if bad or not tokens:
        raise ValueError('Not progressive tokens: ' + ', '.join(bad))
    editor = FlowEditor(raw, ACTION_GUIDE)
    chart = editor.chart
    entries = {e.name: e for e in chart.entry_points}
    if any(name not in entries or entries[name].main_event.v is None for name in GUIDE_ENTRIES):
        raise ValueError('Unexpected ActionGuide flow.')
    if CONVERTER_ENTRY in entries or any(e.name.startswith('RandoProg') for e in chart.events):
        raise ValueError('ActionGuide flow already converts the progressive tokens.')
    starts = {name: entries[name].main_event.v.name for name in GUIDE_ENTRIES}

    def give(name, actor):
        event = editor.subflow(name, GIVE_CALL[0], GIVE_CALL[1], {'ActorName': actor})
        return event, event, [event]

    # The lift grade last, once every token is converted (starting levels too: added
    # silently, they set no grade either).
    following, subflows = add_lift_grade(editor), []
    # Built from the last token backwards: each one goes on with the next.
    for token in reversed(tokens):
        stem = _stem(token)
        first, gives = add_tier_chain(editor, f'RandoProgTier_{stem}', PROGRESSIVE[token_family(token)], give,
                                      following)
        subflows += gives
        take = editor.action(f'RandoProgTake_{stem}', 'PouchSystemActor', 'EventTriggerAddOrRemovePouchContent',
                             {'Num': -1, 'IsEquipDIrect': False, 'IsSetMessageTargetActorName': True,
                              'Actor': token, 'IsGetEvent': False})
        link(take, first)
        mark = editor.action(f'RandoProgMark_{stem}', 'GameDataActor', 'EventTriggerSetGameDataBool',
                             {'GameDataName': applied_flag(token), 'Index': -1, 'Value': True})
        link(mark, take)
        done = editor.switch(f'RandoProgDone_{stem}', 'GameDataActor', 'EventQueryIsGameDataBool',
                             {'GameDataName': applied_flag(token), 'Index': -1}, following, mark)
        following = editor.switch(f'RandoProgHeld_{stem}', 'GameDataActor', 'EventQueryIsGameDataBool',
                                  {'GameDataName': got_flag(token), 'Index': -1}, done, following)
    converter = EntryPoint(CONVERTER_ENTRY)
    converter.main_event = make_index(following)
    converter._sub_flow_event_indices = [chart.events.index(e) for e in subflows]
    chart.entry_points.append(converter)
    for name in GUIDE_ENTRIES:
        entry = entries[name]
        run = editor.subflow(f'RandoProgRun_{name}', '', CONVERTER_ENTRY, None)
        run.data.nxt = entry.main_event
        entry.main_event = make_index(run)
        entry._sub_flow_event_indices = list(entry._sub_flow_event_indices) + [chart.events.index(run)]
    result, checked = editor.write('The progressive converter')
    written = {e.name: e for e in checked.flowchart.entry_points}
    for name in GUIDE_ENTRIES:
        run = written[name].main_event.v
        if (run.name != f'RandoProgRun_{name}' or run.data.entry_point_name != CONVERTER_ENTRY
                or run.data.res_flowchart_name or _named(run.data.nxt.v) != starts[name]):
            raise ValueError('ActionGuide entry wrongly attached to the converter: ' + name)
    check_converter(written[CONVERTER_ENTRY], tokens)
    return result, {'entry': CONVERTER_ENTRY, 'tokens': tokens, 'guides': list(GUIDE_ENTRIES)}


def check_converter(entry, tokens):
    """The converter entry checks each token, converts it once and gives the next level."""
    event = entry.main_event.v
    last = f'{LIFT_PREFIX}Has{len(PROGRESSIVE[STRENGTH]) - 1}'
    for index, token in enumerate(sorted(tokens)):
        stem = _stem(token)
        after = f'RandoProgHeld_{_stem(sorted(tokens)[index + 1])}' if index + 1 < len(tokens) else last
        held = event
        if (_named(held) != f'RandoProgHeld_{stem}'
                or held.data.params.data != {'GameDataName': got_flag(token), 'Index': -1}
                or _named(case_target(held, 1)) != after):
            raise ValueError('Progressive token wrongly checked: ' + token)
        done = case_target(held, 0)
        mark = case_target(done, 1) if _named(done) == f'RandoProgDone_{stem}' else None
        take = mark.data.nxt.v if mark is not None and mark.data.nxt is not None else None
        if (mark is None or _named(case_target(done, 0)) != after
                or done.data.params.data != {'GameDataName': applied_flag(token), 'Index': -1}
                or mark.data.params.data != {'GameDataName': applied_flag(token), 'Index': -1, 'Value': True}
                or _named(take) != f'RandoProgTake_{stem}'
                or (take.data.params.data.get('Actor'), take.data.params.data.get('Num')) != (token, -1)):
            raise ValueError('Progressive token converted more than once: ' + token)
        check_tier_chain(take.data.nxt.v, f'RandoProgTier_{stem}', PROGRESSIVE[token_family(token)],
                         _given_by_window, after)
        event = case_target(held, 1)
    check_lift_grade(event)


# ---------------------------------------------------------------- gifts outside item gets
def reaches_item_guide(current, flow, event):
    """Whether ActionGuide's item-get entries can run after ``event`` of ``flow``.

    ``current(name)``: raw of a flow (None if absent). Sub-flows are followed transitively.
    """
    from oot_rando.patching.event_info import SWITCH_CALL, entry_calls, event_calls
    stack, seen = list(event_calls(current(flow), event)), set()
    while stack:
        call = stack.pop()
        if call in seen or call == SWITCH_CALL:
            continue
        seen.add(call)
        if call[0] == ACTION_GUIDE and call[1] in GUIDE_ENTRIES:
            return True
        stack.extend(entry_calls(current(call[0]), call[1]) - seen)
    return False


def hook_sites(sources, current, covered=()):
    """{resource: [event]} of the token gifts that must call the converter themselves.

    ``sources``: for each source holding a token, its (resource, event) gift sites;
    ``current(name)``: raw of a flow; ``covered``: resources whose gift is moved to an
    item get (GIFT_AFTER_CUTSCENE). A site followed by another site of the same source
    (Saria: the add, then the display) leaves the call to the last one.
    """
    from oot_rando.patching.event_info import flow_name, reachable
    result = {}
    for sites in sources:
        by_resource = {}
        for resource, event in sites:
            if resource not in covered:
                by_resource.setdefault(resource, set()).add(event)
        for resource, events in sorted(by_resource.items()):
            name = flow_name(resource)
            named = {e.name: e for e in parse_flow(current(name)).flowchart.events}
            for event in sorted(events):
                if events & ({e.name for e in reachable(named[event])} - {event}):
                    continue
                if not reaches_item_guide(current, name, event):
                    result.setdefault(resource, []).append(event)
    return result


def add_converter_calls(raw, events, flow_name):
    """A call to ``ActionGuide/RandoProgressive`` right after each of ``events``."""
    from evfl.util import make_index
    from oot_rando.patching.event_info import reachable
    editor = FlowEditor(raw, flow_name)
    chart = editor.chart
    named = {e.name: e for e in chart.events}
    # An entry lists the sub-flow events it reaches without entering a sub-flow.
    reached = {entry.name: {e.name for e in reachable(entry.main_event.v)} for entry in chart.entry_points}
    for name in sorted(events):
        anchor = named.get(name)
        if anchor is None or getattr(anchor.data, 'nxt', None) is None or AFTER_PREFIX + name in named:
            raise ValueError(f'No gift to follow in {flow_name}: {name}')
        call = editor.subflow(AFTER_PREFIX + name, ACTION_GUIDE, CONVERTER_ENTRY, None)
        call.data.nxt = anchor.data.nxt
        anchor.data.nxt = make_index(call)
        for entry in chart.entry_points:
            if name in reached[entry.name]:
                entry._sub_flow_event_indices = list(entry._sub_flow_event_indices) + [chart.events.index(call)]
    result, checked = editor.write('The progressive converter calls')
    written = {e.name: e for e in checked.flowchart.events}
    for name in events:
        call = written[name].data.nxt.v
        if (_named(call) != AFTER_PREFIX + name
                or (call.data.res_flowchart_name, call.data.entry_point_name) != (ACTION_GUIDE, CONVERTER_ENTRY)):
            raise ValueError('Converter call wrongly chained: ' + name)
    return result


# ---------------------------------------------------------------- global watcher
# Safety net: a token got by a route that reaches neither ActionGuide nor a hook
# stays a dead key item (no bracelet, no gauntlets) until some later item get. The
# global sequence (``Sequence/MainUpdate``) therefore watches every token: while
# ``IsGet.<token>`` is true and ``RandoProg.<token>`` is not, it requests the
# converter entry itself as an event (EventSetting row = the entry's name). The
# converter is idempotent (each token is marked, then converted), so racing the
# ActionGuide call or running again after a load is harmless.
MAIN_UPDATE = 'Sequence/MainUpdate.module.ainb'
EVENT_SETTINGS = 'RSDB/EventSetting.Product.111.rstbl.byml.zs'
WATCH_EVENT = CONVERTER_ENTRY
WATCH_TEMPLATE_ROW = 'CrumblingGanonCastle_Arrive'   # as patching.ap_mailbox: started without an actor
WATCH_TEMPLATE_ANALYZED = 'NaviLockOnHint'
WATCH_NODES = ['SeqQueryGetNonStructGameDataBool', 'Element_BoolSelector', 'SeqQueryGetNonStructGameDataBool',
               'Element_BoolSelector', 'SeqOneShotRequestEvent', 'SeqExecuteGenericDummyAction',
               'SeqExecuteGenericDummyAction']


def watch_event_row(settings_raw):
    """EventSetting row requesting the converter entry of ActionGuide (no actor)."""
    import copy
    document = byml_codec.load(settings_raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    if WATCH_EVENT in by_id:
        raise ValueError('EventSetting row already present: ' + WATCH_EVENT)
    row = copy.deepcopy(by_id[WATCH_TEMPLATE_ROW])
    row.pop('EventEffectSetting', None)
    row['__RowId'] = WATCH_EVENT
    row['FlowchartFileName'] = f'Work/Event/EventFlow/{ACTION_GUIDE}.evfc'
    row['EntryPointName'] = CONVERTER_ENTRY
    rows.append(row)
    rows.sort(key=lambda r: r['__RowId'])
    return byml_codec.dump(document)


def watch_analyzed_row(info_raw, current):
    """GameAnalyzedEventInfo row listing everything the converter calls. ``current(name)``: raw of a flow."""
    import copy
    from oot_rando.patching.event_info import cached_charts, closure, reachable_transitions
    document = byml_codec.load(info_raw)
    rows = document['root']
    by_id = {row['__RowId']: row for row in rows}
    if WATCH_EVENT in by_id:
        raise ValueError('GameAnalyzedEventInfo row already present: ' + WATCH_EVENT)
    current = cached_charts(current)
    call = (ACTION_GUIDE, CONVERTER_ENTRY)
    row = copy.deepcopy(by_id[WATCH_TEMPLATE_ANALYZED])
    flows = closure({call}, current) - {ACTION_GUIDE}
    if flows:
        row['SubFlowList'] = sorted(flows, key=str.lower)
    children = set(reachable_transitions(call, current))
    for child in list(children):
        children.update((by_id.get(child) or {}).get('ChildEventList') or [])
    if children:
        row['ChildEventList'] = sorted(children, key=str.lower)
    row['__RowId'] = WATCH_EVENT
    rows.append(row)
    rows.sort(key=lambda r: r['__RowId'])
    return byml_codec.dump(document), {'subflows': row.get('SubFlowList', []), 'children': row.get('ChildEventList', [])}


def patch_main_update(raw, tokens):
    """The global sequence with one watcher per token (7 nodes each, in groups under the root)."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import WATCHER_GROUP, ainb_input, ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    root = nodes[0]
    if root['Node Type'] != 'Element_Simultaneous' or 'Is Root Node' not in root['Flags']:
        raise ValueError('Unexpected MainUpdate root.')
    dummy = next(n for n in nodes if n['Name'] == 'SeqExecuteGenericDummyAction')
    selector_model = next(n for n in nodes if n['Node Type'] == 'Element_BoolSelector')
    first = len(nodes)
    once = {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]}
    tokens = sorted(tokens)

    def guid(index):
        return f'0a9a9b00-0000-4000-8000-{index:012x}'

    def user(index, name, inputs, outputs=None, flags=(), properties=None):
        return {'Node Type': 'UserDefined', 'Node Index': index, 'Name': name, 'GUID': guid(index),
                'Flags': list(flags), 'Queries': [], 'Attachments': [], 'Properties': properties or {},
                'Parameters': {'Inputs': inputs, 'Outputs': outputs or {}}, 'XLink Actions': [], 'Plugs': {}}

    def query(index, flag):
        return user(index, 'SeqQueryGetNonStructGameDataBool', {
            'Int': [ainb_input('GameDataIndex', -1, True)], 'Bool': [ainb_input('IsDirect', True)],
            'String': [ainb_input('GameDataFullName', flag)]},
            {'Bool': [{'Name': 'Value', 'Is Output': True}]}, ['Is Query'],
            {'Bool': [{'Name': 'OutputOnlyOnEnter', 'Default Value': False, 'Flags': []}]})

    def selector(index, query_index, true_index, false_index):
        node = copy.deepcopy(selector_model)
        node.update({'Node Index': index, 'GUID': guid(index), 'Queries': [query_index],
                     'Flags': [f for f in node['Flags'] if f != 'Is Root Node']})
        node['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False, 'Node Index': query_index,
                                                    'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
        node['Plugs'] = {'Generic': [{'Node Index': query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                         'Child': [{'Node Index': true_index, 'Name': 'True'}, {'Node Index': false_index, 'Name': 'False'}]}
        return node

    groups = []
    for position, token in enumerate(tokens):
        if position % WATCHER_GROUP == 0:
            group = copy.deepcopy(root)
            group.update({'Node Index': len(nodes), 'GUID': guid(len(nodes)), 'Flags': [], 'Plugs': {'Child': []}})
            nodes.append(group)
            root['Plugs']['Child'].append({'Node Index': group['Node Index'], 'Name': ''})
            groups.append(group)
        got_q, got_s, applied_q, applied_s, request_i, idle_a, idle_b = range(len(nodes), len(nodes) + 7)
        request = user(request_i, 'SeqOneShotRequestEvent', {
            'Bool': [ainb_input('IsBancParamValue', False, True)], 'String': [ainb_input('EventName', WATCH_EVENT)]},
            properties=once)
        idle = []
        for index in (idle_a, idle_b):
            node = copy.deepcopy(dummy)
            node.update({'Node Index': index, 'GUID': guid(index)})
            idle.append(node)
        # Got and not yet converted: request; any other state does nothing.
        nodes.extend([query(got_q, got_flag(token)), selector(got_s, got_q, applied_s, idle_a),
                      query(applied_q, applied_flag(token)), selector(applied_s, applied_q, idle_b, request_i),
                      request, idle[0], idle[1]])
        groups[-1]['Plugs']['Child'].append({'Node Index': got_s, 'Name': ''})
    result = ainb_to_binary(document)
    check = ainb.AINB.from_binary(result).as_dict()['Nodes']
    for index, token in enumerate(tokens):
        group_index, slot = divmod(index, WATCHER_GROUP)
        group = first + group_index * (1 + WATCHER_GROUP * 7)
        base = group + 1 + slot * 7
        if check[group]['Node Type'] != 'Element_Simultaneous' or [
                n['Name'] or n['Node Type'] for n in check[base:base + 7]] != WATCH_NODES:
            raise ValueError('MainUpdate token watcher not written as expected: ' + token)
        names = [check[base + k]['Parameters']['Inputs']['String'][0]['Default Value'] for k in (0, 2, 4)]
        if names != [got_flag(token), applied_flag(token), WATCH_EVENT]:
            raise ValueError('MainUpdate token watcher misread: ' + token)
        if check[group]['Plugs']['Child'][slot]['Node Index'] != base + 1:
            raise ValueError('MainUpdate token watcher not attached: ' + token)
    return result


# ---------------------------------------------------------------- token actors
def token_texts(token, language):
    _, english, french, _ = FAMILIES[token_family(token)]
    if language.endswith('fr'):
        return {'Name': f'{french} (progressif)', 'Caption': f'Donne le niveau suivant : {french}.',
                'GetMessage': f'Vous avez obtenu un objet progressif : {french} !',
                'GetCaption': 'Il devient le niveau suivant de cet objet.'}
    return {'Name': f'Progressive {english}', 'Caption': f'Gives the next {english} level.',
            'GetMessage': f'You got a progressive item: {english}!',
            'GetCaption': 'It becomes the next level of this item.'}


# The token template (Forest Medallion) has no pose of its own (AS DemoDummy, no
# animation): the lent model was drawn in its raw axes, the Bow and the Longshot
# lying along their length, the Slingshot on its side (user report 18/11). A token
# takes the animation states of its first level's item actor (Item_Common and the
# item's Pose_Common, as in a vanilla chest), when that actor is made for the
# item-get display (ASInfo Item_GetDemo; not the ocarina, an accessory).
POSE_KEYS = ('ASRef', 'ASInfoRef', 'AnimationRef')
POSE_ASINFO = 'Item_GetDemo'


def pose_lender(family):
    """Item actor whose animation states pose the family's model (same mesh)."""
    model = FAMILIES[family][3]
    return SAME_MODEL.get(model, model)


def pose_parts(read_raw, family):
    """``(files, components, actor_info)`` posing a token like its first level, or None."""
    return actor_pose_parts(read_raw, pose_lender(family))


def actor_pose_parts(read_raw, lender):
    """``(files, components, actor_info)`` posing a generated item like ``lender``, or None
    when ``lender`` is not made for the item-get display."""
    pack = sarc(read_raw(f'Pack/Actor/{lender}.pack.zs'))
    components = resolve_components(pack, lender, byml_codec)
    refs = {key: components.get(key) for key in POSE_KEYS}
    if not all(isinstance(ref, str) and ref for ref in refs.values()) or POSE_ASINFO not in refs['ASInfoRef']:
        return None
    files = {}
    for ref in refs.values():
        copy_ref(pack, ref, files, byml_codec)
    animation = pack_path(refs['AnimationRef'])
    if animation not in files:
        raise ValueError('Item pose animation not found: ' + lender)
    resources = byml_codec.load(files[animation])['root'].get('AnimationResources')
    return files, refs, {'AnimationResources': resources}


def token_specs(tokens, read_raw=None):
    specs, poses = [], {}
    for token in sorted(tokens):
        family = token_family(token)
        name = 'RandoProg_' + _stem(token) + '.event.root'
        spec = {'actor': token, 'model': FAMILIES[family][3], 'event_name': name,
                'event_member': 'AI/' + name + '.ainb', 'event_ain': 'Work/AI/Root/Event/' + name + '.ain',
                'texts': (lambda language, token=token: token_texts(token, language))}
        if read_raw is not None:
            if family not in poses:
                poses[family] = pose_parts(read_raw, family)
            if poses[family] is not None:
                spec['files'], spec['components'], spec['actor_info'] = poses[family]
        specs.append(spec)
    return specs


def build_token_files(read_raw, tokens, message_archives=()):
    """``(modified, new)`` resources of the token actors, plus their saved conversion flags."""
    from oot_rando.patching.soul_adapter import GAMEDATA, RSDB_FILES, build_item_files
    if not tokens:
        return {}, {}
    check_pouch_names(read_raw(RSDB_FILES['ActorInfo']), read_raw(GAMEDATA))
    modified, new = build_item_files(read_raw, token_specs(tokens, read_raw), message_archives)
    raw = modified.get(GAMEDATA)
    modified[GAMEDATA] = add_saved_flags(raw if raw is not None else read_raw(GAMEDATA),
                                         {applied_flag(t): False for t in tokens})
    return modified, new
