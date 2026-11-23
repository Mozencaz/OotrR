/* The items the panel shows, in rows, as the desktop tracker's in-game overlay groups them
 * (OotrR src/oot_rando/tracker/game_overlay.py, GRID), then the ocarina songs in two rows of six. An item is named
 * as the seed file names it. */
#ifndef GRID_H
#define GRID_H

#include <stdbool.h>
#include <stdint.h>

#define GRID_ROWS    4
#define GRID_COLUMNS 9
#define ITEM_CELLS   (GRID_ROWS * GRID_COLUMNS)
#define SONG_ROWS    2
#define SONG_COLUMNS 6
#define SONG_CELLS   (SONG_ROWS * SONG_COLUMNS)
#define GRID_CELLS   (ITEM_CELLS + SONG_CELLS) /* the cells: the items first, then the songs */
#define ABBR_MAX     4 /* an abbreviation's longest text, with its NUL */

typedef struct {
  const char *item;
  const char *abbr;
  uint8_t levels; /* how many levels the item has (the Hookshot's two: Hookshot, Longshot); 1 for a song */
  uint32_t colour; /* 0xRRGGBB when owned */
  bool counted; /* its level is how many of its rules' flags are set, not the highest (the bottles: one flag a slot) */
} grid_cell_t;

const grid_cell_t *grid_cell(int index);
/* The cell showing `item`, or -1. */
int grid_index_of(const char *item);
/* A dungeon's two-letter label for the keys row ("Fo" for the Forest Temple). */
void grid_dungeon_abbr(const char *dungeon, char out[ABBR_MAX]);
/* The medallion of a temple ("Forest Medallion" for the Forest Temple), whose icon labels its keys; NULL for a
 * dungeon without one (Bottom of the Well, Gerudo Training Ground, Ganon's Castle). */
const char *grid_dungeon_medallion(const char *dungeon);

#endif
