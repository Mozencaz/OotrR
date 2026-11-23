/* The module's checked memory reads, for the PC tests: every address above the null page is "mapped". The tests
 * only hand the code memory they allocated, or an address in the null page to see it refused. */
#include "../src/sys.h"

#define NULL_PAGE_END 0x1000

bool sys_mapped(uintptr_t addr, size_t size, uint32_t perm)
{
  return addr >= NULL_PAGE_END && addr + size >= addr;
}

uintptr_t sys_ptr(uintptr_t addr)
{
  if ((addr & 7) || !sys_mapped(addr, 8, SYS_PERM_R))
    return 0;
  return *(volatile uintptr_t *)addr;
}

bool sys_read32(uintptr_t addr, uint32_t *out)
{
  if ((addr & 3) || !sys_mapped(addr, 4, SYS_PERM_R))
    return false;
  *out = *(volatile uint32_t *)addr;
  return true;
}
