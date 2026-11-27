"""A generated seed folder: its manifest, its check catalogue, and whether this version accepts it."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from oot_rando.patching.randomize_kokiri import BUILD, RESTBL, TITLE
from oot_rando.randomizer.randomizer_core import Settings, settings_identity
from oot_rando.versions import is_newer
from oot_rando.versions import version_key


# (generator_version, adapter_version) of the seeds this version still opens.
ACCEPTED_GENERATORS = (
    ('0.1.0', 'kokiri-qol-v1'), ('0.2.0', 'prudent-chests-v2'), ('0.3.0', 'native-environment-v1'),
    ('0.4.0', 'ap-glitchless-v1'), ('0.5.0', 'ap-glitchless-v2'), ('0.6.0', 'ap-glitchless-v2'),
    ('0.7.0', 'ap-glitchless-v3'), ('0.8.0', 'ap-glitchless-v4'), ('0.9.0', 'ap-glitchless-v5'),
    ('0.10.0', 'ap-glitchless-v5'), ('0.11.0', 'ap-glitchless-v5'), ('0.11.1', 'ap-glitchless-v5'),
    ('0.11.2', 'ap-glitchless-v5'), ('0.11.3', 'ap-glitchless-v5'), ('0.11.4', 'ap-glitchless-v5'),
    ('0.10.1', 'ap-glitchless-v5'), ('0.12.0', 'ap-glitchless-v5'), ('0.12.1', 'ap-glitchless-v5'),
    ('0.12.2', 'ap-glitchless-v5'), ('0.12.3', 'ap-glitchless-v5'), ('0.12.4', 'ap-glitchless-v5'),
    ('0.12.5', 'ap-glitchless-v5'), ('0.12.6', 'ap-glitchless-v5'), ('0.12.7', 'ap-glitchless-v5'),
    ('0.12.8', 'ap-glitchless-v5'), ('0.12.16', 'ap-glitchless-v5'), ('0.12.18', 'ap-glitchless-v5'),
    ('0.12.19', 'ap-glitchless-v5'), ('0.12.20', 'ap-glitchless-v5'),
    ('0.12.21', 'ap-glitchless-v5'), ('0.12.22', 'ap-glitchless-v5'), ('0.12.23', 'ap-glitchless-v5'))


QOL_FOLDER = 'OoT_QoL'


# In-game reload test (archipelago/reload_test.py): what to restore, beside the seed's manifest.
RELOAD_TEST_STATE = 'reload_test.json'


QOL_KIND = 'qol'


def seed_original(seed, name, data):
    """The seed's own bytes of resource ``name`` while the test is installed (else ``data``).

    Only the very table the test installed (its SHA-256 is in the state file) stands for
    the backup: any other change of the seed's RESTBL is still reported as a modification.
    """
    state_path, backup = Path(seed) / RELOAD_TEST_STATE, Path(seed) / (RELOAD_TEST_STATE + '.restbl')
    if name != RESTBL or not state_path.is_file() or not backup.is_file():
        return data
    try:
        installed = json.loads(state_path.read_text(encoding='utf-8')).get('restbl_sha256')
    except (OSError, ValueError, AttributeError):
        return data
    if installed and hashlib.sha256(data).hexdigest() == installed:
        return backup.read_bytes()
    return data


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
    if version[0] in {'0.2.0', '0.3.0', '0.4.0', '0.5.0', '0.6.0', '0.7.0', '0.8.0', '0.9.0', '0.10.0', '0.11.0', '0.11.1', '0.11.2', '0.11.3', '0.11.4', '0.10.1', '0.12.0', '0.12.1', '0.12.2', '0.12.3', '0.12.16', '0.12.18', '0.12.19', '0.12.20', '0.12.21', '0.12.22', '0.12.23'}:
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


def manifest_of(directory):
    try:
        manifest = json.loads((Path(directory) / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}
