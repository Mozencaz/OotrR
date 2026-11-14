/* Before each of the game's presents (nvn.c): draws the panel, if it's shown, in the game's own style
 * (trackerui.c), as one command buffer on a slot (slots.c). The panel itself comes from the game's controller
 * thread (app.c). Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3) through ocarinaMIDI's overlay.c (c599fa5). */
#include "overlay.h"

#include "nvn.h"
#include "slots.h"
#include "sys.h"
#include "trackerui.h"

#define COMMAND_BYTES 0x40000 /* command memory per slot: a panel is up to about 1,500 draws (MAX_QUADS in gpuui.c) */

static enum { OV_NONE, OV_READY, OV_FAILED } state;

/* --- the panel, from the game's controller thread to its present thread ------------------------- */

static panel_t published;
static uint32_t published_seq; /* odd while `published` is being written */

void overlay_publish(const panel_t *panel)
{
  uint32_t seq = __atomic_load_n(&published_seq, __ATOMIC_RELAXED);
  __atomic_store_n(&published_seq, seq + 1, __ATOMIC_RELAXED);
  __atomic_thread_fence(__ATOMIC_RELEASE);
  memcpy(&published, panel, sizeof(published));
  __atomic_store_n(&published_seq, seq + 2, __ATOMIC_RELEASE);
}

/* The newest panel; the one read last time if it's being written right now. */
static const panel_t *newest_panel(void)
{
  static panel_t newest;
  panel_t attempt;
  uint32_t before = __atomic_load_n(&published_seq, __ATOMIC_ACQUIRE);
  if (before & 1)
    return &newest;
  memcpy(&attempt, &published, sizeof(attempt));
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  if (__atomic_load_n(&published_seq, __ATOMIC_RELAXED) == before)
    memcpy(&newest, &attempt, sizeof(newest));
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
  nvn_texture_info_t info;
  if (panel->mode == PANEL_HIDDEN || state == OV_FAILED || !nvn_texture_info(texture, &info))
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
  if (trackerui_record(slots_begin(slot), slot, texture, &info, area, panel))
    slots_submit(queue, slot);
  else
    slots_discard();
}
