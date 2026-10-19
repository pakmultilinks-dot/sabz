"""SABZ 3D intersection builder -> models/intersection.glb

Builds a detailed urban intersection with named, animatable nodes:
  - Car_0..Car_9   : Empty parents; animate position/rotation in Three.js
  - Lamp_{N,S,E,W}_Red / Lamp_{N,S,E,W}_Grn : signal lamp meshes (toggle visibility)
  - Static: roads, markings, sidewalks, crosswalks, buildings, street lamps, trees

Units are metres, Z-up. Run:
    blender --background --python build_scene.py
"""
import bpy
import math
import os
import random

random.seed(7)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'models', 'intersection.glb')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

LANE = 3.5
STOP_D = 9.0

# ---------------------------------------------------------------- clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# ---------------------------------------------------------------- helpers
def mat(name, color, roughness=0.8, metallic=0.0, emissive=None, emission_strength=0.0):
    m = bpy.data.materials.new(name=name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if emissive is not None:
        bsdf.inputs['Emission Color'].default_value = (*emissive, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emission_strength
    return m

def box(name, sx, sy, sz, x, y, z, material=None, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if material:
        o.data.materials.append(material)
    if parent:
        o.parent = parent
    return o

def cyl(name, r, depth, x, y, z, material=None, verts=12, parent=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts,
                                        location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    if material:
        o.data.materials.append(material)
    if parent:
        o.parent = parent
    return o

def empty(name, x=0, y=0, z=0):
    bpy.ops.object.empty_add(location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    return o

# ---------------------------------------------------------------- materials
asphalt = mat('Asphalt', (0.13, 0.14, 0.16), roughness=0.95)
ground_m = mat('Ground', (0.10, 0.13, 0.10), roughness=1.0)
white = mat('MarkWhite', (0.85, 0.87, 0.90), roughness=0.6)
yellow_m = mat('MarkYellow', (0.85, 0.66, 0.13), roughness=0.6)
walk_m = mat('Sidewalk', (0.23, 0.24, 0.27), roughness=0.95)
pole_m = mat('Pole', (0.08, 0.08, 0.09), roughness=0.5, metallic=0.4)
glass_m = mat('Glass', (0.05, 0.08, 0.12), roughness=0.12, metallic=0.9)
tire_m = mat('Tire', (0.04, 0.04, 0.04), roughness=0.9)
trunk_m = mat('Trunk', (0.25, 0.16, 0.10), roughness=1.0)
leaf_m = mat('Leaf', (0.10, 0.35, 0.14), roughness=0.9)
head_m = mat('Headlight', (0.05, 0.05, 0.05), emissive=(0.81, 0.91, 1.0),
             emission_strength=3.0)
tail_m = mat('Taillight', (0.10, 0.0, 0.0), emissive=(1.0, 0.10, 0.10),
             emission_strength=1.2)
sig_red = mat('SigRed', (0.05, 0.0, 0.0), emissive=(1.0, 0.16, 0.16),
              emission_strength=6.0)
sig_grn = mat('SigGreen', (0.0, 0.05, 0.0), emissive=(0.16, 1.0, 0.37),
              emission_strength=6.0)
lamp_m = mat('LampGlow', (0.0, 0.0, 0.0), emissive=(1.0, 0.75, 0.42),
             emission_strength=4.0)

# ---------------------------------------------------------------- ground & roads
box('Ground', 420, 420, 0.5, 0, 0, -0.25, ground_m)
box('RoadNS', 7, 150, 0.1, 0, 0, 0.0, asphalt)
box('RoadEW', 150, 7, 0.1, 0, 0, 0.0, asphalt)

for x in (-0.18, 0.18):
    box('CY1', 0.14, 66, 0.02, x, -41, 0.06, yellow_m)
    box('CY2', 0.14, 66, 0.02, x, 41, 0.06, yellow_m)
    box('CY3', 66, 0.14, 0.02, -41, x, 0.06, yellow_m)
    box('CY4', 66, 0.14, 0.02, 41, x, 0.06, yellow_m)
for x in (-3.32, 3.32):
    box('EL1', 0.12, 66, 0.02, x, -41, 0.06, white)
    box('EL2', 0.12, 66, 0.02, x, 41, 0.06, white)
    box('EL3', 66, 0.12, 0.02, -41, x, 0.06, white)
    box('EL4', 66, 0.12, 0.02, 41, x, 0.06, white)
for i in range(10):
    z0 = -70 + i * 14
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

for sx in (1, -1):
    for sy in (1, -1):
        box('Walk', 22, 22, 0.3, sx * 14.5, sy * 14.5, 0.15, walk_m)

# ---------------------------------------------------------------- buildings (14, backdrop ring)
for i in range(14):
    ang = (i / 14.0) * math.pi * 2 + random.uniform(-0.12, 0.12)
    dist = 72 + random.uniform(0, 34)
    w = 10 + random.uniform(0, 14)
    d = 10 + random.uniform(0, 14)
    h = 10 + random.uniform(0, 30)
    bmat = mat('Bldg%d' % i, (0.07 + random.uniform(0, 0.05),
                              0.08 + random.uniform(0, 0.05),
                              0.12 + random.uniform(0, 0.06)),
               roughness=0.85)
    bx, by = math.cos(ang) * dist, math.sin(ang) * dist
    b = box('Bldg%d' % i, w, d, h, bx, by, h / 2.0, bmat)
    b.rotation_euler[2] = random.uniform(0, math.pi)
    # simple roof lip
    box('Roof%d' % i, w + 0.6, d + 0.6, 0.5,
        bx, by, h + 0.2, walk_m)

# ---------------------------------------------------------------- traffic signals (named lamps)
def signal(tag, x, y, rot_z):
    root = empty('Sig_' + tag, x, y, 0)
    p = cyl('Pole_' + tag, 0.14, 6.4, 0, 0, 3.2, pole_m, parent=root)
    p.rotation_euler[2] = rot_z
    arm = cyl('Arm_' + tag, 0.10, 4.4, 0, 0, 6.1, pole_m, parent=root)
    arm.rotation_euler = (0, math.pi / 2, rot_z)
    head = box('Head_' + tag, 0.9, 0.7, 2.4, 0, 0, 5.2, pole_m, parent=root)
    head.rotation_euler[2] = rot_z
    dx, dy = math.cos(rot_z), math.sin(rot_z)
    lx, ly = 2.0 * dx, 2.0 * dy
    # red (top), amber (mid, unlit dummy), green (bottom)
    red = box('Lamp_%s_Red' % tag, 0.5, 0.5, 0.4, lx, ly, 5.95, sig_red, parent=root)
    amb = box('Lamp_%s_Amb' % tag, 0.5, 0.5, 0.4, lx, ly, 5.2, pole_m, parent=root)
    grn = box('Lamp_%s_Grn' % tag, 0.5, 0.5, 0.4, lx, ly, 4.45, sig_grn, parent=root)
    for o in (red, amb, grn):
        o.rotation_euler[2] = rot_z
    return root

signal('N', -5.6, -8.2, math.pi)
signal('S', 5.6, 8.2, 0.0)
signal('E', 8.2, 5.6, -math.pi / 2)
signal('W', -8.2, -5.6, math.pi / 2)

# ---------------------------------------------------------------- street lamps (geometry only)
def street_lamp(x, y):
    cyl('LPole', 0.12, 7.5, x, y, 3.75, pole_m)
    box('LHead', 0.7, 0.7, 0.25, x, y, 7.4, lamp_m)

for x, y in [(-6.5, -10), (6.5, 10), (-6.5, 10), (6.5, -10),
              (-6.5, -30), (6.5, 30), (-30, -6.5), (30, 6.5)]:
    street_lamp(x, y)

# ---------------------------------------------------------------- trees (simple cones)
def tree(x, y, s=1.0):
    root = empty('Tree', x, y, 0)
    cyl('Trunk', 0.16 * s, 2.0 * s, 0, 0, 1.0 * s, trunk_m, parent=root)
    bpy.ops.mesh.primitive_cone_add(radius1=1.7 * s, radius2=0.25 * s,
                                    depth=3.6 * s, vertices=10,
                                    location=(x, y, 3.6 * s))
    fol = bpy.context.active_object
    fol.name = 'Foliage'
    for p in fol.data.polygons:
        p.use_smooth = True
    fol.data.materials.append(leaf_m)
    fol.parent = root

for x, y in [(-22, -18), (22, 18), (-22, 18), (22, -18),
              (-30, 6), (30, -6), (6, -30), (-6, 30)]:
    tree(x, y, random.uniform(0.9, 1.4))

# ---------------------------------------------------------------- cars (10, each under a named Empty)
CAR_PAINTS = [(0.75, 0.23, 0.17), (0.16, 0.50, 0.73), (0.50, 0.55, 0.55),
              (0.17, 0.24, 0.31), (0.95, 0.61, 0.07), (0.56, 0.27, 0.68),
              (0.80, 0.80, 0.82), (0.20, 0.60, 0.35), (0.55, 0.20, 0.55),
              (0.85, 0.45, 0.15)]

CAR_SPOTS = [(-1.75, -16, 180), (-1.75, -24, 180), (-1.75, -32, 180),
             (1.75, 20, 0), (1.75, 30, 0),
             (24, -1.75, 90), (34, -1.75, 90),
             (-26, 1.75, 270), (-36, 1.75, 270),
             (1.75, -40, 0)]

def car(idx, x, y, heading_deg, paint):
    root = empty('Car_%d' % idx, x, y, 0)
    root.rotation_euler[2] = math.radians(heading_deg)
    paint_m = mat('Paint%d' % idx, paint, roughness=0.32, metallic=0.75)
    box('Body', 1.8, 4.4, 0.72, 0, 0, 0.72, paint_m, parent=root)
    box('Cabin', 1.6, 2.3, 0.62, 0, -0.25, 1.32, glass_m, parent=root)
    for wx, wy in ((-0.85, 1.45), (0.85, 1.45), (-0.85, -1.45), (0.85, -1.45)):
        cyl('Wheel', 0.36, 0.28, wx, wy, 0.36, tire_m, parent=root)
    box('HL', 0.34, 0.1, 0.2, -0.55, 2.21, 0.78, head_m, parent=root)
    box('HL', 0.34, 0.1, 0.2, 0.55, 2.21, 0.78, head_m, parent=root)
    box('TL', 1.5, 0.06, 0.16, 0, -2.21, 0.82, tail_m, parent=root)
    return root

for i, (x, y, hdg) in enumerate(CAR_SPOTS):
    car(i, x, y, hdg, CAR_PAINTS[i % len(CAR_PAINTS)])

print('objects: %d' % len(bpy.data.objects))

# ---------------------------------------------------------------- export GLB
bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLB',
    use_selection=False,
    export_yup=True,
    export_apply=False,
    export_materials='EXPORT',
    export_cameras=False,
    export_lights=False,
)
import os as _os
print('GLB written: %s (%.1f KB)' % (OUT, _os.path.getsize(OUT) / 1024))
