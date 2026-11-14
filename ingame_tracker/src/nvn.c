/* Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "nvn.h"

#include "got.h"
#include "sys.h"

#define MAX_SWAPCHAIN_TEXTURES 8

typedef void *(*bootstrap_loader_t)(const char *name);
typedef void *(*getproc_t)(nvn_device_t *device, const char *name);
typedef void (*present_t)(nvn_queue_t *queue, nvn_window_t *window, int texture_index);
typedef void (*set_textures_t)(void *builder, int count, nvn_texture_t *const *textures);
typedef bool (*device_init_t)(nvn_device_t *device, const void *builder);
typedef void (*set_pool_t)(void *command_buffer, const void *pool);

extern void *nvnBootstrapLoader(const char *name); /* from sdk */

/* What our wrappers call: another add-on's wrapper (sloperinaGZ's), or NVN's own function. */
static void *next_bootstrap_loader, *next_getproc, *next_present, *next_set_textures, *next_device_init,
  *next_set_texture_pool, *next_set_sampler_pool;
static nvn_device_t *device;
static const void *volatile game_texture_pool, *volatile game_sampler_pool;
static nvn_texture_t *swapchain_textures[MAX_SWAPCHAIN_TEXTURES];
static int swapchain_texture_count;

static void hook_present(nvn_queue_t *queue, nvn_window_t *window, int index)
{
  static bool warned;
  int count = __atomic_load_n(&swapchain_texture_count, __ATOMIC_ACQUIRE);
  if (index >= 0 && index < count) {
    overlay_before_present(queue, window, swapchain_textures[index]);
  } else if (!warned) {
    warned = true;
    log_printf("present of swapchain texture %d, but %d seen: no panel", index, count);
  }
  ((present_t)next_present)(queue, window, index);
}

static void hook_set_textures(void *builder, int count, nvn_texture_t *const *textures)
{
  int kept = count < MAX_SWAPCHAIN_TEXTURES ? count : MAX_SWAPCHAIN_TEXTURES;
  __atomic_store_n(&swapchain_texture_count, 0, __ATOMIC_RELEASE); /* none usable while it's rewritten */
  for (int i = 0; i < kept; i++)
    swapchain_textures[i] = textures[i];
  __atomic_store_n(&swapchain_texture_count, kept, __ATOMIC_RELEASE);
  ((set_textures_t)next_set_textures)(builder, count, textures);
}

static bool hook_device_init(nvn_device_t *dev, const void *builder)
{
  bool ok = ((device_init_t)next_device_init)(dev, builder);
  if (ok)
    device = dev;
  return ok;
}

static void hook_set_texture_pool(void *command_buffer, const void *pool)
{
  game_texture_pool = pool;
  ((set_pool_t)next_set_texture_pool)(command_buffer, pool);
}

static void hook_set_sampler_pool(void *command_buffer, const void *pool)
{
  game_sampler_pool = pool;
  ((set_pool_t)next_set_sampler_pool)(command_buffer, pool);
}

static void *hook_getproc(nvn_device_t *dev, const char *name);

static const struct {
  const char *name;
  void *hook;
  void **next;
} wrapped[] = {
  { "nvnDeviceGetProcAddress", (void *)hook_getproc, &next_getproc },
  { "nvnQueuePresentTexture", (void *)hook_present, &next_present },
  { "nvnWindowBuilderSetTextures", (void *)hook_set_textures, &next_set_textures },
  { "nvnDeviceInitialize", (void *)hook_device_init, &next_device_init },
  { "nvnCommandBufferSetTexturePool", (void *)hook_set_texture_pool, &next_set_texture_pool },
  { "nvnCommandBufferSetSamplerPool", (void *)hook_set_sampler_pool, &next_set_sampler_pool },
};
#define WRAPPED_COUNT (sizeof(wrapped) / sizeof(*wrapped))

static bool names_equal(const char *a, const char *b)
{
  while (*a && *a == *b) {
    a++;
    b++;
  }
  return *a == *b;
}

/* What the game gets for a function it looks up: our wrapper, if it's one we wrap. */
static void *wrap(const char *name, void *proc)
{
  if (!proc)
    return proc;
  for (size_t i = 0; i < WRAPPED_COUNT; i++) {
    if (!names_equal(name, wrapped[i].name))
      continue;
    if (proc != wrapped[i].hook) /* never our own wrapper: it would call itself */
      *wrapped[i].next = proc;
    return wrapped[i].hook;
  }
  return proc;
}

static void *hook_getproc(nvn_device_t *dev, const char *name)
{
  if (dev && !device)
    device = dev;
  return wrap(name, ((getproc_t)next_getproc)(dev, name));
}

static void *hook_bootstrap_loader(const char *name)
{
  return wrap(name, ((bootstrap_loader_t)next_bootstrap_loader)(name));
}

const char *nvn_hook_game(uintptr_t main_base)
{
  return got_hook(main_base, "nvnBootstrapLoader", (void *)hook_bootstrap_loader, (void *)nvnBootstrapLoader,
                  &next_bootstrap_loader);
}

nvn_device_t *nvn_device(void)
{
  return device;
}

/* What the sdk's own loader gives, not what the add-ons' wrappers (ours, sloperinaGZ's) hand the game:
 * our drawing calls NVN directly, and must not be seen by their hooks (a recorded set of our own
 * texture pool would be put back as the game's). */
void *nvn_proc(const char *name)
{
  static getproc_t sdk_getproc;
  if (!device)
    return 0;
  if (!sdk_getproc)
    sdk_getproc = (getproc_t)nvnBootstrapLoader("nvnDeviceGetProcAddress");
  return sdk_getproc ? sdk_getproc(device, name) : 0;
}

const void *nvn_game_texture_pool(void)
{
  return game_texture_pool;
}

const void *nvn_game_sampler_pool(void)
{
  return game_sampler_pool;
}

/* --- what the drawing code asks NVN, by name through the game's device ------------------------------ */

static struct {
  void (*pool_builder_defaults)(nvn_obj_t *);
  void (*pool_builder_device)(nvn_obj_t *, nvn_device_t *);
  void (*pool_builder_flags)(nvn_obj_t *, int);
  void (*pool_builder_storage)(nvn_obj_t *, void *, size_t);
  bool (*pool_init)(nvn_obj_t *, const nvn_obj_t *);
  int (*tex_width)(const nvn_texture_t *);
  int (*tex_height)(const nvn_texture_t *);
  int (*tex_format)(const nvn_texture_t *);
  void (*window_crop)(const nvn_window_t *, nvn_rect_t *);
  int (*window_origin)(const nvn_device_t *);
} help;

static const char *const help_names[] = {
  "nvnMemoryPoolBuilderSetDefaults", "nvnMemoryPoolBuilderSetDevice", "nvnMemoryPoolBuilderSetFlags",
  "nvnMemoryPoolBuilderSetStorage", "nvnMemoryPoolInitialize", "nvnTextureGetWidth", "nvnTextureGetHeight",
  "nvnTextureGetFormat", "nvnWindowGetCrop", "nvnDeviceGetWindowOriginMode",
};
#define HELP_COUNT (sizeof(help_names) / sizeof(*help_names))
_Static_assert(HELP_COUNT == sizeof(help) / sizeof(void *), "help table");

static bool help_ready(void)
{
  static bool loaded;
  if (loaded)
    return true;
  if (!device)
    return false;
  void **slots = (void **)&help;
  for (unsigned i = 0; i < HELP_COUNT; i++) {
    slots[i] = nvn_proc(help_names[i]);
    if (!slots[i]) {
      log_printf("NVN has no %s", help_names[i]);
      return false;
    }
  }
  loaded = true;
  return true;
}

bool nvn_make_pool(nvn_obj_t *pool, void *mem, size_t size, int flags)
{
  if (!help_ready())
    return false;
  nvn_obj_t builder;
  memset(&builder, 0, sizeof(builder));
  help.pool_builder_defaults(&builder);
  help.pool_builder_device(&builder, device);
  help.pool_builder_flags(&builder, flags);
  help.pool_builder_storage(&builder, mem, size);
  return help.pool_init(pool, &builder);
}

bool nvn_texture_info(const nvn_texture_t *texture, nvn_texture_info_t *info)
{
  if (!help_ready())
    return false;
  info->width = help.tex_width(texture);
  info->height = help.tex_height(texture);
  info->format = help.tex_format(texture);
  return true;
}

nvn_rect_t nvn_visible_area(const nvn_window_t *window, const nvn_texture_info_t *info)
{
  nvn_rect_t crop = { 0, 0, 0, 0 };
  if (window && help_ready())
    help.window_crop(window, &crop);
  if (crop.w <= 0 || crop.h <= 0 || crop.x < 0 || crop.y < 0 || crop.x + crop.w > info->width ||
      crop.y + crop.h > info->height)
    crop = (nvn_rect_t){ 0, 0, info->width, info->height };
  return crop;
}

bool nvn_origin_lower_left(void)
{
  return help_ready() && help.window_origin(device) == 0;
}
