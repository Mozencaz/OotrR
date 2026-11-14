/* Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#include "controls.h"

#include "npad.h"

#define COMBO_MODIFIER  BTN_R
#define COMBO_DIRECTION BTN_RS_UP
#define RIGHT_STICK_DIRECTIONS (BTN_RS_LEFT | BTN_RS_UP | BTN_RS_RIGHT | BTN_RS_DOWN)

static uint32_t held_last_frame;

bool controls_combo_held(uint32_t buttons)
{
  return (buttons & COMBO_MODIFIER) && (buttons & COMBO_DIRECTION);
}

control_t controls_frame(uint32_t held, bool panel_open)
{
  bool combo_pressed = controls_combo_held(held) && !controls_combo_held(held_last_frame);
  bool b_pressed = (held & BTN_B) && !(held_last_frame & BTN_B);
  held_last_frame = held;
  if (combo_pressed)
    return CONTROL_TOGGLE;
  return panel_open && b_pressed ? CONTROL_CLOSE : CONTROL_NONE;
}

bool controls_centres_stick(uint32_t buttons, bool panel_open)
{
  return panel_open || controls_combo_held(buttons);
}

uint32_t controls_hidden(uint32_t buttons, bool panel_open)
{
  if (!controls_centres_stick(buttons, panel_open))
    return 0;
  return COMBO_MODIFIER | RIGHT_STICK_DIRECTIONS | (panel_open ? BTN_B : 0);
}

void controls_reset(void)
{
  held_last_frame = 0;
}
