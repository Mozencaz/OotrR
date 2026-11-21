# The in-game tracker module (`subsdk7`)

`subsdk7` is a prebuilt Horizon module (NSO) for Ocarina of Time (Switch 2, program id 0400486024DEC000). The
application copies it into each seed it generates, as `exefs/subsdk7`, so the game loads it while that seed is enabled.
It draws the in-game randomizer tracker (R + right stick up) from `romfs/RandoTracker/seed.trk`, its postcard (a small card with the icons, the songs included, in a corner of the screen) and its console (Archipelago messages over the game, other players' items included, which the application's Archipelago client writes into the module's memory), whose settings it keeps in `ootrTracker/postcard.cfg` and `ootrTracker/console.cfg` on the SD card.

It is **not** part of this application's MIT licence: it is free software under the GNU General Public License,
version 3 or later (the text is in `LICENSE` here), built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) and
[sloperinaGZ](https://github.com/PracticeROM/sloperina)'s GPL-3 code.

- Source: the `ingame_tracker/` folder of this repository (GPL-3, with its own `LICENSE`)
- Commit: `dcc4734` of [waze3174/OotrR](https://github.com/waze3174/OotrR), where the module was built (version 0.7.2);
  the sources in `ingame_tracker/` here are the same as there
- Built with devkitA64: `make ship` in `ingame_tracker/` at that commit (it embeds `0.7.2 (v0.7.4-27-gdcc4734)`); the build is
  the same from any folder, so `make PACKAGE_VERSION="0.7.2 (v0.7.4-27-gdcc4734)"` there gives this binary again
- sha256 of `subsdk7`: `c4c6fe1b2395ba2d8b823fdb5480bc4e866964b44e295f9f36697f01763d47de` (110,355 bytes)

The source of this exact binary is that folder at the commit above. To change the module, change it there, run `make ship` in that
folder (it copies the new build here and prints its checksum and size), and update this file's commit and checksum (the tests check
that the checksum matches the binary).
