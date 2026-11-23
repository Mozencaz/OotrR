"""Dialogue-only adapters for audited scenes with physical or inventory effects.

Keep the native scene, routing and effects. In particular, never flatten the nine
Goron entries or replay a trade's consumption outside its accepted branch.
"""
from oot_rando.patching.cinematic_tools import SceneEditor, path
from oot_rando.patching.song_lessons import _action, _params
from oot_rando.patching import npc_dialogue_skip as dialogue


FLOWS = (
    'Dm_Zora_0010', 'Dm_HrlCastle_0020', 'Dm_HrlCastle_0020.110',
    'Dm_FireTemple_0020', 'SageOfSpirit_RescueCarpenter',
    'Npc_Kokiri_Mido_Child', 'Npc_Kokiri_Mido_Adult', 'Npc_Hylia_Soldier_003',
    'Get_StoneOfWater', 'Field_PlantMagicBean', 'SageOfSpirit',
    'Dm_DeathMtTrail_0050', 'Npc_Goron_Biggoron_Adult',
    'Npc_Hylia_012_Adult', 'Npc_Hylia_017_Adult', 'Npc_Hylia_045_Adult',
    'Npc_Hylia_049_Adult', 'Npc_Hylia_053_Adult', 'Npc_Kokiri_Fado_Adult',
    'Npc_Zora_KingZora_adult', 'Npc_Hylia_Talon_Adult',
)


def shorten(raw, name, read):
    editor = SceneEditor(raw, name, [read(path('OpeningEvent'))])
    changes = dialogue.plan(editor.chart)
    talks = changes['talks'] + changes['alone']
    if name == 'Dm_DeathMtTrail_0050':
        # The two menus still decide acceptance/repetition. Their explanatory
        # replies can vanish: the pouch check, debit and Step11 stay in place.
        from oot_rando.patching.skip_auto import _roots
        talks = [e for e in dialogue._reach(editor.chart, _roots(editor.chart))
                 if dialogue._is_talk(e) and not dialogue._offers_choice(e)]
    from oot_rando.patching.skip_auto import _successors
    dropped = {e.name for e in talks}
    kept = [e for e in editor.chart.events if dialogue._is_talk(e) and e.name not in dropped]
    kept_names = {e.name for e in kept}
    close_dialog = [e for e in kept if _params(e).get('IsCloseDialog', True) is False and
                    dropped & {f.name for f in dialogue._reach(editor.chart, _successors(e), kept_names)}]
    removed = []
    for event in talks:
        params = _params(event)
        if params.get('ASName'):
            # Talk also requests an animation. Preserve that request separately;
            # a looping talking/wait pose must not become a blocking PlayAS.
            first = editor.act('TalkPose', _action(event)[0], 'EventPlayAS', {
                'ASName': params['ASName'], 'Partial': '',
                'IsAllSlot': params.get('IsPlayASAllSlot', False),
                'IsAnimeDriven': params.get('IsAnimeDriven', False),
                'ForceFadeInFrame': -1.0, 'IsWaitEnd': False,
            })
        else:
            first = editor.act('SilentLine', 'EventSystemActor', 'EventWait',
                               {'Frames': 1, 'IsWaitEnd': True})
        editor.chain([first], event.data.nxt.v)
        if editor.replace(event, first):
            removed.append(event.name)
    # Retained questions/answers must close their own message if their original
    # closing continuation was removed. Never leave an anonymous dialogue box
    # without its speaker, or remove a speaker still needed by a kept question.
    for event in close_dialog:
        event.data.params.data['IsCloseDialog'] = True
        editor.expected[event.name]['IsCloseDialog'] = True
    cleanup = dialogue.plan(editor.chart)
    for event in cleanup['closes'] + cleanup['speakers']:
        editor.replace(event, event.data.nxt.v)
    return editor.finish({'silent_lines': sorted(removed), 'native_motion': True})
