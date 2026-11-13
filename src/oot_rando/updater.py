"""Self-update of the portable application from the GitHub releases.

* :func:`latest_release` asks the GitHub API for the latest published release
  (drafts and pre-releases excluded) and returns it when it is newer than this build.
* :func:`install` downloads the archive of this system, checks it against the
  release's ``SHA256SUMS.txt``, then swaps the executable in place: the running
  file is renamed ``<exe>.old`` (Windows allows renaming, not deleting, a running
  executable) and the new one takes its name. ``data/`` is never touched.
* :func:`restart` starts the new executable; :func:`cleanup` removes the ``.old``
  file at the next start.

Only a frozen build updates itself; from the sources, use ``git pull``.
"""
import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from oot_rando import __version__
from oot_rando.paths import FROZEN

REPOSITORY = 'Mozencaz/OotrR'
LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
USER_AGENT = 'OoT-Randomizer-updater'
CA_FILES = ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt',
            '/etc/ssl/ca-bundle.pem', '/etc/ssl/cert.pem')
MAX_ARCHIVE = 512 << 20


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    page: str            # release page (notes)
    notes: str
    asset: str           # archive name for this system
    asset_url: str
    sums_url: str


def parse_version(text):
    """(major, minor, patch) of 'v1.2.3' / '1.2' / '1.2.3-beta'; None if not a version."""
    match = re.match(r'v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', (text or '').strip())
    return tuple(int(part or 0) for part in match.groups()) if match else None


def is_newer(candidate, current=__version__):
    new, old = parse_version(candidate), parse_version(current)
    return bool(new and old and new > old)


def asset_suffix(platform=sys.platform):
    if platform.startswith('win'):
        return '-windows-x64.zip'
    if platform.startswith('linux'):
        return '-linux-x64.tar.gz'
    return None


def executable():
    return Path(sys.executable).resolve()


def can_self_update():
    return FROZEN and asset_suffix() is not None


def _context():
    context = ssl.create_default_context()
    if not context.get_ca_certs() and sys.platform.startswith('linux'):
        # A bundled OpenSSL may look for certificates where this distribution keeps none.
        for path in CA_FILES:
            if os.path.isfile(path):
                context.load_verify_locations(path)
                break
    return context


def _get(url, timeout, accept='application/octet-stream', limit=MAX_ARCHIVE):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
            data = response.read(limit + 1)
    except OSError as error:   # URLError, timeouts, SSL errors
        raise UpdateError(f'Cannot reach GitHub: {getattr(error, "reason", error)}') from None
    if len(data) > limit:
        raise UpdateError('The download is unexpectedly large.')
    return data


def release_from_json(value, current=__version__, platform=sys.platform):
    """The release described by a GitHub API answer if it is newer and has this system's archive."""
    if not isinstance(value, dict) or value.get('draft') or value.get('prerelease'):
        return None
    version = str(value.get('tag_name') or '').lstrip('v')
    suffix = asset_suffix(platform)
    if not suffix or not is_newer(version, current):
        return None
    assets = {a.get('name'): a.get('browser_download_url') for a in value.get('assets') or [] if isinstance(a, dict)}
    archive = next((name for name in assets if name and name.endswith(suffix)), None)
    if not archive or not assets.get('SHA256SUMS.txt'):
        return None
    return Release(version, str(value.get('html_url') or ''), str(value.get('body') or ''),
                   archive, assets[archive], assets['SHA256SUMS.txt'])


def latest_release(timeout=8):
    """The latest GitHub release when newer than this build, else None."""
    try:
        value = json.loads(_get(LATEST, timeout, 'application/vnd.github+json', 1 << 20))
    except ValueError:
        raise UpdateError('Unexpected answer from GitHub.') from None
    return release_from_json(value)


def expected_hash(sums, name):
    for line in sums.decode('utf-8', 'replace').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip('*') == name and re.fullmatch(r'[0-9a-fA-F]{64}', parts[0]):
            return parts[0].lower()
    raise UpdateError(f'{name} is not listed in SHA256SUMS.txt.')


def extract_executable(archive, name, exe_name):
    """Bytes of the executable inside a release archive (any folder level)."""
    if name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            member = next((m for m in bundle.namelist() if m.replace('\\', '/').rsplit('/', 1)[-1] == exe_name), None)
            if member:
                return bundle.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
            member = next((m for m in bundle.getmembers() if m.isfile() and m.name.rsplit('/', 1)[-1] == exe_name), None)
            if member:
                return bundle.extractfile(member).read()
    raise UpdateError(f'{exe_name} not found in {name}.')


def replace_executable(target, data):
    """Put ``data`` in place of ``target`` (the running executable), keeping ``target.old``."""
    new, old = target.with_name(target.name + '.new'), target.with_name(target.name + '.old')
    new.write_bytes(data)
    if os.name != 'nt':
        new.chmod(0o755)
    try:
        if old.exists():
            old.unlink()
        os.replace(target, old)
    except OSError as error:
        new.unlink(missing_ok=True)
        raise UpdateError(f'Cannot replace {target.name}: {error}') from None
    try:
        os.replace(new, target)
    except OSError as error:
        os.replace(old, target)   # put the running version back
        raise UpdateError(f'Cannot install the new version: {error}') from None


def install(release, progress=None):
    """Download, verify and install ``release``; returns the path of the new executable."""
    report = progress or (lambda message: None)
    if not can_self_update():
        raise UpdateError('Only the portable application updates itself. From the sources, use git pull.')
    target = executable()
    report(f'Downloading version {release.version}…')
    sums = _get(release.sums_url, 30, limit=1 << 16)
    archive = _get(release.asset_url, 120)
    if hashlib.sha256(archive).hexdigest() != expected_hash(sums, release.asset):
        raise UpdateError('The download is corrupted (checksum mismatch). Nothing was changed.')
    report('Installing…')
    replace_executable(target, extract_executable(archive, release.asset, target.name))
    return target


def restart(target):
    """Start ``target`` as a fresh process (not as a child of this PyInstaller instance)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('_MEI', '_PYI'))}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    flags = 0x00000008 | 0x00000200 if os.name == 'nt' else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([str(target)], cwd=str(target.parent), env=env, close_fds=True,
                     creationflags=flags, start_new_session=os.name != 'nt')


def cleanup():
    """Remove the executable left by the previous update (may still be closing: retried next start)."""
    if not FROZEN:
        return
    for leftover in ('.old', '.new'):
        try:
            executable().with_name(executable().name + leftover).unlink(missing_ok=True)
        except OSError:
            pass
