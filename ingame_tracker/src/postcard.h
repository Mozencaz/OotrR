/* The postcard: a small card with the tracker's icons (items, temples, dungeon keys) in a corner of the screen,
 * and its four settings. Pure: the drawing is trackerui.c's, the file on the SD card is postcardfile.c's. */
#ifndef POSTCARD_H
#define POSTCARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
  POSTCARD_TOP_LEFT, POSTCARD_TOP_RIGHT, POSTCARD_BOTTOM_LEFT, POSTCARD_BOTTOM_RIGHT, POSTCARD_POSITION_COUNT,
} postcard_position_t;
typedef enum { POSTCARD_SMALL, POSTCARD_MEDIUM, POSTCARD_LARGE, POSTCARD_SIZE_COUNT } postcard_size_t;
/* the menu's rows, in order */
typedef enum {
  POSTCARD_SETTING_SHOWN, POSTCARD_SETTING_POSITION, POSTCARD_SETTING_SIZE, POSTCARD_SETTING_OPACITY,
  POSTCARD_SETTING_COUNT,
} postcard_setting_t;
#define POSTCARD_OPACITY_COUNT 4

typedef struct {
  bool shown;
  uint8_t position; /* postcard_position_t */
  uint8_t size;     /* postcard_size_t */
  uint8_t opacity;  /* 0 to POSTCARD_OPACITY_COUNT - 1: 25 %, 50 %, 75 %, 100 % */
} postcard_settings_t;

/* Off, bottom right, small, 50 %. */
postcard_settings_t postcard_defaults(void);
/* Whether the card is drawn on its own over the game: it is on, the panel is closed (while the panel is open it
 * draws the card itself, on the Postcard page) and the game isn't paused, so the pause screen and the item menus
 * stay clear. */
bool postcard_over_game(const postcard_settings_t *settings, bool panel_open, bool paused);
/* Moves a setting one value on (direction +1) or back (-1), round the ring of its values. */
void postcard_step(postcard_settings_t *settings, postcard_setting_t setting, int direction);
const char *postcard_setting_name(postcard_setting_t setting);
/* The value of a setting as the menu shows it ("On", "Top left", "Small", "50 %"). */
const char *postcard_value_text(const postcard_settings_t *settings, postcard_setting_t setting);
/* The card's size as a part of its full size, and its opacity from 0 to 1. */
float postcard_scale(const postcard_settings_t *settings);
float postcard_opacity(const postcard_settings_t *settings);
/* The top-left corner of a card of card_w x card_h in an area of area_w x area_h, `margin` from the edges. */
void postcard_origin(postcard_position_t position, float area_w, float area_h, float card_w, float card_h,
                     float margin, float *x, float *y);

/* The file's text: one `name=number` per line (postcard 0 or 1, position and size by their number, opacity in
 * percent). Returns its length, cut to room - 1. */
size_t postcard_format(const postcard_settings_t *settings, char *out, size_t room);
/* Reads what the text sets, line by line, on top of `settings`. A line that isn't a known name with a valid value
 * is skipped, so a damaged or empty file leaves the settings as they were. */
void postcard_parse(postcard_settings_t *settings, const char *text, size_t size);

#endif
