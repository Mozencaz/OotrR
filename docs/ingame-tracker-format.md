# In-game tracker: seed file format

Every seed folder written by the application carries the data the in-game tracker reads:

* `romfs/RandoTracker/seed.trk` — this file, listed in `manifest.json` under `files` with its size and SHA-256;
* `exefs/subsdk7` — the prebuilt tracker module, listed under `exefs` in the manifest;
* `romfs/RandoTracker/icons.bin` — the items' icons, made from the player's own game ([below](#the-items-icons-iconsbin));
  listed under `files` when the seed has it.

The module is GPL-3 and its source is in this repository, in [`ingame_tracker/`](../ingame_tracker/) (the rest is MIT). It reads
`content:/RandoTracker/seed.trk` and compares it with the running game's save flags. It only reads memory.

`seed.trk` holds no placement: no item or reward of any check. It lists which flags to observe, grouped by the
region names the desktop tracker shows, with each check's name as the desktop tracker shows it
(`src/oot_rando/tracker/check_labels.py`). The writer is `src/oot_rando/tracker/ingame_format.py` (`build`); `parse`
there is the reference reader the tests use. The module validates the same bounds and ignores a file that fails.

## Layout

Everything is little-endian. Offsets are from the start of the file. Tables follow the header in this order:
string table, regions, checks, items, rules, keys; each table starts 4-byte aligned.

### Header (72 bytes)

| Offset | Type | Field |
|---|---|---|
| 0 | char[4] | magic `RTRK` |
| 4 | u16 | version (2; 1 in seeds made before the checks had names) |
| 6 | u16 | header size (72) |
| 8 | u32 | file size |
| 12 | u32 | seed marker: Bool hash, true in a save started with this seed |
| 16 | u32 | goal marker: Bool hash set when the goal is reached, 0 if the seed has none |
| 20 | u32 | seed id: string offset (first 16 hex digits of the seed identity, as in the folder name) |
| 24 | u32 | string table offset |
| 28 | u32 | string table size in bytes |
| 32 | u32, u32 | regions: offset, count |
| 40 | u32, u32 | checks: offset, count |
| 48 | u32, u32 | items: offset, count |
| 56 | u32, u32 | rules: offset, count |
| 64 | u32, u32 | keys: offset, count |

A reader rejects the file unless the magic, the version, the header size and the file size match, and every table
lies inside the file. Newer versions may add tables or fields; a reader refuses versions it doesn't know. Version 2
only gives the checks' reserved field a meaning (their name); a reader of version 2 reads version 1 files, whose
checks are then unnamed. A file holds at most 64 regions and 16 key rows (the module keeps a fixed-size state for
each); the writer refuses more.

### String table

UTF-8 strings, each ended by a NUL. Offset 0 is the empty string. A string offset is relative to the table start
and must be below the table size; the last string must be terminated inside the table.

### Regions (12 bytes each)

| Offset | Type | Field |
|---|---|---|
| 0 | u32 | name: string offset |
| 4 | u32 | first check: index into the checks table |
| 8 | u32 | check count |

Regions keep the order of the desktop tracker's catalogue. Only checks the game can be asked about are listed (the
others have no save flag), so the count is "trackable"; a region without such a check is left out.
`first check + check count` must not pass the checks table.

### Checks (16 bytes each)

| Offset | Type | Field |
|---|---|---|
| 0 | u64 | key |
| 8 | u32 | kind: 1 = Bool (key is the u32 hash), 2 = Bool64bitKey (key is the 64-bit key) |
| 12 | u32 | name: string offset (version 2); reserved and 0 in version 1, which reads as the empty string |

A check is collected when the game's flag for its key reads true. A key the game does not know is unknown, not
false. Bool64bitKey keys live in a table that is sorted at the start and followed by unsorted records appended by
the seed: a lookup binary-searches the sorted head and scans the tail. A check's name must be a string offset inside
the table, like every other string; a check without a name (version 1) is shown by its number in its region.

### Items (8 bytes each) and rules (8 bytes each)

An item is a name the tracker shows (the Archipelago item name, for example `Progressive Hookshot`). Its rules say
which save flags prove it and at which level.

| Item offset | Type | Field |
|---|---|---|
| 0 | u32 | name: string offset |
| 4 | u16 | first rule: index into the rules table |
| 6 | u16 | rule count |

| Rule offset | Type | Field |
|---|---|---|
| 0 | u32 | Bool hash |
| 4 | u16 | level held when the flag is true |
| 6 | u16 | reserved (0) |

The level of an item is the highest level among its rules whose flag is true; 0 when none is. If none of the
item's flags exists in the game, the item is unknown (the panel marks it with a `?`). Items whose name starts with
`Soul (` are enemy souls. The strength upgrades (`IsGet.Armor_Child_Gauntlet_Goron`, `..._Adult_Gauntlet_Silver`,
`..._Adult_Gauntlet_Gold`), the Lens of Truth (`IsGet.Armor_GlassTruth`) and the Fire Arrows (`IsGet.Item_Arrow_Fire`)
have no chest actor to lead to their flags: the exporter adds their rules (`tracking_metadata.EXTRA_INVENTORY`),
also to the files of seeds made before it did.

### Keys (24 bytes each)

One row per dungeon with small keys or a boss key to follow.

| Offset | Type | Field |
|---|---|---|
| 0 | u32 | dungeon name: string offset |
| 4 | u8 | flags: 1 = has small keys, 2 = has a boss key, 4 = every small key counts as found, 8 = the boss key counts as found |
| 5 | u8 | small key total |
| 6 | u16 | reserved (0) |
| 8 | u32 | Int hash of the keys found so far |
| 12 | u32 | Int hash of the keys held |
| 16 | u32 | Bool hash of the key ring's get flag (`IsGet.Item_KeyRing_<dungeon>`), 0 if the seed has no ring there |
| 20 | u32 | Bool hash of the boss key: its item's get flag (`IsGet.Item_BossKey_<dungeon>`) if it is an item of the seed, else `DungeonInfo.<folder>.IsGetBossKey` |

Small keys found = the larger of the two Int values, or the total when the key ring flag is true or flag 4 is set.
The boss key is held when its Bool is true or flag 8 is set. The key items' get flags are set as soon as they are
obtained; the flags the item-get hook sets when it applies them (`RandoKeyRing.<folder>`, `IsGetBossKey`) can lag
behind (saves of 13/11: Ganon's Castle's ring obtained, not applied). Files made before 0.2.1 named those; the
exporter now names the get flags, also when it rewrites an older seed's file (`update-tracker`).

## The items' icons (`icons.bin`)

Optional. The application writes it from the player's own game file when it generates a seed, or with
`update-tracker --nup GAME.nup`; nothing of the game ships with the application. Each icon is the game's own
picture (RomFS `UI/Tex/Icon/<name>.bntx.zs`, decompressed; for the spiritual stones and the medallions, which the
pause screen shows as models, the file select's pictures `DataFileImportantIcon_00` to `_08` in the archive
`UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs`) copied as its BNTX stores the first level: ASTC 4x4
blocks in the GPU's block-linear layout, with the BNTX's description of that layout. Nothing is decoded on the PC:
the module makes NVN textures of the bytes. The writer and the reference reader are
`src/oot_rando/tracker/ingame_icons.py` (`build`, `parse`); the module checks the same bounds
(`ingame_tracker/src/iconfile.c`), and shows the items' letters if the file is missing or fails.

Everything is little-endian. The header, the index, then the pictures, each starting 16-byte aligned.

### Header (32 bytes)

| Offset | Type | Field |
|---|---|---|
| 0 | char[4] | magic `RTIC` |
| 4 | u16 | version (1) |
| 6 | u16 | header size (32) |
| 8 | u32 | file size |
| 12 | u32 | icon count (1 to 40) |
| 16 | u32 | index offset (32) |
| 20 | u32 | entry size (64) |
| 24 | u32 | data offset: index offset + count × 64 |
| 28 | u32 | reserved (0) |

### Index entry (64 bytes each)

| Offset | Type | Field |
|---|---|---|
| 0 | char[32] | the item, NUL-terminated, as the module's grid names it (`ingame_tracker/src/grid.c`), or `Small Key` / `Boss Key` for the keys row; at most one entry per name |
| 32 | u32 | width (1 to 4096) |
| 36 | u32 | height (1 to 4096) |
| 40 | u32 | picture offset: 16-byte aligned, at or after the data offset |
| 44 | u32 | picture size: at least its 4x4 blocks × 16 bytes, at most 4 MiB, within the file |
| 48 | u8[8] | the BNTX's packaged texture layout (BRTI + 0x34), as stored |
| 56 | u8[4] | the channels' sources (BRTI + 0x58), as NVN swizzle values: 0 zero, 1 one, 2 to 5 red, green, blue, alpha |
| 60 | u32 | the BNTX's format: 0x2D01 ASTC 4x4 unorm, 0x2D06 ASTC 4x4 sRGB |

The entries follow the panel's grid, then the keys (`Item_Dungeon_SmallKey`, `Item_Dungeon_BossKey`): 38 with
the game of 13/11. An item whose picture the game lacks (another version of the game) has no entry and shows as its
letters. The Megaton Hammer's picture is `Item_Hammer_PouchIcon` (683 pixels), not `Item_Hammer` (1440). The
stones' and medallions' pictures (133 pixels) are read from the archive as it decompresses, only as far as the last
of them; no other of its 878 textures is kept.

## What the module reads from the game

For each hash the module asks the game's save data (GameData) for a Bool or Int by hash, or for a Bool64bitKey
record by key. These are the same flags the desktop tracker reads from `progress.sav` or from the game memory.
Seeds generated before this file existed have no `seed.trk`: the module stays idle for them. A seed generated by
an earlier version gets this version's file and module with `update-tracker` (see the README), and the icons with `--nup`; its other
files stay as they are.
