"""SABZ cinematic stills - Blender Cycles night intersection with real car models.

Usage:
    blender --background --python sabz_blender_cine.py -- --mode test
    blender --background --python sabz_blender_cine.py -- --mode final

Outputs (work dir):
    render_cine_1.png, render_cine_2.png, render_cine_3.png (1920x1080, Cycles)

Design: rainy-night cinematic. Real Kenney CC0 car models, emissive signals,
street lamps with real lights, lit buildings, compositor bloom + vignette.
"""
import bpy
import math
import os
import sys

WORK = os.path.expanduser("~/workspace/goals/ai-championship-adaptive-traffic-signals")
CAR_DIR = os.path.join(WORK, "assets/cars/Models/GLB format")

mode = "test"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--mode" in args:
    v = args[args.index("--mode") + 1]
    if v in ("test", "final"):
        mode = v
print("MODE:", mode)

FINAL = (mode == "final")

# ---------------------------------------------------------------- clear
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for x in list(coll):
        coll.remove(x)

# ---------------------------------------------------------------- helpers
def mat_principled(name, base=(0.05, 0.05, 0.06, 1.0), rough=0.6, metallic=0.0,
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

def box(name, loc, dims, mat):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    o.data.materials.append(mat)
    return o

def plane_strip(name, loc, dims, mat):
    bpy.ops.mesh.primitive_plane_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    o.data.materials.append(mat)
    return o

# ---------------------------------------------------------------- ground & roads
asphalt = mat_principled("Asphalt", base=(0.035, 0.037, 0.045, 1.0),
                         rough=0.38, specular=0.9)   # damp sheen
ground = box("Ground", (0, 0, -0.25), (220, 220, 0.5), asphalt)

# road surface slightly above ground
road_mat = mat_principled("Road", base=(0.05, 0.052, 0.06, 1.0), rough=0.32, specular=1.0)
# N-S road (along Y), E-W road (along X); each 8m wide (2 lanes)
plane_strip("RoadNS", (0, 0, 0.01), (8, 220, 1), road_mat)
plane_strip("RoadEW", (0, 0, 0.012), (220, 8, 1), road_mat)

line_white = mat_principled("LineW", base=(0.9, 0.9, 0.88, 1.0), rough=0.5,
                            emission=(0.55, 0.55, 0.5), e_strength=0.35)
line_yellow = mat_principled("LineY", base=(0.85, 0.62, 0.08, 1.0), rough=0.5,
                             emission=(0.5, 0.35, 0.05), e_strength=0.35)

# centre double-yellow lines (broken into segments to skip intersection box)
for x in (-0.35, 0.35):
    for y0 in (-105, -60, -30, 30, 60):
        if y0 < 0:
            plane_strip(f"CY_{x}_{y0}", (x, y0 - 12, 0.02), (0.18, 22, 1), line_yellow)
        else:
            plane_strip(f"CY_{x}_{y0}", (x, y0 + 12, 0.02), (0.18, 22, 1), line_yellow)
for y in (-0.35, 0.35):
    for x0 in (-105, -60, -30, 30, 60):
        if x0 < 0:
            plane_strip(f"CX_{y}_{x0}", (x0 - 12, y, 0.02), (22, 0.18, 1), line_yellow)
        else:
            plane_strip(f"CX_{y}_{x0}", (x0 + 12, y, 0.02), (22, 0.18, 1), line_yellow)

# lane dashes (white) on each road
for x in (-2.2, 2.2):
    for k in range(-9, 10):
        y = k * 10
        if abs(y) < 8:
            continue
        plane_strip(f"LD_NS_{x}_{k}", (x, y, 0.02), (0.15, 3.0, 1), line_white)
for y in (-2.2, 2.2):
    for k in range(-9, 10):
        x = k * 10
        if abs(x) < 8:
            continue
        plane_strip(f"LD_EW_{y}_{k}", (x, y, 0.02), (3.0, 0.15, 1), line_white)

# crosswalks (zebra stripes) on all four approaches
for sx, sy, rot in ((0, -7, 0), (0, 7, 0), (-7, 0, 1), (7, 0, 1)):
    for i in range(-3, 4):
        if rot == 0:
            plane_strip(f"ZW_{sx}_{sy}_{i}", (i * 1.1, sy, 0.02), (0.55, 2.6, 1), line_white)
        else:
            plane_strip(f"ZW_{sx}_{sy}_{i}", (sx, i * 1.1, 0.02), (2.6, 0.55, 1), line_white)

# ---------------------------------------------------------------- cars (real Kenney GLB models)
CAR_FILES = {
    "sedan": "sedan.glb",
    "suv": "suv.glb",
    "taxi": "taxi.glb",
    "pickup": "delivery.glb",
    "truck": "garbage-truck.glb",
    "bus": "firetruck.glb",   # long vehicle stand-in
    "sport": "sedan-sports.glb",
    "police": "police.glb",
}

def import_car(kind):
    path = os.path.join(CAR_DIR, CAR_FILES[kind])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    # join into one object for easy handling
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    bpy.ops.object.join()
    car = bpy.context.active_object
    car.name = f"Car_{kind}_{len([o for o in bpy.data.objects if o.name.startswith('Car_')])}"
    return car

# headlight / taillight glow quads
hl_mat = mat_principled("Headlight", emission=(1.0, 0.95, 0.8), e_strength=14.0, rough=0.3)
tl_mat = mat_principled("Taillight", emission=(1.0, 0.05, 0.05), e_strength=8.0, rough=0.3)

def add_light_quads(car, forward_axis="+Y"):
    # assumes car faces +Y; places two headlight + two taillight quads
    dims = car.dimensions
    w = dims.x * 0.32
    fy = dims.y / 2 + 0.02
    by = -dims.y / 2 - 0.02
    z = dims.z * 0.42
    for sx in (-1, 1):
        x = sx * dims.x * 0.28
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        q = bpy.context.active_object
        q.dimensions = (w, w * 0.55, 1)
        q.data.materials.append(hl_mat)
        q.parent = car
        q.location = (x, fy, z)
        q.rotation_euler = (0, 0, 0)
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        q2 = bpy.context.active_object
        q2.dimensions = (w, w * 0.4, 1)
        q2.data.materials.append(tl_mat)
        q2.parent = car
        q2.location = (x, by, z)
        q2.rotation_euler = (0, 0, math.pi)

# (lane_x, dist_along, heading_deg, kind)  heading 0 = facing +Y (north)
traffic = [
    # N-S road flowing (green phase): moving through intersection
    (-2.0, 2.5, 0, "sedan"),
    (-2.0, -6.0, 0, "taxi"),
    (2.0, 14.0, 180, "suv"),
    (2.0, -14.0, 0, "sport"),
    (-2.0, -16.5, 0, "pickup"),
    (2.0, 24.0, 180, "sedan"),
    # E-W road queued at red
    (-14.0, -2.0, 90, "truck"),
    (-22.0, -2.0, 90, "sedan"),
    (-29.0, -2.0, 90, "suv"),
    (14.0, 2.0, 270, "bus"),
    (23.0, 2.0, 270, "taxi"),
    (31.0, 2.0, 270, "police"),
]

hero_cars = []
for i, (lx, dy, hdg, kind) in enumerate(traffic):
    car = import_car(kind)
    # Kenney cars face +Z? normalize: rotate so longest axis is Y then heading
    car.location = (lx, dy, 0.02)
    car.rotation_euler = (0, 0, math.radians(hdg) + math.pi)  # +pi: Kenney fwd is -Y
    add_light_quads(car)
    if i < 3:
        hero_cars.append(car)

# headlight spot lights on hero cars only (perf)
for car in hero_cars:
    bpy.ops.object.light_add(type="SPOT", location=(0, 0, 0))
    sp = bpy.context.active_object
    sp.parent = car
    hdg = car.rotation_euler.z
    # forward offset in car local +Y
    sp.location = (0, car.dimensions.y / 2 + 0.3, 1.0)
    sp.rotation_euler = (math.radians(90), 0, 0)  # point forward+down slightly
    sp.data.energy = 220
    sp.data.spot_size = math.radians(55)
    sp.data.spot_blend = 0.4
    sp.data.color = (1.0, 0.95, 0.85)
    sp.data.shadow_soft_size = 0.6

# ---------------------------------------------------------------- traffic signals (N-S green, E-W red)
pole_mat = mat_principled("Pole", base=(0.08, 0.08, 0.09, 1.0), rough=0.5, metallic=0.6)
housing_mat = mat_principled("Housing", base=(0.03, 0.03, 0.035, 1.0), rough=0.6)

def signal_lamp(color, on):
    e = {"red": (1, 0.08, 0.08), "yel": (1, 0.65, 0.05), "grn": (0.05, 1, 0.35)}[color]
    s = 22.0 if on else 0.0
    dim = {"red": (0.35, 0.03, 0.03), "yel": (0.35, 0.2, 0.02), "grn": (0.03, 0.3, 0.08)}[color]
    if on:
        return mat_principled(f"Lamp_{color}_on", emission=e, e_strength=s, rough=0.4)
    return mat_principled(f"Lamp_{color}_off", base=(*dim, 1.0), rough=0.4)

def traffic_signal(x, y, facing_deg, ns_green):
    # pole + head with 3 lamps (kept in scene collection)
    px, py = x, y
    bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=5.2, location=(px, py, 2.6))
    pole = bpy.context.active_object
    pole.name = f"SigPole_{x}_{y}"
    pole.data.materials.append(pole_mat)
    # head box
    hx = px + 1.1 * math.cos(math.radians(facing_deg))
    hy = py + 1.1 * math.sin(math.radians(facing_deg))
    box(f"SigHead_{x}_{y}", (hx, hy, 4.6), (0.45, 0.45, 1.35), housing_mat)
    fx, fy = math.cos(math.radians(facing_deg)), math.sin(math.radians(facing_deg))
    states = {"red": not ns_green, "yel": False, "grn": ns_green}
    for i, c in enumerate(("red", "yel", "grn")):
        lz = 4.95 - i * 0.42
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.13, location=(hx + fx * 0.26, hy + fy * 0.26, lz))
        s = bpy.context.active_object
        s.name = f"SigLamp_{x}_{y}_{c}"
        s.data.materials.append(signal_lamp(c, states[c]))

# ---------------------------------------------------------------- street lamps (emissive + real point lights)
lamp_head_mat = mat_principled("LampHead", emission=(1.0, 0.9, 0.7), e_strength=9.0, rough=0.4)
n_lights = 0
for x, y in [(-8, -20), (8, 20), (-8, 40), (8, -40), (-20, -8), (20, 8), (-40, -8), (40, 8)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=6.5, location=(x, y, 3.25))
    p = bpy.context.active_object
    p.data.materials.append(pole_mat)
    bpy.ops.mesh.primitive_cube_add(location=(x, y, 6.55))
    h = bpy.context.active_object
    h.dimensions = (1.3, 0.5, 0.22)
    h.data.materials.append(lamp_head_mat)
    if n_lights < 6:  # cap real lights for Cycles perf
        bpy.ops.object.light_add(type="POINT", location=(x, y, 6.3))
        li = bpy.context.active_object
        li.data.energy = 900
        li.data.color = (1.0, 0.88, 0.68)
        li.data.shadow_soft_size = 1.2
        n_lights += 1

# ---------------------------------------------------------------- buildings with lit windows
bldg_mat = mat_principled("Bldg", base=(0.05, 0.055, 0.075, 1.0), rough=0.85)
win_on = mat_principled("WinOn", emission=(1.0, 0.82, 0.55), e_strength=3.2, rough=0.4)
win_off = mat_principled("WinOff", base=(0.06, 0.07, 0.1, 1.0), rough=0.4, specular=0.8)

import random as _r
_r.seed(42)
for bx, by, bw, bd, bh in [(-28, -30, 22, 18, 26), (30, -32, 20, 20, 34),
                           (-32, 28, 24, 16, 20), (30, 30, 18, 22, 42),
                           (-60, -10, 16, 30, 18), (58, 12, 20, 16, 24)]:
    b = box(f"Bldg_{bx}_{by}", (bx, by, bh / 2), (bw, bd, bh), bldg_mat)
    # windows on faces toward intersection
    for fl in range(2, int(bh / 3)):
        z = fl * 3
        for k in range(int(bw / 2.4)):
            if _r.random() < 0.5:
                wx = bx - bw / 2 + 1.3 + k * 2.4
                wm = win_on if _r.random() < 0.6 else win_off
                plane_strip(f"Wx1_{bx}_{fl}_{k}", (bx + bw / 2 + 0.02, by, z), (0.02, 1.4, 1.8), wm)
                plane_strip(f"Wx2_{bx}_{fl}_{k}", (bx - bw / 2 - 0.02, by, z), (0.02, 1.4, 1.8), wm)
                plane_strip(f"Wy1_{bx}_{fl}_{k}", (wx, by + bd / 2 + 0.02, z), (1.4, 0.02, 1.8), wm)
                plane_strip(f"Wy2_{bx}_{fl}_{k}", (wx, by - bd / 2 - 0.02, z), (1.4, 0.02, 1.8), wm)

# ---------------------------------------------------------------- world / atmosphere
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.008, 0.012, 0.03, 1.0)
bg.inputs["Strength"].default_value = 0.55

# faint moonlight directional
bpy.ops.object.light_add(type="SUN", location=(30, -40, 60))
sun = bpy.context.active_object
sun.data.energy = 0.35
sun.data.color = (0.55, 0.68, 1.0)

# ---------------------------------------------------------------- cameras
def make_cam(name, loc, look_at):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = name
    d = mathutils.Vector(look_at) - mathutils.Vector(loc)
    c.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    c.data.lens = 35
    return c

import mathutils
cam1 = make_cam("Cine1_Low", (10.5, -13.5, 1.4), (0, 4, 3.2))      # low near road, signal + cars
cam1.data.lens = 28
cam2 = make_cam("Cine2_Aerial", (0, -45, 30), (0, 0, 0))          # aerial 3/4
cam2.data.lens = 32
cam3 = make_cam("Cine3_Driver", (-2.0, -11.5, 1.35), (-2.0, 30, 2.0))  # driver POV down the lane
cam3.data.lens = 40

# ---------------------------------------------------------------- render settings
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.threads_mode = "FIXED"
scene.render.threads = 1  # leave CPU for the DQN training (first priority)
scene.cycles.samples = 128 if FINAL else 20
scene.cycles.use_adaptive_sampling = True if FINAL else False
scene.cycles.adaptive_threshold = 0.05
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100 if FINAL else 35
scene.render.film_transparent = False
scene.view_settings.view_transform = "Filmic"
scene.view_settings.look = "High Contrast"
scene.view_settings.exposure = 0.6

# compositor: bloom + vignette
scene.use_nodes = True
nt = scene.node_tree
for n in nt.nodes:
    nt.nodes.remove(n)
rl = nt.nodes.new("CompositorNodeRLayers")
glare = nt.nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
glare.quality = "HIGH"
glare.threshold = 0.75
glare.size = 8
cc = nt.nodes.new("CompositorNodeColorBalance")
cc.correction_method = "LIFT_GAMMA_GAIN"
cc.lift = (0.98, 1.0, 1.06)
cc.gamma = (1.0, 1.0, 1.0)
cc.gain = (1.06, 1.02, 0.96)
lens = nt.nodes.new("CompositorNodeLensdist")
lens.use_fit = True
# vignette via elliptical mask multiply
ell = nt.nodes.new("CompositorNodeEllipseMask")
ell.width = 1.35
ell.height = 1.35
blur = nt.nodes.new("CompositorNodeBlur")
blur.size_x = 220
blur.size_y = 220
mix = nt.nodes.new("CompositorNodeMixRGB")
mix.blend_type = "MULTIPLY"
mix.inputs["Fac"].default_value = 0.42
comp = nt.nodes.new("CompositorNodeComposite")
nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
nt.links.new(glare.outputs["Image"], cc.inputs["Image"])
nt.links.new(cc.outputs["Image"], lens.inputs["Image"])
nt.links.new(lens.outputs["Image"], mix.inputs[1])
nt.links.new(ell.outputs["Mask"], blur.inputs["Image"])
nt.links.new(blur.outputs["Image"], mix.inputs[2])
nt.links.new(mix.outputs["Image"], comp.inputs["Image"])

# ---------------------------------------------------------------- render the 3 stills
outs = [(cam1, "render_cine_1.png"), (cam2, "render_cine_2.png"), (cam3, "render_cine_3.png")]
for cam, fname in outs:
    scene.camera = cam
    scene.render.filepath = os.path.join(WORK, fname)
    bpy.ops.render.render(write_still=True)
    print("WROTE", fname)
