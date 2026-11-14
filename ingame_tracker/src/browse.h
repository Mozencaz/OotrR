/* Browsing the panel: a highlight moves over the regions (shown in columns, filled top to bottom) and the Postcard
 * entry after them, A opens the highlighted region's checks as a list that scrolls, or the postcard's settings,
 * B goes back. Pure: app.c hands it the commands and the counts. */
#ifndef BROWSE_H
#define BROWSE_H

#include <stdbool.h>
#include <stdint.h>

#include "postcard.h"

#define BROWSE_REGION_COLUMNS 3
#define BROWSE_CHECK_ROWS     18 /* a region's checks shown at once */

typedef enum { BROWSE_REGIONS, BROWSE_CHECKS, BROWSE_POSTCARD } browse_view_t;
typedef enum { NAV_UP, NAV_DOWN, NAV_LEFT, NAV_RIGHT } nav_t;

typedef struct {
  browse_view_t view;
  uint32_t region; /* the highlighted region; the region count is the Postcard entry */
  uint32_t check;  /* in a region's list: the highlighted check, */
  uint32_t top;    /* and the first one shown */
  uint32_t setting; /* in the postcard's settings: the highlighted one (postcard_setting_t) */
} browse_t;

/* How many rows the columns have: the regions and the Postcard entry after them. */
uint32_t browse_region_rows(uint32_t region_count);
/* The regions again, with the highlight where it was (kept inside the regions and the Postcard entry). */
void browse_show_regions(browse_t *browse, uint32_t region_count);
/* Up and down step through the regions in order (down a column, then the next one), left and right go to the
 * next column; in a list, up and down step through the checks, left and right a page; in the postcard's
 * settings, up and down step through them (left and right change a value: app.c's). `check_count`: the
 * highlighted region's checks. */
void browse_move(browse_t *browse, nav_t nav, uint32_t region_count, uint32_t check_count);
/* A: the highlighted region's list from its top, or the postcard's settings. */
void browse_open(browse_t *browse, uint32_t region_count);
/* B: back to the regions; false if they were shown already (B then closes the panel). */
bool browse_back(browse_t *browse);

#endif
