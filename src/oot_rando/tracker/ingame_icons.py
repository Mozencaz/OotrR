"""The items' icons for the in-game tracker (``romfs/RandoTracker/icons.bin``), from the player's own game.

Each icon is the game's own picture (RomFS ``UI/Tex/Icon/<name>.bntx.zs``; for the spiritual stones and the
medallions, the file select's, in its common layout archive) copied as the BNTX stores it: ASTC 4x4 blocks in
the GPU's block-linear layout, with that layout's description. Nothing is decoded here;
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
MAX_ICONS = 40                          # the module's icon atlas
MAX_SIZE = 4 << 20                      # one picture's most bytes (the module's staging memory)
MAX_SIDE = 4096
DATA_ALIGN = 16
ASTC_4X4 = (0x2D01, 0x2D06)             # BNTX: ASTC 4x4 unorm, sRGB
# A smaller picture of the same item, where the usual one is much larger (Item_Hammer is 1440 px, this 683).
SMALLER = {'Megaton Hammer': 'Item_Hammer_PouchIcon'}
# The spiritual stones and the medallions have no icon (the pause menu shows their models): the file select's
# pictures of them, in the common layout archive, stand in.
LAYOUT_ARCHIVE = 'UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs'
LAYOUT_PICTURES = {
    'Kokiri Emerald': 'DataFileImportantIcon_00', 'Goron Ruby': 'DataFileImportantIcon_01',
    'Zora Sapphire': 'DataFileImportantIcon_02', 'Light Medallion': 'DataFileImportantIcon_03',
    'Forest Medallion': 'DataFileImportantIcon_04', 'Fire Medallion': 'DataFileImportantIcon_05',
    'Water Medallion': 'DataFileImportantIcon_06', 'Spirit Medallion': 'DataFileImportantIcon_07',
    'Shadow Medallion': 'DataFileImportantIcon_08',
}
# The dungeons' keys, for the panel's key row (named as the module looks them up; not grid items).
KEY_ICONS = [('Small Key', 'Item_Dungeon_SmallKey'), ('Boss Key', 'Item_Dungeon_BossKey')]
MAX_HEADER = 8 << 20                    # an archive's header (its texture records), the most read


def grid_icons():
    """(item, picture name) of each picture the panel uses: the grid's items that have one, in the grid's
    order, then the keys."""
    icons = []
    for row in GRID:
        for item, *_ in row:
            if item in LAYOUT_PICTURES:
                icons.append((item, LAYOUT_PICTURES[item]))
            elif item in ICONS:
                icons.append((item, SMALLER.get(item, ICONS[item][0])))
    return icons + KEY_ICONS


def _record(data, at, data_from=0):
    """(name, picture without its data, data offset, data size) of the BRTI record at ``at``, if it is
    ASTC 4x4 in block-linear layout."""
    if data[at:at + 4] != b'BRTI':
        raise ValueError('not a texture record')
    tile_mode, = struct.unpack_from('<H', data, at + 0x12)
    levels, = struct.unpack_from('<H', data, at + 0x16)
    fmt, = struct.unpack_from('<I', data, at + 0x1C)
    width, height = struct.unpack_from('<II', data, at + 0x24)
    size, = struct.unpack_from('<I', data, at + 0x50)
    name_at, table = struct.unpack_from('<Q', data, at + 0x60)[0], struct.unpack_from('<Q', data, at + 0x70)[0]
    length = struct.unpack_from('<H', data, name_at)[0] if name_at + 2 <= len(data) else 0
    name = data[name_at + 2:name_at + 2 + length].decode('utf-8', 'replace')
    offsets = [struct.unpack_from('<Q', data, table + 8 * level)[0] for level in range(max(levels, 1))]
    if tile_mode != 0 or fmt not in ASTC_4X4:
        raise ValueError(f'not ASTC 4x4 in block-linear layout ({fmt:#x}, tile mode {tile_mode})')
    if levels > 1:
        size = offsets[1] - offsets[0]
    if offsets[0] < data_from:
        raise ValueError('texture data inside the header')
    return name, {'width': width, 'height': height, 'format': fmt, 'layout': data[at + 0x34:at + 0x3C],
                  'swizzle': data[at + 0x58:at + 0x5C]}, offsets[0], size


def texture(bntx):
    """The first level of a BNTX's only texture, if it is ASTC 4x4 in block-linear layout."""
    if bntx[:4] != b'BNTX':
        raise ValueError('not a BNTX')
    at = bntx.find(b'BRTI')
    if at < 0 or bntx.find(b'BRTI', at + 4) >= 0:
        raise ValueError('not one texture')
    _, picture, offset, size = _record(bntx, at)
    picture['data'] = bntx[offset:offset + size]
    if len(picture['data']) != size:
        raise ValueError('truncated')
    return picture


def archive_textures(read, names):
    """``{name: texture}`` of the textures named, of a BNTX of many whose decompressed bytes come in order
    from ``read(n)``: its header (the records), then only as far as the last texture wanted. A texture that
    isn't there, or isn't ASTC 4x4 in block-linear layout, is left out."""
    head = read(0x40)
    if len(head) < 0x40 or head[:4] != b'BNTX':
        raise ValueError('not a BNTX')
    count, = struct.unpack_from('<I', head, 0x24)
    table, data_at = struct.unpack_from('<Q', head, 0x28)[0], struct.unpack_from('<Q', head, 0x30)[0]
    if not 0x40 <= table < data_at <= MAX_HEADER:
        raise ValueError('bad archive header')
    head += read(data_at - 0x40)
    if len(head) != data_at:
        raise ValueError('truncated')
    wanted = []
    for i in range(count):
        try:
            name, picture, offset, size = _record(head, struct.unpack_from('<Q', head, table + 8 * i)[0], data_at)
        except ValueError:
            continue
        if name in names:
            wanted.append((offset, size, name, picture))
    found, at = {}, data_at
    for offset, size, name, picture in sorted(wanted):
        if offset < at:
            continue   # overlaps the last one read
        while at < offset:
            skipped = len(read(min(offset - at, 1 << 20)))
            if not skipped:
                raise ValueError('truncated')
            at += skipped
        picture['data'] = read(size)
        if len(picture['data']) != size:
            raise ValueError('truncated')
        at += size
        found[name] = picture
    return found


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


def icons_file(read_picture, read_layout=None):
    """icons.bin for the panel, from ``read_picture(name)`` (the decompressed ``UI/Tex/Icon/<name>.bntx.zs``;
    KeyError when the game has no such file) and ``read_layout(names)`` (``{name: texture}`` of the layout
    archive's, see :func:`archive_textures`); None if none could be read."""
    layout = {}
    if read_layout is not None:
        try:
            layout = read_layout({name for item, name in grid_icons() if item in LAYOUT_PICTURES})
        except (KeyError, ValueError, struct.error, zstandard.ZstdError):
            layout = {}
    icons = []
    for item, name in grid_icons():
        try:
            icons.append((item, layout[name] if item in LAYOUT_PICTURES else texture(read_picture(name))))
        except (KeyError, ValueError, struct.error, zstandard.ZstdError):
            continue   # another version of the game: that item shows as its letters
    return build(icons) if icons else None


def nup_reader(nup, dicts=None):
    """read_picture for icons_file from an open NUP (``dicts``: its zstd dictionaries, if already read)."""
    from oot_rando.formats.inspect_resources import decompress, dictionaries
    dicts = dictionaries(nup) if dicts is None else dicts
    return lambda name: decompress(nup.read(nup.latest(f'romfs/UI/Tex/Icon/{name}.bntx.zs')), dicts)


def nup_layout_reader(nup):
    """read_layout for icons_file from an open NUP: the archive is one zstd frame without a dictionary,
    decompressed as it is read."""
    import io

    def read_layout(names):
        stream = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(nup.read(nup.latest('romfs/' + LAYOUT_ARCHIVE))))
        with stream:
            return archive_textures(stream.read, names)
    return read_layout


def nup_icons(nup, dicts=None):
    """icons.bin from an open NUP, or None."""
    return icons_file(nup_reader(nup, dicts), nup_layout_reader(nup))
