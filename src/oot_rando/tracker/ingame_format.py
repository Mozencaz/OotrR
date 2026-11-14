"""Binary seed file read by the in-game tracker module (``RandoTracker/seed.trk``).

The layout is documented in ``docs/ingame-tracker-format.md``; the module parses exactly this.
Little-endian. ``build`` writes version 2 (version 1 without the checks' names), ``parse`` is the
reference reader the tests use and reads both (the module validates the same bounds).
"""
import struct

MAGIC = b'RTRK'
VERSION = 2
READABLE_VERSIONS = (1, 2)   # version 1: the checks have no names

HEADER = struct.Struct('<4sHH16I')
REGION = struct.Struct('<III')       # name offset, first check, check count
CHECK = struct.Struct('<QII')        # key, kind, name offset (reserved and 0 in version 1)
ITEM = struct.Struct('<IHH')         # name offset, first rule, rule count
RULE = struct.Struct('<IHH')         # Bool hash, level, reserved
KEYS = struct.Struct('<IBBHIIII')    # name offset, flags, small key total, reserved, found, held, ring, boss

KIND_BOOL, KIND_BOOL64 = 1, 2
KEY_SMALL, KEY_BOSS, KEY_SMALL_ALL, KEY_BOSS_ALL = 1, 2, 4, 8
MAX_U8, MAX_U16, MAX_U32, MAX_U64 = 0xFF, 0xFFFF, 0xFFFFFFFF, (1 << 64) - 1
STRING_ALIGNMENT = 4
# What the module keeps a fixed-size state for; a larger file is refused there.
MAX_REGIONS, MAX_KEY_ROWS = 64, 16

# Tables in file order: (name, record layout). The header holds ``<singular>_offset`` and ``<singular>_count``.
TABLES = (('region', REGION), ('check', CHECK), ('item', ITEM), ('rule', RULE), ('key', KEYS))
HEADER_FIELDS = (('file_size', 'seed_marker', 'goal_marker', 'seed_id_offset', 'strings_offset', 'strings_size')
                 + tuple(f'{name}_{part}' for name, _ in TABLES for part in ('offset', 'count')))


class _Strings:
    """NUL-terminated string table; offset 0 is the empty string."""

    def __init__(self):
        self.blob = bytearray(b'\0')
        self.offsets = {'': 0}

    def add(self, text):
        if text not in self.offsets:
            self.offsets[text] = len(self.blob)
            self.blob += text.encode('utf-8') + b'\0'
        return self.offsets[text]


def _bounded(value, limit, what):
    value = int(value)
    if not 0 <= value <= limit:
        raise ValueError(f'{what} out of range: {value}')
    return value


def build(seed_id, seed_marker, goal_marker, regions, items, keys):
    """Serialise the seed file.

    ``regions``: ``[(name, [(kind, key, check name)])]``; ``items``: ``[(name, [(hash, level)])]``;
    ``keys``: ``[{'name', 'flags', 'total', 'found', 'held', 'ring', 'boss'}]``.
    """
    if len(regions) > MAX_REGIONS or len(keys) > MAX_KEY_ROWS:
        raise ValueError('More regions or dungeons than the in-game tracker can show.')
    strings = _Strings()
    seed_id_offset = strings.add(seed_id)
    region_rows, check_rows, item_rows, rule_rows = [], [], [], []
    for name, checks in regions:
        region_rows.append(REGION.pack(strings.add(name), len(check_rows), len(checks)))
        check_rows.extend(CHECK.pack(_bounded(key, MAX_U64, 'check key'), kind, strings.add(check_name))
                          for kind, key, check_name in checks)
    for name, rules in items:
        item_rows.append(ITEM.pack(strings.add(name), _bounded(len(rule_rows), MAX_U16, 'rule index'),
                                   _bounded(len(rules), MAX_U16, 'rule count')))
        rule_rows.extend(RULE.pack(_bounded(h, MAX_U32, 'rule hash'), _bounded(level, MAX_U16, 'item level'), 0)
                         for h, level in rules)
    key_rows = [KEYS.pack(strings.add(row['name']), row['flags'], _bounded(row['total'], MAX_U8, 'key total'), 0,
                          *(_bounded(row[field], MAX_U32, 'key hash') for field in ('found', 'held', 'ring', 'boss')))
                for row in keys]
    blob = bytes(strings.blob)
    padded = blob + b'\0' * (-len(blob) % STRING_ALIGNMENT)
    values = {'seed_marker': _bounded(seed_marker, MAX_U32, 'seed marker'),
              'goal_marker': _bounded(goal_marker, MAX_U32, 'goal marker'),
              'seed_id_offset': seed_id_offset, 'strings_offset': HEADER.size, 'strings_size': len(blob)}
    offset = HEADER.size + len(padded)
    tables = dict(zip((name for name, _ in TABLES), (region_rows, check_rows, item_rows, rule_rows, key_rows)))
    for name, rows in tables.items():
        values[name + '_offset'], values[name + '_count'] = offset, len(rows)
        offset += sum(len(row) for row in rows)
    values['file_size'] = offset
    out = bytearray(HEADER.pack(MAGIC, VERSION, HEADER.size, *(values[f] for f in HEADER_FIELDS)))
    out += padded
    for rows in tables.values():
        out += b''.join(rows)
    return bytes(out)


def _string(data, header, offset):
    if offset >= header['strings_size']:
        raise ValueError('String offset outside the table.')
    start = header['strings_offset']
    end = data.index(b'\0', start + offset, start + header['strings_size'])
    return data[start + offset:end].decode('utf-8')


def _read_table(data, header, name, record):
    count, offset = header[name + '_count'], header[name + '_offset']
    if offset < HEADER.size or offset + count * record.size > header['file_size']:
        raise ValueError(f'The {name} table leaves the file.')
    return [record.unpack_from(data, offset + i * record.size) for i in range(count)]


def parse(data):
    """Read and validate a seed file; returns the arguments ``build`` takes."""
    if len(data) < HEADER.size:
        raise ValueError('File shorter than its header.')
    magic, version, header_size, *fields = HEADER.unpack_from(data)
    if magic != MAGIC or version not in READABLE_VERSIONS or header_size != HEADER.size:
        raise ValueError('Not a seed file of a version this reader knows.')
    header = dict(zip(HEADER_FIELDS, fields))
    if header['file_size'] != len(data):
        raise ValueError('File size differs from the header.')
    if header['strings_offset'] < HEADER.size or header['strings_offset'] + header['strings_size'] > len(data):
        raise ValueError('The string table leaves the file.')
    regions, checks, items, rules, keys = (_read_table(data, header, name, record) for name, record in TABLES)
    for table, children in ((regions, checks), (items, rules)):
        if any(first + count > len(children) for _, first, count in table):
            raise ValueError('A table row leaves the table it points into.')
    named = [(kind, key, _string(data, header, check_name)) for key, kind, check_name in checks]
    return {
        'seed_id': _string(data, header, header['seed_id_offset']),
        'seed_marker': header['seed_marker'], 'goal_marker': header['goal_marker'],
        'regions': [(_string(data, header, name), named[first:first + count]) for name, first, count in regions],
        'items': [(_string(data, header, name), [(h, level) for h, level, _ in rules[first:first + count]])
                  for name, first, count in items],
        'keys': [{'name': _string(data, header, name), 'flags': flags, 'total': total, 'found': found,
                  'held': held, 'ring': ring, 'boss': boss}
                 for name, flags, total, _, found, held, ring, boss in keys],
    }
