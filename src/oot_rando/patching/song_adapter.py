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

* at a song location: the teaching calls become a one-frame wait (no wrong melody
  taught or added), the silent add gives the placed item, then its get window;
* at another cutscene source (dungeon reward, great fairy, story reward): the give
  call becomes the silent add, followed by the get window. A pose-based get
  (``Dm_SY_GetInEvent/*``) is replaced the same way;
* an item placed at a song location gets the same text-only window.

Song cutscenes are started by quest steps, not by the song itself, except the
windmill man (adult): he plays Song of Storms' cutscene only while
``IsGet.Item_Melody_StormSong`` is false. When songs are shuffled, his checks read
the check's own collection flag instead, so the location stays available after
Song of Storms was found elsewhere.

Not validated in game.
"""
import io

# AP song item -> (remake actor, MelodyType of Dm_SY_Ocarina).
SONGS = {
    'Zeldas Lullaby': ('Item_Melody_ZeldaLullaby', 0), 'Eponas Song': ('Item_Melody_EponaSong', 1),
    'Sarias Song': ('Item_Melody_SariaSong', 2), 'Suns Song': ('Item_Melody_SunSong', 3),
    'Song of Time': ('Item_Melody_TimeSong', 4), 'Song of Storms': ('Item_Melody_StormSong', 5),
    'Minuet of Forest': ('Item_Melody_ForestMinuet', 6), 'Bolero of Fire': ('Item_Melody_FireBolero', 7),
    'Serenade of Water': ('Item_Melody_WaterSerenade', 8), 'Requiem of Spirit': ('Item_Melody_SpiritRequiem', 9),
    'Nocturne of Shadow': ('Item_Melody_ShadowNocturne', 10), 'Prelude of Light': ('Item_Melody_LightPrelude', 11),
}
SONG_ACTOR_ITEMS = {actor: item for item, (actor, _) in SONGS.items()}
MELODY_PREFIX = 'Item_Melody_'

# Song locations: (AP location, give flow, give event, vanilla actor, teaching flows; None: the give flow).
SONG_LOCATIONS = (
    ('Song from Impa', 'Dm_MelodyGet_Zelda', 'Event111', 'Item_Melody_ZeldaLullaby', None),
    ('Song from Malon', 'Dm_MelodyGet_Epona', 'Event11', 'Item_Melody_EponaSong', None),
    ('Song from Saria', 'Dm_MelodyGet_Saria', 'Event109', 'Item_Melody_SariaSong', None),
    ('Song from Royal Familys Tomb', 'Dm_MelodyGet_Sun_03', 'Event34', 'Item_Melody_SunSong', ('Dm_MelodyGet_Sun',)),
    ('Song from Ocarina of Time', 'Dm_MelodyGet_Time', 'Event4', 'Item_Melody_TimeSong', None),
    ('Song from Windmill', 'Dm_MelodyGet_Storm', 'Event29', 'Item_Melody_StormSong', None),
    ('Sheik in Forest', 'Dm_MelodyGet_Forest', 'Event22', 'Item_Melody_ForestMinuet', None),
    ('Sheik in Crater', 'Dm_MelodyGet_Fire', 'Event192', 'Item_Melody_FireBolero', None),
    ('Sheik in Ice Cavern', 'Dm_MelodyGet_Water', 'Event29', 'Item_Melody_WaterSerenade', None),
    ('Sheik at Colossus', 'Dm_MelodyGet_Spilit', 'Event17', 'Item_Melody_SpiritRequiem', None),
    ('Sheik in Kakariko', 'Dm_MelodyGet_Shadow', 'Event21', 'Item_Melody_ShadowNocturne', None),
    ('Sheik at Temple', 'Dm_MelodyGet_Shine', 'Event53', 'Item_Melody_LightPrelude', None),
)
# Direct writes of a song's own flag in its cutscene (besides the silent add).
SONG_FLAG_EVENTS = {'Sheik in Crater': (('Dm_MelodyGet_Fire', 'Event1', 'IsGet.Item_Melody_FireBolero'),)}
# Queries that start (or describe) a song cutscene only while its song is missing.
TRIGGER_QUERIES = {
    'Song from Windmill': ('Npc_Hylia_009_Adult', ('Event9', 'Event17', 'Event31', 'Event69'),
                           'IsGet.Item_Melody_StormSong'),
}
TEACHING_FLOW = 'Dm_SY_Ocarina'
TEACHING_PREFIX = 'LearningOcarina'
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
SHUFFLE_MODES = ('shuffled', 'dungeon', 'any')


def is_song_actor(actor):
    return isinstance(actor, str) and actor.startswith(MELODY_PREFIX)


def song_gifts():
    """Song locations in the ``EVENT_GIFTS`` format of ``extra_sources``."""
    return tuple(('song', (ap,), (), ((stem, event, actor),)) for ap, stem, event, actor, _ in SONG_LOCATIONS)


def location_flows(ap):
    for location, stem, _, _, teaching in SONG_LOCATIONS:
        if location == ap:
            return (stem,) if teaching is None else tuple(teaching)
    raise ValueError('Not a song location: ' + ap)


def song_allowed(mode, source, actor):
    """Placement rule of the ``shuffle_song_items`` mode (``actor``: canonical reward actor)."""
    song = is_song_actor(actor)
    if mode not in SHUFFLE_MODES:
        return not song and source != 'song'
    if mode == 'shuffled':
        return song == (source == 'song')
    if not song:
        return True
    if mode == 'dungeon':
        return source in ('song', 'boss')
    return source in TEXT_ONLY_SOURCES


def display_event_name(event):
    return 'RandoTextGet_' + event


def _flow(raw):
    from oot_rando.patching.event_patch import _flow as read
    return read(raw)


def _snapshot(flow):
    from oot_rando.patching.event_patch import _snapshot as snap
    return snap(flow)


def patch_flow(raw, ops):
    """Apply the song operations of one flow. Returns new bytes.

    ``ops`` keys (all optional):

    * ``teaching``: True → every ``Dm_SY_Ocarina/LearningOcarina*`` call becomes a
      one-frame ``EventSystemActor.EventWait``;
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
    flow = _flow(raw)
    chart = flow.flowchart
    events = {e.name: e for e in chart.events}
    expected = _snapshot(flow)
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
    if ops.get('teaching'):
        for event in list(chart.events):
            data = event.data
            if (isinstance(data, SubFlowEvent) and data.res_flowchart_name == TEACHING_FLOW
                    and data.entry_point_name.startswith(TEACHING_PREFIX)):
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
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Song patch changed other parameters.')
    written = {e.name: e for e in checked.flowchart.events}
    for name, _, _ in ops.get('text_get', ()):
        shown = written.get(display_event_name(name))
        if shown is not None and written[name].data.nxt.v is not shown:
            raise ValueError('Invalid text-only get chain: ' + name)
    return result


def site_kind(raw, event):
    """``'display'`` (text window call), ``'silent'`` or ``'other'`` for one give event."""
    from evfl.event import SubFlowEvent
    events = {e.name: e for e in _flow(raw).flowchart.events}
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
