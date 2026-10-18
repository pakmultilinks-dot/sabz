#!/usr/bin/env python3
"""SABZ Judge Demo - native 60fps desktop demo for the AI Championship.

NOT a web page. A real desktop app: live AI traffic control, side-by-side
SABZ vs fixed-time comparison, same traffic, real trained brain.

Run:  python3 sabz_demo.py
Keys: SPACE pause | R rush hour | 1/2/3 scenario | F toggle right panel |
      +/- sim speed | ESC quit
"""
import os
import sys
import math
import time

import numpy as np
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sabz_rl import load_net, state_vec_from_dict
from sabz_sim2 import (IntersectionV2, PHASES, OTHER, fixed_decide,
                       actuated_decide, MIN_GREEN, MAX_GREEN)

# ---------------------------------------------------------------- palette
INK        = (11, 18, 32)
PANEL      = (15, 23, 41)
PANEL_BD   = (42, 58, 95)
ROAD       = (28, 39, 60)
ROAD_EDGE  = (55, 74, 105)
ROAD_CTR   = (35, 48, 72)
TEXT       = (237, 242, 247)
MUTED      = (139, 155, 180)
GREEN      = (0, 230, 118)
GREEN_DIM  = (0, 110, 58)
AMBER      = (251, 191, 36)
RED        = (248, 113, 113)
WHITE      = (255, 255, 255)
BLACK      = (0, 0, 0)

CAR_COLORS = [
    (205, 205, 210), (45, 45, 52), (190, 70, 70), (70, 130, 210),
    (225, 185, 70), (95, 185, 145), (150, 150, 165), (100, 100, 210),
    (210, 130, 70), (120, 200, 220),
]

# ---------------------------------------------------------------- scenarios
def rates_asymmetric(a, t):
    return 0.25 if a in ("N", "S") else 0.035

def rates_balanced(a, t):
    return 0.22

def rates_school(a, t):
    # school rush shape (the 7-9am peak, always on for demo clarity)
    return 0.30 if a in ("N", "S") else 0.10

SCENARIOS = [
    ("ASYMMETRIC", rates_asymmetric, "heavy N/S, light E/W"),
    ("BALANCED", rates_balanced, "heavy all approaches"),
    ("SCHOOL RUSH", rates_school, "school zone peak"),
]

# ---------------------------------------------------------------- helpers
def load_font(size, bold=False):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass
    return pygame.font.SysFont("sans", size, bold=bold)


def load_mono(size, bold=False):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass
    return pygame.font.SysFont("monospace", size, bold=bold)


def glow_surface(radius, color, alpha=90):
    """Pre-rendered radial glow sprite."""
    size = radius * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        a = int(alpha * (1 - r / radius) ** 1.6)
        pygame.draw.circle(surf, color + (a,), (radius, radius), r)
    return surf


def rounded_rect(surf, rect, color, radius=4):
    pygame.draw.rect(surf, color, rect, border_radius=radius)


# ---------------------------------------------------------------- brain
class Brain:
    """Wraps the trained DQN; records its thinking for the HUD."""

    def __init__(self, net):
        self.net = net
        self.q_hold = 0.0
        self.q_switch = 0.0
        self.decision = "stay"
        self.reason = "warming up"
        self.last_state = None
        self.decisions_made = 0

    def decide(self, state, prio):
        s = state_vec_from_dict(state)
        q, _ = self.net.forward(s)
        q0, q1 = float(q[0]), float(q[1])
        self.q_hold, self.q_switch = q0, q1
        self.last_state = dict(state)
        self.decision = "switch" if q1 > q0 else "stay"
        self.reason = explain(state, q0, q1)
        self.decisions_made += 1
        return self.decision

    @property
    def confidence(self):
        d = abs(self.q_switch - self.q_hold)
        s = abs(self.q_hold) + abs(self.q_switch) + 1e-6
        return min(1.0, d / s * 4.0)


def explain(state, q0, q1):
    ph = state["phase"]
    op = OTHER[ph]
    cur = PHASES[ph]
    oth = PHASES[op]
    cur_q = sum(state["queue"][a] for a in cur)
    oth_q = sum(state["queue"][a] for a in oth)
    cur_ap = sum(state["approaching"][a] for a in cur)
    oth_ap = sum(state["approaching"][a] for a in oth)
    red_wait = state["red_wait"] * 300.0
    ge = state["green_elapsed"]
    if q1 > q0:  # switch
        if red_wait > 45:
            return "%s starving %.0fs: switch now" % (op, red_wait)
        if cur_q == 0 and (oth_q + oth_ap) > 0:
            return "%s clear, %s waiting: switch" % (ph, op)
        if oth_q > cur_q + 2:
            return "%s queue %d beats %s %d: switch" % (op, oth_q, ph, cur_q)
        return "switch: lower predicted delay"
    if cur_q > 0:
        return "%s discharging %d queued: hold" % (ph, cur_q)
    if cur_ap > 0:
        return "%s flow incoming: hold green" % ph
    if ge < MIN_GREEN + 4:
        return "min-green protection: hold"
    return "hold: no demand on %s" % op

# ---------------------------------------------------------------- demo panel
SCALE = 3.0          # px per meter
DRAW_DIST = 120.0    # m, camera range
ROAD_HW = 30         # half road width px
LANE_OFF = 14        # lane center offset px
BOX_H = 22           # intersection box half-size px


class DemoPanel:
    """One side of the split screen: a live sim + all its render state."""

    def __init__(self, decide_fn, label, accent, seed):
        self.decide_fn = decide_fn
        self.label = label
        self.accent = accent
        self.seed = seed
        self.reset()
        # render state
        self.car_smooth = {}     # id(v) -> [x, y, alpha]
        self.particles = []      # [x, y, vx, vy, life, maxlife, color]
        self.prev_served = 0
        self.rush_until = -1.0
        self.flash = 0.0         # rush badge flash timer

    def reset(self):
        self.sim = IntersectionV2(seed=self.seed, safety_on=True)
        self.rush_until = -1.0
        self.car_smooth = {}
        self.car_orient = {}     # id(v) -> 0:N 1:S 2:E 3:W
        self.particles = []
        self.prev_served = 0

    def set_rates(self, rates_fn):
        self.rates_fn = rates_fn

    def effective_rates(self, a, t):
        r = self.rates_fn(a, t)
        if t < self.rush_until:
            r *= 2.2
        return r

    def step(self):
        s = self.sim
        rates = lambda a, t, _s=s, _self=self: _self.effective_rates(a, t)
        s.step(rates, self.decide_fn)
        # particles on newly served vehicles
        new = s.served - self.prev_served
        self.prev_served = s.served
        if new > 0:
            for _ in range(min(new * 3, 12)):
                ang = np.random.uniform(0, 2 * math.pi)
                sp = np.random.uniform(20, 90)
                self.particles.append([
                    0, 0,  # set relative to panel center at draw time
                    math.cos(ang) * sp, math.sin(ang) * sp,
                    1.0, np.random.uniform(0.5, 1.0), GREEN,
                    True,  # centered flag
                ])

    @property
    def avg_delay(self):
        n = max(self.sim.total, 1)
        return self.sim.delay_sum / n

    def signal_state(self):
        """per-approach lamp color: 'G', 'Y', 'R'."""
        s = self.sim
        out = {}
        if s.transitioning:
            ending = OTHER[s.next_phase]
            for a in ("N", "S", "E", "W"):
                out[a] = "Y" if a in PHASES[ending] else "R"
        else:
            for a in ("N", "S", "E", "W"):
                out[a] = "G" if a in PHASES[s.phase] else "R"
        return out

    # -- geometry ------------------------------------------------------
    def vehicle_xy(self, v, cx, cy):
        d = max(v.dist, 0.0) * SCALE + BOX_H
        if v.approach == "N":   # moving down, left-hand traffic: east lane
            return cx + LANE_OFF, cy - d
        if v.approach == "S":   # moving up: west lane
            return cx - LANE_OFF, cy + d
        if v.approach == "E":   # moving left: south lane
            return cx + d, cy + LANE_OFF
        # W: moving right: north lane
        return cx - d, cy - LANE_OFF

    def update_smooth(self, cx, cy):
        seen = set()
        orient_of = {"N": 0, "S": 1, "E": 2, "W": 3}
        for a in ("N", "S", "E", "W"):
            for v in self.sim.veh[a]:
                if v.dist > DRAW_DIST:
                    continue
                vid = id(v)
                seen.add(vid)
                tx, ty = self.vehicle_xy(v, cx, cy)
                if vid in self.car_smooth:
                    rec = self.car_smooth[vid]
                    rec[0] += (tx - rec[0]) * 0.35
                    rec[1] += (ty - rec[1]) * 0.35
                    rec[2] = min(1.0, rec[2] + 0.12)
                else:
                    self.car_smooth[vid] = [tx, ty, 0.0]
                    self.car_orient[vid] = orient_of[a]
        for vid in list(self.car_smooth.keys()):
            if vid not in seen:
                del self.car_smooth[vid]
                self.car_orient.pop(vid, None)
        # particles
        dt = 1.0 / 60.0
        for p in self.particles:
            p[4] -= dt / p[5]
            p[0] += p[2] * dt
            p[1] += p[3] * dt
        self.particles = [p for p in self.particles if p[4] > 0]

    # -- drawing --------------------------------------------------------
    def draw_road(self, surf, px, py, pw, ph, cx, cy):
        surf.fill(PANEL, (px, py, pw, ph))
        # road strips
        pygame.draw.rect(surf, ROAD, (cx - ROAD_HW, py, ROAD_HW * 2, ph))
        pygame.draw.rect(surf, ROAD, (px, cy - ROAD_HW, pw, ROAD_HW * 2))
        # intersection box
        pygame.draw.rect(surf, ROAD_CTR,
                         (cx - BOX_H, cy - BOX_H, BOX_H * 2, BOX_H * 2))
        # edge lines
        for x in (cx - ROAD_HW, cx + ROAD_HW):
            pygame.draw.line(surf, ROAD_EDGE, (x, py), (x, py + ph), 2)
        for y in (cy - ROAD_HW, cy + ROAD_HW):
            pygame.draw.line(surf, ROAD_EDGE, (px, y), (px + pw, y), 2)
        # center dashes per approach
        dash_c = (120, 140, 170)
        for i in range(0, int(DRAW_DIST * SCALE), 26):
            y0 = cy - BOX_H - i
            if y0 > py + 4:
                pygame.draw.line(surf, dash_c, (cx, y0), (cx, y0 - 12), 2)
            y1 = cy + BOX_H + i
            if y1 < py + ph - 4:
                pygame.draw.line(surf, dash_c, (cx, y1), (cx, y1 + 12), 2)
            x0 = cx - BOX_H - i
            if x0 > px + 4:
                pygame.draw.line(surf, dash_c, (x0, cy), (x0 - 12, cy), 2)
            x1 = cx + BOX_H + i
            if x1 < px + pw - 4:
                pygame.draw.line(surf, dash_c, (x1, cy), (x1 + 12, cy), 2)
        # stop lines
        sl = (210, 220, 235)
        pygame.draw.line(surf, sl, (cx - ROAD_HW, cy - BOX_H - 3),
                         (cx + ROAD_HW, cy - BOX_H - 3), 3)
        pygame.draw.line(surf, sl, (cx - ROAD_HW, cy + BOX_H + 3),
                         (cx + ROAD_HW, cy + BOX_H + 3), 3)
        pygame.draw.line(surf, sl, (cx - BOX_H - 3, cy - ROAD_HW),
                         (cx - BOX_H - 3, cy + ROAD_HW), 3)
        pygame.draw.line(surf, sl, (cx + BOX_H + 3, cy - ROAD_HW),
                         (cx + BOX_H + 3, cy + ROAD_HW), 3)
        # crosswalks (zebra)
        zw = (170, 180, 195)
        for k in range(5):
            x = cx - ROAD_HW + 6 + k * 11
            pygame.draw.line(surf, zw, (x, cy - BOX_H - 16), (x, cy - BOX_H - 9), 4)
            pygame.draw.line(surf, zw, (x, cy + BOX_H + 9), (x, cy + BOX_H + 16), 4)
            y = cy - ROAD_HW + 6 + k * 11
            pygame.draw.line(surf, zw, (cx - BOX_H - 16, y), (cx - BOX_H - 9, y), 4)
            pygame.draw.line(surf, zw, (cx + BOX_H + 9, y), (cx + BOX_H + 16, y), 4)

    def draw_signals(self, surf, cx, cy, glows):
        state = self.signal_state()
        spots = {
            "N": (cx + 44, cy - 44),
            "S": (cx - 44, cy + 44),
            "E": (cx + 44, cy + 44),
            "W": (cx - 44, cy - 44),
        }
        for a, (sx, sy) in spots.items():
            lamp = state[a]
            # pole
            pygame.draw.line(surf, (70, 80, 95), (sx, sy + 22), (sx, sy + 44), 4)
            # head
            rounded_rect(surf, (sx - 9, sy - 22, 18, 44), (20, 26, 38), 5)
            colors = {"R": RED, "Y": AMBER, "G": GREEN}
            ys = {"R": sy - 12, "Y": sy, "G": sy + 12}
            for name, yy in ys.items():
                c = colors[name] if lamp == name else (45, 55, 75)
                pygame.draw.circle(surf, c, (sx, yy), 6)
            if lamp in colors:
                g = glows[lamp]
                surf.blit(g, (sx - g.get_width() // 2, sy - g.get_height() // 2),
                          special_flags=pygame.BLEND_ADD)

    def draw_vehicles(self, surf):
        for vid, rec in self.car_smooth.items():
            x, y, alpha = rec
            if alpha <= 0.02:
                continue
            # find approach by nearest lane (cheap orientation guess)
            # orientation stored at spawn: encode in alpha slot? use dict instead
            self._draw_car(surf, x, y, vid, alpha)

    def _draw_car(self, surf, x, y, vid, alpha):
        orient = self.car_orient.get(vid, 0)  # 0:N 1:S 2:E 3:W
        color = CAR_COLORS[vid % len(CAR_COLORS)]
        w, h = (11, 20) if orient in (0, 1) else (20, 11)
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        a = int(255 * alpha)
        # shadow
        sh = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(90 * alpha)),
                            (0, 0, w + 6, h + 6))
        surf.blit(sh, (x - w / 2 - 3, y - h / 2 - 1))
        rounded_rect(body, (0, 0, w, h), color + (a,), 4)
        # windshield (toward front)
        if orient == 0:   ws = (2, h - 7, w - 4, 4)    # moving down, front=bottom
        elif orient == 1: ws = (2, 3, w - 4, 4)        # moving up
        elif orient == 2: ws = (2, 3, 4, h - 6)        # moving left... front=left
        else:            ws = (w - 6, 3, 4, h - 6)     # moving right
        # NOTE: E approach moves left so front is left; W moves right
        rounded_rect(body, ws, (25, 32, 48, a), 2)
        surf.blit(body, (x - w / 2, y - h / 2))
        # headlights (front) + taillights (rear)
        hl = (255, 250, 220, a)
        tl = (255, 60, 60, a)
        r = 2
        if orient == 0:
            pygame.draw.circle(surf, hl, (x - 3, y + h / 2), r)
            pygame.draw.circle(surf, hl, (x + 3, y + h / 2), r)
            pygame.draw.circle(surf, tl, (x - 3, y - h / 2), r)
            pygame.draw.circle(surf, tl, (x + 3, y - h / 2), r)
        elif orient == 1:
            pygame.draw.circle(surf, hl, (x - 3, y - h / 2), r)
            pygame.draw.circle(surf, hl, (x + 3, y - h / 2), r)
            pygame.draw.circle(surf, tl, (x - 3, y + h / 2), r)
            pygame.draw.circle(surf, tl, (x + 3, y + h / 2), r)
        elif orient == 2:  # moving left, front = left
            pygame.draw.circle(surf, hl, (x - w / 2, y - 3), r)
            pygame.draw.circle(surf, hl, (x - w / 2, y + 3), r)
            pygame.draw.circle(surf, tl, (x + w / 2, y - 3), r)
            pygame.draw.circle(surf, tl, (x + w / 2, y + 3), r)
        else:  # moving right
            pygame.draw.circle(surf, hl, (x + w / 2, y - 3), r)
            pygame.draw.circle(surf, hl, (x + w / 2, y + 3), r)
            pygame.draw.circle(surf, tl, (x - w / 2, y - 3), r)
            pygame.draw.circle(surf, tl, (x - w / 2, y + 3), r)

    def draw_particles(self, surf, cx, cy):
        for p in self.particles:
            life = max(p[4], 0.0)
            a = int(200 * life)
            x = cx + p[0] if p[7] else p[0]
            y = cy + p[1] if p[7] else p[1]
            pygame.draw.circle(surf, p[6] + (a,), (int(x), int(y)), 3)

# ---------------------------------------------------------------- HUD
class Fonts:
    def __init__(self):
        self.title = load_font(44, bold=True)
        self.big = load_font(30, bold=True)
        self.med = load_font(20, bold=True)
        self.small = load_font(15)
        self.small_b = load_font(15, bold=True)
        self.tiny = load_font(12)
        self.mono = load_mono(26, bold=True)
        self.mono_s = load_mono(15, bold=True)


def draw_panel_chrome(surf, fnt, panel, px, py, pw, ph, is_ai, brain,
                      sim_time, rush_active):
    # border
    pygame.draw.rect(surf, PANEL_BD, (px, py, pw, ph), 2)
    # header
    hx, hy, hh = px, py, 56
    pygame.draw.rect(surf, (20, 30, 52), (hx, hy, pw, hh))
    name = "SABZ AI BRAIN" if is_ai else panel.label
    ncol = GREEN if is_ai else AMBER
    surf.blit(fnt.med.render(name, True, ncol), (hx + 14, hy + 8))
    sub = "deep q-network - live" if is_ai else "25s fixed cycle"
    surf.blit(fnt.tiny.render(sub, True, MUTED), (hx + 14, hy + 32))
    # live delay, big, right side of header
    d = panel.avg_delay
    dcol = GREEN if (is_ai and d < 12) or (not is_ai) else TEXT
    dtxt = fnt.mono.render("%.1fs" % d, True, dcol)
    surf.blit(dtxt, (hx + pw - dtxt.get_width() - 14, hy + 6))
    surf.blit(fnt.tiny.render("avg delay / veh", True, MUTED),
              (hx + pw - 118, hy + 36))
    # footer stats
    fy = py + ph - 104
    pygame.draw.rect(surf, (20, 30, 52), (px, fy, pw, 104))
    s = panel.sim
    stats = [
        ("served", str(s.served)),
        ("on road", str(sum(len(s.veh[a]) for a in ("N", "S", "E", "W")))),
        ("phase", s.phase + (" ~" if s.transitioning else "")),
        ("green", "%.0fs" % s.green_elapsed),
        ("clock", "%d:%02d" % (int(s.t // 60), int(s.t % 60))),
    ]
    x = px + 14
    for k, v in stats:
        surf.blit(fnt.tiny.render(k, True, MUTED), (x, fy + 10))
        surf.blit(fnt.small_b.render(v, True, TEXT), (x, fy + 28))
        x += 108
    # phase timer bar
    bar_x, bar_y, bar_w = px + 14, fy + 62, pw - 28
    pygame.draw.rect(surf, (35, 48, 72), (bar_x, bar_y, bar_w, 8))
    frac = min(s.green_elapsed / MAX_GREEN, 1.0)
    pcol = GREEN if not s.transitioning else AMBER
    if s.transitioning:
        frac = 1.0 - s.trans_left / 5.0
    pygame.draw.rect(surf, pcol, (bar_x, bar_y, int(bar_w * frac), 8))
    # brain thinking box (AI panel only)
    if is_ai and brain is not None:
        bx, by, bw, bh = px + 14, fy - 118, pw - 28, 108
        pygame.draw.rect(surf, (13, 20, 36), (bx, by, bw, bh))
        pygame.draw.rect(surf, GREEN_DIM, (bx, by, bw, bh), 1)
        surf.blit(fnt.tiny.render("BRAIN THINKING", True, GREEN),
                  (bx + 10, by + 6))
        # Q bars
        q0, q1 = brain.q_hold, brain.q_switch
        mx = max(abs(q0), abs(q1), 1e-6)
        for i, (qq, nm, col) in enumerate(
                ((q0, "HOLD", (120, 160, 220)), (q1, "SWITCH", GREEN))):
            yy = by + 28 + i * 24
            surf.blit(fnt.tiny.render(nm, True, MUTED), (bx + 10, yy))
            bw2 = int(150 * abs(qq) / mx)
            pygame.draw.rect(surf, (35, 48, 72), (bx + 80, yy, 150, 12))
            pygame.draw.rect(surf, col, (bx + 80, yy, bw2, 12))
            surf.blit(fnt.tiny.render("%.2f" % qq, True, TEXT),
                      (bx + 238, yy))
        dec = brain.decision.upper()
        dcol = GREEN if brain.decision == "switch" else (120, 160, 220)
        surf.blit(fnt.small_b.render(dec, True, dcol), (bx + 330, by + 30))
        surf.blit(fnt.tiny.render("conf %.0f%%" % (brain.confidence * 100),
                                  True, MUTED), (bx + 330, by + 52))
        # reason (truncate)
        rs = brain.reason[:52]
        surf.blit(fnt.tiny.render(rs, True, TEXT), (bx + 10, by + 82))
    # rush badge
    if rush_active:
        if int(time.time() * 3) % 2 == 0:
            rb = fnt.small_b.render("RUSH HOUR x2.2", True, BLACK)
            bg = pygame.Surface((rb.get_width() + 16, 26))
            bg.fill(AMBER)
            bg.blit(rb, (8, 4))
            surf.blit(bg, (px + pw - bg.get_width() - 12, py + 64))


def draw_topbar(surf, fnt, scen_name, scen_desc, speed, paused, logo_img,
                urdu_img):
    pygame.draw.rect(surf, (8, 14, 26), (0, 0, 1600, 64))
    pygame.draw.line(surf, PANEL_BD, (0, 64), (1600, 64), 2)
    if logo_img:
        surf.blit(logo_img, (12, 10))
    surf.blit(fnt.med.render("SABZ  JUDGE DEMO", True, TEXT), (64, 8))
    surf.blit(fnt.tiny.render("AI adaptive traffic signals - live",
                              True, MUTED), (64, 34))
    mid = "%s  -  %s" % (scen_name, scen_desc)
    mt = fnt.small_b.render(mid, True, GREEN)
    surf.blit(mt, (800 - mt.get_width() // 2, 14))
    if urdu_img:
        surf.blit(urdu_img, (800 + mt.get_width() // 2 + 12, 10))
    right = "SPACE pause  R rush  1/2/3 scenario  F right-panel  +/- speed"
    rt = fnt.tiny.render(right, True, MUTED)
    surf.blit(rt, (1600 - rt.get_width() - 14, 16))
    st = "PAUSED" if paused else "LIVE %dx" % speed
    sc = AMBER if paused else GREEN
    stt = fnt.small_b.render(st, True, sc)
    surf.blit(stt, (1600 - stt.get_width() - 14, 36))


def draw_title(surf, fnt, logo_big, urdu_big, frame):
    surf.fill(BLACK)
    a = min(1.0, frame / 40.0)
    if logo_big:
        lg = logo_big.copy()
        lg.set_alpha(int(255 * a))
        surf.blit(lg, (800 - lg.get_width() // 2, 220))
    if urdu_big:
        u = urdu_big.copy()
        u.set_alpha(int(255 * a))
        surf.blit(u, (800 - u.get_width() // 2, 470))
    t3 = fnt.small.render("judge demo - live AI vs fixed-time control",
                          True, MUTED)
    t3.set_alpha(int(255 * a))
    surf.blit(t3, (800 - t3.get_width() // 2, 620))
    if frame > 120:
        t4 = fnt.tiny.render("press any key", True, MUTED)
        if int(frame / 20) % 2 == 0:
            surf.blit(t4, (800 - t4.get_width() // 2, 700))

# ---------------------------------------------------------------- main
def main():
    pygame.init()
    pygame.display.set_caption("SABZ - Judge Demo")
    W, H = 1600, 900
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    fnt = Fonts()

    # assets
    def load_img(name, h):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            return None
        img = pygame.image.load(p).convert_alpha()
        w = int(img.get_width() * h / img.get_height())
        return pygame.transform.smoothscale(img, (w, h))

    logo_small = load_img("logo-dark.png", 44)
    logo_big = load_img("logo.png", 200)
    urdu_small = load_img("logo-urdu.png", 40)
    urdu_big = load_img("logo-urdu.png", 90)

    glows = {
        "G": glow_surface(10, GREEN, 80),
        "Y": glow_surface(10, AMBER, 80),
        "R": glow_surface(10, RED, 80),
    }

    # brain + panels
    net = load_net(os.path.join(HERE, "sabz_dqn_best.npz"))
    brain = Brain(net)
    ai_decide = brain.decide
    right_mode = "fixed"
    right_decide = {"fixed": fixed_decide, "actuated": actuated_decide}

    scen_idx = 0
    base_seed = 1234

    def make_panels():
        pl = DemoPanel(ai_decide, "SABZ AI BRAIN", GREEN, base_seed)
        pr = DemoPanel(right_decide[right_mode],
                       "FIXED TIME" if right_mode == "fixed" else "ACTUATED",
                       AMBER, base_seed)
        pl.set_rates(SCENARIOS[scen_idx][1])
        pr.set_rates(SCENARIOS[scen_idx][1])
        return pl, pr

    panel_l, panel_r = make_panels()

    # geometry
    PX, PY, PW, PH = 8, 72, 784, 820
    QX = 808
    cx_l, cy_l = PX + PW // 2, PY + 56 + (PH - 56 - 104) // 2 + 20
    cx_r, cy_r = QX + PW // 2, PY + 56 + (PH - 56 - 104) // 2 + 20

    paused = False
    speed = 30            # sim-seconds per real second
    acc = 0.0
    title_frames = 0
    in_title = True
    test_frames = int(os.environ.get("SABZ_TEST_FRAMES", "0"))
    frames = 0

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        frames += 1

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if in_title:
                    in_title = False
                    continue
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_r:
                    panel_l.rush_until = panel_l.sim.t + 300
                    panel_r.rush_until = panel_r.sim.t + 300
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    scen_idx = ev.key - pygame.K_1
                    base_seed += 7
                    panel_l, panel_r = make_panels()
                elif ev.key == pygame.K_f:
                    right_mode = "actuated" if right_mode == "fixed" else "fixed"
                    seed = panel_r.seed
                    panel_r = DemoPanel(
                        right_decide[right_mode],
                        "FIXED TIME" if right_mode == "fixed" else "ACTUATED",
                        AMBER, seed)
                    panel_r.set_rates(SCENARIOS[scen_idx][1])
                    # keep sim clock aligned: fast-forward not possible, reset both
                    panel_l.seed = seed
                    panel_l.reset()
                    panel_l.set_rates(SCENARIOS[scen_idx][1])
                elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    speed = min(120, speed * 2)
                elif ev.key == pygame.K_MINUS:
                    speed = max(8, speed // 2)

        if in_title:
            draw_title(screen, fnt, logo_big, urdu_big, title_frames)
            title_frames += 1
            if title_frames > 200:
                in_title = False
            pygame.display.flip()
            if test_frames and frames >= test_frames:
                out = os.environ.get("SABZ_SHOT",
                                     os.path.join(HERE, "demo_test_shot.png"))
                pygame.image.save(screen, out)
                print("shot saved:", out)
                break
            continue

        # --- sim ---
        if not paused:
            acc += dt * speed
            steps = 0
            while acc >= 1.0 and steps < 400:
                panel_l.step()
                panel_r.step()
                acc -= 1.0
                steps += 1

        panel_l.update_smooth(cx_l, cy_l)
        panel_r.update_smooth(cx_r, cy_r)

        # --- draw ---
        screen.fill(INK)
        draw_topbar(screen, fnt, SCENARIOS[scen_idx][0],
                    SCENARIOS[scen_idx][2], speed, paused,
                    logo_small, urdu_small)

        for panel, px, cx, cy, is_ai in (
                (panel_l, PX, cx_l, cy_l, True),
                (panel_r, QX, cx_r, cy_r, False)):
            panel.draw_road(screen, px, PY, PW, PH, cx, cy)
            panel.draw_signals(screen, cx, cy, glows)
            panel.draw_vehicles(screen)
            panel.draw_particles(screen, cx, cy)
            draw_panel_chrome(screen, fnt, panel, px, PY, PW, PH, is_ai,
                              brain if is_ai else None, panel.sim.t,
                              panel.sim.t < panel.rush_until)

        # center divider + savings badge
        pygame.draw.line(screen, PANEL_BD, (800, PY), (800, PY + PH), 2)
        dl, dr = panel_l.avg_delay, panel_r.avg_delay
        save = dr - dl
        badge = fnt.small_b.render("SABZ saves %.1fs/veh" % save, True, BLACK)
        bg = pygame.Surface((badge.get_width() + 20, 30))
        bg.fill(GREEN if save > 0 else AMBER)
        bg.blit(badge, (10, 6))
        screen.blit(bg, (800 - bg.get_width() // 2, PY + PH - 140))

        pygame.display.flip()

        if test_frames and frames >= test_frames:
            out = os.environ.get("SABZ_SHOT",
                                 os.path.join(HERE, "demo_test_shot.png"))
            pygame.image.save(screen, out)
            print("shot saved:", out)
            break

    pygame.quit()


if __name__ == "__main__":
    main()
