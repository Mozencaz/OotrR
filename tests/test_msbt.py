"""MSBT writer and soul get-item texts."""
import _src_path  # noqa: F401  (src on sys.path)
import struct
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats import msbt
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.soul_adapter import MESSAGE_FILE, TEMPLATE, patch_soul_messages, soul_actor, soul_messages, soul_name

NUL = bytes(1)


def sample():
    labels = {TEMPLATE + '_GetMessage': 0, 'Other_Name': 1}
    buckets = 7
    slots = [[] for _ in range(buckets)]
    for name, index in labels.items():
        slots[msbt.label_hash(name, buckets)].append((name, index))
    head, body = bytearray(struct.pack('<I', buckets)), bytearray()
    for slot in slots:
        head += struct.pack('<II', len(slot), 4 + 8 * buckets + len(body))
        for name, index in slot:
            body += bytes([len(name)]) + name.encode() + struct.pack('<I', index)
    texts = ['Vous avez reçu !'.encode() + NUL, b'Nom' + NUL]
    txt = struct.pack('<I', 2) + struct.pack('<II', 12, 12 + len(texts[0])) + b''.join(texts)
    out = bytearray(b'MsgStdBn' + bytes([0xff, 0xfe, 0, 0, 0, 3, 2, 0, 0, 0]) + bytes(14))
    for magic, raw in ((b'LBL1', bytes(head + body)), (b'TXT2', txt)):
        out += magic + struct.pack('<I', len(raw)) + bytes(8) + raw
        out += bytes([0xab]) * (-len(out) % 16)
    struct.pack_into('<I', out, 0x12, len(out))
    return bytes(out)


class MsbtTests(unittest.TestCase):
    def test_round_trip_and_add(self):
        data = sample()
        message = msbt.load(data)
        self.assertEqual(msbt.dump(message), data)
        message.add('Item_Soul_Keese_GetMessage', "Vous avez obtenu l'âme : Keese !")
        again = msbt.load(msbt.dump(message))
        self.assertEqual(again.get('Item_Soul_Keese_GetMessage'), "Vous avez obtenu l'âme : Keese !".encode() + NUL)
        self.assertEqual(again.get('Other_Name'), b'Nom' + NUL)
        with self.assertRaises(ValueError):
            again.add('Other_Name', 'x')

    def test_soul_texts(self):
        texts = soul_messages('Soul (Gohma)', 'EUfr')
        self.assertEqual(texts['GetMessage'], "Vous avez obtenu l'âme : Reine Gohma !")
        self.assertEqual(soul_messages('Soul (Gohma)', 'USen')['GetMessage'], 'You got the soul: Queen Gohma!')
        self.assertEqual(soul_name('Soul (Region:KokiriForest)'), 'Forêt Kokiri')
        self.assertEqual(soul_name('Soul (Region:KokiriForest)', False), 'Kokiri Forest')
        self.assertEqual(set(texts), {'Name', 'Caption', 'GetMessage', 'GetCaption'})

    def test_patch_archive(self):
        archive = byml_codec.build_sarc({MESSAGE_FILE: sample(), 'ActorMsg/Other.msbt': b'x'})
        patched = sarc(patch_soul_messages(archive, 'EUfr', ['Soul (Keese)', 'Soul (Region:LostWood)']))
        message = msbt.load(patched[MESSAGE_FILE])
        for item in ('Soul (Keese)', 'Soul (Region:LostWood)'):
            for suffix in ('Name', 'Caption', 'GetMessage', 'GetCaption'):
                self.assertIsNotNone(message.get(soul_actor(item) + '_' + suffix))
        self.assertEqual(patched['ActorMsg/Other.msbt'], b'x')


if __name__ == '__main__':
    unittest.main()
