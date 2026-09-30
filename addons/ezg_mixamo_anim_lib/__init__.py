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

from . import ezg_i18n
from .ezg_i18n import tr


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


# --- Action channel access across Blender versions -------------------------
# Blender 4.4 moved an action's F-Curves into per-slot channelbags and left
# `action.fcurves` as a legacy view. Blender 5.x REMOVED that attribute, so any
# `action.fcurves` raises AttributeError: 'Action' object has no attribute
# 'fcurves' — the add-on installs fine and dies on the first click.
#
# Everything below goes through the channelbags and only falls back to the old
# attribute when it still exists (4.x with an action that has no slot yet).

def _channelbags(action):
    """Every F-Curve container of `action` (one per slot on Blender 4.4+)."""
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
                    out.append(bag)
    return out


def _fcurves(action):
    """Every F-Curve of `action`, on any Blender version."""
    out = []
    for bag in _channelbags(action):
        out.extend(bag.fcurves)
    if out:
        return out
    return list(getattr(action, "fcurves", ()) or ())


def _remove_fcurve(action, fcurve):
    """Remove `fcurve` from whichever container owns it. True when removed."""
    for bag in _channelbags(action):
        try:
            bag.fcurves.remove(fcurve)
            return True
        except (RuntimeError, ReferenceError, TypeError):
            continue
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        try:
            legacy.remove(fcurve)
            return True
        except (RuntimeError, ReferenceError, TypeError):
            pass
    return False


def _find_fcurve(action, data_path, index=0):
    for bag in _channelbags(action):
        fc = bag.fcurves.find(data_path, index=index)
        if fc is not None:
            return fc
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return legacy.find(data_path, index=index)
    return None


def _stamp_source(action, filepath, target=None):
    """Record which FBX (and its mtime) this action was imported from, and the
    rig scale it was made for."""
    action["mixlib_src_path"] = filepath
    try:
        action["mixlib_src_mtime"] = os.path.getmtime(filepath)
    except OSError:
        pass
    if target is not None:
        action["mixlib_rig_scale"] = _rig_scale(target)


def _rig_scale(arm):
    """Average object scale of the rig - the unit its pose-bone location keys
    are measured in."""
    s = arm.matrix_world.to_scale()
    return (abs(s.x) + abs(s.y) + abs(s.z)) / 3.0


def _unit_mismatch(action, arm):
    """True when `action` was built for a rig of a different scale than `arm`.

    Pose-bone location is measured in armature DATA units, so an action baked
    against a 0.01 Mixamo rig holds centimetres. Handing that same action to a
    rig normalized to 1,1,1 reads those numbers as metres and throws the
    character ~100x away - measured at 140 m on a real Mixamo idle. The curves
    themselves cannot say which unit they are in, hence the stamp.

    Re-importing costs a retarget bake; serving the wrong units costs a broken
    character, so an unknown stamp errs towards re-importing.
    """
    current = _rig_scale(arm)
    stamped = action.get("mixlib_rig_scale")
    if stamped is None:
        # Imported before this stamp existed. Those were all made in Mixamo
        # space, so only a rig still in Mixamo space may reuse them.
        return abs(current - 0.01) > 1e-4
    return abs(stamped - current) > 1e-4 * max(1.0, abs(stamped), abs(current))


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


def _stale_reason(action, filepath, target):
    """Why the cached `action` cannot be reused for `target`, or None.

    'FILE'  - the FBX on disk changed since it was imported (re-downloaded bake).
    'UNITS' - it was made for a rig at another scale (this rig was normalized,
              or the action was cached for a character at a different scale).

    Kept separate so the report can name the real reason: both used to be
    reported as "FBX changed on disk".
    """
    if _is_stale(action, filepath):
        return 'FILE'
    if target is not None and _unit_mismatch(action, target):
        return 'UNITS'
    return None


def _replace_action(old, new):
    """Point every user of `old` (assignments, NLA strips) at `new`, delete
    `old`, and give `new` its name."""
    name = old.name
    old.user_remap(new)
    bpy.data.actions.remove(old)
    new.name = name


def _action_bone_names(action):
    names = set()
    for fc in _fcurves(action):
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
    for fc in _fcurves(action):
        if not fc.data_path.endswith(".location"):
            continue
        if "hips" not in fc.data_path.lower():
            continue
        samples = [fc.evaluate(f_start + (f_end - f_start) * i / 20.0) for i in range(21)]
        rng = max(samples) - min(samples)
        drift = abs(samples[-1] - samples[0])
        if rng > 1e-6 and drift > 0.6 * rng:
            _remove_fcurve(action, fc)
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
    for fc in _fcurves(ad.action):
        if fc.data_path == "location" and fc.array_index == 2:
            _remove_fcurve(ad.action, fc)


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
        return 0, tr("Armature chưa có animation. Hãy áp dụng một animation trước.",
                     "No animation on the armature. Apply an animation first.")
    names = _ground_bone_names(arm)
    if not names:
        return 0, tr("Rig này không có xương bàn chân/ngón chân nào.",
                     "No foot/toe bones found on this rig.")

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
        return 0, tr("Armature chưa có animation. Hãy áp dụng một animation trước.",
                     "No animation on the armature. Apply an animation first.")
    legs = _leg_defs(arm)
    if not legs:
        return 0, tr("Không tìm thấy xương chân (cần mixamorig:{L,R}UpLeg/Leg/Foot).",
                     "Leg bones not found (need mixamorig:{L,R}UpLeg/Leg/Foot).")

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
        return 0, tr("Rig đứng yên ở rest pose — Action đang active không điều khiển "
                     "được xương (kiểm tra NLA solo / action slot). Đã dừng chạm sàn "
                     "để không bake một pose tĩnh đè lên animation.",
                     "Rig is frozen at rest — the active action isn't driving the "
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
        return 0, tr("Bake thất bại: %s", "Bake failed: %s") % exc
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
    for fc in _fcurves(action):
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
                _remove_fcurve(action, fc)
            # Stale keys on the destination channels — left behind by an earlier
            # half-switch through the N-panel dropdown — would survive at frames
            # we don't rewrite and fight the resampled motion.
            for fc in list(_bone_rot_curves(action, prop).get(name, {}).values()):
                _remove_fcurve(action, fc)
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
                fc = _find_fcurve(action, pb.path_from_id(prop), index=i)
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
    name: StringProperty(name=tr("Tên", "Name"))
    filepath: StringProperty(name=tr("Đường dẫn file", "File Path"), subtype='FILE_PATH')


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
        name=tr("Thư mục thư viện", "Library Folder"),
        description=tr("Thư mục chứa các file FBX Mixamo (quét cả thư mục con)",
                       "Folder containing Mixamo FBX files (scanned recursively)"),
        subtype='DIR_PATH',
        update=_library_path_updated,
    )
    items: CollectionProperty(type=MIXLIB_item)
    active_index: IntProperty(default=0, update=_active_index_updated)

    preview_on_click: BoolProperty(
        name=tr("Bấm để xem thử", "Click to Preview"),
        description=tr(
            "Bấm vào một animation đã import (✓) trong danh sách là gán ngay "
            "Action của nó cho armature đang chọn — bật phát (Space) rồi bấm "
            "lần lượt qua danh sách để xem thử",
            "Clicking an imported animation (✓) in the list instantly assigns "
            "its action to the active armature — start playback (Space) and "
            "click through the list to preview",
        ),
        default=True,
    )

    in_place: BoolProperty(
        name="In Place",  # i18n-skip
        description=tr("Bỏ root motion: xoá các kênh location của hips có dịch chuyển xa khỏi điểm đầu",
                       "Strip root motion: remove hips location channels that travel away from the start"),
        default=False,
    )
    push_nla: BoolProperty(
        name="Push to NLA",  # i18n-skip
        description=tr("Đẩy luôn Action vừa áp dụng xuống thành một NLA strip mới",
                       "Also push the applied action down as a new NLA strip"),
        default=False,
    )
    foot_floor_lock: BoolProperty(
        name=tr("Đặt chân chạm sàn khi áp dụng", "Ground Feet on Apply"),
        description=tr(
            "Sau khi áp dụng animation, đặt chân chạm sàn để không bị lún xuyên "
            "sàn (cho nhân vật có tỉ lệ khác với animation)",
            "After applying an animation, ground the feet so they don't sink "
            "through the floor (for characters whose proportions differ from "
            "the animation)",
        ),
        default=False,
    )
    ground_method: EnumProperty(
        name=tr("Cách chạm sàn", "Grounding"),
        description=tr("Cách giữ bàn chân trên sàn", "How to keep the feet on the floor"),
        items=[
            ('FOOT_IK', "Foot IK",  # i18n-skip
             tr("Retarget chân bằng IK 2 xương để bàn chân bám sàn mà thân vẫn "
                "giữ chuyển động (kiểu Mixamo; bake pose chân)",
                "Retarget the legs with 2-bone IK so feet stay planted while the "
                "body keeps its motion (Mixamo-style; bakes leg pose)")),
            ('FLOOR_LOCK', tr("Khoá sàn", "Floor Lock"),
             tr("Nâng/hạ cả thân để bàn chân thấp nhất chạm sàn (đơn giản, không "
                "sửa pose; vài frame có thể bị lơ lửng)",
                "Raise/lower the whole body so the lowest foot touches the floor "
                "(simple, does not edit the pose; may float on some frames)")),
        ],
        default='FOOT_IK',
    )
    floor_z: FloatProperty(
        name=tr("Z của sàn", "Floor Z"),
        description=tr("Độ cao Z (world) của sàn mà bàn chân đặt lên",
                       "World Z height of the floor the feet should rest on"),
        default=0.0,
    )
    set_frame_range: BoolProperty(
        name=tr("Đặt frame range", "Set Frame Range"),
        description=tr("Đặt frame range của scene khớp với animation",
                       "Set the scene frame range to match the animation"),
        default=True,
    )

    rot_mode: EnumProperty(
        name="Rotation",  # i18n-skip
        description=tr("Kiểu kênh rotation dùng để viết lại keyframe của xương",
                       "Rotation channel type the bone keys should be rewritten in"),
        items=[
            ('XYZ', "XYZ Euler",  # i18n-skip
             tr("Curve X/Y/Z dễ đọc trong Graph Editor, dễ sửa tay; có thể bị "
                "gimbal lock ở pose quá gắt",
                "Readable X/Y/Z curves in the Graph Editor, easy to hand-edit; "
                "can gimbal-lock on extreme poses")),
            ('QUATERNION', "Quaternion",  # i18n-skip
             tr("Trở về W/X/Y/Z gốc của Mixamo — không bị gimbal lock, là kiểu "
                "FBX importer/exporter dùng",
                "Back to Mixamo's native W/X/Y/Z — no gimbal lock, what the FBX "
                "importer/exporter uses")),
        ],
        default='XYZ',
    )
    rot_convert_all: BoolProperty(
        name=tr("Mọi Action khớp", "All Matching Actions"),
        description=tr(
            "Chuyển mọi Action thuộc bộ xương này — trong danh sách (✓), trên "
            "NLA strip, và cả Action không dùng được giữ bằng fake user — thay "
            "vì chỉ Action đang active. Nên bật: rotation_mode là thuộc tính "
            "của xương chứ không phải của Action, nên Action nào bị bỏ sót sẽ "
            "ngừng xoay khi xương đổi kiểu",
            "Convert every action that belongs to this skeleton — the list (✓), "
            "the NLA strips, and unused actions kept by a fake user — instead of "
            "only the active one. Recommended: rotation_mode is a property of "
            "the bone, not of the action, so any action left behind stops "
            "rotating once the bones switch",
        ),
        default=True,
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class MIXLIB_OT_scan(Operator):
    bl_idname = "mixlib.scan"
    bl_label = tr("Quét thư viện", "Scan Library")
    bl_description = tr("Quét thư mục thư viện để tìm file FBX",
                        "Scan the library folder for FBX files")

    def execute(self, context):
        count = _rescan(context.scene.mixlib)
        if count < 0:
            self.report({'WARNING'}, tr("Không tìm thấy thư mục thư viện",
                                        "Library folder not found"))
            return {'CANCELLED'}
        self.report({'INFO'}, tr("Tìm thấy %d animation", "Found %d animation(s)") % count)
        return {'FINISHED'}


class MIXLIB_OT_apply(Operator):
    bl_idname = "mixlib.apply"
    bl_label = tr("Áp dụng lên Armature đang chọn", "Apply to Selected Armature")
    bl_description = tr(
        "Import FBX đang chọn, chép animation của nó sang armature đang chọn, "
        "rồi xoá các object vừa import",
        "Import the selected FBX, copy its animation onto the active armature, "
        "then delete the imported objects",
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
        stale_reason = (_stale_reason(action, item.filepath, target)
                        if action is not None else None)
        if stale_reason is not None:
            # Unit mismatch means the rig was normalized (or rebuilt at another
            # scale) after this action was cached. Reusing it verbatim is how a
            # character ends up 100x away, so re-import and retarget instead.
            stale, action = action, None
        if action is None:
            if not os.path.isfile(item.filepath):
                self.report({'ERROR'}, tr("Không tìm thấy file: %s", "File not found: %s")
                            % item.filepath)
                return {'CANCELLED'}

            src_arm, imported = _import_fbx(item.filepath)
            if src_arm is None or src_arm.animation_data is None or src_arm.animation_data.action is None:
                _delete_objects(imported)
                self.report({'ERROR'}, tr("Không có animation trong FBX này (file T-pose?)",
                                          "No animation found in this FBX (T-pose file?)"))
                return {'CANCELLED'}

            src_action = src_arm.animation_data.action
            mism = _rest_mismatch(src_arm, target)
            # Different object scales mean the two rigs measure bone location in
            # different units, and a raw F-curve copy would be off by that
            # factor. Force the bake, which solves in world space, instead of
            # leaving it to _rest_mismatch - that number happens to be huge when
            # units differ, but it measures rest pose, not units, and must not
            # be relied on to catch this.
            units_differ = abs(_rig_scale(src_arm) - _rig_scale(target)) > 1e-4
            if units_differ or (mism is not None and mism > _RETARGET_THRESHOLD):
                # The FBX skeleton's rest pose differs from this rig — a raw
                # F-curve copy would bend the character. Retarget instead.
                action = _retarget_bake(context, src_arm, target, src_action)
                if units_differ:
                    note = (tr("scale của rig %g so với %g trong FBX",
                               "rig scale %g vs %g in the FBX")
                            % (_rig_scale(target), _rig_scale(src_arm)))
                else:
                    note = (tr("rest pose lệch ~%.0f%% kích thước bộ xương",
                               "rest poses differ ~%.0f%% of skeleton size")
                            % (mism * 100))
                self.report({'INFO'},
                            tr("Đã retarget bằng constraint bake (%s)",
                               "Retargeted via constraint bake (%s)") % note)
            else:
                action = src_action.copy()
            action.use_fake_user = True
            _stamp_source(action, item.filepath, target)

            if props.in_place:
                _strip_root_motion(action)

            _delete_objects(imported)
            if src_action.users == 0:
                bpy.data.actions.remove(src_action)

            if stale is not None:
                # Read the stamp BEFORE _replace_action deletes `stale`. An
                # unstamped action counts as Mixamo space (0.01) in
                # _unit_mismatch, so report that same number.
                cached_scale = stale.get("mixlib_rig_scale", 0.01)
                _replace_action(stale, action)
                if stale_reason == 'FILE':
                    self.report({'INFO'}, tr("FBX trên đĩa đã thay đổi — đã import lại animation",
                                             "FBX changed on disk — re-imported the animation"))
                else:
                    self.report({'INFO'},
                                tr("Action đã lưu được làm cho rig scale %g, rig này scale "
                                   "%g — đã import lại animation cho đúng đơn vị",
                                   "The cached action was made for a rig at scale %g, this "
                                   "rig is at %g — re-imported the animation in the right units")
                                % (cached_scale, _rig_scale(target)))
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
                    tr("Chỉ %d/%d xương khớp với rig đích — animation có thể "
                       "chạy sai (khác bộ xương?)",
                       "Only %d/%d bones match the target rig — "
                       "animation may not play correctly (different skeleton?)")
                    % (matched, len(anim_bones)),
                )

        # The rig may have been switched to Euler — an imported quaternion
        # action would then apply cleanly and animate nothing at all.
        rewritten, mode = _match_rig_rotation_mode(target, action)
        if rewritten:
            self.report({'INFO'},
                        tr("Đã viết lại %d xương sang %s cho khớp rig này",
                           "Rewrote %d bone(s) as %s to match this rig")
                        % (rewritten, mode))

        _assign_action(target, action)

        if props.set_frame_range:
            f_start, f_end = action.frame_range
            context.scene.frame_start = int(f_start)
            context.scene.frame_end = max(int(f_end), int(f_start) + 1)
            context.scene.frame_current = int(f_start)

        if props.foot_floor_lock:
            baked, err = ground_feet(context, target, props)
            if err:
                self.report({'WARNING'}, tr("Bỏ qua chạm sàn: %s", "Grounding skipped: %s") % err)
            else:
                self.report({'INFO'}, tr("Đã đặt chân chạm sàn trên %d frame",
                                         "Grounded feet over %d frame(s)") % baked)

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

        self.report({'INFO'}, tr("Đã áp dụng '%s' lên %s", "Applied '%s' to %s")
                    % (action.name, target.name))
        return {'FINISHED'}


class MIXLIB_OT_ground_feet(Operator):
    bl_idname = "mixlib.ground_feet"
    bl_label = tr("Đặt chân chạm sàn", "Ground Feet")
    bl_description = tr(
        "Giữ bàn chân trên sàn cho animation hiện tại, theo cách chạm sàn đã "
        "chọn (Foot IK retarget chân kiểu Mixamo; Khoá sàn dời cả thân). Sửa "
        "lỗi nhân vật bị lún khi tỉ lệ khác với animation. Chạy lại sau khi "
        "đổi animation",
        "Keep the feet on the floor for the current animation, using the chosen "
        "Grounding method (Foot IK retargets the legs like Mixamo; Floor Lock "
        "shifts the whole body). Fixes a character sinking when its proportions "
        "differ from the animation. Re-run after changing the animation",
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
        method = "Foot IK" if props.ground_method == 'FOOT_IK' else tr("Khoá sàn", "Floor Lock")
        self.report({'INFO'}, tr("Đã đặt chân chạm sàn (%s) trên %d frame cho %s",
                                 "Grounded feet (%s) over %d frame(s) on %s")
                    % (method, baked, arm.name))
        return {'FINISHED'}


class MIXLIB_OT_clear_ground(Operator):
    bl_idname = "mixlib.clear_ground"
    bl_label = tr("Bỏ khoá sàn", "Clear Floor Lock")
    bl_description = tr("Xoá độ lệch dọc do khoá sàn khỏi armature đang chọn",
                        "Remove the floor-lock vertical offset from the active armature")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        arm = _active_armature(context)
        return arm is not None and arm.animation_data is not None

    def execute(self, context):
        arm = _active_armature(context)
        _clear_object_z_keys(arm)
        arm.location.z = 0.0
        self.report({'INFO'}, tr("Đã bỏ khoá sàn", "Floor lock cleared"))
        return {'FINISHED'}


class MIXLIB_OT_import_character(Operator):
    bl_idname = "mixlib.import_character"
    bl_label = tr("Import thành nhân vật mới", "Import as New Character")
    bl_description = tr("Import FBX đang chọn thành một nhân vật mới (mesh + armature + animation)",
                        "Import the selected FBX as a new character (mesh + armature + animation)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.mixlib
        return 0 <= props.active_index < len(props.items)

    def execute(self, context):
        props = context.scene.mixlib
        item = props.items[props.active_index]
        if not os.path.isfile(item.filepath):
            self.report({'ERROR'}, tr("Không tìm thấy file: %s", "File not found: %s")
                        % item.filepath)
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

        self.report({'INFO'}, tr("Đã import %d object từ '%s'", "Imported %d object(s) from '%s'")
                    % (len(imported), item.name))
        return {'FINISHED'}


class MIXLIB_OT_import_all_actions(Operator):
    bl_idname = "mixlib.import_all_actions"
    bl_label = tr("Import tất cả thành Action", "Import All as Actions")
    bl_description = tr(
        "Import mọi FBX trong danh sách và chỉ giữ lại Action (có fake user), "
        "để dùng trong Action Editor / NLA",
        "Import every FBX in the list and keep only the actions "
        "(with fake user), for use in the Action Editor / NLA",
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
                if (stale is not None and not _is_stale(stale, item.filepath)
                        and not (target is not None
                                 and _unit_mismatch(stale, target))):
                    continue  # already imported and up to date
                src_arm, imported = _import_fbx(item.filepath)
                if src_arm and src_arm.animation_data and src_arm.animation_data.action:
                    src_action = src_arm.animation_data.action
                    mism = _rest_mismatch(src_arm, target) if target else None
                    units_differ = (target is not None
                                    and abs(_rig_scale(src_arm)
                                            - _rig_scale(target)) > 1e-4)
                    if units_differ or (mism is not None
                                        and mism > _RETARGET_THRESHOLD):
                        action = _retarget_bake(context, src_arm, target, src_action)
                        retargeted += 1
                    else:
                        action = src_action.copy()
                    action.use_fake_user = True
                    _stamp_source(action, item.filepath, target)
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
        msg = tr("Đã import %d Action", "Imported %d action(s)") % count
        if retargeted:
            msg += (tr(" (%d cái được retarget — rest pose khác rig này)",
                       " (%d retargeted — rest pose differs from this rig)")
                    % retargeted)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MIXLIB_OT_remove(Operator):
    bl_idname = "mixlib.remove"
    bl_label = tr("Xoá animation", "Remove Animation")
    bl_description = tr(
        "Xoá animation đang chọn khỏi file blend này: xoá Action của nó và mọi "
        "NLA strip đang dùng nó. File FBX trên đĩa không bị đụng tới — bấm "
        "Áp dụng để import lại sau",
        "Remove the selected animation from this blend file: delete its action "
        "and any NLA strips using it. The FBX file on disk is not touched — "
        "press Apply to import it again later",
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
            tr("Đã xoá '%s' (dọn %d NLA strip)", "Removed '%s' (%d NLA strip(s) cleaned up)")
            % (name, strips_removed),
        )
        return {'FINISHED'}


class MIXLIB_OT_reimport(Operator):
    bl_idname = "mixlib.reimport"
    bl_label = tr("Import lại từ FBX", "Reimport from FBX")
    bl_description = tr(
        "Buộc import lại animation đang chọn từ file FBX và thay Action trong "
        "blend ở mọi nơi đang dùng (gán trực tiếp, NLA strip). CẢNH BÁO: mất "
        "mọi chỉnh sửa keyframe bằng tay trên Action đó",
        "Force re-import the selected animation from its FBX file and replace "
        "the in-blend action everywhere it is used (assignments, NLA strips). "
        "WARNING: discards any manual keyframe edits made to that action",
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
            self.report({'ERROR'}, tr("Không tìm thấy file: %s", "File not found: %s")
                        % item.filepath)
            return {'CANCELLED'}

        # Doc rig dich TRUOC khi import: importer FBX dat armature vua import lam
        # active, doc sau se lay nham no roi xoa mat cung dong import ben duoi.
        target = _active_armature(context)
        src_arm, imported = _import_fbx(item.filepath)
        if src_arm is None or src_arm.animation_data is None or src_arm.animation_data.action is None:
            _delete_objects(imported)
            self.report({'ERROR'}, tr("Không có animation trong FBX này (file T-pose?)",
                                      "No animation found in this FBX (T-pose file?)"))
            return {'CANCELLED'}

        src_action = src_arm.animation_data.action
        mism = _rest_mismatch(src_arm, target) if target else None
        units_differ = (target is not None
                        and abs(_rig_scale(src_arm) - _rig_scale(target)) > 1e-4)
        if units_differ or (mism is not None and mism > _RETARGET_THRESHOLD):
            action = _retarget_bake(context, src_arm, target, src_action)
            if units_differ:
                note = (tr("scale của rig %g so với %g trong FBX",
                           "rig scale %g vs %g in the FBX")
                        % (_rig_scale(target), _rig_scale(src_arm)))
            else:
                note = (tr("rest pose lệch ~%.0f%% kích thước bộ xương",
                           "rest poses differ ~%.0f%% of skeleton size")
                        % (mism * 100))
            self.report({'INFO'}, tr("Đã retarget bằng constraint bake (%s)",
                                     "Retargeted via constraint bake (%s)") % note)
        else:
            action = src_action.copy()
        action.use_fake_user = True
        _stamp_source(action, item.filepath, target)
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

        self.report({'INFO'}, tr("Đã import lại '%s' từ FBX", "Re-imported '%s' from FBX")
                    % item.name)
        return {'FINISHED'}


class MIXLIB_OT_convert_rotation(Operator):
    bl_idname = "mixlib.convert_rotation"
    bl_label = tr("Chuyển keyframe rotation", "Convert Rotation Keys")
    bl_description = tr(
        "Viết lại keyframe rotation của xương trên armature đang chọn sang kiểu "
        "kênh đã chọn, giữ nguyên chuyển động. Dùng nút này thay cho ô Rotation "
        "trong N-panel: ô đó chỉ đổi mode của xương và bỏ rơi keyframe cũ "
        "(Graph Editor vẫn hiện Quaternion, pose ngừng chuyển động)",
        "Rewrite the bone rotation keyframes of the active armature in the "
        "chosen channel type, keeping the motion. Use this instead of the "
        "N-panel Rotation dropdown, which only switches the bone's mode and "
        "leaves the old keys orphaned (Graph Editor still shows Quaternion, "
        "pose stops animating)",
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
            self.report({'ERROR'}, tr("Không có Action nào để chuyển — hãy áp dụng một animation trước",
                                      "No action to convert — apply an animation first"))
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
            self.report({'INFO'}, tr("Đã ở %s — không có gì để chuyển",
                                     "Already in %s — nothing to convert") % props.rot_mode)
            return {'FINISHED'}

        label = "Quaternion" if props.rot_mode == 'QUATERNION' else f"{props.rot_mode} Euler"
        msg = (tr("Đã chuyển %d xương trong %d Action sang %s",
                  "Converted %d bone(s) in %d action(s) to %s")
               % (total_bones, len(done), label))
        if len(rigs) > 1:
            msg += tr(", trên %d rig", ", across %d rigs") % len(rigs)
        if skipped:
            self.report({'WARNING'}, msg + tr(" — bỏ qua %d xương không có trên rig này",
                                              " — %d bone(s) not on this rig were skipped")
                        % len(skipped))
        else:
            self.report({'INFO'}, msg)
        return {'FINISHED'}


class MIXLIB_OT_stash_all(Operator):
    bl_idname = "mixlib.stash_all"
    bl_label = tr("Stash tất cả vào NLA (Unity)", "Stash All to NLA (Unity)")
    bl_description = tr(
        "Tạo một NLA strip cho mỗi Action đã import (✓) trên armature đang chọn. "
        "Mỗi strip thành một animation clip riêng khi export ra FBX / Unity. "
        "Track được để không mute — strip bị mute sẽ bị FBX exporter bỏ qua",
        "Create one NLA strip per imported action (✓) on the active armature. "
        "Each strip becomes a separate animation clip when exported to FBX / Unity. "
        "Tracks are left unmuted — muted strips are skipped by the FBX exporter",
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

        self.report({'INFO'}, tr("Đã stash %d Action vào NLA trên %s",
                                 "Stashed %d action(s) to NLA on %s") % (count, target.name))
        return {'FINISHED'}


class MIXLIB_OT_export_unity(Operator):
    bl_idname = "mixlib.export_unity"
    bl_label = tr("Export FBX cho Unity", "Export FBX (Unity)")
    bl_description = tr(
        "Mở FBX exporter với thiết lập sẵn cho Unity: chỉ object đang chọn, "
        "mỗi NLA strip một clip riêng, không có leaf bone, áp dụng scale",
        "Open the FBX exporter preset for Unity: selected objects only, "
        "NLA strips as separate clips, no leaf bones, applied scale",
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
            # imported, or the rig has been rescaled since — either way Apply
            # will re-import it, so the tick must not claim it is ready to use.
            target = _active_armature(context)
            stale = (_is_stale(action, item.filepath)
                     or (target is not None and _unit_mismatch(action, target)))
            row.label(text="", icon='FILE_REFRESH' if stale else 'CHECKMARK')


class MIXLIB_PT_panel(Panel):
    bl_label = "Mixamo Animation Library"  # i18n-skip
    bl_idname = "MIXLIB_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Mixamo Lib"

    def draw_header_preset(self, context):
        ezg_i18n.draw_toggle(self.layout, "mixlib")

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
            box.label(text=tr("Tuỳ chọn", "Options"), icon='PREFERENCES')
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
                col.label(text=tr("Rig đích: %s", "Target: %s") % target.name,
                          icon='OUTLINER_OB_ARMATURE')
            else:
                col.label(text=tr("Hãy chọn một Armature", "Select an armature"), icon='ERROR')
            col.operator("mixlib.apply", icon='PLAY')
            if SHOW_GROUNDING:
                row = col.row(align=True)
                row.operator("mixlib.ground_feet", icon='CON_FLOOR')
                row.operator("mixlib.clear_ground", text="", icon='X')
            col.operator("mixlib.import_character", icon='OUTLINER_OB_ARMATURE')
            col.operator("mixlib.import_all_actions", icon='ACTION')

            box = layout.box()
            box.label(text="Rotation Channels", icon='ORIENTATION_GIMBAL')  # i18n-skip
            row = box.row(align=True)
            row.prop(props, "rot_mode", expand=True)
            box.prop(props, "rot_convert_all")
            box.operator("mixlib.convert_rotation", icon='FILE_REFRESH')

            box = layout.box()
            box.label(text=tr("Export cho Game Engine", "Game Engine Export"), icon='EXPORT')
            col = box.column(align=True)
            col.operator("mixlib.stash_all", icon='NLA')
            col.operator("mixlib.export_unity", icon='EXPORT')
        elif props.library_path:
            layout.label(text=tr("Không tìm thấy file FBX nào", "No FBX files found"), icon='INFO')
        else:
            layout.label(text=tr("Chọn thư mục FBX Mixamo", "Pick your Mixamo FBX folder"),
                         icon='INFO')


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
    ezg_i18n.make_language_operator("mixlib"),
)


# Nut VI/EN go roi dang ki lai ca addon (xem docs/I18N.md). Du lieu nam trong
# property Scene.mixlib (thu muc, danh sach da quet, muc dang chon, tuy chon)
# la IDProperty cua scene nen van con sau lan dang ki lai. Addon khong co
# modal/timer/cache cap module nao nen khong can ezg_i18n_busy().

def register():
    ezg_i18n.register_classes(classes)
    bpy.types.Scene.mixlib = PointerProperty(type=MIXLIB_props)


def unregister():
    del bpy.types.Scene.mixlib
    ezg_i18n.unregister_classes(classes)


if __name__ == "__main__":
    register()
