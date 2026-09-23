"""Lật gương trái/phải một action.

Cách làm: **soi gương ma trận BIẾN DẠNG trong không gian armature**, không lật
dấu thành phần quaternion. Thứ điều khiển skin là ma trận biến dạng
`D = P @ rest⁻¹`, nên điều kiện để mesh biến dạng đúng ảnh gương là:

    D_b = Mx @ D_m @ Mx        (Mx: lật qua mặt phẳng YZ)

suy ra tư thế phải ghi cho xương b, lấy từ xương ĐỐI BÊN m:

    P_b = Mx @ P_m @ rest_m⁻¹ @ Mx @ rest_b

Mx là phép phản chiếu (det = -1) nên `Mx @ D @ Mx` vẫn là phép quay thuận. Cách
này khỏi phải đoán quy ước dấu quaternion của từng rig, và đúng kể cả khi hai bên
đặt trục xương khác nhau.

Lật thẳng ma trận tư thế (`Mx @ P @ Mx`) chỉ đúng khi rest pose đối xứng. Rig mua
ngoài rất hay có hai bên **vị trí đối xứng hoàn hảo nhưng roll ngược nhau 180°**;
khi đó xương về đúng chỗ mà **mesh rách nát** — đo bằng chỉ số méo cạnh thì bản
lật cho 257–268 cạnh méo trong khi clip bình thường chỉ 15–66.

Ba bài học đắt giá đã gói vào đây:

1. **Sao đủ kênh.** Action gốc thường có cả 9 fcurve cấp OBJECT (location /
   rotation_euler / scale). Nếu bản lật gương chỉ có kênh của xương, trong
   Blender vẫn trông đúng — nhưng khi export sang engine, clip gốc *điều khiển*
   scale về 0.01 còn clip mới không điều khiển gì, nên root giữ scale 1 và nhân
   vật to gấp 100 lần. Lỗi chỉ lộ ở đầu ra, không lộ trong viewport.

2. **Tự tính FK.** `pose_bone.matrix` có thể còn cũ sau `frame_set` ở một số ngữ
   cảnh chạy script, làm mọi phép đo ra 0 và tưởng animation đứng yên. Ở đây
   dựng ma trận từ `matrix_basis` + rest nên luôn đúng.

3. **Lấy vị trí gương cho mọi xương, không chỉ xương gốc.** Rig kiểu IK mang vị
   trí thật trên cổ chân/cổ tay; dựng lại vị trí từ rest là vứt sạch chỗ đặt bàn
   chân, nhân vật tụt hẳn xuống dưới mặt đất.
"""

import math

import bpy
from mathutils import Matrix, Quaternion

from . import core


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
    for fc in core.action_fcurves(action):
        if fc.data_path.startswith("pose.bones"):
            continue
        if fc.data_path not in ("location", "rotation_euler",
                                "rotation_quaternion", "scale"):
            continue
        out[(fc.data_path, fc.array_index)] = fc.evaluate(action.frame_range[0])
    return out


def _bind_slot(ad, action):
    """Xem core.bind_slot(). Giu ten cu o day cho khoi doi het cho goi."""
    return core.bind_slot(ad, action)


def mirror_action(context, ob, src_action, new_name, clone=True):
    """Tao action moi la anh guong trai/phai cua `src_action`.

    clone=True (mac dinh, va la duong ma UI dung)
        Nhan doi action goc roi lat de len. Giu duoc marker, custom property,
        fcurve modifier, channel group, va bao dam do phu kenh y het ban goc —
        ke ca 9 fcurve cap object, thu ma neu thieu se lam engine hien nhan vat
        sai scale. Doi lai: fcurve rac cua ban goc (vi du kenh cho xuong khong
        con ton tai) cung theo sang.

    clone=False
        Dung action rong roi ghi lai tung kenh tu the. Ket qua sach hon nhung
        moi thu khong phai kenh tu the deu mat. Giu lai vi doi khi can dung
        chinh cai tinh chat "sach" do.

    Tra ve (action_moi, canh_bao).
    """
    if ob is None or ob.type != 'ARMATURE':
        raise MirrorError("Chua chon armature.")
    if src_action is None:
        raise MirrorError("Chua chon action can lat guong.")

    report = []
    arm = ob.data

    # Action cua rig KHAC se khong dieu khien xuong nao o day: lat guong van
    # "chay" nhung chi bake ra tu the dung im — nguoi dung tuong mirror hong.
    n_pose = n_match = 0
    for fc in core.action_fcurves(src_action):
        if not fc.data_path.startswith("pose.bones["):
            continue
        n_pose += 1
        try:
            if fc.data_path.split('"')[1] in arm.bones:
                n_match += 1
        except IndexError:
            pass
    if n_pose and not n_match:
        raise MirrorError(
            "Action '%s' khong dieu khien xuong nao cua '%s' — no thuoc rig "
            "khac. Chon dung cap Armature/Action (vi du action da retarget "
            "thi nam tren rig dich)." % (src_action.name, ob.name))
    if arm.pose_position == 'REST':
        arm.pose_position = 'POSE'
        report.append("Armature dang o Rest Position, da chuyen sang Pose.")

    dt, da, worst = rest_symmetry_error(ob)
    if dt > 0.002 or da > 2.0:
        # Tu khi lat theo ma tran bien dang, rest lech khong con lam hong ket
        # qua nua — day chi la thong tin ve chinh cai rig.
        report.append("Rest pose khong doi xung (lech %.1f mm / %.1f do o '%s'). "
                      "Phep lat da bu duoc chuyen nay; ghi lai de biet dac diem "
                      "cua rig."
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
        _bind_slot(ad, src_action)

        src_pose = {}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            src_pose[f] = fk()

        obj_vals = _object_level(src_action)

        old = bpy.data.actions.get(new_name)
        if old:
            bpy.data.actions.remove(old)
        if clone:
            new = src_action.copy()
            new.name = new_name
            if new.name != new_name:
                report.append("Ten '%s' bi chiem, Blender doi thanh '%s'."
                              % (new_name, new.name))
        else:
            new = bpy.data.actions.new(new_name)
        new.use_fake_user = True

        for pb in ob.pose.bones:
            pb.rotation_mode = 'QUATERNION'
        ad.action = new
        _bind_slot(ad, new)

        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            P = {}
            for n in order:
                parent = arm.bones[n].parent
                src = mirror_name(n)
                if src not in src_pose[f]:
                    src = n
                # Lat MA TRAN BIEN DANG (D = P @ rest^-1), khong phai ma tran
                # tu the. Skin duoc dinh nghia theo rest, nen dieu kien de mesh
                # bien dang dung anh guong la D_b = Mx @ D_m @ Mx, suy ra
                # P_b = Mx @ P_m @ rest_m^-1 @ Mx @ rest_b. Dung ke ca khi rest
                # hai ben khong doi xung (roll trai/phai nguoc nhau) — truong
                # hop ma cong thuc cu (Mx @ P @ Mx) lam skin xoan rach.
                D = src_pose[f][src] @ rest[src].inverted()
                Pm = (Mx @ D @ Mx) @ rest[n]
                rot = Pm.to_quaternion().to_matrix().to_4x4()

                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
                # Moi xuong lay vi tri guong cua chinh no, khong dung lai tu
                # rest: rig kieu IK mang vi tri that tren xuong co chan/co tay,
                # dung base.translation la vut sach vi tri do va chan roi tu do.
                P[n] = Matrix.Translation(Pm.translation) @ rot
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

        for fc in core.action_fcurves(new):
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
        _bind_slot(ad, src_action)
        A = {f: fk() for f in (scene.frame_set(f) or f for f in range(f0, f1 + 1))}
        ad.action = dst_action
        _bind_slot(ad, dst_action)
        B = {f: fk() for f in (scene.frame_set(f) or f for f in range(f0, f1 + 1))}
        worst = 0.0
        name = ""
        for f in A:
            for n in order:
                src = mirror_name(n)
                if src not in A[f]:
                    src = n
                # Cung cong thuc bien dang nhu mirror_action, neu khong ham nay
                # se bao sai lech gia tren dung rig ma no can kiem chung nhat.
                D = A[f][src] @ rest[src].inverted()
                want = ((Mx @ D @ Mx) @ rest[n]).to_quaternion()
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
