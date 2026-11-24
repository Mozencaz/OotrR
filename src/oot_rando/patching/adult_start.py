"""Adult start (``starting_age`` = ``adult``): a new game begins as adult Link in the Temple of Time.

The new game still loads Kokiri Forest (the engine's start banc) and its opening flow
runs as usual: seed marker, starting items and start values are written by the
``Opening_LoadingKokiriForest`` entry. In ``Opening_Introduction``, right after its own
quest request (``Event8``), Link now leaves for the Temple of Time instead of playing
the forest introduction:

* ``Sequence_IsChildhood`` is set to false (the same flag the native child-to-adult
  scene ``Market_Child_Field_ChildToAdult`` sets);
* the banc change to ``Market_Adult`` is a copy of that scene's first-arrival request
  (same position, same fade, boot event ``Dm_TimeTemple_0085``: Link stands at the pedestal).

The Door of Time is open from the start (``open_door_of_time`` is forced on by
:func:`oot_rando.logic.rando_options.validate`), so time travel works both ways at the
pedestal. Putting the sword back needs it in the pouch, so an adult start always holds the
Master Sword (:data:`START_ACTORS`); every other starting item is the player's choice
(``start_inventory_from_pool``). Not validated in game.
"""
OPTION = 'starting_age'
VALUE = 'adult'
ANCHOR = 'Event8'                    # Opening_Introduction: after its quest request
ERA_FLAG = 'Sequence_IsChildhood'
ERA_EVENT = 'RandoAdultStart_Era'
WARP_EVENT = 'RandoAdultStart_Warp'
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
    return {ERA_EVENT: {'GameDataName': ERA_FLAG, 'Value': False, 'Index': -1},
            WARP_EVENT: dict(WARP_PARAMS)}


def patch_opening(raw, after=ANCHOR):
    """Opening flow bytes where ``after`` leads to the era flag, then the Temple of Time.

    The forest introduction that followed ``after`` no longer plays. Returns (bytes, report)."""
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    anchor = flow.event(after, 'ActionEvent')
    warp = flow.action(WARP_EVENT, 'GameSystemActor', 'EventReserveBancChange', WARP_PARAMS, None)
    era = flow.set_bool(ERA_EVENT, ERA_FLAG, False, warp)
    anchor.data.nxt = make_index(era)
    result, events = flow.write()
    chain = events[after].data.nxt.v
    if (chain is None or chain.name != ERA_EVENT or chain.data.nxt.v is None
            or chain.data.nxt.v.name != WARP_EVENT or chain.data.nxt.v.data.nxt.v is not None):
        raise ValueError('Adult start wrongly chained.')
    return result, {'after': after, 'events': [ERA_EVENT, WARP_EVENT], 'banc': WARP_PARAMS['NextBanc']}
