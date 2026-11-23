"""Audited physical story results, applied at their original triggers.

These adapters do not grant quest progress on a new save. The callers still own
payments, counters, branch selection, minigames and repeat-visit guards.
"""
from evfl.entry_point import EntryPoint
from evfl.event import SubFlowEvent
from evfl.util import make_index

from oot_rando.patching.cinematic_tools import SceneEditor, path, give, reward
from oot_rando.patching.song_lessons import _action, _params, _transitions


FLOWS = ('Dm_FireTemple_0020', 'Dm_Gerudo_0020', 'SageOfSpirit',
         'SageOfSpirit_RescueCarpenter', 'Npc_Hylia_Soldier_003',
         'Get_StoneOfWater', 'Get_Epona', 'Npc_Bonooru', 'Npc_Pierre')
OFFSTAGE = {'IsWaitEnd': True, 'IsSleepXLink': True,
            'ExecuteSetSpeedZeroEveryFrame': False, 'IsRidingTargetGoOffstage': False}
IDLE = {'ASName': 'Wait', 'Partial': '', 'IsAllSlot': False,
        'IsAnimeDriven': False, 'ForceFadeInFrame': 0.0, 'IsWaitEnd': False}


def apply_world(staged, read):
    """Snap the native gate controllers, including their physical children.

    The existing letter-flag selectors still decide open/closed. Warping just
    the visible shutter would leave its ground controller moving afterward.
    """
    from oot_rando.patching.world_openings import (
        KAKARIKO_CLOSED_MODULE, KAKARIKO_OPEN_MODULE, _ainb_edit, _node, _bool_input)
    def edit(nodes):
        ground = _node(nodes, 0, 'ActorLogicGroundControlResidentMoveTo')
        warp = _bool_input(ground, 'ForceWarp')
        if warp['Node Index'] != -1 or warp['Default Value'] is not False:
            raise ValueError('Unexpected Kakariko gate ForceWarp input')
        warp['Default Value'] = True
    paths = (KAKARIKO_CLOSED_MODULE, KAKARIKO_OPEN_MODULE)
    for resource in paths:
        staged[resource] = _ainb_edit(staged.get(resource) or read(resource), edit)
    return {'instant_gate_controllers': list(paths)}


def fade_out(editor):
    return editor.act('FadeOut', 'UISystemActor', 'EventEventFadeOut',
                      {'Color': 0, 'Length': 1, 'IsNoPlayAnime': False, 'IsWaitEnd': True})


def continuation(editor, label, root, params=None):
    """Return from a native tail even if a quest guard ends it early."""
    entry = EntryPoint('RandoCinema_' + label)
    entry.main_event = make_index(root)
    editor.chart.entry_points.append(entry)
    return editor.call(label, '', entry.name, params)


def replace_scene(editor, scene, steps):
    """One sequence per call site; do not share a tail across different returns."""
    changed = []
    for event in _transitions(editor.chart, scene):
        first = editor.chain([fade_out(editor)] + steps() + [
            editor.flag('HavePlayedEvent.' + scene), editor.fade()], event.data.nxt.v)
        if editor.replace(event, first):
            changed.append(event.name)
    return changed


def gorons(editor):
    # Native entry -> native delete/debit. No common decrement across prisoners.
    prisoners = (('005', 'Event140', 'Event161'), ('001', 'Event149', 'Event159'),
                 ('003', 'Event167', 'Event173'), ('007', 'Event179', 'Event189'),
                 ('004', 'Event120', 'Event198'), ('002', 'Event122', 'Event200'),
                 ('008', 'Event126', 'Event206'), ('009', 'Event128', 'Event227'),
                 ('010', 'Event134', 'Event236'))
    for index, (npc, delete, debit) in enumerate(prisoners):
        flag = _params(editor.events[delete])['GameDataName']
        effects = [editor.act('HidePrisoner', f'Npc_Goron_{npc}_Adult',
                              'EventGoOffstageForUser', OFFSTAGE),
                   editor.clone_action(editor.events[delete]),
                   editor.clone_action(editor.events[debit])]
        if index == 8:
            # The final room also tells the quest that Volvagia has been met.
            effects.append(editor.call('MeetBoss', 'SageOfFire', 'SageOfFire_MeetBoss'))
        done = editor.fade()
        first = editor.chain([fade_out(editor)] + effects, done)
        # Native map aliases normally trigger once; also make a repeated entry safe.
        first = editor.switch(editor.unique('AlreadyReleased'), 'GameDataActor',
                              'EventQueryIsGameDataBool', {'GameDataName': flag, 'Index': -1},
                              done, first)
        editor.entries[f'EntryPoint{index}'].main_event = make_index(first)
    return {'prisoners': 9}


def carpenters(editor):
    # All accounting remains in the caller and Common_Dungeon's StepCheck_Clear.
    # Its fourth-rescue path still launches the shuffled membership-card check.
    for index, (npc, entry, flags) in enumerate((('013', 'Ichiro_OpenDoor_Next0', 'Event154'),
                                               ('014', 'Jiro_OpenDoor_Next', 'Event66'),
                                               ('015', 'Saburo_OpenDoor_Next0', 'Event147'),
                                               ('016', 'Shiro_OpenDoor_Next', 'Event148'))):
        # Reuse each original call's concrete WarpPoint argument. This check
        # belongs BEFORE StepCheck_Clear: the fourth rescue spawns the Gerudo,
        # then the card ceremony sends her home and clears IsInFirstPlace.
        source = editor.events[flags]
        create = editor.call('CarpenterFlags', '', source.data.entry_point_name, _params(source))
        first = editor.chain([fade_out(editor),
            create,
            editor.act('HideCarpenter', f'Npc_Hylia_{npc}_Adult[GerudoFortress]',
                       'EventGoOffstageForUser', OFFSTAGE),
            editor.call('CarpenterCompletion', 'Common_Dungeon_OpenDoorChainLockMove', entry),
            editor.fade()])
        editor.entries[f'EntryPoint{index}'].main_event = make_index(first)
    return {'carpenters': 4}


def spirit(editor, read, current):
    item = reward(current(path('Dm_Gerudo_0025')), 'Event294')
    for event in _transitions(editor.chart, 'Dm_Gerudo_0025'):
        # The native caller warps the Gerudo home after the scene. There is no
        # reason to walk her to Link and back just to give the reward.
        following = editor.chain([editor.flag('HavePlayedEvent.Dm_Gerudo_0025')], event.data.nxt.v)
        first = editor.chain([fade_out(editor), editor.fade()], give(editor, item, following))
        editor.replace(event, first)
    # Nabooru's two questions only repeat exposition; all quest effects and the
    # final Action4 warp are in the caller after this scene.
    native_tail = continuation(editor, 'NabooruCompletion', editor.events['Event411'].data.nxt.v)
    editor.entries['SageOfSpirit_MeetNabooru'].main_event = make_index(editor.chain([
        editor.clone_action(editor.events['Event35']), fade_out(editor),
        editor.flag('HavePlayedEvent.Dm_DesertColossus_0020'),
        editor.flag('HavePlayedEvent.Dm_DesertColossus_0025'),
        editor.clone_action(editor.events['Event126']),
        editor.clone_action(editor.events['Event218']), native_tail, editor.fade()]))
    return {'membership_card': item, 'nabooru': ['Dm_DesertColossus_0020', 'Dm_DesertColossus_0025']}


def rescue_dialogues(editor):
    # Counting advice is an external Navi talk; the dialogue-only pass cannot
    # see inside that call. Its parameterized saved flag still runs once.
    for key in ('Event300', 'Event299'):
        event = editor.events[key]
        editor.replace(event, event.data.nxt.v)
    return {'carpenter_navi_advice': True}


def gate(editor, read):
    scene = SceneEditor(read(path('Dm_Kakariko_0010')), 'Dm_Kakariko_0010')
    # Letter display/debit belongs to the caller; the scene hides its display
    # actor and writes the very flag read by the gate's native world logic.
    return {'letter_gate': replace_scene(editor, 'Dm_Kakariko_0010', lambda: [
        editor.clone_action(editor.events['Event12']),
        editor.clone_action(scene.events['Event18'])])}


def ruto(editor, read):
    scene = SceneEditor(read(path('Dm_InsideJabu_Jabu_0030')), 'Dm_InsideJabu_Jabu_0030')
    # The lift returns to its placement at the end of C14. Do not bind it to a
    # demo locator or leave its collision at the upper, intermediate position.
    from oot_rando.formats.inspect_resources import Byml
    actors = Byml(read('Banc/InsideJabuJabuBelly/InsideJabuJabuBelly_Static.bcett.byml.zs')).root['Actors']
    lift = next(a for a in actors if a['Gyaml'] == 'Obj_InsideJabu_Jabu_ElevatorLift_A_01'
                and a.get('Name') == 'ElevatedFloor1')
    def effects():
        steps = [editor.clone_action(scene.events[k]) for k in ('Event42', 'Event228', 'Event98', 'Event55')]
        steps += [editor.act('LiftFinalPosition', 'Obj_InsideJabu_Jabu_ElevatorLift_A_01[ElevatedFloor1]',
                             'EventWarpToTargetPosAndRot', {'Position': lift['Translate'],
                             'YAngle': 0.0, 'ClothWarpMode': -1, 'IsWaitEnd': True}),
                  editor.clone_action(scene.events['Event227']),
                  editor.clone_action(scene.events['Event236']),
                  editor.clone_action(scene.events['Event87']),
                  editor.clone_action(scene.events['Event217']),
                  editor.clone_action(scene.events['Event29']),
                  editor.clone_action(scene.events['Event74']),
                  editor.clone_action(scene.events['Event226']),
                  editor.clone_action(scene.events['Event260']),
                  editor.clone_action(scene.events['Event54'])]
        return steps
    return {'ruto_platform': replace_scene(editor, 'Dm_InsideJabu_Jabu_0030', effects)}


def epona(editor, read):
    scenes = {name: SceneEditor(read(path(name)), name) for name in
              ('Dm_LonLon_0020', 'Dm_LonLon_0030', 'Dm_LonLon_0040')}
    report = {}
    # Horse/player staging is required before the caller's mounting and start
    # routines. The races, fees, acceptance menus and win counters stay native.
    report['race_staging'] = replace_scene(editor, 'Dm_LonLon_0020', lambda: [
        editor.clone_action(scenes['Dm_LonLon_0020'].events[k]) for k in ('Event24', 'Event14', 'Event77')])
    report['first_win'] = replace_scene(editor, 'Dm_LonLon_0030', lambda: [
        editor.clone_action(scenes['Dm_LonLon_0030'].events[k])
        for k in ('Event29', 'Event30', 'Event31', 'Event40', 'Event55')])
    def final_win():
        scene = scenes['Dm_LonLon_0040']
        return [editor.clone_action(scene.events['Event103']),
                editor.clone_action(scene.events['Event4']),
                editor.clone_action(scene.events['Event87']),
                # The native object's persistent closed pose, from its
                # ASCommand_OnOff/ToOpenToClose parameter, without the demo.
                editor.act('CloseRanchGate', 'Obj_LonLon_Gate_A_01', 'EventPlayAS', dict(IDLE, ASName='Close')),
                editor.clone_action(scene.events['Event108'])]
    report['final_win'] = replace_scene(editor, 'Dm_LonLon_0040', final_win)
    return report


def scarecrows(editor):
    """Keep recording/recognition and their branches; drop response performances."""
    from oot_rando.patching import npc_dialogue_skip as dialogue
    removed = []
    for event in list(editor.chart.events):
        action = _action(event)
        params = _params(event)
        data = event.data
        drop = False
        if dialogue._is_talk(event):
            drop = not dialogue._offers_choice(event)
            if not drop and params.get('IsCloseDialog') is False:
                data.params.data['IsCloseDialog'] = True
                editor.expected[event.name]['IsCloseDialog'] = True
        elif action:
            actor, verb = action
            drop = (actor.startswith(('EventCamera', 'PostProcessingActor', 'DevelopEventSystemActor'))
                    or verb in ('EventWait', 'EventWaitFrameOrSkip', 'EventPlayAS',
                                'EventPlayASWithClothWarp', 'EventTriggerEmitXLink',
                                'EventTriggerChangeEmotion'))
            # The spawn's two-frame wait and final standard poses are functional.
            if editor.name == 'Npc_Bonooru' and event.name in ('Event83', 'Event88', 'Event331', 'Event342'):
                drop = False
            if verb in ('EventEventFadeOut', 'EventEventFadeIn'):
                data.params.data['Length'] = 1
                editor.expected[event.name]['Length'] = 1
        elif isinstance(data, SubFlowEvent):
            drop = (data.res_flowchart_name == 'Common_Camera_Pln' or
                    (data.res_flowchart_name == 'Dm_SY_Ocarina_Scarecrow'
                     and data.entry_point_name in ('PlayAutoBonooru', 'PlayAutoPierre')))
        if drop:
            # Keep terminal entries and fork branches valid, including menus'
            # native result queries. Never skip a recording or learning call.
            noop = editor.act('NoPerformance', 'EventSystemActor', 'EventWait',
                              {'Frames': 1, 'IsWaitEnd': True})
            editor.chain([noop], event.data.nxt.v)
            if (isinstance(data, SubFlowEvent) and data.res_flowchart_name == 'Dm_SY_Ocarina_Scarecrow'
                    and data.entry_point_name in ('PlayAutoBonooru', 'PlayAutoPierre')):
                noop = editor.chain([fade_out(editor), editor.fade()], noop)
            if editor.name == 'Npc_Bonooru' and event.name == 'Event336':
                noop = editor.chain([fade_out(editor),
                    editor.clone_action(editor.events['Event88']), editor.fade()], noop)
            if editor.replace(event, noop):
                removed.append(event.name)
    if editor.name == 'Npc_Bonooru':
        # Pierre is only a temporary quest presentation here: he appears, talks,
        # goes away, then completes the quest. Apply that final state directly;
        # do not spawn a hookshot target for a frame and request a deleted actor.
        editor.entries['PierreApperedFlow'].main_event = make_index(editor.chain([
            fade_out(editor)] + [editor.clone_action(editor.events[k])
                                 for k in ('Event95', 'Event121', 'Event52', 'Event79', 'Event331', 'Event342')]
            + [editor.fade()]))
    # A removed talk must not leave a speaker/close request with no message.
    cleanup = dialogue.plan(editor.chart)
    for event in cleanup['closes'] + cleanup['speakers']:
        editor.replace(event, event.data.nxt.v)
    return {'removed_performances': sorted(removed), 'interactive_ocarina': True}


def shorten(raw, name, read, current):
    sources = [read(path('OpeningEvent')), read(path('Dm_SY_GetInEvent'))]
    sources += [read(path(n)) for n in ('Dm_Kakariko_0010', 'Dm_InsideJabu_Jabu_0030',
                                      'Dm_LonLon_0020', 'Dm_LonLon_0030', 'Dm_LonLon_0040')]
    editor = SceneEditor(raw, name, sources)
    if name == 'Dm_FireTemple_0020':
        report = gorons(editor)
    elif name == 'Dm_Gerudo_0020':
        report = carpenters(editor)
    elif name == 'SageOfSpirit':
        report = spirit(editor, read, current)
    elif name == 'SageOfSpirit_RescueCarpenter':
        report = rescue_dialogues(editor)
    elif name == 'Npc_Hylia_Soldier_003':
        report = gate(editor, read)
    elif name == 'Get_StoneOfWater':
        report = ruto(editor, read)
    elif name == 'Get_Epona':
        report = epona(editor, read)
    else:
        report = scarecrows(editor)
    return editor.finish(report)
