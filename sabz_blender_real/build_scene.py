"""SABZ photorealistic Lahore intersection - scene builder.
Run: blender --background --python build_scene.py
Uses EEVEE for fast rendering with cinematic golden-hour lighting.
"""
import bpy
import math
import random
from mathutils import Vector

random.seed(42)

# ----------------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'

# EEVEE settings for realism
eevee = scene.eevee
eevee.taa_render_samples = 64
eevee.use_gtao = True
eevee.gtao_distance = 2.0
eevee.use_bloom = True
eevee.bloom_threshold = 0.8
eevee.bloom_intensity = 0.15
eevee.bloom_radius = 4.0
eevee.use_ssr = True
eevee.use_ssr_refraction = True
eevee.shadow_cube_size = '1024'
eevee.shadow_cascade_size = '2048'
eevee.use_soft_shadows = True

# Color management - filmic for cinematic look
scene.view_settings.view_transform = 'Filmic'
scene.view_settings.look = 'Medium High Contrast'
scene.view_settings.exposure = 0.3

# ----------------------------------------------------------------------------
# World - golden hour sky
# ----------------------------------------------------------------------------
world = bpy.data.worlds.new('World')
world.use_nodes = True
scene.world = world
wn = world.node_tree.nodes
wl = world.node_tree.links
wn.clear()

out = wn.new('ShaderNodeOutputWorld')
bg = wn.new('ShaderNodeBackground')
sky = wn.new('ShaderNodeTexSky')
sky.sky_type = 'NISHITA'
sky.sun_elevation = math.radians(12)
sky.sun_rotation = math.radians(35)
sky.altitude = 500
sky.air_density = 1.2
sky.dust_density = 8.0
sky.ozone_density = 2.0

world.node_tree.links.new(sky.outputs['Color'], bg.inputs['Color'])
bg.inputs['Strength'].default_value = 1.2
world.node_tree.links.new(bg.outputs['Background'], out.inputs['Surface'])

# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def principled(name, base_color, metallic=0.0, roughness=0.8, **kwargs):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*base_color, 1.0)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    for k, v in kwargs.items():
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    return mat

def car_paint(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.85
    bsdf.inputs['Roughness'].default_value = 0.28
    if 'Clearcoat' in bsdf.inputs:
        bsdf.inputs['Clearcoat'].default_value = 1.0
        bsdf.inputs['Clearcoat Roughness'].default_value = 0.08
    return mat

def glass(name, color=(0.08, 0.10, 0.12), roughness=0.05):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.1
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['IOR'].default_value = 1.5
    return mat

def emissive(name, color, strength=3.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
    if 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = (*color, 1.0)
        bsdf.inputs['Emission Strength'].default_value = strength
    return mat

MAT_grass = principled('Grass', (0.32, 0.38, 0.18), roughness=0.95)
MAT_asphalt = principled('Asphalt', (0.14, 0.14, 0.15), roughness=0.92)
MAT_asphalt_worn = principled('AsphaltWorn', (0.18, 0.18, 0.19), roughness=0.95)
MAT_sidewalk = principled('Sidewalk', (0.62, 0.60, 0.58), roughness=0.92)
MAT_lane_white = principled('LaneWhite', (0.85, 0.85, 0.82), roughness=0.7)
MAT_lane_yellow = principled('LaneYellow', (0.85, 0.65, 0.15), roughness=0.7)
MAT_tire = principled('Tire', (0.05, 0.05, 0.05), roughness=0.95)
MAT_rim = principled('Rim', (0.7, 0.7, 0.72), metallic=0.9, roughness=0.3)
MAT_glass = glass('CarGlass')
MAT_headlight = emissive('Headlight', (1.0, 0.95, 0.8), 4.0)
MAT_taillight = emissive('Taillight', (0.9, 0.05, 0.05), 2.5)
MAT_pole = principled('Pole', (0.25, 0.25, 0.27), metallic=0.6, roughness=0.5)
MAT_signal_off = principled('SigOff', (0.08, 0.08, 0.08), roughness=0.6)
MAT_lamp = emissive('StreetLamp', (1.0, 0.85, 0.6), 6.0)

MAT_bldg = []
bldg_colors = [
    (0.75, 0.68, 0.58), (0.68, 0.55, 0.45), (0.80, 0.75, 0.68),
    (0.60, 0.58, 0.55), (0.72, 0.62, 0.52), (0.65, 0.60, 0.55),
]
for i, c in enumerate(bldg_colors):
    MAT_bldg.append(principled(f'Bldg{i}', c, roughness=0.88))

MAT_window = glass('BldgGlass', (0.15, 0.18, 0.22), 0.1)
MAT_window_lit = emissive('WinLit', (1.0, 0.75, 0.45), 1.5)
MAT_awning = []
for c in [(0.6, 0.15, 0.12), (0.12, 0.35, 0.55), (0.15, 0.5, 0.25), (0.7, 0.55, 0.15)]:
    MAT_awning.append(principled(f'Awning{len(MAT_awning)}', c, roughness=0.8))
MAT_shop_sign = []
for c in [(0.8, 0.2, 0.15), (0.15, 0.5, 0.8), (0.9, 0.7, 0.1), (0.2, 0.7, 0.3)]:
    MAT_shop_sign.append(emissive(f'ShopSign{len(MAT_shop_sign)}', c, 1.2))

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def add_box(name, loc, size, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    if bevel > 0:
        bpy.ops.object.modifier_add(type='BEVEL')
        o.modifiers['Bevel'].width = bevel
        o.modifiers['Bevel'].segments = 2
        bpy.ops.object.modifier_apply(modifier='Bevel')
    if mat:
        o.data.materials.append(mat)
    return o

def add_cyl(name, loc, radius, depth, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    return o

# ----------------------------------------------------------------------------
# Ground and Roads
# ----------------------------------------------------------------------------
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.05))
g = bpy.context.active_object
g.name = 'Ground'
g.data.materials.append(MAT_grass)

ROAD_W = 14
ROAD_LEN = 200
add_box('RoadEW', (0, 0, 0), (ROAD_LEN, ROAD_W, 0.1), MAT_asphalt)
add_box('RoadNS', (0, 0, 0.02), (ROAD_W, ROAD_LEN, 0.1), MAT_asphalt_worn)

def dashed_line(x0, y0, x1, y1, n_dashes=20):
    for i in range(n_dashes):
        t0 = i / n_dashes
        t1 = (i + 0.55) / n_dashes
        mx0 = x0 + (x1 - x0) * t0
        my0 = y0 + (y1 - y0) * t0
        mx1 = x0 + (x1 - x0) * t1
        my1 = y0 + (y1 - y0) * t1
        cx, cy = (mx0 + mx1) / 2, (my0 + my1) / 2
        length = math.hypot(mx1 - mx0, my1 - my0)
        if abs(mx1 - mx0) > abs(my1 - my0):
            add_box('Dash', (cx, cy, 0.08), (length, 0.15, 0.02), MAT_lane_white)
        else:
            add_box('Dash', (cx, cy, 0.08), (0.15, length, 0.02), MAT_lane_white)

for y_lane in [-3.5, 3.5]:
    dashed_line(-100, y_lane, -14, y_lane)
    dashed_line(14, y_lane, 100, y_lane)
for x_lane in [-3.5, 3.5]:
    dashed_line(x_lane, -100, x_lane, -14)
    dashed_line(x_lane, 14, x_lane, 100)

for y_c in [-0.15, 0.15]:
    add_box('CenterY', (0, y_c, 0.08), (200, 0.12, 0.02), MAT_lane_yellow)
for x_c in [-0.15, 0.15]:
    add_box('CenterX', (x_c, 0, 0.09), (0.12, 200, 0.02), MAT_lane_yellow)

for i in range(8):
    add_box('Zebra', (-5.25 + i * 1.5, 10.5, 0.08), (0.8, 3.0, 0.02), MAT_lane_white)
    add_box('Zebra', (-5.25 + i * 1.5, -10.5, 0.08), (0.8, 3.0, 0.02), MAT_lane_white)
    add_box('Zebra', (10.5, -5.25 + i * 1.5, 0.08), (3.0, 0.8, 0.02), MAT_lane_white)
    add_box('Zebra', (-10.5, -5.25 + i * 1.5, 0.08), (3.0, 0.8, 0.02), MAT_lane_white)

SW = 3
for (sx, sy) in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
    add_box('Sidewalk', (sx * (ROAD_W/2 + SW/2 + 2), sy * (ROAD_W/2 + SW/2 + 2), 0.05),
            (30, 30, 0.15), MAT_sidewalk)

# ----------------------------------------------------------------------------
# Buildings
# ----------------------------------------------------------------------------
def make_building(x, y, w, d, h, mat_idx, rot_z=0):
    bldg = add_box(f'Bldg_{x}_{y}', (x, y, h/2), (w, d, h), MAT_bldg[mat_idx % len(MAT_bldg)])
    bldg.rotation_euler[2] = math.radians(rot_z)
    n_floors = max(2, int(h / 3.5))
    n_win = max(3, int(w / 3))
    for f in range(n_floors):
        for wi in range(n_win):
            wx = x - w/2 + (wi + 0.5) * (w / n_win)
            wz = 2.5 + f * 3.2
            wmat = MAT_window_lit if random.random() < 0.25 else MAT_window
            win = add_box('Win', (wx, y + d/2 + 0.05, wz), (1.4, 0.1, 1.6), wmat)
            win.rotation_euler[2] = math.radians(rot_z)
    awn = add_box('Awning', (x, y + d/2 + 1.2, 2.2), (w * 0.8, 2.0, 0.15),
                  MAT_awning[random.randint(0, len(MAT_awning)-1)])
    awn.rotation_euler[0] = math.radians(-15)
    sign = add_box('ShopSign', (x, y + d/2 + 0.15, 3.4), (w * 0.7, 0.15, 0.9),
                   MAT_shop_sign[random.randint(0, len(MAT_shop_sign)-1)])
    return bldg

make_building(28, 22, 24, 16, 11, 0)
make_building(-28, 22, 20, 14, 9, 1)
make_building(28, -24, 22, 15, 12, 2)
make_building(-30, -22, 26, 16, 10, 3)
make_building(55, 20, 20, 14, 8, 4)
make_building(-55, -18, 18, 12, 9, 5)
make_building(20, 48, 24, 14, 10, 1)
make_building(-22, -48, 22, 13, 8, 0)

# ----------------------------------------------------------------------------
# Street lights
# ----------------------------------------------------------------------------
def street_light(x, y):
    pole = add_cyl('LampPole', (x, y, 4), 0.12, 8, MAT_pole)
    arm = add_box('LampArm', (x, y, 7.8), (0.15, 2.5, 0.15), MAT_pole)
    lamp = add_box('LampHead', (x, y, 7.6), (0.5, 0.8, 0.25), MAT_lamp)
    bpy.ops.object.light_add(type='POINT', location=(x, y, 7.2))
    li = bpy.context.active_object
    li.data.energy = 800
    li.data.color = (1.0, 0.82, 0.55)
    li.data.shadow_soft_size = 1.5
    return pole

for x in [-40, -20, 20, 40]:
    street_light(x, 10.5)
    street_light(x, -10.5)
for y in [-40, -20, 20, 40]:
    street_light(10.5, y)
    street_light(-10.5, y)

# ----------------------------------------------------------------------------
# Traffic signals
# ----------------------------------------------------------------------------
def traffic_signal(x, y, facing):
    pole = add_cyl('SigPole', (x, y, 2.5), 0.1, 5, MAT_pole)
    arm = add_box('SigArm', (x, y, 4.8), (0.12, 0.12, 3.0), MAT_pole)
    arm.rotation_euler[2] = math.radians(facing)
    hx = x + math.sin(math.radians(facing)) * 2.8
    hy = y + math.cos(math.radians(facing)) * 2.8
    head = add_box('SigHead', (hx, hy, 4.2), (0.4, 0.35, 1.2),
                   principled('SigBox', (0.1, 0.1, 0.1), roughness=0.6))
    for i, (lname, zoff) in enumerate([('R', 0.35), ('Y', 0), ('G', -0.35)]):
        l = add_cyl(f'SIG_{lname}_{int(x)}_{int(y)}', (hx, hy + 0.19, 4.2 + zoff),
                    0.11, 0.05, MAT_signal_off, rot=(math.radians(90), 0, 0))
    return head

traffic_signal(12, 12, 225)
traffic_signal(-12, 12, 135)
traffic_signal(12, -12, 315)
traffic_signal(-12, -12, 45)

# ----------------------------------------------------------------------------
# Vehicles
# ----------------------------------------------------------------------------
VEHICLES = []

def make_car(name, color, loc):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], 0.65))
    body = bpy.context.active_object
    body.name = f'{name}_body'
    body.scale = (4.2, 1.85, 0.75)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.modifier_add(type='BEVEL')
    body.modifiers['Bevel'].width = 0.18
    body.modifiers['Bevel'].segments = 3
    bpy.ops.object.modifier_apply(modifier='Bevel')
    body.data.materials.append(car_paint(f'{name}_paint', color))
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0] - 0.2, loc[1], 1.25))
    cab = bpy.context.active_object
    cab.name = f'{name}_cabin'
    cab.scale = (2.2, 1.65, 0.55)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.modifier_add(type='BEVEL')
    cab.modifiers['Bevel'].width = 0.15
    cab.modifiers['Bevel'].segments = 3
    bpy.ops.object.modifier_apply(modifier='Bevel')
    cab.data.materials.append(MAT_glass)
    cab.parent = body
    
    for (wx, wy) in [(-1.35, 0.95), (-1.35, -0.95), (1.35, 0.95), (1.35, -0.95)]:
        w = add_cyl(f'{name}_wheel', (wx, wy, -0.3), 0.35, 0.25, MAT_tire,
                    rot=(math.radians(90), 0, 0))
        w.location = (loc[0]+wx, loc[1]+wy, 0.35)
        w.parent = body
        r = add_cyl(f'{name}_rim', (0, 0, 0), 0.18, 0.26, MAT_rim,
                    rot=(math.radians(90), 0, 0))
        r.location = (loc[0]+wx, loc[1]+wy, 0.35)
        r.parent = body
    
    for hy in [-0.6, 0.6]:
        hl = add_box(f'{name}_hl', (0, 0, 0), (0.12, 0.35, 0.18), MAT_headlight)
        hl.location = (loc[0]+2.05, loc[1]+hy, 0.72)
        hl.parent = body
        tl = add_box(f'{name}_tl', (0, 0, 0), (0.12, 0.35, 0.18), MAT_taillight)
        tl.location = (loc[0]-2.05, loc[1]+hy, 0.72)
        tl.parent = body
    
    # Reset children to be relative to body
    body.location = (loc[0], loc[1], 0)
    for child in body.children:
        child.location = (child.location[0] - loc[0], child.location[1] - loc[1], child.location[2])
    
    VEHICLES.append(body)
    return body

def make_rickshaw(name, loc):
    body = add_box(f'{name}_body', (loc[0], loc[1], 0.75), (2.6, 1.35, 0.9),
                   principled(f'{name}_blk', (0.08, 0.08, 0.08), roughness=0.6), bevel=0.12)
    front = add_box(f'{name}_front', (1.25, 0, 0), (0.5, 1.3, 0.85),
                    principled(f'{name}_ylw', (0.85, 0.65, 0.1), roughness=0.55), bevel=0.1)
    front.location = (1.25, 0, 0)
    front.parent = body
    canopy = add_box(f'{name}_canopy', (-0.2, 0, 0.8), (2.0, 1.4, 0.12),
                     principled(f'{name}_can', (0.12, 0.12, 0.12), roughness=0.8))
    canopy.location = (-0.2, 0, 0.8)
    canopy.parent = body
    for (sx, sy) in [(-1.0, 0.6), (-1.0, -0.6), (0.6, 0.6), (0.6, -0.6)]:
        s = add_cyl(f'{name}_sup', (sx, sy, 0.45), 0.03, 0.7, MAT_pole)
        s.parent = body
    for (wx, wy) in [(1.1, 0), (-0.8, 0.65), (-0.8, -0.65)]:
        w = add_cyl(f'{name}_wheel', (wx, wy, -0.47), 0.28, 0.18, MAT_tire,
                    rot=(math.radians(90), 0, 0))
        w.parent = body
    hl = add_box(f'{name}_hl', (1.52, 0, 0.1), (0.08, 0.25, 0.25), MAT_headlight)
    hl.parent = body
    body.location = (loc[0], loc[1], 0)
    VEHICLES.append(body)
    return body

def make_motorcycle(name, loc, rider_color=(0.3, 0.3, 0.35)):
    body = add_box(f'{name}_body', (loc[0], loc[1], 0.55), (1.9, 0.35, 0.45),
                   principled(f'{name}_bike', (0.15, 0.15, 0.18), metallic=0.4, roughness=0.4),
                   bevel=0.08)
    for wx in [-0.75, 0.75]:
        w = add_cyl(f'{name}_wheel', (wx, 0, -0.23), 0.32, 0.12, MAT_tire,
                    rot=(math.radians(90), 0, 0))
        w.parent = body
    torso = add_cyl(f'{name}_rider', (-0.1, 0, 0.6), 0.22, 0.65,
                    principled(f'{name}_cloth', rider_color, roughness=0.85))
    torso.parent = body
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.16, location=(0, 0, 0))
    head = bpy.context.active_object
    head.name = f'{name}_head'
    head.location = (-0.1, 0, 1.1)
    head.data.materials.append(principled(f'{name}_skin', (0.55, 0.42, 0.32), roughness=0.7))
    head.parent = body
    hl = add_box(f'{name}_hl', (0.98, 0, 0.07), (0.06, 0.18, 0.18), MAT_headlight)
    hl.parent = body
    body.location = (loc[0], loc[1], 0)
    VEHICLES.append(body)
    return body

car_colors = [
    (0.85, 0.85, 0.88), (0.12, 0.12, 0.14), (0.7, 0.12, 0.1),
    (0.15, 0.3, 0.65), (0.75, 0.75, 0.78), (0.2, 0.5, 0.25),
]
make_car('Car1', car_colors[0], (-30, 3.5, 0))
make_car('Car2', car_colors[2], (25, -3.5, 0))
make_car('Car3', car_colors[3], (-55, 3.5, 0))
make_car('Car4', car_colors[1], (45, -3.5, 0))
c5 = make_car('Car5', car_colors[4], (3.5, -35, 0))
c5.rotation_euler[2] = math.radians(90)
c6 = make_car('Car6', car_colors[5], (-3.5, 30, 0))
c6.rotation_euler[2] = math.radians(-90)

make_rickshaw('Rick1', (-15, 3.5, 0))
make_rickshaw('Rick2', (10, -3.5, 0))
r3 = make_rickshaw('Rick3', (3.5, -18, 0))
r3.rotation_euler[2] = math.radians(90)
make_rickshaw('Rick4', (-45, -3.5, 0))

make_motorcycle('Bike1', (-22, 3.5, 0), (0.4, 0.25, 0.15))
make_motorcycle('Bike2', (18, -3.5, 0), (0.2, 0.3, 0.5))
b3 = make_motorcycle('Bike3', (-3.5, -25, 0), (0.5, 0.5, 0.5))
b3.rotation_euler[2] = math.radians(-90)

# ----------------------------------------------------------------------------
# Lights
# ----------------------------------------------------------------------------
bpy.ops.object.light_add(type='SUN', location=(50, -30, 25))
sun = bpy.context.active_object
sun.name = 'GoldenSun'
sun.data.energy = 4.5
sun.data.color = (1.0, 0.72, 0.45)
sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(68), 0, math.radians(-35))

bpy.ops.object.light_add(type='SUN', location=(-40, 40, 30))
fill = bpy.context.active_object
fill.name = 'FillLight'
fill.data.energy = 0.5
fill.data.color = (0.6, 0.7, 0.9)
fill.rotation_euler = (math.radians(50), 0, math.radians(140))

# ----------------------------------------------------------------------------
# Camera
# ----------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(28, -32, 26))
cam = bpy.context.active_object
cam.name = 'MainCam'
direction = Vector((0, 0, 1)) - cam.location
rot_quat = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot_quat.to_euler()
cam.data.lens = 32
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 42
cam.data.dof.aperture_fstop = 4.0
scene.camera = cam

# ----------------------------------------------------------------------------
# Animation
# ----------------------------------------------------------------------------
scene.frame_start = 1
scene.frame_end = 600
scene.render.fps = 30

def animate_vehicle(obj, start_pos, end_pos, start_frame=1, end_frame=600):
    obj.location = (start_pos[0], start_pos[1], 0)
    obj.keyframe_insert(data_path="location", frame=start_frame)
    obj.location = (end_pos[0], end_pos[1], 0)
    obj.keyframe_insert(data_path="location", frame=end_frame)
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'

def av(name, sp, ep, sf=1, ef=600):
    v = bpy.data.objects.get(name)
    if v:
        animate_vehicle(v, sp, ep, sf, ef)
    else:
        print(f"WARNING: {name} not found")

av('Car1_body', (-30, 3.5), (95, 3.5))
av('Car2_body', (25, -3.5), (-95, -3.5))
av('Car3_body', (-95, 3.5), (60, 3.5))
av('Car4_body', (95, -3.5), (-60, -3.5))
av('Car5_body', (3.5, -35), (3.5, 95))
av('Car6_body', (-3.5, 30), (-3.5, -95))
av('Rick1_body', (-15, 3.5), (95, 3.5))
av('Rick2_body', (10, -3.5), (-95, -3.5))
av('Rick3_body', (3.5, -18), (3.5, 95))
av('Rick4_body', (-95, -3.5), (40, -3.5))
av('Bike1_body', (-22, 3.5), (95, 3.5))
av('Bike2_body', (18, -3.5), (-95, -3.5))
av('Bike3_body', (-3.5, -25), (-3.5, 95))

cam.location = (28, -32, 26)
cam.keyframe_insert(data_path="location", frame=1)
cam.location = (32, -28, 24)
cam.keyframe_insert(data_path="location", frame=600)

# ----------------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------------
bpy.ops.wm.save_as_mainfile(filepath='/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_blender_real/scene.blend')
print("Scene saved. Vehicles:", len(VEHICLES))
