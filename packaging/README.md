# Portable applications

One executable per system, no installation or Python needed:

| System | Build | Output |
|---|---|---|
| Windows 10/11 x64 | `packaging\build_windows.cmd` | `dist\OoT-Randomizer-windows\OoT-Randomizer.exe` |
| Linux x64 (glibc ≥ 2.36: Debian 12, Ubuntu 22.04+, Fedora 37+…) | `packaging\build_linux_docker.cmd` (from Windows, Docker) or `packaging/build_linux.sh` (on Linux) | `dist/OoT-Randomizer-linux/OoT-Randomizer` |

Both builds use PyInstaller in an isolated environment (`build/venv-windows`, or
a `python:3.12-slim-bookworm` container), with `packaging/oot_rando.spec`. The
logic world (`logic/world/`) is bundled.

## Usage

- Copy the executable anywhere and run it. It creates `data/` next to itself:
  seeds (`data/seeds`), application state (`data/app`), tracking, icons.
- Linux: `chmod +x OoT-Randomizer` if needed. A graphical desktop (X11 or
  XWayland) with at least one installed font is required (any desktop has one).
- A start-up error is written to `data/error.log` (the application has no console).
- The in-game overlay, turbo A and live memory reading only exist on Windows
  (Hookshot); everything else works on Linux.

## Checking a build

```
OoT-Randomizer selftest                            # modules + logic
OoT-Randomizer selftest GAME.nup NEW_FOLDER        # + generation and replay of a seed
```

The report is written to `data/selftest.json`. The same seed (same name, same
settings) produces byte-identical files on Windows, on Linux and from the sources.

## GitHub Actions

| Workflow | Trigger | Role |
|---|---|---|
| `CI` (`.github/workflows/ci.yml`) | every push (all branches), pull requests | unit tests on Windows + Linux, builds of both applications, `selftest` of each executable; builds downloadable for 14 days (run artifacts) |
| `Tag` (`tag.yml`) | manual (Actions tab → Run workflow, pick the branch) | creates the annotated tag `vX.Y.Z` on the head of the branch |
| `Release` (`release.yml`) | manual | tests + builds, then tag `vX.Y.Z` and a GitHub release with `OoT-Randomizer-X.Y.Z-windows-x64.zip`, `OoT-Randomizer-X.Y.Z-linux-x64.tar.gz` and `SHA256SUMS.txt` |

An empty version means the one in `pyproject.toml`. Any other version must
equal it, and `pyproject.toml` must equal `oot_rando/__init__.py`: the release
fails otherwise (the in-app updater compares `__version__` with the tag). An existing tag makes `Tag` and `Release` fail before
any build. The release Linux binary is built on Ubuntu 22.04 (glibc ≥ 2.35).
