/* Adapted from sloperinaGZ's src/ootgz/sys.c (GPL-3).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "sys.h"

#define LOG_PREFIX "ootrTracker: "
#define LOG_PREFIX_LEN (sizeof(LOG_PREFIX) - 1)
#define LOG_LINE_MAX 256

#define NULL_PAGE_END     0x1000 /* never mapped: anything below is a bad pointer */
#define MEM_TYPE_UNMAPPED 0

typedef struct {
  uint64_t addr;
  uint64_t size;
  uint32_t type;
  uint32_t attr;
  uint32_t perm; /* bit 0 R, 1 W, 2 X */
  uint32_t ipc_refcount;
  uint32_t device_refcount;
  uint32_t padding;
} meminfo_t;

static uint32_t query_memory(meminfo_t *info, uint64_t addr)
{
  register uint64_t x0 __asm__("x0") = (uint64_t)info;
  register uint64_t x1 __asm__("x1");
  register uint64_t x2 __asm__("x2") = addr;
  __asm__ volatile("svc 0x6" : "+r"(x0), "=r"(x1), "+r"(x2) : : "memory", "x3", "x4", "x5",
                   "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16",
                   "x17", "x18");
  return (uint32_t)x0;
}

static void output_debug_string(const char *text, size_t len)
{
  register uint64_t x0 __asm__("x0") = (uint64_t)text;
  register uint64_t x1 __asm__("x1") = len;
  __asm__ volatile("svc 0x27" : "+r"(x0), "+r"(x1) : : "memory", "x2", "x3", "x4", "x5", "x6",
                   "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17",
                   "x18");
}

static bool query_mapped(uintptr_t addr, meminfo_t *region)
{
  if (addr < NULL_PAGE_END)
    return false;
  return query_memory(region, addr) == 0 && region->type != MEM_TYPE_UNMAPPED;
}

bool sys_mapped(uintptr_t addr, size_t size, uint32_t perm)
{
  meminfo_t region;
  if (addr + size < addr || !query_mapped(addr, &region))
    return false;
  return (region.perm & perm) == perm && addr + size <= region.addr + region.size;
}

uintptr_t sys_region_start(uintptr_t addr)
{
  meminfo_t region;
  return query_mapped(addr, &region) ? region.addr : 0;
}

uint64_t sys_ms(void)
{
  uint64_t ticks, ticks_per_second;
  __asm__ volatile("mrs %0, cntpct_el0" : "=r"(ticks));
  __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(ticks_per_second));
  return ticks / (ticks_per_second / 1000);
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

void log_printf(const char *fmt, ...)
{
  char line[LOG_LINE_MAX];
  memcpy(line, LOG_PREFIX, LOG_PREFIX_LEN);
  va_list ap;
  va_start(ap, fmt);
  int formatted = vsnprintf(line + LOG_PREFIX_LEN, sizeof(line) - LOG_PREFIX_LEN, fmt, ap);
  va_end(ap);
  if (formatted < 0)
    return;
  size_t message_max = sizeof(line) - LOG_PREFIX_LEN - 1;
  size_t message_len = (size_t)formatted < message_max ? (size_t)formatted : message_max;
  output_debug_string(line, LOG_PREFIX_LEN + message_len);
}

void log_raw(const char *text)
{
  char line[LOG_LINE_MAX] = LOG_PREFIX;
  size_t len = LOG_PREFIX_LEN;
  while (*text && len < sizeof(line) - 1)
    line[len++] = *text++;
  output_debug_string(line, len);
}
