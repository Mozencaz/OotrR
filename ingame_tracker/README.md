# ootrTracker

> **Licence.** This folder is **GPL-3.0-or-later** ([LICENSE](LICENSE)); the rest of the OotrR repository is MIT. The module
> is built from sloperinaGZ's and ocarinaMIDI's GPL-3 code. The prebuilt binary the application ships,
> `src/oot_rando/resources/ingame_tracker/subsdk7`, is built from this folder (`SOURCE.md` there names the commit and the checksum).

An in-game tracker for the Ocarina of Time (Switch 2, program id `0400486024DEC000`) randomizer
[OotrR](https://github.com/Mozencaz/OotrR), whose repository this folder is part of. Press **R + right stick up** and a panel in the game's own style shows what the
save has found:

- the items (swords, shields, boots, bow, bombs, hookshot, magic, ocarina, bottles, stones, medallions), with the
  game's own icons, owned ones lit in their colour and with their level (Hookshot / Longshot, wallet sizes, ...);
- each dungeon's small keys found out of the total and its boss key;
- the checks found, per region and in total, as `collected / trackable` (a check without a save flag can't be
  observed, so it isn't counted), and the enemy souls if the seed has them;
- each region's checks by name, ticked when collected, so you can see what's still missing there;
- the seed's id, a warning when the save isn't from this seed, and "Goal reached".

Version 0.2.0. **Not yet tested in the game**; see [docs/TESTING.md](docs/TESTING.md).

## Controls

| | |
|---|---|
| R + right stick up | open the panel, or close it |
| D-pad or left stick | move the highlight over the regions; in a region's list, scroll (left and right: a page). Held, it repeats |
| A | open the highlighted region's list of checks |
| B | back to the regions, or close the panel |

While the panel is open the game doesn't see R, the right stick (so the camera stays still), A, B, the D-pad or the left
stick (Link stands still); while the combination is held, it doesn't see R or the right stick. A button still held when the
panel closes stays hidden from the game until it's let go, so closing with B doesn't also swing the sword. R + right stick
down is sloperinaGZ's menu and is left alone.

## What it needs

The module is shipped by the randomizer: the application copies it into each seed it generates, as `exefs/subsdk7` next to the
seed's `romfs/RandoTracker/seed.trk` (the flags to watch, no item placements) and `icons.bin` (the items' icons, which
OotrR copies from the player's own game on their PC; without it the items show as letters). It is therefore only active
while that seed is enabled in the game's Properties > Add-Ons, and it does nothing if `seed.trk` is missing. To leave it
out, turn off "In-game tracker" in OotrR's install options (or pass `--no-ingame-tracker` to `ap-install`). OotrR's
"Update the in-game tracker" (or `update-tracker`, with `--nup GAME.nup` for the icons) puts a newer build in an
installed seed.

It reads the game's save data (GameData) in place and never writes to it or calls a game function. It knows main's
layout for the game builds 1.0.0 and 1.1.1; on another build the panel says "Game version not supported" and nothing
else is read. It draws with the game's own font and UI shader, read from the game's RomFS when the panel is first
opened (nothing of the game ships here), so the first opening pauses for a moment.

## Install by hand

- Emulator (Ryuchii, Eden, ...): `<user>/load/0400486024DEC000/<a folder>/exefs/subsdk7`, with
  `RandoTracker/seed.trk` (and `icons.bin`, if any) in that folder's `romfs`. The randomizer does this for you.
- Atmosphere: `atmosphere/contents/0400486024DEC000/exefs/subsdk7`, and `romfs/RandoTracker/seed.trk` next to it.

It uses the slot `subsdk7`, so it runs next to [sloperinaGZ](https://github.com/PracticeROM/sloperina) (`subsdk9`) and
[ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) (`subsdk8`); their hooks and ours call each other
(docs/DESIGN.md).

## Building

[docs/BUILDING.md](docs/BUILDING.md): devkitA64, then `make` in this folder. `make test` runs the PC tests, and `make ship` copies the
build to where the application reads it. The seed file's format is documented once, in OotrR's
[docs/ingame-tracker-format.md](../docs/ingame-tracker-format.md).

## Rules for changes

- Read only: never write the game's memory, never call a game function. Every pointer is checked with `sys_mapped` before it is read.
- Game offsets live in `src/builds.c` only. A build not in it reads no memory.
- A flag the game doesn't have is unknown, never false.
- Every hook calls what its slot held before, unless the slot still points into main (lazy binding: never call main's PLT).
- Our own NVN calls go through `nvn_proc`, never through a function an add-on's hook handed out.
- The seed file's format is shared with the randomizer (`src/oot_rando/tracker/ingame_format.py`): change both, the format document and the
  tests' fixture together (`tests/fixtures/real-seed.trk` was produced by the randomizer's exporter). The same goes for `icons.bin`
  (`ingame_icons.py`, `src/iconfile.c`).
- Files adapted from sloperinaGZ and ocarinaMIDI keep their provenance headers; when sloperinaGZ changes, port from its master and note the commit.

## Licence and credits

GPL-3.0-or-later ([LICENSE](LICENSE)); this folder only, the rest of the repository is MIT.

- The module is built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) (GPL-3), commit c599fa5: its plumbing
  (`crt0.S`, `got.c`, `sys.c`, `hooks.c`, `poll.c`, `nvn.c`, `slots.c`, `lib/module.ld`, the Makefile) and its drawing in the
  game's style (`gamefile.c`, `zstd.c`, `gamefont.c`, `uishader.c`, `gpuui.c`, and `uitext.c` after ocarinaMIDI's
  `gameui.c`). The icons' textures follow sloperinaGZ's later `gpuui.c` (master 5287f64: the game's packaged textures,
  its render-target layer). All of that comes from **sloperinaGZ** (GPL-3, master 8c3a940636; its contributors are in its
  CONTRIBUTORS.md), itself based on **gz**, glankk's practice ROM for Ocarina of Time (N64). The game's memory layout
  (`builds.c`, `gamedata.c`) is what sloperinaGZ's group found.
- The items' grid and the key labels follow the desktop tracker of the randomizer (`src/oot_rando/tracker/` in this repository, MIT).
- `src/third_party` (see its README) holds [stb_truetype](https://github.com/nothings/stb) (public domain) and zstd's educational decoder
  (BSD or GPLv2, Meta Platforms), both as sloperinaGZ ships them.
- No game files are included. You need your own copy of the game; the module reads its font and shader from it at run time,
  and OotrR copies the icons from it into the seed on your PC.
