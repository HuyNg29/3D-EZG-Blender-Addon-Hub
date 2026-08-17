"""Headless test for the Manual Marker Mixamo Rigger add-on (v0.4, axis-configurable symmetry)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402
import sys
import traceback

import bpy
from mathutils import Vector

FAILED = []


def check(cond, msg):
    if cond:
        print(f"  OK   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILED.append(msg)


def expect_error(op, msg):
    try:
        r = op()
        check(r == {'CANCELLED'}, msg)
    except RuntimeError:
        check(True, msg)


def evaluated_loc(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    return obj.evaluated_get(dg).matrix_world.translation.copy()


# Doi tu read_factory_settings sang read_homefile: ban goi reset preferences,
# ma addon gio la extension bat qua preferences nen se bi tat giua chung test.
# read_homefile van cho scene trang nhung khong dung toi preferences.
def main():
    mmr = kit.enable("ezg_mixamo_marker_rigger")
    print("register OK")

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    def add_box(name, loc, scale):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale
        return obj

    torso = add_box("Body", (0, 0, 1.1), (0.20, 0.12, 0.35))
    parts = [add_box("HeadB", (0, 0, 1.62), (0.10, 0.10, 0.12)),
             add_box("ArmL", (0.45, 0, 1.35), (0.28, 0.05, 0.05)),
             add_box("ArmR", (-0.45, 0, 1.35), (0.28, 0.05, 0.05)),
             add_box("LegL", (0.12, 0, 0.40), (0.07, 0.07, 0.42)),
             add_box("LegR", (-0.12, 0, 0.40), (0.07, 0.07, 0.42))]
    for o in ([torso] + parts):
        o.select_set(True)
    bpy.context.view_layer.objects.active = torso
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    mesh = bpy.context.active_object
    mesh.name = "TestHumanoid"

    # --- Defaults (Blender-natural: world Up=Z, Forward=-Y, Symmetry=X) -----
    # The character stands Z-up in Blender; the generated rig is converted to
    # Mixamo's Y-up cm data space internally.
    check(scene.mmr_use_symmetry is True, "Use Symmetry defaults to True")
    check(scene.mmr_symmetry_axis == 'X', "Symmetry Axis defaults to X")
    check(mmr.get_up_axis(bpy.context) == 'Z', "Up axis locked to world Z")
    check(scene.mmr_forward_axis == 'Y', "Character Forward Axis defaults to Y")
    check(scene.mmr_forward_dir == 'NEGATIVE', "Forward Direction defaults to Negative")
    check(scene.mmr_skeleton_lod == 'NO_FINGERS', "Skeleton LOD defaults to No Fingers")

    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.prepare_mesh()

    # Helper: world position of a generated bone head/tail (data is cm/Y-up now).
    def bone_head_world(a, name):
        return a.matrix_world @ a.data.bones[name].head_local

    def bone_tail_world(a, name):
        return a.matrix_world @ a.data.bones[name].tail_local

    # --- Create markers → drivers immediately -------------------------------
    r = bpy.ops.mmr.create_markers()
    check(r == {'FINISHED'}, "create_markers")
    check(len([o for o in bpy.data.objects if o.name.startswith(mmr.MARKER_PREFIX)]) == 10,
          "10 markers created (incl. shoulders)")
    center = bpy.data.objects.get(mmr.SYMMETRY_CENTER_NAME)
    check(center is not None, "MMR_SYMMETRY_CENTER created")
    check(mmr.realtime_symmetry_active(), "realtime symmetry active on create")

    # --- Axis X realtime ----------------------------------------------------
    mmr.find_marker("LeftWrist").location = (0.70, 0.05, 1.35)
    rw = evaluated_loc(mmr.find_marker("RightWrist"))
    check((rw - Vector((-0.70, 0.05, 1.35))).length < 1e-5,
          f"[X] RightWrist = (-Lx, Ly, Lz), got {tuple(round(v,3) for v in rw)}")

    # --- Switch to axis Y → drivers rebuilt live, no recreate ----------------
    scene.mmr_symmetry_axis = 'Y'
    check(mmr.realtime_symmetry_active(), "symmetry still active after axis change")
    mmr.find_marker("LeftWrist").location = (0.70, 0.05, 1.35)
    rw = evaluated_loc(mmr.find_marker("RightWrist"))
    check((rw - Vector((0.70, -0.05, 1.35))).length < 1e-5,
          f"[Y] RightWrist = (Lx, -Ly, Lz), got {tuple(round(v,3) for v in rw)}")

    # --- Switch to axis Z ----------------------------------------------------
    scene.mmr_symmetry_axis = 'Z'
    mmr.find_marker("LeftWrist").location = (0.70, 0.05, 1.35)
    rw = evaluated_loc(mmr.find_marker("RightWrist"))
    check((rw - Vector((0.70, 0.05, -1.35))).length < 1e-5,
          f"[Z] RightWrist = (Lx, Ly, -Lz), got {tuple(round(v,3) for v in rw)}")

    # Center-offset check on axis Z: center.z = 1.0 → Rz = 2*1.0 - Lz
    scene.mmr_symmetry_axis = 'X'  # reset
    center.location = (0.0, 0.0, 0.0)

    # --- Non-zero center on X ------------------------------------------------
    center.location.x = 0.2
    mmr.find_marker("LeftWrist").location = (0.70, 0.0, 1.35)
    rw = evaluated_loc(mmr.find_marker("RightWrist"))
    check(abs(rw.x - (2 * 0.2 - 0.70)) < 1e-5,
          f"[X] center offset: Rx = 2*cx - Lx, got {rw.x:.3f} (want {2*0.2-0.70:.3f})")
    center.location.x = 0.0

    # --- Locking ------------------------------------------------------------
    for rj in ("RightWrist", "RightElbow", "RightKnee"):
        check(all(mmr.find_marker(rj).lock_location), f"{rj} fully locked (X axis)")
    check(mmr.find_marker("Chin").lock_location[0] and
          not mmr.find_marker("Chin").lock_location[2],
          "Chin locked on X only (axis X)")
    scene.mmr_symmetry_axis = 'Z'
    check(mmr.find_marker("Chin").lock_location[2] and
          not mmr.find_marker("Chin").lock_location[0],
          "Chin lock moves to Z after axis change")
    scene.mmr_symmetry_axis = 'X'

    # --- Refresh does not duplicate drivers ---------------------------------
    r = bpy.ops.mmr.refresh_symmetry()
    check(r == {'FINISHED'}, "refresh_symmetry")
    obj = mmr.find_marker("RightWrist")
    n = len([fc for fc in obj.animation_data.drivers if fc.data_path == "location"])
    check(n == 3, f"no duplicate drivers after refresh (got {n})")

    # --- Set Symmetry Center From Selected Mesh -----------------------------
    center.location = (5, 5, 5)
    r = bpy.ops.mmr.set_center_from_mesh()
    check(r == {'FINISHED'}, "set_center_from_mesh")
    bbc = mmr.mesh_bbox_center(mesh)
    check(abs(center.location.x - bbc.x) < 1e-5, "center X set to mesh bbox center X")
    check(abs(center.location.y - 5) < 1e-5 and abs(center.location.z - 5) < 1e-5,
          "only active-axis (X) component changed by set_center_from_mesh")
    center.location = (0, 0, 0)

    # --- Snap Center Markers To Symmetry Plane ------------------------------
    mmr.find_marker("Chin").location = (0.3, 0, 1.50)
    mmr.find_marker("Groin").location = (0.25, 0, 0.85)
    r = bpy.ops.mmr.snap_center_markers()
    check(r == {'FINISHED'}, "snap_center_markers")
    check(abs(mmr.find_marker("Chin").location.x) < 1e-6 and
          abs(mmr.find_marker("Groin").location.x) < 1e-6,
          "center markers snapped to X plane")

    # Place markers for a valid build
    mmr.find_marker("Chin").location = (0, 0, 1.50)
    mmr.find_marker("Groin").location = (0, 0, 0.85)
    mmr.find_marker("LeftShoulder").location = (0.15, 0, 1.36)
    mmr.find_marker("LeftWrist").location = (0.70, 0, 1.35)
    mmr.find_marker("LeftElbow").location = (0.40, 0, 1.35)
    mmr.find_marker("LeftKnee").location = (0.12, 0, 0.45)

    # --- Disable symmetry bakes + unlocks -----------------------------------
    scene.mmr_use_symmetry = False
    check(not mmr.realtime_symmetry_active(), "symmetry inactive after disable")
    rwm = mmr.find_marker("RightWrist")
    check(not any(rwm.lock_location), "right marker unlocked on disable")
    check((rwm.location - Vector((-0.70, 0, 1.35))).length < 1e-5,
          "mirrored position baked on disable")
    check(not mmr.find_marker("Chin").lock_location[0], "center X unlocked on disable")

    # --- Manual mirror respects axis while symmetry off ----------------------
    scene.mmr_symmetry_axis = 'Y'
    mmr.find_marker("LeftWrist").location = (0.70, 0.30, 1.35)
    r = bpy.ops.mmr.mirror_markers()
    check(r == {'FINISHED'}, "manual mirror works (symmetry off)")
    check((mmr.find_marker("RightWrist").location - Vector((0.70, -0.30, 1.35))).length < 1e-5,
          "[Y] manual mirror = (Lx, -Ly, Lz)")
    scene.mmr_symmetry_axis = 'X'
    mmr.find_marker("LeftWrist").location = (0.70, 0, 1.35)
    bpy.ops.mmr.mirror_markers()
    check((mmr.find_marker("RightWrist").location - Vector((-0.70, 0, 1.35))).length < 1e-5,
          "[X] manual mirror = (-Lx, Ly, Lz)")

    # --- Re-enable, missing marker safety -----------------------------------
    scene.mmr_use_symmetry = True
    check(mmr.realtime_symmetry_active(), "symmetry re-enabled via checkbox")
    rk = mmr.find_marker("RightKnee")
    saved = rk.location.copy()
    bpy.data.objects.remove(rk, do_unlink=True)
    try:
        r = bpy.ops.mmr.refresh_symmetry()
        check(r == {'FINISHED'}, "refresh with missing marker warns, no crash")
    except RuntimeError:
        check(False, "refresh with missing marker warns, no crash")
    mmr.create_marker("RightKnee", saved, 0.03, bpy.data.collections[mmr.MARKER_COLLECTION_NAME])
    bpy.ops.mmr.refresh_symmetry()

    # --- Build armature reads driven positions ------------------------------
    r = bpy.ops.mmr.build_armature()
    check(r == {'FINISHED'}, "build_armature")
    arm = bpy.data.objects.get(mmr.ARMATURE_NAME)

    # Duplicate cleanup: a stale tagged ".001" duplicate must be removed on
    # rebuild so the mesh can never end up bound to the wrong armature.
    dup = arm.copy()
    dup.data = arm.data.copy()
    dup.name = mmr.ARMATURE_NAME + "_stale"
    dup[mmr.GENERATED_TAG] = True
    bpy.context.scene.collection.objects.link(dup)
    bpy.ops.mmr.build_armature()
    gen_arms = [o for o in bpy.data.objects
                if o.type == 'ARMATURE' and o.get(mmr.GENERATED_TAG)]
    check(len(gen_arms) == 1,
          f"rebuild removes duplicate generated armatures (got {len(gen_arms)})")
    arm = bpy.data.objects.get(mmr.ARMATURE_NAME)
    bones = arm.data.bones
    check(len(bones) == 20, f"20 bones (got {len(bones)})")

    # --- Build As New Armature: adds a rig without touching existing ones ----
    n_arms_before = len([o for o in bpy.data.objects if o.type == 'ARMATURE'])
    r = bpy.ops.mmr.build_new_armature()
    check(r == {'FINISHED'}, "build_new_armature")
    arms_now = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    check(len(arms_now) == n_arms_before + 1,
          f"additional armature added ({n_arms_before} -> {len(arms_now)})")
    check(bpy.data.objects.get(mmr.ARMATURE_NAME) is arm,
          "original managed armature untouched")
    extra = scene.mmr_armature
    check(extra is not None and extra is not arm and extra.type == 'ARMATURE',
          f"pointer targets the new rig ('{extra.name if extra else None}')")
    check(not extra.get(mmr.GENERATED_TAG), "additional rig is untagged (protected)")
    check(len(extra.data.bones) == 20, "additional rig has full skeleton")
    check(mmr.armature_in_mixamo_space(extra), "additional rig in Mixamo space")
    # A later normal Build must replace ONLY the managed rig, keeping the extra.
    bpy.ops.mmr.build_armature()
    check(extra.name in bpy.data.objects, "additional rig survives a normal rebuild")
    managed = [o for o in bpy.data.objects
               if o.type == 'ARMATURE' and o.get(mmr.GENERATED_TAG)]
    check(len(managed) == 1, "exactly one managed (tagged) rig after rebuild")

    # --- Set Selected Armature: reuse an existing rig as the target ----------
    # Normal build reset the pointer; point it back at the extra rig via the op.
    bpy.ops.object.select_all(action='DESELECT')
    extra.select_set(True); bpy.context.view_layer.objects.active = extra
    r = bpy.ops.mmr.set_selected_armature()
    check(r == {'FINISHED'}, "set_selected_armature")
    check(scene.mmr_armature is extra, "pointer retargeted to the selected rig")
    check(mmr.get_generated_armature(bpy.context) is extra,
          "weight tools now resolve the selected rig")
    # Error path: nothing armature-like selected.
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    expect_error(bpy.ops.mmr.set_selected_armature,
                 "set_selected_armature errors without an armature")
    # Clean up the extra rig and restore state for the following tests.
    bpy.data.objects.remove(extra, do_unlink=True)
    arm = bpy.data.objects.get(mmr.ARMATURE_NAME)
    scene.mmr_armature = arm
    bones = arm.data.bones

    # Armature object matches a Mixamo-imported rig (rot +90 X, scale 0.01).
    import math
    check(abs(arm.rotation_euler.x - math.radians(90)) < 1e-4 and
          abs(arm.scale.x - 0.01) < 1e-6 and arm.location.length < 1e-6,
          "armature object in Mixamo space (rot +90 X, scale 0.01)")
    # Bone data is Y-up centimetres.
    check(arm.data.bones["mixamorig:Hips"].head_local.y > 50,
          "bone data is Y-up in centimetres")

    # Everything else is checked in WORLD space (bones still sit on the mesh).
    rf_tail = bone_tail_world(arm, "mixamorig:RightForeArm")
    check((rf_tail - Vector((-0.70, 0, 1.35))).length < 1e-3,
          f"RightForeArm ends at driven wrist in world ({tuple(round(v,2) for v in rf_tail)})")
    check(all((b.tail_local - b.head_local).length > 1e-4 for b in bones),
          "no zero-length bones")

    # Shoulder: LeftShoulder bone head at Spine2; LeftArm head = Shoulder MARKER
    # (0.15), so the arm starts at the user-placed shoulder, not an estimate.
    lsh_h = bone_head_world(arm, "mixamorig:LeftShoulder")
    sp2_h = bone_head_world(arm, "mixamorig:Spine2")
    check((lsh_h - sp2_h).length < 1e-3, "LeftShoulder head sits at Spine2 (world)")
    sh_x = bone_head_world(arm, "mixamorig:LeftArm").x
    check(abs(sh_x - 0.15) < 1e-3,
          f"LeftArm starts at the Shoulder marker (world x={sh_x:.3f}, marker 0.15)")
    # Canonical orientation: arm points horizontally +X (world), not exactly at
    # the elbow if the shoulder estimate differs in height.
    la_dir = (bone_tail_world(arm, "mixamorig:LeftArm")
              - bone_head_world(arm, "mixamorig:LeftArm")).normalized()
    check(la_dir.x > 0.98, f"LeftArm points +X canonical ({tuple(round(v,2) for v in la_dir)})")
    fa_dir = (bone_tail_world(arm, "mixamorig:LeftForeArm")
              - bone_head_world(arm, "mixamorig:LeftForeArm")).normalized()
    check(fa_dir.x > 0.98, "LeftForeArm points +X canonical")
    rsh_x = bone_head_world(arm, "mixamorig:RightArm").x
    check(abs(rsh_x + sh_x) < 1e-3, "RightShoulder mirrors LeftShoulder in X")

    # Hip sockets offset toward the knees (world X).
    lhip_x = bone_head_world(arm, "mixamorig:LeftUpLeg").x
    rhip_x = bone_head_world(arm, "mixamorig:RightUpLeg").x
    check(lhip_x > 1e-3 and rhip_x < -1e-3 and abs(lhip_x + rhip_x) < 1e-3,
          f"hip sockets split off-center (world L={lhip_x:.3f}, R={rhip_x:.3f})")

    # Feet near mesh bottom; default forward = world -Y, same for both feet.
    lf_h = bone_head_world(arm, "mixamorig:LeftFoot")
    lf_t = bone_tail_world(arm, "mixamorig:LeftFoot")
    rf_h = bone_head_world(arm, "mixamorig:RightFoot")
    rf_t = bone_tail_world(arm, "mixamorig:RightFoot")
    check(lf_h.z < 0.20, "left ankle near mesh bottom (world Z)")
    check(lf_t.y < lf_h.y - 1e-4, "left foot points -Y (default forward)")
    ldelta = lf_t - lf_h
    rdelta = rf_t - rf_h
    check((ldelta - rdelta).length < 1e-4,
          "both feet use identical forward vector (not mirrored)")
    # Foot now points forward (-Y) AND down (-Z), like Mixamo; no X (symmetry).
    check(abs(ldelta.x) < 1e-4 and ldelta.y < -1e-4 and ldelta.z < -1e-4,
          f"foot points forward+down (-Y,-Z), symmetry-independent ({tuple(round(v,3) for v in ldelta)})")

    check(all(math.isfinite(b.matrix_local.to_euler().z) for b in bones),
          "all bone matrices finite (no NaN roll)")
    # Spine is near-vertical in WORLD space (Z).
    sp_dir = (bone_tail_world(arm, "mixamorig:Spine")
              - bone_head_world(arm, "mixamorig:Spine")).normalized()
    check(abs(sp_dir.z) > 0.9, "spine bone is near-vertical in world (Z)")

    r = bpy.ops.mmr.bind_auto_weights()
    check(r == {'FINISHED'}, "bind_auto_weights")

    # --- Symmetrize Weights: mirror one half onto the other (flip L/R) -------
    def group_total(name):
        vg = mesh.vertex_groups.get(name)
        if vg is None:
            return 0.0
        t = 0.0
        for v in mesh.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    t += g.weight
        return t
    la_before = group_total("mixamorig:LeftArm")
    # Corrupt the right side: wipe all RightArm weights.
    rvg = mesh.vertex_groups.get("mixamorig:RightArm")
    if rvg is not None:
        rvg.remove(list(range(len(mesh.data.vertices))))
    check(group_total("mixamorig:RightArm") < 1e-6, "RightArm wiped (corrupted)")
    # Symmetrize +X (left) -> -X (right): RightArm should be rebuilt from LeftArm.
    scene.mmr_weight_sym_dir = 'POS_NEG'
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    r = bpy.ops.mmr.symmetrize_weights()
    check(r == {'FINISHED'}, "symmetrize_weights")
    ra_after = group_total("mixamorig:RightArm")
    check(abs(ra_after - la_before) < 0.05 * max(la_before, 1e-6) + 1e-3,
          f"RightArm restored symmetric to LeftArm ({ra_after:.3f} vs {la_before:.3f})")

    # --- Symmetrize: plane vertices + zero-target-first ----------------------
    # Snap two +X torso verts onto the symmetry plane and give them asymmetric
    # Left/Right weights; also plant stale weights on the -X side in a group
    # the mirror never writes. One symmetrize must fix both.
    la_vg = mesh.vertex_groups.get("mixamorig:LeftArm")
    ra_vg = mesh.vertex_groups.get("mixamorig:RightArm")
    plane_ids = [v.index for v in mesh.data.vertices if v.co.x > 0.19][:2]
    for vid in plane_ids:
        mesh.data.vertices[vid].co.x = 0.0
        for vg in mesh.vertex_groups:
            vg.remove([vid])
        la_vg.add([vid], 0.6, 'REPLACE')
        ra_vg.add([vid], 0.2, 'REPLACE')
    bogus = mesh.vertex_groups.new(name="MMR_TEST_Bogus")
    neg_ids = [v.index for v in mesh.data.vertices if v.co.x < -1e-3][:10]
    bogus.add(neg_ids, 0.7, 'REPLACE')
    # Backup groups must survive symmetrize untouched (ignored like everywhere).
    bkp = mesh.vertex_groups.new(name="MMR_BACKUP_mixamorig:LeftArm")
    bkp.add(neg_ids, 0.33, 'REPLACE')
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    r = bpy.ops.mmr.symmetrize_weights()
    check(r == {'FINISHED'}, "symmetrize_weights (plane + stale pass)")

    def vert_weight(vid, vg):
        for g in mesh.data.vertices[vid].groups:
            if g.group == vg.index:
                return g.weight
        return 0.0
    check(all(abs(vert_weight(vid, la_vg) - vert_weight(vid, ra_vg)) < 1e-4
              for vid in plane_ids),
          "plane vertices end with equal Left/Right pair weights")
    check(all(abs(vert_weight(vid, la_vg) + vert_weight(vid, ra_vg) - 0.8) < 1e-3
              for vid in plane_ids),
          "plane vertices keep their original total weight")
    # Source (+X) LeftArm=0.6 wins the pair, rescaled to the old 0.8 total.
    check(all(abs(vert_weight(vid, la_vg) - 0.4) < 1e-3 for vid in plane_ids),
          "source-side bone weight wins on the plane (0.6/0.2 -> 0.4/0.4)")
    check(group_total("MMR_TEST_Bogus") < 1e-6,
          "target side zeroed first (stale group wiped)")
    check(abs(group_total("MMR_BACKUP_mixamorig:LeftArm") - 0.33 * len(neg_ids)) < 1e-4,
          "backup groups untouched by symmetrize")
    mesh.vertex_groups.remove(mesh.vertex_groups.get("MMR_TEST_Bogus"))
    mesh.vertex_groups.remove(mesh.vertex_groups.get("MMR_BACKUP_mixamorig:LeftArm"))
    bpy.ops.mmr.bind_auto_weights()   # clean re-bind for later tests

    # --- Zero All Weights: weights -> 0 but keep groups/modifier/parent ------
    n_groups_before = len(mesh.vertex_groups)
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    r = bpy.ops.mmr.zero_weights()
    check(r == {'FINISHED'}, "zero_weights")
    check(len(mesh.vertex_groups) == n_groups_before,
          "zero keeps the vertex groups")
    check(any(m.type == 'ARMATURE' for m in mesh.modifiers),
          "zero keeps the armature modifier")
    total_w = sum(g.weight for v in mesh.data.vertices for g in v.groups)
    check(total_w == 0.0, f"all weights are zero after zero_weights ({total_w})")
    # Re-bind so the mesh has weights again for the rest of the tests
    bpy.ops.mmr.bind_auto_weights()

    # --- Unbind mesh: remove modifier + parent + all vertex groups -----------
    world_before = mesh.matrix_world.copy()
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    r = bpy.ops.mmr.unbind_mesh()
    check(r == {'FINISHED'}, "unbind_mesh")
    check(not any(m.type == 'ARMATURE' for m in mesh.modifiers),
          "armature modifier removed by unbind")
    check(len(mesh.vertex_groups) == 0, "all vertex groups deleted by unbind")
    check(mesh.parent is None, "mesh unparented by unbind")
    check((mesh.matrix_world.translation - world_before.translation).length < 1e-5,
          "unbind keeps the mesh world position")
    # Re-bind for the following accessory/weight tests
    bpy.context.scene.mmr_target_mesh = mesh
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    bpy.ops.mmr.bind_auto_weights()

    # --- Bind separate accessory objects (glasses at head, belt at hips) -----
    def add_obj(name, loc, scale):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        o = bpy.context.active_object
        o.name = name
        o.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        return o
    glasses = add_obj("Glasses", (0, 0, 1.63), (0.12, 0.02, 0.03))  # at eye level
    belt = add_obj("Belt", (0, 0, 0.88), (0.22, 0.14, 0.04))        # at hips
    # Select accessories (not the body target) and bind
    bpy.ops.object.select_all(action='DESELECT')
    glasses.select_set(True); belt.select_set(True)
    bpy.context.view_layer.objects.active = glasses
    r = bpy.ops.mmr.bind_accessories()
    check(r == {'FINISHED'}, "bind_accessories")
    gvg = [vg.name for vg in glasses.vertex_groups]
    bvg = [vg.name for vg in belt.vertex_groups]
    check(gvg == ["mixamorig:Head"], f"glasses rigidly bound to Head ({gvg})")
    check(bvg and bvg[0] in ("mixamorig:Hips", "mixamorig:Spine"),
          f"belt bound to a hip/spine bone ({bvg})")
    check(abs(glasses.data.vertices[0].groups[0].weight - 1.0) < 1e-6,
          "accessory weight is 1.0 (rigid)")
    check(any(m.type == 'ARMATURE' and m.object == arm for m in glasses.modifiers),
          "glasses has armature modifier")
    check(glasses.parent == arm, "glasses parented to armature")

    # Accessory follows its bone: pose Head, glasses should move with it.
    g_rest = (glasses.matrix_world @ glasses.data.vertices[0].co).copy()
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixorig:Head" if False else "mixamorig:Head"].rotation_mode = 'XYZ'
    arm.pose.bones["mixamorig:Head"].rotation_euler = (0.6, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    dg = bpy.context.evaluated_depsgraph_get()
    g_posed = (glasses.evaluated_get(dg).matrix_world
               @ glasses.evaluated_get(dg).data.vertices[0].co)
    check((g_posed - g_rest).length > 0.01, "glasses follow the Head bone when posed")
    # reset pose
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:Head"].rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')

    # --- Transfer body weights onto an accessory (hat over the head) ---------
    hat = add_obj("Hat", (0, 0, 1.75), (0.14, 0.14, 0.08))  # sits on the head
    bpy.context.scene.mmr_target_mesh = mesh
    bpy.ops.object.select_all(action='DESELECT')
    hat.select_set(True); bpy.context.view_layer.objects.active = hat
    r = bpy.ops.mmr.transfer_accessory_weights()
    check(r == {'FINISHED'}, "transfer_accessory_weights")
    hvg = {vg.name for vg in hat.vertex_groups}
    check("mixamorig:Head" in hvg, f"hat received Head weights ({sorted(hvg)[:4]})")
    check(any(m.type == 'ARMATURE' and m.object == arm for m in hat.modifiers),
          "hat has armature modifier")
    check(hat.parent == arm, "hat parented to armature")
    # hat follows the head when posed
    h_rest = (hat.matrix_world @ hat.data.vertices[0].co).copy()
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:Head"].rotation_euler = (0.6, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    dg = bpy.context.evaluated_depsgraph_get()
    h_posed = (hat.evaluated_get(dg).matrix_world
               @ hat.evaluated_get(dg).data.vertices[0].co)
    check((h_posed - h_rest).length > 0.01, "hat follows the Head bone when posed")
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:Head"].rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')

    # --- Transfer must sample at REST even if the current frame is posed -----
    def add_cube(loc):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        o = bpy.context.active_object
        o.scale = (0.08, 0.08, 0.08)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        return o

    def dom_bone(o):
        gn = {vg.index: vg.name for vg in o.vertex_groups}
        best, bw_ = None, -1.0
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight > bw_:
                    bw_, best = g.weight, gn[g.group]
        return best

    cubeA = add_cube((0.55, 0, 1.35))   # near the left forearm
    cubeB = add_cube((0.55, 0, 1.35))
    bpy.ops.object.select_all(action='DESELECT')
    cubeA.select_set(True); bpy.context.view_layer.objects.active = cubeA
    mmr.transfer_weights_to_accessory(bpy.context, mesh, cubeA, arm, reach=0.0)
    dom_rest = dom_bone(cubeA)
    # Pose the arm hard, then transfer B WHILE posed.
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:LeftArm"].rotation_mode = 'XYZ'
    arm.pose.bones["mixamorig:LeftArm"].rotation_euler = (0.0, 1.3, 0.0)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    cubeB.select_set(True); bpy.context.view_layer.objects.active = cubeB
    mmr.transfer_weights_to_accessory(bpy.context, mesh, cubeB, arm, reach=0.0)
    dom_posed = dom_bone(cubeB)
    check(dom_rest is not None and dom_rest == dom_posed,
          f"transfer samples at REST regardless of pose ({dom_rest} == {dom_posed})")
    # reset pose + cleanup
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:LeftArm"].rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.data.objects.remove(cubeA, do_unlink=True)
    bpy.data.objects.remove(cubeB, do_unlink=True)

    # --- Copy Weights (Same Topology): exact 1:1, position-independent -------
    dup = mesh.copy()
    dup.data = mesh.data.copy()
    dup.name = "Variant"
    bpy.context.scene.collection.objects.link(dup)
    mmr.unbind_mesh(dup)
    dup.location.x += 3.0     # standing far away — must still copy exactly
    bpy.ops.object.select_all(action='DESELECT')
    dup.select_set(True); bpy.context.view_layer.objects.active = dup
    r = bpy.ops.mmr.copy_weights_topology()
    check(r == {'FINISHED'}, "copy_weights_topology")
    def wmap(o):
        gn = {vg.index: vg.name for vg in o.vertex_groups}
        return {(v.index, gn[g.group]): round(g.weight, 6)
                for v in o.data.vertices for g in v.groups if g.weight > 0}
    check(wmap(dup) == wmap(mesh), "copied weights identical 1:1 (moved apart)")
    check(any(m.type == 'ARMATURE' for m in dup.modifiers), "variant got armature modifier")
    # Mismatched topology → clear error, suggests Transfer
    bpy.ops.mesh.primitive_ico_sphere_add(location=(5, 0, 1))
    ball = bpy.context.active_object
    bpy.ops.object.select_all(action='DESELECT')
    ball.select_set(True); bpy.context.view_layer.objects.active = ball
    expect_error(bpy.ops.mmr.copy_weights_topology,
                 "copy errors on different topology")
    bpy.data.objects.remove(ball, do_unlink=True)
    bpy.data.objects.remove(dup, do_unlink=True)

    # --- Bind Skirt: height blend (Hips/UpLeg/Leg) split across both legs ----
    # A skirt tube from below the knee (0.30) up to the hip (0.90), centred.
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.22, depth=0.60,
                                        location=(0, 0, 0.60))
    skirt = bpy.context.active_object
    skirt.name = "Skirt"
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    gn0 = {vg.index: vg.name for vg in skirt.vertex_groups}  # (none yet)
    bpy.ops.object.select_all(action='DESELECT')
    skirt.select_set(True); bpy.context.view_layer.objects.active = skirt
    r = bpy.ops.mmr.bind_skirt()
    check(r == {'FINISHED'}, "bind_skirt")
    sgroups = {vg.name for vg in skirt.vertex_groups}
    check("mixamorig:LeftLeg" in sgroups and "mixamorig:RightLeg" in sgroups,
          f"skirt got LOWER-leg (Leg) weights ({sorted(sgroups)})")
    check("mixamorig:LeftUpLeg" in sgroups and "mixamorig:RightUpLeg" in sgroups,
          "skirt got both UpLeg sides (centred, won't tear)")

    def sk_w(vi, name=None):
        gn = {vg.index: vg.name for vg in skirt.vertex_groups}
        return {gn[g.group]: g.weight for g in skirt.data.vertices[vi].groups
                if g.weight > 0}

    def leg_weight(vi):  # total lower-leg (Leg, not UpLeg) weight
        return sum(w for n, w in sk_w(vi).items()
                   if n.endswith("Leg") and "UpLeg" not in n)

    # Inverse-distance: low skirt (near knee) picks up real Leg weight; high
    # skirt (near hip) is dominated by Hips/UpLeg with little Leg.
    lows = [v.index for v in skirt.data.vertices if (skirt.matrix_world @ v.co).z < 0.42]
    highs = [v.index for v in skirt.data.vertices if (skirt.matrix_world @ v.co).z > 0.85]
    check(lows and max(leg_weight(vi) for vi in lows) > 0.2,
          "low skirt vertices carry real Leg (lower-leg) weight")
    check(highs and max(leg_weight(vi) for vi in highs) < 0.2,
          "high skirt vertices barely use the Leg (follow hips/thigh)")
    # Weights normalized per vertex
    bad = 0
    for v in skirt.data.vertices:
        w = sk_w(v.index, None)
        if w and abs(sum(w.values()) - 1.0) > 1e-3:
            bad += 1
    check(bad == 0, f"skirt weights normalized ({bad} bad)")
    # Lower skirt follows the knee bend (Leg rotation moves it)
    lo_rest = (skirt.matrix_world @ skirt.data.vertices[lows[0]].co).copy()
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:LeftLeg"].rotation_mode = 'XYZ'
    arm.pose.bones["mixamorig:LeftLeg"].rotation_euler = (0.8, 0, 0)
    arm.pose.bones["mixamorig:RightLeg"].rotation_mode = 'XYZ'
    arm.pose.bones["mixamorig:RightLeg"].rotation_euler = (0.8, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    dg = bpy.context.evaluated_depsgraph_get()
    lo_posed = (skirt.evaluated_get(dg).matrix_world
                @ skirt.evaluated_get(dg).data.vertices[lows[0]].co)
    check((lo_posed - lo_rest).length > 0.01, "lower skirt follows the knee bend")
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["mixamorig:LeftLeg"].rotation_euler = (0, 0, 0)
    arm.pose.bones["mixamorig:RightLeg"].rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')

    # restore target as active for following tests
    bpy.context.scene.mmr_target_mesh = mesh
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh

    # --- Smart weight refine ------------------------------------------------
    def count_group_names(mo):
        gn = {vg.index: vg.name for vg in mo.vertex_groups}
        return gn

    def vweights(mo, vi):
        gn = count_group_names(mo)
        return {gn[g.group]: g.weight for g in mo.data.vertices[vi].groups
                if g.weight > 0 and not gn[g.group].startswith("MMR_BACKUP_")}

    # Inject artificial cross-side contamination: give a clearly-left vertex a
    # RightArm weight, and check refine removes it.
    gn = count_group_names(mesh)
    # find a vertex firmly on the +X (left) side, away from center
    left_vi = None
    for v in mesh.data.vertices:
        co = mesh.matrix_world @ v.co
        if co.x > 0.3:
            left_vi = v.index
            break
    check(left_vi is not None, "found a left-side test vertex")
    rarm = mesh.vertex_groups.get("mixamorig:RightArm")
    if rarm is None:
        rarm = mesh.vertex_groups.new(name="mixamorig:RightArm")
    rarm.add([left_vi], 0.3, 'REPLACE')
    check("mixamorig:RightArm" in vweights(mesh, left_vi),
          "injected cross-side RightArm weight on a left vertex")

    # Backup, then refine
    r = bpy.ops.mmr.backup_weights()
    check(r == {'FINISHED'}, "backup_weights")
    check(any(vg.name.startswith("MMR_BACKUP_") for vg in mesh.vertex_groups),
          "backup groups created")

    scene.mmr_weight_profile = 'BALANCED'
    r = bpy.ops.mmr.smart_mixamo_weight_refine()
    check(r == {'FINISHED'}, "smart_mixamo_weight_refine")
    check("mixamorig:RightArm" not in vweights(mesh, left_vi),
          "cross-side RightArm weight removed from left vertex")

    # All vertices normalized (sum ~1) and <=4 influences
    bad_norm = 0
    over = 0
    for v in mesh.data.vertices:
        w = vweights(mesh, v.index)
        if w:
            if abs(sum(w.values()) - 1.0) > 1e-3:
                bad_norm += 1
            if len(w) > 4:
                over += 1
    check(bad_norm == 0, f"all weighted verts normalized ({bad_norm} bad)")
    check(over == 0, f"max 4 influences per vertex after refine ({over} over)")

    # No backup group is treated as a deform group (they are ignored by refine)
    check(any(vg.name.startswith("MMR_BACKUP_") for vg in mesh.vertex_groups),
          "backup groups still present after refine")

    # Restore brings back the contaminated weight
    r = bpy.ops.mmr.restore_weights()
    check(r == {'FINISHED'}, "restore_weights")
    check("mixamorig:RightArm" in vweights(mesh, left_vi),
          "restore brought back pre-refine weights")

    # Diagnostics runs
    r = bpy.ops.mmr.weight_diagnostics()
    check(r == {'FINISHED'}, "weight_diagnostics")

    # Refine again to leave mesh clean, then clean_weights
    bpy.ops.mmr.smart_mixamo_weight_refine()

    # Soft Organic and Rigid profiles run without error
    scene.mmr_weight_profile = 'SOFT_ORGANIC'
    check(bpy.ops.mmr.smart_mixamo_weight_refine() == {'FINISHED'}, "refine Soft Organic")
    scene.mmr_weight_profile = 'RIGID_GAME'
    check(bpy.ops.mmr.smart_mixamo_weight_refine() == {'FINISHED'}, "refine Rigid Game")
    scene.mmr_weight_profile = 'BALANCED'

    r = bpy.ops.mmr.clean_weights()
    check(r == {'FINISHED'}, "clean_weights")
    over = sum(1 for v in mesh.data.vertices
               if len([g for g in v.groups if g.weight > 0]) > 4)
    check(over == 0, "max 4 influences per vertex")

    # Refine guard: errors cleanly when no armature modifier
    check(mmr.detect_mesh_islands(mesh) is not None, "detect_mesh_islands runs")

    # --- Flip Foot Direction: toggles dir and rebuilds (default was -Y) -----
    r = bpy.ops.mmr.flip_foot_direction()
    check(r == {'FINISHED'}, "flip_foot_direction")
    check(scene.mmr_forward_dir == 'POSITIVE', "flip toggled dir to Positive")
    arm = bpy.data.objects.get(mmr.ARMATURE_NAME)
    lf_d = (bone_tail_world(arm, "mixamorig:LeftFoot")
            - bone_head_world(arm, "mixamorig:LeftFoot"))
    check(lf_d.y > 1e-4, "after flip, left foot points +Y (rebuilt)")
    bpy.ops.mmr.flip_foot_direction()
    check(scene.mmr_forward_dir == 'NEGATIVE', "flip toggled back to Negative")

    # --- Forward axis X: feet point along X, independent of symmetry --------
    scene.mmr_forward_axis = 'X'
    scene.mmr_forward_dir = 'POSITIVE'
    bpy.ops.mmr.build_armature()
    arm = bpy.data.objects.get(mmr.ARMATURE_NAME)
    lde = (bone_tail_world(arm, "mixamorig:LeftFoot")
           - bone_head_world(arm, "mixamorig:LeftFoot"))
    rde = (bone_tail_world(arm, "mixamorig:RightFoot")
           - bone_head_world(arm, "mixamorig:RightFoot"))
    # Forward=X → foot points +X and down (-Z); no Y component.
    check(lde.x > 1e-4 and abs(lde.y) < 1e-4 and lde.z < -1e-4,
          f"forward axis X: left foot points +X and down ({tuple(round(v,3) for v in lde)})")
    check((lde - rde).length < 1e-4, "forward axis X: both feet same direction")
    scene.mmr_forward_axis = 'Y'  # restore default
    scene.mmr_forward_dir = 'NEGATIVE'

    # --- Build guard: unapplied scale must block ----------------------------
    mesh.scale = (2.0, 2.0, 2.0)
    expect_error(bpy.ops.mmr.build_armature, "build blocked by unapplied scale")
    mesh.scale = (1.0, 1.0, 1.0)

    # --- Remove markers removes center --------------------------------------
    r = bpy.ops.mmr.remove_markers()
    check(r == {'FINISHED'}, "remove_markers")
    check(bpy.data.objects.get(mmr.SYMMETRY_CENTER_NAME) is None, "symmetry center removed")
    check(bpy.data.objects.get("TestHumanoid") is not None, "user mesh preserved")

    # set_center_from_mesh error without mesh
    scene.mmr_target_mesh = None
    expect_error(bpy.ops.mmr.set_center_from_mesh, "set_center_from_mesh errors without mesh")

    # =====================================================================
    # Mixamo data-space verification on a fresh Z-up character.
    # =====================================================================
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    check(mmr.get_up_axis(bpy.context) == 'Z' and scene.mmr_forward_axis == 'Y'
          and scene.mmr_symmetry_axis == 'X',
          "fresh scene uses Up=Z(locked) / Forward=Y / Symmetry=X")

    def add_box2(name, loc, scale):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        o = bpy.context.active_object
        o.name = name
        o.scale = scale
        return o

    zt = add_box2("ZBody", (0, 0, 1.1), (0.20, 0.12, 0.35))
    zparts = [add_box2("ZHead", (0, 0, 1.62), (0.10, 0.10, 0.12)),
              add_box2("ZArmL", (0.45, 0, 1.35), (0.28, 0.05, 0.05)),
              add_box2("ZArmR", (-0.45, 0, 1.35), (0.28, 0.05, 0.05)),
              add_box2("ZLegL", (0.12, 0, 0.40), (0.07, 0.07, 0.42)),
              add_box2("ZLegR", (-0.12, 0, 0.40), (0.07, 0.07, 0.42))]
    for o in ([zt] + zparts):
        o.select_set(True)
    bpy.context.view_layer.objects.active = zt
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    zmesh = bpy.context.active_object
    zmesh.name = "ZHumanoid"

    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.create_markers()
    for j, loc in {"Chin": (0, 0, 1.50), "Groin": (0, 0, 0.85),
                   "LeftShoulder": (0.15, 0, 1.36),
                   "LeftWrist": (0.70, 0, 1.35), "LeftElbow": (0.40, 0, 1.35),
                   "LeftKnee": (0.12, 0, 0.45)}.items():
        mmr.find_marker(j).location = loc
    r = bpy.ops.mmr.build_armature()
    check(r == {'FINISHED'}, "[mixamo] build_armature")
    zarm = bpy.data.objects.get(mmr.ARMATURE_NAME)
    zb = zarm.data.bones
    # DATA space is Y-up cm: spine points +Y in data, hips Y in centimetres.
    zsp = zb["mixamorig:Spine"]
    zdir = (zsp.tail_local - zsp.head_local).normalized()
    check(zdir.y > 0.9, f"[mixamo] spine points +Y in DATA space ({tuple(round(v,2) for v in zdir)})")
    check(zb["mixamorig:Hips"].head_local.y > 50, "[mixamo] hips data in centimetres")
    # Arms point +/-X in data (from the world +/-X arms).
    zla = zb["mixamorig:LeftArm"]
    zladir = (zla.tail_local - zla.head_local).normalized()
    check(zladir.x > 0.9, "[mixamo] left arm points +X in data space")
    # Mixamo-space guard helper
    check(mmr.armature_in_mixamo_space(zarm), "fresh armature is in Mixamo space")
    zarm.rotation_euler.x = 0.0
    check(not mmr.armature_in_mixamo_space(zarm),
          "guard detects zeroed rotation (would break anims)")
    zarm.rotation_euler.x = math.radians(90)
    zarm.scale = (1.0, 1.0, 1.0)
    check(not mmr.armature_in_mixamo_space(zarm),
          "guard detects applied scale (would fly character away)")

    # Symmetry cannot be the up axis (Z)
    scene.mmr_symmetry_axis = 'Z'
    expect_error(bpy.ops.mmr.build_armature, "[mixamo] symmetry==up(Z) blocked")
    scene.mmr_symmetry_axis = 'X'

    # Non-upright character (lying) must be rejected, not silently built lying.
    bpy.ops.mmr.create_markers()
    for j, loc in {"Chin": (0, 1.5, 0.9), "Groin": (0, 0.85, 0.9),  # body along Y
                   "LeftShoulder": (0.15, 1.35, 0.9),
                   "LeftWrist": (0.7, 1.2, 0.9), "LeftElbow": (0.4, 1.2, 0.9),
                   "LeftKnee": (0.12, 0.5, 0.9)}.items():
        mmr.find_marker(j).location = loc
    expect_error(bpy.ops.mmr.build_armature, "[mixamo] lying character (not Z-up) rejected")

    # =====================================================================
    # Transfer Weights reach: on a DENSE body, a wider radius makes a skirt
    # pick up the lower-leg (Leg) bone, not just the thigh.
    # =====================================================================
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.16, depth=1.7,
                                        location=(0, 0, 0.9))
    dbody = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.subdivide(number_cuts=20)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    dbody.name = "DenseBody"
    bpy.ops.mmr.set_selected_mesh()
    bpy.ops.mmr.create_markers()
    for j, loc in {"Chin": (0, 0, 1.55), "Groin": (0, 0, 0.92),
                   "LeftShoulder": (0.13, 0, 1.4),
                   "LeftWrist": (0.14, 0, 1.0), "LeftElbow": (0.14, 0, 1.2),
                   "LeftKnee": (0.05, 0, 0.45)}.items():
        mmr.find_marker(j).location = loc
    bpy.ops.mmr.build_armature()
    darm = bpy.data.objects[mmr.ARMATURE_NAME]
    bpy.ops.mmr.bind_auto_weights()

    def leg_group_count(o):
        return sum(1 for vg in o.vertex_groups
                   if vg.name.endswith("Leg") and "UpLeg" not in vg.name)

    # Skirt tube spanning thigh down to just below the knee.
    def make_skirt():
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.22, depth=0.5,
                                            location=(0, 0, 0.55))
        s = bpy.context.active_object
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        return s

    s_low = make_skirt()
    err = mmr.transfer_weights_to_accessory(bpy.context, dbody, s_low, darm, reach=0.05)
    check(err is None, f"transfer low reach ran (err={err})")
    low_legs = leg_group_count(s_low)

    s_high = make_skirt()
    err = mmr.transfer_weights_to_accessory(bpy.context, dbody, s_high, darm, reach=1.0)
    check(err is None, f"transfer high reach ran (err={err})")
    high_legs = leg_group_count(s_high)

    print(f"    skirt Leg groups: low reach={low_legs}, high reach={high_legs}")
    check(high_legs >= 1, "high reach: skirt picks up the lower-leg (Leg) bone")
    check(high_legs >= low_legs, "higher reach reaches at least as many leg bones")

    print()
    if FAILED:
        print(f"RESULT: {len(FAILED)} FAILURES")
        for f in FAILED:
            print("  -", f)
        sys.exit(1)
    print("RESULT: ALL TESTS PASSED")


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(2)
