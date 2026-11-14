/* The game's controller reads, through main's GOT. Module init only hooks two setup imports
 * (nn::hid::InitializeNpad and GetNpadStyleSet); the first call to either, from the game after every
 * module's DT_INIT has run, points the GetNpadStates slots at wrappers that call whatever the slots
 * held then (another module's wrapper, such as sloperinaGZ's), or the sdk's function when a slot was
 * still unbound (got_hook). So the order rtld runs the modules' DT_INITs in doesn't matter, and a
 * module that rewrites those slots at its init without chaining can't undo ours.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef HOOKS_H
#define HOOKS_H

#include <stdint.h>

/* Module init: returns 0 or a message. */
const char *hooks_init(uintptr_t main_base);

#endif
