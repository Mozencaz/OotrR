#!/usr/bin/env bash
# Builds the portable Linux application: dist/OoT-Randomizer-linux/OoT-Randomizer
# Run on Linux (or WSL). Needs python3 (>= 3.11) with venv and tkinter
# (Debian/Ubuntu: sudo apt install python3-venv python3-tk).
# The build happens in a copy under /tmp when the project sits on a Windows
# drive (/mnt/...), which is much faster than building in place.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT"
if [[ "$ROOT" == /mnt/* ]]; then
    WORK="$(mktemp -d)/oot-randomizer"
    mkdir -p "$WORK"
    cp -r "$ROOT/src" "$ROOT/packaging" "$ROOT/README.md" "$ROOT/requirements.txt" "$WORK/"
fi
cd "$WORK"
VENV="${OOT_LINUX_VENV:-$HOME/.cache/oot-randomizer/venv-linux}"
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r requirements.txt PyYAML "pyinstaller>=6.10,<7"
"$VENV/bin/python" -c "import tkinter" || { echo "tkinter manquant : sudo apt install python3-tk"; exit 1; }
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --distpath "$WORK/dist/OoT-Randomizer-linux" \
    --workpath "$WORK/build/pyinstaller-linux" packaging/oot_rando.spec
OUT="$ROOT/dist/OoT-Randomizer-linux"
mkdir -p "$OUT"
if [[ "$WORK" != "$ROOT" ]]; then
    cp "$WORK/dist/OoT-Randomizer-linux/OoT-Randomizer" "$OUT/"
fi
cp "$ROOT/README.md" "$ROOT/src/oot_rando/logic/world/LICENSE-archipelago-oot.txt" "$OUT/"
chmod +x "$OUT/OoT-Randomizer"
echo "Application portable : $OUT/OoT-Randomizer"
