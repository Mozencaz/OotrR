/* What the add-on does with each game frame and each controller state the game reads.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#ifndef APP_H
#define APP_H

#include <stdint.h>

#include "npad.h"

/* Module init: which game build this is. `nnmain_address`: nnMain as rtld linked it. */
void app_init(uintptr_t nnmain_address);
/* A game frame ended; `held` is every button held on a connected controller during it. */
void app_frame(uint32_t held);
/* A controller state the game is about to see (connected ones only). */
void app_edit_state(npad_state_t *state);

#endif
