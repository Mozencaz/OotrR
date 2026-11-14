/* Drawing on the GPU with the game's own UI shader (uishader.c): quads in their corner colours (the panel,
 * the selection band), glyphs from the game's fonts and the items' icons, alpha-blended over the game's
 * picture in the frame being presented, with no read-back. Used by trackerui.c from the present hook.
 * Adapted from sloperinaGZ's src/ootgz/gpuui.h (GPL-3; master 8c3a940636), without its pictures, icons,
 * shapes, lines and depth-tested layer; the icons' textures follow its later gpuui.c (5287f64: the game's
 * packaged textures, its render-target layer).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef GPUUI_H
#define GPUUI_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "gamefont.h"
#include "nvn.h"

typedef struct { float r, g, b, a; } gpu_colour_t;

/* render thread, once, after the game has a device and uishader_load and gamefont_load have succeeded:
 * false if the GPU path can't be used */
bool gpuui_init(void);
bool gpuui_ready(void);

/* One frame: gpuui_begin, quads in drawing order, gpuui_end records them into cmd (between the caller's
 * BeginRecording and EndRecording). area: the visible part of the target, in its pixels; the quads'
 * coordinates are relative to it. slot: the caller's frame slot (its fence guards our memory for the
 * frame). */
void gpuui_begin(nvn_texture_t *target, nvn_rect_t area, int texture_height, bool origin_lower_left, int slot);
/* whether the next gpuui_begin starts the glyph atlas afresh (it was full): the caller first waits until
 * the GPU is done with the frames in flight, whose copies read the atlas's staging rows */
bool gpuui_atlas_resetting(void);
/* a w x h rectangle at (x, y); corners: (left, top), (right, top), (left, bottom), (right, bottom) */
void gpuui_rect(float x, float y, float w, float h, const gpu_colour_t corners[4]);
void gpuui_fill(float x, float y, float w, float h, gpu_colour_t colour);
/* a glyph with its pen at x and baseline at y, and its shadow under it in the same quad (black at
 * GPUUI_SHADOW_ALPHA, right and down by a whole number of pixels that grows with em); returns its advance
 * in pixels (0 if the face has none) */
#define GPUUI_SHADOW_ALPHA 0.55f
float gpuui_glyph_shadowed(gf_face_t face, int em, uint32_t codepoint, float x, float baseline,
                           gpu_colour_t colour);
/* The items' icons: the game's pictures (ASTC 4x4, in its packaged block-linear layout), each shrunk once on
 * the GPU into a slot of an icon atlas (RGBA16F, premultiplied), so that only one picture's bytes are ever
 * held. */
#define GPUUI_ICONS 40
typedef struct {
  int width, height;
  size_t size;
  uint8_t layout[8];  /* NVNpackagedTextureLayout, as the BNTX stores it */
  uint8_t swizzle[4]; /* NVN's, for r, g, b, a */
} gpuui_picture_t;
/* render thread, after gpuui_init: the atlas, and room for a picture of up to `largest` bytes; false (logged)
 * if NVN can't or there's no memory */
bool gpuui_icons_init(size_t largest);
/* between gpuui_begin and gpuui_end: the memory to read the next picture into, or NULL if none can be shrunk
 * this frame (one goes in every other frame, once the GPU is done with the last) */
uint8_t *gpuui_icon_staging(void);
/* the picture just read into that memory, shrunk into icon `slot` by this frame's commands (before its
 * drawing, so it can be drawn at once); false if NVN won't make a texture of it */
bool gpuui_icon_bake(int slot, const gpuui_picture_t *picture);
/* once every picture is in: the picture memory goes back when the GPU is done with it; true once it has */
bool gpuui_icons_done(void);
bool gpuui_icon_ready(int slot);
/* icon `slot` as a w x h quad at (x, y): its colours times colour's, at its opacity times colour.a */
void gpuui_icon(int slot, float x, float y, float w, float h, gpu_colour_t colour);
/* true if anything was recorded; the game's texture and sampler pools (NULL: leave them) are set back
 * after the frame's drawing */
bool gpuui_end(nvn_obj_t *cmd, const void *game_texture_pool, const void *game_sampler_pool);

#endif
