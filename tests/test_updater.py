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

# Test key and signatures made once with OpenSSL (openssl pkeyutl -sign -rawin).
TEST_KEY = bytes.fromhex('92c7a454efe68750bc79e1079c79b4724109d9cdeba49f0ff448dab06cea32b0')
GOOD_SUMS = (hashlib.sha256(b'archive').hexdigest() + '  a.zip\n').encode()
GOOD_SIG = bytes.fromhex('972742de69d9e600d60461d8bff52d12405a18c115b251a36fe767a1e2fdd6ab'
                         'eb26edb18616c0593153fa80f7cc05bfe1ad4b19b8c221556669852cc3eefe0b')
BAD_SUMS = ('00' * 32 + '  a.zip\n').encode()      # signed, but not the archive's hash
BAD_SIG = bytes.fromhex('b5ce71d96de9312b795e2c3878a0cdba1422967fd334f02091164ff164fc6555'
                        '54b2b9e55aea843f89a654fb4156fe21219e8c546957664a7cab40d982a0620b')
URL = updater.DOWNLOADS + 'v9.9.9/'


def api(tag, *names, prerelease=False, base=URL):
    return {'tag_name': tag, 'html_url': 'https://example.invalid/r', 'body': 'Notes', 'draft': False,
            'prerelease': prerelease,
            'assets': [{'name': n, 'browser_download_url': base + n} for n in names]}


def release():
    return updater.Release('9.9.9', '', '', 'a.zip', URL + 'a.zip', URL + 'SHA256SUMS.txt', URL + 'SHA256SUMS.txt.sig')


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
        names = ('OoT-Randomizer-0.4.0-windows-x64.zip', 'OoT-Randomizer-0.4.0-linux-x64.tar.gz', 'SHA256SUMS.txt',
                 'SHA256SUMS.txt.sig')
        release = updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'win32')
        self.assertEqual((release.version, release.asset), ('0.4.0', names[0]))
        self.assertEqual(release.page, updater.PAGES)   # https://example.invalid/r is not opened
        self.assertEqual(updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'linux').asset, names[1])
        self.assertIsNone(updater.release_from_json(api('v0.3.0', *names), '0.3.0', 'win32'))
        self.assertIsNone(updater.release_from_json(api('v0.4.0', *names, prerelease=True), '0.3.0', 'win32'))
        self.assertIsNone(updater.release_from_json(api('v0.4.0', names[0]), '0.3.0', 'win32'))   # no checksums
        self.assertIsNone(updater.release_from_json(api('v0.4.0', *names), '0.3.0', 'darwin'))
        self.assertIsNone(updater.release_from_json(api('v0.4.0', *names[:3]), '0.3.0', 'win32'))   # not signed
        # Downloads from anywhere but this repository's releases are ignored.
        for base in ('https://example.invalid/', 'https://github.com/Other/Repo/releases/download/v1/'):
            self.assertIsNone(updater.release_from_json(api('v0.4.0', *names, base=base), '0.3.0', 'win32'))

    def test_signature(self):
        self.assertTrue(updater.verify_signature(GOOD_SUMS, GOOD_SIG, TEST_KEY))
        import base64
        self.assertTrue(updater.verify_signature(GOOD_SUMS, base64.b64encode(GOOD_SIG) + b'\n', TEST_KEY))
        self.assertFalse(updater.verify_signature(GOOD_SUMS + b'x', GOOD_SIG, TEST_KEY))
        self.assertFalse(updater.verify_signature(GOOD_SUMS, BAD_SIG, TEST_KEY))
        self.assertFalse(updater.verify_signature(GOOD_SUMS, b'garbage', TEST_KEY))
        self.assertFalse(updater.verify_signature(GOOD_SUMS, GOOD_SIG, bytes(32)))

    def test_rfc8032_vector(self):
        from oot_rando.ed25519 import verify
        key = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
        sig = bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555'
                            'fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        self.assertTrue(verify(key, b'', sig))
        self.assertFalse(verify(key, b'x', sig))

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
        if not updater.can_self_update():
            with self.assertRaises(updater.UpdateError):
                updater.install(release())

    def install(self, sums, signature, archive=b'archive', target=None):
        calls = iter([sums, signature, archive])
        original = (updater._get, updater.can_self_update, updater.public_key)
        updater._get = lambda *args, **kwargs: next(calls)
        updater.can_self_update = lambda: True
        updater.public_key = lambda: TEST_KEY
        try:
            return updater.install(target or release())
        finally:
            updater._get, updater.can_self_update, updater.public_key = original

    def test_install_rejects_unsigned_or_bad_checksum(self):
        with self.assertRaisesRegex(updater.UpdateError, 'not signed'):
            self.install(GOOD_SUMS, BAD_SIG)
        with self.assertRaisesRegex(updater.UpdateError, 'checksum'):
            self.install(BAD_SUMS, BAD_SIG)            # signed, but the archive does not match
        with self.assertRaisesRegex(updater.UpdateError, 'not a valid archive'):
            self.install(GOOD_SUMS, GOOD_SIG)          # signed and matching: goes on to the archive
        foreign = updater.Release('9.9.9', '', '', 'a.zip', 'https://example.invalid/a.zip',
                                  URL + 'SHA256SUMS.txt', URL + 'SHA256SUMS.txt.sig')
        with self.assertRaisesRegex(updater.UpdateError, 'outside'):
            self.install(GOOD_SUMS, GOOD_SIG, target=foreign)

    def test_no_key_no_update(self):
        original = updater.public_key
        updater.public_key = lambda: None
        try:
            self.assertFalse(updater.can_self_update())
            self.assertFalse(updater.verify_signature(GOOD_SUMS, GOOD_SIG))
        finally:
            updater.public_key = original


if __name__ == '__main__':
    unittest.main()
