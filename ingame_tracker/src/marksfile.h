/* The checks ticked by hand (marks.h) on the SD card, one file per seed: ootrTracker/marks-<seed id>.cfg, next to the
 * postcard's and the console's settings (sdfile.c). Not next to seed.trk: that is in the game's RomFS, which the game
 * can't write. */
#ifndef MARKSFILE_H
#define MARKSFILE_H

#include <stdbool.h>

#include "marks.h"

/* Reads the seed's file over `marks` (marks_init's); a missing, damaged or other seed's file leaves them as they
 * were. Game thread, after the game's files are mounted. */
void marksfile_load(marks_t *marks, const trk_t *trk);
/* Writes the file again; false (logged) if there is no SD card or the write failed. */
bool marksfile_save(const marks_t *marks, const trk_t *trk);

#endif
