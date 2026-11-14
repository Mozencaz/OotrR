/* The module's logic on the PC, for tests/test_module.py: the seed file's parser, the tracker's state, the game-data
 * reader over a fake GameData in memory, and the controls. `module_host --list` names the tests; `module_host NAME
 * [FIXTURE]` runs one (FIXTURE: a seed file for the tests that read one) and exits 0 if it passes. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/controls.h"
#include "../src/gamedata.h"
#include "../src/grid.h"
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

/* Two regions (2 and 1 checks), four items, two dungeons with keys; the strings come first. */
static blob_t synthetic(void)
{
  blob_t blob = { { 0 }, 0 };
  strings_t strings = { { 0 }, 1 };
  uint32_t seed_id = add_string(&strings, "abc123");
  uint32_t kokiri = add_string(&strings, "Kokiri Forest"), deku = add_string(&strings, "Deku Tree");
  uint32_t bow = add_string(&strings, "Bow"), boomerang = add_string(&strings, "Boomerang");
  uint32_t ghoul = add_string(&strings, "Soul (Ghoul)"), bat = add_string(&strings, "Soul (Bat)");
  uint32_t forest_temple = add_string(&strings, "Forest Temple"), well = add_string(&strings, "Bottom of the Well");
  uint32_t strings_padded = (strings.size + 3) & ~3u;
  uint32_t regions_at = HEADER_BYTES + strings_padded, checks_at = regions_at + 2 * 12, items_at = checks_at + 3 * 16;
  uint32_t rules_at = items_at + 4 * 8, keys_at = rules_at + 5 * 8, size = keys_at + 2 * 24;
  uint8_t *b = blob.bytes;
  memcpy(b, "RTRK", 4);
  put16(b + 4, 1);
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
    { "magic", 0, 0x58585858, 4 },       { "version", 4, 2, 2 },        { "header size", 6, 64, 2 },
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
  CHECK(controls_frame(0, false) == CONTROL_NONE);
  CHECK(controls_frame(BTN_R, false) == CONTROL_NONE);
  CHECK(controls_frame(BTN_R | BTN_RS_UP, false) == CONTROL_TOGGLE);
  CHECK(controls_frame(BTN_R | BTN_RS_UP, true) == CONTROL_NONE); /* held: no second toggle */
  CHECK(controls_frame(0, true) == CONTROL_NONE);
  CHECK(controls_frame(BTN_RS_UP, true) == CONTROL_NONE);
  CHECK(controls_frame(BTN_RS_UP | BTN_R, true) == CONTROL_TOGGLE); /* the other order */
  CHECK(controls_frame(BTN_R | BTN_RS_DOWN, false) == CONTROL_NONE); /* sloperinaGZ's menu */
  CHECK(controls_frame(BTN_R | BTN_DUP, false) == CONTROL_NONE);
  return 0;
}

static int test_b_closes_only_an_open_panel(void)
{
  controls_reset();
  CHECK(controls_frame(BTN_B, false) == CONTROL_NONE);
  CHECK(controls_frame(0, true) == CONTROL_NONE);
  CHECK(controls_frame(BTN_B, true) == CONTROL_CLOSE);
  CHECK(controls_frame(BTN_B, true) == CONTROL_NONE);
  return 0;
}

static int test_what_the_game_does_not_see(void)
{
  uint32_t combo = BTN_R | BTN_RS_UP | BTN_A;
  CHECK(controls_hidden(BTN_A | BTN_B | BTN_R, false) == 0);
  CHECK(!controls_centres_stick(BTN_RS_UP, false));
  CHECK(controls_centres_stick(combo, false));
  uint32_t hidden = controls_hidden(combo, false);
  CHECK((hidden & BTN_R) && (hidden & BTN_RS_UP) && (hidden & BTN_RS_LEFT) && (hidden & BTN_RS_DOWN));
  CHECK(!(hidden & BTN_B) && !(hidden & BTN_A) && !(hidden & BTN_RSTICK));
  hidden = controls_hidden(BTN_A, true);
  CHECK((hidden & BTN_B) && (hidden & BTN_R) && !(hidden & BTN_A));
  CHECK(controls_centres_stick(0, true));
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

/* --- driver ----------------------------------------------------------------------------------- */

typedef struct { const char *name; int (*run)(void); int (*run_with_file)(const char *); } test_t;

static const test_t tests[] = {
  { "parse_reads_every_table", test_parse_reads_every_table, 0 },
  { "parse_refuses_damage", test_parse_refuses_damage, 0 },
  { "parse_refuses_a_row_leaving_its_table", test_parse_refuses_a_row_leaving_its_table, 0 },
  { "parse_refuses_truncation_and_an_unterminated_string", test_parse_refuses_truncation_and_an_unterminated_string, 0 },
  { "the_real_seed_file", 0, test_the_real_seed_file },
  { "state_of_a_save", test_state_of_a_save, 0 },
  { "state_when_the_game_knows_nothing", test_state_when_the_game_knows_nothing, 0 },
  { "a_save_of_another_seed_and_the_goal", test_a_save_of_another_seed_and_the_goal, 0 },
  { "a_key_ring_counts_every_key", test_a_key_ring_counts_every_key, 0 },
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
  { "b_closes_only_an_open_panel", test_b_closes_only_an_open_panel, 0 },
  { "what_the_game_does_not_see", test_what_the_game_does_not_see, 0 },
  { "grid_names_and_labels", test_grid_names_and_labels, 0 },
  { "text_helpers", test_text_helpers, 0 },
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
