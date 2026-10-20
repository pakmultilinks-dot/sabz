#!/usr/bin/env python3
"""SABZ cinematic title cards: black, minimal, no captions, no em-dashes."""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/tmp/cine/cards"
os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
BG = (4, 4, 6)
WHITE = (232, 232, 232)
GRAY = (168, 168, 168)
GREEN = (0, 230, 118)

FB = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FL = "/usr/share/fonts/truetype/noto/NotoSans-Light.ttf"


def spaced(draw, cx, y, text, font, fill, tracking):
    """Draw letter-spaced text centered at cx, top at y. Returns total width."""
    widths = []
    for ch in text:
        w = draw.textlength(ch, font=font)
        widths.append(w)
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    return total


def centered(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)
    return w


def base():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def line_card(fname, text):
    img, d = base()
    f = ImageFont.truetype(FL, 56)
    asc, desc = f.getmetrics()
    centered(d, W / 2, H / 2 - (asc + desc) / 2, text, f, WHITE)
    img.save(f"{OUT}/{fname}")
    print(fname)


def sabz_card(fname):
    img, d = base()
    f_big = ImageFont.truetype(FB, 190)
    spaced(d, W / 2, H / 2 - 190, "SABZ", f_big, GREEN, 26)
    f_sub = ImageFont.truetype(FL, 36)
    spaced(d, W / 2, H / 2 + 70, "ADAPTIVE TRAFFIC AI", f_sub, GRAY, 14)
    img.save(f"{OUT}/{fname}")
    print(fname)


def stat_card(fname, big, label):
    img, d = base()
    f_big = ImageFont.truetype(FB, 120)
    asc, desc = f_big.getmetrics()
    centered(d, W / 2, H / 2 - (asc + desc) - 6, big, f_big, GREEN)
    f_lab = ImageFont.truetype(FL, 40)
    centered(d, W / 2, H / 2 + 26, label, f_lab, WHITE)
    img.save(f"{OUT}/{fname}")
    print(fname)


def final_card(fname):
    img, d = base()
    f_big = ImageFont.truetype(FB, 150)
    spaced(d, W / 2, H / 2 - 230, "SABZ", f_big, GREEN, 22)
    f_mid = ImageFont.truetype(FR, 52)
    centered(d, W / 2, H / 2 - 20, "Green means smart.", f_mid, WHITE)
    f_small = ImageFont.truetype(FL, 32)
    centered(d, W / 2, H / 2 + 90, "Team SABZ", f_small, GRAY)
    centered(d, W / 2, H / 2 + 140, "Lahore Garrison University", f_small, GRAY)
    img.save(f"{OUT}/{fname}")
    print(fname)


line_card("card1.png", "Every day, the light cannot see you.")
line_card("card2.png", "Fixed timers. Blind to traffic.")
sabz_card("card3.png")
stat_card("stat1.png", "2 of 3", "benchmark scenarios won against actuated control")
stat_card("stat2.png", "7.3s", "best average delay")
stat_card("stat3.png", "Up to 47%", "less delay in the live head-to-head battle")
stat_card("stat4.png", "5,506 parameters", "deep Q-network, trained by reinforcement learning")
final_card("cardF.png")
print("cards done")
