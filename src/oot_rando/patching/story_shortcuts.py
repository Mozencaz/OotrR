"""Explicit story/reward shortcuts built from our game's event resources.

Reward actors/markers come from already patched flows. Native quest/equipment
and map-load continuations are reused rather than replaced with guessed flags.
"""
from evfl.event import ActionEvent, SubFlowEvent, SwitchEvent
from evfl.util import make_index

from oot_rando.patching.cinematic_tools import SceneEditor, path, give, reward
from oot_rando.patching.event_patch import _flow
from oot_rando.patching.song_lessons import _action, _params, _reach, _transitions
from oot_rando.patching.progressive import link

OPTIONS = ('skip_opening', 'skip_tutorials', 'skip_first_pickup_text',
           'skip_story_sequences', 'skip_dungeon_endings', 'skip_fairy_sequences')
REWARDS = (
    ('Queen Gohma', 'Dm_Kokiri_0130', 'Event22', 'BossArea_WarpIn'),
    ('King Dodongo', 'Dm_DeathMtTrail_0025', 'Event26', 'Get_StoneOfFire_EscapeDungeon'),
    ('Barinade', 'Dm_ZoraFountain_0030', 'Event3', 'Get_StoneOfWater_LeaveFromJabuJabuBelly'),
    ('Phantom Ganon', 'Dm_Awake_Forest_Get', 'Event13', 'ForestTemple_SageOfForest_EscapeFromTemple'),
    ('Volvagia', 'Dm_Awake_Fire_Get', 'Event13', 'SageOfFire_ClearEvent'),
    ('Morpha', 'Dm_Awake_Water_Get', 'Event13', 'SageOfWater_ClearEvent'),
    ('Bongo Bongo', 'Dm_Awake_Shadow_Get', 'Event3', 'ShadowTemple_BossArea_WarpIn'),
    ('Twinrova', 'Dm_Awake_Spirit_Get', 'Event14', 'SageOfSpirit_Clear'),
)
FAIRIES = ('Dm_FairyFountain_Din', 'Dm_FairyFountain_Power', 'Dm_FairyFountain_Wisdom',
           'Dm_FairyFountain_Frore', 'Dm_FairyFountain_Nayru', 'Dm_FairyFountain_Courage')
STORY_FLOWS = ('Meet_DekuTree', 'Goto_HyruleCastle', 'DoorOfTime', 'AllSage',
               'Dm_SY_BancChangeArrive', 'Get_StoneOfFire', 'Get_StoneOfWater',
               'SageOfFire', 'SageOfWater', 'Npc_Kokiri_Mido_Child')


def enabled(options):
    return any(options.get(k) for k in OPTIONS) or options.get('skip_song_lessons', False)


def state(editor, raw):
    """Ordered saved effects in the audited small reward scenes (not a general reducer)."""
    if raw is None:
        return []
    chart = _flow(raw).flowchart
    if chart is None:
        return []
    root = next(e for e in chart.entry_points if e.name == 'EntryPoint0')
    reached = {e.name for e in _reach(chart, [root.main_event.v])}
    result = []
    for e in chart.events:
        action = _action(e)
        if e.name in reached and action and action[0] in ('GameDataActor', 'ChallengeSystemActor'):
            if action[1] in ('EventTriggerSetGameDataBool', 'EventTriggerSetGameDataInt',
                             'EventTriggerAddOrSubGameDataInt', 'EventExecuteProgressChallengeStep'):
                if str(_params(e).get('GameDataName', '')).startswith(('IsGet.', 'HavePlayedEvent.')):
                    continue
                result.append(editor.clone_action(e))
    return result


def played(editor, scene, read, following=None, include_state=True):
    steps = [editor.flag('HavePlayedEvent.' + scene)]
    if include_state:
        steps += state(editor, read(path(scene)))
    # The existing timeline analysis lists world effects which must survive a cut.
    from oot_rando.patching.timeline_skip import REPLAYS
    for actor, action, params in REPLAYS.get(scene, ()):
        steps.append(editor.act('TimelineEffect', actor, action, params))
    return editor.chain(steps, following)


def cut(editor, scene, read, item=None, include_state=True):
    changed = []
    for transition in _transitions(editor.chart, scene):
        # A previous timeline patch may already have bypassed this transition.
        from oot_rando.patching.qol_patches import _predecessors
        if not _predecessors(editor.chart, transition):
            continue
        following = transition.data.nxt.v
        # The removed scene can own the fade back from a preceding cinematic or
        # loading transition. Keep an explicit short fade on the replacement path.
        following = editor.chain([editor.fade()], following)
        if item is not None:
            following = give(editor, item, following)
        first = played(editor, scene, read, following, include_state)
        editor.replace(transition, first)
        changed.append(transition.name)
    return changed


def story(raw, name, read, current):
    editor = SceneEditor(raw, name, [read(path('Dm_SY_GetInEvent')), read(path('OpeningEvent'))])
    report = {}
    if name == 'Meet_DekuTree':
        # Skip the entire caller, including its camera, fades and music stop.
        # The tree's NpcKokiriDekuTreeParam.OpendMouth_Child reads the saved
        # mouth flag: no cinematic animation or guessed actor warp is needed.
        scene = SceneEditor(read(path('Dm_Kokiri_0075')), 'Dm_Kokiri_0075')
        effects = [editor.clone_action(scene.events[k]) for k in ('Event43', 'Event39', 'Event40')]
        first = editor.chain(effects + [editor.fade()])
        first = editor.chain([editor.flag('HavePlayedEvent.' + s)
                              for s in ('Dm_Kokiri_0070', 'Dm_Kokiri_0075')], first)
        link(editor.events['Event7'], first)
        report['deku_tree'] = ['Dm_Kokiri_0070', 'Dm_Kokiri_0075']
    elif name == 'Goto_HyruleCastle':
        # The caller already displays the Cucco. Replace everything after that
        # display, including the minute-long native wake-up/run, under black.
        talon = SceneEditor(read(path('Dm_HrlCastle_0020')), 'Dm_HrlCastle_0020')
        effects = [editor.clone_action(talon.events[k]) for k in
                   ('Event42', 'Event69', 'Event121', 'Event141', 'Event133', 'Event134')]
        hide = editor.act('HideTalon', 'Npc_Hylia_Talon_Child', 'EventGoOffstageForUser',
                          _params(talon.events['Event92']))
        # HyruleCastle_Prefab_19e8 wires this flag to Talon's Logic_Delete.
        # Hide first, and make no further actor requests after setting it.
        first = editor.chain([editor.act('FadeOut', 'UISystemActor', 'EventEventFadeOut',
                                         {'Color': 0, 'Length': 1, 'IsNoPlayAnime': False,
                                          'IsWaitEnd': True})] + effects + [hide,
                              editor.flag('HavePlayedEvent.Dm_HrlCastle_0020'), editor.fade()])
        editor.replace(editor.events['Event84'], first)
        report['talon_wake_up'] = 'Dm_HrlCastle_0020'
        # Keep the bridge's environment write and transfer to Hyrule Field.
        item = reward(current(path('Dm_Kokiri_0155')), 'Event68')
        first = give(editor, item, editor.events['Event218'])
        first = editor.chain([editor.flag('HavePlayedEvent.Dm_Kokiri_0150'),
                              editor.flag('HavePlayedEvent.Dm_Kokiri_0155')], first)
        editor.entries['KokiriForest_ArriveLostWood'].main_event = make_index(first)
        report['saria'] = item
        # Zelda's questions here only select exposition/repetition, not a
        # purchase or a gameplay choice. Its other entries write parameterized
        # conversation counters; do not flatten those into saved game effects.
        item = reward(current(path('Dm_HrlCastle_0050')), 'Event59')
        for scene in ('Dm_HrlCastle_0030', 'Dm_HrlCastle_0035', 'Dm_HrlCastle_0045'):
            cut(editor, scene, read)
        report['zelda_letter'] = item
        report['zelda'] = cut(editor, 'Dm_HrlCastle_0050', read, item, include_state=False)
        cut(editor, 'Dm_HrlCastle_0060', read)
    elif name == 'Npc_Kokiri_Mido_Child':
        # Dm_Kokiri_0145 owns presentation only. Keep its caller's saved effects
        # and native Mido/player/Navi repositioning, then omit Navi's extra talk.
        first = editor.chain([editor.act('FadeOut', 'UISystemActor', 'EventEventFadeOut',
                                         {'Color': 0, 'Length': 1, 'IsNoPlayAnime': False,
                                          'IsWaitEnd': True}),
                              editor.flag('HavePlayedEvent.Dm_Kokiri_0145')], editor.events['Event29'])
        editor.entries['KokiriForest_Get_StoneOfForest_Completed_Event'].main_event = make_index(first)
        link(editor.events['Event113'], editor.chain([editor.fade()], editor.events['Event102']))
        report['after_deku_tree'] = 'Dm_Kokiri_0145'
    elif name == 'DoorOfTime':
        # Preserve the first-draw condition, and reuse the later era-change event.
        draw = editor.entries['DoorOfTime_Draw'].main_event.v
        if not isinstance(draw.data, SwitchEvent) or _params(draw).get('EventName') != 'Dm_TimeTemple_0040':
            raise ValueError('Unexpected first Master Sword draw')
        later = draw.data.cases[0].v
        if _params(later).get('EventName') != 'Market_Child_Field_ChildToAdult':
            raise ValueError('Unexpected later sword draw')
        item = reward(current(path('Dm_SageRoom_0005')), 'Event48')
        # Native grant (which the Master Sword shuffle can replace) and its hooks.
        sword = editor.events['Event115']
        grant = reward(raw, 'Event115')
        # Complete the native first-adult quest requests without playing Sheik's talk.
        all_sage = _flow(read(path('AllSage'))).flowchart
        tail = []
        for key in ('Event74', 'Event153', 'Event1', 'Event18', 'Event19'):
            native = next(e for e in all_sage.events if e.name == key)
            tail.append(editor.clone_action(native))
        # Door completion may be guarded by an earlier progression patch: preserve it
        # by a call to a new local tail containing the native guarded continuation.
        recovery = editor.events['Event102']
        after_recovery = recovery.data.nxt.v
        # That branch ends before the later draw; append it with a local entry so
        # a guarded terminal does not swallow the era change.
        from evfl.entry_point import EntryPoint
        complete = EntryPoint('RandoCinema_DrawCompletion')
        complete.main_event = make_index(after_recovery)
        editor.chart.entry_points.append(complete)
        completion = editor.call('CompleteDoor', '', complete.name)
        # Retain Rauru's native recovery, without Recovery's presentation waits.
        healing = [editor.clone_action(editor.events[k]) for k in ('Event70', 'Event74', 'Event72', 'Event71')]
        editor.chain(tail + healing + [completion], later)
        following = give(editor, item, tail[0])
        if grant['actor'] == 'Weapon_Sword_Master':
            master = editor.clone_action(sword)
            if grant.get('flag'):
                following = editor.chain([editor.flag(grant['flag'])], following)
            link(master, following)
            first = master
        else:
            first = give(editor, grant, following)
        flags = ['Dm_TimeTemple_0030', 'Dm_TimeTemple_0040', 'Dm_SageRoom_0000', 'Dm_SageRoom_0005',
                 'Dm_TimeTemple_0050', 'Dm_TimeTemple_0055']
        first = editor.chain([editor.flag('HavePlayedEvent.' + s) for s in flags], first)
        draw.data.cases[1] = make_index(first)
        # The escape becomes its final quest request; weather setup and talk vanish.
        step = editor.clone_action(editor.events['Event12'])
        if _params(step).get('StepName') != 'Step04':
            raise ValueError('Unexpected Zelda escape completion step')
        # HyruleField_Child_Prefab_91f9 creates the moat pickup trigger only
        # while DoorOfTime IsEqual Step04. Step05 belongs to the pickup's own
        # post-lesson continuation, not to the escape shortcut.
        first = played(editor, 'Dm_HrlField_0060', read, editor.chain([step, editor.fade()]), False)
        editor.entries['DoorOfTime_Escape'].main_event = make_index(first)
        report.update(rauru=item, master=grant, escape='Step04')
        # Impa's farewell is after the song and the native map transfer.
        # Keep both (and the lesson when its separate option is disabled).
        report['impa_farewell'] = cut(editor, 'Dm_HrlField_0020', read)
    elif name == 'AllSage':
        item = reward(current(path('Dm_TimeTemple_0130')), 'Event85')
        for entry in ('Market_Adult_Field_GetArrowLight', 'GetArrowLight_OcarinaBackTimeTemple'):
            if entry not in editor.entries:
                raise ValueError('Missing Light Arrows entry: ' + entry)
            tail = editor.events['Event10']
            first = give(editor, item, tail)
            scenes = ('Dm_TimeTemple_0090', 'Dm_TimeTemple_0095', 'Dm_TimeTemple_0110',
                      'Dm_TimeTemple_0115', 'Dm_TimeTemple_0125', 'Dm_TimeTemple_0130', 'Dm_TimeTemple_0135')
            first = editor.chain([editor.flag('HavePlayedEvent.' + s) for s in scenes], first)
            first = editor.chain([editor.clone_action(editor.events['Event165'])], first)
            editor.entries[entry].main_event = make_index(first)
        cut(editor, 'Dm_SageRoom_0010', read)
        report['light_arrows'] = item
    elif name == 'Dm_SY_BancChangeArrive':
        # Keep both native loads: ordinary village -> flashback entry -> burnt village.
        # The native preload targets intentionally differ from the current map.
        tail = editor.events['Event329']
        lesson_start = editor.events.get('RandoLesson_Event68_Played')
        if lesson_start is not None:
            # Give Nocturne while this map/player is still active, then keep
            # both native transfers. The alternate-village boot must not give it
            # again or open an item event under its loading screen.
            item = reward(current(path('Dm_MelodyGet_Shadow')), 'Event21')
            editor.replace(lesson_start, editor.events['Event280'])
            first = give(editor, item, tail)
            first = editor.chain(state(editor, read(path('Dm_MelodyGet_Shadow'))), first)
            first = editor.chain([editor.flag('HavePlayedEvent.Dm_MelodyGet_Shadow')], first)
            tail = first
            report['nocturne_before_load'] = item
        short = played(editor, 'Dm_Kakariko_0030', read,
                       editor.chain([editor.flag('HavePlayedEvent.Dm_Kakariko_0040')], tail), False)
        editor.replace(editor.events['Event37'], short)
        cut(editor, 'Dm_Kakariko_0040', read)
        report['burning'] = ['Event329', 'Event379']
    elif name == 'Get_StoneOfFire':
        # Darunia's approval and bracelet ceremony, not the prerequisite song check.
        if _action(editor.events['Event290']) != ('UISystemActor', 'EventEventFadeOut'):
            raise ValueError('Unexpected successful Darunia song branch')
        approval = played(editor, 'Dm_Goron_0025', read, editor.events['Event39'])
        resume = editor.act('DaruniaMusic', 'SoundSystemActor', 'EventTriggerStartInGameBgm',
                            {'IsFadeIn': False, 'WithPlayableEvent': False, 'ResumeDelay': 0})
        editor.replace(editor.events['Event290'], editor.chain([resume], approval))
        report['dance'] = 'Dm_Goron_0025'
        report['bracelet'] = cut(editor, 'Dm_Goron_0030', read,
                                reward(current(path('Dm_Goron_0030')), 'Event127'))
    elif name == 'Get_StoneOfWater':
        from evfl.entry_point import EntryPoint
        from oot_rando.formats.inspect_resources import Byml
        from math import degrees
        from struct import pack, unpack
        scene = SceneEditor(read(path('Dm_Zora_0010')), 'Dm_Zora_0010')
        # The king's linked Action2 anchor is his post-letter position. Read it
        # from the map rather than approximating the root-motion endpoint.
        actors = Byml(read('Banc/ZoraDomain/ZoraDomain_Child_Static.bcett.byml.zs')).root['Actors']
        king = next(a for a in actors if a['Gyaml'] == 'Npc_Zora_KingZora_child')
        refs = {ref['Dst'] for ref in king['Links']}
        anchor = next(a for a in actors if a['Hash'] in refs and a['Gyaml'] == 'AnchorAction2')
        warp_params = dict(_params(scene.events['Event138']), Position=anchor['Translate'],
                           YAngle=unpack('<f', pack('<f', degrees(anchor['Rotate'][1])))[0],
                           ClothWarpMode=3)
        warp = editor.act('MoveKingZora', 'Npc_Zora_KingZora_child',
                          'EventWarpToTargetPosAndRot', warp_params)
        # Reuse the current guarded Step07/UI tail as a local call, so the fade
        # runs even when a quest guard ends that continuation early.
        complete = EntryPoint('RandoCinema_KingZoraCompletion')
        complete.main_event = make_index(editor.events['Event231'].data.nxt.v)
        editor.chart.entry_points.append(complete)
        first = editor.chain([
            editor.act('FadeOut', 'UISystemActor', 'EventEventFadeOut',
                       {'Color': 0, 'Length': 1, 'IsNoPlayAnime': False, 'IsWaitEnd': True}),
            editor.clone_action(editor.events['Event245']),
            editor.clone_action(editor.events['Event231']), warp,
            editor.clone_action(scene.events['Event55']),
            editor.clone_action(scene.events['Event58']),
            editor.flag('HavePlayedEvent.Dm_Zora_0010'),
            editor.call('CompleteKingZora', '', complete.name), editor.fade()])
        editor.replace(editor.events['Event66'], first)
        report['king_zora_letter'] = 'Dm_Zora_0010'
        # Ruto discovers the sapphire: no reward here. The caller retains the
        # discovery flag and subsequent miniboss/stone-carrying gameplay.
        report['ruto_discovery'] = cut(editor, 'Dm_InsideJabu_Jabu_0020', read)
    elif name == 'SageOfFire':
        # Darunia's meeting creates the room's chain. The native continuation
        # advances the quest and removes the scene actor.
        cut(editor, 'Dm_FireTemple_0000', read)
        report['darunia_meeting'] = cut(editor, 'Dm_FireTemple_0010', read)
    elif name == 'SageOfWater':
        # All equipment queries in this scene choose Navi's presentation only.
        # Water level and Ruto's disappearance are owned by the caller.
        cut(editor, 'Dm_WaterTemple_0010', read)
        report['ruto_meeting'] = cut(editor, 'Dm_WaterTemple_0015', read)
    return editor.finish(report)


def fairy(raw, name, read):
    editor = SceneEditor(raw, name, [read(path('Dm_SY_GetInEvent'))])
    # Only the paid gift path is shortened. The talk, payment, lack-of-money and
    # already-collected/recovery paths keep their native routing and conditions.
    gifts = [e for e in editor.chart.events if isinstance(e.data, SubFlowEvent)
             and not e.data.res_flowchart_name and e.data.entry_point_name == name]
    if len(gifts) != 1 or 'C15-01' not in editor.entries:
        raise ValueError('Unsupported fairy gift: ' + name)
    gift = gifts[0]
    for event in list(editor.chart.events):
        if (isinstance(event.data, SubFlowEvent) and event.data.res_flowchart_name in ('', 'Dm_FairyFountain_Din')
                and event.data.entry_point_name == 'GreatFairy_Appear'):
            editor.replace(event, editor.chain([editor.act('FairyWait', 'EventSystemActor', 'EventWait',
                                                        {'Frames': 0, 'IsWaitEnd': True})], event.data.nxt.v))
        elif (isinstance(event.data, SubFlowEvent) and event.data.res_flowchart_name in ('', 'Dm_FairyFountain_Din')
              and event.data.entry_point_name == 'GreatFairy_Disappear'):
            editor.replace(event, editor.chain([editor.call('FairyHeal', 'TriForcePoint', 'Recover')], event.data.nxt.v))
    body = _reach(editor.chart, [editor.entries[name].main_event.v])
    release = next((e for e in body if _action(e) == ('SoundSystemActor', 'EventSoundReleaseDucking')), None)
    steps = ([editor.clone_action(release)] if release else []) + [editor.call('FairyGift', '', 'C15-01')]
    editor.replace(gift, editor.chain(steps, gift.data.nxt.v))
    # No unbalanced skip state or music stop is entered on the short paid path.
    from oot_rando.patching.qol_patches import _predecessors
    for event in list(editor.chart.events):
        if _action(event) in (('EventSystemActor', 'EventTriggerSkipAcceptStart'),
                              ('SoundSystemActor', 'EventTriggerStopInGameBgm')) and _predecessors(editor.chart, event):
            editor.replace(event, editor.chain([editor.act('NoFairyPresentation', 'EventSystemActor', 'EventWait',
                                                         {'Frames': 0, 'IsWaitEnd': True})], event.data.nxt.v))
    return editor.finish({'gift': gift.name, 'native_give': 'C15-01', 'heal': True})


def endings(raw, read, current):
    editor = SceneEditor(raw, 'Dm_SY_BancChange_EscapeDungeon',
                         [read(path('Dm_SY_GetInEvent')), read(path('OpeningEvent'))])
    report = {}
    for location, scene, event, entry_name in REWARDS:
        item = reward(current(path(scene)), event)
        native = _flow(read(path('Dm_SY_BancChange_EscapeDungeon'))).flowchart
        entry = next(e for e in native.entry_points if e.name == entry_name)
        node = entry.main_event.v
        while not isinstance(node.data, SwitchEvent):
            node = node.data.nxt.v
        if not str(_params(node).get('GameDataName', '')).endswith(('_IsCompleted_Exp', '_IsAfter_EscapeDungeon_Exp')):
            raise ValueError('Unrecognised first-clear guard: ' + entry_name)
        if location == 'Barinade':
            # Ruto's first-clear movie owns its own choice. Replace it with the
            # native repeat-visit warp menu, retaining an accepted-result edge
            # only; the grant happens outside the cinematic player context.
            import copy
            template = editor.events['Event244']
            data = copy.copy(template.data)
            data.cases = {}
            menu = editor._event(editor.unique('JabuWarpChoice'), data, _params(template))
            landing = SceneEditor(read(path('Dm_InsideJabu_Jabu_0050')), 'Dm_InsideJabu_Jabu_0050')
            reserve = editor.clone_action(landing.events['Event90'])
            animation = editor.clone_action(editor.events['Event89'])
            editor.chain([animation, reserve])
            get = give(editor, item, animation)
            first = editor.chain([editor.flag('InsideJabuJabuBelly_WarpPortal')], get)
            data.cases = {k: make_index(first) for k in template.data.cases}
            editor.events[node.name].data.cases[1] = make_index(menu)
            cut(editor, scene, read)
            report[location] = item
            continue
        start = node.data.cases[1].v
        # Walk only first-clear edges up to the first transition. The warp choice
        # has an accepted-result edge only, so cancelling never grants anything.
        todo, edges = [(node, 'case', 1, start)], []
        seen = set()
        while todo:
            owner, kind, key, e = todo.pop()
            if _action(e) == ('EventSystemActor', 'EventTransition'):
                edges.append((owner, kind, key, e)); continue
            if e.name in seen:
                continue
            seen.add(e.name)
            if hasattr(e.data, 'cases'):
                todo += [(e, 'case', k, v.v) for k, v in e.data.cases.items()]
            elif getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is not None:
                todo.append((e, 'nxt', None, e.data.nxt.v))
            else:
                raise ValueError('Unexpected first-clear path: ' + entry_name + '/' + e.name)
        if not edges:
            raise ValueError('First-clear warp missing: ' + entry_name)
        for owner, kind, key, transition in edges:
            owner = editor.events[owner.name]
            following = owner.data.cases[key].v if kind == 'case' else owner.data.nxt.v
            first = give(editor, item, following)
            if kind == 'case': owner.data.cases[key] = make_index(first)
            else: link(owner, first)
        # Retire the later reward scene, but preserve all its state.
        cut(editor, scene, read)
        report[location] = item
    # Other ending movies in this specific sequence have no reward; their
    # timeline side effects are replayed through the existing REPLAYS table.
    presentations = ('Dm_Deku_0010', 'Dm_Kokiri_0080', 'Dm_Kokiri_0095', 'Dm_Kokiri_0090',
                     'Dm_Kokiri_0140', 'Dm_DeathMtTrail_0020', 'Dm_InsideJabu_Jabu_0030',
                     'Dm_Awake_Forest', 'Dm_Awake_Fire', 'Dm_Awake_Water', 'Dm_Awake_Shadow',
                     'Dm_Awake_Spirit', 'Dm_Kakariko_0025', 'Dm_ZoraFountain_0020', 'Dm_LakeHrl_0020',
                     'Dm_DeathMtTrail_0027', 'Dm_DeathMtCrater_0010', 'Dm_Graveyard_0030', 'Dm_DesertColossus_0040',
                     'Dm_Kokiri_0158', 'Dm_Kokiri_0160', 'Dm_Kokiri_0162')
    for scene in presentations:
        # Barinade's interior scene has a second copy of the same check: retire
        # it too, rather than granting again before the exterior scene.
        cut(editor, scene, read)
    stops = {'ForestTemple_SageOfForest_SageRoom': 'ForestTemple_SageOfForest_SageRoom',
             'FireTemple_SageOfFire_SageRoom': 'FireTemple_SageOfFire_SageRoom',
             'SageOfWater_SageRoom': 'SageOfWater_SageRoom',
             'ShadowTemple_SageOfShadow_SageRoom': 'ShadowTemple_Warp_ChamberOfSages',
             'SpiritTemple_SageOfSpirit_SageRoom': 'SpiritTemple_SageOfSpirit_SageRoom',
             'FireTemple_SageOfFire_Kakariko': 'FireTemple_SageOfFire_Kakariko'}
    for e in list(editor.chart.events):
        boot = _params(e).get('BootEventName')
        if _action(e) == ('GameSystemActor', 'EventReserveBancChange') and boot in stops:
            first = editor.chain([editor.call('SkipSageRoom', '', stops[boot])], e.data.nxt.v)
            editor.replace(e, first)
    # Gohma's gift is already moved out of its scene by our older adapter.
    # Retire that old moved grant and its marker/converter chain as well.
    old = editor.events.get('RandoGiftGet')
    if old:
        editor.replace(old, editor.events['Event1'])
    # The forest arrival's camera walk belonged to the retired reward ceremony.
    # Keep the forward-only quest tail and its scene/environment cleanup.
    first = editor.chain([editor.wait_loading(), editor.fade()], editor.events['Event1'])
    first = editor.chain([editor.flag('HavePlayedEvent.' + s) for s in
                          ('Dm_Kokiri_0080', 'Dm_Kokiri_0095', 'Dm_Kokiri_0090',
                           'Dm_Kokiri_0130', 'Dm_Kokiri_0140')], first)
    editor.entries['Warp_Kokiri'].main_event = make_index(first)
    return editor.finish(report)


def extra_song(raw, name, read, current):
    editor = SceneEditor(raw, name, [read(path('Dm_SY_GetInEvent')), read(path('OpeningEvent'))])
    if name == 'DoorOfTime':
        scene = 'Dm_MelodyGet_Time'
        ocarina = reward(current(path(scene)), 'Event70')
        song = reward(current(path(scene)), 'Event4')
        transitions = _transitions(editor.chart, scene)
        if len(transitions) != 1:
            raise ValueError('Unexpected Time lesson trigger')
        transition = transitions[0]
        # Keep the native post-lesson relocation and Step05 request.
        following = editor.chain([editor.call('AfterTimeSong', '', 'Dm_MelodyGet_Time_After')], transition.data.nxt.v)
        following = give(editor, song, following)
        following = give(editor, ocarina, following)
        first = editor.chain([editor.flag('HavePlayedEvent.' + scene)] + state(editor, read(path(scene))), following)
        editor.replace(transition, first)
        # This stop belongs to the lesson only; the field's BGM remains playing.
        editor.replace(editor.events['Event64'], editor.events['Event82'])
        report = {'time_ocarina': ocarina, 'time_song': song}
    else:
        scene = 'Dm_MelodyGet_Spilit'
        item = reward(raw, 'Event17')
        # Unlike the other lessons, this event is started by the map. Use the
        # normal player participation contract, not the cinematic animation set.
        tail = editor.call('MeetSheik', 'AllSage', 'MeetSheik_And_Gone')
        first = give(editor, item, tail)
        first = editor.chain([editor.flag('HavePlayedEvent.' + scene)] + state(editor, read(path(scene))), first)
        steps = [editor.act('PlayerStart', 'Player_Event', 'EventTriggerPlayerEventStartWithDrawn'),
                 editor.act('Participate', 'Player_Event', 'EventTriggerParticipateEvent'),
                 editor.act('Unequip', 'Player_Event', 'EventPlayerUnequip', {'IsWaitEnd': True})]
        editor.entries['EntryPoint0'].main_event = make_index(editor.chain(steps, first))
        report = {'requiem': item}
    return editor.finish(report)


def retire_ruto_display_marker(raw, flag):
    """Ruto shows the sapphire inside Jabu before the boss; that is not a grant.

    Once the actual check moves into the accepted boss warp, this historical
    display alias must no longer announce it to the tracker/Archipelago.
    """
    editor = SceneEditor(raw, 'Dm_InsideJabu_Jabu_0030')
    marker = editor.events.get('RandoCollected_Event181')
    if marker is None:
        return raw, None
    if _params(marker).get('GameDataName') != flag:
        raise ValueError('Ruto display and dungeon reward have different check markers')
    if not isinstance(editor.events['Event181'].data, SubFlowEvent):
        raise ValueError('Unexpected Ruto display reward')
    editor.replace(marker, marker.data.nxt.v)
    return editor.finish({'retired_display_marker': marker.name})


def apply(options, current, read, write):
    """Compose on current bytes, return a deterministic manifest of the shortcuts.

    ``read`` returns original raw bytes (None for absent flow files); ``current``
    returns the most recent patched bytes. ``write`` stages one raw resource.
    """
    from oot_rando.patching import cinematic_comfort
    records = {}
    for resource in cinematic_comfort.paths(options):
        result, report = cinematic_comfort.patch(resource, current(resource), options)
        write(resource, result); records[resource] = report
    if options.get('skip_story_sequences'):
        for name in STORY_FLOWS:
            result, report = story(current(path(name)), name, read, current)
            write(path(name), result); records[path(name)] = report
        from oot_rando.patching import special_dialogues
        for name in special_dialogues.FLOWS:
            resource = path(name)
            if read(resource) is None:
                continue
            result, report = special_dialogues.shorten(current(resource), name, read)
            if report['silent_lines']:
                write(resource, result)
                records.setdefault(resource, {})['special_dialogue'] = report
        from oot_rando.patching import physical_scene_shortcuts
        for name in physical_scene_shortcuts.FLOWS:
            resource = path(name)
            result, report = physical_scene_shortcuts.shorten(current(resource), name, read, current)
            write(resource, result)
            records.setdefault(resource, {})['physical_scene'] = report
    if options.get('skip_song_lessons'):
        for name in ('DoorOfTime', 'Dm_MelodyGet_Spilit'):
            result, report = extra_song(current(path(name)), name, read, current)
            write(path(name), result); records.setdefault(path(name), {}).update(report)
    if options.get('skip_fairy_sequences'):
        for name in FAIRIES:
            result, report = fairy(current(path(name)), name, read)
            write(path(name), result); records[path(name)] = report
    if options.get('skip_dungeon_endings'):
        resource = path('Dm_SY_BancChange_EscapeDungeon')
        result, report = endings(current(resource), read, current)
        write(resource, result); records[resource] = report
        for name in ('Dm_InsideJabu_Jabu_0030', 'Dm_InsideJabu_Jabu_0030.110'):
            resource = path(name)
            if read(resource) is not None:
                result, alias = retire_ruto_display_marker(current(resource), report['Barinade']['flag'])
                if alias:
                    write(resource, result); records[resource] = alias
        # Last-sage state still executes, but its explanatory cinematic does not.
        editor = SceneEditor(current(path('AllSage')), 'AllSage')
        cuts = cut(editor, 'Dm_SageRoom_0010', read)
        result, _ = editor.finish({})
        write(path('AllSage'), result)
        records.setdefault(path('AllSage'), {})['last_sage'] = cuts
    if options.get('skip_song_lessons'):
        from oot_rando.patching.song_lessons import LESSONS
        from oot_rando.patching.cinematic_tools import held_actor
        # The original ten adapters also use standard item gets. Songs must
        # carry animation as well as a harp model, not just the native pouch actor.
        for resource in sorted({path(lesson.trigger) for lesson in LESSONS}):
            editor = SceneEditor(current(resource), resource)
            forms = {}
            for event in editor.chart.events:
                if not event.name.startswith('RandoLesson_') or not isinstance(event.data, SubFlowEvent):
                    continue
                actor = _params(event).get('ActorName')
                if event.data.res_flowchart_name == 'Dm_SY_GetInEvent' and actor and held_actor(actor) != actor:
                    event.data.params.data['ActorName'] = held_actor(actor)
                    editor.expected[event.name]['ActorName'] = held_actor(actor)
                    forms[event.name] = held_actor(actor)
            if forms:
                result, _ = editor.finish({})
                write(resource, result); records.setdefault(resource, {})['held_forms'] = forms
    from oot_rando.patching.quest_guard import check_expressions
    from oot_rando.game.tracking_metadata import GAMEDATA
    expressions = set()
    for resource in records:
        chart = _flow(current(resource)).flowchart
        for event in chart.events:
            data = event.data
            holder = getattr(data, 'actor_query', None)
            if event.name.startswith('RandoCinema_') and holder is not None and holder.v.v == 'EventQueryIsGameDataBoolExp':
                expressions.add(_params(event)['GameDataName'])
    check_expressions(read(GAMEDATA), expressions)
    from oot_rando.formats import byml_codec
    from oot_rando.patching.soul_adapter import murmur3
    data = byml_codec.load(current(GAMEDATA))['root']['Data']
    hashes = {typ: {int(row['Hash']) for row in rows} for typ, rows in data.items() if isinstance(rows, list)}
    for resource in records:
        for event in _flow(current(resource)).flowchart.events:
            action = _action(event)
            if event.name.startswith('RandoCinema_') and action and action[0] == 'GameDataActor' and action[1].startswith('EventTriggerSetGameData'):
                typ = action[1].removeprefix('EventTriggerSetGameData')
                name = _params(event)['GameDataName']
                if murmur3(name) not in hashes.get(typ, set()):
                    raise ValueError('Unknown cinematic GameData write: ' + name)
    return records


def event_styles(raw, options):
    """Use a normal flow event/player for the Requiem and Light Arrows shortcuts."""
    from oot_rando.formats import byml_codec
    document = byml_codec.load(raw)
    rows = {r['__RowId']: r for r in document['root']}
    reference = rows['KokiriForest_ArriveLostWood']
    targets = []
    if options.get('skip_song_lessons'):
        targets.append('Dm_MelodyGet_Spilit')
    if options.get('skip_story_sequences'):
        targets.append('Market_Adult_Field_GetArrowLight')
    for name in targets:
        if name not in rows:
            raise ValueError('Missing scene shortcut event row: ' + name)
        for field in ('EventBaseSetting', 'EventSettingComponentList', 'EventSoundSetting'):
            rows[name][field] = reference[field]
    return byml_codec.dump(document), targets
