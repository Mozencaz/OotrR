/* Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#include "app.h"

#include "controls.h"
#include "gamedata.h"
#include "gamefile.h"
#include "overlay.h"
#include "panel.h"
#include "sys.h"
#include "text.h"
#include "trackerui.h"
#include "trkfile.h"

void free(void *p); /* from main */

#define SEED_FILE          GAME_ROM "/RandoTracker/seed.trk"
#define REFRESH_MS         500   /* the panel is worked out twice a second while it's open */
#define PRELOAD_AFTER_MS   10000 /* the seed file is read this long after the first frame: the game's files are mounted */
#define RETRY_SEED_MS      2000  /* a failed read isn't tried again sooner */

static struct {
  game_t game;
  gamedata_t data;
  trk_t seed;
  bool seed_loaded;
  uint64_t first_frame_ms, next_seed_try_ms, next_refresh_ms;
  bool preload_done;
  bool open;
  panel_mode_t last_mode;
} app;

/* Runs inside rtld's DT_INIT: checked reads and unformatted logging only. */
void app_init(uintptr_t nnmain_address)
{
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
  log_printf("seed %s: %u regions, %u checks, %u items", trk_string(&app.seed, app.seed.seed_id),
             (unsigned)app.seed.region_count, (unsigned)app.seed.check_count, (unsigned)app.seed.item_count);
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
  return app.seed_loaded;
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

static void refresh_panel(uint64_t now)
{
  panel_t panel;
  memset(&panel, 0, sizeof(panel));
  text_copy(panel.seed_id, sizeof(panel.seed_id), trk_string(&app.seed, app.seed.seed_id));
  panel.mode = work_out(&panel);
  overlay_publish(&panel);
  if (panel.mode != app.last_mode)
    log_printf("panel: %s", mode_names[panel.mode]);
  app.last_mode = panel.mode;
  app.next_refresh_ms = now + REFRESH_MS;
}

static void open_panel(uint64_t now)
{
  trackerui_load(); /* the game's font and shader, once: a pause the first time */
  app.open = true;
  refresh_panel(now);
}

static void close_panel(void)
{
  panel_t hidden;
  memset(&hidden, 0, sizeof(hidden));
  app.open = false;
  app.last_mode = PANEL_HIDDEN;
  overlay_publish(&hidden);
}

static void run(control_t command, uint64_t now)
{
  if (command == CONTROL_CLOSE || (command == CONTROL_TOGGLE && app.open))
    close_panel();
  else if (command == CONTROL_TOGGLE && ensure_seed(now))
    open_panel(now);
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
  run(controls_frame(held, app.open), now);
  if (app.open && now >= app.next_refresh_ms)
    refresh_panel(now);
}

void app_edit_state(npad_state_t *state)
{
  if (!app.seed_loaded)
    return;
  uint32_t buttons = (uint32_t)state->buttons;
  if (!controls_centres_stick(buttons, app.open))
    return;
  state->buttons &= ~(uint64_t)controls_hidden(buttons, app.open);
  state->rx = state->ry = 0;
}
