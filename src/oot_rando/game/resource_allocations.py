"""Grow exactly the requested resource allocations; never shrink or add entries."""
import struct
import zlib


def grow_resources(raw, growth_by_path):
    if raw[:6] != b'RESTBL':
        raise ValueError('Invalid RESTBL table.')
    version, block, count, names = struct.unpack_from('<IIII', raw, 6)
    if version != 1 or block != 160 or len(raw) != 22 + count * 8 + names * (block + 4):
        raise ValueError('Unsupported RESTBL format.')
    hashes = {}
    for index in range(count):
        position = 22 + index * 8
        hashes.setdefault(struct.unpack_from('<I', raw, position)[0], []).append(position + 4)
    named = {}
    for index in range(names):
        position = 22 + count * 8 + index * (block + 4)
        name = raw[position:position + block].split(b'\0', 1)[0].decode()
        named.setdefault(name, []).append(position + block)
    result, records, used = bytearray(raw), [], set()
    for path, growth in sorted(growth_by_path.items()):
        if type(growth) is not int or growth < 0:
            raise ValueError('Invalid resource growth.')
        if not growth:
            continue
        target = path.removesuffix('.zs')
        digest = zlib.crc32(target.encode())
        slots = named.get(target, hashes.get(digest, []))
        if len(slots) != 1 or slots[0] in used:
            raise ValueError('Missing or ambiguous allocation: ' + target)
        offset = slots[0]
        used.add(offset)
        before = struct.unpack_from('<I', raw, offset)[0]
        after = (before + growth + 4095) & ~4095
        if after >= 1 << 32:
            raise ValueError('Resource allocation too large.')
        struct.pack_into('<I', result, offset, after)
        records.append({'path': target, 'crc32': f'{digest:08x}', 'before': before, 'after': after})
    allowed = {offset + index for offset in used for index in range(4)}
    if any(a != b and index not in allowed for index, (a, b) in enumerate(zip(raw, result))):
        raise ValueError('Unexpected RESTBL change.')
    return bytes(result), records


def add_resources(raw, sizes_by_path):
    """Insert CRC entries for NEW resources (sorted table); existing ones refused."""
    if raw[:6] != b'RESTBL':
        raise ValueError('Invalid RESTBL table.')
    version, block, count, names = struct.unpack_from('<IIII', raw, 6)
    if version != 1 or block != 160 or len(raw) != 22 + count * 8 + names * (block + 4):
        raise ValueError('Unsupported RESTBL format.')
    entries = [struct.unpack_from('<II', raw, 22 + i * 8) for i in range(count)]
    known = {crc for crc, _ in entries}
    named = {raw[22 + count * 8 + i * (block + 4):][:block].split(b'\0', 1)[0].decode() for i in range(names)}
    records = []
    for path, size in sorted(sizes_by_path.items()):
        target = path.removesuffix('.zs')
        digest = zlib.crc32(target.encode())
        if digest in known or target in named or type(size) is not int or not 0 < size < 1 << 32:
            raise ValueError('Existing RESTBL entry or invalid size: ' + target)
        entries.append((digest, size))
        known.add(digest)
        records.append({'path': target, 'crc32': f'{digest:08x}', 'before': None, 'after': size})
    entries.sort()
    result = bytearray(raw[:6]) + struct.pack('<IIII', version, block, len(entries), names)
    for crc, size in entries:
        result.extend(struct.pack('<II', crc, size))
    result.extend(raw[22 + count * 8:])
    return bytes(result), records
