"""Self-update from GitHub releases: version check, checksum, archive, in-place swap (no network)."""
import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from oot_rando import updater


def api(tag, *names, prerelease=False):
    return {'tag_name': tag, 'html_url': 'https://example.invalid/r', 'body': 'Notes', 'draft': False,
            'prerelease': prerelease,
            'assets': [{'name': n, 'browser_download_url': 'https://example.invalid/' + n} for n in names]}


class UpdaterTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(updater.parse_version('v0.10.2'), (0, 10, 2))
        self.assertEqual(updater.parse_version('1.2'), (1, 2, 0))
        self.assertIsNone(updater.parse_version('latest'))
        self.assertTrue(updater.is_newer('v0.4.0', '0.3.0'))
        self.assertTrue(updater.is_newer('0.10.0', '0.9.9'))
        self.assertFalse(updater.is_newer('v0.3.0', '0.3.0'))
        self.assertFalse(updater.is_newer('v0.2.9', '0.3.0'))

    def test_release_selection(self):
        names = ('OoT-Randomizer-0.4.0-windows-x64.zip', 'OoT-Randomizer-0.4.0-linux-x64.tar.gz', 'SHA256SUMS.txt')
        release = updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'win32')
        self.assertEqual((release.version, release.asset), ('0.4.0', names[0]))
        self.assertEqual(updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'linux').asset, names[1])
        self.assertIsNone(updater.release_from_json(api('v0.3.0', *names), '0.3.0', 'win32'))
        self.assertIsNone(updater.release_from_json(api('v0.4.0', *names, prerelease=True), '0.3.0', 'win32'))
        self.assertIsNone(updater.release_from_json(api('v0.4.0', names[0]), '0.3.0', 'win32'))   # no checksums
        self.assertIsNone(updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'darwin'))

    def test_checksums(self):
        sums = b'aa' * 32 + b'  a.zip\n' + b'BB' * 32 + b' *b.tar.gz\n'
        self.assertEqual(updater.expected_hash(sums, 'a.zip'), 'aa' * 32)
        self.assertEqual(updater.expected_hash(sums, 'b.tar.gz'), 'bb' * 32)
        with self.assertRaises(updater.UpdateError):
            updater.expected_hash(sums, 'c.zip')

    def test_extract(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as bundle:
            bundle.writestr('README.md', 'x')
            bundle.writestr('OoT-Randomizer.exe', b'MZ new')
        self.assertEqual(updater.extract_executable(buffer.getvalue(), 'a.zip', 'OoT-Randomizer.exe'), b'MZ new')
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as bundle:
            info = tarfile.TarInfo('OoT-Randomizer-linux/OoT-Randomizer')
            info.size = 5
            bundle.addfile(info, io.BytesIO(b'\x7fELF!'))
        self.assertEqual(updater.extract_executable(buffer.getvalue(), 'a.tar.gz', 'OoT-Randomizer'), b'\x7fELF!')
        with self.assertRaises(updater.UpdateError):
            updater.extract_executable(buffer.getvalue(), 'a.tar.gz', 'Other')

    def test_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'OoT-Randomizer.exe'
            target.write_bytes(b'old')
            updater.replace_executable(target, b'new')
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(target.with_name(target.name + '.old').read_bytes(), b'old')
            self.assertFalse(target.with_name(target.name + '.new').exists())
            updater.replace_executable(target, b'newer')   # a leftover .old is replaced
            self.assertEqual(target.with_name(target.name + '.old').read_bytes(), b'new')

    def test_install_needs_frozen_build(self):
        release = updater.Release('9.9.9', '', '', 'a.zip', 'u', 's')
        if not updater.can_self_update():
            with self.assertRaises(updater.UpdateError):
                updater.install(release)

    def test_install_rejects_bad_checksum(self):
        archive = b'archive'
        sums = ('00' * 32 + '  a.zip\n').encode()
        calls = iter([sums, archive])
        original = (updater._get, updater.can_self_update)
        updater._get = lambda *args, **kwargs: next(calls)
        updater.can_self_update = lambda: True
        try:
            with self.assertRaisesRegex(updater.UpdateError, 'checksum'):
                updater.install(updater.Release('9.9.9', '', '', 'a.zip', 'u', 's'))
        finally:
            updater._get, updater.can_self_update = original
        self.assertNotEqual(hashlib.sha256(archive).hexdigest(), '00' * 32)


if __name__ == '__main__':
    unittest.main()
