"""Application version numbers: parsing and semver order (pre-releases before their release)."""
import re

from oot_rando import __version__


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
