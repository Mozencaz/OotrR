/* The game builds this module knows the memory of (main's offsets, from sloperinaGZ's
 * src/ootgz/z64hd_builds.h, GPL-3). Nothing is read from the game for any other build. */
#ifndef BUILDS_H
#define BUILDS_H

#include <stdint.h>

typedef struct {
  const char *version;
  uint32_t nnmain;       /* nnMain's offset from main's base */
  uint32_t mod0;         /* where main's MOD0 header is (the word at base + 4) */
  uint32_t gd_mgr_ptr;   /* main + this: a pointer to a pointer to the GameData manager */
  uint32_t vt_int_field; /* the vtable of an Int field object */
  uint32_t vt_bool_type; /* the vtable of the Bool type entry in the manager */
} game_build_t;

typedef struct {
  const game_build_t *build; /* NULL: not a build this module knows */
  uintptr_t main_base;
} game_t;

/* Which known build `nnmain_address` (nnMain's address as rtld linked it) belongs to, checked against
 * main's MOD0 header. */
game_t builds_detect(uintptr_t nnmain_address);

#endif
