/* zstd decompression for the game's RomFS files: zstd's educational decoder
 * (third_party/zstd_decompress.c, BSD or GPLv2) with the module's libc (third_party/zstd_shim.h).
 * Adapted from sloperinaGZ's src/ootgz/zstd.c (GPL-3; master 8c3a940636), without its streaming of
 * frames too big to hold: the fonts and the shader are small.
 *
 * The decoder handles every error by calling ERROR(), which upstream exits on. Here it jumps back to
 * the call that started the work (jump.h), and every block the decoder allocated during that call is
 * freed. The calls run on one thread (the game's), so the jump buffer and the allocation list are plain
 * statics.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "zstd.h"

#include <stdbool.h>

#include "jump.h"
#include "sys.h"

static jump_buf_t jump;

void *aligned_alloc(size_t align, size_t size); /* from main */
void free(void *p);                             /* from main */

#define ALLOC_ALIGN 16
#define MAX_LIVE 256 /* blocks the decoder holds at once: a few per block, plus a dictionary's tables */

static const char no_memory[] = "out of memory"; /* not menu text */

static const char *fail_why;
static bool out_of_memory; /* an allocation failed during this call */
static void *live[MAX_LIVE];
static int live_count;

__attribute__((noreturn)) void zstd_shim_fail(const char *why);

void *zstd_shim_alloc(size_t size)
{
  /* at least one unit: the decoder asks for 0 bytes (a block with no literals), and NULL is an error */
  size_t n = size ? (size + ALLOC_ALIGN - 1) & ~(size_t)(ALLOC_ALIGN - 1) : ALLOC_ALIGN;
  if (live_count == MAX_LIVE) {
    log_printf("zstd: more than %d blocks at once", MAX_LIVE);
    return 0; /* the decoder reports it as an allocation error (more memory wouldn't help) */
  }
  void *p = aligned_alloc(ALLOC_ALIGN, n);
  if (p) {
    live[live_count++] = p;
  } else {
    log_printf("zstd: no memory for %u bytes", (unsigned)size);
    out_of_memory = true;
  }
  return p;
}

void *zstd_shim_calloc(size_t count, size_t size)
{
  if (size && count > (size_t)-1 / size)
    return 0;
  void *p = zstd_shim_alloc(count * size);
  if (p)
    memset(p, 0, count * size);
  return p;
}

void zstd_shim_free(void *p)
{
  if (!p)
    return;
  for (int i = live_count - 1; i >= 0; i--) {
    if (live[i] == p) {
      live[i] = live[--live_count];
      break;
    }
  }
  free(p);
}

__attribute__((noreturn)) void zstd_shim_fail(const char *why)
{
  fail_why = why;
  JUMP_BACK(jump);
}

/* one call into the decoder: on an error, what it allocated is freed */
static void free_live(void)
{
  while (live_count)
    free(live[--live_count]);
}

/* an error's reason, for *why */
static const char *failed_why(void)
{
  return out_of_memory ? no_memory : fail_why ? fail_why : "error";
}

/* the decoder itself; its own names are static to this file except the four it exports */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#pragma GCC diagnostic ignored "-Wunused-function"
#include "third_party/zstd_decompress.c"
#pragma GCC diagnostic pop
#undef malloc /* zstd_shim.h's, for the decoder only */
#undef calloc
#undef free

#define ZSTD_FRAME_MAGIC 0xFD2FB528u

size_t zstd_content_size(const void *src, size_t len)
{
  const uint8_t *s = src;
  if (len < 6 || (s[0] | s[1] << 8 | s[2] << 16 | (uint32_t)s[3] << 24) != ZSTD_FRAME_MAGIC)
    return 0;
  live_count = 0;
  if (JUMP_SET(jump)) {
    free_live();
    return 0;
  }
  size_t n = ZSTD_get_decompressed_size(src, len);
  live_count = 0;
  return n == (size_t)-1 ? 0 : n;
}

uint32_t zstd_frame_dict_id(const void *src, size_t len)
{
  /* frame header: magic, descriptor, the window byte unless single segment, then 0/1/2/4 bytes */
  const uint8_t *s = src;
  if (len < 5 || (s[0] | s[1] << 8 | s[2] << 16 | (uint32_t)s[3] << 24) != ZSTD_FRAME_MAGIC)
    return 0;
  uint8_t descriptor = s[4];
  static const int id_bytes[4] = { 0, 1, 2, 4 };
  int n = id_bytes[descriptor & 3];
  size_t at = 5 + ((descriptor & 0x20) ? 0 : 1);
  if (!n || at + n > len)
    return 0;
  uint32_t id = 0;
  for (int i = 0; i < n; i++)
    id |= (uint32_t)s[at + i] << (8 * i);
  return id;
}

void zstd_dict_free(zstd_dict_t *dict)
{
  if (dict)
    free_dictionary((dictionary_t *)dict); /* its tables, its content and itself, through zstd_shim_free */
}

zstd_dict_t *zstd_dict_load(const void *data, size_t len)
{
  live_count = 0;
  if (JUMP_SET(jump)) {
    free_live();
    return 0;
  }
  dictionary_t *dict = create_dictionary();
  parse_dictionary(dict, data, len);
  live_count = 0; /* what it allocated is the dictionary's now */
  return (zstd_dict_t *)dict;
}

size_t zstd_decompress(void *dst, size_t cap, const void *src, size_t len, const zstd_dict_t *dict,
                       const char **why)
{
  live_count = 0;
  fail_why = 0;
  out_of_memory = false;
  if (JUMP_SET(jump)) {
    free_live();
    if (why)
      *why = failed_why();
    return 0;
  }
  size_t n = dict ? ZSTD_decompress_with_dict(dst, cap, src, len, (dictionary_t *)dict)
                  : ZSTD_decompress(dst, cap, src, len);
  free_live(); /* the decoder frees its blocks itself; this only catches a leak */
  return n;
}
