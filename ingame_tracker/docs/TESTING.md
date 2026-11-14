# Live test plan

0.2.0's icons were seen in the game (13/11: upright, right colours, smooth); 0.2.1 to 0.4.0 (key rows, postcard, songs) were checked in the game on 1.1.1 in the Ryuchii emulator (14/11). Game 1.0.0 is untested. The PC tests (`make test`) cover the seed file's parser (versions 1 and 2), the state, a
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

- Log, at the first opening: `gpu drawing: icon atlas 512x448 (N KiB), 688 KiB for a picture while they go in` (N about 1792), then, about a second later,
  `gpu drawing: the icons are in; the pictures' N KiB go back`, and no `didn't go in` line.
- The cells' letters give way to the items' icons over that second (one every other frame), with no hitch.
- The icons are upright, in their own colours (as on the game's pause screen: not washed out, not too dark), smooth (no jagged edges or
  shimmer: each is shrunk from up to 683 pixels), centred in their cells; owned ones bright, missing and unknown ones dim.
- Opening and closing the panel while the icons go in, and ten times after, works.
- The grid's bottom row shows the three stones and six medallions as pictures (the file select's), owned ones on their coloured cell.
- The keys row: each temple's medallion icon, then the small key's icon with `found/total`, then the boss key's icon, dim until you hold
  it. BW, GTG and GC keep their letters. All eight fit on one line at 720p and 1080p.
- No cell is blank: the Lens of Truth, the strength upgrades and the Fire Arrows show (dim until owned). A cell whose item the game has no
  flag for (none should, with this game) shows a small `?` at its right.
- Ganon's Castle's key ring, once obtained, shows `2/2` even before the next item get (its get flag; see the format doc's keys).
- Rename `icons.bin` and start the game again: the log says `no content:/RandoTracker/icons.bin: the items show as their letters` and the
  cells show their letters. Rename it back.

## 3d. The postcard

- The regions end with a **Postcard** entry (Off at first, dim); the highlight reaches it by down in the last column or right from
  the one before. A opens four rows: Postcard, Position, Size, Opacity, with `< value >`; up and down choose, left and right change
  the value at once (Position wraps, Opacity goes 25, 50, 75, 100 %). B goes back to the regions.
- Turn it On: while the settings are shown the card appears in its corner (bottom right, small, 50 % by default) and follows each change
  of position, size and opacity. It shows the items, the stones and medallions, and the dungeons' keys; a `?` where the game has no flag.
- B twice (the panel closes): the card stays, in the same place, and the game still gets every button (move, camera, A, B).
  Walk around and pick up an item: its cell lights within half a second.
- Open the panel on the regions: the card is hidden meanwhile; close it: it comes back.
- At 1080p small is about 340 pixels wide, medium 470, large 620; each reads at 1080p (the icons, the keys' counts). Check 720p too.
- The opacity covers the box and the icons together (25 % is faint, 100 % is the box's own 86 %).
- Quit the game and start it again: the log says `postcard:` lines only on a problem (`no SD card access`, or `no ... postcard.cfg: the
  defaults` the first time); the settings come back as they were left, and the file is at `<user folder>/sdmc/ootrTracker/postcard.cfg`.
  Delete it or fill it with junk: the defaults are used, nothing crashes.

## 3e. The songs (0.4.0)

With a seed made or updated by 0.4.0, and `icons.bin` made from the game (`update-tracker --nup GAME.nup`):

- Under the items' rows there are two rows of six cells: Minuet, Bolero, Serenade, Requiem, Nocturne, Prelude, then Zelda's Lullaby,
  Epona's, Saria's, Sun's, Song of Time, Song of Storms. Check this is the order of the game's own song list; if the remake's
  differs, say so.
- A new game: all twelve are dim, none has a `?`. Learn a song (the Lullaby from Impa is the first): within half a second its cell lights
  in its colour. Learn each of the twelve one at a time, or load a save that has some: exactly the learned ones are lit.
  This is also the check that `IsGet.Item_Melody_<name>` is set when a song is learned (the flags exist in the game's data; that the game
  sets them is read from its cutscenes, not seen).
- The pictures: in the log, `the icons are in` still shows once, with 50 icons in; each song cell shows a white picture on its colour. Check each
  picture is the right song's (the numbering is the ocarina melody list's; decoded on the PC the pictures match: Epona's a horse, Sun's a
  sun, Storms' clouds, Minuet's a tree, Bolero's a flame, Serenade's a water drop): a wrong one means `ingame_icons.MELODY_ORDER` is off.
- The panel with every song learned, two status lines (a save of another seed, then the goal reached) and the 35 regions fits the
  screen at 720p and 1080p: nothing cut off at the bottom, the hint line visible; the regions' names are readable at the new, tighter
  row height.
- The postcard shows the songs under the items at all three sizes; each stays on the screen at 720p and 1080p in all four corners.
- A seed installed before 0.4.0 and not updated: the song cells show their letters with a `?`, and nothing else changes. After
  `update-tracker` the songs are tracked; its pictures need `--nup`.
- Rename `icons.bin`: the songs show their letters (Mi, Bo, Se, Re, No, Pr, Lu, Ep, Sa, Su, ST, SS).

## 4. What it shows

Pick up things and compare with the desktop tracker (Real time mode) on the same save:

- an item (a sword, a shield, a bomb bag at two levels): its cell lights with its level, within half a second of the pickup;
- a check with a Bool flag (a chest) and one with a Bool64bitKey (a Gold Skulltula, a placed rupee): the region's count goes up;
- a dungeon's small keys found and held, a key ring, the boss key;
- a song learned (see 3e);
- the goal flag, if the seed has one: "Goal reached".

Count the checks: the panel's total is the desktop tracker's "automatic" count. The two differ if the Bool64bitKey reading is wrong: a seed
appends about 300 records after the sorted ones, and the panel's `unreadable` figure should be 0 once a save is loaded.

## 5. Other game versions

On 1.0.0 the Bool64bitKey entry is unverified: an `unreadable` count equal to the Bool64bitKey checks (289 in the test seed) means it wasn't
found. On any other build the panel must say "Game version not supported", and the log `this game build is not known`.
