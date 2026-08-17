# Auto UV Palette — Blender 4.x / 5.x
# Xếp UV của nhiều object (dùng chung 1 material) vào các ô của một tấm palette.
# Nhập số cột x hàng, UV của mỗi object được scale xuống đúng bằng kích thước ô
# (grid 3x3 -> nhân 1/3) rồi dịch vào ô của nó. Thứ tự: theo tên object
# (hiểu số, "2." trước "10."), trái → phải, trên → dưới.

bl_info = {
    "name": "Auto UV Palette",
    "author": "EasyGoing Visual",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport / UV Editor > Sidebar (N) > UV Palette",
    "description": "Scale and arrange the UVs of the selected objects into a grid palette",
    "category": "UV",
}

import glob
import math
import os
import re
import subprocess
import sys

import bpy
import numpy as np
from bpy.props import (
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

_PREVIEW_ROWS = 10
# Texture gốc nhỏ hơn mức này thì bỏ qua, không phóng to lên cho đủ size.
_MIN_SOURCE_PX = 2048
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_JSX_NAME = "auto_uv_palette_build.jsx"

# Script Photoshop: dựng document rồi Place từng PNG thành Smart Object.
# Place đặt layer mới NGAY TRÊN layer đang active, nên vòng lặp chạy ngược để
# object đầu tiên (ô trên-trái) nằm trên cùng bảng Layers.
_JSX_TEMPLATE = """\
#target photoshop
// Sinh tự động bởi add-on Auto UV Palette — đừng sửa tay, chạy lại add-on.
(function () {
    var CANVAS = %(canvas)d;
    var COLS = %(cols)d;
    var ROWS = %(rows)d;
    var LINKED = %(linked)s;
    var ITEMS = [
%(items)s
    ];

    function placeSmartObject(path, linked) {
        var d = new ActionDescriptor();
        d.putPath(stringIDToTypeID("null"), new File(path));
        if (linked) {
            d.putBoolean(stringIDToTypeID("linked"), true);
        }
        executeAction(stringIDToTypeID("placeEvent"), d, DialogModes.NO);
    }

    function sizeOf(layer) {
        var b = layer.bounds;
        return {
            w: b[2].as("px") - b[0].as("px"),
            h: b[3].as("px") - b[1].as("px"),
            cx: (b[0].as("px") + b[2].as("px")) / 2,
            cy: (b[1].as("px") + b[3].as("px")) / 2
        };
    }

    var oldUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    try {
        var doc = app.documents.add(CANVAS, CANVAS, 72, "AutoUVPalette",
                                    NewDocumentMode.RGB,
                                    DocumentFill.TRANSPARENT);
        var filler = doc.layers[0];
        var cellW = CANVAS / COLS;
        var cellH = CANVAS / ROWS;

        for (var i = ITEMS.length - 1; i >= 0; i--) {
            var it = ITEMS[i];
            placeSmartObject(it.file, LINKED);
            var layer = doc.activeLayer;

            var s = sizeOf(layer);
            if (s.w > 0 && s.h > 0) {
                layer.resize(cellW / s.w * 100, cellH / s.h * 100,
                             AnchorPosition.MIDDLECENTER);
            }
            s = sizeOf(layer);
            layer.translate((it.col + 0.5) * cellW - s.cx,
                            (it.row + 0.5) * cellH - s.cy);
            layer.name = it.name;
        }

        // layer trong suốt do documents.add sinh ra, không còn cần
        if (doc.layers.length > ITEMS.length) {
            try { filler.remove(); } catch (e) {}
        }
    } finally {
        app.preferences.rulerUnits = oldUnits;
    }
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _natural_key(name):
    """Sắp tên theo cách người đọc: "2. Body" đứng trước "10. Head"."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def _sorted_targets(context):
    """Các mesh object đang chọn, đã sắp theo tên."""
    objs = [ob for ob in context.selected_objects if ob.type == 'MESH']
    objs.sort(key=lambda ob: _natural_key(ob.name))
    return objs


def _cell_rect(index, rows, cols):
    """Ô thứ `index` (0-based) -> (min_u, min_v, width, height).

    Ô 0 nằm góc trên-trái; chạy hết một hàng từ trái sang phải rồi xuống hàng
    dưới. Trong không gian UV, "trên" là v gần 1.0.
    """
    row, col = divmod(index, cols)
    w = 1.0 / cols
    h = 1.0 / rows
    return col * w, 1.0 - (row + 1) * h, w, h


def _place_uv_in_cell(mesh, rect):
    """Scale UV của `mesh` xuống bằng kích thước ô rồi dịch vào ô.

    Map thẳng không gian UV 0..1 lên ô: (0, 0) -> góc ô, (1, 1) -> góc đối diện.
    Không đo bounding box, không phóng to cho lấp ô, không canh giữa — nhờ vậy
    vị trí tương đối của UV trong tile và texel density giữa các object được
    giữ nguyên.
    """
    min_u, min_v, cell_w, cell_h = rect
    # Có file không set active layer (active_index = -1) nên fallback về layer đầu.
    uv_data = (mesh.uv_layers.active or mesh.uv_layers[0]).data

    co = np.empty(len(uv_data) * 2, dtype=np.float32)
    uv_data.foreach_get("uv", co)
    co.shape = (-1, 2)

    co *= np.array([cell_w, cell_h], dtype=np.float32)
    co += np.array([min_u, min_v], dtype=np.float32)

    uv_data.foreach_set("uv", co.ravel())
    mesh.update()


def _iter_tex_image_nodes(node_tree, seen=None, depth=0):
    """Mọi node Image Texture có ảnh, đi xuống cả node group."""
    if node_tree is None or depth > 8:
        return
    if seen is None:
        seen = set()
    if node_tree in seen:
        return
    seen.add(node_tree)
    for node in node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            if node.image is not None:
                yield node
        elif node.type == 'GROUP':
            yield from _iter_tex_image_nodes(node.node_tree, seen, depth + 1)


def _has_tex_image_node(mat):
    """Material có node Image Texture không (kể cả node trống chưa gắn ảnh)."""
    if not mat.use_nodes or mat.node_tree is None:
        return False
    if any(n.type == 'TEX_IMAGE' for n in mat.node_tree.nodes):
        return True
    # Node nằm trong group thì quét đệ quy; _iter chỉ trả node có ảnh nhưng
    # node trống trong group hiếm gặp, chấp nhận bỏ sót.
    return next(_iter_tex_image_nodes(mat.node_tree), None) is not None


def _feeds_base_color(node):
    return any(link.to_socket.name == "Base Color"
               for out in node.outputs for link in out.links)


def _object_texture(ob):
    """(image, lý_do_bỏ_qua) — texture đại diện cho `ob`.

    Ưu tiên node nối thẳng vào Base Color; nếu không có thì lấy ảnh duy nhất
    tìm được. Nhiều ảnh mà không phân biệt được thì trả về lý do để báo cho user
    chứ không đoán bừa.
    """
    nodes = []
    for slot in ob.material_slots:
        mat = slot.material
        if mat is not None and mat.use_nodes:
            nodes.extend(_iter_tex_image_nodes(mat.node_tree))

    if not nodes:
        return None, "material không có Image Texture"

    pool = [n for n in nodes if _feeds_base_color(n)] or nodes
    images = []
    for node in pool:
        if node.image not in images:
            images.append(node.image)

    if len(images) > 1:
        return None, "có %d texture (%s), không rõ lấy cái nào" % (
            len(images), ", ".join(img.name for img in images))
    return images[0], None


def _safe_filename(name):
    """Tên object -> tên file hợp lệ trên Windows."""
    cleaned = _ILLEGAL_CHARS.sub("_", name).strip().rstrip(". ")
    return cleaned or "unnamed"


def _canvas_fit(size, cols, rows):
    """(chia_hết, [gợi_ý]) — canvas phải chia hết cho cả số cột và số hàng.

    Không chia hết thì ô lẻ ra số thập phân, Smart Object bị đặt lệch nửa pixel
    và thấy rõ đường ghép ở biên ô.
    """
    step = cols * rows // math.gcd(cols, rows)
    if size % step == 0:
        return True, []
    lower = size // step * step
    return False, [v for v in (lower, lower + step) if v >= step]


def _find_photoshop():
    """Đường dẫn Photoshop.exe (bản mới nhất), hoặc None."""
    if sys.platform != "win32":
        return None

    found = []
    try:
        import winreg
    except ImportError:
        winreg = None

    if winreg is not None:
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                base = winreg.OpenKey(root, r"SOFTWARE\Adobe\Photoshop")
            except OSError:
                continue
            with base:
                index = 0
                while True:
                    try:
                        ver = winreg.EnumKey(base, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(base, ver) as sub:
                            root_dir = winreg.QueryValueEx(sub, "ApplicationPath")[0]
                    except OSError:
                        continue
                    try:
                        rank = float(ver)
                    except ValueError:
                        rank = 0.0
                    found.append((rank, os.path.join(root_dir, "Photoshop.exe")))

    for pattern in (r"C:\Program Files\Adobe\Adobe Photoshop *\Photoshop.exe",
                    r"C:\Program Files (x86)\Adobe\Adobe Photoshop *\Photoshop.exe"):
        found.extend((0.0, path) for path in glob.glob(pattern))

    for _rank, exe in sorted(found, key=lambda item: -item[0]):
        if os.path.isfile(exe):
            return exe
    return None


def _js_string(value):
    """Chuỗi Python -> string literal JavaScript an toàn."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _build_jsx(items, canvas, cols, rows, linked):
    """items: list (tên object, đường dẫn png, col, row)."""
    lines = [
        "        {name: %s, file: %s, col: %d, row: %d},"
        % (_js_string(name), _js_string(path.replace("\\", "/")), col, row)
        for name, path, col, row in items
    ]
    return _JSX_TEMPLATE % {
        "canvas": canvas,
        "cols": cols,
        "rows": rows,
        "linked": "true" if linked else "false",
        "items": "\n".join(lines),
    }


def _export_image_png(image, size, filepath):
    """Ghi `image` ra PNG vuông `size` px. Không sửa ảnh gốc."""
    copy = image.copy()
    try:
        if tuple(copy.size) != (size, size):
            copy.scale(size, size)
        copy.file_format = 'PNG'
        copy.filepath_raw = filepath
        copy.save()
    finally:
        bpy.data.images.remove(copy)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class AUTOUVPAL_Props(PropertyGroup):
    cols: IntProperty(
        name="Columns",
        description="Số cột chia tấm palette",
        default=3,
        min=1,
        soft_max=16,
        max=256,
    )
    rows: IntProperty(
        name="Rows",
        description="Số hàng chia tấm palette",
        default=3,
        min=1,
        soft_max=16,
        max=256,
    )
    tex_size: EnumProperty(
        name="Size",
        description="Kích thước PNG xuất ra, dùng chung cho toàn bộ texture",
        items=[
            ('2048', "2K", "2048 x 2048"),
            ('4096', "4K", "4096 x 4096"),
            ('8192', "8K", "8192 x 8192"),
        ],
        default='4096',
    )
    export_dir: StringProperty(
        name="Path",
        description="Thư mục xuất file PNG",
        subtype='DIR_PATH',
        default="",
    )
    canvas_size: IntProperty(
        name="Canvas",
        description=("Kích thước canvas PSD, tính theo pixel và luôn vuông. "
                     "Nên chia hết cho cả số cột và số hàng"),
        default=2048,
        min=64,
        soft_max=16384,
        max=30000,          # PSD tối đa 30000px mỗi chiều
        subtype='PIXEL',
    )
    palette_image: StringProperty(
        name="Palette",
        description=("File ảnh palette đã ghép (PNG/PSD/JPG…) để gắn vào "
                     "material chung"),
        subtype='FILE_PATH',
        default="",
    )
    smart_object_mode: EnumProperty(
        name="Smart Object",
        description="Nhúng ảnh vào PSD hay chỉ trỏ tới file PNG",
        items=[
            ('LINKED', "Linked",
             "PSD trỏ tới file PNG; sửa lại PNG thì PSD tự cập nhật"),
            ('EMBEDDED', "Embedded",
             "Nhúng ảnh vào PSD; file tự chứa nhưng nặng hơn nhiều"),
        ],
        default='LINKED',
    )


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class AUTOUVPAL_OT_pack(Operator):
    bl_idname = "object.auto_uv_palette_pack"
    bl_label = "Pack UVs into Palette"
    bl_description = ("Scale và xếp UV của các object đã chọn vào từng ô của "
                      "palette, rồi tạo 1 material chung gán cho toàn bộ. "
                      "Texture cũ chưa export sẽ mất khi lưu file — nên chạy "
                      "Export Selected Textures trước")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette
        rows, cols = props.rows, props.cols
        cells = rows * cols

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if len(targets) > cells:
            self.report(
                {'ERROR'},
                f"Cần ít nhất {len(targets)} ô cho {len(targets)} object, "
                f"grid {cols}x{rows} chỉ có {cells} ô. Tăng số cột/hàng.",
            )
            return {'CANCELLED'}

        no_uv = [ob.name for ob in targets if not ob.data.uv_layers]
        if no_uv:
            self.report({'ERROR'}, "Chưa có UV map: " + ", ".join(no_uv))
            return {'CANCELLED'}

        empty = [ob.name for ob in targets if not ob.data.loops]
        if empty:
            self.report({'ERROR'}, "Mesh rỗng, không có UV để xếp: "
                                   + ", ".join(empty))
            return {'CANCELLED'}

        # Nhiều object dùng chung một mesh data thì không thể xếp vào 2 ô khác
        # nhau — sửa UV của cái này là sửa luôn cái kia.
        by_mesh = {}
        for ob in targets:
            by_mesh.setdefault(ob.data, []).append(ob.name)
        shared = [names for names in by_mesh.values() if len(names) > 1]
        if shared:
            groups = "; ".join(", ".join(names) for names in shared)
            self.report(
                {'ERROR'},
                f"Các object này dùng chung mesh data ({groups}). Chạy Object > "
                "Relations > Make Single User > Object & Data trước.",
            )
            return {'CANCELLED'}

        # Texture trong material cũ mà chưa export thì sau khi gán material
        # mới sẽ thành orphan — lưu file là Blender purge mất. Cảnh báo trước.
        directory = (bpy.path.abspath(props.export_dir)
                     if props.export_dir else None)
        unexported = []
        for ob in targets:
            image, _reason = _object_texture(ob)
            if image is None:
                continue
            png = (os.path.join(directory, _safe_filename(ob.name) + ".png")
                   if directory else None)
            if png is None or not os.path.isfile(png):
                unexported.append(ob.name)

        for index, ob in enumerate(targets):
            _place_uv_in_cell(ob.data, _cell_rect(index, rows, cols))

        # Material palette chung: tạo mới, gán đè lên toàn bộ object đã chọn.
        # Node Image Texture để trống — chỗ gắn tấm palette sau khi bake/ghép.
        mat = bpy.data.materials.new("UVPalette_%dx%d" % (cols, rows))
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes
                     if n.type == 'BSDF_PRINCIPLED'), None)
        tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        if bsdf is not None:
            tex_node.location = (bsdf.location.x - 300, bsdf.location.y)
            mat.node_tree.links.new(tex_node.outputs["Color"],
                                    bsdf.inputs["Base Color"])
        for ob in targets:
            ob.data.materials.clear()
            ob.data.materials.append(mat)

        done = (f"Đã xếp {len(targets)} object vào grid {cols}x{rows} và gán "
                f"material chung \"{mat.name}\".")
        if unexported:
            self.report(
                {'WARNING'},
                done + " Lưu ý: texture của %s chưa export — material cũ giờ "
                       "không còn ai dùng, lưu file là mất texture. Ctrl+Z rồi "
                       "chạy Export Selected Textures trước nếu cần giữ."
                % ", ".join(unexported),
            )
        else:
            self.report({'INFO'}, done)
        return {'FINISHED'}


class AUTOUVPAL_OT_export_textures(Operator):
    bl_idname = "object.auto_uv_palette_export_textures"
    bl_label = "Export Selected Textures"
    bl_description = ("Xuất texture trong material của từng object đã chọn ra "
                      "PNG cùng một kích thước, tên file theo tên object")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette
        size = int(props.tex_size)

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if not props.export_dir:
            self.report({'ERROR'}, "Chưa chọn đường dẫn export.")
            return {'CANCELLED'}

        directory = bpy.path.abspath(props.export_dir)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as err:
            self.report({'ERROR'}, "Không tạo được thư mục export: %s" % err)
            return {'CANCELLED'}

        written, no_tex, too_small, failed, overwritten = [], [], [], [], []
        for ob in targets:
            image, reason = _object_texture(ob)
            if image is None:
                no_tex.append("%s (%s)" % (ob.name, reason))
                continue

            src_w, src_h = image.size
            if min(src_w, src_h) < _MIN_SOURCE_PX:
                too_small.append("%s (%dx%d)" % (ob.name, src_w, src_h))
                continue

            path = os.path.join(directory, _safe_filename(ob.name) + ".png")
            existed = os.path.exists(path)
            try:
                _export_image_png(image, size, path)
            except (RuntimeError, OSError) as err:
                failed.append("%s (%s)" % (ob.name, err))
                continue
            written.append(ob.name)
            if existed:
                overwritten.append(os.path.basename(path))

        parts = ["Đã xuất %d/%d texture ở %dx%d vào %s"
                 % (len(written), len(targets), size, size, directory)]
        if overwritten:
            parts.append("ghi đè %d file cũ" % len(overwritten))
        if too_small:
            parts.append("bỏ qua vì texture gốc dưới %dpx: %s"
                         % (_MIN_SOURCE_PX, ", ".join(too_small)))
        if no_tex:
            parts.append("không có texture: " + ", ".join(no_tex))
        if failed:
            parts.append("lỗi: " + ", ".join(failed))

        message = ". ".join(parts) + "."
        if failed or not written:
            self.report({'ERROR'} if not written else {'WARNING'}, message)
            return {'CANCELLED'} if not written else {'FINISHED'}
        self.report({'WARNING'} if (too_small or no_tex or overwritten)
                    else {'INFO'}, message)
        return {'FINISHED'}


class AUTOUVPAL_OT_cleanup_textures(Operator):
    bl_idname = "object.auto_uv_palette_cleanup_textures"
    bl_label = "Clean Up Exported Textures"
    bl_description = ("Xóa khỏi file .blend các texture đã export ra PNG "
                      "(giảm dung lượng file). Chỉ xóa khi file PNG tương ứng "
                      "đã có trong thư mục export")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        # Xóa image datablock không undo được đáng tin -> bắt confirm.
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.auto_uv_palette

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if not props.export_dir:
            self.report({'ERROR'}, "Chưa chọn đường dẫn export.")
            return {'CANCELLED'}
        directory = bpy.path.abspath(props.export_dir)

        selected_mats = {slot.material
                         for ob in targets
                         for slot in ob.material_slots
                         if slot.material}

        # image -> các object đã chọn dùng nó (nhiều object có thể chung 1 ảnh)
        candidates = {}
        no_tex = []
        for ob in targets:
            image, reason = _object_texture(ob)
            if image is None:
                no_tex.append(ob.name)
                continue
            candidates.setdefault(image, []).append(ob)

        removed, not_exported, in_use = [], [], []
        for image, users in candidates.items():
            # "đã export" = có PNG của ít nhất 1 object dùng ảnh này
            if not any(os.path.isfile(os.path.join(
                    directory, _safe_filename(ob.name) + ".png"))
                    for ob in users):
                not_exported.append(image.name)
                continue

            # material ngoài selection còn dùng ảnh -> xóa sẽ vỡ, bỏ qua
            other = [mat.name for mat in bpy.data.materials
                     if mat not in selected_mats and mat.use_nodes
                     and any(node.image == image for node in
                             _iter_tex_image_nodes(mat.node_tree))]
            if other:
                in_use.append("%s (material %s)"
                              % (image.name, ", ".join(other)))
                continue

            removed.append(image.name)
            bpy.data.images.remove(image)

        parts = ["Đã xóa %d texture khỏi file .blend" % len(removed)]
        if removed:
            parts.append("(%s)" % ", ".join(removed))
        if not_exported:
            parts.append("chưa export nên giữ lại: " + ", ".join(not_exported))
        if in_use:
            parts.append("object ngoài selection còn dùng nên giữ lại: "
                         + ", ".join(in_use))
        if no_tex:
            parts.append("không có texture: " + ", ".join(no_tex))
        message = ". ".join(parts) + ". Lưu file để dung lượng giảm thật."

        if not removed:
            self.report({'WARNING'}, message)
            return {'CANCELLED'}
        self.report({'WARNING'} if (not_exported or in_use) else {'INFO'},
                    message)
        return {'FINISHED'}


class AUTOUVPAL_OT_cleanup_materials(Operator):
    bl_idname = "object.auto_uv_palette_cleanup_materials"
    bl_label = "Clean Up Old Materials"
    bl_description = ("Xóa khỏi file .blend các material cũ của những object "
                      "đã export texture ra PNG. Giữ lại material palette "
                      "(UVPalette_*), material không gắn texture và material "
                      "mà object ngoài selection còn dùng")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        # Xóa material datablock không undo được đáng tin -> bắt confirm.
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.auto_uv_palette

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if not props.export_dir:
            self.report({'ERROR'}, "Chưa chọn đường dẫn export.")
            return {'CANCELLED'}
        directory = bpy.path.abspath(props.export_dir)

        selected = set(targets)

        # Material "cũ" = đang gắn trên object đã chọn mà PNG của object đó
        # đã nằm trong thư mục export. Chưa export thì chưa được xóa material.
        candidates, not_exported = [], []
        for ob in targets:
            if not os.path.isfile(os.path.join(
                    directory, _safe_filename(ob.name) + ".png")):
                not_exported.append(ob.name)
                continue
            for slot in ob.material_slots:
                mat = slot.material
                if mat is not None and mat not in candidates:
                    candidates.append(mat)

        removed, palette, no_tex, in_use = [], [], [], []
        for mat in candidates:
            # Material palette do Pack UVs tạo — không phải "material cũ".
            if mat.name.startswith("UVPalette_"):
                palette.append(mat.name)
                continue
            # Material thuần màu không gắn texture nào -> không thuộc diện
            # "material cũ của texture đã export", giữ lại.
            if not _has_tex_image_node(mat):
                no_tex.append(mat.name)
                continue
            other = [ob.name for ob in bpy.data.objects
                     if ob not in selected
                     and any(slot.material == mat
                             for slot in ob.material_slots)]
            if other:
                in_use.append("%s (object %s)" % (mat.name, ", ".join(other)))
                continue
            removed.append(mat.name)
            bpy.data.materials.remove(mat)

        # Chỉ dọn slot rỗng khi object mất hết material — xóa lẻ một slot sẽ
        # xáo trộn material_index theo mặt của các slot còn lại.
        for ob in targets:
            if ob.material_slots and all(slot.material is None
                                         for slot in ob.material_slots):
                ob.data.materials.clear()

        parts = ["Đã xóa %d material cũ khỏi file .blend" % len(removed)]
        if removed:
            parts.append("(%s)" % ", ".join(removed))
        if not_exported:
            parts.append("chưa export PNG nên giữ nguyên material: "
                         + ", ".join(not_exported))
        if palette:
            parts.append("material palette giữ lại: " + ", ".join(palette))
        if no_tex:
            parts.append("không gắn texture nên giữ lại: " + ", ".join(no_tex))
        if in_use:
            parts.append("object ngoài selection còn dùng nên giữ lại: "
                         + ", ".join(in_use))

        if not removed:
            self.report({'WARNING'}, ". ".join(parts) + ".")
            return {'CANCELLED'}
        self.report(
            {'WARNING'} if (not_exported or no_tex or in_use) else {'INFO'},
            ". ".join(parts) + ". Texture còn kẹt trong material cũ giờ đã "
                               "mồ côi — lưu file là Blender tự dọn.")
        return {'FINISHED'}


class AUTOUVPAL_OT_build_psd(Operator):
    bl_idname = "object.auto_uv_palette_build_psd"
    bl_label = "Build Palette PSD"
    bl_description = ("Sinh script Photoshop xếp các PNG đã export thành Smart "
                      "Object vào đúng ô của palette, rồi mở Photoshop chạy nó")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette
        cols, rows = props.cols, props.rows
        canvas = props.canvas_size

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        cells = cols * rows
        if len(targets) > cells:
            self.report(
                {'ERROR'},
                f"Cần ít nhất {len(targets)} ô cho {len(targets)} object, "
                f"grid {cols}x{rows} chỉ có {cells} ô. Tăng số cột/hàng.",
            )
            return {'CANCELLED'}

        if not props.export_dir:
            self.report({'ERROR'}, "Chưa chọn đường dẫn export.")
            return {'CANCELLED'}

        directory = bpy.path.abspath(props.export_dir)
        if not os.path.isdir(directory):
            self.report({'ERROR'}, "Thư mục export không tồn tại: " + directory)
            return {'CANCELLED'}

        items, missing = [], []
        for index, ob in enumerate(targets):
            path = os.path.join(directory, _safe_filename(ob.name) + ".png")
            if not os.path.isfile(path):
                missing.append(os.path.basename(path))
                continue
            row, col = divmod(index, cols)
            items.append((ob.name, path, col, row))

        if missing:
            self.report(
                {'ERROR'},
                "Chưa có PNG cho: %s. Chạy Export Selected Textures trước."
                % ", ".join(missing),
            )
            return {'CANCELLED'}

        jsx_path = os.path.join(directory, _JSX_NAME)
        script = _build_jsx(items, canvas, cols, rows,
                            props.smart_object_mode == 'LINKED')
        try:
            with open(jsx_path, "w", encoding="utf-8") as handle:
                handle.write(script)
        except OSError as err:
            self.report({'ERROR'}, "Không ghi được script: %s" % err)
            return {'CANCELLED'}

        notes = []
        divisible, hints = _canvas_fit(canvas, cols, rows)
        if not divisible:
            note = ("canvas %d không chia hết cho %dx%d nên ô lẻ %.2fx%.2f px, "
                    "Smart Object sẽ lệch nửa pixel"
                    % (canvas, cols, rows, canvas / cols, canvas / rows))
            if hints:
                note += " (nên dùng %s)" % " hoặc ".join(str(v) for v in hints)
            notes.append(note)

        exe = _find_photoshop()
        if exe is None:
            self.report(
                {'WARNING'},
                "Đã ghi %s nhưng không tìm thấy Photoshop.exe — chạy tay bằng "
                "File > Scripts > Browse.%s"
                % (jsx_path, (" Lưu ý: " + "; ".join(notes)) if notes else ""),
            )
            return {'FINISHED'}

        try:
            subprocess.Popen([exe, jsx_path], close_fds=True)
        except OSError as err:
            self.report(
                {'WARNING'},
                "Đã ghi %s nhưng không mở được Photoshop (%s) — chạy tay bằng "
                "File > Scripts > Browse." % (jsx_path, err),
            )
            return {'FINISHED'}

        mode = "Linked" if props.smart_object_mode == 'LINKED' else "Embedded"
        message = ("Đã ghi %s (%d layer %s Smart Object, canvas %dpx) và mở "
                   "Photoshop." % (_JSX_NAME, len(items), mode, canvas))
        if notes:
            self.report({'WARNING'}, message + " Lưu ý: " + "; ".join(notes))
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


class AUTOUVPAL_OT_assign_palette(Operator):
    bl_idname = "object.auto_uv_palette_assign_palette"
    bl_label = "Assign Palette to Material"
    bl_description = ("Nạp file ảnh palette và gắn vào node Image Texture "
                      "trong material của các object đã chọn")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if not props.palette_image:
            self.report({'ERROR'}, "Chưa chọn file ảnh palette.")
            return {'CANCELLED'}
        path = bpy.path.abspath(props.palette_image)
        if not os.path.isfile(path):
            self.report({'ERROR'}, "File không tồn tại: " + path)
            return {'CANCELLED'}

        mats, no_mat = [], []
        for ob in targets:
            found = [slot.material for slot in ob.material_slots
                     if slot.material and slot.material.use_nodes]
            if not found:
                no_mat.append(ob.name)
            for mat in found:
                if mat not in mats:
                    mats.append(mat)
        if not mats:
            self.report({'ERROR'}, "Object đã chọn không có material nào "
                                   "(chạy Pack UVs trước).")
            return {'CANCELLED'}

        try:
            image = bpy.data.images.load(path, check_existing=True)
            image.reload()          # file đổi trên đĩa thì lấy bản mới
        except RuntimeError as err:
            self.report({'ERROR'}, "Không nạp được ảnh: %s" % err)
            return {'CANCELLED'}

        for mat in mats:
            nodes = list(_iter_tex_image_nodes(mat.node_tree))
            # node trống add-on tạo sẵn không lọt qua _iter (nó bỏ node không
            # có ảnh) -> quét lại lấy cả node trống
            all_tex = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE']
            target_node = next(
                (n for n in all_tex if n.image is None),
                next((n for n in all_tex if _feeds_base_color(n)),
                     all_tex[0] if all_tex else None))
            if target_node is None:
                target_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                bsdf = next((n for n in mat.node_tree.nodes
                             if n.type == 'BSDF_PRINCIPLED'), None)
                if bsdf is not None:
                    target_node.location = (bsdf.location.x - 300,
                                            bsdf.location.y)
                    mat.node_tree.links.new(target_node.outputs["Color"],
                                            bsdf.inputs["Base Color"])
            target_node.image = image

        message = ("Đã gắn \"%s\" vào %d material (%s)."
                   % (image.name, len(mats),
                      ", ".join(mat.name for mat in mats)))
        if no_mat:
            self.report({'WARNING'}, message + " Không có material: "
                                              + ", ".join(no_mat))
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class AUTOUVPAL_PT_mixin:
    bl_label = "Auto UV Palette"
    bl_region_type = 'UI'
    bl_category = "UV Palette"

    def draw(self, context):
        layout = self.layout
        props = context.scene.auto_uv_palette
        rows, cols = props.rows, props.cols
        cells = rows * cols

        if context.mode != 'OBJECT':
            layout.label(text="Cần ở Object Mode", icon='ERROR')
            return

        targets = _sorted_targets(context)

        header = layout.row()
        header.label(text="Palette Grid", icon='GRID')
        col = layout.column(align=True)
        col.prop(props, "cols")
        col.prop(props, "rows")

        box = layout.box()
        if not targets:
            box.label(text=f"{cells} ô · chưa chọn object", icon='INFO')
        elif len(targets) > cells:
            box.label(text=f"{cells} ô · {len(targets)} object — thiếu ô",
                      icon='ERROR')
        else:
            box.label(text=f"{cells} ô · {len(targets)} object", icon='CHECKMARK')

        if targets:
            preview = box.column(align=True)
            for index, ob in enumerate(targets[:_PREVIEW_ROWS]):
                row, cell_col = divmod(index, cols)
                preview.label(text=f"H{row + 1} C{cell_col + 1}   {ob.name}")
            if len(targets) > _PREVIEW_ROWS:
                preview.label(text=f"… và {len(targets) - _PREVIEW_ROWS} object nữa")

        layout.operator(AUTOUVPAL_OT_pack.bl_idname, icon='UV_DATA')

        layout.separator()
        layout.label(text="Export Textures", icon='IMAGE_DATA')
        col = layout.column(align=True)
        col.prop(props, "tex_size")
        col.prop(props, "export_dir")

        if targets:
            missing = [ob.name for ob in targets
                       if _object_texture(ob)[0] is None]
            if missing:
                info = layout.box()
                info.label(text="%d object không có texture" % len(missing),
                           icon='ERROR')
                for name in missing[:_PREVIEW_ROWS]:
                    info.label(text=name)

        col = layout.column(align=True)
        col.enabled = bool(props.export_dir)
        col.operator(AUTOUVPAL_OT_export_textures.bl_idname, icon='EXPORT')
        col.operator(AUTOUVPAL_OT_cleanup_textures.bl_idname, icon='TRASH')
        col.operator(AUTOUVPAL_OT_cleanup_materials.bl_idname, icon='MATERIAL')

        layout.separator()
        layout.label(text="Palette PSD", icon='FILE_IMAGE')
        layout.prop(props, "canvas_size")
        layout.row().prop(props, "smart_object_mode", expand=True)

        cell_box = layout.box()
        divisible, hints = _canvas_fit(props.canvas_size, cols, rows)
        if divisible:
            cell_box.label(
                text="Ô = %d x %d px" % (props.canvas_size // cols,
                                         props.canvas_size // rows),
                icon='CHECKMARK')
        else:
            cell_box.label(text="Canvas không chia hết cho %dx%d" % (cols, rows),
                           icon='ERROR')
            cell_box.label(text="Ô = %.2f x %.2f px, sẽ lệch nửa pixel"
                                % (props.canvas_size / cols,
                                   props.canvas_size / rows))
            if hints:
                cell_box.label(text="Nên dùng: "
                                    + " hoặc ".join(str(v) for v in hints))

        row = layout.row()
        row.enabled = bool(props.export_dir)
        row.operator(AUTOUVPAL_OT_build_psd.bl_idname, icon='FILE_IMAGE')

        layout.separator()
        layout.label(text="Assign Palette", icon='NODE_TEXTURE')
        layout.prop(props, "palette_image")
        row = layout.row()
        row.enabled = bool(props.palette_image)
        row.operator(AUTOUVPAL_OT_assign_palette.bl_idname, icon='LINKED')


class AUTOUVPAL_PT_view3d(AUTOUVPAL_PT_mixin, Panel):
    bl_idname = "AUTOUVPAL_PT_view3d"
    bl_space_type = 'VIEW_3D'


class AUTOUVPAL_PT_image(AUTOUVPAL_PT_mixin, Panel):
    bl_idname = "AUTOUVPAL_PT_image"
    bl_space_type = 'IMAGE_EDITOR'


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = (
    AUTOUVPAL_Props,
    AUTOUVPAL_OT_pack,
    AUTOUVPAL_OT_export_textures,
    AUTOUVPAL_OT_cleanup_textures,
    AUTOUVPAL_OT_cleanup_materials,
    AUTOUVPAL_OT_build_psd,
    AUTOUVPAL_OT_assign_palette,
    AUTOUVPAL_PT_view3d,
    AUTOUVPAL_PT_image,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.auto_uv_palette = PointerProperty(type=AUTOUVPAL_Props)


def unregister():
    del bpy.types.Scene.auto_uv_palette
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
