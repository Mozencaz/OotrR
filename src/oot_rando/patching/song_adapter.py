"""Songs as items: song locations as sources, songs given with their text only.

The remake's songs are pouch actors (``Item_Melody_<song>``, model of a rupee as a
placeholder, ``KeyItemMelody`` content). Each song cutscene (``Dm_MelodyGet_*``)
teaches its melody with ``Dm_SY_Ocarina/LearningOcarina*`` (the NPC plays it,
the player plays it back, then ``LearningOcarinaPlayAuto``/``…ForSeek`` adds the
melody of the current ``MelodyType`` to the pouch) and also adds it silently with
``GetPouchContent/GetPouchContentByActorName`` (the event shuffled here).

The game already has a text-only get: ``GetPouchContent/DisplayGetByActorName``
opens the get window of an actor ("You learned Saria's Song!", with its caption)
without any pose; Saria's Fairy Ocarina gift uses it after a silent add. Every
shuffled song is given that way, so nothing appears in Link's hands:

* at every song location (songs shuffled or not): the NPC's example
  (``LearningOcarinaPlayExample``) only sets the melody to play, without the NPC
  playing it; the player's play-back (``LearningOcarinaFollowExample``) stays: Link's
  tune at the end (Sheik's duet for the warp songs) plays the notes just input, it
  stays silent without them (tested 19/11). A location keeping its own
  song keeps the vanilla end, which adds the melody; a location given another item
  plays it without the melody being added (``LearningOcarinaPlayAuto*`` → the
  ``Rando*`` entries of :func:`add_teaching_entries`), the silent add gives the
  placed item, then its get window;
* at another cutscene source (dungeon reward, great fairy, story reward): the give
  call becomes the silent add, followed by the get window. A pose-based get
  (``Dm_SY_GetInEvent/*``) is replaced the same way;
* an item placed at a song location gets the same text-only window.

Song cutscenes are started by quest steps, not by the song itself, except the
windmill man (adult): he plays Song of Storms' cutscene only while
``IsGet.Item_Melody_StormSong`` is false. When songs are shuffled, his checks parse_flow
the check's own collection flag instead, so the location stays available after
Song of Storms was found elsewhere.

Not validated in game.
"""
import io

from oot_rando.catalog.songs import (  # noqa: F401  (moved to oot_rando.catalog.songs, re-exported)
    SONGS,
    SONG_ACTOR_ITEMS,
    MELODY_PREFIX,
    SONG_LOCATIONS,
    is_song_actor,
    song_gifts,
)
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

# Direct writes of a song's own flag in its cutscene (besides the silent add).
SONG_FLAG_EVENTS = {'Sheik in Crater': (('Dm_MelodyGet_Fire', 'Event1', 'IsGet.Item_Melody_FireBolero'),)}
# Queries that start (or describe) a song cutscene only while its song is missing.
TRIGGER_QUERIES = {
    'Song from Windmill': ('Npc_Hylia_009_Adult', ('Event9', 'Event17', 'Event31', 'Event69'),
                           'IsGet.Item_Melody_StormSong'),
}
TEACHING_FLOW = 'Dm_SY_Ocarina'
TEACHING_PREFIX = 'LearningOcarina'
TEACHING_FLOW_PATH = 'Event/EventFlow/Dm_SY_Ocarina.bfevfl.zs'
# Teaching calls → entries of ours: the example to memorise goes, the player's
# play-back (TEACHING_KEPT) and Link's tune stay (user reports 19/11), no melody is
# added. Any other teaching call becomes a one-frame wait. ``teaching`` op values: True (another item
# is placed: every call of TEACHING_REPLACED) or KEEP_ADD (the song stays: only the
# minigame is replaced, the vanilla end adds the melody).
KEEP_ADD = 'keep_add'
TEACHING_KEEP_ADD = ('LearningOcarinaPlayAuto', 'LearningOcarinaPlayAutoForSeek')
TEACHING_KEPT = ('LearningOcarinaFollowExample',)
TEACHING_REPLACED = {
    'LearningOcarinaPlayExample': 'RandoLearningPrepare',
    'LearningOcarinaPlayAuto': 'RandoLearningPlayAuto',
    'LearningOcarinaPlayAutoForSeek': 'RandoLearningPlayAutoForSeek',
}
# Frames LearningOcarinaPlayAuto waits per melody type for Link's tune to end.
PLAY_AUTO_WAITS = {0: 330, 1: 270, 2: 250, 3: 150, 4: 380, 5: 180, 12: 60}
GET_FLOW = 'GetPouchContent'
SILENT_ENTRY = 'GetPouchContentByActorName'
DISPLAY_ENTRY = 'DisplayGetByActorName'
DISPLAY_ENTRIES = (DISPLAY_ENTRY, 'DisplayRutoGetByActorName')
POSE_FLOW = 'Dm_SY_GetInEvent'
# Cutscene sources whose give event can become a text-only get (see module doc).
TEXT_ONLY_SOURCES = ('song', 'boss', 'fairy', 'quest')
# Sources whose item is given back after the cutscene with Link's pose
# (``qol_patches.GIFT_AFTER_CUTSCENE``, pilot): never a song there.
POSE_AFTER_CUTSCENE = ('Queen Gohma',)
WAIT_PARAMS = {'IsWaitEnd': True, 'Frames': 1}
SHUFFLE_MODES = ('shuffled', 'dungeon', 'any', 'everywhere')
# "Everywhere": a song can also stand in a chest or be a pickup (freestanding spot,
# pot, crate, gold skulltula...). Those gets show the song's actor in Link's hands,
# so the songs get Sheik's harp as their model, in the song's colour (song_models).
HELD_FORMS = ('chest', 'world')


def location_flows(ap):
    for location, stem, _, _, teaching in SONG_LOCATIONS:
        if location == ap:
            return (stem,) if teaching is None else tuple(teaching)
    raise ValueError('Not a song location: ' + ap)


def song_allowed(mode, source, actor, form=None):
    """Placement rule of the ``shuffle_song_items`` mode (``actor``: canonical reward actor,
    ``form``: item form of the location, see ``item_forms``)."""
    song = is_song_actor(actor)
    if mode not in SHUFFLE_MODES:
        return not song and source != 'song'
    if mode == 'shuffled':
        return song == (source == 'song')
    if not song:
        return True
    if mode == 'dungeon':
        return source in ('song', 'boss')
    if mode == 'everywhere' and form in HELD_FORMS:
        return True
    return source in TEXT_ONLY_SOURCES


def display_event_name(event):
    return 'RandoTextGet_' + event


def patch_flow(raw, ops):
    """Apply the song operations of one flow. Returns new bytes.

    ``ops`` keys (all optional):

    * ``teaching``: True → the ``Dm_SY_Ocarina/LearningOcarina*`` calls of
      :data:`TEACHING_REPLACED` call our entries instead (same parameters), any other
      becomes a one-frame ``EventSystemActor.EventWait``; :data:`KEEP_ADD`: the same,
      except the calls of :data:`TEACHING_KEEP_ADD`, left as they are;
    * ``neutralize``: event names turned into the same wait (a song flag write);
    * ``text_get``: ``[[event, actor, show], …]``: the give event becomes the silent
      ``GetPouchContent/GetPouchContentByActorName`` of ``actor`` (unless it already
      adds silently or displays); with ``show``, ``GetPouchContent/DisplayGetByActorName``
      then shows its text (a site whose source already has a display call gets none);
    * ``params``: ``[[event, param, before, after], …]`` string parameter changes.

    Every other event keeps its parameters (checked on the written flow).
    """
    from evfl.common import StringHolder
    from evfl.container import Container
    from evfl.event import ActionEvent, Event, SubFlowEvent
    from evfl.util import make_index, make_rindex
    flow = parse_flow(raw)
    chart = flow.flowchart
    events = {e.name: e for e in chart.events}
    expected = params_by_event(flow)
    wait = None

    def to_wait(event):
        nonlocal wait
        if wait is None:
            actor = next((a for a in chart.actors if str(a.identifier) == 'EventSystemActor'), None)
            if actor is None:
                raise ValueError('EventSystemActor missing from the song flow.')
            action = next((a for a in actor.actions if a.v == 'EventWait'), None)
            if action is None:
                action = StringHolder('EventWait')
                actor.actions.append(action)
            wait = (actor, action)
        data = ActionEvent()
        data.nxt = event.data.nxt
        data.actor, data.actor_action = make_rindex(wait[0]), make_rindex(wait[1])
        data.params = Container()
        data.params.data = dict(WAIT_PARAMS)
        event.data = data
        expected[event.name] = dict(WAIT_PARAMS)

    stripped = 0
    teaching = ops.get('teaching')
    if teaching not in (None, False, True, KEEP_ADD):
        raise ValueError('Unknown song teaching mode.')
    if teaching:
        for event in list(chart.events):
            data = event.data
            if (isinstance(data, SubFlowEvent) and data.res_flowchart_name == TEACHING_FLOW
                    and data.entry_point_name.startswith(TEACHING_PREFIX)):
                if data.entry_point_name in TEACHING_KEPT or (
                        teaching == KEEP_ADD and data.entry_point_name in TEACHING_KEEP_ADD):
                    continue
                if data.entry_point_name in TEACHING_REPLACED:
                    data.entry_point_name = TEACHING_REPLACED[data.entry_point_name]
                else:
                    to_wait(event)
                stripped += 1
        if not stripped:
            raise ValueError('No melody teaching found in the song flow.')
    for name in ops.get('neutralize', ()):
        if name not in events:
            raise ValueError('Song flag event missing: ' + name)
        to_wait(events[name])
    for name, param, before, after in ops.get('params', ()):
        event = events.get(name)
        params = getattr(getattr(event, 'data', None), 'params', None)
        if params is None or params.data.get(param) != before or not isinstance(after, str) or not after:
            raise ValueError(f'Unexpected song event parameter: {name}.{param}')
        params.data[param] = after
        expected[name][param] = after
    for name, actor, show in ops.get('text_get', ()):
        event = events.get(name)
        data = getattr(event, 'data', None)
        if not isinstance(actor, str) or not actor:
            raise ValueError('Invalid text-only item.')
        if isinstance(data, SubFlowEvent) and data.res_flowchart_name == GET_FLOW \
                and data.entry_point_name in DISPLAY_ENTRIES:
            continue                       # already a text window (its silent add is another site)
        if isinstance(data, SubFlowEvent) and data.res_flowchart_name in (GET_FLOW, POSE_FLOW):
            if data.res_flowchart_name == POSE_FLOW or data.entry_point_name != SILENT_ENTRY:
                # Pose-based get → silent add (the text follows).
                data.res_flowchart_name, data.entry_point_name = GET_FLOW, SILENT_ENTRY
                data.params = Container()
                data.params.data = {'ActorName': actor}
                expected[name] = {'ActorName': actor}
            # A silent add keeps its item parameter (set by the placement edit).
        elif isinstance(data, ActionEvent) and str(data.actor.v.identifier) == 'PouchSystemActor' \
                and data.actor_action.v.v == 'EventTriggerAddOrRemovePouchContent':
            pass
        else:
            raise ValueError('Give event that cannot show a text-only get: ' + name)
        if not show:
            continue
        display = display_event_name(name)
        if display in events:
            raise ValueError('Text-only get already added: ' + name)
        shown = Event()
        shown.name, shown.data = display, SubFlowEvent()
        shown.data.res_flowchart_name, shown.data.entry_point_name = GET_FLOW, DISPLAY_ENTRY
        shown.data.params = Container()
        shown.data.params.data = {'ActorName': actor}
        shown.data.nxt = event.data.nxt
        event.data.nxt = make_index(shown)
        chart.events.append(shown)
        events[display] = shown
        expected[display] = {'ActorName': actor}
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = parse_flow(result)
    if params_by_event(checked) != expected:
        raise ValueError('Song patch changed other parameters.')
    written = {e.name: e for e in checked.flowchart.events}
    for name, _, _ in ops.get('text_get', ()):
        shown = written.get(display_event_name(name))
        if shown is not None and written[name].data.nxt.v is not shown:
            raise ValueError('Invalid text-only get chain: ' + name)
    return result


def add_teaching_entries(raw):
    """``Dm_SY_Ocarina`` with the entries the patched song cutscenes call (:data:`TEACHING_REPLACED`).

    * ``RandoLearningPrepare`` (``MelodyType`` from the caller): the melody to play is
      set as the example sets it, nobody plays it;
    * ``RandoLearningPlayAuto``: Link plays the melody (``PlayAuto_MelodyGet``), waits as
      ``LearningOcarinaPlayAuto`` does, then its light goes off; nothing added;
    * ``RandoLearningPlayAutoForSeek``: the warp-song duet with Sheik, nothing added.
    """
    from evfl.common import Argument
    from evfl.entry_point import EntryPoint
    from evfl.event import SwitchEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.progressive import FlowEditor, link
    editor = FlowEditor(raw, TEACHING_FLOW)
    chart = editor.chart
    entries = {e.name for e in chart.entry_points}
    if set(TEACHING_REPLACED.values()) & entries:
        raise ValueError('Teaching entries already added.')
    for needed in ('PlayAuto_MelodyGet', 'LightOff_NoPalette', *TEACHING_REPLACED):
        if needed not in entries:
            raise ValueError('Dm_SY_Ocarina entry missing: ' + needed)

    def entry(name, first, sub_flows=()):
        point = EntryPoint(name)
        point.main_event = make_index(first)
        point._sub_flow_event_indices = [chart.events.index(e) for e in sub_flows]
        chart.entry_points.append(point)

    # The example, without the NPC playing it.
    melody = editor.action('RandoTeach_SetMelody', 'GameSystemActor', 'EventTriggerPreparePlayExample',
                           {'MelodyType': Argument('MelodyType')})   # the caller's, not a text
    entry('RandoLearningPrepare', melody)
    # Link's tune, nothing added.
    play = editor.subflow('RandoTeach_PlayAuto', '', 'PlayAuto_MelodyGet', None)
    light = editor.subflow('RandoTeach_LightOff', '', 'LightOff_NoPalette', None)
    owner = editor.actor('GameSystemActor')
    switch = SwitchEvent()
    switch.actor = make_rindex(owner)
    switch.actor_query = make_rindex(editor._holder(owner.queries, 'EventQueryMelodyTypeForNormal'))
    chooser = editor._event('RandoTeach_Melody', switch, None)
    cases = {}
    for melody_type, frames in sorted(PLAY_AUTO_WAITS.items()):
        wait = editor.action(f'RandoTeach_Wait{melody_type}', 'EventSystemActor', 'EventWait',
                             {'IsWaitEnd': True, 'Frames': frames})
        link(wait, light)
        cases[melody_type] = make_index(wait)
    switch.cases = cases
    link(play, chooser)
    entry('RandoLearningPlayAuto', play, (play, light))
    # The warp songs' duet, nothing added.
    close = editor.action('RandoTeach_SeekClose', 'GameSystemActor', 'EventCloseMessageDialog', {'IsWaitEnd': True})
    pause = editor.action('RandoTeach_SeekWait', 'EventSystemActor', 'EventWait', {'IsWaitEnd': True, 'Frames': 30})
    tune = editor.action('RandoTeach_SeekTune', 'GameSystemActor', 'EventTriggerPlayAutoFixedTune',
                         {'IsLearningWarpMelodyDemo': True})
    link(close, pause)
    link(pause, tune)
    entry('RandoLearningPlayAutoForSeek', close)
    result, checked = editor.write('The song teaching entries')
    written = {e.name: e for e in checked.flowchart.entry_points}
    for name in TEACHING_REPLACED.values():
        if name not in written:
            raise ValueError('Teaching entry not written: ' + name)
    adds = [e for e in checked.flowchart.events if e.name.startswith('RandoTeach_')
            and getattr(getattr(e.data, 'actor_action', None), 'v', None) is not None
            and e.data.actor_action.v.v == 'EventTriggerAddOrRemovePouchContent']
    if adds:
        raise ValueError('A teaching entry adds a melody.')
    return result


def site_kind(raw, event):
    """``'display'`` (text window call), ``'silent'`` or ``'other'`` for one give event."""
    from evfl.event import SubFlowEvent
    events = {e.name: e for e in parse_flow(raw).flowchart.events}
    data = getattr(events.get(event), 'data', None)
    if isinstance(data, SubFlowEvent) and data.res_flowchart_name == GET_FLOW and data.entry_point_name in DISPLAY_ENTRIES:
        return 'display'
    return 'silent'


def plan_song_flows(placements, tracking_flags, shuffled_mode, paths, kind=lambda resource, event: 'silent'):
    """Song operations per flow (resource path → ops) for the placed items.

    ``placements``: dicts with ``source``, ``ap`` (AP locations), ``before``/``after``
    (vanilla / placed reward actor, canonical) and ``variants`` (``resource``,
    ``event``) of each shuffled cutscene source. ``tracking_flags``: AP location →
    collection flag of its check (song locations). ``paths(stem)``: the game's
    files of a flow (base and update). ``kind(resource, event)``: see :func:`site_kind`.
    """
    ops = {}

    def flow_ops(path):
        return ops.setdefault(path, {})

    def text_gets(placement, after):
        shown = any(kind(v['resource'], v['event']) == 'display' for v in placement['variants'])
        for variant in placement['variants']:
            flow_ops(variant['resource']).setdefault('text_get', []).append(
                [variant['event'], after, not shown])

    # Every song cutscene: no minigame, Link plays the melody himself (KEEP_ADD unless
    # another item is placed there, below).
    for ap, *_ in SONG_LOCATIONS:
        for stem in location_flows(ap):
            for path in paths(stem):
                flow_ops(path)['teaching'] = KEEP_ADD
    for placement in placements:
        source, before, after = placement['source'], placement['before'], placement['after']
        if source == 'song':
            ap = placement['ap'][0]
            if after != before:
                for stem in location_flows(ap):
                    for path in paths(stem):
                        flow_ops(path)['teaching'] = True
                text_gets(placement, after)
                for stem, event, flag in SONG_FLAG_EVENTS.get(ap, ()):
                    for path in paths(stem):
                        if is_song_actor(after):
                            flow_ops(path).setdefault('params', []).append(
                                [event, 'GameDataName', flag, 'IsGet.' + after])
                        else:
                            flow_ops(path).setdefault('neutralize', []).append(event)
        elif is_song_actor(after) and after != before:
            if source not in TEXT_ONLY_SOURCES:
                raise ValueError('A song cannot be given by this source: ' + source)
            text_gets(placement, after)
    if shuffled_mode in SHUFFLE_MODES:
        for ap, (stem, events, flag) in sorted(TRIGGER_QUERIES.items()):
            own = tracking_flags.get(ap)
            if not own:
                continue
            for path in paths(stem):
                flow_ops(path).setdefault('params', []).extend([[e, 'GameDataName', flag, own] for e in events])
    for value in ops.values():
        for key in ('text_get', 'params', 'neutralize'):
            if key in value:
                value[key] = sorted(value[key])
    return {path: value for path, value in sorted(ops.items())}


def check_song_ops(ops, event_edits):
    """Every text-only item matches the shuffled item of its event (verification)."""
    for path, value in ops.items():
        edits = event_edits.get(path, {})
        for event, actor, _ in value.get('text_get', ()):
            placed = next((a for (name, _), a in edits.items() if name == event), None)
            if placed is not None and placed != actor:
                raise ValueError('Text-only item differs from the spoiler: ' + path)
