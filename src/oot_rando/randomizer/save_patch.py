"""Bring an existing progress.sav up to date with the start values of its seed.

Some fixes only reach a new game: the opening writes GameData values once
(``event_patch.add_start_values``) and a game started before the fix never gets
them. The seed's manifest lists those values (``start_values``: name -> value).
This module sets the matching booleans of an existing save, in place:

* only booleans of table 0 that the save already holds are changed; a key is
  never added and the file keeps its exact size and layout;
* the save must belong to the seed (its ``RandoSeed.<id>`` flag is true);
* the game (PC port or emulator) must not be running, since it rewrites the
  save from memory;
* a dated backup is written next to the save first, the file is replaced
  atomically and read back; on any mismatch the backup is put back.
"""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import struct

from oot_rando.catalog.hashing import murmur3
from oot_rando.formats.save_file import decode_progress, load_snapshot, SaveFormatError
from oot_rando.pc_port import KNOWN_EXES
from oot_rando.pc_port import is_port_process
from oot_rando.system import emulator_exes
from oot_rando.versions import is_newer
from oot_rando.versions import version_key

BACKUP_SUFFIX = '.backup-'


class SavePatchRefused(ValueError):
    """The save cannot be patched now (game running, other seed, unsupported file)."""


class GameRunning(SavePatchRefused):
    """The game or an emulator runs: it would overwrite the save from memory."""


def seed_marker_name(manifest):
    """Name of the flag binding saves to ``manifest``'s seed (``randomizer_core.save_marker``)."""
    from oot_rando.randomizer.randomizer_core import save_marker
    return save_marker(manifest)


def bool_targets(start_values):
    """``{hash: (name, value)}`` of the boolean start values (integers are left alone)."""
    targets = {}
    for name, value in (start_values or {}).items():
        if isinstance(value, bool):
            targets[murmur3(name)] = (name, value)
    return targets


def _bool_offsets(data):
    """File offset of the value of every record of table 0 (``decode_progress`` validated it)."""
    table_end = struct.unpack_from('<I', data, 8)[0]
    offsets, section = {}, -1
    for offset in range(32, table_end, 8):
        key, value = struct.unpack_from('<II', data, offset)
        if key == 0:
            section = value
            if section > 0:
                break
        elif section == 0:
            offsets[key] = offset + 4
    return offsets


def plan_patch(data, start_values, markers):
    """Changes ``data`` needs: ``(new bytes, [(name, old, new)], [missing names])``.

    ``markers``: names of the seed flags accepted for this save (one must be true).
    Raises SavePatchRefused if the save belongs to another seed."""
    try:
        snapshot = decode_progress(data)
    except SaveFormatError as error:
        raise SavePatchRefused('Unsupported save: ' + str(error)) from error
    if not any(snapshot['bool'].get(murmur3(name)) is True for name in markers):
        raise SavePatchRefused('This save does not belong to this seed.')
    offsets = _bool_offsets(data)
    patched, changes, missing = bytearray(data), [], []
    for key, (name, value) in sorted(bool_targets(start_values).items(), key=lambda item: item[1][0]):
        if key not in offsets:
            missing.append(name)
            continue
        old = snapshot['bool'][key]
        if old != value:
            struct.pack_into('<I', patched, offsets[key], int(value))
            changes.append((name, old, value))
    return bytes(patched), changes, missing


def running_game(processes=None):
    """Exe name of a running game (PC port or emulator), or None.

    ``processes``: image paths of the running processes (default: the system's)."""
    if processes is None:
        processes = process_images()
    names = set(KNOWN_EXES) | emulator_exes()
    for image in processes:
        # Windows and POSIX separators alike (a Windows image path read on Linux too).
        name = image.replace('\\', '/').rsplit('/', 1)[-1].lower()
        if name in names or is_port_process(image):
            return name
    return None


def process_images():
    """Image path (or bare name) of every process visible to this user (Windows only)."""
    if os.name != 'nt':
        return []
    import ctypes
    from ctypes import wintypes
    psapi = ctypes.WinDLL('psapi')
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    array = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(array, ctypes.sizeof(array), ctypes.byref(needed)):
        raise SavePatchRefused('Cannot list the running programs.')
    images = []
    for pid in array[:needed.value // 4]:
        handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            size = wintypes.DWORD(520)
            buffer = ctypes.create_unicode_buffer(size.value)
            if k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                images.append(buffer.value)
        finally:
            k32.CloseHandle(handle)
    return images


def backup_path(path, now=None):
    stamp = (now or datetime.now()).strftime('%Y%m%d-%H%M%S')
    target = path.with_name(path.name + BACKUP_SUFFIX + stamp)
    index = 1
    while target.exists():
        index += 1
        target = path.with_name(f'{path.name}{BACKUP_SUFFIX}{stamp}-{index}')
    return target


def patch_save(path, start_values, markers, processes=None, now=None):
    """Apply ``start_values`` to the save at ``path``. Returns a report dict:

    ``changes`` [(name, old, new)], ``missing`` (names absent from the save, left
    absent), ``backup`` (path, or None when nothing had to change).
    Raises SavePatchRefused when the game runs or the save is not this seed's."""
    path = Path(path)
    game = running_game(processes)
    if game:
        raise GameRunning(f'Close the game first ({game} is running).')
    snapshot = load_snapshot(path)
    data = path.read_bytes()
    if snapshot['sha256'] != hashlib.sha256(data).hexdigest():
        raise SavePatchRefused('The save changed while it was read; try again.')
    patched, changes, missing = plan_patch(data, start_values, markers)
    report = {'path': str(path), 'changes': changes, 'missing': missing, 'backup': None}
    if not changes:
        return report
    backup = backup_path(path, now)
    shutil.copy2(path, backup)
    report['backup'] = str(backup)
    temporary = path.with_name(path.name + '.rando-tmp')
    try:
        with temporary.open('wb') as stream:
            stream.write(patched)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        written = path.read_bytes()
        after = decode_progress(written)
        expected = decode_progress(patched)
        if written != patched or after['bool'] != expected['bool'] or len(written) != len(data):
            raise SavePatchRefused('The save read back differs from what was written.')
    except Exception:
        if temporary.exists():
            temporary.unlink()
        shutil.copy2(backup, path)
        raise
    return report


def pending_changes(path, start_values, markers):
    """Names that would change in the save at ``path`` ([] if none or unreadable)."""
    try:
        _, changes, _ = plan_patch(Path(path).read_bytes(), start_values, markers)
    except (OSError, SavePatchRefused):
        return []
    return [name for name, _, _ in changes]


# Save fixes that are not start values, oldest first: (application version, fix), where
# ``fix(manifest)`` returns {name: bool}. A save is given every fix of a version newer than
# the oldest application its game may come from (:func:`saves_from`), in order, a later one
# winning: a player who skipped several versions, or regenerated without updating the saves,
# still gets them all. Start values need no entry: the opening of the new seed writes all of
# them (every earlier fix included), so they are always applied.
SAVE_FIXES = ()

# ``saves_from`` of a seed replacing one made before 0.7.3 (no version recorded): every fix.
BEFORE_RECORDED_VERSIONS = '0.0.0'


def saves_from(manifest):
    """Oldest application version the saves of this seed may have been started with, or None
    when unknown (every fix may be missing).

    A regenerated seed keeps the origin of the seed it replaced (``saves_from`` of its
    manifest, :func:`oot_rando.randomizer.mods_folder.generate_in_mods`): a save
    is never assumed to hold the fixes of a version whose update the player declined.
    Otherwise the application that made the seed (``app_version``, none before 0.7.3)."""
    if not isinstance(manifest, dict):
        return None
    return manifest.get('saves_from') or manifest.get('app_version')


def migration_values(manifest, previous=None):
    """Booleans to set in the saves of ``manifest``'s seed (start values and :data:`SAVE_FIXES`).

    The fixes the saves may lack are those newer than :func:`saves_from` of the new seed
    when it recorded the origin of the game it continues, else of ``previous`` (manifest of
    the seed it replaced); unknown: every fix."""
    since = manifest.get('saves_from') or saves_from(previous)
    values = dict(manifest.get('start_values') or {})
    for version, fix in sorted(SAVE_FIXES, key=lambda step: _version_order(step[0])):
        if since is None or is_newer(version, str(since)):
            values.update(fix(manifest))
    if bool_targets(values):
        # The new seed's own flag, when the save already holds it (the game rewrote the
        # save with this seed's data): the save then reads as this seed's.
        values[seed_marker_name(manifest)] = True
    return values


def _version_order(version):
    return version_key(version) or ((0, 0, 0), 0, ())


def migration_markers(manifest, previous=None):
    """Seed flags of the saves to bring up to date after ``manifest`` was installed.

    The new seed's own flag, plus those of the same seed made by an earlier generator:
    a seed generated again after an update of the application gets a new identity, but
    its saves are the same game. That is the flag of ``previous`` (the seed it replaced)
    when both have the same settings, and the identity of these settings under every
    generator version still accepted, so a save started several versions ago (several
    regenerations ago, or never regenerated) is still recognized."""
    markers = [seed_marker_name(manifest)]

    def add(name):
        if name not in markers:
            markers.append(name)
    same = isinstance(previous, dict) and previous.get('settings') == manifest.get('settings')
    if same:
        add(seed_marker_name(previous))
    if not manifest.get('save_seed_id') and isinstance(manifest.get('settings'), dict):
        from oot_rando.randomizer.randomizer_core import SEED_MARKER_PREFIX, Settings, settings_identity
        from oot_rando.randomizer.artifact import ACCEPTED_GENERATORS
        try:
            settings = Settings.from_dict(manifest['settings'])
        except (KeyError, TypeError, ValueError):
            settings = None
        if settings is not None:
            for generator, adapter in ACCEPTED_GENERATORS:
                add(SEED_MARKER_PREFIX + settings_identity(settings, generator, adapter))
    return markers


def migration_candidates(paths, manifest, previous=None):
    """``[(path, [names that would change])]`` for the saves of the seed that need it."""
    values = migration_values(manifest, previous)
    if not bool_targets(values):
        return []
    markers = migration_markers(manifest, previous)
    found = []
    for path in paths:
        names = pending_changes(path, values, markers)
        if names:
            found.append((Path(path), names))
    return found
