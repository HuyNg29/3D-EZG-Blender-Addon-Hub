"""Thao tác của EZG Animation Tools."""

import bpy
from bpy.types import Operator

from . import bounce, core, mirror, roles


def _settings(context):
    return context.scene.ezg_anim_tools


def _frame_range(st):
    """Khoảng frame theo chế độ đang chọn. Trả về (start, end)."""
    if st.frame_mode == 'MANUAL':
        return st.frame_start, st.frame_end
    if st.frame_mode == 'SCENE':
        sc = bpy.context.scene
        return sc.frame_start, sc.frame_end
    ad = st.source.animation_data if st.source else None
    if ad and ad.action:
        fr = ad.action.frame_range
        return int(fr[0]), int(fr[1])
    return st.frame_start, st.frame_end


def _active_pairs(st):
    """Các cặp đang bật, đã kèm xương con để đo hướng chi."""
    rows = [r for r in st.mapping if r.use and r.src and r.tgt]
    return roles.resolve_children(rows)


class EZG_AT_OT_auto_map(Operator):
    bl_idname = "ezg_at.auto_map"
    bl_label = "Auto Map Bones"
    bl_description = "Doan bang anh xa xuong tu ten cua hai rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = _settings(context)
        if not st.source or not st.target:
            cls.poll_message_set("Chua chon du armature nguon va dich.")
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        found = roles.pair_up(st.source.data, st.target.data)

        st.mapping.clear()
        for role, side, src, tgt in found:
            it = st.mapping.add()
            it.role, it.side, it.src, it.tgt, it.use = role, side, src, tgt, True
        st.map_index = 0

        if not found:
            self.report({'WARNING'},
                        "Khong tu doan duoc cap nao. Hay noi tay trong bang.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Da doan %d cap xuong." % len(found))
        return {'FINISHED'}


class EZG_AT_OT_add_row(Operator):
    bl_idname = "ezg_at.add_row"
    bl_label = "Add Row"
    bl_description = "Them mot cap xuong trong"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = _settings(context)
        it = st.mapping.add()
        it.role, it.use = "custom", True
        st.map_index = len(st.mapping) - 1
        return {'FINISHED'}


class EZG_AT_OT_remove_row(Operator):
    bl_idname = "ezg_at.remove_row"
    bl_label = "Remove Row"
    bl_description = "Xoa cap dang chon"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = _settings(context)
        return 0 <= st.map_index < len(st.mapping)

    def execute(self, context):
        st = _settings(context)
        st.mapping.remove(st.map_index)
        st.map_index = max(0, min(st.map_index, len(st.mapping) - 1))
        return {'FINISHED'}


class EZG_AT_OT_clear_map(Operator):
    bl_idname = "ezg_at.clear_map"
    bl_label = "Clear Mapping"
    bl_description = "Xoa toan bo bang anh xa"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _settings(context).mapping.clear()
        return {'FINISHED'}


class EZG_AT_OT_retarget(Operator):
    bl_idname = "ezg_at.retarget"
    bl_label = "Retarget"
    bl_description = "Bake animation cua rig nguon len rig dich"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = _settings(context)
        if not st.source or not st.target:
            cls.poll_message_set("Chua chon du armature nguon va dich.")
            return False
        if st.source == st.target:
            cls.poll_message_set("Nguon va dich dang la cung mot armature.")
            return False
        if not any(r.use and r.src and r.tgt for r in st.mapping):
            cls.poll_message_set("Bang anh xa dang rong. Bam Auto Map truoc.")
            return False
        ad = st.source.animation_data
        if ad is None or ad.action is None:
            cls.poll_message_set("Armature nguon khong co action nao dang gan.")
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        pairs = _active_pairs(st)
        hips = next((p for p in pairs if p["role"] == "hips"), None)
        f0, f1 = _frame_range(st)
        if f1 < f0:
            self.report({'ERROR'}, "Khoang frame khong hop le.")
            return {'CANCELLED'}

        try:
            act, report = core.retarget(
                context, st.source, st.target, pairs, f0, f1,
                st.action_name or "Retargeted",
                align_rest=st.align_rest,
                use_hips_loc=st.use_hips_loc,
                hips_scale=None if st.hips_auto else st.hips_scale,
                hips_pair=hips,
            )
        except core.RetargetError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        msg = "Da tao '%s': %d xuong, frame %d..%d." % (act.name, len(pairs), f0, f1)
        for line in report:
            print("[EZG Anim Tools]", line)
        self.report({'WARNING'} if report else {'INFO'},
                    msg + (" %d canh bao (xem System Console)." % len(report) if report else ""))
        return {'FINISHED'}


class EZG_AT_OT_check(Operator):
    bl_idname = "ezg_at.check"
    bl_label = "Check Accuracy"
    bl_description = ("Do sai lech GOC giua huong chi hai rig qua tung frame. "
                      "Chay sau khi retarget de biet ket qua bam sat den dau")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return EZG_AT_OT_retarget.poll(context)

    def execute(self, context):
        st = _settings(context)
        pairs = _active_pairs(st)
        f0, f1 = _frame_range(st)
        res = core.measure_error(context, st.source, st.target, pairs, f0, f1)
        if not res:
            self.report({'WARNING'}, "Khong du du lieu de do.")
            return {'CANCELLED'}
        msg = ("Lech goc trung binh %.2f do, lon nhat %.2f do o '%s' (%d mau)."
               % (res["mean"], res["max"], res["worst"], res["samples"]))
        print("[EZG Anim Tools]", msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _mirror_inputs(context):
    st = _settings(context)
    ob = st.mirror_object or st.target or context.object
    act = st.mirror_action
    if act is None and ob and ob.animation_data:
        act = ob.animation_data.action
    return ob, act


class EZG_AT_OT_mirror(Operator):
    bl_idname = "ezg_at.mirror"
    bl_label = "Mirror Action"
    bl_description = ("Nhan doi action da chon roi lat guong trai/phai de len. "
                      "Giu nguyen marker, custom property, fcurve modifier va do "
                      "phu kenh cua ban goc")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob, act = _mirror_inputs(context)
        if ob is None or ob.type != 'ARMATURE':
            cls.poll_message_set("Chua chon armature.")
            return False
        if act is None:
            cls.poll_message_set("Chua co action nao de lat guong.")
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        ob, act = _mirror_inputs(context)
        name = st.mirror_name.strip() or (act.name + "_Mirror")
        if name == act.name:
            self.report({'ERROR'}, "Ten moi trung ten action goc.")
            return {'CANCELLED'}

        try:
            new, report = mirror.mirror_action(context, ob, act, name, clone=True)
        except mirror.MirrorError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        err, worst = mirror.mirror_error(context, ob, act, new)
        msg = "Da tao '%s' (%d fcurve). Lech so voi anh guong ly thuyet: %.3f do." \
              % (new.name, len(new.fcurves), err)
        for line in report:
            print("[EZG Anim Tools]", line)
        if worst and err > 0.5:
            print("[EZG Anim Tools] lech nhieu nhat o '%s'" % worst)
        self.report({'WARNING'} if report else {'INFO'},
                    msg + (" %d canh bao (System Console)." % len(report) if report else ""))
        return {'FINISHED'}


def _polish_inputs(context):
    st = _settings(context)
    ob = st.polish_object or st.target or context.object
    act = st.polish_action
    if act is None and ob and ob.animation_data:
        act = ob.animation_data.action
    return ob, act


class EZG_AT_OT_bounce(Operator):
    bl_idname = "ezg_at.bounce"
    bl_label = "Add Bounce"
    bl_description = ("Them nhip nhun, ghim ban chan dinh san bang IK hai xuong. "
                      "Dat do cao hong tuyet doi nen chay lai khong nhun chong nhun")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob, act = _polish_inputs(context)
        if ob is None or ob.type != 'ARMATURE':
            cls.poll_message_set("Chua chon armature.")
            return False
        if act is None:
            cls.poll_message_set("Chua co action nao de chinh.")
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        ob, act = _polish_inputs(context)
        try:
            report, stats = bounce.add_bounce(context, ob, act,
                                             st.bounce_depth, st.bounce_cycles)
        except bounce.BounceError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        msg = ("Nhun %.1f mm, ban chan truot %.2f mm, %d frame."
               % (stats["bounce"] * 1000.0, stats["drift"] * 1000.0, stats["frames"]))
        for line in report:
            print("[EZG Anim Tools]", line)
        self.report({'WARNING'} if report else {'INFO'},
                    msg + (" %d canh bao (System Console)." % len(report) if report else ""))
        return {'FINISHED'}


class EZG_AT_OT_amplify(Operator):
    bl_idname = "ezg_at.amplify"
    bl_label = "Amplify Torso Motion"
    bl_description = ("Day chuyen dong cua than xa tu the trung binh. "
                      "KHONG idempotent: chay hai lan la nhan hai lan")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return EZG_AT_OT_bounce.poll(context)

    def execute(self, context):
        st = _settings(context)
        ob, act = _polish_inputs(context)
        try:
            n, before, after = bounce.amplify_motion(context, ob, act,
                                                     st.amplify_factor)
        except bounce.BounceError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "%d xuong than: bien do %.2f -> %.2f do."
                    % (n, before, after))
        return {'FINISHED'}


classes = (
    EZG_AT_OT_auto_map,
    EZG_AT_OT_add_row,
    EZG_AT_OT_remove_row,
    EZG_AT_OT_clear_map,
    EZG_AT_OT_retarget,
    EZG_AT_OT_check,
    EZG_AT_OT_mirror,
    EZG_AT_OT_bounce,
    EZG_AT_OT_amplify,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
