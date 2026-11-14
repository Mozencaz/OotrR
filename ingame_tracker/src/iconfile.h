/* The items' icons the randomizer writes from the player's game (RandoTracker/icons.bin): for each item, the game's
 * own picture as its BNTX stores it (ASTC 4x4 blocks in the GPU's block-linear layout) and that layout. The format
 * is in docs/ingame-tracker-format.md at the root of the OotrR repository. Only the header and the index are read
 * here, and every field is checked; each picture is read later, by offset, into the GPU's memory. */
#ifndef ICONFILE_H
#define ICONFILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ICONFILE_VERSION 1
#define ICONFILE_HEADER  32
#define ICONFILE_ENTRY   64
#define ICONFILE_MAX     40          /* the icon atlas's slots (gpuui.c) */
#define ICONFILE_NAME    32          /* an item's name, with its NUL */
#define ICONFILE_HEAD_MAX (ICONFILE_HEADER + ICONFILE_MAX * ICONFILE_ENTRY) /* the most a reader needs to parse */
#define ICONFILE_PICTURE_MAX (4u << 20) /* one picture's most bytes */

typedef struct {
  char name[ICONFILE_NAME]; /* the item, as the grid names it */
  uint32_t width, height, offset, size, format; /* format: the BNTX's, ASTC 4x4 (0x2d01 unorm, 0x2d06 sRGB) */
  uint8_t layout[8];        /* the BNTX's packaged layout, as stored */
  uint8_t swizzle[4];       /* the channels' sources, as NVN's swizzle values */
} icon_entry_t;

typedef struct {
  uint32_t count;
  uint32_t largest; /* the largest picture's size */
  icon_entry_t entries[ICONFILE_MAX];
} icon_index_t;

/* The header and the index (the file's first `size` bytes; ICONFILE_HEAD_MAX, or the whole file if it's smaller,
 * is always enough) of a file of `file_size` bytes. False with *why set if it isn't an icons file of this version
 * or anything in it is out of bounds. */
bool iconfile_parse(icon_index_t *index, const uint8_t *head, size_t size, uint64_t file_size, const char **why);

#endif
