/* The game's own UI fonts, loaded from its RomFS and rasterised with stb_truetype: Clarimo UD PE (the
 * menus' type), regular and DemiBold. Nothing of them is in this repository or the release: they're the
 * user's own game files. Adapted from sloperinaGZ's src/ootgz/gamefont.h (GPL-3; master 8c3a940636),
 * without the button glyphs.
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#ifndef GAMEFONT_H
#define GAMEFONT_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
  GF_REGULAR, /* Clarimo UD PE */
  GF_BOLD,    /* Clarimo UD PE DemiBold */
  GF_FACES
} gf_face_t;

typedef struct {
  const uint8_t *coverage; /* w x h, 0..255 */
  int16_t w, h;
  int16_t x0, y0;          /* the bitmap's top-left from the pen, y0 negative above the baseline */
  int16_t advance;         /* in 1/64 pixel */
} gf_glyph_t;

/* once, on the game thread (it reads files): true when every face is ready */
bool gamefont_load(void);
bool gamefont_ready(void);

/* render thread (one thread only). em: the em square in pixels. NULL when the face has no such character, or the cache
 * is full (it starts again at the next gamefont_begin_draw). A glyph stays valid until then. */
const gf_glyph_t *gamefont_glyph(gf_face_t face, int em, uint32_t codepoint);
/* render thread: before drawing a panel (the cache may start afresh here), and after it: false when a
 * glyph was left out for want of room (draw again after gamefont_begin_draw, or another way) */
void gamefont_begin_draw(void);
bool gamefont_draw_complete(void);
/* the em (pixels) whose ascent plus descent is `height` pixels */
int gamefont_em_for_height(gf_face_t face, int height);
/* kerning between two characters, 1/64 pixel */
int gamefont_kern(gf_face_t face, int em, uint32_t left, uint32_t right);
/* the pen advance of a string (1/64 pixel) */
int gamefont_measure(gf_face_t face, int em, const char *s, int n);

#endif
