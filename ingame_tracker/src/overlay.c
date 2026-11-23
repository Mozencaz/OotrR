/* Before each of the game's presents (nvn.c): draws the panel and the console, if they're shown, in the game's own
 * style (trackerui.c), as one command buffer on a slot (slots.c). What they show comes from the game's controller
 * thread (app.c). Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3) through ocarinaMIDI's overlay.c (c599fa5). */
#include "overlay.h"

#include "nvn.h"
#include "slots.h"
#include "sys.h"
#include "trackerui.h"

#define COMMAND_BYTES 0x40000 /* command memory per slot: a panel is up to about 1,500 draws (MAX_QUADS in gpuui.c) */

static enum { OV_NONE, OV_READY, OV_FAILED } state;

/* --- the panel and the console, from the game's controller thread to its present thread ------ */

/* A sequence lock: `seq` is odd while `to` is being written. */
static void publish(void *to, uint32_t *seq, const void *from, size_t size)
{
  uint32_t now = __atomic_load_n(seq, __ATOMIC_RELAXED);
  __atomic_store_n(seq, now + 1, __ATOMIC_RELAXED);
  __atomic_thread_fence(__ATOMIC_RELEASE);
  memcpy(to, from, size);
  __atomic_store_n(seq, now + 2, __ATOMIC_RELEASE);
}

/* `newest` becomes `published` unless that is being written right now (it then stays the one read last time). */
static void read_newest(void *newest, void *attempt, const void *published, const uint32_t *seq, size_t size)
{
  uint32_t before = __atomic_load_n(seq, __ATOMIC_ACQUIRE);
  if (before & 1)
    return;
  memcpy(attempt, published, size);
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  if (__atomic_load_n(seq, __ATOMIC_RELAXED) == before)
    memcpy(newest, attempt, size);
}

static panel_t published;
static uint32_t published_seq;
static console_view_t published_console;
static uint32_t published_console_seq;

void overlay_publish(const panel_t *panel)
{
  publish(&published, &published_seq, panel, sizeof(published));
}

void overlay_publish_console(const console_view_t *view)
{
  publish(&published_console, &published_console_seq, view, sizeof(published_console));
}

static locate_view_t published_locate;
static uint32_t published_locate_seq;

void overlay_publish_locate(const locate_view_t *view)
{
  publish(&published_locate, &published_locate_seq, view, sizeof(published_locate));
}

static const locate_view_t *newest_locate(void)
{
  static locate_view_t newest, attempt;
  read_newest(&newest, &attempt, &published_locate, &published_locate_seq, sizeof(newest));
  return &newest;
}

static const panel_t *newest_panel(void)
{
  static panel_t newest, attempt;
  read_newest(&newest, &attempt, &published, &published_seq, sizeof(newest));
  return &newest;
}

static const console_view_t *newest_console(void)
{
  static console_view_t newest, attempt;
  read_newest(&newest, &attempt, &published_console, &published_console_seq, sizeof(newest));
  return &newest;
}

/* --- drawing ------------------------------------------------------------------------------------ */

static void overlay_fail(const char *why)
{
  log_printf("panel off: %s", why);
  state = OV_FAILED;
}

void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture)
{
  const panel_t *panel = newest_panel();
  const console_view_t *console = newest_console();
  const locate_view_t *located = newest_locate();
  uint64_t now = sys_ms();
  nvn_texture_info_t info;
  bool console_shown = console_view_showing(console, now);
  if ((panel->mode == PANEL_HIDDEN && !console_shown && !located->shown) || state == OV_FAILED ||
      !nvn_texture_info(texture, &info))
    return;
  if (state == OV_NONE) {
    if (!slots_init(COMMAND_BYTES)) {
      overlay_fail("no commands to draw with");
      return;
    }
    state = OV_READY;
  }
  if (!trackerui_usable())
    return;
  int slot = slots_acquire();
  if (slot < 0) { /* the GPU is behind: this frame goes without, rather than held up */
    if (slots_stuck())
      overlay_fail("the GPU didn't finish the previous drawing");
    return;
  }
  nvn_rect_t area = nvn_visible_area(window, &info);
  if (trackerui_record(slots_begin(slot), slot, texture, &info, area, panel, console, located, now))
    slots_submit(queue, slot);
  else
    slots_discard();
}
