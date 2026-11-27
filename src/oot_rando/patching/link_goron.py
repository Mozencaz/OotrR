"""Make adult Link the Goron playable before his introductory scene.

The map hides the real actor until CityIn sets GenerateDaruniaJr; its two demo
actors wait in the city. Bypass that camera sequence and hide its doubles.
Ready also uses a roll that does not react to bombs. Reuse the native
StopDaruniaJr schedule (including its stun/talk entry), and prevent a delayed
introduction from undoing the bomb hit or subsequent quest progress.
"""
import copy

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc

MODULE = 'Logic/GoronCity_Adult_Prefab_118a.logic.module.ainb'
SCHEDULES = 'Pack/AIScheduleParam.pack.zs'
READY = 'Component/AIScheduleParam/SageOfFire_Ready_Npc_Goron_DaruniaJr_Adult.game__component__AIScheduleParam.bgyml'
STOP = READY.replace('_Ready_', '_StopDaruniaJr_')
FLOW = 'Event/EventFlow/SageOfFire.bfevfl.zs'
STEPS = ('Ready', 'StopDaruniaJr', 'TalkDaruniaJr', 'MoveStatue', 'EnterCrater',
         'MeetSheik', 'EnterTemple', 'MeetDarunia', 'GetBossKey', 'MeetBoss',
         'DefeatBoss', 'GoToWarpPoint')


def spawn_from_first_entry(raw):
    from oot_rando.patching.story_fixes import edit_ainb_module

    def check(nodes):
        create = nodes[0]['Parameters']['Inputs']['Bool'][4]
        if (nodes[0]['Name'] != 'ActorLogicNpc'
                or (create['Name'], create['Node Index'], create['Output Index']) != ('Logic_Create', 13, 0)
                or nodes[13]['Parameters']['Inputs']['String'][0]['Default Value'] != 'SageOfFire_GenerateDaruniaJr'
                or nodes[0]['Queries'] != [3, 13]):
            raise ValueError('Unexpected Darunia Jr. spawn gate (already patched?).')
        for index in (10, 11):
            delete = nodes[index]['Parameters']['Inputs']['Bool'][5]
            if (nodes[index]['Name'] != 'ActorLogicNpc'
                    or (delete['Name'], delete['Node Index']) != ('Logic_Delete', 12)):
                raise ValueError('Unexpected Darunia Jr. cinematic double.')

    def edit(nodes):
        create = nodes[0]['Parameters']['Inputs']['Bool'][4]
        create.update({'Node Index': -1, 'Default Value': True, 'Flags': ['Uses Default', 'Is Output']})
        nodes[0]['Queries'].remove(13)
        nodes[0]['Plugs']['Generic'] = [p for p in nodes[0]['Plugs']['Generic'] if p['Name'] != 'Logic_Create']
        for index in (10, 11):
            node = nodes[index]
            delete = node['Parameters']['Inputs']['Bool'][5]
            delete.update({'Node Index': -1, 'Default Value': True, 'Flags': ['Uses Default', 'Is Output']})
            node['Queries'].remove(12)
            node['Plugs']['Generic'] = [p for p in node['Plugs']['Generic'] if p['Name'] != 'Logic_Delete']
            if not node['Plugs']['Generic']:
                del node['Plugs']['Generic']

    return edit_ainb_module(raw, check, edit), {'module': MODULE, 'spawn': 'first_entry'}


def stunnable_before_intro(raw):
    files = sarc(raw)
    ready = byml_codec.load(files[READY])
    stop = byml_codec.load(files[STOP])['root']
    action = ready['root']['DefaultSchedule']['ActionSchedule'][0]
    normal = stop['DefaultSchedule']['ActionSchedule'][0]
    if (ready['root']['ConditionalSchedule'] or stop['ConditionalSchedule']
            or action['ActionType'] != normal['ActionType']
            or action['Setting']['IsTurnToTerror'] is not False
            or normal['Setting']['IsTurnToTerror'] is not True
            or action['Setting']['MovingAS'] != 'Run_GoronRoll_02'):
        raise ValueError('Unexpected Darunia Jr. rolling schedules (already patched?).')
    ready['root']['DefaultSchedule'] = copy.deepcopy(stop['DefaultSchedule'])
    files[READY] = byml_codec.dump(ready)
    result = byml_codec.build_sarc(files)
    if byml_codec.load(sarc(result)[READY]) != ready:
        raise ValueError('Darunia Jr. schedule wrongly rewritten.')
    return result, {'schedule': READY, 'rolling_schedule': STOP}


def keep_quest_forward(raw):
    from oot_rando.patching import quest_guard
    from oot_rando.patching.story_fixes import _Chart
    from evfl.util import make_index
    flow = _Chart(raw)
    intro = flow.action('RandoGoronIntroPlayed', 'GameDataActor', 'EventTriggerSetGameDataBool',
                       {'GameDataName': 'HavePlayedEvent.SageOfFire_CityIn', 'Index': -1, 'Value': True},
                       flow.events['Event4'])
    start = flow.action('RandoGoronIntroSpawn', 'GameDataActor', 'EventTriggerSetGameDataBool',
                       {'GameDataName': 'SageOfFire_GenerateDaruniaJr', 'Index': -1, 'Value': True}, intro)
    for name, original in (('SageOfFire_CityIn', 'Event294'), ('SageOfFire_CityIn_CrackWall', 'Event444')):
        entry = next(e for e in flow.chart.entry_points if e.name == name)
        if entry.main_event.v.name != original:
            raise ValueError('Unexpected Darunia Jr. introduction entry: ' + name)
        entry.main_event = make_index(start)
        # The replacement contains no subflow calls.
        entry._sub_flow_event_indices = []
    raw, _ = flow.write()
    report = []
    for index, step in enumerate(STEPS[1:4]):
        raw, details = quest_guard.guard_requests(
            raw, 'SageOfFire', {'SageOfFire': list(STEPS)}, (step,),
            f'SageOfFire_IsAfter_{step}_Exp', prefix=f'RandoGoronForward_{index}_')
        if len(details['guarded']) != 1:
            raise ValueError('Unexpected Darunia Jr. quest requests: ' + step)
        report.append(details)
    return raw, {'flow': FLOW, 'intro_skipped': True, 'guards': report}


def resource_fixes():
    return ((MODULE, spawn_from_first_entry), (SCHEDULES, stunnable_before_intro), (FLOW, keep_quest_forward))
