# The in-game tracker module (`subsdk7`)

`subsdk7` is a prebuilt Horizon module (NSO) for Ocarina of Time (Switch 2, program id 0400486024DEC000). The
application copies it into each seed it generates, as `exefs/subsdk7`, so the game loads it while that seed is enabled.
It draws the in-game randomizer tracker (R + right stick up) from `romfs/RandoTracker/seed.trk`.

It is **not** part of this application's MIT licence: it is free software under the GNU General Public License,
version 3 or later (the text is in `LICENSE` here), built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) and
[sloperinaGZ](https://github.com/PracticeROM/sloperina)'s GPL-3 code.

- Source: <https://github.com/waze3174/ootr-ingame-tracker>
- Commit: `565cb4e` (version 0.1.0)
- Built with devkitA64 (`make`, see the module's docs/BUILDING.md)
- sha256 of `subsdk7`: `054734cd8690585a1be78ac76296f9e33daeb94fd3b0ea559346a4faa3b70d8e` (66,723 bytes)

The source of this exact binary is the commit above in that repository. To change the module, change it there and copy the new
build and this file's commit and checksum here (the tests check that the checksum matches the binary).
