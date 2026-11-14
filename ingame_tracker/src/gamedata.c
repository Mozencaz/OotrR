#include "gamedata.h"

#include "sys.h"

/* Offsets in the GameData manager, the same in every known build */
#define MANAGER_INT_TYPE     0xC8
#define MANAGER_TYPES_SCAN   0x800 /* the Bool entry is found by its vtable within manager+0..this */
#define MANAGER_BOOL64_TYPE  0xC58
#define BOOL64_SCAN_FROM     0xC08 /* where it is looked for if it isn't at MANAGER_BOOL64_TYPE */
#define BOOL64_SCAN_TO       0xD08
#define TYPE_ENTRY_ALIGN     8

/* Where a field's value is in its object, and the object's size */
#define BOOL_STRIDE        0x18
#define BOOL_VALUE_OFFSET  0x16
#define INT_STRIDE         0x28
#define INT_VALUE_OFFSET   0x1C

/* sanity limits for a type entry read from memory */
#define MAX_FIELD_COUNT     0x10000
#define MAX_HASH_TABLE_SIZE 0x100000
#define HASH_PAIR_BYTES     8

/* The first Gold Skulltula of the game's own list: the right Bool64bitKey entry has its flag, in the
 * sorted part of the records. */
#define BOOL64_PROBE_KEY 0xECDC46B409ED7D38ull
#define BOOL64_FLAG_SET  1

/* --- type entries ---------------------------------------------------------------------------- */

static bool type_plausible(const gd_type_t *type)
{
  if (!sys_mapped((uintptr_t)type, sizeof(*type), SYS_PERM_R))
    return false;
  if (type->count == 0 || type->count >= MAX_FIELD_COUNT || type->table_size == 0 ||
      type->table_size >= MAX_HASH_TABLE_SIZE)
    return false;
  return sys_mapped((uintptr_t)type->table, (size_t)type->table_size * HASH_PAIR_BYTES, SYS_PERM_R) &&
         sys_mapped((uintptr_t)type->objects, sizeof(uintptr_t), SYS_PERM_R);
}

static const gd_type_t *int_entry(const gamedata_t *data)
{
  const gd_type_t *type = (const gd_type_t *)(data->manager + MANAGER_INT_TYPE);
  bool is_int = type_plausible(type) &&
                sys_ptr((uintptr_t)type->objects) == data->game.main_base + data->game.build->vt_int_field;
  return is_int ? type : 0;
}

static bool is_bool_entry(const gamedata_t *data, uint32_t offset)
{
  const gd_type_t *type = (const gd_type_t *)(data->manager + offset);
  return sys_mapped((uintptr_t)type, sizeof(*type), SYS_PERM_R) &&
         type->vtable == data->game.main_base + data->game.build->vt_bool_type && type_plausible(type);
}

static const gd_type_t *bool_entry(gamedata_t *data)
{
  if (data->bool_entry_offset && is_bool_entry(data, data->bool_entry_offset))
    return (const gd_type_t *)(data->manager + data->bool_entry_offset);
  data->bool_entry_offset = 0;
  if (!sys_mapped((uintptr_t)data->manager, MANAGER_TYPES_SCAN + sizeof(gd_type_t), SYS_PERM_R))
    return 0;
  for (uint32_t offset = 0; offset < MANAGER_TYPES_SCAN; offset += TYPE_ENTRY_ALIGN) {
    if (is_bool_entry(data, offset)) {
      data->bool_entry_offset = offset;
      return (const gd_type_t *)(data->manager + offset);
    }
  }
  return 0;
}

/* The (hash, index) pair for `hash`, probing as the game does. */
static const uint32_t *find_pair(const gd_type_t *type, uint32_t hash)
{
  if (!hash)
    return 0;
  uint32_t start = hash % type->table_size, slot = start;
  do {
    const uint32_t *pair = type->table + 2 * (size_t)slot;
    if (pair[0] == hash)
      return pair;
    if (pair[0] == 0)
      return 0;
    slot = slot + 1 >= type->table_size ? 0 : slot + 1;
  } while (slot != start);
  return 0;
}

/* The bytes of field `hash`'s value, or NULL if the game has no such field or its object isn't mapped. */
static const uint8_t *field_value(const gd_type_t *type, uint32_t hash, uint32_t stride, uint32_t value_offset,
                                  uint32_t value_size)
{
  const uint32_t *pair = find_pair(type, hash);
  if (!pair || pair[1] >= type->count)
    return 0;
  uintptr_t at = (uintptr_t)type->objects + (uintptr_t)pair[1] * stride + value_offset;
  return sys_mapped(at, value_size, SYS_PERM_R) ? (const uint8_t *)at : 0;
}

/* --- Bool64bitKey ---------------------------------------------------------------------------- */

/* How many records from the start are in strictly rising key order. */
static uint32_t sorted_prefix(const gd_bool64_t *records, uint32_t count)
{
  uint32_t length = 1;
  while (length < count && records[length - 1].key < records[length].key)
    length++;
  return count ? length : 0;
}

/* The record for `key` among `count` records whose first `sorted` are in key order: a binary search of
 * those, then a scan of the ones appended after. */
static const gd_bool64_t *bool64_find(const gd_bool64_t *records, uint32_t count, uint32_t sorted, uint64_t key)
{
  uint32_t low = 0, high = sorted;
  while (low < high) {
    uint32_t mid = low + (high - low) / 2;
    uint64_t at = records[mid].key;
    if (at == key)
      return &records[mid];
    if (at < key)
      low = mid + 1;
    else
      high = mid;
  }
  for (uint32_t i = sorted; i < count; i++)
    if (records[i].key == key)
      return &records[i];
  return 0;
}

static bool bool64_plausible(gamedata_t *data, const gd_bool64_type_t *type)
{
  if (!sys_mapped((uintptr_t)type, sizeof(*type), SYS_PERM_R) || type->count == 0 ||
      type->count >= MAX_FIELD_COUNT || ((uintptr_t)type->records & (sizeof(uint64_t) - 1)) ||
      !sys_mapped((uintptr_t)type->records, (size_t)type->count * sizeof(gd_bool64_t), SYS_PERM_R))
    return false;
  if (data->sorted_for != type->records || data->sorted_for_count != type->count) {
    data->bool64_sorted = sorted_prefix(type->records, type->count);
    data->sorted_for = type->records;
    data->sorted_for_count = type->count;
  }
  /* the probe must be among the sorted records: a table of other flags has no such key there */
  return bool64_find(type->records, data->bool64_sorted, data->bool64_sorted, BOOL64_PROBE_KEY) != 0;
}

static const gd_bool64_type_t *bool64_entry(gamedata_t *data)
{
  if (data->bool64_entry_offset) {
    const gd_bool64_type_t *known = (const gd_bool64_type_t *)(data->manager + data->bool64_entry_offset);
    if (bool64_plausible(data, known))
      return known;
    data->bool64_entry_offset = 0;
  }
  const gd_bool64_type_t *at_default = (const gd_bool64_type_t *)(data->manager + MANAGER_BOOL64_TYPE);
  if (bool64_plausible(data, at_default)) {
    data->bool64_entry_offset = MANAGER_BOOL64_TYPE;
    return at_default;
  }
  for (uint32_t offset = BOOL64_SCAN_FROM; offset < BOOL64_SCAN_TO; offset += TYPE_ENTRY_ALIGN) {
    const gd_bool64_type_t *candidate = (const gd_bool64_type_t *)(data->manager + offset);
    if (bool64_plausible(data, candidate)) {
      data->bool64_entry_offset = offset;
      return candidate;
    }
  }
  return 0;
}

/* --- what the tracker asks ------------------------------------------------------------------- */

static gd_flag_t flag_of(bool known, bool set)
{
  return !known ? GD_UNKNOWN : set ? GD_TRUE : GD_FALSE;
}

static gd_flag_t read_bool(const flag_source_t *source, uint32_t hash)
{
  const gamedata_t *data = (const gamedata_t *)source;
  const uint8_t *value = data->bool_type ? field_value(data->bool_type, hash, BOOL_STRIDE, BOOL_VALUE_OFFSET, 1) : 0;
  return flag_of(value != 0, value && *value);
}

static bool read_int(const flag_source_t *source, uint32_t hash, int32_t *out)
{
  const gamedata_t *data = (const gamedata_t *)source;
  const uint8_t *value = data->int_type ? field_value(data->int_type, hash, INT_STRIDE, INT_VALUE_OFFSET, 4) : 0;
  if (value)
    *out = *(const int32_t *)value;
  return value != 0;
}

static gd_flag_t read_bool64(const flag_source_t *source, uint64_t key)
{
  const gamedata_t *data = (const gamedata_t *)source;
  const gd_bool64_type_t *table = data->bool64_type;
  const gd_bool64_t *record = table ? bool64_find(table->records, table->count, data->bool64_sorted, key) : 0;
  return flag_of(record != 0, record && record->value == BOOL64_FLAG_SET);
}

/* --- finding the tables ---------------------------------------------------------------------- */

void gamedata_init(gamedata_t *data, game_t game)
{
  *data = (gamedata_t){ .source = { read_bool, read_bool64, read_int }, .game = game };
}

static const uint8_t *find_manager(const gamedata_t *data)
{
  uintptr_t holder = sys_ptr(data->game.main_base + data->game.build->gd_mgr_ptr);
  return (const uint8_t *)(holder ? sys_ptr(holder) : 0);
}

bool gamedata_attach(gamedata_t *data)
{
  data->manager = find_manager(data);
  data->int_type = data->bool_type = 0;
  data->bool64_type = 0;
  if (!data->manager)
    return false;
  data->int_type = int_entry(data);
  data->bool_type = bool_entry(data);
  data->bool64_type = bool64_entry(data);
  return data->int_type && data->bool_type;
}

bool gamedata_has_bool64(const gamedata_t *data)
{
  return data->bool64_type != 0;
}
