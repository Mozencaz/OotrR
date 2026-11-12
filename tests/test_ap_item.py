"""Archipelago medallion: logo, ASTC blocks, BNTX rewrite; with OOT_NUP, the model files."""
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

    def test_logo_colours(self):
        self.assertEqual(ap_item.logo_colour(256, 410), (217, 160, 125))   # bottom circle, drawn last
        self.assertEqual(ap_item.logo_colour(255.5, 30), (201, 118, 130))   # top of the first circle
        self.assertIsNone(ap_item.logo_colour(256, 256))                    # empty centre
        self.assertIsNone(ap_item.logo_colour(5, 5))
        self.assertEqual(ap_item.face_colour(0, ap_item.FACE_RADIUS - 1), ap_item.GOLD)
        self.assertIsNone(ap_item.face_colour(ap_item.FACE_RADIUS + 1, 0))
        self.assertEqual(ap_item.face_colour(0, 0), ap_item.CREAM)

    def test_void_extent_block(self):
        block = ap_item.void_extent((255, 0, 128, 255))
        self.assertEqual(len(block), 16)
        self.assertEqual(block[:8], bytes.fromhex('fcfdffffffffffff'))
        self.assertEqual(struct.unpack('<4H', block[8:]), (65535, 0, 128 * 257, 65535))

    def test_paint_rewrites_only_chosen_blocks(self):
        data = tiny_bntx()
        info = ap_item.bntx_info(data)
        self.assertEqual((info['width'], info['height'], info['levels']), (16, 8, [0x200]))
        painted, count = ap_item.paint_bntx(data, lambda x, y, w, h: (1, 2, 3, 4) if x < 8 else None)
        self.assertEqual(count, 4)                   # 2 of 4 block columns, 2 block rows
        self.assertEqual(len(painted), len(data))
        block = ap_item.void_extent((1, 2, 3, 4))
        for x, y, expected in ((0, 0, True), (1, 1, True), (2, 0, False), (3, 1, False)):
            address = 0x200 + ap_item._block_address(x, y, 1, 1)
            self.assertEqual(painted[address:address + 16] == block, expected, (x, y))
        with self.assertRaises(ValueError):
            ap_item.paint_bntx(tiny_bntx(fmt=0x1d), lambda *b: (0, 0, 0, 0))   # BC4: not ASTC

    def test_rename_keeps_length(self):
        self.assertEqual(ap_item.rename(b'xx_Fire_Alb\0', 'Fire', 'Arch'), b'xx_Arch_Alb\0')
        with self.assertRaises(ValueError):
            ap_item.rename(b'Fire', 'Fire', 'Archipelago')
        with self.assertRaises(ValueError):
            ap_item.rename(b'Water', 'Fire', 'Arch')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    def test_model_files(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            members, d = effective_members(nup), dictionaries(nup)
            self.assertFalse([p for p in members if ap_item.PROJECT in p or ap_item.NEW_TEX in p])

            def read_raw(path):
                return decompress(nup.read(members[path]), d)
            files = ap_item.build_model_files(read_raw)
            self.assertEqual(set(files), {ap_item.NEW_MODEL_FILE} | {
                f'Tex/{ap_item.NEW_TEX}_{s}.bntx.zs' for s in ap_item.REPLACED})
            model, template = files[ap_item.NEW_MODEL_FILE]
            self.assertEqual(len(model), len(read_raw(template)))
            for suffix in ap_item.REPLACED:
                self.assertEqual(model.count(f'{ap_item.NEW_TEX}_{suffix}'.encode()), 1)
                self.assertNotIn(f'{ap_item.OLD_TEX}_{suffix}'.encode(), model)
            self.assertIn(b'Mt_Item_Medal_Fire_Mtl', model)   # metal/roughness/AO stay shared
            for path, (raw, template) in files.items():
                if path.startswith('Tex/'):
                    original = read_raw(template)
                    self.assertEqual(len(raw), len(original))
                    self.assertNotEqual(raw, original)
        finally:
            nup.stream.close()


if __name__ == '__main__':
    unittest.main()
