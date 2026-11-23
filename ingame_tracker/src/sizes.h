/* The panel's, the postcard's and the console's sizes in font pixels (fp: a 360th of the picture's height, so a size is the same
 * share of the screen at 720p and 1080p). Pure, so the tests can check that they fit on the screen. */
#ifndef SIZES_H
#define SIZES_H

#include <stdbool.h>
#include <stdint.h>

#include "browse.h"
#include "console.h"
#include "grid.h"
#include "postcard.h"

#define PICTURE_HEIGHT_FP 360.0f

#define MARGIN_FP         8
#define PANEL_WIDTH_FP    560
#define SETTINGS_PANEL_WIDTH_FP 320 /* the panel showing a settings page */
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
#define COUNTER_ROW_FP    13   /* the postcard's last row: the Skulltula count */
#define REGION_ROW_FP     10
#define HINT_ROW_FP       12
#define LIST_HEAD_ROW_FP  14
#define LIST_ROW_FP       11
#define LIST_DETAIL_ROWS  2    /* under a region's list: the highlighted check's name and id, where it is (locate.h) */
#define DETAIL_ROW_FP     11
#define SETTING_ROW_FP    14
#define CARD_CELL_W_FP    22   /* the postcard at full size: item cells this wide, so the icons are nearly square */
#define CARD_PAD_FP       5
#define CARD_KEY_COLUMNS  3
#define MAX_STATUS_LINES  2    /* the lines of warnings under the title (not this seed's save, goal reached) */
#define CONSOLE_WIDE_W_FP 380  /* the console at the top or the bottom */
#define CONSOLE_MIN_WIDE_W_FP 260 /* ... narrowed to keep clear of the postcard */
#define CONSOLE_TALL_W_FP 180  /* at the left or the right */
#define CONSOLE_ROW_FP    10
#define CONSOLE_PAD_X_FP  5
#define CONSOLE_PAD_Y_FP  3
#define CONSOLE_GAP_FP    4    /* kept between the console and the postcard */
#define MARK_BAND_W_FP    240  /* at most: the band naming the check shown in the world (locate.h), the panel closed */
#define MARK_ROW_FP       10

/* the items' rows, a gap, the songs' rows */
#define CELLS_BLOCK_FP (GRID_ROWS * GRID_ROW_FP + SONGS_GAP_FP + SONG_ROWS * SONG_ROW_FP)

/* what decides the panel's height */
typedef struct {
  int status_lines;
  bool tracking;      /* the cells, the hint and what follows them are shown */
  bool list;          /* a region's list of checks */
  uint32_t settings_rows; /* a settings page's rows (0: it isn't one) */
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

typedef struct { float x, y, w, h; } box_t;
/* The postcard's box in an area area_w wide and PICTURE_HEIGHT_FP high (font pixels of the picture), in the
 * corner its settings choose. */
box_t sizes_card_box(const postcard_settings_t *settings, uint32_t key_count, float area_w);
/* The console's box for `lines` lines in the same area, at its position, kept clear of `card` (NULL: none shown):
 * at the top or the bottom it moves sideways, then narrows to CONSOLE_MIN_WIDE_W_FP, then goes over or under the
 * card; at the left or the right it moves up or down, then beside the card. Its lines fill it from the bottom
 * (from the top at the top). */
box_t sizes_console_box(console_position_t position, int lines, float area_w, const box_t *card);

#endif
