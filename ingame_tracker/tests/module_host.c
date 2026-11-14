/* The module's logic on the PC, for tests/test_module.py: the seed file's parser, the tracker's state, the game-data
 * reader over a fake GameData in memory, the controls, the browsing and the icons file's index. `module_host --list` names the tests; `module_host NAME
 * [FIXTURE]` runs one (FIXTURE: a seed file for the tests that read one) and exits 0 if it passes. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/browse.h"
#include "../src/controls.h"
#include "../src/gamedata.h"
#include "../src/grid.h"
#include "../src/iconfile.h"
#include "../src/npad.h"
#include "../src/text.h"
#include "../src/tracker.h"
#include "../src/trkfile.h"

static char failure[256];

#define CHECK(condition)                                                                       \
  do {                                                                                         \
    if (!(condition)) {                                                                        \
      snprintf(failure, sizeof(failure), "line %d: %s", __LINE__, #condition);                 \
      return 1;                                                                                \
    }                                                                                          \
  } while (0)

/* --- a seed file made in memory --------------------------------------------------------------- */

#define HEADER_BYTES 72
#define BLOB_MAX     4096

typedef struct { uint8_t bytes[BLOB_MAX]; size_t size; } blob_t;

static void put16(uint8_t *at, uint32_t value) { at[0] = (uint8_t)value; at[1] = (uint8_t)(value >> 8); }
static void put32(uint8_t *at, uint32_t value) { put16(at, value & 0xFFFF); put16(at + 2, value >> 16); }
static void put64(uint8_t *at, uint64_t value) { put32(at, (uint32_t)value); put32(at + 4, (uint32_t)(value >> 32)); }

typedef struct { uint8_t bytes[512]; uint32_t size; } strings_t;

static uint32_t add_string(strings_t *strings, const char *text)
{
  uint32_t at = strings->size;
  strcpy((char *)strings->bytes + at, text);
  strings->size += (uint32_t)strlen(text) + 1;
  return at;
}

enum { SEED_MARKER = 4000, GOAL_MARKER = 5000, BOOL_A = 100, BOOL_B = 200, BOW_L1 = 11, BOW_L2 = 12, BOOMERANG = 13,
       SOUL_GHOUL = 14, SOUL_BAT = 15, FOREST_FOUND = 21, FOREST_HELD = 22, FOREST_RING = 23, FOREST_BOSS = 24,
       WELL_FOUND = 31, WELL_HELD = 32 };
#define BOOL64_KEY 0x1111222233334444ull

static const char *const check_names[3] = { "Mido's House Chest", "Kokiri Sword Chest", "Deku Tree Map Chest" };

/* Two regions (2 and 1 checks), four items, two dungeons with keys; the strings come first. Version 1 has no
 * check names. */
static blob_t synthetic_of_version(int version)
{
  blob_t blob = { { 0 }, 0 };
  strings_t strings = { { 0 }, 1 };
  uint32_t seed_id = add_string(&strings, "abc123");
  uint32_t kokiri = add_string(&strings, "Kokiri Forest"), deku = add_string(&strings, "Deku Tree");
  uint32_t bow = add_string(&strings, "Bow"), boomerang = add_string(&strings, "Boomerang");
  uint32_t ghoul = add_string(&strings, "Soul (Ghoul)"), bat = add_string(&strings, "Soul (Bat)");
  uint32_t forest_temple = add_string(&strings, "Forest Temple"), well = add_string(&strings, "Bottom of the Well");
  uint32_t names[3] = { 0, 0, 0 };
  for (int i = 0; version >= 2 && i < 3; i++)
    names[i] = add_string(&strings, check_names[i]);
  uint32_t strings_padded = (strings.size + 3) & ~3u;
  uint32_t regions_at = HEADER_BYTES + strings_padded, checks_at = regions_at + 2 * 12, items_at = checks_at + 3 * 16;
  uint32_t rules_at = items_at + 4 * 8, keys_at = rules_at + 5 * 8, size = keys_at + 2 * 24;
  uint8_t *b = blob.bytes;
  memcpy(b, "RTRK", 4);
  put16(b + 4, (uint32_t)version);
  put16(b + 6, HEADER_BYTES);
  put32(b + 8, size);
  put32(b + 12, SEED_MARKER);
  put32(b + 16, GOAL_MARKER);
  put32(b + 20, seed_id);
  put32(b + 24, HEADER_BYTES);
  put32(b + 28, strings.size);
  put32(b + 32, regions_at); put32(b + 36, 2);
  put32(b + 40, checks_at); put32(b + 44, 3);
  put32(b + 48, items_at); put32(b + 52, 4);
  put32(b + 56, rules_at); put32(b + 60, 5);
  put32(b + 64, keys_at); put32(b + 68, 2);
  memcpy(b + HEADER_BYTES, strings.bytes, strings.size);
  uint32_t regions[2][3] = { { kokiri, 0, 2 }, { deku, 2, 1 } };
  for (int i = 0; i < 2; i++)
    for (int f = 0; f < 3; f++)
      put32(b + regions_at + i * 12 + f * 4, regions[i][f]);
  put64(b + checks_at, BOOL_A); put32(b + checks_at + 8, TRK_KIND_BOOL);
  put64(b + checks_at + 16, BOOL64_KEY); put32(b + checks_at + 24, TRK_KIND_BOOL64);
  put64(b + checks_at + 32, BOOL_B); put32(b + checks_at + 40, TRK_KIND_BOOL);
  for (int i = 0; i < 3; i++)
    put32(b + checks_at + i * 16 + 12, names[i]);
  uint32_t items[4][3] = { { bow, 0, 2 }, { boomerang, 2, 1 }, { ghoul, 3, 1 }, { bat, 4, 1 } };
  for (int i = 0; i < 4; i++) {
    put32(b + items_at + i * 8, items[i][0]);
    put16(b + items_at + i * 8 + 4, items[i][1]);
    put16(b + items_at + i * 8 + 6, items[i][2]);
  }
  uint32_t rules[5][2] = { { BOW_L1, 1 }, { BOW_L2, 2 }, { BOOMERANG, 1 }, { SOUL_GHOUL, 1 }, { SOUL_BAT, 1 } };
  for (int i = 0; i < 5; i++) {
    put32(b + rules_at + i * 8, rules[i][0]);
    put16(b + rules_at + i * 8 + 4, rules[i][1]);
  }
  put32(b + keys_at, forest_temple);
  b[keys_at + 4] = TRK_KEY_SMALL | TRK_KEY_BOSS;
  b[keys_at + 5] = 5;
  put32(b + keys_at + 8, FOREST_FOUND); put32(b + keys_at + 12, FOREST_HELD);
  put32(b + keys_at + 16, FOREST_RING); put32(b + keys_at + 20, FOREST_BOSS);
  put32(b + keys_at + 24, well);
  b[keys_at + 24 + 4] = TRK_KEY_SMALL | TRK_KEY_SMALL_ALL;
  b[keys_at + 24 + 5] = 3;
  put32(b + keys_at + 24 + 8, WELL_FOUND); put32(b + keys_at + 24 + 12, WELL_HELD);
  blob.size = size;
  return blob;
}

static blob_t synthetic(void)
{
  return synthetic_of_version(TRK_VERSION);
}

static bool parses(const blob_t *blob)
{
  trk_t trk;
  const char *why = "";
  return trk_parse(&trk, blob->bytes, blob->size, &why);
}

/* --- the seed file ---------------------------------------------------------------------------- */

static int test_parse_reads_every_table(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(trk.seed_marker == SEED_MARKER && trk.goal_marker == GOAL_MARKER);
  CHECK(!strcmp(trk_string(&trk, trk.seed_id), "abc123"));
  CHECK(trk.region_count == 2 && trk.check_count == 3 && trk.item_count == 4 && trk.key_count == 2);
  trk_region_t deku = trk_region(&trk, 1);
  CHECK(!strcmp(trk_string(&trk, deku.name), "Deku Tree") && deku.first_check == 2 && deku.check_count == 1);
  trk_check_t check = trk_check(&trk, 1);
  CHECK(check.key == BOOL64_KEY && check.kind == TRK_KIND_BOOL64);
  CHECK(trk.version == 2 && !strcmp(trk_string(&trk, check.name), "Kokiri Sword Chest"));
  trk_item_t bow = trk_item(&trk, 0);
  CHECK(bow.rule_count == 2 && trk_rule(&trk, 1).hash == BOW_L2 && trk_rule(&trk, 1).level == 2);
  trk_keys_t well = trk_keys(&trk, 1);
  CHECK(!strcmp(trk_string(&trk, well.name), "Bottom of the Well") && well.small_total == 3);
  CHECK(well.flags == (TRK_KEY_SMALL | TRK_KEY_SMALL_ALL) && well.found_hash == WELL_FOUND);
  CHECK(!strcmp(trk_string(&trk, 100000), ""));
  return 0;
}

static int test_parse_refuses_damage(void)
{
  struct { const char *what; size_t at; uint32_t value; int bytes; } damage[] = {
    { "magic", 0, 0x58585858, 4 },       { "version", 4, 3, 2 },        { "header size", 6, 64, 2 },
    { "version 0", 4, 0, 2 },
    { "file size", 8, 100, 4 },          { "strings outside", 24, 100000, 4 },
    { "strings size", 28, 100000, 4 },   { "regions outside", 32, 100000, 4 },
    { "region count", 36, 5000, 4 },     { "checks outside", 40, 100000, 4 },
    { "items count", 52, 100000, 4 },    { "rules outside", 56, 4000, 4 },
    { "keys count", 68, 17, 4 },         { "regions before the header", 32, 8, 4 },
  };
  for (unsigned i = 0; i < sizeof(damage) / sizeof(*damage); i++) {
    blob_t blob = synthetic();
    if (damage[i].bytes == 4)
      put32(blob.bytes + damage[i].at, damage[i].value);
    else
      put16(blob.bytes + damage[i].at, damage[i].value);
    if (parses(&blob)) {
      snprintf(failure, sizeof(failure), "a damaged %s was accepted", damage[i].what);
      return 1;
    }
  }
  return 0;
}

static int test_parse_refuses_a_row_leaving_its_table(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  put32(blob.bytes + trk.regions_at + 8, 9); /* the first region claims 9 checks of 3 */
  CHECK(!parses(&blob));
  blob = synthetic();
  put16(blob.bytes + trk.items_at + 6, 9); /* the first item claims 9 rules of 5 */
  CHECK(!parses(&blob));
  return 0;
}

static int test_parse_reads_version_1_without_names(void)
{
  blob_t blob = synthetic_of_version(1);
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(trk.version == 1 && trk.check_count == 3);
  for (uint32_t i = 0; i < trk.check_count; i++)
    CHECK(trk_check(&trk, i).name == 0 && !strcmp(trk_string(&trk, trk_check(&trk, i).name), ""));
  return 0;
}

static int test_parse_refuses_a_name_outside_the_strings(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  put32(blob.bytes + trk.checks_at + 2 * 16 + 12, trk.strings_size); /* one past the table */
  CHECK(!parses(&blob));
  return 0;
}

static int test_parse_refuses_truncation_and_an_unterminated_string(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  for (size_t cut = 0; cut < blob.size; cut += 7)
    CHECK(!trk_parse(&trk, blob.bytes, cut, &why));
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  blob.bytes[HEADER_BYTES + trk.strings_size - 1] = 'x';
  CHECK(!parses(&blob));
  return 0;
}

static int test_the_real_seed_file(const char *path)
{
  FILE *file = path ? fopen(path, "rb") : 0;
  CHECK(file);
  static uint8_t bytes[1 << 20];
  size_t size = fread(bytes, 1, sizeof(bytes), file);
  fclose(file);
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, bytes, size, &why));
  CHECK(trk.region_count == 35 && trk.check_count == 840 && trk.item_count == 44);
  CHECK(trk.seed_marker == 1220450581u && trk.goal_marker == 3488204275u);
  CHECK(!strcmp(trk_string(&trk, trk.seed_id), "76069ecc4740cec6"));
  CHECK(trk.version == 1 && trk_check(&trk, 839).name == 0); /* made by the 0.1.0 exporter: no names */
  return 0;
}

/* --- the tracker's state ---------------------------------------------------------------------- */

typedef struct {
  flag_source_t source;
  struct { uint32_t hash; gd_flag_t value; } bools[16];
  int bool_count;
  struct { uint64_t key; gd_flag_t value; } bool64s[4];
  int bool64_count;
  struct { uint32_t hash; int32_t value; } ints[8];
  int int_count;
  gd_flag_t everything_else;
} fake_flags_t;

static gd_flag_t fake_bool(const flag_source_t *source, uint32_t hash)
{
  const fake_flags_t *fake = (const fake_flags_t *)source;
  for (int i = 0; i < fake->bool_count; i++)
    if (fake->bools[i].hash == hash)
      return fake->bools[i].value;
  return fake->everything_else;
}

static gd_flag_t fake_bool64(const flag_source_t *source, uint64_t key)
{
  const fake_flags_t *fake = (const fake_flags_t *)source;
  for (int i = 0; i < fake->bool64_count; i++)
    if (fake->bool64s[i].key == key)
      return fake->bool64s[i].value;
  return fake->everything_else;
}

static bool fake_int(const flag_source_t *source, uint32_t hash, int32_t *out)
{
  const fake_flags_t *fake = (const fake_flags_t *)source;
  for (int i = 0; i < fake->int_count; i++) {
    if (fake->ints[i].hash == hash) {
      *out = fake->ints[i].value;
      return true;
    }
  }
  return false;
}

static fake_flags_t fake_with(gd_flag_t everything_else)
{
  fake_flags_t fake = { .source = { fake_bool, fake_bool64, fake_int }, .everything_else = everything_else };
  return fake;
}

static void set_bool(fake_flags_t *fake, uint32_t hash, gd_flag_t value)
{
  fake->bools[fake->bool_count].hash = hash;
  fake->bools[fake->bool_count++].value = value;
}

static int test_state_of_a_save(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  set_bool(&fake, SEED_MARKER, GD_TRUE);
  set_bool(&fake, GOAL_MARKER, GD_FALSE);
  set_bool(&fake, BOOL_A, GD_TRUE);
  set_bool(&fake, BOOL_B, GD_FALSE);
  set_bool(&fake, BOW_L1, GD_TRUE);
  set_bool(&fake, BOW_L2, GD_TRUE);
  set_bool(&fake, BOOMERANG, GD_FALSE);
  set_bool(&fake, SOUL_GHOUL, GD_TRUE);
  set_bool(&fake, FOREST_RING, GD_FALSE);
  set_bool(&fake, FOREST_BOSS, GD_TRUE);
  fake.bool64s[fake.bool64_count].key = BOOL64_KEY;
  fake.bool64s[fake.bool64_count++].value = GD_TRUE;
  fake.ints[fake.int_count].hash = FOREST_FOUND;
  fake.ints[fake.int_count++].value = 2;
  fake.ints[fake.int_count].hash = FOREST_HELD;
  fake.ints[fake.int_count++].value = 3;
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.link == SAVE_OF_THIS_SEED && !state.goal_reached);
  int bow = grid_index_of("Bow"), boomerang = grid_index_of("Boomerang"), hookshot = grid_index_of("Progressive Hookshot");
  CHECK(state.cells[bow].status == ITEM_OWNED && state.cells[bow].level == 2);
  CHECK(state.cells[boomerang].status == ITEM_MISSING && state.cells[boomerang].level == 0);
  CHECK(state.cells[hookshot].status == ITEM_UNKNOWN);
  CHECK(state.souls_total == 2 && state.souls_owned == 1);
  CHECK(state.region_count == 2 && !strcmp(state.regions[0].name, "Kokiri Forest"));
  CHECK(state.regions[0].collected == 2 && state.regions[0].trackable == 2);
  CHECK(state.regions[1].collected == 0 && state.regions[1].trackable == 1);
  CHECK(state.collected == 2 && state.trackable == 3 && state.unreadable == 0);
  CHECK(state.key_count == 2 && state.keys[0].has_small_keys && state.keys[0].small_keys_known);
  CHECK(state.keys[0].found == 3 && state.keys[0].total == 5 && state.keys[0].boss == BOSS_KEY_HELD);
  CHECK(state.keys[1].found == 3 && state.keys[1].total == 3 && state.keys[1].boss == BOSS_KEY_NONE);
  return 0;
}

static int test_state_when_the_game_knows_nothing(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.link == SAVE_LINK_UNKNOWN && !state.goal_reached);
  CHECK(state.collected == 0 && state.trackable == 3 && state.unreadable == 3);
  CHECK(state.cells[grid_index_of("Bow")].status == ITEM_UNKNOWN);
  CHECK(state.keys[0].has_small_keys && !state.keys[0].small_keys_known && state.keys[0].boss == BOSS_KEY_UNKNOWN);
  CHECK(state.keys[1].small_keys_known && state.keys[1].found == 3); /* every key counts: no reading needed */
  return 0;
}

static int test_a_save_of_another_seed_and_the_goal(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_FALSE);
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.link == SAVE_OF_ANOTHER && state.collected == 0 && state.unreadable == 0);
  CHECK(state.cells[grid_index_of("Bow")].status == ITEM_MISSING);
  set_bool(&fake, GOAL_MARKER, GD_TRUE);
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.goal_reached);
  return 0;
}

static int test_a_key_ring_counts_every_key(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  set_bool(&fake, FOREST_RING, GD_TRUE);
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.keys[0].small_keys_known && state.keys[0].found == 5 && state.keys[0].total == 5);
  return 0;
}

static int test_a_regions_checks_by_name_and_state(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  set_bool(&fake, BOOL_A, GD_TRUE);
  set_bool(&fake, BOOL_B, GD_FALSE);
  check_row_t rows[4];
  CHECK(tracker_check_rows(&trk, &fake.source, 0, 0, rows, 4) == 2);
  CHECK(!strcmp(rows[0].name, check_names[0]) && rows[0].number == 1 && rows[0].flag == GD_TRUE);
  CHECK(!strcmp(rows[1].name, check_names[1]) && rows[1].number == 2 && rows[1].flag == GD_UNKNOWN); /* bool64, not set */
  CHECK(tracker_check_rows(&trk, &fake.source, 1, 0, rows, 4) == 1);
  CHECK(!strcmp(rows[0].name, check_names[2]) && rows[0].flag == GD_FALSE);
  CHECK(tracker_check_rows(&trk, &fake.source, 0, 1, rows, 1) == 1 && rows[0].number == 2); /* from the second, room for one */
  CHECK(tracker_check_rows(&trk, &fake.source, 0, 5, rows, 4) == 0);
  CHECK(tracker_check_rows(&trk, &fake.source, 2, 0, rows, 4) == 0); /* no such region */
  blob = synthetic_of_version(1);
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(tracker_check_rows(&trk, &fake.source, 0, 0, rows, 4) == 2 && !strcmp(rows[1].name, "") && rows[1].number == 2);
  return 0;
}

static int test_the_real_seed_with_every_flag_set(const char *path)
{
  FILE *file = path ? fopen(path, "rb") : 0;
  CHECK(file);
  static uint8_t bytes[1 << 20];
  size_t size = fread(bytes, 1, sizeof(bytes), file);
  fclose(file);
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, bytes, size, &why));
  fake_flags_t fake = fake_with(GD_TRUE);
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.link == SAVE_OF_THIS_SEED && state.goal_reached);
  CHECK(state.region_count == 35 && state.trackable == 840 && state.collected == 840);
  CHECK(state.cells[grid_index_of("Progressive Hookshot")].level == 2);
  CHECK(state.cells[grid_index_of("Bow")].level == 3);
  fake = fake_with(GD_UNKNOWN);
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.collected == 0 && state.unreadable == 840);
  return 0;
}

/* --- the game's data, read in place ------------------------------------------------------------ */

#define FAKE_MAIN_SIZE      0x1000
#define TABLE_SIZE          16
#define BOOL_COUNT          6
#define INT_COUNT           3
#define MANAGER_SIZE        0x2000
#define BOOL_ENTRY_AT       0x80
#define BOOL64_COUNT        12
#define BOOL64_PROBE        0xECDC46B409ED7D38ull
#define INT_VTABLE_AT       0x200
#define BOOL_VTABLE_AT      0x300
#define MANAGER_POINTER_AT  0x100

typedef struct {
  uint8_t *main_block, *manager;
  uint8_t bool_objects[BOOL_COUNT][0x18];
  uint8_t int_objects[INT_COUNT][0x28];
  uint32_t bool_table[2 * TABLE_SIZE], int_table[2 * TABLE_SIZE];
  gd_bool64_t records[BOOL64_COUNT];
  uintptr_t manager_holder;
  game_build_t build;
  game_t game;
} fake_game_t;

static void table_insert(uint32_t *table, uint32_t hash, uint32_t index)
{
  uint32_t slot = hash % TABLE_SIZE;
  while (table[2 * slot])
    slot = (slot + 1) % TABLE_SIZE;
  table[2 * slot] = hash;
  table[2 * slot + 1] = index;
}

static void fill_type(gd_type_t *type, uintptr_t vtable, uint32_t count, void *objects, uint32_t *table)
{
  type->vtable = vtable;
  type->count = count;
  type->objects = objects;
  type->table = table;
  type->table_size = TABLE_SIZE;
}

/* Hashes 1 and 17 share a slot (the table has 16): the second is found by probing. */
static const uint32_t bool_hashes[BOOL_COUNT] = { 1, 17, 33, 700, 701, 702 };
static const uint32_t int_hashes[INT_COUNT] = { 5, 21, 900 };

static void fill_bool64(fake_game_t *fake, gd_bool64_type_t *entry)
{
  /* sorted records, with the probe key among them, then records a seed appended in no order, one of them
   * lower than the sorted ones' last key */
  uint64_t keys[BOOL64_COUNT] = { 10, 20, 30, 40, BOOL64_PROBE - 1, BOOL64_PROBE, BOOL64_PROBE + 5, 0xFFFF000000000000ull,
                                  0x5000, 0xFFFFFFFFFFFF0000ull, 15, 0x7777 };
  for (int i = 0; i < BOOL64_COUNT; i++)
    fake->records[i] = (gd_bool64_t){ .key = keys[i], .value = (uint8_t)(i % 2 == 0) };
  *entry = (gd_bool64_type_t){ BOOL64_COUNT, 0, fake->records };
}

static void build_fake_game(fake_game_t *fake)
{
  memset(fake, 0, sizeof(*fake));
  fake->main_block = calloc(1, FAKE_MAIN_SIZE);
  fake->manager = calloc(1, MANAGER_SIZE);
  fake->build = (game_build_t){ "test", 0, 0, MANAGER_POINTER_AT, INT_VTABLE_AT, BOOL_VTABLE_AT };
  fake->game = (game_t){ &fake->build, (uintptr_t)fake->main_block };
  uintptr_t int_vtable = fake->game.main_base + INT_VTABLE_AT, bool_vtable = fake->game.main_base + BOOL_VTABLE_AT;
  for (int i = 0; i < INT_COUNT; i++) {
    memcpy(fake->int_objects[i], &int_vtable, sizeof(int_vtable));
    *(int32_t *)(fake->int_objects[i] + 0x1C) = (int32_t)(100 + i);
    table_insert(fake->int_table, int_hashes[i], (uint32_t)i);
  }
  for (int i = 0; i < BOOL_COUNT; i++) {
    fake->bool_objects[i][0x16] = (uint8_t)(i % 2 == 0);
    table_insert(fake->bool_table, bool_hashes[i], (uint32_t)i);
  }
  fill_type((gd_type_t *)(fake->manager + 0xC8), int_vtable, INT_COUNT, fake->int_objects, fake->int_table);
  fill_type((gd_type_t *)(fake->manager + BOOL_ENTRY_AT), bool_vtable, BOOL_COUNT, fake->bool_objects, fake->bool_table);
  fill_bool64(fake, (gd_bool64_type_t *)(fake->manager + 0xC58));
  fake->manager_holder = (uintptr_t)fake->manager;
  uintptr_t holder_address = (uintptr_t)&fake->manager_holder;
  memcpy(fake->main_block + MANAGER_POINTER_AT, &holder_address, sizeof(holder_address));
}

static void free_fake_game(fake_game_t *fake)
{
  free(fake->main_block);
  free(fake->manager);
}

static int test_reads_bools_and_ints(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data));
  for (int i = 0; i < BOOL_COUNT; i++)
    CHECK(data.source.bool_flag(&data.source, bool_hashes[i]) == (i % 2 == 0 ? GD_TRUE : GD_FALSE));
  CHECK(data.source.bool_flag(&data.source, 12345) == GD_UNKNOWN);
  CHECK(data.source.bool_flag(&data.source, 0) == GD_UNKNOWN);
  int32_t value = 0;
  CHECK(data.source.int_value(&data.source, 21, &value) && value == 101);
  CHECK(data.source.int_value(&data.source, 900, &value) && value == 102);
  CHECK(!data.source.int_value(&data.source, 6, &value));
  free_fake_game(&fake);
  return 0;
}

static int test_bool64_head_and_appended_tail(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data) && gamedata_has_bool64(&data));
  for (int i = 0; i < BOOL64_COUNT; i++) {
    gd_flag_t expected = fake.records[i].value ? GD_TRUE : GD_FALSE;
    if (data.source.bool64_flag(&data.source, fake.records[i].key) != expected) {
      snprintf(failure, sizeof(failure), "record %d (key 0x%llx) read wrong", i, (unsigned long long)fake.records[i].key);
      return 1;
    }
  }
  CHECK(data.source.bool64_flag(&data.source, 11) == GD_UNKNOWN);
  CHECK(data.source.bool64_flag(&data.source, 0x6000) == GD_UNKNOWN);
  free_fake_game(&fake);
  return 0;
}

static int test_the_sorted_part_is_where_the_keys_stop_rising(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data));
  /* 10, 20, 30, 40, probe - 1, probe, probe + 5, 0xFFFF0000..., then 0x5000 breaks the order */
  CHECK(data.bool64_sorted == 8);
  free_fake_game(&fake);
  return 0;
}

static int test_a_table_of_other_flags_is_not_the_bool64_table(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  for (int i = 0; i < BOOL64_COUNT; i++)
    fake.records[i].key = (uint64_t)(i + 1) * 3; /* no probe key */
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data)); /* the Bool and Int flags still read */
  CHECK(!gamedata_has_bool64(&data));
  CHECK(data.source.bool64_flag(&data.source, 3) == GD_UNKNOWN);
  CHECK(data.source.bool_flag(&data.source, 1) == GD_TRUE);
  free_fake_game(&fake);
  return 0;
}

static int test_the_bool64_table_is_found_near_its_usual_place(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  memcpy(fake.manager + 0xC40, fake.manager + 0xC58, sizeof(gd_bool64_type_t));
  memset(fake.manager + 0xC58, 0, sizeof(gd_bool64_type_t));
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data) && gamedata_has_bool64(&data));
  CHECK(data.bool64_entry_offset == 0xC40);
  CHECK(data.source.bool64_flag(&data.source, BOOL64_PROBE) == GD_FALSE); /* record 5: a clear flag, but found */
  CHECK(data.source.bool64_flag(&data.source, BOOL64_PROBE - 1) == GD_TRUE);
  free_fake_game(&fake);
  return 0;
}

static int test_nothing_is_read_without_a_manager(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  fake.manager_holder = 0;
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(!gamedata_attach(&data));
  CHECK(data.source.bool_flag(&data.source, 1) == GD_UNKNOWN);
  CHECK(data.source.bool64_flag(&data.source, BOOL64_PROBE) == GD_UNKNOWN);
  int32_t value;
  CHECK(!data.source.int_value(&data.source, 5, &value));
  uintptr_t null_page = 0x10;
  memcpy(fake.main_block + MANAGER_POINTER_AT, &null_page, sizeof(null_page));
  CHECK(!gamedata_attach(&data));
  free_fake_game(&fake);
  return 0;
}

static int test_the_bool_entry_is_recognised_by_its_vtable(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  ((gd_type_t *)(fake.manager + BOOL_ENTRY_AT))->vtable += 8;
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(!gamedata_attach(&data));
  CHECK(data.source.bool_flag(&data.source, 1) == GD_UNKNOWN);
  free_fake_game(&fake);
  return 0;
}

static int test_moving_data_is_followed_by_the_next_attach(void)
{
  static fake_game_t fake;
  build_fake_game(&fake);
  gamedata_t data;
  gamedata_init(&data, fake.game);
  CHECK(gamedata_attach(&data));
  memmove(fake.manager + 0x400, fake.manager + BOOL_ENTRY_AT, sizeof(gd_type_t));
  memset(fake.manager + BOOL_ENTRY_AT, 0, sizeof(gd_type_t));
  CHECK(gamedata_attach(&data));
  CHECK(data.bool_entry_offset == 0x400);
  CHECK(data.source.bool_flag(&data.source, 1) == GD_TRUE);
  free_fake_game(&fake);
  return 0;
}

/* --- the controls ----------------------------------------------------------------------------- */

static int test_the_combo_toggles_on_its_press_only(void)
{
  controls_reset();
  CHECK(controls_frame(0, false, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_R, false, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_R | BTN_RS_UP, false, 0) == CONTROL_TOGGLE);
  CHECK(controls_frame(BTN_R | BTN_RS_UP, true, 0) == CONTROL_NONE); /* held: no second toggle */
  CHECK(controls_frame(0, true, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_RS_UP, true, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_RS_UP | BTN_R, true, 0) == CONTROL_TOGGLE); /* the other order */
  CHECK(controls_frame(BTN_R | BTN_RS_DOWN, false, 0) == CONTROL_NONE); /* sloperinaGZ's menu */
  CHECK(controls_frame(BTN_R | BTN_DUP, false, 0) == CONTROL_NONE);
  return 0;
}

static int test_a_and_b_and_directions_only_with_the_panel_open(void)
{
  controls_reset();
  CHECK(controls_frame(BTN_B, false, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_A, false, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DDOWN, false, 0) == CONTROL_NONE);
  CHECK(controls_frame(0, true, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_B, true, 0) == CONTROL_BACK);
  CHECK(controls_frame(BTN_B, true, 0) == CONTROL_NONE); /* on the press only */
  CHECK(controls_frame(BTN_A, true, 0) == CONTROL_SELECT);
  CHECK(controls_frame(BTN_A | BTN_B, true, 0) == CONTROL_BACK); /* B pressed while A is held */
  CHECK(controls_frame(0, true, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DLEFT, true, 0) == CONTROL_LEFT);
  CHECK(controls_frame(BTN_LS_RIGHT, true, 10) == CONTROL_RIGHT); /* the left stick as a D-pad */
  CHECK(controls_frame(BTN_LS_UP, true, 20) == CONTROL_UP);
  CHECK(controls_frame(BTN_DDOWN, true, 30) == CONTROL_DOWN);
  return 0;
}

static int test_a_held_direction_repeats(void)
{
  controls_reset();
  CHECK(controls_frame(BTN_DDOWN, true, 1000) == CONTROL_DOWN);
  CHECK(controls_frame(BTN_DDOWN, true, 1033) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DDOWN, true, 1349) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DDOWN, true, 1350) == CONTROL_DOWN); /* after the delay, */
  CHECK(controls_frame(BTN_DDOWN, true, 1400) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DDOWN, true, 1440) == CONTROL_DOWN); /* then more often */
  CHECK(controls_frame(BTN_DUP, true, 1450) == CONTROL_UP);     /* another direction: at once */
  CHECK(controls_frame(0, true, 1460) == CONTROL_NONE);
  CHECK(controls_frame(BTN_DUP, true, 1470) == CONTROL_UP);     /* let go and pressed again */
  CHECK(controls_frame(BTN_DUP, false, 2000) == CONTROL_NONE);  /* closed: nothing */
  CHECK(controls_frame(BTN_DUP, true, 2010) == CONTROL_UP);     /* open again: a fresh press */
  return 0;
}

static int test_what_the_game_does_not_see(void)
{
  controls_reset();
  uint32_t combo = BTN_R | BTN_RS_UP | BTN_A;
  CHECK(controls_hidden(BTN_A | BTN_B | BTN_R | BTN_DUP, false) == 0);
  CHECK(!controls_centres_right_stick(BTN_RS_UP, false) && !controls_centres_left_stick(false));
  CHECK(controls_centres_right_stick(combo, false));
  uint32_t hidden = controls_hidden(combo, false);
  CHECK((hidden & BTN_R) && (hidden & BTN_RS_UP) && (hidden & BTN_RS_LEFT) && (hidden & BTN_RS_DOWN));
  CHECK(!(hidden & BTN_B) && !(hidden & BTN_A) && !(hidden & BTN_RSTICK));
  hidden = controls_hidden(0, true);
  CHECK((hidden & BTN_B) && (hidden & BTN_R) && (hidden & BTN_A) && (hidden & BTN_DPAD) == BTN_DPAD);
  CHECK((hidden & BTN_LS_LEFT) && (hidden & BTN_LS_DOWN) && !(hidden & BTN_X) && !(hidden & BTN_ZL));
  CHECK(controls_centres_right_stick(0, true) && controls_centres_left_stick(true));
  return 0;
}

static int test_buttons_held_at_closing_stay_hidden_until_let_go(void)
{
  controls_reset();
  CHECK(controls_frame(0, true, 0) == CONTROL_NONE);
  CHECK(controls_frame(BTN_B | BTN_LS_LEFT | BTN_X, true, 10) == CONTROL_BACK);
  controls_hold_back_held(); /* B closed the panel */
  uint32_t hidden = controls_hidden(BTN_B | BTN_LS_LEFT | BTN_X, false);
  CHECK((hidden & BTN_B) && (hidden & BTN_LS_LEFT) && !(hidden & BTN_X)); /* X never was the panel's */
  CHECK(controls_centres_left_stick(false));
  CHECK(controls_frame(BTN_B, false, 20) == CONTROL_NONE); /* the stick let go, B still held */
  CHECK((controls_hidden(BTN_B, false) & BTN_B) && !controls_centres_left_stick(false));
  CHECK(controls_frame(0, false, 30) == CONTROL_NONE);
  CHECK(controls_hidden(BTN_B, false) == 0); /* a new press of B is the game's */
  return 0;
}

/* --- browsing --------------------------------------------------------------------------------- */

static int test_the_highlight_moves_over_the_regions_columns(void)
{
  /* 35 regions in 3 columns of 12: 0-11, 12-23, 24-34 */
  browse_t b = { BROWSE_REGIONS, 0, 0, 0 };
  CHECK(browse_region_rows(35) == 12 && browse_region_rows(36) == 12 && browse_region_rows(1) == 1);
  browse_move(&b, NAV_UP, 35, 0);
  CHECK(b.region == 0); /* the first stays */
  browse_move(&b, NAV_LEFT, 35, 0);
  CHECK(b.region == 0);
  browse_move(&b, NAV_DOWN, 35, 0);
  CHECK(b.region == 1);
  browse_move(&b, NAV_RIGHT, 35, 0);
  CHECK(b.region == 13);
  browse_move(&b, NAV_RIGHT, 35, 0);
  CHECK(b.region == 25);
  browse_move(&b, NAV_RIGHT, 35, 0);
  CHECK(b.region == 25); /* no fourth column */
  browse_move(&b, NAV_LEFT, 35, 0);
  CHECK(b.region == 13);
  b.region = 11;
  browse_move(&b, NAV_DOWN, 35, 0);
  CHECK(b.region == 12); /* down from a column's foot: the next column's head */
  b.region = 23;
  browse_move(&b, NAV_RIGHT, 35, 0);
  CHECK(b.region == 34); /* the shorter last column: its last region */
  browse_move(&b, NAV_DOWN, 35, 0);
  CHECK(b.region == 34);
  browse_move(&b, NAV_DOWN, 0, 0); /* no regions: nothing moves */
  CHECK(b.region == 34);
  browse_show_regions(&b, 20); /* fewer regions than the highlight: kept inside */
  CHECK(b.view == BROWSE_REGIONS && b.region == 19);
  return 0;
}

static int test_a_list_opens_scrolls_and_goes_back(void)
{
  browse_t b = { BROWSE_REGIONS, 4, 7, 3 };
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_REGIONS); /* the highlight is past the regions */
  b.region = 2;
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_CHECKS && b.region == 2 && b.check == 0 && b.top == 0);
  uint32_t count = 40;
  browse_move(&b, NAV_UP, 3, count);
  CHECK(b.check == 0 && b.top == 0);
  for (int i = 0; i < BROWSE_CHECK_ROWS - 1; i++)
    browse_move(&b, NAV_DOWN, 3, count);
  CHECK(b.check == BROWSE_CHECK_ROWS - 1 && b.top == 0); /* the last row shown */
  browse_move(&b, NAV_DOWN, 3, count);
  CHECK(b.check == BROWSE_CHECK_ROWS && b.top == 1); /* scrolled by one */
  browse_move(&b, NAV_RIGHT, 3, count);
  CHECK(b.check == 2 * BROWSE_CHECK_ROWS && b.top == BROWSE_CHECK_ROWS + 1);
  browse_move(&b, NAV_RIGHT, 3, count);
  CHECK(b.check == count - 1 && b.top == count - BROWSE_CHECK_ROWS); /* a page past the end: the last */
  browse_move(&b, NAV_DOWN, 3, count);
  CHECK(b.check == count - 1);
  browse_move(&b, NAV_LEFT, 3, count);
  CHECK(b.check == count - 1 - BROWSE_CHECK_ROWS && b.top == b.check);
  browse_move(&b, NAV_LEFT, 3, count);
  browse_move(&b, NAV_LEFT, 3, count);
  CHECK(b.check == 0 && b.top == 0);
  CHECK(browse_back(&b) && b.view == BROWSE_REGIONS && b.region == 2);
  CHECK(!browse_back(&b)); /* B at the regions: the panel closes */
  browse_open(&b, 3);
  browse_move(&b, NAV_DOWN, 3, 0); /* an empty list */
  CHECK(b.check == 0 && b.top == 0);
  return 0;
}

/* --- grid and text ---------------------------------------------------------------------------- */

static int test_grid_names_and_labels(void)
{
  CHECK(grid_index_of("Bow") >= 0 && grid_index_of("Light Medallion") == GRID_CELLS - 1);
  CHECK(grid_index_of("Soul (Bat)") == -1);
  for (int i = 0; i < GRID_CELLS; i++) {
    for (int j = i + 1; j < GRID_CELLS; j++)
      CHECK(strcmp(grid_cell(i)->item, grid_cell(j)->item) != 0);
    CHECK(strlen(grid_cell(i)->abbr) < ABBR_MAX && grid_cell(i)->levels >= 1);
  }
  char abbr[ABBR_MAX];
  grid_dungeon_abbr("Gerudo Training Ground", abbr);
  CHECK(!strcmp(abbr, "GTG"));
  grid_dungeon_abbr("Deku Tree", abbr);
  CHECK(!strcmp(abbr, "De"));
  grid_dungeon_abbr("", abbr);
  CHECK(!strcmp(abbr, ""));
  return 0;
}

static int test_text_helpers(void)
{
  char out[5];
  CHECK(text_equal("a", "a") && !text_equal("a", "ab") && !text_equal("ab", "a"));
  CHECK(text_starts_with("Soul (Bat)", "Soul (") && !text_starts_with("Sou", "Soul ("));
  CHECK(text_copy(out, sizeof(out), "abcdefgh") == 4 && !strcmp(out, "abcd"));
  CHECK(text_copy(out, sizeof(out), "ab") == 2 && !strcmp(out, "ab"));
  CHECK(text_copy(out, 0, "ab") == 0);
  return 0;
}

/* --- the icons file's index ------------------------------------------------------------------- */

#define ICONS_BYTES 4288 /* a 64 x 64 bow (4096 bytes) and an 8 x 4 hookshot (32), after the header and 2 entries */

static uint8_t icons[ICONS_BYTES];

static void put_icon(int i, const char *name, uint32_t width, uint32_t height, uint32_t offset, uint32_t size)
{
  uint8_t *e = icons + ICONFILE_HEADER + i * ICONFILE_ENTRY;
  memset(e, 0, ICONFILE_ENTRY);
  memcpy(e, name, strlen(name));
  put32(e + 32, width);
  put32(e + 36, height);
  put32(e + 40, offset);
  put32(e + 44, size);
  for (int b = 0; b < 8; b++)
    e[48 + b] = (uint8_t)(b == 0 ? 4 : 0);
  e[56] = 2, e[57] = 3, e[58] = 4, e[59] = 5;
  put32(e + 60, i ? 0x2D06 : 0x2D01);
}

static void synthetic_icons(void)
{
  memset(icons, 0, sizeof(icons));
  memcpy(icons, "RTIC", 4);
  put16(icons + 4, ICONFILE_VERSION);
  put16(icons + 6, ICONFILE_HEADER);
  put32(icons + 8, ICONS_BYTES);
  put32(icons + 12, 2);
  put32(icons + 16, ICONFILE_HEADER);
  put32(icons + 20, ICONFILE_ENTRY);
  put32(icons + 24, ICONFILE_HEADER + 2 * ICONFILE_ENTRY);
  put_icon(0, "Bow", 64, 64, 160, 4096);
  put_icon(1, "Hookshot", 8, 4, 4256, 32);
}

static bool icons_parse(icon_index_t *index, size_t size)
{
  const char *why = "";
  return iconfile_parse(index, icons, size, ICONS_BYTES, &why);
}

static int test_icons_index_reads_every_entry(void)
{
  icon_index_t index;
  synthetic_icons();
  CHECK(icons_parse(&index, sizeof(icons)));
  CHECK(index.count == 2 && index.largest == 4096);
  const icon_entry_t *bow = &index.entries[0], *hookshot = &index.entries[1];
  CHECK(!strcmp(bow->name, "Bow") && bow->width == 64 && bow->height == 64 && bow->offset == 160 && bow->size == 4096);
  CHECK(bow->format == 0x2D01 && bow->layout[0] == 4 && bow->swizzle[0] == 2 && bow->swizzle[3] == 5);
  CHECK(!strcmp(hookshot->name, "Hookshot") && hookshot->format == 0x2D06 && hookshot->offset == 4256);
  CHECK(icons_parse(&index, ICONFILE_HEADER + 2 * ICONFILE_ENTRY)); /* the head is enough */
  return 0;
}

static int test_icons_index_refuses_damage(void)
{
  struct { const char *what; size_t at; uint32_t value; int bytes; } damage[] = {
    { "magic", 0, 0x58585858, 4 },        { "version", 4, 2, 2 },               { "header size", 6, 64, 2 },
    { "file size", 8, 100, 4 },           { "count 0", 12, 0, 4 },              { "count 31", 12, 31, 4 },
    { "index place", 16, 64, 4 },         { "entry size", 20, 48, 4 },          { "data place", 24, 176, 4 },
    { "reserved", 28, 1, 4 },             { "an empty name", 32, 0, 1 },        { "width 0", 64, 0, 4 },
    { "width 5000", 64, 5000, 4 },        { "height 0", 68, 0, 4 },             { "a misaligned offset", 72, 168, 4 },
    { "an offset in the index", 72, 144, 4 }, { "a size under its blocks", 76, 4080, 4 },
    { "a size over 4 MiB", 76, (4u << 20) + 16, 4 }, { "a swizzle", 88, 6, 1 }, { "the format", 92, 0x2D02, 4 },
    { "a picture past the end", 136, 4272, 4 },
  };
  icon_index_t index;
  for (unsigned i = 0; i < sizeof(damage) / sizeof(*damage); i++) {
    synthetic_icons();
    if (damage[i].bytes == 4)
      put32(icons + damage[i].at, damage[i].value);
    else if (damage[i].bytes == 2)
      put16(icons + damage[i].at, damage[i].value);
    else
      icons[damage[i].at] = (uint8_t)damage[i].value;
    if (icons_parse(&index, sizeof(icons))) {
      snprintf(failure, sizeof(failure), "a damaged %s was accepted", damage[i].what);
      return 1;
    }
  }
  synthetic_icons();
  memset(icons + ICONFILE_HEADER, 'A', ICONFILE_NAME); /* a name without its NUL */
  CHECK(!icons_parse(&index, sizeof(icons)));
  synthetic_icons();
  put_icon(1, "Bow", 8, 4, 4256, 32); /* two icons of one item */
  CHECK(!icons_parse(&index, sizeof(icons)));
  synthetic_icons();
  CHECK(!icons_parse(&index, ICONFILE_HEADER + ICONFILE_ENTRY) && !icons_parse(&index, ICONFILE_HEADER - 1));
  const char *why = "";
  CHECK(!iconfile_parse(&index, icons, sizeof(icons), ICONS_BYTES + 16, &why) && why[0]);
  return 0;
}

/* --- driver ----------------------------------------------------------------------------------- */

typedef struct { const char *name; int (*run)(void); int (*run_with_file)(const char *); } test_t;

static const test_t tests[] = {
  { "parse_reads_every_table", test_parse_reads_every_table, 0 },
  { "parse_refuses_damage", test_parse_refuses_damage, 0 },
  { "parse_refuses_a_row_leaving_its_table", test_parse_refuses_a_row_leaving_its_table, 0 },
  { "parse_refuses_truncation_and_an_unterminated_string", test_parse_refuses_truncation_and_an_unterminated_string, 0 },
  { "parse_reads_version_1_without_names", test_parse_reads_version_1_without_names, 0 },
  { "parse_refuses_a_name_outside_the_strings", test_parse_refuses_a_name_outside_the_strings, 0 },
  { "the_real_seed_file", 0, test_the_real_seed_file },
  { "state_of_a_save", test_state_of_a_save, 0 },
  { "state_when_the_game_knows_nothing", test_state_when_the_game_knows_nothing, 0 },
  { "a_save_of_another_seed_and_the_goal", test_a_save_of_another_seed_and_the_goal, 0 },
  { "a_key_ring_counts_every_key", test_a_key_ring_counts_every_key, 0 },
  { "a_regions_checks_by_name_and_state", test_a_regions_checks_by_name_and_state, 0 },
  { "the_real_seed_with_every_flag_set", 0, test_the_real_seed_with_every_flag_set },
  { "reads_bools_and_ints", test_reads_bools_and_ints, 0 },
  { "bool64_head_and_appended_tail", test_bool64_head_and_appended_tail, 0 },
  { "the_sorted_part_is_where_the_keys_stop_rising", test_the_sorted_part_is_where_the_keys_stop_rising, 0 },
  { "a_table_of_other_flags_is_not_the_bool64_table", test_a_table_of_other_flags_is_not_the_bool64_table, 0 },
  { "the_bool64_table_is_found_near_its_usual_place", test_the_bool64_table_is_found_near_its_usual_place, 0 },
  { "nothing_is_read_without_a_manager", test_nothing_is_read_without_a_manager, 0 },
  { "the_bool_entry_is_recognised_by_its_vtable", test_the_bool_entry_is_recognised_by_its_vtable, 0 },
  { "moving_data_is_followed_by_the_next_attach", test_moving_data_is_followed_by_the_next_attach, 0 },
  { "the_combo_toggles_on_its_press_only", test_the_combo_toggles_on_its_press_only, 0 },
  { "a_and_b_and_directions_only_with_the_panel_open", test_a_and_b_and_directions_only_with_the_panel_open, 0 },
  { "a_held_direction_repeats", test_a_held_direction_repeats, 0 },
  { "what_the_game_does_not_see", test_what_the_game_does_not_see, 0 },
  { "buttons_held_at_closing_stay_hidden_until_let_go", test_buttons_held_at_closing_stay_hidden_until_let_go, 0 },
  { "the_highlight_moves_over_the_regions_columns", test_the_highlight_moves_over_the_regions_columns, 0 },
  { "a_list_opens_scrolls_and_goes_back", test_a_list_opens_scrolls_and_goes_back, 0 },
  { "grid_names_and_labels", test_grid_names_and_labels, 0 },
  { "text_helpers", test_text_helpers, 0 },
  { "icons_index_reads_every_entry", test_icons_index_reads_every_entry, 0 },
  { "icons_index_refuses_damage", test_icons_index_refuses_damage, 0 },
};

int main(int argc, char **argv)
{
  size_t count = sizeof(tests) / sizeof(*tests);
  if (argc > 1 && !strcmp(argv[1], "--list")) {
    for (size_t i = 0; i < count; i++)
      printf("%s%s\n", tests[i].name, tests[i].run_with_file ? " file" : "");
    return 0;
  }
  for (size_t i = 0; argc > 1 && i < count; i++) {
    if (strcmp(argv[1], tests[i].name))
      continue;
    int failed = tests[i].run ? tests[i].run() : tests[i].run_with_file(argc > 2 ? argv[2] : 0);
    if (failed)
      fprintf(stderr, "%s\n", failure);
    return failed;
  }
  fprintf(stderr, "no such test\n");
  return 2;
}
