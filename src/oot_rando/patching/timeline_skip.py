"""Animated story scenes that never play (option ``skip_story_timelines``).

A *pure timeline* is an event row (RSDB ``EventSetting``) with a ``TimelineFileName``:
camera, animations, voices, effects, fades, no flowchart. It changes nothing in the
save: the scan of 1.1.1 (20/11) found no GameData, quest, pouch or world write in any
of them. Flows play them with ``EventSystemActor.EventTransition`` (``EventName`` =
the row). With the option, each such transition listed in :data:`SITES` becomes
``HavePlayedEvent.<scene>`` = true (as if it had played: what tests it moves on),
then the flow goes on from where the scene would have ended. Same technique as
OOTRR (ootrando/ootrr, story_skip.rs), reimplemented.

Kept (never dropped), by rule, so the table can be rebuilt by :func:`scan`:

* the title demos, the staff roll and the ending (``Dm_Title_*``, ``Dm_StaffCredit_*``,
  ``Dm_Ending_*``) and every site that leads to them (the sages after Ganon);
* timelines that act on the world beyond the scene (:data:`STATE_ACTIONS`): actor warps
  (scarecrows at Lake Hylia, Ganon's tower rubble), the end credits' equipment change
  (actions ending with their scene are not changes: :func:`scene_only`, Link's sword held
  during the scene, the scene's own locators);
* scenes without a saved ``HavePlayedEvent`` Bool;
* sites where the scene is the first thing its event shows (the new-game intro, under
  the loading screen: nothing else would fade the screen in);
* sites where the screen is black before the scene (fade-out just before) and the
  scene does not fade it back in at its end (``FadeInTypeEventEnd`` 0): nothing would.

World actions a flow can run too (:data:`REPLAYED`) are replayed in place of the scene
(:data:`REPLAYS`): the time of day (Kaepora in Hyrule Field, Zelda's escape, Kakariko
burning and at night, Zora's Fountain) and the boss intros' fight start and boss music
(``EventDungeonBossSetConsiderBattlePresentation``, as the boss rush does without them).

"Was the last scene skipped?" (``EventQueryIsEventSkipedMostRecent``) asked after a dropped
scene has no answer about it any more: it takes the skipped case, made by the game for a
scene cut short (boss intros: boss music, camera; others: a fade). A site where that query
is also reached another way is kept.

When the screen is black before the scene and the scene fades it back in at its end,
the dropped scene is replaced by the same fade-in. Not validated in game.
"""
FLOWS = 'Event/EventFlow/'
PREFIX = 'RandoTimeline_'
EXCLUDED_FAMILIES = ('Dm_Title_', 'Dm_StaffCredit_', 'Dm_Ending_')
STATE_ACTIONS = ('EventWarpToTargetPosAndRot', 'EventWarpToHomeMatrix',
                 'EventTriggerEquipmentUserRequestChangeState',
                 'EventViewStaffRoll', 'EventOpenStaffRollEnd',
                 'EventCloseStaffRollEnd', 'EventPlayStaffRollEndIn', 'EventPlayStaffRollEndOut')
# Timeline actions that look like world changes but end with the scene (not replayed):
# * Link's sword in hand (``DynamicEquipmentSlot`` 0 = sword, ``EquipmentState`` 1 = held):
#   a clip that ends at the latest with the timeline, like the temporary boots. Nothing in
#   the pouch or the saved equipment changes, so dropping it changes no item, owned or
#   not; replaying it would draw a sword in play, even one Link does not have;
# * warps of the scene's own demo actors (``Dm_Locator``...: they exist only in the event).
# Warps of world actors (Lake Hylia's scarecrows) still keep their scene.
SWORD_IN_HAND = ('EventTriggerEquipmentUserRequestChangeState', {'DynamicEquipmentSlot': 0, 'EquipmentState': 1})
SCENE_ONLY_WARPS = ('EventWarpToTargetPosAndRot',)
SCENE_ACTOR_PREFIX = 'Dm_'
# Timeline actions on the world that the flows run too: replayed in place of the dropped
# scene (:data:`REPLAYS`), in the timeline's order, the last one of each actor and action
# (its final state). action -> its parameters (none: written without, as the flows do).
REPLAYED = {
    'EventTrigger_SetTime': ('TimeHour', 'TimeMin'),              # time of day (sun's song)
    'EventDungeonBossSetConsiderBattlePresentation': (),          # the boss fights (boss rush)
    'EventTriggerSoundStartBossBgm': ('BgmName',),
    'EventTriggerSoundStopBGM': ('BGMName', 'IsUseSuspendFade'),
}
TIME_ACTOR, TIME_ACTION = 'EventWorldManagerController', 'EventTrigger_SetTime'
SYSTEM_SUFFIXES = ('SystemActor', 'Controller')
QUERY = 'EventQueryIsEventSkipedMostRecent'
# Events walked back over to find the fade-out before a scene (they show nothing).
NEUTRAL_BEFORE = ('EventWait', 'EventTriggerParticipateEvent', 'EventSoundRequestDucking',
                  'EventTriggerStopInGameBgm', 'EventTriggerSetGameDataBool', 'EventPlayerUnequip')
FADE_IN = {'Color': 0, 'IsNoPlayAnime': False, 'IsWaitEnd': True, 'Length': 1}

# scene -> ((actor, action, params or None), ...) replayed when it is dropped
# (:func:`scene_replays` rebuilds it, tests compare).
REPLAYS = {
    'Dm_Deku_BossIn': (
        ('Enemy_DungeonBoss_Gohma', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_DodongoCave_BossIn': (
        ('Enemy_DungeonBoss_Dodongo', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss_Dinasour'}),
    ),
    'Dm_FireTemple_BossIn': (
        ('Enemy_DungeonBoss_Volvagia', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss_Volvagia'}),
    ),
    'Dm_ForestTemple_BossIn': (
        ('Enemy_DungeonBoss_PhantomGanon', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_HrlField_0005': (
        ('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 7, 'TimeMin': 30}),
    ),
    'Dm_HrlField_0060': (
        ('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 12, 'TimeMin': 0}),
    ),
    'Dm_InsideGanonCastle_BossIn': (
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss_Ganondorf'}),
        ('Enemy_DungeonBoss_Ganondorf', 'EventDungeonBossSetConsiderBattlePresentation', None),
    ),
    'Dm_InsideJabu_Jabu_BossIn': (
        ('Enemy_DungeonBoss_Barinade', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_Kakariko_0030': (
        ('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 0, 'TimeMin': 0}),
    ),
    'Dm_Kakariko_0040': (
        ('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 22, 'TimeMin': 0}),
    ),
    'Dm_ShadowTemple_BossIn': (
        ('Enemy_DungeonBoss_BongoBongo', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_SpiritTemple_0010': (
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_MiddleBoss'}),
    ),
    'Dm_SpiritTemple_0030': (
        ('SoundSystemActor', 'EventTriggerSoundStopBGM', {'BGMName': 'BGM_DungeonBoss_KotakeKoume', 'IsUseSuspendFade': False}),
        ('Enemy_DungeonBoss_Twinrova', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_SpiritTemple_BossIn': (
        ('Enemy_DungeonBoss_Kotake[KotakeKoumeBattleClient]', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('Enemy_DungeonBoss_Koume[KotakeKoumeBattleClient]', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss_KotakeKoume'}),
    ),
    'Dm_WaterTemple_BossIn': (
        ('Enemy_DungeonBoss_Morpha[BossDefeat]', 'EventDungeonBossSetConsiderBattlePresentation', None),
        ('SoundSystemActor', 'EventTriggerSoundStartBossBgm', {'BgmName': 'BGM_DungeonBoss'}),
    ),
    'Dm_ZoraFountain_0020': (
        ('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 12, 'TimeMin': 0}),
    ),
}

# flow -> ((transition event, scene), ...): every site dropped with the option (scan of
# 1.1.1, 20/11; :func:`scan` rebuilds it, tests compare).
SITES = {
    'AllSage': (('Event8', 'Dm_SageRoom_0010'), ('Event12', 'Dm_TimeTemple_0090'),
                ('Event14', 'Dm_TimeTemple_0110'), ('Event63', 'Dm_TimeTemple_0125'),
                ('Event42', 'Dm_TimeTemple_0135')),
    'Defeat_Ganon': (('Event269', 'Dm_FinalBattle_0005'), ('Event0', 'Dm_InsideGanonCastle_0000'),
                     ('Event154', 'Dm_InsideGanonCastle_0015'), ('Event152', 'Dm_InsideGanonCastle_0025'),
                     ('Event153', 'Dm_InsideGanonCastle_0032'), ('Event155', 'Dm_InsideGanonCastle_0055'),
                     ('Event156', 'Dm_InsideGanonCastle_0075'), ('Event157', 'Dm_InsideGanonCastle_0085'),
                     ('Event80', 'Dm_InsideGanonCastle_0110'), ('Event28', 'Dm_InsideGanonCastle_BossIn'),
                     ('Event30', 'Dm_InsideGanonCastle_BossOut')),
    'Dm_SY_BancChangeArrive': (('Event70', 'Dm_Kakariko_0030'), ('Event50', 'Dm_Kakariko_0040')),
    'Dm_SY_BancChange_EscapeDungeon': (('Event21', 'Dm_Awake_Fire'), ('Event211', 'Dm_Awake_Forest'),
                                       ('Event111', 'Dm_Awake_Shadow'), ('Event133', 'Dm_Awake_Spirit'),
                                       ('Event97', 'Dm_Awake_Water'), ('Event45', 'Dm_DeathMtTrail_0020'),
                                       ('Event245', 'Dm_Kokiri_0090'), ('Event3', 'Dm_Kokiri_0140'),
                                       ('Event215', 'Dm_Kokiri_0158'), ('Event216', 'Dm_Kokiri_0160'),
                                       ('Event42', 'Dm_LakeHrl_0020'), ('Event16', 'Dm_ZoraFountain_0020')),
    'DoorOfTime': (('Event13', 'Dm_HrlField_0060'), ('Event95', 'Dm_SageRoom_0000'),
                   ('Event17', 'Dm_TimeTemple_0010'), ('Event159', 'Dm_TimeTemple_0020'),
                   ('Event94', 'Dm_TimeTemple_0040')),
    'DreamBossStage': (('Event48', 'Dm_InsideGanonCastle_BossOut'),),
    'DreamBossStage.110': (('Event48', 'Dm_InsideGanonCastle_BossOut'),),
    'EscapeFromCrumblingGanonCastle': (('Event161', 'Dm_FinalBattle_0002'),),
    'Get_Epona': (('Event194', 'Dm_HrlField_0070'), ('Event195', 'Dm_HrlField_0071'),
                  ('Event196', 'Dm_HrlField_0072'), ('Event228', 'Dm_HrlField_0073')),
    'Get_StoneOfFire': (('Event6', 'Dm_DodongoCave_BossIn'), ('Event7', 'Dm_DodongoCave_BossOut'),
                        ('Event228', 'Dm_DodongoCave_BossOut'), ('Event141', 'Dm_Goron_0020')),
    'Get_StoneOfForest': (('Event6', 'Dm_Deku_BossIn'), ('Event78', 'Dm_Deku_BossOut'),
                          ('Event80', 'Dm_Deku_BossOut')),
    'Get_StoneOfWater': (('Event22', 'Dm_InsideJabu_Jabu_0010'), ('Event82', 'Dm_InsideJabu_Jabu_BossIn'),
                         ('Event285', 'Dm_InsideJabu_Jabu_BossOut'),
                         ('Event358', 'Dm_InsideJabu_Jabu_BossOut'), ('Event0', 'Dm_ZoraFountain_0010')),
    'Goto_HyruleCastle': (('Event216', 'Dm_HrlCastle_0030'), ('Event34', 'Dm_HrlCastle_0060'),
                          ('Event59', 'Dm_HrlField_0005'), ('Event43', 'Dm_Kokiri_0150')),
    'Meet_DekuTree': (('Event3', 'Dm_Kokiri_0070'),),
    'Npc_Kaepora_DeathMountainTrail': (('Event5', 'Dm_DeathMtTrail_0030'),),
    'OpeningEvent': (('Event5', 'Dm_Kokiri_0030'),),
    'SageOfFire': (('Event2', 'Dm_FireTemple_0000'), ('Event315', 'Dm_FireTemple_BossIn'),
                   ('Event99', 'Dm_FireTemple_BossOut'), ('Event345', 'Dm_FireTemple_BossOut')),
    'SageOfForest': (('Event10', 'Dm_ForestTemple_BossIn'), ('Event9', 'Dm_ForestTemple_BossOut'),
                     ('Event184', 'Dm_ForestTemple_BossOut')),
    'SageOfShadow': (('Event5', 'Dm_ShadowTemple_BossIn'), ('Event0', 'Dm_ShadowTemple_BossOut'),
                     ('Event9', 'Dm_ShadowTemple_BossOut')),
    'SageOfSpirit': (('Event20', 'Dm_DesertColossus_0020'), ('Event1', 'Dm_DesertColossus_0030'),
                     ('Event107', 'Dm_SpiritTemple_0010'), ('Event5', 'Dm_SpiritTemple_0020'),
                     ('Event7', 'Dm_SpiritTemple_0030'), ('Event6', 'Dm_SpiritTemple_BossIn'),
                     ('Event8', 'Dm_SpiritTemple_BossOut'), ('Event467', 'Dm_SpiritTemple_BossOut'),
                     ('Event421', 'Dm_TimeTemple_0086'), ('Event305', 'Dm_TimeTemple_0086'),
                     ('Event304', 'Dm_TimeTemple_0087')),
    'SageOfWater': (('Event8', 'Dm_WaterTemple_0010'), ('Event17', 'Dm_WaterTemple_BossIn'),
                    ('Event18', 'Dm_WaterTemple_BossOut'), ('Event85', 'Dm_WaterTemple_BossOut')),
}


def flow_path(name):
    return FLOWS + name + '.bfevfl.zs'


def site_flows(enabled):
    """Flows changed by the option (empty when off)."""
    return tuple(sorted(SITES)) if enabled else ()


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


def scene_only(item, timeline):
    """Whether a timeline item acts only inside its scene (:data:`SWORD_IN_HAND`, demo actor warps)."""
    action = item.actor_action.v.v
    params = dict(item.params.data) if item.params is not None and item.params.data else {}
    if action in SCENE_ONLY_WARPS and item.actor.v.identifier.name.startswith(SCENE_ACTOR_PREFIX):
        return True
    if action == SWORD_IN_HAND[0] and params == SWORD_IN_HAND[1]:
        # A clip: over at its end, at the latest with the scene.
        end = getattr(item, 'start_time', -1.0) + getattr(item, 'duration', -1.0)
        return getattr(item, 'duration', -1.0) > 0 and end <= timeline.duration
    return False


def timeline_actions(read_flow, row):
    """{actor.action} run by the timeline of an event row and its sub-timelines (those
    acting only inside the scene left out, :func:`scene_only`)."""
    from oot_rando.patching.event_patch import _flow
    found = set()
    files = [row['TimelineFileName']] + list(row.get('SubTimelineNames') or [])
    for name in files:
        stem = name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        raw = read_flow(stem)
        if raw is None:
            continue
        timeline = _flow(raw).timeline
        if timeline is None:
            continue
        for item in list(timeline.clips) + list(timeline.oneshots):
            if not scene_only(item, timeline):
                found.add(str(item.actor.v.identifier) + '.' + item.actor_action.v.v)
    return found


def _actor_key(identifier):
    """The flow's name of a timeline actor (``SoundSystemActor[0]`` -> ``SoundSystemActor``)."""
    sub = identifier.sub_name
    return identifier.name if not sub or sub.isdigit() else f'{identifier.name}[{sub}]'


def timeline_replays(read_flow, row):
    """((actor, action, params or None), ...): the :data:`REPLAYED` actions of the timeline of
    ``row`` and its sub-timelines, in time order, the last one of each actor and action."""
    from oot_rando.patching.event_patch import _flow
    found = {}
    files = [row['TimelineFileName']] + list(row.get('SubTimelineNames') or [])
    for name in files:
        raw = read_flow(name.rsplit('/', 1)[-1].rsplit('.', 1)[0])
        timeline = _flow(raw).timeline if raw is not None else None
        for item in list(timeline.clips) + list(timeline.oneshots) if timeline is not None else ():
            action = item.actor_action.v.v
            if action not in REPLAYED:
                continue
            params = dict(item.params.data) if item.params is not None and item.params.data else {}
            if set(params) != set(REPLAYED[action]):
                raise ValueError(f'Unexpected {action} parameters: ' + row['__RowId'])
            when = getattr(item, 'start_time', None)
            if when is None:
                when = getattr(item, 'time', 0.0)
            key = (_actor_key(item.actor.v.identifier), action)
            if key not in found or when >= found[key][0]:
                found[key] = (when, {k: params[k] for k in REPLAYED[action]} or None)
    return tuple((actor, action, params) for (actor, action), (_, params)
                 in sorted(found.items(), key=lambda f: (f[1][0], f[0])))


def scene_replays(read_flow, rows, sites=None):
    """{scene: replays} for the dropped scenes that have some (:data:`REPLAYS` format)."""
    by_row = {row['__RowId']: row for row in rows}
    scenes = {scene for found in (SITES if sites is None else sites).values() for _, scene in found}
    replays = {scene: timeline_replays(read_flow, by_row[scene]) for scene in sorted(scenes)}
    return {scene: found for scene, found in replays.items() if found}


def scene_reason(name, row, actions, bools):
    """Why a pure timeline is kept (None: it may be dropped)."""
    from oot_rando.patching.soul_adapter import murmur3
    if name.startswith(EXCLUDED_FAMILIES):
        return 'title, staff roll or ending'
    state = sorted({a.rsplit('.', 1)[1] for a in actions if a.rsplit('.', 1)[1] in STATE_ACTIONS})
    if state:
        return 'acts on the world: ' + ', '.join(state)
    if murmur3('HavePlayedEvent.' + name) not in bools:
        return 'no saved HavePlayedEvent'
    return None


def _black_before(chart, event):
    """The fade-out right before ``event`` (walking back over neutral events), 'entry' when
    nothing shown comes before it in its event, or None."""
    from oot_rando.patching.qol_patches import _predecessors
    current = event
    for _ in range(6):
        links = _predecessors(chart, current)
        if len(links) == 1 and links[0][1] == 'entry':
            return 'entry'
        if len(links) != 1 or links[0][1] != 'nxt':
            return None
        current = links[0][0]
        action = _action(current)
        if action is None:
            return None
        if action == ('UISystemActor', 'EventEventFadeOut'):
            return current
        if action[1] not in NEUTRAL_BEFORE:
            return None
    return None


def _leads_to(chart, event, families):
    """Whether the flow can go from ``event`` to a transition to one of ``families``."""
    seen, todo = set(), _successors(event)
    while todo:
        current = todo.pop()
        if current.name in seen:
            continue
        seen.add(current.name)
        if (_action(current) == ('EventSystemActor', 'EventTransition')
                and str(_params(current).get('EventName', '')).startswith(families)):
            return True
        todo.extend(_successors(current))
    return False


def _query(event):
    from evfl.event import SwitchEvent
    return event.data.actor_query.v.v if isinstance(event.data, SwitchEvent) else None


def _until_next_scene(start_events):
    """Events run from ``start_events`` up to the next scene transition (included)."""
    seen, todo, found = set(), list(start_events), []
    while todo:
        current = todo.pop()
        if current.name in seen:
            continue
        seen.add(current.name)
        found.append(current)
        if _action(current) != ('EventSystemActor', 'EventTransition'):
            todo.extend(_successors(current))
    return found


def after_queries(chart, event):
    """(own, shared): the skip queries ("was the last scene skipped?") asked after ``event``
    before the next scene; own = reached only through ``event`` (they answer about it),
    shared = also reached another way."""
    from oot_rando.patching.qol_patches import _predecessors
    region = _until_next_scene(_successors(event))
    owned, changed = {event.name}, True
    while changed:
        changed = False
        for current in region:
            if current.name not in owned and all(
                    getattr(owner, 'name', None) in owned and kind != 'entry'
                    for owner, kind, _ in _predecessors(chart, current)):
                owned.add(current.name)
                changed = True
    queries = [e for e in region if _query(e) == QUERY]
    return ([q for q in queries if q.name in owned], [q for q in queries if q.name not in owned])


def site_plan(chart, event, scene):
    """(fade-in params or None, reason the site is kept or None)."""
    if _leads_to(chart, event, EXCLUDED_FAMILIES):
        return None, 'leads to the ending'
    if after_queries(chart, event)[1]:
        return None, 'skip query shared with other paths'
    fade_out = _black_before(chart, event)
    if fade_out is None:
        return None, None
    if fade_out == 'entry':
        # First thing its event shows: maybe under the loading screen (new game).
        return None, 'starts its event'
    if _params(event).get('FadeInTypeEventEnd', 0) == 0:
        return None, 'black screen before, no fade-in after'
    return dict(FADE_IN, Color=_params(fade_out).get('Color', 0)), None


def scan(read_flow, flow_names, rows, gamedata_raw):
    """(sites, kept): the drop table (:data:`SITES` format) and {scene or flow/event: reason}."""
    from evfl.event import ActionEvent
    from oot_rando.formats import byml_codec
    from oot_rando.patching.event_patch import _flow
    bools = {int(e['Hash']) for e in byml_codec.load(gamedata_raw)['root']['Data']['Bool']}
    by_row = {row['__RowId']: row for row in rows}
    reasons, sites, kept = {}, {}, {}
    for flow in sorted(flow_names):
        raw = read_flow(flow)
        chart = _flow(raw).flowchart if raw is not None else None
        if chart is None:
            continue
        for event in chart.events:
            if not isinstance(event.data, ActionEvent) or _action(event) != ('EventSystemActor', 'EventTransition'):
                continue
            scene = _params(event).get('EventName')
            row = by_row.get(scene)
            if row is None or not row.get('TimelineFileName'):
                continue
            if scene not in reasons:
                reasons[scene] = scene_reason(scene, row, timeline_actions(read_flow, row), bools)
            if reasons[scene] is not None:
                kept[scene] = reasons[scene]
                continue
            _, why = site_plan(chart, event, scene)
            if why is not None:
                kept[flow + '/' + event.name] = why
                continue
            sites.setdefault(flow, []).append((event.name, scene))
    return {flow: tuple(sorted(found, key=lambda s: s[1])) for flow, found in sites.items()}, kept


def _system_actor(editor, identifier):
    """``identifier`` (a system actor) of the flow, added with the system parameters."""
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier
    from evfl.container import Container
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
    if not any(str(a.identifier) == identifier for a in editor.chart.actors):
        owner = Actor()
        owner.identifier = ActorIdentifier(identifier)
        owner.concurrent_clips = 1
        owner.params = Container()
        owner.params.data = dict(GAMEDATA_ACTOR_PARAMS)
        editor.chart.actors.append(owner)


def drop_timelines(raw, flow, sites=None):
    """Returns (bytes, report): ``flow``'s listed timeline transitions no longer play.

    report = [{'event', 'scene', 'chain'}] (a site no event leads to any more is left out)."""
    from oot_rando.patching.progressive import FlowEditor, link
    from oot_rando.patching.qol_patches import _predecessors
    from oot_rando.patching.skip_auto import _redirect
    from evfl.util import make_index
    sites = SITES[flow] if sites is None else sites
    editor = FlowEditor(raw, flow)
    chart = editor.chart
    events = {e.name: e for e in chart.events}
    report, plans = [], []
    # Planned on the flow as given, before any site is replaced.
    for name, scene in sites:
        event = events.get(name)
        if (event is None or _action(event) != ('EventSystemActor', 'EventTransition')
                or _params(event).get('EventName') != scene):
            raise ValueError(f'Timeline site changed: {flow}/{name} ({scene})')
        if PREFIX + name + '_Played' in events:
            raise ValueError(f'Timeline already dropped: {flow}/{name}')
        if not _predecessors(chart, event):
            continue   # already bypassed by another patch (Kaepora's first field scene: owl_advice)
        fade_in, why = site_plan(chart, event, scene)
        if why is not None:
            raise ValueError(f'Timeline site no longer droppable ({why}): {flow}/{name}')
        plans.append((name, scene, event, fade_in, after_queries(chart, event)[0]))
    for name, scene, event, fade_in, queries in plans:
        chain = [editor.action(PREFIX + name + '_Played', 'GameDataActor', 'EventTriggerSetGameDataBool',
                               {'GameDataName': 'HavePlayedEvent.' + scene, 'Value': True, 'Index': -1})]
        for index, (actor, action, params) in enumerate(REPLAYS.get(scene, ())):
            if actor.endswith(SYSTEM_SUFFIXES):
                _system_actor(editor, actor)
            chain.append(editor.action(f'{PREFIX}{name}_Replay{index}', actor, action,
                                       dict(params) if params is not None else None))
        if fade_in is not None:
            chain.append(editor.action(PREFIX + name + '_FadeIn', 'UISystemActor', 'EventEventFadeIn', fade_in))
        following = event.data.nxt.v if event.data.nxt is not None else None
        for current, nxt in zip(chain, chain[1:] + [following]):
            link(current, nxt)
        for owner, kind, key in _predecessors(chart, event):
            if kind == 'nxt':
                owner.data.nxt = make_index(chain[0])
            elif kind == 'case':
                owner.data.cases[key] = make_index(chain[0])
            elif kind == 'fork':
                owner.data.forks[key] = make_index(chain[0])
            else:
                owner.main_event = make_index(chain[0])
        events.update({e.name: e for e in chain})
        entry = {'event': name, 'scene': scene, 'chain': [e.name for e in chain]}
        # Asked after the scene, "was it skipped?" has no answer about it any more: the
        # skipped case, made for a scene cut short (as skip_auto).
        for query in queries:
            case = query.data.cases.get(0)
            _redirect(chart, query, case.v if case is not None else None, query.name)
        if queries:
            entry['queries'] = sorted(q.name for q in queries)
        report.append(entry)
    result, _ = editor.write('Timeline skip')
    if not dropped(result, flow, sites):
        raise ValueError('Timeline skip not written: ' + flow)
    return result, report


def dropped(raw, flow, sites=None):
    """Whether no entry of ``raw`` reaches a listed transition any more and each reached one is replaced."""
    from oot_rando.patching.event_patch import _flow
    sites = SITES[flow] if sites is None else sites
    chart = _flow(raw).flowchart
    events = {e.name: e for e in chart.events}
    seen, todo = set(), [e.main_event.v for e in chart.entry_points if e.main_event.v is not None]
    while todo:
        current = todo.pop()
        if current.name in seen:
            continue
        seen.add(current.name)
        todo.extend(_successors(current))
    for name, scene in sites:
        played = events.get(PREFIX + name + '_Played')
        if name in seen:
            return False
        if played is None:
            continue   # bypassed before the drop (see drop_timelines)
        if _params(played).get('GameDataName') != 'HavePlayedEvent.' + scene:
            return False
        if any(_query(e) == QUERY for e in _until_next_scene([played])):
            return False
    return True
