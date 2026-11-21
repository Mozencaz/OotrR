# How ootrTracker works

The module reads, never writes: it does not call a game function and it does not change the save. (It writes its own
memory only: its console's mailbox, which the desktop client fills.) It is
[ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI)'s skeleton (hooks, frame counting, drawing in the game's style) with the song
player replaced by a reader of the game's save data. This file covers what differs; ocarinaMIDI's DESIGN.md has the rest at length
(lazy binding, chaining with sloperinaGZ, the NVN hooks, the slots).

## Loading

`subsdk7` in the game's exefs. rtld links it (imports: `nnMain`, `aligned_alloc` and `free` from main; nn::fs (also the SD card's mount, create, delete and write, for the postcard's and the console's settings), `nvnBootstrapLoader`,
`snprintf` and a few libc functions from sdk; the list in `lib/imports.txt` is checked at link time) and calls
`ootr_tracker_module_init` (DT_INIT). That does three things, with checked reads and unformatted logging only:

1. `hooks_init` points two of main's setup imports (`nn::hid::InitializeNpad`, `GetNpadStyleSet`) at wrappers. The first call to
   either points main's five `GetNpadStates` GOT slots at wrappers that call what the slots held then.
2. `app_init` finds which game build this is (`builds.c`: nnMain's address minus the build's offset gives main's base, and main's MOD0
   header must be where the build says). Builds 1.0.0 and 1.1.1 are known. Another build leaves `app.game.build` NULL.
3. `nvn_hook_game` wraps `nvnBootstrapLoader`, so the module sees the device and each present.

Next to sloperinaGZ (`subsdk9`) and ocarinaMIDI (`subsdk8`) every hook calls what its slot held before, or the sdk's own function when
the slot still points into main (a lazily bound import: calling it would crash). No symbol is shared: the module is linked with hidden
visibility. It has no IPS patch and takes no game offset beyond the GameData, camera and Link ones in `builds.c`; it hooks
nothing new for show in the world (the marker is drawn in the present hook it already has), so it adds no clash with
sloperinaGZ's hooks. It reads `content:` (the game's RomFS, mounted
by the game) and, for the postcard's and the console's settings, mounts the SD card once as `ootrtrk` (`sdfile.c`) (a mount name can be used once, and sloperinaGZ
and ocarinaMIDI have their own).

## The seed file

`content:/RandoTracker/seed.trk` ([docs/ingame-tracker-format.md](../../docs/ingame-tracker-format.md)): the seed's markers, the flags to watch by region with each check's name, the items' flags, the dungeons' key flags.
Version 4 files add each check's id (its internal key) and its places in the game's maps (show in the world, below).
Version 3 files add a flags word (bit 0: an Archipelago seed, which turns the console on by default); version 2 files (no flags: a local
seed) name the checks; version 1 files (seeds made by the 0.1.0 exporter) are read too, and their checks are shown as "Check N".
It is read once, on the game thread, 10 s after the first frame, and again at a press of the combination if that first read found
nothing (at most every 2 s). If it is missing or damaged (`trkfile.c` checks every offset and count) the module stays idle: the
combination does nothing and the game sees every button. The bytes are kept for good, because the panel's names point into them.

## Reading the game's save data

`gamedata.c`, from sloperinaGZ's `gamedata.c` and its FINDINGS. The GameData manager is `**(main + gd_mgr_ptr)`. It holds one entry per
field type:

| | where | a field |
|---|---|---|
| Int | manager + 0xC8 | object of 0x28 bytes, value (int32) at +0x1C |
| Bool | the entry whose vtable is the build's `vt_bool_type`, found by scanning manager + 0..0x800 | object of 0x18 bytes, value (u8) at +0x16 |
| Bool64bitKey | manager + 0xC58 (scan 0xC08..0xD08 if not there) | 16-byte records: key (u64), value (u8 at +0xC) |

Bool and Int are open-addressed hash tables of (hash, index) pairs, probed as the game does. Every pointer is checked with `sys_mapped`
before it is read, and each `gamedata_attach` (at every refresh: the manager moves when a save is loaded) finds the entries again and
validates them.

**The Bool64bitKey table is only partly sorted.** The game's own records are sorted by key and it binary-searches them. A seed appends
about 300 more after them, in no order (the randomizer's own live tracker was bitten by this, and sloperinaGZ's collectibles page may be).
So the table is a sorted head and an unsorted tail: the head's length is found once by scanning for where the keys stop rising (cached per
table address and count), and a key is searched by binary search in the head, then linearly in the tail. The table is accepted only if
the game's first Gold Skulltula key is in the head.

A key the game doesn't have is `GD_UNKNOWN`, never false: an unknown check isn't counted as collected, and the panel counts them
(`unreadable`).

## Working out the panel

`tracker.c` is pure: `tracker_compute(seed, flag source, state)` asks a `flag_source_t` (three function pointers) and fills a fixed-size
`tracker_state_t`; the PC tests use a table in place of the game. It does what the desktop tracker does:

- an item's level is the highest of its rules whose Bool is set (owned); it is missing when the game knows a flag but none is set, and
  unknown when it knows none. Items named `Soul (...)` are counted as souls, the others are looked up in `grid.c`'s cells: the 36 items
  in four rows of nine, then the 12 ocarina songs. A song is an item of one rule, the game's `IsGet.Item_Melody_<name>` Bool, which the
  exporter adds to every seed (`tracking_metadata.SONGS`); a seed file made before that has none, so its songs are unknown (`?`) until
  `update-tracker`. A cell whose `grid.c` entry is `counted` (the Bottle, five levels) takes as its level how many of its rules'
  Bools are set instead of the highest: its rules are the five bottle slots' `...BottleInfo.Bottle<A-E>.IsValid` Bools, so two
  bottles in slots B and D read 2, and the cell draws the number as it does a level. The postcard draws the same cells;
- a region's count is its checks whose flag is set, out of its checks;
- small keys found = the larger of keys found and keys held, or all of them with a key ring applied; the boss key is its Bool;
- the save is of this seed when the seed marker reads true, and of another when it reads false.

`app.c` calls it twice a second while the panel is open (never while it is closed) on the game's controller thread, then publishes the
result (`overlay.c`, a sequence lock) to the present thread. With a region's list open, `tracker_check_rows` reads the flags of the
checks shown (at most `BROWSE_CHECK_ROWS`, 18) into the panel. A move of the highlight publishes the panel again at once, with only
those rows read anew: the rest waits for the next refresh, so scrolling costs a few flag reads, not the whole seed's.

## Controls

`controls.c`. A frame is counted from the controller reads (`poll.c`): the first controller the game reads is the anchor, a read of it
8 ms after the last starts a frame, and the buttons held during the frame that ended are the frame's input. R + right stick up
(`BTN_R`, `BTN_RS_UP`, bit 21) toggles on its press. With the panel open, B (on its press) goes back or closes, A opens the
highlighted region's list (in a list, it ticks the highlighted check by hand), Y (`CONTROL_LOCATE`) shows a list's highlighted check in
the world, and the D-pad or the left stick's direction bits move the highlight: on the press, then after 350 ms every 90 ms while
held. One command a frame, in that order (the combination, B, A, Y, a direction). Y does nothing outside a region's list.

While the panel is open, every state the game reads has R, the right stick's direction bits, A, B, Y, the D-pad and the left stick's
direction bits cleared, and both sticks' axes centred (`app_edit_state`); while the combination is held with the panel closed, R and
the right stick. When the panel closes, those of them still held stay hidden (and a stick still pushed stays centred) until they are
let go for a frame, so the B that closed the panel doesn't reach the game. Nothing is hidden until the seed file has loaded. R + right
stick down is sloperinaGZ's menu, R3 + D-pad is ocarinaMIDI's.

## Browsing

`browse.c` is pure: the highlighted region, and with its list open the highlighted check and the first one shown. The regions are drawn in
three columns filled top to bottom: up and down step through them in that order, left and right jump a column (to the last region of a
shorter last column). In a list, up and down step one check and left and right a page, and the list scrolls to keep the highlight shown.
B goes back to the regions, and B there closes the panel. Opening the panel shows the page it was closed on, with its highlight
(`browse_reopen`: in a list, the same check, kept in sight). The browse state lives as long as the game runs.

After the regions comes the **Settings** entry (the region count). A opens `BROWSE_SETTINGS`, whose two rows (`browse_t.entry`) open
`BROWSE_POSTCARD` and `BROWSE_CONSOLE` (`browse_t.setting`); the console's rows after Fade are its kinds of message
(`CONSOLE_SETTING_FIRST_KIND` on), which A or left and right tick. B goes back one page: Postcard and Console to Settings, Settings
to the regions. Each page's highlight starts at its first row when it is opened, and is kept when a page below it is left.

## Drawing

`trackerui.c`, with `uitext.c`, over `gpuui.c`: the game's own font (Clarimo UD PE, regular and DemiBold) and UI shader, read from its
RomFS through `gamefile.c` the first time the panel is opened (a pause), rasterised with stb_truetype into a glyph atlas, and one draw
per quad (a glyph or a rectangle), blended over the picture just before the game's present, with no read-back. The sizes are
sloperinaGZ's: a font pixel is a 360th of the picture's height, so the panel scales with the resolution (560 font pixels wide: 1,680 pixels
at 1080p, 1,120 at 720p). Top to bottom: title and seed id; status lines (not this seed's save, goal reached); the items, 4 rows of 9, as
their icons (below) or else their letters (owned: lit in the item's colour, with its level; missing and unknown: dim), and under them the 12 songs in two rows of six, drawn the same way across the box's width; the dungeons' keys; the checks' total, the Gold Skulltulas and the souls; the regions in
three columns, each `collected/trackable` (green when all, dim when none), the highlighted one on a gold band; a line of hints. With a
region's list open, the grid and the regions give way to the region's name, its count and which checks are shown, then up to 18 checks:
a filled green box and a green name when collected, an empty white box and a white name when missing, a dim question mark when the game
doesn't have the flag.

Quad budget: ocarinaMIDI draws at most 512 quads (a short list). This panel's text is about 1,050 quads at most (35 regions, 48 cells), so
`MAX_QUADS` in `gpuui.c` is 1,536, the command memory per slot (`overlay.c`) 0x40000 (sloperinaGZ's own size) and the elements 2 x 1,536 x
256 bytes. Over the budget the rest of the frame is left out, with a log line, not a crash. The icons add at most 72 quads (48 cells and
three per dungeon in the keys row, which then draws fewer letters), and shrinking a picture has its own 36 elements per slot.

## The items' icons

`content:/RandoTracker/icons.bin` ([docs/ingame-tracker-format.md](../../docs/ingame-tracker-format.md)), which the randomizer writes on the
player's PC from their own game: for each item of the grid, the game's picture as its BNTX stores it (ASTC 4x4 blocks in the GPU's
block-linear layout) and the BNTX's description of that layout. Nothing is decoded on either side: the module gives the bytes to NVN as an
ASTC 4x4 texture with that packaged layout (`nvnTextureBuilderSetPackagedTextureLayout`), as sloperinaGZ's `gpuui.c` (`make_images`,
master 5287f64) makes textures of the game's controller pictures; sloperinaGZ decodes its icons on the CPU instead (`astc.c`). They are
sampled as unorm whatever the BNTX says, as sloperinaGZ's `gameimage.c` does: no sRGB decode, like everything else the panel draws.

The pictures are large (up to 704 KB each, about 7.3 MB for the first 38; the songs' are 14 KB each) and the game's heap has little to spare (sloperinaGZ's NATIVE_UI.md and
FINDINGS.md: it refused allocations past about 10 to 11 MB), so they are not kept. Each is shrunk once, on the GPU, into a 64-pixel slot
of an icon atlas (512 x 448, 56 slots, RGBA16F: 1.75 MiB, kept; the game of 13/11 gives 38 icons, the 12 songs make 50, the Skulltula token 51), and only one picture's bytes
are held at a time (688 KiB at most, freed once they are in):

1. The first frame the panel is drawn (`trackerui.c`, `icons_start`), the file's header and index are read and checked (`iconfile.c`), the
   grid's cells are matched with its entries by name, and `gpuui_icons_init` makes the atlas (registered after the glyph atlas) and room
   for the largest picture.
2. Then one picture every other frame the panel is drawn (frame slot 0, so the GPU is done with the last one): its bytes are read by offset
   into that memory, NVN makes a texture of them, and the frame's commands draw it into its slot before the panel. Each atlas pixel is the
   mean of up to 6 x 6 filtered samples, their premultiplied colours added up by blending, so a 683-pixel picture doesn't alias at a tenth
   of its size. The cell shows its icon from that frame on, its letters until then.
3. Once all are in, the picture memory is freed (log: `the icons are in; the pictures' N KiB go back`).

A cell's icon is a square as tall as the cell, in its middle, drawn with premultiplied blending: at full strength when the item is owned,
dimmed when it is missing, fainter still when it is unknown (the game has none of its flags), which also gets a small `?` at the cell's
right. The stones and medallions use the file select's pictures (`DataFileImportantIcon_00` to `_08`). The songs use the ocarina's
melody list's (`OcarinaMelodyIcon_00` to `_11` of the same archive: 107 pixels, ASTC 4x4 sRGB, swizzled to grey with an alpha channel, so they
are drawn white on the song's coloured cell), numbered as the game's melody scores list the songs (Zelda's Lullaby first,
Epona's, Saria's, Sun's, Time, Storms, then the six warp songs; the 13th, `_12`, is the scarecrow's, unused). That the numbering is the
melody list's was checked by decoding the 13 pictures on the PC with the emulator's ASTC decoder (a horse, a sun, storm clouds, a tree, a
flame, a water drop and a scarecrow are 01, 03, 05, 06, 07, 08 and 12); it is not yet seen in the game. In the keys row each temple is
labelled by its medallion's icon (Bottom of the Well, Gerudo Training Ground and Ganon's Castle, which have none, keep their letters),
then the small key's icon and `found/total`, then the boss key's icon, dimmed until it is held; without the icons, the letters and a `B`
as before. The Gold Skulltula count (0.7.2) is the token's icon and `held/100` in the summary row, left of the souls, and in a last row of
the postcard; the number is the Int `PouchData.Item_Token_Gold.StockNum` (0x04735978, sloperinaGZ's `data_skulltulas`), `?/100` if the
game has no such field, and `GS` stands in for the icon without it. The hearts have no such count: the game keeps no container count
(`PouchData.Obj_Heart_Container.StockNum` doesn't exist), only `PlayerStatus.MaxLife` and the pieces' count modulo 4, so they are not shown. The atlas is a render target, so its rows run the window's way up: with the lower-left origin it is
sampled upside down, as sloperinaGZ samples its layer.

## Sizes

`sizes.c` holds every size that decides the height of the panel or the card, in font pixels, so the host tests can check that they
fit. Under the title the panel is the items' four rows of 18, a gap of 2, the songs' two rows of 14 (each cell a sixth of the box's inner width), then
the keys, the summary and the regions in three columns of 10 per row. At 35 regions it is 326 font pixels tall, 350 with the most status
lines (2); the picture is 360 high and the panel starts 8 down, so 352 is the most. (The songs' rows took the room by making the items'
rows 18 instead of 20, the regions' 10 instead of 11 and the gaps between sections 6 instead of 8.) The postcard at full size is 208 wide and
157 tall with eight dungeons' keys (112 with none), times 0.55, 0.75 or 1.0.

## The postcard

A small card with the items' grid, the songs under it and the dungeons' keys, drawn in a corner while the panel is closed. Its parts:

- `postcard.c` is pure: the four settings (on, position, size, opacity), their values and text, stepping through them,
  the card's corner (`postcard_origin`), and the settings file's text (`postcard_format`, `postcard_parse`: `name=number` lines,
  a bad line or value is skipped so a damaged file leaves the defaults).
- `postcardfile.c` mounts the SD card as `ootrtrk` (`MountSdCard`, else `MountSdCardForDebug`) and reads and writes
  `ootrTracker/postcard.cfg` as sloperinaGZ's `settings.c` does (create the directory, delete, create, write with flush). It reads when the
  seed file has loaded (`ensure_seed` in `app.c`) and writes when the settings page is left or the panel closed with a change (not at each
  press: a write is a few file calls on the game thread). With no SD card the settings are in memory only.
- Browsing: the region count is the highlight's last stop, the **Postcard** entry, drawn in the regions' columns with On or Off in
  place of a count. A opens `BROWSE_POSTCARD`: four rows (`browse_t.setting`); up and down move, left and right change the value
  (`app.c` calls `postcard_step`), B goes back. That page is a narrower panel (320 font pixels).
- With the card on and the panel closed, `app_frame` publishes a `panel_t` with `menu` false twice a second, filled by
  `tracker_compute_icons` (items, songs, keys and the Skulltula count only: not the 1,500 region flags), and the present hook draws the card from it every frame.
  While the settings page is open the card is drawn as a preview: the panel is drawn first, then the card
  over its corner, so a change is seen at once. On the regions and a region's list the card is hidden.
- The game's pause: while the card or the console is on, `read_pause` in `app.c` reads it every 100 ms (`gamedata_paused`,
  sloperinaGZ's `gd_game_paused`: the Bool `Sequence_IsPause`, or the Int `Sequence_GamePauseRequestCount` above 0). While the game
  is paused and the panel closed, the card isn't published (`postcard_over_game`): an empty panel is, once, and the card comes back
  at the next frame after the pause. The panel itself doesn't read the pause.
- Drawing (`trackerui.c`): `layout_scaled` gives the fonts and hairline for a font pixel of any size, so the card is the panel's
  own `draw_grid` and `draw_keys` at the card's scale (`postcard_scale` of the picture's font pixel: 0.55, 0.75 or 1.0 of the full-size
  card, items in 22 x 18 font-pixel cells, so the icons are nearly square, the songs in cells a sixth of the card's width and 14 tall) with the keys in 3 columns and the Skulltula count under them. The opacity is `gpuui_set_opacity`: each
  quad records the frame's opacity, and `write_element` multiplies its alpha by it (and a premultiplied icon's colour too), so
  the box, the glyphs and the icons fade together. Quads overlap as they do at full opacity (text over a fainter box), so it reads as one
  translucent card, not a flattened image.

## The console

A few lines of Archipelago messages over the game, written into the module's memory by the desktop client (its layout and protocol
are in [the format document](../../docs/ingame-tracker-format.md#the-consoles-mailbox)). Its parts:

- `mailbox.c`: the mailbox is a static `mailbox_t` in the module's data with its header filled in (so its magic is in memory from the
  start). Each frame `app_frame` calls `mailbox_poll`: the heartbeat is read on its own; when the sequence is even and new, the status
  and the entries from the module's read head to the client's head (at most the last 32: a client faster than the module loses the
  oldest, never shows a half-written one) are copied, and kept only if the sequence is unchanged after the copy. A kind it doesn't know
  is a server notice; a length over the entry's room is cut to it. `mailbox_set_seed` writes the seed id once the seed file is read.
- `consolelog.c` is pure: the last 32 lines with their kind and the time they came, made drawable on arrival (`console_sanitize`:
  UTF-8 to the font's characters, ASCII and Latin-1 as one byte each, others `?`, tabs and line ends to spaces, controls dropped); the
  view of the newest lines of the kinds ticked; each line's fade (full for the Fade time, then out over a second).
- `console.c` is pure: the settings (on for local and for Archipelago seeds kept apart, position, opacity, lines, fade, the kinds as
  bits), their text, stepping, and `console.cfg`'s text (`version=1` first, then `name=number` lines; a file without `version=1` is
  ignored whole, a bad line or value is skipped). `cfgtext.c` is the `name=number` reader and writer it shares with `postcard.c`;
  `consolefile.c` reads and writes the file through `sdfile.c`, as the postcard's (on loading the seed; when the console's page is left
  or the panel is closed).
- `app.c` publishes a `console_view_t` (settings, on or off for this seed, status line, the lines to show) to the present thread
  through its own seqlock (`overlay_publish_console`) when a line, the status line or a setting changes. The status line comes from
  `mailbox_status_line`: "Archipelago client not running" after 10 s without a heartbeat (for an Archipelago seed counted from loading
  the seed, for a local one only once a client was heard), else "connecting to ..." or "not connected" while the client says so.
- Drawing: `sizes_console_box` places the box (wide 380 font pixels at the top or the bottom, 180 tall at either side, a row of 10 per
  line) and keeps it clear of the postcard's box: sideways, then narrower (down to 260), then above or below it; a tall one up or down,
  then beside it. The rows are collected from the bottom (the status line, then the newest lines, each wrapped over at most 3 rows) until
  the box is full; each row has its own band, so a short console doesn't darken an empty box. The opacity and each line's fade multiply
  through `gpuui_set_opacity`. While the panel is open it is drawn only as the preview on the console's page (whole, at full fade).
  While the game is paused and the panel closed, the view is published with `shown` false (`console_over_game`), and again when the
  pause ends; opening or closing the panel publishes it again, so the preview shows while paused.
  With the console's 12 rows and the postcard the frame stays under `MAX_QUADS`; the console is never drawn with the regions' panel.

## Show in the world

Y on a check of a region's list (`app.c` `toggle_located`) makes it the check shown, Y on it again none, Y on another that one; a
check the seed file has no place for (an NPC's gift, an event, or a file older than version 4) stays as it was, and the row under the
list says why. The parts:

- `locate.c` is pure: a region's nth check's index, the toggle, `locate_find` (the check's places, binary-searched in the place table
  by `trk_places_of`, against the game's map: here, with the point; elsewhere, with the first map's label and how many others; no place;
  an old file; the map not known yet) and its words (`12 m away, 3 m up`, `In Deku Tree and 1 other map`, `turn left`).
- `gamedata.c` reads the String64 "map" (`0x1D6189DA`, the type entry at manager + 0x608, objects 0x108 apart with the text's pointer
  at 0x68 and its capacity after it: sloperinaGZ's `gamedata.c` `string_at` and `gd_get_str`, 8a2c73c), the save's map name, which is
  the map's layout name without `_Static` or `_Dynamic` (`KokiriForest_Child`, `GohmaStage`): the exporter's `check_places.py` names
  the places the same way. The pause is sloperinaGZ's `gd_game_paused`: the Bool `Sequence_IsPause` or the Int
  `Sequence_GamePauseRequestCount` above 0.
- `app.c` works out a `locate_view_t` every 250 ms while a check is shown (open panel or not) and hands it to the present thread through
  its own seqlock (`overlay_publish_locate`) when it changes: shown (not while paused), drawn (in this map), the point, the check's name,
  where it is otherwise, and main + the build's `camera_ptr` and `disp_ptr`. The list's two rows under the checks (`locate_detail_t`
  in the panel) are worked out with the panel: the check's id, and the line `locate_panel_line` makes.
- `view.c` is sloperinaGZ's `view.c` (8a2c73c): the camera's basis from its position and look-at (right = (-forward.z, 0, forward.x),
  up = right x forward), the tangents of its fov and aspect, a world point to camera space and to the picture (0..1 across and down);
  and its `airwall.c` `clip_near` and `clip_to_picture` (Liang-Barsky) to cut a segment at the near plane and to the picture. The module
  imports no `sqrtf`: `view_root` is the CPU's `fsqrt` (gamefont.c's way), and Newton's method on the PC for the tests.
- `worldmark.c`, on the present thread, reads the camera as sloperinaGZ's `link.c` `camera()` and `view.c` `view_camera` do
  (`[[main + camera_ptr] + 0x68]`: position 0x38, look-at 0x44, near 0x128, fov 0x130, aspect 0x140; every read checked) and Link's
  drawn position (`[[main + disp_ptr]] + 0x29C`, `link_drawn_pos`), and draws the marker: a box 1 m across and 1 m high on the
  check's position (an actor's position is its base) and a beam 30 m up from its top centre, each of the 13 lines a `gpuui_line`
  (sloperinaGZ's soft line: a quad along it sampling a 4 x 32 coverage profile in the glyph atlas) 2.4 px wide at 1080p over a 9 px
  glow at 22 % (its `overlayui.c` widths), in the panel's gold. They are drawn first, so the panel and the band go over them, and
  are **not depth-tested** (sloperinaGZ tests its walls against the game's depth; the marker has to be found through walls).
- `trackerui.c` draws the marker whenever a check is shown, and, with the panel closed, a band at the top centre (the bottom when the
  console is at the top) with the check's name and how far it is from Link, or where it is; `trackerui_record` and the overlay draw a
  frame for it alone too.

The marker is 26 quads (13 lines and their glows) and the band about 100, well within `MAX_QUADS`.

## Failure modes

Each is logged once and leaves the game alone: no `seed.trk` or a damaged one (idle); an unknown build (the panel opens and says so);
no save data yet (the panel says "Waiting for the game's save data"); the game's font or shader can't be read, or the GPU side can't start
(no panel; the controls still work); the GPU not finishing a frame's drawing for 5 s (the panel gives up); no `icons.bin`, a damaged one,
an NVN without the functions the icons need, or no memory for them (the items show as their letters); a picture that can't be read or
that NVN won't take (that item shows as its letters).

## Ticked by hand

A on a check of a region's list (`app.c` `toggle_mark`) ticks it, or unticks it, as the desktop tracker's double click toggles a
check's manual completion (`ManualTracker` in `randomizer_services.py`, shown as `Done (manual)`). As there, a check the save shows
collected can't be ticked or unticked, and a tick counts as found. The parts:

- `marks.c` is pure: a bit per check of the seed file (up to 4,096), the toggle, and the file's text. The ticks are on only for a
  version 4 seed file with ids and a seed id of letters and digits; a check's id must be 1 to 160 characters without a control
  character. The file is `ootrTracker marks 1`, `seed <id>`, a `check <id>` line per tick in the seed file's order, and
  `end <count> <FNV-1a of every byte before that line, 8 hexadecimal digits>`. `marks_t.length` is kept exact at each toggle, and a
  tick that would take the file past 32 KiB is refused, so the file always fits its buffer. `marks_parse` takes a file only if it is
  whole (each line ended, the count and the sum right, nothing after the end line), of version 1 and of this seed; an id the seed
  file doesn't have, or a second line of one, is left out, as `ManualTracker` intersects its file with the seed's ids. A lookup
  starts after the last check found, so a file in the seed's order is read in one pass.
- `tracker.c`: `tracker_count_marks` adds the ticked checks the save doesn't show collected to their region's and the total
  `collected` (a `?` one leaves `unreadable`), after `tracker_compute`; `tracker_mark_rows` sets `check_row_t.marked` for the rows
  of a list. The trackable counts don't change.
- `marksfile.c` keeps the file on the SD card through `sdfile.c` (the RomFS, where `seed.trk` is, can't be written):
  `ootrTracker/marks-<seed id>.cfg`. The module can't rename a file: `nn::fs::RenameFile` isn't among the sdk functions it is known
  to call, and a missing import would only show in the game. So a save writes the same text to `marks-<seed id>.new`, then to the
  file, and deletes the copy once both are written; a load reads the file, or the copy if the file is missing or damaged. A write
  cut off therefore leaves one whole copy of the ticks before that save. It reads when the seed file loads and writes when the list
  is left or the panel closed with a change, as the settings are, with a 32 KiB buffer from the heap for the time of the call.
- `trackerui.c`: a ticked box is `done_colour`'s outline over the same green at 35 % (a collected one is filled), the name in a
  dimmer green, and the second row under the list starts with `Ticked by hand` before the place's line.

## Known limits

- Show in the world: a check's place is its actor's position in the vanilla layouts, so a check that moves (a Gold Skulltula that
  flies, an item dropped by an enemy) is shown where it starts; the map's name to show is made from the layout's name, not the
  game's own text; the marker's lines go through everything, so in a room above or below the check the beam is the way to tell.

- The postcard's and the console's settings are written when their page is left: if the game is closed on that page, the last
  changes are lost.
- The console shows only what the client writes while the game runs: lines from before the game started, or from while the module
  couldn't take them (the client keeps up to 200 waiting), are not shown later.

- Nothing was tested in the game when this was written (TESTING.md has the plan).
- Only ASCII is drawn (other characters show as `?`, one per byte); region and check names are ASCII in full-randomizer seeds (the
  Kokiri-only mode's "Four-chest house" checks have an em dash).
- The panel is drawn at the present, over everything, the game's pause screen included.
- "In logic" (what can be reached now) is not shown: it needs the randomizer's Python logic sweep.
- The icons need the player's game when the seed is made, or `update-tracker --nup`: a seed without `icons.bin` shows the items' letters.
