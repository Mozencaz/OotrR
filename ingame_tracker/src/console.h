/* The Archipelago console's settings: whether it is shown (for local and for Archipelago seeds apart), where, how
 * opaque, how many lines, how long a line stays, and which kinds of message it shows. Pure: the lines are
 * consolelog.c's, the drawing trackerui.c's, the file on the SD card consolefile.c's. */
#ifndef CONSOLE_H
#define CONSOLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { CONSOLE_BOTTOM, CONSOLE_TOP, CONSOLE_LEFT, CONSOLE_RIGHT, CONSOLE_POSITION_COUNT } console_position_t;
/* the kinds of message, as the mailbox numbers them less one (mailbox.h); a new kind goes last, so that the mailbox's
 * numbers and the bits of saved settings keep their meaning */
typedef enum {
  CONSOLE_RECEIVED, CONSOLE_SENT, CONSOLE_HINT, CONSOLE_CHAT, CONSOLE_SERVER, CONSOLE_OTHERS, CONSOLE_KIND_COUNT,
} console_kind_t;
/* the Console page's rows, in order: the settings with a value, then a row per kind of message, ticked or not */
typedef enum {
  CONSOLE_SETTING_SHOWN, CONSOLE_SETTING_POSITION, CONSOLE_SETTING_OPACITY, CONSOLE_SETTING_LINES,
  CONSOLE_SETTING_FADE, CONSOLE_SETTING_FIRST_KIND,
  CONSOLE_SETTING_COUNT = CONSOLE_SETTING_FIRST_KIND + CONSOLE_KIND_COUNT,
} console_setting_t;
#define CONSOLE_STEPS     4  /* opacity, lines and fade each have four values */
#define CONSOLE_MAX_LINES 12 /* the most lines it shows */

typedef struct {
  bool shown[2];    /* [0]: local seeds, [1]: Archipelago seeds */
  uint8_t position; /* console_position_t */
  uint8_t opacity;  /* 0 to CONSOLE_STEPS - 1: 25, 50, 75, 100 % */
  uint8_t lines;    /* ... 4, 6, 8, 12 */
  uint8_t fade;     /* ... 5 s, 10 s, 30 s, permanent */
  uint8_t kinds;    /* a bit per console_kind_t: shown */
} console_settings_t;

/* Off for local seeds, on for Archipelago ones; bottom centre, 75 %, 6 lines, 10 s, every kind. A file without a
 * kind's line (one written before that kind came) leaves it at this default. */
console_settings_t console_defaults(void);
bool console_shown(const console_settings_t *settings, bool archipelago);
/* Whether the console is handed over to be drawn: it is on for this kind of seed and the game isn't paused, so the
 * pause screen and the item menus stay clear; with the panel open (opened on purpose) the pause doesn't count, and
 * the Console page shows it as its preview. */
bool console_over_game(const console_settings_t *settings, bool archipelago, bool panel_open, bool paused);
bool console_kind_shown(const console_settings_t *settings, console_kind_t kind);
/* Moves a setting of the Console page one value on (+1) or back (-1), round its values; On/Off is the one of
 * this kind of seed. A kind's row ticks or unticks it, either way. */
void console_step(console_settings_t *settings, console_setting_t setting, int direction, bool archipelago);
void console_toggle_kind(console_settings_t *settings, console_kind_t kind);

/* A row's name: the setting's, or for a kind's row the kind's. */
const char *console_setting_name(console_setting_t setting);
bool console_setting_is_kind(console_setting_t setting);
console_kind_t console_setting_kind(console_setting_t setting);
/* A setting's value as the page shows it ("On", "Bottom centre", "75 %", "6", "10 s"); NULL for a kind's row,
 * which the page shows as a tick box. */
const char *console_value_text(const console_settings_t *settings, console_setting_t setting, bool archipelago);
const char *console_kind_name(console_kind_t kind);

float console_opacity(const console_settings_t *settings);
int console_lines(const console_settings_t *settings);
/* How long a line stays, in milliseconds; 0: for good (the last lines stay). */
uint32_t console_fade_ms(const console_settings_t *settings);

/* The file's text: `version=1`, then a `name=number` line per setting. Returns its length, cut to room - 1. */
size_t console_format(const console_settings_t *settings, char *out, size_t room);
/* Reads the file's text over `settings`. A file without `version=1` (missing, damaged or from another version)
 * leaves them as they were; in one, a line that isn't a known name with a valid value is skipped. */
void console_parse(console_settings_t *settings, const char *text, size_t size);

#endif
