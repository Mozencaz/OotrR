#include "marks.h"

#include "sys.h"

#define FIRST_VERSION_WITH_IDS 4
#define MAGIC_LINE   "ootrTracker marks 1"
#define SEED_WORD    "seed "
#define CHECK_WORD   "check "
#define END_WORD     "end "
#define SUM_DIGITS   8
#define SEED_ID_MAX  32
#define FILE_PREFIX  "marks-"
#define FILE_SUFFIX  ".cfg"
#define COPY_SUFFIX  ".new"
#define FNV_OFFSET   2166136261u
#define FNV_PRIME    16777619u

static size_t digits_of(uint32_t value)
{
  size_t digits = 1;
  for (; value >= 10; value /= 10)
    digits++;
  return digits;
}

/* "end <count> <sum>\n" */
static size_t end_length(uint32_t count)
{
  return sizeof(END_WORD) - 1 + digits_of(count) + 1 + SUM_DIGITS + 1;
}

static bool seed_id_ok(const char *id)
{
  size_t n = 0;
  for (; id[n]; n++) {
    char c = id[n];
    bool alnum = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
    if (!alnum || n >= SEED_ID_MAX)
      return false;
  }
  return n > 0;
}

static bool ident_ok(const char *ident)
{
  size_t n = 0;
  for (; ident[n]; n++)
    if ((unsigned char)ident[n] < 0x20 || ident[n] == 0x7F || n >= MARKS_IDENT_MAX)
      return false;
  return n > 0;
}

static const char *ident_of(const trk_t *trk, uint32_t check)
{
  return trk_string(trk, trk_check_ident(trk, check));
}

static const char *seed_of(const trk_t *trk)
{
  return trk_string(trk, trk->seed_id);
}

static size_t header_length(const trk_t *trk)
{
  return sizeof(MAGIC_LINE) + sizeof(SEED_WORD) - 1 + strlen(seed_of(trk)) + 1;
}

static size_t line_length(const char *ident)
{
  return sizeof(CHECK_WORD) - 1 + strlen(ident) + 1;
}

static uint32_t fnv1a(const char *text, size_t size)
{
  uint32_t sum = FNV_OFFSET;
  for (size_t i = 0; i < size; i++)
    sum = (sum ^ (uint8_t)text[i]) * FNV_PRIME;
  return sum;
}

void marks_init(marks_t *marks, const trk_t *trk)
{
  memset(marks, 0, sizeof(*marks));
  marks->check_count = trk->check_count;
  if (trk->version < FIRST_VERSION_WITH_IDS || !trk->ident_count)
    marks->state = MARKS_OLD_FILE;
  else if (trk->check_count > MARKS_MAX_CHECKS || !seed_id_ok(seed_of(trk)))
    marks->state = MARKS_UNUSABLE;
  else
    marks->state = MARKS_ON;
  marks->length = header_length(trk) + end_length(0);
}

bool marks_has(const marks_t *marks, uint32_t check)
{
  return check < marks->check_count && check < MARKS_MAX_CHECKS && (marks->bits[check >> 3] >> (check & 7) & 1);
}

static void set_bit(uint8_t *bits, uint32_t check, bool on)
{
  if (on)
    bits[check >> 3] |= (uint8_t)(1u << (check & 7));
  else
    bits[check >> 3] &= (uint8_t)~(1u << (check & 7));
}

bool marks_can_tick(const marks_t *marks, const trk_t *trk, uint32_t check)
{
  return marks->state == MARKS_ON && check < marks->check_count && ident_ok(ident_of(trk, check));
}

mark_result_t marks_toggle(marks_t *marks, const trk_t *trk, uint32_t check)
{
  if (!marks_can_tick(marks, trk, check))
    return MARK_REFUSED;
  size_t line = line_length(ident_of(trk, check)), rest = marks->length - end_length(marks->count);
  if (marks_has(marks, check)) {
    set_bit(marks->bits, check, false);
    marks->count--;
    marks->length = rest - line + end_length(marks->count);
    return MARK_UNTICKED;
  }
  size_t length = rest + line + end_length(marks->count + 1);
  if (length > MARKS_FILE_ROOM)
    return MARK_REFUSED;
  set_bit(marks->bits, check, true);
  marks->count++;
  marks->length = length;
  return MARK_TICKED;
}

/* --- the file ---------------------------------------------------------------------------------- */

static void put(char *out, size_t room, size_t *at, const char *text)
{
  while (*text && *at < room)
    out[(*at)++] = *text++;
}

static void put_number(char *out, size_t room, size_t *at, uint32_t value)
{
  char digits[11];
  size_t n = digits_of(value);
  digits[n] = 0;
  for (size_t i = n; i-- > 0; value /= 10)
    digits[i] = (char)('0' + value % 10);
  put(out, room, at, digits);
}

static void put_hex(char *out, size_t room, size_t *at, uint32_t value)
{
  char digits[SUM_DIGITS + 1];
  for (int i = SUM_DIGITS - 1; i >= 0; i--, value >>= 4)
    digits[i] = "0123456789abcdef"[value & 15];
  digits[SUM_DIGITS] = 0;
  put(out, room, at, digits);
}

size_t marks_format(const marks_t *marks, const trk_t *trk, char *out, size_t room)
{
  if (marks->state != MARKS_ON || marks->length > room)
    return 0;
  size_t at = 0;
  put(out, room, &at, MAGIC_LINE "\n" SEED_WORD);
  put(out, room, &at, seed_of(trk));
  put(out, room, &at, "\n");
  for (uint32_t check = 0; check < marks->check_count; check++) {
    if (!marks_has(marks, check))
      continue;
    put(out, room, &at, CHECK_WORD);
    put(out, room, &at, ident_of(trk, check));
    put(out, room, &at, "\n");
  }
  uint32_t sum = fnv1a(out, at);
  put(out, room, &at, END_WORD);
  put_number(out, room, &at, marks->count);
  put(out, room, &at, " ");
  put_hex(out, room, &at, sum);
  put(out, room, &at, "\n");
  return at;
}

/* The line at *at (without its line end), *at moved past it; false if there's no whole line left. */
static bool next_line(const char **at, const char *end, const char **line, size_t *length)
{
  const char *p = *at;
  while (p < end && *p != '\n')
    p++;
  if (p == end)
    return false;
  *line = *at;
  *length = (size_t)(p - *at);
  *at = p + 1;
  return true;
}

static bool line_is(const char *line, size_t length, const char *prefix, const char *rest)
{
  size_t prefix_length = strlen(prefix), rest_length = strlen(rest);
  return length == prefix_length + rest_length && !memcmp(line, prefix, prefix_length) &&
         !memcmp(line + prefix_length, rest, rest_length);
}

static bool starts_with(const char *line, size_t length, const char *prefix)
{
  size_t prefix_length = strlen(prefix);
  return length >= prefix_length && !memcmp(line, prefix, prefix_length);
}

/* "<count> <sum>": both read; false if they're anything else */
static bool read_end(const char *text, size_t length, uint32_t *count, uint32_t *sum)
{
  size_t i = 0;
  uint64_t value = 0;
  for (; i < length && text[i] >= '0' && text[i] <= '9' && value <= UINT32_MAX; i++)
    value = value * 10 + (uint32_t)(text[i] - '0');
  if (!i || value > UINT32_MAX || i + 1 + SUM_DIGITS != length || text[i] != ' ')
    return false;
  *count = (uint32_t)value;
  *sum = 0;
  for (size_t d = i + 1; d < length; d++) {
    char c = text[d];
    uint32_t nibble = c >= '0' && c <= '9' ? (uint32_t)(c - '0') : c >= 'a' && c <= 'f' ? (uint32_t)(c - 'a' + 10) : 16;
    if (nibble > 15)
      return false;
    *sum = *sum << 4 | nibble;
  }
  return true;
}

/* The check whose id is the `length` bytes at `ident`, looked for from `from` on (the file keeps the seed file's
 * order, so the next one is usually there); UINT32_MAX if there is none. */
static uint32_t check_named(const trk_t *trk, uint32_t check_count, const char *ident, size_t length, uint32_t from)
{
  for (uint32_t k = 0; k < check_count; k++) {
    uint32_t check = (from + k) % check_count;
    const char *name = ident_of(trk, check);
    if (strlen(name) == length && !memcmp(name, ident, length))
      return check;
  }
  return UINT32_MAX;
}

bool marks_parse(marks_t *marks, const trk_t *trk, const char *text, size_t size)
{
  if (marks->state != MARKS_ON)
    return false;
  const char *at = text, *end = text + size, *line;
  size_t length;
  if (!next_line(&at, end, &line, &length) || !line_is(line, length, MAGIC_LINE, "") ||
      !next_line(&at, end, &line, &length) || !line_is(line, length, SEED_WORD, seed_of(trk)))
    return false;
  const char *checks_at = at;
  uint32_t lines = 0, count = 0, sum = 0;
  for (;;) {
    if (!next_line(&at, end, &line, &length))
      return false;
    if (starts_with(line, length, END_WORD))
      break;
    size_t ident_length = length - (sizeof(CHECK_WORD) - 1);
    if (!starts_with(line, length, CHECK_WORD) || !ident_length || ident_length > MARKS_IDENT_MAX)
      return false;
    lines++;
  }
  size_t sealed = (size_t)(line - text);
  if (!read_end(line + sizeof(END_WORD) - 1, length - (sizeof(END_WORD) - 1), &count, &sum) || at != end ||
      count != lines || sum != fnv1a(text, sealed))
    return false;
  marks_t read = *marks;
  memset(read.bits, 0, sizeof(read.bits));
  read.count = 0;
  read.length = header_length(trk);
  uint32_t from = 0;
  for (at = checks_at; next_line(&at, end, &line, &length) && starts_with(line, length, CHECK_WORD);) {
    uint32_t check = check_named(trk, read.check_count, line + sizeof(CHECK_WORD) - 1,
                                 length - (sizeof(CHECK_WORD) - 1), from);
    if (check == UINT32_MAX || marks_has(&read, check) || !marks_can_tick(&read, trk, check))
      continue; /* an id this seed file doesn't have, or twice */
    set_bit(read.bits, check, true);
    read.count++;
    read.length += line_length(ident_of(trk, check));
    from = check + 1;
  }
  read.length += end_length(read.count);
  if (read.length > MARKS_FILE_ROOM)
    return false;
  *marks = read;
  return true;
}

bool marks_file_name(const trk_t *trk, bool copy, char *out, size_t room)
{
  const char *seed = seed_of(trk);
  size_t at = 0;
  if (!seed_id_ok(seed) || !room)
    return false;
  put(out, room, &at, FILE_PREFIX);
  put(out, room, &at, seed);
  put(out, room, &at, copy ? COPY_SUFFIX : FILE_SUFFIX);
  if (at >= room)
    return false;
  out[at] = 0;
  return true;
}
