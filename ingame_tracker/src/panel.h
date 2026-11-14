/* What the panel shows, handed from the game's controller thread (app.c) to its present thread (overlay.c). */
#ifndef PANEL_H
#define PANEL_H

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
} panel_t;

#endif
