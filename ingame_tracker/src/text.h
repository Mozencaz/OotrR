/* Small string helpers: the module has no libc beyond what the game's sdk exports. */
#ifndef TEXT_H
#define TEXT_H

#include <stdbool.h>
#include <stddef.h>

bool text_equal(const char *a, const char *b);
bool text_starts_with(const char *text, const char *prefix);
/* Copies at most room - 1 characters of `from` and ends `to` with a NUL; returns how many it kept. */
size_t text_copy(char *to, size_t room, const char *from);

#endif
