#include "tracker.h"

#include "text.h"

#define SOUL_PREFIX "Soul ("

static save_link_t link_of(const trk_t *seed, const flag_source_t *flags)
{
  switch (flags->bool_flag(flags, seed->seed_marker)) {
    case GD_TRUE: return SAVE_OF_THIS_SEED;
    case GD_FALSE: return SAVE_OF_ANOTHER;
    default: return SAVE_LINK_UNKNOWN;
  }
}

/* An item's level is the highest of its rules whose flag is set; it is unknown if the game has none of them. */
static void evaluate_item(const trk_t *seed, trk_item_t item, const flag_source_t *flags, cell_state_t *out)
{
  bool known = false;
  uint32_t level = 0;
  for (uint32_t r = 0; r < item.rule_count; r++) {
    trk_rule_t rule = trk_rule(seed, item.first_rule + r);
    gd_flag_t flag = flags->bool_flag(flags, rule.hash);
    known |= flag != GD_UNKNOWN;
    if (flag == GD_TRUE && rule.level > level)
      level = rule.level;
  }
  out->level = (uint8_t)(level > UINT8_MAX ? UINT8_MAX : level);
  out->status = level ? ITEM_OWNED : known ? ITEM_MISSING : ITEM_UNKNOWN;
}

static void compute_items(const trk_t *seed, const flag_source_t *flags, tracker_state_t *state)
{
  for (uint32_t i = 0; i < seed->item_count; i++) {
    trk_item_t item = trk_item(seed, i);
    const char *name = trk_string(seed, item.name);
    cell_state_t evaluated;
    evaluate_item(seed, item, flags, &evaluated);
    int cell = grid_index_of(name);
    if (cell >= 0) {
      state->cells[cell] = evaluated;
    } else if (text_starts_with(name, SOUL_PREFIX)) {
      state->souls_total++;
      state->souls_owned += evaluated.status == ITEM_OWNED;
    }
  }
}

static gd_flag_t check_flag(const trk_check_t *check, const flag_source_t *flags)
{
  if (check->kind == TRK_KIND_BOOL64)
    return flags->bool64_flag(flags, check->key);
  return flags->bool_flag(flags, (uint32_t)check->key);
}

static void compute_regions(const trk_t *seed, const flag_source_t *flags, tracker_state_t *state)
{
  state->region_count = seed->region_count;
  for (uint32_t i = 0; i < seed->region_count; i++) {
    trk_region_t region = trk_region(seed, i);
    region_state_t *out = &state->regions[i];
    out->name = trk_string(seed, region.name);
    out->trackable = region.check_count;
    for (uint32_t c = 0; c < region.check_count; c++) {
      trk_check_t check = trk_check(seed, region.first_check + c);
      gd_flag_t flag = check_flag(&check, flags);
      out->collected += flag == GD_TRUE;
      state->unreadable += flag == GD_UNKNOWN;
    }
    state->collected += out->collected;
    state->trackable += out->trackable;
  }
}

static uint16_t clamp_u16(int64_t value)
{
  return (uint16_t)(value < 0 ? 0 : value > UINT16_MAX ? UINT16_MAX : value);
}

/* Small keys found: the larger of the keys found and the keys held, or all of them once a key ring is
 * applied or the seed removed the keys. */
static void compute_small_keys(trk_keys_t keys, const flag_source_t *flags, dungeon_keys_t *out)
{
  int32_t found = 0, held = 0;
  bool found_known = flags->int_value(flags, keys.found_hash, &found);
  bool held_known = flags->int_value(flags, keys.held_hash, &held);
  bool all = (keys.flags & TRK_KEY_SMALL_ALL) ||
             (keys.ring_hash && flags->bool_flag(flags, keys.ring_hash) == GD_TRUE);
  out->has_small_keys = true;
  out->small_keys_known = found_known || held_known || all;
  out->total = (uint16_t)keys.small_total;
  out->found = all ? out->total : clamp_u16(found > held ? found : held);
  if (out->found > out->total)
    out->total = out->found;
}

static boss_key_t boss_key_of(trk_keys_t keys, const flag_source_t *flags)
{
  if (keys.flags & TRK_KEY_BOSS_ALL)
    return BOSS_KEY_HELD;
  switch (flags->bool_flag(flags, keys.boss_hash)) {
    case GD_TRUE: return BOSS_KEY_HELD;
    case GD_FALSE: return BOSS_KEY_MISSING;
    default: return BOSS_KEY_UNKNOWN;
  }
}

static void compute_keys(const trk_t *seed, const flag_source_t *flags, tracker_state_t *state)
{
  state->key_count = seed->key_count;
  for (uint32_t i = 0; i < seed->key_count; i++) {
    trk_keys_t keys = trk_keys(seed, i);
    dungeon_keys_t *out = &state->keys[i];
    out->name = trk_string(seed, keys.name);
    if (keys.flags & TRK_KEY_SMALL)
      compute_small_keys(keys, flags, out);
    out->boss = (keys.flags & TRK_KEY_BOSS) ? boss_key_of(keys, flags) : BOSS_KEY_NONE;
  }
}

void tracker_compute(const trk_t *seed, const flag_source_t *flags, tracker_state_t *state)
{
  *state = (tracker_state_t){ .link = link_of(seed, flags) };
  state->goal_reached = seed->goal_marker && flags->bool_flag(flags, seed->goal_marker) == GD_TRUE;
  compute_items(seed, flags, state);
  compute_regions(seed, flags, state);
  compute_keys(seed, flags, state);
}
