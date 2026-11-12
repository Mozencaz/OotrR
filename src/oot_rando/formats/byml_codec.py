"""Typed BYML (v2–v7) and SARC encoders for new or restructured resources.

``load`` keeps every scalar's native type through thin wrappers (``U32``,
``I64``, ``U64``, ``F64``); ``dump`` writes them back with the same type codes.
Plain ``int`` is a signed 32-bit integer, plain ``float`` a 32-bit float.
"""
import struct


class U32(int):
    pass


class I64(int):
    pass


class U64(int):
    pass


class F64(float):
    pass


def load(data):
    if data[:2] not in (b'YB', b'BY'):
        raise ValueError('BYML attendu.')
    e = '<' if data[:2] == b'YB' else '>'
    order = 'little' if e == '<' else 'big'
    version = struct.unpack_from(e + 'H', data, 2)[0]

    def u32(o):
        return struct.unpack_from(e + 'I', data, o)[0]

    def u24(o):
        return int.from_bytes(data[o:o + 3], order)

    def table(off):
        if not off:
            return []
        return [data[off + u32(off + 4 + i * 4):].split(b'\0', 1)[0].decode() for i in range(u24(off + 1))]

    keys, strings = table(u32(4)), table(u32(8))

    def value(t, o):
        v = u32(o)
        if t in (0xc0, 0xc1):
            return node(v)
        if t == 0xa0:
            return strings[v]
        if t == 0xd0:
            return bool(v)
        if t == 0xd1:
            return struct.unpack_from(e + 'i', data, o)[0]
        if t == 0xd2:
            return struct.unpack_from(e + 'f', data, o)[0]
        if t == 0xd3:
            return U32(v)
        if t == 0xd4:
            return I64(struct.unpack_from(e + 'q', data, v)[0])
        if t == 0xd5:
            return U64(struct.unpack_from(e + 'Q', data, v)[0])
        if t == 0xd6:
            return F64(struct.unpack_from(e + 'd', data, v)[0])
        if t == 0xff:
            return None
        raise ValueError(f'Unsupported BYML type {t:#x}')

    def node(o):
        t, n = data[o], u24(o + 1)
        if t == 0xc1:
            return {keys[u24(o + 4 + i * 8)]: value(data[o + 7 + i * 8], o + 8 + i * 8) for i in range(n)}
        if t == 0xc0:
            base = (o + 4 + n + 3) & ~3
            return [value(data[o + 4 + i], base + i * 4) for i in range(n)]
        raise ValueError(f'Unsupported BYML node {t:#x}')

    return {'endian': e, 'version': version, 'root': node(u32(12))}


def _type(v):
    if isinstance(v, bool):
        return 0xd0
    if isinstance(v, dict):
        return 0xc1
    if isinstance(v, list):
        return 0xc0
    if isinstance(v, str):
        return 0xa0
    if isinstance(v, I64):
        return 0xd4
    if isinstance(v, U64):
        return 0xd5
    if isinstance(v, U32):
        return 0xd3
    if isinstance(v, int):
        return 0xd1
    if isinstance(v, F64):
        return 0xd6
    if isinstance(v, float):
        return 0xd2
    if v is None:
        return 0xff
    raise ValueError('BYML value cannot be encoded: ' + type(v).__name__)


def dump(document):
    e = document['endian']
    order = 'little' if e == '<' else 'big'
    root = document['root']
    keys, strings = set(), set()

    def collect(v):
        if isinstance(v, dict):
            for k, x in v.items():
                keys.add(k)
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)
        elif isinstance(v, str):
            strings.add(v)
    collect(root)
    keys = sorted(keys, key=lambda s: s.encode())
    strings = sorted(strings, key=lambda s: s.encode())
    key_id = {k: i for i, k in enumerate(keys)}
    string_id = {s: i for i, s in enumerate(strings)}
    out = bytearray(16)
    out[:2] = b'YB' if e == '<' else b'BY'
    struct.pack_into(e + 'H', out, 2, document['version'])

    def align(n=4):
        out.extend(bytes(-len(out) % n))

    def write_table(values):
        if not values:
            return 0
        align()
        start = len(out)
        encoded = [v.encode() + b'\0' for v in values]
        out.extend(b'\xc2' + len(values).to_bytes(3, order))
        offset = 4 + 4 * (len(values) + 1)
        for v in encoded:
            out.extend(struct.pack(e + 'I', offset))
            offset += len(v)
        out.extend(struct.pack(e + 'I', offset))
        out.extend(b''.join(encoded))
        return start

    struct.pack_into(e + 'I', out, 4, write_table(keys))
    struct.pack_into(e + 'I', out, 8, write_table(strings))
    memo = {}

    def payload(v):
        t = _type(v)
        if t in (0xc0, 0xc1):
            return struct.pack(e + 'I', write_node(v))
        if t == 0xa0:
            return struct.pack(e + 'I', string_id[v])
        if t == 0xd0:
            return struct.pack(e + 'I', int(v))
        if t == 0xd1:
            return struct.pack(e + 'i', v)
        if t == 0xd2:
            return struct.pack(e + 'f', v)
        if t == 0xd3:
            return struct.pack(e + 'I', v)
        if t == 0xff:
            return bytes(4)
        align(8)
        position = len(out)
        out.extend(struct.pack(e + {0xd4: 'q', 0xd5: 'Q', 0xd6: 'd'}[t], v))
        return struct.pack(e + 'I', position)

    signatures, interned = {}, {}

    def signature(v):
        # Structural identity interned to small integers (cheap to hash).
        if isinstance(v, (dict, list)):
            cached = signatures.get(id(v))
            if cached is None:
                if isinstance(v, dict):
                    shape = ('d',) + tuple((k, signature(x)) for k, x in v.items())
                else:
                    shape = ('l',) + tuple(signature(x) for x in v)
                cached = interned.setdefault(shape, len(interned))
                signatures[id(v)] = cached
            return cached
        return interned.setdefault((_type(v), v), len(interned))

    def write_node(v):
        sig = signature(v)
        if sig in memo:
            return memo[sig]
        if isinstance(v, dict):
            items = sorted(v.items(), key=lambda kv: key_id[kv[0]])
            entries = [(key_id[k], _type(x), payload(x)) for k, x in items]
            align()
            start = len(out)
            out.extend(b'\xc1' + len(entries).to_bytes(3, order))
            for k, t, p in entries:
                out.extend(k.to_bytes(3, order) + bytes([t]) + p)
        else:
            entries = [(_type(x), payload(x)) for x in v]
            align()
            start = len(out)
            out.extend(b'\xc0' + len(entries).to_bytes(3, order))
            out.extend(bytes(t for t, _ in entries))
            align()
            for _, p in entries:
                out.extend(p)
        memo[sig] = start
        return start

    struct.pack_into(e + 'I', out, 12, write_node(root))
    return bytes(out)


def sarc_hash(name, key=0x65):
    h = 0
    for byte in name.encode():
        h = (h * key + (byte if byte < 128 else byte - 256)) & 0xffffffff
    return h


def build_sarc(files, alignment=8):
    """Little-endian SARC with sorted name hashes (as produced by the game tools)."""
    entries = sorted(files.items(), key=lambda kv: sarc_hash(kv[0]))
    names = bytearray()
    offsets = []
    for name, _ in entries:
        offsets.append(len(names) // 4)
        names.extend(name.encode() + b'\0')
        names.extend(bytes(-len(names) % 4))
    data = bytearray()
    ranges = []
    for _, content in entries:
        data.extend(bytes(-len(data) % alignment))
        ranges.append((len(data), len(data) + len(content)))
        data.extend(content)
    header_size = 0x14 + 0x0c + 16 * len(entries) + 8 + len(names)
    data_offset = (header_size + alignment - 1) & ~(alignment - 1)
    out = bytearray(b'SARC' + struct.pack('<HHIIHH', 0x14, 0xFEFF, 0, data_offset, 0x100, 0))
    out.extend(b'SFAT' + struct.pack('<HHI', 0x0c, len(entries), 0x65))
    for (name, _), name_offset, (start, end) in zip(entries, offsets, ranges):
        out.extend(struct.pack('<IIII', sarc_hash(name), 0x01000000 | name_offset, start, end))
    out.extend(b'SFNT' + struct.pack('<HH', 8, 0))
    out.extend(names)
    out.extend(bytes(data_offset - len(out)))
    out.extend(data)
    struct.pack_into('<I', out, 8, len(out))
    return bytes(out)
