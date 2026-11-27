from oot_rando.formats.evfl_tools import event_params_of, links_to
"""Skip Kaepora's field tutorials while retaining his optional transport services.

The dream-world NPC is a separate game service, not a field tutorial. In particular,
TimeTemple_0086 must NOT be marked played: both transport owls disappear on that flag.
"""

ADVICE_EVENTS = (
    'Dm_HrlCastle_0000', 'Dm_HrlField_0030', 'Dm_HrlField_0040', 'Dm_HrlField_0050',
    'Dm_LostWood_0000', 'Dm_LostWood_0010', 'Dm_ZoraRiver_0000', 'Dm_ZoraRiver_0005',
)
CASTLE_FLOW = 'Event/EventFlow/Goto_HyruleCastle.bfevfl.zs'
DMT_FLOW = 'Event/EventFlow/Npc_Kaepora_DeathMountainTrail.bfevfl.zs'
LAKE_FLOW = 'Event/EventFlow/Npc_Kaepora_LakeHylia.bfevfl.zs'
DREAM_INTRO_FLOW = 'Event/EventFlow/Dm_HrlField_0080.bfevfl.zs'


# --- Kaepora's first field arrival: the day/night cycle -----------------------------
# Vanilla holds the clock until Kaepora's first talk in Hyrule Field (Discord 19/11,
# "Day/Night Cycle"): the cycle starts once ``Goto_HyruleCastle_Kaepora_00`` has run.
# That sequence (``HyruleField_Child_Prefab_de5f``: Link in its area while
# ``Dm_HrlField_0010`` is not played, the area deleted once ``Goto_HyruleCastle`` is
# past ``Step01``) sets ``HyruleField_ArriveEntrance`` (read by no game file: native),
# plays ``Dm_HrlField_0000/0005/0010``, then gives the amiibo menu, requests ``Step02``,
# opens the challenge menu and the Hyrule Field music. In a seed it broke three ways:
# Kokiri left by Goron City or Zora's River (no clock until the bridge), the owl scenes
# skipped (``Dm_HrlField_0000`` alone: a black screen), and the child castle skipped
# (the quest past ``Step01``: the area deleted, no clock ever).
#
# Its saved effects are now written at the end of the new-game opening, so the
# trigger never fires and the clock runs from the start; the amiibo menu is given with
# the starting items; ``Step02`` is requested right after the Deku Tree escape's own
# ``Step01`` (skipped once the quest is past ``Step01``). Not validated in game.
FIELD_ARRIVAL_EVENTS = ('Dm_HrlField_0000', 'Dm_HrlField_0005', 'Dm_HrlField_0010')
FIELD_ARRIVAL_VALUES = {
    'HyruleField_ArriveEntrance': True,
    'UI_IsFinishChallengeMenuOpenEvent': True,
    'NaviHint_Disp_FieldHint_01': False,
}
FIELD_ARRIVAL_POUCH = ('Pouch_Amiibo',)
ESCAPE_FLOW = 'Event/EventFlow/Dm_SY_BancChange_EscapeDungeon.bfevfl.zs'
ESCAPE_STEP01 = 'Event4'
FIELD_STEP = 'RandoOwlFieldStep02'
FIELD_STEP_GUARD = 'RandoOwlFieldStep02Guard_'
FIELD_STEP_SKIP = 'Goto_HyruleCastle_IsAfter_Step01_Exp'


def start_values():
    """Tutorial flags with no lost inventory or story effects, and the first field arrival."""
    values = {'HavePlayedEvent.' + event: True for event in ADVICE_EVENTS + FIELD_ARRIVAL_EVENTS}
    values.update(FIELD_ARRIVAL_VALUES)
    return values


def field_step_after_escape(raw, steps):
    """Deku Tree escape flow: Kaepora's ``Step02`` right after its ``Step01`` request.

    ``steps``: the challenge table (:func:`oot_rando.patching.quest_guard.challenge_steps`).
    Returns (bytes, report)."""
    from oot_rando.patching import quest_guard
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    flow.fresh(FIELD_STEP)
    escape = flow.event(ESCAPE_STEP01, 'ActionEvent')
    params = event_params_of(escape)
    if (escape.data.actor_action.v.v != quest_guard.STEP_ACTION
            or params.get('ChallengeName') != 'Goto_HyruleCastle' or params.get('StepName') != 'Step01'
            or escape.data.nxt.v is None):
        raise ValueError('Unexpected Deku Tree escape request.')
    if any(name == 'Step02' for _, name in quest_guard.step_requests(raw, 'Goto_HyruleCastle')):
        raise ValueError('Deku Tree escape already requests Step02.')
    from evfl.util import make_index
    # Kaepora's own request (Goto_HyruleCastle Event14), banner hidden.
    request = flow.action(FIELD_STEP, str(escape.data.actor.v.identifier), quest_guard.STEP_ACTION,
                          dict(params, StepName='Step02', IsIgnoreCompletedChallenge=True,
                               IsIgnoreChallengeProgressUI=True), escape.data.nxt.v)
    escape.data.nxt = make_index(request)
    result, _ = flow.write()
    result, report = quest_guard.guard_requests(result, 'Goto_HyruleCastle', steps, ('Step02',),
                                                FIELD_STEP_SKIP, prefix=FIELD_STEP_GUARD)
    if [event for event, _, _ in report['guarded']] != [FIELD_STEP]:
        raise ValueError('Kaepora field step wrongly guarded.')
    return result, {'after': ESCAPE_STEP01, 'event': FIELD_STEP, 'skip_when': FIELD_STEP_SKIP}


def skip_first_field_advice(raw):
    """Run the first field arrival's environment/quest work, without the two owl scenes."""
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    report = {}
    for name, scene, following in (('Event59', 'Dm_HrlField_0005', 'Event217'),
                                    ('Event12', 'Dm_HrlField_0010', 'Event96')):
        old = flow.event(name, 'ActionEvent')
        if (old.data.actor_action.v.v != 'EventTransition' or event_params_of(old).get('EventName') != scene
                or old.data.nxt.v.name != following):
            raise ValueError('Unexpected first owl scene: ' + name)
        links = links_to(flow.chart, old)
        if not links:
            raise ValueError('First owl scene already bypassed: ' + name)
        # Set the flag here, not in OpeningEvent: the native first-arrival work must
        # run once before its HasPlayed gate disables the area's request.
        seen = flow.set_bool('RandoOwlSeen' + name, 'HavePlayedEvent.' + scene, True, old.data.nxt.v)
        for owner, kind, key in links:
            if kind == 'nxt':
                owner.data.nxt = make_index(seen)
            elif kind == 'case':
                owner.data.cases[key] = make_index(seen)
            elif kind == 'entry':
                owner.main_event = make_index(seen)
            else:
                raise ValueError('Unexpected first owl scene predecessor: ' + kind)
        report[name] = {'scene': scene, 'resume': following}
    result, _ = flow.write()
    return result, report


def _short_ride(raw, lake):
    """Keep the native yes/no flight choice and all loading, warp and Cucco cleanup."""
    from evfl.event import SubFlowEvent
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    flow.fresh('RandoOwlRideInit')
    question = flow.event('Event13', 'ActionEvent')
    if (question.data.actor_action.v.v != 'EventTalk' or event_params_of(question).get('ChoiceNumber') != 2
            or not event_params_of(question).get('IsCloseDialog')):
        raise ValueError('Unexpected owl ride choice.')
    entries = {e.name: e for e in flow.chart.entry_points}
    if entries['Talk'].main_event.v.name != ('Event27' if lake else 'Event41'):
        raise ValueError('Unexpected owl transport entry.')
    # Mask_All includes advice and mask reactions; use its native InitTalk instead.
    data = SubFlowEvent()
    data.res_flowchart_name, data.entry_point_name = 'InitTalk', 'InitTalk'
    data.nxt = make_index(flow.event('Event15', 'ActionEvent') if lake else question)
    init = flow._add('RandoOwlRideInit', data, {'Arg_Greeting': 4, 'Arg_Turn': 4})
    entries['Talk'].main_event = make_index(init)
    entries['Near'].main_event = make_index(None)  # no unsolicited speech balloons
    if lake:
        participate = flow.event('Event15', 'ActionEvent')
        if participate.data.actor_action.v.v != 'EventTriggerParticipateEvent':
            raise ValueError('Unexpected lake owl participation.')
        participate.data.nxt = make_index(question)
        yes, advice, resume, no = 'Event39', 'Event16', 'Event2', 'Event40'
    else:
        yes, advice, resume, no = 'Event0', 'Event15', 'Event24', 'Event54'
    accept = flow.event(yes, 'SubFlowEvent')
    if accept.data.nxt.v.name != advice:
        raise ValueError('Unexpected owl flight acceptance.')
    accept.data.nxt = make_index(flow.events[resume])
    # A declined flight needs no additional explanation after the closed question.
    decline = flow.event(no, 'ActionEvent')
    if decline.data.actor_action.v.v != 'EventPlayerPlayASForFlowchart':
        raise ValueError('Unexpected owl flight refusal.')
    decline.data.nxt = make_index(None)
    result, _ = flow.write()
    return result, {'question': 'Event13', 'accept': yes, 'resume': resume, 'decline': no}


def short_mountain_ride(raw):
    return _short_ride(raw, False)


def short_lake_ride(raw):
    return _short_ride(raw, True)


def skip_dream_advice(raw):
    """The field owl unlocks the Dream World silently; its game service stays available."""
    from evfl.util import make_index
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    flow.fresh('RandoOwlDreamReady')
    unlock = flow.event('Event55', 'ActionEvent')
    if (unlock.data.actor_action.v.v != 'EventTriggerSetGameDataBool'
            or event_params_of(unlock) != {'GameDataName': 'DreamWorld_Open', 'Value': True, 'Index': -1}):
        raise ValueError('Unexpected owl Dream World unlock.')
    # Refuse to omit any additional persistent/inventory side effect on another build.
    for event in flow.chart.events:
        if type(event.data).__name__ == 'ActionEvent':
            action = event.data.actor_action.v.v
            if any(word in action for word in ('GameData', 'Challenge', 'Pouch')) and event is not unlock:
                raise ValueError('Unexpected side effect in owl Dream World introduction.')
    entry = next(e for e in flow.chart.entry_points if e.name == 'EntryPoint0')
    if entry.main_event.v.name != 'Event4':
        raise ValueError('Unexpected owl Dream World entry.')
    wait = flow.event('Event72', 'ActionEvent')
    reset = flow.event('Event35', 'ActionEvent')
    music = flow.event('Event10', 'ActionEvent')
    if (wait.data.actor_action.v.v != 'EventWaitCloseLoadingFade'
            or reset.data.actor_action.v.v != 'EventTriggerSendReserveCameraResetMessageToPlayerCamera'
            or reset.data.nxt.v is not music
            or music.data.actor_action.v.v != 'EventTriggerSoundStartSceneBgm'):
        raise ValueError('Unexpected owl Dream World scene cleanup.')
    # The scene is also called during area arrival: keep its loading-fade
    # synchronization and its camera/music cleanup, even without a conversation.
    ready = flow.set_bool('RandoOwlDreamReady', 'DreamWorld_Open', True, wait)
    wait.data.nxt = make_index(reset)
    entry.main_event = make_index(ready)
    result, _ = flow.write()
    return result, {'entry': 'EntryPoint0', 'preserved_flag': 'DreamWorld_Open'}


FLOW_FIXES = ((CASTLE_FLOW, 'owl_first_field', skip_first_field_advice),
              (DMT_FLOW, 'owl_mountain_ride', short_mountain_ride),
              (LAKE_FLOW, 'owl_lake_ride', short_lake_ride),
              (DREAM_INTRO_FLOW, 'owl_dream_advice', skip_dream_advice))
