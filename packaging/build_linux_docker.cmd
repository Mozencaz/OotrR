@echo off
rem Builds the portable Linux application from Windows with Docker (no WSL setup needed):
rem dist\OoT-Randomizer-linux\OoT-Randomizer
rem Debian Bookworm image: glibc 2.36, so the binary runs on most current distributions.
setlocal
cd /d "%~dp0.."
docker run --rm -v "%cd%:/project" -w /project python:3.12-slim-bookworm bash -c ^
  "apt-get update -qq && apt-get install -y -qq --no-install-recommends libtk8.6 binutils >/dev/null && OOT_LINUX_VENV=/tmp/venv bash packaging/build_linux.sh" || exit /b 1
echo Application portable : dist\OoT-Randomizer-linux\OoT-Randomizer
