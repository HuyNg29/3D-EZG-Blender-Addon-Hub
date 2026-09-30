"""Giao diện EZG Animation Tools — View3D > phím N > tab 'EZG Anim'."""

import bpy
from bpy.types import Panel, UIList

from . import ezg_i18n
from .ezg_i18n import tr

CATEGORY = "EZG Anim"


class EZG_AT_UL_map(UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        st = context.scene.ezg_anim_tools
        row = layout.row(align=True)
        row.prop(item, "use", text="")

        sub = row.row()
        sub.enabled = item.use
        sub.label(text=item.label)

        if st.source and st.source.type == 'ARMATURE':
            sub.prop_search(item, "src", st.source.data, "bones", text="", icon='BONE_DATA')
        else:
            sub.prop(item, "src", text="")

        sub.label(text="", icon='FORWARD')

        if st.target and st.target.type == 'ARMATURE':
            sub.prop_search(item, "tgt", st.target.data, "bones", text="", icon='BONE_DATA')
        else:
            sub.prop(item, "tgt", text="")

        # Truyen vi tri: chi rig IK moi can, nen de gon o cuoi dong. O chon
        # xuong neo chi hien khi da bat, khong thi hang danh sach roi ram.
        sub.prop(item, "pos", text="", icon='CON_LOCLIKE')
        if item.pos:
            if st.target and st.target.type == 'ARMATURE':
                sub.prop_search(item, "anchor", st.target.data, "bones",
                                text="", icon='SNAP_ON')
            else:
                sub.prop(item, "anchor", text="")


class EZG_AT_PT_retarget(Panel):
    bl_label = "Retarget"  # i18n-skip
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    def draw_header_preset(self, context):
        ezg_i18n.draw_toggle(self.layout, "ezg_at")

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.label(text="Armature", icon='ARMATURE_DATA')  # i18n-skip
        box.prop(st, "source", text=tr("Từ", "From"))
        box.prop(st, "target", text=tr("Sang", "To"))

        if st.source and st.source.animation_data and st.source.animation_data.action:
            act = st.source.animation_data.action
            fr = act.frame_range
            box.label(text="Action: %s  (%d..%d)" % (act.name, fr[0], fr[1]), icon='ACTION')  # i18n-skip
        elif st.source:
            box.label(text=tr("Rig nguồn chưa có action nào.", "The source rig has no action yet."),
                      icon='ERROR')

        if st.source and st.source.data.pose_position == 'REST':
            box.label(text=tr("Rig nguồn đang ở Rest Position.", "The source rig is in Rest Position."),
                      icon='ERROR')

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Bone mapping", icon='GROUP_BONE')  # i18n-skip
        row.operator("ezg_at.auto_map", text="Auto Map", icon='AUTO')  # i18n-skip

        row = box.row()
        row.template_list("EZG_AT_UL_map", "", st, "mapping", st, "map_index", rows=8)
        col = row.column(align=True)
        col.operator("ezg_at.add_row", text="", icon='ADD')
        col.operator("ezg_at.remove_row", text="", icon='REMOVE')
        col.separator()
        col.operator("ezg_at.clear_map", text="", icon='TRASH')

        n = sum(1 for r in st.mapping if r.use and r.src and r.tgt)
        n_pos = sum(1 for r in st.mapping if r.use and r.pos and r.src and r.tgt)
        box.label(text=tr("%d cặp đang bật%s", "%d pairs enabled%s")
                  % (n, (tr(", %d truyền vị trí", ", %d with position") % n_pos) if n_pos else ""))
        col = box.column()
        col.scale_y = 0.7
        col.label(text=tr("Nút vị trí (mũi tên): bật cho xương IK mang",
                          "Position toggle (arrows): turn on for IK bones"), icon='CON_LOCLIKE')
        col.label(text=tr("vị trí thật (cổ chân/cổ tay treo riêng vào root),",
                          "that carry the real position (ankle/wrist on root),"))
        col.label(text=tr("rồi chọn xương neo — neo vào đầu gối tốt hơn hông.",
                          "then pick an anchor — the knee works better than the hips."))

        box = layout.box()
        box.label(text=tr("Tuỳ chọn", "Options"), icon='OPTIONS')
        box.prop(st, "align_rest")
        box.prop(st, "use_hips_loc")
        sub = box.column(align=True)
        sub.enabled = st.use_hips_loc
        sub.prop(st, "hips_auto")
        row = sub.row()
        row.enabled = not st.hips_auto
        row.prop(st, "hips_scale")

        box.prop(st, "frame_mode", text=tr("Khoảng frame", "Range"))
        if st.frame_mode == 'MANUAL':
            row = box.row(align=True)
            row.prop(st, "frame_start")
            row.prop(st, "frame_end")

        box = layout.box()
        box.prop(st, "action_name", text="Action")  # i18n-skip
        box.operator("ezg_at.retarget", text="Retarget", icon='PLAY')  # i18n-skip
        box.operator("ezg_at.check", text=tr("Kiểm tra độ chính xác", "Check Accuracy"),
                     icon='DRIVER_DISTANCE')

        col = layout.column()
        col.scale_y = 0.7
        col.label(text=tr("Sai lệch được đo bằng GÓC, không phải vị trí:",
                          "The error is measured as an ANGLE, not a position:"), icon='INFO')
        col.label(text=tr("hai nhân vật khác tỉ lệ cơ thể thì không thể",
                          "two characters with different proportions can"))
        col.label(text=tr("khớp vị trí khớp được.", "never match joint positions."))


class EZG_AT_PT_mirror(Panel):
    bl_label = tr("Lật gương action", "Mirror Action")
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.prop(st, "mirror_object", text="Armature")  # i18n-skip
        box.prop(st, "mirror_action", text="Action")  # i18n-skip

        ob = st.mirror_object or st.target or context.object
        act = st.mirror_action
        if act is None and ob and ob.animation_data:
            act = ob.animation_data.action
            if act:
                box.label(text=tr("Đang lấy action đang gán: %s", "Using the assigned action: %s")
                          % act.name, icon='ACTION')

        box.prop(st, "mirror_name", text=tr("Tên mới", "New Name"))
        if act and not st.mirror_name.strip():
            box.label(text="-> '%s_Mirror'" % act.name, icon='DOT')  # i18n-skip

        layout.operator("ezg_at.mirror", text=tr("Lật gương trái / phải", "Mirror Left / Right"),
                        icon='MOD_MIRROR')

        col = layout.column()
        col.scale_y = 0.7
        col.label(text=tr("Sao đủ cả 9 kênh cấp object (location /",
                          "Copies all 9 object-level channels (location /"), icon='INFO')
        col.label(text=tr("rotation / scale). Thiếu chúng thì Blender vẫn",
                          "rotation / scale). Without them Blender still"))
        col.label(text=tr("đúng nhưng engine sẽ hiện nhân vật sai scale.",
                          "looks right but the engine shows the wrong scale."))
        col.separator()
        col.label(text=tr("Nút này nhân đôi action gốc rồi lật đè lên, nên",
                          "This duplicates the original action and mirrors it,"),
                  icon='DUPLICATE')
        col.label(text=tr("giữ cả marker, custom property, fcurve modifier.",
                          "keeping markers, custom properties, F-Curve modifiers."))
        col.label(text=tr("Đổi lại: fcurve rác của bản gốc cũng theo sang.",
                          "Downside: junk F-Curves of the original come along too."))


classes = (EZG_AT_UL_map, EZG_AT_PT_retarget, EZG_AT_PT_mirror)


def register():
    ezg_i18n.register_classes(classes)


def unregister():
    ezg_i18n.unregister_classes(classes)


class EZG_AT_PT_polish(Panel):
    bl_label = tr("Nhún / Tinh chỉnh", "Bounce / Polish")
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.prop(st, "polish_object", text="Armature")  # i18n-skip
        box.prop(st, "polish_action", text="Action")  # i18n-skip
        ob = st.polish_object or st.target or context.object
        if st.polish_action is None and ob and ob.animation_data and ob.animation_data.action:
            box.label(text=tr("Đang lấy action đang gán: %s", "Using the assigned action: %s")
                      % ob.animation_data.action.name, icon='ACTION')

        box = layout.box()
        box.label(text=tr("Nhún", "Bounce"), icon='FORCE_HARMONIC')
        box.prop(st, "bounce_depth")
        box.prop(st, "bounce_cycles")
        box.operator("ezg_at.bounce", text=tr("Thêm nhịp nhún", "Add Bounce"), icon='PLAY')

        box = layout.box()
        box.label(text=tr("Khuếch đại thân", "Amplify Torso"), icon='CON_TRANSLIKE')
        box.prop(st, "amplify_factor")
        box.operator("ezg_at.amplify",
                     text=tr("Khuếch đại chuyển động thân", "Amplify Torso Motion"), icon='PLAY')
        col = box.column()
        col.scale_y = 0.7
        col.label(text=tr("KHÔNG idempotent: chạy hai lần là",
                          "NOT idempotent: running it twice"), icon='ERROR')
        col.label(text=tr("nhân hai lần.", "amplifies twice."))

        col = layout.column()
        col.scale_y = 0.7
        col.label(text=tr("Nhún ghim bàn chân bằng IK hai xương, và đặt",
                          "Bounce pins the feet with two-bone IK and"), icon='INFO')
        col.label(text=tr("độ cao hông tuyệt đối -> chạy lại không bị",
                          "sets an absolute hip height -> running it"))
        col.label(text=tr("nhún chồng nhún. Số nhịp phải NGUYÊN.",
                          "again won't stack. Cycles must be WHOLE."))


classes = classes + (EZG_AT_PT_polish,)
