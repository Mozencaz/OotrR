"""Title screen badge (patching/title_badge.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest

from oot_rando.patching import title_badge as tb

NUP = os.environ.get('OOT_NUP')


def decode_block(block):
    """Texels of a block in the encoder's own mode (reference decoder of that ASTC subset)."""
    word = int.from_bytes(block, 'little')
    assert word & 0x7FF == tb.BLOCK_MODE and (word >> 11) & 3 == 0 and (word >> 13) & 15 == tb.CEM_RGBA_DIRECT
    v = [(word >> (17 + 8 * i)) & 0xFF for i in range(8)]
    e0, e1 = (v[0], v[2], v[4], v[6]), (v[1], v[3], v[5], v[7])
    assert sum(e1[:3]) >= sum(e0[:3])                  # no blue contraction
    stream = int(format(word >> 96, '032b')[::-1], 2)
    texels = []
    for index in range(16):
        w = tb.WEIGHT_LEVELS[(stream >> (2 * index)) & 3]
        texels.append(tuple((a * 257 * (64 - w) + b * 257 * w + 32) // 64 >> 8 for a, b in zip(e0, e1)))
    return texels


def fake_bntx(cols=416, rows=320, block_height=4, fill=bytes(16)):
    """A BNTX with one ASTC 1664x1280 logo, every block ``fill``."""
    gobs = (cols * 16 + 63) // 64
    size = ((rows + (8 << block_height) - 1) // (8 << block_height)) * (8 << block_height) * gobs * 64
    name = b'Logo_USEU_00'
    info, brti, name_at, mips_at, data_at = 0x40, 0x100, 0x200, 0x240, 0x400
    raw = bytearray(data_at + size)
    raw[:4] = b'BNTX'
    struct.pack_into('<Iq', raw, 0x24, 1, info)
    struct.pack_into('<q', raw, info, brti)
    raw[brti:brti + 4] = b'BRTI'
    struct.pack_into('<IIiiiii', raw, brti + 0x1C, tb.ASTC_4X4_SRGB, 0, cols * 4, rows * 4, 1, 1, block_height)
    struct.pack_into('<I', raw, brti + 0x50, size)
    struct.pack_into('<qqq', raw, brti + 0x60, name_at, 0, mips_at)
    struct.pack_into('<H', raw, name_at, len(name))
    raw[name_at + 2:name_at + 2 + len(name)] = name
    struct.pack_into('<q', raw, mips_at, data_at)
    raw[data_at:] = fill * (size // 16)
    return bytes(raw)


class EncoderTests(unittest.TestCase):
    def test_two_colour_block_round_trip(self):
        gold, clear = (240, 190, 60, 255), (40, 22, 4, 0)
        texels = [gold if (i // 4 + i % 4) % 2 else clear for i in range(16)]
        self.assertEqual(decode_block(tb.encode_block(texels)), texels)

    def test_flat_and_gradient_blocks(self):
        flat = [(200, 150, 50, 255)] * 16
        self.assertEqual(decode_block(tb.encode_block(flat)), flat)
        ramp = [(255 - 17 * i, 120 - 5 * i, 40, 255) for i in range(16)]   # darker end first: swapped
        decoded = decode_block(tb.encode_block(ramp))
        self.assertTrue(all(abs(a - b) <= 43 for t, u in zip(ramp, decoded) for a, b in zip(t, u)))   # 4 levels: step 255/3

    def test_badge_image(self):
        width, height, rgba = tb.badge_image()
        self.assertEqual((width % 4, height % 4), (0, 0))
        blocks = tb.encode_blocks(width, height, rgba)
        self.assertTrue(blocks)
        self.assertLessEqual(max(c for c, _ in blocks), width // 4 - 1)


class BadgeTests(unittest.TestCase):
    def test_block_linear_offsets_are_a_permutation(self):
        cols, rows = 20, 300
        offsets = {tb.block_offset(c, r, cols, 4) for c in range(cols) for r in range(rows)}
        self.assertEqual(len(offsets), cols * rows)
        self.assertTrue(all(o % 16 == 0 for o in offsets))

    def test_gob_bit_order(self):
        # Bits 4..8 of a GOB address: y0, y1, xb4, y2, xb5 (as ap_item, checked in game).
        self.assertEqual(tb.block_offset(0, 1, 4, 0), 16)
        self.assertEqual(tb.block_offset(0, 2, 4, 0), 32)
        self.assertEqual(tb.block_offset(1, 0, 4, 0), 64)
        self.assertEqual(tb.block_offset(0, 4, 4, 0), 128)
        self.assertEqual(tb.block_offset(2, 0, 4, 0), 256)

    def test_refuses_an_unknown_area(self):
        with self.assertRaises(ValueError):
            tb.add_title_badge(fake_bntx())

    def test_only_the_badge_area_changes(self):
        original = tb.AREA_SHA256
        raw = fake_bntx()
        width, height, _ = tb.badge_image()
        start = 0x400
        tb.AREA_SHA256 = tb.area_digest(raw, start, 416, 4, tb.badge_area(width, height))
        try:
            out, report = tb.add_title_badge(raw)
            with self.assertRaises(ValueError):   # never twice
                tb.add_title_badge(out)
        finally:
            tb.AREA_SHA256 = original
        self.assertEqual(len(out), len(raw))
        left, top, cols, rows = tb.badge_area(width, height)
        inside = {start + tb.block_offset(left + c, top + r, 416, 4) for c in range(cols) for r in range(rows)}
        changed = {i for i in range(0, len(raw), 16) if raw[i:i + 16] != out[i:i + 16]}
        self.assertTrue(changed)
        self.assertLessEqual(changed, inside)
        self.assertEqual(report['blocks'], len(changed))

    @unittest.skipUnless(NUP, 'OOT_NUP not set')
    def test_both_logos_of_the_game(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        members = effective_members(nup)
        for path in tb.BADGE_FILES:
            raw = decompress(nup.read(members[path]), dictionaries(nup))
            out, report = tb.add_title_badge(raw)
            self.assertEqual(report['texture'], 'Logo_USEU_00')
            self.assertEqual(len(out), len(raw))


if __name__ == '__main__':
    unittest.main()
