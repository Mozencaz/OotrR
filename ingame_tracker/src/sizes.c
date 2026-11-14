#include "sizes.h"

float sizes_panel_width(const panel_shape_t *shape)
{
  return shape->postcard_page ? POSTCARD_PANEL_WIDTH_FP : PANEL_WIDTH_FP;
}

float sizes_panel_height(const panel_shape_t *shape)
{
  float h = 2 * PAD_Y_FP + TITLE_ROW_FP + TITLE_GAP_FP + shape->status_lines * STATUS_ROW_FP;
  if (shape->list)
    return h + LIST_HEAD_ROW_FP + BROWSE_CHECK_ROWS * LIST_ROW_FP + SECTION_GAP_FP + HINT_ROW_FP;
  if (shape->postcard_page)
    return h + LIST_HEAD_ROW_FP + POSTCARD_SETTING_COUNT * SETTING_ROW_FP + SECTION_GAP_FP + HINT_ROW_FP;
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
  return 2 * CARD_PAD_FP + CELLS_BLOCK_FP + (rows ? SECTION_GAP_FP + rows * KEYS_ROW_FP : 0);
}
