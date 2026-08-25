"""GN Info Namer — đặt nhãn cho node Object Info / Collection Info theo tên
object (hoặc collection) mà node đó đang trỏ tới.

Geometry Node Editor > phím N > tab "EZG".

Node Object Info nào cũng hiện đúng một chữ "Object Info" trên đầu, nên một cây
có mười node nhìn giống hệt nhau — phải bấm vào từng cái mới biết nó lấy object
gì. Addon này ghi tên object vào `node.label`, là chuỗi Blender hiển thị thay cho
tên node, nên nhìn cây là đọc được ngay.

Nhãn KHÔNG tự cập nhật khi đổi object trong node. Bấm lại nút là xong.
"""

import bpy

# Node muon dat nhan -> ten socket dau vao chua datablock lay ten.
# Dung node.bl_idname (khong doi giua cac ban Blender) thay vi node.type.
INFO_NODES = {
    "GeometryNodeObjectInfo": "Object",
    "GeometryNodeCollectionInfo": "Collection",
}

CATEGORY = "EZG"


def _walk_trees(root):
    """Duyet mot node tree VA moi group long ben trong no (khong lap vo han)."""
    seen = set()
    stack = [root]
    while stack:
        tree = stack.pop()
        if tree is None or tree.as_pointer() in seen:
            continue
        seen.add(tree.as_pointer())
        yield tree
        for node in tree.nodes:
            sub = getattr(node, "node_tree", None)
            if sub is not None:
                stack.append(sub)


def _trees_in_file():
    """Moi geometry node tree trong file, ke ca group chua gan vao modifier nao.

    Ban goc chi quet node_group cua modifier nen bo sot group long ben trong va
    cac cay dang lam do chua gan vao object.
    """
    for tree in bpy.data.node_groups:
        if tree.bl_idname == "GeometryNodeTree":
            yield tree


def label_info_nodes(trees):
    """Ghi ten object/collection vao node.label. Tra ve (so nhan doi, so bo trong).

    Node chua tro toi datablock nao thi de nguyen — xoa nhan cua no se lam mat
    ghi chu nguoi dung tu go.
    """
    renamed = 0
    empty = 0
    for tree in trees:
        for node in tree.nodes:
            socket_name = INFO_NODES.get(node.bl_idname)
            if socket_name is None:
                continue
            socket = node.inputs.get(socket_name)
            data = socket.default_value if socket else None
            if data is None:
                empty += 1
                continue
            if node.label != data.name:
                node.label = data.name
                renamed += 1
    return renamed, empty


def _edit_tree(context):
    """Cay geometry node dang mo trong editor, hoac None."""
    space = getattr(context, "space_data", None)
    if space is None or space.type != 'NODE_EDITOR':
        return None
    if space.tree_type != 'GeometryNodeTree':
        return None
    return space.edit_tree


class EZG_GN_OT_label_info_nodes(bpy.types.Operator):
    """Ghi ten object / collection vao nhan cua node Info"""

    bl_idname = "ezg_gn.label_info_nodes"
    bl_label = "Đặt nhãn theo tên Object"
    bl_options = {'REGISTER', 'UNDO'}

    whole_file: bpy.props.BoolProperty(
        name="Cả file",
        default=False,
        description=("Xu li moi geometry node tree trong file, khong chi cay dang mo. "
                     "Tat: chi cay dang mo va cac group long ben trong no"),
    )

    @classmethod
    def description(cls, context, properties):
        if properties.whole_file:
            return "Đặt nhãn cho node Info trong MỌI geometry node tree của file này"
        return "Đặt nhãn cho node Info trong cây đang mở và các group lồng bên trong"

    def execute(self, context):
        if self.whole_file:
            trees = _trees_in_file()
        else:
            tree = _edit_tree(context)
            if tree is None:
                self.report({'WARNING'}, "Không có cây Geometry Nodes nào đang mở.")
                return {'CANCELLED'}
            trees = _walk_trees(tree)

        renamed, empty = label_info_nodes(trees)

        msg = "Đã đặt nhãn cho %d node." % renamed
        if renamed == 0:
            msg = "Không có nhãn nào cần đổi."
        if empty:
            msg += " Bỏ qua %d node chưa trỏ tới object/collection nào." % empty
        self.report({'INFO'} if not empty else {'WARNING'}, msg)
        return {'FINISHED'}


class EZG_GN_PT_info_namer(bpy.types.Panel):
    bl_label = "GN Info Namer"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    @classmethod
    def poll(cls, context):
        # Chi hien trong Geometry Node Editor — panel nay vo nghia o shader/compositor.
        space = getattr(context, "space_data", None)
        return space is not None and getattr(space, "tree_type", "") == 'GeometryNodeTree'

    def draw(self, context):
        layout = self.layout
        tree = _edit_tree(context)

        if tree is None:
            layout.label(text="Chưa mở cây node nào.", icon='INFO')
            return

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator(EZG_GN_OT_label_info_nodes.bl_idname,
                     icon='SORTALPHA').whole_file = False

        row = layout.row(align=True)
        row.operator(EZG_GN_OT_label_info_nodes.bl_idname,
                     text="Cả file", icon='FILE_BLEND').whole_file = True

        n_info = sum(
            1 for t in _walk_trees(tree) for node in t.nodes
            if node.bl_idname in INFO_NODES
        )
        layout.label(text="Cây này: %d node Info" % n_info, icon='NODE')


classes = (EZG_GN_OT_label_info_nodes, EZG_GN_PT_info_namer)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
