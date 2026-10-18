"""SABZ 3D demo animation v2 - clean 3-shot, 30s, EEVEE.

Usage:
    blender --background --python sabz_demo_anim.py -- --shot 1
    blender --background --python sabz_demo_anim.py -- --shot 2
    blender --background --python sabz_demo_anim.py -- --shot 3

3 shots x 240 frames @24fps = 30 seconds total.
Output: /tmp/sabz_demo/shotN/frame_####.png  (1280x720, EEVEE+bloom)
"""
import bpy
import math
import os
import sys
import time
import random as _r

WORK = os.path.expanduser("~/workspace/goals/ai-championship-adaptive-traffic-signals")
CAR_DIR = os.path.join(WORK, "assets/cars/Models/GLB format")
OUT_BASE = "/tmp/sabz_demo"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHOT = int(args[args.index("--shot") + 1]) if "--shot" in args else 1
SHOT_RANGES = {1: (1, 240), 2: (241, 480), 3: (481, 720)}
FSTART, FEND = SHOT_RANGES[SHOT]
print(f"SHOT {SHOT}: frames {FSTART}-{FEND}", flush=True)
_r.seed(7)

# ---------------------------------------------------------------- clear
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for x in list(coll):
        coll.remove(x)

# ---------------------------------------------------------------- helpers
def mat(name, base=(0.05, 0.05, 0.06, 1.0), rough=0.6, metallic=0.0,
        emission=None, e_strength=0.0, specular=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Specular IOR Level"].default_value = specular
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = e_strength
    return m


def box(name, loc, dims, material):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    o.data.materials.append(material)
    return o


def strip(name, loc, dims, material):
    bpy.ops.mesh.primitive_plane_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    o.data.materials.append(material)
    return o


def keyframe_emission(mat_obj, frame_values):
    node = mat_obj.node_tree.nodes["Principled BSDF"]
    inp = node.inputs["Emission Strength"]
    for f, v in frame_values:
        inp.default_value = v
        inp.keyframe_insert(data_path="default_value", frame=f)
    for fc in mat_obj.node_tree.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"


def key_loc(obj, frame, loc, interp="LINEAR"):
    obj.location = loc
    obj.keyframe_insert(data_path="location", frame=frame)
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 0.5:
                        kp.interpolation = interp


# ---------------------------------------------------------------- ground & roads
asphalt = mat("Asphalt", base=(0.045, 0.047, 0.058, 1.0), rough=0.42, specular=0.9)
box("Ground", (0, 0, -0.25), (220, 220, 0.5), asphalt)
road_mat = mat("Road", base=(0.06, 0.062, 0.072, 1.0), rough=0.35, specular=1.0)
strip("RoadNS", (0, 0, 0.01), (8, 220, 1), road_mat)
strip("RoadEW", (0, 0, 0.012), (220, 8, 1), road_mat)
line_w = mat("LineW", base=(0.9, 0.9, 0.88, 1.0), rough=0.5,
             emission=(0.55, 0.55, 0.5), e_strength=0.5)
line_y = mat("LineY", base=(0.85, 0.62, 0.08, 1.0), rough=0.5,
             emission=(0.5, 0.35, 0.05), e_strength=0.5)
for x in (-0.35, 0.35):
    for y0 in (-105, -60, -30, 30, 60):
        strip(f"CY_{x}_{y0}", (x, y0 - 12 if y0 < 0 else y0 + 12, 0.02), (0.18, 22, 1), line_y)
for y in (-0.35, 0.35):
    for x0 in (-105, -60, -30, 30, 60):
        strip(f"CX_{y}_{x0}", (x0 - 12 if x0 < 0 else x0 + 12, y, 0.02), (22, 0.18, 1), line_y)
for x in (-2.2, 2.2):
    for k in range(-9, 10):
        if abs(k * 10) < 8:
            continue
        strip(f"LDN_{x}_{k}", (x, k * 10, 0.02), (0.15, 3.0, 1), line_w)
for y in (-2.2, 2.2):
    for k in range(-9, 10):
        if abs(k * 10) < 8:
            continue
        strip(f"LDE_{y}_{k}", (k * 10, y, 0.02), (3.0, 0.15, 1), line_w)
for sx, sy, rot in ((0, -7, 0), (0, 7, 0), (-7, 0, 1), (7, 0, 1)):
    for i in range(-3, 4):
        if rot == 0:
            strip(f"ZW_{sx}_{sy}_{i}", (i * 1.1, sy, 0.02), (0.55, 2.6, 1), line_w)
        else:
            strip(f"ZW_{sx}_{sy}_{i}", (sx, i * 1.1, 0.02), (2.6, 0.55, 1), line_w)

# ---------------------------------------------------------------- signals (emission-keyframed)
pole_mat = mat("Pole", base=(0.09, 0.09, 0.1, 1.0), rough=0.5, metallic=0.6)
housing_mat = mat("Housing", base=(0.04, 0.04, 0.045, 1.0), rough=0.6)


def lamp_mat(name, color):
    e = {"red": (1, 0.08, 0.08), "yel": (1, 0.65, 0.05), "grn": (0.05, 1, 0.35)}[color]
    return mat(name, base=(0.06, 0.06, 0.06, 1.0), rough=0.4, emission=e, e_strength=0.0)


ns_lamps = {c: lamp_mat(f"NS_{c}", c) for c in ("red", "yel", "grn")}
ew_lamps = {c: lamp_mat(f"EW_{c}", c) for c in ("red", "yel", "grn")}


def phase_keys(windows):
    kf = [(1, 0.0)]
    for s, e in windows:
        kf += [(max(1, s - 2), 0.0), (s, 26.0), (e, 26.0), (e + 2, 0.0)]
    kf.append((720, 0.0))
    seen = {}
    for f, v in kf:
        seen[f] = v
    return sorted(seen.items())


# 30s timeline: NS grn 1-300, NS yel 301-348, EW grn 349-648, EW yel 649-696, NS grn 697-720
keyframe_emission(ns_lamps["grn"], phase_keys([(1, 300), (697, 720)]))
keyframe_emission(ns_lamps["yel"], phase_keys([(301, 348)]))
keyframe_emission(ns_lamps["red"], phase_keys([(349, 696)]))
keyframe_emission(ew_lamps["grn"], phase_keys([(349, 648)]))
keyframe_emission(ew_lamps["yel"], phase_keys([(649, 696)]))
keyframe_emission(ew_lamps["red"], phase_keys([(1, 348), (697, 720)]))


def signal(x, y, facing_deg, lamp_mats, tag):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=5.2, location=(x, y, 2.6))
    p = bpy.context.active_object
    p.name = f"Pole_{tag}"
    p.data.materials.append(pole_mat)
    fx, fy = math.cos(math.radians(facing_deg)), math.sin(math.radians(facing_deg))
    hx, hy = x + 1.1 * fx, y + 1.1 * fy
    box(f"Head_{tag}", (hx, hy, 4.6), (0.45, 0.45, 1.35), housing_mat)
    for i, c in enumerate(("red", "yel", "grn")):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.14, location=(hx + fx * 0.26, hy + fy * 0.26, 4.95 - i * 0.42))
        s = bpy.context.active_object
        s.name = f"Lamp_{tag}_{c}"
        s.data.materials.append(lamp_mats[c])


signal(5.5, -7.5, 270, ns_lamps, "S")
signal(-5.5, 7.5, 90, ns_lamps, "N")
signal(7.5, 5.5, 0, ew_lamps, "E")
signal(-7.5, -5.5, 180, ew_lamps, "W")

# ---------------------------------------------------------------- street lamps (brighter)
lamp_head = mat("LampHead", emission=(1.0, 0.9, 0.7), e_strength=12.0, rough=0.4)
for x, y in [(-8, -20), (8, 20), (-8, 40), (8, -40), (-20, -8), (20, 8)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=6.5, location=(x, y, 3.25))
    bpy.context.active_object.data.materials.append(pole_mat)
    bpy.ops.mesh.primitive_cube_add(location=(x, y, 6.55))
    h = bpy.context.active_object
    h.dimensions = (1.3, 0.5, 0.22)
    h.data.materials.append(lamp_head)
    bpy.ops.object.light_add(type="POINT", location=(x, y, 6.3))
    li = bpy.context.active_object
    li.data.energy = 1500
    li.data.color = (1.0, 0.88, 0.68)

# ---------------------------------------------------------------- buildings (fewer, placed clear of cameras)
bldg_mat = mat("Bldg", base=(0.07, 0.075, 0.1, 1.0), rough=0.85)
win_on = mat("WinOn", emission=(1.0, 0.82, 0.55), e_strength=4.5, rough=0.4)
win_off = mat("WinOff", base=(0.08, 0.09, 0.12, 1.0), rough=0.4, specular=0.8)
for bx, by, bw, bd, bh in [(-30, -34, 20, 16, 24), (32, -36, 18, 18, 30),
                           (-34, 30, 22, 14, 18), (32, 32, 16, 20, 36)]:
    box(f"B_{bx}_{by}", (bx, by, bh / 2), (bw, bd, bh), bldg_mat)
    for fl in range(2, int(bh / 3)):
        z = fl * 3
        for k in range(int(bw / 2.4)):
            if _r.random() < 0.55:
                wm = win_on if _r.random() < 0.65 else win_off
                strip(f"WA_{bx}_{fl}_{k}", (bx + bw / 2 + 0.02, by, z), (0.02, 1.4, 1.8), wm)
                strip(f"WB_{bx}_{fl}_{k}", (bx - bw / 2 - 0.02, by, z), (0.02, 1.4, 1.8), wm)

# ---------------------------------------------------------------- world (brighter)
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.015, 0.02, 0.045, 1.0)
bg.inputs["Strength"].default_value = 1.1
bpy.ops.object.light_add(type="SUN", location=(30, -40, 60))
sun = bpy.context.active_object
sun.data.energy = 0.6
sun.data.color = (0.55, 0.68, 1.0)

# ---------------------------------------------------------------- join static geometry (draw-call optimization)
def join_by_prefix(prefix, new_name):
    obs = [o for o in bpy.data.objects
           if o.name.startswith(prefix) and o.type == "MESH"]
    if len(obs) < 2:
        return
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    bpy.context.active_object.name = new_name


join_by_prefix("WA_", "WindowsA")
join_by_prefix("WB_", "WindowsB")
join_by_prefix("CY_", "CenterYellow")
join_by_prefix("CX_", "CenterYellowX")
join_by_prefix("LDN_", "LaneDashN")
join_by_prefix("LDE_", "LaneDashE")
join_by_prefix("ZW_", "Crosswalk")

# ---------------------------------------------------------------- cars
CAR_FILES = {"sedan": "sedan.glb", "suv": "suv.glb", "taxi": "taxi.glb",
             "pickup": "delivery.glb", "sport": "sedan-sports.glb",
             "police": "police.glb", "hatch": "hatchback-sports.glb"}
_n = [0]


def import_car(kind, label):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CAR_DIR, CAR_FILES[kind]))
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    bpy.ops.object.join()
    car = bpy.context.active_object
    _n[0] += 1
    car.name = f"Car_{label}"
    return car


hl = mat("HL", emission=(1.0, 0.95, 0.8), e_strength=16.0, rough=0.3)
tl = mat("TL", emission=(1.0, 0.05, 0.05), e_strength=10.0, rough=0.3)


def lights(car):
    d = car.dimensions
    w = d.x * 0.32
    for sx in (-1, 1):
        x = sx * d.x * 0.28
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        q = bpy.context.active_object
        q.dimensions = (w, w * 0.55, 1)
        q.data.materials.append(hl)
        q.parent = car
        q.location = (x, d.y / 2 + 0.02, d.z * 0.42)
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        q2 = bpy.context.active_object
        q2.dimensions = (w, w * 0.4, 1)
        q2.data.materials.append(tl)
        q2.parent = car
        q2.location = (x, -d.y / 2 - 0.02, d.z * 0.42)
        q2.rotation_euler = (0, 0, math.pi)


def place(kind, label, x, y, hdg):
    car = import_car(kind, label)
    car.location = (x, y, 0.02)
    car.rotation_euler = (0, 0, math.radians(hdg) + math.pi)
    lights(car)
    return car


# animated: A,B on NS green (1-300); C,D wait then go on EW green (349-648)
carA = place("sedan", "A", -2, -25, 0)
carB = place("suv", "B", 2, 25, 180)
carC = place("taxi", "C", -25, -2, 90)
carD = place("pickup", "D", 25, 2, 270)
key_loc(carA, 1, (-2, -25, 0.02)); key_loc(carA, 300, (-2, 25, 0.02))
key_loc(carA, 301, (-2, 25, 0.02)); key_loc(carA, 720, (-2, 25, 0.02))
key_loc(carB, 1, (2, 25, 0.02));   key_loc(carB, 300, (2, -25, 0.02))
key_loc(carB, 301, (2, -25, 0.02)); key_loc(carB, 720, (2, -25, 0.02))
key_loc(carC, 1, (-25, -2, 0.02)); key_loc(carC, 120, (-9, -2, 0.02))
key_loc(carC, 349, (-9, -2, 0.02)); key_loc(carC, 648, (25, -2, 0.02))
key_loc(carC, 649, (25, -2, 0.02)); key_loc(carC, 720, (25, -2, 0.02))
key_loc(carD, 1, (25, 2, 0.02));  key_loc(carD, 120, (9, 2, 0.02))
key_loc(carD, 349, (9, 2, 0.02));  key_loc(carD, 648, (-25, 2, 0.02))
key_loc(carD, 649, (-25, 2, 0.02)); key_loc(carD, 720, (-25, 2, 0.02))
# static queued cars
place("sport", "Q1", -16, -2, 90)
place("police", "Q2", 16, 2, 270)
place("hatch", "Q3", -2, -33, 0)
place("sedan", "Q4", 2, 33, 180)
# headlight spots on A and C
for car in (carA, carC):
    bpy.ops.object.light_add(type="SPOT", location=(0, 0, 0))
    sp = bpy.context.active_object
    sp.parent = car
    sp.location = (0, car.dimensions.y / 2 + 0.3, 1.0)
    sp.rotation_euler = (math.radians(90), 0, 0)
    sp.data.energy = 300
    sp.data.spot_size = math.radians(55)
    sp.data.spot_blend = 0.4

# ---------------------------------------------------------------- cameras with TrackTo
bpy.ops.object.empty_add(location=(0, 0, 2.5))
focus = bpy.context.active_object
focus.name = "Focus"


def cam(name, loc, lens=32):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = name
    c.data.lens = lens
    con = c.constraints.new(type="TRACK_TO")
    con.target = focus
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return c


def key_cam(c, frame, loc):
    c.location = loc
    c.keyframe_insert(data_path="location", frame=frame)
    if c.animation_data and c.animation_data.action:
        for fc in c.animation_data.action.fcurves:
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 0.5:
                        kp.interpolation = "BEZIER"


# Shot 1: establishing push-in (clear sightline, no buildings in the way)
cam1 = cam("Cam1", (15, -19, 4.5))
key_cam(cam1, 1, (15, -19, 4.5))
key_cam(cam1, 240, (10, -12.5, 2.2))
# Shot 2: aerial arc
cam2 = cam("Cam2", (0, -38, 26), lens=30)
key_cam(cam2, 241, (0, -38, 26), )
key_cam(cam2, 360, (27, -27, 24))
key_cam(cam2, 480, (38, 0, 24))
for fc in cam2.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"
# Shot 3: street level, cars passing
cam3 = cam("Cam3", (-15, -19, 1.3), lens=36)
key_cam(cam3, 481, (-15, -19, 1.3))
key_cam(cam3, 720, (-10, -12, 1.6))

SHOT_CAMS = {1: cam1, 2: cam2, 3: cam3}

# ---------------------------------------------------------------- render (EEVEE)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.threads_mode = "FIXED"
scene.render.threads = 2
scene.cycles.samples = 32
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.2
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
# speed: shadows off (huge EEVEE speedup, acceptable for night scene)
for _o in bpy.data.objects:
    if _o.type == "LIGHT":
        try:
            _o.data.use_shadow = False
        except AttributeError:
            pass
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "Filmic"
scene.view_settings.look = "High Contrast"
scene.view_settings.exposure = 1.15
scene.render.fps = 24
scene.frame_start = FSTART
scene.frame_end = FEND
scene.frame_step = 8  # render 3fps, minterpolate to 24fps in post
scene.camera = SHOT_CAMS[SHOT]
out_dir = os.path.join(OUT_BASE, f"shot{SHOT}")
os.makedirs(out_dir, exist_ok=True)
scene.render.filepath = os.path.join(out_dir, "frame_####.png")
scene.use_nodes = True
nt = scene.node_tree
for n in nt.nodes:
    nt.nodes.remove(n)
rl = nt.nodes.new("CompositorNodeRLayers")
glare = nt.nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
glare.quality = "MEDIUM"
glare.threshold = 0.8
glare.size = 7
comp = nt.nodes.new("CompositorNodeComposite")
nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
nt.links.new(glare.outputs["Image"], comp.inputs["Image"])

t0 = time.time()
bpy.ops.render.render(animation=True)
got = sum(1 for f in os.listdir(out_dir) if f.startswith("frame_") and f.endswith(".png"))
print(f"SHOT {SHOT} done in {time.time()-t0:.0f}s: {got} frames", flush=True)
