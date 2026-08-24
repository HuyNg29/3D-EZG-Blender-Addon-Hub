"""Lật gương trái/phải một action.

Cách làm: **soi gương ma trận tư thế trong không gian armature**, không lật dấu
thành phần quaternion. Với mỗi xương, tư thế mới lấy từ xương ĐỐI BÊN:

    P_moi(b) = Mx @ P_cu(doi_ben(b)) @ Mx        (Mx: lật qua mặt phẳng YZ)

Mx là phép phản chiếu (det = -1) nên `Mx @ P @ Mx` vẫn là phép quay thuận. Cách
này khỏi phải đoán quy ước dấu quaternion của từng rig, và đúng kể cả khi hai bên
đặt trục xương khác nhau.

Hai bài học đắt giá đã gói vào đây:

1. **Sao đủ kênh.** Action gốc thường có cả 9 fcurve cấp OBJECT (location /
   rotation_euler / scale). Nếu bản lật gương chỉ có kênh của xương, trong
   Blender vẫn trông đúng — nhưng khi export sang engine, clip gốc *điều khiển*
   scale về 0.01 còn clip mới không điều khiển gì, nên root giữ scale 1 và nhân
   vật to gấp 100 lần. Lỗi chỉ lộ ở đầu ra, không lộ trong viewport.

2. **Tự tính FK.** `pose_bone.matrix` có thể còn cũ sau `frame_set` ở một số ngữ
   cảnh chạy script, làm mọi phép đo ra 0 và tưởng animation đứng yên. Ở đây
   dựng ma trận từ `matrix_basis` + rest nên luôn đúng.
"""

import math

import bpy
from mathutils import Matrix, Quaternion


class MirrorError(Exception):
    pass


_PAIRS = (("Left", "Right"), ("left", "right"), ("LEFT", "RIGHT"),
          ("_L", "_R"), (".L", ".R"), ("_l", "_r"), (".l", ".r"),
          ("-L", "-R"), ("-l", "-r"))


def mirror_name(name):
    """Ten xuong doi ben. Tra ve chinh no neu la xuong giua than."""
    for a, b in _PAIRS:
        if a in name:
            return name.replace(a, b, 1)
        if b in name:
            return name.replace(b, a, 1)
    # Tien to dang 'L_xxx' / 'R_xxx'
    if len(name) > 2 and name[1] in "_.-":
        if name[0] in "Ll":
            return ("R" if name[0] == "L" else "r") + name[1:]
        if name[0] in "Rr":
            return ("L" if name[0] == "R" else "l") + name[1:]
    return name


def hierarchy_order(arm):
    order = []

    def walk(b):
        order.append(b.name)
        for c in b.children:
            walk(c)

    for b in arm.bones:
        if b.parent is None:
            walk(b)
    return order


def rest_symmetry_error(ob):
    """Rest pose co doi xung trai/phai khong. Tra ve (lech_mm, lech_do, ten).

    Rest lech thi ban lat guong van dung ve GOC nhung vi tri khop se lech theo.
    Bao cho nguoi dung biet, vi do la khuyet tat cua RIG chu khong phai cua phep
    lat, va ho se thay hai ban trai/phai "hoi khac nhau".
    """
    Mx = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    rest = {b.name: b.matrix_local.copy() for b in ob.data.bones}
    R = ob.matrix_world.to_3x3()
    worst_t = worst_a = 0.0
    worst = ""
    for name, m in rest.items():
        other = mirror_name(name)
        if other == name or other not in rest:
            continue
        A = Mx @ rest[other] @ Mx
        dt = (R @ (A.translation - m.translation)).length
        d = A.to_quaternion().rotation_difference(m.to_quaternion()).angle
        da = math.degrees(min(d, 2 * math.pi - d))
        if dt > worst_t:
            worst_t, worst = dt, name
        worst_a = max(worst_a, da)
    return worst_t, worst_a, worst


def _object_level(action):
    """{(data_path, index): gia_tri_tai_frame_dau} cho cac fcurve cap object."""
    out = {}
    for fc in action.fcurves:
        if fc.data_path.startswith("pose.bones"):
            continue
        if fc.data_path not in ("location", "rotation_euler",
                                "rotation_quaternion", "scale"):
            continue
        out[(fc.data_path, fc.array_index)] = fc.evaluate(action.frame_range[0])
    return out


def mirror_action(context, ob, src_action, new_name):
    """Tao action moi la anh guong trai/phai cua `src_action`.

    Tra ve (action_moi, canh_bao).
    """
    if ob is None or ob.type != 'ARMATURE':
        raise MirrorError("Chua chon armature.")
    if src_action is None:
        raise MirrorError("Chua chon action can lat guong.")

    report = []
    arm = ob.data
    if arm.pose_position == 'REST':
        arm.pose_position = 'POSE'
        report.append("Armature dang o Rest Position, da chuyen sang Pose.")

    dt, da, worst = rest_symmetry_error(ob)
    if dt > 0.002 or da > 2.0:
        report.append("Rest pose khong doi xung (lech %.1f mm / %.1f do o '%s'): "
                      "vi tri khop hai ban se lech chut it."
                      % (dt * 1000.0, da, worst.replace("mixamorig:", "")))

    Mx = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    rest = {b.name: b.matrix_local.copy() for b in arm.bones}
    order = hierarchy_order(arm)

    fr = src_action.frame_range
    f0, f1 = int(round(fr[0])), int(round(fr[1]))

    ad = ob.animation_data
    if ad is None:
        raise MirrorError("Armature khong co animation data.")

    muted = [(t, t.mute, t.is_solo) for t in ad.nla_tracks]
    prev_action = ad.action
    scene = context.scene
    saved_frame = scene.frame_current

    def fk():
        """Ma tran tu the trong khong gian armature, tu tinh tu matrix_basis."""
        P = {}
        for n in order:
            parent = arm.bones[n].parent
            base = rest[n].copy() if parent is None else \
                P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
            P[n] = base @ ob.pose.bones[n].matrix_basis
        return P

    try:
        # NLA phai im hoan toan, khong thi doc lan tu the cua track khac.
        for t, _, _ in muted:
            t.is_solo = False
            t.mute = True
        ad.action = src_action

        src_pose = {}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            src_pose[f] = fk()

        obj_vals = _object_level(src_action)

        old = bpy.data.actions.get(new_name)
        if old:
            bpy.data.actions.remove(old)
        new = bpy.data.actions.new(new_name)
        new.use_fake_user = True

        for pb in ob.pose.bones:
            pb.rotation_mode = 'QUATERNION'
        ad.action = new

        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            P = {}
            for n in order:
                parent = arm.bones[n].parent
                src = mirror_name(n)
                if src not in src_pose[f]:
                    src = n
                Pm = Mx @ src_pose[f][src] @ Mx
                rot = Pm.to_quaternion().to_matrix().to_4x4()

                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
                loc = Pm.translation if parent is None else base.translation
                P[n] = Matrix.Translation(loc) @ rot
                ob.pose.bones[n].matrix_basis = base.inverted() @ P[n]

            # Ghi DU kenh: thieu kenh cap object la nhan vat sai scale khi export.
            for path, idx in obj_vals:
                v = obj_vals[(path, idx)]
                if path == "location":
                    ob.location[idx] = v
                elif path == "rotation_euler":
                    ob.rotation_euler[idx] = v
                elif path == "scale":
                    ob.scale[idx] = v
            for path in sorted({p for p, _ in obj_vals}):
                ob.keyframe_insert(path, frame=f)

            for pb in ob.pose.bones:
                pb.keyframe_insert("rotation_quaternion", frame=f)
                pb.keyframe_insert("location", frame=f)
                pb.keyframe_insert("scale", frame=f)

        for fc in new.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'

        if not obj_vals:
            report.append("Action goc khong co kenh cap object nen ban moi cung "
                          "khong co. Kiem tra scale khi export.")
        return new, report
    finally:
        for t, m, s in muted:
            t.mute = m
            t.is_solo = s
        if ad.action is not None and ad.action.name != new_name:
            ad.action = prev_action
        scene.frame_set(saved_frame)


def mirror_error(context, ob, src_action, dst_action):
    """Kiem chung: sai lech goc giua ban moi va anh guong ly thuyet, tinh bang do."""
    Mx = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    arm = ob.data
    rest = {b.name: b.matrix_local.copy() for b in arm.bones}
    order = hierarchy_order(arm)
    fr = src_action.frame_range
    f0, f1 = int(round(fr[0])), int(round(fr[1]))
    ad = ob.animation_data
    muted = [(t, t.mute, t.is_solo) for t in ad.nla_tracks]
    prev = ad.action
    scene = context.scene
    saved = scene.frame_current

    def fk():
        P = {}
        for n in order:
            parent = arm.bones[n].parent
            base = rest[n].copy() if parent is None else \
                P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
            P[n] = base @ ob.pose.bones[n].matrix_basis
        return P

    try:
        for t, _, _ in muted:
            t.is_solo = False
            t.mute = True
        ad.action = src_action
        A = {f: fk() for f in (scene.frame_set(f) or f for f in range(f0, f1 + 1))}
        ad.action = dst_action
        B = {f: fk() for f in (scene.frame_set(f) or f for f in range(f0, f1 + 1))}
        worst = 0.0
        name = ""
        for f in A:
            for n in order:
                src = mirror_name(n)
                if src not in A[f]:
                    src = n
                want = (Mx @ A[f][src] @ Mx).to_quaternion()
                got = B[f][n].to_quaternion()
                d = want.rotation_difference(got).angle
                d = math.degrees(min(d, 2 * math.pi - d))
                if d > worst:
                    worst, name = d, n
        return worst, name
    finally:
        for t, m, s in muted:
            t.mute = m
            t.is_solo = s
        ad.action = prev
        scene.frame_set(saved)
