#include "text.h"

bool text_equal(const char *a, const char *b)
{
  while (*a && *a == *b) {
    a++;
    b++;
  }
  return *a == *b;
}

bool text_starts_with(const char *text, const char *prefix)
{
  while (*prefix && *text == *prefix) {
    text++;
    prefix++;
  }
  return !*prefix;
}

size_t text_copy(char *to, size_t room, const char *from)
{
  size_t kept = 0;
  while (room && kept < room - 1 && from[kept]) {
    to[kept] = from[kept];
    kept++;
  }
  if (room)
    to[kept] = 0;
  return kept;
}
