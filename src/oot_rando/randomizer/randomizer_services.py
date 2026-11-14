"""Local artifact verification, conservative installation and manual tracker storage."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from oot_rando.randomizer.randomizer_core import Settings, settings_identity
from oot_rando.patching.randomize_kokiri import TITLE, BUILD
from oot_rando.pc_port import is_port_folder
from oot_rando.tracker import ingame_bundle
from oot_rando.tracker.ingame_bundle import MODULE_FILE, SEED_FILE


def _verify_exefs(directory, manifest):
    """Check the code modules the seed ships (``exefs/<name>``) against the manifest."""
    for name, info in (manifest.get('exefs') or {}).items():
        if name != MODULE_FILE:
            raise ValueError('Unknown code module: ' + name)
        data = (directory / 'exefs' / name).read_bytes()
        if len(data) != info['size'] or hashlib.sha256(data).hexdigest() != info['sha256']:
            raise ValueError('Modified or incomplete code module: ' + name)


def read_artifact(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('title_id') != TITLE or manifest.get('build_id') != BUILD:
        raise ValueError('Unsupported manifest or build.')
    settings = Settings.from_dict(manifest['settings'])
    version = (manifest.get('generator_version'), manifest.get('adapter_version'))
    if version not in {('0.1.0', 'kokiri-qol-v1'), ('0.2.0', 'prudent-chests-v2'),
                       ('0.3.0', 'native-environment-v1'), ('0.4.0', 'ap-glitchless-v1'),
                       ('0.5.0', 'ap-glitchless-v2'), ('0.6.0', 'ap-glitchless-v2'),
                       ('0.7.0', 'ap-glitchless-v3'), ('0.8.0', 'ap-glitchless-v4')}:
        raise ValueError('Unsupported generator version.')
    if version[0] in {'0.2.0', '0.3.0', '0.4.0', '0.5.0', '0.6.0', '0.7.0', '0.8.0'}:
        settings.validate_supported()
    if version[0] in ('0.1.0', '0.4.0'):
        # Early 0.1 manifests predate the categories field and 0.4 manifests the
        # non-chest options. Do not inject defaults into their historical seed
        # identity while validating their settings.
        identity = hashlib.sha256(json.dumps({'generator': version[0], 'adapter': version[1],
                                              'settings': manifest['settings']}, ensure_ascii=False,
                                             sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    else:
        identity = settings_identity(settings, *version)
    if manifest.get('seed_id') != identity:
        raise ValueError('Seed identity does not match its settings.')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('The mod holds no resource to install.')
    for name, info in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid resource path.')
        path = (directory / 'romfs' / name).resolve()
        if not path.is_relative_to(directory / 'romfs'):
            raise ValueError('Resource outside the mod.')
        data = path.read_bytes()
        # In-game reload test (archipelago.reload_test): the seed's own table is kept beside it.
        from oot_rando.archipelago.reload_test import seed_original
        data = seed_original(directory, name, data)
        if len(data) != info['size'] or hashlib.sha256(data).hexdigest() != info['sha256']:
            raise ValueError('Modified or incomplete resource: ' + name)
    _verify_exefs(directory, manifest)
    checks = json.loads((directory / 'checks.json').read_text(encoding='utf-8'))
    if checks.get('seed_id') != manifest['seed_id']:
        raise ValueError('The check catalogue belongs to another seed.')
    rows = checks.get('checks')
    if not isinstance(rows, list) or any(not isinstance(c, dict) or not isinstance(c.get('id'), str)
                                         or not isinstance(c.get('name'), str) or not isinstance(c.get('region'), str) for c in rows):
        raise ValueError('Invalid tracking catalogue.')
    if len({c['id'] for c in rows}) != len(rows):
        raise ValueError('Duplicate tracking identifiers.')
    if manifest.get('tracking'):
        raw = (directory / 'tracking.json').read_bytes()
        tracking = json.loads(raw)
        if (hashlib.sha256(raw).hexdigest() != manifest['tracking'].get('sha256')
                or tracking.get('seed_id') != manifest['seed_id'] or tracking.get('schema_version') != 1):
            raise ValueError('Tracking data modified or belonging to another seed.')
    return manifest, checks


def is_randomizer_seed(directory):
    """True only for a seed folder written by this application (verified manifest)."""
    directory = Path(directory)
    if not directory.is_dir() or not directory.name.startswith('OoT_Randomizer_'):
        return False
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return (manifest.get('title_id') == TITLE and isinstance(manifest.get('seed_id'), str)
            and directory.name == 'OoT_Randomizer_' + manifest['seed_id'][:16])


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


def _conflicting_mods(title_directory, manifest, skip):
    return [other.name for other in title_directory.iterdir()
            if other.is_dir() and other.name != skip and not is_randomizer_seed(other)
            and any((other / 'romfs' / name).exists() for name in manifest['files'])]


def _move_to_archive(directory, archive, suffix):
    archive.mkdir(parents=True, exist_ok=True)
    target, index = archive / (directory.name + suffix), 1
    while target.exists():
        index += 1
        target = archive / f'{directory.name}{suffix}-{index}'
    shutil.move(str(directory), str(target))
    return target


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


def generate_in_mods(nup, title_directory, settings, progress=None, archive=None, generate=None,
                     ingame_tracker=True):
    """Generate a seed straight into the mods folder (no separate output folder).

    The seed folder ``OoT_Randomizer_<id>`` is written in ``title_directory``. It is
    always generated anew: the same settings give the same folder name, but a copy
    already there may come from an older version of the application, so it is moved
    to ``archive`` first (never deleted). Earlier seeds of this application are then
    archived too. A seed sharing resources with another mod is moved to the archive
    and installation stops. An Archipelago seed keeps the saves of the seed of the same
    slot it replaces (:func:`continued_save`). ``ingame_tracker=False`` leaves the in-game
    tracker module and its data out of the seed. Returns the seed folder.
    """
    if generate is None:
        from oot_rando.randomizer.randomizer_core import generate
    report = progress or (lambda message: None)
    title_directory = validate_mod_directory(title_directory)
    name = 'OoT_Randomizer_' + settings_identity(settings)[:16]
    destination = title_directory / name
    save_seed_id = continued_save(title_directory, settings)
    if destination.exists():
        if archive is None or not is_randomizer_seed(destination):
            raise ValueError('Folder ' + name + ' already exists in the mods.')
        report('Same seed already installed: old copy archived, generating again…')
        _move_to_archive(destination, Path(archive), '-replaced')
    title_directory.mkdir(parents=True, exist_ok=True)
    options = {} if ingame_tracker else {'ingame_tracker': False}
    if save_seed_id:
        report('Same Archipelago slot already installed: its saves carry over.')
        options['save_seed_id'] = save_seed_id
    generate(nup, destination, settings, report, **options)
    manifest, _ = read_artifact(destination)
    conflicts = _conflicting_mods(title_directory, manifest, name)
    if conflicts:
        if archive is not None:
            _move_to_archive(destination, Path(archive), '')
        raise ValueError('Resources shared with: ' + ', '.join(conflicts)
                         + '. Move these mods out of the title folder, then generate again.')
    if archive is not None:
        archive_previous_seeds(title_directory, Path(archive), keep=name)
    return destination


def has_ingame_tracker(manifest):
    return SEED_FILE in manifest['files'] or MODULE_FILE in (manifest.get('exefs') or {})


def _replace_files(directory, contents):
    """Put ``contents`` ({relative path: bytes}) in ``directory``, in order: all staged first, then each
    moved into place; if a move fails, the files already moved are put back."""
    with tempfile.TemporaryDirectory(prefix='.oot-tracker-', dir=directory) as temporary:
        stage, staged, created, moved = Path(temporary), [], [], []
        for index, (relative, data) in enumerate(contents.items()):
            (stage / f'new-{index}').write_bytes(data)
            staged.append((directory / relative, stage / f'new-{index}', stage / f'old-{index}'))
        try:
            for target, new, old in staged:
                for folder in reversed(target.parents):
                    if folder.is_relative_to(directory) and not folder.exists():
                        folder.mkdir()
                        created.append(folder)
                backup = None
                if target.exists():
                    os.replace(target, old)
                    backup = old
                moved.append((target, backup))
                os.replace(new, target)
        except OSError as error:
            for target, backup in reversed(moved):
                if backup is not None:
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            for folder in reversed(created):
                folder.rmdir()
            if isinstance(error, PermissionError):
                raise ValueError('A file of the seed is in use: close the game, then update the in-game tracker again.') from error
            raise


def update_ingame_tracker(directory, add=False):
    """Bring a seed's in-game tracker to this version of the application: ``romfs/RandoTracker/seed.trk``,
    ``exefs/subsdk7`` and their entries in ``manifest.json``. Nothing else in the folder changes. A seed made
    without the tracker gets it only with ``add``. Returns the files written (none when already up to date)."""
    directory = Path(directory).resolve()
    if not (directory / 'manifest.json').is_file():
        raise ValueError('Not a seed folder (no manifest.json): ' + str(directory))
    raw = (directory / 'manifest.json').read_bytes()
    try:
        manifest, catalogue = read_artifact(directory)
    except (OSError, KeyError, TypeError) as error:
        raise ValueError('This seed folder is damaged or incomplete (' + str(error) + '): generate it again.') from error
    if not manifest.get('tracking'):
        raise ValueError('This seed has no tracking data, so it can\'t have the in-game tracker: generate it again.')
    if not has_ingame_tracker(manifest) and not add:
        raise ValueError('This seed was made without the in-game tracker. Ask to add it to update it.')
    tracking = json.loads((directory / 'tracking.json').read_bytes())
    updated, files, exefs = copy.deepcopy(manifest), {}, {}
    try:
        ingame_bundle.attach(updated, files, exefs, catalogue['checks'], tracking)
    except (KeyError, TypeError) as error:
        raise ValueError('This seed\'s tracking data is too old for the in-game tracker: generate it again.') from error
    contents = {}
    for relative, data in [(Path('romfs', SEED_FILE), files[SEED_FILE]), (Path('exefs', MODULE_FILE), exefs[MODULE_FILE])]:
        path = directory / relative
        if not path.is_file() or path.read_bytes() != data:
            contents[relative] = data
    if updated != manifest:
        newline = '\r\n' if b'\r\n' in raw else '\n'
        text = json.dumps(updated, ensure_ascii=False, indent=2).replace('\n', newline)
        contents[Path('manifest.json')] = text.encode('utf-8')
    if contents:
        _replace_files(directory, contents)
        read_artifact(directory)
    return [relative.as_posix() for relative in contents]


def update_ingame_trackers(folder, add=False):
    """:func:`update_ingame_tracker` on a seed folder, or on each seed of this application in a mods folder.
    Returns ``[(seed folder, files written)]``."""
    folder = Path(folder)
    if (folder / 'manifest.json').is_file():
        return [(folder, update_ingame_tracker(folder, add))]
    seeds = sorted(other for other in folder.iterdir() if is_randomizer_seed(other)) if folder.is_dir() else []
    if not seeds:
        raise ValueError('Neither a seed folder (no manifest.json) nor a mods folder holding a seed: ' + str(folder))
    return [(seed, update_ingame_tracker(seed, add)) for seed in seeds]


class ManualTracker:
    def __init__(self, directory, seed_id, slot, check_ids):
        if not isinstance(slot, str) or not slot.strip():
            raise ValueError('Give the game profile a name.')
        self.seed_id, self.slot = seed_id, slot
        self.allowed = set(check_ids)
        digest = hashlib.sha256((seed_id + '\0' + slot).encode()).hexdigest()
        self.path = Path(directory) / (digest + '.json')
        self.completed = set()
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('seed_id') != seed_id or data.get('slot') != slot:
                raise ValueError('Inconsistent tracking profile.')
            self.completed = set(data['completed']) & self.allowed

    def set_completed(self, ident, value):
        if ident not in self.allowed:
            raise ValueError('Check inconnu.')
        updated = set(self.completed)
        updated.add(ident) if value else updated.discard(ident)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema_version': 1, 'seed_id': self.seed_id,
                                        'slot': self.slot, 'source': 'manual',
                                        'completed': sorted(updated)}, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.completed = updated
