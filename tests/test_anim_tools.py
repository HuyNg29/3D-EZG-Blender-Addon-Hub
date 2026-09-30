"""EZG Retarget phai chuyen dung chuyen dong giua hai rig KHAC HAN nhau.

Hai rig trong test co chu dich khac nhau o moi chieu co the khac:

  nguon  A-pose, cao 1.7m, don vi met, Z-up, object khong xoay,
         ten xuong kieu game/Maya  (hip, L_UpArm, L_Knee...)
  dich   T-pose, chibi chan ngan dau to, don vi CENTIMET, data Y-up,
         object scale 0.01 + xoay X 90 do, ten xuong kieu Mixamo

Cai bay lon nhat cua retarget la **rest pose hai ben khac nhau**. Test do sai
lech bang GOC huong chi (khong phai vi tri — hai nhan vat khac ti le co the thi
khong the khop vi tri), va bat buoc phai chung minh ca chieu nguoc lai: TAT phep
bu rest pose thi sai so phai VOT LEN. Neu khong co ve nay, mot bug lam phep bu
tro thanh vo hieu se lot qua ma khong ai biet.

CHAY BANG tools\\run_tests.ps1.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

import bpy  # noqa: E402
from mathutils import Euler, Matrix, Quaternion, Vector  # noqa: E402

FAILED = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


def build(name, bones, scale=1.0, rot_x=0.0):
    """bones: list (ten, head, tail, ten_cha). Toa do trong DATA space."""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    made = {}
    for bname, head, tail, parent in bones:
        eb = arm.edit_bones.new(bname)
        eb.head, eb.tail = Vector(head), Vector(tail)
        if parent:
            eb.parent = made[parent]
        made[bname] = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.scale = (scale, scale, scale)
    ob.rotation_euler = Euler((rot_x, 0.0, 0.0), 'XYZ')
    bpy.context.view_layer.update()
    return ob


# --- Rig nguon: A-pose, met, Z-up, ten kieu game -----------------------------
def src_bones():
    b = [
        ("hip",   (0, 0, 0.95), (0, 0, 1.05), None),
        ("spine", (0, 0, 1.05), (0, 0, 1.25), "hip"),
        ("Chest", (0, 0, 1.25), (0, 0, 1.45), "spine"),
        ("Head",  (0, 0, 1.45), (0, 0, 1.70), "Chest"),
    ]
    for s, x in (("L", 1.0), ("R", -1.0)):
        b += [
            ("%s_Shoulder" % s, (0.05 * x, 0, 1.42), (0.15 * x, 0, 1.42), "Chest"),
            # A-pose: tay xuoi cheo 45 do
            ("%s_UpArm" % s,    (0.15 * x, 0, 1.42), (0.35 * x, 0, 1.22), "%s_Shoulder" % s),
            ("%s_ForeArm" % s,  (0.35 * x, 0, 1.22), (0.55 * x, 0, 1.02), "%s_UpArm" % s),
            ("%s_hand" % s,     (0.55 * x, 0, 1.02), (0.63 * x, 0, 0.94), "%s_ForeArm" % s),
            ("%s_thigh" % s,    (0.10 * x, 0, 0.95), (0.10 * x, 0, 0.52), "hip"),
            ("%s_Knee" % s,     (0.10 * x, 0, 0.52), (0.10 * x, 0, 0.10), "%s_thigh" % s),
            ("%s_foot" % s,     (0.10 * x, 0, 0.10), (0.10 * x, -0.15, 0.04), "%s_Knee" % s),
            ("%s_toe" % s,      (0.10 * x, -0.15, 0.04), (0.10 * x, -0.25, 0.04), "%s_foot" % s),
        ]
    return b


# --- Rig dich: T-pose, chibi, centimet, data Y-up, ten Mixamo ---------------
def tgt_bones():
    m = "mixamorig:"
    b = [
        (m + "Hips",   (0, 22, 0), (0, 26, 0), None),
        (m + "Spine",  (0, 26, 0), (0, 30, 0), m + "Hips"),
        (m + "Spine2", (0, 30, 0), (0, 34, 0), m + "Spine"),
        (m + "Head",   (0, 34, 0), (0, 50, 0), m + "Spine2"),   # dau to
    ]
    for s, x in (("Left", 1.0), ("Right", -1.0)):
        b += [
            (m + s + "Shoulder", (2 * x, 33, 0), (5 * x, 33, 0), m + "Spine2"),
            # T-pose: tay dang ngang
            (m + s + "Arm",      (5 * x, 33, 0), (12 * x, 33, 0), m + s + "Shoulder"),
            (m + s + "ForeArm",  (12 * x, 33, 0), (18 * x, 33, 0), m + s + "Arm"),
            (m + s + "Hand",     (18 * x, 33, 0), (21 * x, 33, 0), m + s + "ForeArm"),
            (m + s + "UpLeg",    (3 * x, 22, 0), (3 * x, 12, 0), m + "Hips"),   # chan ngan
            (m + s + "Leg",      (3 * x, 12, 0), (3 * x, 4, 0), m + s + "UpLeg"),
            (m + s + "Foot",     (3 * x, 4, 0), (3 * x, 1, 4), m + s + "Leg"),
            (m + s + "ToeBase",  (3 * x, 1, 4), (3 * x, 1, 8), m + s + "Foot"),
        ]
    return b


def animate(ob, frames=8):
    """Cho rig nguon vai chuyen dong that: vung tay, xoay than, nhac dui."""
    ob.animation_data_create()
    act = bpy.data.actions.new("SrcMotion")
    ob.animation_data.action = act
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    moves = {
        "L_UpArm":  ('X', 55.0),
        "R_UpArm":  ('X', -40.0),
        "L_ForeArm": ('Z', 35.0),
        "spine":    ('Z', 18.0),
        "Chest":    ('X', -12.0),
        "L_thigh":  ('X', 25.0),
        "R_Knee":   ('X', -30.0),
        "Head":     ('Y', 20.0),
    }
    for f in range(1, frames + 1):
        t = math.sin(math.pi * (f - 1) / (frames - 1))
        bpy.context.scene.frame_set(f)
        for bone, (axis, deg) in moves.items():
            pb = ob.pose.bones[bone]
            pb.rotation_quaternion = Quaternion(
                {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[axis],
                math.radians(deg) * t)
            pb.keyframe_insert("rotation_quaternion", frame=f)
    bpy.context.scene.frame_set(1)
    return act


# ---------------------------------------------------------------------------
mod = kit.enable("ezg_anim_tools")
core, roles, mirror = mod.core, mod.roles, mod.mirror

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

src = build("SRC", src_bones())
tgt = build("TGT", tgt_bones(), scale=0.01, rot_x=math.radians(90))
animate(src)

# --- Tu doan bang anh xa giua hai quy uoc dat ten hoan toan khac nhau -------
pairs_raw = roles.pair_up(src.data, tgt.data)
got = {(r, s) for r, s, _, _ in pairs_raw}
expect = {("hips", ""), ("spine", ""), ("chest", ""), ("head", "")}
for side in ("L", "R"):
    for role in ("shoulder", "upperarm", "forearm", "hand",
                 "thigh", "shin", "foot", "toe"):
        expect.add((role, side))

missing = sorted(expect - got)
check(not missing, "auto map noi duoc het %d vai tro (thieu: %s)"
      % (len(expect), missing or "khong"))

by_role = {(r, s): (a, b) for r, s, a, b in pairs_raw}
check(by_role.get(("upperarm", "L")) == ("L_UpArm", "mixamorig:LeftArm"),
      "L_UpArm -> LeftArm (khong bi 'arm' nuot thanh forearm)")
check(by_role.get(("forearm", "L")) == ("L_ForeArm", "mixamorig:LeftForeArm"),
      "L_ForeArm -> LeftForeArm")
check(by_role.get(("thigh", "L")) == ("L_thigh", "mixamorig:LeftUpLeg"),
      "L_thigh -> LeftUpLeg (khong nham voi Leg)")
check(by_role.get(("chest", "")) == ("Chest", "mixamorig:Spine2"),
      "Chest -> Spine2")


# --- Rig game kieu LoL: ten xuong danh lua duoc bo tu khoa -------------------
# "L_Hip" la DUI (khong phai hips), "L_Shoulder" la BAP TAY (khong phai vai),
# "L_KneeUpper" la ong chan. Hoi quy cho bug that: hips bi gan nham vao L_Hip
# lam ca khung chau lai theo dui trai -> chan trai nhac han len sau retarget.
def lol_bones():
    b = [
        ("Root",   (0, 0, 1.00), (0, 0, 1.05), None),
        ("Spine1", (0, 0, 1.05), (0, 0, 1.25), "Root"),
        ("Chest",  (0, 0, 1.25), (0, 0, 1.45), "Spine1"),
        ("Neck",   (0, 0, 1.45), (0, 0, 1.55), "Chest"),
        ("Head",   (0, 0, 1.55), (0, 0, 1.70), "Neck"),
        ("Pelvis", (0, 0, 0.98), (0, 0, 0.90), "Root"),
    ]
    for s, x in (("L", 1.0), ("R", -1.0)):
        b += [
            ("%s_Clavicle" % s,  (0.03 * x, 0, 1.44), (0.15 * x, 0, 1.42), "Chest"),
            ("%s_Shoulder" % s,  (0.18 * x, 0, 1.41), (0.30 * x, 0, 1.20), "%s_Clavicle" % s),
            ("%s_Elbow" % s,     (0.30 * x, 0, 1.19), (0.40 * x, -0.10, 1.02), "%s_Shoulder" % s),
            ("%s_Hand" % s,      (0.40 * x, -0.10, 1.02), (0.46 * x, -0.15, 0.95), "%s_Elbow" % s),
            ("%s_Hip" % s,       (0.10 * x, 0, 0.96), (0.16 * x, 0, 0.55), "Pelvis"),
            # Cap xuong goi TRUNG DAU (lech vai phan van nhu rig that):
            # animation chi nam o KneeLower.
            ("%s_KneeUpper" % s, (0.16 * x, 0, 0.55), (0.23 * x, 0.05, 0.10), "%s_Hip" % s),
            ("%s_KneeLower" % s, (0.16 * x, 0.0003, 0.5501), (0.23 * x, 0.05, 0.10), "%s_KneeUpper" % s),
            ("%s_Foot" % s,      (0.23 * x, 0.05, 0.10), (0.25 * x, -0.08, 0.04), "%s_KneeLower" % s),
            ("%s_Toe" % s,       (0.25 * x, -0.08, 0.04), (0.25 * x, -0.15, 0.03), "%s_Foot" % s),
        ]
    return b


lol = build("LOL", lol_bones())
amap = roles.auto_map(lol.data)
check(amap.get(("hips", "")) == "Pelvis",
      "rig game: hips = Pelvis, khong bi 'L_Hip' cuop mat")
check(amap.get(("thigh", "L")) == "L_Hip" and amap.get(("thigh", "R")) == "R_Hip",
      "rig game: L_Hip/R_Hip duoc nhan la DUI nho cau truc cha-con")
check(amap.get(("upperarm", "L")) == "L_Shoulder",
      "rig game: L_Shoulder duoc nhan la bap tay (cha cua L_Elbow)")
check(amap.get(("shoulder", "L")) == "L_Clavicle",
      "rig game: shoulder van la L_Clavicle")
check(amap.get(("shin", "L")) == "L_KneeLower",
      "rig game: shin = L_KneeLower (cha truc tiep cua Foot, noi mang anim)")
lol_pairs = roles.pair_up(lol.data, tgt.data)
lol_got = {(r, s) for r, s, _, _ in lol_pairs}
check(lol_got >= expect,
      "rig game noi duoc du %d vai tro voi rig Mixamo (thieu: %s)"
      % (len(expect), sorted(expect - lol_got) or "khong"))
bpy.data.objects.remove(lol, do_unlink=True)


class Row:
    def __init__(self, role, side, s, t):
        self.role, self.side, self.src, self.tgt = role, side, s, t


rows = [Row(r, s, a, b) for r, s, a, b in pairs_raw]
pairs = roles.resolve_children(rows)
hips = next(p for p in pairs if p["role"] == "hips")

ctx = bpy.context
f0, f1 = 1, 8

# --- Co bu rest pose: sai so phai gan nhu bang 0 ---------------------------
core.retarget(ctx, src, tgt, pairs, f0, f1, "RT_Aligned",
              align_rest=True, use_hips_loc=True, hips_pair=hips)
good = core.measure_error(ctx, src, tgt, pairs, f0, f1)
print("    co bu rest: TB %.3f do, max %.3f do (%d mau)"
      % (good["mean"], good["max"], good["samples"]))
check(good["mean"] < 1.0, "co bu rest pose: lech goc trung binh < 1 do")
check(good["max"] < 2.5, "co bu rest pose: lech goc lon nhat < 2.5 do")

# --- Tat bu rest pose: sai so PHAI vot len, neu khong la phep bu vo hieu ----
core.retarget(ctx, src, tgt, pairs, f0, f1, "RT_Raw",
              align_rest=False, use_hips_loc=True, hips_pair=hips)
bad = core.measure_error(ctx, src, tgt, pairs, f0, f1)
print("    khong bu  : TB %.3f do, max %.3f do" % (bad["mean"], bad["max"]))
check(bad["mean"] > good["mean"] + 5.0,
      "tat bu rest pose thi sai so vot len (A-pose vs T-pose)")

# --- Tinh tien hong phai duoc quy doi theo ti le chieu cao ------------------
ratio = core.auto_hips_scale(src, tgt, "hip", "mixamorig:Hips")
h_src = core.rest_head_world(src, "hip").z
h_tgt = core.rest_head_world(tgt, "mixamorig:Hips").z
check(abs(ratio - h_tgt / h_src) < 1e-6, "he so quy doi hong = ti le chieu cao hong")
check(0.05 < ratio < 0.5, "chibi thap hon nhieu -> he so %.3f nam trong khoang hop li" % ratio)

# --- Rig dich xoay 90 do + scale 0.01 van phai dung huong ------------------
tgt.animation_data.action = bpy.data.actions["RT_Aligned"]
ctx.scene.frame_set(f1)
ctx.view_layer.update()
up = (tgt.matrix_world @ tgt.pose.bones["mixamorig:Head"].matrix).translation
hips_w = (tgt.matrix_world @ tgt.pose.bones["mixamorig:Hips"].matrix).translation
check(up.z > hips_w.z, "nhan vat dich van dung thang (dau cao hon hong)")

# --- Bao ve: rig nguon o Rest Position phai duoc phat hien -----------------
src.data.pose_position = 'REST'
_, rep = core.retarget(ctx, src, tgt, pairs, f0, f1, "RT_RestGuard",
                       align_rest=True, use_hips_loc=True, hips_pair=hips)
check(src.data.pose_position == 'POSE' and any("Rest Position" in r for r in rep),
      "phat hien va sua duoc rig nguon dang o Rest Position")

# ===========================================================================
# Mirror
# ===========================================================================
check(mirror.mirror_name("mixamorig:LeftForeArm") == "mixamorig:RightForeArm",
      "mirror_name: Mixamo LeftForeArm -> RightForeArm")
check(mirror.mirror_name("R_Knee") == "L_Knee", "mirror_name: tien to R_ -> L_")
check(mirror.mirror_name("hand.L") == "hand.R", "mirror_name: hau to .L -> .R")
check(mirror.mirror_name("thigh_r") == "thigh_l", "mirror_name: hau to _r -> _l")
check(mirror.mirror_name("mixamorig:Spine1") == "mixamorig:Spine1",
      "mirror_name: xuong giua than khong doi")

# Action cua rig khac phai bi TU CHOI thang, khong duoc im lang bake ra rac.
# Hoi quy cho bug that: mirror action nguon tren rig dich -> lech 144 do.
try:
    mirror.mirror_action(ctx, tgt, bpy.data.actions["SrcMotion"], "PhaiLoi")
    check(False, "mirror action cua rig khac phai nem MirrorError")
except mirror.MirrorError:
    check(True, "mirror action cua rig khac phai nem MirrorError")

# Rest cua rig dich doi xung, nen phai bao "khong lech"
dt, da, _ = mirror.rest_symmetry_error(tgt)
check(dt < 1e-4 and da < 0.5,
      "rest_symmetry_error: rig doi xung -> bao lech ~0 (%.5f m / %.3f do)" % (dt, da))

# Gan lai ban retarget tot roi them KENH CAP OBJECT vao action nguon.
# Day la hoi quy cho mot bug that: ban lat guong thieu 9 fcurve cap object thi
# trong Blender van dung nhung engine se hien nhan vat sai scale 100 lan.
src_act = bpy.data.actions["RT_Aligned"]
tgt.animation_data.action = src_act
for f in (f0, f1):
    ctx.scene.frame_set(f)
    for path in ("location", "rotation_euler", "scale"):
        tgt.keyframe_insert(path, frame=f)
n_obj_src = len([fc for fc in src_act.fcurves if not fc.data_path.startswith("pose.bones")])
check(n_obj_src == 9, "action nguon co 9 fcurve cap object (%d)" % n_obj_src)

new, rep = mirror.mirror_action(ctx, tgt, src_act, "RT_Aligned_Mirror")
n_obj_new = len([fc for fc in new.fcurves if not fc.data_path.startswith("pose.bones")])
check(n_obj_new == 9, "ban lat guong sao du 9 fcurve cap object (%d)" % n_obj_new)

got = {(fc.data_path, fc.array_index): round(fc.evaluate(f0), 6)
       for fc in new.fcurves if not fc.data_path.startswith("pose.bones")}
want = {(fc.data_path, fc.array_index): round(fc.evaluate(f0), 6)
        for fc in src_act.fcurves if not fc.data_path.startswith("pose.bones")}
check(got == want, "gia tri kenh cap object trung khop ban goc (scale 0.01, xoay 90 do)")

err, worst = mirror.mirror_error(ctx, tgt, src_act, new)
print("    lech so voi anh guong ly thuyet: %.5f do" % err)
check(err < 0.01, "lat guong chinh xac (< 0.01 do)")

# --- Ban clone: nhan doi action goc roi lat de len ------------------------
# Dat dau vet vao ban goc de chung minh clone mang theo, con ban dung action
# rong thi khong. Day chinh la khac biet giua hai nut.
src_act["ezg_test_tag"] = 4242
src_act.frame_range  # cham vao cho chac frame_range da tinh

cl, rep_cl = mirror.mirror_action(ctx, tgt, src_act, "RT_Aligned_Clone", clone=True)
check(cl.get("ezg_test_tag") == 4242,
      "clone mang theo custom property cua ban goc")
check(new.get("ezg_test_tag") is None,
      "ban dung action rong KHONG mang theo (dung nhu mo ta)")
check(len(cl.fcurves) >= len(src_act.fcurves),
      "clone co do phu kenh khong kem ban goc (%d vs %d)"
      % (len(cl.fcurves), len(src_act.fcurves)))

n_obj_cl = len([fc for fc in cl.fcurves if not fc.data_path.startswith("pose.bones")])
check(n_obj_cl == 9, "clone giu du 9 fcurve cap object (%d)" % n_obj_cl)

err_cl, _ = mirror.mirror_error(ctx, tgt, src_act, cl)
print("    ban clone lech: %.5f do" % err_cl)
check(err_cl < 0.01, "ban clone lat guong cung chinh xac (< 0.01 do)")


# ---------------------------------------------------------------------------
# Rig co rest KHONG doi xung ve huong (vi tri khop hoan hao, roll hai ben nguoc
# nhau 180 do). Rat pho bien o rig game mua ngoai.
#
# Lat thang ma tran tu the (Mx @ P @ Mx) dua xuong ve dung cho nhung XOAN SKIN:
# thu dieu khien mesh la ma tran bien dang D = P @ rest^-1, va dieu kien dung la
# D_lat = Mx @ D_goc @ Mx. Test do thang vao D nen bat duoc loi nay chinh xac,
# khong phu thuoc vao viec nhin mesh.
# ---------------------------------------------------------------------------
print("\n-- Rest lech roll 180 do --")

asym = build("AsymRig", [
    ("root",  (0, 0, 0.0), (0, 0, 0.2), None),
    ("L_up",  (0.1, 0, 0.0), (0.1, 0, 0.5), "root"),
    ("L_lo",  (0.1, 0, 0.5), (0.1, 0, 1.0), "L_up"),
    ("R_up",  (-0.1, 0, 0.0), (-0.1, 0, 0.5), "root"),
    ("R_lo",  (-0.1, 0, 0.5), (-0.1, 0, 1.0), "R_up"),
    # Xuong mang vi tri that, treo thang vao root nhu co chan IK.
    ("L_ik",  (0.1, 0, 1.0), (0.1, 0, 1.1), "root"),
    ("R_ik",  (-0.1, 0, 1.0), (-0.1, 0, 1.1), "root"),
])
bpy.context.view_layer.objects.active = asym
bpy.ops.object.mode_set(mode='EDIT')
for name in ("R_up", "R_lo", "R_ik"):
    asym.data.edit_bones[name].roll = math.pi      # lech 180 do so voi ben trai
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()

dt_a, da_a, _ = mirror.rest_symmetry_error(asym)
print("    rest lech: %.4f mm / %.1f do" % (dt_a * 1000.0, da_a))
check(dt_a < 1e-4, "rig thu nghiem: vi tri rest doi xung hoan hao")
check(da_a > 170.0, "rig thu nghiem: huong rest lech ~180 do (%.1f)" % da_a)

# Action tren ben TRAI: xoay + day xuong IK di mot doan that.
asym_act = bpy.data.actions.new("AsymMotion")
asym_act.use_fake_user = True
ad_a = asym.animation_data_create()
ad_a.action = asym_act
for pb in asym.pose.bones:
    pb.rotation_mode = 'QUATERNION'
for f, ang, dx in ((1, 0.0, 0.0), (10, 0.6, 0.25)):
    ctx.scene.frame_set(f)
    asym.pose.bones["L_up"].rotation_quaternion = Quaternion((0, 1, 0), ang)
    asym.pose.bones["L_lo"].rotation_quaternion = Quaternion((1, 0, 0), ang * 0.5)
    asym.pose.bones["L_ik"].location = Vector((dx, 0.0, -0.1))
    for n in ("L_up", "L_lo", "L_ik"):
        asym.pose.bones[n].keyframe_insert("rotation_quaternion", frame=f)
        asym.pose.bones[n].keyframe_insert("location", frame=f)

A_REST = {b.name: b.matrix_local.copy() for b in asym.data.bones}
A_ORDER = mirror.hierarchy_order(asym.data)


def fk_from_action(act, f):
    """Tu the trong khong gian armature, tinh THANG tu fcurve.

    Khong dung pose_bone.matrix: sau khi doi action/frame trong script no co the
    con la tu the cua clip truoc, va moi phep do se ra "moi clip deu giong nhau".
    """
    fcs = core.action_fcurves(act)
    P = {}
    for n in A_ORDER:
        q = [1.0, 0.0, 0.0, 0.0]
        loc = [0.0, 0.0, 0.0]
        for fc in fcs:
            if fc.data_path == 'pose.bones["%s"].rotation_quaternion' % n:
                q[fc.array_index] = fc.evaluate(f)
            elif fc.data_path == 'pose.bones["%s"].location' % n:
                loc[fc.array_index] = fc.evaluate(f)
        qq = Quaternion(q)
        qq.normalize()
        basis = Matrix.Translation(Vector(loc)) @ qq.to_matrix().to_4x4()
        parent = asym.data.bones[n].parent
        base = A_REST[n].copy() if parent is None else \
            P[parent.name] @ (A_REST[parent.name].inverted() @ A_REST[n])
        P[n] = base @ basis
    return P


def deform_gap(act_src, act_dst, frames):
    """max ||D_lat - Mx @ D_goc @ Mx||. Bang 0 nghia la skin bien dang dung guong."""
    Mx = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    worst = 0.0
    for f in frames:
        Ps, Pd = fk_from_action(act_src, f), fk_from_action(act_dst, f)
        for n in A_ORDER:
            s = mirror.mirror_name(n)
            if s not in Ps:
                s = n
            want = Mx @ (Ps[s] @ A_REST[s].inverted()) @ Mx
            got = Pd[n] @ A_REST[n].inverted()
            worst = max(worst, max(abs(want[i][j] - got[i][j])
                                   for i in range(4) for j in range(4)))
    return worst


asym_mir, _ = mirror.mirror_action(ctx, asym, asym_act, "AsymMotion_Mirror")
gap = deform_gap(asym_act, asym_mir, (1, 5, 10))
print("    sai lech ma tran bien dang: %.9f" % gap)
check(gap < 1e-5, "skin bien dang dung anh guong tren rig rest lech (%.2e)" % gap)

# Chung minh phep lat CU that su hong tren rig nay — neu khong, test tren se
# van dat ke ca khi ai do quay ve cong thuc cu.
Mx_t = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
old_gap = 0.0
for f in (1, 5, 10):
    Ps = fk_from_action(asym_act, f)
    for n in A_ORDER:
        s = mirror.mirror_name(n)
        if s not in Ps:
            s = n
        want = Mx_t @ (Ps[s] @ A_REST[s].inverted()) @ Mx_t
        old = (Mx_t @ Ps[s] @ Mx_t) @ A_REST[n].inverted()   # cong thuc cu
        old_gap = max(old_gap, max(abs(want[i][j] - old[i][j])
                                   for i in range(4) for j in range(4)))
print("    cong thuc cu lech: %.4f" % old_gap)
check(old_gap > 0.5,
      "cong thuc cu (Mx@P@Mx) that su sai tren rig nay -> test co y nghia")

# Loi 2: xuong IK mang vi tri that phai duoc lat, khong bi dung lai tu rest.
P_src = fk_from_action(asym_act, 10)
P_mir = fk_from_action(asym_mir, 10)
want_x = -P_src["L_ik"].translation.x
got_x = P_mir["R_ik"].translation.x
print("    vi tri xuong IK: goc L_ik x=%.4f -> lat R_ik x=%.4f (ky vong %.4f)"
      % (P_src["L_ik"].translation.x, got_x, want_x))
check(abs(got_x - want_x) < 1e-5, "vi tri xuong IK duoc lat dung, khong bi vut")
check(abs(P_mir["R_ik"].translation.z - P_src["L_ik"].translation.z) < 1e-5,
      "vi tri xuong IK giu nguyen do cao khi lat")


# ---------------------------------------------------------------------------
# build_alignment phai bo qua "xuong con" nam o nhanh khac (rig kieu IK)
# ---------------------------------------------------------------------------
print("\n-- Xuong con khac nhanh --")
check(core.is_descendant(asym.data, "L_up", "L_lo"),
      "is_descendant: L_lo nam duoi L_up")
check(not core.is_descendant(asym.data, "L_lo", "L_ik"),
      "is_descendant: L_ik KHONG nam duoi L_lo (nhanh rieng)")

cross = [{"role": "shin", "side": "L", "src": "L_lo", "tgt": "L_lo",
          "src_child": "L_ik", "tgt_child": "L_ik"}]
al = core.build_alignment(asym, asym, cross)
check(al["L_lo"] == Matrix.Identity(3),
      "build_alignment: xuong con khac nhanh -> roi ve fallback, khong lay rac")


# ---------------------------------------------------------------------------
# Action slot: action cua rig khac khong dieu khien gi, bake ra se dung im
# ---------------------------------------------------------------------------
print("\n-- Action Slot --")
if hasattr(ad_a, "action_slot"):
    foreign = asym_act.copy()
    foreign.name = "ForeignSlot"
    foreign.use_fake_user = True
    try:
        foreign.slots[0].name_display = "MotRigKhac"
    except Exception:
        pass
    ad_a.action = None
    ad_a.action = foreign
    check(ad_a.action_slot is None,
          "slot ten khac object -> Blender de trong (goc cua bug 'bake ra tinh')")
    check(core.bind_slot(ad_a, foreign), "bind_slot noi lai duoc slot dang trong")
    check(ad_a.action_slot is not None, "sau bind_slot da co slot")
    # Da co slot roi thi khong duoc doi nua: action nhieu slot se bi keo sai.
    check(not core.bind_slot(ad_a, foreign), "bind_slot khong doi slot dang dung")
    ad_a.action = asym_act
    core.bind_slot(ad_a, asym_act)

check(core.action_is_static(bpy.data.actions.new("Rong")),
      "action_is_static: action rong la tinh")
check(not core.action_is_static(asym_act),
      "action_is_static: action co chuyen dong khong bi bao tinh")


# ---------------------------------------------------------------------------
# Rig kieu IK: co chan treo thang vao root thanh nhanh rieng, VI TRI cua no moi
# la diem dat ban chan. Chi truyen goc xoay thi co chan dung yen o rest trong
# khi than di chuyen -> chi bi keo gian.
#
# Do bang **do gian cua doan goi->co chan** so voi rest. Day la phep do dung
# cho viec nay: hai rig khac ti le co the thi khong the khop vi tri tuyet doi,
# nhung mot cai chan khong duoc dai ra ngan lai.
# ---------------------------------------------------------------------------
print("\n-- Rig IK: truyen vi tri per-bone --")


def ik_bones(hip_z, knee_z):
    """root -> hip -> knee (chuoi FK), va ankle treo THANG vao root."""
    return [
        ("root",  (0, 0, 0.0), (0, 0, 0.1), None),
        ("hip",   (0, 0, hip_z), (0, 0, hip_z - 0.1), "root"),
        ("knee",  (0, 0, knee_z), (0, 0, knee_z - 0.1), "hip"),
        ("ankle", (0, 0, 0.05), (0, 0.1, 0.05), "root"),
    ]


# Hai nhan vat khac TI LE CHI, khong phai ban thu nho deu: dui/ong cua dich
# ngan hon han so voi chieu cao hong. Day moi la ca ma he so k co viec de lam.
ik_src = build("IK_SRC", ik_bones(1.00, 0.55))
ik_tgt = build("IK_TGT", ik_bones(0.70, 0.45))

ik_act = bpy.data.actions.new("IKMotion")
ik_src.animation_data_create().action = ik_act
for pb in ik_src.pose.bones:
    pb.rotation_mode = 'QUATERNION'
for f, ang, dy in ((1, 0.0, 0.0), (6, 0.7, 0.30)):
    ctx.scene.frame_set(f)
    ik_src.pose.bones["hip"].rotation_quaternion = Quaternion((1, 0, 0), ang)
    ik_src.pose.bones["knee"].rotation_quaternion = Quaternion((1, 0, 0), -ang)
    # Ban chan buoc han ra truoc — dung thu ma rig IK dung xuong nay de ta.
    ik_src.pose.bones["ankle"].location = Vector((0.0, dy, 0.0))
    for n in ("hip", "knee", "ankle"):
        ik_src.pose.bones[n].keyframe_insert("rotation_quaternion", frame=f)
        ik_src.pose.bones[n].keyframe_insert("location", frame=f)

ik_pairs_base = [
    {"role": "hips", "side": "", "src": "hip", "tgt": "hip",
     "src_child": "knee", "tgt_child": "knee"},
    {"role": "shin", "side": "", "src": "knee", "tgt": "knee",
     "src_child": None, "tgt_child": None},
    {"role": "foot", "side": "", "src": "ankle", "tgt": "ankle",
     "src_child": None, "tgt_child": None},
]


FRAMES = list(range(1, 7))


def ankle_offsets(ob):
    """Vi tri co chan so voi xuong neo (goi), tung frame, trong khong gian the gioi.

    Do tu XUONG NEO chu khong tu goc toa do: hai nhan vat cao thap khac nhau
    thi vi tri tuyet doi khong so duoc, con doan goi->co chan thi so duoc.
    """
    out = []
    for f in FRAMES:
        ctx.scene.frame_set(f)
        ctx.view_layer.update()
        a = (ob.matrix_world @ ob.pose.bones["ankle"].matrix).translation
        k = (ob.matrix_world @ ob.pose.bones["knee"].matrix).translation
        out.append((a - k).copy())
    return out


src_off = ankle_offsets(ik_src)
src_move = max((v - src_off[0]).length for v in src_off)
check(src_move > 0.05,
      "clip goc that su co dich chuyen co chan (%.3f m) — test co y nghia" % src_move)

# He so k: chi cua rig dich ngan hon nen doan goi->co chan phai ngan theo.
k_expect = ((core.rest_head_world(ik_tgt, "ankle")
             - core.rest_head_world(ik_tgt, "knee")).length
            / (core.rest_head_world(ik_src, "ankle")
               - core.rest_head_world(ik_src, "knee")).length)


def ik_run(pairs, name):
    act, rep = core.retarget(ctx, ik_src, ik_tgt, pairs, 1, 6, name,
                             use_hips_loc=False)
    ik_tgt.animation_data.action = act
    core.bind_slot(ik_tgt.animation_data, act)
    off = ankle_offsets(ik_tgt)
    move = max((v - off[0]).length for v in off)
    gap = max((got - want * k_expect).length
              for got, want in zip(off, src_off))
    return move, gap, rep


mv_rot, gap_rot, _ = ik_run([dict(p) for p in ik_pairs_base], "IK_RotOnly")

with_pos = [dict(p) for p in ik_pairs_base]
with_pos[2]["pos"] = True
with_pos[2]["anchor"] = "knee"
mv_pos, gap_pos, rep_pos = ik_run(with_pos, "IK_WithPos")

print("    he so chi k = %.3f" % k_expect)
print("    chi truyen goc xoay:  co chan dich chuyen %.4f m, lech so voi guong "
      "mong doi %.4f m" % (mv_rot, gap_rot))
print("    co truyen vi tri:     co chan dich chuyen %.4f m, lech %.4f m"
      % (mv_pos, gap_pos))

check(gap_rot > 0.1,
      "chi truyen goc: co chan khong theo nguon, lech %.3f m — test co y nghia"
      % gap_rot)
check(gap_pos < 1e-5,
      "truyen vi tri dat co chan dung ti le chi cua rig dich (lech %.2e m)" % gap_pos)
check(gap_pos < gap_rot / 100.0,
      "truyen vi tri tot hon han chi truyen goc (%.2e vs %.4f m)" % (gap_pos, gap_rot))
check(not rep_pos, "truyen vi tri chay sach, khong canh bao (%s)" % rep_pos)

# Xuong neo khong co trong bang -> bao ro va bo qua, khong im lang lam sai.
bad = [dict(p) for p in ik_pairs_base]
bad[2]["pos"] = True
bad[2]["anchor"] = "khong_ton_tai"
_, rep_bad = core.retarget(ctx, ik_src, ik_tgt, bad, 1, 6, "IK_BadAnchor",
                           use_hips_loc=False)
check(any("không có trong bảng" in r for r in rep_bad),
      "xuong neo khong hop le -> co canh bao (%s)" % rep_bad)

# Bat 'pos' ma quen chon neo cung phai bao.
noanchor = [dict(p) for p in ik_pairs_base]
noanchor[2]["pos"] = True
_, rep_na = core.retarget(ctx, ik_src, ik_tgt, noanchor, 1, 6, "IK_NoAnchor",
                          use_hips_loc=False)
check(any("chưa chọn xương neo" in r for r in rep_na),
      "bat truyen vi tri ma khong co neo -> co canh bao (%s)" % rep_na)

# Tay phai cua ban moi phai o dung cho tay trai cua ban goc, va nguoc lai
def hand_y(action, bone):
    tgt.animation_data.action = action
    ys = []
    for f in range(f0, f1 + 1):
        ctx.scene.frame_set(f)
        ys.append((tgt.matrix_world @ tgt.pose.bones[bone].matrix).translation.y)
    return sum(ys) / len(ys)

lh_src = hand_y(src_act, "mixamorig:LeftHand")
rh_new = hand_y(new, "mixamorig:RightHand")
check(abs(lh_src - rh_new) < 1e-4,
      "tay phai ban moi trung vi tri tay trai ban goc (%.5f vs %.5f)" % (lh_src, rh_new))

# ===========================================================================
# Bounce / Polish
# ===========================================================================
bounce = mod.bounce

legs = bounce.find_legs(tgt)
check(legs["hips"] == "mixamorig:Hips", "find_legs: nhan ra xuong hong")
check(legs["L"]["thigh"] == "mixamorig:LeftUpLeg" and
      legs["L"]["shin"] == "mixamorig:LeftLeg" and
      legs["L"]["foot"] == "mixamorig:LeftFoot" and
      legs["L"].get("toe") == "mixamorig:LeftToeBase",
      "find_legs: nhan ra du chuoi chan trai")

bact = bpy.data.actions["RT_Aligned"]
DEPTH = 0.02
rep, st1 = bounce.add_bounce(ctx, tgt, bact, DEPTH, 2)
print("    nhun %.4f m | chan truot %.6f m | goi ra truoc %.4f m"
      % (st1["bounce"], st1["drift"], st1["knee_min"]))
check(abs(st1["bounce"] - DEPTH) < DEPTH * 0.15,
      "nhun dat dung do sau dat (%.4f vs %.4f)" % (st1["bounce"], DEPTH))
check(st1["drift"] < 1e-4,
      "ban chan dinh san sau khi them nhun (truot %.6f m)" % st1["drift"])
check(st1["knee_min"] > 0.0,
      "goi gap ra PHIA TRUOC o moi frame (%.4f m)" % st1["knee_min"])

# Chay lai phai KHONG cong don. Day la ly do dat do cao hong tuyet doi thay vi
# cong them: neu khong, moi lan bam nut la nhan vat lai lun sau thanh gap doi.
rep2, st2 = bounce.add_bounce(ctx, tgt, bact, DEPTH, 2)
check(abs(st2["bounce"] - st1["bounce"]) < 1e-5,
      "add_bounce idempotent (%.4f -> %.4f)" % (st1["bounce"], st2["bounce"]))
check(st2["drift"] < 1e-4, "chay lai van dinh san")

# Nhun sau qua chieu dai chan phai bi bao
rep3, _ = bounce.add_bounce(ctx, tgt, bact, 0.15, 2)
check(any("khá sâu" in r for r in rep3), "canh bao khi nhun sau qua chieu dai chan")
bounce.add_bounce(ctx, tgt, bact, DEPTH, 2)   # tra ve muc binh thuong

n, before, after = bounce.amplify_motion(ctx, tgt, bact, 2.0)
print("    khuech dai than: %d xuong, bien do %.3f -> %.3f do" % (n, before, after))
check(n >= 4, "amplify_motion nhan ra it nhat 4 xuong than (%d)" % n)
check(after > before * 1.9, "bien do than tang gan gap doi")

if FAILED:
    print("\nFAILED %d:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_anim_tools: OK")
