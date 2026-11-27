"""Cuccos to bring back (AP ``chicken_count``): the cucco lady's pen in Kakariko (child).

Three places hold the vanilla 7:

* ``Logic/MiniGame_CatchCucco_c69b.logic.module.ainb``: node 17 (``OperateCompareInt``)
  compares ``Int_A`` = 7 with the cuccos in the pen (``Int_B``, node 9
  ``OperateBoolCount``). ``Equal`` sets ``Npc_Hylia_049_Child_Cucco06_IsInTheCage``
  (node 18), the flag her flows test before the reward; ``A_Bigger`` clears it (node 19).
* ``Minigame_CatchCucco``: ``Event3`` sets ``Npc_Hylia_049_Child_HowManyCuccos`` to 7
  before ``Event2`` subtracts the cuccos in the pen (her "Only N left" lines), and
  ``Event82`` compares what is left with 7 (below: some were brought back).
* Her lines (``EventFlowMsg/Npc_Hylia_049_Child.msbt``) name the number at the start of
  a coloured span, as a digit or a word depending on the language.

For N cuccos, node 17 compares with N - 1 and node 18 reads ``A_Smaller``: N or more
in the pen set the flag, so a reload with more than N saved still counts. Node 19 keeps
``A_Bigger`` (N - 2 or fewer clear it; N - 1 keeps the flag as it was). The flow's two
values and the spans become N. Not validated in game.
"""
import io
from oot_rando.formats.evfl_tools import params_by_event, parse_flow
from oot_rando.formats import byml_codec
from oot_rando.formats import msbt
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.extra_sources import event_paths

FLOW = 'Minigame_CatchCucco'
LOGIC_MODULE = 'Logic/MiniGame_CatchCucco_c69b.logic.module.ainb'
MESSAGE_FILE = 'EventFlowMsg/Npc_Hylia_049_Child.msbt'
REMAINING = 'Npc_Hylia_049_Child_HowManyCuccos'
FLOW_EVENTS = ('Event3', 'Event82')
VANILLA_COUNT = 7
# Her lines with the number: the request (Talk_19, Talk_21, Talk_21_1) and the reward (Talk_40).
LINES = ('Talk_19', 'Talk_21', 'Talk_21_1', 'Talk_40')
SPAN_ON = b'\x0e\x00\x00\x03\x00\x02\x00\x00\x00'
SPAN_OFF = b'\x0e\x00\x00\x03\x00\x02\x00\xff\xff'
# "7" in every language of the game (Polish and Russian decline it), longest first.
NUMBER_WORDS = tuple(sorted(('7', 'seven', 'sieben', 'sept', 'sette', 'zeven', 'sete', 'siedem', 'siódemkę',
                             'siódemka', 'семь', 'семерых'), key=lambda w: -len(w.encode())))
_COMPARE, _COUNTER, _SET, _CLEAR, _TRIGGER = 17, 9, 18, 19, 73


def check_count(count):
    if type(count) is not int or not 1 <= count <= VANILLA_COUNT:
        raise ValueError('Cucco count out of range.')
    return count


def patch_flow(raw, count):
    """``Minigame_CatchCucco`` counting ``count`` cuccos. Returns new bytes (unchanged for 7)."""
    if check_count(count) == VANILLA_COUNT:
        return raw
    flow = parse_flow(raw)
    events = {e.name: e for e in flow.flowchart.events}
    expected = params_by_event(flow)
    for name in FLOW_EVENTS:
        params = getattr(getattr(events.get(name), 'data', None), 'params', None)
        if (params is None or params.data.get('GameDataName') != REMAINING
                or params.data.get('Value') != VANILLA_COUNT):
            raise ValueError('Unexpected cucco count event: ' + name)
        params.data['Value'] = count
        expected[name]['Value'] = count
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    if params_by_event(parse_flow(result)) != expected:
        raise ValueError('Cucco patch changed other event parameters.')
    return result


def _readers(nodes, index):
    """Nodes whose inputs read an output of node ``index``."""
    found = set()
    for node in nodes:
        for inputs in (node.get('Parameters') or {}).get('Inputs', {}).values():
            for entry in inputs:
                sources = entry.get('Sources') or [entry]
                if any(s.get('Node Index') == index for s in sources):
                    found.add(node['Node Index'])
    return found


def _pen_wiring(document):
    """The nodes of the pen module as the patch expects them (raises otherwise)."""
    nodes = document['Nodes']
    if document['Version'] != 0x408 or document['Category'] != 'Logic' or document['Commands'] or len(nodes) != 79:
        raise ValueError('Unexpected cucco pen logic module.')
    compare = nodes[_COMPARE]
    ints = compare['Parameters']['Inputs'].get('Int') or []
    outputs = compare['Parameters']['Outputs'].get('Bool') or []
    if (compare['Name'] != 'OperateCompareInt' or nodes[_COUNTER]['Name'] != 'OperateBoolCount'
            or [(i['Name'], i['Node Index'], i['Default Value']) for i in ints]
            != [('Int_A', -1, VANILLA_COUNT), ('Int_B', _COUNTER, 0)]
            or [(o['Name'], o['Is Output']) for o in outputs]
            != [('A_Bigger', True), ('A_Smaller', False), ('Equal', True)]
            or _readers(nodes, _COMPARE) != {_SET, _CLEAR}):
        raise ValueError('Unexpected cucco pen comparison.')
    for index, output in ((_SET, 2), (_CLEAR, 0)):
        node = nodes[index]
        bools = node['Parameters']['Inputs'].get('Bool') or []
        if (node['Name'] != 'OperateAND' or not bools or bools[0]['Name'] != 'BoolMulti'
                or [(s['Node Index'], s['Output Index']) for s in bools[0]['Sources']]
                != [(_TRIGGER, 1), (_COMPARE, output)]):
            raise ValueError('Unexpected cucco pen flag update.')
    return nodes


def patch_logic(raw, count):
    """The pen's logic module for ``count`` cuccos (in place, same size). Unchanged for 7."""
    import copy
    import struct
    import ainb
    from oot_rando.patching.qol_patches import _AINB_NODE_SIZE, _AINB_NODE_TABLE
    if check_count(count) == VANILLA_COUNT:
        return raw
    original = ainb.AINB.from_binary(raw).as_dict()
    _pen_wiring(original)
    header = struct.unpack_from('<29I', raw, 0)
    io_offset, multi_offset = header[13], header[14]
    int_inputs = struct.unpack_from('<I', raw, io_offset)[0]
    bool_inputs, bool_outputs = struct.unpack_from('<2I', raw, io_offset + 8 * 1)
    result = bytearray(raw)

    def io_base(index, kind):
        """(first input, first output) of the node's parameters of ``kind`` (0 Int, 1 Bool)."""
        node = _AINB_NODE_TABLE + index * _AINB_NODE_SIZE
        if struct.unpack_from('<h', raw, node + 2)[0] != index:
            raise ValueError('Cucco pen node table misread.')
        params = struct.unpack_from('<I', raw, node + 0x14)[0]
        base_in, _, base_out, _ = struct.unpack_from('<4I', raw, params + 0x30 + 16 * kind)
        return base_in, base_out

    # 1. Int_A: N - 1 (input entry: name, node, output, flags, default value).
    at = int_inputs + io_base(_COMPARE, 0)[0] * 0x10
    source, _, _, default = struct.unpack_from('<hhIi', raw, at + 4)
    if (source, default) != (-1, VANILLA_COUNT):
        raise ValueError('Cucco pen count misread.')
    struct.pack_into('<i', result, at + 0xc, count - 1)
    # 2. The flag is set on A_Smaller (more than N - 1 in the pen) instead of Equal.
    window = -100 - struct.unpack_from('<h', raw, bool_inputs + io_base(_SET, 1)[0] * 0x10 + 4)[0]
    entry = multi_offset + (window + 1) * 8
    if struct.unpack_from('<hh', raw, entry) != (_COMPARE, 2):
        raise ValueError('Cucco pen flag source misread.')
    struct.pack_into('<hh', result, entry, _COMPARE, 1)
    # 3. Output flags: A_Smaller is now read, Equal no longer.
    first = io_base(_COMPARE, 1)[1]
    for position, used in ((1, True), (2, False)):
        at = bool_outputs + (first + position) * 4
        flags = struct.unpack_from('<I', raw, at)[0]
        struct.pack_into('<I', result, at, (flags | 1 << 31) if used else (flags & ~(1 << 31)))
    result = bytes(result)
    expected = copy.deepcopy(original)
    nodes = expected['Nodes']
    nodes[_COMPARE]['Parameters']['Inputs']['Int'][0]['Default Value'] = count - 1
    nodes[_COMPARE]['Parameters']['Outputs']['Bool'][1]['Is Output'] = True
    nodes[_COMPARE]['Parameters']['Outputs']['Bool'][2]['Is Output'] = False
    nodes[_SET]['Parameters']['Inputs']['Bool'][0]['Sources'][1]['Output Index'] = 1
    if ainb.AINB.from_binary(result).as_dict() != expected or len(result) != len(raw):
        raise ValueError('The cucco pen patch changed more than its count.')
    return result


def _spans(text):
    """``(start, end)`` of the coloured spans of a message (raw bytes)."""
    spans, at = [], 0
    while (start := text.find(SPAN_ON, at)) >= 0:
        start += len(SPAN_ON)
        end = text.find(SPAN_OFF, start)
        if end < 0:
            raise ValueError('Unclosed colour span in the cucco lines.')
        spans.append((start, end))
        at = end + len(SPAN_OFF)
    return spans


def _number(span):
    """Length of the vanilla number word that starts ``span`` (0 if none)."""
    for word in NUMBER_WORDS:
        token = word.encode()
        if span.startswith(token):
            rest = span[len(token):len(token) + 1]
            if rest.isdigit() if word == '7' else rest not in (b'', b' '):
                continue
            return len(token)
    return 0


def patch_message_file(raw, count):
    """Her message file with ``count`` in place of the number. Returns (bytes, numbers replaced)."""
    message = msbt.load(raw)
    replaced = 0
    for label in LINES:
        index = message.labels.get(label)
        if index is None:
            raise ValueError('Cucco line not found: ' + label)
        text = message.texts[index]
        for start, end in reversed(_spans(text)):
            length = _number(text[start:end])
            if length:
                text = text[:start] + str(count).encode() + text[start + length:]
                replaced += 1
        message.texts[index] = text
    if not replaced:
        raise ValueError('No cucco count found in her lines.')
    return msbt.dump(message), replaced


def patch_messages(archive, count):
    """A ``Mals`` archive (SARC) with her lines naming ``count``. Returns (bytes, numbers replaced)."""
    if check_count(count) == VANILLA_COUNT:
        return archive, 0
    files = dict(sarc(archive))
    if MESSAGE_FILE not in files:
        raise ValueError('Cucco lines not found in the message archive.')
    files[MESSAGE_FILE], replaced = patch_message_file(files[MESSAGE_FILE], count)
    return byml_codec.build_sarc(files), replaced


def her_lines(archive):
    """``{label: raw text}`` of her lines with the number, in a ``Mals`` archive."""
    message = msbt.load(dict(sarc(archive))[MESSAGE_FILE])
    return {label: message.get(label) for label in LINES}


def message_paths(members):
    return sorted(m for m in members if m.startswith('Mals/') and '.Product.110.' in m)


def flow_values(raw):
    """``{event: Value}`` of the flow's two count events."""
    events = {e.name: e for e in parse_flow(raw).flowchart.events}
    values = {}
    for name in FLOW_EVENTS:
        params = getattr(getattr(events.get(name), 'data', None), 'params', None)
        values[name] = None if params is None else params.data.get('Value')
    return values


def check_messages(count, paths, original, produced):
    """Verification: her lines in the produced archives. ``original``/``produced``: path ->
    decompressed bytes. Returns the numbers replaced (raises on a difference)."""
    if not paths:
        raise ValueError('No message archive for the cucco lines.')
    total = 0
    for path in paths:
        expected, replaced = patch_messages(original(path), count)
        if her_lines(produced(path)) != her_lines(expected):
            raise ValueError('Unexpected cucco count in her lines: ' + path)
        total += replaced
    return total


def check_seed(manifest, members, original, produced):
    """Verification of a seed's cucco count. ``original``/``produced``: path -> bytes (``.zs``
    files decompressed). Returns the report entries (none for 7); raises on a difference."""
    count = ((manifest.get('settings') or {}).get('full') or {}).get('chicken_count', VANILLA_COUNT)
    if (manifest.get('skips') or {}).get('cuccos', VANILLA_COUNT) != count:
        raise ValueError('Cucco count differs from the settings.')
    if count == VANILLA_COUNT:
        return {}
    flows = event_paths(members, FLOW)
    if not flows or {LOGIC_MODULE, *flows, *message_paths(members)} - set(manifest['files']):
        raise ValueError('Missing cucco count file.')
    if produced(LOGIC_MODULE) != patch_logic(original(LOGIC_MODULE), count):
        raise ValueError('Unexpected cucco pen logic: ' + LOGIC_MODULE)
    for path in flows:
        if flow_values(produced(path)) != dict.fromkeys(FLOW_EVENTS, count):
            raise ValueError('Unexpected cucco count in the flow: ' + path)
    return {'cuccos': count, 'cucco_lines': check_messages(count, message_paths(members), original, produced)}
