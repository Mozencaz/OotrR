/* The tracker panel in the game's own style (see trackerui.h). The box, the gold title over a hairline and
 * the type are sloperinaGZ's menu in its game style, at its sizes: a font pixel is a 360th of the picture's
 * height (3 pixels at 1080p). The sections follow OotrR's overlay: the items in rows, the dungeons' keys, the
 * checks found by region. */
#include "trackerui.h"

#include "gamefont.h"
#include "gpuui.h"
#include "slots.h"
#include "sys.h"
#include "text.h"
#include "uishader.h"
#include "uitext.h"

#define PICTURE_LINES_PER_FP 360.0f
#define MIN_LINE_PX          1.0f
#define LINE_FP              0.5f /* a hairline's thickness */

/* sizes in font pixels (fp) */
#define MARGIN_FP         8
#define PANEL_WIDTH_FP    560
#define PAD_X_FP          14
#define PAD_Y_FP          12
#define TITLE_ROW_FP      15
#define TITLE_TEXT_FP     11
#define TITLE_GAP_FP      9
#define TITLE_RULE_AT     0.42f /* of the gap under the title row */
#define BODY_TEXT_FP      8
#define STATUS_ROW_FP     12
#define SECTION_GAP_FP    8
#define GRID_ROW_FP       20
#define CELL_GAP_FP       2
#define CELL_LEVEL_PAD_FP 3
#define KEYS_ROW_FP       13
#define SUMMARY_ROW_FP    13
#define REGION_ROW_FP     11
#define REGION_COLUMNS    3
#define REGION_COLUMN_GAP_FP 12
#define REGION_NAME_GAP_FP   4 /* between a region's name and its count */

/* opacities */
#define BOX_OPACITY        0.86f
#define RULE_OPACITY       0.6f
#define CELL_OWNED_ALPHA   0.85f
#define CELL_MISSING_ALPHA 0.10f
#define CELL_UNKNOWN_ALPHA 0.04f

#define MAX_STATUS_LINES 2
#define STATUS_ROOM      80
#define NAME_ROOM        64
#define ELLIPSIS         ".."
#define COUNT_ROOM       24

static const rgb_t box_colour = { 0x0A, 0x09, 0x08 };
static const rgb_t title_colour = { 0xF5, 0xD6, 0x85 };
static const rgb_t text_colour = { 0xEC, 0xE8, 0xDE };
static const rgb_t white = { 0xFF, 0xFF, 0xFF };
static const rgb_t dim_colour = { 0x96, 0x91, 0x87 };
static const rgb_t faint_colour = { 0x5A, 0x57, 0x52 };
static const rgb_t warning_colour = { 0xFF, 0x9A, 0x7A };
static const rgb_t done_colour = { 0x9A, 0xDF, 0x9A };

/* what loading the game's files came to: set on the game thread, read on the render thread */
static enum { LOAD_NONE, LOAD_OK, LOAD_FAILED } load_state;
static enum { GPU_NONE, GPU_READY, GPU_FAILED } gpu_state;

void trackerui_load(void)
{
  if (__atomic_load_n(&load_state, __ATOMIC_ACQUIRE) != LOAD_NONE)
    return;
  /* the shader first: both read the same zstd dictionary, which the font loader lets go of */
  bool ok = uishader_load() && gamefont_load();
  if (!ok)
    log_printf("the game's font or UI shader can't be read: no panel");
  __atomic_store_n(&load_state, ok ? LOAD_OK : LOAD_FAILED, __ATOMIC_RELEASE);
}

bool trackerui_usable(void)
{
  if (gpu_state == GPU_READY)
    return true;
  if (gpu_state == GPU_FAILED || __atomic_load_n(&load_state, __ATOMIC_ACQUIRE) != LOAD_OK)
    return false;
  gpu_state = gpuui_init() ? GPU_READY : GPU_FAILED;
  if (gpu_state == GPU_FAILED)
    log_printf("game-style drawing can't start: no panel");
  return gpu_state == GPU_READY;
}

/* --- what the panel holds ---------------------------------------------------------------------- */

typedef struct {
  char text[STATUS_ROOM];
  const rgb_t *colour;
} status_line_t;

typedef struct {
  status_line_t status[MAX_STATUS_LINES];
  int status_count;
  bool tracking, has_keys, has_summary;
  int region_rows;
} content_t;

static void add_status(content_t *content, const char *text, const rgb_t *colour)
{
  status_line_t *line = &content->status[content->status_count++];
  text_copy(line->text, sizeof(line->text), text);
  line->colour = colour;
}

static void add_tracking_status(content_t *content, const tracker_state_t *state)
{
  if (state->link == SAVE_OF_ANOTHER)
    add_status(content, "This save is not from this seed", &warning_colour);
  else if (state->link == SAVE_LINK_UNKNOWN)
    add_status(content, "No flags of this seed in the game: is the seed enabled?", &warning_colour);
  if (state->goal_reached)
    add_status(content, "Goal reached", &done_colour);
}

static content_t content_of(const panel_t *panel)
{
  content_t content = { .tracking = panel->mode == PANEL_TRACKING };
  switch (panel->mode) {
    case PANEL_UNSUPPORTED_BUILD: add_status(&content, "Game version not supported", &warning_colour); break;
    case PANEL_WAITING_FOR_GAME_DATA: add_status(&content, "Waiting for the game's save data", &dim_colour); break;
    case PANEL_TRACKING: add_tracking_status(&content, &panel->state); break;
    case PANEL_HIDDEN: break;
  }
  if (content.tracking) {
    content.has_keys = panel->state.key_count > 0;
    content.has_summary = true;
    content.region_rows = (int)((panel->state.region_count + REGION_COLUMNS - 1) / REGION_COLUMNS);
  }
  return content;
}

/* --- layout ------------------------------------------------------------------------------------ */

typedef struct {
  float fp;          /* screen pixels per font pixel */
  float line;        /* a hairline's thickness */
  type_t title, body, bold;
  float x, y, w, h;  /* the box */
  float inner_x, inner_w;
} layout_t;

static float content_height_fp(const content_t *content)
{
  float h = 2 * PAD_Y_FP + TITLE_ROW_FP + TITLE_GAP_FP + content->status_count * STATUS_ROW_FP;
  if (content->tracking)
    h += GRID_ROWS * GRID_ROW_FP + SECTION_GAP_FP;
  if (content->has_keys)
    h += KEYS_ROW_FP + SECTION_GAP_FP;
  if (content->has_summary)
    h += SUMMARY_ROW_FP + SECTION_GAP_FP;
  return h + content->region_rows * REGION_ROW_FP;
}

static layout_t layout_for(const content_t *content, nvn_rect_t area)
{
  layout_t l;
  l.fp = area.h / PICTURE_LINES_PER_FP;
  l.line = l.fp * LINE_FP < MIN_LINE_PX ? MIN_LINE_PX : (float)(int)(l.fp * LINE_FP + 0.5f);
  l.title = type_for(GF_BOLD, TITLE_TEXT_FP, l.fp);
  l.body = type_for(GF_REGULAR, BODY_TEXT_FP, l.fp);
  l.bold = type_for(GF_BOLD, BODY_TEXT_FP, l.fp);
  float room = area.w - 2 * MARGIN_FP * l.fp;
  l.w = PANEL_WIDTH_FP * l.fp < room ? PANEL_WIDTH_FP * l.fp : room;
  l.h = content_height_fp(content) * l.fp;
  l.x = (float)(int)((area.w - l.w) / 2);
  l.y = (float)(int)(MARGIN_FP * l.fp);
  l.inner_x = l.x + PAD_X_FP * l.fp;
  l.inner_w = l.w - 2 * PAD_X_FP * l.fp;
  return l;
}

/* --- sections: each draws at `y` and returns where the next one starts ------------------------- */

static float draw_header(const layout_t *l, const panel_t *panel, float y)
{
  float row = TITLE_ROW_FP * l->fp;
  draw_text(&l->title, "Randomizer tracker", l->inner_x, baseline_in(&l->title, y, row), title_colour);
  if (panel->seed_id[0]) {
    char seed[SEED_ID_ROOM + 8];
    snprintf(seed, sizeof(seed), "seed %s", panel->seed_id);
    float x = l->inner_x + l->inner_w - text_width(&l->body, seed);
    draw_text(&l->body, seed, x, baseline_in(&l->body, y, row), dim_colour);
  }
  float gap = TITLE_GAP_FP * l->fp, over = PAD_X_FP * l->fp / 2;
  gpuui_fill(l->inner_x - over, y + row + gap * TITLE_RULE_AT - l->line / 2, l->inner_w + 2 * over, l->line,
             to_gpu(dim_colour, RULE_OPACITY));
  return y + row + gap;
}

static float draw_status(const layout_t *l, const content_t *content, float y)
{
  float row = STATUS_ROW_FP * l->fp;
  for (int i = 0; i < content->status_count; i++) {
    draw_text(&l->bold, content->status[i].text, l->inner_x, baseline_in(&l->bold, y, row), *content->status[i].colour);
    y += row;
  }
  return y;
}

static void draw_cell(const layout_t *l, const grid_cell_t *cell, cell_state_t state, float x, float y, float w, float h)
{
  bool owned = state.status == ITEM_OWNED, leveled = owned && cell->levels > 1;
  float alpha = owned ? CELL_OWNED_ALPHA : state.status == ITEM_MISSING ? CELL_MISSING_ALPHA : CELL_UNKNOWN_ALPHA;
  gpuui_fill(x, y, w, h, to_gpu(owned ? rgb_from_hex(cell->colour) : white, alpha));
  rgb_t colour = owned ? white : state.status == ITEM_MISSING ? dim_colour : faint_colour;
  float baseline = baseline_in(&l->bold, y, h), pad = CELL_LEVEL_PAD_FP * l->fp;
  draw_text(&l->bold, cell->abbr, leveled ? x + pad : x + (w - text_width(&l->bold, cell->abbr)) / 2, baseline, colour);
  if (leveled) {
    char digit[2] = { (char)('0' + (state.level > 9 ? 9 : state.level)), 0 };
    draw_text(&l->body, digit, x + w - pad - text_width(&l->body, digit), baseline, white);
  }
}

static float draw_grid(const layout_t *l, const tracker_state_t *state, float y)
{
  float cell_w = l->inner_w / GRID_COLUMNS, row = GRID_ROW_FP * l->fp, gap = CELL_GAP_FP * l->fp;
  for (int i = 0; i < GRID_CELLS; i++) {
    float x = l->inner_x + (i % GRID_COLUMNS) * cell_w, top = y + (i / GRID_COLUMNS) * row;
    draw_cell(l, grid_cell(i), state->cells[i], x + gap / 2, top + gap / 2, cell_w - gap, row - gap);
  }
  return y + GRID_ROWS * row + SECTION_GAP_FP * l->fp;
}

static void draw_dungeon_keys(const layout_t *l, const dungeon_keys_t *keys, float x, float y, float row)
{
  char abbr[ABBR_MAX], line[COUNT_ROOM];
  grid_dungeon_abbr(keys->name, abbr);
  float baseline = baseline_in(&l->bold, y, row);
  x += draw_text(&l->bold, abbr, x, baseline, title_colour) + l->body.em / 2;
  if (keys->has_small_keys) {
    if (keys->small_keys_known)
      snprintf(line, sizeof(line), "%u/%u", (unsigned)keys->found, (unsigned)keys->total);
    else
      snprintf(line, sizeof(line), "?/%u", (unsigned)keys->total);
    x += draw_text(&l->body, line, x, baseline, text_colour) + l->body.em / 2;
  }
  if (keys->boss != BOSS_KEY_NONE)
    draw_text(&l->bold, "B", x, baseline, keys->boss == BOSS_KEY_HELD ? white : faint_colour);
}

static float draw_keys(const layout_t *l, const tracker_state_t *state, float y)
{
  float row = KEYS_ROW_FP * l->fp, column_w = l->inner_w / (float)state->key_count;
  for (uint32_t i = 0; i < state->key_count; i++)
    draw_dungeon_keys(l, &state->keys[i], l->inner_x + i * column_w, y, row);
  return y + row + SECTION_GAP_FP * l->fp;
}

static float draw_summary(const layout_t *l, const tracker_state_t *state, float y)
{
  char line[COUNT_ROOM * 2];
  float row = SUMMARY_ROW_FP * l->fp, baseline = baseline_in(&l->bold, y, row);
  snprintf(line, sizeof(line), "Checks %u / %u", (unsigned)state->collected, (unsigned)state->trackable);
  float x = l->inner_x + draw_text(&l->bold, line, l->inner_x, baseline, white) + l->body.em;
  if (state->unreadable) {
    snprintf(line, sizeof(line), "%u unreadable", (unsigned)state->unreadable);
    draw_text(&l->body, line, x, baseline, dim_colour);
  }
  if (state->souls_total) {
    snprintf(line, sizeof(line), "Souls %u/%u", (unsigned)state->souls_owned, (unsigned)state->souls_total);
    draw_text(&l->body, line, l->inner_x + l->inner_w - text_width(&l->body, line), baseline, text_colour);
  }
  return y + row + SECTION_GAP_FP * l->fp;
}

/* The region's name cut with ".." so that it is no wider than `room`. */
static void fit_name(const layout_t *l, const char *name, float room, char out[NAME_ROOM])
{
  int length = (int)text_copy(out, NAME_ROOM, name);
  if (text_width_n(&l->body, out, length) <= room)
    return;
  float ellipsis = text_width(&l->body, ELLIPSIS);
  while (length > 0 && text_width_n(&l->body, out, length) + ellipsis > room)
    length--;
  text_copy(out + length, NAME_ROOM - length, ELLIPSIS);
}

static void draw_region(const layout_t *l, const region_state_t *region, float x, float column_w, float y, float row)
{
  char count[COUNT_ROOM], name[NAME_ROOM];
  snprintf(count, sizeof(count), "%u/%u", (unsigned)region->collected, (unsigned)region->trackable);
  float count_w = text_width(&l->body, count), baseline = baseline_in(&l->body, y, row);
  bool done = region->collected == region->trackable, none = region->collected == 0;
  fit_name(l, region->name, column_w - count_w - REGION_NAME_GAP_FP * l->fp, name);
  draw_text(&l->body, name, x, baseline, done ? done_colour : none ? dim_colour : text_colour);
  draw_text(&l->body, count, x + column_w - count_w, baseline, done ? done_colour : none ? dim_colour : white);
}

static void draw_regions(const layout_t *l, const tracker_state_t *state, int rows, float y)
{
  float gap = REGION_COLUMN_GAP_FP * l->fp, row = REGION_ROW_FP * l->fp;
  float column_w = (l->inner_w - (REGION_COLUMNS - 1) * gap) / REGION_COLUMNS;
  for (uint32_t i = 0; i < state->region_count; i++) {
    int column = (int)i / rows, line = (int)i % rows;
    draw_region(l, &state->regions[i], l->inner_x + column * (column_w + gap), column_w, y + line * row, row);
  }
}

static void draw_panel(const panel_t *panel, nvn_rect_t area)
{
  content_t content = content_of(panel);
  layout_t l = layout_for(&content, area);
  gpuui_fill(l.x, l.y, l.w, l.h, to_gpu(box_colour, BOX_OPACITY));
  float y = draw_header(&l, panel, l.y + PAD_Y_FP * l.fp);
  y = draw_status(&l, &content, y);
  if (!content.tracking)
    return;
  y = draw_grid(&l, &panel->state, y);
  if (content.has_keys)
    y = draw_keys(&l, &panel->state, y);
  y = draw_summary(&l, &panel->state, y);
  draw_regions(&l, &panel->state, content.region_rows, y);
}

bool trackerui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                      nvn_rect_t area, const panel_t *panel)
{
  if (area.h <= 0 || panel->mode == PANEL_HIDDEN)
    return false;
  if (gpuui_atlas_resetting() && !slots_wait_idle())
    return false;
  gpuui_begin(texture, area, info->height, nvn_origin_lower_left(), slot);
  draw_panel(panel, area);
  return gpuui_end(cmd, nvn_game_texture_pool(), nvn_game_sampler_pool());
}
