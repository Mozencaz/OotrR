/* Small files on the SD card (ootrTracker/<name>.cfg: the postcard's and the console's settings, the ticks of
 * marksfile.c), written and read through the game's own nn::fs as sloperinaGZ keeps its settings
 * (src/ootgz/settings.c, GPL-3). The card is user:/sdmc in an emulator's user folder. The card is mounted once, at the
 * first read; without it nothing is kept past the game's end. */
#ifndef SDFILE_H
#define SDFILE_H

#include <stdbool.h>
#include <stddef.h>

#define SDFILE_DIR "ootrtrk:/ootrTracker" /* a mount name can only be used once: not sloperinaGZ's or ocarinaMIDI's */

/* Reads the file at `path` (at most `room` bytes) into `text`; false, logged with `who` first, if the card or the
 * file can't be read (`size` is then 0). Game thread, after the game's files are mounted. */
bool sdfile_read(const char *who, const char *path, char *text, size_t room, size_t *size);
/* Writes the file again; false (logged) if there is no card or the write failed. */
bool sdfile_write(const char *who, const char *path, const char *text, size_t length);
/* Deletes the file, if the card is mounted (nothing if the file isn't there). */
void sdfile_delete(const char *path);

#endif
