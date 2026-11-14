/* Reading files through the game's own nn::fs (exported by sdk). Declarations from sloperinaGZ's
 * src/ootgz/sdfs.h (GPL-3), without the SD card. */
#ifndef NNFS_H
#define NNFS_H

#include <stddef.h>
#include <stdint.h>

typedef uint32_t nn_result_t;
typedef struct { void *handle; } fs_file_t;
enum { FS_READ = 1 };

nn_result_t fs_open(fs_file_t *out, const char *path, int mode) __asm__("_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci");
nn_result_t fs_size(int64_t *out, fs_file_t f) __asm__("_ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE");
nn_result_t fs_read(size_t *read, fs_file_t f, int64_t offset, void *buf, size_t size)
  __asm__("_ZN2nn2fs8ReadFileEPmNS0_10FileHandleElPvm");
void fs_close(fs_file_t f) __asm__("_ZN2nn2fs9CloseFileENS0_10FileHandleE");

#endif
