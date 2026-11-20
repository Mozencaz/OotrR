"""Draw the title screen badge (``src/oot_rando/patching/title_badge.rgba.zlib``).

Run once by hand (needs Pillow and the Windows font Palatino Linotype Bold); the
generator only reads the result: a little header (width, height as u16) and the RGBA
pixels, zlib-compressed. Gold capitals with a dark outline and a soft shadow, as the
"OCARINA OF TIME" line above it, and a small triforce on each side.

    python tools/make_title_badge.py [preview.png]
"""
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT = r'C:\Windows\Fonts\palab.ttf'
WORD = 'RANDOMIZER'
SIZE = 66            # font size in texels (cap height about 46)
TRACKING = 7         # extra space between letters
PAD = 10
OUT = Path(__file__).resolve().parents[1] / 'src' / 'oot_rando' / 'patching' / 'title_badge.rgba.zlib'

GOLD_TOP, GOLD_BOTTOM = (255, 232, 140), (196, 132, 30)
OUTLINE = (40, 22, 4)


def triforce(size):
    """Mask of a triforce ``size`` texels wide."""
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    h = size * 0.866
    top = (size - h) / 2
    draw.polygon([(size / 2, top), (0, top + h), (size, top + h)], fill=255)
    draw.polygon([(size / 4, top + h / 2), (size * 3 / 4, top + h / 2), (size / 2, top + h)], fill=0)
    return mask


def text_mask(font):
    widths = [font.getbbox(c)[2] - font.getbbox(c)[0] for c in WORD]
    ascent, descent = font.getmetrics()
    width = sum(widths) + TRACKING * (len(WORD) - 1)
    mask = Image.new('L', (width + 4, ascent + descent), 0)
    draw = ImageDraw.Draw(mask)
    x = 0
    for c, w in zip(WORD, widths):
        draw.text((x - font.getbbox(c)[0], 0), c, font=font, fill=255)
        x += w + TRACKING
    return mask.crop(mask.getbbox())


def badge():
    font = ImageFont.truetype(FONT, SIZE)
    text = text_mask(font)
    tri = triforce(text.height + 4)
    gap = 18
    width = tri.width * 2 + text.width + 2 * gap + 2 * PAD
    height = max(text.height, tri.height) + 2 * PAD
    width, height = (width + 3) // 4 * 4, (height + 3) // 4 * 4
    shape = Image.new('L', (width, height), 0)
    left = (width - (tri.width * 2 + text.width + 2 * gap)) // 2
    top_text = (height - text.height) // 2
    top_tri = (height - tri.height) // 2
    shape.paste(tri, (left, top_tri), tri)
    shape.paste(text, (left + tri.width + gap, top_text), text)
    shape.paste(tri, (left + tri.width + 2 * gap + text.width, top_tri), tri)
    # Gold vertical gradient over the shape.
    gradient = Image.new('RGB', (1, height))
    for y in range(height):
        t = min(max((y - top_text) / max(text.height, 1), 0), 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(GOLD_TOP, GOLD_BOTTOM)))
    gold = gradient.resize((width, height))
    # Outline (dilated shape) and a soft shadow under it.
    outline = shape.filter(ImageFilter.MaxFilter(5))
    shadow = outline.filter(ImageFilter.GaussianBlur(3)).point(lambda v: v * 0.7)
    shadow = ImageChops.offset(shadow, 2, 3)
    image = Image.new('RGBA', (width, height), OUTLINE + (0,))
    image.putalpha(ImageChops.lighter(outline, shadow))
    image.paste(gold, (0, 0), shape)
    return image


def main(argv):
    image = badge()
    OUT.write_bytes(zlib.compress(struct.pack('<HH', *image.size) + image.tobytes(), 9))
    print(OUT, image.size)
    if argv:
        preview = Image.new('RGBA', image.size, (40, 60, 120, 255))
        preview.alpha_composite(image)
        preview.resize((image.width * 2, image.height * 2), Image.NEAREST).save(argv[0])


if __name__ == '__main__':
    main(sys.argv[1:])
