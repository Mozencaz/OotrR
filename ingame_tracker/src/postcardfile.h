/* The postcard's settings in a small file on the SD card, written and read through the game's own nn::fs as
 * sloperinaGZ keeps its settings (src/ootgz/settings.c, GPL-3). The card is user:/sdmc/ootrTracker/postcard.cfg
 * in an emulator's user folder. Without an SD card the settings only last until the game is closed. */
#ifndef POSTCARDFILE_H
#define POSTCARDFILE_H

#include <stdbool.h>

#include "postcard.h"

/* Mounts the SD card and reads the file on top of `settings`; a missing or damaged file leaves them as they were.
 * Game thread, once, after the game's files are mounted. */
void postcardfile_load(postcard_settings_t *settings);
/* Writes the file again; false (logged) if there is no SD card or the write failed. */
bool postcardfile_save(const postcard_settings_t *settings);

#endif
