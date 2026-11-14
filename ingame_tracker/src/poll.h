/* Every batch of controller states the game reads (hooks.c) passes through here. Game frames are
 * counted from the reads: the first controller the game reads is the anchor, and each new read of it
 * at least MIN_FRAME_MS after the last starts a frame.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef POLL_H
#define POLL_H

#include <stdint.h>

/* `style` indexes the GetNpadStates overloads (hooks.c); `states` holds `count` states. */
void poll_states(int style, uint32_t npad_id, void *states, int count);

#endif
