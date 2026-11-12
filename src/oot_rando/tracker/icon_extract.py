"""Extract item icons from the player's own RomFS (UI/Tex/Icon/*.bntx.zs) to PNG.

Nothing from the game is shipped with the randomizer: icons are decoded locally, on
demand, into build/app/icons. The textures are ASTC 4x4 in Tegra block-linear layout.
ASTC decoding needs `texture2ddecoder` (HookshotBuilder's bundled Python has it), so this
file is self-contained and may run under another interpreter:

    python icon_extract.py <romfs> <out_dir> <size> Name1 Name2 ...

Prints one line per icon: "ok <name>" or "fail <name>: <reason>".
"""
import struct
import sys
from pathlib import Path

ASTC_FORMATS = {0x2d: (4, 4), 0x2e: (5, 4), 0x2f: (5, 5), 0x30: (6, 5), 0x31: (6, 6),
                0x32: (8, 5), 0x33: (8, 6), 0x34: (8, 8)}


def parse_bntx(data):
    """(width, height, format_type, block_height_log2, image bytes) of the first texture."""
    if data[:4] != b'BNTX':
        raise ValueError('not a BNTX')
    at = data.find(b'BRTI')
    if at < 0:
        raise ValueError('BRTI absent')
    tile_mode = struct.unpack_from('<H', data, at + 0x12)[0]
    fmt = struct.unpack_from('<I', data, at + 0x1C)[0]
    width, height = struct.unpack_from('<II', data, at + 0x24)
    layout = struct.unpack_from('<I', data, at + 0x34)[0]
    size = struct.unpack_from('<I', data, at + 0x50)[0]
    mips = struct.unpack_from('<Q', data, at + 0x70)[0]
    start = struct.unpack_from('<Q', data, mips)[0]
    if tile_mode != 0:
        raise ValueError('linear layout not supported')
    return width, height, fmt >> 8, layout & 7, data[start:start + size]


def deblock_linear(raw, width_blocks, height_blocks, block_height_log2):
    """Tegra block-linear -> linear rows of 16-byte elements (ASTC blocks).

    A GOB is 64 bytes x 8 rows = 4 x 8 elements. Inside it, the element's address bits 4..8 are
    y0, y1, x0, y2, x1: found by decoding the game's own icons (every other order leaves 4-pixel
    holes); gob_height GOBs stack vertically, then GOB columns follow.
    """
    bpe = 16
    gob_height = 1 << block_height_log2
    width_gobs = -(-width_blocks * bpe // 64)
    out = bytearray(width_blocks * height_blocks * bpe)
    row_stride = width_blocks * bpe
    for y in range(height_blocks):
        gob_row = (y // (8 * gob_height)) * 512 * gob_height * width_gobs + ((y % (8 * gob_height)) // 8) * 512
        y_in = (y & 1) * 16 + ((y >> 1) & 1) * 32 + ((y >> 2) & 1) * 128
        for x in range(width_blocks):
            address = gob_row + (x // 4) * 512 * gob_height + y_in + (x & 1) * 64 + ((x >> 1) & 1) * 256
            out[y * row_stride + x * bpe:y * row_stride + (x + 1) * bpe] = raw[address:address + bpe]
    return bytes(out)


def decode_icon(path):
    import zstandard
    import texture2ddecoder
    from PIL import Image
    data = zstandard.ZstdDecompressor().decompress(Path(path).read_bytes(), max_output_size=1 << 28)
    width, height, fmt, bh_log2, raw = parse_bntx(data)
    if fmt not in ASTC_FORMATS:
        raise ValueError(f'format {fmt:#x} not supported')
    bw, bh = ASTC_FORMATS[fmt]
    wb, hb = -(-width // bw), -(-height // bh)
    linear = deblock_linear(raw, wb, hb, bh_log2)
    pixels = texture2ddecoder.decode_astc(linear, width, height, bw, bh)
    return Image.frombytes('RGBA', (width, height), pixels, 'raw', 'BGRA')


def main(argv):
    romfs, out, size, names = Path(argv[1]), Path(argv[2]), int(argv[3]), argv[4:]
    out.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for name in names:
        try:
            image = decode_icon(romfs / 'UI' / 'Tex' / 'Icon' / f'{name}.bntx.zs')
            image.thumbnail((size, size), Image.LANCZOS)
            image.save(out / f'{name}.png')
            print('ok', name, flush=True)
        except Exception as error:   # one bad icon must not stop the others
            print('fail', name + ':', error, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
