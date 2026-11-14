/* What the panel shows, handed from the game's controller thread (app.c) to its present thread (overlay.c). */
#ifndef PANEL_H
#define PANEL_H

#include "browse.h"
#include "tracker.h"

#define SEED_ID_ROOM 24 /* the seed id as shown, with its NUL: the file holds 16 hexadecimal digits */

typedef enum {
  PANEL_HIDDEN,
  PANEL_UNSUPPORTED_BUILD, /* a game build whose memory this module doesn't know */
  PANEL_WAITING_FOR_GAME_DATA,
  PANEL_TRACKING,
} panel_mode_t;

typedef struct {
  panel_mode_t mode;
  char seed_id[SEED_ID_ROOM];
  tracker_state_t state; /* only meaningful when tracking; its names point into the seed file, kept for good */
  browse_t browse;
  uint32_t row_count;    /* with a region's list open: its checks from browse.top */
  check_row_t rows[BROWSE_CHECK_ROWS];
} panel_t;

#endif
