#include "consolelog.h"

#include "sys.h"

#define LATIN1_FIRST 0xA0 /* the no-break space; the Latin-1 signs and letters follow it */
#define SOFT_HYPHEN  0xAD
#define REPLACEMENT  '?'

/* the length of the UTF-8 sequence led by `lead` (0: not a lead byte) */
static size_t sequence_length(uint8_t lead)
{
  if (lead >= 0xC2 && lead <= 0xDF)
    return 2;
  if (lead >= 0xE0 && lead <= 0xEF)
    return 3;
  if (lead >= 0xF0 && lead <= 0xF4)
    return 4;
  return 0;
}

/* the code point of the sequence at `in` of `n` bytes, or -1 if a byte after the lead isn't a continuation */
static int32_t decode(const uint8_t *in, size_t n)
{
  int32_t point = in[0] & (0x7F >> n);
  for (size_t i = 1; i < n; i++) {
    if ((in[i] & 0xC0) != 0x80)
      return -1;
    point = point << 6 | (in[i] & 0x3F);
  }
  return point;
}

/* the byte drawn for the character at `in`, and how many bytes it took; 0: nothing drawn */
static uint8_t drawn_byte(const uint8_t *in, size_t left, size_t *used)
{
  uint8_t c = in[0];
  *used = 1;
  if (c == '\t' || c == '\n' || c == '\r')
    return ' ';
  if (c < 0x20 || c == 0x7F)
    return 0;
  if (c < 0x80)
    return c;
  size_t n = sequence_length(c);
  if (!n || n > left)
    return REPLACEMENT;
  int32_t point = decode(in, n);
  if (point < 0)
    return REPLACEMENT;
  *used = n;
  if (point == SOFT_HYPHEN)
    return 0;
  if (point == LATIN1_FIRST)
    return ' ';
  return point > LATIN1_FIRST && point <= 0xFF ? (uint8_t)point : REPLACEMENT;
}

size_t console_sanitize(char *out, size_t room, const uint8_t *in, size_t length)
{
  size_t at = 0;
  for (size_t i = 0; i < length && in[i] && at + 1 < room;) {
    size_t used;
    uint8_t c = drawn_byte(in + i, length - i, &used);
    if (c)
      out[at++] = (char)c;
    i += used;
  }
  if (room)
    out[at] = 0;
  return at;
}

void consolelog_add(console_log_t *log, console_kind_t kind, const uint8_t *text, size_t length, uint64_t now)
{
  console_line_t *line = &log->lines[log->count % CONSOLE_HISTORY];
  if (!console_sanitize(line->text, sizeof(line->text), text, length))
    return;
  line->kind = (uint8_t)kind;
  line->time_ms = now;
  log->count++;
}

void consolelog_view(const console_log_t *log, const console_settings_t *settings, console_view_t *view)
{
  uint32_t kept = log->count < CONSOLE_HISTORY ? log->count : CONSOLE_HISTORY, picked = 0;
  uint32_t newest_first[CONSOLE_MAX_LINES];
  for (uint32_t back = 1; back <= kept && picked < CONSOLE_MAX_LINES; back++) {
    uint32_t n = log->count - back;
    if (console_kind_shown(settings, (console_kind_t)log->lines[n % CONSOLE_HISTORY].kind))
      newest_first[picked++] = n;
  }
  view->count = picked;
  for (uint32_t i = 0; i < picked; i++)
    view->lines[i] = log->lines[newest_first[picked - 1 - i] % CONSOLE_HISTORY];
}

float console_line_alpha(const console_settings_t *settings, uint64_t line_ms, uint64_t now)
{
  uint32_t fade = console_fade_ms(settings);
  if (!fade)
    return 1;
  uint64_t age = now > line_ms ? now - line_ms : 0;
  if (age >= fade)
    return 0;
  uint64_t left = fade - age;
  return left >= CONSOLE_FADE_OUT_MS ? 1 : (float)left / CONSOLE_FADE_OUT_MS;
}

bool console_view_showing(const console_view_t *view, uint64_t now)
{
  if (!view->shown)
    return false;
  if (view->status[0])
    return true;
  return view->count && console_line_alpha(&view->settings, view->lines[view->count - 1].time_ms, now) > 0;
}
