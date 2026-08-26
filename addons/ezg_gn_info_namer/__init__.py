"""GN Info Namer — dọn đám node Object Info / Collection Info trong Geometry Nodes.

Geometry Node Editor > phím N > tab "EZG". Năm việc:

  Thêm object chọn object ngoài viewport, bấm một nút là mỗi cái thành một node
              Object Info, nối hết vào một Join Geometry, đặt nhãn và dàn thẳng
              hàng luôn. Object đang mang chính modifier đó (thường là object
              chọn cuối cùng, chữ vàng) bị loại ra — trỏ node vào chính nó là
              vòng phụ thuộc, Blender cho cả modifier chết.

  Đặt nhãn    ghi tên object (hoặc collection) mà node đang trỏ tới vào
              `node.label` — chuỗi Blender hiển thị thay cho tên node.
              Node Object Info nào cũng hiện đúng một chữ "Object Info" trên
              đầu, nên một cây mười node nhìn giống hệt nhau; có nhãn thì nhìn
              là đọc được ngay, khỏi bấm vào từng cái.

  Sắp xếp     dàn các node đó về một cột (hoặc hàng) thẳng, cách đều, và thu
              nhỏ (`node.hide`) cho gọn. Sắp được theo vị trí đang thấy hoặc
              theo nhãn A→Z — nên chạy sau khi đặt nhãn thì ra danh sách xếp
              theo tên object. Cắm lại luôn dây vào Join theo đúng thứ tự trên
              xuống để chúng chạy song song, không chéo qua nhau.

  Chọn object chọn node Info rồi bấm là object nó trỏ tới sáng lên ngoài
              viewport và outliner. Có công tắc làm việc đó tự động.

  Dọn         xoá các node Info không trỏ tới object nào, hoặc không có dây nào
              đi ra từ đầu ra của nó. Đây là việc duy nhất trong addon có thể
              làm mất công đang làm, nên nó luôn hiện bảng xem trước liệt kê
              đúng những node sắp bị xoá kèm lý do, xác nhận rồi mới xoá.

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
            if node.bl_idname not in INFO_NODES:
                continue
            data = _info_datablock(node)
            if data is None:
                empty += 1
                continue
            if node.label != data.name:
                node.label = data.name
                renamed += 1
    return renamed, empty


def _info_datablock(node):
    """Object / Collection ma node Info dang tro toi. None neu o trong."""
    socket_name = INFO_NODES.get(node.bl_idname)
    if socket_name is None:
        return None
    socket = node.inputs.get(socket_name)
    return socket.default_value if socket else None


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


# --- Sap xep -----------------------------------------------------------------
#
# Chieu cao mot node da thu nho (hide=True). Blender ve no thanh mot vien thuoc
# cao co dinh, khong phu thuoc so socket.
HIDDEN_HEIGHT = 32.0

# Node khong the thu nho / khong nen keo di rieng:
#   Frame  keo frame la keo theo moi node ben trong
#   Reroute chi la mot cham noi day, hide khong co tac dung
SKIP_TYPES = {"NodeFrame", "NodeReroute"}


def _node_height(node, ui_scale=1.0):
    """Chieu cao node theo don vi cua node tree.

    `node.dimensions` bang 0 voi node CHUA TUNG duoc ve tren man hinh, va bi cu
    ngay sau khi doi `hide` (Blender chi cap nhat luc redraw). Nen o day chi
    dung dimensions khi no co gia tri that, con lai thi uoc luong theo so socket.
    """
    if node.hide:
        return HIDDEN_HEIGHT

    dim_y = node.dimensions.y / (ui_scale or 1.0)
    if dim_y > 1.0:
        return dim_y

    sockets = sum(1 for s in node.inputs if s.enabled and not s.hide)
    sockets += sum(1 for s in node.outputs if s.enabled and not s.hide)
    return 34.0 + 22.0 * sockets


def _abs_y(node):
    """Do cao that trong cay: node trong frame co location tinh theo goc frame."""
    y = node.location.y
    parent = node.parent
    while parent is not None:
        y += parent.location.y
        parent = parent.parent
    return y


def untangle_links(tree, socket):
    """Cam lai day vao mot socket multi-input theo thu tu tren -> duoi cua node nguon.

    Cho cam cua tung soi day tren socket multi-input do `multi_input_sort_id`
    quyet dinh, ma thuoc tinh do CHI DOC va Blender dat no theo THU TU TAO
    LINK. Nen cach duy nhat de day het xoan la go het ra roi cam lai lan luot
    tu tren xuong. Tra ve so day da cam lai.
    """
    if not socket.is_multi_input:
        return 0

    links = list(socket.links)
    if len(links) < 2:
        return 0

    ordered = sorted(links, key=lambda l: (-_abs_y(l.from_node), l.from_node.location.x))
    # Ghi lai bang TEN: sau khi go link, giu tham chieu socket la khong chac chan.
    sources = [(l.from_node.name, l.from_socket.identifier) for l in ordered]

    for link in links:
        tree.links.remove(link)

    remade = 0
    for node_name, socket_id in sources:
        node = tree.nodes.get(node_name)
        if node is None:
            continue
        out = next((s for s in node.outputs if s.identifier == socket_id), None)
        if out is not None:
            tree.links.new(out, socket)
            remade += 1
    return remade


def untangle_downstream(tree, nodes):
    """Go xoan moi socket multi-input dang nhan day tu cac node nay."""
    targets = []
    seen = set()
    for node in nodes:
        for out in node.outputs:
            for link in out.links:
                socket = link.to_socket
                if not socket.is_multi_input:
                    continue
                key = (link.to_node.name, socket.identifier)
                if key not in seen:
                    seen.add(key)
                    targets.append(socket)
    return sum(untangle_links(tree, s) for s in targets)


def set_collapse(nodes, collapse):
    """collapse True/False -> thu nho / mo lai. None -> giu nguyen."""
    if collapse is None:
        return 0
    changed = 0
    for node in nodes:
        if node.hide != collapse:
            node.hide = collapse
            changed += 1
    return changed


def arrange_nodes(nodes, axis='COLUMN', gap=10.0, order='POSITION', ui_scale=1.0):
    """Dan node ve mot cot (hoac mot hang) thang, cach deu. Tra ve so node da doi cho.

    Node nam trong frame duoc dan RIENG theo tung frame: `node.location` cua
    chung tinh theo goc cua frame, tron chung voi node ngoai frame se nhay lung
    tung. Node khong o frame nao cung la mot nhom.
    """
    buckets = {}
    for node in nodes:
        buckets.setdefault(node.parent, []).append(node)

    if order == 'NAME':
        def key(n):
            return ((n.label or n.name).lower(), n.name.lower())
    elif axis == 'ROW':
        def key(n):
            return (n.location.x, -n.location.y)
    else:
        def key(n):
            return (-n.location.y, n.location.x)

    moved = 0
    for group in buckets.values():
        group.sort(key=key)
        # Neo vao goc trai-tren cua chinh nhom do, de no khong nhay di cho khac.
        x0 = min(n.location.x for n in group)
        y0 = max(n.location.y for n in group)

        cursor = 0.0
        for node in group:
            if axis == 'ROW':
                target = (x0 + cursor, y0)
                cursor += node.width + gap
            else:
                target = (x0, y0 - cursor)
                cursor += _node_height(node, ui_scale) + gap

            if abs(node.location.x - target[0]) > 1e-4 or \
               abs(node.location.y - target[1]) > 1e-4:
                moved += 1
            node.location = target

    return moved


def _arrange_targets(tree, scope):
    """Node se bi sap xep. Bo qua frame va reroute (xem SKIP_TYPES)."""
    if scope == 'SELECTED':
        pool = [n for n in tree.nodes if n.select]
    else:
        pool = [n for n in tree.nodes if n.bl_idname in INFO_NODES]
    return [n for n in pool if n.bl_idname not in SKIP_TYPES]


class EZG_GN_OT_arrange_nodes(bpy.types.Operator):
    """Dan node thang hang va thu nho lai cho gon"""

    bl_idname = "ezg_gn.arrange_nodes"
    bl_label = "Thẳng hàng + thu nhỏ"
    bl_options = {'REGISTER', 'UNDO'}

    scope: bpy.props.EnumProperty(
        name="Phạm vi",
        items=[
            ('INFO', "Node Info", "Moi node Object Info / Collection Info trong cay dang mo"),
            ('SELECTED', "Đang chọn", "Chi cac node dang chon, thuoc loai nao cung duoc"),
        ],
        default='INFO',
    )
    collapse: bpy.props.EnumProperty(
        name="Thu nhỏ",
        items=[
            ('COLLAPSE', "Thu nhỏ", "Gap node lai thanh mot vach nho"),
            ('EXPAND', "Mở ra", "Mo lai node dang bi gap"),
            ('KEEP', "Giữ nguyên", "Khong dong den trang thai gap/mo"),
        ],
        default='COLLAPSE',
    )
    axis: bpy.props.EnumProperty(
        name="Hướng",
        items=[
            ('COLUMN', "Cột dọc", "Xep chong tu tren xuong, thang le trai"),
            ('ROW', "Hàng ngang", "Xep tu trai sang phai, thang le tren"),
        ],
        default='COLUMN',
    )
    order: bpy.props.EnumProperty(
        name="Thứ tự",
        items=[
            ('POSITION', "Theo vị trí", "Giu nguyen thu tu dang thay tren man hinh"),
            ('NAME', "Theo nhãn A→Z", "Sap theo nhan node, xep chua co nhan theo ten node"),
        ],
        default='POSITION',
    )
    gap: bpy.props.FloatProperty(
        name="Khoảng cách",
        default=10.0, min=0.0, soft_max=120.0,
        description="Khoang ho giua hai node lien nhau",
    )
    untangle: bpy.props.BoolProperty(
        name="Gỡ xoắn dây",
        default=True,
        description=("Cam lai day vao Join Geometry theo dung thu tu tren xuong, "
                     "de chung chay song song thay vi cheo qua nhau"),
    )

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None

    def execute(self, context):
        tree = _edit_tree(context)
        if tree is None:
            self.report({'WARNING'}, "Không có cây Geometry Nodes nào đang mở.")
            return {'CANCELLED'}

        targets = _arrange_targets(tree, self.scope)
        if not targets:
            if self.scope == 'SELECTED':
                self.report({'WARNING'}, "Chưa chọn node nào.")
            else:
                self.report({'WARNING'}, "Cây này không có node Info nào.")
            return {'CANCELLED'}

        collapse = {'COLLAPSE': True, 'EXPAND': False}.get(self.collapse)
        set_collapse(targets, collapse)

        ui_scale = context.preferences.system.ui_scale
        moved = arrange_nodes(targets, axis=self.axis, gap=self.gap,
                              order=self.order, ui_scale=ui_scale)

        # Dan node xong ma khong cam lai day thi day van theo cho cam cu -> xoan
        # het vao nhau. Hai viec nay luon phai di cung mot luot.
        rewired = untangle_downstream(tree, targets) if self.untangle else 0

        msg = "Đã sắp xếp %d node (%d node đổi chỗ)." % (len(targets), moved)
        if rewired:
            msg += " Cắm lại %d dây cho hết xoắn." % rewired
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# --- Them object dang chon vao cay -------------------------------------------
#
# Loai object KHONG mang hinh khoi. Cam mot cai vao Join Geometry thi Join nhan
# duoc dung so khong, chi to them mot node vo nghia trong cay.
NO_GEOMETRY_TYPES = {'CAMERA', 'LIGHT', 'SPEAKER', 'LIGHT_PROBE', 'EMPTY', 'ARMATURE'}

# Khoang cach giua cot Object Info -> Join -> Group Output khi phai tu dat cho.
COLUMN_GAP = 260.0


def _tree_hosts(tree):
    """Object dang dung chinh cay nay lam modifier.

    Tro mot node Object Info vao object dang chay cay do la tu tham chieu chinh
    minh: Blender phat hien vong phu thuoc va cho ca modifier chet, khong ra
    hinh gi. Nen nhung object nay luon bi loai khoi danh sach them vao.
    """
    hosts = set()
    for ob in bpy.data.objects:
        for mod in ob.modifiers:
            if mod.type == 'NODES' and mod.node_group is tree:
                hosts.add(ob)
    return hosts


def _find_group_output(tree):
    outs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
    for node in outs:
        if node.is_active_output:
            return node
    return outs[0] if outs else None


def _geometry_socket(sockets):
    """Socket hinh khoi that su.

    Bo qua NodeSocketVirtual (o cuoi Group Output): noi day vao no bang Python
    khong bao loi nhung cung khong tao ra socket that — day di vao hu vo.
    """
    for socket in sockets:
        if socket.type == 'GEOMETRY':
            return socket
    return None


def drop_group_input_links(tree, join):
    """Go day di thang tu Group Input vao Join. Tra ve so day da go.

    Group Input mang hinh khoi cua chinh object dang deo modifier. Gan nhu luon
    la mot cube placeholder, va gop no vao Join chi to them mot khoi thua nam
    giua canh. Nen mac dinh la khong noi.
    """
    dead = [l for s in join.inputs for l in s.links
            if l.from_node.bl_idname == "NodeGroupInput"]
    for link in dead:
        tree.links.remove(link)
    return len(dead)


def ensure_join(tree, keep_group_input=False):
    """Tra ve (join, da_tao_moi, da_noi_ra_output).

    Dung lai Join Geometry dang cam vao Group Output neu co san. Neu Group
    Output dang nhan day tu mot node KHAC thi node do duoc cam vao Join chu
    khong bi thay the — them object khong duoc lam bien mat mach dang co.
    Rieng Group Input thi khong, xem drop_group_input_links.
    """
    out = _find_group_output(tree)
    sock = _geometry_socket(out.inputs) if out else None

    if sock is not None and sock.is_linked:
        src = sock.links[0].from_node
        if src.bl_idname == "GeometryNodeJoinGeometry":
            if not keep_group_input:
                drop_group_input_links(tree, src)
            return src, False, True

    join = tree.nodes.new("GeometryNodeJoinGeometry")
    if out is not None:
        join.location = (out.location.x - COLUMN_GAP, out.location.y)

    if sock is None:
        return join, True, False

    if sock.is_linked:
        old = sock.links[0]
        if keep_group_input or old.from_node.bl_idname != "NodeGroupInput":
            tree.links.new(old.from_socket, join.inputs[0])
    tree.links.new(join.outputs[0], sock)
    return join, True, True


def nodes_feeding(join):
    """Cac node Info dang cam vao Join nay (khong lap, giu thu tu gap duoc)."""
    found = []
    seen = set()
    for socket in join.inputs:
        for link in socket.links:
            node = link.from_node
            if node.bl_idname in INFO_NODES and node.as_pointer() not in seen:
                seen.add(node.as_pointer())
                found.append(node)
    return found


def objects_feeding(join):
    """{object: node} — de biet object nao da co node roi, khoi tao trung."""
    existing = {}
    for node in nodes_feeding(join):
        data = _info_datablock(node)
        if data is not None:
            existing.setdefault(data, node)
    return existing


def add_objects_to_join(tree, objects, join, relative=True, as_instance=False):
    """Tao mot node Object Info cho moi object roi cam vao Join. Tra ve list node."""
    made = []
    for ob in objects:
        node = tree.nodes.new("GeometryNodeObjectInfo")
        node.inputs["Object"].default_value = ob
        node.inputs["As Instance"].default_value = as_instance
        node.transform_space = 'RELATIVE' if relative else 'ORIGINAL'
        node.label = ob.name
        node.location = (join.location.x - COLUMN_GAP, join.location.y)
        tree.links.new(node.outputs["Geometry"], join.inputs[0])
        made.append(node)
    return made


class EZG_GN_OT_add_selected_objects(bpy.types.Operator):
    """Tạo node Object Info cho các object đang chọn rồi nối hết vào một Join Geometry"""

    bl_idname = "ezg_gn.add_selected_objects"
    bl_label = "Thêm object đang chọn"
    bl_options = {'REGISTER', 'UNDO'}

    relative: bpy.props.BoolProperty(
        name="Giữ đúng vị trí ngoài scene",
        default=True,
        description=("Transform Space = Relative: object hien ra dung cho no dang dung. "
                     "Tat = Original: lay hinh o goc toa do rieng cua no"),
    )
    as_instance: bpy.props.BoolProperty(
        name="Lấy dạng instance",
        default=False,
        description="As Instance: nhe hon nhieu khi cung mot hinh lap lai nhieu lan",
    )
    collapse: bpy.props.BoolProperty(
        name="Thu nhỏ node",
        default=True,
        description="Gap cac node vua tao lai cho gon",
    )
    keep_group_input: bpy.props.BoolProperty(
        name="Giữ dây Group Input",
        default=False,
        description=("Gop ca hinh khoi cua chinh object dang deo modifier vao Join. "
                     "Tat: chi gop cac object them vao"),
    )

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None

    def execute(self, context):
        tree = _edit_tree(context)
        if tree is None:
            self.report({'WARNING'}, "Không có cây Geometry Nodes nào đang mở.")
            return {'CANCELLED'}

        hosts = _tree_hosts(tree)
        selected = list(context.view_layer.objects.selected)

        # Xep theo ten cho ket qua on dinh: Blender khong luu thu tu bam chuot.
        wanted = sorted(
            (ob for ob in selected
             if ob not in hosts and ob.type not in NO_GEOMETRY_TYPES),
            key=lambda o: o.name.lower(),
        )
        n_host = sum(1 for ob in selected if ob in hosts)
        n_skip = sum(1 for ob in selected
                     if ob not in hosts and ob.type in NO_GEOMETRY_TYPES)

        if not wanted:
            if n_host and len(selected) == n_host:
                self.report({'WARNING'},
                            "Chỉ chọn mỗi object đang mang modifier — "
                            "chọn thêm object nguồn.")
            elif n_skip:
                self.report({'WARNING'}, "Các object đang chọn đều không có hình khối.")
            else:
                self.report({'WARNING'}, "Chưa chọn object nào.")
            return {'CANCELLED'}

        join, join_created, wired = ensure_join(tree, self.keep_group_input)

        # Bam nut hai lan khong duoc tao ra hai node cho cung mot object.
        existing = objects_feeding(join)
        fresh = [ob for ob in wanted if ob not in existing]
        n_dup = len(wanted) - len(fresh)

        made = add_objects_to_join(tree, fresh, join,
                                   relative=self.relative,
                                   as_instance=self.as_instance)

        # Dat nhan + dan thang ca cot: node moi va node da co san deu cam vao
        # cung mot Join nen chung la mot chong, sap chung voi nhau moi gon.
        column = nodes_feeding(join)
        set_collapse(column, True if self.collapse else None)
        arrange_nodes(column, axis='COLUMN', gap=10.0, order='NAME',
                      ui_scale=context.preferences.system.ui_scale)
        # Cam lai TOAN BO day vao Join, khong chi day moi: day cu van theo cho
        # cam cu nen chi cam lai mot phan la van xoan.
        untangle_links(tree, join.inputs[0])

        for node in tree.nodes:
            node.select = node in made
        if made:
            tree.nodes.active = made[0]

        notes = []
        if n_dup:
            notes.append("%d object đã có node sẵn" % n_dup)
        if n_host:
            notes.append("bỏ qua %d object đang mang modifier" % n_host)
        if n_skip:
            notes.append("bỏ qua %d object không có hình khối" % n_skip)
        if join_created and not wired:
            notes.append("Join CHƯA nối ra Group Output — cây này không có "
                         "đầu ra hình khối")

        msg = "Đã thêm %d object vào Join." % len(made)
        if notes:
            msg += " (" + "; ".join(notes) + ")"
        self.report({'WARNING'} if (join_created and not wired) else {'INFO'}, msg)
        return {'FINISHED'}


# --- Transform Space ----------------------------------------------------------
#
# O chon Transform Space nam trong THAN node, ma addon nay thu nho node lai cho
# gon — thu nho xong thi khong con thay o do nua. Nen phai co cho bat tat o
# ngoai panel, khong thi doi y roi la phai mo tung node ra.
TRANSFORM_SPACES = (
    ('RELATIVE', "Relative",
     "Object hien ra dung cho no dang dung ngoai scene"),
    ('ORIGINAL', "Original",
     "Lay hinh o goc toa do rieng cua object, bo qua vi tri ngoai scene"),
)


def info_nodes_in(tree, selected_only=False):
    """Node Info trong cay. selected_only -> chi nhung cai dang chon."""
    return [n for n in tree.nodes
            if n.bl_idname in INFO_NODES and (n.select or not selected_only)]


def set_transform_space(nodes, space):
    """Doi Transform Space. Tra ve so node thuc su doi."""
    changed = 0
    for node in nodes:
        if node.transform_space != space:
            node.transform_space = space
            changed += 1
    return changed


class EZG_GN_OT_set_transform_space(bpy.types.Operator):
    """Đổi Transform Space của node Info hàng loạt"""

    bl_idname = "ezg_gn.set_transform_space"
    bl_label = "Transform Space"
    bl_options = {'REGISTER', 'UNDO'}

    space: bpy.props.EnumProperty(
        name="Transform Space", items=TRANSFORM_SPACES, default='RELATIVE',
    )
    selected_only: bpy.props.BoolProperty(
        name="Chỉ node đang chọn", default=False,
    )

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None

    @classmethod
    def description(cls, context, properties):
        for ident, label, note in TRANSFORM_SPACES:
            if ident == properties.space:
                return "%s — %s" % (label, note)
        return ""

    def execute(self, context):
        tree = _edit_tree(context)
        nodes = info_nodes_in(tree, self.selected_only)
        if not nodes:
            self.report({'WARNING'}, "Không có node Info nào.")
            return {'CANCELLED'}

        changed = set_transform_space(nodes, self.space)
        self.report({'INFO'}, "Đã đổi %d/%d node sang %s."
                    % (changed, len(nodes), self.space.title()))
        return {'FINISHED'}


# --- Chon object tu node -----------------------------------------------------
#
# Blender KHONG phat su kien nao khi doi node dang chon, nen khong co cach nao
# "bat" cu click de dong bo ngay. Hai duong di:
#
#   nut bam    chac chan, khong ton gi khi khong dung
#   tu dong    mot timer nhe cu 0.25s doc lai node dang chon; chi chay khi bat
#
# Timer chi doc du lieu roi doi selection — dung cach ma ezg_deco_namer da lam.
SYNC_INTERVAL = 0.25

_sync_key = None      # node da dong bo lan cuoi, de khong lam di lam lai


def objects_of_nodes(nodes):
    """Object cac node Info dang tro toi. Collection Info -> moi object trong nhom."""
    found = []
    seen = set()
    for node in nodes:
        data = _info_datablock(node)
        if data is None:
            continue
        members = data.objects if isinstance(data, bpy.types.Collection) else [data]
        for ob in members:
            if ob.name not in seen:
                seen.add(ob.name)
                found.append(ob)
    return found


def select_objects(view_layer, objects):
    """Chon dung nhung object nay. Tra ve so object chon duoc.

    Object nam trong collection bi loai khoi view layer thi khong chon duoc —
    bo qua chu khong bao loi, vi node van hop le va van ra hinh binh thuong.
    """
    targets = [view_layer.objects.get(ob.name) for ob in objects]
    targets = [ob for ob in targets if ob is not None]
    if not targets:
        return 0

    for ob in view_layer.objects:
        ob.select_set(False)

    picked = 0
    for ob in targets:
        try:
            ob.select_set(True)
        except RuntimeError:
            continue
        picked += 1

    if picked:
        view_layer.objects.active = targets[-1]
    return picked


def selected_info_nodes(tree):
    """Node Info dang chon, node active xep CUOI de no thanh object active."""
    nodes = [n for n in tree.nodes if n.select and n.bl_idname in INFO_NODES]
    active = tree.nodes.active
    if active is not None and active.bl_idname in INFO_NODES:
        nodes = [n for n in nodes if n != active] + [active]
    return nodes


def _node_editors():
    """(window, tree) cua moi Geometry Node Editor dang mo."""
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        screen = getattr(win, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'NODE_EDITOR':
                continue
            space = area.spaces.active
            if getattr(space, "tree_type", "") != 'GeometryNodeTree':
                continue
            tree = getattr(space, "edit_tree", None)
            if tree is not None:
                yield win, tree


def _sync_timer():
    """Tra ve None de tu huy khi tat cong tac hoac khi addon bi go."""
    global _sync_key
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None or not getattr(wm, "ezg_gn_sync_select", False):
        _sync_key = None
        return None

    for win, tree in _node_editors():
        nodes = selected_info_nodes(tree)
        if not nodes:
            continue
        key = (tree.name, tuple(n.name for n in nodes))
        if key == _sync_key:
            continue
        _sync_key = key
        select_objects(win.view_layer, objects_of_nodes(nodes))
        break

    return SYNC_INTERVAL


def _on_sync_toggled(self, context):
    global _sync_key
    _sync_key = None
    if self.ezg_gn_sync_select and not bpy.app.timers.is_registered(_sync_timer):
        bpy.app.timers.register(_sync_timer, first_interval=0.0)


class EZG_GN_OT_select_objects(bpy.types.Operator):
    """Chọn object mà các node Info đang chọn trỏ tới, ngoài viewport và outliner"""

    bl_idname = "ezg_gn.select_objects"
    bl_label = "Chọn object của node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None

    def execute(self, context):
        tree = _edit_tree(context)
        nodes = selected_info_nodes(tree)
        if not nodes:
            self.report({'WARNING'}, "Chưa chọn node Info nào.")
            return {'CANCELLED'}

        objects = objects_of_nodes(nodes)
        if not objects:
            self.report({'WARNING'}, "Các node đang chọn chưa trỏ tới object nào.")
            return {'CANCELLED'}

        picked = select_objects(context.view_layer, objects)
        if not picked:
            self.report({'WARNING'},
                        "Object của node không có trong view layer này "
                        "(collection bị loại trừ?).")
            return {'CANCELLED'}

        msg = "Đã chọn %d object." % picked
        if picked < len(objects):
            msg += " %d object không có trong view layer." % (len(objects) - picked)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# --- Don node thua -----------------------------------------------------------
#
# Day la chuc nang DUY NHAT trong addon co the lam mat viec dang lam, nen no
# khong bao gio chay thang: bam nut la hien bang liet ke dung nhung node sap bi
# xoa va ly do, xac nhan roi moi xoa.

# Ly do mot node bi coi la thua. Thu tu quan trong: mot node vua trong vua khong
# noi day thi bao ca hai, con "trong nhung DANG noi day" la truong hop can canh
# vi xoa no la dut mach cay.
REASON_EMPTY = "trống"
REASON_UNLINKED = "không nối"
REASON_EMPTY_LINKED = "trống, nhưng đang nối dây"


def node_waste_reason(node, remove_empty=True, remove_unlinked=True):
    """Ly do node nay bi coi la thua, hoac None neu no van dang co ich.

    "Khong noi" xet o dau RA: node Info sinh du lieu cho phan sau cua cay, day
    vao dau vao cua no (vd Object tro tu Group Input) khong lam no co ich neu
    khong ai lay ket qua.
    """
    if node.bl_idname not in INFO_NODES:
        return None

    is_empty = _info_datablock(node) is None
    is_unlinked = not any(s.is_linked for s in node.outputs)

    reasons = []
    if remove_empty and is_empty:
        reasons.append(REASON_EMPTY)
    if remove_unlinked and is_unlinked:
        reasons.append(REASON_UNLINKED)

    if not reasons:
        return None
    if is_empty and not is_unlinked:
        # Xoa node nay se dut mot soi day dang co that -> phai noi ro.
        return REASON_EMPTY_LINKED
    return ", ".join(reasons)


def find_waste_nodes(tree, remove_empty=True, remove_unlinked=True,
                     selected_only=False):
    """Danh sach (node, ly do) cac node Info thua trong MOT cay."""
    found = []
    for node in tree.nodes:
        if selected_only and not node.select:
            continue
        reason = node_waste_reason(node, remove_empty, remove_unlinked)
        if reason is not None:
            found.append((node, reason))
    return found


def remove_nodes(tree, nodes):
    """Xoa cac node khoi cay. Tra ve so node da xoa."""
    count = 0
    for node in list(nodes):
        tree.nodes.remove(node)
        count += 1
    return count


def _node_title(node):
    return node.label or node.name


class EZG_GN_OT_clean_info_nodes(bpy.types.Operator):
    """Xoá các node Info không trỏ tới object nào, hoặc không nối vào đâu cả"""

    bl_idname = "ezg_gn.clean_info_nodes"
    bl_label = "Dọn node thừa"
    bl_options = {'REGISTER', 'UNDO'}

    remove_empty: bpy.props.BoolProperty(
        name="Không chứa object",
        default=True,
        description="Node Info chua tro toi object / collection nao",
    )
    remove_unlinked: bpy.props.BoolProperty(
        name="Không nối vào đâu",
        default=True,
        description="Node Info khong co day nao di ra tu dau ra cua no",
    )
    selected_only: bpy.props.BoolProperty(
        name="Chỉ node đang chọn",
        default=False,
        description="Chi xet cac node dang chon, thay vi ca cay dang mo",
    )

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None

    def _found(self, context):
        tree = _edit_tree(context)
        if tree is None:
            return []
        return find_waste_nodes(tree, self.remove_empty, self.remove_unlinked,
                                self.selected_only)

    def invoke(self, context, event):
        if not (self.remove_empty or self.remove_unlinked):
            self.report({'WARNING'}, "Chưa chọn điều kiện nào để dọn.")
            return {'CANCELLED'}
        if not self._found(context):
            self.report({'INFO'}, "Không có node Info nào thừa.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.prop(self, "remove_empty")
        col.prop(self, "remove_unlinked")
        col.prop(self, "selected_only")

        layout.separator()

        found = self._found(context)
        if not found:
            layout.label(text="Không còn node nào khớp điều kiện.", icon='CHECKMARK')
            return

        layout.label(text="Sẽ xoá %d node:" % len(found), icon='TRASH')

        box = layout.box()
        col = box.column(align=True)
        SHOWN = 12
        for node, reason in found[:SHOWN]:
            icon = 'ERROR' if reason == REASON_EMPTY_LINKED else 'DOT'
            col.label(text="%s  —  %s" % (_node_title(node), reason), icon=icon)
        if len(found) > SHOWN:
            col.label(text="… và %d node nữa" % (len(found) - SHOWN))

        if any(r == REASON_EMPTY_LINKED for _, r in found):
            layout.label(text="Node đánh dấu đỏ đang có dây — xoá là đứt mạch.",
                         icon='ERROR')

    def execute(self, context):
        tree = _edit_tree(context)
        if tree is None:
            self.report({'WARNING'}, "Không có cây Geometry Nodes nào đang mở.")
            return {'CANCELLED'}

        found = self._found(context)
        if not found:
            self.report({'INFO'}, "Không có node Info nào thừa.")
            return {'CANCELLED'}

        cut_links = sum(1 for _, r in found if r == REASON_EMPTY_LINKED)
        removed = remove_nodes(tree, [n for n, _ in found])

        msg = "Đã xoá %d node thừa." % removed
        if cut_links:
            msg += " %d node trong đó đang có dây — Ctrl+Z nếu cần." % cut_links
        self.report({'WARNING'} if cut_links else {'INFO'}, msg)
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

        # Object se duoc them vao: dem san de nut noi ro no sap lam gi.
        hosts = _tree_hosts(tree)
        selected = list(context.view_layer.objects.selected)
        addable = [ob for ob in selected
                   if ob not in hosts and ob.type not in NO_GEOMETRY_TYPES]

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.enabled = bool(addable)
        col.operator(EZG_GN_OT_add_selected_objects.bl_idname, icon='ADD')

        if addable:
            layout.label(text="Sẽ thêm: %d object" % len(addable),
                         icon='OUTLINER_OB_MESH')
        elif selected:
            # Chon moi object dang mang modifier la truong hop rat de gap:
            # no la object active, sang mau vang, nen nguoi dung tuong da chon du.
            layout.label(text="Object đang chọn không thêm được.", icon='INFO')
        else:
            layout.label(text="Chưa chọn object nào ngoài viewport.", icon='INFO')

        layout.separator()

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator(EZG_GN_OT_label_info_nodes.bl_idname,
                     icon='SORTALPHA').whole_file = False

        row = layout.row(align=True)
        row.operator(EZG_GN_OT_label_info_nodes.bl_idname,
                     text="Cả file", icon='FILE_BLEND').whole_file = True

        layout.separator()

        n_info_sel = len(selected_info_nodes(tree))

        # O chon Transform Space nam trong than node, thu nho node lai la khong
        # con thay. Bay ra day de doi duoc ma khong phai mo tung node.
        ts_nodes = info_nodes_in(tree, bool(n_info_sel))
        if ts_nodes:
            layout.label(text="Transform Space — %d node%s"
                              % (len(ts_nodes), " đang chọn" if n_info_sel else ""))
            spaces = {n.transform_space for n in ts_nodes}
            row = layout.row(align=True)
            for ident, label, _note in TRANSFORM_SPACES:
                op = row.operator(EZG_GN_OT_set_transform_space.bl_idname,
                                  text=label, depress=(spaces == {ident}))
                op.space = ident
                op.selected_only = bool(n_info_sel)

        layout.separator()

        row = layout.row(align=True)
        row.enabled = bool(n_info_sel)
        row.operator(EZG_GN_OT_select_objects.bl_idname,
                     text="Chọn object của %d node" % n_info_sel
                          if n_info_sel else "Chọn object của node",
                     icon='RESTRICT_SELECT_OFF')
        layout.prop(context.window_manager, "ezg_gn_sync_select", toggle=True,
                    icon='UV_SYNC_SELECT')

        layout.separator()

        n_sel = len(_arrange_targets(tree, 'SELECTED'))
        scope = 'SELECTED' if n_sel else 'INFO'

        col = layout.column(align=True)
        col.scale_y = 1.4
        op = col.operator(EZG_GN_OT_arrange_nodes.bl_idname, icon='ALIGN_JUSTIFY')
        op.scope = scope
        op.collapse = 'COLLAPSE'

        row = layout.row(align=True)
        op = row.operator(EZG_GN_OT_arrange_nodes.bl_idname,
                          text="Mở ra", icon='FULLSCREEN_ENTER')
        op.scope = scope
        op.collapse = 'EXPAND'
        op = row.operator(EZG_GN_OT_arrange_nodes.bl_idname,
                          text="Theo nhãn A→Z", icon='SORTALPHA')
        op.scope = scope
        op.collapse = 'KEEP'
        op.order = 'NAME'

        # Nut chay tren node dang chon neu co, khong thi chay tren moi node Info.
        # Noi ro ra vi hai truong hop cho ket qua rat khac nhau.
        n_info = sum(1 for node in tree.nodes if node.bl_idname in INFO_NODES)
        if n_sel:
            layout.label(text="Sẽ sắp xếp: %d node đang chọn" % n_sel,
                         icon='RESTRICT_SELECT_OFF')
        else:
            layout.label(text="Sẽ sắp xếp: %d node Info trong cây" % n_info,
                         icon='NODE')

        n_all = sum(
            1 for t in _walk_trees(tree) for node in t.nodes
            if node.bl_idname in INFO_NODES
        )
        if n_all != n_info:
            layout.label(text="Kể cả group lồng: %d node Info" % n_all, icon='NODETREE')

        layout.separator()

        # Dem san so node thua ngay tren panel: nut xoa ma khong noi truoc no se
        # xoa bao nhieu thi khong ai dam bam.
        waste = find_waste_nodes(tree, selected_only=bool(n_sel))

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.enabled = bool(waste)
        op = col.operator(EZG_GN_OT_clean_info_nodes.bl_idname, icon='TRASH')
        op.selected_only = bool(n_sel)

        if waste:
            layout.label(text="Thừa: %d node (bấm để xem trước)" % len(waste),
                         icon='INFO')
        else:
            layout.label(text="Không có node Info nào thừa.", icon='CHECKMARK')


classes = (
    EZG_GN_OT_add_selected_objects,
    EZG_GN_OT_label_info_nodes,
    EZG_GN_OT_arrange_nodes,
    EZG_GN_OT_set_transform_space,
    EZG_GN_OT_select_objects,
    EZG_GN_OT_clean_info_nodes,
    EZG_GN_PT_info_namer,
)


def _stop_sync():
    """Tat timer dong bo. Bo sot cho nay la timer con chay sau khi go addon,
    goi vao ham da bien mat -> Blender bao loi moi 0.25 giay."""
    global _sync_key
    _sync_key = None
    try:
        if bpy.app.timers.is_registered(_sync_timer):
            bpy.app.timers.unregister(_sync_timer)
    except Exception:
        pass


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.WindowManager.ezg_gn_sync_select = bpy.props.BoolProperty(
        name="Tự chọn theo node",
        default=False,
        update=_on_sync_toggled,
        description=("Chon node Info nao thi object cua no tu sang len ngoai viewport. "
                     "Blender khong bao khi doi node dang chon nen cho nay phai doc "
                     "lai moi 0.25 giay — tat di khi khong dung"),
    )


def unregister():
    _stop_sync()

    wm = getattr(bpy.context, "window_manager", None)
    if wm is not None and hasattr(wm, "ezg_gn_sync_select"):
        try:
            wm.ezg_gn_sync_select = False
        except Exception:
            pass
    if hasattr(bpy.types.WindowManager, "ezg_gn_sync_select"):
        del bpy.types.WindowManager.ezg_gn_sync_select

    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
