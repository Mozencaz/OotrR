"""World openings: zones open from the start of a new game.

Each opening is the pair of building blocks of the remake's story:

* a new-game default in the GameData list (:mod:`oot_rando.patching.game_defaults`),
  read by the game before any flow runs;
* a quest floor guard (:mod:`oot_rando.patching.quest_guard`) on every flow that
  would request an earlier step of the same quest, so the opening cannot close again.

**Zora's Fountain open** (``zora_fountain`` = ``open``). King Zora's position follows
the ``Get_StoneOfWater`` quest (saved enum ``Step_Get_StoneOfWater``). ``Step07`` is
the step after he read Ruto's Letter (moved aside: the fountain is reachable). A new
game starts there. The quest is requested from two flows only (scan of the 914 flows
of 1.1.1): ``Get_StoneOfWater`` (the diving game, the letter found and read, the
quest scenes) and ``Dm_SY_BancChangeArrive`` (the first arrival in Zora's Domain,
``Step03`` / ``Step03_Impa``). Their requests of a step before ``Step07`` are skipped
once the quest is past ``Step06``. Later steps (Jabu-Jabu, the Zora Sapphire) are
untouched. Ruto's Letter stays an item: with the king moved it can no longer be
delivered, so the logic never counts it as a bottle. Not validated in game.
"""
from oot_rando.patching import game_defaults, quest_guard

ZORA_QUEST = 'Get_StoneOfWater'
ZORA_STEP = 'Step_Get_StoneOfWater'
ZORA_FLOOR = 'Step07'
ZORA_FLOWS = ('Event/EventFlow/Get_StoneOfWater.bfevfl.zs',
              'Event/EventFlow/Dm_SY_BancChangeArrive.bfevfl.zs')


def zora_fountain_open(read_flow, gamedata_raw, challenges_raw):
    """The Zora's Fountain opening.

    ``read_flow(path)`` returns the current bytes of a flow (an earlier edit or the
    game's). Returns (gamedata bytes, {flow path: bytes}, report).
    """
    steps = quest_guard.challenge_steps(challenges_raw)
    gamedata = game_defaults.set_new_game_defaults(gamedata_raw, {ZORA_STEP: ZORA_FLOOR})
    flows, guarded = {}, {}
    for path in ZORA_FLOWS:
        flows[path], report = quest_guard.guard_regressions(read_flow(path), ZORA_QUEST, steps, ZORA_FLOOR,
                                                            gamedata_raw=gamedata)
        if not report['guarded']:
            raise ValueError(f'Zora quest guard: no request to guard in {path}')
        guarded[path] = report['guarded']
    expression = quest_guard.floor_expression(steps, ZORA_QUEST, ZORA_FLOOR)
    return gamedata, flows, {'default': {ZORA_STEP: ZORA_FLOOR}, 'expression': expression, 'guarded': guarded}
