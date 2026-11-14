/* Browsing the panel: a highlight moves over the regions (shown in columns, filled top to bottom), A opens the
 * highlighted region's checks as a list that scrolls, B goes back to the regions. Pure: app.c hands it the
 * commands and the counts. */
#ifndef BROWSE_H
#define BROWSE_H

#include <stdbool.h>
#include <stdint.h>

#define BROWSE_REGION_COLUMNS 3
#define BROWSE_CHECK_ROWS     18 /* a region's checks shown at once */

typedef enum { BROWSE_REGIONS, BROWSE_CHECKS } browse_view_t;
typedef enum { NAV_UP, NAV_DOWN, NAV_LEFT, NAV_RIGHT } nav_t;

typedef struct {
  browse_view_t view;
  uint32_t region; /* the highlighted region */
  uint32_t check;  /* in its list: the highlighted check, */
  uint32_t top;    /* and the first one shown */
} browse_t;

/* How many rows the regions' columns have. */
uint32_t browse_region_rows(uint32_t region_count);
/* The regions again, with the highlight where it was (kept inside `region_count`). */
void browse_show_regions(browse_t *browse, uint32_t region_count);
/* Up and down step through the regions in order (down a column, then the next one), left and right go to the
 * next column; in a list, up and down step through the checks, left and right a page. `check_count`: the
 * highlighted region's checks. */
void browse_move(browse_t *browse, nav_t nav, uint32_t region_count, uint32_t check_count);
/* A: the highlighted region's list, from its top. */
void browse_open(browse_t *browse, uint32_t region_count);
/* B: back to the regions; false if they were shown already (B then closes the panel). */
bool browse_back(browse_t *browse);

#endif
