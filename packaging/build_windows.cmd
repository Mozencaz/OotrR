@echo off
rem Builds the portable Windows application: dist\OoT-Randomizer-windows\OoT-Randomizer.exe
rem Uses an isolated environment in build\venv-windows (the system Python is not modified).
setlocal
cd /d "%~dp0.."
if not exist build\venv-windows\Scripts\python.exe (
    python -m venv build\venv-windows || exit /b 1
)
set PY=build\venv-windows\Scripts\python.exe
%PY% -m pip install --disable-pip-version-check -q -c packaging\constraints.txt -r requirements.txt PyYAML pyinstaller || exit /b 1
set VENDOR_7Z=src\oot_rando\midnas_devotion\vendor\7zip
if not exist "%VENDOR_7Z%\7z.exe" (
    if exist "%ProgramFiles%\7-Zip\7z.exe" if exist "%ProgramFiles%\7-Zip\7z.dll" (
        mkdir "%VENDOR_7Z%" 2>nul
        copy /y "%ProgramFiles%\7-Zip\7z.exe" "%VENDOR_7Z%\" >nul
        copy /y "%ProgramFiles%\7-Zip\7z.dll" "%VENDOR_7Z%\" >nul
        if exist "%ProgramFiles%\7-Zip\License.txt" copy /y "%ProgramFiles%\7-Zip\License.txt" "%VENDOR_7Z%\" >nul
        echo Bundled 7-Zip CLI from %ProgramFiles%\7-Zip
    ) else (
        echo Note: 7-Zip not found in %ProgramFiles%\7-Zip; Windows build will fall back to system 7-Zip/WinRAR or Windows 11 tar.exe.
    )
)
%PY% -m PyInstaller --noconfirm --clean --distpath dist\OoT-Randomizer-windows --workpath build\pyinstaller-windows packaging\oot_rando.spec || exit /b 1
copy /y README.md dist\OoT-Randomizer-windows\README.md >nul
copy /y src\oot_rando\logic\world\LICENSE-archipelago-oot.txt dist\OoT-Randomizer-windows\ >nul
echo.
echo Application portable : dist\OoT-Randomizer-windows\OoT-Randomizer.exe
