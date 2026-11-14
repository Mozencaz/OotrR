/* The items the panel shows, in rows, as the desktop tracker's in-game overlay groups them
 * (OotrR src/oot_rando/tracker/game_overlay.py, GRID). An item is named as the seed file names it. */
#ifndef GRID_H
#define GRID_H

#include <stdint.h>

#define GRID_ROWS    4
#define GRID_COLUMNS 9
#define GRID_CELLS   (GRID_ROWS * GRID_COLUMNS)
#define ABBR_MAX     4 /* an abbreviation's longest text, with its NUL */

typedef struct {
  const char *item;
  const char *abbr;
  uint8_t levels; /* how many levels the item has (the Hookshot's two: Hookshot, Longshot) */
  uint32_t colour; /* 0xRRGGBB when owned */
} grid_cell_t;

const grid_cell_t *grid_cell(int index);
/* The cell showing `item`, or -1. */
int grid_index_of(const char *item);
/* A dungeon's two-letter label for the keys row ("Fo" for the Forest Temple). */
void grid_dungeon_abbr(const char *dungeon, char out[ABBR_MAX]);

#endif
