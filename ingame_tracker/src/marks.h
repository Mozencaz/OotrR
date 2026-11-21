/* Checks ticked by hand: A on a check of a region's list ticks it, A again unticks it, as a double click does in the
 * randomizer's desktop tracker ("Done (manual)"). A tick counts the check as found, as the desktop tracker counts its
 * own; a check the save shows collected stays collected and can't be ticked or unticked. The ticks are kept by the
 * checks' ids (seed file version 4), one file per seed on the SD card (marksfile.c), so they last from one game to
 * the next and through an update of the seed's tracker; an older seed file has no ids, so nothing can be ticked.
 * The file is:
 *
 *   ootrTracker marks 1
 *   seed <the seed's id>
 *   check <a check's id>      (one line per tick, in the seed file's order)
 *   end <the ticks> <FNV-1a of every byte before this line, 8 hexadecimal digits>
 *
 * Pure: the tests run it on the PC. */
#ifndef MARKS_H
#define MARKS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "trkfile.h"

#define MARKS_MAX_CHECKS 4096        /* a seed file with more checks can't have ticks */
#define MARKS_FILE_ROOM  (32u << 10) /* the file's most: a tick that would make it larger is refused */
#define MARKS_IDENT_MAX  160         /* a longer id, or one with a control character, can't be ticked */

typedef enum {
  MARKS_ON,
  MARKS_OLD_FILE, /* the seed file is older than version 4: no ids */
  MARKS_UNUSABLE, /* more checks than MARKS_MAX_CHECKS, or a seed id that can't be written */
} marks_state_t;

typedef enum { MARK_TICKED, MARK_UNTICKED, MARK_REFUSED } mark_result_t;

typedef struct {
  marks_state_t state;
  uint32_t check_count; /* the seed file's */
  uint32_t count;       /* checks ticked */
  size_t length;        /* of the file marks_format writes */
  uint8_t bits[MARKS_MAX_CHECKS / 8];
} marks_t;

/* No ticks yet, for seed file `trk`. */
void marks_init(marks_t *marks, const trk_t *trk);
bool marks_has(const marks_t *marks, uint32_t check);
/* Whether check `check` can be ticked: the ticks are on and its id is one the file can hold. */
bool marks_can_tick(const marks_t *marks, const trk_t *trk, uint32_t check);
/* Ticks check `check`, or unticks it if it was; refused (nothing changes) if it can't be ticked or the file would
 * get larger than MARKS_FILE_ROOM. */
mark_result_t marks_toggle(marks_t *marks, const trk_t *trk, uint32_t check);

/* The file's text in `out`: its length (marks->length), or 0 if it doesn't fit in `room` or the ticks are off. */
size_t marks_format(const marks_t *marks, const trk_t *trk, char *out, size_t room);
/* Reads a file marks_format wrote over `marks`. False, and nothing changes, if the ticks are off or the text isn't
 * a whole file of this version and this seed (cut short, a wrong count or sum, another seed's). A line of an id the
 * seed file doesn't have is left out, as the desktop tracker leaves out ids its seed doesn't have. */
bool marks_parse(marks_t *marks, const trk_t *trk, const char *text, size_t size);
/* The file's name for this seed, "marks-<seed id>.cfg" (`copy`: "marks-<seed id>.new"); false if the seed's id isn't
 * 1 to 32 letters and digits. */
bool marks_file_name(const trk_t *trk, bool copy, char *out, size_t room);

#endif
