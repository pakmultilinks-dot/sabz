#!/usr/bin/env python3
"""SABZ monitor loop v2 - animated scene renderer (PIL frames -> ffmpeg).
Renders: sting (150f), beats (243f), results (315f), cta (150f) into seg2/.
Design rules from LOOP_RESEARCH.md: one message per scene, huge type,
dark bg, green accent, animation only where it serves the read."""
import math, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals"
LB = ROOT + "/sabz_cinematic/loop_build"
FONTS = ROOT + "/battle-live/fonts"
W, H, FPS = 1920, 1080, 30
GREEN = (0, 230, 118)
WHITE = (237, 245, 240)
GREY = (127, 174, 143)
BG = (6, 17, 12)

F700 = lambda s: ImageFont.truetype(FONTS + "/sg-700.ttf", s)
F500 = lambda s: ImageFont.truetype(FONTS + "/sg-500.ttf", s)

def tracked_w(draw, text, font, tr):
    return sum(draw.textlength(ch, font=font) for ch in text) + tr * (len(text) - 1)

def draw_tracked(draw, xy, text, font, fill, tr=0, anchor_left=None):
    x, y = xy
    if anchor_left is None:  # centered
        x = (W - tracked_w(draw, text, font, tr)) / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tr
    return x

def ease_out(t):
    return 1 - (1 - t) ** 3

def ease_inout(t):
    return t * t * (3 - 2 * t)

# ---------- shared background: ink with a soft green radial glow ----------
def make_bg():
    small = Image.new("RGB", (480, 270), BG)
    px = small.load()
    cx, cy = 240, 120
    for yy in range(270):
        for xx in range(480):
            d = math.hypot(xx - cx, yy - cy) / 300.0
            g = max(0.0, 1 - d) ** 2
            px[xx, yy] = (BG[0] + int(10 * g), BG[1] + int(38 * g), BG[2] + int(24 * g))
    return small.resize((W, H), Image.BILINEAR)

BGIMG = make_bg()

# glow sprite (radial, RGBA), tintable
def make_glow(size=256, color=(0, 230, 118)):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = im.load()
    c = size / 2
    for yy in range(size):
        for xx in range(size):
            d = math.hypot(xx - c, yy - c) / c
            a = int(255 * max(0.0, 1 - d) ** 2)
            px[xx, yy] = color + (a,)
    return im

GLOW = make_glow()
GLOWS = {(255, 82, 82): make_glow(color=(255, 82, 82)),
         (255, 179, 0): make_glow(color=(255, 179, 0)),
         (0, 230, 118): GLOW}

def paste_glow(base, cx, cy, diameter, alpha_scale, sprite=None):
    g = (sprite or GLOW).resize((diameter, diameter), Image.BILINEAR)
    a = g.split()[3].point(lambda v: int(v * alpha_scale))
    g.putalpha(a)
    base.paste(g, (int(cx - diameter / 2), int(cy - diameter / 2)), g)

def pipe_out(path, frames):
    cmd = ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
           "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "15360", path, "-y"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fr in frames:
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    print("wrote", path)

# ---------- logo + green lamp location ----------
logo = Image.open(ROOT + "/logo.png").convert("RGBA")
lw, lh = logo.size  # 1440x512
lamp = None
px = logo.load()
pts = []
for yy in range(0, lh, 3):
    for xx in range(0, 520, 3):
        r, g, b, a = px[xx, yy]
        if g > 140 and g > r + 60 and g > b + 50:
            pts.append((xx, yy))
if pts:
    lamp = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
else:
    lamp = (256, 320)
print("green lamp centroid in logo coords:", lamp)

# ---------- STING (150f) ----------
def sting_frames():
    scale = 1150 / lw
    logo_s = logo.resize((1150, int(lh * scale)), Image.LANCZOS)
    lx, ly = (W - 1150) // 2, 290
    lampx = lx + lamp[0] * scale
    lampy = ly + lamp[1] * scale
    frames = []
    for i in range(150):
        t = i / FPS
        fr = BGIMG.copy()
        # glow: off while lamp "off", then on with a pulse
        if t > 1.0:
            on = min(1.0, (t - 1.0) / 0.35)
            pulse = 0.78 + 0.22 * math.sin(2 * math.pi * (t - 1.0) / 1.7)
            paste_glow(fr, lampx, lampy, 330, 0.55 * on * pulse)
        fr.paste(logo_s, (lx, ly), logo_s)
        d = ImageDraw.Draw(fr, "RGBA")
        # lamp dimmer at the very start: the light "turns green" at t=1.0
        if t < 1.35:
            dim = int(215 * max(0.0, 1 - (t - 0.85) / 0.5)) if t > 0.85 else 215
            r = 30 * scale * 2
            d.ellipse([lampx - r, lampy - r, lampx + r, lampy + r], fill=(4, 10, 8, dim))
        # pulse rings after turn-on
        for start in (1.15, 1.95):
            lt = t - start
            if 0 <= lt <= 0.85:
                rr = 26 + 120 * ease_out(lt / 0.85)
                a = int(170 * (1 - lt / 0.85))
                d.ellipse([lampx - rr, lampy - rr, lampx + rr, lampy + rr],
                          outline=(0, 230, 118, a), width=5)
        # tagline rises + fades in
        if t > 0.75:
            p = ease_out(min(1.0, (t - 0.75) / 0.7))
            ty = 800 - int(26 * (1 - p))
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            txt = "GREEN MEANS SMART."
            f = F700(96)
            total = tracked_w(ld, txt, f, 4)
            x = (W - total) / 2
            for ch in txt[:-1]:
                ld.text((x, ty), ch, font=f, fill=WHITE + (255,))
                x += ld.textlength(ch, font=f) + 4
            ld.text((x, ty), ".", font=f, fill=GREEN + (255,))
            layer.putalpha(layer.split()[3].point(lambda v: int(v * p)))
            fr.paste(Image.alpha_composite(fr.convert("RGBA"), layer).convert("RGB"),
                     (0, 0))
        frames.append(fr)
    return frames

# ---------- BEATS (3 x 81f) ----------
BEATS = [
    ("CAMERAS COUNT.", (255, 82, 82)),
    ("THE BRAIN DECIDES.", (255, 179, 0)),
    ("ONE ROAD AT A TIME.", GREEN),
]

def beats_frames():
    frames = []
    for bi, (txt, col) in enumerate(BEATS):
        for i in range(81):
            t = i / FPS
            fr = BGIMG.copy()
            d = ImageDraw.Draw(fr, "RGBA")
            # three signal dots at top; this beat's light is on
            cx = W // 2
            for k in range(3):
                dx = cx + (k - 1) * 84
                if k == bi:
                    paste_glow(fr, dx, 268, 190, 0.8, sprite=GLOWS[BEATS[k][1]])
                    d = ImageDraw.Draw(fr, "RGBA")
                    d.ellipse([dx - 24, 268 - 24, dx + 24, 268 + 24], fill=BEATS[k][1] + (255,))
                else:
                    d.ellipse([dx - 24, 268 - 24, dx + 24, 268 + 24],
                              fill=(16, 30, 22, 255), outline=(44, 70, 56, 255), width=3)
            # text: rises and fades in, fades out at the end
            ain = ease_out(min(1.0, t / 0.5))
            aout = 1.0 if t < 2.25 else max(0.0, 1 - (t - 2.25) / 0.45)
            a = min(ain, aout)
            ty = 520 - int(30 * (1 - ain))
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            f = F700(118)
            draw_tracked(ld, (0, ty), txt, f, WHITE + (255,), tr=2)
            if a < 1:
                layer.putalpha(layer.split()[3].point(lambda v: int(v * a)))
            fr = Image.alpha_composite(fr.convert("RGBA"), layer).convert("RGB")
            frames.append(fr)
    return frames

# ---------- RESULTS (3 x 105f) ----------
RESULTS = [
    ("frac", 2, 3, "SCENARIOS WON"),
    ("dec", 7.3, None, "BEST AVG DELAY"),
    ("pct", 47, None, "LESS DELAY IN THE LIVE BATTLE"),
]

def results_frames():
    frames = []
    for kind, target, denom, label in RESULTS:
        for i in range(105):
            t = i / FPS
            fr = BGIMG.copy()
            d = ImageDraw.Draw(fr)
            f = F500(40)
            draw_tracked(d, (0, 168), "RESULTS", f, GREY, tr=10)
            # count-up over 1.5s starting at 0.25s
            p = ease_out(max(0.0, min(1.0, (t - 0.25) / 1.5)))
            if kind == "frac":
                cur = int(round(p * target))
                num = f"{cur}/{denom}"
            elif kind == "dec":
                num = f"{p * target:.1f}s"
            else:
                num = f"{int(round(p * target))}%"
            aout = 1.0 if t < 3.05 else max(0.0, 1 - (t - 3.05) / 0.45)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            draw_tracked(ld, (0, 330), num, F700(330), GREEN + (255,), tr=2)
            draw_tracked(ld, (0, 760), label, F700(58), WHITE + (255,), tr=4)
            if aout < 1:
                layer.putalpha(layer.split()[3].point(lambda v: int(v * aout)))
            fr = Image.alpha_composite(fr.convert("RGBA"), layer).convert("RGB")
            frames.append(fr)
    return frames

# ---------- CTA (150f) ----------
def cta_frames():
    qr = Image.open(ROOT + "/judge_prep/demo_qr.png").convert("L")
    frames = []
    for i in range(150):
        t = i / FPS
        fr = BGIMG.copy()
        d = ImageDraw.Draw(fr, "RGBA")
        ain = ease_out(min(1.0, t / 0.6))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        draw_tracked(ld, (0, 205), "SEE THE LIVE DEMO.", F700(118), WHITE + (255,), tr=2)
        draw_tracked(ld, (0, 345), "RIGHT HERE.", F700(118), GREEN + (255,), tr=2)
        if ain < 1:
            layer.putalpha(layer.split()[3].point(lambda v: int(v * ain)))
        fr = Image.alpha_composite(fr.convert("RGBA"), layer).convert("RGB")
        # QR card fades in from t=0.9
        if t > 0.9:
            qa = ease_inout(min(1.0, (t - 0.9) / 0.6))
            card = Image.new("RGBA", (400, 400), (255, 255, 255, int(255 * qa)))
            q = qr.resize((360, 360), Image.NEAREST).convert("RGBA")
            q.putalpha(q.split()[3].point(lambda v: int(v * qa)) if False else 255)
            tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            td.rounded_rectangle([W // 2 - 200, 585, W // 2 + 200, 985], radius=28,
                                 fill=(255, 255, 255, int(255 * qa)))
            tmp.paste(q, (W // 2 - 180, 605), q)
            draw_tracked(td, (0, 1000), "SCAN TO OPEN THE DEMO", F500(34),
                         (180, 210, 192, int(255 * qa)), tr=4)
            fr = Image.alpha_composite(fr.convert("RGBA"), tmp).convert("RGB")
        frames.append(fr)
    return frames

if __name__ == "__main__":
    which = sys.argv[1]
    out = LB + "/seg2/"
    if which == "sting":
        pipe_out(out + "v2_s1_sting.mp4", sting_frames())
    elif which == "beats":
        pipe_out(out + "v2_s5_beats.mp4", beats_frames())
    elif which == "results":
        pipe_out(out + "v2_s6_results.mp4", results_frames())
    elif which == "cta":
        pipe_out(out + "v2_s7_cta.mp4", cta_frames())
