"""Auto UV Palette: xep them object vao palette DA CO, chi vao o con trong.

Diem de vo nhat cua tinh nang nay la "o nao dang trong":
  - doc sai o cua object da pack  -> ghi de len texture nguoi ta da ghep
  - bo qua alpha cua anh palette  -> object cu khong con trong scene la mat
  - chay lai tren object da trong palette -> UV bi thu nho lan thu hai

Test dung ca hai nguon (object trong scene + alpha cua anh) va chay lai de bat
dung ba loi do.

CHAY BANG tools\\run_tests.ps1.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

FAILED = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


def make_obj(name):
    """Mot quad co UV phu tron o 0..1."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
                     [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for i, co in enumerate([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]):
        uv.data[i].uv = co
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    return ob


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def cancelled(fn):
    """True neu operator bao loi (bpy.ops nem RuntimeError khi report ERROR)."""
    try:
        return fn() == {'CANCELLED'}
    except RuntimeError as err:
        print("       (bao loi: %s)" % err)
        return True


mod = kit.enable("ezg_auto_uv_palette")

props = bpy.context.scene.auto_uv_palette
props.cols = 3
props.rows = 3

# --- _uv_cell_index: doc lai dung o ma _place_uv_in_cell vua dat -------------
probe = make_obj("probe")
for index in (0, 1, 4, 8):
    mod._place_uv_in_cell(probe.data, mod._cell_rect(index, 3, 3))
    got = mod._uv_cell_index(probe.data, 3, 3)
    check(got == index, "_uv_cell_index doc lai o %d (duoc %s)" % (index, got))
    # tra UV ve 0..1 cho vong sau
    uv = probe.data.uv_layers[0]
    for i, co in enumerate([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]):
        uv.data[i].uv = co
bpy.data.objects.remove(probe)

# --- _image_occupancy: alpha cua anh palette ---------------------------------
img = bpy.data.images.new("pal_test", 300, 300, alpha=True)
buf = np.zeros((300, 300, 4), dtype=np.float32)
# pixel Blender bat dau tu day anh: o H1C1 (index 0) nam o 100 dong tren cung
buf[200:300, 0:100, 3] = 1.0
# o H2C3 (index 5)
buf[100:200, 200:300, 3] = 1.0
img.pixels.foreach_set(buf.ravel())
check(mod._image_occupancy(img, 3, 3) == {0, 5},
      "_image_occupancy doc dung 2 o dac (duoc %s)"
      % mod._image_occupancy(img, 3, 3))

# Anh lon hon 1024px phai di qua nhanh thu nho (anh 8K doc thang la ~1 GB
# float) ma van doc dung o. Phai la anh tu file: anh "generated" bi Blender
# dung generated_color dung lai buffer khi copy, khong phai truong hop that.
big = bpy.data.images.new("pal_big", 2048, 2048, alpha=True)
bigbuf = np.zeros((2048, 2048, 4), dtype=np.float32)
bigbuf[0:512, 512:1024, 3] = 1.0            # H4C2 -> index 13 trong grid 4x4
big.pixels.foreach_set(bigbuf.ravel())
del bigbuf
big.filepath_raw = os.path.join(bpy.app.tempdir, "pal_big.png")
big.file_format = 'PNG'
big.save()
bpy.data.images.remove(big)
big = bpy.data.images.load(os.path.join(bpy.app.tempdir, "pal_big.png"))
check(mod._image_occupancy(big, 4, 4) == {13},
      "anh 2K: thu nho roi van doc dung o (duoc %s)"
      % mod._image_occupancy(big, 4, 4))
check("pal_big.001" not in bpy.data.images,
      "ban copy tam de quet alpha da duoc xoa, khong ket lai trong file")
bpy.data.images.remove(big)

opaque = bpy.data.images.new("pal_opaque", 90, 90, alpha=True)
obuf = np.ones((90, 90, 4), dtype=np.float32)
opaque.pixels.foreach_set(obuf.ravel())
check(mod._image_occupancy(opaque, 3, 3) is None,
      "anh dac kin -> None (khong doan bua la het cho)")

# --- Pack 4 object dau, roi them 2 object vao o trong ------------------------
first = [make_obj("%d. Goc" % i) for i in range(1, 5)]
select(first)
check(bpy.ops.object.auto_uv_palette_pack() == {'FINISHED'}, "Pack 4 object")

mats = [m for m in bpy.data.materials if m.name.startswith("UVPalette_")]
check(len(mats) == 1 and mats[0].name == "UVPalette_3x3",
      "Pack tao dung 1 material UVPalette_3x3 (%s)"
      % [m.name for m in mats])

extra = [make_obj("9. Them A"), make_obj("9. Them B")]
select(extra)
check(bpy.ops.object.auto_uv_palette_add() == {'FINISHED'},
      "Add Selected to Empty Cells chay duoc")

cells = [mod._uv_cell_index(ob.data, 3, 3) for ob in extra]
check(cells == [4, 5], "2 object moi vao o 4 va 5, khong de len 0..3 (duoc %s)"
                       % cells)
check(all(ob.data.materials and ob.data.materials[0] is mats[0]
          for ob in extra),
      "object moi duoc gan material palette chung")
check([mod._uv_cell_index(ob.data, 3, 3) for ob in first] == [0, 1, 2, 3],
      "object cu van nam nguyen o cu")

# UV cua object moi phai vua dung 1 o, khong bi thu nho hai lan.
uv = extra[0].data.uv_layers[0]
co = np.empty(len(uv.data) * 2, dtype=np.float32)
uv.data.foreach_get("uv", co)
co.shape = (-1, 2)
width = float(co[:, 0].max() - co[:, 0].min())
check(abs(width - 1.0 / 3.0) < 1e-5,
      "UV object moi rong dung 1/3 o (duoc %.4f)" % width)

# --- Chay lai tren object da nam trong palette: phai tu choi -----------------
select(extra)
check(cancelled(bpy.ops.object.auto_uv_palette_add),
      "tu choi object da nam trong palette (khong thu nho UV lan 2)")
check(abs(float(width) - 1.0 / 3.0) < 1e-5 and
      abs(mod._uv_cell_index(extra[0].data, 3, 3) - 4) == 0,
      "UV object da trong palette khong bi dong vao")

# --- Anh palette bit them o: object sau phai tranh ca o do -------------------
# Gia lap palette da ghep san texture o H3C1 (index 6) du scene khong co object.
blocker = bpy.data.images.new("pal_block", 300, 300, alpha=True)
bbuf = np.zeros((300, 300, 4), dtype=np.float32)
for index in range(6):                       # 0..5 da co object that
    row, col = divmod(index, 3)
    y0 = 300 - (row + 1) * 100
    bbuf[y0:y0 + 100, col * 100:(col + 1) * 100, 3] = 1.0
bbuf[0:100, 0:100, 3] = 1.0                  # them o 6 (H3C1)
blocker.pixels.foreach_set(bbuf.ravel())
blocker.filepath_raw = os.path.join(bpy.app.tempdir, "pal_block.png")
blocker.file_format = 'PNG'
blocker.save()
props.palette_image = blocker.filepath_raw

after_block = make_obj("9. Them C")
select([after_block])
check(bpy.ops.object.auto_uv_palette_add() == {'FINISHED'},
      "Add chay duoc khi co ca anh palette")
check(mod._uv_cell_index(after_block.data, 3, 3) == 7,
      "tranh o 6 da co texture trong anh, vao o 7 (duoc %s)"
      % mod._uv_cell_index(after_block.data, 3, 3))

# --- Het o trong: tu choi, khong xep de len ----------------------------------
last = make_obj("9. Them D")
too_many = make_obj("9. Them E")
select([last, too_many])
check(cancelled(bpy.ops.object.auto_uv_palette_add),
      "2 object ma chi con 1 o -> tu choi")
luv = last.data.uv_layers[0]
lco = np.empty(len(luv.data) * 2, dtype=np.float32)
luv.data.foreach_get("uv", lco)
check(abs(float(lco.max() - lco.min()) - 1.0) < 1e-6,
      "object bi tu choi giu nguyen UV 0..1 (chua bi thu nho)")
check(not last.data.materials,
      "object bi tu choi chua bi gan material palette")

select([last])
check(bpy.ops.object.auto_uv_palette_add() == {'FINISHED'},
      "1 object vao dung o cuoi cung")
check(mod._uv_cell_index(last.data, 3, 3) == 8, "o cuoi cung la 8")

select([too_many])
check(cancelled(bpy.ops.object.auto_uv_palette_add),
      "palette day -> tu choi")

# --- Grid khong khop: khong duoc lay bua palette khac -----------------------
props.cols = 4
props.rows = 4
select([too_many])
check(cancelled(bpy.ops.object.auto_uv_palette_add),
      "doi grid sang 4x4 ma khong co palette 4x4 -> tu choi")
props.cols = 3
props.rows = 3

# --- JSX append: dung o, dung document dich ---------------------------------
jsx = mod._build_append_jsx([("A", "D:\\x\\a.png", 2, 1)], 3, 3, True,
                            "D:\\x\\pal.psd")
check('col: 2, row: 1' in jsx, "jsx ghi dung col/row")
check('var PSD = "D:/x/pal.psd";' in jsx, "jsx tro toi dung file PSD")
check('doc.width.as("px") / COLS' in jsx,
      "jsx lay kich thuoc o tu document that, khong tu Canvas trong panel")
jsx_active = mod._build_append_jsx([("A", "a.png", 0, 0)], 3, 3, False, "")
check('var PSD = "";' in jsx_active and "app.activeDocument" in jsx_active,
      "bo trong duong dan PSD -> dung document dang mo")

# --- Panel ve duoc: loi trong draw() la spam do ca sidebar ------------------
# Background mode khong tao duoc UILayout that, nen dung layout gia — van chay
# het phan dinh dang chuoi, doc property va quet scene cua draw().
class FakeLayout:
    def __init__(self, sink):
        self.sink = sink
        self.enabled = True

    def label(self, text="", icon='NONE'):
        self.sink.append(("label", text, icon))

    def row(self, align=False):
        return FakeLayout(self.sink)

    def column(self, align=False):
        return FakeLayout(self.sink)

    def box(self):
        return FakeLayout(self.sink)

    def prop(self, data, name, **kw):
        getattr(data, name)              # property phai ton tai that
        self.sink.append(("prop", name, None))

    def operator(self, idname, **kw):
        self.sink.append(("operator", idname, None))

    def separator(self):
        pass


class FakePanel:
    def __init__(self, sink):
        self.layout = FakeLayout(sink)


for grid, label in (((3, 3), "grid khop palette"),
                    ((4, 4), "grid khong co palette"),
                    ((1, 1), "grid 1x1")):
    props.cols, props.rows = grid
    sink = []
    try:
        mod.AUTOUVPAL_PT_view3d.draw(FakePanel(sink), bpy.context)
        drawn = True
    except Exception as err:          # noqa: BLE001 — chinh la thu dang bat
        drawn = False
        print("       (draw loi: %r)" % err)
    check(drawn, "panel ve duoc voi %s" % label)
    if drawn:
        names = [item[1] for item in sink]
        check("object.auto_uv_palette_add" in names
              and "object.auto_uv_palette_append_psd" in names
              and "palette_psd" in names,
              "panel co du nut/o nhap moi (%s)" % label)
props.cols, props.rows = 3, 3

if FAILED:
    print("\nFAILED %d:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_auto_uv_palette: OK")
