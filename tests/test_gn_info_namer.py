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

if FAILED:
    print("\nFAILED %d:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_gn_info_namer: OK")
