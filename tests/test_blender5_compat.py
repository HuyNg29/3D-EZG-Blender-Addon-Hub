"""Addon phai chay duoc tren Blender 5.x, noi `Action.fcurves` da bi BO HAN.

Blender 4.4 chuyen F-Curve cua action vao channelbag theo tung slot va de
`action.fcurves` lai lam loi vao cu. Blender 5.x xoa han thuoc tinh do, nen moi
cho con dung no se nem:

    AttributeError: 'Action' object has no attribute 'fcurves'

Addon van CAI duoc binh thuong roi chet ngay lan bam dau tien — da xay ra that
voi Mixamo Animation Library tren may Blender 5.2 (nut Apply, tuy chon In Place
-> `_strip_root_motion`).

May chay test chi co Blender 4.5, o do `action.fcurves` VAN CON, nen chay test
binh thuong khong the bat duoc lop loi nay: moi ham se lang le roi vao duong cu
va bao dat. Vi vay test boc Action trong mot proxy CHAN dung thuoc tinh do —
dung dieu kien cua 5.x — roi goi ham that. Qua duoc proxy nghia la khong con
cho nao cham vao loi vao cu.

CHAY BANG tools\\run_tests.ps1.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

import bpy  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

FAILED = []


def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


class Blender5Action:
    """Action nhu Blender 5.x nhin thay: khong con `fcurves`.

    Moi thu khac chuyen thang xuong Action that, nen ham duoc test van doc
    layers/slots/frame_range va van XOA duoc fcurve that.
    """

    def __init__(self, action):
        object.__setattr__(self, "_real", action)

    def __getattr__(self, name):
        if name == "fcurves":
            raise AttributeError("'Action' object has no attribute 'fcurves'")
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_real"), name, value)

    def __getitem__(self, key):
        return object.__getattribute__(self, "_real")[key]

    def __setitem__(self, key, value):
        object.__getattribute__(self, "_real")[key] = value


def make_rig(name):
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    root = arm.edit_bones.new("mixamorig:Hips")
    root.head, root.tail = Vector((0, 0, 1.0)), Vector((0, 0, 1.2))
    child = arm.edit_bones.new("mixamorig:Spine")
    child.head, child.tail = Vector((0, 0, 1.2)), Vector((0, 0, 1.4))
    child.parent = root
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def make_action(ob, name):
    """Action co: Hips di chuyen tinh tien (root motion), Spine chi xoay."""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    ad = ob.animation_data_create()
    ad.action = act
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    for f, travel in ((1, 0.0), (10, 2.0)):
        bpy.context.scene.frame_set(f)
        ob.pose.bones["mixamorig:Hips"].location = Vector((0.0, travel, 0.0))
        ob.pose.bones["mixamorig:Hips"].keyframe_insert("location", frame=f)
        ob.pose.bones["mixamorig:Spine"].rotation_quaternion = \
            Quaternion((1, 0, 0), 0.4 * f / 10.0)
        ob.pose.bones["mixamorig:Spine"].keyframe_insert("rotation_quaternion",
                                                        frame=f)
    ob.keyframe_insert("location", frame=1)
    return act


# ---------------------------------------------------------------------------
print("=== Proxy gia lap Blender 5.x ===")
bpy.ops.wm.read_homefile(use_empty=True)
rig = make_rig("CompatRig")
real_act = make_action(rig, "CompatClip")
proxy = Blender5Action(real_act)

try:
    # Chinh dong nay la thu da no tren may Blender 5.2 cua thanh vien:
    #   for fc in list(action.fcurves):   <- _strip_root_motion, ban cu
    list(proxy.fcurves)
    check(False, "proxy phai chan duoc .fcurves")
except AttributeError as exc:
    check("has no attribute 'fcurves'" in str(exc),
          "proxy tai hien dung nguyen van loi cua Blender 5.2 (%s)" % exc)
check(not hasattr(proxy, "fcurves"), "hasattr(proxy, 'fcurves') la False")
check(len(proxy.slots) >= 1, "proxy van chuyen tiep slots/layers xuong Action that")


# ---------------------------------------------------------------------------
print("\n=== ezg_mixamo_anim_lib ===")
lib = kit.enable("ezg_mixamo_anim_lib")

fcs = lib._fcurves(proxy)
check(len(fcs) >= 3, "_fcurves doc duoc kenh ma khong cham .fcurves (%d)" % len(fcs))

names = lib._action_bone_names(proxy)
check(names == {"mixamorig:Hips", "mixamorig:Spine"},
      "_action_bone_names chay duoc tren 5.x (%s)" % sorted(names))

rot = lib._bone_rot_curves(proxy, "rotation_quaternion")
check("mixamorig:Spine" in rot, "_bone_rot_curves chay duoc tren 5.x")

found = lib._find_fcurve(proxy, 'pose.bones["mixamorig:Hips"].location', index=1)
check(found is not None, "_find_fcurve tim duoc kenh tren 5.x")

# Day la dung ham da nem loi tren may thanh vien: Apply + In Place.
before = len(lib._fcurves(proxy))
removed = lib._strip_root_motion(proxy)
after = len(lib._fcurves(proxy))
check(removed >= 1, "_strip_root_motion xoa duoc kenh root motion (%d)" % removed)
check(after == before - removed,
      "so kenh giam dung bang so kenh bi xoa (%d -> %d)" % (before, after))
# Chi kenh THAT SU tinh tien bi xoa (o day la Y); X/Z dung yen nen giu lai —
# do la y do cua _strip_root_motion, khong phai xoa ca cum location.
left = {fc.array_index for fc in lib._fcurves(proxy)
        if fc.data_path.endswith(".location") and "hips" in fc.data_path.lower()}
check(1 not in left,
      "kenh tinh tien (Y) cua Hips da bi xoa that khoi Action (con lai: %s)"
      % sorted(left))
check(left == {0, 2},
      "hai kenh dung yen cua Hips duoc giu nguyen (con lai: %s)" % sorted(left))

lib._clear_object_z_keys(rig)
check(True, "_clear_object_z_keys chay duoc tren rig that")


# ---------------------------------------------------------------------------
print("\n=== ezg_anim_tools ===")
at = kit.enable("ezg_anim_tools")

at_fcs = at.core.action_fcurves(proxy)
check(len(at_fcs) >= 2, "core.action_fcurves chay duoc tren 5.x (%d)" % len(at_fcs))
check(not at.core.action_is_static(proxy),
      "core.action_is_static chay duoc tren 5.x")

obj_lv = at.mirror._object_level(proxy)
check(("location", 0) in obj_lv,
      "mirror._object_level thay kenh cap object tren 5.x (%s)" % sorted(obj_lv))

# Action rong: khong co layer/slot nao, day la cho fallback tung tro toi
# `action.fcurves`. Tren 5.x no phai tra ve rong chu khong duoc nem loi.
empty = Blender5Action(bpy.data.actions.new("Rong5x"))
check(at.core.action_fcurves(empty) == [],
      "action rong -> danh sach rong, khong nem AttributeError")
check(at.core.action_is_static(empty), "action rong van bao la tinh")


# ---------------------------------------------------------------------------
print("\n=== ezg_mixamo_marker_rigger ===")
mmr = kit.enable("ezg_mixamo_marker_rigger")

conts = mmr.action_channel_containers(proxy)
check(conts and all(hasattr(c, "fcurves") for c in conts),
      "action_channel_containers tra ve container doc duoc (%d)" % len(conts))
check(proxy not in conts and real_act not in conts,
      "khong roi ve chinh Action — do la cho se no tren 5.x")

empty_conts = mmr.action_channel_containers(empty)
check(empty_conts == [],
      "action rong tren 5.x -> rong, thay vi [action] roi no khi doc .fcurves")
for c in empty_conts:
    list(c.fcurves)
check(True, "duyet ket qua cua action rong khong nem loi")


print()
if FAILED:
    print("THAT BAI %d muc:" % len(FAILED))
    for m in FAILED:
        print("  - " + m)
    sys.exit(1)
print("test_blender5_compat: OK")
