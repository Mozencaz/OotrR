#include "iconfile.h"

#include "sys.h"
#include "text.h"

#define MAGIC      0x43495452u /* "RTIC" read as a little-endian word */
#define DATA_ALIGN 16
#define MAX_SIDE   4096
#define BNTX_ASTC_4X4_UNORM 0x2D01u
#define BNTX_ASTC_4X4_SRGB  0x2D06u
#define LAST_SOURCE 5 /* NVN's swizzle values: zero, one, r, g, b, a */

/* header field offsets */
enum { H_MAGIC = 0, H_VERSION = 4, H_HEADER_SIZE = 6, H_FILE_SIZE = 8, H_COUNT = 12, H_INDEX_AT = 16, H_ENTRY_SIZE = 20,
       H_DATA_AT = 24, H_RESERVED = 28 };
/* entry field offsets */
enum { E_NAME = 0, E_WIDTH = 32, E_HEIGHT = 36, E_OFFSET = 40, E_SIZE = 44, E_LAYOUT = 48, E_SWIZZLE = 56, E_FORMAT = 60 };

static uint16_t le16(const uint8_t *p)
{
  return (uint16_t)(p[0] | p[1] << 8);
}

static uint32_t le32(const uint8_t *p)
{
  return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}

static bool terminated(const uint8_t *name)
{
  for (int i = 0; i < ICONFILE_NAME; i++)
    if (!name[i])
      return true;
  return false;
}

static bool fail(const char **why, const char *reason)
{
  *why = reason;
  return false;
}

/* the entry's fields, checked against the file */
static bool read_entry(icon_entry_t *e, const uint8_t *at, uint64_t data_at, uint64_t file_size)
{
  if (!at[E_NAME] || !terminated(at + E_NAME))
    return false;
  memcpy(e->name, at + E_NAME, ICONFILE_NAME);
  e->width = le32(at + E_WIDTH);
  e->height = le32(at + E_HEIGHT);
  e->offset = le32(at + E_OFFSET);
  e->size = le32(at + E_SIZE);
  e->format = le32(at + E_FORMAT);
  memcpy(e->layout, at + E_LAYOUT, sizeof(e->layout));
  memcpy(e->swizzle, at + E_SWIZZLE, sizeof(e->swizzle));
  if (!e->width || e->width > MAX_SIDE || !e->height || e->height > MAX_SIDE)
    return false;
  if (e->format != BNTX_ASTC_4X4_UNORM && e->format != BNTX_ASTC_4X4_SRGB)
    return false;
  uint64_t blocks = (uint64_t)((e->width + 3) / 4) * ((e->height + 3) / 4) * 16;
  if (e->size < blocks || e->size > ICONFILE_PICTURE_MAX)
    return false;
  if (e->offset < data_at || e->offset % DATA_ALIGN || (uint64_t)e->offset + e->size > file_size)
    return false;
  for (int i = 0; i < 4; i++)
    if (e->swizzle[i] > LAST_SOURCE)
      return false;
  return true;
}

bool iconfile_parse(icon_index_t *index, const uint8_t *head, size_t size, uint64_t file_size, const char **why)
{
  memset(index, 0, sizeof(*index));
  if (size < ICONFILE_HEADER)
    return fail(why, "too short");
  if (le32(head + H_MAGIC) != MAGIC || le16(head + H_VERSION) != ICONFILE_VERSION ||
      le16(head + H_HEADER_SIZE) != ICONFILE_HEADER || le32(head + H_ENTRY_SIZE) != ICONFILE_ENTRY ||
      le32(head + H_INDEX_AT) != ICONFILE_HEADER || le32(head + H_RESERVED))
    return fail(why, "not an icons file of a version this module reads");
  uint32_t count = le32(head + H_COUNT), data_at = le32(head + H_DATA_AT);
  if (le32(head + H_FILE_SIZE) != file_size)
    return fail(why, "its size isn't the one its header gives");
  if (!count || count > ICONFILE_MAX || data_at != ICONFILE_HEADER + count * ICONFILE_ENTRY || data_at > file_size)
    return fail(why, "its index doesn't fit");
  if (size < data_at)
    return fail(why, "too short");
  for (uint32_t i = 0; i < count; i++) {
    icon_entry_t *e = &index->entries[i];
    if (!read_entry(e, head + ICONFILE_HEADER + i * ICONFILE_ENTRY, data_at, file_size))
      return fail(why, "an icon's entry is damaged");
    for (uint32_t j = 0; j < i; j++)
      if (text_equal(index->entries[j].name, e->name))
        return fail(why, "two icons of one item");
    if (e->size > index->largest)
      index->largest = e->size;
  }
  index->count = count;
  return true;
}
