@echo off
rem Builds the portable Windows application: dist\OoT-Randomizer-windows\OoT-Randomizer.exe
rem Uses an isolated environment in build\venv-windows (the system Python is not modified).
setlocal
cd /d "%~dp0.."
if not exist build\venv-windows\Scripts\python.exe (
    python -m venv build\venv-windows || exit /b 1
)
set PY=build\venv-windows\Scripts\python.exe
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt PyYAML "pyinstaller>=6.10,<7" || exit /b 1
%PY% -m PyInstaller --noconfirm --clean --distpath dist\OoT-Randomizer-windows --workpath build\pyinstaller-windows packaging\oot_rando.spec || exit /b 1
copy /y README.md dist\OoT-Randomizer-windows\README.md >nul
copy /y src\oot_rando\logic\world\LICENSE-archipelago-oot.txt dist\OoT-Randomizer-windows\ >nul
echo.
echo Application portable : dist\OoT-Randomizer-windows\OoT-Randomizer.exe
