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
* **Talon at the castle twice.** ``SubEvent_GetEponaSong/GetEponaSong_StepCheck``
  sends Malon back to the castle (``IsMalonAppear_HyruleCastleSecondTime``, with an
  awake Talon at the entrance) once Dodongo's Cavern is done and Jabu-Jabu is not.
  Vanilla never gets there before Talon was woken; done in another order, the first
  Malon (the Weird Egg) was hidden and the sleeping Talon stayed: no egg, no Zelda.
  Malon now only comes back after Talon's wake-up scene (``Dm_HrlCastle_0020``);
  before it the flag is cleared, which also repairs a save already in that state.
* **Sheik at the Master Sword.** In the Temple of Time (``Market_Adult_Static``),
  adult Sheik waits in front of the pedestal, so Link could not put the sword back
  before the Forest Temple (``SageOfForest``) was finished. He now only appears once
  that quest is complete (his talk is hints only: no quest step depends on it).
* **Bombchu Bowling.** The alley opened only after Dodongo's Cavern
  (``MiniGame_BombchuBowling/AfterWakeUp`` Event137, ``Get_StoneOfFire_IsCompleted_Exp``):
  it is open from the start, as the logic expects.

Bool switches: case 0 = true, case 1 = false (as the vanilla flows). Not validated in game.
"""
import io

from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, _flow, _snapshot

FIRE_STONE_FLOW = 'Event/EventFlow/Get_StoneOfFire.bfevfl.zs'
DARUNIA_GIFT_FLOW = 'Event/EventFlow/Dm_Goron_0030.bfevfl.zs'
EPONA_FLOW = 'Event/EventFlow/SubEvent_GetEponaSong.bfevfl.zs'
BOWLING_FLOW = 'Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs'
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
        self.flow = _flow(raw)
        self.chart = self.flow.flowchart
        self.expected = _snapshot(self.flow)
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

    def switch(self, name, query, params, true, false):
        from evfl.event import SwitchEvent
        from evfl.util import make_index, make_rindex
        gamedata = self.actor('GameDataActor')
        data = SwitchEvent()
        data.actor = make_rindex(gamedata)
        data.actor_query = make_rindex(self.holder(gamedata.queries, query))
        data.cases = {0: make_index(true), 1: make_index(false)}
        return self._add(name, data, params)

    def set_bool(self, name, flag, value, following):
        from evfl.event import ActionEvent
        from evfl.util import make_index, make_rindex
        gamedata = self.actor('GameDataActor')
        data = ActionEvent()
        data.actor = make_rindex(gamedata)
        data.actor_action = make_rindex(self.holder(gamedata.actions, 'EventTriggerSetGameDataBool'))
        data.nxt = make_index(following)
        return self._add(name, data, {'GameDataName': flag, 'Value': value, 'Index': -1})

    def write(self):
        stream = io.BytesIO()
        self.flow.write(stream)
        result = stream.getvalue()
        checked = _flow(result)
        if _snapshot(checked) != self.expected:
            raise ValueError('A story fix changed other parameters.')
        return result, {e.name: e for e in checked.flowchart.events}


def _params(event):
    return dict(event.data.params.data) if event.data.params is not None else {}


def _case(event, key):
    case = event.data.cases.get(key)
    return case.v if case is not None else None


def darunia_gift_after_dungeon(raw):
    """``Get_StoneOfFire``: the gift scene after the dance while it was never played.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    check = flow.event('Event39', 'SwitchEvent')
    gift, done = _case(check, 1), _case(check, 0)
    if (_params(check) != {'GameDataName': AFTER_SARIA_PLAY} or gift is None or done is None
            or type(gift.data).__name__ != 'ActionEvent'
            or _params(gift).get('EventName') != 'Dm_Goron_0030'):
        raise ValueError("Unexpected Darunia dance continuation.")
    given = flow.switch('RandoDaruniaGiftGiven', 'EventQueryIsGameDataBool',
                        {'GameDataName': DARUNIA_GIFT_PLAYED, 'Index': -1}, done, gift)
    check.data.cases[0] = make_index(given)
    result, events = flow.write()
    written = events['Event39'].data.cases
    switch = events['RandoDaruniaGiftGiven'].data.cases
    if (written[0].v.name != 'RandoDaruniaGiftGiven' or written[1].v.name != gift.name
            or switch[0].v.name != done.name or switch[1].v.name != gift.name):
        raise ValueError('Darunia gift wrongly chained.')
    return result, {'flow': FIRE_STONE_FLOW, 'switch': 'RandoDaruniaGiftGiven', 'flag': DARUNIA_GIFT_PLAYED}


def keep_fire_quest_forward(raw):
    """``Dm_Goron_0030``: the step ``DodongoCavernOpne`` only while not already past it.

    Returns (bytes, report)."""
    from oot_rando.patching.qol_patches import _predecessors
    from evfl.util import make_index
    flow = _Chart(raw)
    step = flow.event('Event121', 'ActionEvent')
    if (step.data.actor_action.v.v != 'EventExecuteProgressChallengeStep'
            or _params(step).get('ChallengeName') != 'Get_StoneOfFire'
            or _params(step).get('StepName') != 'DodongoCavernOpne'):
        raise ValueError('Unexpected Darunia gift step.')
    ui = step.data.nxt.v
    if (ui is None or type(ui.data).__name__ != 'ActionEvent'
            or ui.data.actor_action.v.v != 'EventTriggerShowChallengeProgressUI'):
        raise ValueError('Unexpected Darunia gift step continuation.')
    resume = ui.data.nxt.v
    links = _predecessors(flow.chart, step)
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
    appear = _case(jabu, 1)
    if (_params(jabu) != {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'} or appear is None
            or appear.name != 'Event36' or _params(appear) != {'GameDataName': SECOND_MALON, 'Value': True,
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
    opened, closed = _case(gate, 0), _case(gate, 1)
    if (_params(gate) != {'GameDataName': 'Get_StoneOfFire_IsCompleted_Exp'} or opened is None
            or closed is None or opened is closed):
        raise ValueError('Unexpected Bombchu Bowling gate.')
    gate.data.cases[1] = make_index(opened)
    result, events = flow.write()
    cases = events['Event137'].data.cases
    if cases[0].v.name != opened.name or cases[1].v.name != opened.name:
        raise ValueError('Bombchu Bowling gate not opened.')
    return result, {'flow': BOWLING_FLOW, 'gate': 'Event137', 'closed_talk': closed.name}


def sheik_presence_edits(root):
    """``patch_strings`` edits: adult Sheik of the Temple of Time after the Forest Temple."""
    found = [i for i, actor in enumerate(root.get('Actors', [])) if actor.get('Gyaml') == SHEIK]
    if len(found) != 1:
        raise ValueError('Temple of Time Sheik not found.')
    index = found[0]
    if 'Presence' in root['Actors'][index]:
        raise ValueError('Temple of Time Sheik already conditioned.')
    base = ('Actors', index, 'Presence')
    return [{'path': base + ('FlagName',), 'before': None, 'after': SHEIK_PRESENCE},
            {'path': base + ('IsCheckLazy',), 'before': None, 'after': False},
            {'path': base + ('IsNegation',), 'before': None, 'after': False}]


# The presence the fix gives the Temple of Time Sheik (as verify reads it back).
SHEIK_PRESENCE_ENTRY = {'FlagName': SHEIK_PRESENCE, 'IsCheckLazy': False, 'IsNegation': False}


FLOW_FIXES = (
    (FIRE_STONE_FLOW, 'darunia_gift', darunia_gift_after_dungeon),
    (DARUNIA_GIFT_FLOW, 'fire_quest_forward', keep_fire_quest_forward),
    (EPONA_FLOW, 'second_malon', second_malon_after_talon),
    (BOWLING_FLOW, 'bombchu_bowling', open_bombchu_bowling),
)
