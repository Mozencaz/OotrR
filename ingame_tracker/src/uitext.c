#include "uitext.h"

#include "sys.h"

#define CAP_HEIGHT_EM 0.66f /* the capitals' height when the font has no 'H' */
#define KERN_UNITS    64.0f /* the font code's units: 1/64 pixel */
#define FP_ROUNDING   0.5f
#define BYTE_MAX      255.0f

type_t type_for(gf_face_t face, int text_fp, float fp)
{
  type_t t = { face, gamefont_em_for_height(face, (int)(text_fp * fp + FP_ROUNDING)), 0 };
  const gf_glyph_t *h = gamefont_glyph(face, t.em, 'H');
  t.cap = h && h->h > 0 ? (float)-h->y0 : t.em * CAP_HEIGHT_EM;
  return t;
}

float text_width_n(const type_t *type, const char *text, int length)
{
  return gamefont_measure(type->face, type->em, text, length) / KERN_UNITS;
}

float text_width(const type_t *type, const char *text)
{
  return text_width_n(type, text, (int)strlen(text));
}

float baseline_in(const type_t *type, float row_top, float row_height)
{
  return (float)(int)(row_top + (row_height + type->cap) / 2 + FP_ROUNDING);
}

gpu_colour_t to_gpu(rgb_t colour, float alpha)
{
  return (gpu_colour_t){ colour.r / BYTE_MAX, colour.g / BYTE_MAX, colour.b / BYTE_MAX, alpha };
}

rgb_t rgb_from_hex(uint32_t hex)
{
  return (rgb_t){ (uint8_t)(hex >> 16), (uint8_t)(hex >> 8), (uint8_t)hex };
}

float draw_text(const type_t *type, const char *text, float x, float baseline, rgb_t colour)
{
  float pen = x;
  for (; *text; text++) {
    unsigned char c = (unsigned char)*text;
    float advance = gpuui_glyph_shadowed(type->face, type->em, c, pen, baseline, to_gpu(colour, 1));
    if (!advance && c != '?')
      advance = gpuui_glyph_shadowed(GF_REGULAR, type->em, '?', pen, baseline, to_gpu(colour, 1));
    pen += advance;
    if (text[1])
      pen += gamefont_kern(type->face, type->em, c, (unsigned char)text[1]) / KERN_UNITS;
  }
  return pen - x;
}
