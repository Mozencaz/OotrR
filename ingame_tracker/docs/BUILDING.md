# Building

- [devkitA64](https://devkitpro.org/wiki/Getting_Started), with `DEVKITPRO` set: devkitPro's MSYS2 shell sets it (`/opt/devkitpro`).
- Python 3 for `make test`, and a C compiler for the PC for its tests (`$CC`, or `cc`, `gcc` or `clang` on the PATH, or LLVM in its
  default place on Windows); without one they are skipped.

```
make            # bin/subsdk7
make dist       # dist/emulator/load/0400486024DEC000/ootrTracker/exefs/subsdk7, dist/atmosphere/contents/0400486024DEC000/exefs/subsdk7
make test       # the PC tests: the seed file's parser, the tracker, the game-data reader, the controls
make clean
```

On Windows without the MSYS2 shell open:

```
C:\devkitPro\msys2\usr\bin\bash.exe -lc "cd /c/path/to/OotrR/ingame_tracker && make"
```

The link step fails if the module needs a symbol that's neither defined nor in `lib/imports.txt` (the imports sloperinaGZ has used on this
game, and a few libc functions, checked in the game's sdk). `readelf -r bin/ootrTracker.elf | grep JUMP_SLOT` must print nothing: a
JUMP_SLOT would be an import bound lazily inside this module.

The application ships a copy of `bin/subsdk7`, in this repository at `src/oot_rando/resources/ingame_tracker/subsdk7`. After a change,
commit it, then run `make ship` (it builds, copies the binary there and prints its sha256 and size), update that folder's `SOURCE.md`
with the commit that holds the change and the printed values, and commit them (the application's tests check the checksum).

The build embeds `PACKAGE_VERSION`, by default the version in `VERSION` and `git describe` of the repository (it appears in the log's
`loaded ...` line). The shipped 0.1.0 binary was built with `make PACKAGE_VERSION="0.1.0 (565cb4e)"`; the same flag rebuilds it
byte for byte, provided the sources are unchanged and the build path is the one named below.

## Checking a build loads

In the emulator's log, at boot:

```
ootrTracker: game build:
ootrTracker: 1.1.1
ootrTracker: loaded 0.1.0 (...); controller hooks go in at the game's first controller setup
ootrTracker: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...
...
ootrTracker: counting frames from reads of controller style 0, NpadIdType 0x0
ootrTracker: seed 76069ecc4740cec6: 35 regions, 840 checks, 44 items      (10 s after the first frame)
```

"calls another module" instead of "calls the sdk" means another add-on hooked that import first and ours wraps it.
`no content:/RandoTracker/seed.trk: the tracker stays off` means the seed folder has no data file (an older seed) or the RomFS doesn't show it.
