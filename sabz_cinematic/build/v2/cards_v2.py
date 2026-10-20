#!/usr/bin/env python3
"""SABZ cinematic v2 title cards: black, minimal, no em-dashes."""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v2/work/cards"
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
    widths = [draw.textlength(ch, font=font) for ch in text]
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


def line_card(fname, text, size=56):
    img, d = base()
    f = ImageFont.truetype(FL, size)
    asc, desc = f.getmetrics()
    centered(d, W / 2, H / 2 - (asc + desc) / 2, text, f, WHITE)
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
line_card("card_eye.png", "SABZ sees every vehicle.")
line_card("card_brain.png", "18 numbers in. One decision out. Every second.")
line_card("card_decision.png", "Same traffic. Two controllers.")
line_card("card_safety.png", "Hard rule: never cut the green while a car is approaching.", size=48)
stat_card("stat1.png", "2 of 3", "benchmark scenarios won against actuated control")
stat_card("stat2.png", "7.3s", "best average delay")
stat_card("stat3.png", "Up to 47%", "less delay in the live head-to-head battle")
stat_card("stat4.png", "Deep Q-network", "trained by reinforcement learning")
final_card("cardF.png")
print("cards done")
