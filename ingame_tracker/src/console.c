#include "console.h"

#include "cfgtext.h"

#define FILE_VERSION     1
#define ALL_KINDS        ((1u << CONSOLE_KIND_COUNT) - 1)
#define DEFAULT_OPACITY  2 /* 75 % */
#define DEFAULT_LINES    1 /* 6 */
#define DEFAULT_FADE     1 /* 10 s */
#define MS_PER_SECOND    1000u
#define PERCENT_FULL     100.0f

static const char *const setting_names[CONSOLE_SETTING_FIRST_KIND] = {
  [CONSOLE_SETTING_SHOWN] = "Console", [CONSOLE_SETTING_POSITION] = "Position", [CONSOLE_SETTING_OPACITY] = "Opacity",
  [CONSOLE_SETTING_LINES] = "Lines", [CONSOLE_SETTING_FADE] = "Fade",
};
static const char *const position_texts[CONSOLE_POSITION_COUNT] = {
  [CONSOLE_BOTTOM] = "Bottom centre", [CONSOLE_TOP] = "Top centre", [CONSOLE_LEFT] = "Left centre",
  [CONSOLE_RIGHT] = "Right centre",
};
static const char *const kind_names[CONSOLE_KIND_COUNT] = {
  [CONSOLE_RECEIVED] = "Items received", [CONSOLE_SENT] = "Items sent", [CONSOLE_HINT] = "Hints",
  [CONSOLE_CHAT] = "Chat", [CONSOLE_SERVER] = "Server notices", [CONSOLE_OTHERS] = "Other players' items",
};
static const uint8_t opacity_percents[CONSOLE_STEPS] = { 25, 50, 75, 100 };
static const char *const opacity_texts[CONSOLE_STEPS] = { "25 %", "50 %", "75 %", "100 %" };
static const uint8_t line_counts[CONSOLE_STEPS] = { 4, 6, 8, CONSOLE_MAX_LINES };
static const char *const line_texts[CONSOLE_STEPS] = { "4", "6", "8", "12" };
static const uint8_t fade_seconds[CONSOLE_STEPS] = { 5, 10, 30, 0 }; /* 0: permanent */
static const char *const fade_texts[CONSOLE_STEPS] = { "5 s", "10 s", "30 s", "Permanent" };

/* the file's names: its version, the settings, then a line per kind */
enum {
  FILE_VERSION_LINE, FILE_ON_LOCAL, FILE_ON_ARCHIPELAGO, FILE_POSITION, FILE_OPACITY, FILE_LINES, FILE_FADE,
  FILE_FIRST_KIND, FILE_NAME_COUNT = FILE_FIRST_KIND + CONSOLE_KIND_COUNT,
};
static const char *const file_names[FILE_NAME_COUNT] = {
  "version", "on_local", "on_archipelago", "position", "opacity", "lines", "fade",
  "received", "sent", "hints", "chat", "server", "others",
};

console_settings_t console_defaults(void)
{
  return (console_settings_t){ .shown = { false, true }, .position = CONSOLE_BOTTOM, .opacity = DEFAULT_OPACITY,
                               .lines = DEFAULT_LINES, .fade = DEFAULT_FADE, .kinds = ALL_KINDS };
}

bool console_shown(const console_settings_t *settings, bool archipelago)
{
  return settings->shown[archipelago];
}

bool console_over_game(const console_settings_t *settings, bool archipelago, bool panel_open, bool paused)
{
  return console_shown(settings, archipelago) && (panel_open || !paused);
}

bool console_kind_shown(const console_settings_t *settings, console_kind_t kind)
{
  return kind < CONSOLE_KIND_COUNT && (settings->kinds >> kind & 1);
}

static uint8_t step_in_ring(uint8_t value, int direction, unsigned count)
{
  return (uint8_t)((value + (direction < 0 ? count - 1 : 1)) % count);
}

void console_step(console_settings_t *settings, console_setting_t setting, int direction, bool archipelago)
{
  switch (setting) {
    case CONSOLE_SETTING_SHOWN: settings->shown[archipelago] = !settings->shown[archipelago]; break;
    case CONSOLE_SETTING_POSITION:
      settings->position = step_in_ring(settings->position, direction, CONSOLE_POSITION_COUNT);
      break;
    case CONSOLE_SETTING_OPACITY: settings->opacity = step_in_ring(settings->opacity, direction, CONSOLE_STEPS); break;
    case CONSOLE_SETTING_LINES: settings->lines = step_in_ring(settings->lines, direction, CONSOLE_STEPS); break;
    case CONSOLE_SETTING_FADE: settings->fade = step_in_ring(settings->fade, direction, CONSOLE_STEPS); break;
    default:
      if (console_setting_is_kind(setting))
        console_toggle_kind(settings, console_setting_kind(setting));
      break;
  }
}

void console_toggle_kind(console_settings_t *settings, console_kind_t kind)
{
  if (kind < CONSOLE_KIND_COUNT)
    settings->kinds ^= (uint8_t)(1u << kind);
}

bool console_setting_is_kind(console_setting_t setting)
{
  return setting >= CONSOLE_SETTING_FIRST_KIND && setting < CONSOLE_SETTING_COUNT;
}

console_kind_t console_setting_kind(console_setting_t setting)
{
  return console_setting_is_kind(setting) ? (console_kind_t)(setting - CONSOLE_SETTING_FIRST_KIND) : CONSOLE_KIND_COUNT;
}

const char *console_setting_name(console_setting_t setting)
{
  if (console_setting_is_kind(setting))
    return console_kind_name(console_setting_kind(setting));
  return setting < CONSOLE_SETTING_FIRST_KIND ? setting_names[setting] : "";
}

const char *console_value_text(const console_settings_t *settings, console_setting_t setting, bool archipelago)
{
  switch (setting) {
    case CONSOLE_SETTING_SHOWN: return console_shown(settings, archipelago) ? "On" : "Off";
    case CONSOLE_SETTING_POSITION: return position_texts[settings->position % CONSOLE_POSITION_COUNT];
    case CONSOLE_SETTING_OPACITY: return opacity_texts[settings->opacity % CONSOLE_STEPS];
    case CONSOLE_SETTING_LINES: return line_texts[settings->lines % CONSOLE_STEPS];
    case CONSOLE_SETTING_FADE: return fade_texts[settings->fade % CONSOLE_STEPS];
    default: return console_setting_is_kind(setting) ? 0 : "";
  }
}

const char *console_kind_name(console_kind_t kind)
{
  return kind < CONSOLE_KIND_COUNT ? kind_names[kind] : "";
}

float console_opacity(const console_settings_t *settings)
{
  return opacity_percents[settings->opacity % CONSOLE_STEPS] / PERCENT_FULL;
}

int console_lines(const console_settings_t *settings)
{
  return line_counts[settings->lines % CONSOLE_STEPS];
}

uint32_t console_fade_ms(const console_settings_t *settings)
{
  return fade_seconds[settings->fade % CONSOLE_STEPS] * MS_PER_SECOND;
}

/* --- the file ----------------------------------------------------------------------------------- */

static uint32_t file_value(const console_settings_t *settings, int name)
{
  switch (name) {
    case FILE_VERSION_LINE: return FILE_VERSION;
    case FILE_ON_LOCAL: return settings->shown[0];
    case FILE_ON_ARCHIPELAGO: return settings->shown[1];
    case FILE_POSITION: return settings->position;
    case FILE_OPACITY: return opacity_percents[settings->opacity % CONSOLE_STEPS];
    case FILE_LINES: return line_counts[settings->lines % CONSOLE_STEPS];
    case FILE_FADE: return fade_seconds[settings->fade % CONSOLE_STEPS];
    default: return console_kind_shown(settings, (console_kind_t)(name - FILE_FIRST_KIND));
  }
}

size_t console_format(const console_settings_t *settings, char *out, size_t room)
{
  size_t length = 0;
  for (int name = 0; name < FILE_NAME_COUNT; name++)
    length = cfgtext_line(out, room, length, file_names[name], file_value(settings, name));
  if (room)
    out[length] = 0;
  return length;
}

/* the step whose value is `value`, if any */
static bool apply_step(uint8_t *to, const uint8_t values[CONSOLE_STEPS], uint32_t value)
{
  for (int i = 0; i < CONSOLE_STEPS; i++) {
    if (values[i] == value) {
      *to = (uint8_t)i;
      return true;
    }
  }
  return false;
}

typedef struct {
  console_settings_t settings;
  bool versioned;
} parsing_t;

static bool apply_value(void *to, int name, uint32_t value)
{
  parsing_t *parsing = to;
  console_settings_t *s = &parsing->settings;
  switch (name) {
    case FILE_VERSION_LINE:
      parsing->versioned = value == FILE_VERSION;
      return parsing->versioned;
    case FILE_POSITION:
      if (value >= CONSOLE_POSITION_COUNT)
        return false;
      s->position = (uint8_t)value;
      return true;
    case FILE_OPACITY: return apply_step(&s->opacity, opacity_percents, value);
    case FILE_LINES: return apply_step(&s->lines, line_counts, value);
    case FILE_FADE: return apply_step(&s->fade, fade_seconds, value);
    default:
      if (value > 1)
        return false;
      if (name == FILE_ON_LOCAL || name == FILE_ON_ARCHIPELAGO)
        s->shown[name == FILE_ON_ARCHIPELAGO] = value == 1;
      else if ((value == 1) != console_kind_shown(s, (console_kind_t)(name - FILE_FIRST_KIND)))
        console_toggle_kind(s, (console_kind_t)(name - FILE_FIRST_KIND));
      return true;
  }
}

void console_parse(console_settings_t *settings, const char *text, size_t size)
{
  parsing_t parsing = { *settings, false };
  cfgtext_parse(text, size, file_names, FILE_NAME_COUNT, apply_value, &parsing);
  if (parsing.versioned)
    *settings = parsing.settings;
}
