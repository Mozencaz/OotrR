/* Text in the game's UI font on the GPU drawing (gpuui.c): sizes in screen pixels, measured and placed the way
 * the game's own menus do. Adapted from sloperinaGZ's menu in its game style (src/ootgz/nativeui.c, GPL-3;
 * master 8c3a940636) through ocarinaMIDI's gameui.c (c599fa5). */
#ifndef UITEXT_H
#define UITEXT_H

#include <stdint.h>

#include "gamefont.h"
#include "gpuui.h"

typedef struct { uint8_t r, g, b; } rgb_t;

typedef struct {
  gf_face_t face;
  int em;
  float cap; /* the capitals' height in pixels */
} type_t;

/* A face at `text_fp` font pixels, `fp` screen pixels each. */
type_t type_for(gf_face_t face, int text_fp, float fp);
float text_width(const type_t *type, const char *text);
/* The width of the first `length` characters. */
float text_width_n(const type_t *type, const char *text, int length);
/* The baseline that centres the capitals in a row. */
float baseline_in(const type_t *type, float row_top, float row_height);
gpu_colour_t to_gpu(rgb_t colour, float alpha);
rgb_t rgb_from_hex(uint32_t hex);
/* The text with its pen at x on the baseline, kerned; returns its width. */
float draw_text(const type_t *type, const char *text, float x, float baseline, rgb_t colour);

#endif
