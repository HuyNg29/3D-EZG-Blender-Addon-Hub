"""Thêm nhịp nhún cho animation, giữ bàn chân dính sàn bằng IK hai xương.

Hông là xương GỐC, nên hạ hông xuống là cả bàn chân chìm theo. Cách sai (đã thử
và bỏ): gập gối rồi bù lại độ cao hông — gập gối đẩy bàn chân đi **ngang** mà
phép bù chỉ kéo được theo chiều **dọc**, kết quả chân trượt hàng centimet.

Cách đúng ở đây: **ghim mặt cổ chân**, hạ hông theo nhịp, rồi giải ngược đùi và
cẳng chân bằng IK hai xương để cổ chân vẫn nằm đúng chỗ cũ. Bàn chân bị ép về
hướng xoay trung bình nên luôn áp phẳng sàn.

Ba chi tiết quan trọng:

* **Ghim vào vị trí TRUNG BÌNH của cả vòng.** Nhờ vậy hàm này xoá luôn phần
  trượt chân vốn đã có sẵn trong animation, chứ không chỉ tránh gây thêm.
* **Hướng gập gối ép về phía trước.** Nếu lấy vị trí gối hiện có làm pole thì
  chân nào gần thẳng sẽ có thành phần vuông góc bé tí và nhiễu, bộ giải chọn
  nhầm phía và gối gập NGƯỢC. Chỉ mượn phần lệch ngang của nó để giữ độ xoè.
* **Đặt độ cao hông TUYỆT ĐỐI** (mốc là đỉnh nhịp, tức hông cao nhất trong
  vòng) thay vì cộng thêm. Nhờ vậy chạy lại không bị nhún chồng lên nhún.
"""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import roles


class BounceError(Exception):
    pass


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


def mean_quat(qs):
    """Quaternion trung bình. Đồng dấu trước khi cộng, không thì chúng triệt tiêu."""
    ref = qs[0]
    acc = [0.0, 0.0, 0.0, 0.0]
    for q in qs:
        s = 1.0 if q.dot(ref) >= 0 else -1.0
        for i in range(4):
            acc[i] += s * q[i]
    q = Quaternion(acc)
    q.normalize()
    return q


def find_legs(ob):
    """{'hips': ten, 'L': {...}, 'R': {...}} tu bo nhan dien vai tro."""
    found = roles.auto_map(ob.data)
    out = {}
    hips = found.get(("hips", ""))
    if not hips:
        raise BounceError("Khong tim thay xuong hong tren rig nay.")
    out["hips"] = hips
    for side in ("L", "R"):
        leg = {}
        for role, key in (("thigh", "thigh"), ("shin", "shin"),
                          ("foot", "foot"), ("toe", "toe")):
            name = found.get((role, side))
            if name:
                leg[key] = name
        missing = [k for k in ("thigh", "shin", "foot") if k not in leg]
        if missing:
            raise BounceError("Chan %s thieu xuong: %s" % (side, ", ".join(missing)))
        out[side] = leg
    return out


def solve_ik(hip_w, ankle_w, l1, l2, lateral, forward):
    """Tra ve (huong_dui, huong_cang_chan) trong he the gioi."""
    d = ankle_w - hip_w
    dist = d.length
    if dist < 1e-6:
        return Vector((0, 0, -1)), Vector((0, 0, -1))
    dist = max(min(dist, l1 + l2 - 1e-5), abs(l1 - l2) + 1e-5)
    u = d.normalized()

    # Ep goi ve phia truoc, chi muon phan lech NGANG cua goi hien tai de giu
    # do xoe. Lay thang vi tri goi lam pole se gap nguoc o chan gan thang.
    pole = forward + lateral
    perp = pole - u * pole.dot(u)
    if perp.length < 1e-6:
        perp = forward - u * forward.dot(u)
        if perp.length < 1e-6:
            perp = Vector((1.0, 0.0, 0.0))
    perp.normalize()

    cos_a = max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)))
    a = math.acos(cos_a)
    thigh_dir = (u * math.cos(a) + perp * math.sin(a)).normalized()
    knee = hip_w + thigh_dir * l1
    return thigh_dir, (ankle_w - knee).normalized()


def add_bounce(context, ob, action, depth, cycles):
    """Ghi nhip nhun vao `action`. Tra ve (bao_cao, so_do).

    depth  : do ha hong o day nhip, don vi met
    cycles : so nhip moi vong. PHAI la so nguyen, khong thi vong lap se giat.
    """
    if ob is None or ob.type != 'ARMATURE':
        raise BounceError("Chua chon armature.")
    if action is None:
        raise BounceError("Chua chon action.")
    if cycles < 1:
        raise BounceError("So nhip phai tu 1 tro len.")

    report = []
    arm = ob.data
    if arm.pose_position == 'REST':
        arm.pose_position = 'POSE'
        report.append("Armature dang o Rest Position, da chuyen sang Pose.")

    legs = find_legs(ob)
    hips = legs["hips"]
    M = ob.matrix_world
    Rt = M.to_3x3().normalized()
    Rt_inv = Rt.inverted()
    scale = M.to_scale()[0]
    if abs(scale) < 1e-9:
        raise BounceError("Armature co scale bang 0.")

    rest = {b.name: b.matrix_local.copy() for b in arm.bones}
    order = hierarchy_order(arm)

    fr = action.frame_range
    f0, f1 = int(round(fr[0])), int(round(fr[1]))
    period = max(f1 - f0 + 1, 1)

    ad = ob.animation_data
    if ad is None:
        raise BounceError("Armature khong co animation data.")
    muted = [(t, t.mute, t.is_solo) for t in ad.nla_tracks]
    prev_action = ad.action
    scene = context.scene
    saved_frame = scene.frame_current

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
        ad.action = action

        BS, W = {}, {}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            BS[f] = {n: ob.pose.bones[n].matrix_basis.copy() for n in order}
            P = fk()
            W[f] = {n: (M @ P[n]) for n in order}

        # --- Muc tieu ghim: trung binh ca vong -> xoa luon truot co san ---
        pin = {}
        for s in ("L", "R"):
            leg = legs[s]
            n = len(W)
            pin[s] = {
                "ankle": sum((W[f][leg["foot"]].translation for f in W), Vector()) / n,
                "knee": sum((W[f][leg["shin"]].translation for f in W), Vector()) / n,
                "foot_rot": mean_quat([W[f][leg["foot"]].to_quaternion() for f in W]),
            }

        # --- Huong mat: lay tu vector co chan -> mui chan, chieu xuong mat ngang.
        # Tu do ra chu khong hardcode, de rig quay huong nao cung dung.
        fwd = Vector((0.0, 0.0, 0.0))
        for s in ("L", "R"):
            toe = legs[s].get("toe")
            if not toe:
                continue
            for f in W:
                v = W[f][toe].translation - W[f][legs[s]["foot"]].translation
                fwd += Vector((v.x, v.y, 0.0))
        if fwd.length < 1e-9:
            fwd = Vector((0.0, -1.0, 0.0))
            report.append("Rig khong co xuong mui chan, gia dinh mat quay -Y.")
        fwd.normalize()

        lat = {}
        for s in ("L", "R"):
            p = pin[s]["knee"] - pin[s]["ankle"]
            lat[s] = Vector((p.x, 0.0, 0.0))

        L = {}
        for s in ("L", "R"):
            leg = legs[s]
            h = M @ rest[leg["thigh"]].translation
            k = M @ rest[leg["shin"]].translation
            a = M @ rest[leg["foot"]].translation
            L[s] = ((k - h).length, (a - k).length)

        # Moc do cao: hong CAO NHAT trong vong = dinh nhip. Dat tuyet doi nen
        # chay lai khong nhun chong nhun.
        base_z = max(W[f][hips].translation.z for f in W)
        reach = min(L["L"][0] + L["L"][1], L["R"][0] + L["R"][1])

        leg_bones = set()
        for s in ("L", "R"):
            leg_bones |= {legs[s]["thigh"], legs[s]["shin"], legs[s]["foot"]}

        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            t = (f - f0) / period
            dz = -depth * (1.0 - math.cos(2 * math.pi * cycles * t)) / 2.0
            need = (base_z + dz) - W[f][hips].translation.z
            offs = (Rt_inv @ Vector((0.0, 0.0, need))) / scale

            P = {}
            dirs = {}
            for n in order:
                parent = arm.bones[n].parent
                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])

                if n == hips:
                    p = base @ BS[f][n]
                    p = Matrix.Translation(p.translation + offs) @ \
                        p.to_quaternion().to_matrix().to_4x4()
                elif n in leg_bones:
                    s = "L" if n in (legs["L"]["thigh"], legs["L"]["shin"],
                                     legs["L"]["foot"]) else "R"
                    if n == legs[s]["thigh"]:
                        hip_w = (M @ base).translation
                        dirs[s] = solve_ik(hip_w, pin[s]["ankle"],
                                           L[s][0], L[s][1], lat[s], fwd)
                        want = dirs[s][0]
                        child = legs[s]["shin"]
                    elif n == legs[s]["shin"]:
                        want = dirs[s][1]
                        child = legs[s]["foot"]
                    else:
                        want = None

                    if want is not None:
                        off = (rest[n].inverted() @ rest[child]).translation
                        cur = (Rt @ base.to_3x3() @ off).normalized()
                        rot = Rt_inv @ cur.rotation_difference(want).to_matrix() \
                            @ Rt @ base.to_3x3()
                        p = Matrix.Translation(base.translation) @ rot.to_4x4()
                    else:
                        rot_arm = Rt_inv @ pin[s]["foot_rot"].to_matrix()
                        p = Matrix.Translation(base.translation) @ rot_arm.to_4x4()
                else:
                    p = base @ BS[f][n]

                P[n] = p

            for n in order:
                parent = arm.bones[n].parent
                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
                ob.pose.bones[n].matrix_basis = base.inverted() @ P[n]

            for n in {hips} | leg_bones:
                pb = ob.pose.bones[n]
                pb.keyframe_insert("rotation_quaternion", frame=f)
                if n == hips:
                    pb.keyframe_insert("location", frame=f)

        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'

        # --- Do lai ------------------------------------------------------
        hz, ank, knee_fwd = [], [], []
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            P = fk()
            hz.append((M @ P[hips]).translation.z)
            ank.append([(M @ P[legs[s]["foot"]]).translation.copy() for s in ("L", "R")])
            for s in ("L", "R"):
                h = (M @ P[legs[s]["thigh"]]).translation
                k = (M @ P[legs[s]["shin"]]).translation
                a = (M @ P[legs[s]["foot"]]).translation
                u = (a - h)
                if u.length < 1e-9:
                    continue
                u.normalize()
                perp = (k - h) - u * (k - h).dot(u)
                knee_fwd.append(perp.dot(fwd))

        drift = 0.0
        for i in range(len(ank)):
            for j in range(i + 1, len(ank)):
                for k in range(2):
                    drift = max(drift, (ank[i][k] - ank[j][k]).length)

        if depth > reach * 0.5:
            report.append("Do nhun %.3f m kha sau so voi chieu dai chan %.3f m."
                          % (depth, reach))
        if knee_fwd and min(knee_fwd) <= 0.0:
            report.append("Co frame goi gap NGUOC (lech %.4f m ve phia sau)."
                          % -min(knee_fwd))

        stats = {
            "bounce": max(hz) - min(hz),
            "drift": drift,
            "knee_min": min(knee_fwd) if knee_fwd else 0.0,
            "frames": period,
        }
        return report, stats
    finally:
        for t, m, s in muted:
            t.mute = m
            t.is_solo = s
        if ad.action is not action:
            ad.action = prev_action
        scene.frame_set(saved_frame)


TORSO_ROLES = ("spine", "chest", "neck", "head")


def amplify_motion(context, ob, action, factor):
    """Đẩy chuyển động của thân xa tư thế trung bình gấp `factor` lần.

    KHÔNG idempotent: chạy hai lần là nhân hai lần. Hông cố ý bị loại, vì xoay
    hông kéo chân đi ngang mà hàm này không giải lại chân.
    """
    if ob is None or ob.type != 'ARMATURE':
        raise BounceError("Chua chon armature.")
    if action is None:
        raise BounceError("Chua chon action.")

    found = roles.auto_map(ob.data)
    names = [found[(r, "")] for r in TORSO_ROLES if (r, "") in found]
    for side in ("L", "R"):
        if ("shoulder", side) in found:
            names.append(found[("shoulder", side)])
    if not names:
        raise BounceError("Khong nhan ra xuong than nao tren rig nay.")

    arm = ob.data
    if arm.pose_position == 'REST':
        arm.pose_position = 'POSE'

    fr = action.frame_range
    f0, f1 = int(round(fr[0])), int(round(fr[1]))
    ad = ob.animation_data
    muted = [(t, t.mute, t.is_solo) for t in ad.nla_tracks]
    prev = ad.action
    scene = context.scene
    saved = scene.frame_current

    try:
        for t, _, _ in muted:
            t.is_solo = False
            t.mute = True
        ad.action = action

        B = {}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            B[f] = {n: ob.pose.bones[n].matrix_basis.copy() for n in names}

        mean = {n: mean_quat([B[f][n].to_quaternion() for f in B]) for n in names}

        before = 0.0
        after = 0.0
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            for n in names:
                q = B[f][n].to_quaternion()
                d = mean[n].inverted() @ q
                ang = d.angle
                if ang > math.pi:
                    ang -= 2 * math.pi
                before = max(before, abs(math.degrees(ang)))
                if abs(ang) < 1e-6:
                    newq = q
                else:
                    newq = mean[n] @ Quaternion(d.axis, ang * factor)
                after = max(after, abs(math.degrees(ang * factor)))
                loc = B[f][n].to_translation()
                ob.pose.bones[n].matrix_basis = \
                    Matrix.Translation(loc) @ newq.to_matrix().to_4x4()
                ob.pose.bones[n].keyframe_insert("rotation_quaternion", frame=f)

        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'

        return len(names), before, after
    finally:
        for t, m, s in muted:
            t.mute = m
            t.is_solo = s
        if ad.action is not action:
            ad.action = prev
        scene.frame_set(saved)
