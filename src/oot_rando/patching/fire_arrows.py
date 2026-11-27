"""Fire Arrows (``LH Sun``): the sun-shot cutscene follows the shuffled pickup.

The reward is a placed pickup of the adult Hyrule Field map (``Obj_Arrow_Fire``,
instance name ``Item``). Shooting the sun plays ``Dm_LakeHrl_0030``, whose actor
``Obj_Arrow_Fire[Item]`` binds that pickup to the cutscene locator, plays its
effects and puts it back. Once the map holds another actor there (a derived
pickup with the same instance name), the cutscene actor is renamed to it, so the
cutscene still finds the pickup it shows. Nothing else of the flow changes.

Not validated in game.
"""
import io
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

CUTSCENE_FLOW = 'Event/EventFlow/Dm_LakeHrl_0030.bfevfl.zs'
ACTOR = 'Obj_Arrow_Fire'
INSTANCE = 'Item'


def retarget_cutscene(raw, actor):
    """``Dm_LakeHrl_0030`` with its ``Obj_Arrow_Fire[Item]`` actor renamed ``actor[Item]``."""
    from evfl.common import ActorIdentifier
    if not actor or actor == ACTOR:
        return raw
    flow = parse_flow(raw)
    chart = flow.flowchart
    expected = params_by_event(flow)
    found = [a for a in chart.actors if a.identifier.name == ACTOR and a.identifier.sub_name == INSTANCE]
    if len(found) != 1:
        raise ValueError('Fire Arrow cutscene actor not found.')
    if any(a.identifier.name == actor and a.identifier.sub_name == INSTANCE for a in chart.actors):
        raise ValueError('Fire Arrow cutscene already retargeted.')
    found[0].identifier = ActorIdentifier(actor, INSTANCE)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    check = parse_flow(result)
    names = [(a.identifier.name, a.identifier.sub_name) for a in check.flowchart.actors]
    if (actor, INSTANCE) not in names or (ACTOR, INSTANCE) in names or params_by_event(check) != expected:
        raise ValueError('Fire Arrow cutscene wrongly retargeted.')
    return result


def placed_actor(placements):
    """Actor that replaces the Fire Arrow pickup in the map, or None when it stays."""
    for placement in placements:
        if placement.get('before') == ACTOR and placement.get('source') == 'quest':
            after = placement.get('after')
            return after if after and after != ACTOR else None
    return None
