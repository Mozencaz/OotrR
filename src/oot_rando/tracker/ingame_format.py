"""Binary seed file read by the in-game tracker module (``RandoTracker/seed.trk``).

The layout is documented in ``docs/ingame-tracker-format.md``; the module parses exactly this.
Little-endian. ``build`` writes version 4 (version 3 without the checks' ids and places after the header's
flags, version 2 without the flags word either, version 1 without the checks' names), or version 3 for a module
that reads no later one, ``parse`` is the reference reader the tests use and reads all four (the module validates
the same bounds).
"""
import math
import struct

MAGIC = b'RTRK'
VERSION = 4
READABLE_VERSIONS = (1, 2, 3, 4)   # 1: the checks have no names; 1 and 2: no flags; 1 to 3: no ids or places
WRITABLE_VERSIONS = (3, 4)

HEADER = struct.Struct('<4sHH21I')
HEADER_V3 = struct.Struct('<4sHH17I')
HEADER_V2 = struct.Struct('<4sHH16I')   # versions 1 and 2
REGION = struct.Struct('<III')       # name offset, first check, check count
CHECK = struct.Struct('<QII')        # key, kind, name offset (reserved and 0 in version 1)
ITEM = struct.Struct('<IHH')         # name offset, first rule, rule count
RULE = struct.Struct('<IHH')         # Bool hash, level, reserved
KEYS = struct.Struct('<IBBHIIII')    # name offset, flags, small key total, reserved, found, held, ring, boss
IDENT = struct.Struct('<I')          # a check's id (its internal key), by check index: string offset
PLACE = struct.Struct('<IIIfff')     # check index, map name offset, map label offset, x, y, z (metres)

KIND_BOOL, KIND_BOOL64 = 1, 2
FLAG_ARCHIPELAGO = 1                 # the seed comes from an Archipelago patch (the console is on by default)
KEY_SMALL, KEY_BOSS, KEY_SMALL_ALL, KEY_BOSS_ALL = 1, 2, 4, 8
MAX_U8, MAX_U16, MAX_U32, MAX_U64 = 0xFF, 0xFFFF, 0xFFFFFFFF, (1 << 64) - 1
MAX_COORDINATE = 1e7                 # metres; the module refuses a place farther out (and a NaN)
STRING_ALIGNMENT = 4
# What the module keeps a fixed-size state for; a larger file is refused there.
MAX_REGIONS, MAX_KEY_ROWS = 64, 16

# Tables in file order: (name, record layout). The header holds ``<singular>_offset`` and ``<singular>_count``.
TABLES_V3 = (('region', REGION), ('check', CHECK), ('item', ITEM), ('rule', RULE), ('key', KEYS))
TABLES = TABLES_V3 + (('ident', IDENT), ('place', PLACE))
HEADER_FIELDS_V3 = (('file_size', 'seed_marker', 'goal_marker', 'seed_id_offset', 'strings_offset', 'strings_size')
                    + tuple(f'{name}_{part}' for name, _ in TABLES_V3 for part in ('offset', 'count')) + ('flags',))
HEADER_FIELDS = HEADER_FIELDS_V3 + tuple(f'{name}_{part}' for name, _ in TABLES[len(TABLES_V3):]
                                         for part in ('offset', 'count'))


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


def _coordinate(value):
    value = float(value)
    if not -MAX_COORDINATE <= value <= MAX_COORDINATE:
        raise ValueError(f'Place coordinate out of range: {value}')
    return value


def build(seed_id, seed_marker, goal_marker, regions, items, keys, flags=0, version=VERSION):
    """Serialise the seed file.

    ``regions``: ``[(name, [(kind, key, check name[, check id, places])])]``, ``places`` being
    ``[(map, map label, x, y, z)]``; ``items``: ``[(name, [(hash, level)])]``;
    ``keys``: ``[{'name', 'flags', 'total', 'found', 'held', 'ring', 'boss'}]``; ``flags``: FLAG_*.
    ``version`` 3 leaves the ids and places out (the file a module older than them reads).
    """
    if version not in WRITABLE_VERSIONS:
        raise ValueError(f'Seed file version {version} is not one this exporter writes.')
    if len(regions) > MAX_REGIONS or len(keys) > MAX_KEY_ROWS:
        raise ValueError('More regions or dungeons than the in-game tracker can show.')
    header, fields = _layout(version)
    table_names = [name for name, _ in (TABLES if version >= 4 else TABLES_V3)]
    strings = _Strings()
    seed_id_offset = strings.add(seed_id)
    region_rows, check_rows, item_rows, rule_rows, ident_rows, place_rows = [], [], [], [], [], []
    for name, checks in regions:
        region_rows.append(REGION.pack(strings.add(name), len(check_rows), len(checks)))
        for kind, key, check_name, *rest in checks:
            ident, places = rest if rest else ('', ())
            index = len(check_rows)
            check_rows.append(CHECK.pack(_bounded(key, MAX_U64, 'check key'), kind, strings.add(check_name)))
            if version < 4:
                continue
            ident_rows.append(IDENT.pack(strings.add(ident)))
            place_rows.extend(PLACE.pack(index, strings.add(place_map), strings.add(label),
                                         *(_coordinate(v) for v in (x, y, z)))
                              for place_map, label, x, y, z in places)
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
              'seed_id_offset': seed_id_offset, 'strings_offset': header.size, 'strings_size': len(blob),
              'flags': _bounded(flags, MAX_U32, 'flags')}
    offset = header.size + len(padded)
    tables = dict(zip(table_names, (region_rows, check_rows, item_rows, rule_rows, key_rows, ident_rows, place_rows)))
    for name, rows in tables.items():
        values[name + '_offset'], values[name + '_count'] = offset, len(rows)
        offset += sum(len(row) for row in rows)
    values['file_size'] = offset
    out = bytearray(header.pack(MAGIC, version, header.size, *(values[f] for f in fields)))
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
    """A table's records; a table the file's version doesn't have is empty."""
    count, offset = header.get(name + '_count', 0), header.get(name + '_offset', header['header_size'])
    if offset < header['header_size'] or offset + count * record.size > header['file_size']:
        raise ValueError(f'The {name} table leaves the file.')
    return [record.unpack_from(data, offset + i * record.size) for i in range(count)]


def _layout(version):
    """The header's struct and fields of a version."""
    if version >= 4:
        return HEADER, HEADER_FIELDS
    return (HEADER_V3, HEADER_FIELDS_V3) if version == 3 else (HEADER_V2, HEADER_FIELDS_V3[:-1])


def _places_by_check(data, header, places, check_count):
    """Each check's places (the table is in check order, as the module requires)."""
    result, last = [[] for _ in range(check_count)], 0
    for check, place_map, label, x, y, z in places:
        if check >= check_count or check < last:
            raise ValueError('A place out of check order or past the checks.')
        if not all(-MAX_COORDINATE <= v <= MAX_COORDINATE for v in (x, y, z)):
            raise ValueError('A place out of the world.')
        last = check
        result[check].append((_string(data, header, place_map), _string(data, header, label), x, y, z))
    return result


def parse(data):
    """Read and validate a seed file; returns the arguments ``build`` takes, each check with its id and places
    (an older version's: none)."""
    if len(data) < HEADER_V2.size:
        raise ValueError('File shorter than its header.')
    magic, version, header_size = struct.unpack_from('<4sHH', data)
    if magic != MAGIC or version not in READABLE_VERSIONS:
        raise ValueError('Not a seed file of a version this reader knows.')
    layout, fields = _layout(version)
    if header_size != layout.size or len(data) < layout.size:
        raise ValueError('Not a seed file of a version this reader knows.')
    header = {'flags': 0, **dict(zip(fields, layout.unpack_from(data)[3:])), 'header_size': layout.size}
    if header['file_size'] != len(data):
        raise ValueError('File size differs from the header.')
    if header['strings_offset'] < layout.size or header['strings_offset'] + header['strings_size'] > len(data):
        raise ValueError('The string table leaves the file.')
    regions, checks, items, rules, keys, idents, places = (_read_table(data, header, name, record)
                                                           for name, record in TABLES)
    for table, children in ((regions, checks), (items, rules)):
        if any(first + count > len(children) for _, first, count in table):
            raise ValueError('A table row leaves the table it points into.')
    if idents and len(idents) != len(checks):
        raise ValueError('The ids are not one per check.')
    ids = [_string(data, header, offset) for offset, in idents] or [''] * len(checks)
    located = _places_by_check(data, header, places, len(checks))
    named = [(kind, key, _string(data, header, check_name), ids[i], located[i])
             for i, (key, kind, check_name) in enumerate(checks)]
    return {
        'seed_id': _string(data, header, header['seed_id_offset']),
        'seed_marker': header['seed_marker'], 'goal_marker': header['goal_marker'], 'flags': header['flags'],
        'regions': [(_string(data, header, name), named[first:first + count]) for name, first, count in regions],
        'items': [(_string(data, header, name), [(h, level) for h, level, _ in rules[first:first + count]])
                  for name, first, count in items],
        'keys': [{'name': _string(data, header, name), 'flags': flags, 'total': total, 'found': found,
                  'held': held, 'ring': ring, 'boss': boss}
                 for name, flags, total, _, found, held, ring, boss in keys],
    }


def version_of(data):
    """The version a seed file says it is (not validated: parse does that)."""
    return struct.unpack_from('<4sH', data)[1]


def places_by_id(data):
    """``{check id: places}`` of a seed file (empty for a version without them): what an update of a seed's
    tracker without the game file keeps."""
    return {ident: places for _, checks in parse(data)['regions'] for _, _, _, ident, places in checks
            if ident and places}
