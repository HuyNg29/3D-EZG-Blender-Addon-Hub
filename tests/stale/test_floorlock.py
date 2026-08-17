"""Test the Mixamo Animation Library foot floor-lock on a short-legged rig."""

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

    # Short/stocky character: SHORT legs (knee high, hip low), feet at Z=0.
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.28, depth=1.3, location=(0, 0, 0.65))
    body = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.subdivide(number_cuts=6); bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    body.name = "Dwarf"

    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.create_markers()
    # Stocky proportions: short legs (knee at 0.35, hip at 0.7).
    for j, loc in {"Chin": (0, 0, 1.15), "Groin": (0, 0, 0.70),
                   "LeftShoulder": (0.15, 0, 1.02),
                   "LeftWrist": (0.6, 0, 1.0), "LeftElbow": (0.33, 0, 1.0),
                   "LeftKnee": (0.13, 0, 0.35)}.items():
        mmr.find_marker(j).location = loc
    bpy.ops.mmr.build_armature()
    arm = bpy.data.objects[mmr.ARMATURE_NAME]
    bpy.ops.mmr.bind_auto_weights()

    # Point the Library at the resource folder and import the punch action.
    scene.mixlib.library_path = RES
    lib._rescan(scene.mixlib)
    # find "Standing Melee Punch"
    idx = next((i for i, it in enumerate(scene.mixlib.items)
                if "Melee Punch" in it.name), None)
    check(idx is not None, "found Melee Punch in library")
    scene.mixlib.active_index = idx

    # Select the armature as active target.
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm

    def lowest_over_anim():
        f0, f1 = scene.frame_start, scene.frame_end
        lo = 1e9
        for f in range(f0, f1 + 1, max(1, (f1 - f0) // 10)):
            scene.frame_set(f)
            lo = min(lo, mesh_low_z(bpy.context, arm))
        return lo

    # --- Apply WITHOUT floor lock: feet dip below the floor ------------------
    scene.mixlib.foot_floor_lock = False
    bpy.ops.mixlib.apply()
    before = lowest_over_anim()
    print(f"    without floor-lock: lowest foot Z = {before:.3f}")
    check(before < -0.005, f"feet sink below floor without lock ({before:.3f})")

    # --- Bake floor lock directly and re-measure -----------------------------
    baked, err = lib.bake_foot_floor_lock(bpy.context, arm, 0.0)
    check(err is None and baked > 0, f"bake_foot_floor_lock ran ({baked} frames, err={err})")
    after = lowest_over_anim()
    print(f"    with floor-lock:    lowest foot Z = {after:.3f}")
    check(abs(after) < 0.02, f"floor-lock keeps feet on the floor (lowest {after:.3f})")
    check(after > before + 0.005, "floor-lock raised the sinking feet")

    # Standalone operators (re-select the armature as active first)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    scene.mixlib.ground_method = 'FLOOR_LOCK'
    check(bpy.ops.mixlib.ground_feet() == {'FINISHED'}, "ground_feet (floor lock) runs")
    check(bpy.ops.mixlib.clear_ground() == {'FINISHED'}, "clear_ground operator runs")
    scene.mixlib.ground_method = 'FOOT_IK'
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    check(bpy.ops.mixlib.ground_feet() == {'FINISHED'}, "ground_feet (foot IK) runs")
    # after clear, object z key removed
    ad = arm.animation_data
    has_z = ad and ad.action and any(fc.data_path == "location" and fc.array_index == 2
                                     for fc in ad.action.fcurves)
    check(not has_z, "clear removed object-Z keyframes")

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
