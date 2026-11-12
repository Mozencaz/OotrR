"""Small test-only little-endian BYML writer (no game assets)."""
import struct

def fixture(actors):
    """Small test-only LE BYML writer, preserving shared dictionary identities."""
    root = {'Actors': actors}
    keys, strings = set(), set()

    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, str):
            strings.add(value)
    collect(root)
    keys, strings = sorted(keys), sorted(strings)
    data = bytearray(b'YB\x07\x00' + bytes(12))

    def align():
        data.extend(bytes(-len(data) % 4))

    def table(values):
        align()
        position = len(data)
        encoded = [v.encode() + b'\0' for v in values]
        data.extend(b'\xc2' + len(values).to_bytes(3, 'little'))
        offset = 4 + 4 * (len(values) + 1)
        for value in encoded:
            data.extend(struct.pack('<I', offset))
            offset += len(value)
        data.extend(struct.pack('<I', offset))
        data.extend(b''.join(encoded))
        return position

    key_pos, string_pos = table(keys), table(strings)
    memo = {}

    def value(value):
        if isinstance(value, (dict, list)):
            return (0xc1 if isinstance(value, dict) else 0xc0), node(value)
        if isinstance(value, str):
            return 0xa0, strings.index(value)
        align()
        position = len(data)
        data.extend(struct.pack('<Q', value))
        return 0xd5, position

    def node(item):
        if id(item) in memo:
            return memo[id(item)]
        children = [value(item[key]) for key in sorted(item)] if isinstance(item, dict) else [value(v) for v in item]
        align()
        position = len(data)
        memo[id(item)] = position
        data.extend(bytes([0xc1 if isinstance(item, dict) else 0xc0]) + len(item).to_bytes(3, 'little'))
        if isinstance(item, dict):
            for key, (typ, offset) in zip(sorted(item), children):
                data.extend(keys.index(key).to_bytes(3, 'little') + bytes([typ]) + struct.pack('<I', offset))
        else:
            data.extend(bytes(typ for typ, _ in children))
            align()
            for _, offset in children:
                data.extend(struct.pack('<I', offset))
        return position

    root_pos = node(root)
    struct.pack_into('<III', data, 4, key_pos, string_pos, root_pos)
    return bytes(data)
