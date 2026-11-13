"""Quality-of-life install without randomization: intro skip and fast chests.

Writes the folder ``OoT_QoL`` into the emulator's title folder from the player's own
game file; nothing of the game is shipped. The patches are those of the randomizer
(``patching.qol_patches``, by Mozencaz, reused with his permission), applied and
compressed by the same code.
"""
import argparse
import json
import shutil
from pathlib import Path
from typing import NamedTuple

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import decompress, dictionaries
from oot_rando.game.world_maps import effective_members
from oot_rando.patching.qol_patches import (CHEST_FLOW, INTRO, INTRO_PARENT, SMALL_CHEST_FLOW, patch_intro,
                                            quick_chest, quick_small_chest, sha256)
from oot_rando.patching.randomize_kokiri import BUILD, TITLE, check_supported_game
from oot_rando.randomizer.randomizer_core import (GENERATOR_VERSION, compress_changed, complete_event_info,
                                                  grow_resource_table, json_document, publish_mod, source_reader)
from oot_rando.randomizer.randomizer_services import (QOL_FOLDER, QOL_KIND, conflicting_mods, is_qol_install,
                                                      is_randomizer_seed, validate_mod_directory)

CREDIT = 'Patches from OotrR by Mozencaz, reused with his permission.'
NO_OPTION = 'Choose at least one option: the intro skip or the fast chests.'


class QolInstall(NamedTuple):
    folder: Path
    warnings: list


def generate_qol_files(nup_path, intro_skip=True, fast_chests=True, progress=None):
    """Return (files, manifest): the resources to write under ``romfs/`` and the folder's manifest."""
    if not (intro_skip or fast_chests):
        raise ValueError(NO_OPTION)
    report = progress or (lambda message: None)
    report('Checking the game…')
    nup = Nup(nup_path)
    try:
        check_supported_game(nup)
        d = dictionaries(nup)
        members = effective_members(nup)
        sources, files, skips, extra_raw = {}, {}, {}, {}
        read = source_reader(nup, members, sources)
        if intro_skip:
            report('Skippable introduction…')
            files[INTRO] = patch_intro(read(INTRO), read(INTRO_PARENT))
            skips['intro'] = ['Dm_Kokiri_0000']
        if fast_chests:
            report('Chests without cutscene…')
            extra_raw[CHEST_FLOW], skips['quick_chest'] = quick_chest(decompress(read(CHEST_FLOW), d))
            extra_raw[SMALL_CHEST_FLOW], skips['quick_small_chest'] = quick_small_chest(
                decompress(read(SMALL_CHEST_FLOW), d))
            skips.update(complete_event_info(extra_raw, nup, members, d, read))
        growths = {}
        compress_changed(extra_raw, files, growths, read, d)
        allocations = grow_resource_table(files, growths, {}, read, d)
    finally:
        nup.stream.close()
    manifest = {'schema_version': 1, 'kind': QOL_KIND, 'generator_version': GENERATOR_VERSION,
                'title_id': TITLE, 'build_id': BUILD,
                'options': {'intro_skip': intro_skip, 'fast_chests': fast_chests},
                'files': {p: {'size': len(v), 'sha256': sha256(v)} for p, v in sorted(files.items())},
                'source_files': sources, 'resource_allocations': allocations, 'skips': skips,
                'credit': CREDIT}
    return files, manifest


def install_warnings(title_directory, manifest):
    """What may stop the emulator from using ``OoT_QoL``: a seed enabled beside it, or another mod
    changing the same resources."""
    title_directory = Path(title_directory)
    if not title_directory.is_dir():
        return []
    warnings = []
    seeds = [other.name for other in sorted(title_directory.iterdir()) if is_randomizer_seed(other)]
    if seeds:
        warnings.append('A randomizer seed is installed (' + ', '.join(seeds) + '). The randomizer already '
                        'contains its own quality of life, and the emulator turns ' + QOL_FOLDER
                        + ' off while a seed is enabled.')
    shared = conflicting_mods(title_directory, manifest, QOL_FOLDER)
    if shared:
        warnings.append('Other mods change the same resources: ' + ', '.join(shared)
                        + '. Only one of them can apply; disable the others.')
    return warnings


def install_qol(nup_path, title_directory, intro_skip=True, fast_chests=True, progress=None):
    """Write ``OoT_QoL`` into ``title_directory``, replacing an earlier install of it.

    The files are generated before anything on disk changes. A folder of that name that this
    application did not write is never replaced. Returns the folder and the warnings."""
    report = progress or (lambda message: None)
    title_directory = validate_mod_directory(title_directory)
    destination = title_directory / QOL_FOLDER
    if destination.exists() and not is_qol_install(destination):
        raise ValueError('Folder ' + QOL_FOLDER + ' already exists in the mods and is not a quality-of-life '
                         'install of this application. Move it away, then install again.')
    files, manifest = generate_qol_files(nup_path, intro_skip, fast_chests, report)
    warnings = install_warnings(title_directory, manifest)
    for warning in warnings:
        report('Warning: ' + warning)
    report('Writing the mod…')
    if destination.exists():
        shutil.rmtree(destination)
    publish_mod(destination, files, {'manifest.json': json_document(manifest)})
    report('Installed: ' + str(destination))
    return QolInstall(destination, warnings)


def main(argv):
    """``qol-install GAME.nup MODS_DIR [--intro-skip|--no-intro-skip] [--fast-chests|--no-fast-chests]``."""
    parser = argparse.ArgumentParser(
        prog='qol-install', description="Install the quality-of-life patches only (no randomization) "
                                        "into the emulator's mods folder.")
    parser.add_argument('nup', help='your Ocarina of Time .nup file')
    parser.add_argument('mods_dir', help="the emulator's load/" + TITLE
                        + ' folder (or the mods folder next to hookshot.exe)')
    parser.add_argument('--intro-skip', action=argparse.BooleanOptionalAction, default=True,
                        help='skip the introduction cutscene (default: on)')
    parser.add_argument('--fast-chests', action=argparse.BooleanOptionalAction, default=True,
                        help='open big and small chests without their cutscene (default: on)')
    args = parser.parse_args(argv)
    if not (args.intro_skip or args.fast_chests):
        parser.error(NO_OPTION)
    result = install_qol(args.nup, args.mods_dir, args.intro_skip, args.fast_chests, print)
    print(json.dumps({'installed': str(result.folder), 'warnings': len(result.warnings)}))
    return 0
