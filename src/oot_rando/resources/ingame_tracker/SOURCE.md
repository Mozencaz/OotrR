# The in-game tracker module (`subsdk7`)

`subsdk7` is a prebuilt Horizon module (NSO) for Ocarina of Time (Switch 2, program id 0400486024DEC000). The
application copies it into each seed it generates, as `exefs/subsdk7`, so the game loads it while that seed is enabled.
It draws the in-game randomizer tracker (R + right stick up) from `romfs/RandoTracker/seed.trk`.

It is **not** part of this application's MIT licence: it is free software under the GNU General Public License,
version 3 or later (the text is in `LICENSE` here), built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) and
[sloperinaGZ](https://github.com/PracticeROM/sloperina)'s GPL-3 code.

- Source: the `ingame_tracker/` folder of this repository (GPL-3, with its own `LICENSE`)
- Commit: `d403cc1` (module version 0.1.0; it was `565cb4e` in the repository the module lived in before)
- Built with devkitA64: `make PACKAGE_VERSION="0.1.0 (565cb4e)"` in `ingame_tracker/` (see its `docs/BUILDING.md`)
- sha256 of `subsdk7`: `054734cd8690585a1be78ac76296f9e33daeb94fd3b0ea559346a4faa3b70d8e` (66,723 bytes)

The source of this exact binary is that folder at the commit above. To change the module, change it there, run `make ship` in that
folder (it copies the new build here and prints its checksum and size), and update this file's commit and checksum (the tests check
that the checksum matches the binary).
