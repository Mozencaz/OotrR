"""Adult start (``starting_age`` = ``adult``): a new game begins as adult Link in the Temple of Time.

The new game still loads Kokiri Forest (the engine's start banc) and its opening flow
runs as usual: seed marker, starting items and start values are written by the
``Opening_LoadingKokiriForest`` entry. In ``Opening_Introduction``, right after its own
quest request (``Event8``), Link now leaves for the Temple of Time instead of playing
the forest introduction:

* a 30-frame ``EventSystemActor.EventWait`` (:data:`WAIT_EVENT`) first, behind the black
  fade: without it the banc change raced the opening skip (``skip_opening``) and the
  new game stalled on a black screen when the child castle skip was off;
* ``Sequence_IsChildhood`` is set to false (the same flag the native child-to-adult
  scene ``Market_Child_Field_ChildToAdult`` sets);
* the quest state of the native first adult arrival (``AllSage/Market_Adult_AllSage_Start``,
  played by the Temple of Time trigger the first time Link enters it as adult) is set
  too, since the introduction scenes are not played: ``AllSage`` and ``SageOfForest`` at
  ``Step01`` and ``Market_Child_Firsttime_GotoAdult``. Without ``AllSage`` past ``Ready``
  Sheik stayed beside the pedestal and blocked the put-in prompt
  (:data:`oot_rando.patching.story_fixes.SHEIK_TEMPLE_GONE`);
* the banc change to ``Market_Adult`` is a copy of that scene's first-arrival request
  (same position, same fade, boot event ``Dm_TimeTemple_0085``: Link stands at the pedestal).

The Door of Time is open from the start (``open_door_of_time`` is forced on by
:func:`oot_rando.logic.rando_options.validate`), so time travel works both ways at the
pedestal. Putting the sword back needs it in the pouch, so an adult start holds the
Master Sword (:data:`START_ACTORS`) unless ``shuffle_master_sword`` is on (then it is a
find like any other); every other starting item is the player's choice
(``start_inventory_from_pool``). Not validated in game.
"""
OPTION = 'starting_age'
VALUE = 'adult'
ANCHOR = 'Event8'                    # Opening_Introduction: after its quest request
ERA_FLAG = 'Sequence_IsChildhood'
ERA_EVENT = 'RandoAdultStart_Era'
WARP_EVENT = 'RandoAdultStart_Warp'
WAIT_EVENT = 'RandoAdultStart_Wait'
WAIT_PARAMS = {'IsWaitEnd': True, 'Frames': 30}
ARRIVAL_EVENTS = ('RandoAdultStart_AllSage', 'RandoAdultStart_Forest', 'RandoAdultStart_GotoAdult')
# Challenge requests of AllSage/Event18 and Event19, parameter for parameter.
_STEP = {'IsWaitEnd': True, 'IsIgnoreCompletedChallenge': False, 'IsIgnoreChallengeProgressUI': False}
ARRIVAL_PARAMS = {
    ARRIVAL_EVENTS[0]: dict(_STEP, ChallengeName='AllSage', StepName='Step01'),
    ARRIVAL_EVENTS[1]: dict(_STEP, ChallengeName='SageOfForest', StepName='Step01'),
    ARRIVAL_EVENTS[2]: {'GameDataName': 'Market_Child_Firsttime_GotoAdult', 'Value': True, 'Index': -1}}
START_ACTORS = ('Weapon_Sword_Master',)
# GameSystemActor.EventReserveBancChange of Market_Child_Field_ChildToAdult (Event0), parameter
# for parameter.
WARP_PARAMS = {'IsWaitEnd': True, 'IsStartOnEvent': False, 'NextStartPos': '', 'NextBanc': 'Market_Adult',
               'BootEventName': 'Dm_TimeTemple_0085', 'FadePattern': 2, 'EventStarterName': '',
               'IsItemWarp': False, 'NextPosition': [137.20840454101562, 106.12010192871094, -34.0],
               'NextStartRot': [0.0, 90.0, 0.0]}


def enabled(options):
    return (options or {}).get(OPTION) == VALUE


def event_params():
    """{event name: parameters} added to the opening flow."""
    return {WAIT_EVENT: dict(WAIT_PARAMS), **ARRIVAL_PARAMS, ERA_EVENT: {'GameDataName': ERA_FLAG, 'Value': False, 'Index': -1},
            WARP_EVENT: dict(WARP_PARAMS)}


def patch_opening(raw, after=ANCHOR):
    """Opening flow bytes where ``after`` leads to a short wait, the era flag, then the Temple of Time.

    The forest introduction that followed ``after`` no longer plays. Returns (bytes, report)."""
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    anchor = flow.event(after, 'ActionEvent')
    warp = flow.action(WARP_EVENT, 'GameSystemActor', 'EventReserveBancChange', WARP_PARAMS, None)
    era = flow.set_bool(ERA_EVENT, ERA_FLAG, False, warp)
    goto = flow.set_bool(ARRIVAL_EVENTS[2], 'Market_Child_Firsttime_GotoAdult', True, era)
    forest = flow.action(ARRIVAL_EVENTS[1], 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep',
                         ARRIVAL_PARAMS[ARRIVAL_EVENTS[1]], goto)
    sage = flow.action(ARRIVAL_EVENTS[0], 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep',
                       ARRIVAL_PARAMS[ARRIVAL_EVENTS[0]], forest)
    wait = flow.action(WAIT_EVENT, 'EventSystemActor', 'EventWait', WAIT_PARAMS, sage)
    anchor.data.nxt = make_index(wait)
    result, events = flow.write()
    names, event = [], events[after].data.nxt.v
    while event is not None:
        names.append(event.name)
        event = event.data.nxt.v
    if names != [WAIT_EVENT, *ARRIVAL_EVENTS, ERA_EVENT, WARP_EVENT]:
        raise ValueError('Adult start wrongly chained.')
    return result, {'after': after, 'events': list(event_params()), 'banc': WARP_PARAMS['NextBanc']}
