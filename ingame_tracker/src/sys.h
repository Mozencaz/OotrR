/* Horizon system calls, memory checks and logging to the emulator's log.
 * Adapted from sloperinaGZ's src/ootgz/sys.h (GPL-3).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef SYS_H
#define SYS_H

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* imported from the game's sdk module (resolved by rtld) */
int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap);
int snprintf(char *buf, size_t size, const char *fmt, ...);
void *memcpy(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);

#define SYS_PERM_R 1u
#define SYS_PERM_W 2u
#define SYS_PERM_X 4u

/* True if [addr, addr + size) lies in one mapped region with at least `perm`. */
bool sys_mapped(uintptr_t addr, size_t size, uint32_t perm);
/* Start of the mapped region holding addr (a module's base, for an address in its code), or 0. */
uintptr_t sys_region_start(uintptr_t addr);
uint64_t sys_ms(void); /* milliseconds since the console started */
/* The pointer or 32-bit word at addr, read only if the memory is mapped and aligned; 0 / false otherwise. */
uintptr_t sys_ptr(uintptr_t addr);
bool sys_read32(uintptr_t addr, uint32_t *out);

/* One line in the log (svcOutputDebugString), prefixed "ootrTracker: ". */
void log_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
/* Unformatted; safe before the sdk is initialised (module init). */
void log_raw(const char *text);

#endif
