@echo off
rem Runs the application from the sources (development).
rem Portable build without Python: dist\OoT-Randomizer-windows\OoT-Randomizer.exe
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
python -m oot_rando
if errorlevel 1 pause
