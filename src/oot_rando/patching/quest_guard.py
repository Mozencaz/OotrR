"""Keep a quest from going back once a seed has moved it forward.

The remake's quests are *challenges* (``RSDB/Challenge.Product.111``): an ordered
list of steps per quest, moved by the ``EventExecuteProgressChallengeStep`` action
(``ChallengeName``, ``StepName``) and read through the saved-data expressions
``<Challenge>_IsAfter_<Step>_Exp`` (one per step, bytecode ``[12, quest], [2, step]``)
and ``<Challenge>_IsCompleted_Exp``.

A world opening or a story skip starts a quest at a later step (the *floor*). Many
flows still request an earlier step when they run (an arrival scene, a mini-game,
an item pickup) and would pull the quest back, closing the opening again. The
guard puts a ``EventQueryIsGameDataBoolExp`` switch in front of every such request:
when the quest is already past the step just before the floor, the request (and
the progress banner right after it) is skipped; otherwise it runs as before.

The expression tested is ``IsAfter_<step before the floor>``: whether the game reads
"after" as ``>`` or ``>=``, a quest held at the floor or beyond always takes the
skip, and a quest that never reached the floor keeps its vanilla behaviour.
Not validated in game.
"""
from oot_rando.formats import byml_codec
from oot_rando.patching.soul_adapter import murmur3
from oot_rando.patching.story_fixes import _Chart
from oot_rando.formats.evfl_tools import event_params_of

CHALLENGES = 'RSDB/Challenge.Product.111.rstbl.byml.zs'
STEP_ACTION = 'EventExecuteProgressChallengeStep'
PROGRESS_UI = 'EventTriggerShowChallengeProgressUI'
QUERY = 'EventQueryIsGameDataBoolExp'
PREFIX = 'RandoQuestFloor_'


def challenge_steps(rsdb_raw):
    """{challenge: [step names in order]} read from the challenge table."""
    result = {}
    for row in byml_codec.load(rsdb_raw)['root']:
        name = row['__RowId'].rsplit('/', 1)[-1].split('.', 1)[0]
        result[name] = [step['Name'] for step in row['Steps']]
    return result


def after_expression(challenge, step):
    return f'{challenge}_IsAfter_{step}_Exp'


def floor_expression(steps, challenge, floor):
    """The expression true once ``challenge`` has reached ``floor`` (see module doc)."""
    order = steps.get(challenge)
    if not order:
        raise ValueError('Unknown challenge: ' + challenge)
    if floor not in order:
        raise ValueError(f'{challenge} has no step {floor}')
    index = order.index(floor)
    if index == 0:
        raise ValueError(f'{floor} is the first step of {challenge}: nothing to guard')
    return after_expression(challenge, order[index - 1])


def check_expressions(gamedata_raw, names):
    """Raise ValueError unless every BoolExp name exists in the GameData list."""
    known = {int(e['Hash']) for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
    missing = [name for name in names if murmur3(name) not in known]
    if missing:
        raise ValueError('Unknown GameData expressions: ' + ', '.join(sorted(missing)))


def step_requests(raw, challenge):
    """[(event name, step name)] of the step requests of ``challenge`` in a flow."""
    chart = _Chart(raw).chart
    return [(e.name, event_params_of(e)['StepName']) for e in chart.events
            if getattr(e.data, 'actor_action', None) is not None
            and e.data.actor_action.v.v == STEP_ACTION
            and event_params_of(e).get('ChallengeName') == challenge]


def _relink(chart, target, replacement):
    """Point every link to ``target`` (next, switch case, fork, entry point) at ``replacement``."""
    from evfl.util import make_index
    count = 0
    for event in chart.events:
        if event is replacement:
            continue
        data = event.data
        if getattr(data, 'nxt', None) is not None and data.nxt.v is target:
            data.nxt = make_index(replacement)
            count += 1
        for key, case in list((getattr(data, 'cases', None) or {}).items()):
            if case.v is target:
                data.cases[key] = make_index(replacement)
                count += 1
        forks = getattr(data, 'forks', None) or []
        for index, fork in enumerate(forks):
            if fork.v is target:
                forks[index] = make_index(replacement)
                count += 1
    for entry in chart.entry_points:
        if entry.main_event.v is target:
            entry.main_event = make_index(replacement)
            count += 1
    return count


def guard_regressions(raw, challenge, steps, floor, gamedata_raw=None, prefix=PREFIX):
    """Flow bytes where no request of a step before ``floor`` runs once the quest reached it.

    ``steps``: the challenge table (:func:`challenge_steps`). Not every step has its
    ``IsAfter`` expression (several mini-games, the mask quest, part of Epona's):
    with ``gamedata_raw`` the expression is checked first. Returns (bytes, report)
    with report = {'expression', 'guarded': [(event, step, skip_to or None)]}; the
    input is returned unchanged (empty ``guarded``) when the flow has no such request.
    Use a distinct ``prefix`` when another quest floor edits the same flow.
    """
    expression = floor_expression(steps, challenge, floor)
    order = steps[challenge]
    return guard_requests(raw, challenge, steps, order[:order.index(floor)], expression,
                          skip_when=True, gamedata_raw=gamedata_raw, prefix=prefix)


def guard_requests(raw, challenge, steps, wanted, expression, skip_when=True, gamedata_raw=None,
                   prefix=PREFIX):
    """Flow bytes where every request of a ``wanted`` step of ``challenge`` depends on ``expression``.

    ``skip_when=True``: the request is skipped while the expression is true (a floor);
    ``False``: it only runs while the expression is true. The progress banner right
    after a skipped request is skipped with it. Returns (bytes, report) as
    :func:`guard_regressions`.
    """
    if gamedata_raw is not None:
        check_expressions(gamedata_raw, [expression])
    order = steps.get(challenge)
    if not order:
        raise ValueError('Unknown challenge: ' + challenge)
    wanted = set(wanted)
    if wanted - set(order) - {'Complete'}:
        raise ValueError(f'{challenge} has no step {sorted(wanted - set(order) - {"Complete"})}')
    flow = _Chart(raw)
    if any(name.startswith(prefix) for name in flow.events):
        raise ValueError('Quest guard already applied: ' + prefix)
    requests = [e for e in flow.chart.events
                if getattr(e.data, 'actor_action', None) is not None
                and e.data.actor_action.v.v == STEP_ACTION
                and event_params_of(e).get('ChallengeName') == challenge]
    unknown = [event_params_of(e).get('StepName') for e in requests
               if event_params_of(e).get('StepName') not in order and event_params_of(e).get('StepName') != 'Complete']
    if unknown:
        raise ValueError(f'{challenge}: steps missing from the challenge table: {unknown}')
    targets = [e for e in requests if event_params_of(e).get('StepName') in wanted]
    if not targets:
        return raw, {'expression': expression, 'guarded': []}
    planned = []
    for step in targets:
        resume = step.data.nxt.v
        # The progress banner shown right after the request goes with it.
        if (resume is not None and getattr(resume.data, 'actor_action', None) is not None
                and resume.data.actor_action.v.v == PROGRESS_UI):
            resume = resume.data.nxt.v
        planned.append((step, resume))
    for index, (step, resume) in enumerate(planned):
        true, false = (resume, step) if skip_when else (step, resume)
        guard = flow.switch(f'{prefix}{index}', QUERY, {'GameDataName': expression}, true, false)
        if _relink(flow.chart, step, guard) == 0:
            # An unreachable request: drop the unused switch again.
            flow.chart.events.remove(guard)
            del flow.events[guard.name], flow.expected[guard.name]
    result, events = flow.write()
    # A request resuming on another guarded request now resumes on its guard.
    guard_of = {step.name: f'{prefix}{index}' for index, (step, _) in enumerate(planned)
                if f'{prefix}{index}' in events}
    guarded = []
    for index, (step, resume) in enumerate(planned):
        guard = events.get(f'{prefix}{index}')
        if guard is None:
            continue
        cases = guard.data.cases
        expected = None if resume is None else guard_of.get(resume.name, resume.name)
        run_key, skip_key = (1, 0) if skip_when else (0, 1)
        if (cases[run_key].v.name != step.name or (expected is None) != (skip_key not in cases)
                or (expected is not None and cases[skip_key].v.name != expected)):
            raise ValueError('Quest guard wrongly chained: ' + step.name)
        guarded.append((step.name, event_params_of(step)['StepName'], resume.name if resume is not None else None))
    return result, {'expression': expression, 'guarded': guarded}
