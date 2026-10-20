#!/usr/bin/env python3
"""SABZ final video: title / problem / results / close cards. 1920x1080."""
from PIL import Image, ImageDraw, ImageFont

B = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_video/build"
FONTS = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/battle-live/fonts"
W, H = 1920, 1080
BG = (11, 15, 20)          # #0B0F14
PANEL = (16, 22, 30)       # #10161E
BORDER = (35, 45, 61)      # #232D3D
GREEN = (0, 230, 118)      # #00E676
GREEN_DK = (4, 20, 10)
RED = (255, 90, 90)
WHITE = (232, 234, 240)
MUTED = (154, 163, 178)

def f(name, size):
    return ImageFont.truetype(f"{FONTS}/{name}", size)

def tracked(draw, xy, text, font, fill, tracking=0, anchor_left=True):
    x, y = xy
    total = 0
    widths = []
    for ch in text:
        wch = draw.textlength(ch, font=font)
        widths.append(wch)
        total += wch + tracking
    total -= tracking if text else 0
    start = x if anchor_left else x - total / 2
    cx = start
    for ch, wch in zip(text, widths):
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += wch + tracking
    return total

def tracked_center(draw, cx, y, text, font, fill, tracking=0):
    return tracked(draw, (cx, y), text, font, fill, tracking, anchor_left=False)

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def rrect(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)

# ---------------------------------------------------------------- CARD 1: TITLE
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
# subtle grid dots
for gx in range(60, W, 60):
    for gy in range(60, H, 60):
        d.ellipse([gx, gy, gx + 3, gy + 3], fill=(20, 27, 38))
# S mark
ms = 170
mx, my = W // 2 - ms // 2, 250
rrect(d, [mx, my, mx + ms, my + ms], 36, fill=GREEN)
sf = f("sg-700.ttf", 118)
tw = d.textlength("S", font=sf)
d.text((W // 2 - tw / 2, my + 16), "S", font=sf, fill=GREEN_DK)
# SABZ
tracked_center(d, W // 2, 480, "SABZ", f("sg-700.ttf", 210), WHITE, tracking=26)
# rule
d.rectangle([W // 2 - 130, 745, W // 2 + 130, 751], fill=GREEN)
tracked_center(d, W // 2, 790, "AI TRAFFIC CONTROL FOR LAHORE", f("sg-500.ttf", 37), MUTED, tracking=10)
img.save(f"{B}/card_title.png")

# ---------------------------------------------------------------- CARD 2: PROBLEM
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
MX = 150
tracked(d, (MX, 120), "THE PROBLEM", f("sg-600.ttf", 32), RED, tracking=8)
y = 200
for line in ["Lahore's traffic lights", "cannot see the traffic."]:
    d.text((MX, y), line, font=f("sg-700.ttf", 96), fill=WHITE)
    y += 122
y += 36
body = ("Fixed timers switch every 30 seconds, whether the road is empty or "
        "completely jammed. Drivers wait. Fuel burns. The city stands still.")
for line in wrap(d, body, f("sg-400.ttf", 42), W - 2 * MX - 60):
    d.text((MX, y), line, font=f("sg-400.ttf", 42), fill=MUTED)
    y += 62
# chips
chips = ["EVERY 30s: BLIND SWITCH", "NO SENSORS", "NO ADAPTATION"]
cx = MX
cy = 830
for c in chips:
    cf = f("sg-600.ttf", 30)
    cw = d.textlength(c, font=cf) + 64
    rrect(d, [cx, cy, cx + cw, cy + 74], 14, fill=PANEL, outline=(90, 40, 40), width=2)
    d.text((cx + 32, cy + 20), c, font=cf, fill=(255, 150, 150))
    cx += cw + 28
img.save(f"{B}/card_problem.png")

# ---------------------------------------------------------------- CARD 3: RESULTS
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
tracked_center(d, W // 2, 92, "THE RESULTS", f("sg-600.ttf", 34), GREEN, tracking=10)
stats = [
    ("2 of 3", ["benchmark scenarios won", "against actuated control"]),
    ("7.3s", ["best average delay", "in benchmark tests"]),
    ("47%", ["less delay in live battle,", "best recorded run"]),
]
col_w = (W - 300) // 3
for i, (num, labs) in enumerate(stats):
    x0 = 150 + i * col_w
    rrect(d, [x0, 190, x0 + col_w - 30, 470], 18, fill=PANEL, outline=BORDER, width=2)
    nf = f("sg-700.ttf", 118)
    nw = d.textlength(num, font=nf)
    d.text((x0 + (col_w - 30) / 2 - nw / 2, 228), num, font=nf, fill=GREEN)
    ly = 378
    for lab in labs:
        lf = f("sg-400.ttf", 29)
        lw = d.textlength(lab, font=lf)
        d.text((x0 + (col_w - 30) / 2 - lw / 2, ly), lab, font=lf, fill=MUTED)
        ly += 38
# integration flow
tracked_center(d, W // 2, 545, "HOW IT INTEGRATES", f("sg-600.ttf", 28), MUTED, tracking=8)
steps = ["CAMERAS", "VEHICLE COUNT", "18-FEATURE STATE", "DQN BRAIN", "DECISION", "SIGNALS"]
sf = f("sg-600.ttf", 27)
widths = [d.textlength(s, font=sf) + 52 for s in steps]
arrow_gap = 46
total = sum(widths) + arrow_gap * (len(steps) - 1)
x = (W - total) / 2
y = 610
for s, wch in zip(steps, widths):
    rrect(d, [x, y, x + wch, y + 84], 14, fill=PANEL, outline=BORDER, width=2)
    tw = d.textlength(s, font=sf)
    d.text((x + (wch - tw) / 2, y + 27), s, font=sf, fill=WHITE)
    x += wch
    if s != steps[-1]:
        af = f("sg-700.ttf", 30)
        d.text((x + 8, y + 24), "→", font=af, fill=GREEN)
        x += arrow_gap
tracked_center(d, W // 2, 770, "Benchmarks: 3 scenarios, 3 seeds each, full 3600 second simulated runs.",
               f("sg-400.ttf", 27), (110, 120, 138), tracking=1)
img.save(f"{B}/card_results.png")

# ---------------------------------------------------------------- CARD 4: CLOSE
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
for gx in range(60, W, 60):
    for gy in range(60, H, 60):
        d.ellipse([gx, gy, gx + 3, gy + 3], fill=(20, 27, 38))
ms = 92
mx, my = W // 2 - ms // 2, 120
rrect(d, [mx, my, mx + ms, my + ms], 20, fill=GREEN)
sf = f("sg-700.ttf", 62)
tw = d.textlength("S", font=sf)
d.text((W // 2 - tw / 2, my + 10), "S", font=sf, fill=GREEN_DK)
tracked_center(d, W // 2, 238, "SABZ", f("sg-700.ttf", 54), WHITE, tracking=14)
quote = "The people who sit in the traffic should be the people who build the fix."
qy = 400
for line in wrap(d, quote, f("sg-600.ttf", 66), 1300):
    lw = d.textlength(line, font=f("sg-600.ttf", 66))
    d.text(((W - lw) / 2, qy), line, font=f("sg-600.ttf", 66), fill=WHITE)
    qy += 92
d.rectangle([W // 2 - 90, qy + 26, W // 2 + 90, qy + 31], fill=GREEN)
tracked_center(d, W // 2, qy + 62, "TEAM SABZ", f("sg-700.ttf", 46), GREEN, tracking=8)
tracked_center(d, W // 2, qy + 128, "Lahore Garrison University", f("sg-400.ttf", 36), MUTED, tracking=2)
tracked_center(d, W // 2, 972, "GREEN MEANS SMART", f("sg-600.ttf", 30), GREEN, tracking=10)
img.save(f"{B}/card_close.png")
print("cards done")
