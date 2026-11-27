"""Read-only structural decoder for the supported remake's progress.sav.

The file stores a 32-byte header, 33 typed hash/value tables separated by
``(0, type_id)`` records, then out-of-line data. Type 32 points to the sorted,
zero-terminated set of true Bool64bitKey flags. No game files are changed.
"""
from pathlib import Path
import hashlib
import os
import struct
import time


MAGIC = 0x01020304
FORMAT_VERSION = 0x002D80EB
PROGRESS_TYPE_HASH = 0xA3DB7114
MAX_SAVE_SIZE = 16 * 1024 * 1024


class SaveFormatError(ValueError):
    """The save is unsupported, incomplete or structurally inconsistent."""


class SaveChangedError(OSError):
    """A consistent read could not be obtained while the game writes its save."""


def decode_progress(data):
    """Decode one immutable byte snapshot, without guessing flag positions.

    ``bool64`` contains the keys whose value is true. A key absent from this
    complete sparse table is false only if it is known to the seed's GameData
    schema and belongs to progress.sav. It is not evidence about unknown keys.
    """
    if not isinstance(data, bytes):
        raise TypeError('Save data must be bytes.')
    if not 32 + 33 * 8 + 16 <= len(data) <= MAX_SAVE_SIZE:
        raise SaveFormatError('Truncated save or unsupported size.')
    magic, version, table_end = struct.unpack_from('<III', data)
    if magic != MAGIC or version != FORMAT_VERSION:
        raise SaveFormatError('Unsupported save format.')
    if any(data[12:32]):
        raise SaveFormatError('Unsupported save header.')
    if table_end % 8 or not 32 + 33 * 8 <= table_end <= len(data) - 8:
        raise SaveFormatError('Invalid save table bound.')

    sections = [dict() for _ in range(33)]
    section = -1
    for offset in range(32, table_end, 8):
        key, value = struct.unpack_from('<II', data, offset)
        if key == 0:
            if value != section + 1 or value >= len(sections):
                raise SaveFormatError('Invalid save type sequence.')
            section = value
        else:
            if section < 0 or key in sections[section]:
                raise SaveFormatError('Duplicate save key or missing table.')
            sections[section][key] = value
    if section != 32:
        raise SaveFormatError('Incomplete save tables.')
    if set(sections[32]) != {PROGRESS_TYPE_HASH}:
        raise SaveFormatError('This file is not a progress save.')

    def span(pointer, size):
        if pointer < table_end or size < 0 or pointer + size > len(data):
            raise SaveFormatError('Save data out of bounds.')
        return data[pointer:pointer + size]

    bools = {}
    for key, value in sections[0].items():
        if value not in (0, 1):
            raise SaveFormatError('Invalid save boolean value.')
        bools[key] = bool(value)
    integers = {key: struct.unpack('<i', struct.pack('<I', value))[0]
                for key, value in sections[2].items()}
    if integers.keys() & sections[20].keys():
        raise SaveFormatError('Ambiguous integer key in the save.')
    integers.update(sections[20])
    strings = {}
    for type_id, size in ((12, 16), (14, 32), (16, 64)):
        for key, pointer in sections[type_id].items():
            raw = span(pointer, size)
            if b'\0' not in raw:
                raise SaveFormatError('Unterminated save string.')
            try:
                value = raw.split(b'\0', 1)[0].decode('utf-8')
            except UnicodeDecodeError as error:
                raise SaveFormatError('Invalid UTF-8 save string.') from error
            if key in strings:
                raise SaveFormatError('Ambiguous string key in the save.')
            strings[key] = value
    int64 = {key: struct.unpack('<q', span(pointer, 8))[0]
             for key, pointer in sections[22].items()}
    uint64 = {key: struct.unpack('<Q', span(pointer, 8))[0]
              for key, pointer in sections[24].items()}

    sparse_start = sections[32][PROGRESS_TYPE_HASH]
    span(sparse_start, 8)
    if sparse_start % 4:
        raise SaveFormatError('Invalid collection table alignment.')
    flags64, previous, cursor = {}, 0, sparse_start
    while cursor + 8 <= len(data):
        value = struct.unpack_from('<Q', data, cursor)[0]
        cursor += 8
        if value == 0:
            break
        if value <= previous:
            raise SaveFormatError('Unsorted or duplicate collection keys.')
        flags64[value] = True
        previous = value
    else:
        raise SaveFormatError('Truncated or unterminated collection table.')
    # Current files end at the terminator. Only zero padding is tolerated;
    # stale/nonzero bytes after it may indicate an interrupted rewrite.
    if any(data[cursor:]):
        raise SaveFormatError('Inconsistent end of save.')

    # Validate pointers for the remaining reference-valued types too. Their
    # payloads are deliberately not interpreted as inventory or collection.
    scalar_types = {0, 2, 4, 6, 20}
    for type_id, values in enumerate(sections):
        if type_id in scalar_types:
            continue
        for pointer in values.values():
            span(pointer, 1)

    return {'bool': bools, 'bool64': flags64, 'bool64_complete': True,
            'int': integers, 'uint': dict(sections[20]), 'int64': int64,
            'uint64': uint64, 'enum': dict(sections[6]), 'strings': strings,
            'format_version': version, 'sha256': hashlib.sha256(data).hexdigest()}


def _stamp(stat):
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _read_once(path):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_SAVE_SIZE:
            raise SaveFormatError('Save too large.')
        data = stream.read(MAX_SAVE_SIZE + 1)
        after = os.fstat(stream.fileno())
    if _stamp(before) != _stamp(after) or len(data) != after.st_size:
        raise SaveChangedError('Save being written; read it again.')
    return data, after


def load_snapshot(path, attempts=3):
    """Read a stable progress.sav twice, and reject concurrent changes.

    Bounded retries are for save writers; a malformed file never becomes an
    empty (apparently fresh) game. The caller should retain its last good state.
    """
    path = Path(path).resolve()
    if not isinstance(attempts, int) or not 1 <= attempts <= 5:
        raise ValueError('The number of reads must be between 1 and 5.')
    for attempt in range(attempts):
        try:
            first, first_stat = _read_once(path)
            second, second_stat = _read_once(path)
            if first != second or _stamp(first_stat) != _stamp(second_stat):
                raise SaveChangedError('Save being written; read it again.')
            snapshot = decode_progress(second)
            snapshot.update(path=str(path), mtime_ns=second_stat.st_mtime_ns,
                            size=second_stat.st_size, source='save')
            return snapshot
        except SaveChangedError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02)
    raise AssertionError('unreachable')
