"""requirements.txt (running from the sources) and pyproject.toml (pip install) declare the same packages."""
import _src_path  # noqa: F401
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _requirements(lines):
    found = {}
    for line in lines:
        line = line.split('#', 1)[0].strip()
        if line:
            name = re.match(r'[A-Za-z0-9_.-]+', line).group(0)
            found[name.lower()] = line[len(name):].replace(' ', '')
    return found


class DependencyTest(unittest.TestCase):
    def test_requirements_match_pyproject(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        declared = _requirements(project['dependencies'] + project['optional-dependencies']['overlay'])
        listed = _requirements((ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines())
        self.assertEqual(listed, declared)

    def test_every_package_is_pinned_for_the_builds(self):
        listed = _requirements((ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines())
        pinned = _requirements((ROOT / 'packaging' / 'constraints.txt').read_text(encoding='utf-8').splitlines())
        self.assertEqual(sorted(set(listed) - set(pinned)), [])

    def test_version_has_one_source(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertNotIn('version', project['project'])
        self.assertEqual(project['tool']['setuptools']['dynamic']['version'], {'attr': 'oot_rando.__version__'})


if __name__ == '__main__':
    unittest.main()
