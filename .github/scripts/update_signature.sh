#!/usr/bin/env bash
# Release signature of SHA256SUMS.txt (Ed25519), checked by the application's updater.
#   update_signature.sh check          the UPDATE_SIGNING_KEY secret exists and matches
#                                      src/oot_rando/update_key.py (run before tagging)
#   update_signature.sh sign FILE      writes FILE.sig and checks it with the application's code
# The private key (PEM) comes from the UPDATE_SIGNING_KEY environment variable only and
# is written to a private temporary file removed on exit. See tools/make_update_key.py.
set -euo pipefail

mode="${1:-}"
if [[ -z "${UPDATE_SIGNING_KEY:-}" ]]; then
  echo "::error::The UPDATE_SIGNING_KEY secret is missing: run tools/make_update_key.py, then add the secret." >&2
  exit 1
fi
umask 077
key_file="$(mktemp)"
trap 'rm -f "$key_file"' EXIT
printf '%s\n' "$UPDATE_SIGNING_KEY" > "$key_file"

expected="$(python3 -c 'import sys; sys.path.insert(0, "src"); from oot_rando.update_key import PUBLIC_KEY; print(PUBLIC_KEY)')"
actual="$(openssl pkey -in "$key_file" -pubout -outform DER | tail -c 32 | od -An -v -tx1 | tr -d ' \n')"
if [[ -z "$expected" || "$actual" != "$expected" ]]; then
  echo "::error::UPDATE_SIGNING_KEY does not match the public key of src/oot_rando/update_key.py." >&2
  exit 1
fi

case "$mode" in
  check)
    echo "Update signing key OK ($expected)."
    ;;
  sign)
    file="${2:?file to sign}"
    openssl pkeyutl -sign -inkey "$key_file" -rawin -in "$file" -out "$file.sig"
    python3 - "$file" <<'EOF'
import sys
sys.path.insert(0, 'src')
from pathlib import Path
from oot_rando.updater import verify_signature
path = Path(sys.argv[1])
if not verify_signature(path.read_bytes(), path.with_name(path.name + '.sig').read_bytes()):
    sys.exit('The signature does not verify with the application\'s key.')
print('Signed and verified:', path.name + '.sig')
EOF
    ;;
  *)
    echo "usage: $0 check | sign FILE" >&2
    exit 2
    ;;
esac
