/* The Archipelago console's lines: those the desktop client sent (mailbox.c) with the time they came, and what of
 * them the present thread is handed to draw. Pure. */
#ifndef CONSOLELOG_H
#define CONSOLELOG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "console.h"

#define CONSOLE_TEXT_ROOM   160 /* a line's text with its NUL */
#define CONSOLE_STATUS_ROOM 96  /* the status line's */
#define CONSOLE_HISTORY     32  /* lines kept, of every kind */
#define CONSOLE_FADE_OUT_MS 1000 /* a line fades out over its last second */

typedef struct {
  uint8_t kind; /* console_kind_t */
  uint64_t time_ms;
  char text[CONSOLE_TEXT_ROOM];
} console_line_t;

typedef struct {
  console_line_t lines[CONSOLE_HISTORY]; /* line n is at n % CONSOLE_HISTORY */
  uint32_t count;                        /* lines ever added */
} console_log_t;

/* What the present thread draws: the settings, the status line (empty: none) and the newest lines of the kinds
 * shown, oldest first. Whether each is still shown is worked out at each frame from its time. */
typedef struct {
  console_settings_t settings;
  bool shown; /* the console is on for this seed */
  char status[CONSOLE_STATUS_ROOM];
  uint32_t count;
  console_line_t lines[CONSOLE_MAX_LINES];
} console_view_t;

/* Text as the game's font can draw it, from UTF-8: printable ASCII and Latin-1 letters and signs as one byte each,
 * any other character as one '?', a tab or a line break as a space, other control characters left out. At most
 * room - 1 bytes and a NUL; returns the length. */
size_t console_sanitize(char *out, size_t room, const uint8_t *in, size_t length);

/* A line that came at `now` (its text is sanitised; an empty one isn't kept). */
void consolelog_add(console_log_t *log, console_kind_t kind, const uint8_t *text, size_t length, uint64_t now);
/* The view of the log: the newest CONSOLE_MAX_LINES lines whose kind the settings show, oldest first. */
void consolelog_view(const console_log_t *log, const console_settings_t *settings, console_view_t *view);

/* A line's opacity at `now`: 1, then down to 0 over its last CONSOLE_FADE_OUT_MS, 0 once it has gone; always 1
 * with a permanent fade. */
float console_line_alpha(const console_settings_t *settings, uint64_t line_ms, uint64_t now);
/* Whether the view has anything to draw at `now` with the panel closed. */
bool console_view_showing(const console_view_t *view, uint64_t now);

#endif
