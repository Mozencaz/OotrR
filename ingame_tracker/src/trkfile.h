/* The seed file the randomizer writes (RandoTracker/seed.trk): which save flags to observe, grouped
 * by region, the items' flags, the seed's markers. The layout is in docs/ingame-tracker-format.md at the root
 * of the OotrR repository (the randomizer writes the file). Parsing checks every
 * offset and count, so a damaged file is refused, never read past its end. Reading is zero-copy: the
 * accessors decode a record out of the file's bytes, which must stay in place while the trk_t is used. */
#ifndef TRKFILE_H
#define TRKFILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TRK_VERSION 1
#define TRK_MAX_REGIONS 64  /* the module keeps a fixed-size state per region */
#define TRK_MAX_KEY_ROWS 16 /* ... and per dungeon with keys */

enum { TRK_KIND_BOOL = 1, TRK_KIND_BOOL64 = 2 };
enum { TRK_KEY_SMALL = 1, TRK_KEY_BOSS = 2, TRK_KEY_SMALL_ALL = 4, TRK_KEY_BOSS_ALL = 8 };

typedef struct { uint32_t name, first_check, check_count; } trk_region_t;
typedef struct { uint64_t key; uint32_t kind; } trk_check_t;
typedef struct { uint32_t name, first_rule, rule_count; } trk_item_t;
typedef struct { uint32_t hash, level; } trk_rule_t;
typedef struct {
  uint32_t name, flags, small_total;
  uint32_t found_hash, held_hash, ring_hash, boss_hash;
} trk_keys_t;

typedef struct {
  const uint8_t *data;
  size_t size;
  uint32_t seed_marker, goal_marker; /* Bool hashes; goal_marker 0: the seed has none */
  uint32_t seed_id;                  /* string offset */
  uint32_t strings_at, strings_size;
  uint32_t regions_at, region_count;
  uint32_t checks_at, check_count;
  uint32_t items_at, item_count;
  uint32_t rules_at, rule_count;
  uint32_t keys_at, key_count;
} trk_t;

/* Validates `data` and fills `trk`. False with *why set if the file isn't a version 1 seed file or any
 * of its parts leaves the file. */
bool trk_parse(trk_t *trk, const uint8_t *data, size_t size, const char **why);

/* The NUL-terminated string at `offset` in the string table ("" if the offset is outside it). */
const char *trk_string(const trk_t *trk, uint32_t offset);

/* Records by index (< the table's count). */
trk_region_t trk_region(const trk_t *trk, uint32_t index);
trk_check_t trk_check(const trk_t *trk, uint32_t index);
trk_item_t trk_item(const trk_t *trk, uint32_t index);
trk_rule_t trk_rule(const trk_t *trk, uint32_t index);
trk_keys_t trk_keys(const trk_t *trk, uint32_t index);

#endif
