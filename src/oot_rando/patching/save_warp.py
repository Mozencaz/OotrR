"""Save warp, as on the N64: a "Save Warp" button in the pause menu's System tab saves,
then sends Link to the dungeon entrance, else to Link's house (child) or the Temple of
Time (adult).

* Layout: the System tab (``PaSystemMenu_00.buil`` in the Common layout archive) gets a
  sixth ``PaCommonBtnThin_00`` button, ``Pa_Button_05``, under "Title Screen"
  (:func:`add_system_button`). Its text is the ``PlusMenu_00.msbt`` label
  ``Pa_System_00-Pa_Button_05-T_Btn_00``.
* Plus menu (``PlusMenu.module``): the button sets ``RandoSaveWarp``, then opens the
  usual save screen (``Save.module``).
* Save screen: with the flag, "Save" clears it (the save never holds it), saves as Save
  does, capturing its slot in ``CaptionData.SelectedSavePathIndex`` before the write,
  waits for the auto save and caption managers as the plus menu does before a load
  (else the load reads the previous save), leaves the menu as the load screen does
  before a load (overlay closed; pre-game pause turned into the game pause), sets the flag again and ends with ``Warp``. The plus menu then runs its load
  (``_LocalModule_bde133631675``): the vanilla load of that save (the flag is gone once it
  is read back), into the warp destination. Cancel (and B) clear the flag.
* The load prepares the screens first, then enters a separate decision state. Each
  destination transitions to its own load state before GameData is reset, so restoring
  the request flag/current banc cannot switch the active load branch.

Loads from the title screen and the load screens are the vanilla ones. The warp's banc
change, the vanilla one but for its destination (fast load off: nothing prepared it):

* dungeons (and the ``VANILLA_LOAD`` bancs): the same banc, start name ``SavePos``;
* elsewhere: Kokiri Forest (child, start name ``SavePos``) or Market (adult, start name
  ``LightPrelude``, the Temple of Time warp point).

How the remake places Link when a banc loads (``Sequence/OnLoadBancParam.module.ainb``):
node 14: debug override, else node 42; node 42: the banc's ``IsAlwaysStartFromStartPos``
(no banc of the game sets it): its start position (node 44), else node 10; node 10: the
caller's ``IsOverrideTraverseBasePos``: node 71, else the banc's start position (node 28);
node 71: the caller's start name: empty, the caller's position (node 11, a save's
``PlayerStatus.SavePos``); else node 76; node 76: the ``StartPos`` of that name (node 73),
else the banc's start position (28).

Patched in place: node 76 falls back on node 42 instead of 28, node 42 on the saved
position (node 11) instead of node 10, node 14 goes straight to node 10. The dungeons and
Kokiri Forest set ``IsAlwaysStartFromStartPos``: ``SavePos`` (the name of no
``StartPos``) leads there to the banc's start position (a dungeon's entrance, Link's
house). The ``VANILLA_LOAD`` bancs (boss and miniboss stages, dream world, Ganon's
Castle escape and final battles, Sage room, credits) keep the saved position, set back to
false where they inherit the parameter. The only other change: a named start position
missing from its banc (never the case in the vanilla transitions, as far as checked)
falls back on the caller's position in the other bancs.
"""
import copy
import struct
import uuid
from oot_rando.formats import byml_codec
from oot_rando.formats import msbt
from oot_rando.formats.inspect_resources import sarc

SAVE_WARP_FLAG = 'RandoSaveWarp'
ON_LOAD_MODULE = 'Sequence/OnLoadBancParam.module.ainb'
SAVE_MODULE = 'Sequence/Save.module.ainb'
PLUS_MENU_MODULE = 'Sequence/PlusMenu.module.ainb'
MENU_LOAD_MODULE = 'Sequence/_LocalModule_bde133631675.module.ainb'
MENU_LOAD_CALL = (3, 0, 5)     # ChangeBanc call, Sequential running it, Sequence_CurrentBanc query
MENU_LOAD_NODE = 68            # PlusMenu: _LocalModule_bde133631675.module (ConfirmationLoad's Yes)
SAVE_NODE = 58                 # PlusMenu: Save.module
SYSTEM_BUTTONS = 51            # PlusMenu: StringSelector on the System tab button
SYSTEM_BUTTONS_OTHER = 65      # PlusMenu: the same choice, other state (every button but the last -> 52)
LAYOUT_ARCHIVE = 'UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs'
SYSTEM_LAYOUT = 'PaSystemMenu_00.buil'
NEW_BUTTON = 'Pa_Button_05'
BUTTON_PATH = 'Pa_System_00/' + NEW_BUTTON
MENU_TEXT = 'LayoutMsg/PlusMenu_00.msbt'
BUTTON_LABEL = 'Pa_System_00-Pa_Button_05-T_Btn_00'
BUTTON_TEXT = 'Save Warp'          # every language
LOAD_MARKER = 'SavePos'
CHILD_HOME = 'KokiriForest_Child'                  # Link's house: the banc's start position
ADULT_HOME = ('Market_Adult', 'LightPrelude')       # the Temple of Time warp point
START_NAME = 'OverrideTraverseStartPosName'
ALWAYS_START = 'IsAlwaysStartFromStartPos'
DUNGEONS = ('InsideTheDekuTree', 'DodongoCavern', 'InsideJabuJabuBelly', 'ForestTemple', 'FireTemple',
            'WaterTemple', 'ShadowTemple', 'SpiritTemple', 'BottomOfTheWell', 'IceCavern',
            'GerudoTrainingGround', 'InsideGanonCastle')
# The other bancs: a save warp from there goes home.
WORLD_ZONES = tuple(f'{zone}_{age}' for zone in (
    'DeathMountainCrater', 'DeathMountainTrail', 'DesertColossus', 'GerudoValley', 'GoronCity', 'Graveyard',
    'HountedWasteland', 'HyruleField', 'KokiriForest', 'LostWood', 'Market', 'SacredForestMeadow',
    'ZoraDomain', 'ZoraFountain', 'ZoraRiver', 'KakarikoVillage') for age in ('Child', 'Adult')) + (
    'KakarikoVillage_Adult_Alternative', 'ZoraDomain_Adult_Alternative', 'GerudoFortress_Adult',
    'HyruleCastle', 'GanonCastle')
ZONES = DUNGEONS + (CHILD_HOME,)   # set IsAlwaysStartFromStartPos
# Bancs keeping the saved position: boss and miniboss stages, dream world, scripted bancs.
VANILLA_LOAD = ('GohmaStage', 'DodongoStage', 'LizalfosStage', 'BarinadeStage', 'BigOctoStage',
                'PhantomGanonStage', 'StalfosWeakStage', 'MegStage', 'VolvagiaStage', 'FlareDancerStage',
                'MorphaStage', 'DarkLinkStage', 'BongoBongoStage', 'StalfosStage', 'TwinrovaStage',
                'NaboruStage', 'IronKnuckleWhiteStage', 'DeadHandStage', 'WolfosWhiteStage',
                'GanondorfStage', 'IronKnuckleBlackStage', 'DinolfosStage', 'GerudoThiefStage', 'WolfosStage',
                'GanonStage', 'BossRushIntervalRoom', 'EnemyMuseum', 'CrumblingGanonCastle', 'FinalBattleField',
                'SageRoom', 'Demo_ShootingLocation_Tapestry_ED')


def banc_param(name):
    return f'Banc/GameBancParam/{name}.game__banc__GameBancParam.bgyml'


# (node, child plug position, vanilla target, new target) in OnLoadBancParam.
ON_LOAD_REWIRING = ((14, 1, 42, 10),   # no debug override: the caller's choice directly
                    (76, 1, 28, 42),   # named start missing: ask the banc
                    (42, 1, 10, 11))   # banc without IsAlwaysStartFromStartPos: the caller's position
ON_LOAD_NAMES = {10: 'Element_BoolSelector', 11: 'SeqOneShotSetTraverseBasePos', 14: 'Element_BoolSelector',
                 28: 'Element_Simultaneous', 42: 'Element_BoolSelector', 43: 'SeqQueryGetBoolFromGameBancParam',
                 44: 'Element_Simultaneous', 71: 'Element_StringSelector', 75: 'SeqQueryStartPosByName',
                 76: 'Element_BoolSelector'}

_HEADER, _COMMAND_SIZE, _NODE_SIZE = 0x74, 0x18, 0x3c   # the node table follows the commands
_CHILD = 2                        # PlugType.Child


class _Module:
    """Offsets of a version 0x408 AINB module, read with the layout the ainb library reads."""

    def __init__(self, raw):
        if raw[:4] != b'AIB ' or struct.unpack_from('<I', raw, 4)[0] != 0x408:
            raise ValueError('Unexpected AINB module version.')
        header = struct.unpack_from('<29I', raw, 0)
        self.raw = raw
        self.nodes = _HEADER + _COMMAND_SIZE * header[3]

    def node_params(self, index):
        at = self.nodes + index * _NODE_SIZE
        if struct.unpack_from('<h', self.raw, at + 2)[0] != index:
            raise ValueError('AINB node table misread.')
        return struct.unpack_from('<I', self.raw, at + 0x14)[0]

    def child_plug(self, index, position):
        """File offset of the node's child plug (its target node index, s32, comes first)."""
        params = self.node_params(index)
        count, base = struct.unpack_from('<BB', self.raw, params + 0x90 + 2 * _CHILD)
        if position >= count:
            raise ValueError('AINB child plug misread.')
        return struct.unpack_from('<I', self.raw, params + 0xa4 + (base + position) * 4)[0]


def _document(raw):
    import ainb
    return ainb.AINB.from_binary(raw).as_dict()


def _check(raw, expected):
    if _document(raw) != expected:
        raise ValueError('The save warp patch changed more than intended.')


def write_ainb(document):
    """AINB bytes of an ``as_dict`` document, read back to check them.

    The ainb library writes an empty blackboard section 8 bytes short for version 0x408
    (0x30 instead of the 0x38 its offsets count), shifting everything after it: an
    explicit empty blackboard is written at full size."""
    import ainb
    from ainb.blackboard import Blackboard
    module = ainb.AINB.from_dict(copy.deepcopy(document))
    if module.blackboard is None:
        module.blackboard = Blackboard()
    raw = module.to_binary()
    _check(raw, document)
    return raw


# --- node builders (the ``as_dict`` form of the ainb library) ---------------------------

def _guid(key):
    return str(uuid.uuid5(uuid.NAMESPACE_OID, 'oot-rando-save-warp-' + key))


def _node(document, kind, name, key, flags=(), queries=(), properties=None, inputs=None, outputs=None,
          plugs=None):
    """Append a node to ``document``; returns its index."""
    index = len(document['Nodes'])
    document['Nodes'].append({
        'Node Type': kind, 'Node Index': index, 'Name': name, 'GUID': _guid(f'{document["Filename"]}-{key}'),
        'Flags': list(flags), 'Queries': list(queries), 'Attachments': [], 'Properties': properties or {},
        'Parameters': {'Inputs': inputs or {}, 'Outputs': outputs or {}}, 'XLink Actions': [], 'Plugs': plugs or {}})
    return index


def _param(name, value, source=-1):
    return {'Name': name, 'Default Value': value, 'Node Index': source, 'Output Index': 0,
            'Flags': [] if source != -1 else ['Uses Default']}


_ONCE = {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]}
_QUERY = {'Bool': [{'Name': 'OutputOnlyOnEnter', 'Default Value': False, 'Flags': []}]}
_CHOOSE = {'Int': [{'Name': 'CalculateTiming', 'Default Value': 0, 'Flags': []}],
           'Bool': [{'Name': 'ChildFrameSync', 'Default Value': False, 'Flags': []},
                    {'Name': 'IsNoSelectWhenChildBusy', 'Default Value': False, 'Flags': []}]}
_SEQUENTIAL = {'Int': [{'Name': name, 'Default Value': 0, 'Flags': []}
                       for name in ('BusyPolicy', 'NumLoop', 'PlayPolicy', 'ResultPolicy')],
               'Bool': [{'Name': name, 'Default Value': False, 'Flags': []}
                        for name in ('IsDelayJudge', 'IsLoop', 'IsUpdateNextInFrame')]}


def _bool_query(document, key, name):
    return _node(document, 'UserDefined', 'SeqQueryGetNonStructGameDataBool', key, flags=['Is Query'],
                 properties=copy.deepcopy(_QUERY),
                 inputs={'Int': [_param('GameDataIndex', -1)], 'Bool': [_param('IsDirect', False)],
                         'String': [_param('GameDataFullName', name)]},
                 outputs={'Bool': [{'Name': 'Value', 'Is Output': True}]})


def _bool_selector(document, key, query, when_true, when_false):
    properties = copy.deepcopy(_CHOOSE)
    properties['Bool'].insert(1, {'Name': 'InputValue', 'Default Value': False, 'Flags': []})
    return _node(document, 'Element_BoolSelector', '', key, queries=[query], properties=properties,
                 inputs={'Bool': [_param('Input', False, query)]},
                 plugs={'Generic': [{'Node Index': query, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                        'Child': [{'Node Index': when_true, 'Name': 'True'},
                                  {'Node Index': when_false, 'Name': 'False'}]})


def _sequential(document, key, children, transition=None, root=False):
    plugs = {'Child': [{'Node Index': child, 'Name': ''} for child in children]}
    if transition is not None:
        plugs['Transition'] = [{'Node Index': transition, 'Transition Type': 1, 'Update Post Calc': False}]
    return _node(document, 'Element_Sequential', '', key, flags=['Is Root Node'] if root else [],
                 properties=copy.deepcopy(_SEQUENTIAL), plugs=plugs)


def _set_bool(document, key, name, value, transition=None):
    plugs = {'Transition': [{'Node Index': transition, 'Transition Type': 1, 'Update Post Calc': True}]} \
        if transition is not None else {}
    return _node(document, 'UserDefined', 'SeqOneShotSetNonStructGameDataBool', key,
                 properties=copy.deepcopy(_ONCE), plugs=plugs,
                 inputs={'Int': [_param('GameDataIndex', -1)], 'Bool': [_param('Value', value)],
                         'String': [_param('GameDataFullName', name)]})


def _set_string64(document, key, name, value):
    return _node(document, 'UserDefined', 'SeqOneShotSetNonStructGameDataString64', key,
                 properties=copy.deepcopy(_ONCE),
                 inputs={'Int': [_param('GameDataIndex', -1)],
                         'String': [_param('GameDataFullName', name), _param('Value', value)]})


# --- the layout: a sixth System button -------------------------------------------------
#
# ``.buil`` files (``BFFH``, "Nintendo.Ui.ResModels.LayoutResData") are serialized object
# graphs: absolute u64 offsets, arrays as (offset, count, element size), a "Default"
# data section followed by the string pool (a ``BFSI`` header each). Dictionaries are
# three parallel arrays (name, value, 64-bit name hash) and a count; the root holds the
# pane dictionary at 0x118 and the parts dictionary at 0x1b8. A pane record (0x44 bytes):
# scale at 0x10, translation at 0x1c, parent index at 0x28, size at 0x2c, end of its
# subtree (pre-order index) at 0x34, kind flags at 0x38, part index at 0x42. A part
# (0x48 bytes): layout name, three optional override arrays, an empty one at 0x38, the
# owner pane index at 0x40 (``Pa_Button_03`` has no overrides and is cloned).

_PANES, _PARTS = 0x118, 0x1b8
_POOL_OFFSET, _POOL_SIZE, _DEFAULT_SIZE = 0xd4, 0xd8, 0xb0
_PANE_SIZE, _PART_SIZE = 0x44, 0x48
BUTTON_STEP = -188.0      # between the last buttons (y: -140, -328, -516)
# The name hash's algorithm is not known; the new name only gets a distinct value.
NEW_BUTTON_HASH = 0x5361766557617270


def _dictionary(raw, at):
    names, values, hashes, count = struct.unpack_from('<QQQI', raw, at)
    keys = []
    for i in range(count):
        offset = struct.unpack_from('<Q', raw, names + 8 * i)[0]
        keys.append(raw[offset:raw.index(b'\0', offset)].decode())
    return keys, [struct.unpack_from('<Q', raw, values + 8 * i)[0] for i in range(count)], \
        [struct.unpack_from('<Q', raw, hashes + 8 * i)[0] for i in range(count)]


def read_layout_dictionaries(raw):
    """``(panes, parts)``: {name: (record offset, hash)} of a ``.buil`` layout."""
    out = []
    for at in (_PANES, _PARTS):
        keys, values, hashes = _dictionary(raw, at)
        out.append({k: (v, h) for k, v, h in zip(keys, values, hashes)})
    return out


def add_system_button(raw):
    """``PaSystemMenu_00.buil`` with ``Pa_Button_05`` under ``Pa_Button_04``."""
    if raw[:4] != b'BFFH' or struct.unpack_from('<I', raw, 8)[0] != len(raw):
        raise ValueError('Unexpected System menu layout.')
    pool = struct.unpack_from('<I', raw, _POOL_OFFSET)[0]
    pool_size = struct.unpack_from('<I', raw, _POOL_SIZE)[0]
    if pool + pool_size != len(raw) or struct.unpack_from('<Q', raw, 0x110)[0] != pool:
        raise ValueError('Unexpected System menu string pool.')
    pane_names, pane_values, pane_hashes = _dictionary(raw, _PANES)
    part_names, part_values, part_hashes = _dictionary(raw, _PARTS)
    buttons = [f'Pa_Button_0{i}' for i in range(5)]
    if pane_names[-5:] != buttons or part_names[1:] != buttons or NEW_BUTTON in pane_names \
            or NEW_BUTTON_HASH in pane_hashes:
        raise ValueError('Unexpected System menu panes.')
    last = pane_values[-1]
    index = len(pane_names)
    record = bytearray(raw[last:last + _PANE_SIZE])
    parent, subtree_end = struct.unpack_from('<II', record, 0x28)[0], struct.unpack_from('<I', record, 0x34)[0]
    part_index = struct.unpack_from('<H', record, 0x42)[0]
    if subtree_end != index or part_index != len(part_names) - 1:
        raise ValueError('Unexpected System menu button record.')
    template = part_values[part_names.index('Pa_Button_03')]
    part = bytearray(raw[template:template + _PART_SIZE])
    if any(part[8:0x38]) or struct.unpack_from('<Q', raw, struct.unpack_from('<Q', part, 0x38)[0] + 8)[0] != 0:
        raise ValueError('Unexpected System menu button part.')

    # New block, inserted where the string pool starts (8-aligned objects inside). Its
    # offsets are final; ``strings`` lists its old string offsets, moved with the pool.
    block = bytearray(-pool % 8)
    strings = []

    def place(data, string_at=()):
        block.extend(b'\0' * (-len(block) % 8))
        at = pool + len(block)
        strings.extend(len(block) + offset for offset in string_at)
        block.extend(data)
        return at
    y = struct.unpack_from('<f', record, 0x20)[0] + BUTTON_STEP
    struct.pack_into('<f', record, 0x20, y)
    struct.pack_into('<I', record, 0x34, index + 1)
    struct.pack_into('<H', record, 0x42, len(part_names))
    new_record = place(bytes(record))
    empty = place(bytes(16))
    struct.pack_into('<Q', part, 0x38, empty)
    struct.pack_into('<I', part, 0x40, index)
    new_part = place(bytes(part), string_at=(0,))
    # Dictionaries: (names, values, hashes) arrays, one entry longer. The new name's
    # offset is filled once the pool has moved.
    tables = {}
    for key, values, hashes, extra in (('panes', pane_values, pane_hashes, new_record),
                                       ('parts', part_values, part_hashes, new_part)):
        at = _PANES if key == 'panes' else _PARTS
        names_at = struct.unpack_from('<Q', raw, at)[0]
        names = [struct.unpack_from('<Q', raw, names_at + 8 * i)[0] for i in range(len(values))]
        tables[key] = (place(struct.pack(f'<{len(names) + 1}Q', *names, 0), string_at=range(0, 8 * len(names), 8)),
                       place(struct.pack(f'<{len(values) + 1}Q', *values, extra)),
                       place(struct.pack(f'<{len(hashes) + 1}Q', *hashes, NEW_BUTTON_HASH)), len(values) + 1)
    block.extend(b'\0' * (-len(block) % 8))
    shift = len(block)
    for at in strings:
        struct.pack_into('<Q', block, at, struct.unpack_from('<Q', block, at)[0] + shift)
    name = NEW_BUTTON.encode() + b'\0'
    out = bytearray(raw[:pool]) + block + raw[pool:] + name
    # Every string offset before the pool moves with it (all are aligned u64 at string
    # starts; the BFSI header's u32 offset is set below).
    starts = {pool} | {i + 1 for i in range(pool, len(raw) - 1) if raw[i] == 0}
    for at in range(0, pool - 7, 8):
        value = struct.unpack_from('<Q', raw, at)[0]
        if pool <= value < len(raw):
            if value not in starts:
                raise ValueError('Unexpected pointer into the System menu string pool.')
            struct.pack_into('<Q', out, at, value + shift)
    new_name = len(raw) + shift
    for key, at in (('panes', _PANES), ('parts', _PARTS)):
        names_at, values_at, hashes_at, count = tables[key]
        struct.pack_into('<Q', out, names_at + 8 * (count - 1), new_name)
        struct.pack_into('<QQQI', out, at, names_at, values_at, hashes_at, count)
    # The new pane closes the subtrees of its ancestors.
    ancestor = parent
    while ancestor != 0xffffffff:
        rec = pane_values[ancestor]
        if struct.unpack_from('<I', out, rec + 0x34)[0] != index:
            raise ValueError('Unexpected System menu pane tree.')
        struct.pack_into('<I', out, rec + 0x34, index + 1)
        ancestor = struct.unpack_from('<I', out, rec + 0x28)[0]
    struct.pack_into('<I', out, _POOL_OFFSET, pool + shift)
    struct.pack_into('<I', out, _POOL_SIZE, pool_size + len(name))
    struct.pack_into('<I', out, _DEFAULT_SIZE, struct.unpack_from('<I', raw, _DEFAULT_SIZE)[0] + shift)
    struct.pack_into('<I', out, 8, len(out))
    return bytes(out)


def patch_layout_archive(sarc_raw):
    files = dict(sarc(sarc_raw))
    files[SYSTEM_LAYOUT] = add_system_button(files[SYSTEM_LAYOUT])
    return byml_codec.build_sarc(files)


def add_button_text(sarc_raw, text=BUTTON_TEXT):
    files = dict(sarc(sarc_raw))
    message = msbt.load(files[MENU_TEXT])
    if 'Pa_System_00-Pa_Button_04-T_Btn_00' not in message.labels:
        raise ValueError('System menu button texts not found.')
    message.add(BUTTON_LABEL, text)
    files[MENU_TEXT] = msbt.dump(message)
    return byml_codec.build_sarc(files)


# --- the patches ---------------------------------------------------------------------

def patch_menu_load(raw):
    """The plus menu's load: after a save warp, the same load (of the save just written) into the warp destination."""
    call, sequence, banc_query = MENU_LOAD_CALL
    document = _document(raw)
    nodes = document['Nodes']
    entry = nodes[call]
    names = {p['Name']: p for p in entry['Parameters']['Inputs']['String']}
    bools = {p['Name']: p.get('Default Value') for p in entry['Parameters']['Inputs']['Bool']}
    query = nodes[banc_query]
    children = [p['Node Index'] for p in nodes[sequence]['Plugs'].get('Child', [])]
    path = names['BancParam'].get('Node Index', -1)
    if (entry['Name'] != 'ChangeBanc.module' or names[START_NAME]['Default Value'] != ''
            or names[START_NAME].get('Node Index', -1) != -1
            or not bools.get('IsLoadFromSaveData') or not bools.get('IsOverrideTraverseBasePos')
            or [p['Name'] for p in entry['Plugs'].get('Child', [])] != ['DoAfterDestroyBanc']
            or nodes[entry['Plugs']['Child'][0]['Node Index']]['Name'] != 'OnLoadGameSaveData.module'
            or path == -1 or path not in entry['Queries'] or nodes[path]['Name'] != 'SeqQueryGenericConcatString'
            or [p.get('Node Index', -1) for p in nodes[path]['Parameters']['Inputs']['String']] != [-1, banc_query, -1]
            or nodes[sequence]['Node Type'] != 'Element_Sequential' or children.count(call) != 1
            or nodes[2]['Node Type'] != 'Element_StateEnd'
            or query['Name'] != 'SeqQueryGetNonStructGameDataString64'
            or query['Parameters']['Inputs']['String'][0]['Default Value'] != 'Sequence_CurrentBanc'):
        raise ValueError('Unexpected plus menu load module.')
    module = next(m for m in document['Modules'] if m['Path'] == 'ChangeBanc.module.ainb')
    load_save = next(m for m in document['Modules'] if m['Path'] == 'OnLoadGameSaveData.module.ainb')

    def banc_path(key, banc):
        """The GameBancParam path query, for a fixed banc."""
        copied = copy.deepcopy(nodes[path])
        copied.update({'Node Index': len(nodes), 'GUID': _guid(f'{document["Filename"]}-{key}'),
                       'Queries': [], 'Plugs': {}})
        copied['Parameters']['Inputs']['String'][1].update(
            {'Default Value': banc, 'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default']})
        nodes.append(copied)
        return copied['Node Index']

    def change_banc(key, start_name, banc=None):
        """The vanilla call (the save loaded once the banc is destroyed), fast load off:
        nothing prepared the destination."""
        copied = copy.deepcopy(entry)
        if banc is not None:
            source = banc_path(key + '-path', banc)
            copied['Queries'] = [source if q == path else q for q in copied['Queries']]
            copied['Plugs']['String'] = [dict(p, **{'Node Index': source}) if p['Node Index'] == path else p
                                         for p in copied['Plugs']['String']]
            for param in copied['Parameters']['Inputs']['String']:
                if param['Name'] == 'BancParam':
                    param['Node Index'] = source
        after = copy.deepcopy(nodes[entry['Plugs']['Child'][0]['Node Index']])   # its own OnLoadGameSaveData
        after.update({'Node Index': len(nodes), 'GUID': _guid(f'{document["Filename"]}-{key}-load-save')})
        nodes.append(after)
        load_save['Instance Count'] += 1
        copied['Plugs']['Child'][0]['Node Index'] = after['Node Index']
        copied.update({'Node Index': len(nodes), 'GUID': _guid(f'{document["Filename"]}-{key}')})
        for param in copied['Parameters']['Inputs']['String']:
            if param['Name'] == START_NAME:
                param['Default Value'] = start_name
        for param in copied['Parameters']['Inputs']['Bool']:
            if param['Name'] == 'IsEnableFastLoad':
                param['Default Value'] = False
        nodes.append(copied)
        # Vector3 parameters use Generic output plugs as well as the consumer's
        # input/Queries records. A copied call must be connected at both ends.
        # Keep the queries shared, as native graphs do for multiple consumers.
        for param in copied['Parameters']['Inputs'].get('Vector3F', []):
            source = nodes[param['Node Index']]
            links = source['Plugs'].get('Generic', [])
            for link in list(links):
                if link['Node Index'] == call:
                    links.append(dict(link, **{'Node Index': copied['Node Index']}))
        module['Instance Count'] += 1
        # Loading restores GameData, including the request flag and current banc.
        # Exit the selectors before that happens: they must not be able to change
        # the active load midway through its callback. Use a native state transition
        # (as Save does), then finish at the original module's StateEnd.
        state = _sequential(document, key + '-state', [copied['Node Index']], transition=2, root=True)
        return _node(document, 'UserDefined', 'SeqOneShotEnd', key + '-start',
                     properties=copy.deepcopy(_ONCE),
                     plugs={'Transition': [{'Node Index': state, 'Transition Type': 1,
                                             'Update Post Calc': True}]})
    in_place = change_banc('change-banc-save-pos', LOAD_MARKER)
    child_home = change_banc('change-banc-home', LOAD_MARKER, CHILD_HOME)
    temple = change_banc('change-banc-temple', ADULT_HOME[1], ADULT_HOME[0])
    age = _bool_selector(document, 'age', _bool_query(document, 'childhood', 'Sequence_IsChildhood'),
                         child_home, temple)
    properties = copy.deepcopy(_CHOOSE)
    properties['String'] = [{'Name': 'InputValue', 'Default Value': '', 'Flags': []}]
    destination = _node(
        document, 'Element_StringSelector', '', 'destination', queries=[banc_query], properties=properties,
        inputs={'String': [_param('Input', '', banc_query)]},
        plugs={'Child': [{'Node Index': in_place, 'Name': '', 'Condition': name} for name in DUNGEONS + VANILLA_LOAD]
               + [{'Node Index': age, 'Name': '', 'Is Default': True}],
               'String': [{'Node Index': banc_query, 'Name': 'Input', 'Unknown': 0, 'Default Value': ''}]})
    normal = _sequential(document, 'normal-load-state', [call], transition=2, root=True)
    normal_start = _node(document, 'UserDefined', 'SeqOneShotEnd', 'normal-load-start',
                         properties=copy.deepcopy(_ONCE),
                         plugs={'Transition': [{'Node Index': normal, 'Transition Type': 1,
                                                 'Update Post Calc': True}]})
    gate = _bool_selector(document, 'gate', _bool_query(document, 'flag', SAVE_WARP_FLAG),
                           destination, normal_start)
    # The decision must itself be a state, outside the preparation Sequential:
    # transitions from its selector children then reach the state machine directly.
    nodes[gate]['Flags'].append('Is Root Node')
    del nodes[sequence]['Plugs']['Child'][children.index(call)]
    nodes[sequence]['Plugs']['Transition'][0]['Node Index'] = gate
    return write_ainb(document)


def _module_call(document, key, name, inputs=None):
    """A call of ``Sequence/<name>.ainb`` (``name`` ends with ``.module``)."""
    path = name + '.ainb'
    entry = next((m for m in document['Modules'] if m['Path'] == path), None)
    if entry is None:
        document['Modules'].append({'Path': path, 'Category': 'Sequence', 'Instance Count': 1})
    else:
        entry['Instance Count'] += 1
    return _node(document, 'UserDefined', name, key, flags=['Is Module'], inputs=inputs)


def _simultaneous(document, key, children):
    return _node(document, 'Element_Simultaneous', '', key,
                 properties={'Int': [{'Name': 'EndPolicy', 'Default Value': 0, 'Flags': []},
                                     {'Name': 'ResultPolicy', 'Default Value': 0, 'Flags': []}]},
                 plugs={'Child': [{'Node Index': child, 'Name': ''} for child in children]})


def _leave_menu(document):
    """What the load screen does before the plus menu's load (``LoadCheck.module``, "Load"
    outside the title screen): close the overlay; from the menu's pre-game pause, the full
    game pause, the menu's screen capture cancelled."""
    overlay = _node(document, 'UserDefined', 'SeqOneShotCloseScreen', 'close-overlay', properties=copy.deepcopy(_ONCE),
                    inputs={'Bool': [_param('IsDirect', False)], 'String': [_param('ScreenName', 'SystemOverlay_00')]})
    paused = _node(document, 'UserDefined', 'SeqQueryGetNonStructGameDataBool', 'pre-game-pause', flags=['Is Query'],
                   properties=copy.deepcopy(_QUERY),
                   inputs={'Int': [_param('GameDataIndex', -1)], 'Bool': [_param('IsDirect', True)],
                           'String': [_param('GameDataFullName', 'Sequence_IsPreGamePause')]},
                   outputs={'Bool': [{'Name': 'Value', 'Is Output': True}]})
    pause = _simultaneous(document, 'game-pause', [
        _module_call(document, 'leave-pre-game-pause', 'ChangePreGamePause.module',
                     {'Bool': [_param('IsPause', False)]}),
        _node(document, 'UserDefined', 'SeqOneShotRequestCancelGameScreenCapture', 'cancel-capture',
              properties=copy.deepcopy(_ONCE), inputs={'Int': [_param('Target', 1)], 'Bool': [_param('IsForce', True)]}),
        _module_call(document, 'game-pause-on', 'GamePauseOn.module')])
    no_pause = _node(document, 'UserDefined', 'SeqOneShotEnd', 'no-pause', properties=copy.deepcopy(_ONCE))
    return _simultaneous(document, 'leave-menu',
                         [overlay, _bool_selector(document, 'paused', paused, pause, no_pause)])


def _select_written_save(document):
    """Capture the manual slot about to be written, using the save action's query.

    GetLatestSaveIndex is used by Retry and tracks the previously loaded save;
    a manual write must not rely on it becoming the latest loaded index.
    Capture before the write/caption update can advance the manual slot.
    """
    nodes = document['Nodes']
    caption = _node(document, 'UserDefined', 'SeqQueryGetNonStructGameDataStruct', 'caption', flags=['Is Query'],
                    properties=copy.deepcopy(_QUERY),
                    inputs={'Int': [_param('GameDataIndex', -1)], 'Bool': [_param('IsDirect', False)],
                            'String': [_param('GameDataFullName', 'CaptionData')]},
                    outputs={'Pointer': [{'Name': 'Value', 'Classname': 'const void', 'Is Output': True}]})
    slot = next(p['Node Index'] for p in nodes[5]['Parameters']['Inputs']['Int']
                if p['Name'] == 'SlotIndex')
    if slot < 0 or nodes[slot]['Name'] != 'SeqQueryGameDataGetManualSaveIndex':
        raise ValueError('Unexpected manual save slot query.')
    nodes[caption]['Plugs'] = {'Generic': [{'Node Index': len(nodes), 'Name': 'Value'}]}
    return _node(document, 'UserDefined', 'SeqOneShotSetGameDataInt', 'select', queries=[slot, caption],
                 properties=copy.deepcopy(_ONCE),
                 inputs={'Int': [_param('GameDataIndex', -1), _param('Value', 0, slot)],
                         'String': [_param('GameDataName', 'SelectedSavePathIndex')],
                         'Pointer': [{'Name': 'ParentStruct', 'Classname': 'const void', 'Default Value': None,
                                      'Node Index': caption, 'Output Index': 0, 'Flags': []}]},
                 plugs={'Int': [{'Node Index': slot, 'Name': 'Value'}]})


def _wait_saves(document):
    """What the plus menu does before any of its loads (``ConfirmationLoad.module``): wait
    for the auto save manager, then for the caption manager to be stable. The save just
    written is only then readable; a load started earlier reads the previous one."""
    nodes = document['Nodes']
    wait_auto = next(n for n in nodes if n['Name'] == 'SeqExecuteWaitAutoSave')
    auto = _node(document, 'UserDefined', 'SeqExecuteWaitAutoSave', 'wait-auto-save',
                 inputs=copy.deepcopy(wait_auto['Parameters']['Inputs']))
    stable = _node(document, 'UserDefined', 'SeqExecuteWaitCaptionMgrStable', 'wait-caption-stable')
    return _simultaneous(document, 'wait-auto-save-any', [auto]), stable


def patch_save(raw):
    """With the flag, "Save" captures its slot and saves (the flag cleared during the save),
    waits for the save to be readable, leaves the menu as the load screen does, sets the
    flag and ends with ``Warp``."""
    document = _document(raw)
    nodes = document['Nodes']
    choice = nodes[0]['Plugs']['Child']
    if ([(p.get('Condition'), p['Node Index']) for p in choice[:2]] != [('Pa_CheckButton_00', 1),
                                                                         ('Pa_CheckButton_01', 12)]
            or nodes[1]['Plugs'] != {'Transition': [{'Node Index': 10, 'Transition Type': 1, 'Update Post Calc': True}]}
            or [p['Node Index'] for p in nodes[10]['Plugs']['Child']] != [54, 25, 27]
            or [p['Node Index'] for p in nodes[11]['Plugs']['Child']] != [35, 23, 56]
            or [p['Node Index'] for p in nodes[24]['Plugs']['Child']] != [15, 31]
            or nodes[5]['Name'] != 'SeqExecuteSaveGameData'):
        raise ValueError('Unexpected Save module.')
    end = _node(document, 'Element_StateEnd', '', 'end-warp', flags=['Is Root Node'],
                properties={'String': [{'Name': 'TransitionCommand', 'Default Value': 'Warp', 'Flags': []}]})
    after = _sequential(document, 'after-save',
                        [35, 23, 56, *_wait_saves(document), _leave_menu(document),
                         _set_bool(document, 'flag-on', SAVE_WARP_FLAG, True)],
                        transition=end, root=True)
    save = _sequential(document, 'save', [_set_bool(document, 'flag-off', SAVE_WARP_FLAG, False),
                                        54, 25, _select_written_save(document), 27],
                       transition=after, root=True)
    start = _node(document, 'UserDefined', 'SeqOneShotEnd', 'start', properties=copy.deepcopy(_ONCE),
                  plugs={'Transition': [{'Node Index': save, 'Transition Type': 1, 'Update Post Calc': True}]})
    choice[0]['Node Index'] = _bool_selector(document, 'warp', _bool_query(document, 'flag', SAVE_WARP_FLAG),
                                             start, 1)
    # Cancel / B: the request ends.
    nodes[24]['Plugs']['Child'].append({'Node Index': _set_bool(document, 'cancel', SAVE_WARP_FLAG, False),
                                        'Name': ''})
    return write_ainb(document)


def patch_plus_menu(raw):
    """The new System button opens the save screen with the flag; its ``Warp`` end runs the load."""
    document = _document(raw)
    nodes = document['Nodes']
    save, load = nodes[SAVE_NODE], nodes[MENU_LOAD_NODE]
    buttons, other = nodes[SYSTEM_BUTTONS]['Plugs']['Child'], nodes[SYSTEM_BUTTONS_OTHER]['Plugs']['Child']
    expected = [f'Pa_System_00/Pa_Button_0{i}' for i in range(5)]
    if (save['Name'] != 'Save.module' or load['Name'] != '_LocalModule_bde133631675.module'
            or sorted(p['Transition Name'] for p in save['Plugs']['Transition']) != ['No', 'Yes']
            or [p.get('Condition') for p in buttons[:-1]] != expected or not buttons[-1].get('Is Default')
            or [p.get('Condition') for p in other[:-1]] != expected or not other[-1].get('Is Default')
            or buttons[0]['Node Index'] != 53
            or nodes[53]['Plugs'] != {'Transition': [{'Node Index': SAVE_NODE, 'Transition Type': 1,
                                                      'Update Post Calc': True}]}):
        raise ValueError('Unexpected PlusMenu module.')
    save['Plugs']['Transition'].append({'Node Index': MENU_LOAD_NODE, 'Transition Type': 0,
                                        'Update Post Calc': True, 'Transition Name': 'Warp'})
    request = _set_bool(document, 'request', SAVE_WARP_FLAG, True)
    nodes[request]['Plugs'] = copy.deepcopy(nodes[53]['Plugs'])     # then the save screen, as Save
    buttons.insert(len(buttons) - 1, {'Node Index': request, 'Name': '', 'Condition': BUTTON_PATH})
    other.insert(len(other) - 1, {'Node Index': other[0]['Node Index'], 'Name': '', 'Condition': BUTTON_PATH})
    return write_ainb(document)


def rewire_on_load(raw):
    """Missing start names fall back on the banc's IsAlwaysStartFromStartPos, then on the caller's position."""
    original = _document(raw)
    nodes = original['Nodes']
    if len(nodes) != 131 or any((nodes[i]['Name'] or nodes[i]['Node Type']) != name
                                for i, name in ON_LOAD_NAMES.items()):
        raise ValueError('Unexpected OnLoadBancParam module.')
    query = nodes[43]['Parameters']['Inputs']['String'][0]
    marker = nodes[71]['Plugs']['Child']
    if (query['Default Value'] != ALWAYS_START or [p.get('Node Index') for p in marker] != [11, 76]
            or marker[0].get('Condition') != '' or nodes[76]['Queries'] != [75]):
        raise ValueError('Unexpected OnLoadBancParam wiring.')
    module = _Module(raw)
    result = bytearray(raw)
    expected = copy.deepcopy(original)
    for node, position, vanilla, new in ON_LOAD_REWIRING:
        plug = nodes[node]['Plugs']['Child'][position]
        at = module.child_plug(node, position)
        if plug.get('Name') != 'False' or plug['Node Index'] != vanilla \
                or struct.unpack_from('<i', raw, at)[0] != vanilla:
            raise ValueError('Unexpected OnLoadBancParam wiring.')
        struct.pack_into('<i', result, at, new)
        expected['Nodes'][node]['Plugs']['Child'][position]['Node Index'] = new
    result = bytes(result)
    _check(result, expected)
    return result


def set_always_start(raw, value):
    """GameBancParam with ``IsAlwaysStartFromStartPos`` set to ``value``."""
    document = byml_codec.load(raw)
    if ALWAYS_START in document['root']:
        raise ValueError('GameBancParam already sets ' + ALWAYS_START)
    document['root'][ALWAYS_START] = bool(value)
    return byml_codec.dump(document)


def patch_save_warp(read, messages=(), read_archive=None):
    """Every resource of the save warp. ``read(path)``: original bytes of an uncompressed
    resource; ``read_archive(path)``: decompressed archive (layouts, messages). Returns {path: bytes}."""
    files = {ON_LOAD_MODULE: rewire_on_load(read(ON_LOAD_MODULE)),
             SAVE_MODULE: patch_save(read(SAVE_MODULE)),
             PLUS_MENU_MODULE: patch_plus_menu(read(PLUS_MENU_MODULE)),
             MENU_LOAD_MODULE: patch_menu_load(read(MENU_LOAD_MODULE))}
    if read_archive is not None:
        files[LAYOUT_ARCHIVE] = patch_layout_archive(read_archive(LAYOUT_ARCHIVE))
        for path in messages:
            files[path] = add_button_text(read_archive(path))
    parents = {}
    for name in ZONES + VANILLA_LOAD:
        parent = byml_codec.load(read(banc_param(name)))['root'].get('$parent')
        parents[name] = parent.rsplit('/', 1)[-1].split('.')[0] if parent else None
    for name in ZONES:
        files[banc_param(name)] = set_always_start(read(banc_param(name)), True)
    for name in VANILLA_LOAD:
        ancestor = parents[name]
        while ancestor and ancestor not in ZONES:
            ancestor = parents.get(ancestor)
        if ancestor:   # inherits the parameter from a zone: set back to false
            files[banc_param(name)] = set_always_start(read(banc_param(name)), False)
    return files
