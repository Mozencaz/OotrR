"""Market lost dog availability and one-time reward."""
from oot_rando.patching.quest_guard import CHALLENGES  # noqa: F401  (re-exported: lost_dog.CHALLENGES)
from oot_rando.formats.evfl_tools import case_target, event_params_of
from oot_rando.formats import byml_codec

FLOW = 'Event/EventFlow/SubEvent_FindRichard.bfevfl.zs'
MODULE = 'Logic/Market_Child_Prefab_f3a2.logic.module.ainb'
POOL_MODULE = 'Logic/HrlMarket_Child_Dog_Prefab_7574.logic.module.ainb'
POOL_GATE_NODE = 2
CHILDHOOD = 'Sequence_IsChildhood'
KAKARIKO_GATE = 'Npc_Hylia_Soldier_003_GateOpen'
RECEIPT = 'SubEvent_FindRichard_GetHeartPiece'


def quest_from_start(raw):
    """Enable the native Ready/Step01 schedules from the first child visit."""
    document = byml_codec.load(raw)
    rows = [r for r in document['root'] if r['__RowId'].endswith(
        '/SubEvent_FindRichard.game__challenge__Challenge.gyml')]
    if len(rows) != 1 or rows[0]['DependFlagName'] != KAKARIKO_GATE:
        raise ValueError('Unexpected lost dog challenge dependency (already patched?).')
    rows[0]['DependFlagName'] = CHILDHOOD
    result = byml_codec.dump(document)
    if byml_codec.load(result) != document:
        raise ValueError('Lost dog challenge wrongly rewritten.')
    return result, {'challenge': 'SubEvent_FindRichard', 'dependency': CHILDHOOD}


def map_from_start(raw):
    """Release the native dog/chase actors without changing their time or return gates."""
    from oot_rando.patching.story_fixes import edit_ainb_module

    def check(nodes):
        for index in (7, 14):
            if (nodes[index]['Name'] != 'HoldGameDataGetBoolSimple'
                    or nodes[index]['Parameters']['Inputs']['String'][0]['Default Value'] != KAKARIKO_GATE):
                raise ValueError('Unexpected lost dog map gate (already patched?).')

    def edit(nodes):
        for index in (7, 14):
            nodes[index]['Parameters']['Inputs']['String'][0]['Default Value'] = CHILDHOOD

    return edit_ainb_module(raw, check, edit), {'module': MODULE, 'dependency': CHILDHOOD}


def pool_from_start(raw):
    """Release the random-appear Market dogs (the lost dog's spawn pool) without the gate."""
    from oot_rando.patching.story_fixes import edit_ainb_module

    def check(nodes):
        node = nodes[POOL_GATE_NODE]
        if (node['Name'] != 'HoldGameDataGetBoolSimple'
                or node['Parameters']['Inputs']['String'][0]['Default Value'] != KAKARIKO_GATE):
            raise ValueError('Unexpected lost dog spawn gate (already patched?).')

    def edit(nodes):
        nodes[POOL_GATE_NODE]['Parameters']['Inputs']['String'][0]['Default Value'] = CHILDHOOD

    return edit_ainb_module(raw, check, edit), {'module': POOL_MODULE, 'dependency': CHILDHOOD}


def reward_until_received(raw):
    """Only the first reward's saved receipt selects the repeat blue rupee."""
    from evfl.util import make_rindex
    from oot_rando.patching.story_fixes import _Chart
    flow = _Chart(raw)
    check = flow.event('Event50', 'SwitchEvent')
    receipt = flow.event('Event55', 'ActionEvent')
    if (event_params_of(check) != {'GameDataName': 'SubEvent_FindRichard_IsCompleted_Exp'}
            or check.data.actor_query.v.v != 'EventQueryIsGameDataBoolExp'
            or case_target(check, 0).name != 'Event73' or case_target(check, 1).name != 'Event16'
            or event_params_of(receipt) != {'GameDataName': RECEIPT, 'Index': -1, 'Value': True}):
        raise ValueError('Unexpected lost dog reward gate (already patched?).')
    check.data.actor_query = make_rindex(flow.holder(check.data.actor.v.queries, 'EventQueryIsGameDataBool'))
    check.data.params.data = {'GameDataName': RECEIPT, 'Index': -1}
    flow.expected[check.name] = dict(check.data.params.data)
    result, _ = flow.write()
    return result, {'flow': FLOW, 'receipt': RECEIPT}
