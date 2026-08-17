"""Verify the generated rig matches the real Mixamo rig closely enough that
Animation Library actions apply without flying the character away."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402
import sys, math
import bpy
from mathutils import Vector

RES = kit.assets_dir()
if RES is None:
    kit.skip("can bo FBX mau cua Mixamo - dat bien EZG_TEST_ASSETS "
             "hoac chay: .\tools\run_tests.ps1 -Assets \"D:\EZG Addon Assets\MixamoLibResource\"")
FAILED = []


def check(cond, msg):
    print(("  OK  " if cond else "  FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


def import_mixamo(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True,
                             automatic_bone_orientation=False)
    imp = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in imp if o.type == 'ARMATURE')
    return arm, imp


def bone_world_axes(arm, bone_name):
    """Return (origin, x_axis, y_axis, z_axis) of a bone's rest matrix in world."""
    b = arm.data.bones.get(bone_name)
    if b is None:
        return None
    m = arm.matrix_world @ b.matrix_local
    return (m.translation.copy(),
            m.col[0].xyz.normalized(),
            m.col[1].xyz.normalized(),
            m.col[2].xyz.normalized())


# Doi tu read_factory_settings sang read_homefile: ban goi reset preferences,
# ma addon gio la extension bat qua preferences nen se bi tat giua chung test.
# read_homefile van cho scene trang nhung khong dung toi preferences.
def main():
    mmr = kit.enable("ezg_mixamo_marker_rigger")
    # --- Reference: the real Mixamo rig -----------------------------------
    bpy.ops.wm.read_homefile(use_empty=True)
    ref_arm, _ = import_mixamo(RES + r"\T-Pose.fbx")
    P = "mixamorig:"

    def ref_head_world(name):
        b = ref_arm.data.bones[P + name]
        return (ref_arm.matrix_world @ b.head_local).copy()

    # Marker world positions derived from the reference rig.
    markers = {
        "Chin":         ref_head_world("Head"),
        "Groin":        ref_head_world("Hips"),
        "LeftShoulder": ref_head_world("LeftArm"),   # Mixamo LeftArm head = shoulder
        "LeftWrist":    ref_head_world("LeftHand"),
        "LeftElbow":    ref_head_world("LeftForeArm"),
        "LeftKnee":     ref_head_world("LeftLeg"),
    }
    print("Ref Hips world:", tuple(round(v, 3) for v in markers["Groin"]))

    # A mesh matching the reference bounding box so height scale is realistic.
    mn = Vector((min(ref_head_world(n).x for n in
                     ["LeftHand", "Hips", "Head", "LeftLeg", "LeftFoot"]) - 0.2, 0, -0.2))
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.9))
    body = bpy.context.active_object
    body.name = "RefBody"
    body.scale = (0.7, 0.2, 0.95)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # --- Build our rig fitted to the reference proportions -----------------
    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.create_markers()
    for j, loc in markers.items():
        mmr.find_marker(j).location = loc
    r = bpy.ops.mmr.build_armature()
    check(r == {'FINISHED'}, "build_armature at Mixamo proportions")
    gen = bpy.data.objects.get(mmr.ARMATURE_NAME)

    # --- 1. Armature object transform matches Mixamo -----------------------
    check(abs(gen.rotation_euler.x - math.radians(90)) < 1e-4,
          "generated armature rotated +90 X (like Mixamo)")
    check(abs(gen.scale.x - 0.01) < 1e-6, "generated armature scale 0.01 (cm)")

    # --- 2. Bone DATA is Y-up centimetres ----------------------------------
    hips_data = gen.data.bones[P + "Hips"].head_local
    check(hips_data.y > 50, f"Hips data Y in centimetres/Y-up ({hips_data.y:.1f})")
    spine = gen.data.bones[P + "Spine"]
    sdir = (spine.tail_local - spine.head_local).normalized()
    check(sdir.y > 0.8, f"Spine points +Y in data space ({tuple(round(v,2) for v in sdir)})")

    # --- 3. Rest orientation matches the real Mixamo rig (world axes) ------
    # Compare bone Y (direction) and Z axes; small angle => rotations transfer.
    compare = ["Hips", "Spine", "Spine2", "Neck", "Head",
               "LeftArm", "LeftForeArm", "RightArm",
               "LeftUpLeg", "LeftLeg", "RightUpLeg"]
    worst_y = 0.0
    worst_z = 0.0
    for name in compare:
        g = bone_world_axes(gen, P + name)
        r_ = bone_world_axes(ref_arm, P + name)
        if g is None or r_ is None:
            continue
        ay = math.degrees(g[2].angle(r_[2]))   # Y axis (direction)
        az = math.degrees(g[3].angle(r_[3]))   # Z axis (roll)
        worst_y = max(worst_y, ay)
        worst_z = max(worst_z, az)
        print(f"    {name:14s} dir_angle={ay:5.1f}  roll_axis_angle={az:5.1f}")
    check(worst_y < 20.0, f"bone directions match Mixamo within 20 deg (worst {worst_y:.1f})")
    check(worst_z < 25.0, f"bone roll axes match Mixamo within 25 deg (worst {worst_z:.1f})")

    # --- 4. Apply a real Mixamo animation: character must NOT fly away ------
    anim_arm, _ = import_mixamo(RES + r"\Standing Melee Punch.fbx")
    src = anim_arm.animation_data.action
    action = src.copy()
    # Assign the Mixamo action directly to our generated rig (as the lib does).
    if gen.animation_data is None:
        gen.animation_data_create()
    gen.animation_data.action = action
    if hasattr(action, "slots") and len(getattr(action, "slots", [])):
        try:
            gen.animation_data.action_slot = action.slots[0]
        except Exception:
            pass

    f0, f1 = (int(action.frame_range[0]), int(action.frame_range[1]))
    hips_pb = gen.pose.bones.get(P + "Hips")
    check(hips_pb is not None, "generated rig has Hips pose bone")
    max_dist = 0.0
    finite = True
    for f in range(f0, f1 + 1, max(1, (f1 - f0) // 12)):
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        gen_eval = gen.evaluated_get(dg)
        wloc = gen_eval.matrix_world @ gen_eval.pose.bones[P + "Hips"].matrix.translation
        if not all(math.isfinite(c) for c in wloc):
            finite = False
        max_dist = max(max_dist, wloc.length)
    print(f"    Hips max world distance over anim: {max_dist:.2f} m")
    check(finite, "posed Hips position stays finite (no NaN)")
    check(max_dist < 3.0, f"character does NOT fly away (Hips stays < 3 m, got {max_dist:.2f})")

    # Bone-name match ratio (how the lib decides to apply)
    anim_bones = set()
    import re
    for fc in action.fcurves:
        m = re.match(r'pose\.bones\["(.+?)"\]', fc.data_path)
        if m:
            anim_bones.add(m.group(1))
    # Every body bone we generate must be driven by the Mixamo action; the
    # action's extra finger/toe bones are simply ignored (MVP has no fingers).
    mine = [b.name for b in gen.pose.bones]
    driven = sum(1 for n in mine if n in anim_bones)
    print(f"    my bones driven by anim: {driven}/{len(mine)}")
    check(driven == len(mine),
          f"all generated bones are driven by the Mixamo action ({driven}/{len(mine)})")

    print()
    print("RESULT:", "ALL TESTS PASSED" if not FAILED else f"{len(FAILED)} FAILURES")
    if FAILED:
        sys.exit(1)


import traceback
try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(2)
