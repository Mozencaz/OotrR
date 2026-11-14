/* The tracker's controls: R + right stick up opens and closes the panel, B closes it. While the panel is open
 * (or the combination is held) the game doesn't see R, the right stick or, with the panel open, B. R + right stick
 * down is sloperinaGZ's menu, so it is left alone.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#ifndef CONTROLS_H
#define CONTROLS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum { CONTROL_NONE, CONTROL_TOGGLE, CONTROL_CLOSE } control_t;

/* The command pressed this frame, from every button held on any controller during it. `panel_open`: whether
 * B closes. */
control_t controls_frame(uint32_t held, bool panel_open);
/* R and right stick up are both down in `buttons`. */
bool controls_combo_held(uint32_t buttons);
/* The buttons to hide from the game in a state with `buttons`: none unless the combination is held or the
 * panel is open. */
uint32_t controls_hidden(uint32_t buttons, bool panel_open);
/* Whether the right stick's axes are to be centred for the game in this state. */
bool controls_centres_stick(uint32_t buttons, bool panel_open);
/* Forget the buttons seen last frame. */
void controls_reset(void);

#endif
