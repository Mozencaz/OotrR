"""Effect/sound link files (XLNK: ``ELink2/*.belnk``, ``SLink2/*.bslnk``), layout version 0x24.

Only what grafting one call tree from a user into another needs is decoded
(verified on the game's ``elink2.Product.110.belnk``, 27/11; general layout after
the xlink2 project by dt-12345 and the Nintendo-File-Formats wiki):

* header: user count at 0x48, condition table and name table positions at 0x50 and
  0x58 (absolute), user CRC32 name hashes at 0x60 (sorted), then one u64 absolute
  offset per user (8-aligned); the parameter define table follows (its u32 at +4 is
  the number of user parameters every user stores);
* user: 0x38-byte header (``USER_HEADER``: call table and asset counts, trigger table
  position relative to the user), local property name pointers (u64), user parameters
  (u32 each), the call indices sorted by key name (u16, 4-aligned), the call tables
  (0x30 bytes, ``CALL``), the containers (offsets relative to their area), then the
  triggers, which refer to calls by their offset in the call table;
* call: key name (name table offset), asset index (-1 for a container), flags (bit 0:
  container), emit count, parent call index, GUID, CRC32 of the key, then the asset
  parameter offset (global table; container area for a container) and the condition
  offset (global table, 0xffffffff for none);
* container: type (0 switch, 3 blend, 5 grid...), first and last child call indices,
  then type data; a grid ends with its cells, call indices (-1: empty).

Names, asset parameters and conditions are shared tables: a grafted call keeps the
source offsets, so only the target user grows. Users after it move, as do the
condition and name tables.
"""
import struct
import zlib

USER_COUNT, CONDITION_POS, NAME_POS, USER_HASHES = 0x48, 0x50, 0x58, 0x60
USER_HEADER = struct.Struct('<IHH9I4xQ')
CALL = struct.Struct('<QhHiiIIIQQ')
CONTAINER_FLAG = 1
NO_CONDITION = 0xffffffff
SWITCH, BLEND, GRID = 0, 3, 5
CONTAINER_SIZES = {SWITCH: 0x20, BLEND: 0x10, 4: 0x10, 6: 0x10}   # random kinds are counted apart
GRID_HEAD = 0x28


def _align(value, alignment):
    return -(-value // alignment) * alignment


class Xlink:
    """Users of an XLNK file, by name hash."""

    def __init__(self, data):
        if data[:4] != b'XLNK' or struct.unpack_from('<I', data, 8)[0] != 0x24:
            raise ValueError('XLNK version 0x24 expected.')
        self.data = bytes(data)
        count = struct.unpack_from('<I', data, USER_COUNT)[0]
        self.hashes = struct.unpack_from(f'<{count}I', data, USER_HASHES)
        self.offset_table = _align(USER_HASHES + 4 * count, 8)
        self.offsets = struct.unpack_from(f'<{count}Q', data, self.offset_table)
        self.condition_pos, self.name_pos = struct.unpack_from('<QQ', data, CONDITION_POS)
        self.user_params = struct.unpack_from('<I', data, self.offset_table + 8 * count + 4)[0]
        ends = sorted(self.offsets) + [self.condition_pos]
        self.ends = {start: ends[i + 1] for i, start in enumerate(ends[:-1])}

    def name(self, offset):
        start = self.name_pos + offset
        return self.data[start:self.data.index(b'\0', start)]

    def user(self, name):
        key = zlib.crc32(name.encode())
        if key not in self.hashes:
            raise KeyError(f'XLNK user {name} not found.')
        start = self.offsets[self.hashes.index(key)]
        return User(self, start, self.ends[start])


class User:
    """One user: header counts, calls, raw container and trigger areas."""

    def __init__(self, xlink, start, end):
        data = self.data = xlink.data
        self.xlink, self.start, self.end = xlink, start, end
        self.header = list(USER_HEADER.unpack_from(data, start))
        locals_count, calls = self.header[1], self.header[3]
        params = start + USER_HEADER.size + 8 * locals_count
        sorted_pos = params + 4 * xlink.user_params
        self.prefix = data[start + USER_HEADER.size:sorted_pos]
        self.sorted = list(struct.unpack_from(f'<{calls}H', data, sorted_pos))
        call_pos = start + _align(sorted_pos + 2 * calls - start, 4)
        self.calls = [list(CALL.unpack_from(data, call_pos + i * CALL.size)) for i in range(calls)]
        self.container_pos = call_pos + CALL.size * calls
        trigger_pos = start + self.header[-1]
        self.containers = data[self.container_pos:trigger_pos]
        self.triggers = data[trigger_pos:end]
        for i, call in enumerate(self.calls):
            if call[6] != zlib.crc32(xlink.name(call[0])):
                raise ValueError(f'XLNK call {i} of user at {start:#x}: key hash mismatch.')

    def key(self, index):
        return self.xlink.name(self.calls[index][0])

    def top_call(self, key):
        found = [i for i, call in enumerate(self.calls) if call[4] == -1 and self.key(i) == key.encode()]
        if len(found) != 1:
            raise ValueError(f'Expected one top-level XLNK call {key}, found {len(found)}.')
        return found[0]

    def container(self, index):
        """(type, first child, last child, raw bytes) of a container call."""
        offset = self.calls[index][8]
        kind, first, last = struct.unpack_from('<Iii', self.containers, offset)
        if kind == GRID:
            rows, columns = self.containers[offset + 0x26], self.containers[offset + 0x27]
            size = GRID_HEAD + 4 * (rows + columns + rows * columns)
        elif kind in CONTAINER_SIZES:
            size = CONTAINER_SIZES[kind]
        else:
            raise ValueError(f'Unsupported XLNK container type {kind}.')
        return kind, first, last, bytearray(self.containers[offset:offset + size])

    def children(self, index):
        if not self.calls[index][2] & CONTAINER_FLAG:
            return []
        _, first, last, _ = self.container(index)
        for child in range(first, last + 1):
            if self.calls[child][4] != index:
                raise ValueError(f'XLNK call {child} is not a child of {index}.')
        return list(range(first, last + 1))

    def find(self, path):
        """Call at ``path``: a top-level key, then one child key per level."""
        index = self.top_call(path[0])
        for key in path[1:]:
            found = [child for child in self.children(index) if self.key(child) == key.encode()]
            if len(found) != 1:
                raise ValueError(f'Expected one XLNK call {key} under {path[0]}, found {len(found)}.')
            index = found[0]
        return index

    def tree(self, index):
        """Calls under ``index`` (itself first), each container's children in a row."""
        order = [index]
        for call in order:
            order.extend(self.children(call))
        return order

    def build(self):
        """The user's bytes, triggers last."""
        out = bytearray(USER_HEADER.pack(*self.header))
        out += self.prefix
        out += struct.pack(f'<{len(self.sorted)}H', *self.sorted)
        out += bytes(_align(len(out), 4) - len(out))
        for call in self.calls:
            out += CALL.pack(*call)
        out += self.containers
        out += self.triggers
        return bytes(out)


def graft_call(data, source, target, key, source_path=None):
    """``data`` where ``target``'s top-level call ``key`` plays a tree of ``source``.

    The tree is ``source``'s call at ``source_path`` (default: its own ``key``). It is
    copied (containers and assets) into the target call, which keeps its key, GUID
    and lack of condition (its triggers refer to it by position). The descendants are
    appended to the target's calls."""
    xlink = Xlink(data)
    src, dst = xlink.user(source), xlink.user(target)
    root, slot = src.find(source_path or (key,)), dst.top_call(key)
    order = src.tree(root)
    new_index = {root: slot}
    for call in order[1:]:
        new_index[call] = len(dst.calls) + len(new_index) - 1
    guids = {call[5] for call in dst.calls}
    free_assets = [dst.calls[slot][1]] if dst.calls[slot][1] >= 0 else []
    assets = dst.header[4]
    containers = bytearray(dst.containers)
    added = []
    for call in order:
        record = list(src.calls[call])
        if call == root:
            record[0], record[5], record[6] = dst.calls[slot][0], dst.calls[slot][5], dst.calls[slot][6]
            record[9] = NO_CONDITION
        elif record[5] in guids:
            raise ValueError(f'XLNK GUID {record[5]:#x} already used by {target}.')
        record[4] = new_index[record[4]] if call != root else -1
        if record[2] & CONTAINER_FLAG:
            kind, first, last, raw = src.container(call)
            if kind not in CONTAINER_SIZES and kind != GRID:
                raise ValueError(f'Unsupported XLNK container type {kind}.')
            struct.pack_into('<ii', raw, 4, new_index[first], new_index[last])
            if kind == GRID:
                rows, columns = raw[0x26], raw[0x27]
                cells = GRID_HEAD + 4 * (rows + columns)
                for cell in range(rows * columns):
                    value = struct.unpack_from('<i', raw, cells + 4 * cell)[0]
                    if value >= 0:
                        struct.pack_into('<i', raw, cells + 4 * cell, new_index[value])
            containers += bytes(_align(len(containers), 4) - len(containers))
            record[8] = len(containers)
            containers += raw
        else:
            if free_assets:
                record[1] = free_assets.pop()
            else:
                record[1], assets = assets, assets + 1
        if call == root:
            dst.calls[slot] = record
        else:
            added.append(record)
    dst.calls += added
    dst.header[3], dst.header[4] = len(dst.calls), assets
    old_size = dst.end - dst.start
    order_by_key = dst.sorted + list(range(len(dst.calls) - len(added), len(dst.calls)))
    dst.sorted = sorted(order_by_key, key=_key_of(dst))   # stable: ties keep their order
    head = len(dst.build()) - len(dst.containers) - len(dst.triggers)
    trigger_pos = head + len(containers)
    # Same alignment as before for the triggers and everything after the user.
    containers += bytes((dst.header[-1] - trigger_pos) % 8)
    dst.containers = bytes(containers)
    dst.header[-1] = head + len(dst.containers)
    user = dst.build()
    delta = len(user) - old_size
    if delta % 8:
        raise ValueError('XLNK user grew by an unaligned size.')
    out = bytearray(data[:dst.start] + user + data[dst.end:])
    struct.pack_into('<I', out, 4, struct.unpack_from('<I', out, 4)[0] + delta)
    struct.pack_into('<QQ', out, CONDITION_POS, xlink.condition_pos + delta, xlink.name_pos + delta)
    offsets = [offset + delta if offset > dst.start else offset for offset in xlink.offsets]
    struct.pack_into(f'<{len(offsets)}Q', out, xlink.offset_table, *offsets)
    return bytes(out)


def _key_of(user):
    keys = {}

    def key(index):
        if index not in keys:
            keys[index] = user.key(index)
        return keys[index]
    return key


def call_tree(data, user, path):
    """``[(key, flags, emit count, asset params, condition, container type, depth)]`` of a call tree.

    The tree of the call at ``path`` (see :meth:`User.find`), its root without key and
    condition: comparable across users and grafts (no indices)."""
    target = Xlink(data).user(user)
    root = target.find(path)
    depth = {root: 0}
    rows = []
    for call in target.tree(root):
        record = target.calls[call]
        for child in target.children(call):
            depth[child] = depth[call] + 1
        kind = target.container(call)[0] if record[2] & CONTAINER_FLAG else None
        params = None if kind is not None else record[8]
        if call == root:
            rows.append((None, record[2], record[3], params, None, kind, 0))
        else:
            rows.append((target.key(call), record[2], record[3], params, record[9], kind, depth[call]))
    return rows
