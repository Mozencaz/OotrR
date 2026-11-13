# PyInstaller spec: one portable executable (Windows .exe or Linux binary).
# Build with packaging/build_windows.cmd or packaging/build_linux.sh.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / 'src'
PKG = SRC / 'oot_rando'

datas = [
    (str(PKG / 'logic' / 'world'), 'oot_rando/logic/world'),
    # Prebuilt in-game tracker module (GPL-3, with its licence and source link), copied into each seed.
    (str(PKG / 'resources' / 'ingame_tracker'), 'oot_rando/resources/ingame_tracker'),
    # Run by the external Python of HookshotBuilder to extract icons (by path).
    (str(PKG / 'tracker' / 'icon_extract.py'), 'oot_rando/tracker'),
    (str(ROOT / 'README.md'), '.'),
]
# Sources copied into the Archipelago .apworld (``python -m oot_rando apworld``).
sys.path.insert(0, str(SRC))
from oot_rando.archipelago.apworld_build import TEMPLATE, VENDORED  # noqa: E402
for _name in VENDORED + (TEMPLATE,):
    _parent = Path(_name).parent.as_posix()
    datas.append((str(PKG / _name), 'oot_rando' + ('' if _parent == '.' else '/' + _parent)))
datas += collect_data_files('ainb')
hiddenimports = (collect_submodules('oot_rando') + collect_submodules('ainb') + collect_submodules('evfl')
                 + collect_submodules('websockets'))

a = Analysis(
    [str(ROOT / 'packaging' / 'launcher.py')],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports + ['yaml'],
    excludes=['pytest', 'numpy', 'matplotlib'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OoT-Randomizer',
    console=False,          # graphical application; the CLI stays available from the sources
    upx=False,
    strip=False,
)
