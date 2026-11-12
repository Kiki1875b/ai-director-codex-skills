"""Pojangmacha set blockout (script/10-pojangmacha-spec.md), headless Blender.
Coordinates in meters: x = left->right (seen from the customer side), y = front(0)->back(2.6), z = up.
Usage:
  blender -b -P pojangmacha_blockout.py -- --out <dir> [--cams camA,camB,top] [--people]
Renders clay images (Workbench, object colors) per camera, plus a .blend for later shots.
"""
import bpy, math, sys, os, argparse

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--cams", default="camA,camB,top")
ap.add_argument("--people", action="store_true")
ap.add_argument("--res", default="1672x941")
ap.add_argument("--shot", help="name:x,y,z:tx,ty,tz:lens[:wild]  extra camera for one shot (wild=front|back|none)")
ap.add_argument("--who", default="", help="comma list: haeun,yeon,yeon_stand  (only these mannequins)")
ap.add_argument("--face", default="", help="haeun=deg,yeon=deg  facing yaw in degrees (0 = toward front/-y, 90 = toward +x/right)")
A = ap.parse_args(argv)
A.out = os.path.abspath(A.out); os.makedirs(A.out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
W, D, H = 4.0, 2.6, 2.2

def mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    return m

C = {
    "floor": mat("floor", (0.55, 0.47, 0.36)), "wall": mat("wall", (0.75, 0.42, 0.22)),
    "vinyl": mat("vinyl", (0.62, 0.70, 0.74)), "steel": mat("steel", (0.70, 0.72, 0.74)),
    "wood": mat("wood", (0.42, 0.28, 0.17)), "red": mat("red", (0.75, 0.12, 0.10)),
    "blue": mat("blue", (0.12, 0.22, 0.65)), "dark": mat("dark", (0.15, 0.15, 0.16)),
    "white": mat("white", (0.92, 0.92, 0.90)), "green": mat("green", (0.10, 0.45, 0.20)),
    "person": mat("person", (0.95, 0.85, 0.55)), "flame": mat("flame", (0.3, 0.5, 1.0)),
    "roof": mat("roof", (0.80, 0.40, 0.18)), "photo": mat("photo", (0.95, 0.9, 0.3)),
}

def box(name, x0, x1, y0, y1, z0, z1, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object; o.name = name
    o.scale = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    o.data.materials.append(C[m]); o.color = (*C[m].diffuse_color[:3], 1)
    return o

def cyl(name, x, y, z0, h, r, m, verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(x, y, z0 + h / 2))
    o = bpy.context.object; o.name = name
    o.data.materials.append(C[m]); o.color = (*C[m].diffuse_color[:3], 1)
    return o

T = 0.02  # wall thickness
# floor, walls (lower 0.3 m tarp skirt + vinyl above), roof
box("floor", 0, W, 0, D, -0.02, 0, "floor")
def wall_x(name, x, y0, y1):
    box(name + "_skirt", x - T / 2, x + T / 2, y0, y1, 0, 0.3, "wall")
    box(name + "_vinyl", x - T / 2, x + T / 2, y0, y1, 0.3, H, "vinyl")
def wall_y(name, y, x0, x1):
    box(name + "_skirt", x0, x1, y - T / 2, y + T / 2, 0, 0.3, "wall")
    box(name + "_vinyl", x0, x1, y - T / 2, y + T / 2, 0.3, H, "vinyl")
wall_x("wall_left", 0, 0, D)
wall_x("wall_right", W, 0.8, D)          # entrance opening: right wall, front corner, y 0..0.8
wall_y("wall_back", D, 0, W)
wall_y("wall_front", 0, 0, W)
box("roof", 0, W, 0, D, H, H + 0.03, "roof")
box("roof_ridge", 0, W, D / 2 - 0.05, D / 2 + 0.05, H + 0.03, 2.4, "roof")
for x in (0.02, W - 0.02):
    for y in (0.02, D - 0.02):
        cyl("pole", x, y, 0, H, 0.02, "dark", 8)

# counter: x 0.4..3.28, y 1.0..1.5, top 0.9 ; pillar at right end ; staff gap 0.6 to right wall
CX0, CX1, CY0, CY1, CZ = 0.4, 3.28, 1.0, 1.5, 0.9
box("counter_body", CX0, CX1, CY0 + 0.03, CY1, 0, CZ - 0.03, "steel")
box("counter_top", CX0 - 0.02, CX1, CY0, CY1, CZ - 0.03, CZ, "steel")
box("pillar", CX1, CX1 + 0.12, CY0 + 0.19, CY0 + 0.31, 0, H, "wood")
box("pillar_photo", CX1 - 0.002, CX1 + 0.002, CY0 + 0.21, CY0 + 0.29, 1.55, 1.62, "photo").location.x = CX1 - 0.003
box("pillar_switch", CX1 - 0.01, CX1, CY0 + 0.23, CY0 + 0.27, 1.25, 1.33, "white")
# built-in fish-cake pot (left of center), burner flames
box("odeng_pot", 1.0, 1.6, CY0 + 0.07, CY0 + 0.42, CZ - 0.08, CZ + 0.10, "steel")
box("odeng_broth", 1.02, 1.58, CY0 + 0.09, CY0 + 0.40, CZ + 0.07, CZ + 0.095, "photo")
# counter items (right of center)
cyl("spoon_holder", 1.95, 1.22, CZ, 0.17, 0.06, "steel")
box("plate_basket", 2.1, 2.45, 1.08, 1.33, CZ, CZ + 0.10, "red")
cyl("sauce_red", 2.6, 1.2, CZ, 0.20, 0.035, "red")
cyl("sauce_brown", 2.7, 1.2, CZ, 0.20, 0.035, "wood")
box("tissue", 2.95, 3.18, 1.1, 1.22, CZ, CZ + 0.10, "white")

# aisle y 1.5..2.0 ; cooking wall y 2.0..2.6 along the back
box("range_stand", 0.15, 0.80, 2.05, 2.55, 0, 0.70, "steel")
box("range", 0.15, 0.80, 2.10, 2.50, 0.70, 0.85, "dark")
box("griddle", 0.18, 0.47, 2.12, 2.45, 0.85, 0.90, "dark")
cyl("soup_pot", 0.62, 2.30, 0.85, 0.27, 0.16, "steel")
box("prep_table", 0.85, 1.65, 2.05, 2.55, 0, 0.85, "steel")
box("cutting_board", 1.25, 1.62, 2.15, 2.40, 0.85, 0.89, "wood")
for i, x in enumerate((0.90, 1.02, 1.14)):
    box(f"bin{i}", x, x + 0.10, 2.15, 2.33, 0.85, 0.95, "white")
box("basin", 0.95, 1.30, 2.15, 2.45, 0, 0.18, "red")
box("water_jug", 1.35, 1.55, 2.20, 2.40, 0, 0.40, "white")
box("cupboard", 1.75, 2.65, 2.20, 2.55, 0, 1.10, "wood")
for i in range(6):
    cyl(f"cup{i}", 1.83 + i * 0.15, 2.37, 1.10, 0.09, 0.045, "white")
box("soju_shelf", 2.75, 3.55, 2.15, 2.55, 0, 0.85, "steel")
box("icebox", 2.85, 3.33, 2.20, 2.50, 0, 0.30, "white")
for i in range(4):
    cyl(f"soju{i}", 2.85 + i * 0.09, 2.35, 0.85, 0.22, 0.033, "green")
cyl("kettle", 3.35, 2.35, 0.85, 0.18, 0.11, "steel")

# stools (customer zone), left -> right red blue red blue red ; leftmost = Yeon, next = empty seat
STOOLS = [0.70, 1.25, 1.80, 2.35, 2.90]
for i, x in enumerate(STOOLS):
    cyl(f"stool{i}", x, 0.78, 0, 0.45, 0.15, "red" if i % 2 == 0 else "blue")

# bulb (practical, only light) on its cord
cyl("bulb_cord", 1.84, 1.25, 2.06, H - 2.06, 0.004, "dark", 6)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.04, location=(1.84, 1.25, 2.0)); b = bpy.context.object; b.name = "bulb"
b.data.materials.append(C["white"]); b.color = (1, 1, 0.8, 1)

def person(name, x, y, height, seated=False, facing=0.0):
    hh = height / 7.3
    if seated:
        body = cyl(name + "_body", x, y, 0.45, height * 0.42, 0.17, "person", 12)
        head = cyl(name + "_head", x, y, 0.45 + height * 0.42, hh, 0.10, "person", 12)
    else:
        body = cyl(name + "_body", x, y, 0, height - hh, 0.18, "person", 12)
        head = cyl(name + "_head", x, y, height - hh, hh, 0.10, "person", 12)
    # nose block shows facing direction
    nx, ny = math.sin(facing), -math.cos(facing)
    box(name + "_nose", x + nx * 0.10 - 0.03, x + nx * 0.10 + 0.03, y + ny * 0.10 - 0.03, y + ny * 0.10 + 0.03,
        head.location.z, head.location.z + 0.05, "dark")

FACE = {k: math.radians(float(v)) for k, v in (kv.split("=") for kv in A.face.split(",") if kv)}
WHO = set(A.who.split(",")) if A.who else ({"haeun", "yeon"} if A.people else set())
if "haeun" in WHO:
    person("haeun", 2.30, 1.75, 1.63, facing=FACE.get("haeun", 0.0))       # aisle behind the counter
if "yeon" in WHO:
    person("yeon", STOOLS[0], 0.78, 1.78, seated=True, facing=FACE.get("yeon", math.pi))  # leftmost stool
if "yeon_stand" in WHO:
    person("yeon", 3.75, 0.35, 1.78, facing=FACE.get("yeon", math.pi * 1.25))  # just inside the entrance

# cameras
from mathutils import Vector
def cam(name, loc, target=None, lens=28, ortho=None):
    c = bpy.data.cameras.new(name); c.lens = lens; c.sensor_width = 36; c.sensor_fit = "HORIZONTAL"
    c.clip_start = 0.05
    if ortho: c.type = "ORTHO"; c.ortho_scale = ortho
    o = bpy.data.objects.new(name, c); scn.collection.objects.link(o)
    o.location = loc
    if target:
        d = Vector(target) - Vector(loc); o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o
CAMS = {
    # CAM A: standing in the customer zone at the front, looking at the counter and the back wall
    "camA": cam("camA", (2.0, -1.7, 1.25), (2.0, 2.0, 0.95), 28),
    # CAM B: standing in the aisle behind the counter, looking out at the stools and the front vinyl
    "camB": cam("camB", (1.45, 2.05, 1.75), None, 20),
    "top":  cam("top", (W / 2, D / 2, 6.0), None, ortho=4.6),
}
CAMS["camB"].rotation_euler = (math.radians(62), 0, math.radians(180))
# render settings: clay, object colors, soft studio light, cavity
scn.render.engine = "BLENDER_WORKBENCH"
sh = scn.display.shading
sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True; sh.show_shadows = True
sh.show_object_outline = True
rw, rh = (int(v) for v in A.res.split("x"))
scn.render.resolution_x, scn.render.resolution_y = rw, rh
scn.render.image_settings.file_format = "PNG"

WILD = {"camA": ("wall_front",), "camB": ()}
if A.shot:
    parts = A.shot.split(":")
    nm, loc, tgt, lens = parts[0], tuple(map(float, parts[1].split(","))), tuple(map(float, parts[2].split(","))), float(parts[3])
    CAMS[nm] = cam(nm, loc, tgt, lens)
    w = parts[4] if len(parts) > 4 else "front"
    WILD[nm] = {"front": ("wall_front",), "back": ("wall_back",), "none": ()}[w]
    A.cams = nm   # wild walls removed for the shot, like a real set
for n in A.cams.split(","):
    for o in scn.objects:
        if o.name.startswith(WILD.get(n, ("@",))): o.hide_render = True
    if n == "top":
        for o in scn.objects:
            if o.name.startswith(("roof", "wall_front")):
                o.hide_render = True
        scn.render.resolution_x, scn.render.resolution_y = 1400, 941
    scn.camera = CAMS[n]
    scn.render.filepath = os.path.join(A.out, f"blockout_{n}.png")
    bpy.ops.render.render(write_still=True)
    for o in scn.objects: o.hide_render = False
    scn.render.resolution_x, scn.render.resolution_y = rw, rh
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(A.out, "pojangmacha_blockout.blend"))
print("done")
