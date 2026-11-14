/* The GPU path (see gpuui.h). Adapted from sloperinaGZ's src/ootgz/gpuui.c (GPL-3; master 8c3a940636),
 * which has the same drawing for its menus. How it uses the game's MergeShader (sloperinaGZ's
 * docs/NATIVE_UI.md has the sources):
 *
 *   vertices      one strip of 4, (0,0) (1,0) (0,1) (1,1), as both attributes (_p0 position, _u0 corner),
 *                 RG32F at offset 0, stride 8
 *   VS uniform 1  `view`: a column-major 4x4 matrix; here the visible area's pixels (y down) to clip space
 *   VS uniform 2  64 zero bytes (word 15 would turn on a shadow texture-coordinate remap)
 *   VS storage 6  one 46-word element per quad: a row-major 3x4 matrix, the four corners' colours, the size,
 *                 the four corners' texture coordinates, a 2x3 texture matrix
 *   FS uniform 4  `UiMaterial`: colour scale 1, offset 0, alpha and RGB multipliers 1, flags 0x2 (discard
 *                 where alpha is 0)
 *   FS texture 8  the glyph atlas: RG8, a luminance and a coverage, seen as (l, l, l, coverage). A glyph
 *                 with its shadow baked in has the luminance 0 where only the shadow shows, so one quad
 *                 draws both
 * Output alpha is straight, so blending is SRC_ALPHA / ONE_MINUS_SRC_ALPHA. Each quad is one draw with
 * its element bound. The atlas only grows within a frame: glyphs are added as they're asked for and the
 * rows they touched are copied up before the frame's draws. Nothing here waits for the GPU: the caller's
 * slots (each guarded by its fence) keep a frame's elements and view until the GPU is done with them.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "gpuui.h"

#include <stddef.h>

#include "sys.h"
#include "uishader.h"

void *aligned_alloc(size_t align, size_t size); /* from main */
void free(void *p);                             /* from main */

#define PAGE 0x1000
#define SLOTS 2               /* the caller's frame slots */
#define MAX_QUADS 1536        /* a frame's quads (a glyph is one, its shadow baked into its image); the tracker panel's text is most of them */
#define ELEMENT_SIZE 0x100    /* 46 words, at the storage-buffer alignment */
#define ELEMENT_WORDS 46
#define UNIFORM_SIZE 0x100
#define VERTEX_BYTES 32
#define VERTEX_STRIDE 8
#define POOL_ENTRIES 512      /* texture / sampler descriptors: the first ones (256) are NVN's own */
#define ATLAS_W 512
#define ATLAS_H 512
#define ATLAS_BPP 2                        /* RG8: a texel's luminance, then its coverage */
#define ATLAS_STRIDE (ATLAS_W * ATLAS_BPP) /* a staging row, in bytes */
#define ATLAS_SLOTS 512                    /* a power of two */
#define GLYPH_PAD 1                        /* empty texels around each glyph, so linear filtering doesn't bleed */
#define CODE_ALIGN 0x100
#define CODE_PADDING 0x800    /* after the last code area (NVN 2's shader pool padding) */
#define CMD_RESERVE 0x4000    /* command memory kept free (the caller's own commands, the restore) */
#define MATERIAL_BYTES 64
#define MATERIAL_DISCARD_CLEAR 0x2u /* UiMaterial's flags: discard where alpha is 0 */
#define SHADOW_DIVISOR 14.0f  /* a soft shadow that grows with the type: em / this pixels, at least one */
#define DEFAULT_DESCRIPTOR_SIZE 32
#define DEFAULT_RESERVED_ID 256
#define MAX_DESCRIPTOR_SIZE 256

/* NVN values */
enum {
  STAGE_VERTEX = 0, STAGE_FRAGMENT = 1, STAGES_GRAPHICS = 0xFF,
  BLEND_ONE = 2, BLEND_SRC_ALPHA = 5, BLEND_ONE_MINUS_SRC_ALPHA = 6, BLEND_ADD = 1,
  FACE_NONE = 0, PRIM_TRIANGLE_STRIP = 5,
  FMT_RG8 = 0x0D, FMT_RG32F = 0x16, TARGET_2D = 1,
  SWIZZLE_R = 2, SWIZZLE_G = 3, FILTER_LINEAR = 1, WRAP_CLAMP_TO_EDGE = 7,
  BARRIER_ORDER_PRIMITIVES = 1, BARRIER_ORDER_FRAGMENTS = 2, BARRIER_INVALIDATE_TEXTURE = 0x10,
  INFO_TEXTURE_DESCRIPTOR_SIZE = 0xF, INFO_SAMPLER_DESCRIPTOR_SIZE = 0x10, INFO_RESERVED_TEXTURES = 0x11,
  INFO_RESERVED_SAMPLERS = 0x12,
};

typedef struct { uint64_t data; const void *control; } shader_data_t;

static struct {
  nvn_addr_t (*pool_address)(const nvn_obj_t *);
  bool (*program_init)(nvn_obj_t *, nvn_device_t *);
  bool (*program_set_shaders)(nvn_obj_t *, int, const shader_data_t *);
  void (*blend_defaults)(void *);
  void (*blend_target)(void *, int);
  void (*blend_func)(void *, int, int, int, int);
  void (*blend_equation)(void *, int, int);
  void (*colour_defaults)(void *);
  void (*colour_blend_enable)(void *, int, bool);
  void (*channel_defaults)(void *);
  void (*multisample_defaults)(void *);
  void (*polygon_defaults)(void *);
  void (*polygon_cull)(void *, int);
  void (*depth_defaults)(void *);
  void (*depth_test)(void *, bool);
  void (*depth_write)(void *, bool);
  void (*attrib_defaults)(void *);
  void (*attrib_format)(void *, int, ptrdiff_t);
  void (*attrib_stream)(void *, int);
  void (*stream_defaults)(void *);
  void (*stream_stride)(void *, ptrdiff_t);
  void (*tb_device)(void *, nvn_device_t *);
  void (*tb_defaults)(void *);
  void (*tb_target)(void *, int);
  void (*tb_format)(void *, int);
  void (*tb_size)(void *, int, int);
  void (*tb_levels)(void *, int);
  void (*tb_flags)(void *, int);
  void (*tb_swizzle)(void *, int, int, int, int);
  size_t (*tb_storage_size)(const void *);
  size_t (*tb_storage_align)(const void *);
  void (*tb_storage)(void *, const nvn_obj_t *, ptrdiff_t);
  bool (*texture_init)(void *, const void *);
  void (*sb_device)(void *, nvn_device_t *);
  void (*sb_defaults)(void *);
  void (*sb_filter)(void *, int, int);
  void (*sb_wrap)(void *, int, int, int);
  bool (*sampler_init)(void *, const void *);
  bool (*texture_pool_init)(void *, const nvn_obj_t *, ptrdiff_t, int);
  bool (*sampler_pool_init)(void *, const nvn_obj_t *, ptrdiff_t, int);
  void (*texture_pool_register)(const void *, int, const void *, const void *);
  void (*sampler_pool_register)(const void *, int, const void *);
  nvn_handle_t (*texture_handle)(const nvn_device_t *, int, int);
  void (*cmd_render_enable)(nvn_obj_t *, bool);
  void (*cmd_targets)(nvn_obj_t *, int, nvn_texture_t *const *, const void *const *, const void *, const void *);
  void (*cmd_viewport)(nvn_obj_t *, int, int, int, int);
  void (*cmd_scissor)(nvn_obj_t *, int, int, int, int);
  void (*cmd_program)(nvn_obj_t *, const nvn_obj_t *, int);
  void (*cmd_blend)(nvn_obj_t *, const void *);
  void (*cmd_colour)(nvn_obj_t *, const void *);
  void (*cmd_channels)(nvn_obj_t *, const void *);
  void (*cmd_multisample)(nvn_obj_t *, const void *);
  void (*cmd_polygon)(nvn_obj_t *, const void *);
  void (*cmd_depth)(nvn_obj_t *, const void *);
  void (*cmd_attribs)(nvn_obj_t *, int, const void *);
  void (*cmd_streams)(nvn_obj_t *, int, const void *);
  void (*cmd_vertex_buffer)(nvn_obj_t *, int, nvn_addr_t, size_t);
  void (*cmd_uniform)(nvn_obj_t *, int, int, nvn_addr_t, size_t);
  void (*cmd_storage)(nvn_obj_t *, int, int, nvn_addr_t, size_t);
  void (*cmd_texture_pool)(nvn_obj_t *, const void *);
  void (*cmd_sampler_pool)(nvn_obj_t *, const void *);
  void (*cmd_texture)(nvn_obj_t *, int, int, nvn_handle_t);
  void (*cmd_draw)(nvn_obj_t *, int, int, int);
  void (*cmd_copy_to_texture)(nvn_obj_t *, nvn_addr_t, const void *, const void *, const nvn_region_t *, int);
  void (*cmd_barrier)(nvn_obj_t *, int);
  void (*cmd_copy_stride)(nvn_obj_t *, ptrdiff_t);
  size_t (*cmd_free)(const nvn_obj_t *);
} g;

static const char *const g_names[] = {
  "nvnMemoryPoolGetBufferAddress", "nvnProgramInitialize", "nvnProgramSetShaders",
  "nvnBlendStateSetDefaults", "nvnBlendStateSetBlendTarget", "nvnBlendStateSetBlendFunc", "nvnBlendStateSetBlendEquation",
  "nvnColorStateSetDefaults", "nvnColorStateSetBlendEnable", "nvnChannelMaskStateSetDefaults",
  "nvnMultisampleStateSetDefaults", "nvnPolygonStateSetDefaults", "nvnPolygonStateSetCullFace",
  "nvnDepthStencilStateSetDefaults", "nvnDepthStencilStateSetDepthTestEnable", "nvnDepthStencilStateSetDepthWriteEnable",
  "nvnVertexAttribStateSetDefaults", "nvnVertexAttribStateSetFormat", "nvnVertexAttribStateSetStreamIndex",
  "nvnVertexStreamStateSetDefaults", "nvnVertexStreamStateSetStride",
  "nvnTextureBuilderSetDevice", "nvnTextureBuilderSetDefaults", "nvnTextureBuilderSetTarget", "nvnTextureBuilderSetFormat",
  "nvnTextureBuilderSetSize2D", "nvnTextureBuilderSetLevels", "nvnTextureBuilderSetFlags", "nvnTextureBuilderSetSwizzle",
  "nvnTextureBuilderGetStorageSize", "nvnTextureBuilderGetStorageAlignment", "nvnTextureBuilderSetStorage",
  "nvnTextureInitialize",
  "nvnSamplerBuilderSetDevice", "nvnSamplerBuilderSetDefaults", "nvnSamplerBuilderSetMinMagFilter",
  "nvnSamplerBuilderSetWrapMode", "nvnSamplerInitialize",
  "nvnTexturePoolInitialize", "nvnSamplerPoolInitialize", "nvnTexturePoolRegisterTexture", "nvnSamplerPoolRegisterSampler",
  "nvnDeviceGetTextureHandle",
  "nvnCommandBufferSetRenderEnable", "nvnCommandBufferSetRenderTargets", "nvnCommandBufferSetViewport",
  "nvnCommandBufferSetScissor", "nvnCommandBufferBindProgram", "nvnCommandBufferBindBlendState",
  "nvnCommandBufferBindColorState", "nvnCommandBufferBindChannelMaskState", "nvnCommandBufferBindMultisampleState",
  "nvnCommandBufferBindPolygonState", "nvnCommandBufferBindDepthStencilState", "nvnCommandBufferBindVertexAttribState",
  "nvnCommandBufferBindVertexStreamState", "nvnCommandBufferBindVertexBuffer", "nvnCommandBufferBindUniformBuffer",
  "nvnCommandBufferBindStorageBuffer", "nvnCommandBufferSetTexturePool", "nvnCommandBufferSetSamplerPool",
  "nvnCommandBufferBindTexture", "nvnCommandBufferDrawArrays", "nvnCommandBufferCopyBufferToTexture",
  "nvnCommandBufferBarrier", "nvnCommandBufferSetCopyRowStride", "nvnCommandBufferGetCommandMemoryFree",
};
_Static_assert(sizeof(g_names) / sizeof(*g_names) == sizeof(g) / sizeof(void *), "gpuui function table");

/* optional: NVN's own sizes of the descriptors, else NVN 2's */
static void (*device_integer)(const nvn_device_t *, int, int *);

/* --- objects and memory ------------------------------------------------------------------------------ */

static bool ready;

static nvn_obj_t code_pool, data_pool;
static uint8_t *code_mem, *data_mem;
static size_t code_size;
static nvn_addr_t data_gpu;
static nvn_obj_t programs[UI_PROGRAMS];
static shader_data_t shader_data[UI_PROGRAMS][2];
static nvn_obj_t blend, colour, channels, multisample, polygon, depth;
static _Alignas(16) uint8_t attribs[2 * 4]; /* NVN 2's vertex attribute state is 4 bytes (the game's stride) */
static _Alignas(16) uint8_t streams[8];     /* ... its vertex stream state 8 */
static nvn_obj_t atlas_builder, atlas, sampler_builder, sampler, texture_pool, sampler_pool;
static nvn_handle_t atlas_handle;
/* the descriptor pools: each descriptor's size, and the first IDs (NVN's own); ours come after them */
static int texture_descriptor = DEFAULT_DESCRIPTOR_SIZE, sampler_descriptor = DEFAULT_DESCRIPTOR_SIZE;
static int our_texture_id = DEFAULT_RESERVED_ID, our_sampler_id = DEFAULT_RESERVED_ID;

/* NVN's answer for an item, if it's sane, else NVN 2's (its sdk's table) */
static int device_info(int item, int fallback, int most)
{
  int v = 0;
  if (device_integer)
    device_integer(nvn_device(), item, &v);
  return v > 0 && v <= most ? v : fallback;
}

/* the data pool's layout */
static size_t off_vertices, off_view, off_shadow, off_material, off_textures, off_samplers, off_elements, off_staging,
  off_atlas, data_size;

static size_t round_up(size_t n, size_t to) { return (n + to - 1) / to * to; }

/* the shader code areas in a pool of their own, each 256-aligned, with the padding NVN 2 wants after them */
static bool make_programs(void)
{
  code_size = 0;
  for (int p = 0; p < UI_PROGRAMS; p++) {
    const uishader_program_t *program = uishader_program(p);
    if (!program)
      return false;
    code_size += round_up(program->vertex.code_size, CODE_ALIGN) + round_up(program->fragment.code_size, CODE_ALIGN);
  }
  code_size = round_up(code_size + CODE_PADDING, PAGE);
  code_mem = aligned_alloc(PAGE, code_size);
  if (!code_mem)
    return false;
  /* written once it's a pool (uncached): nothing of it waits in the CPU's cache */
  if (!nvn_make_pool(&code_pool, code_mem, code_size,
                     NVN_POOL_CPU_UNCACHED | NVN_POOL_GPU_CACHED | NVN_POOL_SHADER_CODE)) {
    free(code_mem);
    code_mem = 0;
    return false;
  }
  memset(code_mem, 0, code_size);
  size_t at = 0;
  for (int p = 0; p < UI_PROGRAMS; p++) {
    const uishader_program_t *program = uishader_program(p);
    const uishader_stage_t *stages[2] = { &program->vertex, &program->fragment };
    for (int s = 0; s < 2; s++) {
      memcpy(code_mem + at, stages[s]->code, stages[s]->code_size);
      shader_data[p][s].data = at; /* made an address below, once the pool has one */
      shader_data[p][s].control = stages[s]->control;
      at += round_up(stages[s]->code_size, CODE_ALIGN);
    }
  }
  nvn_addr_t code_gpu = g.pool_address(&code_pool);
  for (int p = 0; p < UI_PROGRAMS; p++) {
    shader_data[p][0].data += code_gpu;
    shader_data[p][1].data += code_gpu;
    if (!g.program_init(&programs[p], nvn_device()) || !g.program_set_shaders(&programs[p], 2, shader_data[p]))
      return false;
  }
  return true;
}

static void make_states(void)
{
  g.blend_defaults(&blend);
  g.blend_target(&blend, 0);
  g.blend_func(&blend, BLEND_SRC_ALPHA, BLEND_ONE_MINUS_SRC_ALPHA, BLEND_ONE, BLEND_ONE_MINUS_SRC_ALPHA);
  g.blend_equation(&blend, BLEND_ADD, BLEND_ADD);
  g.colour_defaults(&colour);
  g.colour_blend_enable(&colour, 0, true);
  g.channel_defaults(&channels);
  g.multisample_defaults(&multisample);
  g.polygon_defaults(&polygon);
  g.polygon_cull(&polygon, FACE_NONE);
  g.depth_defaults(&depth);
  g.depth_test(&depth, false);
  g.depth_write(&depth, false);
  for (int i = 0; i < 2; i++) {
    g.attrib_defaults(attribs + 4 * i);
    g.attrib_format(attribs + 4 * i, FMT_RG32F, 0); /* both read the corner: _p0 scaled by the size, _u0 as is */
    g.attrib_stream(attribs + 4 * i, 0);
  }
  g.stream_defaults(streams);
  g.stream_stride(streams, VERTEX_STRIDE);
}

static void describe_atlas(void)
{
  g.tb_device(&atlas_builder, nvn_device());
  g.tb_defaults(&atlas_builder);
  g.tb_target(&atlas_builder, TARGET_2D);
  g.tb_format(&atlas_builder, FMT_RG8);
  g.tb_size(&atlas_builder, ATLAS_W, ATLAS_H);
  g.tb_levels(&atlas_builder, 1);
  g.tb_flags(&atlas_builder, 0); /* block-linear: the copy lays the texels out */
  g.tb_swizzle(&atlas_builder, SWIZZLE_R, SWIZZLE_R, SWIZZLE_R, SWIZZLE_G); /* (luminance x3, coverage) */
}

static void write_constants(void)
{
  static const float corners[8] = { 0, 0, 1, 0, 0, 1, 1, 1 };
  memcpy(data_mem + off_vertices, corners, sizeof(corners));
  float material[MATERIAL_BYTES / 4] = { 1, 1, 1, 1, 0, 0, 0, 0, 1, 1 };
  uint32_t discard_clear = MATERIAL_DISCARD_CLEAR;
  memcpy(&material[10], &discard_clear, 4);
  memcpy(data_mem + off_material, material, sizeof(material));
}

/* the data pool's layout: the vertices, the uniforms, the descriptor pools, the elements, the atlas */
static void plan_data(size_t atlas_size, size_t atlas_align)
{
  size_t at = 0;
  off_vertices = at, at += UNIFORM_SIZE;
  off_view = at, at += UNIFORM_SIZE * SLOTS;
  off_shadow = at, at += UNIFORM_SIZE;
  off_material = at, at += UNIFORM_SIZE;
  at = round_up(at, PAGE);
  texture_descriptor = device_info(INFO_TEXTURE_DESCRIPTOR_SIZE, DEFAULT_DESCRIPTOR_SIZE, MAX_DESCRIPTOR_SIZE);
  sampler_descriptor = device_info(INFO_SAMPLER_DESCRIPTOR_SIZE, DEFAULT_DESCRIPTOR_SIZE, MAX_DESCRIPTOR_SIZE);
  our_texture_id = device_info(INFO_RESERVED_TEXTURES, DEFAULT_RESERVED_ID, POOL_ENTRIES - 2); /* then the atlas */
  our_sampler_id = device_info(INFO_RESERVED_SAMPLERS, DEFAULT_RESERVED_ID, POOL_ENTRIES - 1);
  off_textures = at, at += (size_t)POOL_ENTRIES * texture_descriptor;
  at = round_up(at, PAGE);
  off_samplers = at, at += (size_t)POOL_ENTRIES * sampler_descriptor;
  at = round_up(at, PAGE);
  off_elements = at, at += (size_t)SLOTS * MAX_QUADS * ELEMENT_SIZE;
  off_staging = at, at += (size_t)ATLAS_STRIDE * ATLAS_H;
  at = round_up(at, atlas_align);
  off_atlas = at, at += atlas_size;
  data_size = round_up(at, PAGE);
}

static bool make_data(void)
{
  describe_atlas();
  size_t atlas_align = g.tb_storage_align(&atlas_builder);
  plan_data(g.tb_storage_size(&atlas_builder), atlas_align < PAGE ? PAGE : atlas_align);
  data_mem = aligned_alloc(PAGE, data_size);
  if (!data_mem)
    return false;
  /* written once it's a pool (uncached): nothing of it waits in the CPU's cache */
  if (!nvn_make_pool(&data_pool, data_mem, data_size, NVN_POOL_CPU_UNCACHED | NVN_POOL_GPU_CACHED)) {
    free(data_mem);
    data_mem = 0;
    return false;
  }
  memset(data_mem, 0, off_elements);
  data_gpu = g.pool_address(&data_pool);
  write_constants();

  g.tb_storage(&atlas_builder, &data_pool, (ptrdiff_t)off_atlas);
  if (!g.texture_init(&atlas, &atlas_builder))
    return false;
  g.sb_device(&sampler_builder, nvn_device());
  g.sb_defaults(&sampler_builder);
  g.sb_filter(&sampler_builder, FILTER_LINEAR, FILTER_LINEAR);
  g.sb_wrap(&sampler_builder, WRAP_CLAMP_TO_EDGE, WRAP_CLAMP_TO_EDGE, WRAP_CLAMP_TO_EDGE);
  if (!g.sampler_init(&sampler, &sampler_builder))
    return false;
  if (!g.texture_pool_init(&texture_pool, &data_pool, (ptrdiff_t)off_textures, POOL_ENTRIES) ||
      !g.sampler_pool_init(&sampler_pool, &data_pool, (ptrdiff_t)off_samplers, POOL_ENTRIES))
    return false;
  g.texture_pool_register(&texture_pool, our_texture_id, &atlas, 0);
  g.sampler_pool_register(&sampler_pool, our_sampler_id, &sampler);
  atlas_handle = g.texture_handle(nvn_device(), our_texture_id, our_sampler_id);
  return true;
}

static bool load_functions(void)
{
  void **slots = (void **)&g;
  for (unsigned i = 0; i < sizeof(g_names) / sizeof(*g_names); i++) {
    slots[i] = nvn_proc(g_names[i]);
    if (!slots[i]) {
      log_printf("gpu drawing: NVN has no %s", g_names[i]);
      return false;
    }
  }
  device_integer = nvn_proc("nvnDeviceGetInteger");
  return true;
}

bool gpuui_init(void)
{
  if (ready)
    return true;
  if (!load_functions())
    return false;
  if (!make_programs()) {
    log_printf("gpu drawing: the ui shader's programs didn't build");
    return false;
  }
  make_states();
  if (!make_data()) {
    log_printf("gpu drawing: no memory for its buffers and atlas");
    return false;
  }
  ready = true;
  log_printf("gpu drawing ready (%u KiB, shader code %u KiB)", (unsigned)(data_size / 1024),
             (unsigned)(code_size / 1024));
  return true;
}

bool gpuui_ready(void)
{
  return ready;
}

/* --- the glyph atlas ------------------------------------------------------------------------------- */

typedef struct {
  uint32_t codepoint;
  uint16_t em;
  uint8_t face, state; /* 0 empty, 1 placed, 2 nothing to draw */
  uint16_t x, y, w, h;
  int16_t x0, y0;
  float advance;
} atlas_slot_t;

static atlas_slot_t atlas_map[ATLAS_SLOTS];
static int shelf_x, shelf_y, shelf_h, atlas_count;
static int dirty_top = ATLAS_H, dirty_bottom = 0;
static bool atlas_full;

static void atlas_reset(void)
{
  for (int i = 0; i < ATLAS_SLOTS; i++)
    atlas_map[i].state = 0;
  shelf_x = shelf_y = shelf_h = atlas_count = 0;
}

/* the slot for (face, em, cp): found, or the empty one it goes in (state 0); NULL: the map is full */
static atlas_slot_t *atlas_find(uint8_t face, int em, uint32_t cp)
{
  uint32_t h = cp * 2654435761u ^ (uint32_t)em * 40503u ^ (uint32_t)face * 0x9E3779B9u;
  unsigned i = (h ^ h >> 15) & (ATLAS_SLOTS - 1);
  for (int probe = 0; probe < ATLAS_SLOTS; probe++, i = (i + 1) & (ATLAS_SLOTS - 1)) {
    atlas_slot_t *s = &atlas_map[i];
    if (!s->state || (s->codepoint == cp && s->em == em && s->face == face))
      return s;
  }
  return 0;
}

/* where texel (x, y) is in the staging copy (write only: the pool's memory is uncached) */
static uint8_t *staging_at(int x, int y)
{
  return data_mem + off_staging + (size_t)y * ATLAS_STRIDE + (size_t)x * ATLAS_BPP;
}

/* n texels of luminance 1 with no coverage */
static void clear_texels(uint8_t *texels, int n)
{
  for (int i = 0; i < n; i++) {
    texels[ATLAS_BPP * i] = 255;
    texels[ATLAS_BPP * i + 1] = 0;
  }
}

/* room for a w x h image in the slot s (empty), with an empty border, cleared in the staging copy;
 * false: the atlas is full (gpuui_begin starts it afresh next frame) */
static bool atlas_place(atlas_slot_t *s, uint8_t face, int em, uint32_t cp, int w, int h)
{
  int pw = w + 2 * GLYPH_PAD, ph = h + 2 * GLYPH_PAD;
  if (atlas_count >= ATLAS_SLOTS * 3 / 4 || pw > ATLAS_W || ph > ATLAS_H)
    return false;
  if (shelf_x + pw > ATLAS_W) { /* the next shelf */
    shelf_y += shelf_h;
    shelf_x = shelf_h = 0;
  }
  if (shelf_y + ph > ATLAS_H)
    return false;
  *s = (atlas_slot_t){ cp, (uint16_t)em, face, 1, (uint16_t)(shelf_x + GLYPH_PAD), (uint16_t)(shelf_y + GLYPH_PAD),
                       (uint16_t)w, (uint16_t)h, 0, 0, 0 };
  if (!w || !h)
    s->state = 2;
  for (int y = 0; y < ph; y++) /* luminance 1 (so filtering at an edge doesn't darken it), coverage 0 */
    clear_texels(staging_at(shelf_x, shelf_y + y), pw);
  if (shelf_y < dirty_top)
    dirty_top = shelf_y;
  if (shelf_y + ph > dirty_bottom)
    dirty_bottom = shelf_y + ph;
  shelf_x += pw;
  if (ph > shelf_h)
    shelf_h = ph;
  atlas_count++;
  return true;
}

/* A glyph and its shadow as one image: the shadow is the glyph again, black at GPUUI_SHADOW_ALPHA, `d` texels
 * right and down, under the glyph. Where the glyph covers g and the shadow s (both 0..1), the glyph in colour
 * C over the shadow is the colour C g / a at coverage a = g + s (1 - g): so the texel's luminance is g / a
 * and its coverage a, and the quad's colour C times it gives both. */
static int shadow_offset(int em)
{
  float d = em / SHADOW_DIVISOR > 1 ? em / SHADOW_DIVISOR : 1;
  return (int)(d + 0.5f);
}

static const atlas_slot_t *atlas_glyph_shadowed(gf_face_t face, int em, uint32_t cp)
{
  atlas_slot_t *s = atlas_find((uint8_t)face, em, cp);
  if (s && s->state)
    return s;
  const gf_glyph_t *glyph = gamefont_glyph(face, em, cp);
  if (!glyph || !s)
    return 0;
  int d = shadow_offset(em), gw = glyph->w, gh = glyph->h;
  bool empty = !gw || !gh; /* a space: nothing to draw, only its advance */
  if (!atlas_place(s, (uint8_t)face, em, cp, empty ? 0 : gw + d, empty ? 0 : gh + d))
    return 0;
  s->x0 = glyph->x0;
  s->y0 = glyph->y0;
  s->advance = glyph->advance / 64.0f;
  const unsigned shadow_alpha = (unsigned)(GPUUI_SHADOW_ALPHA * 255 + 0.5f);
  for (int y = 0; y < s->h; y++) {
    uint8_t *row = staging_at(s->x, s->y + y);
    for (int x = 0; x < s->w; x++) {
      unsigned glyph_cov = x < gw && y < gh ? glyph->coverage[y * gw + x] : 0;
      unsigned shadow_cov = x >= d && y >= d ? glyph->coverage[(y - d) * gw + (x - d)] * shadow_alpha / 255 : 0;
      unsigned cov = glyph_cov + shadow_cov * (255 - glyph_cov) / 255;
      row[ATLAS_BPP * x] = (uint8_t)(cov ? (glyph_cov * 255 + cov / 2) / cov : 255);
      row[ATLAS_BPP * x + 1] = (uint8_t)cov;
    }
  }
  return s;
}

/* --- a frame ----------------------------------------------------------------------------------------- */

typedef struct {
  float m[12];         /* row-major 3x4 */
  gpu_colour_t c[4];
  float w, h;
  float st[8];         /* the corners' texture coordinates */
  bool textured;
} quad_t;

static quad_t quads[MAX_QUADS];
static int n_quads;
static nvn_texture_t *frame_target;
static nvn_rect_t frame_area;
static int frame_texture_height, frame_slot;
static bool frame_lower_left;

bool gpuui_atlas_resetting(void)
{
  return atlas_full;
}

void gpuui_begin(nvn_texture_t *target, nvn_rect_t area, int texture_height, bool origin_lower_left, int slot)
{
  n_quads = 0;
  frame_target = target;
  frame_area = area;
  frame_texture_height = texture_height;
  frame_lower_left = origin_lower_left;
  frame_slot = slot % SLOTS;
  gamefont_begin_draw();
  if (atlas_full) {
    atlas_reset();
    atlas_full = false;
  }
}

static quad_t *new_quad(void)
{
  if (ready && n_quads < MAX_QUADS)
    return &quads[n_quads++];
  static bool warned;
  if (ready && !warned) {
    log_printf("gpu drawing: more than %d quads in a frame; the rest left out", MAX_QUADS);
    warned = true;
  }
  return 0;
}

static void set_translate(quad_t *q, float x, float y)
{
  static const float identity[12] = { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0 };
  memcpy(q->m, identity, sizeof(identity));
  q->m[3] = x;
  q->m[7] = y;
}

void gpuui_rect(float x, float y, float w, float h, const gpu_colour_t corners[4])
{
  if (w <= 0 || h <= 0)
    return;
  quad_t *q = new_quad();
  if (!q)
    return;
  set_translate(q, x, y);
  memcpy(q->c, corners, sizeof(q->c));
  q->w = w;
  q->h = h;
  q->textured = false;
}

void gpuui_fill(float x, float y, float w, float h, gpu_colour_t colour)
{
  gpu_colour_t corners[4] = { colour, colour, colour, colour };
  gpuui_rect(x, y, w, h, corners);
}

/* the atlas image of slot s as a quad at (x, y) */
static void textured_quad(const atlas_slot_t *s, float x, float y, gpu_colour_t colour)
{
  quad_t *q = new_quad();
  if (!q)
    return;
  set_translate(q, x, y);
  for (int i = 0; i < 4; i++)
    q->c[i] = colour;
  q->w = s->w;
  q->h = s->h;
  float s0 = (float)s->x / ATLAS_W, t0 = (float)s->y / ATLAS_H;
  float s1 = (float)(s->x + s->w) / ATLAS_W, t1 = (float)(s->y + s->h) / ATLAS_H;
  float st[8] = { s0, t0, s1, t0, s0, t1, s1, t1 };
  memcpy(q->st, st, sizeof(st));
  q->textured = true;
}

float gpuui_glyph_shadowed(gf_face_t face, int em, uint32_t cp, float x, float baseline, gpu_colour_t colour)
{
  if (!ready)
    return 0;
  const atlas_slot_t *s = atlas_glyph_shadowed(face, em, cp);
  if (!s) {
    const gf_glyph_t *glyph = gamefont_glyph(face, em, cp);
    if (glyph)
      atlas_full = true; /* there was a glyph, but no room: next frame starts the atlas afresh */
    return glyph ? glyph->advance / 64.0f : 0;
  }
  if (s->state == 1) /* pixel-aligned, as the glyph was rasterised (its shadow is in the image, to its right and below) */
    textured_quad(s, (float)(int)(x + 0.5f) + s->x0, baseline + s->y0, colour);
  return s->advance;
}

static void write_element(uint8_t *at, const quad_t *q)
{
  float e[ELEMENT_WORDS] = { 0 };
  memcpy(e, q->m, sizeof(q->m));
  for (int i = 0; i < 4; i++) {
    e[12 + 4 * i] = q->c[i].r;
    e[13 + 4 * i] = q->c[i].g;
    e[14 + 4 * i] = q->c[i].b;
    e[15 + 4 * i] = q->c[i].a;
  }
  e[28] = q->w;
  e[29] = q->h;
  if (q->textured)
    memcpy(&e[32], q->st, sizeof(q->st));
  e[40] = 1; /* the texture matrix: identity */
  e[43] = 1;
  memcpy(at, e, sizeof(e));
}

/* the state a frame's draws start from */
static void bind_frame(nvn_obj_t *cmd, size_t view_at)
{
  g.cmd_blend(cmd, &blend);
  g.cmd_colour(cmd, &colour);
  g.cmd_channels(cmd, &channels);
  g.cmd_multisample(cmd, &multisample);
  g.cmd_polygon(cmd, &polygon);
  g.cmd_depth(cmd, &depth);
  g.cmd_attribs(cmd, 2, attribs);
  g.cmd_streams(cmd, 1, streams);
  g.cmd_vertex_buffer(cmd, 0, data_gpu + off_vertices, VERTEX_BYTES);
  g.cmd_uniform(cmd, STAGE_VERTEX, 1, data_gpu + view_at, UNIFORM_SIZE);
  g.cmd_uniform(cmd, STAGE_VERTEX, 2, data_gpu + off_shadow, MATERIAL_BYTES);
  g.cmd_uniform(cmd, STAGE_FRAGMENT, 4, data_gpu + off_material, MATERIAL_BYTES);
  g.cmd_texture_pool(cmd, &texture_pool);
  g.cmd_sampler_pool(cmd, &sampler_pool);
  g.cmd_texture(cmd, STAGE_FRAGMENT, 8, atlas_handle);
}

/* the rows the frame's new glyphs touched, up before they're drawn */
static void upload_atlas(nvn_obj_t *cmd)
{
  if (dirty_bottom <= dirty_top)
    return;
  g.cmd_copy_stride(cmd, 0);
  nvn_region_t rows = { 0, dirty_top, 0, ATLAS_W, dirty_bottom - dirty_top, 1 };
  g.cmd_copy_to_texture(cmd, data_gpu + off_staging + (nvn_addr_t)dirty_top * ATLAS_STRIDE, &atlas, 0, &rows, 0);
  g.cmd_barrier(cmd, BARRIER_ORDER_PRIMITIVES | BARRIER_ORDER_FRAGMENTS | BARRIER_INVALIDATE_TEXTURE);
  dirty_top = ATLAS_H;
  dirty_bottom = 0;
}

/* the view: the visible area's pixels, y down, to clip space (column-major) */
static void write_view(size_t view_at)
{
  float sw = (float)frame_area.w, sh = (float)frame_area.h;
  float view[16] = { 2 / sw, 0, 0, 0, 0, -2 / sh, 0, 0, 0, 0, 1, 0, -1, 1, 0, 1 };
  memcpy(data_mem + view_at, view, sizeof(view));
}

/* the frame's quads, each one draw with its element bound; stops when command memory runs short */
static void draw_quads(nvn_obj_t *cmd, size_t elements)
{
  int program = -1;
  for (int i = 0; i < n_quads; i++) {
    if (g.cmd_free(cmd) < CMD_RESERVE) {
      log_printf("gpu drawing: out of command memory in a frame of %d quads; the rest left out", n_quads);
      return;
    }
    const quad_t *q = &quads[i];
    int wanted = q->textured ? UI_PROGRAM_TEXTURE : UI_PROGRAM_SOLID;
    if (wanted != program) {
      g.cmd_program(cmd, &programs[wanted], STAGES_GRAPHICS);
      program = wanted;
    }
    size_t at = elements + (size_t)i * ELEMENT_SIZE;
    write_element(data_mem + at, q);
    g.cmd_storage(cmd, STAGE_VERTEX, 6, data_gpu + at, ELEMENT_SIZE);
    g.cmd_draw(cmd, PRIM_TRIANGLE_STRIP, 0, 4);
  }
}

bool gpuui_end(nvn_obj_t *cmd, const void *game_texture_pool, const void *game_sampler_pool)
{
  if (!ready || !n_quads)
    return false;
  upload_atlas(cmd);
  size_t view_at = off_view + (size_t)frame_slot * UNIFORM_SIZE;
  write_view(view_at);
  int vy = frame_lower_left ? frame_texture_height - frame_area.y - frame_area.h : frame_area.y;
  g.cmd_render_enable(cmd, true);
  g.cmd_targets(cmd, 1, &frame_target, 0, 0, 0);
  g.cmd_viewport(cmd, frame_area.x, vy, frame_area.w, frame_area.h);
  g.cmd_scissor(cmd, frame_area.x, vy, frame_area.w, frame_area.h);
  bind_frame(cmd, view_at);
  draw_quads(cmd, off_elements + (size_t)frame_slot * MAX_QUADS * ELEMENT_SIZE);
  /* the game's descriptor pools back, for its next frame's commands */
  if (game_texture_pool)
    g.cmd_texture_pool(cmd, game_texture_pool);
  if (game_sampler_pool)
    g.cmd_sampler_pool(cmd, game_sampler_pool);
  return true;
}
