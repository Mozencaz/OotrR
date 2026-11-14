/* The tracker panel in the game's own style (see trackerui.h). The box, the gold title over a hairline and
 * the type are sloperinaGZ's menu in its game style, at its sizes: a font pixel is a 360th of the picture's
 * height (3 pixels at 1080p). The sections follow OotrR's overlay: the items in rows (their icons, from the
 * seed's icons.bin, once they're in; their letters until then or without it), the dungeons' keys, the
 * checks found by region, one of them highlighted; or, with a region's list open, its checks. */
#include "trackerui.h"

#include "gamefile.h"
#include "gamefont.h"
#include "gpuui.h"
#include "iconfile.h"
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
#define KEY_ICON_FP       11   /* the keys row's icons */
#define KEY_ICON_GAP_FP   2    /* between the small key's icon and its count */
#define SUMMARY_ROW_FP    13
#define REGION_ROW_FP     11
#define REGION_COLUMNS    BROWSE_REGION_COLUMNS
#define REGION_COLUMN_GAP_FP 12
#define REGION_NAME_GAP_FP   4 /* between a region's name and its count */
#define HIGHLIGHT_PAD_FP  3    /* the highlight band reaches this far left and right of its row */
#define HIGHLIGHT_BAR_FP  1    /* its gold edge on the left */
#define HINT_ROW_FP       12
#define LIST_HEAD_ROW_FP  14
#define LIST_ROW_FP       11
#define TICK_BOX_FP       5    /* a check's box */
#define TICK_GAP_FP       5    /* between the box and the name */
#define TICK_LINE_FP      0.6f /* an empty box's outline */

/* opacities */
#define BOX_OPACITY        0.86f
#define RULE_OPACITY       0.6f
#define CELL_OWNED_ALPHA   0.85f
#define CELL_MISSING_ALPHA 0.10f
#define CELL_UNKNOWN_ALPHA 0.04f
#define HIGHLIGHT_ALPHA    0.16f

#define MAX_STATUS_LINES 2
#define STATUS_ROOM      80
#define NAME_ROOM        64
#define ELLIPSIS         ".."
#define COUNT_ROOM       24
#define HINT_REGIONS     "D-pad: choose a region     A: its checks     B: close"
#define ICON_FILE        GAME_ROM "/RandoTracker/icons.bin"
#define SMALL_KEY_ICON   "Small Key" /* the keys' entries in it, after the grid's items */
#define BOSS_KEY_ICON    "Boss Key"
_Static_assert(ICONFILE_MAX <= GPUUI_ICONS, "an atlas slot for each icon");
#define HINT_LIST        "D-pad: scroll (left / right: a page)     B: back to the regions"

static const rgb_t box_colour = { 0x0A, 0x09, 0x08 };
static const rgb_t title_colour = { 0xF5, 0xD6, 0x85 };
static const rgb_t text_colour = { 0xEC, 0xE8, 0xDE };
static const rgb_t white = { 0xFF, 0xFF, 0xFF };
static const rgb_t dim_colour = { 0x96, 0x91, 0x87 };
static const rgb_t faint_colour = { 0x5A, 0x57, 0x52 };
static const rgb_t warning_colour = { 0xFF, 0x9A, 0x7A };
static const rgb_t done_colour = { 0x9A, 0xDF, 0x9A };
static const gpu_colour_t icon_owned = { 1, 1, 1, 1 };
static const gpu_colour_t icon_missing = { 0.55f, 0.55f, 0.55f, 0.4f };
static const gpu_colour_t icon_unknown = { 0.5f, 0.5f, 0.5f, 0.18f };

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

/* --- the items' icons: on the render thread, one in every other frame the panel is drawn --------- */

static struct {
  enum { ICONS_UNREAD, ICONS_LOADING, ICONS_IN, ICONS_NONE } state;
  icon_index_t index;
  uint64_t file_size;
  uint32_t next;                /* the next entry to bring in */
  int8_t cell_icon[GRID_CELLS]; /* each grid cell's icon (its entry and atlas slot), or -1 */
  int8_t small_key, boss_key;   /* the keys row's, or -1 */
} icon_ui;

static bool icon_used(uint32_t entry)
{
  if ((int8_t)entry == icon_ui.small_key || (int8_t)entry == icon_ui.boss_key)
    return true;
  int cell = grid_index_of(icon_ui.index.entries[entry].name);
  return cell >= 0 && icon_ui.cell_icon[cell] == (int8_t)entry;
}

/* the icons file's index, and the GPU's room for its pictures */
static void icons_start(void)
{
  static uint8_t head[ICONFILE_HEAD_MAX];
  icon_ui.state = ICONS_NONE;
  for (int i = 0; i < GRID_CELLS; i++)
    icon_ui.cell_icon[i] = -1;
  icon_ui.small_key = icon_ui.boss_key = -1;
  const char *why = "";
  int64_t got = gamefile_read_at(ICON_FILE, 0, head, sizeof(head), &icon_ui.file_size);
  if (got < 0) {
    log_printf("no %s: the items show as their letters", ICON_FILE);
    return;
  }
  if (!iconfile_parse(&icon_ui.index, head, (size_t)got, icon_ui.file_size, &why)) {
    log_printf("%s refused: %s; the items show as their letters", ICON_FILE, why);
    return;
  }
  int used = 0;
  for (uint32_t i = 0; i < icon_ui.index.count; i++) {
    const char *name = icon_ui.index.entries[i].name;
    int cell = grid_index_of(name);
    int8_t *icon = cell >= 0 ? &icon_ui.cell_icon[cell] : text_equal(name, SMALL_KEY_ICON) ? &icon_ui.small_key
                 : text_equal(name, BOSS_KEY_ICON) ? &icon_ui.boss_key : 0;
    if (icon && *icon < 0) {
      *icon = (int8_t)i;
      used++;
    }
  }
  if (used && gpuui_icons_init(icon_ui.index.largest))
    icon_ui.state = ICONS_LOADING;
}

/* the next picture into the atlas, when the GPU can take one; the picture memory back once they're all in */
static void icons_step(void)
{
  if (icon_ui.state == ICONS_UNREAD)
    icons_start();
  if (icon_ui.state != ICONS_LOADING)
    return;
  while (icon_ui.next < icon_ui.index.count && !icon_used(icon_ui.next))
    icon_ui.next++;
  if (icon_ui.next == icon_ui.index.count) {
    if (gpuui_icons_done())
      icon_ui.state = ICONS_IN;
    return;
  }
  uint8_t *memory = gpuui_icon_staging();
  if (!memory)
    return;
  const icon_entry_t *e = &icon_ui.index.entries[icon_ui.next];
  gpuui_picture_t picture = { (int)e->width, (int)e->height, e->size, { 0 }, { 0 } };
  memcpy(picture.layout, e->layout, sizeof(picture.layout));
  memcpy(picture.swizzle, e->swizzle, sizeof(picture.swizzle));
  uint64_t file_size = 0;
  if (gamefile_read_at(ICON_FILE, e->offset, memory, e->size, &file_size) != (int64_t)e->size ||
      file_size != icon_ui.file_size || !gpuui_icon_bake((int)icon_ui.next, &picture))
    log_printf("the icon of %s didn't go in: it shows as its letters", e->name);
  icon_ui.next++;
}

/* --- what the panel holds ---------------------------------------------------------------------- */

typedef struct {
  char text[STATUS_ROOM];
  const rgb_t *colour;
} status_line_t;

typedef struct {
  status_line_t status[MAX_STATUS_LINES];
  int status_count;
  bool tracking, has_keys, has_summary, list;
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
    content.list = panel->browse.view == BROWSE_CHECKS && panel->browse.region < panel->state.region_count;
    content.has_keys = !content.list && panel->state.key_count > 0;
    content.has_summary = !content.list;
    content.region_rows = content.list ? 0 : (int)browse_region_rows(panel->state.region_count);
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
  if (content->list)
    return h + LIST_HEAD_ROW_FP + BROWSE_CHECK_ROWS * LIST_ROW_FP + SECTION_GAP_FP + HINT_ROW_FP;
  if (content->tracking)
    h += GRID_ROWS * GRID_ROW_FP + SECTION_GAP_FP + HINT_ROW_FP;
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

/* icon entry `icon` (-1: none) as a square of `side` at (x, y); false if it isn't in (yet) */
static bool draw_icon_at(int icon, float x, float y, float side, gpu_colour_t colour)
{
  if (icon < 0 || (icon_ui.state != ICONS_LOADING && icon_ui.state != ICONS_IN) || !gpuui_icon_ready(icon))
    return false;
  gpuui_icon(icon, x, y, side, side, colour);
  return true;
}

/* the cell's icon, a square as tall as the cell in its middle; false if it has none (yet) */
static bool draw_icon(int index, cell_state_t state, float x, float y, float w, float h)
{
  return draw_icon_at(icon_ui.cell_icon[index], x + (w - h) / 2, y, h,
                      state.status == ITEM_OWNED ? icon_owned : state.status == ITEM_MISSING ? icon_missing : icon_unknown);
}

static void draw_cell(const layout_t *l, int index, cell_state_t state, float x, float y, float w, float h)
{
  const grid_cell_t *cell = grid_cell(index);
  bool owned = state.status == ITEM_OWNED, leveled = owned && cell->levels > 1;
  float alpha = owned ? CELL_OWNED_ALPHA : state.status == ITEM_MISSING ? CELL_MISSING_ALPHA : CELL_UNKNOWN_ALPHA;
  gpuui_fill(x, y, w, h, to_gpu(owned ? rgb_from_hex(cell->colour) : white, alpha));
  rgb_t colour = owned ? white : state.status == ITEM_MISSING ? dim_colour : faint_colour;
  float baseline = baseline_in(&l->bold, y, h), pad = CELL_LEVEL_PAD_FP * l->fp;
  if (!draw_icon(index, state, x, y, w, h))
    draw_text(&l->bold, cell->abbr, leveled ? x + pad : x + (w - text_width(&l->bold, cell->abbr)) / 2, baseline, colour);
  if (state.status == ITEM_UNKNOWN) /* the game has none of its flags: not the same as missing */
    draw_text(&l->body, "?", x + w - pad - text_width(&l->body, "?"), baseline, dim_colour);
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
    draw_cell(l, i, state->cells[i], x + gap / 2, top + gap / 2, cell_w - gap, row - gap);
  }
  return y + GRID_ROWS * row + SECTION_GAP_FP * l->fp;
}

/* a dungeon's keys: its medallion's icon (else its letters), the small key's icon and the keys found, then the boss
 * key's icon, dim until it is held (without the icons, a "B") */
static void draw_dungeon_keys(const layout_t *l, const dungeon_keys_t *keys, float x, float y, float row)
{
  char abbr[ABBR_MAX], line[COUNT_ROOM];
  float baseline = baseline_in(&l->bold, y, row), side = KEY_ICON_FP * l->fp, top = y + (row - side) / 2;
  float space = l->body.em / 2;
  const char *medallion = grid_dungeon_medallion(keys->name);
  int cell = medallion ? grid_index_of(medallion) : -1;
  if (cell >= 0 && draw_icon_at(icon_ui.cell_icon[cell], x, top, side, icon_owned)) {
    x += side + space;
  } else {
    grid_dungeon_abbr(keys->name, abbr);
    x += draw_text(&l->bold, abbr, x, baseline, title_colour) + space;
  }
  if (keys->has_small_keys) {
    if (draw_icon_at(icon_ui.small_key, x, top, side, icon_owned))
      x += side + KEY_ICON_GAP_FP * l->fp;
    if (keys->small_keys_known)
      snprintf(line, sizeof(line), "%u/%u", (unsigned)keys->found, (unsigned)keys->total);
    else
      snprintf(line, sizeof(line), "?/%u", (unsigned)keys->total);
    x += draw_text(&l->body, line, x, baseline, text_colour) + space;
  }
  if (keys->boss == BOSS_KEY_NONE)
    return;
  bool held = keys->boss == BOSS_KEY_HELD;
  if (!draw_icon_at(icon_ui.boss_key, x, top, side,
                    held ? icon_owned : keys->boss == BOSS_KEY_MISSING ? icon_missing : icon_unknown))
    draw_text(&l->bold, "B", x, baseline, held ? white : faint_colour);
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

/* the band behind the highlighted row, with its gold edge */
static void draw_highlight(const layout_t *l, float x, float y, float w, float h)
{
  float pad = HIGHLIGHT_PAD_FP * l->fp;
  gpuui_fill(x - pad, y, w + 2 * pad, h, to_gpu(title_colour, HIGHLIGHT_ALPHA));
  gpuui_fill(x - pad, y, HIGHLIGHT_BAR_FP * l->fp, h, to_gpu(title_colour, 1));
}

static void draw_hint(const layout_t *l, const char *hint, float y)
{
  draw_text(&l->body, hint, l->inner_x, baseline_in(&l->body, y, HINT_ROW_FP * l->fp), dim_colour);
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

static float draw_regions(const layout_t *l, const panel_t *panel, int rows, float y)
{
  const tracker_state_t *state = &panel->state;
  float gap = REGION_COLUMN_GAP_FP * l->fp, row = REGION_ROW_FP * l->fp;
  float column_w = (l->inner_w - (REGION_COLUMNS - 1) * gap) / REGION_COLUMNS;
  for (uint32_t i = 0; i < state->region_count; i++) {
    int column = (int)i / rows, line = (int)i % rows;
    float x = l->inner_x + column * (column_w + gap), top = y + line * row;
    if (i == panel->browse.region)
      draw_highlight(l, x, top, column_w, row);
    draw_region(l, &state->regions[i], x, column_w, top, row);
  }
  return y + rows * row;
}

/* --- a region's list of checks ------------------------------------------------------------------ */

static float draw_list_heading(const layout_t *l, const panel_t *panel, float y)
{
  const region_state_t *region = &panel->state.regions[panel->browse.region];
  char count[COUNT_ROOM * 2];
  float row = LIST_HEAD_ROW_FP * l->fp, baseline = baseline_in(&l->bold, y, row);
  draw_text(&l->bold, region->name, l->inner_x, baseline, title_colour);
  uint32_t first = panel->row_count ? panel->browse.top + 1 : 0, last = panel->browse.top + panel->row_count;
  snprintf(count, sizeof(count), "%u / %u found     %u-%u of %u", (unsigned)region->collected,
           (unsigned)region->trackable, (unsigned)first, (unsigned)last, (unsigned)region->trackable);
  draw_text(&l->body, count, l->inner_x + l->inner_w - text_width(&l->body, count), baseline, dim_colour);
  return y + row;
}

/* a check's box: filled when it's collected, empty when it's missing, a question mark when the game can't say */
static void draw_tick_box(const layout_t *l, gd_flag_t flag, float x, float y, float row)
{
  float box = TICK_BOX_FP * l->fp, top = (float)(int)(y + (row - box) / 2);
  float line = TICK_LINE_FP * l->fp < MIN_LINE_PX ? MIN_LINE_PX : (float)(int)(TICK_LINE_FP * l->fp + 0.5f);
  if (flag == GD_TRUE) {
    gpuui_fill(x, top, box, box, to_gpu(done_colour, 1));
  } else if (flag == GD_FALSE) {
    gpu_colour_t edge = to_gpu(white, 1);
    gpuui_fill(x, top, box, line, edge);
    gpuui_fill(x, top + box - line, box, line, edge);
    gpuui_fill(x, top, line, box, edge);
    gpuui_fill(x + box - line, top, line, box, edge);
  } else {
    draw_text(&l->bold, "?", x, baseline_in(&l->bold, y, row), faint_colour);
  }
}

static void draw_check_row(const layout_t *l, const check_row_t *check, float y, float row)
{
  char unnamed[COUNT_ROOM], name[NAME_ROOM];
  const char *text = check->name;
  if (!text[0]) { /* a seed file made before the checks had names */
    snprintf(unnamed, sizeof(unnamed), "Check %u", (unsigned)check->number);
    text = unnamed;
  }
  draw_tick_box(l, (gd_flag_t)check->flag, l->inner_x, y, row);
  float x = l->inner_x + (TICK_BOX_FP + TICK_GAP_FP) * l->fp;
  fit_name(l, text, l->inner_x + l->inner_w - x, name);
  rgb_t colour = check->flag == GD_TRUE ? done_colour : check->flag == GD_FALSE ? white : faint_colour;
  draw_text(&l->body, name, x, baseline_in(&l->body, y, row), colour);
}

static float draw_list(const layout_t *l, const panel_t *panel, float y)
{
  float row = LIST_ROW_FP * l->fp;
  for (uint32_t i = 0; i < panel->row_count; i++) {
    float top = y + i * row;
    if (panel->browse.top + i == panel->browse.check)
      draw_highlight(l, l->inner_x, top, l->inner_w, row);
    draw_check_row(l, &panel->rows[i], top, row);
  }
  return y + BROWSE_CHECK_ROWS * row + SECTION_GAP_FP * l->fp;
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
  if (content.list) {
    y = draw_list(&l, panel, draw_list_heading(&l, panel, y));
    draw_hint(&l, HINT_LIST, y);
    return;
  }
  y = draw_grid(&l, &panel->state, y);
  if (content.has_keys)
    y = draw_keys(&l, &panel->state, y);
  y = draw_summary(&l, &panel->state, y);
  draw_hint(&l, HINT_REGIONS, draw_regions(&l, panel, content.region_rows, y));
}

bool trackerui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                      nvn_rect_t area, const panel_t *panel)
{
  if (area.h <= 0 || panel->mode == PANEL_HIDDEN)
    return false;
  if (gpuui_atlas_resetting() && !slots_wait_idle())
    return false;
  gpuui_begin(texture, area, info->height, nvn_origin_lower_left(), slot);
  icons_step();
  draw_panel(panel, area);
  return gpuui_end(cmd, nvn_game_texture_pool(), nvn_game_sampler_pool());
}
