"""SABZ cinematic - Blender-rendered 3D assets for the championship demo.

Builds a night-time smart intersection in Blender with animated traffic,
changing signal phases, and a cinematic camera move.

Usage:
    blender --background --python sabz_blender_cinematic.py -- --mode stills
    blender --background --python sabz_blender_cinematic.py -- --mode anim

Outputs (in the work dir):
    render_3d_1.png, render_3d_2.png, render_3d_3.png  (Cycles, 1920x1080)
    sabz_3d_cinematic.mp4                              (Eevee, 1920x1080, 10s)

Units are metres, Z-up.
"""
import bpy
import math
import random
import sys

random.seed(7)

# ------------------------------------------------------------------ args
mode = 'stills'
for i, a in enumerate(sys.argv):
    if a == '--' and i + 1 < len(sys.argv):
        nxt = sys.argv[i + 1]
        if nxt in ('stills', 'anim'):
            mode = nxt

FPS = 24
DUR = 120                      # 5 s animation (render-feasible)
LANE = 3.5
STOP_D = 9.0

# signal timing (frames, 1-indexed like Blender)
PH_NS_GREEN = (1, 60)
PH_NS_YEL   = (61, 72)
PH_ALL_RED  = (73, 84)
PH_EW_GREEN = (85, 120)

# ------------------------------------------------------------------ clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for coll in list(bpy.data.collections):
    if coll.name not in ('Collection',):
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass

# ------------------------------------------------------------------ helpers
def mat(name, color, roughness=0.8, metallic=0.0, emissive=None,
        emission_strength=0.0):
    m = bpy.data.materials.new(name=name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*color, 1.0)
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
        if emissive is not None:
            bsdf.inputs['Emission Color'].default_value = (*emissive, 1.0)
            bsdf.inputs['Emission Strength'].default_value = emission_strength
    return m

def box(name, sx, sy, sz, x, y, z, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if material:
        o.data.materials.append(material)
    return o

def cyl(name, r, depth, x, y, z, material=None, verts=20):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts,
                                       location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    if material:
        o.data.materials.append(material)
    return o

def bez(p0, p1, p2, t):
    u = 1 - t
    return (u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
            u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1])

# ------------------------------------------------------------------ materials
asphalt  = mat('Asphalt', (0.10, 0.11, 0.13), roughness=0.92)
ground_m = mat('Ground', (0.045, 0.05, 0.065), roughness=1.0)
white    = mat('MarkWhite', (0.82, 0.84, 0.87), roughness=0.55)
yellow_m = mat('MarkYellow', (0.80, 0.60, 0.10), roughness=0.55)
walk_m   = mat('Sidewalk', (0.20, 0.21, 0.24), roughness=0.95)
curb_m   = mat('Curb', (0.32, 0.33, 0.36), roughness=0.9)
pole_m   = mat('Pole', (0.07, 0.07, 0.08), roughness=0.45, metallic=0.5)
glass_m  = mat('Glass', (0.04, 0.07, 0.11), roughness=0.08, metallic=0.9)
tire_m   = mat('Tire', (0.03, 0.03, 0.03), roughness=0.9)
rim_m    = mat('Rim', (0.55, 0.58, 0.62), roughness=0.3, metallic=0.9)
head_m   = mat('Headlight', (0.04, 0.04, 0.04), emissive=(0.82, 0.92, 1.0),
               emission_strength=4.0)
tail_m   = mat('Taillight', (0.08, 0.0, 0.0), emissive=(1.0, 0.08, 0.08),
               emission_strength=1.0)
tail_brake_m = mat('TaillightBrake', (0.08, 0.0, 0.0),
                   emissive=(1.0, 0.08, 0.08), emission_strength=4.0)
lamp_m   = mat('LampGlow', (0.0, 0.0, 0.0), emissive=(1.0, 0.72, 0.40),
               emission_strength=5.0)
win_m    = mat('WinGlow', (0.0, 0.0, 0.0), emissive=(1.0, 0.80, 0.50),
               emission_strength=1.6)

# signal lamp materials: each lamp gets its own so we can keyframe emission
def sig_mat(name, rgb):
    return mat(name, (0.02, 0.02, 0.02), roughness=0.4,
               emissive=rgb, emission_strength=0.15)

# ------------------------------------------------------------------ ground & roads
box('Ground', 700, 700, 0.5, 0, 0, -0.25, ground_m)
box('RoadNS', 7, 170, 0.1, 0, 0, 0.0, asphalt)
box('RoadEW', 170, 7, 0.1, 0, 0, 0.0, asphalt)

for x in (-0.18, 0.18):
    box('CY', 0.14, 78, 0.02, x, -46.5, 0.06, yellow_m)
    box('CY', 0.14, 78, 0.02, x, 46.5, 0.06, yellow_m)
    box('CY', 78, 0.14, 0.02, -46.5, x, 0.06, yellow_m)
    box('CY', 78, 0.14, 0.02, 46.5, x, 0.06, yellow_m)
for x in (-3.32, 3.32):
    box('EL', 0.12, 78, 0.02, x, -46.5, 0.06, white)
    box('EL', 0.12, 78, 0.02, x, 46.5, 0.06, white)
    box('EL', 78, 0.12, 0.02, -46.5, x, 0.06, white)
    box('EL', 78, 0.12, 0.02, 46.5, x, 0.06, white)
for i in range(12):
    z0 = -80 + i * 13
    if abs(z0) < 12:
        continue
    box('Dash', 0.14, 3, 0.02, 0, z0, 0.06, white)
    box('Dash', 3, 0.14, 0.02, z0, 0, 0.06, white)

box('Stop', 3.1, 0.55, 0.02, -1.75, -STOP_D, 0.06, white)
box('Stop', 3.1, 0.55, 0.02, 1.75, STOP_D, 0.06, white)
box('Stop', 0.55, 3.1, 0.02, STOP_D, 1.75, 0.06, white)
box('Stop', 0.55, 3.1, 0.02, -STOP_D, -1.75, 0.06, white)

def crosswalk(x0, y0, along_x):
    for i in range(8):
        off = -3 + i * 0.86
        if along_x:
            box('Xwalk', 0.5, 2.6, 0.02, x0 + off, y0, 0.06, white)
        else:
            box('Xwalk', 2.6, 0.5, 0.02, x0, y0 + off, 0.06, white)

crosswalk(0, -12.5, True)
crosswalk(0, 12.5, True)
crosswalk(-12.5, 0, False)
crosswalk(12.5, 0, False)

# sidewalks + curbs
for sx in (1, -1):
    for sy in (1, -1):
        box('Walk', 24, 24, 0.3, sx * 15.5, sy * 15.5, 0.15, walk_m)
# curb strips along roads
for z in (-46.5, 46.5):
    box('Curb', 0.4, 78, 0.35, -3.7, z, 0.17, curb_m)
    box('Curb', 0.4, 78, 0.35, 3.7, z, 0.17, curb_m)
for x in (-46.5, 46.5):
    box('Curb', 78, 0.4, 0.35, x, -3.7, 0.17, curb_m)
    box('Curb', 78, 0.4, 0.35, x, 3.7, 0.17, curb_m)

# ------------------------------------------------------------------ buildings
def building(bx, by, w, d, h, seed):
    rnd = random.Random(seed)
    facade = mat('Fac%d' % seed,
                 (0.08 + rnd.uniform(0, 0.06), 0.09 + rnd.uniform(0, 0.06),
                  0.13 + rnd.uniform(0, 0.06)), roughness=0.9)
    b = box('Bldg%d' % seed, w, d, h, bx, by, h / 2.0, facade)
    # lit windows: fewer, larger (speed optimization)
    cols = max(2, int(w / 5))
    rows = max(2, int(h / 5))
    for ci in range(cols):
        for ri in range(rows):
            if rnd.random() < 0.35:
                wz = 3.0 + ri * 5.0
                if wz > h - 1:
                    continue
                fx = -1 if bx > 0 else 1
                fy = -1 if by > 0 else 1
                if abs(bx) > abs(by):
                    box('Win', 0.06, 2.2, 2.6, bx + fx * (w / 2 + 0.02),
                        by, wz, win_m)
                else:
                    box('Win', 2.2, 0.06, 2.6,
                        bx - w / 2 + (ci + 0.5) * (w / cols),
                        by + fy * (d / 2 + 0.02), wz, win_m)

spots = [(-38, -34, 16, 14, 22), (34, -40, 20, 16, 30), (-40, 36, 18, 18, 16),
         (40, 34, 14, 20, 26), (-62, -8, 16, 22, 34), (62, 6, 18, 16, 20),
         (-8, -64, 22, 16, 28), (10, 62, 16, 18, 18)]
for i, (bx, by, w, d, h) in enumerate(spots):
    building(bx, by, w, d, h, 100 + i)

# ------------------------------------------------------------------ street lamps
def street_lamp(x, y, with_light=False):
    cyl('LPole', 0.12, 7.5, x, y, 3.75, pole_m)
    box('LHead', 0.7, 0.7, 0.25, x, y, 7.4, lamp_m)
    if with_light:
        bpy.ops.object.light_add(type='POINT', location=(x, y, 6.9))
        li = bpy.context.active_object
        li.name = 'LampLight'
        li.data.energy = 900
        li.data.color = (1.0, 0.72, 0.42)
        li.data.shadow_soft_size = 1.2
        li.data.use_shadow = False  # speed: no shadow raytracing on lamps

# only 4 real lights, rest are emissive-only (fast)
for i, (x, y) in enumerate([(-6.5, -11), (6.5, 11), (-6.5, 11), (6.5, -11),
             (-6.5, -30), (6.5, 30), (-30, 6.5), (30, -6.5)]):
    street_lamp(x, y, with_light=(i < 4))

# ------------------------------------------------------------------ traffic signals
# returns dict with lamp materials for animation
signals = []

def signal(x, y, rot_z, group):
    """group 'NS' or 'EW'. Builds pole+arm+head, returns lamp mats."""
    mats = {}
    p = cyl('Pole', 0.14, 6.6, x, y, 3.3, pole_m)
    p.rotation_euler[2] = rot_z
    arm = cyl('Arm', 0.10, 4.6, x, y, 6.3, pole_m)
    arm.rotation_euler = (0, math.pi / 2, rot_z)
    dx, dy = math.cos(rot_z), math.sin(rot_z)
    hx, hy = x + 2.3 * dx, y + 2.3 * dy
    head = box('Head', 0.9, 0.7, 2.5, hx, hy, 5.3, pole_m)
    head.rotation_euler[2] = rot_z
    for j, (cname, rgb) in enumerate(
            [('red', (1.0, 0.14, 0.14)),
             ('yel', (1.0, 0.72, 0.10)),
             ('grn', (0.14, 1.0, 0.36))]):
        m = sig_mat('Sig_%s_%d_%s' % (group, len(signals), cname), rgb)
        lamp = box('Lamp', 0.5, 0.5, 0.42, hx, hy, 5.3 + 0.78 - j * 0.78, m)
        lamp.rotation_euler[2] = rot_z
        # visor hood
        box('Visor', 0.56, 0.56, 0.18, hx, hy, 5.3 + 0.78 - j * 0.78 + 0.28,
            pole_m)
        mats[cname] = m
    signals.append({'group': group, 'mats': mats})

signal(-5.6, -8.2, math.pi, 'NS')
signal(5.6, 8.2, 0.0, 'NS')
signal(8.2, 5.6, -math.pi / 2, 'EW')
signal(-8.2, -5.6, math.pi / 2, 'EW')

def key_emission(material, frame, strength):
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    sock = bsdf.inputs['Emission Strength']
    sock.default_value = strength
    sock.keyframe_insert(data_path='default_value', frame=frame)

ON, OFF = 6.0, 0.12
# NS: green 1-120, yellow 121-144, red 145-240
# EW: red 1-168, green 169-240
sched = {
    'NS': [('grn', 1, 60), ('yel', 61, 72), ('red', 73, 120)],
    'EW': [('red', 1, 84), ('grn', 85, 120)],
}
for sig in signals:
    g = sig['group']
    for cname in ('red', 'yel', 'grn'):
        m = sig['mats'][cname]
        spans = [s for s in sched[g] if s[0] == cname]
        if not spans:
            # always off with keyframes at ends
            key_emission(m, 1, OFF)
            key_emission(m, DUR, OFF)
            continue
        _, f0, f1 = spans[0]
        key_emission(m, 1, OFF)
        if f0 > 1:
            key_emission(m, f0 - 1, OFF)
        key_emission(m, f0, ON)
        key_emission(m, f1, ON)
        if f1 < DUR:
            key_emission(m, f1 + 1, OFF)
            key_emission(m, DUR, OFF)

# ------------------------------------------------------------------ cars
CAR_PAINTS = [(0.72, 0.20, 0.15), (0.14, 0.45, 0.70), (0.75, 0.75, 0.78),
              (0.15, 0.22, 0.30), (0.90, 0.58, 0.06), (0.30, 0.55, 0.35),
              (0.55, 0.25, 0.60), (0.85, 0.85, 0.88)]

def make_car(paint, idx):
    paint_m = mat('Paint%d' % idx, paint, roughness=0.28, metallic=0.8)
    col = bpy.data.collections.new('Car%d' % idx)
    bpy.context.scene.collection.children.link(col)

    def link(o):
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
        return o

    # lower body, hood, trunk, cabin, bumpers, mirrors, wheels, lights
    link(box('Body', 1.82, 3.1, 0.62, 0, -0.35, 0.72, paint_m))
    link(box('Hood', 1.78, 1.05, 0.42, 0, 1.62, 0.78, paint_m))
    link(box('Trunk', 1.78, 0.85, 0.45, 0, -1.95, 0.80, paint_m))
    link(box('Cabin', 1.62, 1.9, 0.60, 0, -0.15, 1.28, glass_m))
    link(box('Roof', 1.66, 1.5, 0.08, 0, -0.15, 1.60, paint_m))
    link(box('BumpF', 1.86, 0.22, 0.34, 0, 2.22, 0.55, pole_m))
    link(box('BumpR', 1.86, 0.22, 0.34, 0, -2.42, 0.55, pole_m))
    link(box('MirL', 0.14, 0.22, 0.12, -0.98, 0.55, 1.18, paint_m))
    link(box('MirR', 0.14, 0.22, 0.12, 0.98, 0.55, 1.18, paint_m))
    wheels = []
    for wx, wy in ((-0.88, 1.35), (0.88, 1.35), (-0.88, -1.35), (0.88, -1.35)):
        w = link(cyl('Wheel', 0.37, 0.30, wx, wy, 0.37, tire_m))
        w.rotation_euler = (0, math.pi / 2, 0)
        rim = link(cyl('Rim', 0.20, 0.32, wx, wy, 0.37, rim_m, verts=10))
        rim.rotation_euler = (0, math.pi / 2, 0)
        wheels.append((w, rim))
    link(box('HL', 0.36, 0.10, 0.20, -0.58, 2.16, 0.80, head_m))
    link(box('HL', 0.36, 0.10, 0.20, 0.58, 2.16, 0.80, head_m))
    tl = link(box('TL', 1.55, 0.08, 0.17, 0, -2.44, 0.84, tail_m))
    return col, wheels, tl

# ---------------- traffic choreography ----------------
# path model: straight lines with bezier turns; car faces direction of travel
SPAWN = 48.0
SPEED = 11.0            # m/s

def approach_spec(appr):
    if appr == 'N':
        return {'lane': (-1.75, 0), 'dir': (0, 1), 'stop': -STOP_D,
                'axis': 1, 'sign': 1, 'group': 'NS'}
    if appr == 'S':
        return {'lane': (1.75, 0), 'dir': (0, -1), 'stop': STOP_D,
                'axis': 1, 'sign': -1, 'group': 'NS'}
    if appr == 'E':
        return {'lane': (0, 1.75), 'dir': (-1, 0), 'stop': STOP_D,
                'axis': 0, 'sign': -1, 'group': 'EW'}
    return {'lane': (0, -1.75), 'dir': (1, 0), 'stop': -STOP_D,
            'axis': 0, 'sign': 1, 'group': 'EW'}

def path_points(appr, move):
    """Return list of (x, y) waypoints from spawn to despawn."""
    A = approach_spec(appr)
    (lx, ly), (dx, dy) = A['lane'], A['dir']
    sx, sy = lx - dx * 0, ly - dy * 0
    # start
    if appr == 'N':
        pts = [(-1.75, -SPAWN)]
    elif appr == 'S':
        pts = [(1.75, SPAWN)]
    elif appr == 'E':
        pts = [(SPAWN, 1.75)]
    else:
        pts = [(-SPAWN, -1.75)]
    # turn geometry
    if move == 'straight':
        if appr == 'N':
            pts += [(-1.75, SPAWN)]
        elif appr == 'S':
            pts += [(1.75, -SPAWN)]
        elif appr == 'E':
            pts += [(-SPAWN, 1.75)]
        else:
            pts += [(SPAWN, -1.75)]
    elif move == 'right':
        if appr == 'N':
            c = [(-1.75, -1.75)]
            for t in [0.25, 0.5, 0.75, 1.0]:
                pts.append(bez((-1.75, -3.5), c[0], (-3.5, -1.75), t))
            pts.append((-SPAWN, -1.75))
        elif appr == 'S':
            c = [(1.75, 1.75)]
            for t in [0.25, 0.5, 0.75, 1.0]:
                pts.append(bez((1.75, 3.5), c[0], (3.5, 1.75), t))
            pts.append((SPAWN, 1.75))
        elif appr == 'E':
            c = [(1.75, 1.75)]
            for t in [0.25, 0.5, 0.75, 1.0]:
                pts.append(bez((3.5, 1.75), c[0], (1.75, 3.5), t))
            pts.append((1.75, SPAWN))
        else:
            c = [(-1.75, -1.75)]
            for t in [0.25, 0.5, 0.75, 1.0]:
                pts.append(bez((-3.5, -1.75), c[0], (-1.75, -3.5), t))
            pts.append((-1.75, -SPAWN))
    else:  # left
        if appr == 'N':
            for t in [0.2, 0.4, 0.6, 0.8, 1.0]:
                pts.append(bez((-1.75, -3.5), (0, 0), (3.5, 1.75), t))
            pts.append((SPAWN, 1.75))
        elif appr == 'S':
            for t in [0.2, 0.4, 0.6, 0.8, 1.0]:
                pts.append(bez((1.75, 3.5), (0, 0), (-3.5, -1.75), t))
            pts.append((-SPAWN, -1.75))
        elif appr == 'E':
            for t in [0.2, 0.4, 0.6, 0.8, 1.0]:
                pts.append(bez((3.5, 1.75), (0, 0), (-1.75, 3.5), t))
            pts.append((-1.75, SPAWN))
        else:
            for t in [0.2, 0.4, 0.6, 0.8, 1.0]:
                pts.append(bez((-3.5, -1.75), (0, 0), (1.75, -3.5), t))
            pts.append((1.75, -SPAWN))
    return pts

def cumdist(pts):
    d = [0.0]
    for i in range(1, len(pts)):
        d.append(d[-1] + math.hypot(pts[i][0] - pts[i-1][0],
                                    pts[i][1] - pts[i-1][1]))
    return d

def stop_dist(pts, appr):
    """arc distance of the stop line along the path"""
    A = approach_spec(appr)
    d = cumdist(pts)
    if A['axis'] == 1:  # NS road: stop on y
        target, idx = A['stop'], 1
    else:
        target, idx = A['stop'], 0
    best, bi = 1e9, 0
    for i, p in enumerate(pts):
        dd = abs(p[idx] - target)
        if dd < best:
            best, bi = dd, i
    return d[bi]

def green_intervals(group):
    if group == 'NS':
        return [(1, 60)]
    return [(85, 120)]

def car_pos_at(pts, dists, total, s):
    s = max(0.0, min(total, s))
    i = 0
    while i < len(dists) - 2 and dists[i + 1] < s:
        i += 1
    seg = dists[i + 1] - dists[i]
    t = 0.0 if seg == 0 else (s - dists[i]) / seg
    x = pts[i][0] + t * (pts[i + 1][0] - pts[i][0])
    y = pts[i][1] + t * (pts[i + 1][1] - pts[i][1])
    # heading from segment direction
    ang = math.degrees(math.atan2(pts[i + 1][0] - pts[i][0],
                                  pts[i + 1][1] - pts[i][1]))
    return x, y, ang

def simulate(appr, move, spawn_frame):
    """Return dict frame -> (x, y, heading_deg, braking)."""
    pts = path_points(appr, move)
    dists = cumdist(pts)
    total = dists[-1]
    A = approach_spec(appr)
    sd = stop_dist(pts, appr)
    greens = green_intervals(A['group'])
    dt = 1.0 / FPS
    s = 0.0
    v = SPEED
    out = {}
    f = spawn_frame
    while f <= DUR and s < total:
        # am I allowed through the stop line?
        allowed = any(g0 <= f <= g1 for g0, g1 in greens)
        dist_to_stop = sd - s
        braking = False
        if not allowed and dist_to_stop > 0 and dist_to_stop < 25:
            # decelerate to stop 1.2m before line
            want = max(0.0, (dist_to_stop - 1.2)) / 25.0
            v = min(v, SPEED * want + 0.5)
            braking = v < SPEED * 0.9
            if dist_to_stop <= 1.3:
                v = 0.0
        elif allowed or dist_to_stop <= 0:
            v = min(SPEED, v + 30 * dt)  # accelerate back
        else:
            v = SPEED
        s += v * dt
        x, y, ang = car_pos_at(pts, dists, total, s)
        out[f] = (x, y, ang, braking)
        f += 1
    return out

# choreography: (approach, move, spawn_frame)
PLAN = [
    ('N', 'straight', 1), ('N', 'straight', 15), ('N', 'right', 30),
    ('S', 'straight', 5), ('S', 'left', 25), ('S', 'straight', 40),
    ('E', 'straight', 20), ('E', 'straight', 35), ('W', 'straight', 28),
    ('W', 'left', 45), ('E', 'right', 55),
    ('E', 'straight', 75), ('W', 'straight', 80), ('E', 'straight', 95),
    ('W', 'right', 100),
]

car_cols = []
for idx, (appr, move, sf) in enumerate(PLAN):
    col, wheels, tl = make_car(CAR_PAINTS[idx % len(CAR_PAINTS)], idx)
    traj = simulate(appr, move, sf)
    if not traj:
        continue
    frames = sorted(traj.keys())
    # hide before spawn / after end via scale keyframes is messy; instead
    # place at spawn and keyframe every frame (Blender handles 240 keys fine)
    for f in frames:
        x, y, ang, braking = traj[f]
        for o in col.objects:
            pass
        # set transforms on the collection via a parent empty for simplicity
        break
    # parent everything to an empty we animate
    bpy.ops.object.empty_add(location=(0, 0, 0))
    rig = bpy.context.active_object
    rig.name = 'Rig%d' % idx
    for o in list(col.objects):
        o.parent = rig
    for f in frames:
        x, y, ang, braking = traj[f]
        rig.location = (x, y, 0)
        rig.rotation_euler = (0, 0, math.radians(ang))
        rig.keyframe_insert(data_path='location', frame=f)
        rig.keyframe_insert(data_path='rotation_euler', frame=f)
    # brake-light flare while braking
    tl_mat = tl.data.materials[0]
    bsdf = tl_mat.node_tree.nodes.get('Principled BSDF')
    sock = bsdf.inputs['Emission Strength']
    prev = None
    for f in frames:
        _, _, _, braking = traj[f]
        if braking != prev:
            sock.default_value = 4.0 if braking else 1.0
            sock.keyframe_insert(data_path='default_value', frame=f)
            prev = braking
    car_cols.append(col)

# ------------------------------------------------------------------ world / lighting
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.012, 0.016, 0.030, 1.0)
bg.inputs['Strength'].default_value = 1.2

bpy.ops.object.light_add(type='SUN', location=(-60, -45, 42))
sun = bpy.context.active_object
sun.data.energy = 1.2
sun.data.color = (0.55, 0.65, 0.95)

# cool moonlight fill
bpy.ops.object.light_add(type='SUN', location=(50, 30, 60))
moon = bpy.context.active_object
moon.data.energy = 0.8
moon.data.color = (0.5, 0.65, 1.0)

# ------------------------------------------------------------------ camera
from mathutils import Vector

def look_at(obj, target):
    direction = Vector(target) - Vector(obj.location)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    obj.rotation_euler = rot_quat.to_euler()

bpy.ops.object.camera_add(location=(20, -28, 6))
cam = bpy.context.active_object
cam.name = 'CineCam'
bpy.context.scene.camera = cam
cam.data.lens = 32
look_at(cam, (0, 0, 2))

def cam_key(frame, loc, tgt):
    cam.location = loc
    look_at(cam, tgt)
    cam.keyframe_insert(data_path='location', frame=frame)
    cam.keyframe_insert(data_path='rotation_euler', frame=frame)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'

# cinematic sweep: low street-level -> rising aerial orbit (clear of buildings)
cam_key(1, (20, -28, 6), (0, 0, 2))
cam_key(40, (14, -24, 10), (0, 0, 2))
cam_key(80, (-16, -18, 18), (0, 0, 2))
cam_key(120, (-24, 6, 28), (0, 0, 1))

# still cameras (positions verified clear of buildings)
still_cams = []
for i, (loc, tgt) in enumerate([
        ((24, -30, 12), (0, 0, 2)),
        ((-22, 26, 5), (0, 0, 2)),
        ((0, -2, 48), (0, 0, 0))]):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = 'Still%d' % (i + 1)
    c.data.lens = 28 if i < 2 else 24
    look_at(c, tgt)
    still_cams.append(c)

# ------------------------------------------------------------------ render
scene = bpy.context.scene
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = False
scene.frame_start = 1
scene.frame_end = DUR
scene.render.fps = FPS

import os
OUT = os.path.expanduser('~/workspace/goals/ai-championship-adaptive-traffic-signals')

if mode == 'stills':
    # Cycles with OIDN denoising (official Blender build)
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.render.image_settings.file_format = 'PNG'
    # pick interesting frames: NS green flow, yellow, EW green flow
    shots = [(still_cams[0], 30, 'render_3d_1.png'),
             (still_cams[1], 100, 'render_3d_2.png'),
             (still_cams[2], 50, 'render_3d_3.png')]
    for cam_o, fr, fname in shots:
        scene.camera = cam_o
        scene.frame_set(fr)
        scene.render.filepath = os.path.join(OUT, fname)
        bpy.ops.render.render(write_still=True)
        print('still written:', fname)
else:
    scene.camera = bpy.data.objects['CineCam']
    # Cycles for animation (Eevee cannot run headless); low samples + OIDN
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.filepath = os.path.join(OUT, 'sabz_3d_cinematic.mp4')
    bpy.ops.render.render(animation=True)
    print('animation written: sabz_3d_cinematic.mp4')

print('DONE mode=%s' % mode)
