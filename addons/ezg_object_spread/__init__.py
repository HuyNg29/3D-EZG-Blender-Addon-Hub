"""Object Spread: trai cac object dang chon thanh luoi de xem, hoac dua ve 0,0,0.

Object con ma parent CUNG dang duoc chon thi khong xep rieng: no di theo parent
nhu binh thuong, giu nguyen vi tri tuong doi. Chi object "goc" cua nhom chon
(khong co to tien nao dang duoc chon) moi bi dich. Khong object nao bi go parent.
"""

import math
import re

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty
from mathutils import Vector

from . import ezg_i18n
from .ezg_i18n import tr


# Object khong co hinh: bound_box cua no chi la mot diem -> khong tinh vao kich thuoc o.
NO_GEOMETRY_TYPES = {'EMPTY', 'LIGHT', 'LIGHT_PROBE', 'CAMERA', 'SPEAKER'}

# Duoi nguong nay coi la 0: tranh panel N hien "-0 m" sau khi dua ve 0,0,0.
EPSILON = 1e-6

MODE_ITEMS = [
    ('AUTO', tr("Tự động", "Auto"),
     tr("Lưới gần vuông, tự tính theo số object", "A near-square grid sized to the selection")),
    ('COLUMNS', tr("Theo cột", "By Columns"),
     tr("Đặt số cột, số hàng tự tính", "Set the column count, rows follow")),
    ('ROWS', tr("Theo hàng", "By Rows"),
     tr("Đặt số hàng, object chia đều cho các hàng",
        "Set the row count, objects are shared evenly between the rows")),
]


# Property dung chung cho bang Settings (panel) va operator Xep luoi (bang F9).
def _mode_prop(**kw):
    return EnumProperty(name=tr("Chia lưới", "Grid"),
                        description=tr("Cách tính số cột và số hàng",
                                       "How the column and row counts are chosen"),
                        items=MODE_ITEMS, default='AUTO', **kw)


def _columns_prop(**kw):
    return IntProperty(name=tr("Số cột", "Columns"),
                       description=tr("Số object trên mỗi hàng", "Objects per row"),
                       min=1, soft_max=50, default=5, **kw)


def _rows_prop(**kw):
    return IntProperty(name=tr("Số hàng", "Rows"),
                       description=tr("Số hàng của lưới", "Number of rows in the grid"),
                       min=1, soft_max=50, default=2, **kw)


def _gap_prop(**kw):
    return FloatProperty(name=tr("Khoảng cách", "Gap"),
                         description=tr("Khoảng trống tối thiểu giữa hai object cạnh nhau, "
                                        "đo từ mép object chứ không phải từ pivot",
                                        "Minimum empty space between neighbouring objects, "
                                        "measured from their edges, not their pivots"),
                         subtype='DISTANCE', min=0.0, soft_max=10.0, default=1.0, **kw)


# ---------------------------------------------------------------------------
# Tinh toan
# ---------------------------------------------------------------------------

def _natural_key(ob):
    # "Rock_2" dung truoc "Rock_10". re.split co nhom bat nen so luon o vi tri le.
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", ob.name)]


def selection_roots(objects):
    """Object goc cua nhom chon: khong co to tien nao cung dang duoc chon.

    Tra ve (danh sach goc sap theo ten, so object con di theo parent).
    """
    chosen = set(objects)
    roots = []
    for ob in objects:
        p = ob.parent
        while p is not None and p not in chosen:
            p = p.parent
        if p is None:
            roots.append(ob)
    roots.sort(key=_natural_key)
    return roots, len(objects) - len(roots)


def grid_cells(n, mode, columns, rows):
    """O (cot, hang) cho n object, doc trai -> phai, tren -> duoi.

    Tra ve (danh sach o, so cot, so hang).
    """
    if n <= 0:
        return [], 0, 0
    if mode == 'ROWS':
        # Giu dung so hang: chia deu, hang tren nhan phan du.
        # 7 object / 5 hang -> 2, 2, 1, 1, 1 (thay vi 2, 2, 2, 1 chi co 4 hang).
        r = max(1, min(rows, n))
        base, extra = divmod(n, r)
        cells = [(col, row) for row in range(r)
                 for col in range(base + (1 if row < extra else 0))]
        return cells, base + (1 if extra else 0), r
    if mode == 'COLUMNS':
        c = max(1, min(columns, n))
    else:
        c = math.ceil(math.sqrt(n))
    return [(i % c, i // c) for i in range(n)], c, math.ceil(n / c)


def _members(roots):
    """Moi goc keo theo chinh no + toan bo con chau (chon hay khong cung di theo)."""
    children = {}
    for ob in bpy.data.objects:
        if ob.parent is not None:
            children.setdefault(ob.parent, []).append(ob)
    groups = []
    for root in roots:
        group, stack = [], [root]
        while stack:
            ob = stack.pop()
            group.append(ob)
            stack.extend(children.get(ob, ()))
        groups.append(group)
    return groups


def _makes_instances(ob):
    return (ob.instance_type != 'NONE'
            or any(m.type == 'NODES' for m in ob.modifiers)
            or len(ob.particle_systems) > 0)


def _grow(box, matrix, corners):
    """Noi hop bao XY [minx, miny, maxx, maxy] cho them bound_box (toa do local)."""
    if all(c[0] == c[1] == c[2] == 0.0 for c in corners):
        return box  # bound_box rong: object khong co hinh nao that
    pts = [matrix @ Vector(c) for c in corners]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    if box is None:
        return [min(xs), min(ys), max(xs), max(ys)]
    return [min(box[0], *xs), min(box[1], *ys), max(box[2], *xs), max(box[3], *ys)]


def world_bounds(context, groups):
    """Hop bao XY theo truc the gioi cua tung nhom; None neu nhom khong co hinh.

    Chi tinh object dang hien. Hinh sinh ra boi collection instance, Geometry
    Nodes, particle khong nam trong bound_box cua object, phai lay qua
    depsgraph.object_instances — chi duyet khi can vi canh lon co the co hang
    trieu instance.
    """
    depsgraph = context.evaluated_depsgraph_get()
    view_layer = context.view_layer
    boxes = [None] * len(groups)
    owner = {}
    need_instances = False
    for idx, group in enumerate(groups):
        for ob in group:
            owner[ob] = idx
            if _makes_instances(ob):
                need_instances = True
            if ob.type in NO_GEOMETRY_TYPES or not ob.visible_get(view_layer=view_layer):
                continue
            ev = ob.evaluated_get(depsgraph)
            boxes[idx] = _grow(boxes[idx], ev.matrix_world, ev.bound_box)

    if need_instances:
        for inst in depsgraph.object_instances:
            if not inst.is_instance or inst.object.type in NO_GEOMETRY_TYPES:
                continue
            idx = owner.get(inst.parent.original)
            if idx is not None:
                boxes[idx] = _grow(boxes[idx], inst.matrix_world, inst.object.bound_box)
    return boxes


def _place(ob, target):
    """Dua pivot cua object toi diem `target` (toa do the gioi).

    Object con giu nguyen parent: chi doi location trong khong gian cua parent,
    nen sau do van di theo parent nhu cu.
    """
    if ob.parent is None and not ob.constraints:
        # Gan thang: matrix_world.translation = location + delta_location, nen
        # object cung cot ra dung cung mot so X, khong lech nhau vai ulp.
        new = target - ob.delta_location
    else:
        space = ob.matrix_world @ ob.matrix_basis.inverted_safe()
        delta = target - ob.matrix_world.translation
        new = ob.location + space.to_3x3().inverted_safe() @ delta
    ob.location = [0.0 if abs(v) < EPSILON else v for v in new]


def _editable(objects):
    """Tach object link tu thu vien (khong sua duoc vi tri) ra khoi danh sach."""
    ok = [ob for ob in objects if ob.is_editable]
    return ok, len(objects) - len(ok)


def arrange(context, roots, mode, columns, rows, gap):
    """Dat pivot cua cac goc len cac diem cua luoi quanh 3D cursor.

    Cung cot thi cung X, cung hang thi cung Y, moi pivot cung do cao Z voi
    cursor. Buoc luoi = phan object thoi ra xa nhat ve hai phia cua pivot + gap
    (tinh rieng cho X va Y), nen luoi deu ma khong object nao chong len nhau, ke
    ca asset co pivot nam o mep thay vi o giua. Tra ve (so cot, so hang).
    """
    groups = _members(roots)
    boxes = world_bounds(context, groups)
    pivots = [root.matrix_world.translation.copy() for root in roots]
    for i, p in enumerate(pivots):
        if boxes[i] is None:  # Empty, light... khong co hinh: chi la mot diem o pivot
            boxes[i] = [p.x, p.y, p.x, p.y]

    pairs = list(zip(pivots, boxes))
    step_x = (max(p.x - b[0] for p, b in pairs)      # thoi sang trai pivot
              + max(b[2] - p.x for p, b in pairs) + gap)
    step_y = (max(b[3] - p.y for p, b in pairs)      # thoi len tren pivot
              + max(p.y - b[1] for p, b in pairs) + gap)

    cells, n_cols, n_rows = grid_cells(len(roots), mode, columns, rows)
    cursor = context.scene.cursor.location
    for root, (col, row) in zip(roots, cells):
        _place(root, Vector((cursor.x + (col - (n_cols - 1) / 2) * step_x,
                             cursor.y - (row - (n_rows - 1) / 2) * step_y,
                             cursor.z)))
    return n_cols, n_rows


def to_origin(context, roots):
    context.evaluated_depsgraph_get()  # cho chac matrix_world da cap nhat
    for root in roots:
        _place(root, Vector((0.0, 0.0, 0.0)))


def _follow_note(followers):
    if not followers:
        return ""
    return tr(" %d object con đi theo parent.", " %d children follow their parent.") % followers


def _skip_note(skipped):
    if not skipped:
        return ""
    return tr(" Bỏ qua %d object link từ thư viện.",
              " Skipped %d objects linked from a library.") % skipped


def _has_selection(cls, context):
    if getattr(context, "selected_objects", None):
        return True
    cls.poll_message_set(tr("Chưa chọn object nào.", "No objects selected."))
    return False


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class EZG_SPREAD_Settings(bpy.types.PropertyGroup):
    mode: _mode_prop()
    columns: _columns_prop()
    rows: _rows_prop()
    gap: _gap_prop()


GRID_PROPS = ("mode", "columns", "rows", "gap")


class EZG_SPREAD_OT_arrange(bpy.types.Operator):
    bl_idname = "ezg_spread.arrange"
    bl_label = tr("Xếp lưới", "Arrange in Grid")
    bl_description = tr("Đặt pivot của các object đang chọn lên lưới quanh 3D cursor: cùng cột "
                        "thì cùng X, cùng hàng thì cùng Y, mọi pivot cùng độ cao Z với cursor. "
                        "Object con có parent cũng đang chọn thì đi theo parent",
                        "Put the pivots of the selected objects on a grid around the 3D cursor: "
                        "same column means same X, same row means same Y, and every pivot "
                        "sits at the cursor's height. Children whose parent is also selected "
                        "follow the parent")
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: khong nho gia tri lan truoc -> property nao chua dat thi lay
    # tu panel. Chinh o bang Adjust Last Operation (F9) thi ghi nguoc ve panel.
    mode: _mode_prop(options={'SKIP_SAVE'})
    columns: _columns_prop(options={'SKIP_SAVE'})
    rows: _rows_prop(options={'SKIP_SAVE'})
    gap: _gap_prop(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _has_selection(cls, context)

    def execute(self, context):
        settings = context.scene.ezg_spread
        for name in GRID_PROPS:
            if not self.properties.is_property_set(name):
                setattr(self, name, getattr(settings, name))
            setattr(settings, name, getattr(self, name))

        roots, followers = selection_roots(context.selected_objects)
        roots, skipped = _editable(roots)
        if not roots:
            self.report({'WARNING'}, tr("Không có object nào sửa được vị trí.",
                                        "No selected object can be moved.") + _skip_note(skipped))
            return {'CANCELLED'}

        n_cols, n_rows = arrange(context, roots, self.mode, self.columns, self.rows, self.gap)
        self.report({'WARNING'} if skipped else {'INFO'},
                    tr("Đã xếp %d object thành lưới %d cột × %d hàng.",
                       "Arranged %d objects in a grid of %d columns × %d rows.")
                    % (len(roots), n_cols, n_rows) + _follow_note(followers) + _skip_note(skipped))
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "mode")
        if self.mode == 'COLUMNS':
            layout.prop(self, "columns")
        elif self.mode == 'ROWS':
            layout.prop(self, "rows")
        layout.prop(self, "gap")


class EZG_SPREAD_OT_to_origin(bpy.types.Operator):
    bl_idname = "ezg_spread.to_origin"
    bl_label = tr("Về 0,0,0", "Move to 0,0,0")
    bl_description = tr("Đưa pivot của các object đang chọn về gốc toạ độ 0,0,0. Object con có "
                        "parent cũng đang chọn thì đi theo parent, giữ nguyên vị trí tương đối",
                        "Move the pivot of the selected objects to the world origin 0,0,0. "
                        "Children whose parent is also selected follow the parent and keep "
                        "their offset")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _has_selection(cls, context)

    def execute(self, context):
        roots, followers = selection_roots(context.selected_objects)
        roots, skipped = _editable(roots)
        if not roots:
            self.report({'WARNING'}, tr("Không có object nào sửa được vị trí.",
                                        "No selected object can be moved.") + _skip_note(skipped))
            return {'CANCELLED'}

        to_origin(context, roots)
        self.report({'WARNING'} if skipped else {'INFO'},
                    tr("Đã đưa %d object về 0,0,0.", "Moved %d objects to 0,0,0.") % len(roots)
                    + _follow_note(followers) + _skip_note(skipped))
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class EZG_SPREAD_PT_panel(bpy.types.Panel):
    bl_label = "Object Spread"  # i18n-skip
    bl_idname = "EZG_SPREAD_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Spread"

    def draw_header_preset(self, context):
        ezg_i18n.draw_toggle(self.layout, "ezg_spread")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ezg_spread
        selected = getattr(context, "selected_objects", None) or []
        roots, followers = selection_roots(selected)

        col = layout.box().column(align=True)
        if selected:
            col.label(text=tr("Object đang chọn: %d", "Selected objects: %d") % len(selected),
                      icon='OBJECT_DATA')
            if followers:
                col.label(text=tr("Object con đi theo parent: %d",
                                  "Children following their parent: %d") % followers,
                          icon='CON_CHILDOF')
        else:
            col.label(text=tr("Chưa chọn object nào.", "No objects selected."), icon='INFO')

        layout.separator(factor=0.5)
        layout.row(align=True).prop(settings, "mode", expand=True)
        if settings.mode == 'COLUMNS':
            layout.prop(settings, "columns")
        elif settings.mode == 'ROWS':
            layout.prop(settings, "rows")
        if roots:
            _, n_cols, n_rows = grid_cells(len(roots), settings.mode,
                                           settings.columns, settings.rows)
            layout.label(text=tr("Cột × hàng: %d × %d", "Columns × rows: %d × %d")
                         % (n_cols, n_rows), icon='MESH_GRID')
        layout.prop(settings, "gap")

        layout.separator(factor=0.5)
        col = layout.column(align=True)
        col.scale_y = 1.6
        col.operator(EZG_SPREAD_OT_arrange.bl_idname, icon='MESH_GRID')
        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator(EZG_SPREAD_OT_to_origin.bl_idname, icon='EMPTY_AXIS')


classes = (
    EZG_SPREAD_Settings,
    EZG_SPREAD_OT_arrange,
    EZG_SPREAD_OT_to_origin,
    EZG_SPREAD_PT_panel,
    ezg_i18n.make_language_operator("ezg_spread"),
)


def register():
    ezg_i18n.register_classes(classes)
    bpy.types.Scene.ezg_spread = PointerProperty(type=EZG_SPREAD_Settings)


def unregister():
    del bpy.types.Scene.ezg_spread
    ezg_i18n.unregister_classes(classes)
