/* The tracker's controls: R + right stick up opens and closes the panel. While it's open the D-pad or the left
 * stick moves its highlight (held, it repeats), A opens a region's list and B goes back, or closes. While the
 * panel is open (or the combination is held) the game doesn't see R or the right stick, nor, with the panel open,
 * A, B, the D-pad or the left stick; the buttons still held when it closes stay hidden until they're let go.
 * R + right stick down is sloperinaGZ's menu, so it is left alone.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#ifndef CONTROLS_H
#define CONTROLS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
  CONTROL_NONE, CONTROL_TOGGLE, CONTROL_BACK, CONTROL_SELECT,
  CONTROL_UP, CONTROL_DOWN, CONTROL_LEFT, CONTROL_RIGHT,
} control_t;

/* The command of this frame, from every button held on any controller during it, at `now_ms`. Only the
 * combination counts while the panel is closed. */
control_t controls_frame(uint32_t held, bool panel_open, uint64_t now_ms);
/* The panel was just closed: what the last frame held stays hidden from the game until it's let go. */
void controls_hold_back_held(void);
/* R and right stick up are both down in `buttons`. */
bool controls_combo_held(uint32_t buttons);
/* The buttons to hide from the game in a state with `buttons`. */
uint32_t controls_hidden(uint32_t buttons, bool panel_open);
/* Whether a stick's axes are to be centred for the game in this state. */
bool controls_centres_right_stick(uint32_t buttons, bool panel_open);
bool controls_centres_left_stick(bool panel_open);
/* Forget the buttons seen so far. */
void controls_reset(void);

#endif
