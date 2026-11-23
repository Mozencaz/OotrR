"""Optional opening, action-guide and first-ground-pickup shortcuts.

Guide names were enumerated from the game's LayoutMsg/ActionGuide_00 Title_ labels.
They are checked against saved GameData before a seed is written.
"""
from evfl.util import make_index

from oot_rando.patching.cinematic_tools import SceneEditor, path
from oot_rando.patching.song_lessons import _action, _params

GUIDES = (
    'ActivationAmiibo', 'AgonyStone', 'AlarmCucco', 'Amiibo', 'Backflip', 'Bomb', 'Bombchu',
    'Boomerang', 'BootShortcut', 'Bottle', 'Bow', 'DekuNut', 'DekuStick', 'DinFire',
    'EquipmentMenu', 'EquipmentMenuForBoot', 'EquipmentMenuForHeadArmor', 'FaroreWind',
    'FireArrow', 'FishingRod', 'GoronGauntlet', 'Hammer', 'HeadShortcut', 'Hookshot',
    'HorizontalSlash', 'IceArrow', 'ItemMenu', 'ItemShortcut', 'JumpSlash', 'LightArrow',
    'LockOn', 'LockOnShield', 'LockOnSideMove', 'Longshot', 'MagicBean', 'Navi', 'NayruLove',
    'Ocarina', 'OcarinaSongEstimate', 'RollAttack', 'RotarySlash', 'Save', 'ScrubBusinessSeed',
    'SideJump', 'SinkingLure', 'SlingShot', 'SystemMinus', 'Thrust', 'TimeTrail', 'VerticalSlash',
    'Weapon_Shield_Hylian', 'Weapon_Shield_Mirror', 'ZeldaLetter',
)
PICKUPS = ('Obj_Rupee_Green', 'Obj_Rupee_Blue', 'Obj_Rupee_Red', 'Obj_Rupee_Purple', 'Obj_Heart',
           'Obj_MagicJar_Small', 'Obj_MagicJar_Large', 'Obj_ArrowBundle_Small',
           'Obj_ArrowBundle_Medium', 'Obj_ArrowBundle_Large', 'Obj_DekuSeed', 'Item_DekuSeed',
           'Item_Bomb', 'Item_Bombchu', 'Item_DekuNut', 'Item_DekuStick')


def start_values(options):
    flags = {}
    if options.get('skip_tutorials'):
        flags.update({'ActionGuide_IsEnd.' + name: True for name in GUIDES})
        flags.update({name: True for name in ('IsGet.Item_Dungeon_Map', 'IsGet.Item_Dungeon_Compass',
                     'HavePlayedGetEvent.Item_Dungeon_Map', 'HavePlayedGetEvent.Item_Dungeon_Compass',
                     'HavePlayedEvent.NaviHint_Shield_Hylian', 'HavePlayedEvent.NaviHint_Shield_Hylian_BuyShop')})
    if options.get('skip_first_pickup_text'):
        flags.update({'HavePlayedGetEvent.' + actor: True for actor in PICKUPS})
    return flags


def tutorials(raw):
    editor = SceneEditor(raw, 'ActionGuide')
    # These are the vanilla bodies, not their entry points: our progression,
    # progressive and key hooks are prepended outside these roots and survive.
    native = ('Event44', 'Event88')
    for name in native:
        if name not in editor.events:
            raise ValueError('Unsupported ActionGuide body: ' + name)
    end = editor.act('NoGuide', 'EventSystemActor', 'EventWait', {'Frames': 1, 'IsWaitEnd': True})
    for name in native:
        editor.replace(editor.events[name], end)
    for name in ('OpenActionGuideSceen', 'OpenActionGuideSceenForce', 'OpenActionGuideSceenForOcarina'):
        if name not in editor.entries:
            raise ValueError('Unsupported tutorial entry: ' + name)
        editor.entries[name].main_event = make_index(end)
    return editor.finish({'entries': sorted(editor.entries), 'native_bodies': list(native)})


def opening(raw, options):
    editor = SceneEditor(raw, 'OpeningEvent')
    changes = []
    if options.get('skip_opening'):
        movie, scene = editor.events['Event3'], editor.events['Event5']
        if (_params(movie).get('EventName'), _params(scene).get('EventName')) != ('Dm_Kokiri_0000', 'Dm_Kokiri_0030'):
            raise ValueError('Unexpected opening scenes')
        # Event3's continuation contains our save marker and start-value chain.
        editor.replace(movie, editor.chain([editor.flag('HavePlayedEvent.Dm_Kokiri_0000')], movie.data.nxt.v))
        # Follow the native skipped wake-up path (Navi warp, camera reset, fade).
        short = editor.chain([editor.flag('HavePlayedEvent.Dm_Kokiri_0030')], editor.events['Event25'])
        editor.replace(scene, short)
        editor.replace(editor.events['Event32'], short)
        for name in ('Event19', 'Event21'):
            event = editor.events[name]
            if not _action(event)[1].endswith('EventWait'):
                raise ValueError('Unexpected opening wait')
            event.data.params.data['Frames'] = 1
            editor.expected[name]['Frames'] = 1
        changes.append('opening')
    if options.get('skip_first_pickup_text'):
        anchor = editor.events['RandoCollected_Event3']
        following = anchor.data.nxt.v
        for bag in ('Nut', 'Stick'):
            base = f'Item_{bag}Bag_Small'
            grant = editor.act('BaseBag', 'PouchSystemActor', 'EventTriggerAddOrRemovePouchContent',
                               {'Actor': base, 'Num': 1, 'IsEquipDIrect': False,
                                'IsSetMessageTargetActorName': False, 'IsGetEvent': False})
            from oot_rando.patching.progressive import link
            link(grant, following)
            first = grant
            # Every owned tier bypasses the grant, so starting upgrades never regress.
            for tier in ('Small', 'Medium', 'Large'):
                first = editor.switch(editor.unique('BagHeld'), 'PouchSystemActor', 'EventQueryIsExistInPouch',
                                      {'Actor': f'Item_{bag}Bag_{tier}', 'Num': 1}, following, first)
            following = first
        anchor.data.nxt = make_index(following)
        changes.append('pickup_bags')
    return editor.finish({'changes': changes})


def paths(options):
    result = []
    if options.get('skip_tutorials'):
        result.append(path('ActionGuide'))
    if options.get('skip_opening') or options.get('skip_first_pickup_text'):
        result.append(path('OpeningEvent'))
    return result


def patch(resource, raw, options):
    return tutorials(raw) if resource == path('ActionGuide') else opening(raw, options)
