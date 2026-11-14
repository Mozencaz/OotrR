#include "grid.h"

#include "text.h"

#define EQUIPMENT 0x5F84B0
#define ITEMS     0xA9814A
#define MAGIC     0x8466B0
#define DUNGEON_ABBR_FALLBACK 2 /* characters of a dungeon with no known label */
_Static_assert(DUNGEON_ABBR_FALLBACK < ABBR_MAX, "the label fits");

static const grid_cell_t cells[GRID_CELLS] = {
  { "Kokiri Sword", "KS", 1, EQUIPMENT }, { "Biggoron Sword", "BS", 1, EQUIPMENT },
  { "Deku Shield", "DS", 1, EQUIPMENT }, { "Hylian Shield", "HS", 1, EQUIPMENT },
  { "Mirror Shield", "MS", 1, EQUIPMENT }, { "Iron Boots", "IB", 1, EQUIPMENT },
  { "Hover Boots", "HB", 1, EQUIPMENT }, { "Progressive Strength Upgrade", "St", 3, EQUIPMENT },
  { "Progressive Scale", "Sc", 2, EQUIPMENT },

  { "Slingshot", "Sl", 3, ITEMS }, { "Bow", "Bow", 3, ITEMS },
  { "Bomb Bag", "Bo", 3, ITEMS }, { "Progressive Hookshot", "Hk", 2, ITEMS },
  { "Boomerang", "Bm", 1, ITEMS }, { "Megaton Hammer", "MH", 1, ITEMS },
  { "Lens of Truth", "LT", 1, ITEMS }, { "Ocarina", "Oc", 2, ITEMS },
  { "Bottle", "Bt", 1, ITEMS },

  { "Magic Meter", "Mg", 2, MAGIC }, { "Dins Fire", "Din", 1, MAGIC },
  { "Farores Wind", "Far", 1, MAGIC }, { "Nayrus Love", "Nay", 1, MAGIC },
  { "Fire Arrows", "FA", 1, MAGIC }, { "Ice Arrows", "IA", 1, MAGIC },
  { "Light Arrows", "LA", 1, MAGIC }, { "Zeldas Letter", "ZL", 1, ITEMS },
  { "Stone of Agony", "SA", 1, ITEMS },

  { "Kokiri Emerald", "KE", 1, 0x3C9A5C }, { "Goron Ruby", "GR", 1, 0xB8463C },
  { "Zora Sapphire", "ZS", 1, 0x3C6FB8 }, { "Forest Medallion", "Fo", 1, 0x3C8F4A },
  { "Fire Medallion", "Fi", 1, 0xB8553A }, { "Water Medallion", "Wa", 1, 0x3A74B8 },
  { "Spirit Medallion", "Sp", 1, 0xB8923A }, { "Shadow Medallion", "Sh", 1, 0x744CA0 },
  { "Light Medallion", "Li", 1, 0xB8A83E },
};

static const struct { const char *dungeon, *abbr, *medallion; } dungeon_abbrs[] = {
  { "Forest Temple", "Fo", "Forest Medallion" }, { "Fire Temple", "Fi", "Fire Medallion" },
  { "Water Temple", "Wa", "Water Medallion" }, { "Shadow Temple", "Sh", "Shadow Medallion" },
  { "Spirit Temple", "Sp", "Spirit Medallion" }, { "Bottom of the Well", "BW", 0 },
  { "Gerudo Training Ground", "GTG", 0 }, { "Ganon's Castle", "GC", 0 },
};

const grid_cell_t *grid_cell(int index)
{
  return &cells[index];
}

int grid_index_of(const char *item)
{
  for (int i = 0; i < GRID_CELLS; i++)
    if (text_equal(cells[i].item, item))
      return i;
  return -1;
}

void grid_dungeon_abbr(const char *dungeon, char out[ABBR_MAX])
{
  for (unsigned i = 0; i < sizeof(dungeon_abbrs) / sizeof(*dungeon_abbrs); i++) {
    if (text_equal(dungeon_abbrs[i].dungeon, dungeon)) {
      text_copy(out, ABBR_MAX, dungeon_abbrs[i].abbr);
      return;
    }
  }
  text_copy(out, DUNGEON_ABBR_FALLBACK + 1, dungeon);
}

const char *grid_dungeon_medallion(const char *dungeon)
{
  for (unsigned i = 0; i < sizeof(dungeon_abbrs) / sizeof(*dungeon_abbrs); i++)
    if (text_equal(dungeon_abbrs[i].dungeon, dungeon))
      return dungeon_abbrs[i].medallion;
  return 0;
}
