/* The game's save data (GameData), read in place and never written: Bool and Int fields by the MurmurHash3 of
 * their name, and the Bool64bitKey flags (a placed actor's 64-bit id) by key. Layouts and offsets from
 * sloperinaGZ's src/ootgz/gamedata.c (GPL-3; master 8c3a940636) and its FINDINGS. Nothing here calls a
 * game function. Every pointer is checked to be mapped before it is read. */
#ifndef GAMEDATA_H
#define GAMEDATA_H

#include <stdbool.h>
#include <stdint.h>

#include "builds.h"
#include "flags.h"

/* A type entry in the manager (0x60 bytes): its field objects and the hash table that finds them. */
typedef struct {
  uintptr_t vtable;     /* 0x00 */
  uint32_t  count;      /* 0x08 */
  uint32_t  _0c;
  uint8_t  *objects;    /* 0x10: `count` objects, a stride apart */
  uint32_t *table;      /* 0x18: (hash, index) pairs, open addressing, hash 0 = empty */
  uint32_t  _20;
  uint32_t  table_size; /* 0x24 */
} gd_type_t;

/* One Bool64bitKey record (16 bytes). */
typedef struct {
  uint64_t key;
  uint32_t reset;
  uint8_t  value; /* 1 = set */
  uint8_t  save_index;
  uint8_t  _0e;
  uint8_t  extra;
} gd_bool64_t;

/* The Bool64bitKey entry in the manager: a count and the records. The first `sorted` are in key order;
 * a seed appends more after them, in no order. */
typedef struct {
  uint32_t           count;
  uint32_t           _04;
  const gd_bool64_t *records;
} gd_bool64_type_t;

typedef struct {
  flag_source_t source; /* first: the tracker reads the game through this */
  game_t game;
  const uint8_t *manager;
  const gd_type_t *int_type, *bool_type;
  const gd_bool64_type_t *bool64_type;
  uint32_t bool_entry_offset, bool64_entry_offset; /* where the scans found them, to look there first */
  uint32_t bool64_sorted;                          /* records in key order from the start of the table */
  const gd_bool64_t *sorted_for;                   /* the table `bool64_sorted` was counted for */
  uint32_t sorted_for_count;
} gamedata_t;

void gamedata_init(gamedata_t *data, game_t game);
/* Finds the manager and its tables as they are now (they move when a save is loaded). False until the
 * game has its save data; the flags answer GD_UNKNOWN then. */
bool gamedata_attach(gamedata_t *data);
/* Whether the Bool64bitKey flags were found by the last attach. */
bool gamedata_has_bool64(const gamedata_t *data);

#endif
