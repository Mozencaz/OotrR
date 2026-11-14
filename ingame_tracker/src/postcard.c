#include "postcard.h"

#include "sys.h"

#define PERCENT_FULL 100.0f
#define DEFAULT_OPACITY_STEP 1 /* 50 % */
#define MAX_NUMBER_DIGITS 9

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

/* `name=value` and a newline at out + at, if they fit with the final NUL; the new length */
static size_t append_line(char *out, size_t room, size_t at, const char *name, unsigned value)
{
  char digits[MAX_NUMBER_DIGITS + 1];
  size_t digit_count = 0, name_length = strlen(name);
  do {
    digits[digit_count++] = (char)('0' + value % 10);
    value /= 10;
  } while (value);
  if (at + name_length + 1 + digit_count + 1 >= room)
    return at;
  memcpy(out + at, name, name_length);
  at += name_length;
  out[at++] = '=';
  while (digit_count)
    out[at++] = digits[--digit_count];
  out[at++] = '\n';
  return at;
}

size_t postcard_format(const postcard_settings_t *settings, char *out, size_t room)
{
  size_t length = 0;
  for (int i = 0; i < POSTCARD_SETTING_COUNT; i++)
    length = append_line(out, room, length, file_names[i], file_value(settings, (postcard_setting_t)i));
  if (room)
    out[length] = 0;
  return length;
}

/* Sets the setting if `value` is one it can have. */
static bool apply_value(postcard_settings_t *settings, postcard_setting_t setting, uint32_t value)
{
  switch (setting) {
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

static bool name_is(const char *name, const char *text, size_t length)
{
  return strlen(name) == length && !memcmp(name, text, length);
}

/* One line, "name=digits": its setting and number; false if it is anything else. */
static bool read_line(const char *line, const char *end, postcard_setting_t *setting, uint32_t *value)
{
  const char *equals = line;
  while (equals < end && *equals != '=')
    equals++;
  if (equals == end)
    return false;
  int found = -1;
  for (int i = 0; i < POSTCARD_SETTING_COUNT; i++)
    if (name_is(file_names[i], line, (size_t)(equals - line)))
      found = i;
  const char *digit = equals + 1;
  if (found < 0 || digit == end || end - digit > MAX_NUMBER_DIGITS)
    return false;
  *setting = (postcard_setting_t)found;
  *value = 0;
  for (; digit < end; digit++) {
    if (*digit < '0' || *digit > '9')
      return false;
    *value = *value * 10 + (uint32_t)(*digit - '0');
  }
  return true;
}

void postcard_parse(postcard_settings_t *settings, const char *text, size_t size)
{
  const char *end = text + size;
  while (text < end) {
    const char *line_end = text;
    while (line_end < end && *line_end != '\n')
      line_end++;
    const char *content_end = line_end > text && line_end[-1] == '\r' ? line_end - 1 : line_end;
    postcard_setting_t setting;
    uint32_t value;
    if (read_line(text, content_end, &setting, &value))
      apply_value(settings, setting, value);
    text = line_end < end ? line_end + 1 : end;
  }
}
