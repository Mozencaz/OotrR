"""A "Randomizer" badge under the title logo (main menu and title screen).

Players and viewers see at once that a seed is installed. The logo is the texture
``Logo_USEU_00`` (the European and American one), ASTC 4x4 sRGB, 1664x1280, Tegra
block-linear layout. The main menu (Continue / New game) draws it from the common UI
archive (``Common…bntx``, layout ``OpeningTitle_00``), the title screen from
``Title…bntx`` (layout ``Title_00``): both copies get the badge. Checked in game (16/11):
only the ``Title`` copy was patched and the menu showed no badge.

The badge (``title_badge.rgba.zlib``, drawn by ``tools/make_title_badge.py``: gold
capitals and two triforces) goes under "OCARINA OF TIME", centred on it, in an area of
the logo that is fully transparent (decoded once: alpha 0 from y = 1016 to 1130 right of
the shield). Its texels are encoded here as ASTC blocks (one partition, RGBA endpoints,
2-bit weights), at the same place in the file: the texture keeps its size and every other
byte. The area's original blocks are checked against their known digest first, so a
different game build stops the generation instead of drawing over the logo.
"""
import hashlib
import struct
import zlib
from oot_rando.paths import resource

TITLE_BNTX = 'UI/Layout2Archive/Title.Product.100.Nin_Ounce_NVN2.bntx.zs'
COMMON_BNTX = 'UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs'
BADGE_FILES = (TITLE_BNTX, COMMON_BNTX)
LOGO = 'Logo_USEU_00'
ASTC_4X4_SRGB = 0x2D06
BLOCK = 16                          # bytes per ASTC block (4x4 texels)
# Badge place in the logo, in texels (multiples of 4): centred under "OCARINA OF TIME"
# (x 690..1567, bottom y 1000).
CENTER_X, TOP_Y = 1128, 1024
# sha256 of the original blocks of the badge area (row by row): transparent there.
AREA_SHA256 = 'ad5593cd51cb089caf830424301c036d7e4755f95eb4183c7823dcc5b157b553'


def badge_image():
    """(width, height, RGBA bytes) of the badge."""
    raw = zlib.decompress(resource('patching', 'title_badge.rgba.zlib').read_bytes())
    width, height = struct.unpack_from('<HH', raw)
    if width % 4 or height % 4 or len(raw) != 4 + width * height * 4:
        raise ValueError('Unexpected title badge image.')
    return width, height, raw[4:]


# ------------------------------------------------------------------ ASTC encoder
# Block mode: 4x4 weight grid, one plane, weights in 4 levels (QUANT_4: R = 100b, H = 0).
# With bits 1..0 != 0: R0 = bit 4, R1 = bit 0, R2 = bit 1; bits 3..2 = 00 gives
# width B + 4 (bits 8..7) and height A + 2 (bits 6..5).
BLOCK_MODE = 0b00001000010          # A = 2, B = 0, R2 = 1
CEM_RGBA_DIRECT = 12
WEIGHT_LEVELS = (0, 21, 43, 64)     # QUANT_4 unquantized (0..64)


def _bits(value, at, count, word):
    return word | ((value & ((1 << count) - 1)) << at)


def encode_block(texels):
    """ASTC 4x4 block (16 bytes) of 16 RGBA texels (row-major), LDR, 8-bit endpoints."""
    # Endpoints: the two texels farthest apart (RGBA), refined to the extremes along that axis.
    best, pair = -1, (texels[0], texels[0])
    for i, a in enumerate(texels):
        for b in texels[i + 1:]:
            d = sum((x - y) ** 2 for x, y in zip(a, b))
            if d > best:
                best, pair = d, (a, b)
    e0, e1 = list(pair[0]), list(pair[1])
    # CEM 12 swaps (and blue-contracts) when e1's RGB sum is below e0's: keep e1 >= e0.
    if sum(e1[:3]) < sum(e0[:3]):
        e0, e1 = e1, e0
    axis = [b - a for a, b in zip(e0, e1)]
    length = sum(v * v for v in axis)
    weights = []
    for texel in texels:
        if length == 0:
            weights.append(0)
            continue
        t = sum((c - a) * v for c, a, v in zip(texel, e0, axis)) / length * 64
        weights.append(min(range(4), key=lambda q: abs(WEIGHT_LEVELS[q] - t)))
    word = BLOCK_MODE                                   # bits 0..10
    word = _bits(0, 11, 2, word)                        # one partition
    word = _bits(CEM_RGBA_DIRECT, 13, 4, word)
    values = [e0[0], e1[0], e0[1], e1[1], e0[2], e1[2], e0[3], e1[3]]
    for index, value in enumerate(values):              # QUANT_256: plain 8-bit values
        word = _bits(value, 17 + 8 * index, 8, word)
    stream = 0
    for index, weight in enumerate(weights):            # weights, read from bit 127 down
        stream |= weight << (2 * index)
    reversed_stream = int(format(stream, '032b')[::-1], 2)
    word |= reversed_stream << 96
    return word.to_bytes(16, 'little')


def encode_blocks(width, height, rgba):
    """{(column, row): block} of an RGBA image whose sides are multiples of 4."""
    blocks = {}
    for row in range(height // 4):
        for col in range(width // 4):
            texels = []
            for y in range(4):
                at = ((row * 4 + y) * width + col * 4) * 4
                texels.extend(tuple(rgba[at + 4 * x:at + 4 * x + 4]) for x in range(4))
            if any(t[3] for t in texels):
                blocks[(col, row)] = encode_block(texels)
    return blocks


# ------------------------------------------------------------------ BNTX layout
def textures(raw):
    """(name, format, width, height, block height log2, data offset, data size) of a BNTX."""
    if raw[:4] != b'BNTX':
        raise ValueError('Not a BNTX texture archive.')
    count = struct.unpack_from('<I', raw, 0x24)[0]
    info = struct.unpack_from('<q', raw, 0x28)[0]
    for index in range(count):
        brti = struct.unpack_from('<q', raw, info + 8 * index)[0]
        if raw[brti:brti + 4] != b'BRTI':
            raise ValueError('Unexpected BNTX texture header.')
        fmt, _, width, height, _, _, block_height = struct.unpack_from('<IIiiiii', raw, brti + 0x1C)
        size = struct.unpack_from('<I', raw, brti + 0x50)[0]
        name_at, _, mips_at = struct.unpack_from('<qqq', raw, brti + 0x60)
        length = struct.unpack_from('<H', raw, name_at)[0]
        name = raw[name_at + 2:name_at + 2 + length].decode('ascii')
        yield name, fmt, width, height, block_height, struct.unpack_from('<q', raw, mips_at)[0], size


def block_offset(col, row, width_blocks, block_height):
    """Byte offset of block (col, row) in a Tegra block-linear surface of 16-byte blocks.

    Same addressing as ``ap_item.block_address`` (checked in game): inside a GOB the
    address bits 4..8 are y0, y1, xb4, y2, xb5. An earlier order (y0, xb4, y1, y2, xb5)
    swapped neighbouring blocks: the badge showed as a checkerboard (16/11).
    """
    from oot_rando.patching.ap_item import block_address
    gobs_wide = (width_blocks * BLOCK + 63) // 64
    return block_address(col, row, 1 << block_height, gobs_wide)


def badge_area(width, height):
    """(left column, top row, columns, rows) of the badge in the logo, in blocks."""
    left = (CENTER_X - width // 2) // 4
    return left, TOP_Y // 4, width // 4, height // 4


def area_digest(raw, start, cols, block_height, area):
    left, top, width, height = area
    digest = hashlib.sha256()
    for row in range(top, top + height):
        for col in range(left, left + width):
            at = start + block_offset(col, row, cols, block_height)
            digest.update(raw[at:at + BLOCK])
    return digest.hexdigest()


def add_title_badge(raw):
    """Draw the badge under the European/American logo of a BNTX. Returns (bytes, report)."""
    width, height, rgba = badge_image()
    blocks = encode_blocks(width, height, rgba)
    data = bytearray(raw)
    for name, fmt, w, h, block_height, start, size in textures(raw):
        if name != LOGO:
            continue
        if fmt != ASTC_4X4_SRGB or (w, h) != (1664, 1280):
            raise ValueError(f'{name}: unexpected texture format {fmt:#x} {w}x{h}.')
        cols = (w + 3) // 4
        area = badge_area(width, height)
        if AREA_SHA256 and area_digest(raw, start, cols, block_height, area) != AREA_SHA256:
            raise ValueError(f'{name}: the area under the logo differs from the known game build.')
        left, top, _, _ = area
        for (col, row), block in blocks.items():
            at = start + block_offset(left + col, top + row, cols, block_height)
            if at + BLOCK > start + size:
                raise ValueError(f'{name}: badge outside the texture.')
            data[at:at + BLOCK] = block
        return bytes(data), {'texture': name, 'blocks': len(blocks), 'area': list(area)}
    raise ValueError('No title logo found.')
