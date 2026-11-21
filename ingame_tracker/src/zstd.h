/* zstd decompression in the module, for the game's RomFS files (.zs), with or without a dictionary
 * (the game's are in content:/Pack/ZsDic.pack.zs). Uses zstd's educational decoder
 * (third_party/zstd_decompress.c): small and slow, enough for a few font files. Adapted from
 * sloperinaGZ's src/ootgz/zstd.h (GPL-3; master 8c3a940636).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef ZSTD_H
#define ZSTD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct zstd_dict zstd_dict_t;

/* the frame's decompressed size from its header; 0 when the header doesn't say or src isn't zstd */
size_t zstd_content_size(const void *src, size_t len);
/* the dictionary ID a frame asks for; 0 = none */
uint32_t zstd_frame_dict_id(const void *src, size_t len);
/* a dictionary from a .zsdic (zstd dictionary format); NULL if it's damaged */
zstd_dict_t *zstd_dict_load(const void *data, size_t len);
void zstd_dict_free(zstd_dict_t *dict);

/* decompress src into dst (cap bytes) with dict (NULL: none). Returns the bytes written, or 0 with
 * *why set (damaged input, too small, out of memory); nothing is left allocated either way. */
size_t zstd_decompress(void *dst, size_t cap, const void *src, size_t len, const zstd_dict_t *dict,
                       const char **why);

#endif
