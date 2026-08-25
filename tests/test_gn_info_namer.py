"""GN Info Namer phai dat nhan dung, va phai voi toi node NAM TRONG GROUP LONG.

Ban goc cua addon chi quet `modifier.node_group`, nen mot node Object Info nam
trong group con (rat pho bien: mot group "scatter" dung lai o nhieu noi) khong
bao gio duoc dat nhan. Test dung cau truc long nhau de bat dung loi do.

Hai diem con lai de vo:
  - node chua tro toi object nao -> phai DE NGUYEN nhan, khong xoa ghi chu tay
  - chay lai lan hai -> khong co gi doi (khong dem trung)

CHAY BANG tools\\run_tests.ps1.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

import bpy  # noqa: E402

FAILED = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


mod = kit.enable("ezg_gn_info_namer")

# --- Du lieu: mot cay cha chua mot group con, moi ben mot node Info ----------
cube = bpy.data.objects.new("Cai_Ghe", bpy.data.meshes.new("Cai_Ghe"))
bpy.context.collection.objects.link(cube)
coll = bpy.data.collections.new("Nhom_Cay")

inner = bpy.data.node_groups.new("Inner", "GeometryNodeTree")
n_coll = inner.nodes.new("GeometryNodeCollectionInfo")
n_coll.inputs["Collection"].default_value = coll

outer = bpy.data.node_groups.new("Outer", "GeometryNodeTree")
n_obj = outer.nodes.new("GeometryNodeObjectInfo")
n_obj.inputs["Object"].default_value = cube
n_empty = outer.nodes.new("GeometryNodeObjectInfo")   # chua tro toi gi
n_empty.label = "ghi chu tay"
n_group = outer.nodes.new("GeometryNodeGroup")
n_group.node_tree = inner

trees = list(mod._walk_trees(outer))
check(len(trees) == 2, "_walk_trees di vao group long (%d cay)" % len(trees))

renamed, empty = mod.label_info_nodes(mod._walk_trees(outer))
check(renamed == 2, "dat nhan 2 node (duoc %d)" % renamed)
check(empty == 1, "dem 1 node chua tro toi gi (duoc %d)" % empty)
check(n_obj.label == "Cai_Ghe", "Object Info -> %r" % n_obj.label)
check(n_coll.label == "Nhom_Cay", "Collection Info trong group long -> %r" % n_coll.label)
check(n_empty.label == "ghi chu tay", "node trong giu nguyen ghi chu tay")

# Chay lai: khong duoc dem lai nhung node da dung nhan.
renamed2, _ = mod.label_info_nodes(mod._walk_trees(outer))
check(renamed2 == 0, "chay lai khong doi gi (bao %d)" % renamed2)

# Doi object -> nhan cu thanh lech, chay lai phai cap nhat.
cube.name = "Ghe_Doi_Ten"
renamed3, _ = mod.label_info_nodes(mod._walk_trees(outer))
check(renamed3 == 1 and n_obj.label == "Ghe_Doi_Ten",
      "doi ten object roi chay lai -> nhan cap nhat (%r)" % n_obj.label)

# Vong lap group tro vao chinh no khong duoc lam treo _walk_trees.
inner.nodes.new("GeometryNodeGroup").node_tree = outer
check(len(list(mod._walk_trees(outer))) == 2, "group tro vong lai khong lap vo han")

# Cay khong phai geometry nodes khong duoc lot vao _trees_in_file.
bpy.data.node_groups.new("ShaderGroup", "ShaderNodeTree")
names = [t.name for t in mod._trees_in_file()]
check("ShaderGroup" not in names and "Outer" in names,
      "_trees_in_file chi lay GeometryNodeTree (%s)" % ", ".join(names))


# --- Sap xep ----------------------------------------------------------------
print("--- sap xep ---")

lay = bpy.data.node_groups.new("Layout", "GeometryNodeTree")


def obj_info(name, x, y, label=""):
    n = lay.nodes.new("GeometryNodeObjectInfo")
    n.name = name
    n.location = (x, y)
    n.label = label
    n.select = False
    return n


# Ba node lech lac, thu tu tren xuong la c (y=400), a (y=100), b (y=-200).
c = obj_info("c", 30.0, 400.0, "Zebra")
a = obj_info("a", -50.0, 100.0, "Mango")
b = obj_info("b", 900.0, -200.0, "Apple")

changed = mod.set_collapse([a, b, c], True)
check(changed == 3 and all(n.hide for n in (a, b, c)), "thu nho ca 3 node")
check(mod.set_collapse([a, b, c], True) == 0, "thu nho lan hai khong dem lai")

GAP = 10.0
STEP = mod.HIDDEN_HEIGHT + GAP
mod.arrange_nodes([a, b, c], axis='COLUMN', gap=GAP, order='POSITION')

xs = {round(n.location.x, 4) for n in (a, b, c)}
check(xs == {-50.0}, "ca cot thang le trai theo node trai nhat (%s)" % xs)
check(c.location.y == 400.0, "node tren cung giu nguyen do cao")
check(abs(a.location.y - (400.0 - STEP)) < 1e-4,
      "node thu hai cach deu (%.1f)" % a.location.y)
check(abs(b.location.y - (400.0 - 2 * STEP)) < 1e-4,
      "node thu ba cach deu (%.1f)" % b.location.y)

# Sap theo nhan: Apple, Mango, Zebra — khac han thu tu vi tri.
mod.arrange_nodes([a, b, c], axis='COLUMN', gap=GAP, order='NAME')
by_y = sorted((a, b, c), key=lambda n: -n.location.y)
check([n.label for n in by_y] == ["Apple", "Mango", "Zebra"],
      "sap theo nhan A->Z (%s)" % [n.label for n in by_y])

# Hang ngang: cung y, cach nhau theo be ngang that cua node.
mod.arrange_nodes([a, b, c], axis='ROW', gap=GAP, order='NAME')
ys = {round(n.location.y, 4) for n in (a, b, c)}
check(len(ys) == 1, "hang ngang thang le tren (%s)" % ys)
by_x = sorted((a, b, c), key=lambda n: n.location.x)
check(abs((by_x[1].location.x - by_x[0].location.x) - (by_x[0].width + GAP)) < 1e-4,
      "hang ngang cach nhau theo be ngang node")

# Node trong frame phai duoc dan RIENG: location cua chung tinh theo goc frame,
# tron chung voi node ngoai frame se nhay lung tung.
frame = lay.nodes.new("NodeFrame")
d = obj_info("d", 5.0, 5.0)
e = obj_info("e", 7.0, -300.0)
d.parent = frame
e.parent = frame
mod.arrange_nodes([a, b, c, d, e], axis='COLUMN', gap=GAP, order='POSITION')
check(round(d.location.x, 4) == 5.0 and round(e.location.x, 4) == 5.0,
      "node trong frame dan theo goc frame, khong nhay ra ngoai (%.1f, %.1f)"
      % (d.location.x, e.location.x))
check(round(a.location.x, 4) != 5.0, "node ngoai frame khong bi keo vao cot cua frame")

# Frame va reroute khong duoc dua vao danh sach sap xep.
lay.nodes.new("NodeReroute").select = True
frame.select = True
for n in (a, b, c):
    n.select = True
sel = mod._arrange_targets(lay, 'SELECTED')
check(sorted(n.name for n in sel) == ["a", "b", "c"],
      "bo qua frame va reroute (%s)" % [n.name for n in sel])

info_scope = mod._arrange_targets(lay, 'INFO')
check(len(info_scope) == 5, "pham vi INFO lay het 5 node Info (%d)" % len(info_scope))

# Node chua tung duoc ve co dimensions = 0 — khong duoc rot ve chieu cao 0,
# neu khong ca cot se chong len nhau thanh mot dong.
mod.set_collapse([a, b, c], False)
check(a.dimensions.y == 0.0, "node chua ve that su co dimensions = 0")
check(mod._node_height(a) > 100.0,
      "uoc luong chieu cao khi khong do duoc (%.1f)" % mod._node_height(a))
mod.arrange_nodes([a, b, c], axis='COLUMN', gap=GAP, order='POSITION')
stack = sorted((a, b, c), key=lambda n: -n.location.y)
gaps = [abs(n.location.y - m.location.y) for n, m in zip(stack, stack[1:])]
check(all(g > 100.0 for g in gaps), "node mo ra khong chong len nhau (%s)" % gaps)

if FAILED:
    print("\nFAILED %d:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_gn_info_namer: OK")
