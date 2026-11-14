# How ootrTracker works

The module reads, never writes: it does not call a game function and it does not change the save. It is
[ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI)'s skeleton (hooks, frame counting, drawing in the game's style) with the song
player replaced by a reader of the game's save data. This file covers what differs; ocarinaMIDI's DESIGN.md has the rest at length
(lazy binding, chaining with sloperinaGZ, the NVN hooks, the slots).

## Loading

`subsdk7` in the game's exefs. rtld links it (imports: `nnMain`, `aligned_alloc` and `free` from main; nn::fs, `nvnBootstrapLoader`,
`snprintf` and a few libc functions from sdk; the list in `lib/imports.txt` is checked at link time) and calls
`ootr_tracker_module_init` (DT_INIT). That does three things, with checked reads and unformatted logging only:

1. `hooks_init` points two of main's setup imports (`nn::hid::InitializeNpad`, `GetNpadStyleSet`) at wrappers. The first call to
   either points main's five `GetNpadStates` GOT slots at wrappers that call what the slots held then.
2. `app_init` finds which game build this is (`builds.c`: nnMain's address minus the build's offset gives main's base, and main's MOD0
   header must be where the build says). Builds 1.0.0 and 1.1.1 are known. Another build leaves `app.game.build` NULL.
3. `nvn_hook_game` wraps `nvnBootstrapLoader`, so the module sees the device and each present.

Next to sloperinaGZ (`subsdk9`) and ocarinaMIDI (`subsdk8`) every hook calls what its slot held before, or the sdk's own function when
the slot still points into main (a lazily bound import: calling it would crash). No symbol is shared: the module is linked with hidden
visibility. It has no IPS patch and takes no game offset beyond the GameData ones in `builds.c`. It mounts nothing: it only reads
`content:` (the game's RomFS, mounted by the game), so there is no mount name to clash.

## The seed file

`content:/RandoTracker/seed.trk` ([docs/ingame-tracker-format.md](../../docs/ingame-tracker-format.md)): the seed's markers, the flags to watch by region with each check's name, the items' flags, the dungeons' key flags.
Version 2 files name the checks; version 1 files (seeds made by the 0.1.0 exporter) are read too, and their checks are shown as "Check N".
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
  unknown when it knows none. Items named `Soul (...)` are counted as souls, the others are looked up in `grid.c`'s rows;
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
highlighted region's list, and the D-pad or the left stick's direction bits move the highlight: on the press, then after 350 ms every
90 ms while held. One command a frame, in that order (the combination, B, A, a direction).

While the panel is open, every state the game reads has R, the right stick's direction bits, A, B, the D-pad and the left stick's direction
bits cleared, and both sticks' axes centred (`app_edit_state`); while the combination is held with the panel closed, R and the right
stick. When the panel closes, those of them still held stay hidden (and a stick still pushed stays centred) until they are let go for a
frame, so the B that closed the panel doesn't reach the game. Nothing is hidden until the seed file has loaded. R + right stick down is
sloperinaGZ's menu, R3 + D-pad is ocarinaMIDI's.

## Browsing

`browse.c` is pure: the highlighted region, and with its list open the highlighted check and the first one shown. The regions are drawn in
three columns filled top to bottom: up and down step through them in that order, left and right jump a column (to the last region of a
shorter last column). In a list, up and down step one check and left and right a page, and the list scrolls to keep the highlight shown.
B goes back to the regions, and B there closes the panel. Opening the panel shows the regions again, with the highlight where it was.

## Drawing

`trackerui.c`, with `uitext.c`, over `gpuui.c`: the game's own font (Clarimo UD PE, regular and DemiBold) and UI shader, read from its
RomFS through `gamefile.c` the first time the panel is opened (a pause), rasterised with stb_truetype into a glyph atlas, and one draw
per quad (a glyph or a rectangle), blended over the picture just before the game's present, with no read-back. The sizes are
sloperinaGZ's: a font pixel is a 360th of the picture's height, so the panel scales with the resolution (560 font pixels wide: 1,680 pixels
at 1080p, 1,120 at 720p). Top to bottom: title and seed id; status lines (not this seed's save, goal reached); the items, 4 rows of 9, as
their icons (below) or else their letters (owned: lit in the item's colour, with its level; missing and unknown: dim); the dungeons' keys; the checks' total and the souls; the regions in
three columns, each `collected/trackable` (green when all, dim when none), the highlighted one on a gold band; a line of hints. With a
region's list open, the grid and the regions give way to the region's name, its count and which checks are shown, then up to 18 checks:
a filled green box and a green name when collected, an empty white box and a white name when missing, a dim question mark when the game
doesn't have the flag.

Quad budget: ocarinaMIDI draws at most 512 quads (a short list). This panel's text is about 1,000 quads at most (35 regions, 36 cells), so
`MAX_QUADS` in `gpuui.c` is 1,536, the command memory per slot (`overlay.c`) 0x40000 (sloperinaGZ's own size) and the elements 2 x 1,536 x
256 bytes. Over the budget the rest of the frame is left out, with a log line, not a crash. The icons add at most 27 quads, and shrinking
a picture has its own 36 elements per slot.

## The items' icons

`content:/RandoTracker/icons.bin` ([docs/ingame-tracker-format.md](../../docs/ingame-tracker-format.md)), which the randomizer writes on the
player's PC from their own game: for each item of the grid, the game's picture as its BNTX stores it (ASTC 4x4 blocks in the GPU's
block-linear layout) and the BNTX's description of that layout. Nothing is decoded on either side: the module gives the bytes to NVN as an
ASTC 4x4 texture with that packaged layout (`nvnTextureBuilderSetPackagedTextureLayout`), as sloperinaGZ's `gpuui.c` (`make_images`,
master 5287f64) makes textures of the game's controller pictures; sloperinaGZ decodes its icons on the CPU instead (`astc.c`). They are
sampled as unorm whatever the BNTX says, as sloperinaGZ's `gameimage.c` does: no sRGB decode, like everything else the panel draws.

The pictures are large (up to 704 KB each, about 7 MB for the 27) and the game's heap has little to spare (sloperinaGZ's NATIVE_UI.md and
FINDINGS.md: it refused allocations past about 10 to 11 MB), so they are not kept. Each is shrunk once, on the GPU, into a 64-pixel slot
of an icon atlas (384 x 320, RGBA16F, about 1 MB), and only one picture's bytes are held at a time:

1. The first frame the panel is drawn (`trackerui.c`, `icons_start`), the file's header and index are read and checked (`iconfile.c`), the
   grid's cells are matched with its entries by name, and `gpuui_icons_init` makes the atlas (registered after the glyph atlas) and room
   for the largest picture.
2. Then one picture every other frame the panel is drawn (frame slot 0, so the GPU is done with the last one): its bytes are read by offset
   into that memory, NVN makes a texture of them, and the frame's commands draw it into its slot before the panel. Each atlas pixel is the
   mean of up to 6 x 6 filtered samples, their premultiplied colours added up by blending, so a 683-pixel picture doesn't alias at a tenth
   of its size. The cell shows its icon from that frame on, its letters until then.
3. Once all are in, the picture memory is freed (log: `the icons are in; the pictures' N KiB go back`).

A cell's icon is a square as tall as the cell, in its middle, drawn with premultiplied blending: at full strength when the item is owned,
dimmed when it is missing or unknown. The atlas is a render target, so its rows run the window's way up: with the lower-left origin it is
sampled upside down, as sloperinaGZ samples its layer.

## Failure modes

Each is logged once and leaves the game alone: no `seed.trk` or a damaged one (idle); an unknown build (the panel opens and says so);
no save data yet (the panel says "Waiting for the game's save data"); the game's font or shader can't be read, or the GPU side can't start
(no panel; the controls still work); the GPU not finishing a frame's drawing for 5 s (the panel gives up); no `icons.bin`, a damaged one,
an NVN without the functions the icons need, or no memory for them (the items show as their letters); a picture that can't be read or
that NVN won't take (that item shows as its letters).

## Known limits

- Nothing was tested in the game when this was written (TESTING.md has the plan).
- Only ASCII is drawn (other characters show as `?`, one per byte); region and check names are ASCII in full-randomizer seeds (the
  Kokiri-only mode's "Four-chest house" checks have an em dash).
- The panel is drawn at the present, over everything, the game's pause screen included.
- "In logic" (what can be reached now) is not shown: it needs the randomizer's Python logic sweep.
- The icons need the player's game when the seed is made, or `update-tracker --nup`: a seed without `icons.bin` shows the items' letters.
