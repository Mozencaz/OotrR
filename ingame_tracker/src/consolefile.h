/* The console's settings in ootrTracker/console.cfg on the SD card (sdfile.c), as the postcard's are kept. */
#ifndef CONSOLEFILE_H
#define CONSOLEFILE_H

#include <stdbool.h>

#include "console.h"

/* Reads the file over `settings`; a missing, damaged or other version's file leaves them as they were. Game thread,
 * after the game's files are mounted. */
void consolefile_load(console_settings_t *settings);
/* Writes the file again; false (logged) if there is no SD card or the write failed. */
bool consolefile_save(const console_settings_t *settings);

#endif
