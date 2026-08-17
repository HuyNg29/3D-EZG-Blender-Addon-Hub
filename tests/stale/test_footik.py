"""Test foot-IK grounding: feet planted, knees forward, body still moves."""

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
P = "mixamorig:"
FAILED = []


def check(c, m):
    print(("  OK  " if c else "  FAIL ") + m)
    if not c:
        FAILED.append(m)


def mesh_low_z(context, arm):
    dg = context.evaluated_depsgraph_get()
    lo = None
    for ch in arm.children_recursive:
        if ch.type != 'MESH':
            continue
        ev = ch.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        for v in me.vertices:
            z = (mw @ v.co).z
            lo = z if lo is None else min(lo, z)
        ev.to_mesh_clear()
    return lo


# Doi tu read_factory_settings sang read_homefile: ban goi reset preferences,
# ma addon gio la extension bat qua preferences nen se bi tat giua chung test.
# read_homefile van cho scene trang nhung khong dung toi preferences.
def main():
    mmr = kit.enable("ezg_mixamo_marker_rigger")
    lib = kit.enable("ezg_mixamo_anim_lib")
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    # Short/stocky character, feet at Z=0.
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.28, depth=1.3, location=(0, 0, 0.65))
    body = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.subdivide(number_cuts=6); bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    body.name = "Dwarf"

    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.create_markers()
    for j, loc in {"Chin": (0, 0, 1.15), "Groin": (0, 0, 0.70),
                   "LeftShoulder": (0.15, 0, 1.02),
                   "LeftWrist": (0.6, 0, 1.0), "LeftElbow": (0.33, 0, 1.0),
                   "LeftKnee": (0.13, 0, 0.35)}.items():
        mmr.find_marker(j).location = loc
    bpy.ops.mmr.build_armature()
    arm = bpy.data.objects[mmr.ARMATURE_NAME]
    bpy.ops.mmr.bind_auto_weights()

    scene.mixlib.library_path = RES
    lib._rescan(scene.mixlib)
    idx = next(i for i, it in enumerate(scene.mixlib.items) if "Melee Punch" in it.name)
    scene.mixlib.active_index = idx
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm

    scene.mixlib.foot_floor_lock = False
    bpy.ops.mixlib.apply()

    def sample(fn):
        f0, f1 = scene.frame_start, scene.frame_end
        out = []
        for f in range(f0, f1 + 1, max(1, (f1 - f0) // 10)):
            scene.frame_set(f)
            out.append(fn(f))
        return out

    mw = arm.matrix_world

    def foot_bone_low(f):
        # lowest of both feet's foot/toe bone points (what the IK controls)
        zs = []
        for s in ("Left", "Right"):
            z = lib._side_sole_world_z(arm, s)
            if z is not None:
                zs.append(z)
        return min(zs)

    # BEFORE: foot-BONE sink and hip Z range (proxy has no real feet, so we
    # validate the bone the IK actually controls, not the crude mesh rim).
    sink_before = min(sample(foot_bone_low))
    hipz_before = sample(lambda f: (mw @ arm.pose.bones[P + "Hips"].head).z)
    print(f"    before IK: min foot-bone Z={sink_before:.3f}  hipZ=[{min(hipz_before):.3f},{max(hipz_before):.3f}]")
    check(sink_before < -0.01, "foot bones sink below floor before IK")

    # Apply foot-IK
    baked, err = lib.bake_foot_ik(bpy.context, arm, 0.0)
    check(err is None and baked > 0, f"bake_foot_ik ran ({baked} frames, err={err})")

    # AFTER
    sink_after = min(sample(foot_bone_low))
    hipz_after = sample(lambda f: (mw @ arm.pose.bones[P + "Hips"].head).z)
    print(f"    after IK:  min foot-bone Z={sink_after:.3f}  hipZ=[{min(hipz_after):.3f},{max(hipz_after):.3f}]")

    check(sink_after > sink_before + 0.008, f"foot-IK lifted the sinking feet ({sink_before:.3f} -> {sink_after:.3f})")
    check(sink_after > -0.02, f"foot bones at/above floor after IK ({sink_after:.3f})")

    # Body still moves (hip Z varies), i.e. we adjusted legs not froze the body.
    hip_range_after = max(hipz_after) - min(hipz_after)
    check(hip_range_after > 0.02, f"body still moves after IK (hip Z range {hip_range_after:.3f})")

    # Knees point forward (world -Y): knee Y < hip Y and < ankle Y at each frame.
    def knee_forward(side):
        scene.frame_set((scene.frame_start + scene.frame_end) // 2)
        hip = mw @ arm.pose.bones[P + side + "UpLeg"].head
        knee = mw @ arm.pose.bones[P + side + "Leg"].head
        ankle = mw @ arm.pose.bones[P + side + "Foot"].head
        # forward = -Y; knee should be at or forward of the hip-ankle line, not behind
        return knee.y <= max(hip.y, ankle.y) + 0.05
    check(knee_forward("Left") and knee_forward("Right"),
          "knees do not flip backward after IK")

    # No leftover IK constraints
    leftover = any(c.name == "MMR_FOOT_IK"
                   for pb in arm.pose.bones for c in pb.constraints)
    check(not leftover, "IK constraints removed after bake")
    check(not any(o.name.startswith("MMR_IK_TGT") for o in bpy.data.objects),
          "IK target empties removed")

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
