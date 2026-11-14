/* The panel's and the postcard's sizes in font pixels (fp: a 360th of the picture's height, so a size is the same
 * share of the screen at 720p and 1080p). Pure, so the tests can check that they fit on the screen. */
#ifndef SIZES_H
#define SIZES_H

#include <stdbool.h>
#include <stdint.h>

#include "browse.h"
#include "grid.h"
#include "postcard.h"

#define PICTURE_HEIGHT_FP 360.0f

#define MARGIN_FP         8
#define PANEL_WIDTH_FP    560
#define POSTCARD_PANEL_WIDTH_FP 320 /* the panel showing the postcard's settings */
#define PAD_Y_FP          12
#define TITLE_ROW_FP      15
#define TITLE_GAP_FP      9
#define STATUS_ROW_FP     12
#define SECTION_GAP_FP    6
#define GRID_ROW_FP       18
#define SONGS_GAP_FP      2    /* between the items and the songs */
#define SONG_ROW_FP       14
#define KEYS_ROW_FP       13
#define SUMMARY_ROW_FP    13
#define REGION_ROW_FP     10
#define HINT_ROW_FP       12
#define LIST_HEAD_ROW_FP  14
#define LIST_ROW_FP       11
#define SETTING_ROW_FP    14
#define CARD_CELL_W_FP    22   /* the postcard at full size: item cells this wide, so the icons are nearly square */
#define CARD_PAD_FP       5
#define CARD_KEY_COLUMNS  3
#define MAX_STATUS_LINES  2    /* the lines of warnings under the title (not this seed's save, goal reached) */

/* the items' rows, a gap, the songs' rows */
#define CELLS_BLOCK_FP (GRID_ROWS * GRID_ROW_FP + SONGS_GAP_FP + SONG_ROWS * SONG_ROW_FP)

/* what decides the panel's height */
typedef struct {
  int status_lines;
  bool tracking;      /* the cells, the hint and what follows them are shown */
  bool list;          /* a region's list of checks */
  bool postcard_page; /* the postcard's settings */
  bool has_keys, has_summary;
  uint32_t region_rows;
} panel_shape_t;

float sizes_panel_width(const panel_shape_t *shape);
float sizes_panel_height(const panel_shape_t *shape);
/* How many rows `key_count` dungeons take in `columns` columns. */
uint32_t sizes_key_rows(uint32_t key_count, uint32_t columns);
/* The postcard at full size (it is scaled by postcard_scale): its box for `key_count` dungeons with keys. */
float sizes_card_width(void);
float sizes_card_height(uint32_t key_count);

#endif
