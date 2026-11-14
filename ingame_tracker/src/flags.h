/* What the tracker asks of the game's save data: a flag by hash or key, and a counter by hash. A
 * flag the game doesn't know is GD_UNKNOWN, never false. gamedata.c answers from the running game;
 * the tests answer from a table. */
#ifndef FLAGS_H
#define FLAGS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum { GD_UNKNOWN, GD_FALSE, GD_TRUE } gd_flag_t;

typedef struct flag_source flag_source_t;
struct flag_source {
  gd_flag_t (*bool_flag)(const flag_source_t *source, uint32_t hash);
  gd_flag_t (*bool64_flag)(const flag_source_t *source, uint64_t key);
  bool (*int_value)(const flag_source_t *source, uint32_t hash, int32_t *out);
};

#endif
