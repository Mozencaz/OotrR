#include "locate.h"

#include "text.h"

#define FIRST_VERSION_WITH_PLACES 4
#define HEIGHT_SAID_M             2 /* a place this much above or below Link says so */

uint32_t locate_check_of(const trk_t *trk, uint32_t region, uint32_t nth)
{
  if (region >= trk->region_count)
    return LOCATE_NONE;
  trk_region_t r = trk_region(trk, region);
  return nth < r.check_count ? r.first_check + nth : LOCATE_NONE;
}

uint32_t locate_toggle(uint32_t shown, uint32_t check)
{
  return check == shown ? LOCATE_NONE : check;
}

locate_t locate_find(const trk_t *trk, uint32_t check, const char *map)
{
  locate_t where = { .state = LOCATE_OFF };
  if (check == LOCATE_NONE || check >= trk->check_count)
    return where;
  if (trk->version < FIRST_VERSION_WITH_PLACES) {
    where.state = LOCATE_OLD_FILE;
    return where;
  }
  uint32_t first, count = trk_places_of(trk, check, &first);
  if (!count) {
    where.state = LOCATE_NOWHERE;
    return where;
  }
  for (uint32_t i = 0; map && i < count; i++) {
    trk_place_t place = trk_place(trk, first + i);
    if (text_equal(trk_string(trk, place.map), map)) {
      where.state = LOCATE_HERE;
      where.point[0] = place.x;
      where.point[1] = place.y;
      where.point[2] = place.z;
      return where;
    }
  }
  where.state = map ? LOCATE_ELSEWHERE : LOCATE_MAP_UNKNOWN;
  where.label = trk_string(trk, trk_place(trk, first).label);
  where.more_maps = count - 1;
  return where;
}

/* --- the words ------------------------------------------------------------------------------------ */

/* `text` added at out[*at], as much as fits (the module has no snprintf for its pure parts) */
static void put(char *out, size_t room, size_t *at, const char *text)
{
  while (*text && *at + 1 < room)
    out[(*at)++] = *text++;
  out[*at < room ? *at : room - 1] = 0;
}

static void put_number(char *out, size_t room, size_t *at, uint32_t value)
{
  char digits[11];
  int n = 0;
  do {
    digits[n++] = (char)('0' + value % 10);
    value /= 10;
  } while (value);
  char text[11];
  for (int i = 0; i < n; i++)
    text[i] = digits[n - 1 - i];
  text[n] = 0;
  put(out, room, at, text);
}

static uint32_t metres(float v)
{
  v = v < 0 ? -v : v;
  return v > 1e6f ? 1000000u : (uint32_t)(v + 0.5f);
}

static void describe_distance(const float point[3], const float link[3], char *out, size_t room, size_t *at)
{
  float d[3] = { point[0] - link[0], point[1] - link[1], point[2] - link[2] };
  uint32_t away = metres(view_length(d));
  if (!away) {
    put(out, room, at, "Right here");
    return;
  }
  put_number(out, room, at, away);
  put(out, room, at, " m away");
  if (d[1] >= HEIGHT_SAID_M || d[1] <= -HEIGHT_SAID_M) {
    put(out, room, at, ", ");
    put_number(out, room, at, metres(d[1]));
    put(out, room, at, d[1] > 0 ? " m up" : " m down");
  }
}

static void describe_maps(const locate_t *where, char *out, size_t room, size_t *at)
{
  put(out, room, at, "In ");
  put(out, room, at, where->label ? where->label : "another map");
  if (where->more_maps) {
    put(out, room, at, " and ");
    put_number(out, room, at, where->more_maps);
    put(out, room, at, where->more_maps == 1 ? " other map" : " other maps");
  }
}

void locate_describe(const locate_t *where, const float link[3], char *out, size_t room)
{
  size_t at = 0;
  if (!room)
    return;
  out[0] = 0;
  switch (where->state) {
    case LOCATE_HERE:
      if (link)
        describe_distance(where->point, link, out, room, &at);
      else
        put(out, room, &at, "In this map");
      return;
    case LOCATE_ELSEWHERE:
    case LOCATE_MAP_UNKNOWN:
      describe_maps(where, out, room, &at);
      return;
    case LOCATE_NOWHERE:
      put(out, room, &at, "No place in the world for this check");
      return;
    case LOCATE_OLD_FILE:
      put(out, room, &at, "This seed's file is too old to tick checks or show them: update its tracker with the game "
                          "file");
      return;
    case LOCATE_OFF:
      return;
  }
}

void locate_band_line(const float point[3], const float link[3], view_side_t side, char *out, size_t room)
{
  static const char *const ways[] = {
    [VIEW_ON_PICTURE] = "", [VIEW_LEFT] = "turn left", [VIEW_RIGHT] = "turn right", [VIEW_ABOVE] = "look up",
    [VIEW_BELOW] = "look down", [VIEW_BEHIND] = "behind you",
  };
  size_t at = 0;
  if (!room)
    return;
  out[0] = 0;
  if (link)
    describe_distance(point, link, out, room, &at);
  else
    put(out, room, &at, "In this map");
  const char *way = (unsigned)side < sizeof(ways) / sizeof(*ways) ? ways[side] : "";
  if (way[0]) {
    put(out, room, &at, ", ");
    put(out, room, &at, way);
  }
}

void locate_panel_line(bool shown, const locate_t *where, const float link[3], char *out, size_t room)
{
  size_t at = 0;
  if (!room)
    return;
  out[0] = 0;
  bool placed = where->state == LOCATE_HERE || where->state == LOCATE_ELSEWHERE || where->state == LOCATE_MAP_UNKNOWN;
  if (!placed) {
    locate_describe(where, link, out, room);
    return;
  }
  put(out, room, &at, shown ? "Shown in the world: " : "Y: show in the world     ");
  char said[LOCATE_TEXT_ROOM];
  locate_describe(where, link, said, sizeof(said));
  put(out, room, &at, said);
}
