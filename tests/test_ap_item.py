"""Archipelago medallion: logo, BC1/BC4/ASTC blocks, BNTX rewrite; with OOT_NUP, the model files."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest

from oot_rando.patching import ap_item

NUP = os.environ.get('OOT_NUP')


def tiny_bntx(width=16, height=8, fmt=0x2d, size=512):
    """Single-texture BNTX header with one mip level (ASTC 4x4 by default)."""
    data = bytearray(0x200 + size)
    data[:4] = b'BNTX'
    at = 0x40
    data[at:at + 4] = b'BRTI'
    struct.pack_into('<H', data, at + 0x12, 0)              # block-linear
    struct.pack_into('<H', data, at + 0x16, 1)              # one mip level
    struct.pack_into('<I', data, at + 0x1C, (fmt << 8) | 1)
    struct.pack_into('<II', data, at + 0x24, width, height)
    struct.pack_into('<I', data, at + 0x34, 0)              # GOB height 1
    struct.pack_into('<I', data, at + 0x50, size)
    struct.pack_into('<Q', data, at + 0x70, 0x180)          # mip table
    struct.pack_into('<Q', data, 0x180, 0x200)              # level 0 data
    return bytes(data)


def decode_bc1(block):
    """Reference BC1 decoder (four-colour mode) → 16 RGB texels."""
    c0, c1, indices = struct.unpack('<HHI', block)
    e0, e1 = ap_item._expand565(c0), ap_item._expand565(c1)
    palette = (e0, e1, tuple((2 * e0[k] + e1[k]) // 3 for k in range(3)),
               tuple((e0[k] + 2 * e1[k]) // 3 for k in range(3)))
    return [palette[(indices >> (2 * i)) & 3] for i in range(16)]


class Units(unittest.TestCase):
    def test_item_and_actor_names(self):
        item = ap_item.ap_item('Sword (Ami)')
        self.assertTrue(ap_item.is_ap_item(item))
        actor = ap_item.ap_actor(item)
        self.assertTrue(ap_item.is_ap_actor(actor))
        self.assertEqual(actor, ap_item.ap_actor('Archipelago: Sword (Ami)'))
        self.assertNotEqual(actor, ap_item.ap_actor(ap_item.ap_item('Sword (Bob)')))

    def test_planner_knows_the_medallion(self):
        from oot_rando.game.item_forms import can_take
        from oot_rando.game.remake_world import item_actor
        actor = item_actor(ap_item.ap_item('Sword (Ami)'), 'KokiriForest')
        self.assertTrue(ap_item.is_ap_actor(actor))
        self.assertTrue(can_take(actor, 'chest') and can_take(actor, 'world'))
        self.assertFalse(can_take(actor, 'shop'))

    def test_texts_name_item_and_player(self):
        french = ap_item.ap_messages('Sword', 'Ami', 'EUfr')
        self.assertIn('« Sword » pour Ami', french['GetMessage'])
        english = ap_item.ap_messages('Sword', 'Ami', 'USen')
        self.assertEqual(english['Name'], 'Sword (Ami)')
        self.assertEqual(set(french), {'Name', 'Caption', 'GetMessage', 'GetCaption'})

    def test_logo_and_sheet(self):
        self.assertEqual(ap_item.logo_colour(256, 410), (217, 160, 125))   # bottom circle, drawn last
        self.assertEqual(ap_item.logo_colour(255.5, 30), (201, 118, 130))   # top of the first circle
        self.assertIsNone(ap_item.logo_colour(256, 256))                    # empty centre
        self.assertEqual(ap_item.face_colour(0, ap_item.FACE_RADIUS - 1), ap_item.GOLD)
        self.assertIsNone(ap_item.face_colour(ap_item.FACE_RADIUS + 1, 0))
        self.assertEqual(ap_item.face_colour(0, 0), ap_item.CREAM)
        self.assertEqual(ap_item.sheet_colour(560, 20), ap_item.GOLD)       # edge of the disc
        self.assertTrue(ap_item.on_logo(*ap_item.FACES[0]))
        self.assertFalse(ap_item.on_logo(560, 20))

    def test_bc1_two_colour_block_is_exact(self):
        red, cream = (255, 0, 0), (255, 255, 255)
        texels = [red if (i % 4) < 2 else cream for i in range(16)]
        decoded = decode_bc1(ap_item.bc1_block(texels))
        for texel, expected in zip(decoded, texels):
            self.assertTrue(all(abs(texel[k] - expected[k]) <= 8 for k in range(3)), (texel, expected))
        c0, c1, _ = struct.unpack('<HHI', ap_item.bc1_block(texels))
        self.assertGreater(c0, c1)                                          # four-colour mode
        flat = ap_item.bc1_block([cream] * 16)
        self.assertEqual(decode_bc1(flat), [ap_item._expand565(ap_item._rgb565(cream))] * 16)

    def test_constant_blocks(self):
        block = ap_item.void_extent((255, 0, 128, 255))
        self.assertEqual(block[:8], bytes.fromhex('fcfdffffffffffff'))
        self.assertEqual(struct.unpack('<4H', block[8:]), (65535, 0, 128 * 257, 65535))
        self.assertEqual(ap_item.bc4_constant(96), bytes((96, 96)) + bytes(6))

    def test_paint_rewrites_only_chosen_blocks(self):
        data = tiny_bntx()
        info = ap_item.bntx_info(data)
        self.assertEqual((info['width'], info['height'], info['levels']), (16, 8, [0x200]))
        block = ap_item.void_extent((1, 2, 3, 4))
        painted, count = ap_item.paint_bntx(data, lambda x, y, w, h, s: block if x < 8 else None)
        self.assertEqual(count, 4)                   # 2 of 4 block columns, 2 block rows
        self.assertEqual(len(painted), len(data))
        for x, y, expected in ((0, 0, True), (1, 1, True), (2, 0, False), (3, 1, False)):
            address = 0x200 + ap_item._block_address(x, y, 1, 1)
            self.assertEqual(painted[address:address + 16] == block, expected, (x, y))
        with self.assertRaises(ValueError):          # BC4 blocks are 8 bytes
            ap_item.paint_bntx(tiny_bntx(fmt=0x1d), lambda *b: block)

    def test_fill_sets_every_block(self):
        data = tiny_bntx(fmt=0x1d, size=64)
        filled = ap_item.fill_bntx(data, ap_item.bc4_constant(7))
        self.assertEqual(filled[0x200:0x240], ap_item.bc4_constant(7) * 8)
        self.assertEqual(filled[:0x200], data[:0x200])

    def test_rename_keeps_length(self):
        self.assertEqual(ap_item.rename(b'xx_Fire_Alb\0', 'Fire', 'Arch'), b'xx_Arch_Alb\0')
        with self.assertRaises(ValueError):
            ap_item.rename(b'Fire', 'Fire', 'Archipelago')
        with self.assertRaises(ValueError):
            ap_item.rename(b'Water', 'Fire', 'Arch')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            members, d = effective_members(nup), dictionaries(nup)
            cls.members = set(members)
            needed = [ap_item.MODEL_FILE, f'Pack/Actor/{ap_item.SPIN_TEMPLATE}.pack.zs'] + [
                ap_item.SOURCES.get(s, f'Tex/{ap_item.OLD_TEX}_{s}.bntx.zs') for s in ap_item.REPLACED]
            cls.raw = {path: decompress(nup.read(members[path]), d) for path in needed}
        finally:
            nup.stream.close()

    def test_new_names_are_free(self):
        self.assertFalse([p for p in self.members if ap_item.PROJECT in p or ap_item.NEW_TEX in p])

    def test_model_files(self):
        files = ap_item.build_model_files(self.raw.__getitem__)
        self.assertEqual(set(files), {ap_item.NEW_MODEL_FILE} | {
            f'Tex/{ap_item.NEW_TEX}_{s}.bntx.zs' for s in ap_item.REPLACED})
        model, template = files[ap_item.NEW_MODEL_FILE]
        self.assertEqual(len(model), len(self.raw[template]))
        for suffix in ap_item.REPLACED:
            self.assertEqual(model.count(f'{ap_item.NEW_TEX}_{suffix}'.encode()), 1)
            self.assertNotIn(f'{ap_item.OLD_TEX}_{suffix}'.encode(), model)
        for path, (raw, source) in files.items():
            if path.startswith('Tex/'):
                self.assertEqual(len(raw), len(self.raw[source]))
                self.assertNotEqual(raw, self.raw[source])
                self.assertIn(path[4:-8].encode(), raw)
        albedo = ap_item.bntx_info(files[f'Tex/{ap_item.NEW_TEX}_Alb.bntx.zs'][0])
        self.assertEqual((albedo['format'], albedo['width']), (ap_item.BC1, ap_item.SHEET))

    def test_hidden_shapes_only(self):
        original = self.raw[ap_item.MODEL_FILE]
        hidden = ap_item.hide_shapes(original)
        changed = [i for i, (a, b) in enumerate(zip(original, hidden)) if a != b]
        self.assertTrue(changed)
        rlt = struct.unpack_from('<I', original, 0x18)[0]
        buffers = struct.unpack_from('<QI', original, rlt + 16 + 24)[1]
        self.assertTrue(all(i >= buffers for i in changed))   # only vertex data moves
        with self.assertRaises(ValueError):
            ap_item.hide_shapes(original, ('Missing__Shape',))

    def test_spin_parts(self):
        files, components, info = ap_item.spin_parts(self.raw.__getitem__)
        self.assertEqual(components['ASRef'], ap_item.SPIN_AS)
        self.assertTrue(all(ref[1:] in files for key, ref in components.items() if key != 'ASRef'))
        self.assertEqual(info['AnimationResources'], [{'ModelProjectName': ap_item.SPIN_ANIMATION}])
        self.assertIn('Model/Item_Common_Animation.anim.bfres.zs', self.members)
        self.assertIn('AS/Item_Common.root.asb.zs', self.members)


if __name__ == '__main__':
    unittest.main()
