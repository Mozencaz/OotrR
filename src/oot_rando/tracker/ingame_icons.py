"""The items' icons for the in-game tracker (``romfs/RandoTracker/icons.bin``), from the player's own game.

Each icon is the game's own picture (RomFS ``UI/Tex/Icon/<name>.bntx.zs``) copied as the BNTX stores it:
ASTC 4x4 blocks in the GPU's block-linear layout, with that layout's description. Nothing is decoded here;
the module makes GPU textures of the bytes. Nothing of the game ships with the application: the file is
written on the player's PC, from their game, into their seed. Format: docs/ingame-tracker-format.md.
"""
import struct

import zstandard

from oot_rando.tracker.game_overlay import GRID, ICONS

ICON_FILE = 'RandoTracker/icons.bin'
MAGIC, VERSION = b'RTIC', 1
HEADER = struct.Struct('<4sHHIIIIII')   # 32 bytes
ENTRY = struct.Struct('<32sIIII8s4sI')  # 64 bytes
NAME_ROOM = 32
MAX_ICONS = 30                          # the module's icon atlas
MAX_SIZE = 4 << 20                      # one picture's most bytes (the module's staging memory)
MAX_SIDE = 4096
DATA_ALIGN = 16
ASTC_4X4 = (0x2D01, 0x2D06)             # BNTX: ASTC 4x4 unorm, sRGB
# A smaller picture of the same item, where the usual one is much larger (Item_Hammer is 1440 px, this 683).
SMALLER = {'Megaton Hammer': 'Item_Hammer_PouchIcon'}


def grid_icons():
    """(item, picture name) of each item of the panel's grid that has a picture, in the grid's order."""
    return [(item, SMALLER.get(item, ICONS[item][0])) for row in GRID for item, *_ in row if item in ICONS]


def texture(bntx):
    """The first level of a BNTX's only texture, if it is ASTC 4x4 in block-linear layout."""
    if bntx[:4] != b'BNTX':
        raise ValueError('not a BNTX')
    at = bntx.find(b'BRTI')
    if at < 0 or bntx.find(b'BRTI', at + 4) >= 0:
        raise ValueError('not one texture')
    tile_mode, = struct.unpack_from('<H', bntx, at + 0x12)
    levels, = struct.unpack_from('<H', bntx, at + 0x16)
    fmt, = struct.unpack_from('<I', bntx, at + 0x1C)
    width, height = struct.unpack_from('<II', bntx, at + 0x24)
    size, = struct.unpack_from('<I', bntx, at + 0x50)
    table, = struct.unpack_from('<Q', bntx, at + 0x70)
    offsets = [struct.unpack_from('<Q', bntx, table + 8 * level)[0] for level in range(max(levels, 1))]
    if tile_mode != 0 or fmt not in ASTC_4X4:
        raise ValueError(f'not ASTC 4x4 in block-linear layout ({fmt:#x}, tile mode {tile_mode})')
    if levels > 1:
        size = offsets[1] - offsets[0]
    data = bntx[offsets[0]:offsets[0] + size]
    if len(data) != size:
        raise ValueError('truncated')
    return {'width': width, 'height': height, 'format': fmt, 'layout': bntx[at + 0x34:at + 0x3C],
            'swizzle': bntx[at + 0x58:at + 0x5C], 'data': data}


def _padded(n):
    return -(-n // DATA_ALIGN) * DATA_ALIGN


def build(icons):
    """icons.bin from ``[(item, texture(...))]``."""
    if not 0 < len(icons) <= MAX_ICONS:
        raise ValueError('between 1 and %d icons' % MAX_ICONS)
    index_at = HEADER.size
    at = data_at = index_at + ENTRY.size * len(icons)
    entries, data = [], bytearray()
    for item, picture in icons:
        name = item.encode('utf-8')
        if len(name) >= NAME_ROOM:
            raise ValueError('item name too long: ' + item)
        entries.append(ENTRY.pack(name, picture['width'], picture['height'], at, len(picture['data']),
                                  picture['layout'], picture['swizzle'], picture['format']))
        data += picture['data'] + bytes(_padded(len(picture['data'])) - len(picture['data']))
        at = data_at + len(data)
    size = data_at + len(data)
    return HEADER.pack(MAGIC, VERSION, HEADER.size, size, len(icons), index_at, ENTRY.size, data_at, 0) + b''.join(entries) + data


def parse(data):
    """``[(item, entry)]`` of an icons.bin, checked as the module checks it."""
    if len(data) < HEADER.size:
        raise ValueError('truncated')
    magic, version, header_size, size, count, index_at, entry_size, data_at, reserved = HEADER.unpack_from(data)
    if (magic, version, header_size, entry_size, index_at, reserved) != (MAGIC, VERSION, HEADER.size, ENTRY.size, HEADER.size, 0):
        raise ValueError('not an icons file of a version this reader knows')
    if size != len(data) or not 0 < count <= MAX_ICONS or data_at != index_at + count * ENTRY.size or data_at > size:
        raise ValueError('bad header')
    icons, names = [], set()
    for i in range(count):
        raw, width, height, at, length, layout, swizzle, fmt = ENTRY.unpack_from(data, index_at + i * ENTRY.size)
        if b'\0' not in raw or not raw.split(b'\0')[0]:
            raise ValueError('bad item name')
        name = raw.split(b'\0')[0].decode('utf-8')
        blocks = -(-width // 4) * -(-height // 4) * 16
        if (name in names or not 0 < width <= MAX_SIDE or not 0 < height <= MAX_SIDE or fmt not in ASTC_4X4
                or not blocks <= length <= MAX_SIZE or at < data_at or at % DATA_ALIGN or at + length > size
                or any(source > 5 for source in swizzle)):
            raise ValueError('bad icon: ' + name)
        names.add(name)
        icons.append((name, {'width': width, 'height': height, 'format': fmt, 'layout': layout, 'swizzle': swizzle,
                             'data': data[at:at + length]}))
    return icons


def icons_file(read_picture):
    """icons.bin for the grid, from ``read_picture(name)`` (the decompressed ``UI/Tex/Icon/<name>.bntx.zs``;
    KeyError when the game has no such file); None if none could be read."""
    icons = []
    for item, name in grid_icons():
        try:
            icons.append((item, texture(read_picture(name))))
        except (KeyError, ValueError, struct.error, zstandard.ZstdError):
            continue   # another version of the game: that item shows as its letters
    return build(icons) if icons else None


def nup_reader(nup, dicts=None):
    """read_picture for icons_file from an open NUP (``dicts``: its zstd dictionaries, if already read)."""
    from oot_rando.formats.inspect_resources import decompress, dictionaries
    dicts = dictionaries(nup) if dicts is None else dicts
    return lambda name: decompress(nup.read(nup.latest(f'romfs/UI/Tex/Icon/{name}.bntx.zs')), dicts)
