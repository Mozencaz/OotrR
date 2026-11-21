/* "Show in the world": Y on a check of a region's list shows where it is, Y on it again puts it away and Y on
 * another check shows that one instead. The seed file (version 4) holds each check's places in the game's maps; the
 * check is drawn in the world when the game is in one of them (worldmark.c), and named by map otherwise. Only the
 * place is shown, never what the check holds: the file has no rewards. Pure (no game reads), so the tests run it on
 * the PC. */
#ifndef LOCATE_H
#define LOCATE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "trkfile.h"
#include "view.h"

#define LOCATE_NONE      UINT32_MAX /* no check chosen */
#define LOCATE_TEXT_ROOM 160
#define LOCATE_NAME_ROOM 96

typedef enum {
  LOCATE_OFF,         /* no check is shown */
  LOCATE_HERE,        /* in the map the game is in: drawn there */
  LOCATE_ELSEWHERE,   /* in other maps only */
  LOCATE_NOWHERE,     /* the seed file has no place for it (an NPC's gift, an event) */
  LOCATE_OLD_FILE,    /* the seed file is older than version 4: it has no places at all */
  LOCATE_MAP_UNKNOWN, /* the game's map can't be read yet (no save data) */
} locate_state_t;

typedef struct {
  locate_state_t state;
  float point[3];      /* LOCATE_HERE: the check's place in this map */
  const char *label;   /* LOCATE_ELSEWHERE: the first map it is in, to show (it points into the seed file) */
  uint32_t more_maps;  /* LOCATE_ELSEWHERE: how many other maps it is in after that one */
} locate_t;

/* What the present thread draws (overlay.c hands it over), from the game's controller thread (app.c). */
typedef struct {
  bool shown;                   /* a check is shown and the game isn't paused: its band, with the panel closed */
  bool drawn;                   /* ... and it is in this map: its marker, and how far it is */
  float point[3];
  char name[LOCATE_NAME_ROOM];  /* the check's name, as the list shows it */
  char where[LOCATE_TEXT_ROOM]; /* not drawn: where it is ("In Kokiri Forest (child)") */
  uintptr_t camera_holder;      /* main + the build's camera_ptr and disp_ptr (worldmark.c reads them) */
  uintptr_t link_holder;
} locate_view_t;

/* The highlighted check of a region's list, under the list (panel.h). */
typedef struct {
  const char *ident;            /* its internal key, the id the randomizer gives it ("" in older seed files) */
  bool shown;                   /* it is the check shown in the world */
  locate_state_t state;
  char line[LOCATE_TEXT_ROOM];  /* locate_panel_line's */
} locate_detail_t;

/* The seed file's index of region `region`'s check `nth`, or LOCATE_NONE. */
uint32_t locate_check_of(const trk_t *trk, uint32_t region, uint32_t nth);
/* Y on check `check` while `shown` is shown: the check shown from now on. */
uint32_t locate_toggle(uint32_t shown, uint32_t check);
/* Where check `check` is, the game being in map `map` (NULL: not known). */
locate_t locate_find(const trk_t *trk, uint32_t check, const char *map);
/* What to say about it: "12 m away, 3 m up" (from `link`, Link's position, NULL if not known), "In Kokiri Forest
 * (child)", "No place in the world for this check"... */
void locate_describe(const locate_t *where, const float link[3], char *out, size_t room);
/* The panel's line for a check shown: "Shown in the world: " and locate_describe's, or what Y does. */
void locate_panel_line(bool shown, const locate_t *where, const float link[3], char *out, size_t room);
/* The band's line for the check drawn at `point`: how far it is from `link` (NULL: not known) and, when it isn't on
 * the picture (`side`), which way to look: "12 m away, 3 m up, turn left". */
void locate_band_line(const float point[3], const float link[3], view_side_t side, char *out, size_t room);

#endif
