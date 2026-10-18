"""SABZ model explainer film - Blender shots.

Usage:
    blender --background --python sabz_film.py -- --shot 2
    blender --background --python sabz_film.py -- --shot 3
    blender --background --python sabz_film.py -- --shot 4
    blender --background --python sabz_film.py -- --shot 5

Shots 1 (logo intro) and 6 (outro) are built with ffmpeg (black + logo.png).
This script renders shots 2,3,4,5 at 640x360, 3fps (frame_step=8),
Cycles CPU 32 samples + OIDN + glare compositor.
"""
import bpy
import math
import os
import sys
import time
import random as _r

WORK = os.path.expanduser("~/workspace/goals/ai-championship-adaptive-traffic-signals")
CAR_DIR = os.path.join(WORK, "assets/cars/Models/GLB format")
OUT_BASE = os.path.join(WORK, "film_frames")  # persistent: survives restarts
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHOT = int(args[args.index("--shot") + 1]) if "--shot" in args else 2
print(f"FILM SHOT {SHOT}", flush=True)
_r.seed(11)

# ---------------------------------------------------------------- clear
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
             bpy.data.cameras, bpy.data.fonts, bpy.data.curves):
    for x in list(coll):
        try:
            coll.remove(x)
        except Exception:
            pass

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


def emis_keys(m, frame_values):
    node = m.node_tree.nodes["Principled BSDF"]
    inp = node.inputs["Emission Strength"]
    for f, v in frame_values:
        inp.default_value = v
        inp.keyframe_insert(data_path="default_value", frame=f)
    if m.node_tree.animation_data:
        for fc in m.node_tree.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"


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


def key_loc(obj, frame, loc, interp="LINEAR"):
    obj.location = loc
    obj.keyframe_insert(data_path="location", frame=frame)
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 0.5:
                        kp.interpolation = interp


def add_text(body, size, material, parent_cam=None, cam_offset=(0, 0, -8)):
    bpy.ops.object.text_add(location=(0, 0, 0))
    t = bpy.context.active_object
    t.data.body = body
    t.data.size = size
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    t.data.extrude = 0.04
    try:
        fnt = bpy.data.fonts.load(FONT_PATH)
        t.data.font = fnt
    except Exception as e:
        print("font load issue:", e, flush=True)
    t.data.materials.append(material)
    if parent_cam is not None:
        t.parent = parent_cam
        t.location = cam_offset
    return t


def text_fade(m, f_in0, f_in1, f_out0, f_out1, peak=6.0):
    emis_keys(m, [(f_in0, 0.0), (f_in1, peak), (f_out0, peak), (f_out1, 0.0)])



def hide_keys(obj, fi, fo):
    """Fully hide object outside [fi, fo] so no ghost remains."""
    for attr in ("hide_viewport", "hide_render"):
        setattr(obj, attr, True)
        obj.keyframe_insert(data_path=attr, frame=max(1, fi - 1))
        setattr(obj, attr, False)
        obj.keyframe_insert(data_path=attr, frame=fi)
        setattr(obj, attr, False)
        obj.keyframe_insert(data_path=attr, frame=fo)
        setattr(obj, attr, True)
        obj.keyframe_insert(data_path=attr, frame=fo + 1)

def setup_world(dark=(0.012, 0.016, 0.035, 1.0), strength=1.1):
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = dark
    bg.inputs["Strength"].default_value = strength


def setup_render(out_dir, cam, fstart, fend, step=1, samples=32):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.2
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
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
    scene.render.fps = 3
    scene.frame_start = fstart
    scene.frame_end = fend
    scene.frame_step = step
    scene.camera = cam
    os.makedirs(out_dir, exist_ok=True)
    scene.render.filepath = os.path.join(out_dir, "frame_####.png")
    scene.use_nodes = True
    nt = scene.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    glare = nt.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "MEDIUM"
    glare.threshold = 1.0
    glare.size = 6
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], comp.inputs["Image"])


def do_render(out_dir, cam, fstart, fend, tag, samples=32):
    setup_render(out_dir, cam, fstart, fend, samples=samples)
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    got = sum(1 for f in os.listdir(out_dir)
              if f.startswith("frame_") and f.endswith(".png"))
    print(f"{tag} done in {time.time()-t0:.0f}s: {got} frames -> {out_dir}",
          flush=True)
    return got


# ---------------------------------------------------------------- shared intersection builders
def build_roads():
    asphalt = mat("Asphalt", base=(0.045, 0.047, 0.058, 1.0), rough=0.42,
                  specular=0.9)
    box("Ground", (0, 0, -0.25), (220, 220, 0.5), asphalt)
    road_mat = mat("Road", base=(0.06, 0.062, 0.072, 1.0), rough=0.35,
                   specular=1.0)
    strip("RoadNS", (0, 0, 0.01), (8, 220, 1), road_mat)
    strip("RoadEW", (0, 0, 0.012), (220, 8, 1), road_mat)
    line_w = mat("LineW", base=(0.9, 0.9, 0.88, 1.0), rough=0.5,
                 emission=(0.55, 0.55, 0.5), e_strength=0.5)
    line_y = mat("LineY", base=(0.85, 0.62, 0.08, 1.0), rough=0.5,
                 emission=(0.5, 0.35, 0.05), e_strength=0.5)
    for x in (-0.35, 0.35):
        for y0 in (-105, -60, -30, 30, 60):
            strip(f"CY_{x}_{y0}", (x, y0 - 12 if y0 < 0 else y0 + 12, 0.02),
                  (0.18, 22, 1), line_y)
    for y in (-0.35, 0.35):
        for x0 in (-105, -60, -30, 30, 60):
            strip(f"CX_{y}_{x0}", (x0 - 12 if x0 < 0 else x0 + 12, y, 0.02),
                  (22, 0.18, 1), line_y)
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
                strip(f"ZW_{sx}_{sy}_{i}", (i * 1.1, sy, 0.02), (0.55, 2.6, 1),
                      line_w)
            else:
                strip(f"ZW_{sx}_{sy}_{i}", (sx, i * 1.1, 0.02), (2.6, 0.55, 1),
                      line_w)


def lamp_mat(name, color):
    e = {"red": (1, 0.08, 0.08), "yel": (1, 0.65, 0.05),
         "grn": (0.05, 1, 0.35)}[color]
    return mat(name, base=(0.06, 0.06, 0.06, 1.0), rough=0.4,
               emission=e, e_strength=0.0)


def build_signals():
    pole_mat = mat("Pole", base=(0.09, 0.09, 0.1, 1.0), rough=0.5,
                   metallic=0.6)
    housing_mat = mat("Housing", base=(0.04, 0.04, 0.045, 1.0), rough=0.6)
    ns = {c: lamp_mat(f"NS_{c}", c) for c in ("red", "yel", "grn")}
    ew = {c: lamp_mat(f"EW_{c}", c) for c in ("red", "yel", "grn")}

    def signal(x, y, facing_deg, lamp_mats, tag):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=5.2,
                                            location=(x, y, 2.6))
        p = bpy.context.active_object
        p.name = f"Pole_{tag}"
        p.data.materials.append(pole_mat)
        fx, fy = math.cos(math.radians(facing_deg)), math.sin(math.radians(facing_deg))
        hx, hy = x + 1.1 * fx, y + 1.1 * fy
        box(f"Head_{tag}", (hx, hy, 4.6), (0.45, 0.45, 1.35), housing_mat)
        for i, c in enumerate(("red", "yel", "grn")):
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=0.14,
                location=(hx + fx * 0.26, hy + fy * 0.26, 4.95 - i * 0.42))
            s = bpy.context.active_object
            s.name = f"Lamp_{tag}_{c}"
            s.data.materials.append(lamp_mats[c])

    signal(5.5, -7.5, 270, ns, "S")
    signal(-5.5, 7.5, 90, ns, "N")
    signal(7.5, 5.5, 0, ew, "E")
    signal(-7.5, -5.5, 180, ew, "W")
    return ns, ew


def static_lamps(ns, ew, ns_color, ew_color, fend=60):
    cmap = {"red": 0, "yel": 1, "grn": 2}
    for mats, col in ((ns, ns_color), (ew, ew_color)):
        for c, m in mats.items():
            v = 26.0 if c == col else 0.0
            emis_keys(m, [(1, v), (fend, v)])


def build_lamps_and_buildings():
    pole_mat = bpy.data.materials.get("Pole") or mat(
        "Pole", base=(0.09, 0.09, 0.1, 1.0), rough=0.5, metallic=0.6)
    lamp_head = mat("LampHead", emission=(1.0, 0.9, 0.7), e_strength=12.0,
                    rough=0.4)
    for x, y in [(-8, -20), (8, 20), (-8, 40), (8, -40), (-20, -8), (20, 8)]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=6.5,
                                            location=(x, y, 3.25))
        bpy.context.active_object.data.materials.append(pole_mat)
        bpy.ops.mesh.primitive_cube_add(location=(x, y, 6.55))
        h = bpy.context.active_object
        h.dimensions = (1.3, 0.5, 0.22)
        h.data.materials.append(lamp_head)
        bpy.ops.object.light_add(type="POINT", location=(x, y, 6.3))
        li = bpy.context.active_object
        li.data.energy = 1500
        li.data.color = (1.0, 0.88, 0.68)
    bldg_mat = mat("Bldg", base=(0.07, 0.075, 0.1, 1.0), rough=0.85)
    win_on = mat("WinOn", emission=(1.0, 0.82, 0.55), e_strength=4.5,
                 rough=0.4)
    win_off = mat("WinOff", base=(0.08, 0.09, 0.12, 1.0), rough=0.4,
                  specular=0.8)
    for bx, by, bw, bd, bh in [(-30, -34, 20, 16, 24), (32, -36, 18, 18, 30),
                               (-34, 30, 22, 14, 18), (32, 32, 16, 20, 36)]:
        box(f"B_{bx}_{by}", (bx, by, bh / 2), (bw, bd, bh), bldg_mat)
        for fl in range(2, int(bh / 3)):
            z = fl * 3
            for k in range(int(bw / 2.4)):
                if _r.random() < 0.55:
                    wm = win_on if _r.random() < 0.65 else win_off
                    strip(f"WA_{bx}_{fl}_{k}", (bx + bw / 2 + 0.02, by, z),
                          (0.02, 1.4, 1.8), wm)


CAR_FILES = {"sedan": "sedan.glb", "suv": "suv.glb", "taxi": "taxi.glb",
             "pickup": "delivery.glb", "sport": "sedan-sports.glb",
             "police": "police.glb", "hatch": "hatchback-sports.glb"}
_cn = [0]


def import_car(kind, label):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(
        filepath=os.path.join(CAR_DIR, CAR_FILES[kind]))
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    bpy.ops.object.join()
    car = bpy.context.active_object
    _cn[0] += 1
    car.name = f"Car_{label}_{_cn[0]}"
    return car


def car_lights(car):
    hl = bpy.data.materials.get("HL") or mat(
        "HL", emission=(1.0, 0.95, 0.8), e_strength=16.0, rough=0.3)
    tl = bpy.data.materials.get("TL") or mat(
        "TL", emission=(1.0, 0.05, 0.05), e_strength=10.0, rough=0.3)
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


def place_car(kind, label, x, y, hdg):
    car = import_car(kind, label)
    car.location = (x, y, 0.02)
    car.rotation_euler = (0, 0, math.radians(hdg) + math.pi)
    car_lights(car)
    return car


def make_cam(name, loc, lens=32, focus_loc=(0, 0, 2.5)):
    bpy.ops.object.empty_add(location=focus_loc)
    focus = bpy.context.active_object
    focus.name = f"Focus_{name}"
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = name
    c.data.lens = lens
    con = c.constraints.new(type="TRACK_TO")
    con.target = focus
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return c, focus


def key_cam(c, frame, loc, interp="BEZIER"):
    c.location = loc
    c.keyframe_insert(data_path="location", frame=frame)
    if c.animation_data and c.animation_data.action:
        for fc in c.animation_data.action.fcurves:
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 0.5:
                        kp.interpolation = interp


# ================================================================ SHOT 2: problem
def shot_problem():
    setup_world()
    build_roads()
    ns, ew = build_signals()
    static_lamps(ns, ew, "red", "red", fend=30)  # everything red = jam
    build_lamps_and_buildings()
    bpy.ops.object.light_add(type="SUN", location=(30, -40, 60))
    sun = bpy.context.active_object
    sun.data.energy = 0.6
    sun.data.color = (0.55, 0.68, 1.0)

    # jammed queues on all approaches (static) + 2 creeping cars
    kinds = ["sedan", "suv", "taxi", "pickup", "sport", "hatch"]
    qi = 0
    for x, y, hdg in [(-2, -10, 0), (-2, -16, 0), (-2, -22, 0),
                      (2, 10, 180), (2, 16, 180), (2, 22, 180),
                      (-10, -2, 90), (-16, -2, 90), (-22, -2, 90),
                      (10, 2, 270), (16, 2, 270), (22, 2, 270)]:
        place_car(kinds[qi % len(kinds)], f"Q{qi}", x, y, hdg)
        qi += 1
    c1 = place_car("sedan", "M1", -2, -34, 0)
    key_loc(c1, 1, (-2, -34, 0.02)); key_loc(c1, 30, (-2, -28, 0.02))
    c2 = place_car("taxi", "M2", 34, 2, 270)
    key_loc(c2, 1, (34, 2, 0.02)); key_loc(c2, 30, (28, 2, 0.02))

    cam, _ = make_cam("CamProblem", (17, -21, 5.5), lens=32)
    key_cam(cam, 1, (17, -21, 5.5))
    key_cam(cam, 30, (10.5, -13, 2.4))

    # text overlays (camera-parented, lower third)
    m1 = mat("Txt1", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
             emission=(1.0, 1.0, 1.0), e_strength=0.0)
    t1 = add_text("4.1 MILLION VEHICLES", 1.15, m1, cam, (0, -1.7, -9))
    text_fade(m1, 2, 5, 13, 16, peak=3.6)
    hide_keys(t1, 2, 16)
    m2 = mat("Txt2", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
             emission=(1.0, 0.45, 0.2), e_strength=0.0)
    t2 = add_text("FIXED TIMERS CAN'T SEE TRAFFIC", 0.85, m2, cam,
                  (0, -1.7, -9))
    text_fade(m2, 17, 20, 28, 30, peak=3.6)
    hide_keys(t2, 17, 30)

    do_render(os.path.join(OUT_BASE, "shot2"), cam, 1, 30, "SHOT2 problem")


# ================================================================ SHOT 3: brain
def shot_brain():
    setup_world(dark=(0.004, 0.006, 0.014, 1.0), strength=0.6)

    # layers along X
    layers = []
    # input: 18 in a column
    inp = [( -14, -8.0 + i * (16.0 / 17), 0) for i in range(18)]
    layers.append(("in", inp, 0.34, (0.1, 1.0, 0.45)))
    # hidden1: 8x8 grid
    h1 = [(-5, -3.85 + (i % 8) * 1.1, -3.85 + (i // 8) * 1.1)
          for i in range(64)]
    layers.append(("h1", h1, 0.26, (0.25, 0.75, 1.0)))
    # hidden2: 8x8 grid
    h2 = [(5, -3.85 + (i % 8) * 1.1, -3.85 + (i // 8) * 1.1)
          for i in range(64)]
    layers.append(("h2", h2, 0.26, (0.45, 0.5, 1.0)))
    # output: 2
    out = [(14, -1.4, 0), (14, 1.4, 0)]
    layers.append(("out", out, 0.42, (1.0, 0.7, 0.15)))

    layer_mats = {}
    for tag, pts, rad, ecol in layers:
        m = mat(f"NM_{tag}", base=(0.03, 0.03, 0.04, 1.0), rough=0.35,
                emission=ecol, e_strength=2.2)
        layer_mats[tag] = m
        for j, p in enumerate(pts):
            bpy.ops.mesh.primitive_uv_sphere_add(radius=rad, location=p,
                                                 segments=10, ring_count=6)
            s = bpy.context.active_object
            s.name = f"N_{tag}_{j}"
            s.data.materials.append(m)

    # sparse connections, joined per pair (1 per neuron: fast, still reads)
    conn_mat = mat("NM_conn", base=(0.05, 0.06, 0.09, 1.0), rough=0.5,
                   emission=(0.3, 0.55, 0.9), e_strength=0.55)
    for a in range(len(layers) - 1):
        pa = layers[a][1]
        pb = layers[a + 1][1]
        cyls = []
        for j, p0 in enumerate(pa):
            for k in _r.sample(range(len(pb)), 1):
                p1 = pb[k]
                mx, my, mz = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, \
                    (p0[2] + p1[2]) / 2
                dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                bpy.ops.mesh.primitive_cylinder_add(
                    radius=0.045, depth=length, location=(mx, my, mz),
                    vertices=8)
                c = bpy.context.active_object
                # orient Z axis along (dx,dy,dz)
                z_ang = math.atan2(dy, dx) - math.pi / 2
                xy = math.sqrt(dx * dx + dy * dy)
                x_ang = math.atan2(dz, xy)
                c.rotation_euler = (x_ang, 0, z_ang)
                c.data.materials.append(conn_mat)
                cyls.append(c)
        if len(cyls) > 1:
            bpy.ops.object.select_all(action="DESELECT")
            for c in cyls:
                c.select_set(True)
            bpy.context.view_layer.objects.active = cyls[0]
            bpy.ops.object.join()
            bpy.context.active_object.name = f"Conn_{a}"

    # pulse wave across layers (emission strength)
    F = 48
    emis_keys(layer_mats["in"],
              [(1, 1.2), (6, 5.5), (12, 1.2), (24, 1.2), (30, 5.5),
               (36, 1.2), (F, 1.2)])
    emis_keys(layer_mats["h1"],
              [(1, 1.2), (10, 1.2), (16, 5.5), (22, 1.2), (34, 1.2),
               (40, 5.5), (F, 1.2)])
    emis_keys(layer_mats["h2"],
              [(1, 1.2), (20, 1.2), (26, 5.5), (32, 1.2), (44, 1.2),
               (F, 2.2)])
    emis_keys(layer_mats["out"],
              [(1, 1.5), (28, 1.5), (34, 6.5), (40, 1.5), (F, 2.5)])

    # traveler pulses: small bright spheres flying input -> output
    trav_mat = mat("NM_trav", emission=(1.0, 1.0, 1.0), e_strength=10.0,
                   rough=0.3)
    for ti in range(4):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(-14, 0, 0))
        s = bpy.context.active_object
        s.name = f"Trav_{ti}"
        s.data.materials.append(trav_mat)
        yy = [-4.5, 2.5, -1.0, 5.0][ti]
        zz = [1.5, -2.0, 3.0, -3.5][ti]
        f0 = 1 + ti * 10
        key_loc(s, f0, (-14, yy, zz))
        key_loc(s, f0 + 16, (14, yy * 0.3, zz * 0.3))
        key_loc(s, min(F, f0 + 17), (-14, yy, zz))

    # dim fill lights for sphere shading
    for lx, ly in [(-20, 10), (20, -10)]:
        bpy.ops.object.light_add(type="POINT", location=(lx, ly, 12))
        li = bpy.context.active_object
        li.data.energy = 800
        li.data.color = (0.6, 0.75, 1.0)

    # orbiting camera
    cam, focus = make_cam("CamBrain", (30, 0, 7), lens=30,
                          focus_loc=(0, 0, 0))
    for f in (1, 16, 32, 48):
        ang = math.radians(-45 + (f - 1) * (90 / 47))
        key_cam(cam, f, (30 * math.cos(ang), 30 * math.sin(ang),
                         7 - (f - 1) * 0.04), interp="LINEAR")

    # text overlays
    texts = [
        ("18-DIMENSIONAL STATE", 2, 13),
        ("SEES EVERY QUEUE, EVERY WAIT", 14, 25),
        ("DEEP Q-NETWORK", 26, 37),
        ("LEARNS THE PERFECT TIMING", 38, 48),
    ]
    for i, (body, fi, fo) in enumerate(texts):
        m = mat(f"BTxt{i}", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
                emission=(0.55, 0.95, 1.0), e_strength=0.0)
        tx = add_text(body, 0.95, m, cam, (0, -1.9, -10))
        text_fade(m, fi, fi + 3, fo - 2, fo, peak=3.2)
        hide_keys(tx, fi, fo)

    do_render(os.path.join(OUT_BASE, "shot3"), cam, 1, 48, "SHOT3 brain",
              samples=16)


# ================================================================ SHOT 4: action
def shot_action():
    setup_world()
    build_roads()
    ns, ew = build_signals()
    build_lamps_and_buildings()
    bpy.ops.object.light_add(type="SUN", location=(30, -40, 60))
    sun = bpy.context.active_object
    sun.data.energy = 0.6
    sun.data.color = (0.55, 0.68, 1.0)

    F = 60
    # Part A (1-30): FIXED - EW red with long queues, NS green but EMPTY
    static_lamps(ns, ew, "grn", "red", fend=F)
    kinds = ["sedan", "suv", "taxi", "pickup", "sport", "hatch"]
    qi = 0
    for x, y, hdg in [(-9, -2, 90), (-15, -2, 90), (-21, -2, 90),
                      (-27, -2, 90), (9, 2, 270), (15, 2, 270),
                      (21, 2, 270), (27, 2, 270)]:
        place_car(kinds[qi % len(kinds)], f"FQ{qi}", x, y, hdg)
        qi += 1
    # Part B (31-60): SABZ - NS green extends, cars flow through on NS road
    flow = []
    for i, (kind, y0) in enumerate([("sedan", -34), ("suv", -44),
                                   ("taxi", -54)]):
        c = place_car(kind, f"FL{i}", -2, y0, 0)  # northbound
        key_loc(c, 31, (-2, y0, 0.02))
        key_loc(c, 60, (-2, y0 + 66, 0.02))
        flow.append(c)
    for i, (kind, y0) in enumerate([("pickup", 36), ("sport", 46)]):
        c = place_car(kind, f"FLB{i}", 2, y0, 180)  # southbound
        key_loc(c, 31, (2, y0, 0.02))
        key_loc(c, 60, (2, y0 - 66, 0.02))

    # camera A: street level on the jammed EW approach
    camA, _ = make_cam("CamFixed", (24, -6.5, 2.0), lens=36)
    key_cam(camA, 1, (24, -6.5, 2.0))
    key_cam(camA, 30, (17, -5.5, 1.7))
    mA = mat("ATxt", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
             emission=(1.0, 0.5, 0.25), e_strength=0.0)
    txA = add_text("FIXED", 1.6, mA, camA, (0, 2.0, -10))
    text_fade(mA, 3, 6, 27, 30, peak=3.6)
    hide_keys(txA, 3, 30)

    # camera B: NS approach, flowing
    camB, _ = make_cam("CamSabz", (-6.5, -24, 2.4), lens=36)
    key_cam(camB, 31, (-6.5, -24, 2.4))
    key_cam(camB, 60, (-5.5, -16, 2.0))
    mB = mat("BTxtA", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
             emission=(0.1, 1.0, 0.45), e_strength=0.0)
    txB = add_text("SABZ AI", 1.6, mB, camB, (0, 2.0, -10))
    text_fade(mB, 33, 36, 43, 46, peak=3.6)
    hide_keys(txB, 33, 46)
    mC = mat("BTxtB", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
             emission=(1.0, 1.0, 1.0), e_strength=0.0)
    txC = add_text("THE SIGNAL THAT CAN SEE", 0.95, mC, camB, (0, -1.9, -10))
    text_fade(mC, 47, 50, 58, 60, peak=3.2)
    hide_keys(txC, 47, 60)

    do_render(os.path.join(OUT_BASE, "shot4a"), camA, 1, 30,
              "SHOT4a fixed")
    do_render(os.path.join(OUT_BASE, "shot4b"), camB, 31, 60,
              "SHOT4b sabz")


# ================================================================ SHOT 5: results
def shot_results():
    setup_world(dark=(0.004, 0.006, 0.014, 1.0), strength=0.5)
    cam, focus = make_cam("CamResults", (0, -16, 4.5), lens=34,
                          focus_loc=(0, 0, 2.2))

    pairs = [
        ("44%", "LESS DELAY VS FIXED TIMING", (0.1, 1.0, 0.45), 1, 10),
        ("7.3s", "AVERAGE DELAY", (0.55, 0.9, 1.0), 11, 20),
        ("2/3", "SCENARIOS WON", (1.0, 0.75, 0.2), 21, 30),
    ]
    for i, (num, label, ecol, fi, fo) in enumerate(pairs):
        mn = mat(f"RNum{i}", base=(0.0, 0.0, 0.0, 1.0), rough=0.5,
                 emission=ecol, e_strength=0.0)
        tn = add_text(num, 3.4, mn)
        tn.location = (0, 0, 3.6)
        tn.rotation_euler = (math.radians(90), 0, 0)  # face the camera
        hide_keys(tn, fi, fo)
        # pop: 0 -> overshoot -> settle (kept readable, no blowout)
        emis_keys(mn, [(fi, 0.0), (fi + 2, 5.0), (fi + 4, 3.2),
                       (fo - 1, 3.2), (fo, 0.0)])
        ml = mat(f"RLab{i}", base=(0.0, 0.0, 0.0, 1.0), rough=0.6,
                 emission=(0.9, 0.95, 1.0), e_strength=0.0)
        tl = add_text(label, 0.85, ml)
        tl.location = (0, 0, 1.3)
        tl.rotation_euler = (math.radians(90), 0, 0)  # face the camera
        text_fade(ml, fi + 1, fi + 3, fo - 1, fo, peak=2.6)
        hide_keys(tl, fi + 1, fo)

    do_render(os.path.join(OUT_BASE, "shot5"), cam, 1, 30,
              "SHOT5 results")


# ---------------------------------------------------------------- dispatch
if SHOT == 2:
    shot_problem()
elif SHOT == 3:
    shot_brain()
elif SHOT == 4:
    shot_action()
elif SHOT == 5:
    shot_results()
else:
    print(f"unknown shot {SHOT}", flush=True)
