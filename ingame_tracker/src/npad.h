/* nn::hid controller states, as the game reads them. Bit and field layout as in sloperinaGZ's
 * src/ootgz/input.h and input.c (GPL-3).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef NPAD_H
#define NPAD_H

#include <stdint.h>

/* nn::hid::NpadButton bits */
enum {
  BTN_A = 1u << 0, BTN_B = 1u << 1, BTN_X = 1u << 2, BTN_Y = 1u << 3,
  BTN_LSTICK = 1u << 4, BTN_RSTICK = 1u << 5, BTN_L = 1u << 6, BTN_R = 1u << 7,
  BTN_ZL = 1u << 8, BTN_ZR = 1u << 9, BTN_PLUS = 1u << 10, BTN_MINUS = 1u << 11,
  BTN_DLEFT = 1u << 12, BTN_DUP = 1u << 13, BTN_DRIGHT = 1u << 14, BTN_DDOWN = 1u << 15,
  BTN_LS_LEFT = 1u << 16, BTN_LS_UP = 1u << 17, BTN_LS_RIGHT = 1u << 18, BTN_LS_DOWN = 1u << 19,
  BTN_RS_LEFT = 1u << 20, BTN_RS_UP = 1u << 21, BTN_RS_RIGHT = 1u << 22, BTN_RS_DOWN = 1u << 23,
};
#define BTN_DPAD (BTN_DLEFT | BTN_DUP | BTN_DRIGHT | BTN_DDOWN)

/* Switch 1 layout (0x28 bytes); only the leading fields are touched, so a longer Switch 2 state is
 * harmless as long as the stride between states stays NPAD_STATE_SIZE. */
typedef struct {
  int64_t  sampling_number;
  uint64_t buttons;
  int32_t  lx, ly, rx, ry;
  uint32_t attributes;
} npad_state_t;

#define NPAD_STATE_SIZE     0x28
#define NPAD_ATTR_CONNECTED 1u /* NpadAttribute::IsConnected */

/* A stick axis beyond this sets its direction "button" (the emulator's rule: half the range). */
#define NPAD_STICK_DIRECTION_THRESHOLD (0x7FFF / 2)

#endif
