#!/usr/bin/env python3
"""SABZ 90-second cinematic demo video builder.
Renders frames with PIL, pipes raw video to ffmpeg, muxes numpy-generated audio.
Usage: python3 build_video.py [--preview] [--start S --end E]
"""
import os, sys, math, subprocess, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1920, 1080, 24
DUR = 90
NFRAMES = DUR * FPS
WORK = os.path.expanduser("~/workspace/goals/ai-championship-adaptive-traffic-signals")
FONTDIR = os.path.expanduser("~/.fonts/sabz")

GREEN = (0, 230, 118)
WHITE = (237, 242, 247)
MUTED = (138, 148, 166)
BLUE = (91, 141, 239)
BG = (5, 7, 12)

def font_sg(size, weight=700):
    f = ImageFont.truetype(os.path.join(FONTDIR, "SpaceGrotesk.ttf"), size)
    try: f.set_variation_by_axes([weight])
    except Exception: pass
    return f

def font_inter(size, weight=500):
    f = ImageFont.truetype(os.path.join(FONTDIR, "Inter.ttf"), size)
    try: f.set_variation_by_axes([weight])
    except Exception: pass
    return f

def font_urdu(size):
    return ImageFont.truetype(os.path.join(FONTDIR, "NotoNastaliqUrdu.ttf"), size)

def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def fade_in(frame, f0, f1):
    return smooth((frame - f0) / max(1, f1 - f0))

def fade_out(frame, f0, f1):
    return 1.0 - smooth((frame - f0) / max(1, f1 - f0))

def text_layer(text, font, fill, pad=40):
    """Prerender text to RGBA image."""
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font, direction="rtl" if any("\u0600" <= c <= "\u06FF" for c in text) else "ltr")
    w, h = bbox[2] - bbox[0] + pad * 2, bbox[3] - bbox[1] + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=fill + (255,),
           direction="rtl" if any("\u0600" <= c <= "\u06FF" for c in text) else "ltr")
    return im

def paste_faded(base, overlay, alpha, pos):
    if alpha <= 0: return
    a = max(0, min(1, alpha))
    ov = overlay.copy()
    alpha_ch = ov.getchannel("A").point(lambda v: int(v * a))
    ov.putalpha(alpha_ch)
    base.paste(ov, pos, ov)

def bottom_gradient():
    g = Image.new("L", (1, H), 0)
    px = g.load()
    for y in range(H):
        t = max(0.0, (y - H * 0.45) / (H * 0.55))
        px[0, y] = int(200 * t * t)
    g = g.resize((W, H))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black.putalpha(g)
    return black

def vignette():
    v = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(v)
    d.ellipse((-W * 0.25, -H * 0.25, W * 1.25, H * 1.25), fill=255)
    v = v.filter(ImageFilter.GaussianBlur(220))
    v = v.point(lambda x: 255 - int((255 - x) * 0.55))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black.putalpha(v.point(lambda x: 255 - x))
    return black

class KenBurns:
    def __init__(self, path, scale=1.25):
        im = Image.open(path).convert("RGB")
        # cover 1920x1080 then upscale for pan room
        sw, sh = int(W * scale), int(H * scale)
        r = max(sw / im.width, sh / im.height)
        im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        self.im = im
        self.maxx = im.width - W
        self.maxy = im.height - H
    def frame(self, t, x0=0.5, x1=0.5, y0=0.5, y1=0.5, z0=1.0, z1=1.0):
        """t in 0..1. Returns 1920x1080 RGB."""
        x = (x0 + (x1 - x0) * t) * self.maxx
        y = (y0 + (y1 - y0) * t) * self.maxy
        z = z0 + (z1 - z0) * t
        cw, ch = int(W / z), int(H / z)
        cx = int(x + (W - cw) / 2); cy = int(y + (H - ch) / 2)
        cx = max(0, min(self.im.width - cw, cx)); cy = max(0, min(self.im.height - ch, cy))
        crop = self.im.crop((cx, cy, cx + cw, cy + ch))
        return crop.resize((W, H), Image.LANCZOS).convert("RGBA")

def rounded_rect(d, xy, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

# ---------------- AUDIO ----------------
def build_audio(path):
    sr = 44100
    n = DUR * sr
    t = np.arange(n) / sr
    audio = np.zeros((n, 2))
    # deep pad: 55, 82.5, 110 Hz with slow swell
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * t / 24 + 1.0)
    pad = (np.sin(2*np.pi*55*t) * 0.30 + np.sin(2*np.pi*82.5*t) * 0.18
           + np.sin(2*np.pi*110*t) * 0.12 + np.sin(2*np.pi*165*t) * 0.06)
    pad *= (0.35 + 0.65 * swell) * 0.5
    audio += pad[:, None] * np.array([0.9, 0.9])
    # soft pulse every 1.5s from 8s to 58s
    for ps in np.arange(8, 58, 1.5):
        i0 = int(ps * sr); L = int(0.5 * sr)
        if i0 + L < n:
            env = np.exp(-np.arange(L) / (sr * 0.09))
            kick = np.sin(2 * np.pi * 58 * np.arange(L) / sr) * env * 0.35
            audio[i0:i0+L] += kick[:, None] * np.array([1.0, 1.0])
    # riser 56-60s
    i0, i1 = int(56*sr), int(60*sr)
    L = i1 - i0
    noise = np.random.RandomState(7).randn(L)
    # crude rising sweep: amplitude ramp + pitch via cumulative phase
    ramp = np.linspace(0, 1, L) ** 2
    phase = np.cumsum(np.linspace(200, 1200, L) / sr * 2 * np.pi)
    riser = np.sin(phase) * ramp * 0.25 + noise * ramp * 0.05
    audio[i0:i1] += riser[:, None]
    # hit at 60s
    i0 = int(60*sr); L = int(1.2*sr)
    env = np.exp(-np.arange(L)/(sr*0.25))
    hit = np.sin(2*np.pi*48*np.arange(L)/sr)*env*0.6
    audio[i0:i0+L] += hit[:, None]
    # second-half drive: pulse every 1.0s 60-75s
    for ps in np.arange(61, 75, 1.0):
        i0 = int(ps*sr); L = int(0.4*sr)
        env = np.exp(-np.arange(L)/(sr*0.07))
        kick = np.sin(2*np.pi*62*np.arange(L)/sr)*env*0.30
        audio[i0:i0+L] += kick[:, None]
    # outro pluck at 82s + fade
    i0 = int(82*sr); L = int(2.5*sr)
    env = np.exp(-np.arange(L)/(sr*0.6))
    pluck = (np.sin(2*np.pi*220*np.arange(L)/sr) + 0.4*np.sin(2*np.pi*440*np.arange(L)/sr)
             + 0.2*np.sin(2*np.pi*660*np.arange(L)/sr)) * env * 0.22
    audio[i0:i0+L] += pluck[:, None]
    # master fade out last 4s, fade in first 1s
    fo = int(4*sr); audio[-fo:] *= np.linspace(1, 0, fo)[:, None]
    fi = int(1*sr); audio[:fi] *= np.linspace(0, 1, fi)[:, None]
    # normalize
    peak = np.abs(audio).max()
    audio = audio / peak * 0.85
    import wave
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    print("audio written", path)

# ---------------- SECTIONS ----------------
def build_assets():
    A = {}
    A["logo"] = Image.open(os.path.join(WORK, "logo_video.png")).convert("RGBA")
    A["kb2"] = KenBurns(os.path.join(WORK, "render_cine_2.png"))
    A["kb1"] = KenBurns(os.path.join(WORK, "render_cine_1.png"))
    A["kb3"] = KenBurns(os.path.join(WORK, "render_cine_3.png"))
    A["grad"] = bottom_gradient()
    A["vig"] = vignette()
    sg_big = font_sg(110); sg_med = font_sg(64); sg_sm = font_sg(40)
    it_med = font_inter(44, 500); it_sm = font_inter(32, 500); it_lab = font_inter(28, 600)
    ur_big = font_urdu(120); ur_sm = font_urdu(72)
    A["t"] = {
        "sabz_big": text_layer("SABZ", sg_big, WHITE),
        "urdu_big": text_layer("سبز", ur_big, GREEN),
        "urdu_sm": text_layer("سبز", ur_sm, GREEN),
        "p1a": text_layer("LAHORE LOSES HOURS", sg_med, WHITE),
        "p1b": text_layer("TO TRAFFIC EVERY DAY", sg_med, GREEN),
        "p2a": text_layer("FIXED SIGNALS WASTE GREEN", sg_med, WHITE),
        "p2b": text_layer("ON EMPTY ROADS", sg_med, GREEN),
        "s1": text_layer("AI THAT WATCHES TRAFFIC", sg_med, WHITE),
        "s2": text_layer("AND ADAPTS IN REAL TIME", sg_med, GREEN),
        "h_ngsim": text_layer("TRAINED ON 1M+ REAL NGSIM TRAJECTORIES", it_med, WHITE),
        "h_safe": text_layer("HARD SAFETY: NEVER CUTS GREEN ON APPROACHING CARS", it_med, GREEN),
        "r_title": text_layer("BENCHMARK: AVERAGE DELAY  (LOWER IS BETTER)", sg_sm, WHITE),
        "r_foot": text_layer("2 WINS  \u00b7  0 LOSSES  \u00b7  0 COLLAPSES", sg_sm, GREEN),
        "v1": text_layer("SMART SIGNALS FOR PAKISTAN", sg_med, WHITE),
        "v2": text_layer("DEPLOYED ACROSS LAHORE", sg_med, GREEN),
        "asym": text_layer("ASYMMETRIC RUSH", it_lab, MUTED),
        "school": text_layer("SCHOOL ZONE", it_lab, MUTED),
        "bal": text_layer("BALANCED LOAD", it_lab, MUTED),
        "tie": text_layer("TIE", it_lab, MUTED),
        "win": text_layer("WIN", it_lab, GREEN),
        "sabz_lab": text_layer("SABZ", it_lab, GREEN),
        "act_lab": text_layer("ACTUATED", it_lab, BLUE),
        "n_cam": text_layer("CAMERA", it_lab, WHITE),
        "n_state": text_layer("STATE  18-DIM", it_lab, WHITE),
        "n_brain": text_layer("DQN BRAIN", it_lab, WHITE),
        "n_sig": text_layer("SIGNAL", it_lab, WHITE),
        "h_title": text_layer("HOW IT WORKS", sg_sm, MUTED),
    }
    return A

def draw_diagram(base, A, f):
    """Animated 4-node pipeline, frames 840-1439."""
    cx, cy = W // 2, 400
    nodes = ["n_cam", "n_state", "n_brain", "n_sig"]
    nw, nh, gap = 300, 110, 90
    total_w = 4 * nw + 3 * gap
    x0 = cx - total_w // 2
    d = ImageDraw.Draw(base)
    # connecting line grows
    prog = smooth((f - 860) / 220)
    line_x1 = x0 + total_w * prog
    d.line([(x0, cy), (line_x1, cy)], fill=(0, 230, 118, 160), width=4)
    for i, nk in enumerate(nodes):
        nx = x0 + i * (nw + gap)
        appear = smooth((f - (860 + i * 70)) / 30)
        if appear <= 0: continue
        active = prog * 4 > i + 0.5
        col = GREEN if active else (70, 80, 95)
        box = Image.new("RGBA", (nw + 20, nh + 20), (0, 0, 0, 0))
        db = ImageDraw.Draw(box)
        rounded_rect(db, [10, 10, nw + 10, nh + 10], 22,
                     fill=(13, 18, 30, int(235 * appear)),
                     outline=col + (int(255 * appear),), width=3)
        base.paste(box, (nx - 10, cy - nh // 2 - 10), box)
        paste_faded(base, A["t"][nk], appear, (nx + (nw - A["t"][nk].width) // 2, cy - A["t"][nk].height // 2))

def draw_results(base, A, f):
    d = ImageDraw.Draw(base)
    paste_faded(base, A["t"]["r_title"], fade_in(f, 1450, 1470), ((W - A["t"]["r_title"].width)//2, 130))
    scenarios = [
        ("asym", 5.0, 5.0, "tie", 300),
        ("school", 5.0, 5.3, "win", 480),
        ("bal", 11.9, 11.9, "tie", 660),
    ]
    maxv = 12.5
    bw_max = 560
    for lab, sv, av, res, y in scenarios:
        # grow bars
        p = smooth((f - 1490) / 90)
        # scenario label above the bars (account for 40px layer pad)
        paste_faded(base, A["t"][lab], p, (560, y - 84))
        # SABZ bar (green)
        sw_ = int(bw_max * sv / maxv * p)
        # actuated bar (blue)
        aw_ = int(bw_max * av / maxv * p)
        if p > 0:
            d.rounded_rectangle([560, y, 560 + sw_, y + 44], radius=10, fill=GREEN)
            d.rounded_rectangle([560, y + 58, 560 + aw_, y + 102], radius=10, fill=BLUE)
        if p > 0.85:
            a = fade_in(f, 1560, 1590)
            # mini labels right-aligned, ending before bars start
            sx = A["t"]["sabz_lab"]; ax = A["t"]["act_lab"]
            paste_faded(base, sx, a, (545 - sx.width, y + 4))
            paste_faded(base, ax, a, (545 - ax.width, y + 62))
            # value labels
            vl = text_layer(f"{sv:.1f}s", font_inter(26, 600), WHITE)
            paste_faded(base, vl, a, (570 + sw_ + 12, y + 2))
            vl2 = text_layer(f"{av:.1f}s", font_inter(26, 600), WHITE)
            paste_faded(base, vl2, a, (570 + aw_ + 12, y + 60))
            paste_faded(base, A["t"][res], a, (1180, y + 30))
    paste_faded(base, A["t"]["r_foot"], fade_in(f, 1640, 1680) * fade_out(f, 1770, 1795),
                ((W - A["t"]["r_foot"].width)//2, 880))

def render_frame(f, A):
    base = Image.new("RGBA", (W, H), BG + (255,))
    # ---- 0-8s LOGO INTRO ----
    if f < 192:
        a = fade_in(f, 12, 60)
        if a > 0:
            sc = 0.92 + 0.08 * smooth((f - 12) / 120)
            lw, lh = int(A["logo"].width * sc), int(A["logo"].height * sc)
            logo = A["logo"].resize((lw, lh), Image.LANCZOS)
            paste_faded(base, logo, a, ((W - lw)//2, 300))
            # pulse rings at signal lens: logo 1440x512 placed at y=300
            # signal lens in logo_video: badge x 16..496 (2x of 8..248), lens cx=256, cy=320
            sx = (W - 1440*sc)//2 + 256*sc if False else (W - lw)//2 + int(256 * lw / 1440)
            sy = 300 + int(320 * lh / 512)
            d = ImageDraw.Draw(base)
            for k in range(2):
                rt = ((f - 60 - k * 40) % 90) / 90
                if 0 <= rt <= 1 and f > 60:
                    r = 20 + rt * 130
                    al = int(200 * (1 - rt) * a)
                    d.ellipse([sx-r, sy-r, sx+r, sy+r], outline=(0,230,118,al), width=4)
        ua = fade_in(f, 84, 140)
        if ua > 0:
            u = A["t"]["urdu_big"]
            paste_faded(base, u, ua, ((W - u.width)//2, 830))
        # fade to black
        if f >= 180:
            k = smooth((f-180)/12)
            black = Image.new("RGBA", (W,H), (0,0,0,int(255*k)))
            base = Image.alpha_composite(base, black)
        return base
    # ---- 8-20s PROBLEM ----
    if f < 480:
        t = (f - 192) / 288
        bg = A["kb2"].frame(t, x0=0.3, x1=0.7, z0=1.0, z1=1.12)
        base = Image.alpha_composite(bg, A["grad"])
        base = Image.alpha_composite(base, A["vig"])
        a1 = fade_in(f, 205, 235) * fade_out(f, 320, 345)
        if a1 > 0:
            yoff = int(18 * (1 - smooth((f-205)/30)))
            paste_faded(base, A["t"]["p1a"], a1, ((W-A["t"]["p1a"].width)//2, 700+yoff))
            paste_faded(base, A["t"]["p1b"], a1, ((W-A["t"]["p1b"].width)//2, 790+yoff))
        a2 = fade_in(f, 350, 380) * fade_out(f, 455, 478)
        if a2 > 0:
            yoff = int(18 * (1 - smooth((f-350)/30)))
            paste_faded(base, A["t"]["p2a"], a2, ((W-A["t"]["p2a"].width)//2, 700+yoff))
            paste_faded(base, A["t"]["p2b"], a2, ((W-A["t"]["p2b"].width)//2, 790+yoff))
        return base
    # ---- 20-35s SOLUTION ----
    if f < 840:
        t = (f - 480) / 360
        bg = A["kb1"].frame(t, x0=0.7, x1=0.3, z0=1.05, z1=1.15)
        base = Image.alpha_composite(bg, A["grad"])
        base = Image.alpha_composite(base, A["vig"])
        a = fade_in(f, 495, 525)
        if a > 0:
            s = A["t"]["sabz_big"]
            paste_faded(base, s, a, ((W-s.width)//2, 620))
        a1 = fade_in(f, 540, 570) * fade_out(f, 640, 665)
        if a1 > 0:
            paste_faded(base, A["t"]["s1"], a1, ((W-A["t"]["s1"].width)//2, 780))
        a2 = fade_in(f, 675, 705) * fade_out(f, 810, 835)
        if a2 > 0:
            paste_faded(base, A["t"]["s2"], a2, ((W-A["t"]["s2"].width)//2, 780))
        return base
    # ---- 35-60s HOW IT WORKS ----
    if f < 1440:
        paste_faded(base, A["t"]["h_title"], fade_in(f, 845, 870), ((W-A["t"]["h_title"].width)//2, 150))
        draw_diagram(base, A, f)
        a1 = fade_in(f, 1150, 1180) * fade_out(f, 1260, 1290)
        if a1 > 0:
            paste_faded(base, A["t"]["h_ngsim"], a1, ((W-A["t"]["h_ngsim"].width)//2, 640))
        a2 = fade_in(f, 1300, 1330) * fade_out(f, 1410, 1435)
        if a2 > 0:
            paste_faded(base, A["t"]["h_safe"], a2, ((W-A["t"]["h_safe"].width)//2, 640))
        return base
    # ---- 60-75s RESULTS ----
    if f < 1800:
        draw_results(base, A, f)
        return base
    # ---- 75-90s VISION + OUTRO ----
    t = (f - 1800) / 360
    bg = A["kb3"].frame(t, x0=0.5, x1=0.5, z0=1.0, z1=1.1)
    base = Image.alpha_composite(bg, A["grad"])
    base = Image.alpha_composite(base, A["vig"])
    a1 = fade_in(f, 1820, 1850) * fade_out(f, 1955, 1980)
    if a1 > 0:
        paste_faded(base, A["t"]["v1"], a1, ((W-A["t"]["v1"].width)//2, 700))
    a2 = fade_in(f, 1990, 2020) * fade_out(f, 2075, 2100)
    if a2 > 0:
        paste_faded(base, A["t"]["v2"], a2, ((W-A["t"]["v2"].width)//2, 700))
    if f >= 2100:
        k = smooth((f-2100)/24)
        black = Image.new("RGBA", (W,H), (0,0,0,int(255*k)))
        base = Image.alpha_composite(base, black)
        la = smooth((f-2112)/24)
        if la > 0:
            sc = 0.8
            lw, lh = int(A["logo"].width*sc), int(A["logo"].height*sc)
            logo = A["logo"].resize((lw, lh), Image.LANCZOS)
            paste_faded(base, logo, la, ((W-lw)//2, 380))
            u = A["t"]["urdu_sm"]
            paste_faded(base, u, la, ((W-u.width)//2, 800))
    return base

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=NFRAMES)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()
    if args.preview:
        args.start, args.end = 0, 240
    A = build_assets()
    print("assets ready", flush=True)
    out = args.out or os.path.join(WORK, "sabz_demo_preview.mp4" if args.preview else "sabz_demo_video.mp4")
    wav = "/tmp/sabz_audio.wav"
    if args.no_audio:
        pass
    elif not args.preview:
        build_audio(wav)
    else:
        # 10s silent-ish tone bed for preview
        sr = 44100; n = 10*sr
        t = np.arange(n)/sr
        tone = np.sin(2*np.pi*110*t)*0.1*np.exp(-t/8)
        import wave
        pcm = np.stack([tone, tone], 1)
        pcm = (pcm/pcm.max()*0.5*32767).astype(np.int16)
        with wave.open(wav, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(pcm.tobytes())
    cmd = ["ffmpeg", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-"]
    if not args.no_audio:
        cmd += ["-i", wav]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p"]
    if not args.no_audio:
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [out]
    # audio length: pad/trim to video length
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    nframes = args.end - args.start
    for i, f in enumerate(range(args.start, args.end)):
        frame = render_frame(f, A)
        proc.stdin.write(frame.convert("RGB").tobytes())
        if i % 120 == 0:
            print(f"frame {i}/{nframes}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("wrote", out, os.path.getsize(out)//1024, "KB")

if __name__ == "__main__":
    main()
