#include "postcard.h"

#include "cfgtext.h"
#include "sys.h"

#define PERCENT_FULL 100.0f
#define DEFAULT_OPACITY_STEP 1 /* 50 % */

static const char *const setting_names[POSTCARD_SETTING_COUNT] = {
  [POSTCARD_SETTING_SHOWN] = "Postcard", [POSTCARD_SETTING_POSITION] = "Position", [POSTCARD_SETTING_SIZE] = "Size",
  [POSTCARD_SETTING_OPACITY] = "Opacity",
};
static const char *const position_texts[POSTCARD_POSITION_COUNT] = {
  [POSTCARD_TOP_LEFT] = "Top left", [POSTCARD_TOP_RIGHT] = "Top right", [POSTCARD_BOTTOM_LEFT] = "Bottom left",
  [POSTCARD_BOTTOM_RIGHT] = "Bottom right",
};
static const char *const size_texts[POSTCARD_SIZE_COUNT] = {
  [POSTCARD_SMALL] = "Small", [POSTCARD_MEDIUM] = "Medium", [POSTCARD_LARGE] = "Large",
};
static const float size_scales[POSTCARD_SIZE_COUNT] = {
  [POSTCARD_SMALL] = 0.55f, [POSTCARD_MEDIUM] = 0.75f, [POSTCARD_LARGE] = 1.0f,
};
static const uint8_t opacity_percents[POSTCARD_OPACITY_COUNT] = { 25, 50, 75, 100 };
static const char *const opacity_texts[POSTCARD_OPACITY_COUNT] = { "25 %", "50 %", "75 %", "100 %" };

/* the file's names, in the order of postcard_setting_t */
static const char *const file_names[POSTCARD_SETTING_COUNT] = { "postcard", "position", "size", "opacity" };

postcard_settings_t postcard_defaults(void)
{
  return (postcard_settings_t){ .shown = false, .position = POSTCARD_BOTTOM_RIGHT, .size = POSTCARD_SMALL,
                                .opacity = DEFAULT_OPACITY_STEP };
}

bool postcard_over_game(const postcard_settings_t *settings, bool panel_open, bool paused)
{
  return settings->shown && !panel_open && !paused;
}

static uint8_t step_in_ring(uint8_t value, int direction, unsigned count)
{
  return (uint8_t)((value + (direction < 0 ? count - 1 : 1)) % count);
}

void postcard_step(postcard_settings_t *settings, postcard_setting_t setting, int direction)
{
  switch (setting) {
    case POSTCARD_SETTING_SHOWN:
      settings->shown = !settings->shown;
      break;
    case POSTCARD_SETTING_POSITION:
      settings->position = step_in_ring(settings->position, direction, POSTCARD_POSITION_COUNT);
      break;
    case POSTCARD_SETTING_SIZE:
      settings->size = step_in_ring(settings->size, direction, POSTCARD_SIZE_COUNT);
      break;
    case POSTCARD_SETTING_OPACITY:
      settings->opacity = step_in_ring(settings->opacity, direction, POSTCARD_OPACITY_COUNT);
      break;
    default:
      break;
  }
}

const char *postcard_setting_name(postcard_setting_t setting)
{
  return setting < POSTCARD_SETTING_COUNT ? setting_names[setting] : "";
}

const char *postcard_value_text(const postcard_settings_t *settings, postcard_setting_t setting)
{
  switch (setting) {
    case POSTCARD_SETTING_SHOWN: return settings->shown ? "On" : "Off";
    case POSTCARD_SETTING_POSITION: return position_texts[settings->position % POSTCARD_POSITION_COUNT];
    case POSTCARD_SETTING_SIZE: return size_texts[settings->size % POSTCARD_SIZE_COUNT];
    case POSTCARD_SETTING_OPACITY: return opacity_texts[settings->opacity % POSTCARD_OPACITY_COUNT];
    default: return "";
  }
}

float postcard_scale(const postcard_settings_t *settings)
{
  return size_scales[settings->size % POSTCARD_SIZE_COUNT];
}

float postcard_opacity(const postcard_settings_t *settings)
{
  return opacity_percents[settings->opacity % POSTCARD_OPACITY_COUNT] / PERCENT_FULL;
}

void postcard_origin(postcard_position_t position, float area_w, float area_h, float card_w, float card_h,
                     float margin, float *x, float *y)
{
  bool right = position == POSTCARD_TOP_RIGHT || position == POSTCARD_BOTTOM_RIGHT;
  bool bottom = position == POSTCARD_BOTTOM_LEFT || position == POSTCARD_BOTTOM_RIGHT;
  *x = right ? area_w - margin - card_w : margin;
  *y = bottom ? area_h - margin - card_h : margin;
}

/* --- the file ----------------------------------------------------------------------------------- */

static unsigned file_value(const postcard_settings_t *settings, postcard_setting_t setting)
{
  switch (setting) {
    case POSTCARD_SETTING_SHOWN: return settings->shown;
    case POSTCARD_SETTING_POSITION: return settings->position;
    case POSTCARD_SETTING_SIZE: return settings->size;
    default: return opacity_percents[settings->opacity % POSTCARD_OPACITY_COUNT];
  }
}

size_t postcard_format(const postcard_settings_t *settings, char *out, size_t room)
{
  size_t length = 0;
  for (int i = 0; i < POSTCARD_SETTING_COUNT; i++)
    length = cfgtext_line(out, room, length, file_names[i], file_value(settings, (postcard_setting_t)i));
  if (room)
    out[length] = 0;
  return length;
}

/* Sets the setting if `value` is one it can have. */
static bool apply_value(void *to, int name, uint32_t value)
{
  postcard_settings_t *settings = to;
  switch ((postcard_setting_t)name) {
    case POSTCARD_SETTING_SHOWN:
      if (value > 1)
        return false;
      settings->shown = value == 1;
      return true;
    case POSTCARD_SETTING_POSITION:
      if (value >= POSTCARD_POSITION_COUNT)
        return false;
      settings->position = (uint8_t)value;
      return true;
    case POSTCARD_SETTING_SIZE:
      if (value >= POSTCARD_SIZE_COUNT)
        return false;
      settings->size = (uint8_t)value;
      return true;
    default:
      for (uint8_t i = 0; i < POSTCARD_OPACITY_COUNT; i++) {
        if (opacity_percents[i] == value) {
          settings->opacity = i;
          return true;
        }
      }
      return false;
  }
}

void postcard_parse(postcard_settings_t *settings, const char *text, size_t size)
{
  cfgtext_parse(text, size, file_names, POSTCARD_SETTING_COUNT, apply_value, settings);
}
