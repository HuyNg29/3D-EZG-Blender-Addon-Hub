# Mixamo Animation Library — Blender 4.x / 5.x
# Quét thư mục chứa file FBX tải từ Mixamo, liệt kê trong sidebar,
# và áp animation lên armature đang chọn (rig Mixamo cùng bộ xương).

bl_info = {
    "name": "Mixamo Animation Library",
    "author": "EasyGoing Visual",
    "version": (1, 4, 2),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Sidebar (N) > Mixamo Lib",
    "description": "Browse a folder of Mixamo FBX files, apply animations to the selected armature, and floor-lock the feet",
    "category": "Animation",
}

import os
import re
import bpy
from mathutils import Euler, Quaternion, Vector
from bpy.types import (
    Operator,
    Panel,
    PropertyGroup,
    UIList,
)
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


# Feature flag: hide the foot-grounding UI block (Ground Feet on Apply, Foot IK
# / Floor Lock, Floor Z, and the Ground Feet / Clear buttons). Set True to
# re-enable it later. The operators/functions stay registered — only the panel
# section is hidden.
SHOW_GROUNDING = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_fbx_files(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.lower().endswith(".fbx"):
                yield os.path.join(dirpath, fn)


def _import_fbx(filepath):
    """Import an FBX file, return (armature, imported_objects)."""
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.fbx(
            filepath=filepath,
            ignore_leaf_bones=True,
            automatic_bone_orientation=False,
        )
    except AttributeError:
        # Blender builds where the Python FBX importer is replaced by the
        # native one (bpy.ops.wm.fbx_import).
        bpy.ops.wm.fbx_import(filepath=filepath)
    imported = [ob for ob in bpy.data.objects if ob not in before]
    armature = next((ob for ob in imported if ob.type == 'ARMATURE'), None)
    return armature, imported


def _delete_objects(objects):
    """Remove objects and their now-unused data blocks."""
    meshes, armatures = set(), set()
    for ob in objects:
        if ob.type == 'MESH' and ob.data:
            meshes.add(ob.data)
        elif ob.type == 'ARMATURE' and ob.data:
            armatures.add(ob.data)
        bpy.data.objects.remove(ob, do_unlink=True)
    for me in meshes:
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for arm in armatures:
        if arm.users == 0:
            bpy.data.armatures.remove(arm)


def _assign_action(target, action):
    """Assign an action, handling slotted actions (Blender 4.4+)."""
    if target.animation_data is None:
        target.animation_data_create()
    ad = target.animation_data
    ad.action = action
    if hasattr(ad, "action_slot") and getattr(action, "slots", None):
        if len(action.slots):
            try:
                ad.action_slot = action.slots[0]
            except Exception:
                pass


def _stamp_source(action, filepath):
    """Record which FBX (and its mtime) this action was imported from."""
    action["mixlib_src_path"] = filepath
    try:
        action["mixlib_src_mtime"] = os.path.getmtime(filepath)
    except OSError:
        pass


def _is_stale(action, filepath):
    """True when the FBX on disk changed since this action was imported.

    A re-downloaded animation (same filename, new bake — e.g. after the
    character was re-rigged/re-uploaded on Mixamo) must not be served from
    the old in-blend action, or the pose comes out bent/crooked.
    """
    try:
        cur = os.path.getmtime(filepath)
    except OSError:
        return False  # file missing — keep the in-blend action
    saved = action.get("mixlib_src_mtime")
    if saved is None:
        # Unstamped: imported before stamping existed, possibly with manual
        # keyframe edits. Never treat as stale — user edits must survive.
        # Apply/Import All adopt-stamp these so future re-downloads are seen.
        return False
    return abs(saved - cur) > 0.5


def _replace_action(old, new):
    """Point every user of `old` (assignments, NLA strips) at `new`, delete
    `old`, and give `new` its name."""
    name = old.name
    old.user_remap(new)
    bpy.data.actions.remove(old)
    new.name = name


def _action_bone_names(action):
    names = set()
    for fc in action.fcurves:
        m = re.match(r'pose\.bones\["(.+?)"\]', fc.data_path)
        if m:
            names.add(m.group(1))
    return names


def _strip_root_motion(action):
    """Remove hips location channels that carry net displacement.

    A travelling channel (walk forward) has end-start drift close to its full
    value range; bobbing/sway channels return near their start. Comparing
    drift against range keeps the check unit- and scale-independent.
    """
    removed = 0
    f_start, f_end = action.frame_range
    for fc in list(action.fcurves):
        if not fc.data_path.endswith(".location"):
            continue
        if "hips" not in fc.data_path.lower():
            continue
        samples = [fc.evaluate(f_start + (f_end - f_start) * i / 20.0) for i in range(21)]
        rng = max(samples) - min(samples)
        drift = abs(samples[-1] - samples[0])
        if rng > 1e-6 and drift > 0.6 * rng:
            action.fcurves.remove(fc)
            removed += 1
    return removed


# Rest-pose mismatch above this fraction of skeleton size triggers a
# constraint-bake retarget instead of a raw F-curve copy on import.
_RETARGET_THRESHOLD = 0.02


def _rest_mismatch(src_arm, dst_arm):
    """Average rest-pose head distance between same-named bones, normalized by
    skeleton size. ~0 when the FBX was baked on this very skeleton; large when
    the rest poses differ (a direct F-curve copy would bend the character)."""
    src = {b.name: b.head_local for b in src_arm.data.bones}
    dst = {b.name: b.head_local for b in dst_arm.data.bones}
    common = set(src) & set(dst)
    if not common:
        return None
    avg = sum((src[n] - dst[n]).length for n in common) / len(common)
    size = max((v.length for v in dst.values()), default=0.0)
    if size < 1e-6:
        return None
    return avg / size


def _retarget_bake(context, src_arm, target, src_action):
    """Retarget src_action onto `target` by constraining same-named bones to
    the imported source skeleton (world space) and baking the solved pose.
    Correct even when the two rigs have different rest poses. Returns the
    baked action (left assigned on `target`)."""
    f0, f1 = int(src_action.frame_range[0]), int(src_action.frame_range[1])

    if target.animation_data is None:
        target.animation_data_create()
    ad = target.animation_data

    # Isolate the bake: the previously assigned action and any unmuted NLA
    # strips would leak bone location/scale values (constraints only override
    # rotations + hips location) straight into the baked keys.
    ad.action = None
    prev_mutes = [(t, t.mute) for t in ad.nla_tracks]
    for t in ad.nla_tracks:
        t.mute = True
    for pb in target.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)

    cons = []
    for pb in target.pose.bones:
        if pb.name not in src_arm.pose.bones:
            continue
        c = pb.constraints.new('COPY_ROTATION')
        c.name = "MIXLIB_RT"
        c.target = src_arm
        c.subtarget = pb.name
        cons.append((pb, c))
        if pb.parent is None or "hips" in pb.name.lower():
            c = pb.constraints.new('COPY_LOCATION')
            c.name = "MIXLIB_RT"
            c.target = src_arm
            c.subtarget = pb.name
            cons.append((pb, c))

    try:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.nla.bake(
            frame_start=f0, frame_end=f1, step=1,
            only_selected=False, visual_keying=True,
            clear_constraints=False, clear_parents=False,
            use_current_action=False, bake_types={'POSE'},
        )
        bpy.ops.object.mode_set(mode='OBJECT')
    finally:
        for pb, c in cons:
            try:
                pb.constraints.remove(c)
            except Exception:
                pass
        for t, m in prev_mutes:
            t.mute = m

    return ad.action


def _rescan(props):
    """Refill the animation list from the library folder. Returns item count or -1."""
    props.items.clear()
    root = bpy.path.abspath(props.library_path)
    if not root or not os.path.isdir(root):
        return -1
    for path in _iter_fbx_files(root):
        item = props.items.add()
        item.name = os.path.splitext(os.path.basename(path))[0]
        item.filepath = path
    props.active_index = min(props.active_index, max(0, len(props.items) - 1))
    return len(props.items)


def _active_armature(context):
    ob = context.active_object
    if ob and ob.type == 'ARMATURE':
        return ob
    for ob in context.selected_objects:
        if ob.type == 'ARMATURE':
            return ob
    return None


# --- Foot floor-lock (grounding) -------------------------------------------
# A Mixamo action baked to standard proportions, copied directly onto a
# differently-proportioned character (e.g. a short/stocky one), makes the feet
# sink through the floor because there is no proportion retargeting. This bakes
# a per-frame vertical offset onto the armature OBJECT so the lowest foot stays
# on the floor — a practical "floor lock" (not full foot IK).

def _ground_bone_names(arm):
    """Pose-bone names that touch the ground (feet / toes)."""
    names = []
    for pb in arm.pose.bones:
        low = pb.name.lower()
        if "foot" in low or "toebase" in low or low.endswith(":toe"):
            names.append(pb.name)
    return names


def _lowest_foot_world_z(arm, names):
    """Lowest world Z among the ground bones' head and tail points."""
    mw = arm.matrix_world
    zs = []
    for name in names:
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        zs.append((mw @ pb.head).z)
        zs.append((mw @ pb.tail).z)
    return min(zs) if zs else None


def _mesh_lowest_world_z(context, arm):
    """Lowest world Z of the armature's deformed child meshes (the true sole)."""
    depsgraph = context.evaluated_depsgraph_get()
    lowest = None
    for child in arm.children_recursive:
        if child.type != 'MESH':
            continue
        ev = child.evaluated_get(depsgraph)
        try:
            me = ev.to_mesh()
        except RuntimeError:
            continue
        mw = ev.matrix_world
        for v in me.vertices:
            z = (mw @ v.co).z
            if lowest is None or z < lowest:
                lowest = z
        ev.to_mesh_clear()
    return lowest


def _clear_object_z_keys(arm):
    """Remove object location-Z keyframes from the armature's active action."""
    ad = arm.animation_data
    if ad is None or ad.action is None:
        return
    for fc in list(ad.action.fcurves):
        if fc.data_path == "location" and fc.array_index == 2:
            ad.action.fcurves.remove(fc)


def _isolate_active_action(arm):
    """Make the assigned active action the ONLY thing driving the rig, and
    return a state token for _restore_isolation().

    Foot grounding reads the *evaluated* (visual) pose and — for Foot IK —
    bakes it straight back into the active action. When an NLA track is soloed,
    the NLA stack overrides the action, or a slotted action's slot is unbound
    (Blender 4.4+), the rig evaluates to some *other* pose (usually rest). A
    visual bake would then stamp that wrong pose over every frame and destroy
    the animation. Disabling NLA and binding the slot for the duration
    guarantees we sample and ground the action we actually mean to.
    """
    ad = arm.animation_data
    if ad is None:
        return None
    saved = {"use_nla": ad.use_nla,
             "solo": [(t, t.is_solo) for t in ad.nla_tracks]}
    ad.use_nla = False
    for t in ad.nla_tracks:
        if t.is_solo:
            t.is_solo = False
    act = ad.action
    if act is not None and hasattr(ad, "action_slot") and getattr(act, "slots", None):
        if len(act.slots) and ad.action_slot is None:
            try:
                ad.action_slot = act.slots[0]
            except Exception:
                pass
    return saved


def _restore_isolation(arm, saved):
    """Undo _isolate_active_action(). The slot binding is left in place (it was
    missing state, not a user choice); NLA enable + solo flags are restored."""
    if saved is None:
        return
    ad = arm.animation_data
    if ad is None:
        return
    ad.use_nla = saved["use_nla"]
    for t, s in saved["solo"]:
        try:
            t.is_solo = s
        except ReferenceError:
            pass          # track removed during the bake


def bake_foot_floor_lock(context, arm, floor_z=0.0):
    """Isolate the active action, then floor-lock. See _bake_foot_floor_lock."""
    iso = _isolate_active_action(arm)
    try:
        return _bake_foot_floor_lock(context, arm, floor_z)
    finally:
        _restore_isolation(arm, iso)


def _bake_foot_floor_lock(context, arm, floor_z=0.0):
    """Bake armature-object Z so the lowest foot stays on the floor each frame.

    Returns (frames_baked, error_message). One of the two is meaningful.
    """
    if arm.animation_data is None or arm.animation_data.action is None:
        return 0, "No animation on the armature. Apply an animation first."
    names = _ground_bone_names(arm)
    if not names:
        return 0, "No foot/toe bones found on this rig."

    scene = context.scene
    action = arm.animation_data.action
    f0, f1 = int(action.frame_range[0]), int(action.frame_range[1])

    orig_z = arm.location.z
    _clear_object_z_keys(arm)          # start from a clean baseline
    arm.location.z = orig_z

    # Foot "thickness": how far the sole (mesh) sits below the foot bone.
    scene.frame_set(f0)
    context.view_layer.update()
    mesh_low = _mesh_lowest_world_z(context, arm)
    bone_low = _lowest_foot_world_z(arm, names)
    thickness = 0.0
    if mesh_low is not None and bone_low is not None:
        thickness = mesh_low - bone_low   # usually negative (sole below bone)

    # Pass 1: measure the lowest foot per frame at the baseline object height.
    needed = {}
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        context.view_layer.update()
        bone_low = _lowest_foot_world_z(arm, names)
        if bone_low is None:
            continue
        # Move the whole rig so (bone_low + thickness) == floor_z.
        needed[f] = orig_z + floor_z - (bone_low + thickness)

    # Pass 2: key the object Z offset.
    for f, z in needed.items():
        arm.location.z = z
        arm.keyframe_insert(data_path="location", index=2, frame=f)

    scene.frame_set(f0)
    return len(needed), None


# --- Foot IK retargeting (adjusts the legs, keeps the body — Mixamo-style) --

_MR = "mixamorig:"


def _leg_defs(arm):
    """Return [(side, upleg, leg, foot)] for legs present on the rig, or None."""
    legs = []
    for side in ("Left", "Right"):
        u, l, f = _MR + side + "UpLeg", _MR + side + "Leg", _MR + side + "Foot"
        if all(n in arm.pose.bones for n in (u, l, f)):
            legs.append((side, u, l, f))
    return legs


def _side_sole_world_z(arm, side):
    """Lowest world Z of a leg's foot (+ toe) bone points."""
    mw = arm.matrix_world
    names = [_MR + side + "Foot"]
    if _MR + side + "ToeBase" in arm.pose.bones:
        names.append(_MR + side + "ToeBase")
    zs = []
    for n in names:
        pb = arm.pose.bones.get(n)
        if pb:
            zs.append((mw @ pb.head).z)
            zs.append((mw @ pb.tail).z)
    return min(zs) if zs else None


def bake_foot_ik(context, arm, floor_z=0.0):
    """Isolate the active action, then Foot-IK ground. See _bake_foot_ik."""
    iso = _isolate_active_action(arm)
    try:
        return _bake_foot_ik(context, arm, floor_z)
    finally:
        _restore_isolation(arm, iso)


def _bake_foot_ik(context, arm, floor_z=0.0):
    """Retarget the legs with 2-bone IK so the feet stay on the floor while the
    body keeps the original animation. Bakes the solved leg pose into the action.

    Returns (frames_baked, error_message).
    """
    if arm.animation_data is None or arm.animation_data.action is None:
        return 0, "No animation on the armature. Apply an animation first."
    legs = _leg_defs(arm)
    if not legs:
        return 0, "Leg bones not found (need mixamorig:{L,R}UpLeg/Leg/Foot)."

    scene = context.scene
    action = arm.animation_data.action
    f0, f1 = int(action.frame_range[0]), int(action.frame_range[1])
    mw = arm.matrix_world

    # Any stale floor-lock object offset would fight the IK — clear it.
    _clear_object_z_keys(arm)
    arm.location.z = 0.0

    # Foot "thickness": how far the mesh sole sits below the foot bones. The IK
    # targets the ankle bone, so we must lift by this extra amount to plant the
    # actual mesh sole (shoe/boot) on the floor rather than the bone.
    scene.frame_set(f0)
    context.view_layer.update()
    mesh_low = _mesh_lowest_world_z(context, arm)
    bone_lows = [z for z in (_side_sole_world_z(arm, s) for s, _, _, _ in legs)
                 if z is not None]
    thickness = 0.0
    if mesh_low is not None and bone_lows:
        thickness = mesh_low - min(bone_lows)   # usually negative (mesh below bone)

    # Guard against baking a frozen rig over the animation. If the active
    # action never actually poses the bones (it evaluated to rest — unbound
    # slot, NLA override, wrong solo), a visual bake here would overwrite it
    # with a static T-pose. Probe a few upper-body bones via matrix_basis (so it
    # works whatever the rotation mode): every real Mixamo clip, idles included,
    # moves them off identity; a pure rest pose leaves matrix_basis == identity.
    probe = [n for n in (_MR + "Spine", _MR + "Spine1", _MR + "RightArm",
                         _MR + "LeftArm", _MR + "Head") if n in arm.pose.bones]
    pose_has_motion = False

    def _basis_moved(pb):
        mb = pb.matrix_basis
        return sum(abs(mb[i][j] - (1.0 if i == j else 0.0))
                   for i in range(4) for j in range(4)) > 1e-4

    # Pass 1: from the ORIGINAL animation, record the world ankle target per
    # frame (keep horizontal; lift only enough to plant a sinking foot).
    targets = {side: {} for side, _, _, _ in legs}
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        context.view_layer.update()
        if not pose_has_motion:
            if any(_basis_moved(arm.pose.bones[n]) for n in probe):
                pose_has_motion = True
        for side, u, l, fb in legs:
            ankle = mw @ arm.pose.bones[fb].head
            sole = _side_sole_world_z(arm, side)
            # Lift so the mesh sole (sole_bone + thickness) reaches the floor.
            lift = max(0.0, floor_z - (sole + thickness)) if sole is not None else 0.0
            targets[side][f] = Vector((ankle.x, ankle.y, ankle.z + lift))

    if probe and not pose_has_motion:
        scene.frame_set(f0)
        return 0, ("Rig is frozen at rest — the active action isn't driving the "
                   "bones (check NLA solo / action slot). Grounding aborted so it "
                   "won't bake a static pose over the animation.")

    # Pass 2: IK constraints + animated target empties.
    empties = []
    for side, u, l, fb in legs:
        emp = bpy.data.objects.new(f"MMR_IK_TGT_{side}", None)
        emp.empty_display_size = 0.05
        scene.collection.objects.link(emp)
        con = arm.pose.bones[l].constraints.new('IK')
        con.name = "MMR_FOOT_IK"
        con.target = emp
        con.chain_count = 2          # Leg + UpLeg
        con.use_tail = True          # Leg.tail (ankle) reaches the target
        empties.append((side, emp))

    for side, emp in empties:
        for f, pos in targets[side].items():
            emp.location = pos
            emp.keyframe_insert("location", frame=f)

    # Bake the visual (IK-solved) pose into the action, then drop constraints.
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    try:
        bpy.ops.nla.bake(
            frame_start=f0, frame_end=f1, step=1,
            only_selected=False, visual_keying=True,
            clear_constraints=True, clear_parents=False,
            use_current_action=True, bake_types={'POSE'},
        )
    except RuntimeError as exc:
        # Clean up on failure: drop constraints and target empties.
        for side, u, l, fb in legs:
            for c in list(arm.pose.bones[l].constraints):
                if c.name == "MMR_FOOT_IK":
                    arm.pose.bones[l].constraints.remove(c)
        for _, emp in empties:
            bpy.data.objects.remove(emp, do_unlink=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        return 0, f"Bake failed: {exc}"
    bpy.ops.object.mode_set(mode='OBJECT')

    # Remove any leftover IK constraints (should be cleared by the bake) + empties.
    for side, u, l, fb in legs:
        for c in list(arm.pose.bones[l].constraints):
            if c.name == "MMR_FOOT_IK":
                arm.pose.bones[l].constraints.remove(c)
    for _, emp in empties:
        bpy.data.objects.remove(emp, do_unlink=True)

    scene.frame_set(f0)
    return (f1 - f0 + 1), None


def ground_feet(context, arm, props):
    """Dispatch to the chosen grounding method. Returns (frames, error)."""
    if props.ground_method == 'FOOT_IK':
        return bake_foot_ik(context, arm, props.floor_z)
    return bake_foot_floor_lock(context, arm, props.floor_z)


# --- Rotation channels: Quaternion <-> Euler --------------------------------
# Mixamo FBX imports key bone rotation as Quaternion (W/X/Y/Z), which is what
# the Graph Editor then shows. `rotation_mode` lives on the POSE BONE, not on
# the action, so flipping it in the N-panel does not touch the existing keys —
# the quaternion F-curves are simply orphaned and the pose stops animating.
# These helpers resample the keys so the motion survives the switch.

_EULER_ORDERS = ('XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX')


def _pb_rotation_quat(pb):
    """A pose bone's current static rotation as a quaternion, whatever mode."""
    mode = pb.rotation_mode
    if mode == 'QUATERNION':
        return pb.rotation_quaternion.copy()
    if mode == 'AXIS_ANGLE':
        aa = pb.rotation_axis_angle
        return Quaternion(Vector((aa[1], aa[2], aa[3])), aa[0])
    return Euler(pb.rotation_euler, mode).to_quaternion()


def _set_pb_rotation_mode(pb, mode):
    """Switch rotation_mode while keeping the pose put.

    Bones with no rotation keys still hold a static rotation in the old
    representation; flipping the mode alone would silently drop it.
    """
    if pb.rotation_mode == mode:
        return
    q = _pb_rotation_quat(pb)
    pb.rotation_mode = mode
    if mode == 'QUATERNION':
        pb.rotation_quaternion = q
    else:
        pb.rotation_euler = q.to_euler(mode)


def _bone_rot_curves(action, prop_name):
    """{bone_name: {array_index: fcurve}} for pose.bones[...].<prop_name>."""
    out = {}
    pat = re.compile(r'^pose\.bones\["(.+?)"\]\.' + prop_name + r'$')
    for fc in action.fcurves:
        m = pat.match(fc.data_path)
        if m:
            out.setdefault(m.group(1), {})[fc.array_index] = fc
    return out


def _curve_frames(curves):
    """Sorted union of the keyframe times across a bone's rotation curves."""
    frames = set()
    for fc in curves.values():
        for kp in fc.keyframe_points:
            frames.add(round(kp.co[0], 5))
    return sorted(frames)


def convert_action_rotation(arm, action, to_mode='XYZ'):
    """Rewrite an action's bone rotation keys in `to_mode` ('QUATERNION' or an
    Euler order), keeping the motion. Returns (bones_converted, skipped_names).

    Keys are read straight off the F-curves (no scene stepping) and written
    back through keyframe_insert, so slotted actions (Blender 4.4+) work.
    """
    to_quat = to_mode == 'QUATERNION'
    src = _bone_rot_curves(action, "rotation_euler" if to_quat else "rotation_quaternion")
    if not src:
        return 0, []

    # Read every source key before touching anything.
    default = (0.0, 0.0, 0.0) if to_quat else (1.0, 0.0, 0.0, 0.0)
    samples, meta = {}, {}
    for name, curves in src.items():
        samples[name] = [
            (f, [curves[i].evaluate(f) if i in curves else default[i]
                 for i in range(len(default))])
            for f in _curve_frames(curves)
        ]
        first = curves[min(curves)]
        grp = first.group.name if first.group else name
        interp = first.keyframe_points[0].interpolation if first.keyframe_points else 'BEZIER'
        meta[name] = (grp, interp)

    # keyframe_insert() reads the pose bone's current value, so the action has
    # to be the active one on the rig while we write. Put the old one back after.
    if arm.animation_data is None:
        arm.animation_data_create()
    prev_action = arm.animation_data.action
    _assign_action(arm, action)

    converted, skipped = 0, []
    try:
        for name, vals in samples.items():
            pb = arm.pose.bones.get(name)
            if pb is None:
                skipped.append(name)      # action baked on a different skeleton
                continue
            grp, interp = meta[name]
            src_order = pb.rotation_mode if pb.rotation_mode in _EULER_ORDERS else 'XYZ'

            prop = "rotation_quaternion" if to_quat else "rotation_euler"
            for fc in list(src[name].values()):
                action.fcurves.remove(fc)
            # Stale keys on the destination channels — left behind by an earlier
            # half-switch through the N-panel dropdown — would survive at frames
            # we don't rewrite and fight the resampled motion.
            for fc in list(_bone_rot_curves(action, prop).get(name, {}).values()):
                action.fcurves.remove(fc)
            _set_pb_rotation_mode(pb, to_mode)
            prev = None
            for f, comps in vals:
                if to_quat:
                    val = Euler(comps, src_order).to_quaternion()
                    # Keep the sign continuous: q and -q are the same rotation,
                    # but a flip mid-curve reads as a 360° spin when interpolated.
                    if prev is not None and val.dot(prev) < 0.0:
                        val.negate()
                    pb.rotation_quaternion = val
                else:
                    q = Quaternion(comps)
                    val = q.to_euler(to_mode, prev) if prev else q.to_euler(to_mode)
                    pb.rotation_euler = val
                prev = val
                pb.keyframe_insert(prop, frame=f, group=grp)

            for i in range(4 if to_quat else 3):
                fc = action.fcurves.find(pb.path_from_id(prop), index=i)
                if fc is None:
                    continue
                for kp in fc.keyframe_points:
                    kp.interpolation = interp
                fc.update()
            converted += 1
    finally:
        if prev_action is not None and prev_action.name in bpy.data.actions:
            _assign_action(arm, prev_action)
        else:
            # The rig had no action — leaving the last converted one assigned
            # would silently change what it plays.
            arm.animation_data.action = None

    return converted, skipped


def _rig_rotation_mode(arm):
    """The rotation mode this rig's bones actually use (majority wins)."""
    counts = {}
    for pb in arm.pose.bones:
        counts[pb.rotation_mode] = counts.get(pb.rotation_mode, 0) + 1
    return max(counts, key=counts.get) if counts else 'QUATERNION'


def _match_rig_rotation_mode(arm, action):
    """Bring a freshly imported action into the rig's rotation representation.

    Mixamo FBX always arrives keyed as quaternion. On a rig whose bones were
    switched to Euler those curves drive nothing, so the animation applies but
    the character just freezes in one pose — no error anywhere. Returns the
    number of bones rewritten (0 when the action already matches).
    """
    mode = _rig_rotation_mode(arm)
    if mode != 'QUATERNION' and mode not in _EULER_ORDERS:
        return 0, mode        # AXIS_ANGLE — not something we resample
    bones, _skipped = convert_action_rotation(arm, action, mode)
    return bones, mode


def _rig_action_closure(arm, props):
    """Every action that must convert together with `arm`, plus every rig those
    actions reach.

    rotation_mode lives on the pose bone, not the action, so a single action
    left in the old representation stops rotating the moment the bones switch.
    Actions are shared datablocks, so this walks the closure:
    this rig's actions -> rigs that also use them -> those rigs' actions.
    """
    def used_by(ob):
        ad = ob.animation_data
        if ad is None:
            return set()
        used = {ad.action} if ad.action else set()
        used |= {s.action for t in ad.nla_tracks for s in t.strips if s.action}
        return used

    actions = {a for a in (bpy.data.actions.get(i.name) for i in props.items)
               if a is not None}
    actions |= used_by(arm)

    rigs = {arm}
    grew = True
    while grew:
        grew = False
        for ob in bpy.data.objects:
            if ob.type != 'ARMATURE' or ob in rigs:
                continue
            used = used_by(ob)
            if used & actions:
                rigs.add(ob)
                actions |= used
                grew = True

    # Unused actions kept by a fake user (earlier imports, Action Editor
    # leftovers) are not reachable from any rig, but they key this skeleton and
    # the user can pick them later — convert them too rather than leave traps.
    bones = set(arm.pose.bones.keys())
    for action in bpy.data.actions:
        if action in actions:
            continue
        keyed = _action_bone_names(action)
        if keyed and len(keyed & bones) >= 0.5 * len(keyed):
            actions.add(action)

    return actions, rigs


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class MIXLIB_item(PropertyGroup):
    name: StringProperty(name="Name")
    filepath: StringProperty(name="File Path", subtype='FILE_PATH')


def _library_path_updated(self, context):
    _rescan(self)


def _active_index_updated(self, context):
    """Click-to-preview: selecting an already-imported animation (✓)
    assigns its action to the active armature immediately."""
    if not self.preview_on_click:
        return
    if not (0 <= self.active_index < len(self.items)):
        return
    action = bpy.data.actions.get(self.items[self.active_index].name)
    if action is None:
        return  # not imported yet — press Apply once first
    target = _active_armature(context)
    if target is None:
        return
    _assign_action(target, action)
    if self.set_frame_range:
        f_start, f_end = action.frame_range
        scene = context.scene
        scene.frame_start = int(f_start)
        scene.frame_end = max(int(f_end), int(f_start) + 1)
        if not (scene.frame_start <= scene.frame_current <= scene.frame_end):
            scene.frame_current = scene.frame_start


class MIXLIB_props(PropertyGroup):
    library_path: StringProperty(
        name="Library Folder",
        description="Folder containing Mixamo FBX files (scanned recursively)",
        subtype='DIR_PATH',
        update=_library_path_updated,
    )
    items: CollectionProperty(type=MIXLIB_item)
    active_index: IntProperty(default=0, update=_active_index_updated)

    preview_on_click: BoolProperty(
        name="Click to Preview",
        description=(
            "Clicking an imported animation (✓) in the list instantly assigns "
            "its action to the active armature — start playback (Space) and "
            "click through the list to preview"
        ),
        default=True,
    )

    in_place: BoolProperty(
        name="In Place",
        description="Strip root motion: remove hips location channels that travel away from the start",
        default=False,
    )
    push_nla: BoolProperty(
        name="Push to NLA",
        description="Also push the applied action down as a new NLA strip",
        default=False,
    )
    foot_floor_lock: BoolProperty(
        name="Ground Feet on Apply",
        description=(
            "After applying an animation, ground the feet so they don't sink "
            "through the floor (for characters whose proportions differ from "
            "the animation)"
        ),
        default=False,
    )
    ground_method: EnumProperty(
        name="Grounding",
        description="How to keep the feet on the floor",
        items=[
            ('FOOT_IK', "Foot IK",
             "Retarget the legs with 2-bone IK so feet stay planted while the "
             "body keeps its motion (Mixamo-style; bakes leg pose)"),
            ('FLOOR_LOCK', "Floor Lock",
             "Raise/lower the whole body so the lowest foot touches the floor "
             "(simple, does not edit the pose; may float on some frames)"),
        ],
        default='FOOT_IK',
    )
    floor_z: FloatProperty(
        name="Floor Z",
        description="World Z height of the floor the feet should rest on",
        default=0.0,
    )
    set_frame_range: BoolProperty(
        name="Set Frame Range",
        description="Set the scene frame range to match the animation",
        default=True,
    )

    rot_mode: EnumProperty(
        name="Rotation",
        description="Rotation channel type the bone keys should be rewritten in",
        items=[
            ('XYZ', "XYZ Euler",
             "Readable X/Y/Z curves in the Graph Editor, easy to hand-edit; "
             "can gimbal-lock on extreme poses"),
            ('QUATERNION', "Quaternion",
             "Back to Mixamo's native W/X/Y/Z — no gimbal lock, what the FBX "
             "importer/exporter uses"),
        ],
        default='XYZ',
    )
    rot_convert_all: BoolProperty(
        name="All Matching Actions",
        description=(
            "Convert every action that belongs to this skeleton — the list (✓), "
            "the NLA strips, and unused actions kept by a fake user — instead of "
            "only the active one. Recommended: rotation_mode is a property of "
            "the bone, not of the action, so any action left behind stops "
            "rotating once the bones switch"
        ),
        default=True,
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class MIXLIB_OT_scan(Operator):
    bl_idname = "mixlib.scan"
    bl_label = "Scan Library"
    bl_description = "Scan the library folder for FBX files"

    def execute(self, context):
        count = _rescan(context.scene.mixlib)
        if count < 0:
            self.report({'WARNING'}, "Library folder not found")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Found {count} animation(s)")
        return {'FINISHED'}


class MIXLIB_OT_apply(Operator):
    bl_idname = "mixlib.apply"
    bl_label = "Apply to Selected Armature"
    bl_description = (
        "Import the selected FBX, copy its animation onto the active armature, "
        "then delete the imported objects"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.mixlib
        return (
            _active_armature(context) is not None
            and 0 <= props.active_index < len(props.items)
        )

    def execute(self, context):
        props = context.scene.mixlib
        item = props.items[props.active_index]
        target = _active_armature(context)

        # Reuse an already-imported action (✓ in the list) instead of
        # importing the FBX again and creating a ".001" duplicate — unless the
        # FBX on disk changed since (re-downloaded bake): then re-import and
        # swap the stale action out everywhere it is used.
        action = bpy.data.actions.get(item.name)
        if action is not None and action.get("mixlib_src_mtime") is None:
            # Pre-stamp (or hand-edited) action: adopt it as the current
            # version instead of wiping possible manual key edits.
            _stamp_source(action, item.filepath)
        stale = None
        if action is not None and _is_stale(action, item.filepath):
            stale, action = action, None
        if action is None:
            if not os.path.isfile(item.filepath):
                self.report({'ERROR'}, f"File not found: {item.filepath}")
                return {'CANCELLED'}

            src_arm, imported = _import_fbx(item.filepath)
            if src_arm is None or src_arm.animation_data is None or src_arm.animation_data.action is None:
                _delete_objects(imported)
                self.report({'ERROR'}, "No animation found in this FBX (T-pose file?)")
                return {'CANCELLED'}

            src_action = src_arm.animation_data.action
            mism = _rest_mismatch(src_arm, target)
            if mism is not None and mism > _RETARGET_THRESHOLD:
                # The FBX skeleton's rest pose differs from this rig — a raw
                # F-curve copy would bend the character. Retarget instead.
                action = _retarget_bake(context, src_arm, target, src_action)
                self.report(
                    {'INFO'},
                    f"Rest poses differ (~{mism * 100:.0f}% of skeleton size) — "
                    "retargeted via constraint bake",
                )
            else:
                action = src_action.copy()
            action.use_fake_user = True
            _stamp_source(action, item.filepath)

            if props.in_place:
                _strip_root_motion(action)

            _delete_objects(imported)
            if src_action.users == 0:
                bpy.data.actions.remove(src_action)

            if stale is not None:
                _replace_action(stale, action)
                self.report({'INFO'}, "FBX changed on disk — re-imported the animation")
            else:
                action.name = item.name

        # Warn when the skeletons clearly don't match.
        anim_bones = _action_bone_names(action)
        if anim_bones:
            matched = sum(1 for n in anim_bones if n in target.pose.bones)
            ratio = matched / len(anim_bones)
            if ratio < 0.5:
                self.report(
                    {'WARNING'},
                    f"Only {matched}/{len(anim_bones)} bones match the target rig — "
                    "animation may not play correctly (different skeleton?)",
                )

        # The rig may have been switched to Euler — an imported quaternion
        # action would then apply cleanly and animate nothing at all.
        rewritten, mode = _match_rig_rotation_mode(target, action)
        if rewritten:
            self.report({'INFO'},
                        f"Rewrote {rewritten} bone(s) as {mode} to match this rig")

        _assign_action(target, action)

        if props.set_frame_range:
            f_start, f_end = action.frame_range
            context.scene.frame_start = int(f_start)
            context.scene.frame_end = max(int(f_end), int(f_start) + 1)
            context.scene.frame_current = int(f_start)

        if props.foot_floor_lock:
            baked, err = ground_feet(context, target, props)
            if err:
                self.report({'WARNING'}, f"Grounding skipped: {err}")
            else:
                self.report({'INFO'}, f"Grounded feet over {baked} frame(s)")

        if props.push_nla:
            ad = target.animation_data
            already = any(
                strip.action == action
                for track in ad.nla_tracks
                for strip in track.strips
            )
            if not already:
                track = ad.nla_tracks.new()
                track.name = action.name
                strip = track.strips.new(action.name, int(action.frame_range[0]), action)
                if hasattr(strip, "action_slot") and getattr(action, "slots", None):
                    if len(action.slots):
                        try:
                            strip.action_slot = action.slots[0]
                        except Exception:
                            pass

        self.report({'INFO'}, f"Applied '{action.name}' to {target.name}")
        return {'FINISHED'}


class MIXLIB_OT_ground_feet(Operator):
    bl_idname = "mixlib.ground_feet"
    bl_label = "Ground Feet"
    bl_description = (
        "Keep the feet on the floor for the current animation, using the chosen "
        "Grounding method (Foot IK retargets the legs like Mixamo; Floor Lock "
        "shifts the whole body). Fixes a character sinking when its proportions "
        "differ from the animation. Re-run after changing the animation"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        arm = _active_armature(context)
        return (arm is not None and arm.animation_data is not None
                and arm.animation_data.action is not None)

    def execute(self, context):
        props = context.scene.mixlib
        arm = _active_armature(context)
        baked, err = ground_feet(context, arm, props)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        method = "Foot IK" if props.ground_method == 'FOOT_IK' else "Floor Lock"
        self.report({'INFO'}, f"Grounded feet ({method}) over {baked} frame(s) on {arm.name}")
        return {'FINISHED'}


class MIXLIB_OT_clear_ground(Operator):
    bl_idname = "mixlib.clear_ground"
    bl_label = "Clear Floor Lock"
    bl_description = "Remove the floor-lock vertical offset from the active armature"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        arm = _active_armature(context)
        return arm is not None and arm.animation_data is not None

    def execute(self, context):
        arm = _active_armature(context)
        _clear_object_z_keys(arm)
        arm.location.z = 0.0
        self.report({'INFO'}, "Floor lock cleared")
        return {'FINISHED'}


class MIXLIB_OT_import_character(Operator):
    bl_idname = "mixlib.import_character"
    bl_label = "Import as New Character"
    bl_description = "Import the selected FBX as a new character (mesh + armature + animation)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.mixlib
        return 0 <= props.active_index < len(props.items)

    def execute(self, context):
        props = context.scene.mixlib
        item = props.items[props.active_index]
        if not os.path.isfile(item.filepath):
            self.report({'ERROR'}, f"File not found: {item.filepath}")
            return {'CANCELLED'}

        armature, imported = _import_fbx(item.filepath)
        if armature and armature.animation_data and armature.animation_data.action:
            action = armature.animation_data.action
            action.name = item.name
            if props.in_place:
                _strip_root_motion(action)
            if props.set_frame_range:
                f_start, f_end = action.frame_range
                context.scene.frame_start = int(f_start)
                context.scene.frame_end = max(int(f_end), int(f_start) + 1)

        self.report({'INFO'}, f"Imported {len(imported)} object(s) from '{item.name}'")
        return {'FINISHED'}


class MIXLIB_OT_import_all_actions(Operator):
    bl_idname = "mixlib.import_all_actions"
    bl_label = "Import All as Actions"
    bl_description = (
        "Import every FBX in the list and keep only the actions "
        "(with fake user), for use in the Action Editor / NLA"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.mixlib.items) > 0

    def execute(self, context):
        props = context.scene.mixlib
        count = 0
        retargeted = 0
        target = _active_armature(context)
        prev_action = None
        if target and target.animation_data:
            prev_action = target.animation_data.action
        wm = context.window_manager
        wm.progress_begin(0, len(props.items))
        try:
            for i, item in enumerate(props.items):
                wm.progress_update(i)
                if not os.path.isfile(item.filepath):
                    continue
                stale = bpy.data.actions.get(item.name)
                if stale is not None and stale.get("mixlib_src_mtime") is None:
                    _stamp_source(stale, item.filepath)  # adopt, keep edits
                if stale is not None and not _is_stale(stale, item.filepath):
                    continue  # already imported and up to date
                src_arm, imported = _import_fbx(item.filepath)
                if src_arm and src_arm.animation_data and src_arm.animation_data.action:
                    src_action = src_arm.animation_data.action
                    mism = _rest_mismatch(src_arm, target) if target else None
                    if mism is not None and mism > _RETARGET_THRESHOLD:
                        action = _retarget_bake(context, src_arm, target, src_action)
                        retargeted += 1
                    else:
                        action = src_action.copy()
                    action.use_fake_user = True
                    _stamp_source(action, item.filepath)
                    if props.in_place:
                        _strip_root_motion(action)
                    _delete_objects(imported)
                    if src_action.users == 0:
                        bpy.data.actions.remove(src_action)
                    if target is not None:
                        _match_rig_rotation_mode(target, action)
                    if stale is not None:
                        _replace_action(stale, action)
                    else:
                        action.name = item.name
                    count += 1
                else:
                    _delete_objects(imported)
        finally:
            wm.progress_end()
        # Baking assigns each action while importing — put the original back.
        if target and prev_action and prev_action.name in bpy.data.actions:
            _assign_action(target, prev_action)
        msg = f"Imported {count} action(s)"
        if retargeted:
            msg += f" ({retargeted} retargeted — rest pose differs from this rig)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MIXLIB_OT_remove(Operator):
    bl_idname = "mixlib.remove"
    bl_label = "Remove Animation"
    bl_description = (
        "Remove the selected animation from this blend file: delete its action "
        "and any NLA strips using it. The FBX file on disk is not touched — "
        "press Apply to import it again later"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.mixlib
        return (
            0 <= props.active_index < len(props.items)
            and props.items[props.active_index].name in bpy.data.actions
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.mixlib
        name = props.items[props.active_index].name
        action = bpy.data.actions.get(name)
        if action is None:
            return {'CANCELLED'}

        strips_removed = 0
        for ob in bpy.data.objects:
            ad = ob.animation_data
            if ad is None:
                continue
            if ad.action == action:
                ad.action = None
            for track in list(ad.nla_tracks):
                emptied = False
                for strip in list(track.strips):
                    if strip.action == action:
                        track.strips.remove(strip)
                        strips_removed += 1
                        emptied = True
                if emptied and not track.strips:
                    ad.nla_tracks.remove(track)

        bpy.data.actions.remove(action)
        self.report(
            {'INFO'},
            f"Removed '{name}' ({strips_removed} NLA strip(s) cleaned up)",
        )
        return {'FINISHED'}


class MIXLIB_OT_reimport(Operator):
    bl_idname = "mixlib.reimport"
    bl_label = "Reimport from FBX"
    bl_description = (
        "Force re-import the selected animation from its FBX file and replace "
        "the in-blend action everywhere it is used (assignments, NLA strips). "
        "WARNING: discards any manual keyframe edits made to that action"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.mixlib
        return 0 <= props.active_index < len(props.items)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.mixlib
        item = props.items[props.active_index]
        if not os.path.isfile(item.filepath):
            self.report({'ERROR'}, f"File not found: {item.filepath}")
            return {'CANCELLED'}

        src_arm, imported = _import_fbx(item.filepath)
        if src_arm is None or src_arm.animation_data is None or src_arm.animation_data.action is None:
            _delete_objects(imported)
            self.report({'ERROR'}, "No animation found in this FBX (T-pose file?)")
            return {'CANCELLED'}

        src_action = src_arm.animation_data.action
        target = _active_armature(context)
        mism = _rest_mismatch(src_arm, target) if target else None
        if mism is not None and mism > _RETARGET_THRESHOLD:
            action = _retarget_bake(context, src_arm, target, src_action)
            self.report(
                {'INFO'},
                f"Rest poses differ (~{mism * 100:.0f}% of skeleton size) — "
                "retargeted via constraint bake",
            )
        else:
            action = src_action.copy()
        action.use_fake_user = True
        _stamp_source(action, item.filepath)
        if props.in_place:
            _strip_root_motion(action)

        _delete_objects(imported)
        if src_action.users == 0:
            bpy.data.actions.remove(src_action)

        if target is not None:
            _match_rig_rotation_mode(target, action)

        old = bpy.data.actions.get(item.name)
        if old is not None:
            _replace_action(old, action)
        else:
            action.name = item.name

        self.report({'INFO'}, f"Re-imported '{item.name}' from FBX")
        return {'FINISHED'}


class MIXLIB_OT_convert_rotation(Operator):
    bl_idname = "mixlib.convert_rotation"
    bl_label = "Convert Rotation Keys"
    bl_description = (
        "Rewrite the bone rotation keyframes of the active armature in the "
        "chosen channel type, keeping the motion. Use this instead of the "
        "N-panel Rotation dropdown, which only switches the bone's mode and "
        "leaves the old keys orphaned (Graph Editor still shows Quaternion, "
        "pose stops animating)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        arm = _active_armature(context)
        if arm is None:
            return False
        if context.scene.mixlib.rot_convert_all:
            return True
        return arm.animation_data is not None and arm.animation_data.action is not None

    def execute(self, context):
        props = context.scene.mixlib
        arm = _active_armature(context)

        if props.rot_convert_all:
            actions, rigs = _rig_action_closure(arm, props)
        else:
            current = arm.animation_data.action if arm.animation_data else None
            actions, rigs = ({current} if current else set()), {arm}

        if not actions:
            self.report({'ERROR'}, "No action to convert — apply an animation first")
            return {'CANCELLED'}

        total_bones, done, skipped = 0, set(), set()
        for action in actions:
            bones, miss = convert_action_rotation(arm, action, props.rot_mode)
            if bones:
                done.add(action)
                total_bones += bones
            skipped.update(miss)

        for ob in rigs:
            # Bones the actions never keyed keep their static rotation, but must
            # still change mode or they read the wrong channels from here on.
            for pb in ob.pose.bones:
                _set_pb_rotation_mode(pb, props.rot_mode)

        if not done:
            self.report({'INFO'}, f"Already in {props.rot_mode} — nothing to convert")
            return {'FINISHED'}

        label = "Quaternion" if props.rot_mode == 'QUATERNION' else f"{props.rot_mode} Euler"
        msg = f"Converted {total_bones} bone(s) in {len(done)} action(s) to {label}"
        if len(rigs) > 1:
            msg += f", across {len(rigs)} rigs"
        if skipped:
            self.report({'WARNING'}, msg + f" — {len(skipped)} bone(s) not on this rig were skipped")
        else:
            self.report({'INFO'}, msg)
        return {'FINISHED'}


class MIXLIB_OT_stash_all(Operator):
    bl_idname = "mixlib.stash_all"
    bl_label = "Stash All to NLA (Unity)"
    bl_description = (
        "Create one NLA strip per imported action (✓) on the active armature. "
        "Each strip becomes a separate animation clip when exported to FBX / Unity. "
        "Tracks are left unmuted — muted strips are skipped by the FBX exporter"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _active_armature(context) is not None

    def execute(self, context):
        props = context.scene.mixlib
        target = _active_armature(context)
        if target.animation_data is None:
            target.animation_data_create()
        ad = target.animation_data

        stashed = {
            strip.action
            for track in ad.nla_tracks
            for strip in track.strips
            if strip.action
        }
        count = 0
        for item in props.items:
            action = bpy.data.actions.get(item.name)
            if action is None or action in stashed:
                continue
            track = ad.nla_tracks.new()
            track.name = action.name
            strip = track.strips.new(action.name, int(action.frame_range[0]), action)
            if hasattr(strip, "action_slot") and getattr(action, "slots", None):
                if len(action.slots):
                    try:
                        strip.action_slot = action.slots[0]
                    except Exception:
                        pass
            count += 1

        self.report({'INFO'}, f"Stashed {count} action(s) to NLA on {target.name}")
        return {'FINISHED'}


class MIXLIB_OT_export_unity(Operator):
    bl_idname = "mixlib.export_unity"
    bl_label = "Export FBX (Unity)"
    bl_description = (
        "Open the FBX exporter preset for Unity: selected objects only, "
        "NLA strips as separate clips, no leaf bones, applied scale"
    )

    @classmethod
    def poll(cls, context):
        return _active_armature(context) is not None

    def execute(self, context):
        target = _active_armature(context)
        # Select the armature and its child meshes for a clean export.
        for ob in context.selected_objects:
            ob.select_set(False)
        target.select_set(True)
        for child in target.children_recursive:
            child.select_set(True)
        context.view_layer.objects.active = target

        bpy.ops.export_scene.fbx(
            'INVOKE_DEFAULT',
            use_selection=True,
            object_types={'ARMATURE', 'MESH'},
            add_leaf_bones=False,
            apply_scale_options='FBX_SCALE_ALL',
            bake_anim=True,
            bake_anim_use_nla_strips=True,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
        )
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class MIXLIB_UL_anims(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text=item.name, icon='ARMATURE_DATA')
        action = bpy.data.actions.get(item.name)
        if action is not None:
            # FILE_REFRESH: the FBX on disk changed since this action was
            # imported — Apply will re-import it.
            stale = _is_stale(action, item.filepath)
            row.label(text="", icon='FILE_REFRESH' if stale else 'CHECKMARK')


class MIXLIB_PT_panel(Panel):
    bl_label = "Mixamo Animation Library"
    bl_idname = "MIXLIB_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Mixamo Lib"

    def draw(self, context):
        layout = self.layout
        props = context.scene.mixlib

        col = layout.column(align=True)
        col.prop(props, "library_path", text="")
        col.operator("mixlib.scan", icon='FILE_REFRESH')

        if props.items:
            row = layout.row()
            row.template_list(
                "MIXLIB_UL_anims", "",
                props, "items",
                props, "active_index",
                rows=8,
            )
            side = row.column(align=True)
            side.operator("mixlib.remove", text="", icon='TRASH')
            side.operator("mixlib.reimport", text="", icon='FILE_REFRESH')

            box = layout.box()
            box.label(text="Options", icon='PREFERENCES')
            box.prop(props, "preview_on_click")
            box.prop(props, "in_place")
            box.prop(props, "set_frame_range")
            box.prop(props, "push_nla")
            # --- Foot grounding (staged/hidden — flip SHOW_GROUNDING) --------
            if SHOW_GROUNDING:
                box.prop(props, "foot_floor_lock")
                row = box.row(align=True)
                row.prop(props, "ground_method", expand=True)
                box.prop(props, "floor_z")

            target = _active_armature(context)
            col = layout.column(align=True)
            if target:
                col.label(text=f"Target: {target.name}", icon='OUTLINER_OB_ARMATURE')
            else:
                col.label(text="Select an armature", icon='ERROR')
            col.operator("mixlib.apply", icon='PLAY')
            if SHOW_GROUNDING:
                row = col.row(align=True)
                row.operator("mixlib.ground_feet", icon='CON_FLOOR')
                row.operator("mixlib.clear_ground", text="", icon='X')
            col.operator("mixlib.import_character", icon='OUTLINER_OB_ARMATURE')
            col.operator("mixlib.import_all_actions", icon='ACTION')

            box = layout.box()
            box.label(text="Rotation Channels", icon='ORIENTATION_GIMBAL')
            row = box.row(align=True)
            row.prop(props, "rot_mode", expand=True)
            box.prop(props, "rot_convert_all")
            box.operator("mixlib.convert_rotation", icon='FILE_REFRESH')

            box = layout.box()
            box.label(text="Game Engine Export", icon='EXPORT')
            col = box.column(align=True)
            col.operator("mixlib.stash_all", icon='NLA')
            col.operator("mixlib.export_unity", icon='EXPORT')
        elif props.library_path:
            layout.label(text="No FBX files found", icon='INFO')
        else:
            layout.label(text="Pick your Mixamo FBX folder", icon='INFO')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    MIXLIB_item,
    MIXLIB_props,
    MIXLIB_OT_scan,
    MIXLIB_OT_apply,
    MIXLIB_OT_ground_feet,
    MIXLIB_OT_clear_ground,
    MIXLIB_OT_import_character,
    MIXLIB_OT_import_all_actions,
    MIXLIB_OT_remove,
    MIXLIB_OT_reimport,
    MIXLIB_OT_convert_rotation,
    MIXLIB_OT_stash_all,
    MIXLIB_OT_export_unity,
    MIXLIB_UL_anims,
    MIXLIB_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mixlib = PointerProperty(type=MIXLIB_props)


def unregister():
    del bpy.types.Scene.mixlib
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
