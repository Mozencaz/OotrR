"""Create the key pair that signs the releases (run once, by the project owner).

    python tools/make_update_key.py [--set-secret] [PRIVATE_KEY_FILE]

* writes the private key (PEM, Ed25519) to PRIVATE_KEY_FILE, by default
  ``~/.oot-randomizer/update_signing_key.pem`` (outside the repository); it is
  never printed and an existing file is never overwritten;
* writes the public key into ``src/oot_rando/update_key.py`` (committed: every
  build embeds it and refuses updates not signed by the private key);
* with ``--set-secret``, also stores the private key as the ``UPDATE_SIGNING_KEY``
  secret of the GitHub repository (``gh`` must be logged in). Otherwise, do it later
  with ``python tools/make_update_key.py --set-secret`` (the existing key is reused).

Keep a backup of the private key file: without it, no later release can update the
application. Needs ``openssl``: the one of Git for Windows is found by itself.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_MODULE = ROOT / 'src' / 'oot_rando' / 'update_key.py'
DEFAULT_KEY = Path.home() / '.oot-randomizer' / 'update_signing_key.pem'
SECRET = 'UPDATE_SIGNING_KEY'


def find_openssl():
    """openssl on the PATH, else the copy shipped with Git for Windows."""
    found = shutil.which('openssl')
    if found:
        return found
    candidates = []
    git = shutil.which('git')
    if git:
        base = Path(git).resolve().parent.parent          # ...\Git\cmd\git.exe -> ...\Git
        candidates += [base / 'usr' / 'bin' / 'openssl.exe', base / 'mingw64' / 'bin' / 'openssl.exe']
    for root in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                 os.environ.get('LOCALAPPDATA') and str(Path(os.environ['LOCALAPPDATA']) / 'Programs')):
        if root:
            candidates += [Path(root) / 'Git' / 'usr' / 'bin' / 'openssl.exe',
                           Path(root) / 'Git' / 'mingw64' / 'bin' / 'openssl.exe']
    for path in candidates:
        if path.is_file():
            return str(path)
    sys.exit('openssl not found: install Git for Windows (it ships one) or OpenSSL, then run again.')


def public_key(openssl, key_file):
    der = subprocess.run([openssl, 'pkey', '-in', str(key_file), '-pubout', '-outform', 'DER'],
                         check=True, capture_output=True).stdout
    return der[-32:].hex()


def write_public_key(public):
    text = KEY_MODULE.read_text(encoding='utf-8')
    text, count = re.subn(r"^PUBLIC_KEY = '[0-9a-f]*'$", f"PUBLIC_KEY = '{public}'", text, flags=re.M)
    if count != 1:
        sys.exit('PUBLIC_KEY line not found in ' + str(KEY_MODULE))
    KEY_MODULE.write_text(text, encoding='utf-8', newline='\n')


def set_secret(key_file):
    gh = shutil.which('gh')
    if not gh:
        sys.exit('GitHub CLI (gh) not found: install it, run "gh auth login", then run again with --set-secret.')
    # The key goes through stdin: never on the command line, nor printed.
    subprocess.run([gh, 'secret', 'set', SECRET], input=Path(key_file).read_bytes(), check=True, cwd=ROOT)
    print(f'GitHub secret {SECRET} set.')


def main(argv):
    args = [a for a in argv[1:] if a != '--set-secret']
    secret = '--set-secret' in argv[1:]
    target = Path(args[0]).expanduser() if args else DEFAULT_KEY
    if ROOT in target.resolve().parents:
        sys.exit('Keep the private key outside the repository.')
    openssl = find_openssl()
    if target.exists():
        if not secret:
            sys.exit(f'{target} already exists: not overwritten. Add --set-secret to store it on GitHub.')
        public = public_key(openssl, target)
        from_module = re.search(r"^PUBLIC_KEY = '([0-9a-f]*)'$", KEY_MODULE.read_text(encoding='utf-8'), re.M)
        if not from_module or from_module.group(1) != public:
            sys.exit(f'{target} does not match src/oot_rando/update_key.py: not stored on GitHub.')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([openssl, 'genpkey', '-algorithm', 'ed25519', '-out', str(target)], check=True)
        try:
            target.chmod(0o600)
        except OSError:
            pass
        public = public_key(openssl, target)
        write_public_key(public)
        print(f'Private key: {target} (back it up; never commit it)')
        print(f'Public key written to {KEY_MODULE.relative_to(ROOT)}: {public}')
    if secret:
        set_secret(target)
    else:
        print('Next: python tools/make_update_key.py --set-secret   (stores the key as the GitHub secret)')
    print('Then commit src/oot_rando/update_key.py.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
