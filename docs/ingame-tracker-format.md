# In-game tracker: seed file format

Every seed folder written by the application carries the data the in-game tracker reads:

* `romfs/RandoTracker/seed.trk` — this file, listed in `manifest.json` under `files` with its size and SHA-256;
* `exefs/subsdk7` — the prebuilt tracker module, listed under `exefs` in the manifest.

The module is a separate GPL-3 project (source: <https://github.com/waze3174/ootr-ingame-tracker>). It reads
`content:/RandoTracker/seed.trk` and compares it with the running game's save flags. It only reads memory.

`seed.trk` holds no placement: no item or reward of any check. It lists which flags to observe, grouped by the
region names the desktop tracker shows. The writer is `src/oot_rando/tracker/ingame_format.py` (`build`); `parse`
there is the reference reader the tests use. The module validates the same bounds and ignores a file that fails.

## Layout

Everything is little-endian. Offsets are from the start of the file. Tables follow the header in this order:
string table, regions, checks, items, rules, keys; each table starts 4-byte aligned.

### Header (72 bytes)

| Offset | Type | Field |
|---|---|---|
| 0 | char[4] | magic `RTRK` |
| 4 | u16 | version (1) |
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
lies inside the file. Newer versions may add tables or fields; a reader of version 1 refuses other versions.
Version 1 holds at most 64 regions and 16 key rows (the module keeps a fixed-size state for each); the writer
refuses more.

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
| 12 | u32 | reserved (0) |

A check is collected when the game's flag for its key reads true. A key the game does not know is unknown, not
false. Bool64bitKey keys live in a table that is sorted at the start and followed by unsorted records appended by
the seed: a lookup binary-searches the sorted head and scans the tail.

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
item's flags exists in the game, the item is unknown. Items whose name starts with `Soul (` are enemy souls.

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
| 16 | u32 | Bool hash of the applied key ring, 0 if none |
| 20 | u32 | Bool hash of the boss key |

Small keys found = the larger of the two Int values, or the total when the key ring flag is true or flag 4 is set.
The boss key is held when its Bool is true or flag 8 is set.

## What the module reads from the game

For each hash the module asks the game's save data (GameData) for a Bool or Int by hash, or for a Bool64bitKey
record by key. These are the same flags the desktop tracker reads from `progress.sav` or from the game memory.
Seeds generated before this file existed have no `seed.trk`: the module stays idle for them.
