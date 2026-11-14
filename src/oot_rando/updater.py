"""Self-update of the portable application from the GitHub releases.

* :func:`latest_release` asks the GitHub API for the latest published release
  (drafts and pre-releases excluded) and returns it when it is newer than this build.
  With ``experimental=True`` (the player's opt-in), pre-releases (``v1.2.0-beta.1``)
  count too: the newest of the recent releases is offered, stable or not.
* :func:`install` downloads the archive of this system, checks the signature of
  the release's ``SHA256SUMS.txt`` (``SHA256SUMS.txt.sig``, Ed25519, public key in
  :mod:`oot_rando.update_key`: a release cannot be replaced without the project's
  private key), checks the archive against it, then swaps the executable in place: the running
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
RECENT = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=30'   # newest first, pre-releases included
# Every download comes from this repository's releases, whatever the API answer says.
DOWNLOADS = f'https://github.com/{REPOSITORY}/releases/download/'
SUMS, SIGNATURE = 'SHA256SUMS.txt', 'SHA256SUMS.txt.sig'
PAGES = f'https://github.com/{REPOSITORY}/releases/'
USER_AGENT = 'OoT-Randomizer-updater'
CA_FILES = ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt',
            '/etc/ssl/ca-bundle.pem', '/etc/ssl/cert.pem')
MAX_ARCHIVE = 512 << 20
MAX_EXECUTABLE = 1 << 30      # uncompressed size of the executable inside the archive


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
    signature_url: str


def parse_version(text):
    """(major, minor, patch) of 'v1.2.3' / '1.2' / '1.2.3-beta'; None if not a version."""
    match = re.match(r'v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', (text or '').strip())
    return tuple(int(part or 0) for part in match.groups()) if match else None


def is_prerelease(text):
    """Whether a version has a pre-release suffix ('1.2.0-beta.1')."""
    return bool(re.match(r'v?\d+(?:\.\d+){0,2}-\S', (text or '').strip()))


def version_key(text):
    """Sort key of a version, pre-releases before their release (semver):
    1.2.0-alpha < 1.2.0-beta.1 < 1.2.0-beta.2 < 1.2.0-rc.1 < 1.2.0 < 1.2.1-beta.1. None if not a version."""
    core = parse_version(text)
    if core is None:
        return None
    match = re.match(r'v?\d+(?:\.\d+){0,2}-([0-9A-Za-z.-]+)', text.strip())
    if not match:
        return core, 1, ()
    parts = tuple((0, int(part), '') if part.isdigit() else (1, 0, part.lower())
                  for part in match.group(1).split('.') if part)
    return core, 0, parts


def is_newer(candidate, current=__version__):
    new, old = version_key(candidate), version_key(current)
    return bool(new and old and new > old)


def asset_suffix(platform=sys.platform):
    if platform.startswith('win'):
        return '-windows-x64.zip'
    if platform.startswith('linux'):
        return '-linux-x64.tar.gz'
    return None


def executable():
    return Path(sys.executable).resolve()


def public_key():
    """Release signing key of this build (32 bytes), or None."""
    from oot_rando.update_key import PUBLIC_KEY
    try:
        key = bytes.fromhex(PUBLIC_KEY)
    except ValueError:
        return None
    return key if len(key) == 32 else None


def can_self_update():
    return FROZEN and asset_suffix() is not None and public_key() is not None


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


def release_from_json(value, current=__version__, platform=sys.platform, experimental=False):
    """The release described by a GitHub API answer if it is newer and has this system's archive.
    Pre-releases only count with ``experimental``."""
    if not isinstance(value, dict) or value.get('draft'):
        return None
    if (value.get('prerelease') or is_prerelease(str(value.get('tag_name') or ''))) and not experimental:
        return None
    version = str(value.get('tag_name') or '').lstrip('v')
    suffix = asset_suffix(platform)
    if not suffix or not is_newer(version, current):
        return None
    assets = {a.get('name'): a.get('browser_download_url') for a in value.get('assets') or [] if isinstance(a, dict)}
    archive = next((name for name in assets if name and name.endswith(suffix)), None)
    if not archive or not assets.get(SUMS) or not assets.get(SIGNATURE):
        return None
    if any(not str(assets[name]).startswith(DOWNLOADS) for name in (archive, SUMS, SIGNATURE)):
        return None
    page = str(value.get('html_url') or '')
    if not page.startswith(PAGES):
        page = PAGES   # the browser only ever opens this repository's release pages
    return Release(version, page, str(value.get('body') or ''),
                   archive, assets[archive], assets[SUMS], assets[SIGNATURE])


def newest_release(values, current=__version__, platform=sys.platform, experimental=False):
    """The newest usable release of a GitHub API release list, or None."""
    found = [r for r in (release_from_json(v, current, platform, experimental)
                         for v in (values if isinstance(values, list) else [])) if r]
    return max(found, key=lambda r: version_key(r.version), default=None)


def latest_release(timeout=8, experimental=False):
    """The latest GitHub release when newer than this build, else None.
    ``experimental``: pre-releases count too (the newest of the recent releases)."""
    try:
        value = json.loads(_get(RECENT if experimental else LATEST, timeout,
                                'application/vnd.github+json', 4 << 20 if experimental else 1 << 20))
    except ValueError:
        raise UpdateError('Unexpected answer from GitHub.') from None
    if experimental:
        return newest_release(value, experimental=True)
    return release_from_json(value)


def expected_hash(sums, name):
    for line in sums.decode('utf-8', 'replace').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip('*') == name and re.fullmatch(r'[0-9a-fA-F]{64}', parts[0]):
            return parts[0].lower()
    raise UpdateError(f'{name} is not listed in SHA256SUMS.txt.')


def verify_signature(sums, signature, key=None):
    """Whether ``signature`` (raw 64 bytes, or base64) signs ``sums`` with the release key."""
    import base64
    import binascii
    from oot_rando.ed25519 import verify
    key = key if key is not None else public_key()
    if key is None:
        return False
    if len(signature) != 64:
        try:
            signature = base64.b64decode(signature.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
    return verify(key, sums, signature)


def extract_executable(archive, name, exe_name):
    """Bytes of the executable inside a release archive (any folder level)."""
    try:
        return _extract(archive, name, exe_name)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as error:
        raise UpdateError(f'{name} is not a valid archive: {error}') from None


def _extract(archive, name, exe_name):
    if name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            member = next((m for m in bundle.infolist()
                           if m.filename.replace('\\', '/').rsplit('/', 1)[-1] == exe_name), None)
            if member:
                if member.file_size > MAX_EXECUTABLE:
                    raise UpdateError(f'{exe_name} is unexpectedly large.')
                return bundle.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
            member = next((m for m in bundle.getmembers() if m.isfile() and m.name.rsplit('/', 1)[-1] == exe_name), None)
            if member:
                if member.size > MAX_EXECUTABLE:
                    raise UpdateError(f'{exe_name} is unexpectedly large.')
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
    for url in (release.asset_url, release.sums_url, release.signature_url):
        if not url.startswith(DOWNLOADS):
            raise UpdateError("Download outside the project's releases refused.")
    target = executable()
    report(f'Downloading version {release.version}…')
    sums = _get(release.sums_url, 30, limit=1 << 16)
    signature = _get(release.signature_url, 30, limit=1 << 10)
    if not verify_signature(sums, signature):
        raise UpdateError('The release is not signed by the project. Nothing was changed.')
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
