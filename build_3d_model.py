"""SABZ intersection - procedural 3D model builder for Blender.

Builds the full SABZ demo intersection inside Blender so the team can
render cinematic stills / turntable animations with Cycles/Eevee.

Usage:
    blender --background --python build_3d_model.py

Output:
    - Builds the scene in the current .blend (roads, markings, sidewalks,
      buildings, traffic lights, lamps, cars, lighting, camera)
    - Renders one preview frame to ./sabz_blender_render.png

Units are metres. Blender Z-up convention is used here.
"""
import bpy
import math
import random

random.seed(42)

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

def box(name, sx, sy, sz, x, y, z, material=None, shadow=True):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if material:
        o.data.materials.append(material)
    o.cycle_visibility.shadow = shadow
    return o

def cyl(name, r, depth, x, y, z, material=None, verts=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts,
                                        location=(x, y, z))
    o = bpy.context.active_object
    o.name = name
    if material:
        o.data.materials.append(material)
    return o

# ---------------------------------------------------------------- materials
asphalt = mat('Asphalt', (0.13, 0.14, 0.16), roughness=0.95)
ground_m = mat('Ground', (0.07, 0.08, 0.10), roughness=1.0)
white = mat('MarkWhite', (0.85, 0.87, 0.90), roughness=0.6)
yellow_m = mat('MarkYellow', (0.85, 0.66, 0.13), roughness=0.6)
walk_m = mat('Sidewalk', (0.23, 0.24, 0.27), roughness=0.95)
pole_m = mat('Pole', (0.08, 0.08, 0.09), roughness=0.5, metallic=0.4)
glass_m = mat('Glass', (0.05, 0.08, 0.12), roughness=0.12, metallic=0.9)
tire_m = mat('Tire', (0.04, 0.04, 0.04), roughness=0.9)
head_m = mat('Headlight', (0.05, 0.05, 0.05), emissive=(0.81, 0.91, 1.0),
             emission_strength=3.0)
tail_m = mat('Taillight', (0.10, 0.0, 0.0), emissive=(1.0, 0.10, 0.10),
             emission_strength=1.2)
sig_red = mat('SigRed', (0.05, 0.0, 0.0), emissive=(1.0, 0.16, 0.16),
              emission_strength=5.0)
sig_grn = mat('SigGreen', (0.0, 0.05, 0.0), emissive=(0.16, 1.0, 0.37),
              emission_strength=5.0)
lamp_m = mat('LampGlow', (0.0, 0.0, 0.0), emissive=(1.0, 0.75, 0.42),
             emission_strength=4.0)

# ---------------------------------------------------------------- ground & roads
box('Ground', 700, 700, 0.5, 0, 0, -0.25, ground_m)
box('RoadNS', 7, 170, 0.1, 0, 0, 0.0, asphalt)
box('RoadEW', 170, 7, 0.1, 0, 0, 0.0, asphalt)

# centre double yellow + edge lines + dashes
for x in (-0.18, 0.18):
    box('CY1', 0.14, 78, 0.02, x, -46.5, 0.06, yellow_m)
    box('CY2', 0.14, 78, 0.02, x, 46.5, 0.06, yellow_m)
    box('CY3', 78, 0.14, 0.02, -46.5, x, 0.06, yellow_m)
    box('CY4', 78, 0.14, 0.02, 46.5, x, 0.06, yellow_m)
for x in (-3.32, 3.32):
    box('EL1', 0.12, 78, 0.02, x, -46.5, 0.06, white)
    box('EL2', 0.12, 78, 0.02, x, 46.5, 0.06, white)
    box('EL3', 78, 0.12, 0.02, -46.5, x, 0.06, white)
    box('EL4', 78, 0.12, 0.02, 46.5, x, 0.06, white)
for i in range(12):
    z0 = -80 + i * 13
    if abs(z0) < 12:
        continue
    box('Dash', 0.14, 3, 0.02, 0, z0, 0.06, white)
    box('Dash', 3, 0.14, 0.02, z0, 0, 0.06, white)

# stop lines
box('Stop', 3.1, 0.55, 0.02, -1.75, -STOP_D, 0.06, white)
box('Stop', 3.1, 0.55, 0.02, 1.75, STOP_D, 0.06, white)
box('Stop', 0.55, 3.1, 0.02, STOP_D, 1.75, 0.06, white)
box('Stop', 0.55, 3.1, 0.02, -STOP_D, -1.75, 0.06, white)

# crosswalks
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

# sidewalks
for sx in (1, -1):
    for sy in (1, -1):
        box('Walk', 22, 22, 0.3, sx * 14.5, sy * 14.5, 0.15, walk_m)

# ---------------------------------------------------------------- buildings
for i in range(30):
    ang = (i / 30.0) * math.pi * 2 + random.uniform(-0.1, 0.1)
    dist = 62 + random.uniform(0, 55)
    w = 8 + random.uniform(0, 14)
    d = 8 + random.uniform(0, 14)
    h = 9 + random.uniform(0, 34)
    # windows via emission on a dark facade: use vertex-light trick with
    # a simple two-tone material here; detailed windows are a texture job
    # for the lookdev pass.
    bmat = mat('Bldg%d' % i, (0.10 + random.uniform(0, 0.08),
                              0.11 + random.uniform(0, 0.08),
                              0.16 + random.uniform(0, 0.08)),
               roughness=0.9,
               emissive=(1.0, 0.83, 0.54),
               emission_strength=random.uniform(0.15, 0.5))
    b = box('Bldg%d' % i, w, d, h, math.cos(ang) * dist,
            math.sin(ang) * dist, h / 2.0, bmat)
    b.rotation_euler[2] = random.uniform(0, math.pi)

# ---------------------------------------------------------------- traffic lights
def signal(x, y, rot_z, green_on=True):
    """Pole + arm + 3-lamp head. rot_z faces the head toward traffic."""
    grp = bpy.data.collections.new('Signal')
    bpy.context.scene.collection.children.link(grp)
    old_active = bpy.context.view_layer.objects.active

    def link(o):
        for c in o.users_collection:
            c.objects.unlink(o)
        grp.objects.link(o)
        return o

    p = link(cyl('Pole', 0.14, 6.4, 0, 0, 3.2, pole_m))
    p.rotation_euler[2] = rot_z
    arm = link(cyl('Arm', 0.10, 4.4, 0, 0, 6.1, pole_m))
    arm.rotation_euler = (0, math.pi / 2, rot_z)
    head = link(box('Head', 0.9, 0.7, 2.4, 0, 0, 5.2, pole_m))
    head.rotation_euler[2] = rot_z
    # lamp positions along the arm direction
    dx, dy = math.cos(rot_z), math.sin(rot_z)
    for j, (col_mat, on) in enumerate(
            [(sig_red, not green_on), (None, False), (sig_grn, green_on)]):
        lx, ly = 2.0 * dx, 2.0 * dy
        lamp = link(box('Lamp', 0.5, 0.5, 0.4, lx, ly, 5.2 + 0.75 - j * 0.75,
                        col_mat if on else pole_m))
        lamp.rotation_euler[2] = rot_z
    # move whole group into place
    for o in grp.objects:
        o.location.x += x
        o.location.y += y
    bpy.context.view_layer.objects.active = old_active
    return grp

signal(-5.6, -8.2, math.pi, green_on=True)     # N approach
signal(5.6, 8.2, 0.0, green_on=True)           # S approach
signal(8.2, 5.6, -math.pi / 2, green_on=False)  # E approach
signal(-8.2, -5.6, math.pi / 2, green_on=False)  # W approach

# ---------------------------------------------------------------- street lamps
def street_lamp(x, y):
    cyl('LPole', 0.12, 7.5, x, y, 3.75, pole_m)
    box('LHead', 0.7, 0.7, 0.25, x, y, 7.4, lamp_m)
    bpy.ops.object.light_add(type='POINT', location=(x, y, 7.0))
    li = bpy.context.active_object
    li.data.energy = 800
    li.data.color = (1.0, 0.75, 0.42)

for x, y in [(-6.5, -10), (6.5, 10), (-6.5, 10), (6.5, -10)]:
    street_lamp(x, y)

# ---------------------------------------------------------------- cars
CAR_PAINTS = [(0.75, 0.23, 0.17), (0.16, 0.50, 0.73), (0.50, 0.55, 0.55),
              (0.17, 0.24, 0.31), (0.95, 0.61, 0.07), (0.56, 0.27, 0.68)]

def car(x, y, heading_deg, paint):
    paint_m = mat('Paint', paint, roughness=0.32, metallic=0.75)
    gcol = bpy.data.collections.new('Car')
    bpy.context.scene.collection.children.link(gcol)

    def link(o):
        for c in o.users_collection:
            c.objects.unlink(o)
        gcol.objects.link(o)
        return o

    body = link(box('Body', 1.8, 4.4, 0.72, 0, 0, 0.72, paint_m))
    link(box('Cabin', 1.6, 2.3, 0.62, 0, -0.25, 1.32, glass_m))
    for wx, wy in ((-0.85, 1.45), (0.85, 1.45), (-0.85, -1.45), (0.85, -1.45)):
        link(cyl('Wheel', 0.36, 0.28, wx, wy, 0.36, tire_m))
    link(box('HL', 0.34, 0.1, 0.2, -0.55, 2.21, 0.78, head_m))
    link(box('HL', 0.34, 0.1, 0.2, 0.55, 2.21, 0.78, head_m))
    link(box('TL', 1.5, 0.06, 0.16, 0, -2.21, 0.82, tail_m))
    for o in gcol.objects:
        o.rotation_euler[2] = math.radians(heading_deg)
        o.location.x += x
        o.location.y += y
    return gcol

# a small queued platoon on the north approach + a couple elsewhere
for i, z in enumerate((-14, -20, -26)):
    car(-1.75, z, 0, CAR_PAINTS[i % len(CAR_PAINTS)])
car(1.75, 18, 180, CAR_PAINTS[3])
car(20, 1.75, 270, CAR_PAINTS[4])
car(-24, -1.75, 90, CAR_PAINTS[1])

# ---------------------------------------------------------------- lighting & camera
bpy.ops.object.light_add(type='SUN', location=(-60, -45, 42))
sun = bpy.context.active_object
sun.data.energy = 2.2
sun.data.color = (1.0, 0.70, 0.48)
sun.rotation_euler = (math.radians(62), 0, math.radians(-38))

world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.03, 0.03, 0.07, 1.0)
bg.inputs['Strength'].default_value = 0.6

bpy.ops.object.camera_add(location=(34, 44, 26),
                          rotation=(math.radians(68), 0, math.radians(142)))
cam = bpy.context.active_object
bpy.context.scene.camera = cam

# ---------------------------------------------------------------- render setup
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 64
scene.render.resolution_x = 1600
scene.render.resolution_y = 900
scene.render.film_transparent = False
scene.render.filepath = './sabz_blender_render.png'
scene.render.image_settings.file_format = 'PNG'

print('SABZ intersection built: %d objects' % len(bpy.data.objects))
bpy.ops.render.render(write_still=True)
print('render written to sabz_blender_render.png')
