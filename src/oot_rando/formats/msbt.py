"""Minimal MSBT (LMS message) reader/writer for the remake's ``Mals`` archives.

Only the layout used by the game's ``ActorMsg`` files is supported: UTF-8
text, little-endian, sections ``LBL1`` and ``TXT2`` only. :func:`load` then :func:`dump` reproduces the source bytes.

Get-item boxes look up ``<actor>_Name``, ``<actor>_Caption``,
``<actor>_GetMessage`` and ``<actor>_GetCaption`` in
``ActorMsg/PouchContent.msbt``. A new pouch actor without these labels opens an
empty message box that can never be closed, so every fabricated actor needs them.
"""
import struct

MAGIC = b'MsgStdBn'
PAD = b'\xab'


def label_hash(label, buckets):
    value = 0
    for char in label.encode('utf-8'):
        value = (value * 0x492 + char) & 0xffffffff
    return value % buckets


class Msbt:
    def __init__(self, header, sections, labels, texts, buckets):
        self.header = header          # raw 0x20-byte header
        self.sections = sections      # [(magic, raw body)] in file order
        self.labels = labels          # label -> text index
        self.texts = texts            # list of raw text bytes (NUL-terminated)
        self.buckets = buckets

    def get(self, label):
        index = self.labels.get(label)
        return None if index is None else self.texts[index]

    def add(self, label, text):
        """Add a new label with plain UTF-8 ``text`` (no control tags)."""
        if label in self.labels:
            raise ValueError('Label already present: ' + label)
        raw = text.encode('utf-8')
        if b'\0' in raw or b'\x0e' in raw or b'\x0f' in raw:
            raise ValueError('Invalid message text.')
        self.labels[label] = len(self.texts)
        self.texts.append(raw + b'\0')


def load(data):
    if data[:8] != MAGIC or data[8:10] != b'\xff\xfe' or data[0x0c] != 0:
        raise ValueError('Unsupported MSBT (UTF-8 little-endian expected).')
    count = struct.unpack_from('<H', data, 0x0e)[0]
    offset, sections = 0x20, []
    for _ in range(count):
        magic = data[offset:offset + 4]
        size = struct.unpack_from('<I', data, offset + 4)[0]
        sections.append((magic, data[offset + 0x10:offset + 0x10 + size]))
        offset = (offset + 0x10 + size + 15) & ~15
    if offset != len(data) or struct.unpack_from('<I', data, 0x12)[0] != len(data):
        raise ValueError('Unexpected MSBT size.')
    body = dict(sections)
    if set(body) != {b'LBL1', b'TXT2'}:
        raise ValueError('Sections MSBT inattendues.')
    lbl = body[b'LBL1']
    buckets = struct.unpack_from('<I', lbl, 0)[0]
    labels = {}
    for bucket in range(buckets):
        number, position = struct.unpack_from('<II', lbl, 4 + 8 * bucket)
        for _ in range(number):
            length = lbl[position]
            name = lbl[position + 1:position + 1 + length].decode('utf-8')
            labels[name] = struct.unpack_from('<I', lbl, position + 1 + length)[0]
            position += 5 + length
    txt = body[b'TXT2']
    number = struct.unpack_from('<I', txt, 0)[0]
    offsets = list(struct.unpack_from(f'<{number}I', txt, 4)) + [len(txt)]
    texts = [txt[offsets[i]:offsets[i + 1]] for i in range(number)]
    return Msbt(data[:0x20], sections, labels, texts, buckets)


def _txt2(texts):
    head = bytearray(struct.pack('<I', len(texts)))
    position = 4 + 4 * len(texts)
    for text in texts:
        head += struct.pack('<I', position)
        position += len(text)
    return bytes(head) + b''.join(texts)


def dump(message):
    out = bytearray(message.header)
    for magic, raw in message.sections:
        if magic == b'LBL1':
            raw = _lbl1(raw, message)
        elif magic == b'TXT2':
            raw = _txt2(message.texts)
        out += magic + struct.pack('<I', len(raw)) + bytes(8) + raw
        out += PAD * (-len(out) % 16)
    struct.pack_into('<I', out, 0x12, len(out))
    return bytes(out)


def _lbl1(raw, message):
    """Rebuild LBL1, keeping the source order of each bucket and appending new labels."""
    buckets = message.buckets
    known = []
    for bucket in range(buckets):
        number, position = struct.unpack_from('<II', raw, 4 + 8 * bucket)
        entries = []
        for _ in range(number):
            length = raw[position]
            entries.append(raw[position + 1:position + 1 + length].decode('utf-8'))
            position += 5 + length
        known.append(entries)
    seen = {name for entries in known for name in entries}
    for name in message.labels:
        if name not in seen:
            known[label_hash(name, buckets)].append(name)
    head = bytearray(struct.pack('<I', buckets))
    body = bytearray()
    start = 4 + 8 * buckets
    for entries in known:
        head += struct.pack('<II', len(entries), start + len(body))
        for name in entries:
            encoded = name.encode('utf-8')
            body += bytes([len(encoded)]) + encoded + struct.pack('<I', message.labels[name])
    return bytes(head + body)
