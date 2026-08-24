"""Lõi retarget: chuyển tư thế từ bộ xương này sang bộ xương khác.

Nguyên tắc: **chuyển độ lệch so với rest, đo trong không gian thế giới.**

    delta     = pose_nguon @ rest_nguon.inverted()   (phép xoay trong hệ thế giới)
    pose_dich = delta @ rest_dich_da_can

Cách này không quan tâm hai rig đặt trục xương thế nào, roll bao nhiêu — thứ duy
nhất được truyền là *chuyển động*. Nhờ vậy rig nguồn kiểu joint (Maya, engine
game — nơi `bone.tail` do Blender bịa ra) vẫn dùng được.

Cạm bẫy lớn nhất là **rest pose hai bên khác nhau** (A-pose với T-pose). Nếu coi
rest nguồn ứng thẳng với rest đích thì mọi khung hình sẽ lệch đúng bằng khoảng
cách giữa hai tư thế đó — tay sai suốt animation. `build_alignment` xử lý bằng
cách xoay rest đích cho hướng chi trùng hướng chi của rest nguồn, đo bằng vector
head→head của xương kế tiếp chứ không dùng `bone.tail`.
"""

import math

import bpy
from mathutils import Matrix


class RetargetError(Exception):
    pass


def hierarchy_order(arm):
    """Tên xương theo thứ tự cha trước, con sau."""
    order = []

    def walk(b):
        order.append(b.name)
        for c in b.children:
            walk(c)

    for b in arm.bones:
        if b.parent is None:
            walk(b)
    return order


def rest_head_world(ob, bone_name):
    return ob.matrix_world @ ob.data.bones[bone_name].matrix_local.translation


def build_alignment(src_ob, tgt_ob, pairs):
    """Phép bù lệch rest pose cho từng xương đích -> {tên_xương: Matrix 3x3}.

    Xương không có xương con tin cậy được (bàn tay, mũi chân, đầu) thì kế thừa
    phép bù của xương cha: ở rest chúng gần như luôn cùng hướng với cha.
    """
    align = {}
    for p in pairs:
        sc, tc = p.get("src_child"), p.get("tgt_child")
        if not sc or not tc:
            align[p["tgt"]] = None
            continue
        try:
            v_s = (rest_head_world(src_ob, sc)
                   - rest_head_world(src_ob, p["src"])).normalized()
            v_t = (rest_head_world(tgt_ob, tc)
                   - rest_head_world(tgt_ob, p["tgt"])).normalized()
        except (KeyError, RuntimeError):
            align[p["tgt"]] = None
            continue
        align[p["tgt"]] = v_t.rotation_difference(v_s).to_matrix()

    bones = tgt_ob.data.bones
    for name in list(align):
        if align[name] is not None:
            continue
        b = bones[name].parent
        while b is not None and align.get(b.name) is None:
            b = b.parent
        align[name] = align[b.name].copy() if b is not None else Matrix.Identity(3)
    return align


def auto_hips_scale(src_ob, tgt_ob, src_hips, tgt_hips):
    """Tỉ lệ quy đổi tịnh tiến hông = tỉ lệ chiều cao hông của hai nhân vật.

    Hông cao bao nhiêu thì chân dài bấy nhiêu, nên dùng nó để quy đổi thì bước
    chân và độ nhún giữ đúng tỉ lệ cơ thể.
    """
    zs = rest_head_world(src_ob, src_hips).z
    if abs(zs) < 1e-9:
        return 1.0
    return rest_head_world(tgt_ob, tgt_hips).z / zs


def retarget(context, src_ob, tgt_ob, pairs, frame_start, frame_end,
             action_name, align_rest=True, use_hips_loc=True,
             hips_scale=None, hips_pair=None):
    """Bake animation của `src_ob` lên `tgt_ob`. Trả về (action, cảnh_báo)."""
    report = []

    if src_ob is None or tgt_ob is None:
        raise RetargetError("Chua chon du armature nguon va dich.")
    if src_ob == tgt_ob:
        raise RetargetError("Nguon va dich dang la cung mot armature.")
    if not pairs:
        raise RetargetError("Bang anh xa xuong dang rong.")

    ad = src_ob.animation_data
    if ad is None or ad.action is None:
        raise RetargetError("Armature nguon khong co action nao dang gan.")

    # Ở Rest Position thì pose.bones[].matrix trả về rest, bake ra sẽ là một loạt
    # khung hình đứng yên mà không báo lỗi gì. Đã dính đúng một lần.
    for ob, nhan in ((src_ob, "nguon"), (tgt_ob, "dich")):
        if ob.data.pose_position == 'REST':
            ob.data.pose_position = 'POSE'
            report.append("Armature %s dang o Rest Position, da chuyen sang Pose." % nhan)

    src_bones = src_ob.data.bones
    tgt_bones = tgt_ob.data.bones
    pairs = [p for p in pairs
             if p.get("src") in src_bones and p.get("tgt") in tgt_bones]
    if not pairs:
        raise RetargetError("Khong cap xuong nao ton tai tren ca hai rig.")

    Ms, Mt = src_ob.matrix_world, tgt_ob.matrix_world
    Rs = Ms.to_3x3().normalized()
    Rt = Mt.to_3x3().normalized()
    Rt_inv = Rt.inverted()
    Mt_inv = Mt.inverted()

    align = build_alignment(src_ob, tgt_ob, pairs) if align_rest else {}
    smap = {p["tgt"]: p["src"] for p in pairs}

    rest = {b.name: b.matrix_local.copy() for b in tgt_bones}
    order = hierarchy_order(tgt_ob.data)

    hips_tgt = hips_src = None
    hips_rest_src_w = hips_rest_tgt_w = None
    ratio = 1.0
    if use_hips_loc and hips_pair:
        ht, hs = hips_pair.get("tgt"), hips_pair.get("src")
        if ht not in tgt_bones or hs not in src_bones:
            report.append("Khong xac dinh duoc xuong hong, bo qua tinh tien.")
        elif tgt_bones[ht].use_connect:
            report.append("Xuong hong ben dich dang Connected nen khong tinh tien duoc.")
        else:
            hips_tgt, hips_src = ht, hs
            ratio = (hips_scale if hips_scale is not None
                     else auto_hips_scale(src_ob, tgt_ob, hips_src, hips_tgt))
            hips_rest_src_w = rest_head_world(src_ob, hips_src)
            hips_rest_tgt_w = rest_head_world(tgt_ob, hips_tgt)

    for pb in tgt_ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.matrix_basis = Matrix.Identity(4)

    old = bpy.data.actions.get(action_name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(action_name)
    act.use_fake_user = True
    if tgt_ob.animation_data is None:
        tgt_ob.animation_data_create()
    tgt_ob.animation_data.action = act

    scene = context.scene
    saved_frame = scene.frame_current

    for f in range(int(frame_start), int(frame_end) + 1):
        scene.frame_set(f)
        context.view_layer.update()

        pose = {}
        for name in order:
            bone = tgt_bones[name]
            parent = bone.parent
            if parent is None:
                base = rest[name].copy()
            else:
                base = pose[parent.name] @ (rest[parent.name].inverted() @ rest[name])

            if name in smap:
                s_name = smap[name]
                s_pose_w = Rs @ src_ob.pose.bones[s_name].matrix.to_3x3()
                s_rest_w = Rs @ src_bones[s_name].matrix_local.to_3x3()
                delta_w = s_pose_w @ s_rest_w.inverted()

                a = align.get(name) or Matrix.Identity(3)
                t_ref_w = a @ (Rt @ rest[name].to_3x3())
                rot = Rt_inv @ (delta_w @ t_ref_w)

                if name == hips_tgt:
                    now_w = (Ms @ src_ob.pose.bones[s_name].matrix).translation
                    want_w = hips_rest_tgt_w + (now_w - hips_rest_src_w) * ratio
                    loc = (Mt_inv @ want_w)
                else:
                    loc = base.translation

                desired = Matrix.Translation(loc) @ rot.to_4x4()
            else:
                desired = base

            pose[name] = desired
            tgt_ob.pose.bones[name].matrix_basis = base.inverted() @ desired

        for name in smap:
            pb = tgt_ob.pose.bones[name]
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if name == hips_tgt:
                pb.keyframe_insert("location", frame=f)

    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'

    scene.frame_set(saved_frame)
    return act, report


def measure_error(context, src_ob, tgt_ob, pairs, frame_start, frame_end):
    """Sai lệch **góc** giữa hướng chi hai rig, tính bằng độ.

    Đây mới là thước đo đúng cho retarget. Hai nhân vật khác tỉ lệ cơ thể thì
    không thể khớp vị trí khớp được — chỉ khớp được góc. Đo bằng vị trí sẽ ra
    con số to tướng và vô nghĩa.
    """
    Ms, Mt = src_ob.matrix_world, tgt_ob.matrix_world
    segs = [p for p in pairs if p.get("src_child") and p.get("tgt_child")]
    if not segs:
        return None

    scene = context.scene
    saved = scene.frame_current
    total = 0.0
    count = 0
    worst = 0.0
    worst_name = ""

    for f in range(int(frame_start), int(frame_end) + 1):
        scene.frame_set(f)
        context.view_layer.update()
        for p in segs:
            try:
                a = (Ms @ src_ob.pose.bones[p["src"]].matrix).translation
                b = (Ms @ src_ob.pose.bones[p["src_child"]].matrix).translation
                c = (Mt @ tgt_ob.pose.bones[p["tgt"]].matrix).translation
                d = (Mt @ tgt_ob.pose.bones[p["tgt_child"]].matrix).translation
            except (KeyError, RuntimeError):
                continue
            v1, v2 = (b - a), (d - c)
            if v1.length < 1e-9 or v2.length < 1e-9:
                continue
            ang = math.degrees(v1.normalized().angle(v2.normalized()))
            total += ang
            count += 1
            if ang > worst:
                worst, worst_name = ang, p["tgt"]

    scene.frame_set(saved)
    if not count:
        return None
    return {"mean": total / count, "max": worst,
            "worst": worst_name, "samples": count}
