/* The settings files' text (postcard.cfg, console.cfg): one `name=number` line per setting. Pure. */
#ifndef CFGTEXT_H
#define CFGTEXT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* `name=value` and a newline at out + at, if they fit with the final NUL; returns the new length. */
size_t cfgtext_line(char *out, size_t room, size_t at, const char *name, uint32_t value);

/* Sets the setting `name` (an index into the caller's names) to `value`; false if it can't have that value. */
typedef bool (*cfgtext_apply_t)(void *settings, int name, uint32_t value);

/* Hands each line that is one of `names` with a number to `apply`, in order. Any other line is skipped, so a
 * damaged or empty file changes nothing. */
void cfgtext_parse(const char *text, size_t size, const char *const *names, int name_count, cfgtext_apply_t apply,
                   void *settings);

#endif
