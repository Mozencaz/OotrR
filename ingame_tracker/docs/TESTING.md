# Live test plan

Nothing in 0.1.0 or 0.2.0 has run in the game. The PC tests (`make test`) cover the seed file's parser (versions 1 and 2), the state, a
region's list of checks, the game-data reader over a fake GameData, the controls (repeat, what the game doesn't see), the browsing and the
icons file's index.
These steps cover the rest. Back up the save first.

## Setup

1. Generate a seed with the randomizer (OotrR, with "In-game tracker" on) into the emulator's `load/0400486024DEC000`, enable it in the
   game's Properties > Add-Ons, and start a **new game** (the seed's marker is set by the new-game opening).
2. Keep the emulator's log open: the module's lines start `ootrTracker:`.

## 1. Does the seed file reach the module (RomFS visibility)

- Log, about 10 s after the game starts: `seed <id>: N regions, N checks, N items`. If it says `no content:/RandoTracker/seed.trk`, the
  RomFS layering doesn't show a new file: that is the first thing to settle (try the same seed in another emulator, or with Atmosphere).

## 2. Loading next to the other add-ons

Boot with the module alone, with sloperinaGZ, with ocarinaMIDI, and with all three. Each logs the hooks (`calls the sdk` or `calls another
module`), no `[rtld] Unresolved symbol`, and the other add-ons still work (sloperinaGZ's menu on R + right stick down, ocarinaMIDI's list on
R3 + D-pad).

## 3. The panel

- R + right stick up: the game may pause for a moment (it reads its font and shader), then the panel. The log says `panel: tracking` (or
  `waiting for the game's save data` on the title screen).
- In a new game of this seed: the header shows the seed's id and no warning. In a save started without the seed: "This save is not from
  this seed".
- The panel has the game's look (dark box, gold title), fits 1280x720 and 1920x1080, doesn't flicker and doesn't slow the game down.
- While it is open, R, the right stick, A, B, the D-pad and the left stick do nothing in the game (the camera and Link stay still).
- B closes it and doesn't act in the game (no sword swing, even if B is held a moment after closing).
- R + right stick up again closes it. Opening and closing ten times in a row works.

## 3b. Browsing the regions

- The D-pad and the left stick move the gold highlight over the regions: down a column, then the next; left and right across columns.
  Held, it repeats after a moment.
- A on a region shows its checks with their names, as the desktop tracker names them. Collected ones have a filled green box, missing ones
  an empty white box. A large region (Kokiri Forest, 90 checks) scrolls with up and down, a page at a time with left and right; the
  heading's `N-M of T` follows.
- Pick up a check of the open list: its box fills within half a second.
- B goes back to the regions, with the same region highlighted; B again closes the panel.

## 3c. The items' icons

With a seed this version made from your game (or one updated with `update-tracker --nup GAME.nup`), so it has
`romfs/RandoTracker/icons.bin`:

- Log, at the first opening: `gpu drawing: icon atlas 384x320 (N KiB), N KiB for a picture while they go in`, then, about a second later,
  `gpu drawing: the icons are in; the pictures' N KiB go back`, and no `didn't go in` line.
- The cells' letters give way to the items' icons over that second (one every other frame), with no hitch.
- The icons are upright, in their own colours (as on the game's pause screen: not washed out, not too dark), smooth (no jagged edges or
  shimmer: each is shrunk from up to 683 pixels), centred in their cells; owned ones bright, missing and unknown ones dim.
- Opening and closing the panel while the icons go in, and ten times after, works.
- Rename `icons.bin` and start the game again: the log says `no content:/RandoTracker/icons.bin: the items show as their letters` and the
  cells show their letters. Rename it back.

## 4. What it shows

Pick up things and compare with the desktop tracker (Real time mode) on the same save:

- an item (a sword, a shield, a bomb bag at two levels): its cell lights with its level, within half a second of the pickup;
- a check with a Bool flag (a chest) and one with a Bool64bitKey (a Gold Skulltula, a placed rupee): the region's count goes up;
- a dungeon's small keys found and held, a key ring, the boss key;
- the goal flag, if the seed has one: "Goal reached".

Count the checks: the panel's total is the desktop tracker's "automatic" count. The two differ if the Bool64bitKey reading is wrong: a seed
appends about 300 records after the sorted ones, and the panel's `unreadable` figure should be 0 once a save is loaded.

## 5. Other game versions

On 1.0.0 the Bool64bitKey entry is unverified: an `unreadable` count equal to the Bool64bitKey checks (289 in the test seed) means it wasn't
found. On any other build the panel must say "Game version not supported", and the log `this game build is not known`.
