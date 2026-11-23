#include "browse.h"

/* the regions, then the Settings entry */
static uint32_t entry_count(uint32_t region_count)
{
  return region_count + 1;
}

uint32_t browse_region_rows(uint32_t region_count)
{
  return (entry_count(region_count) + BROWSE_REGION_COLUMNS - 1) / BROWSE_REGION_COLUMNS;
}

uint32_t browse_page_rows(browse_view_t view)
{
  switch (view) {
    case BROWSE_SETTINGS: return SETTINGS_ENTRY_COUNT;
    case BROWSE_POSTCARD: return POSTCARD_SETTING_COUNT;
    case BROWSE_CONSOLE: return CONSOLE_SETTING_COUNT;
    default: return 0;
  }
}

/* the highlighted row of the settings page shown */
static uint32_t *page_row(browse_t *browse)
{
  switch (browse->view) {
    case BROWSE_SETTINGS: return &browse->entry;
    default: return &browse->setting;
  }
}

uint32_t browse_page_row(const browse_t *browse)
{
  return *page_row((browse_t *)browse);
}

void browse_reopen(browse_t *browse, uint32_t region_count, uint32_t check_count)
{
  if (browse->region > region_count)
    browse->region = region_count;
  if (browse->view != BROWSE_CHECKS)
    return;
  if (browse->region == region_count) { /* the Settings entry has no list */
    browse->view = BROWSE_REGIONS;
    return;
  }
  uint32_t last = check_count ? check_count - 1 : 0;
  if (browse->check > last)
    browse->check = last;
  if (browse->top > browse->check)
    browse->top = browse->check;
  else if (browse->check >= browse->top + BROWSE_CHECK_ROWS)
    browse->top = browse->check - BROWSE_CHECK_ROWS + 1;
}

static void move_over_regions(browse_t *browse, nav_t nav, uint32_t region_count)
{
  uint32_t count = entry_count(region_count);
  uint32_t rows = browse_region_rows(region_count), at = browse->region;
  if (nav == NAV_UP && at > 0)
    browse->region = at - 1;
  else if (nav == NAV_DOWN && at + 1 < count)
    browse->region = at + 1;
  else if (nav == NAV_LEFT && at >= rows)
    browse->region = at - rows;
  else if (nav == NAV_RIGHT && at + rows < count)
    browse->region = at + rows;
  else if (nav == NAV_RIGHT && (at / rows + 1) * rows < count) /* the next column is shorter: its last region */
    browse->region = count - 1;
}

static void move_over_checks(browse_t *browse, nav_t nav, uint32_t count)
{
  uint32_t at = browse->check, last = count ? count - 1 : 0;
  if (nav == NAV_UP)
    at = at > 0 ? at - 1 : 0;
  else if (nav == NAV_DOWN)
    at = at < last ? at + 1 : last;
  else if (nav == NAV_LEFT)
    at = at > BROWSE_CHECK_ROWS ? at - BROWSE_CHECK_ROWS : 0;
  else
    at = last - at > BROWSE_CHECK_ROWS ? at + BROWSE_CHECK_ROWS : last;
  browse->check = at;
  if (at < browse->top)
    browse->top = at;
  else if (at >= browse->top + BROWSE_CHECK_ROWS)
    browse->top = at - BROWSE_CHECK_ROWS + 1;
}

static void move_over_page(browse_t *browse, nav_t nav)
{
  uint32_t *row = page_row(browse);
  if (nav == NAV_UP && *row > 0)
    (*row)--;
  else if (nav == NAV_DOWN && *row + 1 < browse_page_rows(browse->view))
    (*row)++;
}

void browse_move(browse_t *browse, nav_t nav, uint32_t region_count, uint32_t check_count)
{
  if (browse->view == BROWSE_CHECKS)
    move_over_checks(browse, nav, check_count);
  else if (browse->view == BROWSE_REGIONS)
    move_over_regions(browse, nav, region_count);
  else
    move_over_page(browse, nav);
}

static void open_from_regions(browse_t *browse, uint32_t region_count)
{
  if (browse->region > region_count)
    return;
  if (browse->region == region_count) {
    browse->view = BROWSE_SETTINGS;
    browse->entry = 0;
    return;
  }
  browse->view = BROWSE_CHECKS;
  browse->check = browse->top = 0;
}

void browse_open(browse_t *browse, uint32_t region_count)
{
  switch (browse->view) {
    case BROWSE_REGIONS:
      open_from_regions(browse, region_count);
      return;
    case BROWSE_SETTINGS:
      browse->view = browse->entry == SETTINGS_CONSOLE ? BROWSE_CONSOLE : BROWSE_POSTCARD;
      browse->setting = 0;
      return;
    default:
      return;
  }
}

bool browse_back(browse_t *browse)
{
  switch (browse->view) {
    case BROWSE_REGIONS: return false;
    case BROWSE_POSTCARD:
    case BROWSE_CONSOLE: browse->view = BROWSE_SETTINGS; return true;
    default: browse->view = BROWSE_REGIONS; return true;
  }
}
