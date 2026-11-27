"""Story locks of the remake that items found in any order would break.

The remake drives its story with *challenges* (RSDB ``Challenge``): a saved enum per
quest (``Get_StoneOfFire``: ``... SariaMelodyPlay, DodongoCavernOpne, ..., Complete``)
read through ``<Challenge>_IsAfter_<Step>_Exp`` / ``_IsCompleted_Exp`` BoolExps.
Several scenes assume the vanilla order of the quests. Each fix below is an exact
edit of one resource, checked by re-reading it (Discord reports of 15/11):

* **Darunia's gift** (``Dm_Goron_0030``, ``GC Darunias Joy``). Saria's Song played
  to Darunia runs ``Get_StoneOfFire/Get_StoneOfFire_PlayOcarina``: after his dance
  (``Dm_Goron_0025``) the gift scene plays only while the challenge is not past
  ``SariaMelodyPlay`` (Event39). Dodongo's Cavern finished first (bombs found
  early), the challenge is ``Complete`` and the gift never came. It now plays while
  ``HavePlayedEvent.Dm_Goron_0030`` is false. The gift scene itself moves the
  challenge to ``DodongoCavernOpne`` (Event121): that step is now skipped once the
  challenge is past ``SariaMelodyPlay``, so a finished quest never goes back.
  Opening the cavern also selects a restricted ocarina prompt (Event82) which
  omits melody cases 6–11. Until the gift is received, keep the original prompt
  with all melodies, even when the quest has already advanced.
* **Talon at the castle twice.** ``SubEvent_GetEponaSong/GetEponaSong_StepCheck``
  sends Malon back to the castle (``IsMalonAppear_HyruleCastleSecondTime``, with an
  awake Talon at the entrance) once Dodongo's Cavern is done and Jabu-Jabu is not.
  Vanilla never gets there before Talon was woken; done in another order, the first
  Malon (the Weird Egg) was hidden and the sleeping Talon stayed: no egg, no Zelda.
  Malon now only comes back after Talon's wake-up scene (``Dm_HrlCastle_0020``);
  before it the flag is cleared, which also repairs a save already in that state.
* **Sheik at the Master Sword: withdrawn.** Seeds up to 0.6.5 hid the Temple of Time
  Sheik until the Forest Temple was finished. Every Temple of Time scene with him
  (first arrival as adult, Prelude of Light...) then played without him, and the sword
  still could not be put back (Discord 16/11): he was not what blocked it. The
  pedestal's own logic module was (:func:`pedestal_after_first_adult_arrival`).
* **Bombchu Bowling.** The alley opened only after Dodongo's Cavern
  (``MiniGame_BombchuBowling/AfterWakeUp`` Event137, ``Get_StoneOfFire_IsCompleted_Exp``):
  it is open from the start, as the logic expects.
* **Bombchu Shop.** Same lock on the shop door (``Market_Child_Prefab_0c76`` read
  ``Get_StoneOfFire_IsCompleted_Exp``, :func:`bombchu_shop_open_from_start`): it now
  opens from the start, with opening hours removed by ``shop_hours``. The vendor, music and closed sign have
  separate map Presence checks; :func:`bombchu_shop_actor_edits` removes their
  dungeon dependency too, keeping the vendor/music and hiding the closed sign.
* **Great Fairies.** Zelda's Lullaby on a fountain's Triforce mark
  (``TriForcePoint/Sub_PlayOcarinaSequence_FairyFountain``) only calls the fairy of
  Din's Fire (Death Mountain Trail) at once; the five others stay away while
  ``IsGet.Item_DinFire`` is false (Event8), so with Din's Fire shuffled away they
  never came. Every fairy now answers the lullaby from the start; the way into
  each fountain (bombable wall, boulder...) is unchanged.
* **Great Fairy rewards given once, by the fairy.** On a later visit each fairy
  only heals Link when ``IsGet.<her vanilla item>`` is true (Din's Fire, magic,
  Farore's Wind...). That flag follows the item, not the fairy: Din's Fire found in
  a chest first, the Death Mountain fairy never handed over her shuffled reward.
  Each fairy now has her own saved flag (``RandoGreatFairy_<name>``), set right
  before her reward, and every test of her vanilla item in the fountain flows
  (and in ``TriForcePoint``, the six-fairy count of ``Meet_GreatFairy``) reads it.

Bool switches: case 0 = true, case 1 = false (as the vanilla flows). Not validated in game.
"""
import io
from functools import partial

from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
from oot_rando.formats.evfl_tools import case_target, event_params_of, links_to, params_by_event, parse_flow

FIRE_STONE_FLOW = 'Event/EventFlow/Get_StoneOfFire.bfevfl.zs'
DARUNIA_GIFT_FLOW = 'Event/EventFlow/Dm_Goron_0030.bfevfl.zs'
EPONA_FLOW = 'Event/EventFlow/SubEvent_GetEponaSong.bfevfl.zs'
BOWLING_FLOW = 'Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs'
FAIRY_CALL_FLOW = 'Event/EventFlow/TriForcePoint.bfevfl.zs'
FAIRY_CALL_GATE = 'IsGet.Item_DinFire'
# Great Fairy flows: (fountain, reward event, vanilla pouch actor).
GREAT_FAIRIES = (
    ('Din', 'Event212', 'Item_DinFire'), ('Power', 'Event141', 'Item_FairyBless_MP'),
    ('Frore', 'Event174', 'Item_FaroreWind'), ('Nayru', 'Event163', 'Item_NayruLove'),
    ('Wisdom', 'Event144', 'Item_FairyBless_MPDouble'), ('Courage', 'Event144', 'Item_FairyBless_DefenseDouble'),
)
GREAT_FAIRY_FLAG_PREFIX = 'RandoGreatFairy_'


def fairy_flow(name):
    return f'Event/EventFlow/Dm_FairyFountain_{name}.bfevfl.zs'


def fairy_flags():
    """``IsGet.<vanilla item>`` → the fairy's own saved flag, for every Great Fairy."""
    return {'IsGet.' + actor: GREAT_FAIRY_FLAG_PREFIX + name for name, _, actor in GREAT_FAIRIES}


def great_fairy_saved_flags():
    """Bools to register in GameData (false in a new save)."""
    return {flag: False for flag in fairy_flags().values()}
TEMPLE_MAP = 'Banc/Market/Market_Adult_Static.bcett.byml.zs'

DARUNIA_GIFT_PLAYED = 'HavePlayedEvent.Dm_Goron_0030'
AFTER_SARIA_PLAY = 'Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp'
TALON_AWAKE = 'HavePlayedEvent.Dm_HrlCastle_0020'
SECOND_MALON = 'IsMalonAppear_HyruleCastleSecondTime'
SHEIK = 'Npc_Hylia_Sheik_Adult'
SHEIK_PRESENCE = 'SageOfForest_IsCompleted_Exp'


class _Chart:
    """An event flow being edited: new events and the parameters they must keep."""

    def __init__(self, raw):
        self.flow = parse_flow(raw)
        self.chart = self.flow.flowchart
        self.expected = params_by_event(self.flow)
        self.events = {e.name: e for e in self.chart.events}

    def event(self, name, kind):
        if name not in self.events:
            raise ValueError('Unexpected event flow: no ' + name)
        event = self.events[name]
        if type(event.data).__name__ != kind:
            raise ValueError(f'Unexpected event flow: {name} is not a {kind}')
        return event

    def fresh(self, name):
        if name in self.events:
            raise ValueError('Story fix already applied: ' + name)

    def actor(self, name):
        from evfl.actor import Actor
        from evfl.common import ActorIdentifier
        from evfl.container import Container
        actor = next((a for a in self.chart.actors if str(a.identifier) == name), None)
        if actor is None:
            actor = Actor()
            actor.identifier = ActorIdentifier(name)
            actor.concurrent_clips = 1
            # A named actor without its parameter container crashes the game.
            actor.params = Container()
            actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
            self.chart.actors.append(actor)
        return actor

    @staticmethod
    def holder(collection, name):
        from evfl.common import StringHolder
        found = next((h for h in collection if h.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found

    def _add(self, name, data, params):
        from evfl.container import Container
        from evfl.event import Event
        self.fresh(name)
        data.params = Container()
        data.params.data = dict(params)
        event = Event()
        event.name, event.data = name, data
        self.chart.events.append(event)
        self.events[name] = event
        self.expected[name] = dict(params)
        return event

    def switch(self, name, query, params, true, false, actor='GameDataActor'):
        from evfl.event import SwitchEvent
        from evfl.util import make_index, make_rindex
        owner = self.actor(actor)
        data = SwitchEvent()
        data.actor = make_rindex(owner)
        data.actor_query = make_rindex(self.holder(owner.queries, query))
        # A case that ends the flow is left out (as the vanilla switches do).
        data.cases = {key: make_index(target) for key, target in ((0, true), (1, false)) if target is not None}
        return self._add(name, data, params)

    def action(self, name, actor, act, params, following):
        from evfl.event import ActionEvent
        from evfl.util import make_index, make_rindex
        owner = self.actor(actor)
        data = ActionEvent()
        data.actor = make_rindex(owner)
        data.actor_action = make_rindex(self.holder(owner.actions, act))
        data.nxt = make_index(following)
        return self._add(name, data, params)

    def set_bool(self, name, flag, value, following):
        return self.action(name, 'GameDataActor', 'EventTriggerSetGameDataBool',
                           {'GameDataName': flag, 'Value': value, 'Index': -1}, following)

    def write(self):
        stream = io.BytesIO()
        self.flow.write(stream)
        result = stream.getvalue()
        checked = parse_flow(result)
        if params_by_event(checked) != self.expected:
            raise ValueError('A story fix changed other parameters.')
        return result, {e.name: e for e in checked.flowchart.events}


def darunia_gift_after_dungeon(raw):
    """``Get_StoneOfFire``: full ocarina prompt and gift while never received.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    check = flow.event('Event39', 'SwitchEvent')
    gift, done = case_target(check, 1), case_target(check, 0)
    if (event_params_of(check) != {'GameDataName': AFTER_SARIA_PLAY} or gift is None or done is None
            or type(gift.data).__name__ != 'ActionEvent'
            or event_params_of(gift).get('EventName') != 'Dm_Goron_0030'):
        raise ValueError("Unexpected Darunia dance continuation.")
    given = flow.switch('RandoDaruniaGiftGiven', 'EventQueryIsGameDataBool',
                        {'GameDataName': DARUNIA_GIFT_PLAYED, 'Index': -1}, done, gift)
    check.data.cases[0] = make_index(given)
    prompt = flow.event('Event82', 'SwitchEvent')
    late, early = case_target(prompt, 0), case_target(prompt, 1)
    if (event_params_of(prompt) != {'GameDataName': AFTER_SARIA_PLAY}
            or late is None or late.name != 'Event278'
            or early is None or early.name != 'Event193'):
        raise ValueError('Unexpected Darunia ocarina prompt dispatch.')
    prompt_given = flow.switch('RandoDaruniaOcarinaGiftGiven', 'EventQueryIsGameDataBool',
                               {'GameDataName': DARUNIA_GIFT_PLAYED, 'Index': -1}, late, early)
    prompt.data.cases[0] = make_index(prompt_given)
    result, events = flow.write()
    written = events['Event39'].data.cases
    switch = events['RandoDaruniaGiftGiven'].data.cases
    if (written[0].v.name != 'RandoDaruniaGiftGiven' or written[1].v.name != gift.name
            or switch[0].v.name != done.name or switch[1].v.name != gift.name
            or events['Event82'].data.cases[0].v.name != prompt_given.name
            or events['Event82'].data.cases[1].v.name != early.name
            or events[prompt_given.name].data.cases[0].v.name != late.name
            or events[prompt_given.name].data.cases[1].v.name != early.name):
        raise ValueError('Darunia gift wrongly chained.')
    return result, {'flow': FIRE_STONE_FLOW, 'switch': 'RandoDaruniaGiftGiven', 'flag': DARUNIA_GIFT_PLAYED}


def keep_fire_quest_forward(raw):
    """``Dm_Goron_0030``: the step ``DodongoCavernOpne`` only while not already past it.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    step = flow.event('Event121', 'ActionEvent')
    if (step.data.actor_action.v.v != 'EventExecuteProgressChallengeStep'
            or event_params_of(step).get('ChallengeName') != 'Get_StoneOfFire'
            or event_params_of(step).get('StepName') != 'DodongoCavernOpne'):
        raise ValueError('Unexpected Darunia gift step.')
    ui = step.data.nxt.v
    if (ui is None or type(ui.data).__name__ != 'ActionEvent'
            or ui.data.actor_action.v.v != 'EventTriggerShowChallengeProgressUI'):
        raise ValueError('Unexpected Darunia gift step continuation.')
    resume = ui.data.nxt.v
    links = links_to(flow.chart, step)
    if resume is None or len(links) != 1 or links[0][1] != 'nxt':
        raise ValueError('Unexpected Darunia gift step links.')
    guard = flow.switch('RandoFireQuestForward', 'EventQueryIsGameDataBoolExp',
                        {'GameDataName': AFTER_SARIA_PLAY}, resume, step)
    links[0][0].data.nxt = make_index(guard)
    result, events = flow.write()
    cases = events['RandoFireQuestForward'].data.cases
    if cases[0].v.name != resume.name or cases[1].v.name != 'Event121':
        raise ValueError('Darunia gift step wrongly guarded.')
    return result, {'flow': DARUNIA_GIFT_FLOW, 'switch': 'RandoFireQuestForward', 'skip_to': resume.name}


def second_malon_after_talon(raw):
    """``GetEponaSong_StepCheck``: Malon's second castle visit only once Talon is awake.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    jabu = flow.event('Event38', 'SwitchEvent')
    appear = case_target(jabu, 1)
    if (event_params_of(jabu) != {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'} or appear is None
            or appear.name != 'Event36' or event_params_of(appear) != {'GameDataName': SECOND_MALON, 'Value': True,
                                                                 'Index': -1}):
        raise ValueError('Unexpected Malon second visit check.')
    away = flow.set_bool('RandoMalonNotYetBack', SECOND_MALON, False, None)
    awake = flow.switch('RandoTalonAwake', 'EventQueryIsGameDataBool',
                        {'GameDataName': TALON_AWAKE, 'Index': -1}, appear, away)
    jabu.data.cases[1] = make_index(awake)
    result, events = flow.write()
    cases = events['RandoTalonAwake'].data.cases
    if (events['Event38'].data.cases[1].v.name != 'RandoTalonAwake' or cases[0].v.name != 'Event36'
            or cases[1].v.name != 'RandoMalonNotYetBack'
            or getattr(events['RandoMalonNotYetBack'].data.nxt, 'v', None) is not None):
        raise ValueError('Malon second visit wrongly chained.')
    return result, {'flow': EPONA_FLOW, 'switch': 'RandoTalonAwake', 'flag': TALON_AWAKE}


def open_bombchu_bowling(raw):
    """``AfterWakeUp``: the alley plays whether Dodongo's Cavern is done or not.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    gate = flow.event('Event137', 'SwitchEvent')
    opened, closed = case_target(gate, 0), case_target(gate, 1)
    if (event_params_of(gate) != {'GameDataName': 'Get_StoneOfFire_IsCompleted_Exp'} or opened is None
            or closed is None or opened is closed):
        raise ValueError('Unexpected Bombchu Bowling gate.')
    gate.data.cases[1] = make_index(opened)
    result, events = flow.write()
    cases = events['Event137'].data.cases
    if cases[0].v.name != opened.name or cases[1].v.name != opened.name:
        raise ValueError('Bombchu Bowling gate not opened.')
    return result, {'flow': BOWLING_FLOW, 'gate': 'Event137', 'closed_talk': closed.name}


def open_great_fairies(raw):
    """``TriForcePoint``: every Great Fairy answers Zelda's Lullaby, Din's Fire held or not.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    gate = flow.event('Event8', 'SwitchEvent')
    called, refused = case_target(gate, 0), case_target(gate, 1)
    ability = flow.event('Event132', 'SwitchEvent')
    if (event_params_of(gate) != {'GameDataName': FAIRY_CALL_GATE, 'Index': -1} or called is None
            or refused is None or called is refused or case_target(ability, 2) is not called):
        raise ValueError('Unexpected Great Fairy call gate.')
    gate.data.cases[1] = make_index(called)
    result, events = flow.write()
    cases = events['Event8'].data.cases
    if cases[0].v.name != called.name or cases[1].v.name != called.name:
        raise ValueError('Great Fairy call gate not opened.')
    return result, {'flow': FAIRY_CALL_FLOW, 'gate': 'Event8', 'flag': FAIRY_CALL_GATE,
                    'refusal': refused.name}


def _read_fairy_flags(flow):
    """Every Bool query of an item a Great Fairy gives now reads that fairy's flag."""
    replaced = []
    for name, event in flow.events.items():
        data = event.data
        if type(data).__name__ != 'SwitchEvent' or name.startswith('Rando'):
            continue
        if data.actor_query.v.v != 'EventQueryIsGameDataBool':
            continue
        params = data.params.data
        target = fairy_flags().get(params.get('GameDataName'))
        if target is None:
            continue
        if params.get('Index') != -1:
            raise ValueError('Unexpected Great Fairy item query: ' + name)
        params['GameDataName'] = target
        flow.expected[name]['GameDataName'] = target
        replaced.append(name)
    return sorted(replaced)


def _fairy_reward_flag(name, reward, actor):
    """``Dm_FairyFountain_<name>``: the fairy's flag set just before her reward; her
    item tests read it. Returns a fix ``raw -> (bytes, report)``."""
    def fix(raw):
        from evfl.util import make_index
        flow = _Chart(raw)
        gift = flow.event(reward, 'SubFlowEvent')
        # A song placed here is already a silent add (patching/song_adapter.py: text_get).
        posed = (gift.data.res_flowchart_name == 'Dm_SY_GetInEvent'
                 and gift.data.entry_point_name.startswith('GetInEvent'))
        silent = (gift.data.res_flowchart_name, gift.data.entry_point_name) == (
            'GetPouchContent', 'GetPouchContentByActorName')
        if not (posed or silent) or 'ActorName' not in event_params_of(gift):
            raise ValueError('Unexpected Great Fairy reward: ' + name)
        links = links_to(flow.chart, gift)
        if not links or any(kind == 'entry' for _, kind, _ in links):
            raise ValueError('Unexpected Great Fairy reward links: ' + name)
        flag = GREAT_FAIRY_FLAG_PREFIX + name
        marker = flow.set_bool('RandoGreatFairyGiven', flag, True, gift)
        for event, kind, key in links:
            if kind == 'nxt':
                event.data.nxt = make_index(marker)
            elif kind == 'case':
                event.data.cases[key] = make_index(marker)
            else:
                event.data.forks[key] = make_index(marker)
        replaced = _read_fairy_flags(flow)
        if not any(flow.events[e].data.params.data['GameDataName'] == flag for e in replaced):
            raise ValueError('Great Fairy without a test of her own item: ' + name)
        result, events = flow.write()
        given = events['RandoGreatFairyGiven']
        if given.data.nxt.v.name != reward or any(
                e.data.params is not None and e.data.params.data.get('GameDataName') == 'IsGet.' + actor
                for e in events.values() if type(e.data).__name__ == 'SwitchEvent'):
            raise ValueError('Great Fairy flag wrongly chained: ' + name)
        return result, {'flow': fairy_flow(name), 'flag': flag, 'before': reward, 'queries': replaced}
    return fix


def great_fairy_count(raw):
    """``TriForcePoint``: the six fairies of ``Check_Complete`` counted by their own
    flags (plus the opened call gate Event8, both cases alike).

    Applied after ``open_great_fairies`` (same flow). Returns (bytes, report)."""
    flow = _Chart(raw)
    replaced = _read_fairy_flags(flow)
    if replaced != sorted(['Event8', 'Event136', 'Event137', 'Event138', 'Event139', 'Event140', 'Event141']):
        raise ValueError('Unexpected Great Fairy count in TriForcePoint.')
    result, _ = flow.write()
    return result, {'flow': FAIRY_CALL_FLOW, 'queries': replaced}


def open_and_count_great_fairies(raw):
    """``TriForcePoint``: every fairy answers the lullaby; she is counted by her own flag."""
    opened, report = open_great_fairies(raw)
    result, counted = great_fairy_count(opened)
    return result, dict(report, queries=counted['queries'])


# The presence seeds up to 0.6.5 gave the Temple of Time Sheik (verify still reads it back).
SHEIK_PRESENCE_ENTRY = {'FlagName': SHEIK_PRESENCE, 'IsCheckLazy': False, 'IsNegation': False}


# --- Zora's River mouth: no invisible wall for adult Link -------------------------
# Seven ``FldObj_AirWall_Player_GenerateNavMesh`` stand along the fence at the river
# mouth (ZoraRiver_Adult_Static, x -88..-56, z 5..7, baked in the X3_Z4 static
# compound), in one SimultaneousGroup with the two ``Obj_BrokenRock_A_01`` boulders.
# AP lets adult Link hop the fence (``is_adult or has_explosives``); the 0.6.2 logic
# asked for the boulder broken instead, but the wall still stopped adult Link in game
# (Discord, 16/11). Each wall now only exists for child Link (``Sequence_IsChildhood``,
# never true in the adult map), the way Mido's air wall depends on its flag. The child
# map keeps its walls: child Link still needs explosives, as in AP. Not validated in game.
ZORA_RIVER_MAP = 'Banc/ZoraRiver/ZoraRiver_Adult_Static.bcett.byml.zs'
ZORA_RIVER_WALL = 'FldObj_AirWall_Player_GenerateNavMesh'
ZORA_RIVER_WALLS = (4565321854739336115, 7850395794748438732, 7982339630050931435, 9371429508151251838,
                    11266001672277786960, 13781426553798151043, 14077907143773739344)
ZORA_RIVER_WALL_PRESENCE = 'Sequence_IsChildhood'
ZORA_RIVER_WALL_PRESENCE_ENTRY = {'FlagName': ZORA_RIVER_WALL_PRESENCE, 'IsCheckLazy': False,
                                  'IsNegation': False}
# The child map has the same seven walls (own hashes, same places, beside the same
# two boulders). They now only exist for adult Link (``Sequence_IsChildhood``
# negated, never true in the child map): no invisible wall at the river mouth for
# either age. The logic is unchanged (``ZR Front -> Zora River`` still asks for the
# boulder broken, remake.json) until passing over the fence is seen in game.
ZORA_RIVER_CHILD_MAP = 'Banc/ZoraRiver/ZoraRiver_Child_Static.bcett.byml.zs'
ZORA_RIVER_CHILD_WALLS = (1671256346243721333, 2863011381430310501, 4942866467657729468, 8855423962460166888,
                          12374977777450469396, 14519305071033520687, 15623121253783701078)
ZORA_RIVER_CHILD_WALL_PRESENCE_ENTRY = dict(ZORA_RIVER_WALL_PRESENCE_ENTRY, IsNegation=True)


def zora_river_wall_edits(root, walls=None, presence=None):
    """``patch_strings`` edits: the river mouth ``walls`` (default: the adult map's)
    given ``presence`` (default: child-only).

    Returns (edits, actor indices)."""
    walls = ZORA_RIVER_WALLS if walls is None else walls
    presence = ZORA_RIVER_WALL_PRESENCE_ENTRY if presence is None else presence
    found = {actor.get('Hash'): i for i, actor in enumerate(root.get('Actors', []))
             if actor.get('Hash') in walls}
    if set(found) != set(walls):
        raise ValueError("Zora's River mouth walls not found.")
    edits = []
    for ident in walls:
        actor = root['Actors'][found[ident]]
        if actor.get('Gyaml') != ZORA_RIVER_WALL or 'Presence' in actor:
            raise ValueError("Unexpected Zora's River mouth wall.")
        base = ('Actors', found[ident], 'Presence')
        edits += [{'path': base + (key,), 'before': None, 'after': value}
                  for key, value in presence.items()]
    return edits, sorted(found.values())


def zora_river_child_wall_edits(root):
    """The child map's river mouth walls, adult-only (see above)."""
    return zora_river_wall_edits(root, ZORA_RIVER_CHILD_WALLS, ZORA_RIVER_CHILD_WALL_PRESENCE_ENTRY)


# --- Lake Hylia island tree: no invisible wall for the Longshot ----------------------
# One ``FldObj_AirWall_Hookshot`` covers the dead tree of the Gossip Stone island
# (HyruleField_Adult_Dynamic, at -196.3, 144.8, 515.4; its Gold Skulltula is at y 150.3).
# Its Presence is ``WaterTemple_Room07_00`` negated: the wall only goes away once that
# flag is set, by the Longshot chest of the Dark Link room
# (``WaterTemple_Level_Room_07_Prefab_aa21``: TreasureBox OpenState -> SetBoolTrue).
# Vanilla always opens that chest before holding the Longshot; with the Longshot found
# elsewhere the tree stayed out of reach (``LH GS Tree``: Longshot at night). The adult
# map's wall now only exists for child Link (never true there), like the Zora's River
# mouth walls. The child map keeps it (child Link has no Longshot). Not validated in game.
LAKE_TREE_MAP = 'Banc/HyruleField/HyruleField_Adult_Dynamic.bcett.byml.zs'
LAKE_TREE_WALL = 'FldObj_AirWall_Hookshot'
LAKE_TREE_WALL_HASH = 9829790505452123995
LAKE_TREE_WALL_VANILLA = {'FlagName': 'WaterTemple_Room07_00', 'IsCheckLazy': False, 'IsNegation': True}
LAKE_TREE_WALL_PRESENCE_ENTRY = {'FlagName': 'Sequence_IsChildhood', 'IsCheckLazy': False, 'IsNegation': False}


def lake_tree_wall_edits(root):
    """``patch_strings`` edits: the island tree's hookshot wall of the adult map, child-only.

    Returns (edits, actor index)."""
    found = [i for i, actor in enumerate(root.get('Actors', [])) if actor.get('Hash') == LAKE_TREE_WALL_HASH]
    if len(found) != 1:
        raise ValueError('Lake Hylia tree wall not found.')
    actor = root['Actors'][found[0]]
    if actor.get('Gyaml') != LAKE_TREE_WALL or actor.get('Presence') != LAKE_TREE_WALL_VANILLA:
        raise ValueError('Unexpected Lake Hylia tree wall.')
    base = ('Actors', found[0], 'Presence')
    edits = [{'path': base + (key,), 'before': LAKE_TREE_WALL_VANILLA[key], 'after': value}
             for key, value in LAKE_TREE_WALL_PRESENCE_ENTRY.items()
             if value != LAKE_TREE_WALL_VANILLA[key]]
    return edits, found[0]


# --- Zelda's escape (DoorOfTime) on the stones held ----------------------------
# ``DoorOfTime/DoorOfTime_CheckStoneNum`` runs only at the end of Dodongo's Cavern and
# Jabu-Jabu's Belly and reads both dungeon *quests*: with the stones found elsewhere,
# Zelda never fled (15/11, Discord report). Its Step03 branch moves DoorOfTime to
# ``Step03``, raises the Hyrule Field drawbridge (``IsHyruleFieldBridgeClose``) and
# sets ``DoorOfTime_GetStoneCount`` to 0; the drawbridge area then starts
# ``HyruleField_DoorOfTime_Escape`` (Step04), then the moat ``..._GetOcarinaOfTime``.
# It reads only ``Get_StoneOfFire`` and ``Get_StoneOfWater`` (both done: Step03, one:
# Step2_1 or Step2_2, none: 2 stones left); the Kokiri Emerald and the Deku Tree are
# never checked. The ``spiritual_stones`` option picks what the escape asks for (STONE_SETS):
# every stone (default) or, as the native check, the Goron Ruby and the Zora Sapphire.
# The same branch now also runs on those stones held, checked at every item get
# (``ActionGuide/ActionGuide``), at the end of Impa's send-off and at every dungeon end
# (before the native check), once DoorOfTime is past ``Step01`` (send-off done) and not
# past ``Step2_2`` (before Step03; ``IsAfter`` is strict, as Darunia's vanilla gift
# shows). The Hyrule Field drawbridge area (``HyruleField_Child_Prefab_0ce5``) exists
# only while the current step *is* Step03 (``HoldChallengeCurrentStepCheckOrder``
# IsEqual): the dungeon quests are never read. The native check is skipped once
# Step03 is reached, so a later dungeon end never moves it back (vanilla never runs it
# there). The send-off moves Get_StoneOfFire to ``KakarikoVillageNpc``: now only while
# that quest has not started (vanilla order), so Dodongo's Cavern done first stays done.
#
# 16/11 (Discord, 0.6.4): Zelda still waited for the dungeons. The added Step03 request
# lacked ``IsWaitEnd`` (the native one, which works at the dungeon end, has it): it now
# copies the native parameters exactly. Two talks also moved DoorOfTime back to
# ``Srep2_1_1`` (Zelda's ``AboutWaterStone`` with the Fire quest done, Saria's Song):
# both are now skipped once DoorOfTime is past ``Step2_1`` (:func:`door_of_time_forward`).
#
# 17/11 (Discord, 0.6.5): the send-off check works in game (back-to-back scenes), but
# (1) the native dungeon-end check still gave Step03 on both dungeon quests without the
# Goron Ruby: its Step03 branch is now cut (the stones, checked first, are the only way);
# (2) the last stone got after the send-off (HC Great Fairy) never triggered the
# escape: the item-get check is not proven, so talking to Zelda checks the stones too
# (:func:`zelda_escape_on_talk`).
DOOR_FLOW = 'Event/EventFlow/DoorOfTime.bfevfl.zs'
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
# Stone choices shared by the door and escape (older seeds retain separate settings).
STONE_SETS = {'all': ('Item_Stone_Forest', 'Item_Stone_Fire', 'Item_Stone_Water'),
              'vanilla': ('Item_Stone_Fire', 'Item_Stone_Water'), 'song': ()}   # the native check's two quests
STONE_FLAG_PREFIX = 'IsGet.'   # saved when the stone is obtained, however it is given
DOOR_STARTED = 'DoorOfTime_IsAfter_Step01_Exp'
DOOR_BEFORE_ESCAPE = 'DoorOfTime_IsAfter_Step2_2_Exp'
BRIDGE_CLOSED = 'IsHyruleFieldBridgeClose'
FIRE_QUEST_STARTED = 'Get_StoneOfFire_IsAfter_Ready_Exp'
# ``DoorOfTime/Event37``, the native Step03 request, parameter for parameter.
DOOR_STEP03_PARAMS = {'IsIgnoreCompletedChallenge': False, 'IsIgnoreChallengeProgressUI': False,
                      'ChallengeName': 'DoorOfTime', 'IsWaitEnd': True, 'StepName': 'Step03'}


def escape_stones(full):
    """The stones Zelda's escape asks for, from the (stored) full randomizer options."""
    return STONE_SETS[rando_options.escape_requirement(full)]


def _stone_check(flow, prefix, stones, following, done=...):
    """Events: DoorOfTime to Step03 when started, before Step03, and the ``stones`` held.

    ``following``: where the flow goes on when the check does not pass; ``done``: after
    Step03 (``following`` by default)."""
    from evfl.util import make_index
    done = following if done is ... else done
    step = flow.action(prefix + 'Step03', 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep',
                       DOOR_STEP03_PARAMS, None)
    bridge = flow.set_bool(prefix + 'Bridge', BRIDGE_CLOSED, True, None)
    count = flow.action(prefix + 'Count', 'GameDataActor', 'EventTriggerSetGameDataInt',
                        {'GameDataName': 'DoorOfTime_GetStoneCount', 'Value': 0, 'Index': -1}, done)
    step.data.nxt, bridge.data.nxt = make_index(bridge), make_index(count)
    check = step
    for index, stone in reversed(list(enumerate(stones))):
        # The saved ``IsGet.<actor>`` flag: the pouch only answers to pouch names, never
        # to the actor name (EventQueryIsExistInPouch on Item_Stone_* was always false,
        # so Zelda still waited for the bosses; 15/11 report).
        check = flow.switch(f'{prefix}Stone{index}', 'EventQueryIsGameDataBool',
                            {'GameDataName': STONE_FLAG_PREFIX + stone, 'Index': -1}, check, following)
    before = flow.switch(prefix + 'BeforeEscape', 'EventQueryIsGameDataBoolExp',
                         {'GameDataName': DOOR_BEFORE_ESCAPE}, following, check)
    return flow.switch(prefix + 'Started', 'EventQueryIsGameDataBoolExp',
                       {'GameDataName': DOOR_STARTED}, before, following)


def zelda_escape_on_item_get(raw, stones):
    """``ActionGuide/ActionGuide``: the stone check first, at every item get. Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entry = {e.name: e for e in flow.chart.entry_points}.get('ActionGuide')
    if entry is None or entry.main_event.v is None:
        raise ValueError('Unexpected ActionGuide flow.')
    first = entry.main_event.v
    entry.main_event = make_index(_stone_check(flow, 'RandoDoorStones', stones, first))
    result, events = flow.write()
    start = {e.name: e for e in parse_flow(result).flowchart.entry_points}['ActionGuide'].main_event.v
    if start.name != 'RandoDoorStonesStarted' or events['RandoDoorStonesCount'].data.nxt.v.name != first.name:
        raise ValueError('Stone check wrongly chained in ActionGuide.')
    return result, {'flow': ACTION_GUIDE_FLOW, 'start': start.name, 'stones': list(stones)}


def zelda_escape_door_flow(raw, stones=STONE_SETS['all']):
    """``DoorOfTime``: stone check after the send-off, native check never backwards.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entries = {e.name: e for e in flow.chart.entry_points}
    native = entries.get('DoorOfTime_CheckStoneNum')
    if native is None or native.main_event.v is None or native.main_event.v.name != 'Event38':
        raise ValueError('Unexpected DoorOfTime stone check.')
    # Dungeon end: the stones first (Step03 and done), else the native check (vanilla).
    dungeon_end = _stone_check(flow, 'RandoDungeonEndStones', stones, native.main_event.v, done=None)
    guard = flow.switch('RandoDoorCheckForward', 'EventQueryIsGameDataBoolExp',
                        {'GameDataName': DOOR_BEFORE_ESCAPE}, None, dungeon_end)
    native.main_event = make_index(guard)
    # Native check with both dungeon quests done (Event39 case true): Step03 (Event37)
    # only through the stones, already checked above; the dungeons alone no longer
    # open it (Discord 17/11: escape and Temple of Time without the Goron Ruby).
    both = flow.event('Event39', 'SwitchEvent')
    step03 = flow.event('Event37', 'ActionEvent')
    if (event_params_of(both) != {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'}
            or getattr(both.data.cases.get(0), 'v', None) is not step03
            or event_params_of(step03).get('StepName') != 'Step03' or len(links_to(flow.chart, step03)) != 1):
        raise ValueError('Unexpected native DoorOfTime Step03.')
    del both.data.cases[0]
    # Send-off: Step02 (Event7), then Get_StoneOfFire KakarikoVillageNpc (Event62), end.
    step02, fire = flow.event('Event7', 'ActionEvent'), flow.event('Event62', 'ActionEvent')
    if (event_params_of(step02).get('StepName') != 'Step02' or step02.data.nxt.v is not fire
            or event_params_of(fire).get('StepName') != 'KakarikoVillageNpc'
            or getattr(fire.data.nxt, 'v', None) is not None or len(links_to(flow.chart, fire)) != 1):
        raise ValueError('Unexpected Impa send-off end.')
    send_off = _stone_check(flow, 'RandoSendOffStones', stones, None)
    fire.data.nxt = make_index(send_off)
    started = flow.switch('RandoFireQuestStarted', 'EventQueryIsGameDataBoolExp',
                          {'GameDataName': FIRE_QUEST_STARTED}, send_off, fire)
    step02.data.nxt = make_index(started)
    result, events = flow.write()
    if (events['Event7'].data.nxt.v.name != 'RandoFireQuestStarted'
            or events['Event62'].data.nxt.v.name != 'RandoSendOffStonesStarted'
            or events['RandoDoorCheckForward'].data.cases[1].v.name != 'RandoDungeonEndStonesStarted'
            or events['RandoDungeonEndStonesStarted'].data.cases[1].v.name != 'Event38'
            or events['RandoDungeonEndStonesCount'].data.nxt.v is not None):
        raise ValueError('DoorOfTime stone checks wrongly chained.')
    return result, {'flow': DOOR_FLOW, 'native_guard': 'RandoDoorCheckForward', 'send_off': 'RandoSendOffStones',
                    'dungeon_end': 'RandoDungeonEndStones'}


def zelda_escape_on_talk(raw, stones=STONE_SETS['all']):
    """``Npc_Hylia_Zelda_Child/Talk``: the stone check first, at every talk to Zelda.

    17/11 (Discord, 0.6.5): the last stone got after the send-off (from a Great Fairy)
    never moved DoorOfTime to Step03; the item-get check (``ActionGuide``, a sub-flow
    of the get flows) is not validated in game, the send-off check (a main flow) is.
    Talking to Zelda again now runs the same check. Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entry = {e.name: e for e in flow.chart.entry_points}.get('Talk')
    if entry is None or entry.main_event.v is None or entry.main_event.v.name != 'Event99':
        raise ValueError('Unexpected Zelda talk flow.')
    first = entry.main_event.v
    entry.main_event = make_index(_stone_check(flow, 'RandoTalkStones', stones, first))
    result, events = flow.write()
    start = {e.name: e for e in parse_flow(result).flowchart.entry_points}['Talk'].main_event.v
    if start.name != 'RandoTalkStonesStarted' or events['RandoTalkStonesCount'].data.nxt.v.name != first.name:
        raise ValueError('Stone check wrongly chained in the Zelda talk.')
    return result, {'flow': ZELDA_FLOW, 'start': start.name, 'stones': list(stones)}


# --- Stones in the menu after Gohma ---------------------------------------------
# ``Dm_Kokiri_0130`` (Deku Tree's death, vanilla Kokiri Emerald) ends with the quest
# menu presentation of the first stone (Event56 wait -> Event52
# ``UISystemActor.EventOpenPerformanceImportantMenu``), the only stone scene with it.
# With stones found before Gohma and her reward shuffled, it showed the three stones
# on their pedestal, then none (Discord 15/11, "Spiritual Stones disappeared"; the save
# still held them). The presentation is now skipped. Not validated in game.
GOHMA_STONE_FLOW = 'Event/EventFlow/Dm_Kokiri_0130.bfevfl.zs'


def skip_stone_menu_presentation(raw):
    """``Dm_Kokiri_0130``: no quest menu presentation at the end. Returns (bytes, report)."""
    flow = _Chart(raw)
    wait, menu = flow.event('Event56', 'ActionEvent'), flow.event('Event52', 'ActionEvent')
    if (menu.data.actor_action.v.v != 'EventOpenPerformanceImportantMenu' or wait.data.nxt.v is not menu
            or getattr(menu.data.nxt, 'v', None) is not None or len(links_to(flow.chart, menu)) != 1):
        raise ValueError('Unexpected Gohma stone scene end (already patched?).')
    wait.data.nxt.v = None
    result, events = flow.write()
    if getattr(events['Event56'].data.nxt, 'v', None) is not None:
        raise ValueError('Stone menu presentation still chained.')
    return result, {'flow': GOHMA_STONE_FLOW, 'skipped': 'Event52'}


# --- Master Sword pedestal: back to child before the Forest Temple --------------
# The adult pedestal's put-in prompt (``Obj_TimeTemple_MasterSword_A_01``) lives in
# ``Market_Adult_Prefab_89da``: node 0 reads ``SageOfForest_IsCompleted_Exp``, node 1
# inverts it into the attention's ``Logic_Delete``. Link could not go back to child
# until the Forest Temple was finished (Discord 15-16/11, medallion not enough), while
# the logic gives free time travel. Node 0 now reads ``AllSage_IsAfter_Ready_Exp``,
# true from the first adult arrival (``Market_Adult_AllSage_Start``, AllSage Step01).
# The Area before the pedestal is the Prelude of Light trigger (``_edc2``, same flag):
# it is kept. Raw file (not compressed), rewritten byte for byte but this string.
PEDESTAL_MODULE = 'Logic/Market_Adult_Prefab_89da.logic.module.ainb'
PEDESTAL_BEFORE = 'SageOfForest_IsCompleted_Exp'
PEDESTAL_GATE = 'AllSage_IsAfter_Ready_Exp'

# The adult Sheik of the Temple of Time (``Market_Adult_Prefab_7f43``, ``ActorLogicNpc``)
# stands 1.4 m from the sword (Market_Adult_Static, (139.0, 106.4, -34.0) for the sword's
# (137.6, 106.6, -34.0)) until he teaches the Prelude of Light (``Logic_Delete`` = Bool
# ``Market_Adult_GetLightPrelude``). In vanilla the put-in prompt only came after the
# Forest Temple, and he never stood beside it; with the prompt from the first adult
# arrival, he took its place and no prompt showed (20/11). He now stays only for his
# two scenes: the first adult arrival (AllSage before ``Ready``) and the Prelude (Forest
# Medallion held, Prelude not taught). Node 2, an unused BoolExp reader of the module,
# reads that condition and deletes him; node 1 is left unread. Not validated in game.
SHEIK_TEMPLE_MODULE = 'Logic/Market_Adult_Prefab_7f43.logic.module.ainb'
SHEIK_TEMPLE_PRELUDE = 'Market_Adult_GetLightPrelude'
SHEIK_TEMPLE_GONE = 'RandoSheikTemple_Gone'


def _sheik_temple_program():
    """Postfix BoolExp: Prelude taught OR (AllSage after Ready AND NOT Forest Medallion)."""
    from oot_rando.patching.soul_adapter import murmur3
    return [[0, murmur3(SHEIK_TEMPLE_PRELUDE)], [10, murmur3(PEDESTAL_GATE)],
            [0, murmur3(PRELUDE_MEDAL)], [5], [3], [4]]


def sheik_temple_expression(gamedata_raw):
    """GameData with the BoolExp :data:`SHEIK_TEMPLE_GONE`. Returns (bytes, report)."""
    from oot_rando.patching.soul_adapter import murmur3
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    if murmur3(SHEIK_TEMPLE_GONE) in known:
        raise ValueError('Temple Sheik condition already present.')
    bools = {int(e['Hash']) for e in data['Bool']}
    expressions = {int(e['Hash']) for e in data['BoolExp']}
    if (murmur3(SHEIK_TEMPLE_PRELUDE) not in bools or murmur3(PRELUDE_MEDAL) not in bools
            or murmur3(PEDESTAL_GATE) not in expressions):
        raise ValueError('Temple Sheik condition: flag missing from the game data.')
    data['BoolExp'].append({'Hash': byml_codec.U32(murmur3(SHEIK_TEMPLE_GONE)), 'ResetTypeValue': 0,
                            'SaveFileIndex': -1,
                            'Values': [[byml_codec.U64(v) for v in step] for step in _sheik_temple_program()]})
    return byml_codec.dump(document), {'expression': SHEIK_TEMPLE_GONE, 'prelude': SHEIK_TEMPLE_PRELUDE,
                                       'gate': PEDESTAL_GATE, 'medallion': PRELUDE_MEDAL}


def sheik_temple_applied(gamedata_raw):
    from oot_rando.patching.soul_adapter import murmur3
    entries = {int(e['Hash']): e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
    entry = entries.get(murmur3(SHEIK_TEMPLE_GONE))
    return entry is not None and [[int(v) for v in s] for s in entry['Values']] == _sheik_temple_program()


def sheik_leaves_the_pedestal(raw):
    """``Market_Adult_Prefab_7f43``: the temple Sheik deleted on :data:`SHEIK_TEMPLE_GONE`.

    Returns (bytes, report)."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    if ([n['Name'] for n in nodes] != ['ActorLogicNpc', 'HoldGameDataGetBoolSimple', 'HoldGameDataGetBoolExpSimple']
            or ainb_to_binary(copy.deepcopy(document)) != raw):
        raise ValueError('Unexpected temple Sheik logic module.')
    npc, prelude, reader = nodes
    delete = [p for p in npc['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete']
    name = reader['Parameters']['Inputs']['String'][0]
    if (len(delete) != 1 or (delete[0]['Node Index'], delete[0]['Output Index']) != (1, 0)
            or prelude['Parameters']['Inputs']['String'][0]['Default Value'] != SHEIK_TEMPLE_PRELUDE
            or (name['Name'], name['Default Value']) != ('GameDataNameBoolExp', PEDESTAL_GATE)
            or reader['Parameters']['Outputs']['Bool'] != [{'Name': 'Bool', 'Is Output': False}]
            or npc.get('Queries') != [1] or npc.get('Plugs') != {'Generic': [{'Node Index': 1, 'Name': 'Logic_Delete'}]}):
        raise ValueError('Unexpected temple Sheik wiring (already patched?).')
    expected = copy.deepcopy(document)
    npc, prelude, reader = expected['Nodes']
    next(p for p in npc['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete')['Node Index'] = 2
    npc['Queries'] = [2]
    npc['Plugs'] = {'Generic': [{'Node Index': 2, 'Name': 'Logic_Delete'}]}
    # A node only computes its flagged outputs: the reader is now read, node 1 no longer.
    reader['Parameters']['Inputs']['String'][0]['Default Value'] = SHEIK_TEMPLE_GONE
    reader['Parameters']['Outputs']['Bool'][0]['Is Output'] = True
    prelude['Parameters']['Outputs']['Bool'][0]['Is Output'] = False
    result = ainb_to_binary(copy.deepcopy(expected))
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Temple Sheik module wrongly rewritten.')
    return result, {'module': SHEIK_TEMPLE_MODULE, 'delete': SHEIK_TEMPLE_GONE}


# Zelda's revelation: inventory, independent of which bosses granted the rewards.
LIGHT_ARROWS_MODULE = 'Logic/Market_Adult_Prefab_c668.logic.module.ainb'
LIGHT_ARROWS_MEDALS = ('IsGet.Item_Medal_Shadow', 'IsGet.Item_Medal_Spirit')
LIGHT_ARROWS_PLAYED = 'HavePlayedEvent.Dm_TimeTemple_0135'
PRELUDE_MODULE = 'Logic/Market_Adult_Prefab_edc2.logic.module.ainb'
PRELUDE_MEDAL = 'IsGet.Item_Medal_Forest'
PRELUDE_LATER_STEP = 'AllSage_IsAfter_Step01_01_Exp'


def prelude_keeps_later_sage_progress(raw):
    """Teaching Prelude after Zelda's revelation must not roll AllSage back."""
    from evfl.util import make_index
    flow = _Chart(raw)
    teaching = flow.event('Event37', 'ActionEvent')
    rollback = flow.event('Event34', 'ActionEvent')
    if (event_params_of(teaching).get('EventName') != 'Dm_MelodyGet_Shine'
            or teaching.data.nxt.v is not rollback
            or rollback.data.actor_action.v.v != 'EventExecuteRollbackChallengeStep'
            or event_params_of(rollback).get('ChallengeName') != 'AllSage'
            or event_params_of(rollback).get('ChallengeStep') != 'Step01_01'):
        raise ValueError('Unexpected Prelude quest rollback (already patched?).')
    gate = flow.switch('RandoPreludeLaterSages', 'EventQueryIsGameDataBoolExp',
                       {'GameDataName': PRELUDE_LATER_STEP}, None, rollback)
    teaching.data.nxt = make_index(gate)
    result, _ = flow.write()
    return result, {'gate': PRELUDE_LATER_STEP, 'rollback': 'Event34'}


def prelude_on_forest_medallion(raw):
    """The native one-shot Prelude area checks the Forest Medallion, not its boss."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    if len(nodes) != 5 or nodes[3]['Name'] != 'HoldGameDataGetBoolExpSimple':
        raise ValueError('Unexpected Prelude trigger module (already patched?).')
    gate = nodes[3]['Parameters']['Inputs']['String'][0]
    if (gate['Name'], gate['Default Value']) != ('GameDataNameBoolExp', PEDESTAL_BEFORE):
        raise ValueError('Unexpected Prelude story gate.')
    expected = copy.deepcopy(document)
    node = expected['Nodes'][3]
    node['Name'] = 'HoldGameDataGetBoolSimple'
    node['Parameters']['Inputs']['String'][0].update(
        {'Name': 'GameDataNameBool', 'Default Value': PRELUDE_MEDAL})
    node['Parameters']['Inputs']['Int'] = [{'Name': 'GameDataArrayIndex', 'Default Value': -1,
        'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}]
    result = ainb_to_binary(copy.deepcopy(expected))
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Prelude trigger wrongly rewritten.')
    return result, {'module': PRELUDE_MODULE, 'medallion': PRELUDE_MEDAL}


# --- Sheik in Kakariko: the burning village on the three medallions -------------
# Entering adult Kakariko (Hyrule Field, Graveyard, Death Mountain Trail entrances:
# ``AddEventFlag`` / ``AddEventName`` of ``FieldAndDungeonEntranceEventRequestActor``)
# plays ``Dm_SY_BancChangeArrive/KakarikoVillage_Arrive`` (Dm_Kakariko_0030, the
# flashback, then the burnt banc booted on ``KakarikoVillage_MelodyGet_Shadow``,
# Nocturne of Shadow) while the GameData BoolExp ``SageOfShadow_BurningEventShouldPlayed``
# holds: adult AND the three sages awakened (an unnamed BoolExp of
# ``SageOf{Forest,Fire,Water}_IsCompleted_Exp``) AND the scene never played. The burnt
# banc itself is chosen by ``Sequence_IsAlternative_KakarikoAdult`` (adult AND the same
# sages). Both now read the Forest, Fire and Water Medallions held instead of the
# sages, whichever bosses (or other sources) gave them. Not validated in game.
KAKARIKO_BURNING = 'SageOfShadow_BurningEventShouldPlayed'
KAKARIKO_ALTERNATIVE = 'Sequence_IsAlternative_KakarikoAdult'
KAKARIKO_SAGES = 1813060025       # BoolExp: SageOfForest/Fire/Water_IsCompleted_Exp, AND, AND
KAKARIKO_MEDALS = ('IsGet.Item_Medal_Forest', 'IsGet.Item_Medal_Fire', 'IsGet.Item_Medal_Water')


def _kakariko_programs():
    """{BoolExp name: (vanilla program, patched program)}; push Bool 0 / BoolExp 10, NOT 5, AND 3."""
    from oot_rando.patching.soul_adapter import murmur3
    adult = [[0, murmur3('Sequence_IsChildhood')], [5]]
    sages = [[10, KAKARIKO_SAGES]]
    medals = [[0, murmur3(name)] for name in KAKARIKO_MEDALS] + [[3], [3]]
    not_played = [[0, murmur3('HavePlayedEvent.Dm_Kakariko_0030')], [5], [3]]
    return {
        KAKARIKO_BURNING: (adult + sages + not_played + [[3]], adult + medals + not_played + [[3]]),
        KAKARIKO_ALTERNATIVE: (adult + sages + [[3]], adult + medals + [[3]]),
    }


def kakariko_burning_on_medallions(gamedata_raw):
    """GameData where Kakariko's burning scene and burnt banc follow the three medallions.

    Returns (bytes, report)."""
    from oot_rando.patching.soul_adapter import murmur3
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    bools = {int(e['Hash']) for e in data['Bool']}
    if any(murmur3(name) not in bools for name in KAKARIKO_MEDALS):
        raise ValueError('Medallion flag missing from the game data.')
    entries = {int(e['Hash']): e for e in data['BoolExp']}
    for name, (vanilla, patched) in _kakariko_programs().items():
        entry = entries.get(murmur3(name))
        if entry is None or [[int(v) for v in step] for step in entry['Values']] != vanilla:
            raise ValueError('Unexpected Kakariko burning condition (already patched?): ' + name)
        entry['Values'] = [[byml_codec.U64(v) for v in step] for step in patched]
    result = byml_codec.dump(document)
    check = {int(e['Hash']): e for e in byml_codec.load(result)['root']['Data']['BoolExp']}
    for name, (_, patched) in _kakariko_programs().items():
        if [[int(v) for v in step] for step in check[murmur3(name)]['Values']] != patched:
            raise ValueError('Kakariko burning condition wrongly rewritten: ' + name)
    return result, {'expressions': [KAKARIKO_BURNING, KAKARIKO_ALTERNATIVE], 'medallions': list(KAKARIKO_MEDALS)}


def kakariko_burning_applied(gamedata_raw):
    """True when ``gamedata_raw`` holds the patched programs of :func:`kakariko_burning_on_medallions`."""
    from oot_rando.patching.soul_adapter import murmur3
    entries = {int(e['Hash']): e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
    return all(murmur3(name) in entries
               and [[int(v) for v in step] for step in entries[murmur3(name)]['Values']] == patched
               for name, (_, patched) in _kakariko_programs().items())


def light_arrows_on_medallions(raw):
    """Keep the adult temple area; enable it on both medals until Zelda's abduction."""
    import copy
    import uuid
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    if (len(nodes) != 5 or [n['Name'] for n in nodes] != [
            'ActorLogicEventRequestActor', 'ActorLogicAreaActor',
            'HoldChallengeCurrentStepCheckOrder', 'HoldActorObserverBySensorHitInfo', 'OperateAND']
            or ainb.AINB.from_binary(ainb_to_binary(copy.deepcopy(document))).as_dict() != document):
        raise ValueError('Unexpected Light Arrows trigger module (already patched?).')
    inputs = nodes[2]['Parameters']['Inputs']['String']
    if [(p['Name'], p['Default Value']) for p in inputs] != [
            ('ChallengeName', 'Work/Challenge/AllSage.game__challenge__Challenge.gyml'),
            ('ChallengeStepName', 'Step02')]:
        raise ValueError('Unexpected Light Arrows story gate.')

    expected = copy.deepcopy(document)
    nodes = expected['Nodes']

    def query(index, name, inputs, outputs, queries=()):
        # Stable GUIDs keep a seed's generated files reproducible.
        return {'Node Type': 'UserDefined', 'Node Index': index, 'Name': name,
                'GUID': str(uuid.uuid5(uuid.NAMESPACE_URL, 'oot-rando/light-arrows/' + str(index))),
                'Flags': ['Is Query'], 'Queries': list(queries), 'Attachments': [], 'Properties': {},
                'Parameters': {'Inputs': inputs, 'Outputs': outputs}, 'XLink Actions': [], 'Plugs': {}}

    def flag(index, name):
        return query(index, 'HoldGameDataGetBoolSimple', {
            'Int': [{'Name': 'GameDataArrayIndex', 'Default Value': -1, 'Node Index': -1,
                     'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}],
            'String': [{'Name': 'GameDataNameBool', 'Default Value': name, 'Node Index': -1,
                        'Output Index': 0, 'Flags': ['Uses Default']}]},
            {'Bool': [{'Name': 'Bool', 'Is Output': True}]})

    nodes[2] = flag(2, LIGHT_ARROWS_PLAYED)
    nodes.extend(flag(i, name) for i, name in zip((5, 6), LIGHT_ARROWS_MEDALS))
    inverse = query(7, 'InvBool.module', {'Bool': [
        {'Name': 'BoolMulti', 'Default Value': False, 'Node Index': 2, 'Output Index': 0, 'Flags': []},
        {'Name': 'UpdateOnce', 'Default Value': False, 'Node Index': -1, 'Output Index': 0,
         'Flags': ['Uses Default', 'Is Output']}]}, {'Bool': [{'Name': 'InvBool', 'Is Output': True}]}, (2,))
    inverse['Flags'].append('Is Module')
    inverse['Plugs'] = {'Generic': [{'Node Index': 2, 'Name': 'BoolMulti'}]}
    nodes.append(inverse)
    ready = copy.deepcopy(nodes[4])
    ready.update({'Node Index': 8, 'GUID': str(uuid.uuid5(uuid.NAMESPACE_URL, 'oot-rando/light-arrows/8')),
                  'Queries': [5, 6, 7],
                  'Plugs': {'Generic': [{'Node Index': 5, 'Name': 'BoolMulti'}]}})
    ready['Parameters']['Inputs']['Bool'][0]['Sources'] = [
        {'Node Index': i, 'Output Index': 0, 'Flags': []} for i in (5, 6, 7)]
    nodes.append(ready)
    # The area's existence and the event request use the same readiness condition.
    area = next(p for p in nodes[1]['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Create')
    area.update({'Node Index': 8, 'Output Index': 1})
    nodes[1]['Queries'] = [8]
    nodes[1]['Plugs']['Generic'][1]['Node Index'] = 8
    nodes[4]['Queries'] = [3, 8]
    nodes[4]['Parameters']['Inputs']['Bool'][0]['Sources'][1].update({'Node Index': 8, 'Output Index': 1})
    expected['Modules'].append({'Path': 'InvBool.module.ainb', 'Category': 'Logic', 'Instance Count': 1})
    result = ainb_to_binary(copy.deepcopy(expected))
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Light Arrows trigger wrongly rewritten.')
    return result, {'module': LIGHT_ARROWS_MODULE, 'medallions': list(LIGHT_ARROWS_MEDALS),
                    'played': LIGHT_ARROWS_PLAYED}


def pedestal_after_first_adult_arrival(raw):
    """``Market_Adult_Prefab_89da``: the put-in prompt from the first adult arrival on.

    Returns (bytes, report)."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    nodes = document['Nodes']
    if (len(nodes) != 4 or [n['Name'] for n in nodes] != ['HoldGameDataGetBoolExpSimple', 'InvBool.module',
                                                          'ActorLogicAttentionActor', 'ActorLogicEventRequestActor']
            or ainb_to_binary(copy.deepcopy(document)) != raw):
        raise ValueError('Unexpected Master Sword pedestal logic module.')
    gate = nodes[0]['Parameters']['Inputs']['String'][0]
    delete = next(p for p in nodes[2]['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete')
    if (gate['Name'], gate['Default Value']) != ('GameDataNameBoolExp', PEDESTAL_BEFORE) or delete['Node Index'] != 1:
        raise ValueError('Unexpected Master Sword pedestal gate (already patched?).')
    expected = copy.deepcopy(document)
    expected['Nodes'][0]['Parameters']['Inputs']['String'][0]['Default Value'] = PEDESTAL_GATE
    result = ainb_to_binary(copy.deepcopy(expected))
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Master Sword pedestal gate wrongly rewritten.')
    return result, {'module': PEDESTAL_MODULE, 'before': PEDESTAL_BEFORE, 'gate': PEDESTAL_GATE}


# --- Dampé's race: the first race until its prize is opened --------------------
# ``MiniGame_DampeRace`` tells the first race (Hookshot prize, challenge step
# ``Playing``) from the second one (``PlayingSecond``, heart piece) by the Hookshot
# held: ``CheckIsGet Item_Hookshot`` at the start (Event129), pouch Hookshot/Longshot
# in Dampé's talks and balloons, the timer/record steps and the clear count at the finish. With the Hookshot found elsewhere the
# first race and its chest were skipped forever (Discord 17/11). The first prize chest
# (Event201, state ``OpenedHookShot``) now sets a saved flag, and every one of these
# checks reads that flag instead.
DAMPE_FLOW = 'Event/EventFlow/MiniGame_DampeRace.bfevfl.zs'
DAMPE_FIRST_PRIZE = 'RandoDampeFirstPrize'
DAMPE_RESULT_SWITCH = 'Event275'      # Result: IntBranch on MiniGame_DampeRace_ClearCount
DAMPE_HOOKSHOT_RESULT = 'Event277'    # its case 0: Dampé's talk, then the Hookshot chest
DAMPE_HOOKSHOT_CHECKS = {
    'Event129': ('GameDataActor', 'EventQueryCheckIsGet', {'ActorName': 'Item_Hookshot'}),
    'Event18': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Num': 1, 'Actor': 'Item_Longshot'}),
    'Event0': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
    'Event61': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
    'Event98': ('GameDataActor', 'EventQueryCheckIsGet', {'ActorName': 'Item_Hookshot'}),
    'Event157': ('GameDataActor', 'EventQueryCheckIsGet', {'ActorName': 'Item_Hookshot'}),
    'Event443': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
    # Race finish: with the Hookshot held, ``MiniGame_DampeRace_Clear`` (ClearCount + 1)
    # ran before ``Result``, so the first race already counted as cleared and showed
    # the heart piece / rupee chest instead of the Hookshot one (in game, 17/11).
    'Event442': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
    # Dampé's talk during a race and his balloon near the start.
    'Event444': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
    'Event262': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Num': 1, 'Actor': 'Item_Longshot'}),
    'Event260': ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Item_Hookshot', 'Num': 1}),
}


def dampe_saved_flags():
    """Bools to register in GameData (false in a new save)."""
    return {DAMPE_FIRST_PRIZE: False}


def dampe_first_race_until_prize(raw):
    """``MiniGame_DampeRace``: race order by the first prize opened, not the Hookshot held.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    opened = flow.event('Event201', 'ActionEvent')
    if (event_params_of(opened) != {'Index': -1, 'GameDataName': 'Minigame_DampeRace_TreasureBoxState',
                            'Value': 'OpenedHookShot'} or getattr(opened.data.nxt, 'v', None) is None):
        raise ValueError("Unexpected Dampé race prize step.")
    replaced = {}
    for name, (actor, query, params) in DAMPE_HOOKSHOT_CHECKS.items():
        check = flow.event(name, 'SwitchEvent')
        if (str(check.data.actor.v.identifier) != actor or check.data.actor_query.v.v != query
                or event_params_of(check) != params):
            raise ValueError(f"Unexpected Dampé race Hookshot check {name} (already patched?).")
        cases = {key: case.v for key, case in check.data.cases.items()}
        new = flow.switch('RandoDampe' + name, 'EventQueryIsGameDataBool',
                          {'GameDataName': DAMPE_FIRST_PRIZE, 'Index': -1}, cases.get(0), cases.get(1))
        links = links_to(flow.chart, check)
        if not links:
            raise ValueError(f'Dampé race check {name} unreached.')
        for owner, kind, key in links:
            if kind == 'nxt':
                owner.data.nxt = make_index(new)
            elif kind == 'case':
                owner.data.cases[key] = make_index(new)
            elif kind == 'entry':
                owner.main_event = make_index(new)
            else:
                raise ValueError(f'Unexpected link to Dampé race check {name}.')
        replaced[name] = (cases, len(links))
    # Event18/Event262 (Longshot) led to Event0/Event260 (Hookshot): their copies lead to the copies.
    # ``Result`` picks the chest by ``ClearCount`` (0: Hookshot chest). A save whose
    # first race already counted as cleared (Event442 before this fix) keeps the
    # Hookshot chest: until the first prize is opened, Result takes the ClearCount 0 path.
    result_switch = flow.event(DAMPE_RESULT_SWITCH, 'SwitchEvent')
    if (event_params_of(result_switch) != {'GameDataName': 'MiniGame_DampeRace_ClearCount'}
            or result_switch.data.cases[0].v.name != DAMPE_HOOKSHOT_RESULT):
        raise ValueError('Unexpected Dampé race result step.')
    first_result = result_switch.data.cases[0].v
    gate = flow.switch('RandoDampeResult', 'EventQueryIsGameDataBool',
                       {'GameDataName': DAMPE_FIRST_PRIZE, 'Index': -1}, result_switch, first_result)
    result_links = links_to(flow.chart, result_switch)
    for owner, kind, key in result_links:
        if owner is gate:
            continue
        if kind == 'nxt':
            owner.data.nxt = make_index(gate)
        elif kind == 'case':
            owner.data.cases[key] = make_index(gate)
        elif kind == 'entry':
            owner.main_event = make_index(gate)
        else:
            raise ValueError('Unexpected link to the Dampé race result step.')
    mark = flow.set_bool('RandoDampeFirstPrizeOpened', DAMPE_FIRST_PRIZE, True, opened.data.nxt.v)
    opened.data.nxt = make_index(mark)
    result, events = flow.write()
    entries = {}
    for entry in parse_flow(result).flowchart.entry_points:
        if entry.main_event.v is not None:
            entries[entry.main_event.v.name] = entries.get(entry.main_event.v.name, 0) + 1
    for name, (cases, count) in replaced.items():
        new = events['RandoDampe' + name]
        got = {key: case.v.name for key, case in new.data.cases.items()}
        want = {key: ('RandoDampe' + target.name if target.name in DAMPE_HOOKSHOT_CHECKS else target.name)
                for key, target in cases.items() if target is not None}
        refs = sum(1 for e in events.values() for x in [getattr(e.data, 'nxt', None)] if x is not None and x.v is new)
        refs += sum(1 for e in events.values() for c in (getattr(e.data, 'cases', None) or {}).values() if c.v is new)
        refs += entries.get(new.name, 0)
        if got != want or refs != count:
            raise ValueError(f'Dampé race check {name} wrongly rewired.')
    if events['Event201'].data.nxt.v.name != 'RandoDampeFirstPrizeOpened':
        raise ValueError('Dampé race prize flag not chained.')
    gate = events['RandoDampeResult']
    if ({k: c.v.name for k, c in gate.data.cases.items()} != {0: DAMPE_RESULT_SWITCH, 1: DAMPE_HOOKSHOT_RESULT}
            or entries.get(DAMPE_RESULT_SWITCH) or entries.get('RandoDampeResult') != len(
                [1 for owner, kind, _ in result_links if kind == 'entry'])):
        raise ValueError('Dampé race result step wrongly gated.')
    return result, {'flow': DAMPE_FLOW, 'flag': DAMPE_FIRST_PRIZE, 'checks': sorted(replaced)}


# --- Kokiri Forest exit guard (closed forest) -----------------------------------
# ``Npc_Kokiri_007_Child`` blocks the bridge while ``KOKIRI_EXIT_WALL`` (saved, also
# the Presence of its air wall) is true. Only his ``Get_StoneOfForest_IsCompleted_Exp_Talk``
# (schedule state ``Get_StoneOfForest_IsCompleted_Exp``) clears it (Event42). His
# AIScheduleParam ends with ``Goto_HyruleCastle_IsCompleted_Exp`` (talk
# ``KokiriForest_Npc_Kokiri_007_Child_BlockEnd_Talk``), the last true state winning:
# Zelda met before the Deku Tree, which vanilla never allows, that state hid the
# wall-lowering talk forever (Discord 16/11, "Can't exit Kokiri Forest"; same trap as
# Mido, issue #16). The end talk now runs the wall-lowering talk first while the wall
# still stands and the Deku Tree is done; this also repairs a save already stuck.
KOKIRI_EXIT_FLOW = 'Event/EventFlow/Npc_Kokiri_007_Child.bfevfl.zs'
KOKIRI_EXIT_WALL = 'KokiriForest_Npc_Kokiri_007_Child_Blocker_00'
DEKU_TREE_DONE = 'Get_StoneOfForest_IsCompleted_Exp'


def kokiri_exit_guard_steps_aside(raw):
    """``Npc_Kokiri_007_Child``: the end talk lowers a wall still up after the Deku Tree.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entries = {e.name: e for e in flow.chart.entry_points}
    end = entries.get('KokiriForest_Npc_Kokiri_007_Child_BlockEnd_Talk')
    lower = entries.get('Get_StoneOfForest_IsCompleted_Exp_Talk')
    clear = flow.event('Event42', 'ActionEvent')
    if (end is None or lower is None or getattr(end.main_event, 'v', None) is None
            or end.main_event.v.name != 'Event60' or getattr(lower.main_event, 'v', None) is None
            or lower.main_event.v.name != 'Event10'
            or event_params_of(clear) != {'Index': -1, 'GameDataName': KOKIRI_EXIT_WALL, 'Value': False}):
        raise ValueError('Unexpected Kokiri exit guard flow.')
    usual, talk = end.main_event.v, lower.main_event.v
    done = flow.switch('RandoExitDekuTreeDone', 'EventQueryIsGameDataBoolExp',
                       {'GameDataName': DEKU_TREE_DONE}, talk, usual)
    wall = flow.switch('RandoExitWallUp', 'EventQueryIsGameDataBool',
                       {'GameDataName': KOKIRI_EXIT_WALL, 'Index': -1}, done, usual)
    end.main_event = make_index(wall)
    result, events = flow.write()
    start = {e.name: e for e in parse_flow(result).flowchart.entry_points}[end.name].main_event.v
    up, deku = events['RandoExitWallUp'].data.cases, events['RandoExitDekuTreeDone'].data.cases
    if (start.name != 'RandoExitWallUp' or up[0].v.name != 'RandoExitDekuTreeDone' or up[1].v.name != 'Event60'
            or deku[0].v.name != 'Event10' or deku[1].v.name != 'Event60'):
        raise ValueError('Kokiri exit guard check wrongly chained.')
    return result, {'flow': KOKIRI_EXIT_FLOW, 'start': start.name, 'flag': KOKIRI_EXIT_WALL}


# DoorOfTime steps (``RSDB/Challenge``, checked against the table at generation).
DOOR_STEPS = ('Ready', 'Step01', 'Step02', 'Step2_1', 'Srep2_1_1', 'Step2_2', 'Step03', 'Step04', 'Step05', 'Step06')
ZELDA_FLOW = 'Event/EventFlow/Npc_Hylia_Zelda_Child.bfevfl.zs'
SARIA_SONG_FLOW = 'Event/EventFlow/Dm_SY_Ocarina_SariaSong.bfevfl.zs'
DOOR_BACK_REQUESTS = (ZELDA_FLOW, SARIA_SONG_FLOW)
DOOR_PAST_SREP = 'DoorOfTime_IsAfter_Step2_1_Exp'   # strict: Srep2_1_1 or later


def door_of_time_forward(raw):
    """``Srep2_1_1`` requests skipped once DoorOfTime is past Step2_1 (never backwards).

    Zelda's talk about the Water stone (Fire quest done) and Saria's Song request it
    without checking where DoorOfTime stands: with the stones found first it went back
    from Step03 and the drawbridge area disappeared. Returns (bytes, report)."""
    from oot_rando.patching import quest_guard
    result, report = quest_guard.guard_requests(raw, 'DoorOfTime', {'DoorOfTime': list(DOOR_STEPS)},
                                                ('Srep2_1_1',), DOOR_PAST_SREP, prefix='RandoDoorForward_')
    if not report['guarded']:
        raise ValueError('No Srep2_1_1 request to guard.')
    return result, report


# --- The clock before Zelda ------------------------------------------------------
# Issue #40 read the 15:00 cap as waiting for Impa's send-off
# (``HavePlayedEvent.Dm_HrlField_0020``); in game the clock waits for Kaepora's first
# field arrival instead (Discord 19/11): its saved effects are set at the start too
# (:mod:`oot_rando.patching.owl_advice`, ``FIELD_ARRIVAL_VALUES``). The send-off flag
# stays set at the end of the new-game opening. The send-off itself still plays
# (Impa's talk starts it with a map change, not on this flag); the flag is otherwise
# read only by two child NPCs' lines (Npc_Hylia_043_Child, Npc_Hylia_Soldier_008_Child)
# and by the Zora River owl (Dm_ZoraRiver_0005, which also needs Saria's Song).
CLOCK_FLAG = 'HavePlayedEvent.Dm_HrlField_0020'


def story_start_values():
    """GameData values written at the end of the new-game opening (full mode)."""
    from oot_rando.patching.owl_advice import start_values
    return {CLOCK_FLAG: True, **start_values()}


# --- First arrivals never move a quest back --------------------------------------
# An entrance plays its area presentation the first time it is used
# (``FieldAndDungeonEntranceEventRequestActor``: ``InitEventName`` while ``InitEventFlag``
# is false), and some of these scenes request a quest step without checking where the
# quest stands. Vanilla always uses that entrance first; a seed can reach the area
# another way, so the scene comes later and pulls the quest back (Discord 15/11: King
# Zora back in front of the fountain). Scan of the entrances of 1.1.1 (the others check
# the quest before their request):
#
# * Zora River -> Zora's Domain (``Goto_ZoraDomain``, ``HavePlayedEvent.Dm_Zora_0000``):
#   ``Get_StoneOfWater`` to ``Step03`` / ``Step03_Impa``. Zora's Domain reached first
#   from Lake Hylia, Ruto's Letter delivered (``Step07``): King Zora went back to his
#   throne in front of the fountain, the letter already spent.
# * Kakariko -> Death Mountain Trail (``DeathMountainTrail_Arrive``,
#   ``Get_StoneOfFire_DeathMtTrailIn``): ``Get_StoneOfFire`` to ``DeathMtTrailNpc``, even
#   once complete (``IsIgnoreCompletedChallenge`` false). The trail reached first from
#   Goron City (Lost Woods shortcut) or the crater.
# * Haunted Wasteland -> Desert Colossus (``FromWasteland_ArriveColossus``):
#   ``SageOfSpirit`` to ``Step04``. The Colossus reached first with the Requiem.
# * Hyrule Field / castle -> Market (``Goto_HyruleCastle_EntryMarket``):
#   ``Goto_HyruleCastle`` to ``Step02_01``, even once complete.
#
#
# The Water quest's own flow (``Get_StoneOfWater``) has the same trap: three scenes
# that vanilla always plays before Ruto's Letter is read move the quest back from
# ``Step07`` (King Zora aside) and King Zora returns in front of the fountain (Discord
# 19/11, after leaving Zora's Domain):
#
# * ``StoneOfWater_TalkWithImpa`` (Impa at the castle, Zelda met late): ``Step01``
#   with no check at all, even once complete;
# * ``StoneOfWater_TalkKaepora_ZoraRiver`` (child Zora River owl, passed after the
#   domain was reached through the Lost Woods): ``Step02`` while Impa is not met;
# * ``StoneOfWater_ClearDivingGame`` (diving game won after the letter): ``Step05``
#   once past ``Step03``.
#
# Every request before ``Step07`` in that flow is guarded (the king's ``Step01`` talk,
# the letter picked up and read included): none may move the quest back.
#
# Each request is now skipped once the quest is past its step or complete (one guard
# per expression, :func:`oot_rando.patching.quest_guard.guard_requests`). The scenes
# themselves still play. Not validated in game.
ARRIVE_FLOW = 'Event/EventFlow/Dm_SY_BancChangeArrive.bfevfl.zs'
CASTLE_FLOW = 'Event/EventFlow/Goto_HyruleCastle.bfevfl.zs'
WATER_FLOW = 'Event/EventFlow/Get_StoneOfWater.bfevfl.zs'
WATER_EARLY_STEPS = ('Step01', 'Step02', 'Step04', 'Step05', 'Step05_01', 'Step06')
FIRST_ARRIVAL_REQUESTS = {
    ARRIVE_FLOW: (('Get_StoneOfWater', ('Step03', 'Step03_Impa')), ('SageOfSpirit', ('Step04',))),
    WATER_FLOW: (('Get_StoneOfWater', WATER_EARLY_STEPS),),
    FIRE_STONE_FLOW: (('Get_StoneOfFire', ('DeathMtTrailNpc',)),),
    CASTLE_FLOW: (('Goto_HyruleCastle', ('Step02_01',)),),
}
FORWARD_PREFIX = 'RandoArrivalForward'


def first_arrival_forward(path, raw, steps):
    """``raw`` (the flow at ``path``) where its first-arrival requests never move a quest back.

    ``steps``: the challenge table (:func:`oot_rando.patching.quest_guard.challenge_steps`).
    Returns (bytes, [(event, step, expression)])."""
    from oot_rando.patching import quest_guard
    guarded, index = [], 0
    for challenge, wanted in FIRST_ARRIVAL_REQUESTS[path]:
        guards = [(step, quest_guard.after_expression(challenge, step)) for step in wanted]
        guards.append((None, f'{challenge}_IsCompleted_Exp'))
        for step, expression in guards:
            raw, report = quest_guard.guard_requests(raw, challenge, steps, wanted if step is None else (step,),
                                                     expression, prefix=f'{FORWARD_PREFIX}{index}_')
            index += 1
            if not report['guarded']:
                raise ValueError(f'First arrival guard: no {challenge} request to guard in {path}')
            guarded += [(event, name, expression) for event, name, _ in report['guarded']]
    return raw, guarded


def keep_first_arrivals_forward(read_flow, challenges_raw):
    """Every flow of :data:`FIRST_ARRIVAL_REQUESTS`. ``read_flow(path)``: its current bytes.
    Returns ({path: bytes}, {path: guarded})."""
    from oot_rando.patching import quest_guard
    steps = quest_guard.challenge_steps(challenges_raw)
    if tuple(steps.get('DoorOfTime', ())) != DOOR_STEPS:
        raise ValueError('Unexpected DoorOfTime steps in the challenge table.')
    files, report = {}, {}
    for path in FIRST_ARRIVAL_REQUESTS:
        files[path], report[path] = first_arrival_forward(path, read_flow(path), steps)
    return files, report


from oot_rando.patching.owl_advice import FLOW_FIXES as OWL_FLOW_FIXES
from oot_rando.formats import byml_codec
from oot_rando.logic import rando_options

# --- Link the Goron's tunic (adult) ------------------------------------------------
# Adult Link the Goron (``Npc_Goron_DaruniaJr_Adult``) hands over the Goron Tunic in
# ``SageOfFire`` ``Step02`` talk, only while the quest stands at ``TalkDaruniaJr``. The
# Death Mountain Crater sets the quest to ``MeetSheik`` as soon as Link enters it (logic
# ``DeathMountainCrater_Adult_Prefab_a0e2``): after Bolero of Fire, or any crater visit,
# that talk never comes back, and before Dodongo's Cavern the quest stayed out of his
# reach (user report 19/11). His own talk (``Talk``, the one he keeps outside those
# steps) now gives the tunic first while Link has none
# (``Dm_SY_GetInEvent/GetInEvent_NotTurn_NotNpc``, the vanilla get with Link's pose).
LINK_GORON_FLOW = 'Event/EventFlow/Npc_Goron_DaruniaJr_Adult.bfevfl.zs'
LINK_GORON_TALK = 'Talk'
GORON_TUNIC_GIFT = 'Obj_Armor_Goron'
GORON_TUNIC = 'Armor_Adult_Goron'


def link_goron_gives_tunic(raw, reward=None):
    """``Npc_Goron_DaruniaJr_Adult``: his talk gives the Goron Tunic while Link has none.

    Returns (bytes, report)."""
    from evfl.util import make_index
    from oot_rando.patching.progressive import FlowEditor, link
    editor = FlowEditor(raw, 'Npc_Goron_DaruniaJr_Adult')
    chart = editor.chart
    entry = next((e for e in chart.entry_points if e.name == LINK_GORON_TALK), None)
    if entry is None or getattr(entry.main_event, 'v', None) is None or entry.main_event.v.name != 'Event99':
        raise ValueError("Unexpected Link the Goron's talk flow.")
    if any(e.name.startswith('RandoGoronTunic') for e in chart.events):
        raise ValueError('Story fix already applied: RandoGoronTunic')
    usual = entry.main_event.v
    give = editor.subflow('RandoGoronTunicGive', 'Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc',
                          {'ActorName': reward['actor'] if reward else GORON_TUNIC_GIFT, 'IsNpcEventStarter': False})
    following = usual
    if reward:
        following = editor.action('RandoGoronTunicCollected', 'GameDataActor', 'EventTriggerSetGameDataBool',
                                  {'GameDataName': reward['flag'], 'Index': -1, 'Value': True})
        link(following, usual)
    link(give, following)
    if reward:
        # Ownership cannot stand in for collection once the gift is shuffled.
        has = editor.switch('RandoGoronTunicHas', 'GameDataActor', 'EventQueryIsGameDataBool',
                            {'GameDataName': reward['flag'], 'Index': -1}, usual, give)
    else:
        has = editor.switch('RandoGoronTunicHas', 'PouchSystemActor', 'EventQueryIsExistInPouch',
                            {'Actor': GORON_TUNIC, 'Num': 1}, usual, give)
    entry.main_event = make_index(has)
    entry._sub_flow_event_indices = list(entry._sub_flow_event_indices) + [chart.events.index(give)]
    result, checked = editor.write("Link the Goron's tunic")
    events = {e.name: e for e in checked.flowchart.events}
    start = {e.name: e for e in checked.flowchart.entry_points}[LINK_GORON_TALK].main_event.v
    cases = {k: c.v.name for k, c in events['RandoGoronTunicHas'].data.cases.items()}
    if (start.name != 'RandoGoronTunicHas' or cases != {0: 'Event99', 1: 'RandoGoronTunicGive'}
            or events['RandoGoronTunicGive'].data.nxt.v.name != following.name):
        raise ValueError("Link the Goron's tunic wrongly chained.")
    if reward:
        from oot_rando.patching.progressive import is_token, add_converter_calls
        if is_token(reward['actor']):
            result = add_converter_calls(result, ['RandoGoronTunicGive'], 'Npc_Goron_DaruniaJr_Adult')
    return result, {'flow': LINK_GORON_FLOW, 'entry': LINK_GORON_TALK, 'gift': GORON_TUNIC_GIFT}



# --- Three scenes no longer required (21/11) ---------------------------------------
# Each lock below waited for a cutscene the seed may leave for later; the scene itself
# still plays when its own trigger is met, and never moves its quest back.
#
# * **Water Temple gate.** The lake gate (``HyruleField_LakeHylia_Common_Prefab_6a9d``,
#   ``Obj_LakeHrl_SwitchShutter_A_01``) opened only once ``SageOfWater`` was past
#   ``Step05`` (Sheik's Serenade in the Ice Cavern, then the temple arrival) or after its
#   Iron Boots switch scene (``Dm_WaterTemple_0000``). Node 3 now reads
#   :data:`WATER_GATE_OPEN` (that step OR adult Link): the gate opens for adult Link and
#   stays open (node 16 saves the scene as played). The Serenade is still given by the
#   Iron Boots chest (``GetEventName`` ``SageOfWater_MelodyGet_Water``); its Step04 /
#   Step05 requests are skipped once the quest is past Step05 (the temple entered).
# * **Door of Time.** The Song of Time at the door (``DoorOfTime_OpenDoor``) only opened
#   it once ``DoorOfTime`` was past ``Step04`` (Zelda's escape and the Ocarina of Time
#   seen, Event60). The song now opens it at any step (scene ``Dm_TimeTemple_0010``,
#   ``Market_Child_TimeTempleDoor_Opened``); ``Step06`` is still only requested past
#   ``Step04``, so the escape plays later, and once its ``Step05`` comes with the door
#   already open ``Step06`` follows at once. The door module (``Market_Common_f252``)
#   also reads the saved flag, the first sword pull no longer waits for ``Step06``
#   (:func:`oot_rando.patching.world_openings.pedestal_before_sages`) and the quest only
#   completes past ``Step05`` (the escape is not dropped).
# * **Rainbow bridge.** The bridge scene area (``GanonCastle_Level_Field_00_Prefab_14ba``)
#   existed only while ``Defeat_Ganon`` stood at ``Step01``, set by Zelda's revelation
#   (``AllSage`` Event11, Light Arrows). Node 4 now reads :data:`BRIDGE_READY` (vanilla
#   OR the Shadow and Spirit Medallions with the bridge never shown); Zelda's revelation
#   seen afterwards no longer moves the quest back to ``Step01``.
#
# Not validated in game.
WATER_GATE_MODULE = 'Logic/HyruleField_LakeHylia_Common_Prefab_6a9d.logic.module.ainb'
WATER_GATE_OPEN = 'RandoWaterTempleGate_Open'
WATER_GATE_STEP = 'SageOfWater_IsAfter_Step05_Exp'
CHILDHOOD = 'Sequence_IsChildhood'
SAGE_OF_WATER_FLOW = 'Event/EventFlow/SageOfWater.bfevfl.zs'
SAGE_OF_WATER_STEPS = ('Ready', 'Step00', 'Step01', 'Step03', 'Step04', 'Step05', 'Step06', 'Step07',
                       'Step07_00', 'Step07_1', 'Step07_1_Safety', 'Step07_2', 'Step08')
SERENADE_STEPS = ('Step04', 'Step05')
BOMBCHU_SHOP_MODULE = 'Logic/Market_Child_Prefab_0c76.logic.module.ainb'
BOMBCHU_SHOP_QUEST = 'Get_StoneOfFire_IsCompleted_Exp'
BOMBCHU_SHOP_ACTORS = {
    'Banc/Market/Market_Child_Dynamic.bcett.byml.zs': (
        (7765672504758317189, 'Land_HrlCity_ShopSign_A_01', True),),
    'Banc/Market/Market_Child_Static.bcett.byml.zs': (
        (13279196239484838949, 'Npc_Hylia_021_Shop_Child', False),
        (14705828610563193869, 'BGM_Shop_Market_Bombchu', False)),
}


DOOR_MODULE = 'Logic/Market_Common_f252.logic.module.ainb'
DOOR_OPENED = 'Market_Child_TimeTempleDoor_Opened'
# The altar's ReplaceEventParam rejects the ocarina BEFORE DoorOfTime_OpenDoor
# runs when this expression is true. Vanilla requires the quest to equal Step05;
# bypassing Event60 in that flow alone therefore did not free the song (0.7.3).
DOOR_SONG_INVALID = 'Market_Child_TimeTempleDoor_OcarinaReacts'
DOOR_SONG_NATIVE = [[1, 931730378], [2, 1558058783], [5], [0, 1920740541], [4]]
DOOR_SONG_STEP = 'DoorOfTime_IsAfter_Step04_Exp'
DOOR_SONG_PREFIX = 'RandoDoorSongStep06_'
DOOR_COMPLETE_ONLY_AFTER = 'DoorOfTime_IsAfter_Step05_Exp'
DOOR_COMPLETE_PREFIX = 'RandoDoorComplete_'
BRIDGE_MODULE = 'Logic/GanonCastle_Level_Field_00_Prefab_14ba.logic.module.ainb'
BRIDGE_READY = 'RandoGanonBridge_Ready'
BRIDGE_VANILLA = 'Defeat_Ganon_IsAfter_Ready_Exp'
BRIDGE_PLAYED = 'HavePlayedEvent.GanonCastle_Adult_Field_Rainbow'
BRIDGE_MEDALS = ('IsGet.Item_Medal_Shadow', 'IsGet.Item_Medal_Spirit')
ALL_SAGE_FLOW = 'Event/EventFlow/AllSage.bfevfl.zs'
DEFEAT_GANON_STEPS = ('Ready', 'Step01', 'Step02', 'Step03', 'Step04', 'Step05', 'Step06', 'Step07',
                      'Step08', 'Step09')
GANON_PAST_REVELATION = 'Defeat_Ganon_IsAfter_Step01_Exp'


def _door_song_program(requirement):
    """The native ocarina invalid-condition: already opened OR missing stones.

    The ocarina point itself recognises the Song of Time; this gate only adds
    the chosen stones, independently of Zelda's escape and its quest enum.
    """
    from oot_rando.patching.soul_adapter import murmur3
    if requirement not in ('song', 'vanilla', 'all'):
        raise ValueError('Unknown Door of Time requirement: ' + str(requirement))
    program = [[0, murmur3(DOOR_OPENED)]]
    if requirement != 'song':
        stones = STONE_SETS[requirement]
        program.append([0, murmur3(STONE_FLAG_PREFIX + stones[0])])
        for stone in stones[1:]:
            program.extend([[0, murmur3(STONE_FLAG_PREFIX + stone)], [3]])
        program.extend([[5], [4]])
    return program


def door_song_condition(gamedata_raw, requirement='song'):
    """Free the native altar reaction from Step05 and apply the door's stones.

    Returns (GameData bytes, report). Does not alter the separate escape rules.
    """
    from oot_rando.patching.soul_adapter import murmur3
    program = _door_song_program(requirement)
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    entries = [e for e in data['BoolExp'] if int(e['Hash']) == murmur3(DOOR_SONG_INVALID)]
    if len(entries) != 1 or [[int(v) for v in x] for x in entries[0]['Values']] != DOOR_SONG_NATIVE:
        raise ValueError('Unexpected Door of Time ocarina invalid-condition (already patched?).')
    bools = {int(e['Hash']) for e in data['Bool']}
    if any(x[1] not in bools for x in program if x[0] == 0):
        raise ValueError('Door of Time ocarina condition: flag missing from game data.')
    entries[0]['Values'] = [[byml_codec.U64(v) for v in step] for step in program]
    result = byml_codec.dump(document)
    if not door_song_condition_applied(result, requirement):
        raise ValueError('Door of Time ocarina condition wrongly rewritten.')
    return result, {'expression': DOOR_SONG_INVALID, 'requirement': requirement}


def door_song_condition_applied(gamedata_raw, requirement='song'):
    from oot_rando.patching.soul_adapter import murmur3
    entries = [e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']
               if int(e['Hash']) == murmur3(DOOR_SONG_INVALID)]
    return (len(entries) == 1 and [[int(v) for v in x] for x in entries[0]['Values']]
            == _door_song_program(requirement))


def _scene_programs():
    """{BoolExp name: postfix program}; push Bool 0 / BoolExp 10, AND 3, OR 4, NOT 5."""
    from oot_rando.patching.soul_adapter import murmur3
    medals = [[0, murmur3(name)] for name in BRIDGE_MEDALS] + [[3]]
    return {
        WATER_GATE_OPEN: [[10, murmur3(WATER_GATE_STEP)], [0, murmur3(CHILDHOOD)], [5], [4]],
        BRIDGE_READY: [[10, murmur3(BRIDGE_VANILLA)], *medals, [0, murmur3(BRIDGE_PLAYED)], [5], [3], [4]],
    }


def scene_expressions(gamedata_raw):
    """GameData with :data:`WATER_GATE_OPEN` and :data:`BRIDGE_READY`. Returns (bytes, report)."""
    from oot_rando.patching.soul_adapter import murmur3
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    bools = {int(e['Hash']) for e in data['Bool']}
    expressions = {int(e['Hash']) for e in data['BoolExp']}
    if any(murmur3(name) in known for name in _scene_programs()):
        raise ValueError('Scene conditions already present.')
    if (any(murmur3(name) not in bools for name in (CHILDHOOD, BRIDGE_PLAYED, *BRIDGE_MEDALS))
            or any(murmur3(name) not in expressions for name in (WATER_GATE_STEP, BRIDGE_VANILLA))):
        raise ValueError('Scene conditions: flag missing from the game data.')
    for name, program in _scene_programs().items():
        data['BoolExp'].append({'Hash': byml_codec.U32(murmur3(name)), 'ResetTypeValue': 0, 'SaveFileIndex': -1,
                                'Values': [[byml_codec.U64(v) for v in step] for step in program]})
    return byml_codec.dump(document), {'expressions': list(_scene_programs())}


def scene_expressions_applied(gamedata_raw):
    from oot_rando.patching.soul_adapter import murmur3
    entries = {int(e['Hash']): e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
    return all(murmur3(name) in entries and [[int(v) for v in s] for s in entries[murmur3(name)]['Values']] == program
               for name, program in _scene_programs().items())


def edit_ainb_module(raw, check, edit):
    """AINB ``raw`` rewritten by ``edit(nodes)`` once ``check(nodes)`` passed; re-read exactly."""
    import copy
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(raw).as_dict()
    check(document['Nodes'])
    expected = copy.deepcopy(document)
    edit(expected['Nodes'])
    result = ainb_to_binary(copy.deepcopy(expected))
    if ainb.AINB.from_binary(result).as_dict() != expected:
        raise ValueError('Logic module wrongly rewritten.')
    return result


def _links_to(nodes, index):
    """[(node, input name, output index)] of every input reading node ``index``."""
    found = []
    for node in nodes:
        for inputs in node.get('Parameters', {}).get('Inputs', {}).values():
            for entry in inputs:
                for source in entry.get('Sources') or [entry]:
                    if source.get('Node Index') == index:
                        found.append((node['Node Index'], entry['Name'], source.get('Output Index')))
    return found


def water_gate_for_adult(raw):
    """``HyruleField_LakeHylia_Common_Prefab_6a9d``: node 3 reads :data:`WATER_GATE_OPEN`.

    Returns (bytes, report)."""
    def check(nodes):
        step = nodes[3] if len(nodes) > 7 else {}
        strings = {p['Name']: p['Default Value']
                   for p in step.get('Parameters', {}).get('Inputs', {}).get('String', [])}
        if (step.get('Name') != 'HoldChallengeCurrentStepCheckOrder'
                or strings != {'ChallengeName': 'Work/Challenge/SageOfWater.game__challenge__Challenge.gyml',
                               'ChallengeStepName': 'Step05'}
                or nodes[7].get('Name') != 'ActorLogicGateDoor'):
            raise ValueError('Unexpected Water Temple gate module (already patched?).')
        if sorted(_links_to(nodes, 3)) != [(2, 'BoolMulti', 0), (16, 'IsDrive', 0)]:
            raise ValueError('Unexpected Water Temple gate wiring.')

    def edit(nodes):
        nodes[3]['Name'] = 'HoldGameDataGetBoolExpSimple'
        nodes[3]['Parameters'] = {
            'Inputs': {'String': [{'Name': 'GameDataNameBoolExp', 'Default Value': WATER_GATE_OPEN,
                                   'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default']}]},
            'Outputs': {'Bool': [{'Name': 'Bool', 'Is Output': True}]}}
    return edit_ainb_module(raw, check, edit), {'module': WATER_GATE_MODULE, 'gate': WATER_GATE_OPEN}


def serenade_keeps_water_temple(raw):
    """``SageOfWater``: the Serenade's Step04 / Step05 skipped once past Step05. Returns (bytes, report)."""
    from oot_rando.patching import quest_guard
    result, report = quest_guard.guard_requests(raw, 'SageOfWater', {'SageOfWater': list(SAGE_OF_WATER_STEPS)},
                                                SERENADE_STEPS, WATER_GATE_STEP, prefix='RandoWaterForward_')
    if len(report['guarded']) < 2:
        raise ValueError('Serenade requests not found.')
    return result, report


def door_opens_on_saved_flag(raw):
    """``Market_Common_f252``: the door's OR also reads :data:`DOOR_OPENED`. Returns (bytes, report)."""
    def check(nodes):
        if len(nodes) < 9:
            raise ValueError('Unexpected Door of Time module.')
        gate, flag = nodes[5], nodes[6]
        sources = [(s['Node Index'], s['Output Index']) for s in gate['Parameters']['Inputs']['Bool'][0]['Sources']]
        if (gate.get('Name') != 'OperateORFixInputTrue' or sources != [(4, 1), (8, 0), (8, 2)]
                or gate.get('Queries') != [4, 8, 8]
                or flag['Parameters']['Inputs']['String'][0]['Default Value'] != DOOR_OPENED
                or flag['Parameters']['Outputs']['Bool'] != [{'Name': 'Bool', 'Is Output': False}]):
            raise ValueError('Unexpected Door of Time module (already patched?).')

    def edit(nodes):
        gate, flag = nodes[5], nodes[6]
        gate['Parameters']['Inputs']['Bool'][0]['Sources'].append({'Node Index': 6, 'Output Index': 0, 'Flags': []})
        gate['Queries'] = [4, 8, 8, 6]
        # A node only computes its flagged outputs.
        flag['Parameters']['Outputs']['Bool'][0]['Is Output'] = True
    return edit_ainb_module(raw, check, edit), {'module': DOOR_MODULE, 'flag': DOOR_OPENED}


def bombchu_shop_actor_edits(root, path):
    """Keep the child shop's vendor/music present and its closed sign hidden.

    Only replace these actors' dungeon gate with childhood; preserve the native
    negations, vendor links, stock, and the door's separate nighttime condition.
    Returns (patch_strings edits, manifest report).
    """
    edits, indices = [], []
    for ident, gyaml, negation in BOMBCHU_SHOP_ACTORS[path]:
        found = [i for i, actor in enumerate(root.get('Actors', [])) if actor.get('Hash') == ident]
        if len(found) != 1:
            raise ValueError('Bombchu Shop actor not found: ' + gyaml)
        index = found[0]
        actor = root['Actors'][index]
        if (actor.get('Gyaml') != gyaml or actor.get('Presence') != {
                'FlagName': BOMBCHU_SHOP_QUEST, 'IsCheckLazy': False, 'IsNegation': negation}):
            raise ValueError('Unexpected Bombchu Shop actor presence: ' + gyaml)
        edits.append({'path': ('Actors', index, 'Presence', 'FlagName'),
                      'before': BOMBCHU_SHOP_QUEST, 'after': CHILDHOOD})
        indices.append(index)
    return edits, {'actors': indices, 'presence': CHILDHOOD}


def bombchu_shop_open_from_start(raw):
    """``Market_Child_Prefab_0c76``: the Bombchu Shop door no longer asks for the Fire Stone quest.

    Node 1 reads ``Get_StoneOfFire_IsCompleted_Exp``; node 0 (night: opens the door) and node 4
    (day or night: the door's prompt) AND it. Both now read only their time-of-day input
    (the shop stays a night shop, as the logic expects). Returns (bytes, report)."""
    def sources(node):
        return [(s['Node Index'], s['Output Index']) for s in node['Parameters']['Inputs']['Bool'][0]['Sources']]

    def check(nodes):
        if (len(nodes) < 6 or nodes[1].get('Name') != 'HoldGameDataGetBoolExpSimple'
                or nodes[1]['Parameters']['Inputs']['String'][0]['Default Value'] != BOMBCHU_SHOP_QUEST
                or nodes[0].get('Name') != 'OperateAND' or sources(nodes[0]) != [(1, 0), (2, 1)]
                or nodes[4].get('Name') != 'OperateAND' or sources(nodes[4]) != [(1, 0), (5, 1)]
                or nodes[3].get('Flags') != ['Is Query', 'Is Module']):
            raise ValueError('Unexpected Bombchu Shop door module (already patched?).')

    def edit(nodes):
        for node, queries in ((0, [2, 2]), (4, [5, 5])):
            gate = nodes[node]
            time = gate['Parameters']['Inputs']['Bool'][0]['Sources'][1]
            gate['Parameters']['Inputs']['Bool'][0]['Sources'] = [dict(time), dict(time)]
            gate['Queries'] = queries
    return edit_ainb_module(raw, check, edit), {'module': BOMBCHU_SHOP_MODULE, 'dropped': BOMBCHU_SHOP_QUEST}


def door_song_before_escape(raw):
    """``DoorOfTime``: the Song of Time opens the door before the escape (see above).

    Returns (bytes, report)."""
    from evfl.util import make_index
    from oot_rando.patching import quest_guard
    flow = _Chart(raw)
    entries = {e.name: e for e in flow.chart.entry_points}
    gate, opened = flow.event('Event60', 'SwitchEvent'), flow.event('Event69', 'SwitchEvent')
    step06, step05 = flow.event('Event57', 'ActionEvent'), flow.event('Event14', 'ActionEvent')
    if (getattr(entries.get('DoorOfTime_OpenDoor'), 'main_event', None) is None
            or event_params_of(gate) != {'GameDataName': DOOR_SONG_STEP} or case_target(gate, 0) is not opened
            or case_target(gate, 1) is not None or event_params_of(opened).get('GameDataName') != DOOR_OPENED
            or event_params_of(step06).get('StepName') != 'Step06' or event_params_of(step05).get('StepName') != 'Step05'
            or getattr(step05.data.nxt, 'v', None) is None):
        raise ValueError('Unexpected Door of Time song flow (already patched?).')
    gate.data.cases[1] = make_index(opened)
    after = step05.data.nxt.v
    follow = flow.action('RandoDoorOpenedStep06', 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep',
                         event_params_of(step06), after)
    check = flow.switch('RandoDoorOpenedBefore', 'EventQueryIsGameDataBool',
                        {'GameDataName': DOOR_OPENED, 'Index': -1}, follow, after)
    step05.data.nxt = make_index(check)
    result, events = flow.write()
    if (sorted(events['Event60'].data.cases) != [0, 1] or events['Event14'].data.nxt.v.name != 'RandoDoorOpenedBefore'
            or events['RandoDoorOpenedStep06'].data.nxt.v.name != after.name):
        raise ValueError('Door of Time song wrongly chained.')
    steps = {'DoorOfTime': list(DOOR_STEPS)}
    result, song = quest_guard.guard_requests(result, 'DoorOfTime', steps, ['Step06'], DOOR_SONG_STEP,
                                              skip_when=False, prefix=DOOR_SONG_PREFIX)
    result, complete = quest_guard.guard_requests(result, 'DoorOfTime', steps, ['Complete'],
                                                  DOOR_COMPLETE_ONLY_AFTER, skip_when=False,
                                                  prefix=DOOR_COMPLETE_PREFIX)
    if len(song['guarded']) != 2 or len(complete['guarded']) != 1:
        raise ValueError('Door of Time song: unexpected step requests.')
    return result, {'flow': DOOR_FLOW, 'flag': DOOR_OPENED, 'step06_after': DOOR_SONG_STEP,
                    'complete_after': DOOR_COMPLETE_ONLY_AFTER}


def bridge_on_medallions(raw):
    """``GanonCastle_Level_Field_00_Prefab_14ba``: node 4 reads :data:`BRIDGE_READY`. Returns (bytes, report)."""
    def check(nodes):
        reader = nodes[4] if len(nodes) > 5 else {}
        name = (reader.get('Parameters', {}).get('Inputs', {}).get('String') or [{}])[0]
        gate = nodes[5]['Parameters']['Inputs']['Bool'][0].get('Sources', []) if len(nodes) > 5 else []
        if (reader.get('Name') != 'HoldGameDataGetBoolExpSimple'
                or (name.get('Name'), name.get('Default Value')) != ('GameDataNameBoolExp', BRIDGE_VANILLA)
                or [(s['Node Index'], s['Output Index']) for s in gate] != [(4, 0), (6, 0)]):
            raise ValueError('Unexpected rainbow bridge module (already patched?).')

    def edit(nodes):
        nodes[4]['Parameters']['Inputs']['String'][0]['Default Value'] = BRIDGE_READY
    return edit_ainb_module(raw, check, edit), {'module': BRIDGE_MODULE, 'ready': BRIDGE_READY}


def revelation_keeps_ganon_quest(raw):
    """``AllSage``: Zelda's revelation sets ``Defeat_Ganon`` Step01 only while not past it.

    Returns (bytes, report)."""
    from oot_rando.patching import quest_guard
    result, report = quest_guard.guard_requests(raw, 'Defeat_Ganon', {'Defeat_Ganon': list(DEFEAT_GANON_STEPS)},
                                                ('Step01',), GANON_PAST_REVELATION, prefix='RandoGanonForward_')
    if len(report['guarded']) != 1:
        raise ValueError('Zelda revelation: expected one Defeat_Ganon request.')
    return result, report


def scene_module_fixes():
    """((logic module path, report key, fix(raw) -> (bytes, report)), ...) of these fixes."""
    from oot_rando.patching.world_openings import PEDESTAL_MODULE as CHILD_PEDESTAL, pedestal_before_sages
    from oot_rando.patching.world_openings import (KAKARIKO_CLOSED_MODULE, KAKARIKO_OPEN_MODULE,
                                                  kakariko_gate_on_letter)
    from oot_rando.patching import link_goron
    from oot_rando.patching import lost_dog, shop_hours
    return (*shop_hours.module_fixes(),
            (lost_dog.MODULE, 'lost_dog_map', lost_dog.map_from_start),
            (lost_dog.POOL_MODULE, 'lost_dog_pool', lost_dog.pool_from_start),
            (link_goron.MODULE, 'link_goron_spawn', link_goron.spawn_from_first_entry),
            (WATER_GATE_MODULE, 'water_gate', water_gate_for_adult),
            (KAKARIKO_CLOSED_MODULE, 'kakariko_gate_closed',
             lambda raw: kakariko_gate_on_letter(raw, False)),
            (KAKARIKO_OPEN_MODULE, 'kakariko_gate_open',
             lambda raw: kakariko_gate_on_letter(raw, True)),
            (BOMBCHU_SHOP_MODULE, 'bombchu_shop_open', shop_hours.bombchu_from_start),
            (DOOR_MODULE, 'door_saved_flag', door_opens_on_saved_flag),
            (CHILD_PEDESTAL, 'first_pull_any_door_step',
             lambda raw: (pedestal_before_sages(raw), {'module': CHILD_PEDESTAL})),
            (BRIDGE_MODULE, 'bridge_medallions', bridge_on_medallions))


# After Morpha the red ice disappears and the challenge's NPC schedule releases
# King Zora to his ordinary Talk/IrregularTalk. Neither contains his tunic gift.
# Keep the original reward site (SageOfWater/Event242), so item replacement and
# AP/progressive hooks still run, and use its saved receipt instead of ownership.
KING_ZORA_FLOW = 'Event/EventFlow/Npc_Zora_KingZora_adult.bfevfl.zs'
KING_ZORA_GIFT_FLAG = 'SageOfWater_KingZora_adult_Talk_Event198'
KING_ZORA_GIFT_ENTRY = 'RandoKingZoraGift'


def king_zora_gift_entry(raw, shuffled=False):
    """Expose the native gift sequence for a post-Morpha unclaimed reward."""
    from evfl.entry_point import EntryPoint
    from evfl.util import make_index
    from oot_rando.patching.progressive import FlowEditor, link
    editor = FlowEditor(raw, 'SageOfWater')
    events = {e.name: e for e in editor.chart.events}
    gift = events['Event242']
    if (type(gift.data).__name__ != 'SubFlowEvent'
            or (not shuffled and gift.data.params.data.get('ActorName') != 'Obj_Armor_Zora')
            or events['Event69'].data.params.data.get('GameDataName') != KING_ZORA_GIFT_FLAG
            or any(e.name == KING_ZORA_GIFT_ENTRY for e in editor.chart.entry_points)):
        raise ValueError('Unexpected King Zora gift sequence or fix already applied.')
    if shuffled:
        # Both native talks already test the receipt before testing tunic ownership.
        # An unclaimed randomized gift must take the no-tunic branch regardless.
        for name, parent in (('Event136', 'Event137'), ('Event243', 'Event127')):
            node = events[name]
            if node.data.params.data != {'Actor': 'Armor_Adult_Zora', 'Num': 1}:
                raise ValueError('Unexpected King Zora ownership gate.')
            events[parent].data.cases[1] = node.data.cases[1]
    init = editor.subflow('RandoKingZoraGiftInit', 'Get_StoneOfWater', 'Test_InitTalk_KingZora',
                         {'Arg_Turn': 4, 'Arg_Greeting': 4})
    link(init, gift)
    entry = EntryPoint(KING_ZORA_GIFT_ENTRY)
    entry.main_event = make_index(init)
    # Event242 returns through Event265; its true branch ends after Step05,
    # so this post-completion route never requests an earlier challenge step.
    entry._sub_flow_event_indices = [editor.chart.events.index(init), editor.chart.events.index(gift)]
    editor.chart.entry_points.append(entry)
    result, _ = editor.write('King Zora gift entry')
    return result, {'entry': KING_ZORA_GIFT_ENTRY, 'reward': 'Event242', 'flag': KING_ZORA_GIFT_FLAG}


def king_zora_gift_after_morpha(raw):
    """Normal and side-position talk offer the missed gift once after Morpha."""
    from evfl.util import make_index
    from oot_rando.patching.progressive import FlowEditor
    editor = FlowEditor(raw, 'Npc_Zora_KingZora_adult')
    entries = {e.name: e for e in editor.chart.entry_points}
    for name, root in (('Talk', 'Event38'), ('IrregularTalk', 'Event113')):
        entry = entries[name]
        if entry.main_event.v.name != root:
            raise ValueError('Unexpected King Zora talk entry: ' + name)
        usual = entry.main_event.v
        give = editor.subflow('RandoKingZoraGift' + name, 'SageOfWater', KING_ZORA_GIFT_ENTRY, None)
        received = editor.switch('RandoKingZoraGiftReceived' + name, 'GameDataActor',
                                 'EventQueryIsGameDataBool',
                                 {'GameDataName': KING_ZORA_GIFT_FLAG, 'Index': -1}, usual, give)
        completed = editor.switch('RandoKingZoraGiftCompleted' + name, 'GameDataActor',
                                  'EventQueryIsGameDataBoolExp',
                                  {'GameDataName': 'SageOfWater_IsCompleted_Exp'}, received, usual)
        entry.main_event = make_index(completed)
        entry._sub_flow_event_indices = list(entry._sub_flow_event_indices) + [editor.chart.events.index(give)]
    result, _ = editor.write('King Zora gift after Morpha')
    return result, {'entries': ['Talk', 'IrregularTalk'], 'flag': KING_ZORA_GIFT_FLAG}


def link_goron_shuffled_gift(raw, flag):
    """The quest and ordinary talks share one receipt for the shuffled gift."""
    from evfl.util import make_index
    flow = _Chart(raw)
    give = flow.event('Event18', 'SubFlowEvent')
    join = flow.event('Event36', 'JoinEvent')
    if join.data.nxt.v is not give:
        raise ValueError('Unexpected Darunia Jr. gift entrance.')
    guard = flow.switch('RandoGoronGiftCollected', 'EventQueryIsGameDataBool',
                        {'GameDataName': flag, 'Index': -1}, give.data.nxt.v, give)
    join.data.nxt = make_index(guard)
    result, _ = flow.write()
    return result, {'flag': flag}


def flow_fixes(stones, npc_gifts=None):
    """``(flow, report key, fix)`` of every story fix; the escape checks ask for ``stones``."""
    npc_gifts = npc_gifts or {}
    goron = npc_gifts.get('goron')
    from oot_rando.patching.minigame_rewards import FIXES as MINIGAME_FIXES
    from oot_rando.patching import gerudo_fortress as gerudo
    from oot_rando.patching import link_goron
    from oot_rando.patching import lost_dog, shop_hours
    return (
        *shop_hours.flow_fixes(),
        (lost_dog.FLOW, 'lost_dog_reward', lost_dog.reward_until_received),
        (link_goron.FLOW, 'link_goron_forward', link_goron.keep_quest_forward),
        (gerudo.SPIRIT_FLOW, 'gerudo_prison_card',
         partial(gerudo.membership_flow, names=('Event123', 'Event99', 'Event389'))),
        (gerudo.GUARD_FLOW, 'gerudo_guard_card', partial(gerudo.membership_flow, names=('Event20',))),
        *OWL_FLOW_FIXES,
        *MINIGAME_FIXES,
        ('Event/EventFlow/AllSage.bfevfl.zs', 'prelude_quest_forward', prelude_keeps_later_sage_progress),
        (FIRE_STONE_FLOW, 'darunia_gift', darunia_gift_after_dungeon),
        (DARUNIA_GIFT_FLOW, 'fire_quest_forward', keep_fire_quest_forward),
        (EPONA_FLOW, 'second_malon', second_malon_after_talon),
        (BOWLING_FLOW, 'bombchu_bowling', open_bombchu_bowling),
        (FAIRY_CALL_FLOW, 'great_fairies', open_and_count_great_fairies),
        *((fairy_flow(name), 'great_fairy_' + name.lower(), _fairy_reward_flag(name, reward, actor))
          for name, reward, actor in GREAT_FAIRIES),
        (DOOR_FLOW, 'zelda_escape', partial(zelda_escape_door_flow, stones=stones)),
        (ZELDA_FLOW, 'zelda_talk_forward', door_of_time_forward),
        (ZELDA_FLOW, 'zelda_talk_stones', partial(zelda_escape_on_talk, stones=stones)),
        (GOHMA_STONE_FLOW, 'gohma_stone_menu', skip_stone_menu_presentation),
        (KOKIRI_EXIT_FLOW, 'kokiri_exit_guard', kokiri_exit_guard_steps_aside),
        (DAMPE_FLOW, 'dampe_first_race', dampe_first_race_until_prize),
        (SARIA_SONG_FLOW, 'saria_song_forward', door_of_time_forward),
        (LINK_GORON_FLOW, 'link_goron_tunic', partial(link_goron_gives_tunic, reward=goron)),
        *((('Event/EventFlow/SageOfFire.bfevfl.zs', 'link_goron_shuffled',
            partial(link_goron_shuffled_gift, flag=goron['flag'])),) if goron else ()),
        (SAGE_OF_WATER_FLOW, 'serenade_forward', serenade_keeps_water_temple),
        (SAGE_OF_WATER_FLOW, 'king_zora_gift_entry',
         partial(king_zora_gift_entry, shuffled=bool(npc_gifts.get('zora')))),
        (KING_ZORA_FLOW, 'king_zora_gift', king_zora_gift_after_morpha),
        (DOOR_FLOW, 'door_song_before_escape', door_song_before_escape),
        (ALL_SAGE_FLOW, 'revelation_forward', revelation_keeps_ganon_quest),
    )
