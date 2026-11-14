"""Quality-of-life patches validated in game, plus their generalisation.

Validated by the user (9 November 2026): intro skip (``Dm_Kokiri_0000``), open
Kokiri exit towards Hyrule Field (guard, wall, logic and baked collision) and
the **+** skip of Saria's first dialogue.

``cutscene_files`` and ``patch_dialogues`` apply the same two skip mechanisms to
every cutscene and dialogue they apply to:

* every component list carrying ``SkipSetting = DisableSkip`` (only three exist:
  intro, title-screen demo chain, staff credits) loses that entry;
* every RSDB EventSetting row of an ``NPCTalk`` (or ``NPCStepStart``) category list
  is pointed to ``FlowchartEvent``, the validated target of Saria's first
  dialogue. The talk lists carrying dedicated actor exceptions (Zelda escape,
  Zora's Domain, digging tour, business scrubs) keep their rows and components
  but inherit from ``FlowchartEvent`` instead;
* the area presentation cutscenes (flow-driven, ``AREA_PRESENTATIONS``) receive
  the native ``EventTriggerSkipAcceptStart`` … ``EventTriggerSkipEnd`` window
  used by the great fairy fountains, and their non-pausing rows use ``FlowchartEvent``;
  their area name frame opens after the window, only when it was not skipped;
* no skip window covers a flow that talks (``DIALOGUE_ACTIONS``);
* optionally, chests skip their opening performance (``quick_chest`` for the big
  ones, ``quick_small_chest`` for the small ones) while Link still holds the item up.

Table patches keep resource sizes and offsets; every patch is re-read and
compared semantically. Only static checks are performed; gameplay is user-tested.
"""
import copy
import hashlib
import io
import struct

from oot_rando.formats.inspect_resources import Byml
from oot_rando.patching.randomize_kokiri import slot

INTRO = 'Event/EventSetting/EventSettingComponentList/Dm_Kokiri_0000.engine__event__EventSettingComponentList.bgyml'
INTRO_PARENT = 'Event/EventSetting/EventSettingComponentList/RecordMovieTimelineEvent.engine__event__EventSettingComponentList.bgyml'
INTRO_SOURCE_SHA256 = '258d6aae2c51c533978cf8f4e0805096e808eb5346ce8d109ab15c97a2ba8c39'
STATIC = 'Banc/KokiriForest/KokiriForest_Child_Static.bcett.byml.zs'
STATIC_SOURCE_SHA256 = '008869c0349bce0ac82378391e8bd79b5e9862c481bf4fe2816d9212ff9d291b'
DYNAMIC_SOURCE_SHA256 = 'd5e4c39658ae2a6fdc722ea0531d52e5022bf7505a22dfcef351293d8443662a'
GUARD = 6882168009719929077
WALL = 3896376838177072891
REACTION = 13203537043835508815
AREAS = {16871625560285997972, 17791632522232516211}
LOGIC_GROUP = 1787311525728660119
EXIT = 6926381327103603486
PHYSICS = 'Phive/StaticCompoundBody/KokiriForest/KokiriForest_Child_X1_Z1.Nin_Ounce_NVN2.bphsc.zs'
PHYSICS_SOURCE_SHA = '971718f09b592c6ce37809d94bdc3fba807f3d1c6b864687f62bcdd3cfb8ba41'
INSTANCE_OFFSET = 0x2e200
INSTANCE_SOURCE = bytes.fromhex(
    '00000000f55008be00000000b7b87d3f6ef3a3c24528e642d2f017c26e730100'
    '0000003f6666e63f3333b33f2d00ffffc0300200000000000000000000000000')
EVENT_SETTINGS = 'RSDB/EventSetting.Product.111.rstbl.byml.zs'
EVENT_SETTINGS_SOURCE_SHA = '278a5a533991884058b102334f351184c92f523dbd4b8e5dcf29c2e008c16f73'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patch_intro(raw, parent):
    if sha256(raw) != INTRO_SOURCE_SHA256:
        raise ValueError('Unexpected introduction settings resource')
    source = Byml(raw).root
    if '$parent' in Byml(parent).root or 'SkipSetting' in Byml(parent).root['Components']:
        raise ValueError('Unexpected inherited skip settings')
    expected = copy.deepcopy(source)
    skip = expected['Components'].pop('SkipSetting')
    if skip != '?Event/EventSetting/EventSettingComponent/SkipSetting/DisableSkip.engine__event__SkipSetting.bgyml':
        raise ValueError('Unexpected skip prohibition')
    result = bytearray(raw)
    if len(raw) != 512 or raw[0x1ec:0x1f0] != b'\xc1\x02\0\0':
        raise ValueError('Unexpected component dictionary')
    # SkipSetting is the final entry in this exact supported dictionary.
    # Keep the resource size and all pointers unchanged; reduce its entry count.
    result[0x1ed] = 1
    result = bytes(result)
    if Byml(result).root != expected:
        raise ValueError('Introduction semantic verification failed')
    if [i for i,(a,b) in enumerate(zip(raw,result)) if a != b] != [0x1ed]:
        raise ValueError('Unexpected introduction byte changes')
    return result


def remove_array_elements(raw, path, indices, aliases=()):
    """Compact a little-endian BYML array without growing or relocating it."""
    b = Byml(raw)
    if b.endian != '<':
        raise ValueError('Array patch supports little endian map resources only')
    off = b.u32(slot(b, path, 0xc0))
    count = b.u24(off+1)
    indices = set(indices)
    if not indices or not indices <= set(range(count)):
        raise ValueError('Invalid array removal indices')
    values = (off+4+count+3)&~3
    keep = [i for i in range(count) if i not in indices]
    node = bytearray(b'\xc0'+len(keep).to_bytes(3,'little'))
    node.extend(bytes(b.data[off+4+i] for i in keep))
    node.extend(b'\0'*(-len(node)%4))
    for i in keep:
        node.extend(raw[values+i*4:values+i*4+4])
    capacity = values+count*4-off
    if len(node) > capacity:
        raise ValueError('Array patch would grow resource')
    result = bytearray(raw)
    result[off:off+len(node)] = node
    # Unreachable bytes are retained; no other offsets or resource sizes change.
    expected = copy.deepcopy(b.root)
    array = expected
    for key in path[:-1]:
        array = array[key]
    array[path[-1]] = [v for i,v in enumerate(array[path[-1]]) if i not in indices]
    for alias in aliases:
        if b.u32(slot(b,alias,0xc0)) != off:
            raise ValueError('Declared array alias is not shared')
        parent = expected
        for key in alias[:-1]:
            parent = parent[key]
        parent[alias[-1]] = list(array[path[-1]])
    if len(result) != len(raw) or Byml(bytes(result)).root != expected:
        raise ValueError('Array compaction affected unexpected data')
    return bytes(result)


def patch_forest(static_raw, dynamic_raw):
    static = Byml(static_raw).root
    dynamic = Byml(dynamic_raw).root
    expected_static = copy.deepcopy(static)
    expected_dynamic = copy.deepcopy(dynamic)
    static_targets = {GUARD, REACTION} | AREAS
    expected_actor_types = {GUARD:'Npc_Kokiri_007_Child',REACTION:'EventRequestActor',
                            **{a:'Area' for a in AREAS}}
    for ident,typ in expected_actor_types.items():
        matched = [a for a in static['Actors'] if a.get('Hash') == ident]
        if len(matched) != 1 or matched[0].get('Gyaml') != typ:
            raise ValueError(f'Unexpected forest actor {ident}')
    walls = [a for a in dynamic['Actors'] if a.get('Hash') == WALL]
    if len(walls) != 1 or walls[0].get('Presence',{}).get('FlagName') != 'KokiriForest_Npc_Kokiri_007_Child_Blocker_00':
        raise ValueError('Unexpected exit wall')
    matched_logic = [a for a in static['AiGroups'] if a.get('Hash') == LOGIC_GROUP]
    if len(matched_logic) != 1 or not matched_logic[0]['Logic'].endswith('_d26e.logic.module.ain'):
        raise ValueError('Unexpected blocking logic')
    if {a['Reference'] for a in matched_logic[0]['References']} != {REACTION} | AREAS:
        raise ValueError('Unexpected blocking logic references')
    expected_static['Actors'] = [a for a in static['Actors'] if a.get('Hash') not in static_targets]
    expected_static['AiGroups'] = [a for a in static['AiGroups'] if a.get('Hash') != LOGIC_GROUP]
    static_raw = remove_array_elements(static_raw,['Actors'],[i for i,a in enumerate(static['Actors']) if a.get('Hash') in static_targets])
    static_raw = remove_array_elements(static_raw,['AiGroups'],[i for i,a in enumerate(static['AiGroups']) if a.get('Hash') == LOGIC_GROUP])
    related = {REACTION} | AREAS
    for group_name in ['FarDeleteGroups','SimultaneousGroups']:
        expected_static[group_name] = [g for g in static[group_name] if set(g) != related]
    for group_name in ['FarDeleteGroups','SimultaneousGroups']:
        current = Byml(static_raw)
        if current.root[group_name] == expected_static[group_name]:
            continue
        remove = [i for i,g in enumerate(current.root[group_name]) if set(g) == related]
        if len(remove) != 1:
            raise ValueError(f'Unexpected {group_name} dependencies')
        off = current.u32(slot(current,[group_name],0xc0))
        aliases = [[key] for key in ['FarDeleteGroups','SimultaneousGroups'] if key != group_name
                   and current.u32(slot(current,[key],0xc0)) == off]
        static_raw = remove_array_elements(static_raw,[group_name],remove,aliases)
    expected_dynamic['Actors'] = [a for a in dynamic['Actors'] if a.get('Hash') != WALL]
    dynamic_raw = remove_array_elements(dynamic_raw,['Actors'],[i for i,a in enumerate(dynamic['Actors']) if a.get('Hash') == WALL])
    actual_static, actual_dynamic = Byml(static_raw).root, Byml(dynamic_raw).root
    if actual_static != expected_static or actual_dynamic != expected_dynamic:
        raise ValueError('Unexpected forest changes')
    # The Hyrule transfer and Saria bridge sequence are intentionally preserved.
    entrance = next(a for a in actual_static['Actors'] if a.get('Hash') == EXIT)
    if entrance['Dynamic']['NextBancParamNameChild'] != 'HyruleField_Child':
        raise ValueError('Exit destination changed')
    removed = static_targets | {WALL,LOGIC_GROUP}
    def references_removed(value):
        if isinstance(value,dict):
            return any(references_removed(v) for v in value.values())
        if isinstance(value,list):
            return any(references_removed(v) for v in value)
        return isinstance(value,int) and not isinstance(value,bool) and value in removed
    if references_removed(actual_static) or references_removed(actual_dynamic):
        raise ValueError('Dangling map reference to removed blockers')
    return static_raw,dynamic_raw


def patch_baked_wall(raw):
    """Neutralize exactly one supported hknpShapeInstance, keeping all indices.

    Format reference: Starlight's PhiveStaticCompoundFile / HavokClasses and
    OnBancEntityDelete (zero-scale instance with HAS_SCALE). No mesh is removed.
    """
    if sha256(raw) != PHYSICS_SOURCE_SHA or raw[:8] != b'Phive\0\x02\x02':
        raise ValueError('Unsupported static compound resource')
    links, hashes, _, fixed = struct.unpack_from('<4I',raw,0x10)
    if not 0 <= links < hashes <= len(raw) or (hashes-links)%32:
        raise ValueError('Unexpected Phive actor link table')
    linked = [off for off in range(links,hashes,32) if struct.unpack_from('<Q',raw,off+8)[0] == WALL]
    if len(linked) != 1:
        raise ValueError('Missing or ambiguous baked wall identity')
    base,end,ident,srt,_,body,_,_,_ = struct.unpack_from('<IIQIIHBBI',raw,linked[0])
    if (base,end,ident,srt,body) != (45,45,WALL,2766964426,0):
        raise ValueError('Unexpected wall shape linkage')
    instance_index = struct.unpack_from('<H',raw,fixed+base*20+10)[0]
    if instance_index != 31 or raw[INSTANCE_OFFSET:INSTANCE_OFFSET+64] != INSTANCE_SOURCE:
        raise ValueError('Unexpected baked wall transform')
    if struct.unpack_from('<H',raw,INSTANCE_OFFSET+44)[0] != base:
        raise ValueError('Baked wall shape tag mismatch')
    # Keep quaternion, shape reference, tags, leaf index, user data and padding.
    # HAS_SCALE only: rotation/translation flags are off, geometry collapses
    # at the origin rather than leaving even a degenerate point in the passage.
    patched = bytearray(raw)
    patched[INSTANCE_OFFSET+16:INSTANCE_OFFSET+28] = bytes(12)
    patched[INSTANCE_OFFSET+28] = 8
    patched[INSTANCE_OFFSET+32:INSTANCE_OFFSET+44] = bytes(12)
    patched = bytes(patched)
    allowed = set(range(INSTANCE_OFFSET+16,INSTANCE_OFFSET+29)) | set(range(INSTANCE_OFFSET+32,INSTANCE_OFFSET+44))
    actual = {i for i,(a,b) in enumerate(zip(raw,patched)) if a != b}
    if not actual or not actual <= allowed or len(patched) != len(raw):
        raise ValueError('Unexpected static compound changes')
    return patched, {'operation':'Neutralize only the baked wall instance: zero scale/translation and HAS_SCALE flag',
                     'actor_hash':str(WALL),'srt_hash':'2766964426','actor_link_offset':hex(linked[0]),
                     'fixed_index':base,'instance_index':instance_index,'instance_offset':hex(INSTANCE_OFFSET),
                     'changed_byte_offsets':[hex(i) for i in sorted(actual)],'source_sha256':sha256(raw),
                     'decompressed_size_changed':False}


# ---------------------------------------------------------------- skips
LISTS = 'Event/EventSetting/EventSettingComponentList/'
SUFFIX = '.engine__event__EventSettingComponentList'
DISABLE_SKIP = '?Event/EventSetting/EventSettingComponent/SkipSetting/DisableSkip.engine__event__SkipSetting.bgyml'

# The intro uses the original byte-checked pilot; the two others follow the same rule.
LOCKED_CUTSCENES = {
    'Dm_StaffCredit_0005': 'End credits',
    'Dm_Title_0005': 'Title screen demo (and its six follow-ups Dm_Title_0045 to 0095)',
}


def list_path(name):
    return LISTS + name + SUFFIX + '.bgyml'


def _work(name):
    return 'Work/' + LISTS + name + SUFFIX + '.gyml'


# Rows started by a step trigger: the world pauses (FlowchartEvent), so + skips them.
NPC_STEP_START = {
    'NPCStepStart': 'FlowchartEvent',
    'NPCStepStartNoPause': 'FlowchartEvent',
}
# Area presentations: first visit of a zone or dungeon (camera tour + area name,
# ``UISystemActor.EventTriggerOpenLocationUI``). Flow-driven cutscenes are only
# skippable inside an ``EventTriggerSkipAcceptStart`` … ``EventTriggerSkipEnd``
# window (as the great fairy fountains do); these flows have none. Flows that
# write saved data or change map (Dm_Kokiri_0045, Dm_LakeHrl_0003/0005,
# Dm_LonLon_0010) and NPC flows are left alone.
AREA_PRESENTATIONS = (
    'Dm_DeathMtCrater_0000', 'Dm_DeathMtTrail_0000', 'Dm_Deku_0000', 'Dm_DesertColossus_0000',
    'Dm_DodongoCave_0000', 'Dm_ForestTemple_0000', 'Dm_GanonCastle_0000', 'Dm_GerudoValley_0000',
    'Dm_Gerudo_0000', 'Dm_Goron_0000', 'Dm_Graveyard_0000', 'Dm_HrlCastle_0005',
    'Dm_HrlField_0000', 'Dm_InsideGanonCastle_0003', 'Dm_InsideJabu_Jabu_0000', 'Dm_Kakariko_0000',
    'Dm_LakeHrl_0000', 'Dm_TimeTemple_0000', 'Dm_TimeTemple_0065', 'Dm_ZoraFountain_0000', 'Dm_Zora_0000',
    'Goto_FireTemple', 'Goto_GerudoTrainingGround', 'Goto_IceCave', 'Goto_KakarikoWells',
    'Goto_SacredForest', 'Goto_ShadowTemple', 'Goto_SpiritTemple', 'Goto_WaterTemple', 'Goto_ZoraRiver',
)
# Their rows that never pause the world use the paused list, like the fountains.
AREA_PRESENTATION_LISTS = {'NoPauseEvent': 'FlowchartEvent'}
FLOWS = 'Event/EventFlow/'
SKIP_UNSAFE_ACTIONS = ('EventTriggerSetGameData', 'EventTransition', 'AddOrRemovePouchContent',
                       'EventTriggerSkip', 'EventRequestQuit')
# Dialogue: no skip window may cover a flow that talks. Skipping Saria at the ladder
# (Dm_Kokiri_0060) crashed the game twice (11/11: MessageDialogStyle 'NoActor', key
# '%s:%s' not found), and the Deku Tree's talk before entering it (Dm_Kokiri_0075) is
# the same kind of flow. Their text goes faster with the turbo A instead.
# (Dm_HrlCastle_0000, a presentation that talks, left AREA_PRESENTATIONS for that reason.)
DIALOGUE_ACTIONS = ('EventTalk', 'EventTalkWithInstanceNameLabel', 'EventPoeSpiritTalk', 'EventPlayerTalk',
                    'EventPlayerConversate', 'EventCloseMessageDialog', 'EventTriggerBecomeSpeaker')
# The area name frame of a presentation. Nothing closes it: when the presentation is
# skipped it stayed on screen (11/11). It now opens once the presentation is over,
# only when it was watched to the end.
LOCATION_UI_ACTION = 'EventTriggerOpenLocationUI'


def dialogue_actions(chart):
    """Names of the dialogue actions a flowchart runs (empty: no dialogue)."""
    found = set()
    for event in chart.events:
        holder = getattr(event.data, 'actor_action', None)
        if holder is not None and holder.v is not None and holder.v.v in DIALOGUE_ACTIONS:
            found.add(holder.v.v)
    return sorted(found)


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def add_skip_window(raw):
    """Wrap every root entry of a cutscene flow in a native skip window.

    ``EventSystemActor.EventTriggerSkipAcceptStart`` becomes the entry's first
    event; ``EventTriggerSkipEnd`` follows the last join of the entry's top-level
    chain (the cleanup after it — camera reset, ducking release — still runs),
    or ends the chain when it has no join. Returns (bytes, report).
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent, ForkEvent, JoinEvent, SwitchEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot, GAMEDATA_ACTOR_PARAMS
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    for event in chart.events:
        holder = getattr(event.data, 'actor_action', None)
        action = holder.v.v if holder is not None and holder.v is not None else ''
        if any(word in action for word in SKIP_UNSAFE_ACTIONS):
            raise ValueError('Cutscene with an unskippable action: ' + action)
    if dialogue_actions(chart):
        raise ValueError('Cutscene with dialogue: not skippable.')
    actor = next((a for a in chart.actors if a.identifier.name == 'EventSystemActor'
                  and a.identifier.sub_name == ''), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier('EventSystemActor')
        actor.concurrent_clips = 1
        actor.params = Container()
        actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        chart.actors.append(actor)
    def holder(collection, name):
        found = next((a for a in collection if a.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found
    actions = {name: holder(actor.actions, name)
               for name in ('EventTriggerSkipAcceptStart', 'EventTriggerSkipEnd', 'EventWait')}
    location_uis = [e for e in chart.events if isinstance(e.data, ActionEvent)
                    and e.data.actor_action.v.v == LOCATION_UI_ACTION]
    skipped_query = holder(actor.queries, 'EventQueryIsEventSkipedMostRecent') if location_uis else None
    location_names = {}   # deferred frame event -> (LocationName, (actor, action))

    def new_event(name, action, params, owner=None):
        event = Event()
        event.name, event.data = name, ActionEvent()
        event.data.actor = make_rindex(owner[0] if owner else actor)
        event.data.actor_action = make_rindex(owner[1] if owner else actions[action])
        event.data.params = Container()
        event.data.params.data = params
        chart.events.append(event)
        expected[name] = dict(params)
        return event

    called = {e.data.entry_point_name for e in chart.events
              if isinstance(e.data, SubFlowEvent) and not e.data.res_flowchart_name}
    entries_by_name = {e.name: e for e in chart.entry_points}

    def window_region(start, stops):
        """Events run between a window's start and its ends (local sub-flows included)."""
        seen, stack, found = set(), [start], []
        while stack:
            event = stack.pop()
            if event is None or event.name in seen or event.name in stops:
                continue
            seen.add(event.name)
            found.append(event)
            data = event.data
            if isinstance(data, SubFlowEvent) and not data.res_flowchart_name:
                sub = entries_by_name.get(data.entry_point_name)
                stack.append(sub.main_event.v if sub is not None else None)
            stack.extend(_successors(event))
        return found

    def defer_location_ui(entry_name, start, ends):
        """The name frame opens after SkipEnd, only when the window was not skipped."""
        stops = {e.name for e in ends}
        uis = [e for e in window_region(start, stops) if e in location_uis]
        if not uis:
            return None
        for ui in uis:
            if ui.name not in location_names:
                location_names[ui.name] = (ui.data.params.data.get('LocationName'),
                                           (ui.data.actor.v, ui.data.actor_action.v))
        names = {location_names[e.name][0] for e in uis}
        if len(names) != 1 or not all(isinstance(n, str) and n for n in names):
            raise ValueError('Ambiguous area name in the presentation: ' + entry_name)
        name = names.pop()
        owner = location_names[uis[0].name][1]
        for ui in uis:   # in place: the flow's edges stay as they are
            ui.data.actor, ui.data.actor_action = make_rindex(actor), make_rindex(actions['EventWait'])
            ui.data.params.data = {'IsWaitEnd': True, 'Frames': 1}
            expected[ui.name] = dict(ui.data.params.data)
        for index, end in enumerate(ends):
            after = end.data.nxt.v if end.data.nxt is not None else None
            shown = new_event(f'RandoLocationUI_{entry_name}_{index}', None, {'LocationName': name}, owner)
            shown.data.nxt = make_index(after)
            check = Event()
            check.name, check.data = f'RandoLocationCheck_{entry_name}_{index}', SwitchEvent()
            check.data.actor, check.data.actor_query = make_rindex(actor), make_rindex(skipped_query)
            check.data.params = None
            check.data.cases = {1: make_index(shown)}   # case 0 = skipped: no frame
            if after is not None:
                check.data.cases[0] = make_index(after)
            chart.events.append(check)
            expected[check.name] = None
            end.data.nxt = make_index(check)
        return {'location': name, 'deferred': sorted(e.name for e in uis)}
    def anchors(first, seen):
        """Where the window closes: after the last top-level join of the chain; a
        branch closes it in each of its cases. (Until 11/11 a branch after a join
        closed it at that join: Dm_GerudoValley_0000 then only covered the opening
        participation fork, the whole tour came after SkipEnd.)"""
        last, current, tail = None, first, first
        while current is not None and current.name not in seen:
            seen.add(current.name)
            tail = current
            data = current.data
            if isinstance(data, ForkEvent):
                current = data.join.v
                continue
            if isinstance(data, JoinEvent):
                last = current
            if isinstance(data, SwitchEvent):
                found = []
                for case in data.cases.values():
                    if case.v is None or case.v.name in seen:
                        continue   # (merges into a case already followed)
                    for anchor in anchors(case.v, seen):
                        if anchor not in found:
                            found.append(anchor)
                return found or [last if last is not None else current]
            if not hasattr(data, 'nxt'):
                break
            current = data.nxt.v
        return [last if last is not None else tail]

    report = []
    for entry in list(chart.entry_points):
        if entry.name in called or entry.main_event.v is None:
            continue
        first = entry.main_event.v
        ends = anchors(first, set())
        if not ends or any(not hasattr(a.data, 'nxt') or isinstance(a.data, SwitchEvent) for a in ends):
            raise ValueError('Ambiguous cutscene end: ' + entry.name)
        start = new_event('RandoSkipStart_' + entry.name, 'EventTriggerSkipAcceptStart',
                          {'SpecialEventActionType': 3})
        start.data.nxt = make_index(first)
        entry.main_event = make_index(start)
        entry_ends, records = [], []
        for index, anchor in enumerate(ends):
            end = new_event(f'RandoSkipEnd_{entry.name}_{index}', 'EventTriggerSkipEnd',
                            {'SpecialEventActionType': 4, 'FadeInType': 0})
            end.data.nxt = anchor.data.nxt
            anchor.data.nxt = make_index(end)
            entry_ends.append(end)
            records.append({'entry': entry.name, 'after': anchor.name, 'end': end.name})
        deferred = defer_location_ui(entry.name, first, entry_ends)
        if deferred:
            for record in records:
                record['location_ui'] = deferred
        report += records
    if not report:
        raise ValueError('No cutscene entry to make skippable.')
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The skip window changed other parameters.')
    entries = {e.name: e for e in checked.flowchart.entry_points}
    events = {e.name: e for e in checked.flowchart.events}
    for record in report:
        if entries[record['entry']].main_event.v.name != 'RandoSkipStart_' + record['entry']:
            raise ValueError('Cutscene entry not attached to the skip window.')
        if events[record['after']].data.nxt.v.name != record['end']:
            raise ValueError('Misplaced skip window end.')
    return result, report


# ---------------------------------------------------------------- skip windows with replay
# Generalisation of the native windows to flow-driven cutscenes that change state
# (user test 11/11: Kokiri Forest presentation Dm_Kokiri_0045 and Saria's ladder
# dialogue Dm_Kokiri_0060 were not skippable; Dm_Kokiri_0050, a timeline, was).
# Flows that talk (DIALOGUE_ACTIONS) are excluded since skipping Dm_Kokiri_0060 crashed.
# The native skip *jumps* to EventTriggerSkipEnd (the fountains and the Water Temple
# fix what was missed with EventQueryIsEventSkipedMostRecent). Here every entry's
# top-level chain is cut into units (action, local sub-flow, fork…join, switch…merge)
# and each unit is classified from the actions it can run:
# * cosmetic actions (animation, camera, wait, talk without choice, sound, effects,
#   non-player warps…) may be skipped;
# * idempotent writes (constant GameData bool/int, "have talked", event bool, absolute
#   warps of the player) may be skipped when they run on every path of the unit: they
#   are replayed right after SkipEnd when the skip was used;
# * anything else (transition, pouch, quest step, choice, input, pause pairs, unknown
#   action, writes only on some paths, foreign sub-flow that writes) is a barrier.
# Each maximal run of skippable units that actually takes time gets its own window,
# so a cutscene with an event in the middle is skippable up to it, then after it.
#
# World changes (user test 11/11, Deku Tree water: the switch's cutscene skipped ->
# water never lowered, run blocked): ``EventRequestActor`` actions signal the actor
# that started the event (switch, water gate, shutter, chest appearing…), which then
# plays its change while the camera shows it. Skipping cuts that change and replaying
# the signal after SkipEnd does not restart it. An entry that sends such a signal
# (itself or through a sub-flow) gets no window at all: whether a signal sent right
# after a skip works is not proven.
SKIP_REPLAY_ACTIONS = ('EventTriggerSetGameDataBool', 'EventTriggerSetGameDataInt',
                       'EventTriggerSetHaveTalked',
                       'EventTriggerSoundEnableSpMode', 'EventTriggerSoundDisableSpMode')
SKIP_WORLD_CHANGE_ACTORS = ('EventRequestActor',)
SKIP_WORLD_CHANGE_ACTIONS = ('EventTriggerSetEventBool',)
# Fade-outs: no vanilla skip window holds a fade-out, so a fade-out ends a window
# (barrier): the fade and what follows (scene change, transition) always play. They
# once made the whole entry unskippable (white screen after Gohma's blue warp, 11/11),
# but that white screen came from RSDB SubFlowList (event_info), and the rule took the
# skip away from cutscenes ending in a fade, such as the Kokiri Forest presentation
# Dm_Kokiri_0045 (user test 12/11).
SKIP_FADE_OUT_ACTIONS = ('EventEventFadeOut',)


def is_world_change(actor, action):
    """An action never skipped (see above): a world actor changes on screen."""
    return actor in SKIP_WORLD_CHANGE_ACTORS or action in SKIP_WORLD_CHANGE_ACTIONS
SKIP_BARRIER_ACTIONS = ('EventTransition', 'EventTriggerRequestAutoSave')
SKIP_REPLAY_PLAYER_WARPS = ('EventPlayerWarpToTargetPosAndRot', 'EventPlayerWarpToStarterLinkAnchor')
SKIP_BARRIER_WORDS = ('Pouch', 'Challenge', 'AddOrSub', 'Death', 'Equip', 'Create',
                      'DoCommand', 'KeyInput', 'Ocarina', 'Instrument', 'Pause', 'Boots', 'ForbidScreenDucking',
                      'Skip', 'Quit', 'Banc', 'SaveData', 'ShowItem', 'RupeeDisplay', 'Error', 'Dungeon',
                      'Replace', 'Thunder', 'MotionType', 'Schedule', 'Enemy', 'GameData', 'Choice', 'Input',
                      'Appear', 'Damage', 'Kill', 'Delete', 'Spawn', 'Get', 'Melody', 'Learn', 'Ride', 'Horse')
SKIP_COSMETIC_WORDS = ('PlayAS', 'EventWait', 'XLink', 'Comment', 'Camera', 'Offstage', 'Participate', 'DoF',
                       'CutChange', 'Norify', 'Navi', 'Fade', 'Palette', 'Sound', 'Bgm', 'BGM', 'Ducking', 'Look',
                       'ModelBind', 'ModelUnbind', 'Emotion', 'Rumble', 'Voice', 'Lod', 'Effect', 'Light', 'Wind',
                       'Shading', 'Terrain', 'Culling', 'Turn', 'Move', 'EventTalk', 'MessageDialog', 'DoNothing',
                       'ScreenShot', 'Warp', 'Unequip', 'PutAway', 'Drawn', 'EventStartWith', 'CloseDemoScreen',
                       'DynamicResolution', 'Listener', 'RoomSend', 'ReadRiddle', 'Shake', 'Cloth', 'EnvPalette',
                       'AmbientSound', 'LocationUI', 'Color', 'Walk', 'Speaker', 'Conversate', 'Wait')
# Random choices are not input: writes under them are uncertain, hence barriers anyway.
SKIP_INPUT_QUERIES = ('TalkChoice', 'Input', 'Skiped', 'Ocarina', 'Melody')


def skip_action_class(actor, action, params):
    """'replay', 'cosmetic' or 'barrier' for one action event."""
    if is_world_change(actor, action) or action in SKIP_FADE_OUT_ACTIONS:
        return 'barrier'
    if actor == 'Player_Event' and action in SKIP_REPLAY_PLAYER_WARPS:
        return 'replay'
    if action in SKIP_REPLAY_ACTIONS:
        values = list((params or {}).values())
        return 'replay' if all(isinstance(v, (bool, int, float, str)) for v in values) else 'barrier'
    if action in SKIP_BARRIER_ACTIONS:
        return 'barrier'
    if action == 'EventTalk' and (params or {}).get('ChoiceNumber', 0):
        return 'barrier'
    if any(word in action for word in SKIP_BARRIER_WORDS) and 'EventWaitForActorPresence' != action:
        return 'barrier'
    if any(word in action for word in SKIP_COSMETIC_WORDS):
        return 'cosmetic'
    return 'barrier'


def _successors(event):
    from evfl.event import ForkEvent, SwitchEvent
    data = event.data
    if isinstance(data, SwitchEvent):
        return [c.v for c in data.cases.values() if c.v is not None]
    if isinstance(data, ForkEvent):
        return [f.v for f in data.forks] + [data.join.v]
    nxt = getattr(data, 'nxt', None)
    return [nxt.v] if nxt is not None and nxt.v is not None else []


class _SkipAnalysis:
    """Classifies regions of one flow; ``load_flow(name)`` gives other flows (or None)."""

    def __init__(self, chart, load_flow=None):
        self.memo = {}
        self.chart = chart
        self.entries = {e.name: e for e in chart.entry_points}
        self.load_flow = load_flow
        self.foreign = {}
        self.foreign_world = {}  # (flow, entry) -> may change the world (unknown: True)

    def _foreign_ok(self, flow_name, entry_name, depth):
        key = (flow_name, entry_name)
        if key in self.foreign:
            return self.foreign[key]
        self.foreign[key] = False  # recursion guard
        chart = self.load_flow(flow_name) if self.load_flow else None
        entry = next((e for e in chart.entry_points if e.name == entry_name), None) if chart else None
        ok = False
        if entry is not None and depth < 4 and not dialogue_actions(chart):
            sub = _SkipAnalysis(chart, self.load_flow)
            sub.foreign = self.foreign
            sub.foreign_world = self.foreign_world
            info = sub.region(entry.main_event.v, None, depth + 1)
            ok = not info['barrier'] and not info['writes']
            self.foreign_world[key] = info['world']
        self.foreign[key] = ok
        return ok

    def region(self, start, stop, depth=0, active=frozenset()):
        """Every event reachable from ``start`` before ``stop`` (local sub-flows expanded)."""
        from evfl.event import ActionEvent, SwitchEvent, SubFlowEvent
        info = {'barrier': [], 'writes': [], 'content': False, 'world': False}
        seen, stack = set(), [start]
        while stack:
            event = stack.pop()
            if event is None or event is stop or event.name in seen:
                continue
            seen.add(event.name)
            data = event.data
            if isinstance(data, ActionEvent):
                actor = data.actor.v.identifier.name
                action = data.actor_action.v.v
                params = data.params.data if data.params is not None else {}
                kind = skip_action_class(actor, action, params)
                if is_world_change(actor, action):
                    info['world'] = True
                if kind == 'barrier':
                    info['barrier'].append(f'{actor}.{action}')
                elif kind == 'replay':
                    info['writes'].append(event)
                elif params.get('IsWaitEnd') or action == 'EventTalk':
                    info['content'] = True
            elif isinstance(data, SwitchEvent):
                query = data.actor_query.v.v
                if any(word in query for word in SKIP_INPUT_QUERIES):
                    info['barrier'].append(query)
            elif isinstance(data, SubFlowEvent):
                if data.res_flowchart_name:
                    if not self._foreign_ok(data.res_flowchart_name, data.entry_point_name, depth):
                        info['barrier'].append('sous-flow ' + data.res_flowchart_name)
                        if self.foreign_world.get((data.res_flowchart_name, data.entry_point_name), True):
                            info['world'] = True
                else:
                    entry = self.entries.get(data.entry_point_name)
                    if entry is None or entry.main_event.v is None:
                        info['barrier'].append('sous-flow absent')
                    elif entry.name in active or depth > 12:
                        info['barrier'].append('recursive sub-flow')
                    else:
                        sub = self.region(entry.main_event.v, None, depth + 1, active | {entry.name})
                        if sub['writes'] and data.params is not None and data.params.data:
                            sub['barrier'].append('parameterised write')
                        info['barrier'] += sub['barrier']
                        info['writes'] += sub['writes']
                        info['content'] = info['content'] or sub['content']
                        info['world'] = info['world'] or sub['world']
            # depth first along the chain: writes are listed in execution order
            stack.extend(reversed(_successors(event)))
        return info

    def certain(self, event, stop, path=frozenset()):
        """Replayable writes run on every path from ``event`` to ``stop``.

        A loop back into the current path contributes nothing (conservative);
        results are memoised per (event, stop)."""
        key = (event.name if event is not None else None, stop.name if stop is not None else None)
        if key in self.memo:
            return self.memo[key]
        if len(path) > 400:
            return set()
        result = self._certain(event, stop, path)
        self.memo[key] = result
        return result

    def _certain(self, event, stop, path):
        from evfl.event import ActionEvent, ForkEvent, JoinEvent, SwitchEvent, SubFlowEvent
        result = set()
        while event is not None and event is not stop and event.name not in path:
            path = path | {event.name}
            data = event.data
            if isinstance(data, ActionEvent):
                params = data.params.data if data.params is not None else {}
                if skip_action_class(data.actor.v.identifier.name, data.actor_action.v.v, params) == 'replay':
                    result.add(event.name)
            elif isinstance(data, SubFlowEvent) and not data.res_flowchart_name:
                entry = self.entries.get(data.entry_point_name)
                if entry is not None:
                    result |= self.certain(entry.main_event.v, None, path)
            elif isinstance(data, ForkEvent):
                for branch in data.forks:
                    result |= self.certain(branch.v, data.join.v, path)
                event = data.join.v.data.nxt.v if data.join.v.data.nxt is not None else None
                continue
            elif isinstance(data, JoinEvent):
                return result
            elif isinstance(data, SwitchEvent):
                cases = [c.v for c in data.cases.values() if c.v is not None]
                if len(cases) < 2:
                    return result
                common = None
                for case in cases:
                    found = self.certain(case, stop, path)
                    common = found if common is None else common & found
                return result | common
            nxt = getattr(data, 'nxt', None)
            event = nxt.v if nxt is not None else None
        return result

    def merge(self, switch):
        """First event reached by every case of a switch, or None."""
        cases = [c.v for c in switch.data.cases.values() if c.v is not None]
        orders = []
        for case in cases:
            order, seen, queue = [], set(), [case]
            while queue:
                event = queue.pop(0)
                if event is None or event.name in seen:
                    continue
                seen.add(event.name)
                order.append(event)
                queue.extend(_successors(event))
            orders.append(order)
        if len(orders) < 2:
            return None
        names = [{e.name for e in order} for order in orders]
        for event in orders[0]:
            if all(event.name in other for other in names[1:]):
                return event
        return None

    def units(self, first):
        """Top-level units: (start event, exit event or None, kind)."""
        from evfl.event import ForkEvent, JoinEvent, SwitchEvent
        units, event, seen = [], first, set()
        while event is not None and event.name not in seen:
            seen.add(event.name)
            data = event.data
            if isinstance(data, ForkEvent):
                join = data.join.v
                exit_ = join.data.nxt.v if join.data.nxt is not None else None
                units.append((event, exit_, 'fork'))
            elif isinstance(data, SwitchEvent):
                exit_ = self.merge(event)
                units.append((event, exit_, 'switch'))
                if exit_ is None:
                    break
            elif isinstance(data, JoinEvent):
                break
            elif not hasattr(data, 'nxt'):
                break
            else:
                nxt = data.nxt
                exit_ = nxt.v if nxt is not None else None
                units.append((event, exit_, 'single'))
            event = exit_
        return units


def _redirect(unit, target, chart):
    """Point every edge leaving ``unit`` (towards its exit) at ``target``."""
    from evfl.event import ForkEvent
    from evfl.util import make_index
    start, exit_, kind = unit
    if kind == 'single':
        start.data.nxt = make_index(target)
        return
    if kind == 'fork':
        start.data.join.v.data.nxt = make_index(target)
        return
    # switch region: every event of the region whose edge reaches the merge point
    seen, stack = set(), [start]
    while stack:
        event = stack.pop()
        if event is None or event is exit_ or event.name in seen:
            continue
        seen.add(event.name)
        data = event.data
        if hasattr(data, 'cases'):
            for key, case in list(data.cases.items()):
                if case.v is exit_:
                    data.cases[key] = make_index(target)
        elif isinstance(data, ForkEvent):
            pass
        elif getattr(data, 'nxt', None) is not None and data.nxt.v is exit_:
            data.nxt = make_index(target)
        stack.extend(_successors(event))


def add_skip_windows_with_replay(raw, load_flow=None, external_entries=()):
    """Returns (bytes, report). ``external_entries``: entries other flows call as sub-flows."""
    import sys
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent, SwitchEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot, GAMEDATA_ACTOR_PARAMS
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    for event in chart.events:
        holder = getattr(event.data, 'actor_action', None) or getattr(event.data, 'actor_query', None)
        if holder is not None and 'Skip' in holder.v.v:
            raise ValueError('Flow already handles skipping.')
    if dialogue_actions(chart):
        raise ValueError('Flow with dialogue: no skip window.')
    called = {e.data.entry_point_name for e in chart.events
              if isinstance(e.data, SubFlowEvent) and not e.data.res_flowchart_name}
    analysis = _SkipAnalysis(chart, load_flow)
    plans = []
    for entry in chart.entry_points:
        if entry.name in called or entry.name in external_entries or entry.main_event.v is None:
            continue
        units = analysis.units(entry.main_event.v)
        run, run_prev, prev = [], None, None
        def close(run, run_prev):
            if not run:
                return
            infos = [u[3] for u in run]
            if any(i['content'] for i in infos):
                plans.append((entry, run_prev, [u[:3] for u in run], [w for i in infos for w in i['writes_ok']]))
        infos = [analysis.region(unit[0], unit[1]) for unit in units]
        if any(info['world'] for info in infos):
            continue  # whole cutscene unskippable (a skip before the change is not proven safe)
        for unit, info in zip(units, infos):
            ok = False
            if not info['barrier']:
                certain = analysis.certain(unit[0], unit[1])
                if {w.name for w in info['writes']} <= certain:
                    ordered, seen = [], set()
                    for w in info['writes']:
                        if w.name not in seen:
                            seen.add(w.name)
                            ordered.append(w)
                    info['writes_ok'] = ordered
                    ok = True
            if ok:
                if not run:
                    run_prev = prev
                run.append(unit + (info,))
            else:
                close(run, run_prev)
                run = []
            prev = unit
        close(run, run_prev)
    if not plans:
        raise ValueError('No sequence safely skippable.')
    system = next((a for a in chart.actors if a.identifier.name == 'EventSystemActor'
                   and a.identifier.sub_name == ''), None)
    if system is None:
        system = Actor()
        system.identifier = ActorIdentifier('EventSystemActor')
        system.concurrent_clips = 1
        system.params = Container()
        system.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        chart.actors.append(system)
    def holder(collection, name):
        found = next((a for a in collection if a.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found
    start_action = holder(system.actions, 'EventTriggerSkipAcceptStart')
    end_action = holder(system.actions, 'EventTriggerSkipEnd')
    skipped_query = holder(system.queries, 'EventQueryIsEventSkipedMostRecent')
    counter = [0]
    def new_action(prefix, actor, action, params):
        counter[0] += 1
        event = Event()
        event.name, event.data = f'{prefix}_{counter[0]}', ActionEvent()
        event.data.actor, event.data.actor_action = make_rindex(actor), make_rindex(action)
        event.data.params = Container()
        event.data.params.data = dict(params)
        chart.events.append(event)
        expected[event.name] = dict(params)
        return event
    report = []
    for entry, previous, run, writes in plans:
        first, last = run[0], run[-1]
        exit_ = last[1]
        start = new_action('RandoSkipStart', system, start_action, {'SpecialEventActionType': 3})
        end = new_action('RandoSkipEnd', system, end_action, {'SpecialEventActionType': 4, 'FadeInType': 0})
        # predecessor of the run -> start
        if previous is None:
            entry.main_event = make_index(start)
        else:
            _redirect(previous, start, chart)
        start.data.nxt = make_index(first[0])
        _redirect(last, end, chart)
        after = exit_
        if writes:
            clones = [new_action('RandoSkipReplay', w.data.actor.v, w.data.actor_action.v,
                                 w.data.params.data if w.data.params is not None else {}) for w in writes]
            for a, b in zip(clones, clones[1:]):
                a.data.nxt = make_index(b)
            clones[-1].data.nxt = make_index(exit_)
            counter[0] += 1
            check = Event()
            check.name, check.data = f'RandoSkipCheck_{counter[0]}', SwitchEvent()
            check.data.actor, check.data.actor_query = make_rindex(system), make_rindex(skipped_query)
            check.data.params = None
            check.data.cases = {0: make_index(clones[0])}
            if exit_ is not None:
                check.data.cases[1] = make_index(exit_)
            chart.events.append(check)
            expected[check.name] = None
            after = check
        end.data.nxt = make_index(after)
        report.append({'entry': entry.name, 'from': first[0].name, 'to': last[0].name,
                       'replayed': [w.name for w in writes]})
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    if _snapshot(_flow(result)) != expected:
        raise ValueError('The skip windows changed other parameters.')
    return result, report


# System flows (item get, chests, guides, boot/title, mini-games) keep their timing.
SKIP_WINDOW_EXCLUDED_PREFIXES = ('Dm_SY_', 'DmF_', 'ActionGuide', 'GetPouchContent', 'Default', 'OpeningEvent',
                                 'TitleEvent', 'ShieldHylianNaviHintBootEvent', 'MiniGame', 'Minigame')


def skip_window_candidates(event_settings_raw):
    """Cutscene flows started by an EventSetting row (NPC flows are never skipped)."""
    names = set()
    for row in Byml(event_settings_raw).root:
        flow = row.get('FlowchartFileName', '')
        if not flow.startswith('Work/' + FLOWS) or not flow.endswith('.evfc'):
            continue
        name = flow[len('Work/' + FLOWS):-len('.evfc')]
        if name in AREA_PRESENTATIONS or name.startswith(SKIP_WINDOW_EXCLUDED_PREFIXES):
            continue
        if not name.startswith('Npc_'):
            names.add(name)
    return sorted(names)


def skip_window_context(read_flow, flow_names):
    """(load_flow, external entries per flow) from the original flows."""
    from oot_rando.patching.event_patch import _flow
    from evfl.event import SubFlowEvent
    charts = {}
    def load_flow(name):
        if name not in charts:
            charts[name] = None
            if name in flow_names:
                try:
                    charts[name] = _flow(read_flow(flow_path(name))).flowchart
                except ValueError:
                    charts[name] = None
        return charts[name]
    external = {}
    for name in sorted(flow_names):
        chart = load_flow(name)
        for event in chart.events if chart is not None else ():
            data = event.data
            if isinstance(data, SubFlowEvent) and data.res_flowchart_name:
                external.setdefault(data.res_flowchart_name, set()).add(data.entry_point_name)
    return load_flow, external


def cutscene_window_files(read_flow, flow_names, candidates):
    """``read_flow(path)`` gives original decompressed flows. Returns ({path: bytes}, report)."""
    load_flow, external = skip_window_context(read_flow, set(flow_names))
    files, report = {}, {}
    for name in candidates:
        if load_flow(name) is None:
            continue
        try:
            raw, windows = add_skip_windows_with_replay(read_flow(flow_path(name)), load_flow,
                                                        external.get(name, ()))
        except ValueError:
            continue  # nothing safely skippable, or the flow already handles skips
        files[flow_path(name)], report[name] = raw, windows
    return files, report


def area_presentation_files(read_flow):
    """``read_flow(path)`` returns a decompressed flow. Returns ({path: bytes}, report)."""
    files, report = {}, {}
    for name in AREA_PRESENTATIONS:
        files[flow_path(name)], report[name] = add_skip_window(read_flow(flow_path(name)))
    return files, report


# Big chests (Dm_SY_Treasurebox, also used by the scripted chests): ``Success_``
# plays fanfare -> /Success_PlayerPerform (camera, Link's kick, item shown
# rotating, 473-frame wait) -> 90-frame wait -> /Success_AddContent (item added,
# get window) -> /Success_Leave (opened flag, auto-save). The quick version
# replaces the performance by the chest's own /Open (lid animation only) and
# goes straight to the item.
CHEST_FLOW = 'Event/EventFlow/Dm_SY_Treasurebox.bfevfl.zs'
CHEST_LID_ANIMATIONS = ('FrontOpen', 'FrontOpen_Adult')
# Link holds the item up while its get window is open (user request 11/11: the item
# appearing without Link's pose looked odd). Actions and parameters of the vanilla
# item-get pose, Dm_SY_GetInEvent/GetInEvent_NotTurn_NotNpc (Event280, Event264,
# Event51, Event41, Event337); the item is the chest's own ``ContentName`` argument.
CHEST_SHOW_ITEM = (
    ('Player_Event', 'EventCreateShowItemFromActorFileName', {'IsWaitEnd': True, 'Actor': 'ContentName'}),
    ('Player_Event', 'EventPlayerPlayASForFlowchart', {
        'UseAnmDriven': False, 'KeepOneTimeAnm': False, 'IsWaitEnd': False, 'ASCommand': 'DemoGet',
        'IsAllSlot': True, 'ForceFadeFrame': 0.0, 'ClothWarpMode': -1}),
    ('Player_Event', 'EventIgnitionShowItem', {
        'IsWaitEnd': True, 'ItemPos': [0.0, 0.0, 0.0], 'IsScale': False, 'CreateTime': 0.0,
        'IsInvalidateShadow': True, 'IsAsPlay': True, 'ASCommand': 'Rotate_GetDemo'}),
    ('EventSystemActor', 'EventWait', {'IsWaitEnd': True, 'Frames': 40}),
)
CHEST_HIDE_ITEM = ('Player_Event', 'EventDeleteShowItem', {
    'IsWaitEnd': True, 'IsFadeOut': False, 'IsScaleOut': False, 'ChangeVisibleOffWithRequestDelete': False})


def quick_chest(raw):
    from evfl.common import Argument, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    entry = next(e for e in chart.entry_points if e.name == 'Success_')
    switch = entry.main_event.v
    fanfare = switch.data.cases[0].v
    perform = fanfare.data.nxt.v
    wait = perform.data.nxt.v
    add = wait.data.nxt.v
    if (not isinstance(perform.data, SubFlowEvent) or perform.data.entry_point_name != 'Success_PlayerPerform'
            or perform.data.res_flowchart_name or wait.data.actor_action.v.v != 'EventWait'
            or not isinstance(add.data, SubFlowEvent) or add.data.entry_point_name != 'Success_AddContent'):
        raise ValueError('Unexpected big chest flow.')
    if not any(e.name == 'Open' for e in chart.entry_points):
        raise ValueError('Open entry missing from the chest flow.')
    content = perform.data.params.data.get('ContentName') if perform.data.params is not None else None
    if not isinstance(content, Argument) or content != 'ContentName':
        raise ValueError('Big chest content not passed as expected.')
    leave = add.data.nxt.v if add.data.nxt is not None else None
    if not isinstance(getattr(leave, 'data', None), SubFlowEvent) or leave.data.entry_point_name != 'Success_Leave':
        raise ValueError('Unexpected big chest end.')
    # The chest-opening music (the fanfare's intro, timed on the cutscene) is cut
    # (user request 12/11): the item fanfare starts at once, as for small chests
    # (Dm_SY_TreasureboxSmall/ItemDisplay: IsEnableIntro False).
    if (fanfare.data.actor_action.v.v != 'EventTriggerSoundStartFanfare' or fanfare.data.params is None
            or fanfare.data.params.data.get('IsEnableIntro') is not True):
        raise ValueError('Unexpected big chest fanfare.')
    fanfare.data.params.data['IsEnableIntro'] = False
    expected[fanfare.name]['IsEnableIntro'] = False
    actors = {a.identifier.name: a for a in chart.actors if a.identifier.sub_name == ''}

    def new_action(name, actor_name, action, params):
        actor = actors[actor_name]
        holder = next((a for a in actor.actions if a.v == action), None)
        if holder is None:
            holder = StringHolder(action)
            actor.actions.append(holder)
        event = Event()
        event.name, event.data = name, ActionEvent()
        event.data.actor, event.data.actor_action = make_rindex(actor), make_rindex(holder)
        event.data.params = Container()
        event.data.params.data = {k: Argument(v) if k == 'Actor' else v for k, v in params.items()}
        chart.events.append(event)
        expected[name] = dict(event.data.params.data)
        return event
    pose = [new_action(f'RandoQuickChestShow_{i}', *step) for i, step in enumerate(CHEST_SHOW_ITEM)]
    hide = new_action('RandoQuickChestHide', *CHEST_HIDE_ITEM)
    for a, b in zip(pose, pose[1:]):
        a.data.nxt = make_index(b)
    pose[-1].data.nxt = make_index(add)
    add.data.nxt = make_index(hide)
    hide.data.nxt = make_index(leave)
    perform.data.entry_point_name = 'Open'
    perform.data.params = None
    perform.data.nxt = make_index(pose[0])
    expected[perform.name] = None
    # The lid animation is timed on the whole performance (≈ 8 s) and /Open waits
    # for it: the player stayed frozen that long without any cutscene (11/11). Only
    # /Success_PlayerPerform's fork (itself held by a 473-frame wait) and this quick
    # path call /Open, so the lid keeps animating while the item is given.
    lids = [e for e in chart.events if getattr(e.data, 'actor_action', None) is not None
            and e.data.actor_action.v.v == 'EventPlayAS' and e.data.params is not None
            and e.data.params.data.get('ASName') in CHEST_LID_ANIMATIONS]
    if sorted(e.data.params.data['ASName'] for e in lids) != sorted(CHEST_LID_ANIMATIONS):
        raise ValueError('Unexpected chest lid animations.')
    for lid in lids:
        if lid.data.params.data.get('IsWaitEnd') is not True:
            raise ValueError('Unexpected chest lid animation.')
        lid.data.params.data['IsWaitEnd'] = False
        expected[lid.name]['IsWaitEnd'] = False
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The quick chest changed other parameters.')
    events = {e.name: e for e in checked.flowchart.events}
    chain, event = [], events[perform.name]
    while event is not None and len(chain) < 12:
        chain.append(event.name)
        event = event.data.nxt.v if getattr(event.data, 'nxt', None) is not None else None
    if (events[perform.name].data.entry_point_name != 'Open'
            or chain != [perform.name] + [e.name for e in pose] + [add.name, hide.name, leave.name]
            or not isinstance(events[pose[0].name].data.params.data['Actor'], Argument)):
        raise ValueError('Quick chest wrongly chained.')
    return result, {'entry': 'Success_', 'replaced': 'Success_PlayerPerform', 'skipped_wait': wait.name,
                    'fanfare_without_intro': fanfare.name,
                    'lid_not_awaited': sorted(e.name for e in lids),
                    'show_item': [e.name for e in pose], 'hide_item': hide.name}


# Small chests (Dm_SY_TreasureboxSmall): ``Success_`` calls /Open (space and camera
# checks, Link's opening or kicking animation awaited, event cameras, Navi, the lid
# in /TresureboxSmall_Animation, then /Pack_ItemDisplay: item shown, added, get
# window) and goes on with the opened flag and the auto-save. The quick version
# (user request 12/11: every chest opens fast, like the big ones) replaces /Open by
# the lid's own actions (not awaited), Link's get pose (/GetAnimationAction, as in
# vanilla next to the item display) and /Pack_ItemDisplay: no Link animation, no
# event camera.
SMALL_CHEST_FLOW = 'Event/EventFlow/Dm_SY_TreasureboxSmall.bfevfl.zs'
SMALL_CHEST_LID = 'FrontOpenSmall'
SMALL_CHEST_STEPS = ('EventTriggerTBoxPushPoseMask', 'EventPlayAS', 'EventTreasureBoxSetRigLightIntensityScale')


def quick_small_chest(raw):
    from evfl.event import Event, ActionEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    names = {e.name for e in chart.events}
    if any(n.startswith('RandoQuickChest') for n in names):
        raise ValueError('Small chest flow already modified.')
    entry = next(e for e in chart.entry_points if e.name == 'Success_')
    opened = entry.main_event.v
    if (not isinstance(opened.data, SubFlowEvent) or opened.data.entry_point_name != 'Open'
            or opened.data.res_flowchart_name or opened.data.params is None
            or opened.data.params.data.get('ContentName') != 'ContentName'
            or 'IsMiniGame' not in opened.data.params.data):
        raise ValueError('Unexpected small chest flow.')
    entries = {e.name for e in chart.entry_points}
    if not {'Pack_ItemDisplay', 'GetAnimationAction', 'TresureboxSmall_Animation'} <= entries:
        raise ValueError('Small chest entries missing.')

    def actions(action):
        return [e for e in chart.events if isinstance(e.data, ActionEvent) and e.data.actor_action.v.v == action]
    push = actions('EventTriggerTBoxPushPoseMask')
    lids = [e for e in actions('EventPlayAS') if e.data.params is not None
            and e.data.params.data.get('ASName') == SMALL_CHEST_LID]
    lights = actions('EventTreasureBoxSetRigLightIntensityScale')
    poses = [e for e in chart.events if isinstance(e.data, SubFlowEvent)
             and e.data.entry_point_name == 'GetAnimationAction' and not e.data.res_flowchart_name]
    if len(push) != 1 or len(lids) != 1 or len(lights) != 1 or not poses:
        raise ValueError('Unexpected small chest lid.')

    def clone(name, source, **changes):
        event = Event()
        event.name = name
        if isinstance(source.data, ActionEvent):
            event.data = ActionEvent()
            event.data.actor = make_rindex(source.data.actor.v)
            event.data.actor_action = make_rindex(source.data.actor_action.v)
        else:
            event.data = SubFlowEvent()
            event.data.res_flowchart_name = source.data.res_flowchart_name
            event.data.entry_point_name = source.data.entry_point_name
        event.data.params = copy.deepcopy(source.data.params)
        if event.data.params is not None:
            event.data.params.data.update(changes)
        chart.events.append(event)
        expected[name] = dict(event.data.params.data) if event.data.params is not None else None
        return event
    steps = [clone('RandoQuickChestPose', push[0]),
             clone('RandoQuickChestLid', lids[0], IsWaitEnd=False),
             clone('RandoQuickChestLight', lights[0], IsWaitEnd=False),
             clone('RandoQuickChestGetPose', poses[0])]
    for a, b in zip(steps, steps[1:]):
        a.data.nxt = make_index(b)
    # /Open becomes /Pack_ItemDisplay (same arguments, same next event).
    opened.data.entry_point_name = 'Pack_ItemDisplay'
    steps[-1].data.nxt = make_index(opened)
    entry.main_event = make_index(steps[0])
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The quick small chest changed other parameters.')
    events = {e.name: e for e in checked.flowchart.events}
    chain, event = [], next(e for e in checked.flowchart.entry_points if e.name == 'Success_').main_event.v
    while event is not None and len(chain) < 8:
        chain.append(event.name)
        event = event.data.nxt.v if getattr(event.data, 'nxt', None) is not None else None
    if (chain[:5] != [s.name for s in steps] + [opened.name]
            or events[opened.name].data.entry_point_name != 'Pack_ItemDisplay'
            or events['RandoQuickChestLid'].data.params.data.get('IsWaitEnd') is not False):
        raise ValueError('Quick small chest wrongly chained.')
    return result, {'entry': 'Success_', 'replaced': 'Open', 'by': 'Pack_ItemDisplay',
                    'added': [s.name for s in steps]}


# Fairy Ocarina before the Deku Tree. In vanilla the ocarina is handed over on the
# bridge, then the first arrival in Hyrule Field (Dm_SY_BancChangeArrive,
# EntryPoint ``Dm_SY_BancChangeArrive_HyruleField``) runs
# ``ActionGuide/OpenActionGuideSceenForOcarina``: ocarina action guide (type 8,
# ``Ocarina`` in the guide enum) and, when the guide requests it, the
# ``Dm_SY_Ocarina`` play event. An ocarina found earlier never gets that guide and
# could not be played (user test, 11/11). Every item-get flow (Dm_SY_Get,
# Dm_SY_GetInEvent, Dm_SY_Get_WithoutPlayer, both chest flows) ends in
# ``ActionGuide/ActionGuide``: it now first runs the vanilla ocarina sequence while
# the Fairy Ocarina is in the pouch. ``OpenActionGuideSceen`` shows a guide once only
# (``EventQueryHaveOpenedActionGuide``), so this happens on the get of the ocarina
# itself — or, for a save that already holds it, on the next item get.
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
OCARINA_GUIDE_ENTRY = 'OpenActionGuideSceenForOcarina'
OCARINA_ACTOR = 'Item_Ocarina_Fairy'


def ocarina_guide_on_get(raw):
    """Returns (bytes, report). Bool switches: case 0 = true (as the vanilla flows)."""
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, SwitchEvent, SubFlowEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    entries = {e.name: e for e in chart.entry_points}
    if 'ActionGuide' not in entries or OCARINA_GUIDE_ENTRY not in entries:
        raise ValueError('Unexpected ActionGuide flow.')
    entry = entries['ActionGuide']
    first = entry.main_event.v
    if first is None or first.data.actor_query.v.v != 'EventQueryCheckPouchContentCategory':
        raise ValueError('Unexpected ActionGuide entry.')
    actor = next((a for a in chart.actors if a.identifier.name == 'PouchSystemActor'
                  and a.identifier.sub_name == ''), None)
    if actor is None:
        actor = Actor()
        actor.identifier = ActorIdentifier('PouchSystemActor')
        actor.concurrent_clips = 1
        actor.params = Container()
        actor.params.data = {}
        chart.actors.append(actor)
    query = next((q for q in actor.queries if q.v == 'EventQueryIsExistInPouch'), None)
    if query is None:
        query = StringHolder('EventQueryIsExistInPouch')
        actor.queries.append(query)
    names = {e.name for e in chart.events}
    if {'RandoOcarinaHeld', 'RandoOcarinaGuide'} & names:
        raise ValueError('ActionGuide flow already modified.')
    guide = Event()
    guide.name, guide.data = 'RandoOcarinaGuide', SubFlowEvent()
    guide.data.res_flowchart_name = ''
    guide.data.entry_point_name = OCARINA_GUIDE_ENTRY
    guide.data.params = None
    guide.data.nxt = make_index(first)
    held = Event()
    held.name, held.data = 'RandoOcarinaHeld', SwitchEvent()
    held.data.actor, held.data.actor_query = make_rindex(actor), make_rindex(query)
    held.data.params = Container()
    held.data.params.data = {'Actor': OCARINA_ACTOR, 'Num': 1}
    held.data.cases = {0: make_index(guide), 1: make_index(first)}
    chart.events.extend([held, guide])
    entry.main_event = make_index(held)
    expected[held.name] = dict(held.data.params.data)
    expected[guide.name] = None
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The ocarina guide changed other parameters.')
    events = {e.name: e for e in checked.flowchart.events}
    start = {e.name: e for e in checked.flowchart.entry_points}['ActionGuide'].main_event.v
    switch = events['RandoOcarinaHeld'].data
    if (start.name != 'RandoOcarinaHeld' or switch.cases[0].v.name != 'RandoOcarinaGuide'
            or switch.cases[1].v.name != first.name
            or events['RandoOcarinaGuide'].data.nxt.v.name != first.name
            or events['RandoOcarinaGuide'].data.entry_point_name != OCARINA_GUIDE_ENTRY):
        raise ValueError('Ocarina guide wrongly chained.')
    return result, {'entry': 'ActionGuide', 'guide': OCARINA_GUIDE_ENTRY, 'actor': OCARINA_ACTOR}


# Gifts handed over in a cutscene. Some cutscenes add their item with
# ``GetPouchContent/GetPouchContentByActorName`` (get window, no pose) while the scene
# shows its own model of the vanilla item: with a shuffled item, the player never saw
# what was obtained. Calling the vanilla item get there instead does not work (user
# test, 11/11): in the cutscene, Link (Player_Event) plays the scene's own animation set
# (``UseEventAS`` = Dm_Kokiri_0130_Player_Child: its cuts only, no ``DemoGet``), and the
# camera is the scene's. Every vanilla caller of Dm_SY_GetInEvent uses Link's normal
# animation set (``UseEventAS`` 使用しない).
# So the cutscene's add (and its collection marker) is bypassed, and the item is given
# once back in game, by the flow that chains the cutscenes, with the vanilla item get
# used by gifts without a giver (Skull Kid's heart piece): Link holds the item up, get
# window, ActionGuide, camera restored. The collection flag is set after it.
# Pilot: the Deku Tree (Kokiri Emerald) only. The calling event must list
# Dm_SY_GetInEvent (and its own sub-flows) in RSDB GameAnalyzedEventInfo, or it never
# starts (user test 11/11: white screen on arriving in Kokiri Forest after Gohma):
# event_info.add_subflow_dependencies, applied to every changed flow.
GIFT_AFTER_CUTSCENE = {
    'Event/EventFlow/Dm_Kokiri_0130.bfevfl.zs': {
        'event': 'Event22',
        # Warp_Kokiri: ... Dm_Kokiri_0130 -> Dm_Kokiri_0140 -> back in the forest, faded in,
        # Link walked (Event138 joins that), then the quest step 'Complete'.
        'flow': 'Event/EventFlow/Dm_SY_BancChange_EscapeDungeon.bfevfl.zs',
        'after': 'Event138',
    },
}
GIFT_GET_SOURCE = ('GetPouchContent', 'GetPouchContentByActorName')
GIFT_GET_TARGET = ('Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc')
GIFT_GET_EVENT = 'RandoGiftGet'


def _predecessors(chart, target):
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


def bypass_cutscene_gift(raw, name):
    """Returns (bytes, report): the cutscene goes on without adding its item.

    The add and its collection marker (``RandoCollected_<name>``, if any) stay in
    the file, unreachable; report = {'actor', 'flag' (or None), 'resume'}.
    """
    from evfl.event import ActionEvent, SubFlowEvent
    from evfl.util import make_index
    from oot_rando.patching.event_patch import _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    events = {e.name: e for e in chart.events}
    event = events.get(name)
    data = getattr(event, 'data', None)
    if (not isinstance(data, SubFlowEvent) or (data.res_flowchart_name, data.entry_point_name) != GIFT_GET_SOURCE
            or data.params is None or not isinstance(data.params.data.get('ActorName'), str)
            or data.nxt.v is None):
        raise ValueError('Unexpected cutscene item hand-over: ' + str(name))
    resume, flag = data.nxt.v, None
    marker = events.get('RandoCollected_' + name)
    if marker is not None and resume is marker:
        if (not isinstance(marker.data, ActionEvent) or marker.data.actor_action.v.v != 'EventTriggerSetGameDataBool'
                or len(_predecessors(chart, marker)) != 1):
            raise ValueError('Unexpected collection marker: ' + marker.name)
        flag, resume = marker.data.params.data['GameDataName'], marker.data.nxt.v
    if resume is None:
        raise ValueError('Cutscene item hand-over without continuation: ' + name)
    links = _predecessors(chart, event)
    if not links:
        raise ValueError('Cutscene item hand-over never reached: ' + name)
    for owner, kind, key in links:
        if kind == 'nxt':
            owner.data.nxt = make_index(resume)
        elif kind == 'case':
            owner.data.cases[key] = make_index(resume)
        elif kind == 'fork':
            owner.data.forks[key] = make_index(resume)
        else:
            owner.main_event = make_index(resume)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Bypassing the cutscene item changed other parameters.')
    written = {e.name: e for e in checked.flowchart.events}
    if _predecessors(checked.flowchart, written[name]):
        raise ValueError('Cutscene item hand-over still reached: ' + name)
    return result, {'actor': data.params.data['ActorName'], 'flag': flag, 'resume': resume.name}


def give_gift_after(raw, after, actor, flag=None):
    """Returns (bytes, report): the shown item get of ``actor`` right after ``after``.

    ``flag`` (a collection flag) is set once the item get returns.
    """
    from evfl.container import Container
    from evfl.event import Event, SubFlowEvent
    from evfl.util import make_index
    from oot_rando.patching.event_patch import _flow, _snapshot, add_collection_markers
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    events = {e.name: e for e in chart.events}
    anchor = events.get(after)
    if anchor is None or getattr(anchor.data, 'nxt', None) is None or anchor.data.nxt.v is None:
        raise ValueError('No continuation after ' + str(after))
    if GIFT_GET_EVENT in events:
        raise ValueError('Gift already given in this flow.')
    gift = Event()
    gift.name, gift.data = GIFT_GET_EVENT, SubFlowEvent()
    gift.data.res_flowchart_name, gift.data.entry_point_name = GIFT_GET_TARGET
    gift.data.params = Container()
    gift.data.params.data = {'ActorName': actor, 'IsNpcEventStarter': False}
    gift.data.nxt = anchor.data.nxt
    anchor.data.nxt = make_index(gift)
    chart.events.append(gift)
    expected[GIFT_GET_EVENT] = dict(gift.data.params.data)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('The gift changed other parameters.')
    written = {e.name: e for e in checked.flowchart.events}
    if (written[after].data.nxt.v.name != GIFT_GET_EVENT
            or (written[GIFT_GET_EVENT].data.res_flowchart_name, written[GIFT_GET_EVENT].data.entry_point_name)
            != GIFT_GET_TARGET):
        raise ValueError('Gift wrongly chained.')
    report = {'after': after, 'actor': actor, 'call': '/'.join(GIFT_GET_TARGET), 'flag': flag}
    if flag:
        result, records = add_collection_markers(result, {GIFT_GET_EVENT: flag})
        report['marker'] = records[0]['marker']
    return result, report


# Kokiri Sword chest. Its ``GetEventName`` (Get_StoneOfForest_GetSword) runs the
# chest performance, then the ``Dm_Kokiri_0063`` cutscene, which creates the
# Kokiri Sword as a *dynamic* equipment outside the pouch and equips it
# (EventTriggerPlayerRequestCreateDynamicEquipmentNoRelationPouch). With another
# item in the chest, Link still held the sword until the next reload (user test,
# 11/11). The transition is bypassed: the chest itself still gives its content.
SWORD_CHEST_FLOW = 'Event/EventFlow/Get_StoneOfForest.bfevfl.zs'
SWORD_CHEST_ENTRY = 'GetSword'
SWORD_CUTSCENE = 'Dm_Kokiri_0063'


def skip_kokiri_sword_cutscene(raw):
    """Returns (bytes, report). Only the links to the transition change."""
    from evfl.util import make_index
    from oot_rando.patching.event_patch import _flow, _snapshot
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    if not any(e.name == SWORD_CHEST_ENTRY for e in chart.entry_points):
        raise ValueError('GetSword entry missing from Get_StoneOfForest.')
    transitions = [e for e in chart.events if getattr(e.data, 'actor_action', None) is not None
                   and e.data.actor_action.v.v == 'EventTransition' and e.data.params is not None
                   and e.data.params.data.get('EventName') == SWORD_CUTSCENE]
    if len(transitions) != 1 or transitions[0].data.nxt.v is None:
        raise ValueError('Unexpected transition to the Kokiri Sword cutscene.')
    transition = transitions[0]
    after = transition.data.nxt.v
    callers = [e for e in chart.events if getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is transition]
    if (len(callers) != 1 or any(getattr(e.data, 'cases', None) and transition in [c.v for c in e.data.cases.values()]
                                 for e in chart.events)
            or any(ep.main_event.v is transition for ep in chart.entry_points)):
        raise ValueError('Kokiri Sword cutscene called elsewhere.')
    caller = callers[0]
    caller.data.nxt = make_index(after)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Skipping the sword cutscene changed other parameters.')
    events = {e.name: e for e in checked.flowchart.events}
    if events[caller.name].data.nxt.v.name != after.name:
        raise ValueError('Kokiri Sword chest wrongly chained.')
    if any(getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is not None
           and e.data.nxt.v.name == transition.name for e in checked.flowchart.events):
        raise ValueError('The Kokiri Sword cutscene is still reachable.')
    return result, {'entry': SWORD_CHEST_ENTRY, 'bypassed': transition.name, 'cutscene': SWORD_CUTSCENE,
                    'from': caller.name, 'to': after.name}


def unlock_cutscene(raw):
    """Remove a final ``Components.SkipSetting = DisableSkip`` entry in place."""
    b = Byml(raw)
    if b.endian != '<' or b.root.get('Components', {}).get('SkipSetting') != DISABLE_SKIP:
        raise ValueError('Cutscene without a recognised skip ban.')
    off = b.u32(slot(b, ['Components'], 0xc1))
    count = b.u24(off + 1)
    if b.data[off] != 0xc1 or b.keys[b.u24(off + 4 + (count - 1) * 8)] != 'SkipSetting':
        raise ValueError('SkipSetting is not the last dictionary entry.')
    expected = copy.deepcopy(b.root)
    del expected['Components']['SkipSetting']
    patched = bytearray(raw)
    patched[off + 1:off + 4] = (count - 1).to_bytes(3, 'little')
    patched = bytes(patched)
    if len(patched) != len(raw) or Byml(patched).root != expected:
        raise ValueError('Semantic check of the cutscene failed.')
    return patched


def cutscene_files(read):
    """``read(path)`` returns raw loose files. Returns ({path: bytes}, report).

    The intro keeps its byte-checked validated pilot; the other locked cutscenes
    follow the same rule. Area presentations are rows of the EventSetting table
    (``patch_dialogues(..., areas=True)``).
    """
    files = {INTRO: patch_intro(read(INTRO), read(INTRO_PARENT))}
    report = ['Dm_Kokiri_0000']
    for name in sorted(LOCKED_CUTSCENES):
        files[list_path(name)] = unlock_cutscene(read(list_path(name)))
        report.append(name)
    return files, report


def patch_dialogues(raw, step_start=True, areas=True):
    """Return (patched RSDB EventSetting table, summary)."""
    if sha256(raw) != EVENT_SETTINGS_SOURCE_SHA:
        raise ValueError('Unsupported EventSetting table.')
    summary = {'rows': 0, 'by_list': {}, 'area_rows': 0}
    mapping = dict(NPC_STEP_START) if step_start else {}
    b = Byml(raw)
    index = {value: i for i, value in enumerate(b.strings)}
    targets = {}
    for source, target in mapping.items():
        if _work(target) not in index:
            raise ValueError('Target component list missing: ' + target)
        targets[_work(source)] = (source, index[_work(target)])
    expected = copy.deepcopy(b.root)
    patched = bytearray(raw)
    presentations = {'Work/' + FLOWS + name + '.evfc' for name in AREA_PRESENTATIONS}
    areas_to = {}
    if areas:
        for source, target in AREA_PRESENTATION_LISTS.items():
            if _work(target) not in index:
                raise ValueError('Target component list missing: ' + target)
            areas_to[_work(source)] = (source, index[_work(target)])
    for i, row in enumerate(b.root):
        current = row.get('EventSettingComponentList')
        if current in areas_to and row.get('FlowchartFileName') in presentations:
            source, string = areas_to[current]
            struct.pack_into('<I', patched, slot(b, [i, 'EventSettingComponentList']), string)
            expected[i]['EventSettingComponentList'] = b.strings[string]
            summary['area_rows'] += 1
            continue
        if current not in targets:
            continue
        source, string = targets[current]
        struct.pack_into('<I', patched, slot(b, [i, 'EventSettingComponentList']), string)
        expected[i]['EventSettingComponentList'] = b.strings[string]
        summary['rows'] += 1
        summary['by_list'][source] = summary['by_list'].get(source, 0) + 1
    patched = bytes(patched)
    if len(patched) != len(raw) or Byml(patched).root != expected:
        raise ValueError('Semantic check of the dialogues failed.')
    return patched, summary


# Kokiri shop: before the Deku Tree the game shows a short stock (three items,
# "sold out" boards elsewhere); the full stock appears only after the Deku Tree.
# AP logic sells every KF shop slot from the start, and shopsanity may place
# progression there, so the full stock is shown from the start.
KOKIRI_SHOP_MAPS = (
    'Banc/KokiriForest/KokiriForest_Child_Static.bcett.byml.zs',
    'Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs',
    'Banc/KokiriForest/KokiriForest_Adult_Dynamic.bcett.byml.zs',
)
KOKIRI_SHOP_FLAG = 'Meet_DekuTree_IsAfter_Step02_Exp'


def _shop_actor(name):
    return name.startswith('Shop_') or name.startswith('Npc_Kokiri_001_Shop')


def open_kokiri_shop(raw, hidden_flag):
    """Full stock always present; short stock and its sold-out boards hidden.

    ``hidden_flag`` must be a saved bool that is True during play (the seed
    marker set at the end of the opening). Actors are never removed, so no
    reference, group or patched index changes. Returns (raw, changed count).
    """
    from oot_rando.formats import byml_codec
    document = byml_codec.load(raw)
    changed = 0
    for actor in document['root'].get('Actors', []):
        presence = actor.get('Presence')
        if not isinstance(presence, dict) or presence.get('FlagName') != KOKIRI_SHOP_FLAG:
            continue
        if not _shop_actor(actor.get('Gyaml', '')):
            continue
        if presence.get('IsNegation'):
            presence['FlagName'] = hidden_flag  # hidden once the opening is over
        else:
            del actor['Presence']
        changed += 1
    if not changed:
        return raw, 0
    return byml_codec.dump(document), changed


KOKIRI_SHOP_PACKS = tuple(f'Pack/Actor/{name}.pack.zs' for name in (
    'Npc_Kokiri_001_Shop_Child', 'Npc_Kokiri_001_Shop_Adult', 'Npc_Kokiri_001_Shop_Child_ShortStock'))


# Mido guards the way to the Deku Tree. His air wall (KokiriForest_Child_Dynamic,
# FldObj_AirWall_Player_GenerateNavMesh, Presence = MIDO_WALL_FLAG, saved, default
# True) is only lowered by his "sword and shield" talk (DC0_TT, default schedule).
# His AIScheduleParam lists story states, the last true ConditionFlag winning (they
# stay true for the rest of the game). Meeting Zelda first, which vanilla never
# allows, selects the last one (Goto_HyruleCastle_IsCompleted_Exp): Mido walks away
# without that talk and the wall stays forever (issue #16).
#
# While the wall stands he now keeps his post: a copy of the default schedule
# conditioned by the wall flag, then the guard schedule (MIDO_GUARD_FLAG, set while
# the player is in the zone of KokiriForest_Child_Level_All_02_35ae and the wall
# stands), both after every story state. In vanilla both flags are only true before
# his talk, when no story state is: the order changes nothing there.
MIDO_SCHEDULE = 'Component/AIScheduleParam/Npc_Kokiri_Mido_Child.game__component__AIScheduleParam.bgyml'
MIDO_WALL_FLAG = 'KokiriForest_Npc_Kokiri_Mido_Child_Blocker'
MIDO_GUARD_FLAG = 'KokiriForest_Npc_Kokiri_Blocker'
MIDO_PASS_TALK = 'Work/Event/EventSetting/Npc_Kokiri_Mido_Child_DC0_TT.engine__event__EventSettingParam.gyml'


def keep_mido_at_post(raw):
    """Mido keeps guarding the Deku Tree path until his talk lowers the wall.

    Returns (new BYML bytes, summary)."""
    from oot_rando.formats import byml_codec
    document = byml_codec.load(raw)
    root = document['root']
    states = root['ConditionalSchedule']
    flags = [state['ConditionFlag'] for state in states]
    if MIDO_WALL_FLAG in flags:
        raise ValueError("Mido's schedule is already patched.")
    if flags.count(MIDO_GUARD_FLAG) != 1 or flags[0] != MIDO_GUARD_FLAG:
        raise ValueError("Unexpected Mido schedule: guard state not first.")
    default = root['DefaultSchedule']
    if [e.get('EventName') for e in default.get('EventEntry', [])] != [MIDO_PASS_TALK]:
        raise ValueError("Unexpected Mido default schedule: pass talk missing.")
    post = copy.deepcopy(default)
    post['ConditionFlag'] = MIDO_WALL_FLAG
    root['ConditionalSchedule'] = states[1:] + [post, states[0]]
    result = byml_codec.dump(document)
    check = [s['ConditionFlag'] for s in byml_codec.load(result)['root']['ConditionalSchedule']]
    if check != flags[1:] + [MIDO_WALL_FLAG, MIDO_GUARD_FLAG]:
        raise ValueError("Mido's schedule wrongly rewritten.")
    return result, {'file': MIDO_SCHEDULE, 'order': check}


def release_kokiri_shop_goods(pack_raw):
    """Clear the Deku Tree "Release" condition of every good in the shop's ShopParam.

    The shop NPC sells a GoodsList entry only once its ReleaseGameData flag is
    set; five of the eight Kokiri goods wait for ``Meet_DekuTree_IsAfter_Step02_Exp``.
    Only those Release blocks change. Returns (new SARC bytes, changed goods).
    """
    from oot_rando.formats import byml_codec
    from oot_rando.formats.inspect_resources import sarc
    files = dict(sarc(pack_raw))
    changed = 0
    for name in sorted(files):
        if not (name.startswith('Component/ShopParam/') and name.endswith('.bgyml')):
            continue
        if KOKIRI_SHOP_FLAG.encode() not in files[name]:
            continue
        document = byml_codec.load(files[name])
        count = 0
        for good in document['root'].get('GoodsList', []):
            release = good.get('Release')
            if isinstance(release, dict) and release.get('ReleaseGameData') == KOKIRI_SHOP_FLAG:
                release['IsCheckReleaseGameData'] = False
                release['ReleaseGameData'] = ''
                count += 1
        if count:
            files[name] = byml_codec.dump(document)
            changed += count
    if not changed:
        return pack_raw, 0
    return byml_codec.build_sarc(files), changed


# The remake gives the player's own bombs the bomb-flower lift grade, i.e. the
# grade granted by the Goron Bracelet (``Item_Gauntlet_Goron`` ExpansionAbilityActor
# LiftableGrade). Without the bracelet Link takes a bomb out and puts it away at
# once. Vanilla never shows it (bomb bag after the bracelet); AP logic lets bombs
# be used with the bag alone. Bomb flowers keep their own LiftableParam
# (``Obj_BombFlower_Fruit``), so they still need the bracelet.
BOMB_LIFTABLE = 'Component/LiftableParam/Item_Bomb.game__component__LiftableParam.bgyml'
BRACELET_LIFT_GRADE = 3655598229
FREE_LIFT_GRADE = 3069107721      # pots, cuccos, bombchus: no strength needed
# Every pack holding a copy of the bomb's file, patched alike whichever is loaded first.
BOMB_LIFT_PACKS = tuple(f'Pack/Actor/{name}.pack.zs' for name in (
    'Item_Bomb', 'Npc_Hylia_ImperialSoldier_Bomb', 'Obj_BombFlower_A_01', 'Obj_BombFlower_A_04',
    'Obj_BombFlower_Fruit_For_Break_Obj_DeathMtTrail_BrokenRock_A_01'))


def free_bomb_lift(pack_raw):
    """Let Link hold his own bombs without the Goron Bracelet. Returns (SARC bytes, changed)."""
    from oot_rando.formats import byml_codec
    from oot_rando.formats.inspect_resources import sarc
    files = dict(sarc(pack_raw))
    if BOMB_LIFTABLE not in files:
        return pack_raw, 0
    document = byml_codec.load(files[BOMB_LIFTABLE])
    if document['root'].get('LiftGrade') != BRACELET_LIFT_GRADE:
        return pack_raw, 0
    document['root']['LiftGrade'] = byml_codec.U32(FREE_LIFT_GRADE)
    files[BOMB_LIFTABLE] = byml_codec.dump(document)
    return byml_codec.build_sarc(files), 1


# Gold skulltulas shown only at night carry ``Enemy_Skulltula_Gold_Nocturnal: true``
# on their map instance (30 skulltulas in 18 maps, v131072). Setting it to false makes
# them behave like the other skulltulas: present day and night.
NOCTURNAL_FIELD = 'Enemy_Skulltula_Gold_Nocturnal'
NOCTURNAL_SKULLTULA_MAPS = tuple(f'Banc/{folder}/{folder}_{variant}_Static.bcett.byml.zs' for folder, variant in (
    ('DesertColossus', 'Adult'), ('DesertColossus', 'Child'), ('GerudoFortress', 'Adult'),
    ('GerudoValley', 'Adult'), ('GerudoValley', 'Child'), ('Graveyard', 'Adult'), ('Graveyard', 'Child'),
    ('HyruleField', 'Adult'), ('HyruleField', 'Child'), ('KakarikoVillage', 'Adult_Alternative'),
    ('KakarikoVillage', 'Adult'), ('KakarikoVillage', 'Child'), ('KokiriForest', 'Adult'),
    ('KokiriForest', 'Child'), ('ZoraFountain', 'Adult'), ('ZoraFountain', 'Child'),
    ('ZoraRiver', 'Adult'), ('ZoraRiver', 'Child')))


def is_nocturnal_skulltula(actor):
    dynamic = actor.get('Dynamic')
    return (actor.get('Gyaml') == 'Enemy_Skulltula_Gold' and isinstance(dynamic, dict)
            and dynamic.get(NOCTURNAL_FIELD) is True)


def nocturnal_skulltula_edits(root):
    """``patch_strings`` edits making every night-only gold skulltula of a map always present."""
    return [{'path': ('Actors', index, 'Dynamic', NOCTURNAL_FIELD), 'before': True, 'after': False}
            for index, actor in enumerate(root.get('Actors', [])) if is_nocturnal_skulltula(actor)]
