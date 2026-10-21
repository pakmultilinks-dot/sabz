#!/usr/bin/env python3
"""Overlay PNGs for the ffmpeg-built segments of loop v2."""
from PIL import Image, ImageDraw, ImageFont

ROOT = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals"
FONTS = ROOT + "/battle-live/fonts"
LB = ROOT + "/sabz_cinematic/loop_build"
W, H = 1920, 1080
F700 = lambda s: ImageFont.truetype(FONTS + "/sg-700.ttf", s)

def tracked_w(d, text, font, tr):
    return sum(d.textlength(c, font=font) for c in text) + tr * (len(text) - 1)

def draw_centered(d, y, text, size, tr=3):
    f = F700(size)
    total = tracked_w(d, text, f, tr)
    x = (W - total) / 2
    for ch in text[:-1]:
        d.text((x, y), ch, font=f, fill=(237, 245, 240, 255))
        x += d.textlength(ch, font=f) + tr
    d.text((x, y), text[-1], font=f, fill=(0, 230, 118, 255))

def band(im, top=560):
    px = im.load()
    for yy in range(top, H):
        a = int(205 * ((yy - top) / (H - top)) ** 1.4)
        for xx in range(0, W, 2):
            px[xx, yy] = (3, 8, 6, a)
            px[xx + 1, yy] = (3, 8, 6, a)

for name, text in [("ov_gridlock", "LAHORE SITS IN TRAFFIC."),
                   ("ov_redwait", "FIXED TIMERS CANNOT SEE.")]:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band(im)
    d = ImageDraw.Draw(im)
    draw_centered(d, 800, text, 112)
    im.save(f"{LB}/assets/{name}_v2.png")
    print("wrote", name)

# battle caption (no band; the canvas below the crop is plain ink)
im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
f = F700(62)
txt = "SAME TRAFFIC. TWO CONTROLLERS."
total = tracked_w(d, txt, f, 3)
x = (W - total) / 2
for ch in txt:
    col = (0, 230, 118, 255) if ch == "." else (237, 245, 240, 255)
    d.text((x, 972), ch, font=f, fill=col)
    x += d.textlength(ch, font=f) + 3
im.save(f"{LB}/assets/ov_battle_v2.png")
print("wrote ov_battle_v2")
