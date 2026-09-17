# Auto UV Palette — Blender 4.x / 5.x
# Xếp UV của nhiều object (dùng chung 1 material) vào các ô của một tấm palette.
# Nhập số cột x hàng, UV của mỗi object được scale xuống đúng bằng kích thước ô
# (grid 3x3 -> nhân 1/3) rồi dịch vào ô của nó. Thứ tự: theo tên object
# (hiểu số, "2." trước "10."), trái → phải, trên → dưới.
# Object mới đến sau thì xếp vào ô còn trống của palette đã có, không phải làm
# lại từ đầu — ô trống đọc từ object trong scene lẫn alpha của ảnh palette.

bl_info = {
    "name": "Auto UV Palette",
    "author": "EasyGoing Visual",
    "version": (1, 3, 1),
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
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_JSX_NAME = "auto_uv_palette_build.jsx"
_JSX_APPEND_NAME = "auto_uv_palette_append.jsx"

# Tên material palette do Pack UVs tạo — cũng là chỗ đọc ra grid của palette cũ.
_PALETTE_NAME = re.compile(r"^UVPalette_(\d+)x(\d+)")
# Quét alpha trên bản thu nhỏ: ảnh 8K đọc thẳng là ~1 GB float.
_ALPHA_SCAN_PX = 1024
# Ô có pixel đục hơn mức này coi như đã có texture. Thu nhỏ ảnh làm alpha bị
# trung bình hoá nên ngưỡng phải cao hơn 1/255 một chút.
_ALPHA_EMPTY = 0.02
# UV rộng hơn ô bằng ngần này lần thì coi như chưa được xếp vào palette.
_CELL_OVERFLOW = 1.5
# Custom property ghi lên object: (cols, rows, index) của ô nó đang chiếm.
# Không có nó thì không phân biệt được object chiếm nguyên ô thô 8x8 với
# object chỉ chiếm 1 ô mịn 16x16 — UV thưa của cả hai đều có thể nhỏ hơn ô.
_STAMP = "ezg_uv_palette_cell"
_STAMP_FORMAT = "%dx%d:%d"          # "8x8:36" — grid rồi tới ô
# Preview trong panel phải đọc UV, mà panel vẽ lại liên tục — mesh nặng hơn
# ngưỡng này thì bỏ qua, không làm sidebar giật.
_PREVIEW_MAX_LOOPS = 200000

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

# Script Photoshop: mở (hoặc dùng) palette đã có rồi Place thêm PNG vào đúng ô
# trống. Kích thước ô lấy từ document thật, không lấy từ Canvas trong panel.
_JSX_APPEND_TEMPLATE = """\
#target photoshop
// Sinh tự động bởi add-on Auto UV Palette — đừng sửa tay, chạy lại add-on.
// Mỗi item mang sẵn ô của nó dưới dạng tỉ lệ document (u, v, w, h) chứ không
// dùng chung một COLS/ROWS — nhờ vậy asset to (ô 1/8) và asset nhỏ (ô 1/16)
// đặt được vào cùng một tấm palette.
(function () {
    var LINKED = %(linked)s;
    var PSD = %(psd)s;
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
        var doc = null;
        if (PSD !== "") {
            doc = app.open(new File(PSD));
        } else if (app.documents.length > 0) {
            doc = app.activeDocument;
        }
        if (doc === null) {
            alert("Auto UV Palette: chua mo file palette nao trong Photoshop, "
                  + "va cung chua chon duong dan PSD trong add-on.");
            return;
        }
        app.activeDocument = doc;

        var docW = doc.width.as("px");
        var docH = doc.height.as("px");

        // Place đặt layer mới ngay trên layer đang active -> đưa active lên
        // trên cùng để layer mới không chui vào giữa các layer cũ.
        doc.activeLayer = doc.layers[0];
        for (var i = ITEMS.length - 1; i >= 0; i--) {
            var it = ITEMS[i];
            var cellW = it.w * docW;
            var cellH = it.h * docH;
            placeSmartObject(it.file, LINKED);
            var layer = doc.activeLayer;

            var s = sizeOf(layer);
            if (s.w > 0 && s.h > 0) {
                layer.resize(cellW / s.w * 100, cellH / s.h * 100,
                             AnchorPosition.MIDDLECENTER);
            }
            s = sizeOf(layer);
            layer.translate(it.u * docW + cellW / 2 - s.cx,
                            it.v * docH + cellH / 2 - s.cy);
            layer.name = it.name;
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


def _uv_problem(targets):
    """Lý do không xếp UV được cho danh sách object, hoặc None nếu ổn."""
    no_uv = [ob.name for ob in targets if not ob.data.uv_layers]
    if no_uv:
        return "Chưa có UV map: " + ", ".join(no_uv)

    empty = [ob.name for ob in targets if not ob.data.loops]
    if empty:
        return "Mesh rỗng, không có UV để xếp: " + ", ".join(empty)

    # Nhiều object dùng chung một mesh data thì không thể xếp vào 2 ô khác
    # nhau — sửa UV của cái này là sửa luôn cái kia.
    by_mesh = {}
    for ob in targets:
        by_mesh.setdefault(ob.data, []).append(ob.name)
    shared = [names for names in by_mesh.values() if len(names) > 1]
    if shared:
        groups = "; ".join(", ".join(names) for names in shared)
        return (f"Các object này dùng chung mesh data ({groups}). Chạy Object > "
                "Relations > Make Single User > Object & Data trước.")
    return None


def _uv_bounds(mesh):
    """(min_u, min_v, max_u, max_v) của UV, hoặc None nếu không đọc được."""
    if not mesh.uv_layers:
        return None
    uv_data = (mesh.uv_layers.active or mesh.uv_layers[0]).data
    if not len(uv_data):
        return None

    co = np.empty(len(uv_data) * 2, dtype=np.float32)
    uv_data.foreach_get("uv", co)
    co.shape = (-1, 2)
    return (float(co[:, 0].min()), float(co[:, 1].min()),
            float(co[:, 0].max()), float(co[:, 1].max()))


def _uv_cell_index(mesh, rows, cols):
    """Ô mà UV của `mesh` đang nằm trong, hoặc None nếu không đọc được.

    Lấy tâm bounding box của UV rồi quy ra ô — đủ để nhận ra object đã được
    Pack/Add xếp vào ô nào, kể cả khi UV không lấp kín ô.
    """
    bounds = _uv_bounds(mesh)
    if bounds is None:
        return None
    min_u, min_v, max_u, max_v = bounds
    center_u = (min_u + max_u) * 0.5
    center_v = (min_v + max_v) * 0.5
    col = min(cols - 1, max(0, int(center_u * cols)))
    row = min(rows - 1, max(0, int((1.0 - center_v) * rows)))
    return row * cols + col


def _rects_overlap(a, b, eps=1e-6):
    """Hai ô (u, v, w, h) có chồng lên nhau không. Chạm biên không tính.

    eps nuốt sai số dấu phẩy động của grid lẻ (1/3) — không có nó thì hai ô
    sát nhau có thể bị báo nhầm là chồng lên nhau.
    """
    return (a[0] + eps < b[0] + b[2] and b[0] + eps < a[0] + a[2]
            and a[1] + eps < b[1] + b[3] and b[1] + eps < a[1] + a[3])


def _uv_overflows_cell(mesh, rows, cols):
    """UV rộng/cao hơn một ô quá nhiều -> object chưa được xếp vào palette.

    UV còn nguyên 0..1 thì tâm của nó rơi đúng ô giữa palette, nên Append
    Textures to PSD sẽ đặt texture vào **giữa canvas** thay vì ô kế tiếp —
    trông như "không vào ô nào". Đây là chỗ bắt lỗi đó trước khi mở Photoshop.

    Ngưỡng nới rộng 1.5 lần ô để UV tiling tràn nhẹ ra khỏi ô (giới hạn đã ghi
    trong README) không bị báo nhầm là chưa xếp.
    """
    bounds = _uv_bounds(mesh)
    if bounds is None:
        return False
    min_u, min_v, max_u, max_v = bounds
    return ((max_u - min_u) * cols > _CELL_OVERFLOW
            or (max_v - min_v) * rows > _CELL_OVERFLOW)


def _stamp_cell(ob, cols, rows, index):
    """Ghi lại object đang chiếm ô nào, ở grid nào.

    Ghi bằng CHUỖI, không phải tuple 3 số. Bản 1.3.0 ghi `(cols, rows, index)`
    và làm hỏng export FBX: custom property đúng 3 phần tử được exporter đẩy
    vào nhánh `p_vector` (export_fbx_bin.fbx_data_element_custom_properties),
    rồi `encode_bin.add_float64` có `assert isinstance(data, float)` — số
    nguyên làm nó ném AssertionError. Unity báo "Blender could not convert the
    .blend file to FBX file" chính là chỗ đó. Chuỗi đi nhánh `p_string`, an
    toàn với mọi exporter và đọc được ngay trong bảng Custom Properties.
    """
    ob[_STAMP] = _STAMP_FORMAT % (cols, rows, index)


def _stamped_cell(ob):
    """(cols, rows, index) đã ghi lúc xếp, hoặc None nếu chưa/hỏng.

    Đọc cả dạng tuple 3 số của bản 1.3.0 để file cũ không mất dấu ô.
    """
    raw = ob.get(_STAMP)
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            grid, _, cell = raw.partition(":")
            wide, _, high = grid.partition("x")
            cols, rows, index = int(wide), int(high), int(cell)
        else:
            cols, rows, index = (int(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if cols < 1 or rows < 1 or not 0 <= index < cols * rows:
        return None
    return cols, rows, index


def _restamp_legacy(objects):
    """Ghi lại dấu ô dạng tuple cũ thành chuỗi. Trả về tên các object đã sửa.

    Không sửa thì file .blend còn dấu cũ vẫn làm hỏng export FBX, kể cả khi
    add-on đã lên bản mới — dữ liệu nằm trong file chứ không nằm trong code.
    """
    fixed = []
    for ob in objects:
        raw = ob.get(_STAMP)
        if raw is None or isinstance(raw, str):
            continue
        cell = _stamped_cell(ob)
        if cell is None:
            del ob[_STAMP]          # dấu hỏng, xoá luôn cho khỏi kẹt export
        else:
            _stamp_cell(ob, *cell)
        fixed.append(ob.name)
    return fixed


def _subdivides(cols, rows, pcols, prows):
    """Grid `cols`x`rows` có phải bản chia nhỏ đều của `pcols`x`prows` không."""
    return (cols >= pcols and rows >= prows
            and cols % pcols == 0 and rows % prows == 0)


def _cells_covered(index, cols, rows, fcols, frows):
    """Ô `index` của grid cols x rows phủ lên những ô nào của grid mịn hơn.

    Ô của grid 8x8 phủ đúng khối 2x2 ô của grid 16x16 — nhờ vậy object cũ
    không bị đếm thiếu 3/4 ô và asset nhỏ không đè lên texture của nó.
    """
    if not _subdivides(fcols, frows, cols, rows):
        return {index} if 0 <= index < cols * rows else set()
    row, col = divmod(index, cols)
    step_x, step_y = fcols // cols, frows // rows
    return {(row * step_y + dy) * fcols + col * step_x + dx
            for dy in range(step_y)
            for dx in range(step_x)}


def _object_cells(ob, mat_cols, mat_rows, cols, rows):
    """Các ô (của grid `cols`x`rows`) mà `ob` đang chiếm.

    Ưu tiên dấu đã ghi lúc xếp. Object xếp bằng bản add-on cũ chưa có dấu thì
    coi như chiếm nguyên một ô của grid palette — đúng với mọi bản trước đây
    (chưa có chia nhỏ ô) và là phía an toàn: thà chừa dư còn hơn đè lên.
    """
    stamp = _stamped_cell(ob)
    if stamp is not None:
        scols, srows, index = stamp
        if _subdivides(cols, rows, scols, srows):
            return _cells_covered(index, scols, srows, cols, rows)
    index = _uv_cell_index(ob.data, mat_rows, mat_cols)
    if index is None:
        return set()
    return _cells_covered(index, mat_cols, mat_rows, cols, rows)


def _free_cells(occupied, cols, rows, pcols, prows):
    """Ô trống theo thứ tự: lấp nốt khối đang dùng dở trước, rồi mới mở khối mới.

    "Khối" là một ô của grid palette gốc (8x8) — chia nhỏ ra thì nó thành 2x2
    ô mịn. Lấp đầy khối đang dở trước giữ được nhiều khối nguyên vẹn cho asset
    to về sau; cứ lấy ô mịn theo thứ tự đọc thì 2 asset nhỏ đã làm hỏng 2 khối.

    Grid không chia nhỏ (cols == pcols) thì mỗi khối đúng 1 ô, kết quả quay về
    đúng thứ tự đọc trái -> phải, trên -> dưới như cũ.
    """
    partial, empty = [], []
    for block in range(pcols * prows):
        cells = sorted(_cells_covered(block, pcols, prows, cols, rows))
        free = [cell for cell in cells if cell not in occupied]
        if not free:
            continue
        (empty if len(free) == len(cells) else partial).append(free)
    return [cell for group in partial + empty for cell in group]


def _palette_grids():
    """[(material, cols, rows)] — mọi material palette do add-on tạo."""
    out = []
    for mat in bpy.data.materials:
        match = _PALETTE_NAME.match(mat.name)
        if match:
            out.append((mat, int(match.group(1)), int(match.group(2))))
    return out


def _pick_palette_material(context, cols, rows, skip):
    """(material, pcols, prows, lỗi) — palette dùng được với grid `cols`x`rows`.

    Khớp đúng grid, hoặc grid gõ vào là bản **chia nhỏ đều** của grid palette
    (palette 8x8 nhận grid 16x16, 24x24…) để nhét asset nhỏ vào 1/4 ô. Ưu tiên
    khớp đúng trước, rồi tới palette thô nhất — chia càng ít càng đỡ vụn.

    Nhiều material cùng loại thì ưu tiên cái đang có object trong scene dùng
    (ngoài `skip`); vẫn còn nhiều thì trả lỗi chứ không đoán.
    """
    grids = _palette_grids()
    if not grids:
        return None, 0, 0, ("Chưa có material palette nào (UVPalette_*). Chạy "
                            "Pack UVs into Palette để tạo palette trước.")

    exact = [(mat, c, r) for mat, c, r in grids if (c, r) == (cols, rows)]
    coarser = [(mat, c, r) for mat, c, r in grids
               if (c, r) != (cols, rows) and _subdivides(cols, rows, c, r)]
    # Chia càng ít bậc càng tốt: palette 8x8 đứng trước palette 4x4.
    coarser.sort(key=lambda item: -item[1] * item[2])
    pool = exact or coarser
    if not pool:
        have = ", ".join(sorted({"%s (%dx%d)" % (mat.name, c, r)
                                 for mat, c, r in grids}))
        return None, 0, 0, (
            "Grid %dx%d không dùng được với palette nào đang có: %s. Grid phải "
            "khớp đúng, hoặc là bội số nguyên của grid palette (8x8 -> 16x16) "
            "để chia nhỏ ô." % (cols, rows, have))

    best = [item for item in pool if (item[1], item[2]) == (pool[0][1], pool[0][2])]
    if len(best) > 1:
        used = [item for item in best
                if any(ob.type == 'MESH' and ob not in skip
                       and any(slot.material is item[0]
                               for slot in ob.material_slots)
                       for ob in context.scene.objects)]
        if len(used) != 1:
            clash = used or best
            return None, 0, 0, (
                "Có %d material palette %dx%d (%s) — không rõ thêm vào cái "
                "nào. Xóa/đổi tên bớt rồi chạy lại."
                % (len(clash), clash[0][1], clash[0][2],
                   ", ".join(item[0].name for item in clash)))
        best = used
    mat, pcols, prows = best[0]
    return mat, pcols, prows, None


def _scene_occupancy(context, mat, pcols, prows, cols, rows, skip):
    """{ô của grid cols x rows: [tên object]} — ô đã bị object trong scene chiếm.

    Object xếp ở grid thô chiếm nguyên khối ô mịn, xem `_object_cells`.
    """
    occupied = {}
    for ob in context.scene.objects:
        if ob.type != 'MESH' or ob in skip:
            continue
        if not any(slot.material is mat for slot in ob.material_slots):
            continue
        for index in _object_cells(ob, pcols, prows, cols, rows):
            occupied.setdefault(index, []).append(ob.name)
    return occupied


def _image_occupancy(image, rows, cols):
    """Set các ô đã có pixel đục trong ảnh palette, hoặc None nếu không biết.

    None khi ảnh không có alpha, hoặc đục đặc toàn bộ (palette đã flatten lên
    nền) — lúc đó alpha không nói được ô nào trống nên đừng dựa vào nó.
    """
    if image is None or image.channels < 4:
        return None
    src_w, src_h = image.size
    if src_w < cols or src_h < rows:
        return None

    # Đọc trên bản thu nhỏ: ảnh gốc 8K là ~1 GB float32.
    copy = None
    work = image
    if max(src_w, src_h) > _ALPHA_SCAN_PX:
        ratio = _ALPHA_SCAN_PX / max(src_w, src_h)
        copy = image.copy()
        copy.scale(max(cols, int(src_w * ratio)), max(rows, int(src_h * ratio)))
        work = copy

    try:
        width, height = work.size
        channels = work.channels
        if width < cols or height < rows or channels < 4:
            return None
        buf = np.empty(width * height * channels, dtype=np.float32)
        work.pixels.foreach_get(buf)
        alpha = buf.reshape(height, width, channels)[:, :, 3]
        if float(alpha.min()) > 1.0 - _ALPHA_EMPTY:
            return None                 # đục đặc -> không có thông tin ô trống

        occupied = set()
        for row in range(rows):
            # pixel của Blender bắt đầu từ đáy ảnh, ô 0 lại nằm trên cùng
            y0 = round(height * (rows - 1 - row) / rows)
            y1 = round(height * (rows - row) / rows)
            for col in range(cols):
                x0 = round(width * col / cols)
                x1 = round(width * (col + 1) / cols)
                tile = alpha[y0:y1, x0:x1]
                if tile.size and float(tile.max()) > _ALPHA_EMPTY:
                    occupied.add(row * cols + col)
        return occupied
    finally:
        if copy is not None:
            bpy.data.images.remove(copy)


def _palette_image_datablock(props):
    """(image, lỗi) — ảnh palette đang trỏ tới, hoặc (None, None) nếu bỏ trống."""
    if not props.palette_image:
        return None, None
    path = bpy.path.abspath(props.palette_image)
    if not os.path.isfile(path):
        return None, "file palette không tồn tại: " + path
    try:
        image = bpy.data.images.load(path, check_existing=True)
        image.reload()
    except RuntimeError as err:
        return None, "không đọc được ảnh palette (%s)" % err
    return image, None


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


def _unexported_textures(targets, props):
    """Tên các object còn texture chưa có PNG trong thư mục export.

    Gán material palette đè lên sẽ làm material cũ thành mồ côi — lưu file là
    Blender purge, texture chưa export mất luôn. Cả Pack lẫn Add đều cảnh báo.
    """
    directory = (bpy.path.abspath(props.export_dir)
                 if props.export_dir else None)
    names = []
    for ob in targets:
        image, _reason = _object_texture(ob)
        if image is None:
            continue
        png = (os.path.join(directory, _safe_filename(ob.name) + ".png")
               if directory else None)
        if png is None or not os.path.isfile(png):
            names.append(ob.name)
    return names


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


def _build_append_jsx(items, linked, psd_path):
    """items: list (tên object, png, u, v, w, h) — ô tính theo tỉ lệ document.

    u/v là góc trên-trái của ô (v đo từ đỉnh document xuống, đúng chiều toạ độ
    Photoshop). psd_path "" = dùng document đang mở.
    """
    lines = [
        "        {name: %s, file: %s, u: %.9g, v: %.9g, w: %.9g, h: %.9g},"
        % (_js_string(name), _js_string(path.replace("\\", "/")), u, v, w, h)
        for name, path, u, v, w, h in items
    ]
    return _JSX_APPEND_TEMPLATE % {
        "linked": "true" if linked else "false",
        "psd": _js_string(psd_path.replace("\\", "/")),
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
    palette_psd: StringProperty(
        name="PSD",
        description=("File PSD palette đã có, để thêm texture mới vào. Bỏ "
                     "trống thì dùng document đang mở sẵn trong Photoshop"),
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

        problem = _uv_problem(targets)
        if problem:
            self.report({'ERROR'}, problem)
            return {'CANCELLED'}

        # Texture trong material cũ mà chưa export thì sau khi gán material
        # mới sẽ thành orphan — lưu file là Blender purge mất. Cảnh báo trước.
        unexported = _unexported_textures(targets, props)

        for index, ob in enumerate(targets):
            _place_uv_in_cell(ob.data, _cell_rect(index, rows, cols))
            _stamp_cell(ob, cols, rows, index)

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

        # Ô của object trên canvas — mốc dưới cho ảnh nguồn nhỏ.
        cell_px = max(1, min(props.canvas_size // props.cols,
                             props.canvas_size // props.rows))

        written, no_tex, downsized, failed, overwritten = [], [], [], [], []
        for ob in targets:
            image, reason = _object_texture(ob)
            if image is None:
                no_tex.append("%s (%s)" % (ob.name, reason))
                continue

            src_w, src_h = image.size
            # Nguồn nhỏ hơn Size thì xuất ở kích thước gốc — Photoshop resize
            # layer về đúng ô rồi, phóng to ở đây chỉ làm file nặng mà không
            # thêm chi tiết. Nhỏ hơn cả ô thì mới phóng lên bằng ô.
            target = size
            if 0 < min(src_w, src_h) < size:
                target = min(size, max(cell_px, min(src_w, src_h)))
                downsized.append("%s (%dx%d -> %dpx)"
                                 % (ob.name, src_w, src_h, target))

            path = os.path.join(directory, _safe_filename(ob.name) + ".png")
            existed = os.path.exists(path)
            try:
                _export_image_png(image, target, path)
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
        if downsized:
            parts.append("texture gốc nhỏ hơn %dpx nên xuất đúng cỡ gốc "
                         "(không nhỏ hơn ô %dpx): %s"
                         % (size, cell_px, ", ".join(downsized)))
        if no_tex:
            parts.append("không có texture: " + ", ".join(no_tex))
        if failed:
            parts.append("lỗi: " + ", ".join(failed))

        message = ". ".join(parts) + "."
        if failed or not written:
            self.report({'ERROR'} if not written else {'WARNING'}, message)
            return {'CANCELLED'} if not written else {'FINISHED'}
        self.report({'WARNING'} if (downsized or no_tex or overwritten)
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


class AUTOUVPAL_OT_add_to_palette(Operator):
    bl_idname = "object.auto_uv_palette_add"
    bl_label = "Add Selected to Empty Cells"
    bl_description = ("Xếp UV của các object đã chọn vào những ô còn trống của "
                      "palette đã có, rồi gán luôn material palette đó. Ô đã "
                      "có object hoặc đã có texture trong ảnh palette sẽ được "
                      "chừa ra")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette
        rows, cols = props.rows, props.cols

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        problem = _uv_problem(targets)
        if problem:
            self.report({'ERROR'}, problem)
            return {'CANCELLED'}

        mat, pcols, prows, error = _pick_palette_material(
            context, cols, rows, set(targets))
        if mat is None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        # Object đã nằm trong palette thì UV của nó đã bị thu nhỏ vào ô rồi —
        # chạy tiếp là thu nhỏ thêm một lần nữa.
        already = [ob.name for ob in targets
                   if any(slot.material is mat for slot in ob.material_slots)]
        if already:
            self.report(
                {'ERROR'},
                "Đã nằm trong palette \"%s\" rồi, bỏ khỏi selection: %s."
                % (mat.name, ", ".join(already)),
            )
            return {'CANCELLED'}

        # Hai nguồn "ô đã dùng", lấy hợp của cả hai cho chắc: object trong
        # scene đang dùng material palette, và pixel đục trong ảnh palette.
        taken = _scene_occupancy(context, mat, pcols, prows, cols, rows,
                                 set(targets))
        occupied = set(taken)
        sources = ["%d ô có object" % len(taken)] if taken else []

        image, image_error = _palette_image_datablock(props)
        image_cells = _image_occupancy(image, rows, cols) if image else None
        if image_cells is not None:
            occupied |= image_cells
            sources.append("%d ô có texture trong \"%s\"" % (len(image_cells),
                                                            image.name))

        if not occupied:
            notes = []
            if image_error:
                notes.append(image_error)
            elif image is not None and image_cells is None:
                notes.append("ảnh palette không có vùng trong suốt nên không "
                             "đọc được ô trống từ nó")
            elif image is None:
                notes.append("chưa trỏ Palette tới ảnh nào")
            self.report(
                {'ERROR'},
                "Không thấy ô nào đã dùng trong palette \"%s\" (%s) — dùng "
                "Pack UVs into Palette thay vì thêm vào."
                % (mat.name, "; ".join(notes) or "palette rỗng"),
            )
            return {'CANCELLED'}

        free = _free_cells(occupied, cols, rows, pcols, prows)
        if len(free) < len(targets):
            self.report(
                {'ERROR'},
                "Palette \"%s\" chỉ còn %d ô trống, cần %d. Tăng grid rồi xếp "
                "lại từ đầu bằng Pack UVs."
                % (mat.name, len(free), len(targets)),
            )
            return {'CANCELLED'}

        unexported = _unexported_textures(targets, props)

        placed = []
        for ob, index in zip(targets, free):
            _place_uv_in_cell(ob.data, _cell_rect(index, rows, cols))
            _stamp_cell(ob, cols, rows, index)
            ob.data.materials.clear()
            ob.data.materials.append(mat)
            row, col = divmod(index, cols)
            placed.append("%s -> H%d C%d" % (ob.name, row + 1, col + 1))

        split = ("" if (cols, rows) == (pcols, prows) else
                 " (ô %dx%d chia nhỏ từ ô %dx%d, mỗi ô bằng 1/%d ô gốc)"
                 % (cols, rows, pcols, prows,
                    (cols // pcols) * (rows // prows)))
        message = ("Đã thêm %d object vào palette \"%s\"%s (%s). Còn %d ô "
                   "trống. Nguồn ô đã dùng: %s."
                   % (len(placed), mat.name, split, "; ".join(placed),
                      len(free) - len(placed), ", ".join(sources)))
        warnings = []
        if image_error:
            warnings.append(image_error + " — chỉ dựa vào object trong scene")
        if unexported:
            warnings.append(
                "texture của %s chưa export — material cũ giờ không còn ai "
                "dùng, lưu file là mất texture. Ctrl+Z rồi chạy Export "
                "Selected Textures trước nếu cần giữ" % ", ".join(unexported))
        if warnings:
            self.report({'WARNING'},
                        message + " Lưu ý: " + "; ".join(warnings) + ".")
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


class AUTOUVPAL_OT_append_psd(Operator):
    bl_idname = "object.auto_uv_palette_append_psd"
    bl_label = "Append Textures to PSD"
    bl_description = ("Sinh script Photoshop đặt PNG của các object đã chọn "
                      "vào đúng ô của chúng trong file PSD palette đã có, rồi "
                      "mở Photoshop chạy nó")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        props = context.scene.auto_uv_palette
        cols, rows = props.cols, props.rows

        targets = _sorted_targets(context)
        if not targets:
            self.report({'ERROR'}, "Chưa chọn mesh object nào.")
            return {'CANCELLED'}

        if not props.export_dir:
            self.report({'ERROR'}, "Chưa chọn đường dẫn export.")
            return {'CANCELLED'}
        directory = bpy.path.abspath(props.export_dir)
        if not os.path.isdir(directory):
            self.report({'ERROR'}, "Thư mục export không tồn tại: " + directory)
            return {'CANCELLED'}

        psd_path = ""
        if props.palette_psd:
            psd_path = bpy.path.abspath(props.palette_psd)
            if not os.path.isfile(psd_path):
                self.report({'ERROR'}, "File PSD không tồn tại: " + psd_path)
                return {'CANCELLED'}

        # Ô của mỗi object lấy từ dấu đã ghi lúc xếp — nhờ vậy asset to (ô
        # 8x8) và asset nhỏ (ô 16x16) append chung một lượt vẫn đúng cỡ.
        # Object xếp bằng bản add-on cũ chưa có dấu thì đọc từ UV theo grid
        # đang gõ trong panel.
        items, missing, no_cell, clashes, not_packed = [], [], [], [], []
        seen = []
        for ob in targets:
            stamp = _stamped_cell(ob)
            if stamp is not None:
                scols, srows, index = stamp
            else:
                scols, srows = cols, rows
                index = _uv_cell_index(ob.data, rows, cols)
                if index is None:
                    no_cell.append(ob.name)
                    continue
                if _uv_overflows_cell(ob.data, rows, cols):
                    not_packed.append(ob.name)
                    continue
            path = os.path.join(directory, _safe_filename(ob.name) + ".png")
            if not os.path.isfile(path):
                missing.append(os.path.basename(path))
                continue

            min_u, min_v, width, height = _cell_rect(index, srows, scols)
            # Photoshop đo y từ đỉnh xuống, UV đo v từ đáy lên.
            rect = (min_u, 1.0 - min_v - height, width, height)
            overlap = next((name for name, other in seen
                            if _rects_overlap(rect, other)), None)
            if overlap is not None:
                clashes.append("%s và %s" % (overlap, ob.name))
                continue
            seen.append((ob.name, rect))
            items.append((ob.name, path) + rect)

        if no_cell:
            self.report({'ERROR'}, "Không đọc được UV để biết ô: "
                                   + ", ".join(no_cell))
            return {'CANCELLED'}
        if not_packed:
            self.report(
                {'ERROR'},
                "UV của %s còn trải rộng hơn một ô — chưa được xếp vào "
                "palette, đặt vào PSD bây giờ sẽ rơi vào giữa canvas chứ "
                "không vào ô nào. Chạy Add Selected to Empty Cells (hoặc "
                "Pack UVs into Palette) trước, và kiểm tra Columns/Rows đúng "
                "bằng grid của palette." % ", ".join(not_packed),
            )
            return {'CANCELLED'}
        if missing:
            self.report(
                {'ERROR'},
                "Chưa có PNG cho: %s. Chạy Export Selected Textures trước."
                % ", ".join(missing),
            )
            return {'CANCELLED'}
        if clashes:
            self.report(
                {'ERROR'},
                "Ô của các object này chồng lên nhau (%s) — chạy Add Selected "
                "to Empty Cells trước." % "; ".join(clashes),
            )
            return {'CANCELLED'}

        jsx_path = os.path.join(directory, _JSX_APPEND_NAME)
        script = _build_append_jsx(items,
                                   props.smart_object_mode == 'LINKED',
                                   psd_path)
        try:
            with open(jsx_path, "w", encoding="utf-8") as handle:
                handle.write(script)
        except OSError as err:
            self.report({'ERROR'}, "Không ghi được script: %s" % err)
            return {'CANCELLED'}

        where = (os.path.basename(psd_path) if psd_path
                 else "document đang mở trong Photoshop")
        exe = _find_photoshop()
        if exe is None:
            self.report(
                {'WARNING'},
                "Đã ghi %s nhưng không tìm thấy Photoshop.exe — chạy tay bằng "
                "File > Scripts > Browse." % jsx_path,
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
        self.report(
            {'INFO'},
            "Đã ghi %s (%d layer %s Smart Object vào %s) và mở Photoshop. Nhớ "
            "Save lại palette." % (_JSX_APPEND_NAME, len(items), mode, where),
        )
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

        layout.separator()
        layout.label(text="Add to Existing Palette", icon='ADD')

        # Chỉ đọc tên material ở đây — tìm ô trống phải quét UV/pixel nên để
        # operator làm, panel vẽ lại liên tục.
        info = layout.box()
        selected = set(targets)
        grids = _palette_grids()
        chosen, pcols, prows, _error = _pick_palette_material(
            context, cols, rows, selected)
        if chosen is not None:
            users = sum(1 for ob in context.scene.objects
                        if ob.type == 'MESH' and ob not in selected
                        and any(slot.material is chosen
                                for slot in ob.material_slots))
            info.label(text="%s · %d object đã trong palette"
                            % (chosen.name, users), icon='MATERIAL')
            if (cols, rows) != (pcols, prows):
                info.label(text="Chia nhỏ ô: 1 ô %dx%d = %d ô %dx%d"
                                % (pcols, prows,
                                   (cols // pcols) * (rows // prows),
                                   cols, rows))
        elif grids:
            info.label(text="Grid %dx%d không dùng được với palette nào"
                            % (cols, rows), icon='ERROR')
            info.label(text="Đang có: " + ", ".join(
                sorted({"%dx%d" % (c, r) for _mat, c, r in grids})))
        else:
            info.label(text="Chưa có palette nào — chạy Pack UVs trước",
                       icon='ERROR')

        # Ô mà Append sẽ dùng, lấy y hệt operator — để thấy trước object chưa
        # xếp, thay vì phát hiện khi đã vào Photoshop.
        if targets:
            preview = info.column(align=True)
            for ob in targets[:_PREVIEW_ROWS]:
                stamp = _stamped_cell(ob)
                if stamp is not None:
                    scols, srows, index = stamp
                elif len(ob.data.loops) > _PREVIEW_MAX_LOOPS:
                    preview.label(text="%s — mesh nặng, bỏ qua preview"
                                       % ob.name)
                    continue
                else:
                    scols, srows = cols, rows
                    index = _uv_cell_index(ob.data, rows, cols)
                    if index is None:
                        preview.label(text="%s — chưa có UV" % ob.name,
                                      icon='ERROR')
                        continue
                    if _uv_overflows_cell(ob.data, rows, cols):
                        preview.label(text="%s — chưa xếp vào ô nào" % ob.name,
                                      icon='ERROR')
                        continue
                cell_row, cell_col = divmod(index, scols)
                size_note = ("" if (scols, srows) == (cols, rows)
                             else " (ô %dx%d)" % (scols, srows))
                preview.label(text="H%d C%d%s   %s"
                                   % (cell_row + 1, cell_col + 1, size_note,
                                      ob.name))
            if len(targets) > _PREVIEW_ROWS:
                preview.label(text="… và %d object nữa"
                                   % (len(targets) - _PREVIEW_ROWS))

        layout.operator(AUTOUVPAL_OT_add_to_palette.bl_idname, icon='ADD')
        layout.prop(props, "palette_psd")
        row = layout.row()
        row.enabled = bool(props.export_dir)
        row.operator(AUTOUVPAL_OT_append_psd.bl_idname, icon='FILE_IMAGE')


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
    AUTOUVPAL_OT_add_to_palette,
    AUTOUVPAL_OT_append_psd,
    AUTOUVPAL_PT_view3d,
    AUTOUVPAL_PT_image,
)


@bpy.app.handlers.persistent
def _fix_legacy_stamps(_file_path):
    """Vá dấu ô dạng tuple của bản 1.3.0 ngay khi mở file.

    Dấu cũ nằm trong .blend chứ không nằm trong code, nên nâng bản add-on
    không tự hết — file vẫn làm hỏng export FBX (xem `_stamp_cell`). Vá lúc
    mở file thì mở + lưu lại một lần là xong, không cần bấm nút nào.
    """
    fixed = _restamp_legacy(bpy.data.objects)
    if fixed:
        print("Auto UV Palette: da va dau o cu cho %d object (%s). Luu file "
              "de khoi bao loi export FBX." % (len(fixed), ", ".join(fixed)))


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.auto_uv_palette = PointerProperty(type=AUTOUVPAL_Props)
    if _fix_legacy_stamps not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_fix_legacy_stamps)
    # Bật add-on giữa chừng thì vá luôn file đang mở. Lúc Blender khởi động,
    # bpy.data còn bị khoá (_RestrictData) — khi đó load_post lo phần đó.
    if hasattr(bpy.data, "objects"):
        _restamp_legacy(bpy.data.objects)


def unregister():
    if _fix_legacy_stamps in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_fix_legacy_stamps)
    del bpy.types.Scene.auto_uv_palette
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
