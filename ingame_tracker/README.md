# ootrTracker

> **Licence.** This folder is **GPL-3.0-or-later** ([LICENSE](LICENSE)); the rest of the OotrR repository is MIT. The module
> is built from sloperinaGZ's and ocarinaMIDI's GPL-3 code. The prebuilt binary the application ships,
> `src/oot_rando/resources/ingame_tracker/subsdk7`, is built from this folder (`SOURCE.md` there names the commit and the checksum).

An in-game tracker for the Ocarina of Time (Switch 2, program id `0400486024DEC000`) randomizer
[OotrR](https://github.com/Mozencaz/OotrR), whose repository this folder is part of. Press **R + right stick up** and a panel in the game's own style shows what the
save has found:

- the items (swords, shields, boots, bow, bombs, hookshot, magic, ocarina, bottles, stones, medallions), with the
  game's own icons, owned ones lit in their colour and with their level (Hookshot / Longshot, wallet sizes, ...),
  and a `?` on any the game has no flag for;
- the twelve ocarina songs under them, two rows of six (the warp songs, then the others), lit once learned;
- each dungeon's small keys found out of the total and its boss key, with the temple's medallion, the small key and
  the boss key as icons;
- the checks found, per region and in total, as `collected / trackable` (a check without a save flag can't be
  observed, so it isn't counted), and the enemy souls if the seed has them;
- each region's checks by name, ticked when collected, so you can see what's still missing there, with the highlighted
  check's internal key (the randomizer's id for it) under the list;
- **ticks by hand**: A on a check of a region's list ticks it as done, as a double click does in the desktop tracker; it
  counts as found, and the ticks are kept on the SD card for each seed;
- **show in the world**: Y on a check of a region's list marks where it is in the game, with a box and a beam over the
  picture and how far it is, or names the map it's in;
- the seed's id, a warning when the save isn't from this seed, and "Goal reached";
- a **postcard**: a small card with only the icons (items, songs, temples, dungeon keys) in a corner of the screen while you play;
- a **console** for Archipelago seeds: the items you receive and send, other players' items, hints, chat and the server's
  notices, as a few lines over the game, written there by OotrR's Archipelago client.

The postcard and the console hide while the game is paused, so its menus are clear, and come back when it plays again. The panel
works while the game is paused too.

Version 0.7.1. Tested in the game (1.1.1, in the Ryuchii emulator): the panel, icons, postcard and songs, and 0.5.0's console with two players. Other players' items (0.6.0), the Console page's rows (0.6.1), hiding while paused (0.6.2), reopening where it was closed (0.6.3) and show in the world (0.7.0) are **not yet tested in the game**, nor is game 1.0.0. See [docs/TESTING.md](docs/TESTING.md).

## Controls

| | |
|---|---|
| R + right stick up | open the panel where it was last closed (the same page and highlight), or close it |
| D-pad or left stick | move the highlight over the regions and the Settings entry after them; in a region's list, scroll (left and right: a page). Held, it repeats |
| A | open the highlighted region's list of checks, the Settings page or the page of the entry chosen on it; in a region's list, tick the highlighted check by hand, or untick it (a check the save shows collected stays as it is); on the console's page, tick or untick the kind of message chosen |
| Y | in a region's list, show the highlighted check in the world (Y on it again puts it away, Y on another check shows that one instead) |
| B | back a page (a list and the Settings page: to the regions), or close the panel |
| D-pad or left stick, on a settings page | up and down choose a setting, left and right change its value (on a kind of message, they or A tick or untick it) |

While the panel is open the game doesn't see R, the right stick (so the camera stays still), A, B, Y, the D-pad or the left
stick (Link stands still); while the combination is held, it doesn't see R or the right stick. A button still held when the
panel closes stays hidden from the game until it's let go, so closing with B doesn't also swing the sword. R + right stick
down is sloperinaGZ's menu and is left alone.

## Show in the world

In a region's list, two rows under the checks describe the highlighted one: its name with its internal key on the right
(`key KokiriForest#1234567`, the id the randomizer gives the check, which stays the same whatever name it is shown with), then
`Ticked by hand` if it is (below) and where it is: `Y: show in the world     12 m away, 3 m up`, `... In Kokiri Forest (child)`,
or why it can't be shown.

Y shows it. In the map the game is in, the check's place is drawn over the picture: a gold box a metre across round the
check's actor (its position is the box's base) and a beam 30 m up from it, in sloperinaGZ's line style (a soft glow under
each line). The lines are **not depth-tested**: they show through walls and the ground, so the check can be found from
anywhere in the map. With the panel closed, a band at the top of the screen (at the bottom while the console is at the top)
names the check and says how far it is from Link, how far up or down, and, when it is off the picture, which way to look
(`turn left`, `look up`, `behind you`). In another map, the band says which map it is in (`In Deku Tree`, `... and 1 other map`
when it is in several). The marker stays while you play, with the panel closed, until Y puts it away or another check is
shown; it is hidden while the game is paused.

Only the place is shown, never what the check holds: the seed's file has no items, only the vanilla scene data's positions.
A check with no place in the game's maps (an NPC's gift, an event) says `No place in the world for this check`; a seed made
before 0.7.0 says `This seed's file is too old to tick checks or show them: update its tracker with the game file` (OotrR's
"Update the in-game tracker" with the game file, or `update-tracker --nup GAME.nup`).

## Ticked by hand

In a region's list, A ticks the highlighted check by hand and A again unticks it, as a double click (or Space) does in the
randomizer's desktop tracker, which shows such a check as `Done (manual)`. A tick means done: the check counts as found in the
region's and the panel's counts, as the desktop tracker counts its manual ticks. Its box is a green outline over a fainter green
fill and its name a dimmer green, unlike a check the save shows collected (a filled green box), and the row under the list starts
with `Ticked by hand`. A check the save shows collected stays collected: A does nothing on it. A `?` check (one the game has no flag
for) can be ticked, and is then no longer counted as unreadable.

The ticks are kept for each seed on the SD card, in `ootrTracker/marks-<seed id>.cfg` (in an emulator,
`<user folder>/sdmc/ootrTracker/marks-<seed id>.cfg`), written when the list is left or the panel closed and read when the seed's
file is loaded. The game can't write its RomFS, where `seed.trk` is, so the file sits next to the postcard's and the console's
settings instead. The ticks are kept by the checks' ids, so updating the seed's tracker keeps them; a tick of an id the seed no
longer has is dropped. The file is text: `ootrTracker marks 1`, `seed <id>`, a `check <id>` line per tick, then an `end` line with
the count and a checksum. A save writes `marks-<seed id>.new` first, then the file, then deletes the copy, so a write cut off
leaves the ticks as they were before it. A damaged file, or one of another seed or version, is left out (no ticks); the file is at
most 32 KiB, and a tick that would make it larger is refused. A seed made before 0.7.0 has no ids, so nothing can be ticked.

The in-game ticks and the desktop tracker's are kept apart: the desktop tracker doesn't read this file, and the Archipelago client
sends the desktop tracker's manual ticks, not these.

## Settings

The last entry of the regions is **Settings**. A on it opens a page with two entries, **Postcard** and **Console**, each with
its On or Off; A on one opens its settings.

## The postcard

**Settings > Postcard**:

| Setting | Values | Default |
|---|---|---|
| Postcard | On, Off | Off |
| Position | Top left, Top right, Bottom left, Bottom right | Bottom right |
| Size | Small, Medium, Large | Small |
| Opacity | 25 %, 50 %, 75 %, 100 % | 50 % |

Left and right change the chosen setting at once, and while the settings are shown the card is drawn so you see what they do.
With the postcard on and the panel closed, the card is drawn in its corner every frame: the items' grid (with the stones and
medallions) and the songs under it, over the dungeons' keys (medallion, small keys found out of the total, boss key), with the same
icons and `?` marks as the panel and no text lists. It takes no input and the game keeps every button. The opacity is the whole card's, its box and its
icons. At 1080p the card is about 340 pixels wide when small, 470 medium and 620 large. While the game is paused the card
hides, and it comes back when the game plays again.

The settings are saved on the SD card, in `ootrTracker/postcard.cfg` (in an emulator, `<user folder>/sdmc/ootrTracker/postcard.cfg`),
when the settings are left or the panel is closed, and read when the seed's file is loaded at start. A missing or damaged file
means the defaults. If the SD card can't be mounted, the settings last until the game is closed.

## The console

**Settings > Console**:

| Setting | Values | Default |
|---|---|---|
| Console | On, Off | On for an Archipelago seed, Off for a local one |
| Position | Bottom centre, Top centre (wide); Left centre, Right centre (tall) | Bottom centre |
| Opacity | 25 %, 50 %, 75 %, 100 % | 75 % |
| Lines | 4, 6, 8, 12 | 6 |
| Fade | 5 s, 10 s, 30 s, Permanent | 10 s |
| Items received | ticked or not: shown or not | ticked |
| Items sent | ticked or not | ticked |
| Hints | ticked or not | ticked |
| Chat | ticked or not | ticked |
| Server notices | ticked or not | ticked |
| Other players' items | ticked or not | ticked |

The console shows the newest lines of the kinds ticked, oldest at the top, each in its kind's colour (gold received, green sent, blue
hints, white chat, grey notices, lavender other players' items: one player finding their own item, or sending one to a third); a
long line wraps over up to three rows. A line fades out after the Fade time; Permanent keeps the last lines. It is drawn whether
the panel is open or not, takes no input, and keeps clear of the postcard: next to it, narrower, or above or below it. While the
console's page is shown it is drawn whole as a preview, under the panel ("No messages yet" before the first line). While the
game is paused the console hides, as the postcard does, and comes back when it plays again; its page's preview still shows.
Console is kept apart for local and Archipelago seeds, so turning it on for one leaves the other's default.

Its lines come from OotrR's Archipelago client (the desktop application or `ap-client`), which finds the console's mailbox in
this module's memory while the game runs and writes the room's messages there, with the connection's state and a heartbeat
([the mailbox](../docs/ingame-tracker-format.md#the-consoles-mailbox)). A status line at the bottom says "Archipelago: connecting
to ...", "Archipelago: not connected", or, after 10 s without the client's heartbeat on an Archipelago seed, "Archipelago client not
running". The game's font has ASCII and Latin-1 letters; other characters show as `?`. The console keeps the last 32 lines; lines
sent while the game wasn't running aren't shown.

The settings are saved in `ootrTracker/console.cfg` next to the postcard's, when the console's page is left or the panel is closed.

## What it needs

The module is shipped by the randomizer: the application copies it into each seed it generates, as `exefs/subsdk7` next to the
seed's `romfs/RandoTracker/seed.trk` (the flags to watch, no item placements) and `icons.bin` (the items' and songs' icons, which
OotrR copies from the player's own game on their PC; without it the items show as letters). It is therefore only active
while that seed is enabled in the game's Properties > Add-Ons, and it does nothing if `seed.trk` is missing. To leave it
out, turn off "In-game tracker" in OotrR's install options (or pass `--no-ingame-tracker` to `ap-install`). OotrR's
"Update the in-game tracker" (or `update-tracker`, with `--nup GAME.nup` for the icons) puts a newer build in an
installed seed, with the songs' flags too (a seed made before 0.4.0 shows its songs as `?` until then, and as letters until
its icons are updated with `--nup`).

It reads the game's save data (GameData) in place and never writes to it or calls a game function. The only things it writes are its
own settings files on the SD card and its console's mailbox, in its own memory. It knows main's
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
  The console's mailbox is the module's own data; what the client writes there is checked (the sequence, lengths, kinds) before use.
- Game offsets live in `src/builds.c` only. A build not in it reads no memory.
- A flag the game doesn't have is unknown, never false.
- Every hook calls what its slot held before, unless the slot still points into main (lazy binding: never call main's PLT).
- Our own NVN calls go through `nvn_proc`, never through a function an add-on's hook handed out.
- The seed file's format is shared with the randomizer (`src/oot_rando/tracker/ingame_format.py`): change both, the format document and the
  tests' fixture together (`tests/fixtures/real-seed.trk` was produced by the randomizer's exporter). The same goes for the console's
  mailbox (`src/mailbox.h`, `src/oot_rando/archipelago/console_bridge.py`). The same goes for `icons.bin`
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
- The console's kinds of message, a check box each, follow sloperinaGZ's watch list (`src/ootgz/menus.c`, master 5b44a21).
- The game's pause, which hides the postcard and the console, is read as sloperinaGZ's `gd_game_paused` reads it
  (`src/ootgz/gamedata.c`, commit 8a2c73c).
- Show in the world is drawn the way sloperinaGZ draws its collision boxes (commit 8a2c73c): the camera's basis and
  projection (`view.c` from its `src/ootgz/view.c`), the cutting of a line at the near plane and to the picture (its
  `src/ootgz/airwall.c` `clip_near` and `clip_to_picture`), the soft line (`gpuui_line` and its profile, from its
  `src/ootgz/gpuui.c`) with a glow under it (`src/ootgz/overlayui.c`), the camera's and Link's offsets (`worldmark.c` and
  `builds.c`, from its `src/ootgz/link.c` and `src/ootgz/z64hd_builds.h`) and the String64 and pause reads (`gamedata.c`, from
  its `src/ootgz/gamedata.c`).
- `src/third_party` (see its README) holds [stb_truetype](https://github.com/nothings/stb) (public domain) and zstd's educational decoder
  (BSD or GPLv2, Meta Platforms), both as sloperinaGZ ships them.
- No game files are included. You need your own copy of the game; the module reads its font and shader from it at run time,
  and OotrR copies the icons from it into the seed on your PC.
