"""Giao diện EZG Animation Tools — View3D > phím N > tab 'EZG Anim'."""

import bpy
from bpy.types import Panel, UIList

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


class EZG_AT_PT_retarget(Panel):
    bl_label = "Retarget"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.label(text="Armature", icon='ARMATURE_DATA')
        box.prop(st, "source", text="From")
        box.prop(st, "target", text="To")

        if st.source and st.source.animation_data and st.source.animation_data.action:
            act = st.source.animation_data.action
            fr = act.frame_range
            box.label(text="Action: %s  (%d..%d)" % (act.name, fr[0], fr[1]), icon='ACTION')
        elif st.source:
            box.label(text="Rig nguon chua co action nao.", icon='ERROR')

        if st.source and st.source.data.pose_position == 'REST':
            box.label(text="Rig nguon dang o Rest Position.", icon='ERROR')

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Bone mapping", icon='GROUP_BONE')
        row.operator("ezg_at.auto_map", text="Auto Map", icon='AUTO')

        row = box.row()
        row.template_list("EZG_AT_UL_map", "", st, "mapping", st, "map_index", rows=8)
        col = row.column(align=True)
        col.operator("ezg_at.add_row", text="", icon='ADD')
        col.operator("ezg_at.remove_row", text="", icon='REMOVE')
        col.separator()
        col.operator("ezg_at.clear_map", text="", icon='TRASH')

        n = sum(1 for r in st.mapping if r.use and r.src and r.tgt)
        box.label(text="%d cap dang bat" % n)

        box = layout.box()
        box.label(text="Options", icon='OPTIONS')
        box.prop(st, "align_rest")
        box.prop(st, "use_hips_loc")
        sub = box.column(align=True)
        sub.enabled = st.use_hips_loc
        sub.prop(st, "hips_auto")
        row = sub.row()
        row.enabled = not st.hips_auto
        row.prop(st, "hips_scale")

        box.prop(st, "frame_mode", text="Range")
        if st.frame_mode == 'MANUAL':
            row = box.row(align=True)
            row.prop(st, "frame_start")
            row.prop(st, "frame_end")

        box = layout.box()
        box.prop(st, "action_name", text="Action")
        box.operator("ezg_at.retarget", text="Retarget", icon='PLAY')
        box.operator("ezg_at.check", text="Check Accuracy", icon='DRIVER_DISTANCE')

        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Sai lech duoc do bang GOC, khong phai vi tri:", icon='INFO')
        col.label(text="hai nhan vat khac ti le co the thi khong the")
        col.label(text="khop vi tri khop duoc.")


class EZG_AT_PT_mirror(Panel):
    bl_label = "Mirror Action"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.prop(st, "mirror_object", text="Armature")
        box.prop(st, "mirror_action", text="Action")

        ob = st.mirror_object or st.target or context.object
        act = st.mirror_action
        if act is None and ob and ob.animation_data:
            act = ob.animation_data.action
            if act:
                box.label(text="Dang lay action dang gan: %s" % act.name, icon='ACTION')

        box.prop(st, "mirror_name", text="New name")
        if act and not st.mirror_name.strip():
            box.label(text="-> '%s_Mirror'" % act.name, icon='DOT')

        layout.operator("ezg_at.mirror", text="Mirror Left / Right", icon='MOD_MIRROR')

        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Sao du ca 9 kenh cap object (location /", icon='INFO')
        col.label(text="rotation / scale). Thieu chung thi Blender van")
        col.label(text="dung nhung engine se hien nhan vat sai scale.")


classes = (EZG_AT_UL_map, EZG_AT_PT_retarget, EZG_AT_PT_mirror)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass


class EZG_AT_PT_polish(Panel):
    bl_label = "Bounce / Polish"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st = context.scene.ezg_anim_tools
        layout = self.layout

        box = layout.box()
        box.prop(st, "polish_object", text="Armature")
        box.prop(st, "polish_action", text="Action")
        ob = st.polish_object or st.target or context.object
        if st.polish_action is None and ob and ob.animation_data and ob.animation_data.action:
            box.label(text="Dang lay action dang gan: %s" % ob.animation_data.action.name,
                      icon='ACTION')

        box = layout.box()
        box.label(text="Bounce", icon='FORCE_HARMONIC')
        box.prop(st, "bounce_depth")
        box.prop(st, "bounce_cycles")
        box.operator("ezg_at.bounce", text="Add Bounce", icon='PLAY')

        box = layout.box()
        box.label(text="Amplify torso", icon='CON_TRANSLIKE')
        box.prop(st, "amplify_factor")
        box.operator("ezg_at.amplify", text="Amplify Torso Motion", icon='PLAY')
        col = box.column()
        col.scale_y = 0.7
        col.label(text="KHONG idempotent: chay hai lan la", icon='ERROR')
        col.label(text="nhan hai lan.")

        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Nhun ghim ban chan bang IK hai xuong, va dat", icon='INFO')
        col.label(text="do cao hong tuyet doi -> chay lai khong bi")
        col.label(text="nhun chong nhun. So nhip phai NGUYEN.")


classes = classes + (EZG_AT_PT_polish,)
