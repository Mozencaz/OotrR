/* The seed file the randomizer writes (RandoTracker/seed.trk): which save flags to observe, grouped
 * by region, the items' flags, the seed's markers, and (version 4) each check's id and its places in the game's
 * maps. The layout is in docs/ingame-tracker-format.md at the root
 * of the OotrR repository (the randomizer writes the file). Parsing checks every
 * offset and count, so a damaged file is refused, never read past its end. Reading is zero-copy: the
 * accessors decode a record out of the file's bytes, which must stay in place while the trk_t is used. */
#ifndef TRKFILE_H
#define TRKFILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TRK_VERSION 4        /* 3: without the checks' ids and places; 2: nor the header's flags; 1: nor the names */
#define TRK_OLDEST_VERSION 1
#define TRK_MAX_REGIONS 64  /* the module keeps a fixed-size state per region */
#define TRK_MAX_KEY_ROWS 16 /* ... and per dungeon with keys */

enum { TRK_KIND_BOOL = 1, TRK_KIND_BOOL64 = 2 };
enum { TRK_KEY_SMALL = 1, TRK_KEY_BOSS = 2, TRK_KEY_SMALL_ALL = 4, TRK_KEY_BOSS_ALL = 8 };
enum { TRK_FLAG_ARCHIPELAGO = 1 }; /* the header's flags (version 3; 0 in older files: a local seed) */

typedef struct { uint32_t name, first_check, check_count; } trk_region_t;
/* A check's place (version 4): the map it is in, as the save's "map" string names it, that map's name to show and
 * the check's actor's position there (metres). The places are in check order. */
typedef struct { uint32_t check, map, label; float x, y, z; } trk_place_t;
typedef struct { uint64_t key; uint32_t kind, name; } trk_check_t; /* name: a string offset (0, "", in version 1) */
typedef struct { uint32_t name, first_rule, rule_count; } trk_item_t;
typedef struct { uint32_t hash, level; } trk_rule_t;
typedef struct {
  uint32_t name, flags, small_total;
  uint32_t found_hash, held_hash, ring_hash, boss_hash;
} trk_keys_t;

typedef struct {
  const uint8_t *data;
  size_t size;
  uint32_t version, header_size;
  uint32_t flags;
  uint32_t seed_marker, goal_marker; /* Bool hashes; goal_marker 0: the seed has none */
  uint32_t seed_id;                  /* string offset */
  uint32_t strings_at, strings_size;
  uint32_t regions_at, region_count;
  uint32_t checks_at, check_count;
  uint32_t items_at, item_count;
  uint32_t rules_at, rule_count;
  uint32_t keys_at, key_count;
  uint32_t idents_at, ident_count; /* version 4: one per check (0 in older files) */
  uint32_t places_at, place_count; /* version 4 */
} trk_t;

/* Validates `data` and fills `trk`. False with *why set if the file isn't a seed file of a version this module
 * reads (TRK_OLDEST_VERSION to TRK_VERSION) or any of its parts leaves the file. */
bool trk_parse(trk_t *trk, const uint8_t *data, size_t size, const char **why);

/* The NUL-terminated string at `offset` in the string table ("" if the offset is outside it). */
const char *trk_string(const trk_t *trk, uint32_t offset);

/* Records by index (< the table's count). */
trk_region_t trk_region(const trk_t *trk, uint32_t index);
trk_check_t trk_check(const trk_t *trk, uint32_t index);
trk_item_t trk_item(const trk_t *trk, uint32_t index);
trk_rule_t trk_rule(const trk_t *trk, uint32_t index);
trk_keys_t trk_keys(const trk_t *trk, uint32_t index);
trk_place_t trk_place(const trk_t *trk, uint32_t index);
/* Check `check`'s id (its internal key: a string offset, 0 when the file has none). */
uint32_t trk_check_ident(const trk_t *trk, uint32_t check);
/* How many places check `check` has, the first at *first. */
uint32_t trk_places_of(const trk_t *trk, uint32_t check, uint32_t *first);

#endif
