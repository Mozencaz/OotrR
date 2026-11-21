/* The module's logic on the PC, for tests/test_module.py: the seed file's parser, the tracker's state, the game-data
 * reader over a fake GameData in memory, the controls, the browsing, the icons file's index and the check shown in
 * the world (its places, its words, the camera's projection). `module_host --list` names the tests; `module_host NAME
 * [FIXTURE]` runs one (FIXTURE: a seed file for the tests that read one) and exits 0 if it passes. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/browse.h"
#include "../src/console.h"
#include "../src/consolelog.h"
#include "../src/controls.h"
#include "../src/gamedata.h"
#include "../src/grid.h"
#include "../src/iconfile.h"
#include "../src/locate.h"
#include "../src/mailbox.h"
#include "../src/marks.h"
#include "../src/npad.h"
#include "../src/postcard.h"
#include "../src/sizes.h"
#include "../src/text.h"
#include "../src/tracker.h"
#include "../src/trkfile.h"
#include "../src/view.h"

static char failure[256];

#define CHECK(condition)                                                                       \
  do {                                                                                         \
    if (!(condition)) {                                                                        \
      snprintf(failure, sizeof(failure), "line %d: %s", __LINE__, #condition);                 \
      return 1;                                                                                \
    }                                                                                          \
  } while (0)

/* --- a seed file made in memory --------------------------------------------------------------- */

#define HEADER_BYTES 72 /* versions 1 and 2; version 3 has its flags after them */
#define HEADER_V3    76
#define HEADER_V4    92 /* the ids' and places' tables after the flags */
#define BLOB_MAX     4096

typedef struct { uint8_t bytes[BLOB_MAX]; size_t size; } blob_t;

static void put16(uint8_t *at, uint32_t value) { at[0] = (uint8_t)value; at[1] = (uint8_t)(value >> 8); }
static void put32(uint8_t *at, uint32_t value) { put16(at, value & 0xFFFF); put16(at + 2, value >> 16); }
static void put64(uint8_t *at, uint64_t value) { put32(at, (uint32_t)value); put32(at + 4, (uint32_t)(value >> 32)); }
static void put_float(uint8_t *at, float value)
{
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  put32(at, bits);
}

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
       WELL_FOUND = 31, WELL_HELD = 32, LULLABY = 41, SONG_OF_TIME = 42, PRELUDE = 43, BOTTLE_A = 51 };
#define BOTTLE_SLOTS    5 /* the Bottle item's rules: one flag a slot, A to E, at BOTTLE_A + slot */
#define SYNTHETIC_ITEMS 8
#define SYNTHETIC_RULES (8 + BOTTLE_SLOTS)
#define BOOL64_KEY 0x1111222233334444ull

static const char *const check_names[3] = { "Mido's House Chest", "Kokiri Sword Chest", "Deku Tree Map Chest" };
static const char *const check_idents[3] = { "KokiriForest#111", "KokiriForest#222", "npc#Deku Tree Map Chest" };
/* version 4: Mido's chest in the child's Kokiri Forest, the sword's chest in both, the map's chest nowhere */
#define PLACES 3
static const struct { uint32_t check; int map; float x, y, z; } synthetic_places[PLACES] = {
  { 0, 0, 10.5f, 0.25f, -2.75f }, { 1, 0, -20, 1.5f, 30.125f }, { 1, 1, -20, 1.5f, 30 },
};
static const char *const place_maps[2] = { "KokiriForest_Child", "KokiriForest_Adult" };
static const char *const place_labels[2] = { "Kokiri Forest (child)", "Kokiri Forest (adult)" };

/* Two regions (2 and 1 checks), eight items (three songs, then the bottles), two dungeons with keys; the strings come
 * first, the checks' ids and places last. Version 1 has no check names, versions 1 and 2 no flags, versions 1 to 3
 * no ids or places. */
static blob_t synthetic_with(int version, uint32_t flags)
{
  uint32_t header = version >= 4 ? HEADER_V4 : version == 3 ? HEADER_V3 : HEADER_BYTES;
  blob_t blob = { { 0 }, 0 };
  strings_t strings = { { 0 }, 1 };
  uint32_t seed_id = add_string(&strings, "abc123");
  uint32_t kokiri = add_string(&strings, "Kokiri Forest"), deku = add_string(&strings, "Deku Tree");
  uint32_t bow = add_string(&strings, "Bow"), boomerang = add_string(&strings, "Boomerang");
  uint32_t ghoul = add_string(&strings, "Soul (Ghoul)"), bat = add_string(&strings, "Soul (Bat)");
  uint32_t lullaby = add_string(&strings, "Zeldas Lullaby"), time_song = add_string(&strings, "Song of Time");
  uint32_t prelude = add_string(&strings, "Prelude of Light"), bottle = add_string(&strings, "Bottle");
  uint32_t forest_temple = add_string(&strings, "Forest Temple"), well = add_string(&strings, "Bottom of the Well");
  uint32_t names[3] = { 0, 0, 0 };
  for (int i = 0; version >= 2 && i < 3; i++)
    names[i] = add_string(&strings, check_names[i]);
  uint32_t idents[3] = { 0, 0, 0 }, maps[2] = { 0, 0 }, labels[2] = { 0, 0 };
  for (int i = 0; version >= 4 && i < 3; i++)
    idents[i] = add_string(&strings, check_idents[i]);
  for (int i = 0; version >= 4 && i < 2; i++) {
    maps[i] = add_string(&strings, place_maps[i]);
    labels[i] = add_string(&strings, place_labels[i]);
  }
  uint32_t strings_padded = (strings.size + 3) & ~3u;
  uint32_t regions_at = header + strings_padded, checks_at = regions_at + 2 * 12, items_at = checks_at + 3 * 16;
  uint32_t rules_at = items_at + SYNTHETIC_ITEMS * 8, keys_at = rules_at + SYNTHETIC_RULES * 8, idents_at = keys_at + 2 * 24;
  uint32_t places_at = idents_at + (version >= 4 ? 3 * 4 : 0), size = places_at + (version >= 4 ? PLACES * 24 : 0);
  uint8_t *b = blob.bytes;
  memcpy(b, "RTRK", 4);
  put16(b + 4, (uint32_t)version);
  put16(b + 6, header);
  put32(b + 8, size);
  put32(b + 12, SEED_MARKER);
  put32(b + 16, GOAL_MARKER);
  put32(b + 20, seed_id);
  put32(b + 24, header);
  put32(b + 28, strings.size);
  put32(b + 32, regions_at); put32(b + 36, 2);
  put32(b + 40, checks_at); put32(b + 44, 3);
  put32(b + 48, items_at); put32(b + 52, SYNTHETIC_ITEMS);
  put32(b + 56, rules_at); put32(b + 60, SYNTHETIC_RULES);
  put32(b + 64, keys_at); put32(b + 68, 2);
  if (version >= 3)
    put32(b + HEADER_BYTES, flags);
  if (version >= 4) {
    put32(b + 76, idents_at); put32(b + 80, 3);
    put32(b + 84, places_at); put32(b + 88, PLACES);
    for (int i = 0; i < 3; i++)
      put32(b + idents_at + i * 4, idents[i]);
    for (int i = 0; i < PLACES; i++) {
      uint8_t *row = b + places_at + i * 24;
      put32(row, synthetic_places[i].check);
      put32(row + 4, maps[synthetic_places[i].map]);
      put32(row + 8, labels[synthetic_places[i].map]);
      put_float(row + 12, synthetic_places[i].x);
      put_float(row + 16, synthetic_places[i].y);
      put_float(row + 20, synthetic_places[i].z);
    }
  }
  memcpy(b + header, strings.bytes, strings.size);
  uint32_t regions[2][3] = { { kokiri, 0, 2 }, { deku, 2, 1 } };
  for (int i = 0; i < 2; i++)
    for (int f = 0; f < 3; f++)
      put32(b + regions_at + i * 12 + f * 4, regions[i][f]);
  put64(b + checks_at, BOOL_A); put32(b + checks_at + 8, TRK_KIND_BOOL);
  put64(b + checks_at + 16, BOOL64_KEY); put32(b + checks_at + 24, TRK_KIND_BOOL64);
  put64(b + checks_at + 32, BOOL_B); put32(b + checks_at + 40, TRK_KIND_BOOL);
  for (int i = 0; i < 3; i++)
    put32(b + checks_at + i * 16 + 12, names[i]);
  uint32_t items[SYNTHETIC_ITEMS][3] = { { bow, 0, 2 }, { boomerang, 2, 1 }, { ghoul, 3, 1 }, { bat, 4, 1 },
                                         { lullaby, 5, 1 }, { time_song, 6, 1 }, { prelude, 7, 1 },
                                         { bottle, 8, BOTTLE_SLOTS } };
  for (int i = 0; i < SYNTHETIC_ITEMS; i++) {
    put32(b + items_at + i * 8, items[i][0]);
    put16(b + items_at + i * 8 + 4, items[i][1]);
    put16(b + items_at + i * 8 + 6, items[i][2]);
  }
  uint32_t rules[SYNTHETIC_RULES][2] = { { BOW_L1, 1 }, { BOW_L2, 2 }, { BOOMERANG, 1 }, { SOUL_GHOUL, 1 },
                                         { SOUL_BAT, 1 }, { LULLABY, 1 }, { SONG_OF_TIME, 1 }, { PRELUDE, 1 } };
  for (int slot = 0; slot < BOTTLE_SLOTS; slot++) {
    rules[SYNTHETIC_RULES - BOTTLE_SLOTS + slot][0] = BOTTLE_A + slot;
    rules[SYNTHETIC_RULES - BOTTLE_SLOTS + slot][1] = (uint32_t)slot + 1;
  }
  for (int i = 0; i < SYNTHETIC_RULES; i++) {
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

static blob_t synthetic_of_version(int version)
{
  return synthetic_with(version, 0);
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
  CHECK(trk.region_count == 2 && trk.check_count == 3 && trk.item_count == SYNTHETIC_ITEMS && trk.key_count == 2);
  trk_region_t deku = trk_region(&trk, 1);
  CHECK(!strcmp(trk_string(&trk, deku.name), "Deku Tree") && deku.first_check == 2 && deku.check_count == 1);
  trk_check_t check = trk_check(&trk, 1);
  CHECK(check.key == BOOL64_KEY && check.kind == TRK_KIND_BOOL64);
  CHECK(trk.version == TRK_VERSION && !strcmp(trk_string(&trk, check.name), "Kokiri Sword Chest"));
  CHECK(trk.flags == 0 && !(trk.flags & TRK_FLAG_ARCHIPELAGO));
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
    { "magic", 0, 0x58585858, 4 },       { "version", 4, 5, 2 },        { "header size", 6, 64, 2 },
    { "a version 2 header's size", 6, HEADER_BYTES, 2 }, { "a version 3 header's size", 6, HEADER_V3, 2 },
    { "ids outside", 76, 100000, 4 },    { "id count", 80, 100000, 4 },
    { "places outside", 84, 100000, 4 }, { "place count", 88, 50, 4 },
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
  put16(blob.bytes + trk.items_at + 6, SYNTHETIC_RULES + 1); /* the first item claims 14 rules of 13 */
  CHECK(!parses(&blob));
  return 0;
}

static int test_parse_reads_the_archipelago_flag_and_older_versions_as_local(void)
{
  blob_t blob = synthetic_with(3, TRK_FLAG_ARCHIPELAGO);
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(trk.version == 3 && trk.header_size == HEADER_V3 && (trk.flags & TRK_FLAG_ARCHIPELAGO));
  CHECK(trk.region_count == 2 && !strcmp(trk_string(&trk, trk.seed_id), "abc123"));
  for (int version = 1; version <= 2; version++) {
    blob = synthetic_of_version(version);
    CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
    CHECK(trk.version == (uint32_t)version && trk.header_size == HEADER_BYTES && trk.flags == 0);
    put16(blob.bytes + 4, 3); /* a version 3 file must have the longer header */
    CHECK(!parses(&blob));
  }
  blob = synthetic_with(3, 0);
  put32(blob.bytes + 32, HEADER_BYTES); /* the regions over the flags */
  CHECK(!parses(&blob));
  return 0;
}

static int test_parse_reads_the_checks_ids_and_places(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(trk.header_size == HEADER_V4 && trk.ident_count == 3 && trk.place_count == PLACES);
  for (uint32_t i = 0; i < 3; i++)
    CHECK(!strcmp(trk_string(&trk, trk_check_ident(&trk, i)), check_idents[i]));
  CHECK(trk_check_ident(&trk, 3) == 0);
  uint32_t first = 99;
  CHECK(trk_places_of(&trk, 0, &first) == 1 && first == 0);
  CHECK(trk_places_of(&trk, 1, &first) == 2 && first == 1);
  CHECK(trk_places_of(&trk, 2, &first) == 0);
  trk_place_t place = trk_place(&trk, 2);
  CHECK(place.check == 1 && place.x == -20 && place.y == 1.5f && place.z == 30);
  CHECK(!strcmp(trk_string(&trk, place.map), "KokiriForest_Adult"));
  CHECK(!strcmp(trk_string(&trk, place.label), "Kokiri Forest (adult)"));
  CHECK(trk.flags == 0);
  blob = synthetic_with(4, TRK_FLAG_ARCHIPELAGO);
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why) && (trk.flags & TRK_FLAG_ARCHIPELAGO));
  return 0;
}

static int test_older_files_have_no_ids_or_places(void)
{
  for (int version = 1; version <= 3; version++) {
    blob_t blob = synthetic_of_version(version);
    trk_t trk;
    const char *why = "";
    CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
    CHECK(trk.ident_count == 0 && trk.place_count == 0 && trk_check_ident(&trk, 0) == 0);
    uint32_t first;
    CHECK(trk_places_of(&trk, 0, &first) == 0);
    put16(blob.bytes + 4, 4); /* a version 4 file must have the longer header */
    CHECK(!parses(&blob));
  }
  return 0;
}

static int test_parse_refuses_damaged_ids_and_places(void)
{
  blob_t good = synthetic(), blob;
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, good.bytes, good.size, &why));
  struct { const char *what; size_t at; uint32_t value; } damage[] = {
    { "an id count other than the checks'", 80, 2 },
    { "an id outside the strings", trk.idents_at + 4, trk.strings_size },
    { "a place of a check past the checks", trk.places_at + 2 * 24, 3 },
    { "a place of a check before the place before it", trk.places_at + 2 * 24, 0 },
    { "a map outside the strings", trk.places_at + 4, trk.strings_size },
    { "a label outside the strings", trk.places_at + 24 + 8, trk.strings_size },
    { "a coordinate that isn't a number", trk.places_at + 12, 0x7FC00000u },
  };
  for (unsigned i = 0; i < sizeof(damage) / sizeof(*damage); i++) {
    blob = good;
    put32(blob.bytes + damage[i].at, damage[i].value);
    if (parses(&blob)) {
      snprintf(failure, sizeof(failure), "%s was accepted", damage[i].what);
      return 1;
    }
  }
  blob = good;
  put_float(blob.bytes + trk.places_at + 24 + 20, 2e7f); /* off the world */
  CHECK(!parses(&blob));
  blob = good;
  put32(blob.bytes + 80, 0); /* no ids at all: still a file */
  CHECK(parses(&blob));
  blob = good;
  put32(blob.bytes + 88, 0); /* no places */
  CHECK(parses(&blob));
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
  blob.bytes[trk.strings_at + trk.strings_size - 1] = 'x';
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
  set_bool(&fake, LULLABY, GD_TRUE);
  set_bool(&fake, SONG_OF_TIME, GD_FALSE);
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
  CHECK(state.cells[grid_index_of("Zeldas Lullaby")].status == ITEM_OWNED);   /* a song learned */
  CHECK(state.cells[grid_index_of("Song of Time")].status == ITEM_MISSING);   /* the game knows its flag: not learned */
  CHECK(state.cells[grid_index_of("Prelude of Light")].status == ITEM_UNKNOWN); /* the game has no flag for it */
  CHECK(state.cells[grid_index_of("Eponas Song")].status == ITEM_UNKNOWN);    /* a seed file without it */
  CHECK(state.region_count == 2 && !strcmp(state.regions[0].name, "Kokiri Forest"));
  CHECK(state.regions[0].collected == 2 && state.regions[0].trackable == 2);
  CHECK(state.regions[1].collected == 0 && state.regions[1].trackable == 1);
  CHECK(state.collected == 2 && state.trackable == 3 && state.unreadable == 0);
  CHECK(state.key_count == 2 && state.keys[0].has_small_keys && state.keys[0].small_keys_known);
  CHECK(state.keys[0].found == 3 && state.keys[0].total == 5 && state.keys[0].boss == BOSS_KEY_HELD);
  CHECK(state.keys[1].found == 3 && state.keys[1].total == 3 && state.keys[1].boss == BOSS_KEY_NONE);
  return 0;
}

/* the Bottle cell's level with the given slots' flags set, as the panel and as the postcard have it (-1 if they differ) */
static int bottle_level_with(const trk_t *trk, const bool slots[BOTTLE_SLOTS])
{
  fake_flags_t fake = fake_with(GD_FALSE);
  for (int slot = 0; slot < BOTTLE_SLOTS; slot++)
    set_bool(&fake, BOTTLE_A + slot, slots[slot] ? GD_TRUE : GD_FALSE);
  tracker_state_t panel, postcard;
  tracker_compute(trk, &fake.source, &panel);
  tracker_compute_icons(trk, &fake.source, &postcard);
  cell_state_t shown = panel.cells[grid_index_of("Bottle")];
  bool owned = shown.status == ITEM_OWNED;
  return shown.level == postcard.cells[grid_index_of("Bottle")].level && owned == (shown.level > 0) ? shown.level : -1;
}

/* the bottles are counted by their slots' flags, whatever order the slots fill in */
static int test_the_bottle_cell_counts_its_slots(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(grid_cell(grid_index_of("Bottle"))->counted && grid_cell(grid_index_of("Bottle"))->levels == BOTTLE_SLOTS);
  const bool none[BOTTLE_SLOTS] = { false }, only_a[BOTTLE_SLOTS] = { true }, b_and_d[BOTTLE_SLOTS] = { false, true, false, true },
             only_e[BOTTLE_SLOTS] = { false, false, false, false, true }, all[BOTTLE_SLOTS] = { true, true, true, true, true };
  CHECK(bottle_level_with(&trk, none) == 0);
  CHECK(bottle_level_with(&trk, only_a) == 1);
  CHECK(bottle_level_with(&trk, b_and_d) == 2); /* out of order: two bottles, not "level 4" */
  CHECK(bottle_level_with(&trk, only_e) == 1);
  CHECK(bottle_level_with(&trk, all) == BOTTLE_SLOTS);
  fake_flags_t unknown = fake_with(GD_UNKNOWN); /* the game has none of the slots' flags: not the same as no bottle */
  tracker_state_t state;
  tracker_compute(&trk, &unknown.source, &state);
  CHECK(state.cells[grid_index_of("Bottle")].status == ITEM_UNKNOWN);
  return 0;
}

/* the Gold Skulltula count, in the full state and in the postcard's */
static int test_the_skulltula_count(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  const int32_t held[] = { 0, 37, GOLD_SKULLTULA_TOTAL, -5 };
  const uint32_t expected[] = { 0, 37, GOLD_SKULLTULA_TOTAL, 0 }; /* a negative value is none */
  for (unsigned i = 0; i < sizeof(held) / sizeof(*held); i++) {
    fake_flags_t fake = fake_with(GD_UNKNOWN);
    fake.ints[fake.int_count].hash = GOLD_SKULLTULA_COUNT_HASH;
    fake.ints[fake.int_count++].value = held[i];
    tracker_state_t full, icons;
    tracker_compute(&trk, &fake.source, &full);
    tracker_compute_icons(&trk, &fake.source, &icons);
    CHECK(full.skulltulas_known && full.skulltulas == expected[i]);
    CHECK(icons.skulltulas_known && icons.skulltulas == expected[i]);
  }
  fake_flags_t nothing = fake_with(GD_UNKNOWN);
  tracker_state_t state;
  tracker_compute(&trk, &nothing.source, &state);
  CHECK(!state.skulltulas_known && state.skulltulas == 0); /* the game has no such field: shown as ? */
  tracker_compute_icons(&trk, &nothing.source, &state);
  CHECK(!state.skulltulas_known && state.skulltulas == 0);
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
  for (int song = ITEM_CELLS; song < GRID_CELLS; song++) /* a seed file made before the songs: the game's flags aren't asked */
    CHECK(state.cells[song].status == ITEM_UNKNOWN);
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
  fake->build = (game_build_t){ "test", 0, 0, MANAGER_POINTER_AT, INT_VTABLE_AT, BOOL_VTABLE_AT, 0, 0 };
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

/* The String64 "map" (and the others) as the game's GetString64 finds them: its type entry at the manager's 0x608,
 * each object's text pointer at 0x68 and the text's capacity after it. */
static int test_the_games_strings_are_read_as_it_reads_them(void)
{
  static fake_game_t fake;
  static _Alignas(8) uint8_t objects[3][0x108];
  static uint32_t table[2 * TABLE_SIZE];
  static char texts[2][64];
  build_fake_game(&fake);
  memset(objects, 0, sizeof(objects));
  memset(table, 0, sizeof(table));
  memset(texts, 0, sizeof(texts));
  strcpy(texts[0], "KokiriForest_Child");
  strcpy(texts[1], "Short");
  const uint32_t capacities[3] = { 64, 16, 64 };
  for (int i = 0; i < 3; i++) {
    uintptr_t text = i < 2 ? (uintptr_t)texts[i] : 0;
    memcpy(objects[i] + 0x68, &text, sizeof(text));
    memcpy(objects[i] + 0x70, &capacities[i], sizeof(capacities[i]));
  }
  table_insert(table, GAMEDATA_MAP_STRING, 0);
  table_insert(table, 77, 1); /* too little room for a String64: the game would refuse it too */
  table_insert(table, 78, 2); /* no text */
  fill_type((gd_type_t *)(fake.manager + 0x608), 0, 3, objects, table);
  gamedata_t data;
  gamedata_init(&data, fake.game);
  char out[GAMEDATA_STRING_ROOM];
  CHECK(!gamedata_string(&data, GAMEDATA_MAP_STRING, out, sizeof(out)) && !out[0]); /* before an attach */
  CHECK(gamedata_attach(&data));
  CHECK(gamedata_string(&data, GAMEDATA_MAP_STRING, out, sizeof(out)) && !strcmp(out, "KokiriForest_Child"));
  CHECK(gamedata_string(&data, GAMEDATA_MAP_STRING, out, 7) && !strcmp(out, "Kokiri"));
  CHECK(!gamedata_string(&data, 77, out, sizeof(out)) && !out[0]);
  CHECK(!gamedata_string(&data, 78, out, sizeof(out)));
  CHECK(!gamedata_string(&data, 12345, out, sizeof(out)));
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

/* sloperinaGZ's gd_game_paused: Sequence_IsPause, or Sequence_GamePauseRequestCount above 0 */
#define IS_PAUSE_HASH       0x604AEBE1u
#define PAUSE_REQUESTS_HASH 0x64A61098u

static int test_the_games_pause_is_its_bool_or_its_requests(void)
{
  static fake_game_t fake;
  gamedata_t data;
  for (int round = 0; round < 3; round++) {
    build_fake_game(&fake);
    gamedata_init(&data, fake.game);
    CHECK(gamedata_attach(&data) && !gamedata_paused(&data));
    if (round == 0)
      table_insert(fake.bool_table, IS_PAUSE_HASH, 1); /* the bool, false */
    else if (round == 1)
      table_insert(fake.bool_table, IS_PAUSE_HASH, 0); /* the bool, true */
    else
      table_insert(fake.int_table, PAUSE_REQUESTS_HASH, 0); /* 100 requests */
    CHECK(gamedata_paused(&data) == (round > 0));
    free_fake_game(&fake);
  }
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
  CHECK(!(hidden & BTN_B) && !(hidden & BTN_A) && !(hidden & BTN_Y) && !(hidden & BTN_RSTICK));
  hidden = controls_hidden(0, true);
  CHECK((hidden & BTN_B) && (hidden & BTN_R) && (hidden & BTN_A) && (hidden & BTN_DPAD) == BTN_DPAD);
  CHECK(hidden & BTN_Y); /* show in the world's */
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

static int test_y_shows_in_the_world_only_with_the_panel_open(void)
{
  controls_reset();
  CHECK(controls_frame(BTN_Y, false, 0) == CONTROL_NONE); /* the game's while the panel is closed */
  CHECK(controls_hidden(BTN_Y, false) == 0);
  CHECK(controls_frame(0, true, 10) == CONTROL_NONE);
  CHECK(controls_frame(BTN_Y, true, 20) == CONTROL_LOCATE);
  CHECK(controls_frame(BTN_Y, true, 30) == CONTROL_NONE); /* on the press only */
  CHECK(controls_frame(BTN_Y | BTN_A, true, 40) == CONTROL_SELECT); /* A pressed while Y is held */
  CHECK(controls_frame(0, true, 50) == CONTROL_NONE);
  CHECK(controls_frame(BTN_A | BTN_Y, true, 60) == CONTROL_SELECT); /* both at once: A first */
  CHECK(controls_frame(0, true, 70) == CONTROL_NONE);
  CHECK(controls_frame(BTN_Y, true, 80) == CONTROL_LOCATE);
  controls_hold_back_held(); /* the panel closed with Y held */
  CHECK(controls_hidden(BTN_Y, false) & BTN_Y);
  CHECK(controls_frame(0, false, 90) == CONTROL_NONE);
  CHECK(controls_hidden(BTN_Y, false) == 0); /* a new press of Y is the game's */
  return 0;
}

/* --- browsing --------------------------------------------------------------------------------- */

static int test_the_highlight_moves_over_the_regions_columns(void)
{
  /* 35 regions and the Settings entry (35) in 3 columns of 12: 0-11, 12-23, 24-35 */
  browse_t b = { BROWSE_REGIONS, 0, 0, 0, 0, 0 };
  CHECK(browse_region_rows(35) == 12 && browse_region_rows(36) == 13 && browse_region_rows(1) == 1);
  CHECK(browse_region_rows(0) == 1);
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
  CHECK(b.region == 35); /* the last column's foot: the Settings entry */
  browse_move(&b, NAV_DOWN, 35, 0);
  CHECK(b.region == 35);
  b.region = 5; /* 7 regions and the Settings entry: columns of 3, 3 and 2 */
  browse_move(&b, NAV_RIGHT, 7, 0);
  CHECK(b.region == 7); /* the shorter last column: its last entry */
  b.region = 0;
  browse_move(&b, NAV_DOWN, 0, 0); /* no regions: the Settings entry is the only one */
  CHECK(b.region == 0);
  b.region = 35;
  browse_reopen(&b, 20, 0); /* fewer regions than the highlight: kept inside, at the Settings entry */
  CHECK(b.view == BROWSE_REGIONS && b.region == 20);
  return 0;
}

static int test_the_panel_reopens_where_it_was_closed(void)
{
  browse_t b = { BROWSE_CHECKS, 2, 30, 20, 0, 0 };
  browse_reopen(&b, 5, 40);
  CHECK(b.view == BROWSE_CHECKS && b.region == 2 && b.check == 30 && b.top == 20); /* the same list and row */
  browse_reopen(&b, 5, 10);
  CHECK(b.view == BROWSE_CHECKS && b.check == 9 && b.top == 9); /* a shorter list: its last check, shown */
  b.top = 0;
  b.check = 25;
  browse_reopen(&b, 5, 40);
  CHECK(b.check == 25 && b.top == 25 - BROWSE_CHECK_ROWS + 1); /* the row stays in sight */
  b.region = 5;
  browse_reopen(&b, 5, 0);
  CHECK(b.view == BROWSE_REGIONS && b.region == 5); /* the Settings entry has no list */
  b = (browse_t){ BROWSE_CONSOLE, 5, 0, 0, SETTINGS_CONSOLE, 3 };
  browse_reopen(&b, 5, 0);
  CHECK(b.view == BROWSE_CONSOLE && b.entry == SETTINGS_CONSOLE && b.setting == 3); /* a settings page */
  return 0;
}

static int test_a_list_opens_scrolls_and_goes_back(void)
{
  browse_t b = { BROWSE_REGIONS, 4, 7, 3, 0, 0 };
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_REGIONS); /* the highlight is past the regions and the Settings entry */
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

static int test_the_settings_entry_opens_the_postcard_and_the_console(void)
{
  browse_t b = { BROWSE_REGIONS, 3, 7, 3, 1, 2 };
  browse_open(&b, 3); /* the region count is the Settings entry */
  CHECK(b.view == BROWSE_SETTINGS && b.region == 3 && b.entry == SETTINGS_POSTCARD);
  CHECK(browse_page_rows(BROWSE_SETTINGS) == SETTINGS_ENTRY_COUNT && browse_page_row(&b) == 0);
  browse_move(&b, NAV_UP, 3, 0);
  CHECK(b.entry == SETTINGS_POSTCARD);
  browse_move(&b, NAV_DOWN, 3, 0);
  browse_move(&b, NAV_DOWN, 3, 0);
  CHECK(b.entry == SETTINGS_CONSOLE); /* the last stays */
  browse_move(&b, NAV_UP, 3, 0);
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_POSTCARD && b.setting == 0);
  for (int i = 0; i < POSTCARD_SETTING_COUNT + 2; i++)
    browse_move(&b, NAV_DOWN, 3, 0);
  CHECK(b.setting == POSTCARD_SETTING_COUNT - 1 && browse_page_row(&b) == POSTCARD_SETTING_COUNT - 1);
  browse_move(&b, NAV_UP, 3, 0);
  browse_move(&b, NAV_LEFT, 3, 0); /* a value changes in app.c; the highlight stays */
  browse_move(&b, NAV_RIGHT, 3, 0);
  CHECK(b.setting == POSTCARD_SETTING_COUNT - 2 && b.view == BROWSE_POSTCARD);
  browse_open(&b, 3); /* A in the postcard's settings does nothing */
  CHECK(b.view == BROWSE_POSTCARD && b.setting == POSTCARD_SETTING_COUNT - 2);
  CHECK(browse_back(&b) && b.view == BROWSE_SETTINGS && b.entry == SETTINGS_POSTCARD); /* back to Settings */
  CHECK(browse_back(&b) && b.view == BROWSE_REGIONS && b.region == 3);
  CHECK(!browse_back(&b));
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_SETTINGS && b.entry == 0); /* opened afresh from the first entry */
  browse_move(&b, NAV_DOWN, 3, 0);
  browse_open(&b, 3);
  CHECK(b.view == BROWSE_CONSOLE && b.setting == 0 && browse_page_rows(BROWSE_CONSOLE) == CONSOLE_SETTING_COUNT);
  browse_open(&b, 3); /* A on a value: nothing */
  CHECK(b.view == BROWSE_CONSOLE);
  for (int i = 0; i < CONSOLE_SETTING_COUNT + 1; i++)
    browse_move(&b, NAV_DOWN, 3, 0);
  CHECK(b.setting == CONSOLE_SETTING_COUNT - 1 && browse_page_row(&b) == CONSOLE_SETTING_COUNT - 1); /* the last kind */
  CHECK(console_setting_kind((console_setting_t)b.setting) == CONSOLE_OTHERS);
  browse_open(&b, 3); /* A on a kind ticks it in app.c; the page stays */
  CHECK(b.view == BROWSE_CONSOLE && b.setting == CONSOLE_SETTING_COUNT - 1);
  CHECK(browse_back(&b) && b.view == BROWSE_SETTINGS && b.entry == SETTINGS_CONSOLE);
  CHECK(browse_page_rows(BROWSE_REGIONS) == 0 && browse_page_rows(BROWSE_CHECKS) == 0);
  return 0;
}

/* --- the postcard ------------------------------------------------------------------------------ */

static int test_postcard_defaults_and_values(void)
{
  postcard_settings_t s = postcard_defaults();
  CHECK(!s.shown && s.position == POSTCARD_BOTTOM_RIGHT && s.size == POSTCARD_SMALL);
  CHECK(postcard_opacity(&s) == 0.5f);
  CHECK(!strcmp(postcard_value_text(&s, POSTCARD_SETTING_SHOWN), "Off"));
  CHECK(!strcmp(postcard_value_text(&s, POSTCARD_SETTING_POSITION), "Bottom right"));
  CHECK(!strcmp(postcard_value_text(&s, POSTCARD_SETTING_SIZE), "Small"));
  CHECK(!strcmp(postcard_value_text(&s, POSTCARD_SETTING_OPACITY), "50 %"));
  CHECK(!strcmp(postcard_setting_name(POSTCARD_SETTING_SHOWN), "Postcard"));
  CHECK(!strcmp(postcard_setting_name(POSTCARD_SETTING_POSITION), "Position"));
  CHECK(!strcmp(postcard_setting_name(POSTCARD_SETTING_SIZE), "Size"));
  CHECK(!strcmp(postcard_setting_name(POSTCARD_SETTING_OPACITY), "Opacity"));
  CHECK(!strcmp(postcard_setting_name(POSTCARD_SETTING_COUNT), ""));
  postcard_settings_t large = { true, POSTCARD_TOP_LEFT, POSTCARD_LARGE, 3 };
  CHECK(postcard_scale(&large) == 1.0f && postcard_opacity(&large) == 1.0f);
  CHECK(!strcmp(postcard_value_text(&large, POSTCARD_SETTING_SHOWN), "On"));
  CHECK(!strcmp(postcard_value_text(&large, POSTCARD_SETTING_OPACITY), "100 %"));
  CHECK(postcard_scale(&s) < 0.7f && postcard_scale(&s) > 0.3f); /* small is under the medium, which is under the large */
  postcard_settings_t medium = { false, 0, POSTCARD_MEDIUM, 0 };
  CHECK(postcard_scale(&s) < postcard_scale(&medium) && postcard_scale(&medium) < postcard_scale(&large));
  CHECK(postcard_opacity(&medium) == 0.25f);
  return 0;
}

static int test_postcard_settings_cycle_both_ways(void)
{
  postcard_settings_t s = postcard_defaults();
  postcard_step(&s, POSTCARD_SETTING_SHOWN, 1);
  CHECK(s.shown);
  postcard_step(&s, POSTCARD_SETTING_SHOWN, -1);
  CHECK(!s.shown);
  postcard_step(&s, POSTCARD_SETTING_POSITION, 1); /* bottom right wraps to top left */
  CHECK(s.position == POSTCARD_TOP_LEFT);
  postcard_step(&s, POSTCARD_SETTING_POSITION, -1);
  CHECK(s.position == POSTCARD_BOTTOM_RIGHT);
  postcard_step(&s, POSTCARD_SETTING_SIZE, -1); /* small wraps back to large */
  CHECK(s.size == POSTCARD_LARGE);
  postcard_step(&s, POSTCARD_SETTING_SIZE, 1);
  CHECK(s.size == POSTCARD_SMALL);
  for (int i = 0; i < POSTCARD_OPACITY_COUNT; i++)
    postcard_step(&s, POSTCARD_SETTING_OPACITY, 1);
  CHECK(postcard_opacity(&s) == 0.5f); /* a full turn */
  postcard_step(&s, POSTCARD_SETTING_OPACITY, 1);
  CHECK(postcard_opacity(&s) == 0.75f);
  postcard_step(&s, POSTCARD_SETTING_OPACITY, 1);
  postcard_step(&s, POSTCARD_SETTING_OPACITY, 1);
  CHECK(postcard_opacity(&s) == 0.25f); /* 100 % wraps to 25 % */
  postcard_step(&s, POSTCARD_SETTING_OPACITY, -1);
  CHECK(postcard_opacity(&s) == 1.0f);
  postcard_step(&s, POSTCARD_SETTING_COUNT, 1); /* not a setting: nothing changes */
  CHECK(!s.shown && s.position == POSTCARD_BOTTOM_RIGHT && s.size == POSTCARD_SMALL);
  return 0;
}

static int test_the_postcard_sits_in_its_corner(void)
{
  float x, y;
  const float area_w = 1920, area_h = 1080, card_w = 300, card_h = 200, margin = 24;
  postcard_origin(POSTCARD_TOP_LEFT, area_w, area_h, card_w, card_h, margin, &x, &y);
  CHECK(x == 24 && y == 24);
  postcard_origin(POSTCARD_TOP_RIGHT, area_w, area_h, card_w, card_h, margin, &x, &y);
  CHECK(x == 1596 && y == 24);
  postcard_origin(POSTCARD_BOTTOM_LEFT, area_w, area_h, card_w, card_h, margin, &x, &y);
  CHECK(x == 24 && y == 856);
  postcard_origin(POSTCARD_BOTTOM_RIGHT, area_w, area_h, card_w, card_h, margin, &x, &y);
  CHECK(x == 1596 && y == 856);
  return 0;
}

static postcard_settings_t postcard_read(const char *text)
{
  postcard_settings_t s = postcard_defaults();
  postcard_parse(&s, text, strlen(text));
  return s;
}

static bool postcard_equal(postcard_settings_t a, postcard_settings_t b)
{
  return a.shown == b.shown && a.position == b.position && a.size == b.size && a.opacity == b.opacity;
}

static int test_postcard_file_text(void)
{
  char text[64];
  postcard_settings_t defaults = postcard_defaults();
  size_t length = postcard_format(&defaults, text, sizeof(text));
  CHECK(length == strlen(text) && !strcmp(text, "postcard=0\nposition=3\nsize=0\nopacity=50\n"));
  for (int combination = 0; combination < 2 * POSTCARD_POSITION_COUNT * POSTCARD_SIZE_COUNT * POSTCARD_OPACITY_COUNT;
       combination++) {
    postcard_settings_t s = { combination & 1, (uint8_t)(combination / 2 % POSTCARD_POSITION_COUNT),
                              (uint8_t)(combination / 8 % POSTCARD_SIZE_COUNT),
                              (uint8_t)(combination / 24 % POSTCARD_OPACITY_COUNT) };
    postcard_settings_t read = { !s.shown, 1, 1, 1 };
    postcard_format(&s, text, sizeof(text));
    postcard_parse(&read, text, strlen(text));
    CHECK(postcard_equal(read, s));
  }
  char small[16];
  length = postcard_format(&defaults, small, sizeof(small)); /* only whole lines that fit, with their NUL */
  CHECK(length < sizeof(small) && length == strlen(small) && !strcmp(small, "postcard=0\n"));
  CHECK(postcard_format(&defaults, small, 0) == 0);
  return 0;
}

static int test_postcard_file_tolerates_a_bad_file(void)
{
  postcard_settings_t defaults = postcard_defaults();
  CHECK(postcard_equal(postcard_read(""), defaults));
  CHECK(postcard_equal(postcard_read("\n\n"), defaults));
  CHECK(postcard_equal(postcard_read("garbage without any sign"), defaults));
  CHECK(postcard_equal(postcard_read("postcard=\nsize=x\nposition=-1\nopacity=5o\n=3\n"), defaults));
  CHECK(postcard_equal(postcard_read("postcard=2\nposition=4\nsize=3\nopacity=60\nopacity=0\n"), defaults));
  CHECK(postcard_equal(postcard_read("postcard=1\nposition=99999999999999\n"), (postcard_settings_t){ true, 3, 0, 1 }));
  CHECK(postcard_equal(postcard_read("size=1\nunknown=1\nposition=0\n"), (postcard_settings_t){ false, 0, 1, 1 }));
  CHECK(postcard_equal(postcard_read("postcard=1\r\nposition=1\r\nsize=2\r\nopacity=75"), (postcard_settings_t){ true, 1, 2, 2 }));
  CHECK(postcard_equal(postcard_read("size=1\nsize=2\n"), (postcard_settings_t){ false, 3, 2, 1 })); /* the last of a name wins */
  CHECK(postcard_equal(postcard_read("size=2\nsize=7\n"), (postcard_settings_t){ false, 3, 2, 1 })); /* a bad later line leaves it */
  const char binary[] = { 'p', 'o', 's', 'i', 't', 'i', 'o', 'n', '=', '1', '\0', '2', '\n' };
  postcard_settings_t s = defaults;
  postcard_parse(&s, binary, sizeof(binary)); /* the NUL is not a digit: skipped */
  CHECK(postcard_equal(s, defaults));
  s = defaults;
  postcard_parse(&s, "size=2\nopacity=100\n", 7); /* only the first line is in range */
  CHECK(s.size == 2 && s.opacity == 1);
  return 0;
}

static int test_the_icons_state_is_the_full_states_cells_and_keys(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  set_bool(&fake, BOW_L1, GD_TRUE);
  set_bool(&fake, BOOMERANG, GD_FALSE);
  set_bool(&fake, FOREST_BOSS, GD_TRUE);
  fake.ints[fake.int_count].hash = FOREST_FOUND;
  fake.ints[fake.int_count++].value = 2;
  tracker_state_t full, icons;
  tracker_compute(&trk, &fake.source, &full);
  tracker_compute_icons(&trk, &fake.source, &icons);
  CHECK(!memcmp(full.cells, icons.cells, sizeof(full.cells)));
  CHECK(full.key_count == 2 && icons.key_count == full.key_count);
  CHECK(!memcmp(full.keys, icons.keys, 2 * sizeof(full.keys[0])));
  CHECK(icons.region_count == 0 && icons.collected == 0 && icons.trackable == 0);
  return 0;
}

/* --- the console ------------------------------------------------------------------------------- */

static int test_console_defaults_and_values(void)
{
  console_settings_t s = console_defaults();
  CHECK(!console_shown(&s, false) && console_shown(&s, true)); /* off for local seeds, on for Archipelago ones */
  CHECK(s.position == CONSOLE_BOTTOM && console_opacity(&s) == 0.75f && console_lines(&s) == 6);
  CHECK(console_fade_ms(&s) == 10000);
  for (int kind = 0; kind < CONSOLE_KIND_COUNT; kind++)
    CHECK(console_kind_shown(&s, (console_kind_t)kind));
  CHECK(!console_kind_shown(&s, CONSOLE_KIND_COUNT));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_SHOWN, true), "On"));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_SHOWN, false), "Off"));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_POSITION, true), "Bottom centre"));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_OPACITY, true), "75 %"));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_LINES, true), "6"));
  CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_FADE, true), "10 s"));
  CHECK(!strcmp(console_setting_name(CONSOLE_SETTING_SHOWN), "Console"));
  CHECK(!strcmp(console_setting_name(CONSOLE_SETTING_FADE), "Fade"));
  CHECK(!strcmp(console_setting_name(CONSOLE_SETTING_COUNT), ""));
  CHECK(!console_setting_is_kind(CONSOLE_SETTING_FADE) && !console_setting_is_kind(CONSOLE_SETTING_COUNT));
  CHECK(console_setting_kind(CONSOLE_SETTING_COUNT) == CONSOLE_KIND_COUNT);
  /* the page's rows after Fade: one per kind, in the mailbox's order, with a tick box (no value) */
  const char *kinds[CONSOLE_KIND_COUNT] = { "Items received", "Items sent", "Hints", "Chat", "Server notices",
                                           "Other players' items" };
  CHECK(CONSOLE_SETTING_COUNT == CONSOLE_SETTING_FIRST_KIND + CONSOLE_KIND_COUNT && CONSOLE_SETTING_FIRST_KIND == 5);
  for (int kind = 0; kind < CONSOLE_KIND_COUNT; kind++) {
    console_setting_t row = (console_setting_t)(CONSOLE_SETTING_FIRST_KIND + kind);
    CHECK(console_setting_is_kind(row) && console_setting_kind(row) == (console_kind_t)kind);
    CHECK(!strcmp(console_kind_name((console_kind_t)kind), kinds[kind]));
    CHECK(!strcmp(console_setting_name(row), kinds[kind]) && console_value_text(&s, row, true) == 0);
  }
  return 0;
}

static int test_console_settings_cycle_and_each_kind_of_seed_has_its_own_switch(void)
{
  console_settings_t s = console_defaults();
  console_step(&s, CONSOLE_SETTING_SHOWN, 1, true);
  CHECK(!console_shown(&s, true) && !console_shown(&s, false)); /* the Archipelago one only */
  console_step(&s, CONSOLE_SETTING_SHOWN, -1, false);
  CHECK(console_shown(&s, false) && !console_shown(&s, true));
  const char *positions[CONSOLE_POSITION_COUNT] = { "Bottom centre", "Top centre", "Left centre", "Right centre" };
  for (int i = 0; i < CONSOLE_POSITION_COUNT; i++) {
    CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_POSITION, false), positions[i]));
    console_step(&s, CONSOLE_SETTING_POSITION, 1, false);
  }
  CHECK(s.position == CONSOLE_BOTTOM); /* a full turn */
  console_step(&s, CONSOLE_SETTING_POSITION, -1, false);
  CHECK(s.position == CONSOLE_RIGHT);
  const int lines[CONSOLE_STEPS] = { 8, 12, 4, 6 };
  const char *fades[CONSOLE_STEPS] = { "30 s", "Permanent", "5 s", "10 s" };
  const uint32_t fade_ms[CONSOLE_STEPS] = { 30000, 0, 5000, 10000 };
  for (int i = 0; i < CONSOLE_STEPS; i++) {
    console_step(&s, CONSOLE_SETTING_LINES, 1, false);
    console_step(&s, CONSOLE_SETTING_FADE, 1, false);
    CHECK(console_lines(&s) == lines[i] && console_fade_ms(&s) == fade_ms[i]);
    CHECK(!strcmp(console_value_text(&s, CONSOLE_SETTING_FADE, false), fades[i]));
  }
  console_step(&s, CONSOLE_SETTING_OPACITY, 1, false);
  CHECK(console_opacity(&s) == 1.0f);
  console_step(&s, CONSOLE_SETTING_OPACITY, 1, false);
  CHECK(console_opacity(&s) == 0.25f); /* 100 % wraps to 25 % */
  console_settings_t before = s;
  console_step(&s, CONSOLE_SETTING_COUNT, 1, false); /* past the rows: nothing */
  CHECK(!memcmp(&before, &s, sizeof(s)));
  /* a kind's row ticks or unticks it either way, and only it */
  console_step(&s, (console_setting_t)(CONSOLE_SETTING_FIRST_KIND + CONSOLE_CHAT), 1, false);
  console_step(&s, (console_setting_t)(CONSOLE_SETTING_FIRST_KIND + CONSOLE_HINT), -1, false);
  CHECK(!console_kind_shown(&s, CONSOLE_CHAT) && !console_kind_shown(&s, CONSOLE_HINT));
  CHECK(console_kind_shown(&s, CONSOLE_RECEIVED) && console_kind_shown(&s, CONSOLE_OTHERS));
  CHECK(s.position == before.position && s.opacity == before.opacity && s.shown[0] == before.shown[0]);
  console_step(&s, (console_setting_t)(CONSOLE_SETTING_FIRST_KIND + CONSOLE_CHAT), -1, false);
  CHECK(console_kind_shown(&s, CONSOLE_CHAT));
  console_step(&s, (console_setting_t)(CONSOLE_SETTING_FIRST_KIND + CONSOLE_OTHERS), 1, false);
  CHECK(!console_kind_shown(&s, CONSOLE_OTHERS) && console_kind_shown(&s, CONSOLE_SERVER));
  return 0;
}

static bool console_equal(console_settings_t a, console_settings_t b)
{
  return a.shown[0] == b.shown[0] && a.shown[1] == b.shown[1] && a.position == b.position && a.opacity == b.opacity &&
         a.lines == b.lines && a.fade == b.fade && a.kinds == b.kinds;
}

static console_settings_t console_read(const char *text)
{
  console_settings_t s = console_defaults();
  console_parse(&s, text, strlen(text));
  return s;
}

/* paused, the postcard and the console hide; they come back when the game plays again */
static int test_the_pause_hides_the_postcard_and_the_console(void)
{
  postcard_settings_t card = postcard_defaults();
  CHECK(!postcard_over_game(&card, false, false)); /* off at first */
  card.shown = true;
  CHECK(postcard_over_game(&card, false, false));
  CHECK(!postcard_over_game(&card, false, true));
  CHECK(postcard_over_game(&card, false, false));
  console_settings_t console = console_defaults();
  CHECK(console_over_game(&console, true, false, false)); /* on for an Archipelago seed */
  CHECK(!console_over_game(&console, true, false, true));
  CHECK(console_over_game(&console, true, false, false));
  CHECK(!console_over_game(&console, false, false, false)); /* off for a local one, paused or not */
  CHECK(!console_over_game(&console, false, false, true));
  return 0;
}

/* The panel is opened on purpose: paused, it works as ever. It draws the card itself on the Postcard page, so the card
 * isn't drawn on its own meanwhile, paused or not; the console stays handed over for the Console page's preview. */
static int test_the_panel_stays_usable_while_paused(void)
{
  postcard_settings_t card = postcard_defaults();
  card.shown = true;
  CHECK(!postcard_over_game(&card, true, false) && !postcard_over_game(&card, true, true));
  console_settings_t console = console_defaults();
  CHECK(console_over_game(&console, true, true, true));
  CHECK(!console_over_game(&console, false, true, true)); /* off stays off */
  controls_reset(); /* the controls don't read the pause: the combination and the panel's buttons as ever */
  CHECK(controls_frame(BTN_R | BTN_RS_UP, false, 0) == CONTROL_TOGGLE);
  CHECK(controls_frame(0, true, 10) == CONTROL_NONE);
  CHECK(controls_frame(BTN_A, true, 20) == CONTROL_SELECT);
  CHECK(controls_frame(BTN_B, true, 30) == CONTROL_BACK);
  CHECK(controls_hidden(0, true) & BTN_A);
  return 0;
}

static int test_console_file_text(void)
{
  char text[256];
  console_settings_t defaults = console_defaults();
  size_t length = console_format(&defaults, text, sizeof(text));
  CHECK(length == strlen(text));
  CHECK(!strcmp(text, "version=1\non_local=0\non_archipelago=1\nposition=0\nopacity=75\nlines=6\nfade=10\n"
                      "received=1\nsent=1\nhints=1\nchat=1\nserver=1\nothers=1\n"));
  for (int combination = 0; combination < 4 * 4 * 4 * 4 * 64; combination += 7) {
    console_settings_t s = { { combination & 1, combination >> 1 & 1 }, (uint8_t)(combination >> 2 & 3),
                             (uint8_t)(combination >> 4 & 3), (uint8_t)(combination >> 6 & 3),
                             (uint8_t)(combination >> 8 & 3), (uint8_t)(combination >> 3 & 63) };
    console_settings_t read = console_defaults();
    console_format(&s, text, sizeof(text));
    console_parse(&read, text, strlen(text));
    CHECK(console_equal(read, s));
  }
  CHECK(console_format(&defaults, text, 12) == 10 && !strcmp(text, "version=1\n")); /* whole lines only */
  return 0;
}

static int test_console_file_without_its_version_or_damaged_leaves_the_defaults(void)
{
  console_settings_t defaults = console_defaults();
  CHECK(console_equal(console_read(""), defaults));
  CHECK(console_equal(console_read("position=2\nlines=12\n"), defaults)); /* no version: an older file, ignored */
  CHECK(console_equal(console_read("version=2\nposition=2\n"), defaults)); /* a later version's */
  CHECK(console_equal(console_read("garbage\n\n=1\n"), defaults));
  console_settings_t s = console_read("version=1\r\non_local=1\r\nposition=3\r\nfade=0\r\nchat=0\r\nlines=12");
  CHECK(console_shown(&s, false) && console_shown(&s, true) && s.position == CONSOLE_RIGHT);
  CHECK(console_fade_ms(&s) == 0 && console_lines(&s) == 12 && !console_kind_shown(&s, CONSOLE_CHAT));
  s = console_read("version=1\nposition=4\nopacity=60\nlines=5\nfade=11\nchat=2\non_archipelago=7\n");
  CHECK(console_equal(s, defaults)); /* each bad value skipped */
  s = console_read("lines=4\nversion=1\n"); /* the version can come anywhere */
  CHECK(console_lines(&s) == 4);
  return 0;
}

static int test_console_file_of_0_5_0_shows_other_players_items(void)
{
  /* 0.5.0's file has no "others" line: that kind keeps its default, and the kinds it has keep their bits */
  console_settings_t s = console_read("version=1\non_local=0\non_archipelago=1\nposition=0\nopacity=75\nlines=6\n"
                                      "fade=10\nreceived=1\nsent=0\nhints=1\nchat=0\nserver=1\n");
  CHECK(console_kind_shown(&s, CONSOLE_OTHERS) && console_kind_shown(&s, CONSOLE_SERVER));
  CHECK(!console_kind_shown(&s, CONSOLE_SENT) && !console_kind_shown(&s, CONSOLE_CHAT));
  CHECK(console_kind_shown(&s, CONSOLE_RECEIVED) && console_kind_shown(&s, CONSOLE_HINT));
  s = console_read("version=1\nothers=0\n");
  CHECK(!console_kind_shown(&s, CONSOLE_OTHERS) && console_kind_shown(&s, CONSOLE_SERVER));
  return 0;
}

static int test_console_text_is_what_the_font_draws(void)
{
  char out[CONSOLE_TEXT_ROOM];
  const char *ascii = "Link sent Hookshot to Zelda (Kokiri Forest)";
  CHECK(console_sanitize(out, sizeof(out), (const uint8_t *)ascii, strlen(ascii)) == strlen(ascii) && !strcmp(out, ascii));
  const char *accents = "Ren\xC3\xA9" "e \xC3\x9C\xC3\xA7"; /* Latin-1 letters stay, a byte each */
  CHECK(console_sanitize(out, sizeof(out), (const uint8_t *)accents, strlen(accents)) == 8);
  CHECK(!strcmp(out, "Ren\xE9" "e \xDC\xE7"));
  const char *others = "\xE2\x86\x92 \xF0\x9F\x8E\x89 \xE6\x97\xA5x";        /* an arrow, an emoji, a kanji */
  console_sanitize(out, sizeof(out), (const uint8_t *)others, strlen(others));
  CHECK(!strcmp(out, "? ? ?x")); /* one '?' each */
  const char *broken = "a\xC3" "b\xFF" "c\x80" "d\xE2\x86";                  /* a lead without its byte, bytes that lead nothing, a cut end */
  console_sanitize(out, sizeof(out), (const uint8_t *)broken, strlen(broken));
  CHECK(!strcmp(out, "a?b?c?d??"));
  const char *controls = "one\ttwo\nthree\x01\x7F\xC2\xAD" "four\xC2\xA0" "five";
  console_sanitize(out, sizeof(out), (const uint8_t *)controls, strlen(controls));
  CHECK(!strcmp(out, "one two threefour five"));
  char small[5];
  CHECK(console_sanitize(small, sizeof(small), (const uint8_t *)ascii, strlen(ascii)) == 4 && !strcmp(small, "Link"));
  const uint8_t nul[] = { 'a', 0, 'b' };
  CHECK(console_sanitize(out, sizeof(out), nul, sizeof(nul)) == 1); /* stops at a NUL */
  return 0;
}

static void add_line(console_log_t *log, console_kind_t kind, const char *text, uint64_t now)
{
  consolelog_add(log, kind, (const uint8_t *)text, strlen(text), now);
}

static int test_console_view_has_the_newest_lines_of_the_kinds_shown(void)
{
  static console_log_t log;
  static console_view_t view;
  memset(&log, 0, sizeof(log));
  console_settings_t s = console_defaults();
  consolelog_view(&log, &s, &view);
  CHECK(view.count == 0);
  add_line(&log, CONSOLE_RECEIVED, "", 1); /* empty: not kept */
  add_line(&log, CONSOLE_RECEIVED, "\x01\x02", 1);
  CHECK(log.count == 0);
  for (int i = 0; i < 40; i++) {
    char text[16];
    snprintf(text, sizeof(text), "line %d", i);
    add_line(&log, i % 2 ? CONSOLE_CHAT : CONSOLE_RECEIVED, text, 1000 + (uint64_t)i);
  }
  CHECK(log.count == 40);
  consolelog_view(&log, &s, &view);
  CHECK(view.count == CONSOLE_MAX_LINES);
  CHECK(!strcmp(view.lines[0].text, "line 28") && !strcmp(view.lines[CONSOLE_MAX_LINES - 1].text, "line 39"));
  CHECK(view.lines[CONSOLE_MAX_LINES - 1].kind == CONSOLE_CHAT && view.lines[0].time_ms == 1028);
  console_toggle_kind(&s, CONSOLE_CHAT);
  consolelog_view(&log, &s, &view);
  CHECK(view.count == CONSOLE_MAX_LINES && !strcmp(view.lines[0].text, "line 16")); /* only the even ones */
  CHECK(!strcmp(view.lines[CONSOLE_MAX_LINES - 1].text, "line 38"));
  for (int kind = 0; kind < CONSOLE_KIND_COUNT; kind++)
    if (console_kind_shown(&s, (console_kind_t)kind))
      console_toggle_kind(&s, (console_kind_t)kind);
  consolelog_view(&log, &s, &view);
  CHECK(view.count == 0);
  s = console_defaults();
  console_toggle_kind(&s, CONSOLE_RECEIVED);
  consolelog_view(&log, &s, &view);
  CHECK(view.count == CONSOLE_MAX_LINES && !strcmp(view.lines[0].text, "line 17")); /* the history keeps 32: 8-39 */
  return 0;
}

static int test_console_lines_fade_after_their_time(void)
{
  console_settings_t s = console_defaults(); /* 10 s */
  CHECK(console_line_alpha(&s, 1000, 1000) == 1 && console_line_alpha(&s, 1000, 10000) == 1);
  CHECK(console_line_alpha(&s, 1000, 10500) == 0.5f); /* its last second */
  CHECK(console_line_alpha(&s, 1000, 11000) == 0 && console_line_alpha(&s, 1000, 90000) == 0);
  CHECK(console_line_alpha(&s, 5000, 1000) == 1); /* a clock read before the line came */
  s.fade = 3; /* permanent */
  CHECK(console_line_alpha(&s, 1000, 1000000000) == 1);
  static console_view_t view;
  memset(&view, 0, sizeof(view));
  view.settings = console_defaults();
  view.shown = true;
  CHECK(!console_view_showing(&view, 0));
  view.count = 1;
  view.lines[0].time_ms = 1000;
  CHECK(console_view_showing(&view, 5000) && !console_view_showing(&view, 11000));
  memcpy(view.status, "x", 2);
  CHECK(console_view_showing(&view, 11000)); /* the status line stays */
  view.shown = false;
  CHECK(!console_view_showing(&view, 5000));
  return 0;
}

/* --- the mailbox ------------------------------------------------------------------------------- */

/* what the desktop client does: the sequence odd, the entries, the head and the status, the sequence even */
static void client_writes(mailbox_t *box, const char *const *texts, const uint8_t *kinds, int count, uint8_t status,
                          const char *status_text)
{
  box->sequence |= 1;
  for (int i = 0; i < count; i++) {
    mailbox_entry_t *entry = &box->entries[(box->head + (uint32_t)i) % MAILBOX_CAPACITY];
    memset(entry, 0, sizeof(*entry));
    entry->kind = kinds[i];
    entry->length = (uint8_t)strlen(texts[i]);
    memcpy(entry->text, texts[i], entry->length);
  }
  box->head += (uint32_t)count;
  box->status = status;
  snprintf(box->status_text, sizeof(box->status_text), "%s", status_text);
  box->sequence++;
}

static int test_mailbox_header_is_the_documented_one(void)
{
  static mailbox_t box;
  mailbox_blank(&box);
  CHECK(!memcmp(box.magic, "OOTRCON1", 8) && box.version == MAILBOX_VERSION && box.header_size == 0x80);
  CHECK(box.capacity == MAILBOX_CAPACITY && box.entry_size == MAILBOX_ENTRY_SIZE && sizeof(box) == 0x80 + 32 * 168);
  CHECK(box.module_version == MAILBOX_MODULE_VERSION && box.sequence == 0 && box.head == 0 && !box.seed_id[0]);
  CHECK(!memcmp(mailbox_shared()->magic, "OOTRCON1", 8) && mailbox_shared()->capacity == MAILBOX_CAPACITY);
  mailbox_set_seed(&box, "76069ecc4740cec6");
  CHECK(!strcmp(box.seed_id, "76069ecc4740cec6"));
  mailbox_set_seed(&box, "0123456789abcdef0123456789abcdef");
  CHECK(strlen(box.seed_id) == MAILBOX_SEED_ID_ROOM - 1);
  return 0;
}

static int test_mailbox_lines_are_taken_once_and_never_while_written(void)
{
  static mailbox_t box;
  static console_log_t log;
  mailbox_client_t client;
  memset(&log, 0, sizeof(log));
  memset(&client, 0, sizeof(client));
  mailbox_blank(&box);
  CHECK(!mailbox_poll(&box, &client, &log, 10)); /* nothing written yet */
  const char *texts[3] = { "You received Bow from Zelda", "You sent Hookshot to Zelda", "Zelda: hi" };
  const uint8_t kinds[3] = { 1, 2, 4 };
  client_writes(&box, texts, kinds, 3, MAILBOX_STATUS_CONNECTED, "archipelago.gg:38281 as Link");
  box.sequence |= 1; /* still writing */
  CHECK(!mailbox_poll(&box, &client, &log, 20) && log.count == 0 && box.read_head == 0);
  box.sequence++;
  CHECK(mailbox_poll(&box, &client, &log, 30) && log.count == 3 && box.read_head == 3);
  CHECK(!strcmp(log.lines[0].text, texts[0]) && log.lines[0].kind == CONSOLE_RECEIVED && log.lines[0].time_ms == 30);
  CHECK(log.lines[1].kind == CONSOLE_SENT && log.lines[2].kind == CONSOLE_CHAT);
  CHECK(client.status == MAILBOX_STATUS_CONNECTED && !strcmp(client.status_text, "archipelago.gg:38281 as Link"));
  CHECK(!mailbox_poll(&box, &client, &log, 40) && log.count == 3); /* the same sequence: nothing new */
  const char *more[3] = { "a hint", "Saria found her Fairy Bow", "a server notice" };
  const uint8_t other_kinds[3] = { 3, 6, 9 }; /* 9: a kind of a later client, shown as a server notice */
  client_writes(&box, more, other_kinds, 3, MAILBOX_STATUS_CONNECTED, "archipelago.gg:38281 as Link");
  CHECK(mailbox_poll(&box, &client, &log, 50) && log.count == 6);
  CHECK(log.lines[3].kind == CONSOLE_HINT && log.lines[4].kind == CONSOLE_OTHERS && log.lines[5].kind == CONSOLE_SERVER);
  client_writes(&box, more, other_kinds, 0, MAILBOX_STATUS_DISCONNECTED, "");
  CHECK(mailbox_poll(&box, &client, &log, 60) && log.count == 6 && client.status == MAILBOX_STATUS_DISCONNECTED);
  return 0;
}

static int test_mailbox_keeps_up_with_a_full_ring_and_a_client_that_starts_again(void)
{
  static mailbox_t box;
  static console_log_t log;
  mailbox_client_t client;
  memset(&log, 0, sizeof(log));
  memset(&client, 0, sizeof(client));
  mailbox_blank(&box);
  for (int i = 0; i < MAILBOX_CAPACITY + 8; i++) { /* more than the ring holds before the module reads */
    char text[16];
    const char *texts[1] = { text };
    const uint8_t kinds[1] = { 5 };
    snprintf(text, sizeof(text), "notice %d", i);
    client_writes(&box, texts, kinds, 1, MAILBOX_STATUS_CONNECTED, "");
  }
  CHECK(mailbox_poll(&box, &client, &log, 10));
  CHECK(log.count == MAILBOX_CAPACITY && !strcmp(log.lines[0].text, "notice 8")); /* the last 32 */
  CHECK(box.read_head == MAILBOX_CAPACITY + 8);
  mailbox_entry_t *entry = &box.entries[box.head % MAILBOX_CAPACITY];
  box.sequence |= 1;
  entry->kind = 1;
  entry->length = 200; /* longer than its room: only the room is read */
  memset(entry->text, 'x', sizeof(entry->text));
  box.head++;
  box.sequence++;
  CHECK(mailbox_poll(&box, &client, &log, 20) && strlen(log.lines[MAILBOX_CAPACITY % CONSOLE_HISTORY].text) == CONSOLE_TEXT_ROOM - 1);
  uint32_t before = log.count;
  box.sequence += 2;
  box.head = 1; /* a client that counts from the start again */
  CHECK(!mailbox_poll(&box, &client, &log, 30) && log.count == before && box.read_head == 1);
  return 0;
}

static int test_mailbox_status_line(void)
{
  static mailbox_t box;
  mailbox_client_t client;
  char line[CONSOLE_STATUS_ROOM];
  memset(&client, 0, sizeof(client));
  mailbox_blank(&box);
  client.heartbeat_ms = 1000; /* the seed file was read at 1 s */
  mailbox_status_line(&client, true, 5000, line, sizeof(line));
  CHECK(!strcmp(line, "")); /* not yet 10 s */
  mailbox_status_line(&client, true, 11000, line, sizeof(line));
  CHECK(!strcmp(line, "Archipelago client not running"));
  mailbox_status_line(&client, false, 11000, line, sizeof(line));
  CHECK(!strcmp(line, "")); /* a local seed: only once a client was heard */
  static console_log_t log;
  memset(&log, 0, sizeof(log));
  box.heartbeat = 7;
  const uint8_t kinds[1] = { 1 };
  const char *texts[1] = { "x" };
  client_writes(&box, texts, kinds, 0, MAILBOX_STATUS_CONNECTING, "archipelago.gg:38281 \xE2\x86\x92 Link");
  mailbox_poll(&box, &client, &log, 12000);
  CHECK(client.heard && client.heartbeat_ms == 12000);
  mailbox_status_line(&client, false, 12500, line, sizeof(line));
  CHECK(!strcmp(line, "Archipelago: connecting to archipelago.gg:38281 ? Link"));
  client_writes(&box, texts, kinds, 0, MAILBOX_STATUS_DISCONNECTED, "");
  mailbox_poll(&box, &client, &log, 13000);
  mailbox_status_line(&client, false, 13000, line, sizeof(line));
  CHECK(!strcmp(line, "Archipelago: not connected"));
  client_writes(&box, texts, kinds, 0, MAILBOX_STATUS_CONNECTED, "");
  mailbox_poll(&box, &client, &log, 14000);
  mailbox_status_line(&client, false, 14000, line, sizeof(line));
  CHECK(!strcmp(line, ""));
  mailbox_status_line(&client, false, 22000, line, sizeof(line));
  CHECK(!strcmp(line, "Archipelago client not running")); /* heard, then silent for 10 s */
  box.heartbeat++;
  mailbox_poll(&box, &client, &log, 23000);
  mailbox_status_line(&client, false, 23000, line, sizeof(line));
  CHECK(!strcmp(line, "")); /* back */
  mailbox_status_line(&client, false, 23000, line, 8);
  CHECK(strlen(line) <= 7);
  return 0;
}

/* --- where the console goes ------------------------------------------------------------------- */

static bool boxes_apart(box_t a, box_t b)
{
  return a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;
}

static bool box_on_screen(box_t b, float area_w)
{
  return b.x >= MARGIN_FP - 0.01f && b.y >= MARGIN_FP - 0.01f && b.x + b.w <= area_w - MARGIN_FP + 0.01f &&
         b.y + b.h <= PICTURE_HEIGHT_FP - MARGIN_FP + 0.01f;
}

static int test_the_console_sits_at_its_edge(void)
{
  float area_w = 640; /* 16:9 */
  box_t bottom = sizes_console_box(CONSOLE_BOTTOM, 6, area_w, 0), top = sizes_console_box(CONSOLE_TOP, 6, area_w, 0);
  CHECK(bottom.w == CONSOLE_WIDE_W_FP && bottom.x == (area_w - bottom.w) / 2);
  CHECK(bottom.h == 6 * CONSOLE_ROW_FP + 2 * CONSOLE_PAD_Y_FP && bottom.y + bottom.h == PICTURE_HEIGHT_FP - MARGIN_FP);
  CHECK(top.y == MARGIN_FP && top.x == bottom.x);
  box_t left = sizes_console_box(CONSOLE_LEFT, 12, area_w, 0), right = sizes_console_box(CONSOLE_RIGHT, 12, area_w, 0);
  CHECK(left.w == CONSOLE_TALL_W_FP && left.x == MARGIN_FP && right.x + right.w == area_w - MARGIN_FP);
  CHECK(left.y + left.h / 2 == PICTURE_HEIGHT_FP / 2 && right.y == left.y);
  box_t narrow = sizes_console_box(CONSOLE_BOTTOM, 4, 300, 0);
  CHECK(narrow.w == 300 - 2 * MARGIN_FP);
  return 0;
}

/* every position and number of lines, next to every postcard (corner, size, with and without keys), at 16:9 and
 * 4:3: on the screen and clear of the card */
static int test_the_console_keeps_clear_of_the_postcard(void)
{
  const float widths[] = { 640, 480 };
  const uint32_t key_counts[] = { 0, 8 };
  const int lines[] = { 4, 6, 8, 12 };
  for (unsigned w = 0; w < sizeof(widths) / sizeof(*widths); w++)
    for (int corner = 0; corner < POSTCARD_POSITION_COUNT; corner++)
      for (int size = 0; size < POSTCARD_SIZE_COUNT; size++)
        for (unsigned k = 0; k < sizeof(key_counts) / sizeof(*key_counts); k++) {
          postcard_settings_t postcard = { true, (uint8_t)corner, (uint8_t)size, 3 };
          box_t card = sizes_card_box(&postcard, key_counts[k], widths[w]);
          CHECK(box_on_screen(card, widths[w]));
          for (int position = 0; position < CONSOLE_POSITION_COUNT; position++)
            for (unsigned l = 0; l < sizeof(lines) / sizeof(*lines); l++) {
              box_t console = sizes_console_box((console_position_t)position, lines[l], widths[w], &card);
              if (!boxes_apart(console, card) || !box_on_screen(console, widths[w])) {
                snprintf(failure, sizeof(failure), "width %g, card %d/%d/%u, console %d with %d lines", widths[w],
                         corner, size, key_counts[k], position, lines[l]);
                return 1;
              }
            }
        }
  postcard_settings_t large = { true, POSTCARD_BOTTOM_RIGHT, POSTCARD_LARGE, 3 };
  box_t card = sizes_card_box(&large, 8, 640);
  box_t moved = sizes_console_box(CONSOLE_BOTTOM, 6, 640, &card);
  CHECK(moved.w == CONSOLE_WIDE_W_FP && moved.y + moved.h == PICTURE_HEIGHT_FP - MARGIN_FP); /* moved sideways only */
  card = sizes_card_box(&large, 8, 480);
  moved = sizes_console_box(CONSOLE_BOTTOM, 6, 480, &card);
  CHECK(moved.y + moved.h <= card.y); /* no room beside it at 4:3: above it */
  postcard_settings_t small = { true, POSTCARD_BOTTOM_LEFT, POSTCARD_SMALL, 3 };
  card = sizes_card_box(&small, 8, 640);
  box_t untouched = sizes_console_box(CONSOLE_BOTTOM, 6, 640, &card), alone = sizes_console_box(CONSOLE_BOTTOM, 6, 640, 0);
  CHECK(!memcmp(&untouched, &alone, sizeof(alone))); /* the small card leaves it where it is */
  return 0;
}

/* --- grid and text ---------------------------------------------------------------------------- */

static int test_grid_names_and_labels(void)
{
  CHECK(grid_index_of("Bow") >= 0 && grid_index_of("Light Medallion") == ITEM_CELLS - 1);
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
  const char *temples[] = { "Forest Temple", "Fire Temple", "Water Temple", "Shadow Temple", "Spirit Temple" };
  for (unsigned i = 0; i < sizeof(temples) / sizeof(*temples); i++) {
    const char *medallion = grid_dungeon_medallion(temples[i]);
    CHECK(medallion && grid_index_of(medallion) >= 0 && !strncmp(medallion, temples[i], strlen(medallion) - 9));
  }
  CHECK(!strcmp(grid_dungeon_medallion("Shadow Temple"), "Shadow Medallion"));
  CHECK(!grid_dungeon_medallion("Bottom of the Well") && !grid_dungeon_medallion("Gerudo Training Ground"));
  CHECK(!grid_dungeon_medallion("Ganon's Castle") && !grid_dungeon_medallion("Deku Tree"));
  return 0;
}

/* the songs, as the quest status screen lists them: the warp songs, then the others */
static int test_the_songs_follow_the_items_in_two_rows_of_six(void)
{
  const char *songs[SONG_CELLS] = { "Minuet of Forest", "Bolero of Fire", "Serenade of Water", "Requiem of Spirit",
                                    "Nocturne of Shadow", "Prelude of Light", "Zeldas Lullaby", "Eponas Song",
                                    "Sarias Song", "Suns Song", "Song of Time", "Song of Storms" };
  CHECK(SONG_ROWS * SONG_COLUMNS == SONG_CELLS && SONG_CELLS == 12 && GRID_CELLS == ITEM_CELLS + SONG_CELLS);
  for (int i = 0; i < SONG_CELLS; i++) {
    CHECK(!strcmp(grid_cell(ITEM_CELLS + i)->item, songs[i]) && grid_index_of(songs[i]) == ITEM_CELLS + i);
    CHECK(strlen(grid_cell(ITEM_CELLS + i)->abbr) == 2 && grid_cell(ITEM_CELLS + i)->levels == 1);
  }
  return 0;
}

/* --- sizes ------------------------------------------------------------------------------------ */

enum { REAL_SEED_REGIONS = 35, DUNGEONS_WITH_KEYS = 8 };

/* a font pixel is the picture's height over 360, so what fits at one resolution fits at all of the same shape */
static const struct { int width, height; } screens[] = { { 1280, 720 }, { 1920, 1080 } };

static panel_shape_t regions_shape(int status_lines)
{
  return (panel_shape_t){ .status_lines = status_lines, .tracking = true, .has_keys = true, .has_summary = true,
                          .region_rows = browse_region_rows(REAL_SEED_REGIONS) };
}

static int test_the_panel_fits_the_screen_with_the_songs(void)
{
  CHECK(sizes_panel_height(&(panel_shape_t){ 0 }) == 48); /* the title alone */
  panel_shape_t plain = regions_shape(0), warned = regions_shape(MAX_STATUS_LINES);
  CHECK(sizes_panel_height(&plain) == 326 && sizes_panel_height(&warned) == 350);
  panel_shape_t list = { .tracking = true, .list = true };
  panel_shape_t warned_list = { .tracking = true, .list = true, .status_lines = MAX_STATUS_LINES };
  CHECK(sizes_panel_height(&list) == 300 && sizes_panel_height(&warned_list) == 324); /* with the check's two rows */
  panel_shape_t settings = { .tracking = true, .status_lines = MAX_STATUS_LINES, .settings_rows = CONSOLE_SETTING_COUNT };
  const panel_shape_t *shapes[] = { &plain, &warned, &list, &warned_list, &settings };
  for (unsigned s = 0; s < sizeof(screens) / sizeof(*screens); s++) {
    float fp = (float)screens[s].height / PICTURE_HEIGHT_FP;
    for (unsigned i = 0; i < sizeof(shapes) / sizeof(*shapes); i++) {
      CHECK((MARGIN_FP + sizes_panel_height(shapes[i])) * fp <= (float)screens[s].height);
      CHECK((2 * MARGIN_FP + sizes_panel_width(shapes[i])) * fp <= (float)screens[s].width);
    }
  }
  return 0;
}

static int test_the_postcard_fits_the_screen_at_each_size(void)
{
  CHECK(sizes_card_width() == 208 && sizes_card_height(DUNGEONS_WITH_KEYS) == 176 && sizes_card_height(0) == 131);
  CHECK(sizes_card_height(0) == 2 * CARD_PAD_FP + CELLS_BLOCK_FP + SECTION_GAP_FP + COUNTER_ROW_FP); /* the count under the songs */
  CHECK(sizes_key_rows(DUNGEONS_WITH_KEYS, CARD_KEY_COLUMNS) == 3 && sizes_key_rows(0, CARD_KEY_COLUMNS) == 0);
  const float widths_1080[POSTCARD_SIZE_COUNT] = { 343, 468, 624 }; /* about 340, 470 and 620 pixels */
  for (unsigned s = 0; s < sizeof(screens) / sizeof(*screens); s++) {
    float picture_fp = (float)screens[s].height / PICTURE_HEIGHT_FP;
    for (int size = 0; size < POSTCARD_SIZE_COUNT; size++) {
      postcard_settings_t settings = postcard_defaults();
      settings.size = (uint8_t)size;
      float fp = picture_fp * postcard_scale(&settings);
      float width = sizes_card_width() * fp, height = sizes_card_height(DUNGEONS_WITH_KEYS) * fp;
      float margin = MARGIN_FP * picture_fp;
      CHECK(width + 2 * margin <= (float)screens[s].width && height + 2 * margin <= (float)screens[s].height);
      if (screens[s].height == 1080)
        CHECK(width > widths_1080[size] - 1 && width < widths_1080[size] + 1);
    }
  }
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
    { "file size", 8, 100, 4 },           { "count 0", 12, 0, 4 },              { "one icon too many", 12, ICONFILE_MAX + 1, 4 },
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

/* a file of ICONFILE_MAX (or one more) 4 x 4 pictures, one block each: the atlas's every slot */
static int test_icons_index_fills_the_atlas(void)
{
  enum { MOST = ICONFILE_MAX + 1, DATA_AT = ICONFILE_HEADER + MOST * ICONFILE_ENTRY };
  static uint8_t file[DATA_AT + MOST * 16];
  for (int count = ICONFILE_MAX; count <= MOST; count++) {
    uint32_t data_at = ICONFILE_HEADER + count * ICONFILE_ENTRY, size = data_at + count * 16;
    memset(file, 0, sizeof(file));
    memcpy(file, "RTIC", 4);
    put16(file + 4, ICONFILE_VERSION);
    put16(file + 6, ICONFILE_HEADER);
    put32(file + 8, size);
    put32(file + 12, (uint32_t)count);
    put32(file + 16, ICONFILE_HEADER);
    put32(file + 20, ICONFILE_ENTRY);
    put32(file + 24, data_at);
    for (int i = 0; i < count; i++) {
      uint8_t *e = file + ICONFILE_HEADER + i * ICONFILE_ENTRY;
      snprintf((char *)e, ICONFILE_NAME, "Icon %d", i);
      put32(e + 32, 4);
      put32(e + 36, 4);
      put32(e + 40, data_at + (uint32_t)i * 16);
      put32(e + 44, 16);
      e[48] = 4;
      e[56] = 2, e[57] = 3, e[58] = 4, e[59] = 5;
      put32(e + 60, 0x2D06);
    }
    icon_index_t index;
    const char *why = "";
    bool read = iconfile_parse(&index, file, size, size, &why);
    CHECK(read == (count <= ICONFILE_MAX));
    char last[ICONFILE_NAME];
    snprintf(last, sizeof(last), "Icon %d", ICONFILE_MAX - 1);
    if (read)
      CHECK(index.count == ICONFILE_MAX && !strcmp(index.entries[ICONFILE_MAX - 1].name, last));
  }
  return 0;
}

/* --- the check shown in the world ------------------------------------------------------------------ */

static bool near_value(float a, float b)
{
  return a - b < 1e-4f && b - a < 1e-4f;
}

static int test_a_checks_place_is_here_elsewhere_or_nowhere(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(locate_check_of(&trk, 0, 1) == 1 && locate_check_of(&trk, 1, 0) == 2);
  CHECK(locate_check_of(&trk, 0, 2) == LOCATE_NONE && locate_check_of(&trk, 2, 0) == LOCATE_NONE);
  locate_t where = locate_find(&trk, 0, "KokiriForest_Child");
  CHECK(where.state == LOCATE_HERE && where.point[0] == 10.5f && where.point[1] == 0.25f && where.point[2] == -2.75f);
  where = locate_find(&trk, 1, "KokiriForest_Adult"); /* its second place */
  CHECK(where.state == LOCATE_HERE && where.point[2] == 30);
  where = locate_find(&trk, 1, "Market");
  CHECK(where.state == LOCATE_ELSEWHERE && !strcmp(where.label, "Kokiri Forest (child)") && where.more_maps == 1);
  where = locate_find(&trk, 0, 0); /* the game's map isn't known yet */
  CHECK(where.state == LOCATE_MAP_UNKNOWN && !strcmp(where.label, "Kokiri Forest (child)") && where.more_maps == 0);
  CHECK(locate_find(&trk, 2, "KokiriForest_Child").state == LOCATE_NOWHERE);
  CHECK(locate_find(&trk, LOCATE_NONE, "KokiriForest_Child").state == LOCATE_OFF);
  CHECK(locate_find(&trk, 3, "KokiriForest_Child").state == LOCATE_OFF);
  blob = synthetic_of_version(3);
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  CHECK(locate_find(&trk, 0, "KokiriForest_Child").state == LOCATE_OLD_FILE);
  return 0;
}

static int test_y_shows_a_check_and_puts_it_away(void)
{
  CHECK(locate_toggle(LOCATE_NONE, 1) == 1);
  CHECK(locate_toggle(1, 1) == LOCATE_NONE);
  CHECK(locate_toggle(1, 2) == 2); /* another check: it is shown instead */
  return 0;
}

static int test_what_is_said_of_a_checks_place(void)
{
  char text[LOCATE_TEXT_ROOM];
  const float link[3] = { 0, 0, 0 };
  locate_t here = { .state = LOCATE_HERE, .point = { 3, 4, 0 } };
  locate_describe(&here, link, text, sizeof(text));
  CHECK(!strcmp(text, "5 m away, 4 m up"));
  locate_panel_line(true, &here, link, text, sizeof(text));
  CHECK(!strcmp(text, "Shown in the world: 5 m away, 4 m up"));
  locate_band_line(here.point, link, VIEW_LEFT, text, sizeof(text));
  CHECK(!strcmp(text, "5 m away, 4 m up, turn left"));
  locate_band_line(here.point, link, VIEW_ON_PICTURE, text, sizeof(text));
  CHECK(!strcmp(text, "5 m away, 4 m up"));
  locate_band_line(here.point, 0, VIEW_BEHIND, text, sizeof(text));
  CHECK(!strcmp(text, "In this map, behind you"));
  locate_describe(&here, link, text, 8);
  CHECK(!strcmp(text, "5 m awa")); /* cut to the room */
  here.point[1] = -4;
  locate_describe(&here, link, text, sizeof(text));
  CHECK(!strcmp(text, "5 m away, 4 m down"));
  here.point[0] = 0.2f, here.point[1] = 1, here.point[2] = 0;
  locate_describe(&here, link, text, sizeof(text));
  CHECK(!strcmp(text, "1 m away")); /* less than 2 m up isn't said */
  here.point[1] = 0.1f;
  locate_describe(&here, link, text, sizeof(text));
  CHECK(!strcmp(text, "Right here"));
  locate_describe(&here, 0, text, sizeof(text));
  CHECK(!strcmp(text, "In this map"));
  here.point[0] = 2e6f;
  locate_describe(&here, link, text, sizeof(text));
  CHECK(!strcmp(text, "1000000 m away"));
  locate_t elsewhere = { .state = LOCATE_ELSEWHERE, .label = "Kokiri Forest (child)", .more_maps = 1 };
  locate_describe(&elsewhere, link, text, sizeof(text));
  CHECK(!strcmp(text, "In Kokiri Forest (child) and 1 other map"));
  locate_panel_line(false, &elsewhere, link, text, sizeof(text));
  CHECK(!strcmp(text, "Y: show in the world     In Kokiri Forest (child) and 1 other map"));
  elsewhere.more_maps = 2;
  locate_describe(&elsewhere, link, text, sizeof(text));
  CHECK(!strcmp(text, "In Kokiri Forest (child) and 2 other maps"));
  elsewhere.more_maps = 0;
  locate_describe(&elsewhere, link, text, sizeof(text));
  CHECK(!strcmp(text, "In Kokiri Forest (child)"));
  locate_t nowhere = { .state = LOCATE_NOWHERE }, old = { .state = LOCATE_OLD_FILE }, off = { .state = LOCATE_OFF };
  locate_panel_line(false, &nowhere, link, text, sizeof(text));
  CHECK(!strcmp(text, "No place in the world for this check")); /* Y does nothing there */
  locate_panel_line(false, &old, link, text, sizeof(text));
  CHECK(!strcmp(text, "This seed's file is too old to tick checks or show them: update its tracker with the game "
                      "file"));
  locate_panel_line(false, &off, link, text, sizeof(text));
  CHECK(!strcmp(text, ""));
  return 0;
}

static int test_the_camera_projects_as_the_games(void)
{
  view_cam_t cam;
  const float pos[3] = { 0, 0, 0 }, look[3] = { 0, 0, 1 };
  CHECK(view_from(&cam, pos, look, 0.5f, 2.0f, 0));
  CHECK(cam.near == VIEW_DEFAULT_NEAR && cam.tan_x == 1.0f && cam.tan_y == 0.5f);
  /* sloperinaGZ's basis: right = (-forward.z, 0, forward.x), so looking along +z the world's +x is on the left */
  CHECK(cam.right[0] == -1 && cam.right[2] == 0 && cam.up[1] == 1);
  float v[3], sx, sy;
  const float ahead[3] = { 0, 0, 10 }, corner[3] = { -10, -5, 10 };
  view_point(&cam, ahead, v);
  view_screen(&cam, v, &sx, &sy);
  CHECK(near_value(sx, 0.5f) && near_value(sy, 0.5f));
  view_point(&cam, corner, v); /* the picture's right and bottom edges */
  view_screen(&cam, v, &sx, &sy);
  CHECK(near_value(sx, 1) && near_value(sy, 1));
  const float left[3] = { 30, 0, 10 }, right[3] = { -30, 0, 10 }, above[3] = { 0, 30, 10 }, below[3] = { 0, -30, 10 };
  const float behind[3] = { 0, 0, -10 };
  CHECK(view_side(&cam, ahead) == VIEW_ON_PICTURE && view_side(&cam, left) == VIEW_LEFT);
  CHECK(view_side(&cam, right) == VIEW_RIGHT && view_side(&cam, above) == VIEW_ABOVE);
  CHECK(view_side(&cam, below) == VIEW_BELOW && view_side(&cam, behind) == VIEW_BEHIND);
  float s[4];
  const float low[3] = { 0, -100, 10 }, high[3] = { 0, 100, 10 }; /* a beam: cut to the picture's height */
  CHECK(view_segment(&cam, low, high, s));
  CHECK(near_value(s[0], 0.5f) && near_value(s[1], 1) && near_value(s[2], 0.5f) && near_value(s[3], 0));
  const float back[3] = { 0, 1, -10 }, front[3] = { 0, 1, 10 }; /* cut at the near plane, then at the top */
  CHECK(view_segment(&cam, back, front, s));
  CHECK(near_value(s[0], 0.5f) && near_value(s[1], 0) && near_value(s[2], 0.5f) && near_value(s[3], 0.4f));
  const float further_back[3] = { 0, 1, -20 }, left_up[3] = { 30, 1, 10 };
  CHECK(!view_segment(&cam, behind, further_back, s)); /* all of it behind */
  CHECK(!view_segment(&cam, left, left_up, s));         /* all of it to the left */
  return 0;
}

static int test_a_camera_that_isnt_one_is_refused(void)
{
  view_cam_t cam;
  const float pos[3] = { 1, 2, 3 }, up[3] = { 1, 5, 3 }, look[3] = { 1, 2, 4 };
  CHECK(!view_from(&cam, pos, pos, 0.5f, 1.5f, 0.1f)); /* looking at itself */
  CHECK(!view_from(&cam, pos, up, 0.5f, 1.5f, 0.1f));  /* straight up: no right */
  CHECK(!view_from(&cam, pos, look, 0.01f, 1.5f, 0.1f));
  CHECK(!view_from(&cam, pos, look, 0.5f, 10, 0.1f));
  CHECK(view_from(&cam, pos, look, 0.5f, 1.5f, 0.5f) && cam.near == 0.5f);
  CHECK(view_from(&cam, pos, look, 0.5f, 1.5f, 50) && cam.near == VIEW_DEFAULT_NEAR);
  CHECK(view_root(16) == 4 && near_value(view_root(2), 1.41421356f) && view_root(0) == 0 && view_root(-1) == 0);
  return 0;
}

/* --- the checks ticked by hand ----------------------------------------------------------------- */

static int test_a_ticks_a_check_and_a_again_unticks_it(void)
{
  blob_t blob = synthetic(), old = synthetic_of_version(3);
  trk_t trk, old_trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why) && trk_parse(&old_trk, old.bytes, old.size, &why));
  marks_t marks;
  marks_init(&marks, &trk);
  CHECK(marks.state == MARKS_ON && marks.count == 0 && !marks_has(&marks, 1) && marks_can_tick(&marks, &trk, 1));
  size_t empty = marks.length;
  CHECK(marks_toggle(&marks, &trk, 1) == MARK_TICKED && marks_has(&marks, 1) && marks.count == 1);
  CHECK(marks.length == empty + strlen("check ") + strlen(check_idents[1]) + 1);
  CHECK(marks_toggle(&marks, &trk, 1) == MARK_UNTICKED && !marks_has(&marks, 1) && marks.count == 0);
  CHECK(marks.length == empty);
  CHECK(marks_toggle(&marks, &trk, 3) == MARK_REFUSED && marks_toggle(&marks, &trk, UINT32_MAX) == MARK_REFUSED);
  CHECK(marks.count == 0 && !marks_has(&marks, 3));
  char text[64];
  marks_init(&marks, &old_trk); /* version 3: no ids, so nothing can be ticked */
  CHECK(marks.state == MARKS_OLD_FILE && !marks_can_tick(&marks, &old_trk, 0));
  CHECK(marks_toggle(&marks, &old_trk, 0) == MARK_REFUSED && marks.count == 0);
  CHECK(marks_format(&marks, &old_trk, text, sizeof(text)) == 0 && !marks_parse(&marks, &old_trk, text, 0));
  return 0;
}

static int test_ticks_count_as_found_but_never_twice(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  fake_flags_t fake = fake_with(GD_UNKNOWN);
  set_bool(&fake, BOOL_A, GD_TRUE);  /* Mido's chest collected */
  set_bool(&fake, BOOL_B, GD_FALSE); /* the map's chest missing; the sword's chest (a Bool64) unknown: a `?` */
  marks_t marks;
  marks_init(&marks, &trk);
  CHECK(marks_toggle(&marks, &trk, 0) == MARK_TICKED); /* collected already: counted once */
  CHECK(marks_toggle(&marks, &trk, 1) == MARK_TICKED); /* a `?` can be ticked */
  tracker_state_t state;
  tracker_compute(&trk, &fake.source, &state);
  CHECK(state.collected == 1 && state.unreadable == 1);
  tracker_count_marks(&trk, &fake.source, &marks, &state);
  CHECK(state.regions[0].collected == 2 && state.regions[0].trackable == 2);
  CHECK(state.regions[1].collected == 0 && state.collected == 2 && state.trackable == 3 && state.unreadable == 0);
  CHECK(marks_toggle(&marks, &trk, 2) == MARK_TICKED);
  tracker_compute(&trk, &fake.source, &state);
  tracker_count_marks(&trk, &fake.source, &marks, &state);
  CHECK(state.regions[1].collected == 1 && state.collected == 3 && state.trackable == 3);
  check_row_t rows[4];
  uint32_t count = tracker_check_rows(&trk, &fake.source, 0, 0, rows, 4);
  CHECK(count == 2 && !rows[0].marked && !rows[1].marked); /* the save's state alone */
  tracker_mark_rows(&trk, &marks, 0, 0, rows, count);
  CHECK(rows[0].marked && rows[0].flag == GD_TRUE && rows[1].marked && rows[1].flag == GD_UNKNOWN);
  count = tracker_check_rows(&trk, &fake.source, 0, 1, rows, 4); /* from the second */
  tracker_mark_rows(&trk, &marks, 0, 1, rows, count);
  CHECK(count == 1 && rows[0].number == 2 && rows[0].marked);
  CHECK(marks_toggle(&marks, &trk, 1) == MARK_UNTICKED);
  tracker_mark_rows(&trk, &marks, 0, 1, rows, count);
  CHECK(!rows[0].marked);
  CHECK(tracker_check_flag(&trk, &fake.source, 0) == GD_TRUE && tracker_check_flag(&trk, &fake.source, 1) == GD_UNKNOWN);
  CHECK(tracker_check_flag(&trk, &fake.source, 2) == GD_FALSE && tracker_check_flag(&trk, &fake.source, 3) == GD_UNKNOWN);
  return 0;
}

static int test_the_ticks_file_reads_back_what_it_wrote(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  marks_t marks, read;
  marks_init(&marks, &trk);
  static char text[MARKS_FILE_ROOM], again[MARKS_FILE_ROOM];
  size_t length = marks_format(&marks, &trk, text, sizeof(text));
  const char *empty = "ootrTracker marks 1\nseed abc123\nend 0 ";
  CHECK(length == marks.length && length == strlen(empty) + 9 && !memcmp(text, empty, strlen(empty)));
  marks_init(&read, &trk);
  CHECK(marks_parse(&read, &trk, text, length) && read.count == 0);
  CHECK(marks_toggle(&marks, &trk, 2) == MARK_TICKED && marks_toggle(&marks, &trk, 1) == MARK_TICKED);
  length = marks_format(&marks, &trk, text, sizeof(text));
  const char *head = "ootrTracker marks 1\nseed abc123\ncheck KokiriForest#222\ncheck npc#Deku Tree Map Chest\nend 2 ";
  CHECK(length == marks.length && length == strlen(head) + 9 && !memcmp(text, head, strlen(head)));
  CHECK(text[length - 1] == '\n');
  marks_init(&read, &trk);
  CHECK(marks_parse(&read, &trk, text, length));
  CHECK(read.count == 2 && marks_has(&read, 1) && marks_has(&read, 2) && !marks_has(&read, 0) && read.length == length);
  CHECK(marks_format(&read, &trk, again, sizeof(again)) == length && !memcmp(again, text, length));
  CHECK(marks_format(&marks, &trk, again, length - 1) == 0); /* no room for it */
  char name[32];
  CHECK(marks_file_name(&trk, false, name, sizeof(name)) && !strcmp(name, "marks-abc123.cfg"));
  CHECK(marks_file_name(&trk, true, name, sizeof(name)) && !strcmp(name, "marks-abc123.new"));
  CHECK(!marks_file_name(&trk, false, name, 10));
  return 0;
}

/* FNV-1a, as marks.c sums the file */
static uint32_t fnv1a(const char *text, size_t size)
{
  uint32_t sum = 2166136261u;
  for (size_t i = 0; i < size; i++)
    sum = (sum ^ (uint8_t)text[i]) * 16777619u;
  return sum;
}

/* `body` with an end line saying `count` and its sum, as marks_format ends a file */
static size_t sealed(char *out, size_t room, const char *body, uint32_t count)
{
  size_t at = strlen(body);
  memcpy(out, body, at);
  return at + (size_t)snprintf(out + at, room - at, "end %u %08x\n", (unsigned)count, (unsigned)fnv1a(body, at));
}

static int test_a_damaged_or_other_seeds_ticks_file_is_left_out(void)
{
  blob_t blob = synthetic();
  trk_t trk;
  const char *why = "";
  CHECK(trk_parse(&trk, blob.bytes, blob.size, &why));
  marks_t marks, read;
  marks_init(&marks, &trk);
  CHECK(marks_toggle(&marks, &trk, 0) == MARK_TICKED);
  static char good[512], text[512];
  size_t length = marks_format(&marks, &trk, good, sizeof(good));
  const char *body = "ootrTracker marks 1\nseed abc123\ncheck KokiriForest#111\n";
  CHECK(sealed(text, sizeof(text), body, 1) == length && !memcmp(text, good, length)); /* the sum is FNV-1a */
  for (size_t cut = 0; cut < length; cut++) { /* cut short anywhere: refused, and what was there stays */
    marks_init(&read, &trk);
    CHECK(marks_toggle(&read, &trk, 2) == MARK_TICKED);
    CHECK(!marks_parse(&read, &trk, good, cut) && read.count == 1 && marks_has(&read, 2) && !marks_has(&read, 0));
  }
  static const struct { const char *body; uint32_t count; } bad[] = {
    { "ootrTracker marks 1\nseed abc124\ncheck KokiriForest#111\n", 1 }, /* another seed's */
    { "ootrTracker marks 2\nseed abc123\ncheck KokiriForest#111\n", 1 }, /* another version */
    { "ootrTracker marks 1\nseed abc123\ncheck KokiriForest#111\n", 2 }, /* a count other than its lines */
    { "ootrTracker marks 1\nseed abc123\nsomething else\n", 0 },         /* a line of another kind */
    { "ootrTracker marks 1\nseed abc123\ncheck \n", 1 },                 /* an empty id */
    { "ootrTracker marks 1\ncheck KokiriForest#111\n", 1 },              /* no seed line */
  };
  for (size_t i = 0; i < sizeof(bad) / sizeof(*bad); i++) {
    size_t n = sealed(text, sizeof(text), bad[i].body, bad[i].count);
    marks_init(&read, &trk);
    CHECK(!marks_parse(&read, &trk, text, n) && read.count == 0);
  }
  memcpy(text, good, length);
  text[strlen("ootrTracker marks 1\nseed abc123\ncheck Kokiri")] ^= 1; /* a byte changed: the sum says so */
  CHECK(!marks_parse(&read, &trk, text, length));
  memcpy(text, good, length);
  text[length] = '\n'; /* something after the end */
  CHECK(!marks_parse(&read, &trk, text, length + 1));
  size_t n = sealed(text, sizeof(text),
                    "ootrTracker marks 1\nseed abc123\ncheck Gone#1\ncheck npc#Deku Tree Map Chest\n"
                    "check npc#Deku Tree Map Chest\n", 3);
  marks_init(&read, &trk); /* an id this seed file doesn't have is left out, and a second line of one */
  CHECK(marks_parse(&read, &trk, text, n) && read.count == 1 && marks_has(&read, 2));
  CHECK(read.length == marks_format(&read, &trk, good, sizeof(good)));
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
  { "parse_reads_the_checks_ids_and_places", test_parse_reads_the_checks_ids_and_places, 0 },
  { "older_files_have_no_ids_or_places", test_older_files_have_no_ids_or_places, 0 },
  { "parse_refuses_damaged_ids_and_places", test_parse_refuses_damaged_ids_and_places, 0 },
  { "parse_reads_the_archipelago_flag_and_older_versions_as_local",
    test_parse_reads_the_archipelago_flag_and_older_versions_as_local, 0 },
  { "parse_refuses_a_name_outside_the_strings", test_parse_refuses_a_name_outside_the_strings, 0 },
  { "the_real_seed_file", 0, test_the_real_seed_file },
  { "state_of_a_save", test_state_of_a_save, 0 },
  { "the_skulltula_count", test_the_skulltula_count, 0 },
  { "the_bottle_cell_counts_its_slots", test_the_bottle_cell_counts_its_slots, 0 },
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
  { "the_games_strings_are_read_as_it_reads_them", test_the_games_strings_are_read_as_it_reads_them, 0 },
  { "the_games_pause_is_its_bool_or_its_requests", test_the_games_pause_is_its_bool_or_its_requests, 0 },
  { "the_combo_toggles_on_its_press_only", test_the_combo_toggles_on_its_press_only, 0 },
  { "the_panel_reopens_where_it_was_closed", test_the_panel_reopens_where_it_was_closed, 0 },
  { "a_and_b_and_directions_only_with_the_panel_open", test_a_and_b_and_directions_only_with_the_panel_open, 0 },
  { "a_held_direction_repeats", test_a_held_direction_repeats, 0 },
  { "what_the_game_does_not_see", test_what_the_game_does_not_see, 0 },
  { "buttons_held_at_closing_stay_hidden_until_let_go", test_buttons_held_at_closing_stay_hidden_until_let_go, 0 },
  { "y_shows_in_the_world_only_with_the_panel_open", test_y_shows_in_the_world_only_with_the_panel_open, 0 },
  { "the_highlight_moves_over_the_regions_columns", test_the_highlight_moves_over_the_regions_columns, 0 },
  { "a_list_opens_scrolls_and_goes_back", test_a_list_opens_scrolls_and_goes_back, 0 },
  { "the_settings_entry_opens_the_postcard_and_the_console", test_the_settings_entry_opens_the_postcard_and_the_console, 0 },
  { "postcard_defaults_and_values", test_postcard_defaults_and_values, 0 },
  { "postcard_settings_cycle_both_ways", test_postcard_settings_cycle_both_ways, 0 },
  { "the_postcard_sits_in_its_corner", test_the_postcard_sits_in_its_corner, 0 },
  { "postcard_file_text", test_postcard_file_text, 0 },
  { "postcard_file_tolerates_a_bad_file", test_postcard_file_tolerates_a_bad_file, 0 },
  { "the_icons_state_is_the_full_states_cells_and_keys", test_the_icons_state_is_the_full_states_cells_and_keys, 0 },
  { "console_defaults_and_values", test_console_defaults_and_values, 0 },
  { "console_settings_cycle_and_each_kind_of_seed_has_its_own_switch",
    test_console_settings_cycle_and_each_kind_of_seed_has_its_own_switch, 0 },
  { "the_pause_hides_the_postcard_and_the_console", test_the_pause_hides_the_postcard_and_the_console, 0 },
  { "the_panel_stays_usable_while_paused", test_the_panel_stays_usable_while_paused, 0 },
  { "console_file_text", test_console_file_text, 0 },
  { "console_file_without_its_version_or_damaged_leaves_the_defaults",
    test_console_file_without_its_version_or_damaged_leaves_the_defaults, 0 },
  { "console_file_of_0_5_0_shows_other_players_items", test_console_file_of_0_5_0_shows_other_players_items, 0 },
  { "console_text_is_what_the_font_draws", test_console_text_is_what_the_font_draws, 0 },
  { "console_view_has_the_newest_lines_of_the_kinds_shown", test_console_view_has_the_newest_lines_of_the_kinds_shown, 0 },
  { "console_lines_fade_after_their_time", test_console_lines_fade_after_their_time, 0 },
  { "mailbox_header_is_the_documented_one", test_mailbox_header_is_the_documented_one, 0 },
  { "mailbox_lines_are_taken_once_and_never_while_written", test_mailbox_lines_are_taken_once_and_never_while_written, 0 },
  { "mailbox_keeps_up_with_a_full_ring_and_a_client_that_starts_again",
    test_mailbox_keeps_up_with_a_full_ring_and_a_client_that_starts_again, 0 },
  { "mailbox_status_line", test_mailbox_status_line, 0 },
  { "the_console_sits_at_its_edge", test_the_console_sits_at_its_edge, 0 },
  { "the_console_keeps_clear_of_the_postcard", test_the_console_keeps_clear_of_the_postcard, 0 },
  { "grid_names_and_labels", test_grid_names_and_labels, 0 },
  { "the_songs_follow_the_items_in_two_rows_of_six", test_the_songs_follow_the_items_in_two_rows_of_six, 0 },
  { "the_panel_fits_the_screen_with_the_songs", test_the_panel_fits_the_screen_with_the_songs, 0 },
  { "the_postcard_fits_the_screen_at_each_size", test_the_postcard_fits_the_screen_at_each_size, 0 },
  { "text_helpers", test_text_helpers, 0 },
  { "icons_index_reads_every_entry", test_icons_index_reads_every_entry, 0 },
  { "icons_index_refuses_damage", test_icons_index_refuses_damage, 0 },
  { "icons_index_fills_the_atlas", test_icons_index_fills_the_atlas, 0 },
  { "a_checks_place_is_here_elsewhere_or_nowhere", test_a_checks_place_is_here_elsewhere_or_nowhere, 0 },
  { "y_shows_a_check_and_puts_it_away", test_y_shows_a_check_and_puts_it_away, 0 },
  { "what_is_said_of_a_checks_place", test_what_is_said_of_a_checks_place, 0 },
  { "a_ticks_a_check_and_a_again_unticks_it", test_a_ticks_a_check_and_a_again_unticks_it, 0 },
  { "ticks_count_as_found_but_never_twice", test_ticks_count_as_found_but_never_twice, 0 },
  { "the_ticks_file_reads_back_what_it_wrote", test_the_ticks_file_reads_back_what_it_wrote, 0 },
  { "a_damaged_or_other_seeds_ticks_file_is_left_out", test_a_damaged_or_other_seeds_ticks_file_is_left_out, 0 },
  { "the_camera_projects_as_the_games", test_the_camera_projects_as_the_games, 0 },
  { "a_camera_that_isnt_one_is_refused", test_a_camera_that_isnt_one_is_refused, 0 },
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
