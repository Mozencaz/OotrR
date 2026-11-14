#include "browse.h"

uint32_t browse_region_rows(uint32_t region_count)
{
  return (region_count + BROWSE_REGION_COLUMNS - 1) / BROWSE_REGION_COLUMNS;
}

void browse_show_regions(browse_t *browse, uint32_t region_count)
{
  browse->view = BROWSE_REGIONS;
  if (browse->region >= region_count)
    browse->region = region_count ? region_count - 1 : 0;
}

static void move_over_regions(browse_t *browse, nav_t nav, uint32_t count)
{
  uint32_t rows = browse_region_rows(count), at = browse->region;
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

void browse_move(browse_t *browse, nav_t nav, uint32_t region_count, uint32_t check_count)
{
  if (browse->view == BROWSE_CHECKS)
    move_over_checks(browse, nav, check_count);
  else if (region_count)
    move_over_regions(browse, nav, region_count);
}

void browse_open(browse_t *browse, uint32_t region_count)
{
  if (browse->view != BROWSE_REGIONS || browse->region >= region_count)
    return;
  browse->view = BROWSE_CHECKS;
  browse->check = browse->top = 0;
}

bool browse_back(browse_t *browse)
{
  if (browse->view == BROWSE_REGIONS)
    return false;
  browse->view = BROWSE_REGIONS;
  return true;
}
