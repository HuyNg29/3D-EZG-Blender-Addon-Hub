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
from mathutils import Euler, Quaternion, Vector  # noqa: E402

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
check(any("kha sau" in r for r in rep3), "canh bao khi nhun sau qua chieu dai chan")
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
