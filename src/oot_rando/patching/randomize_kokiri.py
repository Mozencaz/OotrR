"""Kokiri Forest map constants and BYML slot / map / RESTBL patch primitives."""
import copy
import struct

from oot_rando.formats.inspect_resources import Byml

TITLE = '0400486024DEC000'
BUILD = 'e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348000000000000000000000000'
UPDATE_VERSION = 131072


def check_supported_game(nup):
    """Raise a clear ValueError unless the NUP holds the supported base game + update.

    Only the title ids, the update version and the main NSO build id matter; the
    package order and directory indices depend on the tool that made the dump."""
    base, update = int(TITLE, 16), int(TITLE, 16) + 0x800
    found = {p[0]: p[4] for p in nup.packages}
    if base not in found:
        ids = ', '.join(f'{t:016X}' for t in found) or 'none'
        raise ValueError(f'Unsupported NUP structure: this is not Ocarina of Time ({TITLE}). '
                         f'Title ids found: {ids}.')
    if update not in found:
        raise ValueError(f'Unsupported NUP structure: the game update is missing. Dump the game '
                         f'together with update v{UPDATE_VERSION} into one .nup.')
    if found[update] != UPDATE_VERSION:
        raise ValueError(f'Unsupported game update v{found[update]}: this randomizer supports '
                         f'update v{UPDATE_VERSION} only.')
    try:
        main = nup.read('1/exefs/main')
    except KeyError:
        raise ValueError('Unsupported NUP structure: the update has no exefs/main.') from None
    if main[:4] != b'NSO0' or main[0x40:0x60].hex() != BUILD:
        raise ValueError('Unsupported game build.')
MAP = 'Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs'
RESTBL = 'System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs'
CHESTS = {10831981390482426294: 'TBox_Rupee_Green', 4555665598794293658: 'TBox_Rupee_Blue',
          9725242744547055868: 'TBox_Rupee_Blue', 12786193094758345086: 'TBox_Rupee_Blue'}
POOL = ['TBox_Rupee_Green', 'TBox_Rupee_Blue', 'TBox_Rupee_Red', 'TBox_Rupee_Purple',
        'TBox_Rupee_Gold', 'TBox_DekuNutBundle', 'TBox_DekuSeedBundle',
        'TBox_ArrowBundle_Small', 'TBox_ArrowBundle_Medium', 'TBox_ArrowBundle_Large',
        'TBox_Shield_Deku', 'TBox_Shield_Hylian']


def slot(byml, path, expected_type=0xa0):
    off = byml.u32(12)
    for depth, key in enumerate(path):
        typ = byml.data[off]
        count = byml.u24(off+1)
        if typ == 0xc1:
            matches = [off+8+i*8 for i in range(count) if byml.keys[byml.u24(off+4+i*8)] == key]
            if len(matches) != 1:
                raise ValueError(f'Ambiguous field: {path}')
            value_off = matches[0]
            value_type = byml.data[value_off-1]
        elif typ == 0xc0 and isinstance(key, int) and 0 <= key < count:
            value_off = ((off+4+count+3)&~3)+key*4
            value_type = byml.data[off+4+key]
        else:
            raise ValueError(f'Invalid path: {path}')
        if depth == len(path)-1:
            if value_type != expected_type:
                raise ValueError('Unexpected field type')
            return value_off
        if value_type not in (0xc0, 0xc1):
            raise ValueError('Invalid intermediate node')
        off = byml.u32(value_off)


def patch_map(raw, placements):
    b = Byml(raw)
    strings = list(b.strings)
    for reward in placements.values():
        if reward not in strings:
            strings.append(reward)
    # Relocate only the value string table. Existing node and value indices stay valid.
    table = bytearray(b'\xc2' + len(strings).to_bytes(3, 'little'))
    encoded = [s.encode('utf-8')+b'\0' for s in strings]
    offset = 4 + 4*(len(strings)+1)
    for s in encoded:
        table.extend(struct.pack('<I', offset))
        offset += len(s)
    table.extend(struct.pack('<I', offset))
    table.extend(b''.join(encoded))
    result = bytearray(raw)
    result.extend(b'\0' * (-len(result)%4))
    table_offset = len(result)
    result.extend(table)
    struct.pack_into('<I', result, 8, table_offset)
    expected = copy.deepcopy(b.root)
    manifest = []
    found = set()
    for i, actor in enumerate(b.root['Actors']):
        ident = actor.get('Hash')
        if ident not in CHESTS:
            continue
        if ident in found or actor.get('Gyaml') != 'Obj_TBox_A_01':
            raise ValueError('Unexpected chest identity')
        found.add(ident)
        dynamic = actor['Dynamic']
        if dynamic.get('Drop__DropActor') != CHESTS[ident] or dynamic.get('GetEventName') != 'KokiriForest_TreasureBox_NaviChatOff':
            raise ValueError('Original chest data mismatch')
        reward = placements[ident]
        # BYML nodes may be deduplicated: the three blue chests share one
        # Dynamic node. Clone it before patching to keep rewards independent.
        pointer = slot(b, ['Actors', i, 'Dynamic'], 0xc1)
        dynamic_start = b.u32(pointer)
        dynamic_size = 4 + 8*b.u24(dynamic_start+1)
        result.extend(b'\0' * (-len(result)%4))
        clone = len(result)
        result.extend(raw[dynamic_start:dynamic_start+dynamic_size])
        off = slot(b, ['Actors', i, 'Dynamic', 'Drop__DropActor'])
        struct.pack_into('<I', result, clone+off-dynamic_start, strings.index(reward))
        struct.pack_into('<I', result, pointer, clone)
        expected['Actors'][i]['Dynamic']['Drop__DropActor'] = reward
        manifest.append({'hash': str(ident), 'position': actor['Translate'], 'before': CHESTS[ident], 'after': reward})
    if found != set(CHESTS) or Byml(bytes(result)).root != expected:
        raise ValueError('Patch verification failed')
    return bytes(result), manifest
