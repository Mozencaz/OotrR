#include "trkfile.h"

#define MAGIC            0x4B525452u /* "RTRK" read as a little-endian word */
#define HEADER_SIZE      72
#define REGION_SIZE      12
#define CHECK_SIZE       16
#define ITEM_SIZE        8
#define RULE_SIZE        8
#define KEYS_SIZE        24
#define MAX_RECORDS      (1u << 20) /* far more than any seed has: a count past this is damage */

/* header field offsets */
enum {
  H_MAGIC = 0, H_VERSION = 4, H_HEADER_SIZE = 6, H_FILE_SIZE = 8, H_SEED_MARKER = 12, H_GOAL_MARKER = 16,
  H_SEED_ID = 20, H_STRINGS_AT = 24, H_STRINGS_SIZE = 28, H_REGIONS_AT = 32, H_REGION_COUNT = 36,
  H_CHECKS_AT = 40, H_CHECK_COUNT = 44, H_ITEMS_AT = 48, H_ITEM_COUNT = 52, H_RULES_AT = 56,
  H_RULE_COUNT = 60, H_KEYS_AT = 64, H_KEY_COUNT = 68,
};

static uint16_t le16(const uint8_t *p)
{
  return (uint16_t)(p[0] | p[1] << 8);
}

static uint32_t le32(const uint8_t *p)
{
  return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint64_t le64(const uint8_t *p)
{
  return le32(p) | (uint64_t)le32(p + 4) << 32;
}

/* [at, at + count * record) lies in the file, after the header */
static bool table_fits(size_t size, uint32_t at, uint32_t count, uint32_t record)
{
  return at >= HEADER_SIZE && at <= size && count <= MAX_RECORDS && (uint64_t)count * record <= size - at;
}

/* every region's checks lie in the check table */
static bool regions_fit(const trk_t *trk)
{
  for (uint32_t i = 0; i < trk->region_count; i++) {
    trk_region_t region = trk_region(trk, i);
    if ((uint64_t)region.first_check + region.check_count > trk->check_count)
      return false;
  }
  return true;
}

/* every check's name lies in the string table */
static bool names_fit(const trk_t *trk)
{
  for (uint32_t i = 0; i < trk->check_count; i++)
    if (trk_check(trk, i).name >= trk->strings_size)
      return false;
  return true;
}

/* every item's rules lie in the rule table */
static bool items_fit(const trk_t *trk)
{
  for (uint32_t i = 0; i < trk->item_count; i++) {
    trk_item_t item = trk_item(trk, i);
    if ((uint64_t)item.first_rule + item.rule_count > trk->rule_count)
      return false;
  }
  return true;
}

static bool header_ok(const uint8_t *data, size_t size, const char **why)
{
  if (size < HEADER_SIZE || le32(data + H_MAGIC) != MAGIC) {
    *why = "not a seed file";
    return false;
  }
  uint16_t version = le16(data + H_VERSION);
  if (version < TRK_OLDEST_VERSION || version > TRK_VERSION || le16(data + H_HEADER_SIZE) != HEADER_SIZE) {
    *why = "another version of the seed file";
    return false;
  }
  if (le32(data + H_FILE_SIZE) != size) {
    *why = "the file's size differs from its header";
    return false;
  }
  return true;
}

static void read_header(trk_t *trk, const uint8_t *data, size_t size)
{
  *trk = (trk_t){
    .data = data, .size = size, .version = le16(data + H_VERSION),
    .seed_marker = le32(data + H_SEED_MARKER), .goal_marker = le32(data + H_GOAL_MARKER),
    .seed_id = le32(data + H_SEED_ID),
    .strings_at = le32(data + H_STRINGS_AT), .strings_size = le32(data + H_STRINGS_SIZE),
    .regions_at = le32(data + H_REGIONS_AT), .region_count = le32(data + H_REGION_COUNT),
    .checks_at = le32(data + H_CHECKS_AT), .check_count = le32(data + H_CHECK_COUNT),
    .items_at = le32(data + H_ITEMS_AT), .item_count = le32(data + H_ITEM_COUNT),
    .rules_at = le32(data + H_RULES_AT), .rule_count = le32(data + H_RULE_COUNT),
    .keys_at = le32(data + H_KEYS_AT), .key_count = le32(data + H_KEY_COUNT),
  };
}

bool trk_parse(trk_t *trk, const uint8_t *data, size_t size, const char **why)
{
  if (!header_ok(data, size, why))
    return false;
  read_header(trk, data, size);
  bool strings_fit = trk->strings_at >= HEADER_SIZE && trk->strings_at <= size &&
                     trk->strings_size <= size - trk->strings_at && trk->strings_size > 0;
  if (!strings_fit || data[trk->strings_at + trk->strings_size - 1] != 0) {
    *why = "the string table is damaged";
    return false;
  }
  if (!table_fits(size, trk->regions_at, trk->region_count, REGION_SIZE) ||
      !table_fits(size, trk->checks_at, trk->check_count, CHECK_SIZE) ||
      !table_fits(size, trk->items_at, trk->item_count, ITEM_SIZE) ||
      !table_fits(size, trk->rules_at, trk->rule_count, RULE_SIZE) ||
      !table_fits(size, trk->keys_at, trk->key_count, KEYS_SIZE)) {
    *why = "a table leaves the file";
    return false;
  }
  if (trk->region_count > TRK_MAX_REGIONS || trk->key_count > TRK_MAX_KEY_ROWS) {
    *why = "more regions or dungeons than this module can show";
    return false;
  }
  if (!regions_fit(trk) || !items_fit(trk)) {
    *why = "a region or an item points outside its table";
    return false;
  }
  if (!names_fit(trk)) {
    *why = "a check's name is outside the string table";
    return false;
  }
  return true;
}

const char *trk_string(const trk_t *trk, uint32_t offset)
{
  return offset < trk->strings_size ? (const char *)trk->data + trk->strings_at + offset : "";
}

trk_region_t trk_region(const trk_t *trk, uint32_t index)
{
  const uint8_t *row = trk->data + trk->regions_at + (size_t)index * REGION_SIZE;
  return (trk_region_t){ le32(row), le32(row + 4), le32(row + 8) };
}

trk_check_t trk_check(const trk_t *trk, uint32_t index)
{
  const uint8_t *row = trk->data + trk->checks_at + (size_t)index * CHECK_SIZE;
  return (trk_check_t){ le64(row), le32(row + 8), le32(row + 12) };
}

trk_item_t trk_item(const trk_t *trk, uint32_t index)
{
  const uint8_t *row = trk->data + trk->items_at + (size_t)index * ITEM_SIZE;
  return (trk_item_t){ le32(row), le16(row + 4), le16(row + 6) };
}

trk_rule_t trk_rule(const trk_t *trk, uint32_t index)
{
  const uint8_t *row = trk->data + trk->rules_at + (size_t)index * RULE_SIZE;
  return (trk_rule_t){ le32(row), le16(row + 4) };
}

trk_keys_t trk_keys(const trk_t *trk, uint32_t index)
{
  const uint8_t *row = trk->data + trk->keys_at + (size_t)index * KEYS_SIZE;
  return (trk_keys_t){ le32(row), row[4], row[5], le32(row + 8), le32(row + 12), le32(row + 16), le32(row + 20) };
}
