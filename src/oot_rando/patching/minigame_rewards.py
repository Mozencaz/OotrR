"""Multi-level mini-games: the first success hands over the rewards of every level.

The remake spreads some mini-game prizes over several wins. Each win is a separate
check in the randomizer, so the later ones asked the player to replay the game for
nothing but an item. The first success now gives all of them, in the order of the
levels, and the saved progress is brought to the end so that later wins only pay
the repeat reward (rupees) as after a full run:

* **Bombchu Bowling** (``MiniGame_BombchuBowling/GetPrise``): first win Bombchus, second
  the bomb bag, third the heart piece. The first win chains the three; the clear
  count (``MiniGameClearCount``) sets the three "cleared" flags at once.
* **Ocarina memory game** (``Npc_SkullKid_Child_02``): three sessions (6, 8 and 10
  notes) paying a blue rupee, a red rupee and the heart piece. The first session chains
  the three and moves the next session to the last grade (8).
* **Horseback archery** (``Minigame_HorsebackArchery``): 750 points the heart piece, 1400
  the quiver. 750 points now hand over both, as 1400 points already did.

The slingshot and bow ranges (``MiniGame_HitTarget``) have a single prize (the bag or
quiver, once: ``Get_BulletBag`` / ``Get_Quiver``; the hard mode only pays rupees), so there
is nothing to merge there.

Events are found by name, never by the item they give: the shuffled items and their
collection markers (``RandoCollected_<event>``, inserted after a gift) are already in
the flow when these fixes run, so a gift's continuation is followed through them.
Only static evidence backs these fixes: each needs an in-game pilot.
"""

BOWLING_FLOW = 'Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs'
SKULL_KID_FLOW = 'Event/EventFlow/Npc_SkullKid_Child_02.bfevfl.zs'
ARCHERY_FLOW = 'Event/EventFlow/Minigame_HorsebackArchery.bfevfl.zs'

BOWLING_FLAGS = ('MiniGame_BombchuBowling_ClearFirstTime', 'MiniGame_BombchuBowling_ClearSecondTime',
                 'MiniGame_BombchuBowling_ClearThirdTime')
SKULL_KID_GRADE = 'Minigame_SkullKidSession_CurrentGradeSoundNumForSession'
SKULL_KID_HEART_FLAG = 'Minigame_SkullKidSession_IsGetHeartPiece'
SKULL_KID_FIRST_GRADE, SKULL_KID_LAST_GRADE = 6, 8
ARCHERY_HEART_ENTRY = 'HourseBackArchery_HeartGet'
ARCHERY_DOUBLE_ENTRY = 'HourseBackArchery_MakeQuiverLarger_DoubleGet'


def _chart(raw):
    from oot_rando.patching.story_fixes import _Chart
    return _Chart(raw)


def _name(event):
    return event.name if event is not None else None


def _tail(give, continuation, label):
    """Last event of ``give``'s chain before ``continuation``: ``give`` itself, or the
    ``Rando*`` action events (collection markers) inserted after it."""
    event = give
    for _ in range(8):
        following = event.data.nxt.v
        if _name(following) == _name(continuation):
            return event
        if (following is None or type(following.data).__name__ != 'ActionEvent'
                or not following.name.startswith('Rando')):
            break
        event = following
    raise ValueError(f'Unexpected continuation of the {label} gift: {give.name}')


def _chain(flow, steps, label):
    """Make each ``(give, continuation)`` of ``steps`` continue with the next one's first event.

    ``steps``: list of ``(first events, continuation, next)``; the tail of every first event
    (one per branch of the same gift) is pointed at ``next``."""
    from evfl.util import make_index
    for gives, continuation, following in steps:
        for give in gives:
            _tail(give, continuation, label).data.nxt = make_index(following)


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def bowling_all_prizes(raw):
    """``MiniGame_BombchuBowling``: Bombchus, bomb bag and heart piece on the first win.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _chart(raw)
    bundle = flow.event('Event309', 'SubFlowEvent')
    choice = flow.event('Event76', 'SwitchEvent')
    heart = flow.event('Event143', 'SubFlowEvent')
    done = flow.event('Event93', 'SubFlowEvent')
    bags = [flow.event('Event304', 'SubFlowEvent'), flow.event('Event306', 'SubFlowEvent')]
    first_check = flow.event('Event73', 'SwitchEvent')
    second_check = flow.event('Event72', 'SwitchEvent')
    third_check = flow.event('Event260', 'SwitchEvent')
    flag = flow.event('Event89', 'ActionEvent')
    _check(first_check.data.cases[1].v is bundle and second_check.data.cases[1].v is choice
           and third_check.data.cases[1].v is heart
           and {choice.data.cases[0].v.name, choice.data.cases[1].v.name} == {b.name for b in bags}
           and done.data.entry_point_name == 'MiniGameClearCount', 'Unexpected Bombchu Bowling prizes.')
    params = dict(flag.data.params.data)
    _check(params == {'GameDataName': BOWLING_FLAGS[0], 'Index': -1, 'Value': True}
           and flag.data.nxt.v is not None, 'Unexpected Bombchu Bowling clear count.')
    _chain(flow, [([bundle], done, choice), (bags, done, heart)], 'Bombchu Bowling')
    # The three clears are counted at the first one: the next wins pay the repeat reward.
    final = flag.data.nxt.v
    third = flow.set_bool('RandoBowlingClearThird', BOWLING_FLAGS[2], True, final)
    second = flow.set_bool('RandoBowlingClearSecond', BOWLING_FLAGS[1], True, third)
    flag.data.nxt = make_index(second)
    result, events = flow.write()
    _check(_name(events['Event89'].data.nxt.v) == 'RandoBowlingClearSecond'
           and _name(events['RandoBowlingClearSecond'].data.nxt.v) == 'RandoBowlingClearThird'
           and _name(events['RandoBowlingClearThird'].data.nxt.v) == final.name
           and _name(_tail(events['Event309'], events['Event76'], 'Bombchu Bowling').data.nxt.v) == 'Event76',
           'Bombchu Bowling prizes wrongly chained.')
    return result, {'flow': BOWLING_FLOW, 'chain': ['Event309', 'Event76', 'Event143'],
                    'flags': list(BOWLING_FLAGS)}


def skull_kid_all_rewards(raw):
    """``Npc_SkullKid_Child_02``: both rupees and the heart piece after the first session.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _chart(raw)
    grade = flow.event('Event9', 'SwitchEvent')
    promote = flow.event('Event11', 'ActionEvent')
    blue, red = flow.event('Event22', 'SubFlowEvent'), flow.event('Event23', 'SubFlowEvent')
    after_blue, after_red = flow.event('Event204', 'ActionEvent'), flow.event('Event202', 'ActionEvent')
    heart_check = flow.event('Event64', 'SwitchEvent')
    heart = flow.event('Event24', 'SubFlowEvent')
    params = dict(promote.data.params.data)
    _check(params == {'GameDataName': SKULL_KID_GRADE, 'Index': -1, 'Value': SKULL_KID_FIRST_GRADE}
           and blue.data.nxt.v is after_blue and red.data.nxt.v is after_red
           and heart_check.data.params.data == {'GameDataName': SKULL_KID_HEART_FLAG, 'Index': -1}
           and heart_check.data.cases[1].v is heart
           and grade.data.cases[0].v.data.nxt.v is promote,
           'Unexpected Skull Kid rewards.')
    # First session over: the next one is the last grade, the rewards are all given.
    promote.data.params.data['Value'] = SKULL_KID_LAST_GRADE
    flow.expected['Event11']['Value'] = SKULL_KID_LAST_GRADE
    after_blue.data.nxt = make_index(red)
    after_red.data.nxt = make_index(heart_check)
    result, events = flow.write()
    _check(_name(events['Event204'].data.nxt.v) == 'Event23' and _name(events['Event202'].data.nxt.v) == 'Event64'
           and events['Event11'].data.params.data['Value'] == SKULL_KID_LAST_GRADE,
           'Skull Kid rewards wrongly chained.')
    return result, {'flow': SKULL_KID_FLOW, 'chain': ['Event22', 'Event23', 'Event64'],
                    'grade': SKULL_KID_LAST_GRADE}


def archery_all_prizes(raw):
    """``Minigame_HorsebackArchery``: the heart piece (750 points) also hands over the quiver.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _chart(raw)
    heart = flow.event('Event117', 'SubFlowEvent')
    double = flow.event('Event110', 'SubFlowEvent')
    _check(heart.data.entry_point_name == ARCHERY_HEART_ENTRY
           and double.data.entry_point_name == ARCHERY_DOUBLE_ENTRY
           and flow.event('Event119', 'SubFlowEvent').data.nxt.v is double,
           'Unexpected horseback archery prizes.')
    heart.data.nxt = make_index(double)
    result, events = flow.write()
    _check(_name(events['Event117'].data.nxt.v) == 'Event110', 'Horseback archery prizes wrongly chained.')
    return result, {'flow': ARCHERY_FLOW, 'chain': ['Event117', 'Event110']}


FIXES = ((BOWLING_FLOW, 'bowling_all_prizes', bowling_all_prizes),
         (SKULL_KID_FLOW, 'memory_game_all_rewards', skull_kid_all_rewards),
         (ARCHERY_FLOW, 'archery_all_prizes', archery_all_prizes))
