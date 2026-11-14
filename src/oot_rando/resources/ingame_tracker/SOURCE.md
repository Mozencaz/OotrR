# The in-game tracker module (`subsdk7`)

`subsdk7` is a prebuilt Horizon module (NSO) for Ocarina of Time (Switch 2, program id 0400486024DEC000). The
application copies it into each seed it generates, as `exefs/subsdk7`, so the game loads it while that seed is enabled.
It draws the in-game randomizer tracker (R + right stick up) from `romfs/RandoTracker/seed.trk`.

It is **not** part of this application's MIT licence: it is free software under the GNU General Public License,
version 3 or later (the text is in `LICENSE` here), built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) and
[sloperinaGZ](https://github.com/PracticeROM/sloperina)'s GPL-3 code.

- Source: the `ingame_tracker/` folder of this repository (GPL-3, with its own `LICENSE`)
- Commit: `5913044` (module version 0.2.0)
- Built with devkitA64: `make ship` in `ingame_tracker/` at that commit (it embeds `0.2.0 (v0.5.1-11-g5913044)`); the build is
  the same from any folder, so `make PACKAGE_VERSION="0.2.0 (v0.5.1-11-g5913044)"` there gives this binary again
- sha256 of `subsdk7`: `e51bbd7e74a28eb7e73765044ae6466eb29c83859b396e839c2ea726a0de0501` (75,825 bytes)

The source of this exact binary is that folder at the commit above. To change the module, change it there, run `make ship` in that
folder (it copies the new build here and prints its checksum and size), and update this file's commit and checksum (the tests check
that the checksum matches the binary).
