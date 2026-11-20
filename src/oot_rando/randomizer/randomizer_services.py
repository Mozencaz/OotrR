"""Local artifact verification, conservative installation and manual tracker storage."""
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from oot_rando.randomizer.randomizer_core import Settings, settings_identity
from oot_rando.patching.randomize_kokiri import TITLE, BUILD
from oot_rando.pc_port import is_port_folder


# (generator_version, adapter_version) of the seeds this version still opens.
ACCEPTED_GENERATORS = (
    ('0.1.0', 'kokiri-qol-v1'), ('0.2.0', 'prudent-chests-v2'), ('0.3.0', 'native-environment-v1'),
    ('0.4.0', 'ap-glitchless-v1'), ('0.5.0', 'ap-glitchless-v2'), ('0.6.0', 'ap-glitchless-v2'),
    ('0.7.0', 'ap-glitchless-v3'), ('0.8.0', 'ap-glitchless-v4'), ('0.9.0', 'ap-glitchless-v5'),
    ('0.10.0', 'ap-glitchless-v5'), ('0.11.0', 'ap-glitchless-v5'), ('0.11.1', 'ap-glitchless-v5'),
    ('0.11.2', 'ap-glitchless-v5'), ('0.11.3', 'ap-glitchless-v5'), ('0.11.4', 'ap-glitchless-v5'),
    ('0.10.1', 'ap-glitchless-v5'), ('0.12.0', 'ap-glitchless-v5'), ('0.12.1', 'ap-glitchless-v5'))

QOL_FOLDER = 'OoT_QoL'
QOL_KIND = 'qol'


def read_artifact(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('kind') == QOL_KIND:
        raise ValueError('This folder is a quality-of-life install, not a randomizer seed.')
    if manifest.get('schema_version') != 1 or manifest.get('title_id') != TITLE or manifest.get('build_id') != BUILD:
        raise ValueError('Unsupported manifest or build.')
    settings = Settings.from_dict(manifest['settings'])
    version = (manifest.get('generator_version'), manifest.get('adapter_version'))
    if version not in ACCEPTED_GENERATORS:
        raise ValueError('Unsupported generator version.')
    if version[0] in {'0.2.0', '0.3.0', '0.4.0', '0.5.0', '0.6.0', '0.7.0', '0.8.0', '0.9.0', '0.10.0', '0.11.0', '0.11.1', '0.11.2', '0.11.3', '0.11.4', '0.10.1', '0.12.0', '0.12.1'}:
        settings.validate_supported()
    if version[0] in ('0.1.0', '0.4.0', '0.9.0', '0.10.0', '0.11.0', '0.11.1', '0.11.2', '0.11.3', '0.11.4', '0.10.1'):
        # Early 0.1 manifests predate the categories field and 0.4 manifests the
        # non-chest options. Do not inject defaults into their historical seed
        # identity while validating their settings.
        # Earlier full settings predate newer option defaults; inserting those
        # defaults must not change an existing artifact's identity.
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


def regeneration_settings(manifest, current_version=None):
    """Settings to generate an accepted seed again with this version of the application, or None.

    ``manifest`` must come from :func:`read_artifact`, which refuses the seeds this version no
    longer supports. Offered when the seed was made by an older version of the application
    (``app_version`` of its manifest; seeds made before 0.7.3 do not record it): a seed made
    by this version, or by a newer one, needs no regeneration. The settings (seed name, full
    options, categories, Archipelago patch...) are read back unchanged, so the regenerated
    seed keeps its name and settings."""
    from oot_rando.updater import is_newer, version_key
    if current_version is None:
        from oot_rando import __version__ as current_version
    if not isinstance(manifest, dict):
        return None
    made_by = manifest.get('app_version')
    if made_by is not None and (version_key(str(made_by)) is None or not is_newer(current_version, str(made_by))):
        return None
    try:
        return Settings.from_dict(manifest['settings']).validate_supported()
    except (KeyError, TypeError, ValueError):
        return None


def installed_regeneration(directory, current_version=None):
    """Settings to regenerate the seed installed in ``directory``, or None when it is up to
    date, missing, or no longer accepted by this version (see :func:`regeneration_settings`)."""
    try:
        manifest, _ = read_artifact(directory)
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return regeneration_settings(manifest, current_version)


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


def is_qol_install(directory):
    """True for the quality-of-life folder written by ``qol_install`` (never a seed)."""
    directory = Path(directory)
    if not directory.is_dir() or directory.name != QOL_FOLDER:
        return False
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return manifest.get('kind') == QOL_KIND and manifest.get('title_id') == TITLE


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


def saves_origin(title_directory, destination, settings):
    """Oldest application version the saves of the seed about to be written at ``destination``
    may come from, when older than this one, else None (``saves_from`` of its manifest).

    The saves continued are those of the seed it replaces: the copy of the same settings in
    ``destination``, or the seed of the same Archipelago slot (:func:`continued_save`). Their
    own origin is kept, so a save is given again every fix it may lack even after several
    regenerations whose save update the player declined (tracker/save_patch.py)."""
    from oot_rando import __version__
    from oot_rando.tracker.save_patch import BEFORE_RECORDED_VERSIONS, saves_from
    from oot_rando.updater import is_newer, version_key
    title_directory, destination = Path(title_directory), Path(destination)
    replaced = [destination] if is_randomizer_seed(destination) else []
    if settings.archipelago is not None and title_directory.is_dir():
        patch = settings.to_dict()['archipelago']
        replaced += [other for other in sorted(title_directory.iterdir())
                     if other != destination and is_randomizer_seed(other)
                     and _manifest(other).get('settings', {}).get('archipelago') == patch]
    versions = [str(saves_from(_manifest(path)) or BEFORE_RECORDED_VERSIONS) for path in replaced]
    versions = [v if version_key(v) else BEFORE_RECORDED_VERSIONS for v in versions]
    if not versions:
        return None
    oldest = min(versions, key=version_key)
    return oldest if is_newer(__version__, oldest) else None


def _manifest(directory):
    try:
        manifest = json.loads((Path(directory) / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


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
    if generate is None:
        from oot_rando.randomizer.randomizer_core import generate
    report = progress or (lambda message: None)
    title_directory = validate_mod_directory(title_directory)
    name = 'OoT_Randomizer_' + settings_identity(settings)[:16]
    destination = title_directory / name
    save_seed_id = continued_save(title_directory, settings)
    origin = saves_origin(title_directory, destination, settings)
    options = {'saves_from': origin} if origin else {}
    if destination.exists():
        if archive is None or not is_randomizer_seed(destination):
            raise ValueError('Folder ' + name + ' already exists in the mods.')
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
