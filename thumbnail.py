"""Thumbnail for the YouTube autopilot — Pillow only.

1280x720: first scene image darkened with a bottom gradient, thumbnail text
in huge bold white with black stroke (first word in yellow for pop).
Font: DejaVuSans-Bold (present on Ubuntu runners and this VM).
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

W, H = 1280, 720
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _wrap(text, font, draw, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(bg_image, text, out_path):
    img = Image.open(bg_image).convert("RGB")
    img = img.resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.55)
    img = ImageEnhance.Color(img).enhance(0.85)
    overlay = Image.new("L", (W, H), 0)
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, H - 420, W, H], fill=200)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, overlay)
    draw = ImageDraw.Draw(img)
    font = _font(150)
    lines = _wrap(text.upper(), font, draw, W - 120)
    while len(lines) > 2 and font.size > 80:
        font = _font(font.size - 10)
        lines = _wrap(text.upper(), font, draw, W - 120)
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + 20 * (len(lines) - 1)
    y = H - total_h - 60
    for li, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        x = (W - w) / 2
        fill = (255, 210, 0) if li == 0 else (255, 255, 255)
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=6, stroke_fill=(0, 0, 0))
        y += draw.textbbox((0, 0), line, font=font)[3] + 20
    img.save(out_path, "JPEG", quality=90)
    print("Wrote thumbnail %s" % out_path)
    return out_path


if __name__ == "__main__":
    import sys
    make_thumbnail(sys.argv[1], sys.argv[2], sys.argv[3])
