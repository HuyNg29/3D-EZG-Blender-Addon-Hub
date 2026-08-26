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


# --- Don node thua ----------------------------------------------------------
print("--- don node thua ---")

clean = bpy.data.node_groups.new("Clean", "GeometryNodeTree")
out = clean.nodes.new("NodeGroupOutput")
join = clean.nodes.new("GeometryNodeJoinGeometry")
clean.links.new(join.outputs[0], out.inputs[0])


def info_node(name, ob=None, wire=True):
    n = clean.nodes.new("GeometryNodeObjectInfo")
    n.name = name
    n.select = False
    if ob is not None:
        n.inputs["Object"].default_value = ob
    if wire:
        clean.links.new(n.outputs["Geometry"], join.inputs[0])
    return n


good = info_node("good", ob=cube, wire=True)            # co object + co day
no_obj = info_node("no_obj", ob=None, wire=True)         # trong nhung dang noi day
orphan = info_node("orphan", ob=cube, wire=False)        # co object, khong noi
dead = info_node("dead", ob=None, wire=False)            # trong va khong noi

check(mod.node_waste_reason(good) is None, "node co object va co day -> giu")
check(mod.node_waste_reason(no_obj) == mod.REASON_EMPTY_LINKED,
      "node trong nhung dang noi day -> canh bao dut mach (%s)"
      % mod.node_waste_reason(no_obj))
check(mod.node_waste_reason(orphan) == mod.REASON_UNLINKED,
      "node co object nhung khong noi -> thua (%s)" % mod.node_waste_reason(orphan))
check(mod.node_waste_reason(dead) == "trống, không nối",
      "node vua trong vua khong noi -> bao ca hai (%s)" % mod.node_waste_reason(dead))

# Tat tung dieu kien mot: nguoi dung phai chan duoc ve ma ho khong muon dong toi.
check(mod.node_waste_reason(orphan, remove_unlinked=False) is None,
      "tat 'khong noi' thi node khong noi duoc tha")
check(mod.node_waste_reason(no_obj, remove_empty=False) is None,
      "tat 'khong chua object' thi node trong dang noi day duoc tha")
check(mod.node_waste_reason(dead, remove_empty=False) == mod.REASON_UNLINKED,
      "tat 'khong chua object' van bat duoc node khong noi")

# Node khong phai Info khong bao gio bi dung toi, du no khong noi vao dau.
lonely = clean.nodes.new("GeometryNodeSetPosition")
check(mod.node_waste_reason(lonely) is None, "node khong phai Info -> khong dung toi")

found = mod.find_waste_nodes(clean)
check(sorted(n.name for n, _ in found) == ["dead", "no_obj", "orphan"],
      "quet ca cay ra dung 3 node thua (%s)" % [n.name for n, _ in found])

orphan.select = True
found_sel = mod.find_waste_nodes(clean, selected_only=True)
check([n.name for n, _ in found_sel] == ["orphan"],
      "pham vi 'dang chon' chi lay node da chon (%s)" % [n.name for n, _ in found_sel])

# Xoa that: node giu lai phai con nguyen, va day cua no khong duoc dut theo.
n_before = len(clean.nodes)
removed = mod.remove_nodes(clean, [n for n, _ in found])
check(removed == 3 and len(clean.nodes) == n_before - 3,
      "xoa dung 3 node (%d)" % removed)
check("good" in clean.nodes, "node con dung giu nguyen")
# Lay lai tham chieu: xoa node khac co the lam con tro Python cu thanh vo hieu.
check(clean.nodes["good"].outputs["Geometry"].is_linked,
      "day cua node giu lai khong bi dut")
check(mod.find_waste_nodes(clean) == [], "quet lai khong con node thua")


# --- Them object vao cay ----------------------------------------------------
print("--- them object vao Join ---")


def gn_tree(name):
    """Cay giong cay Blender tao ra khi them modifier Geometry Nodes."""
    t = bpy.data.node_groups.new(name, "GeometryNodeTree")
    t.interface.new_socket(name="Geometry", in_out='INPUT',
                           socket_type='NodeSocketGeometry')
    t.interface.new_socket(name="Geometry", in_out='OUTPUT',
                           socket_type='NodeSocketGeometry')
    gi = t.nodes.new("NodeGroupInput")
    go = t.nodes.new("NodeGroupOutput")
    go.location = (400.0, 0.0)
    t.links.new(gi.outputs[0], go.inputs[0])
    return t, gi, go


def mesh_obj(name):
    o = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.collection.objects.link(o)
    return o


tree1, gin1, gout1 = gn_tree("Build")
host = mesh_obj("Host")
md = host.modifiers.new("GeometryNodes", 'NODES')
md.node_group = tree1

check(mod._tree_hosts(tree1) == {host},
      "nhan ra object dang mang chinh cay nay lam modifier")

# Join dau tien: phai NOI RA Group Output, va thu dang cam vao output (Group
# Input) phai duoc cam vao Join chu khong bi thay the.
join1, created1, wired1 = mod.ensure_join(tree1)
check(created1 and wired1, "tao Join moi va noi ra Group Output")
# Dung `==` chu khong phai `is`: moi lan doc mot node qua RNA, Blender tra ve
# mot doi tuong Python MOI boc cung mot du lieu. `is` luon False, ke ca khi do
# dung la mot node — day la cach de viet mot test luon xanh ma khong kiem gi.
check(gout1.inputs[0].links[0].from_node == join1, "Group Output nhan tu Join")
# Group Input mang hinh cua chinh object deo modifier — mac dinh KHONG gop vao.
# Mach that su (node khac) thi van duoc giu, xem phan "day vao Join" ben duoi.
check(not any(l.from_node == gin1 for s in join1.inputs for l in s.links),
      "day Group Input bi bo, khong gop vao Join")

# Goi lai: phai DUNG LAI Join da co, khong de ra Join thu hai.
join2, created2, _ = mod.ensure_join(tree1)
check(join2 == join1 and not created2, "goi lai thi dung lai Join da co")
check(sum(1 for n in tree1.nodes
          if n.bl_idname == "GeometryNodeJoinGeometry") == 1,
      "chi co dung mot Join trong cay")

src_a = mesh_obj("Ghe")
src_b = mesh_obj("Ban")
made = mod.add_objects_to_join(tree1, [src_a, src_b], join1)
check(len(made) == 2, "tao 2 node Object Info")
check([n.label for n in made] == ["Ghe", "Ban"], "dat nhan luon theo ten object")
check(all(n.transform_space == 'RELATIVE' for n in made),
      "mac dinh Relative — object hien ra dung cho no dang dung")
check(all(n.outputs["Geometry"].is_linked for n in made), "ca 2 node deu noi vao Join")
check(set(mod.objects_feeding(join1)) == {src_a, src_b},
      "doc lai duoc object nao da co node trong Join")

# Cay khong co dau ra hinh khoi: Join van duoc tao nhung phai bao la CHUA noi,
# khong duoc im lang. Noi day vao socket ao cua Group Output bang Python khong
# bao loi nhung cung khong tao ra socket that — day di vao hu vo.
bare = bpy.data.node_groups.new("Bare", "GeometryNodeTree")
bare.nodes.new("NodeGroupOutput")
_, created3, wired3 = mod.ensure_join(bare)
check(created3 and not wired3, "cay khong co dau ra hinh khoi -> bao chua noi")

# Doi ten object roi chay nut dat nhan: node phai theo ten moi.
src_a.name = "Ghe_Sofa"
mod.label_info_nodes([tree1])
check(made[0].label == "Ghe_Sofa", "dat lai nhan sau khi doi ten object")

# Cot node phai dan thang va nam ben TRAI Join.
mod.set_collapse(made, True)
mod.arrange_nodes(mod.nodes_feeding(join1), axis='COLUMN', gap=10.0, order='NAME')
check(len({round(n.location.x, 4) for n in made}) == 1, "cot node thang le trai")
check(all(n.location.x < join1.location.x for n in made),
      "cot node nam ben trai Join")


# --- Day khong xoan, va bo day Group Input ----------------------------------
print("--- day vao Join ---")

tree2, gin2, gout2 = gn_tree("Wire")
join_w, _, _ = mod.ensure_join(tree2)
check(not any(l.from_node == gin2 for s in join_w.inputs for l in s.links),
      "mac dinh KHONG cam Group Input vao Join")
check(gout2.inputs[0].links[0].from_node == join_w,
      "Group Output van nhan tu Join du da bo Group Input")

tree3, gin3, gout3 = gn_tree("WireKeep")
join_k, _, _ = mod.ensure_join(tree3, keep_group_input=True)
check(any(l.from_node == gin3 for s in join_k.inputs for l in s.links),
      "bat 'giu day Group Input' thi van cam vao")
check(mod.drop_group_input_links(tree3, join_k) == 1, "go duoc day Group Input")
check(not any(l.from_node == gin3 for s in join_k.inputs for l in s.links),
      "go xong thi khong con day Group Input")

# Mach that (khong phai Group Input) dang cam vao output KHONG duoc bien mat.
tree4, gin4, gout4 = gn_tree("WireChain")
setpos = tree4.nodes.new("GeometryNodeSetPosition")
tree4.links.new(setpos.outputs[0], gout4.inputs[0])
join_c, _, _ = mod.ensure_join(tree4)
check(any(l.from_node == setpos for s in join_c.inputs for l in s.links),
      "node dang cam vao output duoc chuyen vao Join, khong bi vut")

# Go xoan: multi_input_sort_id CHI DOC va bang thu tu tao link, nen kiem tra
# bang chinh no — day la thu quyet dinh cho cam tren socket.
tree5, _, gout5 = gn_tree("Untangle")
join5, _, _ = mod.ensure_join(tree5)
objs = [mesh_obj("W_%d" % i) for i in range(4)]
made5 = mod.add_objects_to_join(tree5, objs, join5)

# Dat NGUOC voi thu tu tao link: W_0 xuong duoi cung, W_3 len tren cung. Cho
# cam tren socket van theo thu tu tao nen day cheo het qua nhau — dung canh
# ma go xoan phai sua. Neu dat xuoi thi trang thai "truoc" da dung san, va
# test se xanh ma khong chung minh duoc gi.
for i, n in enumerate(made5):
    n.location = (-400.0, 100.0 * i)
top_down = [n.label for n in sorted(made5, key=lambda n: -n.location.y)]

order_before = [l.from_node.label for l in
                sorted(join5.inputs[0].links, key=lambda l: l.multi_input_sort_id)]
check(order_before != top_down,
      "truoc khi go: cho cam khong khop thu tu tren-duoi (%s)" % order_before)

remade = mod.untangle_links(tree5, join5.inputs[0])
check(remade == 4, "cam lai du 4 day (%d)" % remade)
order_after = [l.from_node.label for l in
               sorted(join5.inputs[0].links, key=lambda l: l.multi_input_sort_id)]
check(order_after == top_down,
      "sau khi go: cho cam chay tu tren xuong dung thu tu node (%s)" % order_after)
check(len(join5.inputs[0].links) == 4, "khong mat day nao khi cam lai")

# Node duoi cung leo len tren -> cam lai phai theo vi tri moi, khong theo cu.
made5[0].location = (-400.0, 900.0)
mod.untangle_links(tree5, join5.inputs[0])
top = min(join5.inputs[0].links, key=lambda l: l.multi_input_sort_id)
check(top.from_node.label == made5[0].label,
      "node leo len tren cung thi day cua no cam len cho tren cung (%s)"
      % top.from_node.label)

check(mod.untangle_downstream(tree5, made5) == 4,
      "untangle_downstream tim ra Join tu chinh cac node nguon")


# --- Chon object tu node ----------------------------------------------------
print("--- chon object tu node ---")

vl = bpy.context.view_layer
grp = bpy.data.collections.new("Bo_Ban_Ghe")
bpy.context.scene.collection.children.link(grp)
c1, c2 = mesh_obj("Trong_Nhom_1"), mesh_obj("Trong_Nhom_2")
for o in (c1, c2):
    grp.objects.link(o)

# Danh sach object cua view layer duoc dung lai theo depsgraph. Vua link object
# xong ma doc ngay thi no chua co trong do — trong Blender that thi khong gap vi
# nguoi dung bam nut rat lau sau khi object da ton tai.
print("    truoc update: vl thay %d/3 object"
      % sum(1 for o in (c1, c2, src_a) if vl.objects.get(o.name) is not None))
vl.update()
print("    sau  update: vl thay %d/3 object"
      % sum(1 for o in (c1, c2, src_a) if vl.objects.get(o.name) is not None))

tree6, _, _ = gn_tree("Pick")
n_obj6 = tree6.nodes.new("GeometryNodeObjectInfo")
n_obj6.inputs["Object"].default_value = src_a
n_coll6 = tree6.nodes.new("GeometryNodeCollectionInfo")
n_coll6.inputs["Collection"].default_value = grp
n_empty6 = tree6.nodes.new("GeometryNodeObjectInfo")

check(mod.objects_of_nodes([n_obj6]) == [src_a], "node Object Info -> dung object do")
check(sorted(o.name for o in mod.objects_of_nodes([n_coll6])) ==
      ["Trong_Nhom_1", "Trong_Nhom_2"],
      "node Collection Info -> moi object trong nhom")
check(mod.objects_of_nodes([n_empty6]) == [], "node trong -> khong chon gi")

# Node active phai xep CUOI de object cua no thanh object active.
for n in (n_obj6, n_coll6):
    n.select = True
n_empty6.select = False
tree6.nodes.active = n_obj6
check(mod.selected_info_nodes(tree6)[-1] == n_obj6, "node active xep cuoi danh sach")

picked = mod.select_objects(vl, [c1, c2, src_a])
check(picked == 3, "chon duoc 3 object (%d)" % picked)
check(vl.objects.active == src_a, "object cuoi danh sach thanh object active")
check(sorted(o.name for o in vl.objects if o.select_get()) ==
      sorted([c1.name, c2.name, src_a.name]), "dung 3 object do dang duoc chon")

# Chon lan hai phai BO CHON nhung cai cu, khong cong don.
mod.select_objects(vl, [c1])
check([o.name for o in vl.objects if o.select_get()] == [c1.name],
      "chon lan hai khong cong don vao lan truoc")

if FAILED:
    print("\nFAILED %d:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_gn_info_namer: OK")
