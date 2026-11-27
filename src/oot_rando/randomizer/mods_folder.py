"""Seeds in the game's mods folder: conservative installation, archiving and conflicts."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from oot_rando.patching.randomize_kokiri import TITLE
from oot_rando.pc_port import is_port_folder
from oot_rando.randomizer.artifact import (QOL_FOLDER, is_qol_install, is_randomizer_seed, manifest_of,
                                          read_artifact)
from oot_rando.randomizer.randomizer_core import settings_identity
from oot_rando.versions import is_newer
from oot_rando.versions import version_key


def archive_previous_seeds(title_directory, archive, keep=None):
    """Move earlier seeds of this application out of the mods folder (never delete them)."""
    title_directory = Path(title_directory)
    moved = []
    if not title_directory.is_dir():
        return moved
    for other in sorted(title_directory.iterdir()):
        if other.name != keep and is_randomizer_seed(other):
            archive.mkdir(parents=True, exist_ok=True)
            target = archive / other.name
            if target.exists():
                target = archive / (other.name + '-' + hashlib.sha256(str(other).encode()).hexdigest()[:6])
            shutil.move(str(other), str(target))
            moved.append(target)
    return moved


def validate_mod_directory(directory):
    """Accept an emulator title folder or the mods folder of a built PC port (Hookshot, Longshot...)."""
    directory = Path(directory).resolve()
    if directory.exists() and not directory.is_dir():
        raise ValueError('The selected mods folder is a file.')
    if directory.name.upper() == TITLE:
        return directory
    game = directory.parent
    if directory.name.lower() == 'mods' and is_port_folder(game):
        return directory
    raise ValueError('Choose the mods folder of title ' + TITLE
                     + ' (emulator), or the mods folder of a PC port (next to image.bin and romfs:'
                     + ' Hookshot, Longshot...).')


def conflicting_mods(title_directory, manifest, skip):
    return [other.name for other in title_directory.iterdir()
            if other.is_dir() and other.name != skip and not is_randomizer_seed(other)
            and not is_qol_install(other)
            and any((other / 'romfs' / name).exists() for name in manifest['files'])]


def _move_to_archive(directory, archive, suffix):
    from oot_rando.path_safety import fs_path, safe_archive_target
    archive = Path(archive)
    os.makedirs(fs_path(archive), exist_ok=True)
    target = safe_archive_target(archive, Path(directory).name, suffix)
    shutil.move(fs_path(directory), fs_path(target))
    return target


def validate_nup_file(nup_path):
    "Verify that nup_path exists and passes check_supported_game before seed generation starts."
    from oot_rando.formats.inspect_nup import Nup
    from oot_rando.patching.randomize_kokiri import check_supported_game
    p = Path(nup_path)
    if not p.is_file():
        raise ValueError("Select the local NUP file.")
    nup = Nup(p)
    try:
        check_supported_game(nup)
    finally:
        close_fn = getattr(nup, "close", None)
        if callable(close_fn):
            close_fn()
    return p


def preflight_plain_generation(nup, title_directory, settings, archive=None, *, check_nup=True, check_game_closed=False):
    "Run upfront sanity checks for plain (My Games off) seed generation before spawning a worker."
    from oot_rando.path_safety import ARCHIVE_HEADROOM, SEED_ROMFS_HEADROOM, validate_path_headroom
    from oot_rando.party_health import preflight_mods_operation
    settings.validate_supported()
    title_directory = validate_mod_directory(title_directory)
    validate_path_headroom(title_directory, max_relative_len=SEED_ROMFS_HEADROOM, label="Mods folder")
    if archive is not None:
        validate_path_headroom(Path(archive), max_relative_len=ARCHIVE_HEADROOM, label="Seed archive folder", enforce_win_classic=False)
    if check_game_closed:
        import subprocess
        from oot_rando.randomizer.save_patch import GameRunning, running_game
        processes = None
        if os.name != "nt":
            try:
                processes = subprocess.check_output(["ps", "-axo", "comm="], text=True).splitlines()
            except (OSError, subprocess.SubprocessError):
                processes = []
        game = running_game(processes)
        if game:
            raise GameRunning(f"Save and close the game / emulator first ({game} is running).")
    if check_nup:
        validate_nup_file(nup)
    name = "OoT_Randomizer_" + settings_identity(settings)[:16]
    destination = title_directory / name
    if destination.exists() and (archive is None or not is_randomizer_seed(destination)):
        raise ValueError("Folder " + name + " already exists in the mods.")
    pf = preflight_mods_operation(
        title_directory,
        source_paths=[nup] if (check_nup and Path(nup).exists()) else (),
        allow_missing_parents=True,
    )
    if not pf["ok"]:
        raise ValueError("; ".join(pf["errors"]))
    if archive is not None:
        pf_arch = preflight_mods_operation(Path(archive), allow_missing_parents=True)
        if not pf_arch["ok"]:
            raise ValueError("; ".join(pf_arch["errors"]))
    return title_directory


def continued_save(title_directory, settings):
    """Seed id that saves of the same Archipelago slot are bound to, from a seed installed
    in ``title_directory``, or None.

    A newer version of the application gives the same patch a new seed id. The placements
    come from the patch, so the new seed keeps the old binding and those saves go on."""
    if settings.archipelago is None or not Path(title_directory).is_dir():
        return None
    patch = settings.to_dict()['archipelago']
    for other in sorted(Path(title_directory).iterdir()):
        if not is_randomizer_seed(other):
            continue
        manifest = json.loads((other / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('settings', {}).get('archipelago') == patch:
            return manifest.get('save_seed_id') or manifest['seed_id']
    return None


def saves_origin(title_directory, destination, settings):
    """Oldest application version the saves of the seed about to be written at ``destination``
    may come from, when older than this one, else None (``saves_from`` of its manifest).

    The saves continued are those of the seed it replaces: the copy of the same settings in
    ``destination``, or the seed of the same Archipelago slot (:func:`continued_save`). Their
    own origin is kept, so a save is given again every fix it may lack even after several
    regenerations whose save update the player declined (randomizer/save_patch.py)."""
    from oot_rando import __version__
    from oot_rando.randomizer.save_patch import BEFORE_RECORDED_VERSIONS, saves_from
    title_directory, destination = Path(title_directory), Path(destination)
    replaced = [destination] if is_randomizer_seed(destination) else []
    if settings.archipelago is not None and title_directory.is_dir():
        patch = settings.to_dict()['archipelago']
        replaced += [other for other in sorted(title_directory.iterdir())
                     if other != destination and is_randomizer_seed(other)
                     and manifest_of(other).get('settings', {}).get('archipelago') == patch]
    versions = [str(saves_from(manifest_of(path)) or BEFORE_RECORDED_VERSIONS) for path in replaced]
    versions = [v if version_key(v) else BEFORE_RECORDED_VERSIONS for v in versions]
    if not versions:
        return None
    oldest = min(versions, key=version_key)
    return oldest if is_newer(__version__, oldest) else None


def generate_in_mods(nup, title_directory, settings, progress=None, archive=None, generate=None):
    """Generate a seed straight into the mods folder (no separate output folder).

    The seed folder ``OoT_Randomizer_<id>`` is written in ``title_directory``. It is
    always generated anew: the same settings give the same folder name, but a copy
    already there may come from an older version of the application, so it is moved
    to ``archive`` first (never deleted). Earlier seeds of this application are then
    archived too. A seed sharing resources with another mod is moved to the archive
    and installation stops. An Archipelago seed keeps the saves of the seed of the same
    slot it replaces (:func:`continued_save`). Returns the seed folder.
    """
    real_generate = generate is None
    if real_generate:
        from oot_rando.randomizer.randomizer_core import generate
    from oot_rando.path_safety import SEED_ROMFS_HEADROOM, validate_path_headroom
    settings.validate_supported()
    report = progress or (lambda message: None)
    title_directory = validate_mod_directory(title_directory)
    validate_path_headroom(title_directory, max_relative_len=SEED_ROMFS_HEADROOM, label="Mods folder", enforce_win_classic=False)
    name = 'OoT_Randomizer_' + settings_identity(settings)[:16]
    destination = title_directory / name
    if destination.exists() and (archive is None or not is_randomizer_seed(destination)):
        raise ValueError('Folder ' + name + ' already exists in the mods.')
    if real_generate:
        validate_nup_file(nup)
    save_seed_id = continued_save(title_directory, settings)
    origin = saves_origin(title_directory, destination, settings)
    options = {'saves_from': origin} if origin else {}
    if destination.exists():
        report('Same seed already installed: old copy archived, generating again…')
        _move_to_archive(destination, Path(archive), '-replaced')
    title_directory.mkdir(parents=True, exist_ok=True)
    if save_seed_id:
        report('Same Archipelago slot already installed: its saves carry over.')
        options['save_seed_id'] = save_seed_id
    generate(nup, destination, settings, report, **options)
    manifest, _ = read_artifact(destination)
    conflicts = conflicting_mods(title_directory, manifest, name)
    if conflicts:
        if archive is not None:
            _move_to_archive(destination, Path(archive), '')
        raise ValueError('Resources shared with: ' + ', '.join(conflicts)
                         + '. Move these mods out of the title folder, then generate again.')
    if archive is not None:
        archive_previous_seeds(title_directory, Path(archive), keep=name)
    warning = qol_seed_warning(title_directory)
    if warning:
        report('Warning: ' + warning)
    return destination


def qol_seed_warning(title_directory):
    """Text to show after a seed install while ``OoT_QoL`` sits beside it, else None.

    The QoL folder sorts first and carries its own resource table and chest flows, which
    would hide the seed's larger ones."""
    if is_qol_install(Path(title_directory) / QOL_FOLDER):
        return (QOL_FOLDER + " is installed in this mods folder. Turn it off in your emulator's add-ons, "
                'or move it out of the mods folder, while playing this seed.')
    return None
