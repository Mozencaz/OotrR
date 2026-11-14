/* Drawing on the GPU with the game's own UI shader (uishader.c): quads in their corner colours (the panel,
 * the selection band) and glyphs from the game's fonts, alpha-blended over the game's picture in the
 * frame being presented, with no read-back. Used by gameui.c from the present hook.
 * Adapted from sloperinaGZ's src/ootgz/gpuui.h (GPL-3; master 8c3a940636), without its pictures, icons,
 * shapes, lines and depth-tested layer.
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
/* true if anything was recorded; the game's texture and sampler pools (NULL: leave them) are set back
 * after the frame's drawing */
bool gpuui_end(nvn_obj_t *cmd, const void *game_texture_pool, const void *game_sampler_pool);

#endif
