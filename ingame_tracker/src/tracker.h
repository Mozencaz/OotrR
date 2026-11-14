/* What the panel shows, worked out from the seed file and the game's save data. Pure: it only asks the
 * flag source, so the tests run it on the PC with a table in place of the game. */
#ifndef TRACKER_H
#define TRACKER_H

#include <stdbool.h>
#include <stdint.h>

#include "flags.h"
#include "grid.h"
#include "trkfile.h"

typedef enum { ITEM_UNKNOWN, ITEM_MISSING, ITEM_OWNED } item_status_t;
typedef enum { BOSS_KEY_NONE, BOSS_KEY_UNKNOWN, BOSS_KEY_MISSING, BOSS_KEY_HELD } boss_key_t;
typedef enum { SAVE_LINK_UNKNOWN, SAVE_OF_THIS_SEED, SAVE_OF_ANOTHER } save_link_t;

typedef struct {
  uint8_t level; /* 0 when not owned */
  uint8_t status; /* item_status_t */
} cell_state_t;

typedef struct {
  const char *name;
  bool has_small_keys;
  bool small_keys_known;
  uint16_t found, total;
  uint8_t boss; /* boss_key_t */
} dungeon_keys_t;

typedef struct {
  const char *name;
  uint32_t collected, trackable;
} region_state_t;

typedef struct {
  save_link_t link;
  bool goal_reached;
  cell_state_t cells[GRID_CELLS];
  uint32_t souls_owned, souls_total;
  dungeon_keys_t keys[TRK_MAX_KEY_ROWS];
  uint32_t key_count;
  region_state_t regions[TRK_MAX_REGIONS];
  uint32_t region_count;
  uint32_t collected, trackable;
  uint32_t unreadable; /* trackable checks whose flag the game doesn't have: not counted as collected */
} tracker_state_t;

typedef struct {
  const char *name; /* points into the seed file; "" if the file has no names (version 1) */
  uint32_t number;  /* its place in its region, from 1 */
  uint8_t flag;     /* gd_flag_t: collected, missing or unknown */
} check_row_t;

void tracker_compute(const trk_t *seed, const flag_source_t *flags, tracker_state_t *state);
/* Up to `room` of region `region`'s checks from its `first`; how many were filled. */
uint32_t tracker_check_rows(const trk_t *seed, const flag_source_t *flags, uint32_t region, uint32_t first,
                            check_row_t *rows, uint32_t room);

#endif
