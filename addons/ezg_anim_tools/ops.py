"""Thao tác của EZG Animation Tools."""

import bpy
from bpy.types import Operator

from . import bounce, core, ezg_i18n, mirror, roles
from .ezg_i18n import tr


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


def _warn_suffix(report):
    """Đuôi thông báo khi có cảnh báo; chi tiết đã in ra System Console."""
    if not report:
        return ""
    return tr(" %d cảnh báo (xem System Console).",
              " Warnings: %d (see System Console).") % len(report)


class EZG_AT_OT_auto_map(Operator):
    bl_idname = "ezg_at.auto_map"
    bl_label = tr("Auto Map xương", "Auto Map Bones")
    bl_description = tr("Đoán bảng ánh xạ xương từ tên xương của hai rig",
                        "Guess the bone mapping from the bone names of both rigs")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = _settings(context)
        if not st.source or not st.target:
            cls.poll_message_set(tr("Chưa chọn đủ armature nguồn và đích.",
                                    "Source and target armatures are not both set yet."))
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
                        tr("Không tự đoán được cặp nào. Hãy nối tay trong bảng.",
                           "Could not guess any pair. Map the bones by hand in the table."))
            return {'CANCELLED'}
        self.report({'INFO'}, tr("Đã đoán %d cặp xương.", "Guessed %d bone pairs.") % len(found))
        return {'FINISHED'}


class EZG_AT_OT_add_row(Operator):
    bl_idname = "ezg_at.add_row"
    bl_label = tr("Thêm dòng", "Add Row")
    bl_description = tr("Thêm một cặp xương trống", "Add an empty bone pair")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = _settings(context)
        it = st.mapping.add()
        it.role, it.use = "custom", True
        st.map_index = len(st.mapping) - 1
        return {'FINISHED'}


class EZG_AT_OT_remove_row(Operator):
    bl_idname = "ezg_at.remove_row"
    bl_label = tr("Xoá dòng", "Remove Row")
    bl_description = tr("Xoá cặp đang chọn", "Remove the selected pair")
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
    bl_label = tr("Xoá bảng ánh xạ", "Clear Mapping")
    bl_description = tr("Xoá toàn bộ bảng ánh xạ xương", "Clear the whole bone mapping")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _settings(context).mapping.clear()
        return {'FINISHED'}


class EZG_AT_OT_retarget(Operator):
    bl_idname = "ezg_at.retarget"
    bl_label = "Retarget"  # i18n-skip
    bl_description = tr("Bake animation của rig nguồn lên rig đích",
                        "Bake the source rig's animation onto the target rig")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = _settings(context)
        if not st.source or not st.target:
            cls.poll_message_set(tr("Chưa chọn đủ armature nguồn và đích.",
                                    "Source and target armatures are not both set yet."))
            return False
        if st.source == st.target:
            cls.poll_message_set(tr("Nguồn và đích đang là cùng một armature.",
                                    "Source and target are the same armature."))
            return False
        if not any(r.use and r.src and r.tgt for r in st.mapping):
            cls.poll_message_set(tr("Bảng ánh xạ đang rỗng. Bấm Auto Map trước.",
                                    "The bone mapping is empty. Click Auto Map first."))
            return False
        ad = st.source.animation_data
        if ad is None or ad.action is None:
            cls.poll_message_set(tr("Armature nguồn không có action nào đang gán.",
                                    "The source armature has no action assigned."))
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        pairs = _active_pairs(st)
        hips = next((p for p in pairs if p["role"] == "hips"), None)
        f0, f1 = _frame_range(st)
        if f1 < f0:
            self.report({'ERROR'}, tr("Khoảng frame không hợp lệ.", "Invalid frame range."))
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

        msg = tr("Đã tạo '%s': %d xương, frame %d..%d.",
                 "Created '%s': %d bones, frames %d..%d.") % (act.name, len(pairs), f0, f1)
        for line in report:
            print("[EZG Anim Tools]", line)
        self.report({'WARNING'} if report else {'INFO'}, msg + _warn_suffix(report))
        return {'FINISHED'}


class EZG_AT_OT_check(Operator):
    bl_idname = "ezg_at.check"
    bl_label = tr("Kiểm tra độ chính xác", "Check Accuracy")
    bl_description = tr("Đo sai lệch GÓC giữa hướng chi hai rig qua từng frame. "
                        "Chạy sau khi retarget để biết kết quả bám sát đến đâu",
                        "Measure the ANGLE error between the limb directions of both rigs "
                        "on every frame. Run after retargeting to see how closely the "
                        "result follows the source")
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
            self.report({'WARNING'}, tr("Không đủ dữ liệu để đo.", "Not enough data to measure."))
            return {'CANCELLED'}
        msg = (tr("Lệch góc trung bình %.2f độ, lớn nhất %.2f độ ở '%s' (%d mẫu).",
                  "Mean angle error %.2f°, max %.2f° at '%s' (%d samples).")
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
    bl_label = tr("Lật gương action", "Mirror Action")
    bl_description = tr("Nhân đôi action đã chọn rồi lật gương trái/phải đè lên. "
                        "Giữ nguyên marker, custom property, fcurve modifier và độ "
                        "phủ kênh của bản gốc",
                        "Duplicate the selected action and mirror it left/right. Keeps "
                        "the original's markers, custom properties, F-Curve modifiers "
                        "and channel coverage")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob, act = _mirror_inputs(context)
        if ob is None or ob.type != 'ARMATURE':
            cls.poll_message_set(tr("Chưa chọn armature.", "No armature selected."))
            return False
        if act is None:
            cls.poll_message_set(tr("Chưa có action nào để lật gương.", "No action to mirror yet."))
            return False
        return True

    def execute(self, context):
        st = _settings(context)
        ob, act = _mirror_inputs(context)
        name = st.mirror_name.strip() or (act.name + "_Mirror")
        if name == act.name:
            self.report({'ERROR'}, tr("Tên mới trùng tên action gốc.",
                                      "The new name is the same as the original action's."))
            return {'CANCELLED'}

        try:
            new, report = mirror.mirror_action(context, ob, act, name, clone=True)
        except mirror.MirrorError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        err, worst = mirror.mirror_error(context, ob, act, new)
        msg = tr("Đã tạo '%s' (%d fcurve). Lệch so với ảnh gương lý thuyết: %.3f độ.",
                 "Created '%s' (%d F-Curves). Deviation from the ideal mirror image: %.3f°.") \
            % (new.name, len(core.action_fcurves(new)), err)
        for line in report:
            print("[EZG Anim Tools]", line)
        if worst and err > 0.5:
            print("[EZG Anim Tools] lech nhieu nhat o '%s'" % worst)
        self.report({'WARNING'} if report else {'INFO'}, msg + _warn_suffix(report))
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
    bl_label = tr("Thêm nhịp nhún", "Add Bounce")
    bl_description = tr("Thêm nhịp nhún, ghim bàn chân dính sàn bằng IK hai xương. "
                        "Đặt độ cao hông tuyệt đối nên chạy lại không bị nhún chồng nhún",
                        "Add a bounce while pinning the feet to the floor with two-bone IK. "
                        "Sets an absolute hip height, so running it again does not stack "
                        "bounces")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob, act = _polish_inputs(context)
        if ob is None or ob.type != 'ARMATURE':
            cls.poll_message_set(tr("Chưa chọn armature.", "No armature selected."))
            return False
        if act is None:
            cls.poll_message_set(tr("Chưa có action nào để chỉnh.", "No action to adjust yet."))
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

        msg = (tr("Nhún %.1f mm, bàn chân trượt %.2f mm, %d frame.",
                  "Bounce %.1f mm, foot slide %.2f mm, %d frames.")
               % (stats["bounce"] * 1000.0, stats["drift"] * 1000.0, stats["frames"]))
        for line in report:
            print("[EZG Anim Tools]", line)
        self.report({'WARNING'} if report else {'INFO'}, msg + _warn_suffix(report))
        return {'FINISHED'}


class EZG_AT_OT_amplify(Operator):
    bl_idname = "ezg_at.amplify"
    bl_label = tr("Khuếch đại chuyển động thân", "Amplify Torso Motion")
    bl_description = tr("Đẩy chuyển động của thân xa tư thế trung bình. "
                        "KHÔNG idempotent: chạy hai lần là nhân hai lần",
                        "Push the torso motion further away from the average pose. "
                        "NOT idempotent: running it twice amplifies twice")
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
        self.report({'INFO'}, tr("%d xương thân: biên độ %.2f -> %.2f độ.",
                                 "%d torso bones: amplitude %.2f° -> %.2f°.")
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
    ezg_i18n.make_language_operator("ezg_at"),
)


def register():
    ezg_i18n.register_classes(classes)


def unregister():
    ezg_i18n.unregister_classes(classes)
