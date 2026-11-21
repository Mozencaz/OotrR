/* Two recording slots on the game's queue, for the drawing that goes in before each present. A slot has
 * its own command memory, control memory and fence, and is reused only once the GPU has finished with
 * what it was last given, so what a slot's commands read (pixels, elements) stays put until then.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef SLOTS_H
#define SLOTS_H

#include <stdbool.h>
#include <stddef.h>

#include "nvn.h"

#define SLOT_COUNT 2

/* Once the game has a device: the command memory (command_bytes per slot), the fences. False, with the
 * reason logged, if something is missing or there's no memory. */
bool slots_init(size_t command_bytes);
/* The slot for this frame, with the GPU done with its last use; -1 if it isn't yet (a frame is then left
 * undrawn rather than held up; slots_stuck says when that has gone on too long). */
int slots_acquire(void);
/* The GPU has not finished a slot's work for several seconds: stop drawing for good. */
bool slots_stuck(void);
/* The slot's command buffer, recording. */
nvn_obj_t *slots_begin(int slot);
/* Ends the recording and queues it on the game's queue, with a fence on the slot. */
void slots_submit(nvn_queue_t *queue, int slot);
/* Ends the recording and drops it: nothing was drawn. */
void slots_discard(void);
/* Waits until every slot's work is done (the glyph atlas starts afresh); false if the GPU doesn't finish. */
bool slots_wait_idle(void);

#endif
