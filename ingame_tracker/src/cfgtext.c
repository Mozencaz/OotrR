#include "cfgtext.h"

#include "sys.h"

#define MAX_NUMBER_DIGITS 9

size_t cfgtext_line(char *out, size_t room, size_t at, const char *name, uint32_t value)
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

static bool name_is(const char *name, const char *text, size_t length)
{
  return strlen(name) == length && !memcmp(name, text, length);
}

/* One line, "name=digits": its name's index and number; false if it is anything else. */
static bool read_line(const char *line, const char *end, const char *const *names, int name_count, int *name,
                      uint32_t *value)
{
  const char *equals = line;
  while (equals < end && *equals != '=')
    equals++;
  if (equals == end)
    return false;
  int found = -1;
  for (int i = 0; i < name_count; i++)
    if (name_is(names[i], line, (size_t)(equals - line)))
      found = i;
  const char *digit = equals + 1;
  if (found < 0 || digit == end || end - digit > MAX_NUMBER_DIGITS)
    return false;
  *name = found;
  *value = 0;
  for (; digit < end; digit++) {
    if (*digit < '0' || *digit > '9')
      return false;
    *value = *value * 10 + (uint32_t)(*digit - '0');
  }
  return true;
}

void cfgtext_parse(const char *text, size_t size, const char *const *names, int name_count, cfgtext_apply_t apply,
                   void *settings)
{
  const char *end = text + size;
  while (text < end) {
    const char *line_end = text;
    while (line_end < end && *line_end != '\n')
      line_end++;
    const char *content_end = line_end > text && line_end[-1] == '\r' ? line_end - 1 : line_end;
    int name;
    uint32_t value;
    if (read_line(text, content_end, names, name_count, &name, &value))
      apply(settings, name, value);
    text = line_end < end ? line_end + 1 : end;
  }
}
