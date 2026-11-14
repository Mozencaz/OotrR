/* The game's NVN. main fetches every NVN function by name, through nvnBootstrapLoader and the
 * nvnDeviceGetProcAddress it returns, so wrapping the loader in main's GOT shows us the device, the
 * swapchain textures and each present. Types and hooks adapted from sloperinaGZ's src/ootgz/nvn.c and
 * nvnapi.h (GPL-3); signatures and enum values are NVN 1's, which this game still uses.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef NVN_H
#define NVN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct nvn_device nvn_device_t;
typedef struct nvn_queue nvn_queue_t;
typedef struct nvn_window nvn_window_t;
typedef struct nvn_texture nvn_texture_t;
typedef uint64_t nvn_addr_t;
typedef uint64_t nvn_handle_t;
typedef struct { int32_t x, y, z, w, h, d; } nvn_region_t;
typedef struct { int32_t x, y, w, h; } nvn_rect_t;

/* memory pool flags (nvnMemoryPoolBuilderSetFlags) */
enum {
  NVN_POOL_CPU_UNCACHED = 0x02,
  NVN_POOL_CPU_CACHED = 0x04,
  NVN_POOL_GPU_UNCACHED = 0x10,
  NVN_POOL_GPU_CACHED = 0x20,
  NVN_POOL_SHADER_CODE = 0x40,
};

/* Room for an NVN object we own: NVN 1's are at most 0x100 bytes, NVN 2's may have grown. */
#define NVN_OBJ_STORAGE 0x400
typedef struct { _Alignas(16) uint8_t b[NVN_OBJ_STORAGE]; } nvn_obj_t;

/* At module init: wrap main's nvnBootstrapLoader. NULL, or why it can't. */
const char *nvn_hook_game(uintptr_t main_base);
/* The game's device, once it has made one (NULL before). */
nvn_device_t *nvn_device(void);
/* An NVN function by name, as the sdk gives it for the game's device, not through any add-on's wrapper
 * (NULL before the game has a device). */
void *nvn_proc(const char *name);

/* A memory pool of `size` bytes at `mem` (page aligned, from the game's heap); false if NVN refuses. */
bool nvn_make_pool(nvn_obj_t *pool, void *mem, size_t size, int flags);

typedef struct { int width, height, format; } nvn_texture_info_t;
/* What a swapchain texture is; false until NVN's functions for it are found. */
bool nvn_texture_info(const nvn_texture_t *texture, nvn_texture_info_t *info);
/* The part of the texture that's shown: the game can render into a larger texture than it displays. */
nvn_rect_t nvn_visible_area(const nvn_window_t *window, const nvn_texture_info_t *info);
/* Whether scissor and viewport rectangles count from the bottom of a target (NVN's default). */
bool nvn_origin_lower_left(void);
/* The texture and sampler pools the game last set on a command buffer (NULL before it has), so a module
 * drawing with its own pools can put the game's back. */
const void *nvn_game_texture_pool(void);
const void *nvn_game_sampler_pool(void);

/* Called before each of the game's presents, with the texture it presents (overlay.c). */
void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture);

#endif
