/* Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#include "app.h"

#include "browse.h"
#include "console.h"
#include "consolefile.h"
#include "consolelog.h"
#include "controls.h"
#include "gamedata.h"
#include "gamefile.h"
#include "locate.h"
#include "mailbox.h"
#include "overlay.h"
#include "panel.h"
#include "postcard.h"
#include "postcardfile.h"
#include "sys.h"
#include "text.h"
#include "trackerui.h"
#include "trkfile.h"
#include "worldmark.h"

void free(void *p); /* from main */

#define SEED_FILE          GAME_ROM "/RandoTracker/seed.trk"
#define REFRESH_MS         500   /* the panel is worked out twice a second while it's open */
#define PRELOAD_AFTER_MS   10000 /* the seed file is read this long after the first frame: the game's files are mounted */
#define RETRY_SEED_MS      2000  /* a failed read isn't tried again sooner */
#define PAUSE_READ_MS      100   /* the game's pause is read this often while the postcard or the console is on */
#define LOCATE_REFRESH_MS  250   /* the check shown in the world: the game's map and its pause read this often */

static struct {
  game_t game;
  gamedata_t data;
  trk_t seed;
  bool seed_loaded;
  uint64_t first_frame_ms, next_seed_try_ms, next_refresh_ms;
  bool preload_done;
  bool open;
  panel_mode_t last_mode;
  browse_t browse;
  postcard_settings_t postcard;
  bool postcard_changed; /* not yet written to the SD card */
  panel_t panel; /* the one shown: moving the highlight shows it again without working it all out anew */
  bool archipelago;      /* the seed file says it is an Archipelago seed */
  console_settings_t console;
  bool console_changed;  /* not yet written to the SD card */
  bool console_dirty;    /* not yet handed to the present thread */
  mailbox_client_t client;
  console_log_t console_log;
  char console_status[CONSOLE_STATUS_ROOM]; /* the status line handed over last */
  bool paused;           /* the game's pause as read last: the postcard and the console hide meanwhile */
  uint64_t next_pause_ms;
  uint32_t located;          /* the check shown in the world (locate.h), LOCATE_NONE if none */
  uint64_t next_locate_ms;
  locate_view_t locate_view; /* handed to the present thread last */
} app;

/* Runs inside rtld's DT_INIT: checked reads and unformatted logging only. */
void app_init(uintptr_t nnmain_address)
{
  app.located = LOCATE_NONE;
  app.postcard = postcard_defaults();
  app.console = console_defaults();
  app.game = builds_detect(nnmain_address);
  if (!app.game.build) {
    log_raw("this game build is not known: the panel will say so");
    return;
  }
  gamedata_init(&app.data, app.game);
  log_raw("game build:");
  log_raw(app.game.build->version);
}

/* --- the seed file ----------------------------------------------------------------------------- */

static bool load_seed(void)
{
  size_t size = 0;
  uint8_t *bytes = gamefile_read(SEED_FILE, &size);
  if (!bytes) {
    log_printf("no %s: the tracker stays off", SEED_FILE);
    return false;
  }
  const char *why = "";
  if (!trk_parse(&app.seed, bytes, size, &why)) {
    log_printf("%s refused: %s", SEED_FILE, why);
    free(bytes);
    return false;
  }
  app.archipelago = app.seed.flags & TRK_FLAG_ARCHIPELAGO;
  log_printf("seed %s: %u regions, %u checks, %u items%s", trk_string(&app.seed, app.seed.seed_id),
             (unsigned)app.seed.region_count, (unsigned)app.seed.check_count, (unsigned)app.seed.item_count,
             app.archipelago ? ", an Archipelago seed" : "");
  return true; /* the bytes stay: the panel's names point into them */
}

/* Reads the seed file once it is wanted and not tried a moment ago. */
static bool ensure_seed(uint64_t now)
{
  if (app.seed_loaded)
    return true;
  if (now < app.next_seed_try_ms)
    return false;
  app.next_seed_try_ms = now + RETRY_SEED_MS;
  app.seed_loaded = load_seed();
  if (app.seed_loaded) {
    postcardfile_load(&app.postcard);
    consolefile_load(&app.console);
    mailbox_set_seed(mailbox_shared(), trk_string(&app.seed, app.seed.seed_id));
    mailbox_start(&app.client, now);
    app.console_dirty = true;
  }
  return app.seed_loaded;
}

/* --- the check shown in the world (locate.h) ---------------------------------------------------- */

/* the map the game is in (its save's "map" string) in `room`, NULL if it can't be read yet */
static const char *current_map(char room[GAMEDATA_STRING_ROOM])
{
  if (!app.game.build || !gamedata_attach(&app.data))
    return 0;
  return gamedata_string(&app.data, GAMEDATA_MAP_STRING, room, GAMEDATA_STRING_ROOM) && room[0] ? room : 0;
}

static bool link_position(float out[3])
{
  return app.game.build && worldmark_link(app.game.main_base + app.game.build->disp_ptr, out);
}

static uint32_t highlighted_check(void)
{
  return app.browse.view == BROWSE_CHECKS ? locate_check_of(&app.seed, app.browse.region, app.browse.check)
                                          : LOCATE_NONE;
}

/* the line under the list for the highlighted check: its id, and where it is or what A does */
static void fill_detail(locate_detail_t *detail)
{
  uint32_t check = highlighted_check();
  char room[GAMEDATA_STRING_ROOM];
  float link[3];
  locate_t where = locate_find(&app.seed, check, current_map(room));
  detail->ident = check == LOCATE_NONE ? "" : trk_string(&app.seed, trk_check_ident(&app.seed, check));
  detail->shown = check != LOCATE_NONE && check == app.located;
  detail->state = where.state;
  locate_panel_line(detail->shown, &where, link_position(link) ? link : 0, detail->line, sizeof(detail->line));
}

/* What the present thread draws for it: handed over when it changes. Hidden while the game is paused. */
static void refresh_located(uint64_t now)
{
  app.next_locate_ms = now + LOCATE_REFRESH_MS;
  static locate_view_t view; /* not on the game thread's stack */
  memset(&view, 0, sizeof(view));
  if (app.located != LOCATE_NONE && app.seed_loaded && app.game.build) {
    char room[GAMEDATA_STRING_ROOM];
    const char *map = current_map(room);
    locate_t where = locate_find(&app.seed, app.located, map);
    view.shown = !(map && gamedata_paused(&app.data)); /* the pause is read only once the save data is */
    view.drawn = view.shown && where.state == LOCATE_HERE;
    for (int i = 0; i < 3; i++)
      view.point[i] = where.point[i];
    text_copy(view.name, sizeof(view.name), trk_string(&app.seed, trk_check(&app.seed, app.located).name));
    if (!view.drawn)
      locate_describe(&where, 0, view.where, sizeof(view.where));
    view.camera_holder = app.game.main_base + app.game.build->camera_ptr;
    view.link_holder = app.game.main_base + app.game.build->disp_ptr;
  }
  if (!memcmp(&view, &app.locate_view, sizeof(view)))
    return;
  memcpy(&app.locate_view, &view, sizeof(view)); /* the padding too, for the comparison */
  overlay_publish_locate(&view);
}

/* A on a check of a region's list: shown in the world, or put away if it was; a check with no place stays as
 * it is (the line under the list says why). */
static void toggle_located(uint64_t now)
{
  uint32_t check = highlighted_check();
  locate_state_t state = locate_find(&app.seed, check, 0).state;
  if (check == LOCATE_NONE || (check != app.located && (state == LOCATE_NOWHERE || state == LOCATE_OLD_FILE)))
    return;
  app.located = locate_toggle(app.located, check);
  if (app.located == LOCATE_NONE)
    log_printf("show in the world: off");
  else
    log_printf("show in the world: check %u", (unsigned)check);
  refresh_located(now);
}

/* --- the panel --------------------------------------------------------------------------------- */

static const char *const mode_names[] = {
  [PANEL_HIDDEN] = "hidden", [PANEL_UNSUPPORTED_BUILD] = "game version not supported",
  [PANEL_WAITING_FOR_GAME_DATA] = "waiting for the game's save data", [PANEL_TRACKING] = "tracking",
};

static panel_mode_t work_out(panel_t *panel)
{
  if (!app.game.build)
    return PANEL_UNSUPPORTED_BUILD;
  if (!gamedata_attach(&app.data))
    return PANEL_WAITING_FOR_GAME_DATA;
  tracker_compute(&app.seed, &app.data.source, &panel->state);
  return PANEL_TRACKING;
}

/* the highlight and, with a region's list open, the checks of it shown now */
static void fill_browse(panel_t *panel)
{
  panel->postcard = app.postcard;
  panel->console = app.console;
  panel->archipelago = app.archipelago;
  panel->browse = app.browse;
  panel->row_count = 0;
  memset(&panel->detail, 0, sizeof(panel->detail));
  if (panel->mode == PANEL_TRACKING && app.browse.view == BROWSE_CHECKS) {
    panel->row_count = tracker_check_rows(&app.seed, &app.data.source, app.browse.region, app.browse.top, panel->rows,
                                          BROWSE_CHECK_ROWS);
    fill_detail(&panel->detail);
  }
}

static void refresh_panel(uint64_t now)
{
  panel_t *panel = &app.panel;
  memset(panel, 0, sizeof(*panel));
  text_copy(panel->seed_id, sizeof(panel->seed_id), trk_string(&app.seed, app.seed.seed_id));
  panel->menu = true;
  panel->mode = work_out(panel);
  fill_browse(panel);
  overlay_publish(panel);
  if (panel->mode != app.last_mode)
    log_printf("panel: %s", mode_names[panel->mode]);
  app.last_mode = panel->mode;
  app.next_refresh_ms = now + REFRESH_MS;
}

/* The postcard is drawn on its own while it's on, the panel is closed and the game isn't paused. */
static bool postcard_wanted(void)
{
  return app.seed_loaded && app.game.build && postcard_over_game(&app.postcard, app.open, app.paused);
}

/* Only the items and keys are worked out for it; it is redrawn every frame from them. */
static void refresh_postcard(uint64_t now)
{
  trackerui_load(); /* the game's font and shader, once: a pause the first time */
  panel_t *panel = &app.panel;
  memset(panel, 0, sizeof(*panel));
  panel->postcard = app.postcard;
  if (gamedata_attach(&app.data)) {
    tracker_compute_icons(&app.seed, &app.data.source, &panel->state);
    panel->mode = PANEL_TRACKING;
  }
  overlay_publish(panel);
  app.next_refresh_ms = now + REFRESH_MS;
}

/* The highlight moved: the panel as it was, with the list read anew (the rest waits for the next refresh). */
static void show_browse(void)
{
  if (app.panel.mode == PANEL_TRACKING && !gamedata_attach(&app.data))
    app.panel.mode = PANEL_WAITING_FOR_GAME_DATA;
  fill_browse(&app.panel);
  overlay_publish(&app.panel);
}

static void publish_hidden(void)
{
  panel_t hidden;
  memset(&hidden, 0, sizeof(hidden));
  overlay_publish(&hidden);
}

static void open_panel(uint64_t now)
{
  trackerui_load(); /* the game's font and shader, once: a pause the first time */
  app.open = true;
  app.console_dirty = true; /* paused, the Console page's preview shows it all the same */
  browse_show_regions(&app.browse, app.seed.region_count);
  refresh_panel(now);
}

static void close_panel(void)
{
  app.open = false;
  app.last_mode = PANEL_HIDDEN;
  app.next_refresh_ms = 0; /* the postcard, if it's on, comes back at the next frame */
  app.console_dirty = true; /* hidden again if the game is paused */
  controls_hold_back_held();
  publish_hidden();
}

static void change_postcard_setting(int direction)
{
  postcard_step(&app.postcard, (postcard_setting_t)app.browse.setting, direction);
  app.postcard_changed = true;
}

static void change_console_setting(int direction)
{
  console_step(&app.console, (console_setting_t)app.browse.setting, direction, app.archipelago);
  app.console_changed = app.console_dirty = true;
}

static bool on_console_page(void)
{
  return app.open && app.browse.view == BROWSE_CONSOLE;
}

/* The settings are written when their page is left (or the panel closed), not at each change. */
static void save_settings_changes(void)
{
  if (app.postcard_changed && !(app.open && app.browse.view == BROWSE_POSTCARD)) {
    app.postcard_changed = false;
    postcardfile_save(&app.postcard);
  }
  if (app.console_changed && !on_console_page()) {
    app.console_changed = false;
    consolefile_save(&app.console);
  }
}

static uint32_t highlighted_region_checks(void)
{
  return app.browse.region < app.seed.region_count ? trk_region(&app.seed, app.browse.region).check_count : 0;
}

static void navigate(control_t command, uint64_t now)
{
  static const nav_t navs[] = {
    [CONTROL_UP] = NAV_UP, [CONTROL_DOWN] = NAV_DOWN, [CONTROL_LEFT] = NAV_LEFT, [CONTROL_RIGHT] = NAV_RIGHT,
  };
  if (app.panel.mode != PANEL_TRACKING) /* no regions shown */
    return;
  bool sideways = command == CONTROL_LEFT || command == CONTROL_RIGHT;
  int direction = command == CONTROL_RIGHT ? 1 : -1;
  bool kind_row = app.browse.view == BROWSE_CONSOLE && console_setting_is_kind((console_setting_t)app.browse.setting);
  if (kind_row && (command == CONTROL_SELECT || sideways))
    change_console_setting(direction);
  else if (command == CONTROL_SELECT && app.browse.view == BROWSE_CHECKS)
    toggle_located(now);
  else if (command == CONTROL_SELECT)
    browse_open(&app.browse, app.seed.region_count);
  else if (app.browse.view == BROWSE_POSTCARD && sideways)
    change_postcard_setting(direction);
  else if (app.browse.view == BROWSE_CONSOLE && sideways)
    change_console_setting(direction);
  else
    browse_move(&app.browse, navs[command], app.seed.region_count, highlighted_region_checks());
  show_browse();
}

static void run(control_t command, uint64_t now)
{
  switch (command) {
    case CONTROL_NONE:
      return;
    case CONTROL_TOGGLE:
      if (app.open)
        close_panel();
      else if (ensure_seed(now))
        open_panel(now);
      return;
    case CONTROL_BACK:
      if (browse_back(&app.browse))
        show_browse();
      else
        close_panel();
      return;
    default:
      navigate(command, now);
      return;
  }
}

/* --- the game's pause -------------------------------------------------------------------------- */

/* While the game is paused (its pause screen or an item menu) the postcard and the console hide, so its menus are
 * clear, and they come back when it plays again. The panel, opened on purpose, works as ever. */
static void read_pause(uint64_t now)
{
  if (now < app.next_pause_ms)
    return;
  app.next_pause_ms = now + PAUSE_READ_MS;
  bool wanted = app.seed_loaded && app.game.build && (app.postcard.shown || console_shown(&app.console, app.archipelago));
  bool paused = wanted && gamedata_attach(&app.data) && gamedata_paused(&app.data);
  if (paused == app.paused)
    return;
  app.paused = paused;
  log_printf("the game is %s: the postcard and the console %s", paused ? "paused" : "playing",
             paused ? "hide" : "show again");
  app.console_dirty = true;
  if (app.open)
    return;
  app.next_refresh_ms = 0; /* the postcard, if it's on, comes back at the next frame */
  if (paused)
    publish_hidden();
}

/* --- the console ------------------------------------------------------------------------------- */

/* The client's new lines and its status, every frame (a few reads while nothing changes); the present thread gets
 * the console again when they, its settings or the status line change. */
static void update_console(uint64_t now)
{
  if (!app.seed_loaded)
    return;
  bool was_heard = app.client.heard;
  uint32_t lines_before = app.console_log.count;
  bool changed = mailbox_poll(mailbox_shared(), &app.client, &app.console_log, now) || app.console_dirty;
  if (app.client.heard && !was_heard)
    log_printf("console: the Archipelago client is writing to it");
  if (app.console_log.count && !lines_before)
    log_printf("console: its first line came");
  char status[CONSOLE_STATUS_ROOM];
  mailbox_status_line(&app.client, app.archipelago, now, status, sizeof(status));
  if (!changed && text_equal(status, app.console_status))
    return;
  static console_view_t view; /* about 2 KiB: not on the game thread's stack */
  view.settings = app.console;
  view.shown = console_over_game(&app.console, app.archipelago, app.open, app.paused);
  text_copy(view.status, sizeof(view.status), status);
  text_copy(app.console_status, sizeof(app.console_status), status);
  consolelog_view(&app.console_log, &app.console, &view);
  if (view.shown && (view.count || view.status[0]))
    trackerui_load(); /* the game's font and shader, once: a pause the first time */
  overlay_publish_console(&view);
  app.console_dirty = false;
}

void app_frame(uint32_t held)
{
  uint64_t now = sys_ms();
  if (!app.first_frame_ms)
    app.first_frame_ms = now;
  if (!app.preload_done && now - app.first_frame_ms >= PRELOAD_AFTER_MS) {
    app.preload_done = true;
    ensure_seed(now);
  }
  run(controls_frame(held, app.open, now), now);
  save_settings_changes();
  read_pause(now);
  update_console(now);
  if (app.located != LOCATE_NONE ? now >= app.next_locate_ms : app.locate_view.shown)
    refresh_located(now);
  if (now < app.next_refresh_ms)
    return;
  if (app.open)
    refresh_panel(now);
  else if (postcard_wanted())
    refresh_postcard(now);
}

void app_edit_state(npad_state_t *state)
{
  if (!app.seed_loaded)
    return;
  uint32_t buttons = (uint32_t)state->buttons;
  state->buttons &= ~(uint64_t)controls_hidden(buttons, app.open);
  if (controls_centres_right_stick(buttons, app.open))
    state->rx = state->ry = 0;
  if (controls_centres_left_stick(app.open))
    state->lx = state->ly = 0;
}
