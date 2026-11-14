/* Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#include "controls.h"

#include "npad.h"

#define COMBO_MODIFIER  BTN_R
#define COMBO_DIRECTION BTN_RS_UP
#define RIGHT_STICK_DIRECTIONS (BTN_RS_LEFT | BTN_RS_UP | BTN_RS_RIGHT | BTN_RS_DOWN)
#define LEFT_STICK_DIRECTIONS  (BTN_LS_LEFT | BTN_LS_UP | BTN_LS_RIGHT | BTN_LS_DOWN)
#define COMBO_BUTTONS          (COMBO_MODIFIER | RIGHT_STICK_DIRECTIONS)
#define PANEL_BUTTONS          (COMBO_BUTTONS | BTN_A | BTN_B | BTN_DPAD | LEFT_STICK_DIRECTIONS)
#define REPEAT_AFTER_MS 350 /* a direction held this long repeats, */
#define REPEAT_EVERY_MS 90  /* this often */

static uint32_t held_last_frame;
static uint32_t held_back; /* still hidden from the game since the panel closed */
static control_t repeating;
static uint64_t next_repeat_ms;

static const struct { uint32_t buttons; control_t direction; } directions[] = {
  { BTN_DUP | BTN_LS_UP, CONTROL_UP }, { BTN_DDOWN | BTN_LS_DOWN, CONTROL_DOWN },
  { BTN_DLEFT | BTN_LS_LEFT, CONTROL_LEFT }, { BTN_DRIGHT | BTN_LS_RIGHT, CONTROL_RIGHT },
};

bool controls_combo_held(uint32_t buttons)
{
  return (buttons & COMBO_MODIFIER) && (buttons & COMBO_DIRECTION);
}

static control_t direction_held(uint32_t held)
{
  for (unsigned i = 0; i < sizeof(directions) / sizeof(*directions); i++)
    if (held & directions[i].buttons)
      return directions[i].direction;
  return CONTROL_NONE;
}

/* A direction on its press, then again while it's held. */
static control_t direction_command(uint32_t held, uint64_t now_ms)
{
  control_t direction = direction_held(held);
  if (direction != repeating) {
    repeating = direction;
    next_repeat_ms = now_ms + REPEAT_AFTER_MS;
    return direction;
  }
  if (direction == CONTROL_NONE || now_ms < next_repeat_ms)
    return CONTROL_NONE;
  next_repeat_ms = now_ms + REPEAT_EVERY_MS;
  return direction;
}

control_t controls_frame(uint32_t held, bool panel_open, uint64_t now_ms)
{
  uint32_t pressed = held & ~held_last_frame;
  bool combo_pressed = controls_combo_held(held) && !controls_combo_held(held_last_frame);
  held_last_frame = held;
  held_back &= held;
  if (combo_pressed)
    return CONTROL_TOGGLE;
  if (!panel_open) {
    repeating = CONTROL_NONE;
    return CONTROL_NONE;
  }
  if (pressed & BTN_B)
    return CONTROL_BACK;
  if (pressed & BTN_A)
    return CONTROL_SELECT;
  return direction_command(held, now_ms);
}

void controls_hold_back_held(void)
{
  held_back |= held_last_frame & PANEL_BUTTONS;
}

bool controls_centres_right_stick(uint32_t buttons, bool panel_open)
{
  return panel_open || controls_combo_held(buttons) || (held_back & RIGHT_STICK_DIRECTIONS);
}

bool controls_centres_left_stick(bool panel_open)
{
  return panel_open || (held_back & LEFT_STICK_DIRECTIONS);
}

uint32_t controls_hidden(uint32_t buttons, bool panel_open)
{
  if (panel_open)
    return PANEL_BUTTONS;
  return held_back | (controls_combo_held(buttons) ? COMBO_BUTTONS : 0);
}

void controls_reset(void)
{
  held_last_frame = held_back = 0;
  repeating = CONTROL_NONE;
}
