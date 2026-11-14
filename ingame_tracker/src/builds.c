#include "builds.h"

#include <stdbool.h>

#include "sys.h"

#define MOD0_MAGIC        0x30444F4Du /* "MOD0" */
#define MOD0_OFFSET_FIELD 4           /* base + 4: the offset of the MOD0 header */

static const game_build_t known_builds[] = {
  {
    .version = "1.0.0",
    .nnmain = 0x11C1FB0, .mod0 = 0x3BE705C, .gd_mgr_ptr = 0x4C184D8,
    .vt_int_field = 0x4BBAB10, .vt_bool_type = 0x4BB9538,
  },
  {
    .version = "1.1.1",
    .nnmain = 0x1202CD0, .mod0 = 0x3C4705C, .gd_mgr_ptr = 0x4C7E180,
    .vt_int_field = 0x4C20718, .vt_bool_type = 0x4C1F140,
  },
};

static bool is_build(const game_build_t *build, uintptr_t base)
{
  uint32_t mod0, magic;
  return sys_read32(base + MOD0_OFFSET_FIELD, &mod0) && mod0 == build->mod0 &&
         sys_read32(base + mod0, &magic) && magic == MOD0_MAGIC;
}

game_t builds_detect(uintptr_t nnmain_address)
{
  for (unsigned i = 0; i < sizeof(known_builds) / sizeof(*known_builds); i++) {
    uintptr_t base = nnmain_address - known_builds[i].nnmain;
    if (is_build(&known_builds[i], base))
      return (game_t){ &known_builds[i], base };
  }
  return (game_t){ 0, 0 };
}
