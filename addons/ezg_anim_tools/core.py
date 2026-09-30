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

from .ezg_i18n import tr


class RetargetError(Exception):
    pass


def bind_slot(ad, action):
    """Blender 4.4+ dung slotted action: gan action xong con phai co slot.

    Blender tu noi lai slot theo TEN khi doi action, nen viec nay chi can thiet
    trong mot truong hop — va do la truong hop hay gap nhat o day: action sinh
    ra tren rig khac (import FBX, rig nguon) co slot mang ten rig do. Ten khong
    khop object hien tai thi `action_slot` ve None, action duoc lien ket nhung
    KHONG dieu khien gi ca — tu the dung im, khong mot dong bao loi.

    Chi noi khi dang trong (`is None`). Ep noi lai luon se de cho action nhieu
    slot bi keo ve slot dau, sai slot dang dung dung.
    """
    if not hasattr(ad, "action_slot"):
        return False
    if ad.action_slot is not None:
        return False
    cands = list(getattr(ad, "action_suitable_slots", None) or ())
    if not cands:
        cands = list(getattr(action, "slots", None) or ())
    if not cands:
        return False
    try:
        ad.action_slot = cands[0]
    except Exception:
        return False
    return True


def action_fcurves(action):
    """Moi F-Curve cua action, ke ca action co slot (Blender 4.4+).

    `action.fcurves` la loi vao cu; voi action nhieu slot no khong nhin thay
    het kenh, nen moi phep dem/do phai di qua day.
    """
    out = []
    for layer in getattr(action, "layers", ()):
        for strip in layer.strips:
            if getattr(strip, "type", "KEYFRAME") != 'KEYFRAME':
                continue
            for slot in action.slots:
                try:
                    bag = strip.channelbag(slot)
                except Exception:
                    bag = None
                if bag is not None:
                    out.extend(bag.fcurves)
    # Blender 5.x da BO han thuoc tinh nay; 4.x thi van con cho action chua
    # co slot. getattr de ban 5.x khong chet voi AttributeError.
    return out or list(getattr(action, "fcurves", ()) or ())


def action_is_static(action, tol=1e-6):
    """Moi kenh cua action deu la hang so."""
    for fc in action_fcurves(action):
        vals = [k.co[1] for k in fc.keyframe_points]
        if vals and (max(vals) - min(vals)) > tol:
            return False
    return True


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


def is_descendant(arm, ancestor, name):
    """`name` co nam duoi `ancestor` trong cay xuong khong."""
    b = arm.bones.get(name)
    while b is not None:
        b = b.parent
        if b is not None and b.name == ancestor:
            return True
    return False


def build_alignment(src_ob, tgt_ob, pairs):
    """Phép bù lệch rest pose cho từng xương đích -> {tên_xương: Matrix 3x3}.

    Xương không có xương con tin cậy được (bàn tay, mũi chân, đầu) thì kế thừa
    phép bù của xương cha: ở rest chúng gần như luôn cùng hướng với cha.
    """
    align = {}
    for p in pairs:
        sc, tc = p.get("src_child"), p.get("tgt_child")
        # `resolve_children` lay xuong theo VAI TRO ke tiep, khong kiem tra quan
        # he cha-con. Rig kieu IK co the tra ve xuong o NHANH KHAC (co chan IK
        # treo thang vao root, khong nam duoi dau goi): vector do huong chi khi
        # do la rac, ma tran can lech hang chuc do ma khong bao gi. Khong phai
        # hau due thi bo, de roi ve fallback ke thua phep can cua xuong cha.
        if sc and not is_descendant(src_ob.data, p["src"], sc):
            sc = None
        if tc and not is_descendant(tgt_ob.data, p["tgt"], tc):
            tc = None
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


def source_moves(context, src_ob, bone_names, frame_start, frame_end, tol=1e-6):
    """Tu the cua `src_ob` co thay doi qua khoang frame khong.

    `view_layer.update()` sau moi `frame_set` la bat buoc: thieu no thi
    `pose_bone.matrix` co the con la tu the cua frame truoc, va phep do nay se
    bao "dung im" cho moi rig.
    """
    names = [n for n in bone_names if n in src_ob.pose.bones]
    if not names:
        return False
    f0, f1 = int(frame_start), int(frame_end)
    frames = sorted({f0, (f0 + f1) // 2, f1})
    scene = context.scene
    saved = scene.frame_current
    try:
        samples = []
        for f in frames:
            scene.frame_set(f)
            context.view_layer.update()
            samples.append([src_ob.pose.bones[n].matrix.copy() for n in names])
        first = samples[0]
        for row in samples[1:]:
            for a, b in zip(row, first):
                if max(abs(a[i][j] - b[i][j])
                       for i in range(4) for j in range(4)) > tol:
                    return True
        return False
    finally:
        scene.frame_set(saved)


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
        raise RetargetError(tr("Chưa chọn đủ armature nguồn và đích.",
                               "Source and target armatures are not both set yet."))
    if src_ob == tgt_ob:
        raise RetargetError(tr("Nguồn và đích đang là cùng một armature.",
                               "Source and target are the same armature."))
    if not pairs:
        raise RetargetError(tr("Bảng ánh xạ xương đang rỗng.", "The bone mapping is empty."))

    ad = src_ob.animation_data
    if ad is None or ad.action is None:
        raise RetargetError(tr("Armature nguồn không có action nào đang gán.",
                               "The source armature has no action assigned."))

    # Ở Rest Position thì pose.bones[].matrix trả về rest, bake ra sẽ là một loạt
    # khung hình đứng yên mà không báo lỗi gì. Đã dính đúng một lần.
    for ob, nhan in ((src_ob, tr("nguồn", "source")), (tgt_ob, tr("đích", "target"))):
        if ob.data.pose_position == 'REST':
            ob.data.pose_position = 'POSE'
            report.append(tr("Armature %s đang ở Rest Position, đã chuyển sang Pose Position.",
                             "The %s armature was in Rest Position; switched it to Pose Position.")
                          % nhan)

    # Slot cua action nguon. Xem bind_slot(): action sinh ra tren rig khac mang
    # slot ten rig do, khong khop thi action nam do ma khong dieu khien gi.
    if bind_slot(ad, ad.action):
        report.append(tr("Action nguồn '%s' chưa nối Action Slot, đã nối lại.",
                         "Source action '%s' had no Action Slot assigned; assigned one.")
                      % ad.action.name)
    if hasattr(ad, "action_slot") and ad.action_slot is None:
        raise RetargetError(
            tr("Action '%s' không nối được Action Slot nào trên '%s' nên nó không "
               "điều khiển xương gì — bake sẽ ra một loạt khung hình đứng im. "
               "Gán lại action trong Action Editor rồi thử lại.",
               "Action '%s' could not be assigned to any Action Slot on '%s', so it "
               "drives no bones — baking would only produce static frames. "
               "Reassign the action in the Action Editor and try again.")
            % (ad.action.name, src_ob.name))

    src_bones = src_ob.data.bones
    tgt_bones = tgt_ob.data.bones
    pairs = [p for p in pairs
             if p.get("src") in src_bones and p.get("tgt") in tgt_bones]
    if not pairs:
        raise RetargetError(tr("Không có cặp xương nào tồn tại trên cả hai rig.",
                               "None of the bone pairs exist on both rigs."))

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
            report.append(tr("Không xác định được xương hông, bỏ qua tịnh tiến.",
                             "Could not identify the hips bone; skipped the translation."))
        elif tgt_bones[ht].use_connect:
            report.append(tr("Xương hông bên đích đang Connected nên không tịnh tiến được.",
                             "The target hips bone is Connected, so it cannot be translated."))
        else:
            hips_tgt, hips_src = ht, hs
            ratio = (hips_scale if hips_scale is not None
                     else auto_hips_scale(src_ob, tgt_ob, hips_src, hips_tgt))
            hips_rest_src_w = rest_head_world(src_ob, hips_src)
            hips_rest_tgt_w = rest_head_world(tgt_ob, hips_tgt)

    # Chot cuoi truoc khi bake: action nguon co chuyen dong ma rig lai dung im
    # thi co thu gi do dang chan viec danh gia (driver, NLA solo, constraint...).
    # Ca bo loi nay deu hong AM THAM — du fcurve, du keyframe, khong exception —
    # nen phai bat bang gia tri, khong the trong vao co che bao loi cua Blender.
    if not action_is_static(ad.action) and not source_moves(
            context, src_ob, [p["src"] for p in pairs], frame_start, frame_end):
        raise RetargetError(
            tr("Action '%s' có chuyển động nhưng tư thế của '%s' không đổi qua các "
               "frame. Kiểm tra driver, NLA (track đang solo?) hoặc constraint đang "
               "khoá xương. Bake lúc này chỉ ra khung hình đứng im.",
               "Action '%s' has motion but the pose of '%s' does not change across "
               "frames. Check drivers, the NLA (a soloed track?) or constraints "
               "locking the bones. Baking now would only produce static frames.")
            % (ad.action.name, src_ob.name))

    # --- Truyen vi tri per-bone (rig kieu IK) ------------------------------
    # Rig IK treo co chan/co tay thanh nhanh rieng vao root: VI TRI cua chung
    # moi la diem dat ban chan, khong phai goc xoay. Chi truyen goc thi co chan
    # dung nguyen o rest trong khi than di chuyen -> chan keo gian.
    #
    # Dat theo huong cua rig nguon nhung DAI theo ti le chi cua rig dich, do tu
    # mot xuong neo do nguoi dung chon. Khong tu doan xuong neo: neo co chan vao
    # dau goi cho ket qua tot hon han neo vao hong, ma chi nguoi dung biet rig
    # cua minh dung kieu nao.
    src_of_tgt = {p["tgt"]: p["src"] for p in pairs}
    pos_rules = []
    for p in pairs:
        if not p.get("pos"):
            continue
        name, a_tgt = p["tgt"], p.get("anchor")
        if not a_tgt:
            report.append(tr("'%s' bật truyền vị trí nhưng chưa chọn xương neo, bỏ qua.",
                             "'%s' has position transfer on but no anchor bone; skipped.")
                          % name)
            continue
        a_src = src_of_tgt.get(a_tgt)
        if a_src is None:
            report.append(tr("Xương neo '%s' của '%s' không có trong bảng ánh xạ, bỏ qua.",
                             "Anchor bone '%s' of '%s' is not in the bone mapping; skipped.")
                          % (a_tgt, name))
            continue
        if tgt_bones[name].use_connect:
            # Blender bo qua location cua xuong Connected: co key cung vo ich.
            report.append(tr("'%s' đang Connected nên không nhận vị trí được, bỏ qua.",
                             "'%s' is Connected, so it cannot take a position; skipped.")
                          % name)
            continue
        d_src = (rest_head_world(src_ob, p["src"])
                 - rest_head_world(src_ob, a_src)).length
        d_tgt = (rest_head_world(tgt_ob, name)
                 - rest_head_world(tgt_ob, a_tgt)).length
        if d_src < 1e-9:
            report.append(tr("'%s' trùng vị trí với xương neo ở rest, bỏ qua truyền vị trí.",
                             "'%s' shares its rest position with the anchor bone; "
                             "skipped the position transfer.")
                          % name)
            continue
        pos_rules.append((name, p["src"], a_tgt, a_src, d_tgt / d_src))

    # Theo thu tu cay: xuong neo phai duoc chot vi tri truoc khi xuong khac do
    # theo no. `hierarchy_order` da la cha-truoc-con.
    rank = {n: i for i, n in enumerate(order)}
    pos_rules.sort(key=lambda r: rank.get(r[0], 0))
    pos_names = {r[0] for r in pos_rules}

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

        # Pass 2: dat lai VI TRI cho cac xuong IK. Phai lam sau vong tren vi
        # xuong neo co the dung SAU trong thu tu duyet (co chan IK treo vao root
        # thuong di truoc ca chuoi dui-goi), luc do chua co vi tri de ma do.
        for name, s_name, a_tgt, a_src, k in pos_rules:
            v = ((Ms @ src_ob.pose.bones[s_name].matrix).translation
                 - (Ms @ src_ob.pose.bones[a_src].matrix).translation)
            want_w = (Mt @ pose[a_tgt].translation) + v * k
            loc = Mt_inv @ want_w

            old = pose[name]
            desired = (Matrix.Translation(loc)
                       @ old.to_quaternion().to_matrix().to_4x4())
            delta = desired.translation - old.translation
            pose[name] = desired

            bone = tgt_bones[name]
            parent = bone.parent
            base = rest[name].copy() if parent is None else \
                pose[parent.name] @ (rest[parent.name].inverted() @ rest[name])
            tgt_ob.pose.bones[name].matrix_basis = base.inverted() @ desired

            # Con chau chi tinh tien theo, huong khong doi — cap nhat de xuong
            # neo cua luat sau doc duoc vi tri dung.
            for child in bone.children_recursive:
                if child.name in pose:
                    pose[child.name] = (Matrix.Translation(delta)
                                        @ pose[child.name])

        for name in smap:
            pb = tgt_ob.pose.bones[name]
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if name == hips_tgt or name in pos_names:
                pb.keyframe_insert("location", frame=f)

    for fc in action_fcurves(act):
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
