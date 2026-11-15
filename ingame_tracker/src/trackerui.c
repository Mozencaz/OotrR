/* The tracker panel in the game's own style (see trackerui.h). The box, the gold title over a hairline and
 * the type are sloperinaGZ's menu in its game style, at its sizes: a font pixel is a 360th of the picture's
 * height (3 pixels at 1080p). The sections follow OotrR's overlay: the items in rows and the ocarina songs under
 * them (their icons, from the seed's icons.bin, once they're in; their letters until then or without it), the
 * dungeons' keys, the checks found by region, one of them highlighted; or, with a region's list open, its checks.
 * The postcard is the items, the songs and the keys alone, as a smaller card in a corner, drawn with the same
 * code; the Archipelago console is the desktop client's latest lines in a band at an edge, each fading out. */
#include "trackerui.h"

#include "gamefile.h"
#include "gamefont.h"
#include "gpuui.h"
#include "iconfile.h"
#include "sizes.h"
#include "slots.h"
#include "sys.h"
#include "text.h"
#include "uishader.h"
#include "uitext.h"

#define MIN_LINE_PX          1.0f
#define LINE_FP              0.5f /* a hairline's thickness */

/* sizes in font pixels (fp) that don't decide the box's size (those are sizes.h's) */
#define PAD_X_FP          14
#define TITLE_TEXT_FP     11
#define TITLE_RULE_AT     0.42f /* of the gap under the title row */
#define BODY_TEXT_FP      8
#define CELL_GAP_FP       2
#define CELL_LEVEL_PAD_FP 3
#define KEY_ICON_FP       11   /* the keys row's icons */
#define KEY_ICON_GAP_FP   2    /* between the small key's icon and its count */
#define REGION_COLUMNS    BROWSE_REGION_COLUMNS
#define REGION_COLUMN_GAP_FP 12
#define REGION_NAME_GAP_FP   4 /* between a region's name and its count */
#define HIGHLIGHT_PAD_FP  3    /* the highlight band reaches this far left and right of its row */
#define HIGHLIGHT_BAR_FP  1    /* its gold edge on the left */
#define TICK_BOX_FP       5    /* a check's box */
#define TICK_GAP_FP       5    /* between the box and the name */
#define TICK_LINE_FP      0.6f /* an empty box's outline */
#define SETTING_VALUE_AT_FP 90 /* a setting's value, from the panel's inner edge */

/* opacities */
#define BOX_OPACITY        0.86f
#define RULE_OPACITY       0.6f
#define CELL_OWNED_ALPHA   0.85f
#define CELL_MISSING_ALPHA 0.10f
#define CELL_UNKNOWN_ALPHA 0.04f
#define HIGHLIGHT_ALPHA    0.16f

#define STATUS_ROOM      80
#define NAME_ROOM        64
#define ELLIPSIS         ".."
#define COUNT_ROOM       24
#define HINT_REGIONS     "D-pad: choose     A: open     B: close"
#define HINT_SETTINGS    "Up / down: choose     A: open     B: back"
#define HINT_POSTCARD    "Up / down: choose     Left / right: change     B: back"
#define HINT_CONSOLE     "Up / down: choose     Left / right or A: change     B: back"
#define SETTINGS_TITLE   "Settings"
#define NO_MESSAGES      "No messages yet"
#define CONSOLE_WRAP_ROWS 3 /* a console line takes at most this many rows; the rest is cut */
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
static const rgb_t notice_colour = { 0xC4, 0xBE, 0xB2 };
static const rgb_t kind_colours[CONSOLE_KIND_COUNT] = {
  [CONSOLE_RECEIVED] = { 0xF5, 0xD6, 0x85 }, [CONSOLE_SENT] = { 0x9A, 0xDF, 0x9A }, [CONSOLE_HINT] = { 0x9C, 0xC8, 0xFF },
  [CONSOLE_CHAT] = { 0xEC, 0xE8, 0xDE }, [CONSOLE_SERVER] = { 0xC4, 0xBE, 0xB2 }, [CONSOLE_OTHERS] = { 0xC8, 0xB4, 0xE6 },
};
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
  panel_shape_t shape;
} content_t;

static void add_status(content_t *content, const char *text, const rgb_t *colour)
{
  status_line_t *line = &content->status[content->shape.status_lines++];
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
  content_t content = { .shape = { .tracking = panel->mode == PANEL_TRACKING } };
  switch (panel->mode) {
    case PANEL_UNSUPPORTED_BUILD: add_status(&content, "Game version not supported", &warning_colour); break;
    case PANEL_WAITING_FOR_GAME_DATA: add_status(&content, "Waiting for the game's save data", &dim_colour); break;
    case PANEL_TRACKING: add_tracking_status(&content, &panel->state); break;
    case PANEL_HIDDEN: break;
  }
  panel_shape_t *shape = &content.shape;
  if (shape->tracking) {
    shape->list = panel->browse.view == BROWSE_CHECKS && panel->browse.region < panel->state.region_count;
    shape->settings_rows = browse_page_rows(panel->browse.view);
    bool regions = !shape->list && !shape->settings_rows;
    shape->has_keys = regions && panel->state.key_count > 0;
    shape->has_summary = regions;
    shape->region_rows = regions ? browse_region_rows(panel->state.region_count) : 0;
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

/* the fonts and the hairline for a font pixel of `fp` screen pixels; the box is the caller's */
static layout_t layout_scaled(float fp)
{
  layout_t l = { .fp = fp };
  l.line = fp * LINE_FP < MIN_LINE_PX ? MIN_LINE_PX : (float)(int)(fp * LINE_FP + 0.5f);
  l.title = type_for(GF_BOLD, TITLE_TEXT_FP, fp);
  l.body = type_for(GF_REGULAR, BODY_TEXT_FP, fp);
  l.bold = type_for(GF_BOLD, BODY_TEXT_FP, fp);
  return l;
}

static float picture_fp(nvn_rect_t area)
{
  return area.h / PICTURE_HEIGHT_FP;
}

static layout_t layout_for(const content_t *content, nvn_rect_t area)
{
  layout_t l = layout_scaled(picture_fp(area));
  float room = area.w - 2 * MARGIN_FP * l.fp;
  float width = sizes_panel_width(&content->shape) * l.fp;
  l.w = width < room ? width : room;
  l.h = sizes_panel_height(&content->shape) * l.fp;
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
  for (int i = 0; i < content->shape.status_lines; i++) {
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

/* `count` cells from `first`, `columns` to a row of `row_fp`, across the box's inner width; returns where they end */
static float draw_cells(const layout_t *l, const tracker_state_t *state, int first, int count, int columns,
                        float row_fp, float y)
{
  float cell_w = l->inner_w / columns, row = row_fp * l->fp, gap = CELL_GAP_FP * l->fp;
  for (int i = 0; i < count; i++) {
    float x = l->inner_x + (i % columns) * cell_w, top = y + (i / columns) * row;
    draw_cell(l, first + i, state->cells[first + i], x + gap / 2, top + gap / 2, cell_w - gap, row - gap);
  }
  return y + (count / columns) * row;
}

/* the items in their rows, the songs in theirs under them */
static float draw_grid(const layout_t *l, const tracker_state_t *state, float y)
{
  y = draw_cells(l, state, 0, ITEM_CELLS, GRID_COLUMNS, GRID_ROW_FP, y) + SONGS_GAP_FP * l->fp;
  y = draw_cells(l, state, ITEM_CELLS, SONG_CELLS, SONG_COLUMNS, SONG_ROW_FP, y);
  return y + SECTION_GAP_FP * l->fp;
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

/* the dungeons' keys, `columns` to a row, filled left to right */
static float draw_keys(const layout_t *l, const tracker_state_t *state, float y, uint32_t columns)
{
  float row = KEYS_ROW_FP * l->fp, column_w = l->inner_w / (float)columns;
  for (uint32_t i = 0; i < state->key_count; i++)
    draw_dungeon_keys(l, &state->keys[i], l->inner_x + (i % columns) * column_w, y + (i / columns) * row, row);
  return y + sizes_key_rows(state->key_count, columns) * row + SECTION_GAP_FP * l->fp;
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

/* `text` cut with ".." (also when `cut`) so that it is no wider than `room`, in `out` of `out_room` bytes. */
static void fit_text(const type_t *type, const char *text, float room, bool cut, char *out, size_t out_room)
{
  int length = (int)text_copy(out, out_room, text);
  if (!cut && text_width_n(type, out, length) <= room)
    return;
  float ellipsis = text_width(type, ELLIPSIS);
  while (length > 0 && text_width_n(type, out, length) + ellipsis > room)
    length--;
  text_copy(out + length, out_room - (size_t)length, ELLIPSIS);
}

/* The region's name cut with ".." so that it is no wider than `room`. */
static void fit_name(const layout_t *l, const char *name, float room, char out[NAME_ROOM])
{
  fit_text(&l->body, name, room, false, out, NAME_ROOM);
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

/* an entry of the columns: its name on the left, its value (a count, On or Off) on the right */
static void draw_entry(const layout_t *l, const char *name, const char *value, rgb_t name_colour, rgb_t value_colour,
                       float x, float column_w, float y, float row)
{
  char shown[NAME_ROOM];
  float value_w = text_width(&l->body, value), baseline = baseline_in(&l->body, y, row);
  fit_name(l, name, column_w - value_w - REGION_NAME_GAP_FP * l->fp, shown);
  draw_text(&l->body, shown, x, baseline, name_colour);
  draw_text(&l->body, value, x + column_w - value_w, baseline, value_colour);
}

static void draw_region(const layout_t *l, const region_state_t *region, float x, float column_w, float y, float row)
{
  char count[COUNT_ROOM];
  snprintf(count, sizeof(count), "%u/%u", (unsigned)region->collected, (unsigned)region->trackable);
  bool done = region->collected == region->trackable, none = region->collected == 0;
  draw_entry(l, region->name, count, done ? done_colour : none ? dim_colour : text_colour,
             done ? done_colour : none ? dim_colour : white, x, column_w, y, row);
}

/* the regions, then the Settings entry, in columns filled top to bottom */
static float draw_regions(const layout_t *l, const panel_t *panel, int rows, float y)
{
  const tracker_state_t *state = &panel->state;
  float gap = REGION_COLUMN_GAP_FP * l->fp, row = REGION_ROW_FP * l->fp;
  float column_w = (l->inner_w - (REGION_COLUMNS - 1) * gap) / REGION_COLUMNS;
  for (uint32_t i = 0; i <= state->region_count; i++) {
    int column = (int)i / rows, line = (int)i % rows;
    float x = l->inner_x + column * (column_w + gap), top = y + line * row;
    if (i == panel->browse.region)
      draw_highlight(l, x, top, column_w, row);
    if (i < state->region_count)
      draw_region(l, &state->regions[i], x, column_w, top, row);
    else
      draw_entry(l, SETTINGS_TITLE, "", text_colour, text_colour, x, column_w, top, row);
  }
  return y + rows * row;
}

/* --- the settings pages ------------------------------------------------------------------------- */

/* The Console page's rows after Fade are the console's kinds of message, each with a check box that shows or hides
 * it, as sloperinaGZ's watch list has a check box per watch for its on-screen box (src/ootgz/menus.c, "watches: the
 * list", GPL-3, master 5b44a21). */

typedef struct {
  const char *name;
  const char *value; /* NULL: a check box before the name instead */
  bool ticked;       /* ... ticked */
  bool arrows;       /* `< value >`: left and right change it */
} setting_row_t;

static setting_row_t settings_entry(const panel_t *panel, settings_entry_t entry)
{
  if (entry == SETTINGS_POSTCARD)
    return (setting_row_t){ postcard_setting_name(POSTCARD_SETTING_SHOWN),
                            postcard_value_text(&panel->postcard, POSTCARD_SETTING_SHOWN), false, false };
  return (setting_row_t){ console_setting_name(CONSOLE_SETTING_SHOWN),
                          console_value_text(&panel->console, CONSOLE_SETTING_SHOWN, panel->archipelago), false, false };
}

#define PAGE_ROWS CONSOLE_SETTING_COUNT /* the longest settings page */
_Static_assert((int)SETTINGS_ENTRY_COUNT <= PAGE_ROWS && (int)POSTCARD_SETTING_COUNT <= PAGE_ROWS,
               "every settings page's rows fit PAGE_ROWS");

/* the rows of the settings page shown, and its title; returns how many */
static uint32_t page_rows(const panel_t *panel, setting_row_t rows[PAGE_ROWS], const char **title)
{
  const console_settings_t *console = &panel->console;
  browse_view_t view = panel->browse.view;
  uint32_t count = browse_page_rows(view);
  *title = view == BROWSE_SETTINGS ? SETTINGS_TITLE
           : view == BROWSE_POSTCARD ? postcard_setting_name(POSTCARD_SETTING_SHOWN)
           : console_setting_name(CONSOLE_SETTING_SHOWN);
  for (uint32_t i = 0; i < count; i++) {
    if (view == BROWSE_SETTINGS)
      rows[i] = settings_entry(panel, (settings_entry_t)i);
    else if (view == BROWSE_POSTCARD)
      rows[i] = (setting_row_t){ postcard_setting_name((postcard_setting_t)i),
                                 postcard_value_text(&panel->postcard, (postcard_setting_t)i), false, true };
    else if (console_setting_is_kind((console_setting_t)i))
      rows[i] = (setting_row_t){ console_setting_name((console_setting_t)i), 0,
                                 console_kind_shown(console, console_setting_kind((console_setting_t)i)), false };
    else
      rows[i] = (setting_row_t){ console_setting_name((console_setting_t)i),
                                 console_value_text(console, (console_setting_t)i, panel->archipelago), false, true };
  }
  return count;
}

static void draw_tick_box(const layout_t *l, gd_flag_t flag, float x, float y, float row);

static float draw_settings_page(const layout_t *l, const panel_t *panel, float y)
{
  setting_row_t rows[PAGE_ROWS];
  const char *title = "";
  uint32_t count = page_rows(panel, rows, &title), highlighted = browse_page_row(&panel->browse);
  float head = LIST_HEAD_ROW_FP * l->fp, row = SETTING_ROW_FP * l->fp;
  draw_text(&l->bold, title, l->inner_x, baseline_in(&l->bold, y, head), title_colour);
  y += head;
  for (uint32_t i = 0; i < count; i++) {
    char value[NAME_ROOM];
    float top = y + i * row, x = l->inner_x;
    if (i == highlighted)
      draw_highlight(l, l->inner_x, top, l->inner_w, row);
    if (!rows[i].value) {
      draw_tick_box(l, rows[i].ticked ? GD_TRUE : GD_FALSE, x, top, row);
      x += (TICK_BOX_FP + TICK_GAP_FP) * l->fp;
    }
    draw_text(&l->body, rows[i].name, x, baseline_in(&l->body, top, row), text_colour);
    if (!rows[i].value)
      continue;
    snprintf(value, sizeof(value), rows[i].arrows ? "< %s >" : "%s", rows[i].value);
    draw_text(&l->bold, value, l->inner_x + SETTING_VALUE_AT_FP * l->fp, baseline_in(&l->bold, top, row), white);
  }
  return y + count * row + SECTION_GAP_FP * l->fp;
}

static const char *page_hint(browse_view_t view)
{
  switch (view) {
    case BROWSE_SETTINGS: return HINT_SETTINGS;
    case BROWSE_CONSOLE: return HINT_CONSOLE;
    default: return HINT_POSTCARD;
  }
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
  const panel_shape_t *shape = &content.shape;
  layout_t l = layout_for(&content, area);
  gpuui_fill(l.x, l.y, l.w, l.h, to_gpu(box_colour, BOX_OPACITY));
  float y = draw_header(&l, panel, l.y + PAD_Y_FP * l.fp);
  y = draw_status(&l, &content, y);
  if (!shape->tracking)
    return;
  if (shape->settings_rows) {
    draw_hint(&l, page_hint(panel->browse.view), draw_settings_page(&l, panel, y));
    return;
  }
  if (shape->list) {
    y = draw_list(&l, panel, draw_list_heading(&l, panel, y));
    draw_hint(&l, HINT_LIST, y);
    return;
  }
  y = draw_grid(&l, &panel->state, y);
  if (shape->has_keys)
    y = draw_keys(&l, &panel->state, y, panel->state.key_count);
  y = draw_summary(&l, &panel->state, y);
  draw_hint(&l, HINT_REGIONS, draw_regions(&l, panel, (int)shape->region_rows, y));
}

/* --- the postcard --------------------------------------------------------------------------------- */

/* the card's box in the corner its settings choose, at its size: the items' cells CARD_CELL_W_FP wide, the songs
 * across the same width and the keys in CARD_KEY_COLUMNS columns under them, all at the card's own scale of the
 * picture's font pixel */
static layout_t card_layout(const postcard_settings_t *settings, const box_t *card, nvn_rect_t area)
{
  float fp = picture_fp(area);
  layout_t l = layout_scaled(fp * postcard_scale(settings));
  l.w = card->w * fp;
  l.inner_w = l.w - 2 * CARD_PAD_FP * l.fp;
  l.h = card->h * fp;
  l.x = (float)(int)(card->x * fp);
  l.y = (float)(int)(card->y * fp);
  l.inner_x = l.x + CARD_PAD_FP * l.fp;
  return l;
}

static void draw_postcard(const panel_t *panel, const box_t *card, nvn_rect_t area)
{
  layout_t l = card_layout(&panel->postcard, card, area);
  gpuui_set_opacity(postcard_opacity(&panel->postcard));
  gpuui_fill(l.x, l.y, l.w, l.h, to_gpu(box_colour, BOX_OPACITY));
  float y = draw_grid(&l, &panel->state, l.y + CARD_PAD_FP * l.fp);
  if (panel->state.key_count)
    draw_keys(&l, &panel->state, y, CARD_KEY_COLUMNS);
  gpuui_set_opacity(1);
}

/* --- the console ---------------------------------------------------------------------------------- */

typedef struct {
  char text[CONSOLE_TEXT_ROOM];
  rgb_t colour;
  float alpha;
} console_row_t;

/* the rows shown, filled from the last (the newest is at the bottom); the render thread's */
static struct {
  console_row_t rows[CONSOLE_MAX_LINES];
  int count, room;
} console_rows;

static void add_console_row(const type_t *type, const char *text, int length, bool cut, float room, rgb_t colour,
                            float alpha)
{
  console_row_t *row = &console_rows.rows[console_rows.room - 1 - console_rows.count++];
  char piece[CONSOLE_TEXT_ROOM];
  text_copy(piece, (size_t)length + 1 < sizeof(piece) ? (size_t)length + 1 : sizeof(piece), text);
  fit_text(type, piece, room, cut, row->text, sizeof(row->text));
  row->colour = colour;
  row->alpha = alpha;
}

/* a line's rows (at most CONSOLE_WRAP_ROWS, the last cut with ".." if the line goes on), its last first, while the
 * console has room */
static void add_console_line(const type_t *type, const char *text, float room, rgb_t colour, float alpha)
{
  int starts[CONSOLE_WRAP_ROWS], lengths[CONSOLE_WRAP_ROWS], rows = 0, at = 0;
  while (text[at] && rows < CONSOLE_WRAP_ROWS) {
    while (text[at] == ' ')
      at++;
    if (!text[at])
      break;
    int taken = text_wrap(type, text + at, room), shown = taken;
    while (shown > 1 && text[at + shown - 1] == ' ')
      shown--;
    starts[rows] = at;
    lengths[rows++] = shown;
    at += taken;
  }
  while (text[at] == ' ')
    at++;
  bool cut = text[at] != 0;
  for (int i = rows - 1; i >= 0 && console_rows.count < console_rows.room; i--)
    add_console_row(type, text + starts[i], lengths[i], cut && i == rows - 1, room, colour, alpha);
}

/* the rows shown: the status line at the bottom, then the newest lines still shown above it */
static void collect_console_rows(const console_view_t *view, const type_t *type, float room, uint64_t now,
                                 bool preview)
{
  console_rows.count = 0;
  console_rows.room = console_lines(&view->settings);
  if (view->status[0])
    add_console_row(type, view->status, (int)strlen(view->status), false, room, dim_colour, 1);
  for (int i = (int)view->count - 1; i >= 0 && console_rows.count < console_rows.room; i--) {
    const console_line_t *line = &view->lines[i];
    float alpha = preview ? 1 : console_line_alpha(&view->settings, line->time_ms, now);
    if (alpha <= 0)
      break; /* the older ones have gone too */
    rgb_t colour = line->kind < CONSOLE_KIND_COUNT ? kind_colours[line->kind] : notice_colour;
    add_console_line(type, line->text, room, colour, alpha);
  }
  if (preview && !console_rows.count)
    add_console_row(type, NO_MESSAGES, (int)strlen(NO_MESSAGES), false, room, dim_colour, 1);
}

/* Its rows in its box at its edge, each row's band and text at the row's opacity, so that a fading line fades with
 * its part of the box. `card`: the postcard's box (font pixels) to keep clear of, or NULL; `preview`: every line at
 * full strength, for its settings pages. */
static void draw_console(const console_view_t *view, nvn_rect_t area, const box_t *card, uint64_t now, bool preview)
{
  float fp = picture_fp(area);
  layout_t l = layout_scaled(fp);
  console_position_t position = (console_position_t)(view->settings.position % CONSOLE_POSITION_COUNT);
  box_t box = sizes_console_box(position, console_lines(&view->settings), area.w / fp, card);
  float pad_x = CONSOLE_PAD_X_FP * fp, pad_y = (float)(int)(CONSOLE_PAD_Y_FP * fp + 0.5f), row = CONSOLE_ROW_FP * fp;
  collect_console_rows(view, &l.body, box.w * fp - 2 * pad_x, now, preview);
  int count = console_rows.count;
  const console_row_t *rows = &console_rows.rows[console_rows.room - count];
  float x = (float)(int)(box.x * fp), w = (float)(int)(box.w * fp);
  float top = position == CONSOLE_TOP ? box.y * fp + pad_y : (box.y + box.h) * fp - pad_y - count * row;
  float opacity = console_opacity(&view->settings);
  for (int i = 0; i < count; i++) {
    float y = (float)(int)(top + i * row), next = (float)(int)(top + (i + 1) * row);
    float band_top = i == 0 ? y - pad_y : y, band_bottom = i == count - 1 ? next + pad_y : next;
    gpuui_set_opacity(opacity * rows[i].alpha);
    gpuui_fill(x, band_top, w, band_bottom - band_top, to_gpu(box_colour, BOX_OPACITY));
    draw_text(&l.body, rows[i].text, x + pad_x, baseline_in(&l.body, y, next - y), rows[i].colour);
  }
  gpuui_set_opacity(1);
}

/* --- a frame ---------------------------------------------------------------------------------------- */

/* The panel when it is open; the postcard when it is on, with the panel closed or showing the postcard's
 * settings (the card then shows what they do); the console when it is on, with the panel closed or showing the
 * console's settings (every line at full strength, clear of where the card is once the panel closes, and under the
 * panel, whose rows it would hide). */
static void draw_frame(const panel_t *panel, const console_view_t *console, nvn_rect_t area, uint64_t now)
{
  bool card_on = panel->mode == PANEL_TRACKING && panel->postcard.shown;
  box_t card = card_on ? sizes_card_box(&panel->postcard, panel->state.key_count, area.w / picture_fp(area))
                       : (box_t){ 0, 0, 0, 0 };
  bool preview = panel->menu && panel->browse.view == BROWSE_CONSOLE;
  if (console->shown && preview)
    draw_console(console, area, card_on ? &card : 0, now, true);
  if (panel->menu)
    draw_panel(panel, area);
  if (card_on && (!panel->menu || panel->browse.view == BROWSE_POSTCARD))
    draw_postcard(panel, &card, area);
  if (console->shown && !panel->menu && console_view_showing(console, now))
    draw_console(console, area, card_on ? &card : 0, now, false);
}

bool trackerui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                      nvn_rect_t area, const panel_t *panel, const console_view_t *console, uint64_t now)
{
  if (area.h <= 0 || (panel->mode == PANEL_HIDDEN && !console_view_showing(console, now)))
    return false;
  if (gpuui_atlas_resetting() && !slots_wait_idle())
    return false;
  gpuui_begin(texture, area, info->height, nvn_origin_lower_left(), slot);
  icons_step();
  draw_frame(panel, console, area, now);
  return gpuui_end(cmd, nvn_game_texture_pool(), nvn_game_sampler_pool());
}
