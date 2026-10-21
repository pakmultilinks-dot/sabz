#!/usr/bin/env python3
"""Render all static assets (cards + overlays) for the SABZ monitor loop."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

ROOT = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals"
OUT = os.path.join(ROOT, "sabz_cinematic/loop_build/assets")
os.makedirs(OUT, exist_ok=True)
FONTS = os.path.join(ROOT, "battle-live/fonts")
W, H = 1920, 1080
INK = (11, 18, 32)
GREEN = (0, 230, 118)
WHITE = (240, 245, 242)
MUTED = (159, 180, 167)
PANEL = (16, 28, 48)

def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

def text_w(draw, s, f, tracking=0):
    w = 0
    for ch in s:
        w += draw.textlength(ch, font=f) + tracking
    return w - tracking if s else 0

def draw_tracked(draw, cx, y, s, f, fill, tracking=0):
    w = text_w(draw, s, f, tracking)
    x = cx - w / 2
    for ch in s:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking
    return w

def centered(draw, cx, y, s, f, fill):
    w = draw.textlength(s, font=f)
    draw.text((cx - w / 2, y), s, font=f, fill=fill)
    return w

def base_card():
    img = Image.new("RGB", (W, H), INK)
    # soft green glow behind centre
    glow = Image.new("RGB", (W, H), INK)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W/2-620, H/2-430, W/2+620, H/2+430], fill=(10, 46, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.blend(img, glow, 0.55)
    return img

# ---------------- TITLE / CLOSE CARD ----------------
def title_card():
    img = base_card()
    d = ImageDraw.Draw(img)
    logo = Image.open(os.path.join(ROOT, "logo.png")).convert("RGBA")
    lw = 1060
    lh = int(logo.height * lw / logo.width)
    logo = logo.resize((lw, lh), Image.LANCZOS)
    img.paste(logo, ((W - lw)//2, 218), logo)
    # GREEN MEANS SMART.  (SMART. in green)
    f = font("sg-700.ttf", 104)
    s1, s2 = "GREEN MEANS ", "SMART."
    w1 = d.textlength(s1, font=f); w2 = d.textlength(s2, font=f)
    x = (W - (w1 + w2)) / 2
    d.text((x, 668), s1, font=f, fill=WHITE)
    d.text((x + w1, 668), s2, font=f, fill=GREEN)
    # subline
    draw_tracked(d, W/2, 838, "SEE THE LIVE DEMO ON THIS TABLE",
                 font("sg-600.ttf", 34), (170, 235, 200), tracking=8)
    img.save(os.path.join(OUT, "card_title.png"))

# ---------------- PROBLEM OVERLAYS ----------------
def problem_overlay(fname, line):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # bottom gradient band
    grad = Image.new("L", (1, 460))
    for i in range(460):
        grad.putpixel((0, i), int(185 * (i / 459) ** 1.4))
    grad = grad.resize((W, 460))
    black = Image.new("RGBA", (W, 460), (0, 0, 0, 255))
    ov.paste(black, (0, H - 460), grad)
    d = ImageDraw.Draw(ov)
    # kicker, left aligned with tracking (manual)
    s = "THE PROBLEM"
    f = font("sg-600.ttf", 32)
    x = 92
    for ch in s:
        d.text((x, 742), ch, font=f, fill=GREEN + (255,))
        x += d.textlength(ch, font=f) + 7
    d.text((90, 796), line, font=font("sg-700.ttf", 100), fill=WHITE + (255,))
    ov.save(os.path.join(OUT, fname))

# ---------------- HOW-IT-WORKS BEAT CARDS ----------------
def icon_camera(d, cx, cy):
    g = GREEN
    d.rounded_rectangle([cx-130, cy-78, cx+130, cy+92], 26, outline=g, width=9)
    d.polygon([(cx-58, cy-78), (cx-30, cy-122), (cx+52, cy-122), (cx+80, cy-78)], outline=g)
    d.line([cx-58, cy-78, cx-30, cy-122, cx+52, cy-122, cx+80, cy-78], fill=g, width=9)
    d.ellipse([cx-52, cy-45, cx+52, cy+59], outline=g, width=9)
    d.ellipse([cx-20, cy-13, cx+20, cy+27], fill=g)
    d.rounded_rectangle([cx+66, cy-58, cx+112, cy-14], 8, outline=g, width=8)

def icon_chip(d, cx, cy):
    g = GREEN
    d.rounded_rectangle([cx-88, cy-88, cx+88, cy+88], 18, outline=g, width=9)
    d.rounded_rectangle([cx-38, cy-38, cx+38, cy+38], 10, outline=g, width=8)
    for t in (-58, 0, 58):
        d.line([cx+t, cy-88, cx+t, cy-128], fill=g, width=9)
        d.line([cx+t, cy+88, cx+t, cy+128], fill=g, width=9)
        d.line([cx-88, cy+t, cx-128, cy+t], fill=g, width=9)
        d.line([cx+88, cy+t, cx+128, cy+t], fill=g, width=9)

def icon_signal(img, cx, cy):
    # green glow behind the lit lamp, composited first
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    yy = cy + 92
    gd.ellipse([cx-62, yy-62, cx+62, yy+62], fill=(0, 230, 118, 130))
    glow = glow.filter(ImageFilter.GaussianBlur(20))
    img.paste(Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([cx-62, cy-150, cx+62, cy+150], 30, outline=GREEN, width=9)
    for i, col in enumerate([(90, 40, 40), (96, 78, 30)]):
        y2 = cy - 92 + i * 92
        d.ellipse([cx-36, y2-36, cx+36, y2+36], outline=col, width=7)
    d.ellipse([cx-36, yy-36, cx+36, yy+36], fill=GREEN)

def beat_card(fname, icon, line):
    img = base_card()
    d = ImageDraw.Draw(img)
    draw_tracked(d, W/2, 96, "HOW IT WORKS", font("sg-600.ttf", 32), GREEN, tracking=9)
    if icon == "signal":
        icon_signal(img, W//2, 400)
    else:
        {"camera": icon_camera, "chip": icon_chip}[icon](d, W//2, 400)
    d = ImageDraw.Draw(img)
    centered(d, W/2, 660, line, font("sg-700.ttf", 92), WHITE)
    img.save(os.path.join(OUT, fname))

def melt_overlay():
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, 460))
    for i in range(460):
        grad.putpixel((0, i), int(185 * (i / 459) ** 1.4))
    grad = grad.resize((W, 460))
    ov.paste(Image.new("RGBA", (W, 460), (0, 0, 0, 255)), (0, H - 460), grad)
    d = ImageDraw.Draw(ov)
    s = "HOW IT WORKS"
    f = font("sg-600.ttf", 32)
    x = 92
    for ch in s:
        d.text((x, 742), ch, font=f, fill=GREEN + (255,))
        x += d.textlength(ch, font=f) + 7
    d.text((90, 796), "QUEUES MELT", font=font("sg-700.ttf", 100), fill=WHITE + (255,))
    ov.save(os.path.join(OUT, "ov_melt.png"))

# ---------------- RESULTS CARD ----------------
def results_card():
    img = base_card()
    d = ImageDraw.Draw(img)
    draw_tracked(d, W/2, 108, "RESULTS", font("sg-600.ttf", 34), GREEN, tracking=10)
    cards = [("2/3", ["SCENARIOS WON"]),
             ("7.3s", ["BEST AVG DELAY"]),
             ("47%", ["LESS DELAY,", "LIVE BATTLE"])]
    cw, chh, gap = 545, 470, 42
    total = cw * 3 + gap * 2
    x0 = (W - total) // 2
    y0 = 318
    for i, (num, labels) in enumerate(cards):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, y0, x + cw, y0 + chh], 24, fill=PANEL, outline=(30, 58, 47), width=2)
        d.rounded_rectangle([x, y0, x + cw, y0 + 10], 5, fill=GREEN)
        fn = font("sg-700.ttf", 168)
        centered(d, x + cw/2, y0 + 74, num, fn, GREEN)
        fl = font("sg-600.ttf", 41)
        ly = y0 + 300
        for lab in labels:
            draw_tracked(d, x + cw/2, ly, lab, fl, WHITE, tracking=2)
            ly += 56
    img.save(os.path.join(OUT, "card_results.png"))

# ---------------- BATTLE CAPTION BAR ----------------
def battle_caption():
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, H - 72, W, H], fill=(7, 13, 24, 255))
    d.ellipse([58, H - 50, 78, H - 30], fill=GREEN + (255,))
    d.text((100, H - 56), "LIVE DEMO: SAME TRAFFIC, TWO CONTROLLERS.",
           font=font("sg-600.ttf", 33), fill=WHITE + (255,))
    ov.save(os.path.join(OUT, "ov_battle.png"))

title_card()
problem_overlay("ov_problem1.png", "LAHORE SITS IN TRAFFIC.")
problem_overlay("ov_problem2.png", "FIXED TIMERS CANNOT SEE.")
beat_card("card_beat1.png", "camera", "CAMERAS COUNT")
beat_card("card_beat2.png", "chip", "DQN BRAIN DECIDES")
beat_card("card_beat3.png", "signal", "ONE ROAD AT A TIME")
melt_overlay()
results_card()
battle_caption()
print("assets rendered:", sorted(os.listdir(OUT)))
