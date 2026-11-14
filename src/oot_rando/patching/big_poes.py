"""Big Poes to bring back (AP ``big_poe_count``): the Poe collector's reward threshold.

``Npc_Hylia_048_BottleShop`` adds 100 points (``GhostShop_CouponNum``) per Big Poe
sold. The sale compares the points held *before* the new Big Poe
(``EventQueryIsGameDataInt``: case 0 below, 1 equal, 2 above):

* ``Event265`` against 400: below → ordinary sale, equal → the 5th Big Poe's own
  line, above → ``Event70``;
* ``Event70`` against 900: below → ordinary sale, equal or above → the reward
  (10th Big Poe, ``SubEvent_GhostShop`` completed).

For N Big Poes, ``Event70`` compares against 100 × (N − 1) and ``Event265`` lets
those points through (at most 400, below the new threshold). Not validated in game.
"""
import io

FLOW = 'Npc_Hylia_048_BottleShop'
REWARD_EVENT, REWARD_POINTS = 'Event70', 900
GATE_EVENT, GATE_POINTS = 'Event265', 400
POINTS = 'GhostShop_CouponNum'
VANILLA_COUNT = 10


def thresholds(count):
    """``{event: (vanilla value, new value)}`` for ``count`` Big Poes (1 to 10)."""
    if type(count) is not int or not 1 <= count <= VANILLA_COUNT:
        raise ValueError('Big Poe count out of range.')
    reward = 100 * (count - 1)
    return {REWARD_EVENT: (REWARD_POINTS, reward), GATE_EVENT: (GATE_POINTS, min(GATE_POINTS, reward - 100))}


def patch_flow(raw, count):
    """Collector flow asking for ``count`` Big Poes. Returns new bytes (unchanged for 10)."""
    from oot_rando.patching.event_patch import _flow, _snapshot
    if count == VANILLA_COUNT:
        return raw
    flow = _flow(raw)
    events = {e.name: e for e in flow.flowchart.events}
    expected = _snapshot(flow)
    for name, (before, after) in thresholds(count).items():
        params = getattr(getattr(events.get(name), 'data', None), 'params', None)
        if params is None or params.data.get('GameDataName') != POINTS or params.data.get('Value') != before:
            raise ValueError('Unexpected Big Poe threshold: ' + name)
        params.data['Value'] = after
        expected[name]['Value'] = after
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    if _snapshot(_flow(result)) != expected:
        raise ValueError('Big Poe patch changed other parameters.')
    return result
