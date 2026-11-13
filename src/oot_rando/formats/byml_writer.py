"""Append-only BYML string edits, retaining every untouched scalar's native type.

This is deliberately not a Python-object serializer: signed/unsigned integers,
float widths and external scalar payloads retain their original representation.
Only changed container branches are cloned, except when a new dictionary key
requires remapping the sorted key table throughout the reachable graph.
"""
import copy
import struct

from oot_rando.formats.inspect_resources import Byml


def patch_strings(raw, changes):
    """Apply ``{path: tuple, before: str|None, after: str|bool}`` records.

    A boolean ``after`` is allowed for a new leaf (``before=None``) or to replace
    an existing boolean leaf of a dictionary (``before`` is that boolean).

    ``before=None`` means the leaf must be absent, not a BYML null. Missing
    dictionary ancestors may then be created. Array sizes never change.
    Both BYML byte orders are supported. Original raw bytes remain a prefix.
    """
    byml = Byml(raw)
    endian, order = byml.endian, byml.byteorder
    records, paths, new_keys, new_strings = [], set(), set(), set()
    expected = copy.deepcopy(byml.root)
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'path', 'before', 'after'}:
            raise ValueError('A string edit requires path, before and after.')
        path, before, after = tuple(change['path']), change['before'], change['after']
        if (not path or any(type(key) not in (str, int) for key in path)
                or not isinstance(after, (str, bool)) or (isinstance(after, str) and '\0' in after)
                or (isinstance(after, bool) and before is not None and not isinstance(before, bool))
                or (isinstance(before, bool) and not isinstance(after, bool))
                or (before is not None and not isinstance(before, (str, bool)))):
            raise ValueError('Invalid string edit.')
        if path in paths or any(path[:len(other)] == other or other[:len(path)] == path for other in paths):
            raise ValueError('Duplicate or overlapping string edits.')
        paths.add(path)
        cursor = expected
        for depth, key in enumerate(path):
            last = depth == len(path) - 1
            if isinstance(cursor, dict) and isinstance(key, str):
                if key not in byml.keys:
                    new_keys.add(key)
                if last:
                    if (before is None and key in cursor) or (before is not None and cursor.get(key) != before):
                        raise ValueError('String edit precondition failed.')
                    if before is not None and type(cursor[key]) is not type(before):
                        raise ValueError('Existing value is not of the expected type.')
                    cursor[key] = after
                else:
                    if key not in cursor:
                        if before is not None:
                            raise ValueError('Missing string edit ancestor.')
                        cursor[key] = {}
                    cursor = cursor[key]
            elif isinstance(cursor, list) and type(key) is int and 0 <= key < len(cursor):
                if last:
                    if before is None or cursor[key] != before or not isinstance(cursor[key], str):
                        raise ValueError('String edit precondition failed.')
                    cursor[key] = after
                else:
                    cursor = cursor[key]
            else:
                raise ValueError('Invalid string edit path.')
        if isinstance(after, str):
            new_strings.add(after)
        records.append({'path': path, 'before': before, 'after': after})
    if not records:
        return raw
    keys = sorted(set(byml.keys) | new_keys) if new_keys else list(byml.keys)
    strings = list(byml.strings) + sorted(new_strings - set(byml.strings))
    key_ids, string_ids = {v: i for i, v in enumerate(keys)}, {v: i for i, v in enumerate(strings)}
    data = bytearray(raw)

    def align():
        data.extend(bytes(-len(data) % 4))

    def table(values):
        if len(values) >= 1 << 24:
            raise ValueError('BYML table exceeds 24-bit size.')
        align()
        start = len(data)
        encoded = [v.encode('utf-8') + b'\0' for v in values]
        data.extend(b'\xc2' + len(values).to_bytes(3, order))
        offset = 4 + 4 * (len(values) + 1)
        for value in encoded:
            data.extend(struct.pack(endian + 'I', offset))
            offset += len(value)
        data.extend(struct.pack(endian + 'I', offset))
        data.extend(b''.join(encoded))
        return start

    if new_keys:
        struct.pack_into(endian + 'I', data, 4, table(keys))
    if len(strings) != len(byml.strings):
        struct.pack_into(endian + 'I', data, 8, table(strings))
    trie = {}
    for record in records:
        cursor = trie
        for key in record['path']:
            cursor = cursor.setdefault(key, {})
        cursor[None] = record['after']
    memo = {}

    def value(typ, offset, edits):
        if None in edits:
            if isinstance(edits[None], bool):
                return 0xd0, struct.pack(endian + 'I', int(edits[None]))
            return 0xa0, struct.pack(endian + 'I', string_ids[edits[None]])
        if typ in (0xc0, 0xc1):
            if not edits and not new_keys:
                return typ, raw[offset:offset + 4]
            start = None if offset is None else byml.u32(offset)
            return typ, struct.pack(endian + 'I', node(start, typ, edits))
        if edits:
            raise ValueError('Cannot traverse a scalar.')
        return typ, raw[offset:offset + 4]

    def node(start, typ, edits):
        if not edits and start in memo:
            return memo[start]
        entries = []
        count = 0 if start is None else byml.u24(start + 1)
        if typ == 0xc1:
            originals = {}
            if start is not None:
                for index in range(count):
                    off = start + 4 + index * 8
                    originals[byml.keys[byml.u24(off)]] = (raw[off + 3], off + 4)
            for key in sorted(set(originals) | set(edits), key=key_ids.__getitem__):
                if key in originals:
                    child_typ, child_offset = originals[key]
                else:
                    child_typ, child_offset = (0xa0, None) if None in edits[key] else (0xc1, None)
                child_typ, payload = value(child_typ, child_offset, edits.get(key, {}))
                entries.append((key_ids[key], child_typ, payload))
        elif typ == 0xc0:
            values = (start + 4 + count + 3) & ~3
            for index in range(count):
                child_typ, payload = value(raw[start + 4 + index], values + index * 4, edits.get(index, {}))
                entries.append((index, child_typ, payload))
        else:
            raise ValueError('Unsupported container.')
        align()
        target = len(data)
        data.extend(bytes([typ]) + len(entries).to_bytes(3, order))
        if typ == 0xc1:
            for key_id, child_typ, payload in entries:
                data.extend(key_id.to_bytes(3, order) + bytes([child_typ]) + payload)
        else:
            data.extend(bytes(child_typ for _, child_typ, _ in entries))
            align()
            for _, _, payload in entries:
                data.extend(payload)
        if not edits and start is not None:
            memo[start] = target
        return target

    root = byml.u32(12)
    new_root = node(root, raw[root], trie)
    struct.pack_into(endian + 'I', data, 12, new_root)
    result = bytes(data)
    if Byml(result).root != expected:
        raise ValueError('BYML edit changed unexpected semantic content.')
    return result
