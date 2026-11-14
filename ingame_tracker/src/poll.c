/* Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "poll.h"

#include <stdbool.h>

#include "app.h"
#include "npad.h"
#include "sys.h"

#define MIN_FRAME_MS 8 /* reads closer than this are the same frame, even at 120 fps */
#define NO_ANCHOR    (-1)

static int anchor_style = NO_ANCHOR;
static uint32_t anchor_npad_id;
static uint64_t frame_start_ms;
static uint32_t held_this_frame;

static bool starts_frame(int style, uint32_t npad_id)
{
  if (anchor_style == NO_ANCHOR) {
    anchor_style = style;
    anchor_npad_id = npad_id;
    frame_start_ms = sys_ms();
    log_printf("counting frames from reads of controller style %d, NpadIdType 0x%x", style, (unsigned)npad_id);
    return false;
  }
  if (style != anchor_style || npad_id != anchor_npad_id)
    return false;
  uint64_t now = sys_ms();
  if (now - frame_start_ms < MIN_FRAME_MS)
    return false;
  frame_start_ms = now;
  return true;
}

void poll_states(int style, uint32_t npad_id, void *states, int count)
{
  if (starts_frame(style, npad_id)) {
    app_frame(held_this_frame);
    held_this_frame = 0;
  }
  for (int i = 0; i < count; i++) {
    npad_state_t *state = (npad_state_t *)((char *)states + i * NPAD_STATE_SIZE);
    if (!(state->attributes & NPAD_ATTR_CONNECTED))
      continue;
    held_this_frame |= (uint32_t)state->buttons;
    app_edit_state(state);
  }
}
