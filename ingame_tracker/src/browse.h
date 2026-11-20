/* Browsing the panel: a highlight moves over the regions (shown in columns, filled top to bottom) and the Settings
 * entry after them. A opens the highlighted region's checks as a list that scrolls, or the Settings page, whose two
 * entries open the postcard's settings and the console's; B goes back a page.
 * Pure: app.c hands it the commands and the counts. */
#ifndef BROWSE_H
#define BROWSE_H

#include <stdbool.h>
#include <stdint.h>

#include "console.h"
#include "postcard.h"

#define BROWSE_REGION_COLUMNS 3
#define BROWSE_CHECK_ROWS     18 /* a region's checks shown at once */

typedef enum {
  BROWSE_REGIONS, BROWSE_CHECKS,
  BROWSE_SETTINGS, /* the Settings page: the postcard and the console */
  BROWSE_POSTCARD, /* the postcard's settings */
  BROWSE_CONSOLE,  /* the console's settings and its kinds of message */
} browse_view_t;
typedef enum { NAV_UP, NAV_DOWN, NAV_LEFT, NAV_RIGHT } nav_t;
/* the Settings page's entries, in order */
typedef enum { SETTINGS_POSTCARD, SETTINGS_CONSOLE, SETTINGS_ENTRY_COUNT } settings_entry_t;

typedef struct {
  browse_view_t view;
  uint32_t region;  /* the highlighted region; the region count is the Settings entry */
  uint32_t check;   /* in a region's list: the highlighted check, */
  uint32_t top;     /* and the first one shown */
  uint32_t entry;   /* on the Settings page: the highlighted entry (settings_entry_t) */
  uint32_t setting; /* in the postcard's or the console's settings: the highlighted one */
} browse_t;

/* How many rows the columns have: the regions and the Settings entry after them. */
uint32_t browse_region_rows(uint32_t region_count);
/* The rows of a settings page (0 if the view isn't one), and the highlighted row of the one shown. */
uint32_t browse_page_rows(browse_view_t view);
uint32_t browse_page_row(const browse_t *browse);
/* The page shown when the panel last closed, with its highlight, kept inside the regions and the Settings entry
 * and, in a list, inside its `check_count` checks. */
void browse_reopen(browse_t *browse, uint32_t region_count, uint32_t check_count);
/* Up and down step through the regions in order (down a column, then the next one), left and right go to the
 * next column; in a list, up and down step through the checks, left and right a page; on a settings page, up and
 * down step through its rows (left and right change a value: app.c's). `check_count`: the highlighted region's
 * checks. */
void browse_move(browse_t *browse, nav_t nav, uint32_t region_count, uint32_t check_count);
/* A: the highlighted region's list from its top, the Settings page, or the highlighted page of it. Elsewhere it
 * does nothing here (on a kind's row of the console's page app.c ticks it). */
void browse_open(browse_t *browse, uint32_t region_count);
/* B: back a page (a list and the Settings page go back to the regions); false if the regions were shown already
 * (B then closes the panel). */
bool browse_back(browse_t *browse);

#endif
