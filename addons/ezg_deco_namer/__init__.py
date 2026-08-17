import bpy


# ==== 5 rule tien to co dinh — sua danh sach nay neu can them/bot ====
PREFIXES = ["deco_00_", "deco_01_", "deco_02_", "deco_03_", "deco_04_"]

# Chu thich hien ngay duoi moi nut rule (kich thuoc tham chieu so voi nguoi).
# Key phai trung voi mot phan tu trong PREFIXES.
NOTES = {
    "deco_00_": "cao hơn người",
    "deco_01_": "ngang người",
    "deco_02_": "thấp hơn người",
    "deco_03_": "lớn hơn nhiều so với người",
    "deco_04_": "trên mặt nước",
}

# Chieu cao 2 dong trong 1 "the nut" (tang len neu muon nut to hon)
BUTTON_SCALE = 1.7   # dong tren: prefix
NOTE_SCALE = 1.1     # dong duoi: chu thich


# ==== Trang thai hover ====
_hover_prefix = None       # rule dang hover (set trong description())
_applied_prefix = None     # rule da ap dung selection gan nhat
_apply_pending = False     # da hen timer ap dung chua


def index_to_letters(index):
    """0 -> a, 25 -> z, 26 -> aa, 27 -> ab ... (kieu ten cot spreadsheet)."""
    result = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        result = chr(ord('a') + rem) + result
    return result


def _selected_meshes(context):
    objs = getattr(context, "selected_objects", None) or []
    return [o for o in objs if o.type == 'MESH']


def _occupied_names(objs):
    """Ten dang bi object KHAC (ngoai nhom dang chon) chiem giu.
    Ten object trong Blender la duy nhat toan file nen chi can so ten."""
    sel = set(o.name for o in objs)
    return set(o.name for o in bpy.data.objects) - sel


def _compute_targets(prefix, count, occupied):
    """Sinh 'count' ten dich cho 'prefix', TU DONG NHAY QUA cac hau to da bi
    chiem (trong 'occupied'). Vd occupied co 'deco_02_b', count=3
    -> [deco_02_a, deco_02_c, deco_02_d]."""
    taken = set(occupied)
    targets = []
    i = 0
    for _ in range(count):
        while (prefix + index_to_letters(i)) in taken:
            i += 1
        name = prefix + index_to_letters(i)
        targets.append(name)
        taken.add(name)  # danh dau de mesh ke tiep khong dung lai
        i += 1
    return targets


# ==== Hover -> chon (sang len) nhom mesh cung ten ====
def _apply_hover_selection():
    """Chay qua bpy.app.timers (context an toan) nen duoc phep sua selection."""
    global _apply_pending, _applied_prefix
    _apply_pending = False
    p = _hover_prefix
    if p == _applied_prefix:
        return None
    _applied_prefix = p
    try:
        ctx = bpy.context
        vl = getattr(ctx, "view_layer", None)
        if vl is None:
            return None
        for o in vl.objects:
            o.select_set(False)
        first = None
        if p:
            for o in vl.objects:
                if o.type == 'MESH' and o.name.startswith(p):
                    o.select_set(True)
                    if first is None:
                        first = o
            if first is not None:
                vl.objects.active = first
        for w in ctx.window_manager.windows:
            for a in w.screen.areas:
                if a.type in {'VIEW_3D', 'OUTLINER'}:
                    a.tag_redraw()
    except Exception:
        pass
    return None  # one-shot: tra None de timer tu huy


def _schedule_hover_apply(prefix):
    """Goi tu description() (luc hover). Chi hen timer, khong ghi data tai day."""
    global _hover_prefix, _apply_pending
    _hover_prefix = prefix
    if _apply_pending:
        return
    _apply_pending = True
    try:
        bpy.app.timers.register(_apply_hover_selection, first_interval=0.0)
    except Exception:
        _apply_pending = False


class DECO_OT_rename_selected(bpy.types.Operator):
    """Doi ten cac mesh dang chon theo tien to, TU DONG NHAY QUA cac hau to
da bi mesh khac chiem. Vd da co deco_02_b -> them 3 mesh se thanh a, c, d."""
    bl_idname = "deco.rename_selected"
    bl_label = "Doi ten mesh theo rule"
    bl_options = {'REGISTER', 'UNDO'}

    prefix: bpy.props.StringProperty(name="Tien to", default=PREFIXES[0])

    @classmethod
    def description(cls, context, properties):
        # Duoc goi luc hover -> hen chon nhom cung ten (sang len trong outliner/viewport)
        _schedule_hover_apply(properties.prefix)
        p = properties.prefix
        return ("Hover: sang len (chon) nhom '%s*'.\n"
                "Bam: doi ten cac mesh DANG CHON theo rule nay (nhay qua slot da co)." % p)

    @classmethod
    def poll(cls, context):
        return len(_selected_meshes(context)) > 0

    def execute(self, context):
        objs = _selected_meshes(context)
        if not objs:
            self.report({'WARNING'}, "Chua chon mesh nao.")
            return {'CANCELLED'}

        # Sap theo ten hien tai (khong phan biet hoa/thuong) de gan chu cai on dinh
        objs.sort(key=lambda o: o.name.lower())

        # Tinh ten dich: tu dong nhay qua cac hau to da bi mesh KHAC chiem
        occupied = _occupied_names(objs)
        targets = _compute_targets(self.prefix, len(objs), occupied)

        # Pass 1: dat ten tam duy nhat -> tranh dung ten khi hoan doi trong nhom chon
        for i, o in enumerate(objs):
            o.name = "__deco_tmp_%d__" % i
        # Pass 2: dat ten cuoi cung theo danh sach targets
        for o, target in zip(objs, targets):
            o.name = target

        # Reset de lan hover sau se chon lai dung (nhom vua doi ten)
        global _applied_prefix
        _applied_prefix = None

        shown = ", ".join(targets[:6]) + (" ..." if len(targets) > 6 else "")
        bad = [o.name for o, t in zip(objs, targets) if o.name != t]
        if bad:
            self.report({'WARNING'}, "Mot so ten bi Blender doi khac du kien: %s" % ", ".join(bad))
        else:
            self.report({'INFO'}, "Da doi ten %d mesh -> %s" % (len(objs), shown))
        return {'FINISHED'}


class DECO_PT_panel(bpy.types.Panel):
    bl_label = "Deco Namer"
    bl_idname = "DECO_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Deco"

    def draw(self, context):
        layout = self.layout
        sel = _selected_meshes(context)
        n = len(sel)

        box = layout.box()
        box.label(text="Da chon: %d mesh" % n, icon='OUTLINER_OB_MESH')

        occupied = _occupied_names(sel) if n else set()
        for p in PREFIXES:
            top_text = p
            if n:
                letters = [t[len(p):] for t in _compute_targets(p, n, occupied)]
                shown = ", ".join(letters[:5]) + (" ..." if len(letters) > 5 else "")
                top_text = "%s  ( %s )" % (p, shown)

            note = NOTES.get(p, "")

            # Moi rule = 1 "the nut" lien khoi (align=True): dong tren = prefix,
            # dong duoi = chu thich NAM NGAY TRONG nut. Bam dong nao cung doi ten.
            block = layout.column(align=True)

            top = block.row(align=True)
            top.scale_y = BUTTON_SCALE
            top.operator(DECO_OT_rename_selected.bl_idname, text=top_text).prefix = p

            if note:
                bot = block.row(align=True)
                bot.scale_y = NOTE_SCALE
                bot.operator(DECO_OT_rename_selected.bl_idname, text=note).prefix = p

            layout.separator(factor=0.4)


classes = (DECO_OT_rename_selected, DECO_PT_panel)


def _cleanup_legacy():
    """Don artifact cua ban cu (khung cam GPU + toggle) neu con sot lai."""
    prev = bpy.app.driver_namespace.pop("_deco_draw_handle", None)
    if prev is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(prev, 'WINDOW')
        except Exception:
            pass
    if hasattr(bpy.types.WindowManager, "deco_hover_highlight"):
        try:
            del bpy.types.WindowManager.deco_hover_highlight
        except Exception:
            pass


def register():
    _cleanup_legacy()
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    global _hover_prefix, _applied_prefix, _apply_pending
    _hover_prefix = None
    _applied_prefix = None
    _apply_pending = False
    _cleanup_legacy()
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
