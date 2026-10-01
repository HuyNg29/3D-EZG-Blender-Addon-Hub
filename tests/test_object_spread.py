"""Object Spread: pivot thang hang theo toa do, khong chong nhau, con di theo parent.

Nhung cho de vo:
  - PIVOT phai nam dung diem luoi: cung cot cung X, cung hang cung Y, Z = 0.
    Luoi giua goc 0,0,0, KHONG theo 3D cursor (1.1.0 theo cursor, cursor dat
    nham len object la ca luoi bay len cao). Ban 1.0.0 dat TAM HINH vao giua o nen asset co pivot o mep (rat hay
    gap: pivot o day / o mat sau) ra lech hang lech cot, nhin lung tung.
  - object to nho lan lon -> buoc luoi phai du cho object LON NHAT, khong thi chong
  - parent va con cung chon -> con KHONG duoc xep rieng (vo cum), chi di theo parent
  - chon con ma khong chon parent -> con dich theo the gioi nhung VAN giu parent
  - parent xoay / scale -> doi location trong khong gian parent phai tinh dung
  - collection instance: hinh khong nam trong bound_box cua Empty, van phai tinh
  - Ve 0,0,0 khong de lai "-0" li ti trong location

CHAY BANG tools\\run_tests.ps1.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

FAILED = []
TOL = 1e-4


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


mod = kit.enable("ezg_object_spread")
scene = bpy.context.scene
view_layer = bpy.context.view_layer

def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    # Khong update thi view_layer.objects con giu cho trong (None) cua object vua xoa.
    view_layer.update()


clear_scene()


def box(name, size, location=(0.0, 0.0, 0.0), parent=None, link=True, offset=(0.0, 0.0)):
    """Hop chu nhat kich thuoc `size`, pivot nam o day (giong asset game).
    `offset` dich hinh theo XY de pivot lech khoi tam, vd nam o mep."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(offset[0], offset[1], size[2] / 2), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    if link:
        scene.collection.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    ob.location = location
    return ob


def select(*objs):
    for ob in view_layer.objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    view_layer.objects.active = objs[0] if objs else None
    view_layer.update()


def bounds(*objs):
    """Hop bao XY the gioi cua mot cum object."""
    view_layer.update()
    pts = [ob.matrix_world @ Vector(c) for ob in objs for c in ob.bound_box]
    return (min(p.x for p in pts), min(p.y for p in pts),
            max(p.x for p in pts), max(p.y for p in pts))


def gap_between(a, b):
    """Khoang trong nho nhat giua hai hop bao (am = chong len nhau)."""
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    return max(dx, dy)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def same_matrix(a, b):
    return all(close(ra, rb) for ra, rb in zip(a, b))


def pivot(ob):
    view_layer.update()
    return ob.matrix_world.translation


# --- grid_cells -------------------------------------------------------------
print("--- grid_cells ---")


def row_counts(cells):
    counts = {}
    for _, row in cells:
        counts[row] = counts.get(row, 0) + 1
    return [counts[r] for r in sorted(counts)]


cells, c, r = mod.grid_cells(10, 'AUTO', 0, 0)
check((c, r) == (4, 3) and row_counts(cells) == [4, 4, 2], "AUTO 10 -> 4 x 3 (%d x %d)" % (c, r))
cells, c, r = mod.grid_cells(7, 'COLUMNS', 3, 99)
check((c, r) == (3, 3) and row_counts(cells) == [3, 3, 1], "COLUMNS 3 cho 7 -> 3,3,1")
cells, c, r = mod.grid_cells(7, 'ROWS', 99, 5)
check((c, r) == (2, 5) and row_counts(cells) == [2, 2, 1, 1, 1],
      "ROWS 5 cho 7 -> giu du 5 hang 2,2,1,1,1 (%s)" % row_counts(cells))
cells, c, r = mod.grid_cells(3, 'COLUMNS', 10, 1)
check((c, r) == (3, 1), "so cot lon hon so object -> 1 hang 3 cot")
cells, c, r = mod.grid_cells(3, 'ROWS', 1, 10)
check((c, r) == (1, 3), "so hang lon hon so object -> 1 cot 3 hang")
check(mod.grid_cells(0, 'AUTO', 1, 1) == ([], 0, 0), "0 object -> luoi rong")


# --- Xep: kich thuoc lan lon, thu tu theo ten --------------------------------
print("--- xep luoi ---")

# Ten co so: Rock_2 phai dung truoc Rock_10.
rocks = [box("Rock_10", (1.0, 1.0, 1.0), (0, 0, 0.5)),
         box("Rock_2", (4.0, 2.0, 3.0), (0, 0, 0.5)),
         box("Rock_1", (0.5, 3.0, 1.0), (0, 0, 0.5)),
         box("Rock_3", (2.0, 2.0, 2.0), (0, 0, 0.5)),
         box("Rock_4", (1.0, 1.0, 1.0), (0, 0, 0.5))]
select(*rocks)
# Cursor de lech ca X, Y, Z: luoi phai bo qua no.
scene.cursor.location = (10.0, -5.0, 3.0)
scene.ezg_spread.mode = 'COLUMNS'
scene.ezg_spread.columns = 3
scene.ezg_spread.gap = 0.5

result = bpy.ops.ezg_spread.arrange()
check(result == {'FINISHED'}, "arrange chay xong (%s)" % result)

def reading_order(objs):
    """Ten object doc theo tam hop bao: hang tren truoc, trong hang trai truoc."""
    def key(o):
        b = bounds(o)
        return (-round((b[1] + b[3]) / 2, 3), round((b[0] + b[2]) / 2, 3))
    return [o.name for o in sorted(objs, key=key)]


order = reading_order(rocks)
check(order == ["Rock_1", "Rock_2", "Rock_3", "Rock_4", "Rock_10"],
      "thu tu doc trai -> phai, tren -> duoi theo ten tu nhien (%s)" % order)

boxes = {o.name: bounds(o) for o in rocks}
worst = min(gap_between(boxes[a.name], boxes[b.name])
            for i, a in enumerate(rocks) for b in rocks[i + 1:])
check(worst >= 0.5 - TOL, "khong cap nao gan nhau hon gap 0.5 (gan nhat %.4f)" % worst)
check(all(o.location.z == 0.0 for o in rocks), "moi pivot o Z = 0, khong theo Z cua cursor")

# Pivot cung cot trung X, cung hang trung Y — trung DUNG so, khong chi xap xi.
cx = {o.name: o.location.x for o in rocks}
cy = {o.name: o.location.y for o in rocks}
check(cx["Rock_1"] == cx["Rock_4"] and cx["Rock_2"] == cx["Rock_10"], "cung cot -> cung X")
check(cy["Rock_1"] == cy["Rock_2"] == cy["Rock_3"] and cy["Rock_4"] == cy["Rock_10"],
      "cung hang -> cung Y")
# Pivot o giua hinh theo XY: buoc cot = rong nhat (4.0) + gap, buoc hang = sau nhat (3.0) + gap.
check(abs((cx["Rock_2"] - cx["Rock_1"]) - 4.5) < TOL, "buoc cot = rong nhat + gap (4.5)")
check(abs((cy["Rock_1"] - cy["Rock_4"]) - 3.5) < TOL, "buoc hang = sau nhat + gap (3.5)")
# Luoi 3 x 2 nam giua goc 0,0,0, khong phai giua cursor.
mid_x = (cx["Rock_1"] + cx["Rock_3"]) / 2
mid_y = (cy["Rock_1"] + cy["Rock_4"]) / 2
check(abs(mid_x) < TOL and abs(mid_y) < TOL,
      "tam luoi o goc 0,0,0 (%.3f, %.3f)" % (mid_x, mid_y))

# Operator ghi nguoc gia tri vao panel (de chinh o F9 thi panel theo).
bpy.ops.ezg_spread.arrange(mode='ROWS', rows=1, gap=2.0)
check(scene.ezg_spread.mode == 'ROWS' and scene.ezg_spread.rows == 1
      and abs(scene.ezg_spread.gap - 2.0) < TOL, "dat property cho operator -> panel cap nhat")
check(len({o.location.y for o in rocks}) == 1, "ROWS 1 -> tat ca tren mot hang")

scene.cursor.location = (0.0, 0.0, 0.0)


# --- Pivot lech khoi tam (loi cua ban 1.0.0) ---------------------------------
print("--- pivot lech khoi tam ---")

clear_scene()
# Pivot o mep sau (-Y), o goc, o mep trai... va dang nam lung tung ca X, Y, Z.
props = [box("Prop_1", (1.0, 2.0, 1.0), (3.1, 0.7, 0.4), offset=(0.0, 1.0)),
         box("Prop_2", (0.4, 0.4, 0.8), (-2.0, 5.0, -1.3)),
         box("Prop_3", (2.0, 1.0, 1.0), (0.2, -4.4, 2.2), offset=(1.0, 0.5)),
         box("Prop_4", (1.5, 1.5, 0.5), (8.0, 1.0, 0.0), offset=(-0.75, 0.0)),
         box("Prop_5", (0.6, 3.0, 2.0), (-6.0, -1.0, 0.9), offset=(0.0, -1.5)),
         box("Prop_6", (1.0, 1.0, 1.0), (1.0, 1.0, 1.0))]
select(*props)
bpy.ops.ezg_spread.arrange(mode='COLUMNS', columns=3, gap=0.3)
loc = {o.name: tuple(o.location) for o in props}
check(loc["Prop_1"][0] == loc["Prop_4"][0] and loc["Prop_2"][0] == loc["Prop_5"][0]
      and loc["Prop_3"][0] == loc["Prop_6"][0], "pivot lech tam: cung cot van cung X")
check(loc["Prop_1"][1] == loc["Prop_2"][1] == loc["Prop_3"][1]
      and loc["Prop_4"][1] == loc["Prop_5"][1] == loc["Prop_6"][1],
      "pivot lech tam: cung hang van cung Y (%s)" % sorted({round(v[1], 4) for v in loc.values()}))
check({v[2] for v in loc.values()} == {0.0}, "pivot lech tam: moi pivot ve Z = 0")
xs = sorted({v[0] for v in loc.values()})
ys = sorted({v[1] for v in loc.values()})
check(close([xs[1] - xs[0]], [xs[2] - xs[1]]) and close([sum(xs) / 3, sum(ys) / 2], [0, 0]),
      "pivot lech tam: cot cach deu, luoi pivot nam giua goc (%s, %s)" % (xs, ys))
pb = {o.name: bounds(o) for o in props}
worst = min(gap_between(pb[a.name], pb[b.name]) for i, a in enumerate(props) for b in props[i + 1:])
check(worst >= 0.3 - TOL, "pivot lech tam: van khong cap nao chong nhau (gan nhat %.4f)" % worst)


# --- Parent / con -----------------------------------------------------------
print("--- parent / con ---")

clear_scene()

car = box("Car", (2.0, 4.0, 1.5), (0, 0, 0))
wheel = box("Wheel", (1.0, 1.0, 1.0), (3.0, 0.0, 0.0), parent=car)   # thoi ra ngoai than xe
bolt = box("Bolt", (0.2, 0.2, 0.2), (0.0, 0.0, 1.0), parent=wheel)   # chau, khong chon
crate = box("Crate", (1.0, 1.0, 1.0), (0, 0, 0))
view_layer.update()
rel_wheel = car.matrix_world.inverted() @ wheel.matrix_world
rel_bolt = car.matrix_world.inverted() @ bolt.matrix_world

select(car, wheel, crate)
roots, followers = mod.selection_roots(list(bpy.context.selected_objects))
check([o.name for o in roots] == ["Car", "Crate"] and followers == 1,
      "goc = Car, Crate; Wheel di theo (%s, %d)" % ([o.name for o in roots], followers))

scene.ezg_spread.mode = 'AUTO'
scene.ezg_spread.gap = 1.0
bpy.ops.ezg_spread.arrange()
view_layer.update()

check(wheel.parent == car and bolt.parent == wheel, "khong go parent nao")
check(same_matrix(car.matrix_world.inverted() @ wheel.matrix_world, rel_wheel),
      "Wheel giu nguyen vi tri so voi Car")
check(same_matrix(car.matrix_world.inverted() @ bolt.matrix_world, rel_bolt),
      "Bolt (khong chon) cung di theo")
# Cum Car tinh ca banh xe thoi ra ngoai -> Crate khong duoc de len banh xe.
g = gap_between(bounds(car, wheel, bolt), bounds(crate))
check(g >= 1.0 - TOL, "Crate cach ca cum Car + Wheel dung gap (%.4f)" % g)

# Chon con ma KHONG chon parent: con dich theo the gioi, van giu parent.
car_before = car.matrix_world.copy()
select(wheel)
scene.cursor.location = (20.0, 0.0, 0.0)
bpy.ops.ezg_spread.arrange()
view_layer.update()
check(wheel.parent == car, "chi chon Wheel -> van con parent Car")
check(car.matrix_world == car_before, "Car (khong chon) khong bi dich")
check(close(pivot(wheel), (0.0, 0.0, 0.0)),
      "pivot Wheel ve giua luoi 0,0,0 du cursor o cho khac (%s)"
      % (tuple(round(v, 4) for v in pivot(wheel)),))
scene.cursor.location = (0.0, 0.0, 0.0)


# --- Ve 0,0,0 ---------------------------------------------------------------
print("--- ve 0,0,0 ---")

# Parent xoay + scale: location cua con nam trong khong gian parent nen phai quy doi.
car.rotation_euler = (0.0, 0.0, math.radians(90.0))
car.scale = (2.0, 2.0, 2.0)
crate.location = (7.3, -2.1, 4.4)
view_layer.update()
rel_wheel = car.matrix_world.inverted() @ wheel.matrix_world

select(car, wheel, crate)
result = bpy.ops.ezg_spread.to_origin()
view_layer.update()
check(result == {'FINISHED'}, "to_origin chay xong")
check(close(car.matrix_world.translation, (0, 0, 0)), "Car ve 0,0,0")
check(tuple(crate.location) == (0.0, 0.0, 0.0), "Crate ve dung 0,0,0, khong con -0 li ti (%s)"
      % (tuple(crate.location),))
check(same_matrix(car.matrix_world.inverted() @ wheel.matrix_world, rel_wheel),
      "Wheel (con, cung chon) giu vi tri so voi Car, khong bi keo ve 0")

# Chi chon con cua parent xoay/scale -> pivot cua con ve 0,0,0 the gioi.
car.location = (5.0, 5.0, 1.0)
select(wheel)
bpy.ops.ezg_spread.to_origin()
view_layer.update()
check(wheel.parent == car and close(wheel.matrix_world.translation, (0, 0, 0)),
      "chi chon Wheel -> pivot ve 0,0,0, van giu parent (%s)"
      % (tuple(round(v, 5) for v in wheel.matrix_world.translation),))

# Delta location: location = -delta de pivot nam dung goc.
crate.delta_location = (1.0, 2.0, 3.0)
crate.location = (4.0, 4.0, 4.0)
select(crate)
bpy.ops.ezg_spread.to_origin()
view_layer.update()
check(close(crate.matrix_world.translation, (0, 0, 0)), "co delta_location van ve dung 0,0,0")
crate.delta_location = (0.0, 0.0, 0.0)


# --- Collection instance ----------------------------------------------------
print("--- collection instance ---")

clear_scene()

asset = bpy.data.collections.new("House")
house = box("House_Mesh", (6.0, 6.0, 4.0), link=False)
asset.objects.link(house)
inst = bpy.data.objects.new("House_Inst", None)
inst.instance_type = 'COLLECTION'
inst.instance_collection = asset
scene.collection.objects.link(inst)
lamp = bpy.data.objects.new("Lamp", bpy.data.lights.new("Lamp", 'POINT'))
scene.collection.objects.link(lamp)
small = box("Small", (1.0, 1.0, 1.0))

select(inst, lamp, small)
bpy.ops.ezg_spread.arrange(mode='COLUMNS', columns=3, gap=1.0)
view_layer.update()
house_box = (inst.location.x - 3, inst.location.y - 3, inst.location.x + 3, inst.location.y + 3)
g = gap_between(house_box, bounds(small))
check(g >= 1.0 - TOL, "hinh cua collection instance (6 m) duoc tinh vao o (%.4f)" % g)
check(abs(lamp.location.x - inst.location.x) >= 6.0 + 1.0 - TOL,
      "Light (khong co hinh) van chiem mot o theo pivot")


# --- Khong chon gi ----------------------------------------------------------
print("--- khong chon gi ---")
select()
check(not bpy.ops.ezg_spread.arrange.poll(), "khong chon gi -> nut Xep bi khoa")
check(not bpy.ops.ezg_spread.to_origin.poll(), "khong chon gi -> nut Ve 0,0,0 bi khoa")


print("=" * 70)
if FAILED:
    print("THAT BAI %d muc:" % len(FAILED))
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("OBJECT SPREAD: TAT CA DEU DAT")
sys.exit(0)
