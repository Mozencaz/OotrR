#include "sizes.h"

float sizes_panel_width(const panel_shape_t *shape)
{
  return shape->settings_rows ? SETTINGS_PANEL_WIDTH_FP : PANEL_WIDTH_FP;
}

float sizes_panel_height(const panel_shape_t *shape)
{
  float h = 2 * PAD_Y_FP + TITLE_ROW_FP + TITLE_GAP_FP + shape->status_lines * STATUS_ROW_FP;
  if (shape->list)
    return h + LIST_HEAD_ROW_FP + BROWSE_CHECK_ROWS * LIST_ROW_FP + SECTION_GAP_FP + LIST_DETAIL_ROWS * DETAIL_ROW_FP +
           HINT_ROW_FP;
  if (shape->settings_rows)
    return h + LIST_HEAD_ROW_FP + shape->settings_rows * SETTING_ROW_FP + SECTION_GAP_FP + HINT_ROW_FP;
  if (shape->tracking)
    h += CELLS_BLOCK_FP + SECTION_GAP_FP + HINT_ROW_FP;
  if (shape->has_keys)
    h += KEYS_ROW_FP + SECTION_GAP_FP;
  if (shape->has_summary)
    h += SUMMARY_ROW_FP + SECTION_GAP_FP;
  return h + shape->region_rows * REGION_ROW_FP;
}

uint32_t sizes_key_rows(uint32_t key_count, uint32_t columns)
{
  return (key_count + columns - 1) / columns;
}

float sizes_card_width(void)
{
  return GRID_COLUMNS * CARD_CELL_W_FP + 2 * CARD_PAD_FP;
}

float sizes_card_height(uint32_t key_count)
{
  uint32_t rows = sizes_key_rows(key_count, CARD_KEY_COLUMNS);
  return 2 * CARD_PAD_FP + CELLS_BLOCK_FP + (rows ? SECTION_GAP_FP + rows * KEYS_ROW_FP : 0) + SECTION_GAP_FP +
         COUNTER_ROW_FP;
}

box_t sizes_card_box(const postcard_settings_t *settings, uint32_t key_count, float area_w)
{
  float scale = postcard_scale(settings);
  box_t card = { 0, 0, sizes_card_width() * scale, sizes_card_height(key_count) * scale };
  postcard_origin((postcard_position_t)settings->position, area_w, PICTURE_HEIGHT_FP, card.w, card.h, MARGIN_FP,
                  &card.x, &card.y);
  return card;
}

static bool overlap(const box_t *a, const box_t *b)
{
  return a->x < b->x + b->w + CONSOLE_GAP_FP && b->x < a->x + a->w + CONSOLE_GAP_FP &&
         a->y < b->y + b->h + CONSOLE_GAP_FP && b->y < a->y + a->h + CONSOLE_GAP_FP;
}

/* at the top or the bottom: sideways, then narrower, then over or under the card */
static void clear_wide(box_t *box, float area_w, const box_t *card)
{
  bool card_right = card->x + card->w / 2 > area_w / 2;
  float x = card_right ? card->x - CONSOLE_GAP_FP - box->w : card->x + card->w + CONSOLE_GAP_FP;
  if (x >= MARGIN_FP && x + box->w <= area_w - MARGIN_FP) {
    box->x = x;
    return;
  }
  float room = card_right ? card->x - CONSOLE_GAP_FP - MARGIN_FP : area_w - MARGIN_FP - (card->x + card->w + CONSOLE_GAP_FP);
  if (room >= CONSOLE_MIN_WIDE_W_FP) {
    box->w = room;
    box->x = card_right ? MARGIN_FP : card->x + card->w + CONSOLE_GAP_FP;
    return;
  }
  bool at_bottom = box->y + box->h / 2 > PICTURE_HEIGHT_FP / 2;
  box->y = at_bottom ? card->y - CONSOLE_GAP_FP - box->h : card->y + card->h + CONSOLE_GAP_FP;
}

/* at the left or the right: up or down, then beside the card */
static void clear_tall(box_t *box, const box_t *card)
{
  bool card_low = card->y + card->h / 2 > PICTURE_HEIGHT_FP / 2;
  float y = card_low ? card->y - CONSOLE_GAP_FP - box->h : card->y + card->h + CONSOLE_GAP_FP;
  if (y >= MARGIN_FP && y + box->h <= PICTURE_HEIGHT_FP - MARGIN_FP) {
    box->y = y;
    return;
  }
  bool card_left = card->x < box->x + box->w / 2;
  box->x = card_left ? card->x + card->w + CONSOLE_GAP_FP : card->x - CONSOLE_GAP_FP - box->w;
}

box_t sizes_console_box(console_position_t position, int lines, float area_w, const box_t *card)
{
  bool wide = position == CONSOLE_BOTTOM || position == CONSOLE_TOP;
  float room = area_w - 2 * MARGIN_FP, w = wide ? CONSOLE_WIDE_W_FP : CONSOLE_TALL_W_FP;
  box_t box = { 0, 0, w < room ? w : room, lines * CONSOLE_ROW_FP + 2 * CONSOLE_PAD_Y_FP };
  switch (position) {
    case CONSOLE_TOP: box.y = MARGIN_FP; break;
    case CONSOLE_LEFT: box.x = MARGIN_FP; break;
    case CONSOLE_RIGHT: box.x = area_w - MARGIN_FP - box.w; break;
    default: box.y = PICTURE_HEIGHT_FP - MARGIN_FP - box.h; break;
  }
  if (wide)
    box.x = (area_w - box.w) / 2;
  else
    box.y = (PICTURE_HEIGHT_FP - box.h) / 2;
  if (!card || !overlap(&box, card))
    return box;
  if (wide)
    clear_wide(&box, area_w, card);
  else
    clear_tall(&box, card);
  return box;
}
