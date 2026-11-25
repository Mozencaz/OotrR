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
    # Title screen badge image (patching/title_badge.py).
    (str(PKG / 'patching' / 'title_badge.rgba.zlib'), 'oot_rando/patching'),
    (str(PKG / 'patching' / 'source_textures'), 'oot_rando/patching/source_textures'),
    # Icon extraction: in process (Pillow and texture2ddecoder are bundled), or by path with
    # HookshotBuilder's Python.
    (str(PKG / 'tracker' / 'icon_extract.py'), 'oot_rando/tracker'),
    (str(ROOT / 'README.md'), '.'),
    (str(PKG / 'midnas_devotion' / 'assets'), 'oot_rando/midnas_devotion/assets'),
    (str(PKG / 'gui' / 'icons'), 'oot_rando/gui/icons'),
]
# Bundle 7-Zip CLI (7z.exe + 7z.dll) on Windows for zero-install .7z / .rar extraction.
_vendor_7z = PKG / 'midnas_devotion' / 'vendor' / '7zip'
if sys.platform == 'win32':
    _7z_search = [
        _vendor_7z,
        Path('C:/Program Files/7-Zip'),
        Path('C:/Program Files (x86)/7-Zip'),
    ]
    for _zdir in _7z_search:
        if (_zdir / '7z.exe').is_file() and (_zdir / '7z.dll').is_file():
            datas.append((str(_zdir / '7z.exe'), 'oot_rando/midnas_devotion/vendor/7zip'))
            datas.append((str(_zdir / '7z.dll'), 'oot_rando/midnas_devotion/vendor/7zip'))
            if (_zdir / 'License.txt').is_file():
                datas.append((str(_zdir / 'License.txt'), 'oot_rando/midnas_devotion/vendor/7zip'))
            break
# Sources copied into the Archipelago .apworld (``python -m oot_rando apworld``).
sys.path.insert(0, str(SRC))
from oot_rando.archipelago.apworld_build import TEMPLATE, VENDORED  # noqa: E402
for _name in VENDORED + (TEMPLATE,):
    _parent = Path(_name).parent.as_posix()
    datas.append((str(PKG / _name), 'oot_rando' + ('' if _parent == '.' else '/' + _parent)))
datas += collect_data_files('ainb')
datas += collect_data_files('certifi')
hiddenimports = (collect_submodules('oot_rando') + collect_submodules('ainb') + collect_submodules('evfl')
                 + collect_submodules('websockets') + collect_submodules('oead') + collect_submodules('restbl') + collect_submodules('byml'))

a = Analysis(
    [str(ROOT / 'packaging' / 'launcher.py')],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports + ['yaml', 'PIL.Image', 'PIL.ImageTk', 'texture2ddecoder'],
    excludes=['pytest', 'numpy', 'matplotlib', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.Qt3DCore'],
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
