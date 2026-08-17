# Manual Marker Mixamo Rigger
# Blender 4.x add-on: place a minimal Mixamo-style set of joint markers
# (chin, groin, wrists, elbows, knees) on a T-Pose humanoid, estimate the
# full Mixamo-compatible skeleton, bind with automatic weights, clean weights.
# Right-side markers follow the left side in realtime via drivers, on a
# user-selectable symmetry axis (X / Y / Z).

import math

import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADDON_NAME = "Manual Marker Mixamo Rigger"
MARKER_PREFIX = "MMR_MARKER_"
MARKER_COLLECTION_NAME = "MMR_Joint_Markers"
ARMATURE_NAME = "MMR_Mixamo_Armature"
SYMMETRY_CENTER_NAME = "MMR_SYMMETRY_CENTER"
BONE_PREFIX = "mixamorig:"
GENERATED_TAG = "mmr_generated"  # custom property tag on generated armatures

CENTER_X = 0.0  # default symmetry center on the X axis

# Symmetry-axis lookup tables.
AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}
AXIS_LETTER = ('x', 'y', 'z')
AXIS_TRANSFORM = ('LOC_X', 'LOC_Y', 'LOC_Z')
FORWARD_SIGN = {'POSITIVE': 1.0, 'NEGATIVE': -1.0}
# The character must stand Z-up in Blender for Mixamo compatibility (the rig's
# +90 X object rotation maps world Z-up -> Mixamo data Y-up). Not configurable.
WORLD_UP_AXIS = 'Z'

# The markers the user places (shoulders are placed manually, not estimated).
CENTER_MARKERS = ["Chin", "Groin"]
LEFT_MARKERS = ["LeftShoulder", "LeftWrist", "LeftElbow", "LeftKnee"]
RIGHT_MARKERS = ["RightShoulder", "RightWrist", "RightElbow", "RightKnee"]
ALL_MARKERS = CENTER_MARKERS + LEFT_MARKERS + RIGHT_MARKERS

MIRROR_PAIRS = [
    ("LeftShoulder", "RightShoulder"),
    ("LeftWrist", "RightWrist"),
    ("LeftElbow", "RightElbow"),
    ("LeftKnee", "RightKnee"),
]

# Default marker layout for a generic T-Pose humanoid.
# Values are fractions of total character height: (x, y, z).
# The character is assumed to face -Y (Blender front view).
MARKER_TEMPLATE = {
    "Chin":         (0.00, 0.00, 0.86),
    "Groin":        (0.00, 0.00, 0.50),
    "LeftShoulder": (0.10, 0.00, 0.81),
    "LeftWrist":    (0.38, 0.00, 0.79),
    "LeftElbow":    (0.24, 0.00, 0.79),
    "LeftKnee":     (0.08, 0.00, 0.28),
}

# Bright viewport colors so markers stand out (empties use object color).
MARKER_COLOR_CENTER = (1.0, 0.85, 0.05, 1.0)  # bright yellow
MARKER_COLOR_LEFT = (0.15, 1.0, 0.25, 1.0)    # bright green
MARKER_COLOR_RIGHT = (0.2, 0.55, 1.0, 1.0)    # bright blue


def marker_color(joint):
    if joint in LEFT_MARKERS:
        return MARKER_COLOR_LEFT
    if joint in RIGHT_MARKERS:
        return MARKER_COLOR_RIGHT
    return MARKER_COLOR_CENTER


# The neck base is placed at the shoulder markers' height along the Groin->Chin
# axis, clamped to a plausible range in case a marker is misplaced. The spine
# joints are fractions of the Groin->Neck segment (these reproduce the old
# 0.25/0.45/0.65-of-Groin->Chin layout for a 0.88 shoulder height).
NECK_T_MIN = 0.55
NECK_T_MAX = 0.92
SPINE_T_OF_NECK = 0.28
SPINE1_T_OF_NECK = 0.51
SPINE2_T_OF_NECK = 0.74

# Internal skeleton joints are estimated from the markers + mesh bounding box.
# Bone definitions in creation order (parents before children):
# (bone name, parent bone, head joint key, tail joint key)
BONE_DEFS = [
    ("Hips",          None,            "Hips",         "Spine"),
    ("Spine",         "Hips",          "Spine",        "Spine1"),
    ("Spine1",        "Spine",         "Spine1",       "Spine2"),
    ("Spine2",        "Spine1",        "Spine2",       "Neck"),
    ("Neck",          "Spine2",        "Neck",         "Head"),
    ("Head",          "Neck",          "Head",         "HeadTop"),

    ("LeftShoulder",  "Spine2",        "Spine2",       "LeftShoulderJ"),
    ("LeftArm",       "LeftShoulder",  "LeftShoulderJ", "LeftElbow"),
    ("LeftForeArm",   "LeftArm",       "LeftElbow",    "LeftWrist"),
    ("LeftHand",      "LeftForeArm",   "LeftWrist",    "LeftHandEnd"),

    ("RightShoulder", "Spine2",        "Spine2",       "RightShoulderJ"),
    ("RightArm",      "RightShoulder", "RightShoulderJ", "RightElbow"),
    ("RightForeArm",  "RightArm",      "RightElbow",   "RightWrist"),
    ("RightHand",     "RightForeArm",  "RightWrist",   "RightHandEnd"),

    ("LeftUpLeg",     "Hips",          "LeftHip",      "LeftKnee"),
    ("LeftLeg",       "LeftUpLeg",     "LeftKnee",     "LeftAnkle"),
    ("LeftFoot",      "LeftLeg",       "LeftAnkle",    "LeftFootEnd"),

    ("RightUpLeg",    "Hips",          "RightHip",     "RightKnee"),
    ("RightLeg",      "RightUpLeg",    "RightKnee",    "RightAnkle"),
    ("RightFoot",     "RightLeg",      "RightAnkle",   "RightFootEnd"),
]

# Fallback direction for the tail when head and tail would coincide.
FALLBACK_TAIL_DIR = {
    "LeftHand":  Vector((1.0, 0.0, 0.0)),
    "RightHand": Vector((-1.0, 0.0, 0.0)),
    "LeftFoot":  Vector((0.0, -1.0, 0.0)),
    "RightFoot": Vector((0.0, -1.0, 0.0)),
}
DEFAULT_TAIL_DIR = Vector((0.0, 0.0, 1.0))

# --- Mixamo rig space -------------------------------------------------------
# A skeleton imported via "Import as New Character" (FBX, automatic_bone_
# orientation=False) has its armature OBJECT rotated +90 deg on X and scaled to
# 0.01, with bone data stored Y-up in centimeters. Mixamo animation actions are
# keyed against exactly this rest space (Hips translation in cm, rotations
# relative to these rest orientations), so our generated rig must match it or
# animations fly the character away / break.
MIXAMO_ARM_ROT_X = math.radians(90.0)   # armature object rotation on X
MIXAMO_ARM_SCALE = 0.01                  # cm -> m
# world = M @ local ; local = M.inverted() @ world
MIXAMO_ARM_MATRIX = (Matrix.Rotation(MIXAMO_ARM_ROT_X, 4, 'X')
                     @ Matrix.Scale(MIXAMO_ARM_SCALE, 4))
MIXAMO_ARM_MATRIX_INV = MIXAMO_ARM_MATRIX.inverted()

# Per-bone roll target: the direction (in armature-data / Y-up space) that each
# bone's local +Z axis should point toward, matching the real Mixamo rest pose.
# Spine/legs -> forward (+Z); arms -> down (-Y); feet -> up-forward.
_Z_FWD = Vector((0.0, 0.0, 1.0))
_Z_DOWN = Vector((0.0, -1.0, 0.0))
_Z_UPFWD = Vector((0.0, 1.0, 1.0))
ROLL_TARGETS = {
    "Hips": _Z_FWD, "Spine": _Z_FWD, "Spine1": _Z_FWD, "Spine2": _Z_FWD,
    "Neck": _Z_FWD, "Head": _Z_FWD,
    "LeftShoulder": _Z_DOWN, "LeftArm": _Z_DOWN, "LeftForeArm": _Z_DOWN,
    "LeftHand": _Z_DOWN,
    "RightShoulder": _Z_DOWN, "RightArm": _Z_DOWN, "RightForeArm": _Z_DOWN,
    "RightHand": _Z_DOWN,
    "LeftUpLeg": _Z_FWD, "LeftLeg": _Z_FWD, "LeftFoot": _Z_UPFWD,
    "RightUpLeg": _Z_FWD, "RightLeg": _Z_FWD, "RightFoot": _Z_UPFWD,
}

# --- Bone groups used by Smart Mixamo Weight Refine ------------------------
CENTER_BONES = [
    BONE_PREFIX + "Hips", BONE_PREFIX + "Spine", BONE_PREFIX + "Spine1",
    BONE_PREFIX + "Spine2", BONE_PREFIX + "Neck", BONE_PREFIX + "Head",
]
LEFT_ARM_BONES = [
    BONE_PREFIX + "LeftShoulder", BONE_PREFIX + "LeftArm",
    BONE_PREFIX + "LeftForeArm", BONE_PREFIX + "LeftHand",
]
RIGHT_ARM_BONES = [
    BONE_PREFIX + "RightShoulder", BONE_PREFIX + "RightArm",
    BONE_PREFIX + "RightForeArm", BONE_PREFIX + "RightHand",
]
LEFT_LEG_BONES = [
    BONE_PREFIX + "LeftUpLeg", BONE_PREFIX + "LeftLeg", BONE_PREFIX + "LeftFoot",
]
RIGHT_LEG_BONES = [
    BONE_PREFIX + "RightUpLeg", BONE_PREFIX + "RightLeg", BONE_PREFIX + "RightFoot",
]

# Ordered chains for capsule/region distance tests.
CHAINS = {
    "torso": CENTER_BONES,
    "left_arm": LEFT_ARM_BONES,
    "right_arm": RIGHT_ARM_BONES,
    "left_leg": LEFT_LEG_BONES,
    "right_leg": RIGHT_LEG_BONES,
}
LEFT_CHAINS = {"left_arm", "left_leg"}
RIGHT_CHAINS = {"right_arm", "right_leg"}
LEFT_SIDE_BONES = set(LEFT_ARM_BONES) | set(LEFT_LEG_BONES)
RIGHT_SIDE_BONES = set(RIGHT_ARM_BONES) | set(RIGHT_LEG_BONES)
ALL_DEFORM_BONES = (CENTER_BONES + LEFT_ARM_BONES + RIGHT_ARM_BONES
                    + LEFT_LEG_BONES + RIGHT_LEG_BONES)

WEIGHT_BACKUP_PREFIX = "MMR_BACKUP_"

# Feature flag: hide the Smart Mixamo Weight Refine UI block (backup/restore,
# profile, thresholds, refine, diagnostics). Set True to re-enable it later.
# The operators/functions stay registered â€” only the panel section is hidden.
SHOW_SMART_REFINE = False

# Weight-profile parameter presets.
WEIGHT_PROFILES = {
    'BALANCED': {
        "clean_threshold": 0.005, "max_weights": 4, "joint_blend_strength": 0.35,
        "cross_side_aggressive": True, "small_part_rigid": True,
    },
    'SOFT_ORGANIC': {
        "clean_threshold": 0.002, "max_weights": 4, "joint_blend_strength": 0.55,
        "cross_side_aggressive": False, "small_part_rigid": False,
    },
    'RIGID_GAME': {
        "clean_threshold": 0.01, "max_weights": 4, "joint_blend_strength": 0.2,
        "cross_side_aggressive": True, "small_part_rigid": True,
    },
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def marker_name(joint):
    return MARKER_PREFIX + joint


def find_marker(joint):
    return bpy.data.objects.get(marker_name(joint))


def missing_marker_joints():
    return [j for j in ALL_MARKERS if find_marker(j) is None]


def marker_world_location(joint, depsgraph):
    """Evaluated world position of a marker â€” correct even for driven markers."""
    obj = find_marker(joint)
    if obj is None:
        return None
    return obj.evaluated_get(depsgraph).matrix_world.translation.copy()


def get_marker_collection(create=False):
    coll = bpy.data.collections.get(MARKER_COLLECTION_NAME)
    if coll is None and create:
        coll = bpy.data.collections.new(MARKER_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)
    return coll


def valid_object(obj, obj_type=None):
    """Return obj if it still exists in the file (and matches type), else None."""
    if obj is None:
        return None
    try:
        if obj.name not in bpy.data.objects:
            return None
    except ReferenceError:
        return None
    if obj_type and obj.type != obj_type:
        return None
    return obj


def get_target_mesh(context):
    return valid_object(context.scene.mmr_target_mesh, 'MESH')


def get_generated_armature(context):
    arm = valid_object(context.scene.mmr_armature, 'ARMATURE')
    if arm is None:
        # Fall back to lookup by name + tag (e.g. after file reload).
        candidate = bpy.data.objects.get(ARMATURE_NAME)
        if candidate and candidate.type == 'ARMATURE' and candidate.get(GENERATED_TAG):
            arm = candidate
    return arm


def armature_in_mixamo_space(arm_obj):
    """True if the armature still has the Mixamo object transform (rot +90 X,
    scale 0.01). Applying/zeroing the transform breaks animation import."""
    if arm_obj is None:
        return True
    rot_ok = abs(arm_obj.rotation_euler.x - MIXAMO_ARM_ROT_X) < 0.02
    scale_ok = all(abs(s - MIXAMO_ARM_SCALE) < 1e-4 for s in arm_obj.scale)
    return rot_ok and scale_ok


def ensure_object_mode(context):
    if context.mode != 'OBJECT' and context.active_object:
        bpy.ops.object.mode_set(mode='OBJECT')


def select_only(context, objects, active=None):
    for obj in context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    if active is not None:
        context.view_layer.objects.active = active


def mesh_bbox_min_max(mesh_obj):
    """World-space bounding-box min and max corners, as two Vectors."""
    corners = [mesh_obj.matrix_world @ Vector(c) for c in mesh_obj.bound_box]
    mn = Vector((min(c.x for c in corners),
                 min(c.y for c in corners),
                 min(c.z for c in corners)))
    mx = Vector((max(c.x for c in corners),
                 max(c.y for c in corners),
                 max(c.z for c in corners)))
    return mn, mx


def mesh_bbox_center(mesh_obj):
    """World-space center of the mesh bounding box, as a Vector."""
    mn, mx = mesh_bbox_min_max(mesh_obj)
    return (mn + mx) * 0.5


def mesh_up_extent(mesh_obj, up_index):
    """(min, max, size) of the bounding box along the given up axis index."""
    mn, mx = mesh_bbox_min_max(mesh_obj)
    return mn[up_index], mx[up_index], mx[up_index] - mn[up_index]


def mesh_max_dimension(mesh_obj):
    """Largest bounding-box dimension â€” an orientation-agnostic size scale."""
    mn, mx = mesh_bbox_min_max(mesh_obj)
    return max(mx - mn)


def get_world_location(obj):
    """World-space location of an object."""
    return obj.matrix_world.translation.copy()


def world_to_armature_local(arm_obj, world_pos):
    """Convert a world-space position into the armature's local space, so edit
    bones are placed correctly even if the armature transform is not identity."""
    return arm_obj.matrix_world.inverted() @ world_pos


def mesh_has_unapplied_transform(mesh_obj):
    """True if the mesh still has non-identity rotation or scale."""
    if any(abs(s - 1.0) > 1e-4 for s in mesh_obj.scale):
        return True
    if any(abs(r) > 1e-4 for r in mesh_obj.rotation_euler):
        return True
    return False


# ---------------------------------------------------------------------------
# Realtime symmetry (drivers)
# ---------------------------------------------------------------------------

def get_symmetry_axis(context):
    """Return the active symmetry axis: 'X', 'Y' or 'Z'."""
    return context.scene.mmr_symmetry_axis


def get_up_axis(context):
    """Character up axis in Blender WORLD space. Locked to Z: the Mixamo rig
    conversion (armature object rot +90 X) assumes the character stands Z-up in
    Blender, so the up axis is not user-configurable â€” a Y-up/lying setup would
    produce a rig lying on its side. The character must stand upright (Z-up)."""
    return WORLD_UP_AXIS


def get_forward_vector(context):
    """Unit vector pointing where the toes/feet should aim. Derived from the
    Character Forward Axis + Forward Direction settings â€” NOT the symmetry axis."""
    axis = context.scene.mmr_forward_axis
    sign = FORWARD_SIGN[context.scene.mmr_forward_dir]
    v = Vector((0.0, 0.0, 0.0))
    v[AXIS_INDEX[axis]] = sign
    return v


def get_or_create_symmetry_center(context):
    """The center empty whose location defines the mirror plane."""
    obj = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    if obj is None:
        obj = bpy.data.objects.new(SYMMETRY_CENTER_NAME, None)  # Empty
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = 0.1
        obj.location = (CENTER_X, 0.0, 0.0)
        obj.show_in_front = True
    if not obj.users_collection:
        get_marker_collection(create=True).objects.link(obj)
    return obj


def clear_location_drivers(obj):
    """Remove all drivers on the object's location channels (safe if none)."""
    if obj is None or obj.animation_data is None:
        return
    try:
        obj.driver_remove("location", -1)  # -1 = all three channels
    except (TypeError, RuntimeError):
        pass


def mirror_position_by_axis(left_pos, center_pos, axis):
    """Mirror left_pos across the plane defined by center_pos on the given axis.
    The chosen axis is inverted; the other two components are copied."""
    p = left_pos.copy()
    a = AXIS_INDEX[axis]
    p[a] = 2.0 * center_pos[a] - left_pos[a]
    return p


def add_realtime_symmetry_driver(left_obj, right_obj, center_obj, axis):
    """Drive right_obj.location from left_obj across center_obj on the given axis.

    Mirrored axis channel:  2*c<axis> - l<axis>
    Other two channels:     l<other>
    """
    clear_location_drivers(right_obj)  # never stack duplicate drivers
    a = AXIS_INDEX[axis]
    for i in range(3):
        letter = AXIS_LETTER[i]
        fcurve = right_obj.driver_add("location", i)
        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        for var in list(driver.variables):
            driver.variables.remove(var)

        # Left-marker variable for this channel (lx / ly / lz).
        lvar = driver.variables.new()
        lvar.name = "l" + letter
        lvar.type = 'TRANSFORMS'
        ltarget = lvar.targets[0]
        ltarget.id = left_obj
        ltarget.transform_type = AXIS_TRANSFORM[i]
        ltarget.transform_space = 'WORLD_SPACE'

        if i == a:
            # Center variable (cx / cy / cz) only on the mirrored channel.
            cvar = driver.variables.new()
            cvar.name = "c" + letter
            cvar.type = 'TRANSFORMS'
            ctarget = cvar.targets[0]
            ctarget.id = center_obj
            ctarget.transform_type = AXIS_TRANSFORM[i]
            ctarget.transform_space = 'WORLD_SPACE'
            driver.expression = f"2*c{letter}-l{letter}"
        else:
            driver.expression = f"l{letter}"

    # Locked channels tell the user these markers are symmetry-controlled.
    right_obj.lock_location = (True, True, True)


def enable_realtime_symmetry(context):
    """Add/refresh mirror drivers on all right markers for the current axis.

    Returns (enabled_pair_count, missing_marker_names).
    """
    center = get_or_create_symmetry_center(context)
    axis = get_symmetry_axis(context)
    a = AXIS_INDEX[axis]
    enabled = 0
    missing = []
    for left_joint, right_joint in MIRROR_PAIRS:
        left = find_marker(left_joint)
        right = find_marker(right_joint)
        if left is None:
            missing.append(left_joint)
            continue
        if right is None:
            missing.append(right_joint)
            continue
        add_realtime_symmetry_driver(left, right, center, axis)
        enabled += 1
    # Lock center markers on the symmetry axis (non-destructive: no auto-snap;
    # use 'Snap Center Markers To Symmetry Plane' to move them onto the plane).
    for joint in CENTER_MARKERS:
        obj = find_marker(joint)
        if obj is not None:
            obj.lock_location = (False, False, False)
            obj.lock_location[a] = True
    return enabled, missing


def disable_realtime_symmetry(context):
    """Remove mirror drivers; right markers keep their mirrored positions."""
    center = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    center_pos = center.location.copy() if center is not None else Vector((CENTER_X, 0, 0))
    axis = get_symmetry_axis(context)
    for left_joint, right_joint in MIRROR_PAIRS:
        right = find_marker(right_joint)
        if right is None:
            continue
        left = find_marker(left_joint)
        clear_location_drivers(right)
        if left is not None:
            # Bake the current mirrored position onto the datablock
            # (drivers only wrote to the evaluated copy).
            right.location = mirror_position_by_axis(left.location, center_pos, axis)
        right.lock_location = (False, False, False)
    for joint in CENTER_MARKERS:
        obj = find_marker(joint)
        if obj is not None:
            obj.lock_location = (False, False, False)


def realtime_symmetry_active():
    """True when all three right markers exist and have location drivers."""
    for _, right_joint in MIRROR_PAIRS:
        right = find_marker(right_joint)
        if right is None or right.animation_data is None:
            return False
        if not any(fc.data_path == "location" for fc in right.animation_data.drivers):
            return False
    return True


def snap_center_markers_to_symmetry_plane(context):
    """Move Chin/Groin onto the symmetry plane along the active axis.

    Returns list of snapped joint names.
    """
    center = get_or_create_symmetry_center(context)
    axis = get_symmetry_axis(context)
    a = AXIS_INDEX[axis]
    snapped = []
    for joint in CENTER_MARKERS:
        obj = find_marker(joint)
        if obj is not None:
            obj.location[a] = center.location[a]  # lock_location doesn't block python
            snapped.append(joint)
    return snapped


def set_symmetry_center_from_mesh(context):
    """Set the center object's active-axis component to the mesh bbox center.

    Returns (value_set, error_message). One of the two is None.
    """
    mesh_obj = get_target_mesh(context)
    if mesh_obj is None:
        return None, "No target mesh set. Use 'Set Selected Mesh' first."
    center = get_or_create_symmetry_center(context)
    axis = get_symmetry_axis(context)
    a = AXIS_INDEX[axis]
    bbox_center = mesh_bbox_center(mesh_obj)
    center.location[a] = bbox_center[a]
    # Drivers reference the center's location live, so they update automatically.
    return bbox_center[a], None


def _symmetry_toggled(self, context):
    """Update callback for the Use Symmetry checkbox."""
    any_right = any(find_marker(rj) is not None for _, rj in MIRROR_PAIRS)
    if self.mmr_use_symmetry:
        if any_right:
            enable_realtime_symmetry(context)
    else:
        disable_realtime_symmetry(context)


def _symmetry_axis_changed(self, context):
    """Update callback for the Symmetry Axis dropdown â€” rebuild drivers live."""
    if self.mmr_use_symmetry:
        any_right = any(find_marker(rj) is not None for _, rj in MIRROR_PAIRS)
        if any_right:
            enable_realtime_symmetry(context)


# ---------------------------------------------------------------------------
# Marker functions
# ---------------------------------------------------------------------------

def remove_all_markers():
    """Delete only this add-on's marker objects and the symmetry center
    (also cleans up markers from older versions). Never touches user meshes."""
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.name.startswith(MARKER_PREFIX) or obj.name == SYMMETRY_CENTER_NAME:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    coll = get_marker_collection()
    if coll is not None and not coll.objects and not coll.children:
        bpy.data.collections.remove(coll)
    return removed


def create_marker(joint, location, size, collection):
    obj = bpy.data.objects.new(marker_name(joint), None)  # Empty
    obj.empty_display_type = 'SPHERE'
    obj.empty_display_size = size
    obj.location = location
    obj.show_in_front = True
    obj.show_name = True
    obj.color = marker_color(joint)
    collection.objects.link(obj)
    return obj


def apply_marker_colors():
    """Re-apply bright colors to any existing markers (keeps positions)."""
    colored = 0
    for joint in ALL_MARKERS:
        obj = find_marker(joint)
        if obj is not None:
            obj.color = marker_color(joint)
            obj.show_in_front = True
            colored += 1
    return colored


def create_all_markers(context, mesh_obj):
    """(Re)create the minimal Mixamo marker set, laid out along the configured
    Up / Forward / Symmetry axes and scaled to the mesh if available. Realtime
    symmetry drivers are added right away when Use Symmetry is on.

    The template tuples are interpreted as (side_frac, depth_frac, up_frac):
    side -> symmetry axis, depth -> forward axis, up -> up axis.
    """
    remove_all_markers()
    coll = get_marker_collection(create=True)

    si = AXIS_INDEX[get_symmetry_axis(context)]   # left/right
    fi = AXIS_INDEX[context.scene.mmr_forward_axis]  # depth/forward
    ui = AXIS_INDEX[get_up_axis(context)]         # up

    if mesh_obj is not None:
        base_up, _, height = mesh_up_extent(mesh_obj, ui)
        center_depth = mesh_bbox_center(mesh_obj)[fi]
        if height < 1e-6:
            base_up, height, center_depth = 0.0, 1.7, 0.0
    else:
        base_up, height, center_depth = 0.0, 1.7, 0.0
    size = max(height * 0.025, 0.005)

    for joint in ALL_MARKERS:
        if joint in MARKER_TEMPLATE:
            side_f, depth_f, up_f = MARKER_TEMPLATE[joint]
        else:
            # Right-side markers mirror the left template on the symmetry axis.
            side_f, depth_f, up_f = MARKER_TEMPLATE[joint.replace("Right", "Left", 1)]
            side_f = -side_f
        location = Vector((0.0, 0.0, 0.0))
        location[si] = CENTER_X + side_f * height
        location[fi] = center_depth + depth_f * height
        location[ui] = base_up + up_f * height
        create_marker(joint, location, size, coll)

    get_or_create_symmetry_center(context)
    if context.scene.mmr_use_symmetry:
        enable_realtime_symmetry(context)


def mirror_left_to_right(context):
    """Manual fallback: copy left marker positions to right markers across the
    symmetry plane, respecting the active axis.

    Returns (mirrored_count, missing_left, missing_right).
    """
    center = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    center_pos = center.location.copy() if center is not None else Vector((CENTER_X, 0, 0))
    axis = get_symmetry_axis(context)
    mirrored = 0
    missing_left = []
    missing_right = []
    for left_joint, right_joint in MIRROR_PAIRS:
        left = find_marker(left_joint)
        right = find_marker(right_joint)
        if left is None:
            missing_left.append(left_joint)
            continue
        if right is None:
            missing_right.append(right_joint)
            continue
        right.location = mirror_position_by_axis(left.location, center_pos, axis)
        mirrored += 1
    return mirrored, missing_left, missing_right


# ---------------------------------------------------------------------------
# Skeleton estimation
# ---------------------------------------------------------------------------

def lerp(a, b, t):
    return a + (b - a) * t


def estimate_skeleton(context, mesh_obj):
    """Estimate the full Mixamo joint positions (WORLD SPACE) from the 8 visible
    markers plus the mesh bounding box, using the selected symmetry axis for the
    left/right direction. Uses evaluated (driver-resolved) marker positions.

    Returns (joints_dict, error_message, info_dict). joints/info are None on error.
    """
    missing = missing_marker_joints()
    if missing:
        return None, "Missing markers: " + ", ".join(missing), None
    if mesh_obj is None:
        return None, "No target mesh set. Use 'Set Selected Mesh' first.", None

    depsgraph = context.evaluated_depsgraph_get()
    m = {j: marker_world_location(j, depsgraph) for j in ALL_MARKERS}

    # Guard against markers accidentally left at the world origin.
    at_origin = [j for j in ALL_MARKERS if m[j].length < 1e-4]
    if at_origin:
        return None, ("Markers at world origin (move them onto the character): "
                      + ", ".join(at_origin)), None

    axis = get_symmetry_axis(context)
    ai = AXIS_INDEX[axis]                     # left/right (side) axis
    up_index = AXIS_INDEX[get_up_axis(context)]  # world up (locked to Z)
    if up_index == ai:
        return None, ("Symmetry Axis cannot be the up axis (Z). The character "
                      "stands Z-up; set Symmetry Axis to X or Y."), None

    # Height/base measured along the world up axis (Z).
    min_up, max_up, height = mesh_up_extent(mesh_obj, up_index)
    if height < 1e-6:
        return None, "Target mesh has no height along the up axis (Z).", None

    chin, groin = m["Chin"], m["Groin"]
    body_vec = chin - groin
    if body_vec.length < 1e-6:
        return None, "Chin and Groin markers coincide; move them apart.", None
    body_up = body_vec.normalized()
    # The character MUST stand upright (Chin above Groin along world Z) or the
    # Mixamo conversion produces a rig lying on its side. This catches markers
    # left in a horizontal/default layout.
    if abs(body_up[up_index]) < 0.6:
        return None, ("Character is not standing upright: the Chin marker must be "
                      "clearly ABOVE the Groin marker along world Z. Recreate the "
                      "markers and place them on a Z-up standing character."), None
    if body_up[up_index] < 0:
        return None, ("Chin marker is BELOW the Groin marker. Place Chin at the "
                      "head and Groin at the pelvis on a Z-up standing character."), None
    # Depth/forward axis = the remaining axis (not up, not symmetry).
    depth_candidates = [i for i in range(3) if i != up_index and i != ai]
    depth_index = depth_candidates[0] if depth_candidates else None

    warnings = []
    j = {}

    # --- Center spine chain (vertical through the body) ---------------------
    # The base of the neck is anatomically level with the shoulders, so derive
    # it from the user's Shoulder markers instead of a fixed fraction of the
    # Groin->Chin span (with a high Chin marker that pushed the Neck bone up
    # near the jaw). The spine joints are then spread over Groin->Neck so the
    # chain keeps its Mixamo-like proportions wherever the neck ends up.
    shoulder_mid = (m["LeftShoulder"] + m["RightShoulder"]) * 0.5
    t_shoulder = (shoulder_mid - groin).dot(body_up) / body_vec.length
    t_neck = min(max(t_shoulder, NECK_T_MIN), NECK_T_MAX)
    if t_neck != t_shoulder:
        warnings.append(
            f"Shoulder markers sit at {t_shoulder:.2f} of the Groin->Chin span; "
            f"the neck base was clamped to {t_neck:.2f}. Check the Chin and "
            f"Shoulder marker heights.")

    j["Hips"] = groin + body_up * (0.03 * height)
    neck = lerp(groin, chin, t_neck)
    j["Spine"] = lerp(groin, neck, SPINE_T_OF_NECK)
    j["Spine1"] = lerp(groin, neck, SPINE1_T_OF_NECK)
    j["Spine2"] = lerp(groin, neck, SPINE2_T_OF_NECK)
    j["Neck"] = neck
    j["Head"] = chin + body_up * (0.03 * height)
    j["HeadTop"] = j["Head"] + body_up * (0.09 * height)
    spine2 = j["Spine2"]

    # --- Arms: the shoulder joint comes from the user's Shoulder marker ------
    for side in ("Left", "Right"):
        shoulder = m[side + "Shoulder"].copy()
        elbow = m[side + "Elbow"]
        wrist = m[side + "Wrist"]

        # Hand extends beyond the wrist along the forearm direction.
        forearm_dir = wrist - elbow
        if forearm_dir.length < 1e-6:
            forearm_dir = FALLBACK_TAIL_DIR[side + "Hand"].copy()
        hand_len = max(forearm_dir.length * 0.35, 0.02 * height)
        hand_end = wrist + forearm_dir.normalized() * hand_len

        j[side + "ShoulderJ"] = shoulder
        j[side + "Elbow"] = elbow.copy()
        j[side + "Wrist"] = wrist.copy()
        j[side + "HandEnd"] = hand_end

        # Validation: wrist beyond elbow, elbow beyond shoulder (along side axis)
        d_shoulder = abs(shoulder[ai] - spine2[ai])
        d_elbow = abs(elbow[ai] - spine2[ai])
        d_wrist = abs(wrist[ai] - spine2[ai])
        if d_wrist <= d_elbow:
            warnings.append(f"{side} wrist is not farther from the body than the "
                            f"elbow along {axis}; check marker placement.")
        if d_elbow <= d_shoulder:
            warnings.append(f"{side} elbow is not farther from the body than the "
                            f"estimated shoulder along {axis}.")

    # --- Legs: hip socket offset toward the knee, foot near mesh bottom ------
    # Foot forward direction comes from Character Forward Axis + Direction and
    # is the SAME for both feet (never mirrored, never the symmetry axis).
    forward_vec = get_forward_vector(context)
    for side in ("Left", "Right"):
        knee = m[side + "Knee"]

        hip = groin.copy()
        hip[ai] = groin[ai] + (knee[ai] - groin[ai]) * 0.35
        hip[up_index] = groin[up_index]

        # Ankle/foot head: under the knee, at a realistic ankle height above the
        # mesh bottom (Mixamo's ankle sits ~7% of height up, not on the floor).
        ankle = knee.copy()
        ankle[up_index] = min_up + 0.07 * height

        # Foot bone points forward AND down toward the toe on the ground, like
        # Mixamo's foot bone (not purely horizontal), so the foot rotates
        # correctly under animation and the toe lands near the floor.
        down = Vector((0.0, 0.0, 0.0))
        down[up_index] = -1.0
        foot_dir = (forward_vec + down).normalized()
        lower_leg_length = (ankle - knee).length
        foot_length = max(height * 0.10, lower_leg_length * 0.30)
        foot_end = ankle + foot_dir * foot_length

        j[side + "Hip"] = hip
        j[side + "Knee"] = knee.copy()
        j[side + "Ankle"] = ankle
        j[side + "FootEnd"] = foot_end

    fi = AXIS_INDEX[context.scene.mmr_forward_axis]
    if fi == ai or fi == up_index:
        warnings.append("Character Forward Axis overlaps the up or symmetry axis; "
                        "feet may point along the body. Use three distinct axes "
                        "(e.g. Up=Y, Forward=Z, Symmetry=X).")

    info = {
        "axis": axis,
        "up_axis": get_up_axis(context),
        "forward_axis": context.scene.mmr_forward_axis,
        "forward_dir": context.scene.mmr_forward_dir,
        "forward_vec": forward_vec,
        "LeftShoulder": j["LeftShoulderJ"].copy(),
        "RightShoulder": j["RightShoulderJ"].copy(),
        "LeftHip": j["LeftHip"].copy(),
        "RightHip": j["RightHip"].copy(),
        "LeftFootHead": j["LeftAnkle"].copy(),
        "LeftFootTail": j["LeftFootEnd"].copy(),
        "RightFootHead": j["RightAnkle"].copy(),
        "RightFootTail": j["RightFootEnd"].copy(),
        "warnings": warnings,
    }
    return j, None, info


# ---------------------------------------------------------------------------
# Armature functions
# ---------------------------------------------------------------------------

def build_mixamo_armature(context, keep_existing=False):
    """Create the Mixamo-style armature from the estimated skeleton.

    keep_existing=False (default): replaces the add-on's managed armature
    (removes every GENERATED_TAG rig first). keep_existing=True: builds an
    ADDITIONAL armature with a unique name and does not touch any existing
    armature â€” the new rig is left untagged so later rebuilds never delete it
    (useful for rigging several characters in one file).

    Returns (armature_object, error_message, info_dict). obj/info are None on error.
    """
    mesh_obj = get_target_mesh(context)
    if mesh_obj is not None and mesh_has_unapplied_transform(mesh_obj):
        return None, ("Mesh '%s' has unapplied rotation/scale. Click 'Prepare "
                      "Mesh' first so joint positions are computed correctly."
                      % mesh_obj.name), None

    joints, error, info = estimate_skeleton(context, mesh_obj)
    if error:
        return None, error, None

    if not keep_existing:
        # Remove EVERY armature this add-on generated (including stale ".001"
        # duplicates) so a rebuild never leaves two rigs behind.
        for obj in list(bpy.data.objects):
            if obj.type == 'ARMATURE' and obj.get(GENERATED_TAG):
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data and data.users == 0:
                    bpy.data.armatures.remove(data)
        # Never overwrite a user's armature that happens to share our name.
        existing = bpy.data.objects.get(ARMATURE_NAME)
        if existing is not None:
            return None, (
                f"An object named '{ARMATURE_NAME}' already exists and was not "
                "generated by this add-on. Rename or remove it first."
            ), None

    # Bone coordinates live in Mixamo data space (cm), so the minimum bone
    # length must be expressed there too (world metres * 100).
    min_bone_len = max(mesh_max_dimension(mesh_obj) * 100.0 * 0.01, 0.1)

    ensure_object_mode(context)

    # Name additional rigs after the character mesh; Blender uniquifies clashes.
    if keep_existing:
        base = ARMATURE_NAME + (("_" + mesh_obj.name) if mesh_obj else "")
    else:
        base = ARMATURE_NAME
    arm_data = bpy.data.armatures.new(base)
    arm_obj = bpy.data.objects.new(base, arm_data)
    if not keep_existing:
        # Only the managed rig carries the tag; additional rigs stay untagged so
        # they are treated like user armatures and never auto-deleted.
        arm_obj[GENERATED_TAG] = True
    # Match a Mixamo-imported rig: object rotated +90 X, scaled 0.01, so the
    # bone DATA ends up Y-up in centimetres while the bones still appear on the
    # character in world space.
    arm_obj.location = (0.0, 0.0, 0.0)
    arm_obj.rotation_euler = (MIXAMO_ARM_ROT_X, 0.0, 0.0)
    arm_obj.scale = (MIXAMO_ARM_SCALE, MIXAMO_ARM_SCALE, MIXAMO_ARM_SCALE)
    context.scene.collection.objects.link(arm_obj)
    select_only(context, [arm_obj], active=arm_obj)

    def to_local(world_pos):
        # Explicit conversion (independent of depsgraph update timing).
        return MIXAMO_ARM_MATRIX_INV @ world_pos

    bpy.ops.object.mode_set(mode='EDIT')
    try:
        edit_bones = arm_data.edit_bones
        for bone_key, parent_key, head_joint, tail_joint in BONE_DEFS:
            bone = edit_bones.new(BONE_PREFIX + bone_key)
            bone.use_deform = True

            # Each bone runs from its own joint to the NEXT joint in the chain,
            # so a child's head lands exactly on its parent's tail. Do not
            # straighten the bone onto a canonical axis: that keeps the head on
            # the joint but throws the tail off the next joint, which breaks the
            # chain visually and when posing.
            head = to_local(joints[head_joint])
            tail = to_local(joints[tail_joint])

            # Never create zero-length bones.
            if (tail - head).length < min_bone_len:
                direction = FALLBACK_TAIL_DIR.get(bone_key, DEFAULT_TAIL_DIR)
                tail = head + direction * min_bone_len

            bone.head = head
            bone.tail = tail
            if parent_key is not None:
                parent_bone = edit_bones[BONE_PREFIX + parent_key]
                bone.parent = parent_bone
                # Connect only when the head really is the parent's tail (spine,
                # arm and leg chains). Shoulders and legs branch off the parent's
                # HEAD, so they must stay unconnected or Blender would snap them.
                bone.use_connect = ((bone.head - parent_bone.tail).length
                                    < min_bone_len * 0.01)

        # Bone roll: align each bone's local axes to the Mixamo rest convention
        # (in armature-data space) so animation rotations transfer correctly.
        for bone_key, _, _, _ in BONE_DEFS:
            eb = edit_bones[BONE_PREFIX + bone_key]
            target = ROLL_TARGETS.get(bone_key)
            if target is not None:
                eb.align_roll(target)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')

    return arm_obj, None, info


# ---------------------------------------------------------------------------
# Weight / bind functions
# ---------------------------------------------------------------------------

def bind_automatic_weights(context, mesh_obj, arm_obj):
    """Parent mesh to armature with automatic weights. Returns error or None."""
    ensure_object_mode(context)
    select_only(context, [mesh_obj, arm_obj], active=arm_obj)
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except RuntimeError as exc:
        return f"Automatic weighting failed: {exc}"

    # Verify / repair the armature modifier.
    mod = next((m for m in mesh_obj.modifiers
                if m.type == 'ARMATURE' and m.object == arm_obj), None)
    if mod is None:
        mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
        mod.object = arm_obj

    # Verify vertex groups were created for the deform bones.
    bone_names = {b.name for b in arm_obj.data.bones if b.use_deform}
    created = bone_names & {vg.name for vg in mesh_obj.vertex_groups}
    if not created:
        return ("No vertex groups were created. Automatic weights likely failed "
                "(check for non-manifold/overlapping geometry or unapplied scale).")
    return None


def bind_accessory_to_nearest_bone(context, acc, arm_obj, bone_override=None):
    """Rigidly bind an accessory mesh (glasses, hat, beard, belt...) to the
    nearest deform bone: single vertex group weight 1 + armature modifier +
    parented to the armature. Returns (bone_name, error_message).
    """
    if acc.type != 'MESH':
        return None, f"'{acc.name}' is not a mesh."
    if not acc.data.vertices:
        return None, f"'{acc.name}' has no geometry."

    deform = [b for b in arm_obj.data.bones if b.use_deform]
    if not deform:
        return None, "Armature has no deform bones."

    if bone_override and bone_override in arm_obj.data.bones:
        bone_name = bone_override
    else:
        # Nearest deform bone to the accessory's world bounding-box centre.
        center = mesh_bbox_center(acc)
        bone_world = get_armature_bone_world_positions(arm_obj)
        best, best_d = None, float('inf')
        for b in deform:
            info = bone_world[b.name]
            d, _ = point_segment_distance_and_t(center, info["head"], info["tail"])
            if d < best_d:
                best_d, best = d, b.name
        bone_name = best

    ensure_object_mode(context)
    # Parent to the armature (keep world position), consistent with the body.
    select_only(context, [acc, arm_obj], active=arm_obj)
    try:
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    except RuntimeError as exc:
        return None, f"Could not parent '{acc.name}': {exc}"

    # Single deform group = 1.0 (rigid follow), replacing any existing groups.
    for vg in list(acc.vertex_groups):
        acc.vertex_groups.remove(vg)
    vg = acc.vertex_groups.new(name=bone_name)
    vg.add(list(range(len(acc.data.vertices))), 1.0, 'REPLACE')

    # Armature modifier tied to the generated armature.
    mod = next((m for m in acc.modifiers
                if m.type == 'ARMATURE' and m.object == arm_obj), None)
    if mod is None:
        mod = acc.modifiers.new(name="Armature", type='ARMATURE')
        mod.object = arm_obj

    return bone_name, None


def transfer_weights_to_accessory(context, source_mesh, acc, arm_obj, reach=0.3):
    """Copy the body's skin weights onto an accessory with Blender's Data
    Transfer (nearest-surface, interpolated) for smooth EVEN weights â€” same
    quality as automatic weights â€” then SMOOTH them across the accessory's own
    surface. `reach` (0..1) = how much smoothing/spreading: 0 keeps the crisp
    nearest-surface result, higher values diffuse weights along the mesh so a
    loose garment (skirt) spreads the lower-leg (Leg) influence up from its
    hem. Adds an armature modifier + parent. Returns error message or None.
    """
    if acc.type != 'MESH':
        return f"'{acc.name}' is not a mesh."
    if not acc.data.vertices:
        return f"'{acc.name}' has no geometry."
    if not source_mesh.vertex_groups:
        return ("Source mesh has no weights. Bind the body with Automatic "
                "Weights first, then transfer.")

    ensure_object_mode(context)
    select_only(context, [acc, arm_obj], active=arm_obj)
    try:
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    except RuntimeError as exc:
        return f"Could not parent '{acc.name}': {exc}"

    for vg in list(acc.vertex_groups):
        acc.vertex_groups.remove(vg)
    # Remove any existing armature deform so the accessory is UNDEFORMED while
    # we transfer (otherwise weights would be sampled from a posed/bent mesh).
    for m in list(acc.modifiers):
        if m.type == 'ARMATURE':
            acc.modifiers.remove(m)

    # Force EVERY involved rig to REST pose during transfer so both the source
    # body and the accessory are sampled undeformed â€” the current frame may be
    # posed. Includes the SOURCE mesh's own armature(s), which may be a
    # different rig when transferring between two characters.
    rest_arms = {arm_obj}
    for m in source_mesh.modifiers:
        if m.type == 'ARMATURE' and m.object is not None:
            rest_arms.add(m.object)
    saved_pose = {a: a.data.pose_position for a in rest_arms}
    for a in rest_arms:
        a.data.pose_position = 'REST'
    context.view_layer.update()

    error = None
    try:
        # 1) Smooth nearest-surface transfer (interpolated over the nearest face).
        select_only(context, [acc], active=acc)
        dt = acc.modifiers.new(name="MMR_WeightXfer", type='DATA_TRANSFER')
        dt.object = source_mesh
        dt.use_vert_data = True
        dt.data_types_verts = {'VGROUP_WEIGHTS'}
        dt.vert_mapping = 'POLYINTERP_NEAREST'
        try:
            bpy.ops.object.datalayout_transfer(modifier=dt.name)
            bpy.ops.object.modifier_apply(modifier=dt.name)
        except RuntimeError as exc:
            if dt.name in {m.name for m in acc.modifiers}:
                acc.modifiers.remove(dt)
            error = f"Weight transfer failed for '{acc.name}': {exc}"

        deform = {b.name for b in arm_obj.data.bones if b.use_deform}
        if error is None and not (deform & {vg.name for vg in acc.vertex_groups}):
            error = (f"No weights transferred to '{acc.name}' (is it far from "
                     "the body surface?).")

        if error is None:
            # 2) Smooth/spread along the accessory surface (topological, even).
            iters = int(round(min(max(reach, 0.0), 1.0) * 30))
            if iters > 0:
                try:
                    bpy.ops.object.vertex_group_smooth(group_select_mode='ALL',
                                                       factor=0.5, repeat=iters)
                except RuntimeError:
                    pass
            # 3) Limit to 4 influences and normalize (Unity/mobile friendly).
            for vi in range(len(acc.data.vertices)):
                limit_vertex_weights(acc, vi, 4)
                normalize_vertex_weights(acc, vi)
    finally:
        for a, pos in saved_pose.items():
            a.data.pose_position = pos
        context.view_layer.update()

    if error:
        return error

    m = acc.modifiers.new(name="Armature", type='ARMATURE')
    m.object = arm_obj
    return None


def copy_weights_same_topology(context, source_mesh, dst, arm_obj):
    """Copy weights 1:1 by vertex INDEX â€” exact, position-independent. Only for
    meshes with IDENTICAL topology (a duplicate / re-skinned variant). Adds an
    armature modifier + parent. Returns error message or None.
    """
    if dst.type != 'MESH':
        return f"'{dst.name}' is not a mesh."
    if len(source_mesh.data.vertices) != len(dst.data.vertices):
        return (f"'{dst.name}' has {len(dst.data.vertices)} vertices but the "
                f"source has {len(source_mesh.data.vertices)} â€” topology differs. "
                "Use 'Transfer Weights To Accessories' instead.")
    if not source_mesh.vertex_groups:
        return "Source mesh has no weights. Bind it first."

    ensure_object_mode(context)
    select_only(context, [dst, arm_obj], active=arm_obj)
    try:
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    except RuntimeError as exc:
        return f"Could not parent '{dst.name}': {exc}"

    for vg in list(dst.vertex_groups):
        dst.vertex_groups.remove(vg)
    src_gn = {vg.index: vg.name for vg in source_mesh.vertex_groups}
    grp = {name: dst.vertex_groups.new(name=name) for name in
           (vg.name for vg in source_mesh.vertex_groups)}
    for v in source_mesh.data.vertices:
        for g in v.groups:
            if g.weight > 0.0:
                grp[src_gn[g.group]].add([v.index], g.weight, 'REPLACE')

    if not any(m.type == 'ARMATURE' and m.object == arm_obj for m in dst.modifiers):
        m = dst.modifiers.new(name="Armature", type='ARMATURE')
        m.object = arm_obj
    return None


SKIRT_BONES = ["Hips", "Spine", "LeftUpLeg", "RightUpLeg",
               "LeftLeg", "RightLeg", "LeftFoot", "RightFoot"]


def bind_skirt(context, skirt, arm_obj, reach=0.5):
    """Weight a skirt/dress by INVERSE DISTANCE to nearby lower-body bones, so
    every vertex picks up weight from the several bones around it (both UpLeg
    AND Leg near the knee) â€” a wider 'search radius' than nearest-bone.

    `reach` (0..1) widens the falloff: 0 = tight (nearest bone dominates),
    1 = wide (more bones blend in). Adds an armature modifier + parent.
    Returns error message or None.
    """
    if skirt.type != 'MESH' or not skirt.data.vertices:
        return f"'{skirt.name}' is not a usable mesh."

    P = BONE_PREFIX
    bw = get_armature_bone_world_positions(arm_obj)
    cand = [P + n for n in SKIRT_BONES if P + n in bw]
    if not cand:
        return "Armature is missing lower-body bones (build the armature first)."

    # Lower reach -> higher power -> more localized; higher reach -> wider blend.
    power = 4.0 - 3.0 * min(max(reach, 0.0), 1.0)   # reach 0->4, 0.5->2.5, 1->1

    ensure_object_mode(context)
    select_only(context, [skirt, arm_obj], active=arm_obj)
    try:
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    except RuntimeError as exc:
        return f"Could not parent '{skirt.name}': {exc}"

    for vg in list(skirt.vertex_groups):
        skirt.vertex_groups.remove(vg)
    grp = {}

    mw = skirt.matrix_world
    for v in skirt.data.vertices:
        co = mw @ v.co
        # Inverse-distance weight to each candidate bone segment.
        ranked = []
        for n in cand:
            d, _ = point_segment_distance_and_t(co, bw[n]["head"], bw[n]["tail"])
            ranked.append((n, 1.0 / ((d + 1e-4) ** power)))
        # Keep the 4 strongest influences (Unity/mobile friendly) and normalize.
        ranked.sort(key=lambda kv: kv[1], reverse=True)
        ranked = ranked[:4]
        total = sum(w for _, w in ranked)
        if total <= 0.0:
            continue
        for n, w in ranked:
            if n not in grp:
                grp[n] = skirt.vertex_groups.new(name=n)
            grp[n].add([v.index], w / total, 'REPLACE')

    if not any(m.type == 'ARMATURE' and m.object == arm_obj for m in skirt.modifiers):
        m = skirt.modifiers.new(name="Armature", type='ARMATURE')
        m.object = arm_obj
    return None


def flip_bone_name(name):
    """Swap Left/Right in a Mixamo bone name (Blender's own name flip does not
    recognize 'Left'/'Right' inside the 'mixamorig:' prefix)."""
    if "Left" in name:
        return name.replace("Left", "Right")
    if "Right" in name:
        return name.replace("Right", "Left")
    return name


def symmetrize_weights(context, mesh_obj, from_positive=True):
    """Make the mesh's weights symmetric across the symmetry plane with the
    source side as the single source of truth:
      1. vertices ON the plane get equal weights for each Left/Right bone pair
         (the source-side bone's weight wins), so the center matches both halves,
      2. the WHOLE target side is zeroed in all groups first,
      3. each target vertex then copies the L/R-flipped weights of its mirror
         partner, searched among source-side/plane vertices only (a target
         vertex can never match a stale same-side neighbour).
    `from_positive` True: +side is the source (copied onto the -side).
    Returns error message or None.
    """
    from mathutils.kdtree import KDTree

    if not mesh_obj.vertex_groups:
        return f"'{mesh_obj.name}' has no vertex groups to symmetrize."

    ai = AXIS_INDEX[get_symmetry_axis(context)]
    center_obj = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    center = center_obj.location[ai] if center_obj is not None else CENTER_X

    mw = mesh_obj.matrix_world
    cos = [mw @ v.co for v in mesh_obj.data.vertices]
    eps = 1e-5
    src_sign = 1.0 if from_positive else -1.0

    source_idx, target_idx, plane_idx = [], [], []
    for i, co in enumerate(cos):
        side = (co[ai] - center) * src_sign
        if side > eps:
            source_idx.append(i)
        elif side < -eps:
            target_idx.append(i)
        else:
            plane_idx.append(i)
    if not source_idx and not plane_idx:
        return "No vertices on the source side to symmetrize from."

    ensure_object_mode(context)

    # Backup groups are ignored (never read, never written), as everywhere else.
    gn = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    src_w = [{gn[g.group]: g.weight for g in v.groups
              if g.weight > 0.0
              and not gn[g.group].startswith(WEIGHT_BACKUP_PREFIX)}
             for v in mesh_obj.data.vertices]

    arm_obj = next((m.object for m in mesh_obj.modifiers
                    if m.type == 'ARMATURE' and m.object is not None), None)

    def on_source_side(name):
        """True if a sided group name belongs to a bone on the source side."""
        if arm_obj is not None:
            bone = arm_obj.data.bones.get(name)
            if bone is not None:
                head = arm_obj.matrix_world @ bone.head_local
                return (head[ai] - center) * src_sign > 0.0
        # No bone to measure: Left bones sit on +X by the marker convention.
        return ("Left" in name) == (src_sign > 0.0)

    # 1) Plane vertices: give both bones of each Left/Right pair the source
    #    bone's weight, keep centre bones, rescale to the original total so the
    #    vertex deforms as strongly as before.
    for i in plane_idx:
        old = src_w[i]
        if not old:
            continue
        new = {}
        for name, w in old.items():
            fname = flip_bone_name(name)
            if fname == name:                    # centre bone (Spine, Hips...)
                new[name] = new.get(name, 0.0) + w
            elif on_source_side(name):
                new[name] = w
                new[fname] = w
        if sum(new.values()) <= 0.0:
            # Only target-side bones had weight here; split each pair evenly
            # instead of leaving the vertex weightless.
            new = {}
            for name, w in old.items():
                fname = flip_bone_name(name)
                if fname == name:
                    new[name] = new.get(name, 0.0) + w
                else:
                    new[name] = new.get(name, 0.0) + w * 0.5
                    new[fname] = new.get(fname, 0.0) + w * 0.5
        scale = sum(old.values()) / sum(new.values())
        for name in old:
            vg = mesh_obj.vertex_groups.get(name)
            if vg is not None:
                vg.remove([i])
        for name, w in new.items():
            vg = mesh_obj.vertex_groups.get(name)
            if vg is None:
                vg = mesh_obj.vertex_groups.new(name=name)
            vg.add([i], w * scale, 'REPLACE')
        src_w[i] = {n: w * scale for n, w in new.items()}

    # 2) Zero the whole target side first so nothing stale survives, even for
    #    vertices with no good mirror partner.
    if target_idx:
        for vg in mesh_obj.vertex_groups:
            if vg.name.startswith(WEIGHT_BACKUP_PREFIX):
                continue
            try:
                vg.remove(target_idx)
            except RuntimeError:
                pass

    # 3) Mirror-copy onto the target side, matching only against source/plane
    #    vertices (plane vertices were already made symmetric above).
    lookup = source_idx + plane_idx
    kd = KDTree(len(lookup))
    for i in lookup:
        kd.insert(cos[i], i)
    kd.balance()

    changed = 0
    for i in target_idx:
        mirror = cos[i].copy()
        mirror[ai] = 2.0 * center - cos[i][ai]  # reflect across the plane
        _, j, _ = kd.find(mirror)               # the mirror partner (source side)
        if j is None:
            continue
        for name, w in src_w[j].items():
            fname = flip_bone_name(name)
            vg = mesh_obj.vertex_groups.get(fname)
            if vg is None:
                vg = mesh_obj.vertex_groups.new(name=fname)
            vg.add([i], w, 'REPLACE')
        changed += 1

    if changed == 0 and not plane_idx:
        return "No vertices on the target side to symmetrize."
    return None


def zero_all_weights(mesh_obj):
    """Set every vertex's weight in every vertex group to 0 (remove all vertices
    from all groups) while KEEPING the groups, the armature modifier and the
    parent. Returns the number of groups cleared.
    """
    all_idx = list(range(len(mesh_obj.data.vertices)))
    cleared = 0
    for vg in mesh_obj.vertex_groups:
        try:
            vg.remove(all_idx)
        except RuntimeError:
            pass
        cleared += 1
    return cleared


def unbind_mesh(mesh_obj):
    """Fully unbind a mesh: remove its Armature modifier(s), unparent from any
    armature (keeping world position), and delete ALL its vertex groups.
    Returns (modifiers_removed, vertex_groups_removed).
    """
    removed_mods = 0
    for m in list(mesh_obj.modifiers):
        if m.type == 'ARMATURE':
            mesh_obj.modifiers.remove(m)
            removed_mods += 1

    # Unparent from an armature, keeping the mesh where it is in the world.
    if mesh_obj.parent is not None and mesh_obj.parent.type == 'ARMATURE':
        world = mesh_obj.matrix_world.copy()
        mesh_obj.parent = None
        mesh_obj.matrix_world = world

    removed_vgroups = len(mesh_obj.vertex_groups)
    mesh_obj.vertex_groups.clear()
    return removed_mods, removed_vgroups


def used_vertex_group_indices(mesh_obj):
    used = set()
    for v in mesh_obj.data.vertices:
        for g in v.groups:
            if g.weight > 0.0:
                used.add(g.group)
    return used


def clean_weights(context, mesh_obj, arm_obj):
    """Normalize, clean tiny weights, limit to 4 influences, drop unused groups.

    Returns (removed_group_count, error_message).
    """
    if not mesh_obj.vertex_groups:
        return 0, "Mesh has no vertex groups. Bind with automatic weights first."

    ensure_object_mode(context)
    select_only(context, [mesh_obj], active=mesh_obj)
    try:
        # BONE_DEFORM only touches groups tied to the armature's deform bones,
        # so MMR_BACKUP_ groups and unrelated user groups are left alone.
        mode = 'BONE_DEFORM' if arm_obj is not None else 'ALL'
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        bpy.ops.object.vertex_group_normalize_all(group_select_mode=mode,
                                                  lock_active=False)
        bpy.ops.object.vertex_group_clean(group_select_mode=mode,
                                          limit=0.01, keep_single=True)
        bpy.ops.object.vertex_group_limit_total(group_select_mode=mode, limit=4)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode=mode,
                                                  lock_active=False)
    except RuntimeError as exc:
        return 0, f"Weight cleanup failed: {exc}"
    finally:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

    # Remove groups with no weights, but keep deform-bone groups even if
    # currently empty so the rig mapping stays intact.
    bone_names = set()
    if arm_obj is not None:
        bone_names = {b.name for b in arm_obj.data.bones if b.use_deform}
    used = used_vertex_group_indices(mesh_obj)
    removable = [vg for vg in mesh_obj.vertex_groups
                 if vg.index not in used and vg.name not in bone_names]
    for vg in removable:
        mesh_obj.vertex_groups.remove(vg)
    return len(removable), None


# ---------------------------------------------------------------------------
# Smart weight refinement
# ---------------------------------------------------------------------------

def get_armature_bone_world_positions(arm_obj):
    """bone_name -> {head, tail, center, length} in world space."""
    mw = arm_obj.matrix_world
    result = {}
    for bone in arm_obj.data.bones:
        head = mw @ bone.head_local
        tail = mw @ bone.tail_local
        result[bone.name] = {
            "head": head,
            "tail": tail,
            "center": (head + tail) * 0.5,
            "length": (tail - head).length,
        }
    return result


def point_segment_distance_and_t(point, a, b):
    """Distance from point to segment AB, and the clamped normalized t in [0,1]."""
    ab = b - a
    ab_len_sq = ab.length_squared
    if ab_len_sq < 1e-12:
        return (point - a).length, 0.0
    t = (point - a).dot(ab) / ab_len_sq
    t = max(0.0, min(1.0, t))
    closest = a + ab * t
    return (point - closest).length, t


def chain_distance(point, chain_bones, bone_world):
    """Smallest point-to-segment distance from point to any bone in the chain."""
    best = float('inf')
    for name in chain_bones:
        info = bone_world.get(name)
        if info is None:
            continue
        d, _ = point_segment_distance_and_t(point, info["head"], info["tail"])
        if d < best:
            best = d
    return best


def _vgroup(mesh_obj, group_name):
    return mesh_obj.vertex_groups.get(group_name)


def get_vertex_group_weight(mesh_obj, group_name, vertex_index):
    vg = _vgroup(mesh_obj, group_name)
    if vg is None:
        return 0.0
    try:
        return vg.weight(vertex_index)
    except RuntimeError:
        return 0.0  # vertex not in group


def set_vertex_group_weight(mesh_obj, group_name, vertex_index, weight):
    vg = _vgroup(mesh_obj, group_name)
    if vg is None:
        vg = mesh_obj.vertex_groups.new(name=group_name)
    vg.add([vertex_index], weight, 'REPLACE')


def remove_vertex_from_group(mesh_obj, group_name, vertex_index):
    vg = _vgroup(mesh_obj, group_name)
    if vg is None:
        return
    try:
        vg.remove([vertex_index])
    except RuntimeError:
        pass


def _vertex_weights(mesh_obj, vertex_index, group_names=None):
    """Return {group_name: weight} for the vertex, EXCLUDING backup groups so
    weight edits/normalization never touch or corrupt a stored backup."""
    weights = {}
    names = group_names if group_names is not None else \
        {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    for g in mesh_obj.data.vertices[vertex_index].groups:
        name = names.get(g.group)
        if (name is not None and g.weight > 0.0
                and not name.startswith(WEIGHT_BACKUP_PREFIX)):
            weights[name] = g.weight
    return weights


def remove_small_weights(mesh_obj, vertex_index, threshold):
    for name, w in list(_vertex_weights(mesh_obj, vertex_index).items()):
        if w < threshold:
            remove_vertex_from_group(mesh_obj, name, vertex_index)


def limit_vertex_weights(mesh_obj, vertex_index, max_weights=4):
    weights = _vertex_weights(mesh_obj, vertex_index)
    if len(weights) <= max_weights:
        return
    keep = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:max_weights]
    keep_names = {k for k, _ in keep}
    for name in weights:
        if name not in keep_names:
            remove_vertex_from_group(mesh_obj, name, vertex_index)


def normalize_vertex_weights(mesh_obj, vertex_index):
    weights = _vertex_weights(mesh_obj, vertex_index)
    total = sum(weights.values())
    if total <= 1e-9:
        return
    for name, w in weights.items():
        set_vertex_group_weight(mesh_obj, group_name=name,
                                vertex_index=vertex_index, weight=w / total)


def detect_mesh_islands(mesh_obj):
    """Disconnected mesh islands via edge connectivity. Returns list of vertex-index lists."""
    mesh = mesh_obj.data
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in mesh.edges:
        union(edge.vertices[0], edge.vertices[1])

    islands = {}
    for i in range(n):
        islands.setdefault(find(i), []).append(i)
    return list(islands.values())


def smart_weight_refine(context, mesh_obj, arm_obj, profile_params,
                        cross_side, limit4, clean_threshold, joint_blend,
                        rigid_parts):
    """Refine automatic weights toward Mixamo quality. Returns (stats, error)."""
    deform_names = {b.name for b in arm_obj.data.bones if b.use_deform}
    present = [n for n in ALL_DEFORM_BONES if n in mesh_obj.vertex_groups
               and n in deform_names]
    if not present:
        return None, ("No Mixamo vertex groups found on the mesh. Bind with "
                      "Automatic Weights first.")

    ensure_object_mode(context)
    depsgraph = context.evaluated_depsgraph_get()
    bone_world = get_armature_bone_world_positions(arm_obj)

    # Symmetry axis + which side is "left".
    axis = get_symmetry_axis(context)
    ai = AXIS_INDEX[axis]
    center = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    center_value = center.location[ai] if center is not None else CENTER_X
    left_marker = find_marker("LeftWrist")
    if left_marker is not None:
        lw = marker_world_location("LeftWrist", depsgraph)
        left_sign = 1.0 if (lw[ai] - center_value) >= 0 else -1.0
    else:
        left_sign = 1.0

    mw = mesh_obj.matrix_world
    height = mesh_max_dimension(mesh_obj)
    center_band = height * 0.025
    joint_band = height * (0.04 + 0.12 * joint_blend)  # wider blend when soft

    group_names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}

    stats = {"cross_removed": 0, "region_removed": 0, "islands_rigid": 0}

    def side_allowed_bones(v_side):
        """Bones allowed for a vertex on a given side (+1 left, -1 right, 0 center)."""
        allowed = set(CENTER_BONES)
        if v_side >= 0:
            allowed |= set(LEFT_ARM_BONES) | set(LEFT_LEG_BONES)
        if v_side <= 0:
            allowed |= set(RIGHT_ARM_BONES) | set(RIGHT_LEG_BONES)
        return allowed

    # Precompute vertex world positions.
    vcos = [mw @ v.co for v in mesh_obj.data.vertices]

    # --- 5 + 6. Cross-side + region cleanup per vertex ----------------------
    for vi, co in enumerate(vcos):
        side_value = (co[ai] - center_value) * left_sign  # >0 => left, <0 => right
        near_center = abs(co[ai] - center_value) <= center_band

        weights = _vertex_weights(mesh_obj, vi, group_names)
        if not weights:
            continue

        # Which chain is this vertex nearest to?
        chain_d = {name: chain_distance(co, bones, bone_world)
                   for name, bones in CHAINS.items()}
        nearest_chain = min(chain_d, key=chain_d.get)

        # 5. Cross-side cleanup.
        if cross_side and not near_center:
            if side_value > 0:  # left vertex -> drop right-side bones
                forbidden = RIGHT_SIDE_BONES
            else:               # right vertex -> drop left-side bones
                forbidden = LEFT_SIDE_BONES
            for name in list(weights):
                if name in forbidden:
                    # Keep only meaningful shoulder/hip blend near center; else drop.
                    remove_vertex_from_group(mesh_obj, name, vi)
                    del weights[name]
                    stats["cross_removed"] += 1

        # 6. Region cleanup: drop bones from clearly-unrelated chains.
        # Keep the nearest chain + center bones; also keep the joint-partner
        # chain when the vertex sits in a shoulder/hip transition zone.
        keep_chains = {nearest_chain, "torso"}
        # Shoulder/hip blend: near an arm/leg root, keep torso already in set.
        allowed = set(CENTER_BONES)
        for cname in keep_chains:
            allowed |= set(CHAINS[cname])
        # Respect side unless near the center band.
        if not near_center:
            allowed &= side_allowed_bones(side_value)
            allowed |= set(CENTER_BONES)

        for name in list(weights):
            if name not in allowed:
                # Only remove if the bone is far from this vertex (avoid nuking
                # legitimate joint blends).
                info = bone_world.get(name)
                if info is None:
                    continue
                d, _ = point_segment_distance_and_t(co, info["head"], info["tail"])
                if d > joint_band:
                    remove_vertex_from_group(mesh_obj, name, vi)
                    del weights[name]
                    stats["region_removed"] += 1

        normalize_vertex_weights(mesh_obj, vi)

    # --- 7. Rigid small parts ------------------------------------------------
    if rigid_parts:
        islands = detect_mesh_islands(mesh_obj)
        if len(islands) > 1:
            main_island = max(islands, key=len)
            for island in islands:
                if island is main_island:
                    continue
                # Small compared to the whole mesh?
                if len(island) > max(0.15 * len(mesh_obj.data.vertices), 50):
                    continue
                # Find dominant nearest deform bone for the island center.
                icenter = Vector((0, 0, 0))
                for vi in island:
                    icenter += vcos[vi]
                icenter /= len(island)
                best_bone, best_d = None, float('inf')
                for name in present:
                    info = bone_world[name]
                    d, _ = point_segment_distance_and_t(icenter, info["head"], info["tail"])
                    if d < best_d:
                        best_d, best_bone = d, name
                if best_bone is None:
                    continue
                # Assign the island rigidly to the dominant bone.
                for vi in island:
                    for name in list(_vertex_weights(mesh_obj, vi, group_names)):
                        if name != best_bone:
                            remove_vertex_from_group(mesh_obj, name, vi)
                    set_vertex_group_weight(mesh_obj, best_bone, vi, 1.0)
                stats["islands_rigid"] += 1

    # --- 8-10. Tiny weights, limit to 4, normalize --------------------------
    for vi in range(len(mesh_obj.data.vertices)):
        remove_small_weights(mesh_obj, vi, clean_threshold)
        if limit4:
            limit_vertex_weights(mesh_obj, vi, profile_params["max_weights"])
        normalize_vertex_weights(mesh_obj, vi)

    return stats, None


# --- Weight backup / restore ------------------------------------------------

def backup_weights(mesh_obj):
    """Duplicate current deform vertex groups into MMR_BACKUP_ groups (one set)."""
    restore_names = [vg.name for vg in mesh_obj.vertex_groups
                     if not vg.name.startswith(WEIGHT_BACKUP_PREFIX)]
    # Remove any previous backup (only keep the latest).
    for vg in [vg for vg in mesh_obj.vertex_groups
               if vg.name.startswith(WEIGHT_BACKUP_PREFIX)]:
        mesh_obj.vertex_groups.remove(vg)

    group_names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    backed = 0
    for src_name in restore_names:
        dst = mesh_obj.vertex_groups.new(name=WEIGHT_BACKUP_PREFIX + src_name)
        for vi in range(len(mesh_obj.data.vertices)):
            w = get_vertex_group_weight(mesh_obj, src_name, vi)
            if w > 0.0:
                dst.add([vi], w, 'REPLACE')
        backed += 1
    return backed


def restore_weights(mesh_obj):
    """Restore weights from MMR_BACKUP_ groups. Returns restored count or -1 if none."""
    backups = [vg.name for vg in mesh_obj.vertex_groups
               if vg.name.startswith(WEIGHT_BACKUP_PREFIX)]
    if not backups:
        return -1
    for backup_name in backups:
        target_name = backup_name[len(WEIGHT_BACKUP_PREFIX):]
        target = mesh_obj.vertex_groups.get(target_name)
        if target is None:
            target = mesh_obj.vertex_groups.new(name=target_name)
        # Clear the target, then copy from backup.
        for vi in range(len(mesh_obj.data.vertices)):
            remove_vertex_from_group(mesh_obj, target_name, vi)
        for vi in range(len(mesh_obj.data.vertices)):
            w = get_vertex_group_weight(mesh_obj, backup_name, vi)
            if w > 0.0:
                target.add([vi], w, 'REPLACE')
    return len(backups)


# --- Weight diagnostics -----------------------------------------------------

def weight_diagnostics(mesh_obj, arm_obj, context):
    """Gather diagnostic stats. Returns a dict."""
    group_names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    n_verts = len(mesh_obj.data.vertices)

    zero = 0
    over4 = 0
    cross = 0
    counts = {vg.name: 0 for vg in mesh_obj.vertex_groups
              if not vg.name.startswith(WEIGHT_BACKUP_PREFIX)}

    # Side detection for cross-side counting.
    axis = get_symmetry_axis(context)
    ai = AXIS_INDEX[axis]
    center = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
    center_value = center.location[ai] if center is not None else CENTER_X
    height = mesh_max_dimension(mesh_obj)
    center_band = height * 0.025
    mw = mesh_obj.matrix_world

    for vi in range(n_verts):
        weights = _vertex_weights(mesh_obj, vi, group_names)
        for name in weights:
            counts[name] = counts.get(name, 0) + 1
        if not weights:
            zero += 1
        if len(weights) > 4:
            over4 += 1
        co = mw @ mesh_obj.data.vertices[vi].co
        if abs(co[ai] - center_value) > center_band:
            has_left = any(n in LEFT_SIDE_BONES for n in weights)
            has_right = any(n in RIGHT_SIDE_BONES for n in weights)
            if has_left and has_right:
                cross += 1

    empty_groups = [name for name, c in counts.items() if c == 0]
    top10 = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    deform_names = {b.name for b in arm_obj.data.bones if b.use_deform}
    missing_required = [n for n in ALL_DEFORM_BONES
                        if n in deform_names and n not in mesh_obj.vertex_groups]

    return {
        "n_verts": n_verts,
        "zero": zero,
        "over4": over4,
        "cross": cross,
        "empty_groups": empty_groups,
        "top10": top10,
        "missing_required": missing_required,
    }


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class MMR_OT_set_selected_mesh(bpy.types.Operator):
    bl_idname = "mmr.set_selected_mesh"
    bl_label = "Set Selected Mesh"
    bl_description = "Store the active mesh object as the rigging target"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object first.")
            return {'CANCELLED'}
        context.scene.mmr_target_mesh = obj
        self.report({'INFO'}, f"Target mesh set to '{obj.name}'.")
        return {'FINISHED'}


class MMR_OT_prepare_mesh(bpy.types.Operator):
    bl_idname = "mmr.prepare_mesh"
    bl_label = "Prepare Mesh"
    bl_description = "Apply scale and rotation on the target mesh (location is kept)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        if mesh_obj is None:
            self.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        ensure_object_mode(context)
        select_only(context, [mesh_obj], active=mesh_obj)
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        except RuntimeError as exc:
            self.report({'ERROR'}, f"Could not apply transforms: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Applied rotation and scale on '{mesh_obj.name}'.")
        return {'FINISHED'}


class MMR_OT_create_markers(bpy.types.Operator):
    bl_idname = "mmr.create_markers"
    bl_label = "Create Mixamo Markers"
    bl_description = ("Create the minimal Mixamo marker set: chin, groin, wrists, "
                      "elbows, knees. Realtime symmetry drivers are set up "
                      "automatically when Use Symmetry is on")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        ensure_object_mode(context)
        create_all_markers(context, mesh_obj)
        sym = " Realtime symmetry is ON." if context.scene.mmr_use_symmetry else ""
        if mesh_obj is None:
            self.report({'WARNING'},
                        "Markers created at default size. Set a target mesh first "
                        "to scale them to your character." + sym)
        else:
            self.report({'INFO'},
                        f"Created {len(ALL_MARKERS)} Mixamo markers scaled to "
                        f"'{mesh_obj.name}'. Move the left-side markers." + sym)
        return {'FINISHED'}


class MMR_OT_refresh_symmetry(bpy.types.Operator):
    bl_idname = "mmr.refresh_symmetry"
    bl_label = "Refresh Realtime Symmetry"
    bl_description = ("Re-create the mirror drivers on the right-side markers for "
                      "the current symmetry axis (clears old drivers first)")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.mmr_use_symmetry:
            self.report({'WARNING'}, "'Use Symmetry' is disabled. Enable it first.")
            return {'CANCELLED'}
        enabled, missing = enable_realtime_symmetry(context)
        if enabled == 0:
            self.report({'ERROR'},
                        "No marker pairs found. Create Mixamo markers first. "
                        "Missing: " + ", ".join(missing))
            return {'CANCELLED'}
        axis = get_symmetry_axis(context)
        msg = f"Realtime symmetry active on {enabled} pair(s), axis {axis}."
        if missing:
            msg += " Missing markers skipped: " + ", ".join(missing)
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)
        return {'FINISHED'}


class MMR_OT_set_center_from_mesh(bpy.types.Operator):
    bl_idname = "mmr.set_center_from_mesh"
    bl_label = "Set Symmetry Center From Selected Mesh"
    bl_description = ("Set the symmetry center's active-axis position to the "
                      "target mesh bounding-box center")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        value, error = set_symmetry_center_from_mesh(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        axis = get_symmetry_axis(context)
        self.report({'INFO'}, f"Symmetry center {axis} set to {value:.4f} "
                              "(mesh bbox center).")
        return {'FINISHED'}


class MMR_OT_snap_center_markers(bpy.types.Operator):
    bl_idname = "mmr.snap_center_markers"
    bl_label = "Snap Center Markers To Symmetry Plane"
    bl_description = ("Move Chin and Groin onto the symmetry plane along the "
                      "active axis")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        snapped = snap_center_markers_to_symmetry_plane(context)
        if not snapped:
            self.report({'WARNING'}, "No center markers found. Create Mixamo markers first.")
            return {'CANCELLED'}
        axis = get_symmetry_axis(context)
        self.report({'INFO'}, f"Snapped {', '.join(snapped)} to the {axis} plane.")
        return {'FINISHED'}


class MMR_OT_color_markers(bpy.types.Operator):
    bl_idname = "mmr.color_markers"
    bl_label = "Refresh Marker Colors"
    bl_description = "Re-apply bright colors to existing markers without moving them"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        colored = apply_marker_colors()
        if colored == 0:
            self.report({'WARNING'}, "No MMR markers found. Create Mixamo markers first.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Colored {colored} markers.")
        return {'FINISHED'}


class MMR_OT_mirror_markers(bpy.types.Operator):
    bl_idname = "mmr.mirror_markers"
    bl_label = "Mirror Left To Right"
    bl_description = ("Manual fallback: copy left wrist/elbow/knee positions to "
                      "the right side once, using the active symmetry axis. Not "
                      "needed while realtime symmetry is on")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.scene.mmr_use_symmetry and realtime_symmetry_active():
            self.report({'INFO'},
                        "Realtime symmetry is ON â€” right markers already follow "
                        "the left side automatically.")
            return {'FINISHED'}
        mirrored, missing_left, missing_right = mirror_left_to_right(context)
        if missing_left:
            self.report({'ERROR'},
                        "Missing left markers: " + ", ".join(missing_left) +
                        ". Create Mixamo markers first.")
            return {'CANCELLED'}
        if missing_right:
            self.report({'WARNING'},
                        "Missing right markers (skipped): " + ", ".join(missing_right))
        axis = get_symmetry_axis(context)
        self.report({'INFO'}, f"Mirrored {mirrored} pair(s) across the {axis} axis.")
        return {'FINISHED'}


class MMR_OT_build_armature(bpy.types.Operator):
    bl_idname = "mmr.build_armature"
    bl_label = "Build Mixamo Armature"
    bl_description = ("Estimate the full Mixamo skeleton from the markers and "
                      "mesh, then generate the armature (Skeleton LOD: No Fingers)")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # If the target mesh was already bound to a generated armature, that
        # armature is about to be replaced â€” the mesh must be re-bound after.
        mesh_obj = get_target_mesh(context)
        was_bound = bool(mesh_obj and any(
            m.type == 'ARMATURE' and m.object is not None
            and m.object.get(GENERATED_TAG) for m in mesh_obj.modifiers))

        arm_obj, error, info = build_mixamo_armature(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        context.scene.mmr_armature = arm_obj

        if was_bound:
            self.report({'WARNING'},
                        "Armature rebuilt â€” the previous bind is now stale. Click "
                        "'Bind With Automatic Weights' again so the mesh follows "
                        "the new armature.")

        # Debug: print estimated joints to the system console.
        if info:
            def fmt(v):
                return "(%.3f, %.3f, %.3f)" % (v.x, v.y, v.z)
            print("[MMR] Symmetry axis     :", info["axis"])
            print("[MMR] Character forward :", info["forward_axis"],
                  info["forward_dir"], fmt(info["forward_vec"]))
            print("[MMR] LeftShoulder      :", fmt(info["LeftShoulder"]))
            print("[MMR] RightShoulder     :", fmt(info["RightShoulder"]))
            print("[MMR] LeftHip           :", fmt(info["LeftHip"]))
            print("[MMR] RightHip          :", fmt(info["RightHip"]))
            print("[MMR] LeftFoot  head/tail:", fmt(info["LeftFootHead"]),
                  "->", fmt(info["LeftFootTail"]))
            print("[MMR] RightFoot head/tail:", fmt(info["RightFootHead"]),
                  "->", fmt(info["RightFootTail"]))
            for w in info.get("warnings", []):
                self.report({'WARNING'}, w)

        self.report({'INFO'}, f"Armature '{arm_obj.name}' created with "
                              f"{len(arm_obj.data.bones)} bones (No Fingers), "
                              f"symmetry {info['axis'] if info else '?'}, "
                              f"forward {info['forward_dir'].lower() if info else '?'} "
                              f"{info['forward_axis'] if info else '?'}.")
        return {'FINISHED'}


class MMR_OT_set_selected_armature(bpy.types.Operator):
    bl_idname = "mmr.set_selected_armature"
    bl_label = "Set Selected Armature"
    bl_description = ("Use the selected EXISTING armature as the rig target for "
                      "Bind / weight tools, instead of building a new one â€” e.g. "
                      "to reuse a previously generated rig or another character's "
                      "skeleton")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'ARMATURE':
            obj = next((o for o in context.selected_objects
                        if o.type == 'ARMATURE'), None)
        if obj is None:
            self.report({'ERROR'}, "Select an armature object first.")
            return {'CANCELLED'}

        context.scene.mmr_armature = obj

        # Sanity warnings â€” still usable, but the user should know.
        mixamo_bones = sum(1 for b in obj.data.bones
                           if b.name.startswith(BONE_PREFIX))
        if mixamo_bones == 0:
            self.report({'WARNING'},
                        f"'{obj.name}' has no 'mixamorig:' bones â€” binding works, "
                        "but Mixamo animations will not match by bone name.")
        elif not armature_in_mixamo_space(obj):
            self.report({'WARNING'},
                        f"'{obj.name}' is not in Mixamo object space (rot X=90, "
                        "scale 0.01) â€” Mixamo animations may play wrong on it.")
        self.report({'INFO'}, f"Rig target set to '{obj.name}' "
                              f"({mixamo_bones} mixamorig bones). Bind and weight "
                              "tools now use this armature.")
        return {'FINISHED'}


class MMR_OT_build_new_armature(bpy.types.Operator):
    bl_idname = "mmr.build_new_armature"
    bl_label = "Build As New Armature"
    bl_description = ("Build an ADDITIONAL armature from the current markers "
                      "with its own name, WITHOUT touching any armature already "
                      "in the file â€” for rigging several characters in one file. "
                      "The new armature becomes the target for Bind")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_obj, error, info = build_mixamo_armature(context, keep_existing=True)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        context.scene.mmr_armature = arm_obj
        if info:
            for w in info.get("warnings", []):
                self.report({'WARNING'}, w)
        self.report({'INFO'},
                    f"New armature '{arm_obj.name}' created "
                    f"({len(arm_obj.data.bones)} bones); existing armatures "
                    "untouched. Bind now targets this rig.")
        return {'FINISHED'}


class MMR_OT_flip_foot_direction(bpy.types.Operator):
    bl_idname = "mmr.flip_foot_direction"
    bl_label = "Flip Foot Direction"
    bl_description = ("Toggle Forward Direction (Positive <-> Negative) and rebuild "
                      "the armature's foot bones if an armature already exists")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.mmr_forward_dir = ('NEGATIVE' if scene.mmr_forward_dir == 'POSITIVE'
                                 else 'POSITIVE')
        new_dir = scene.mmr_forward_dir
        # Rebuild if we already have a generated armature (and markers are ready).
        if get_generated_armature(context) is not None:
            arm_obj, error, info = build_mixamo_armature(context)
            if error:
                self.report({'WARNING'},
                            f"Forward direction set to {new_dir.lower()}, but the "
                            f"armature could not be rebuilt ({error}). Rebuild manually.")
                return {'FINISHED'}
            context.scene.mmr_armature = arm_obj
            self.report({'INFO'}, f"Forward direction {new_dir.lower()}; feet now "
                                  f"point {new_dir.lower()} {scene.mmr_forward_axis}.")
            return {'FINISHED'}
        self.report({'INFO'}, f"Forward direction set to {new_dir.lower()}. "
                              "Build the armature to apply it.")
        return {'FINISHED'}


class MMR_OT_bind_auto_weights(bpy.types.Operator):
    bl_idname = "mmr.bind_auto_weights"
    bl_label = "Bind With Automatic Weights"
    bl_description = "Parent the target mesh to the generated armature with automatic weights"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        if mesh_obj is None:
            self.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        arm_obj = get_generated_armature(context)
        if arm_obj is None:
            self.report({'ERROR'}, "No generated armature found. Build the armature first.")
            return {'CANCELLED'}
        error = bind_automatic_weights(context, mesh_obj, arm_obj)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        self.report({'INFO'}, f"'{mesh_obj.name}' bound to '{arm_obj.name}' "
                              "with automatic weights.")
        return {'FINISHED'}


class MMR_OT_symmetrize_weights(bpy.types.Operator):
    bl_idname = "mmr.symmetrize_weights"
    bl_label = "Symmetrize Weights"
    bl_description = ("Make the selected mesh's weights symmetric: the target "
                      "half is zeroed first, then rebuilt from the source half "
                      "(flips Left/Right bone names); vertices on the symmetry "
                      "plane get equal Left/Right weights. Choose the source "
                      "side with 'Symmetrize From'")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context)
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            target = get_target_mesh(context)
            if target is not None:
                meshes = [target]
        if not meshes:
            self.report({'ERROR'}, "Select a mesh (or set a target mesh).")
            return {'CANCELLED'}

        from_pos = context.scene.mmr_weight_sym_dir == 'POS_NEG'
        done = []
        for mesh_obj in meshes:
            error = symmetrize_weights(context, mesh_obj, from_positive=from_pos)
            if error:
                self.report({'WARNING'}, error)
                continue
            done.append(mesh_obj.name)
        if not done:
            self.report({'ERROR'}, "No mesh was symmetrized.")
            return {'CANCELLED'}
        src = "+X" if from_pos else "-X"
        self.report({'INFO'}, f"Symmetrized weights ({src} -> other side): "
                              + ", ".join(done))
        return {'FINISHED'}


class MMR_OT_zero_weights(bpy.types.Operator):
    bl_idname = "mmr.zero_weights"
    bl_label = "Zero All Weights"
    bl_description = ("Set every vertex weight of the SELECTED mesh(es) to 0 in "
                      "all vertex groups (groups, armature modifier and parent "
                      "are kept) â€” a clean slate for manual weight painting. "
                      "Falls back to the stored target mesh if none selected")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context)
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            target = get_target_mesh(context)
            if target is not None:
                meshes = [target]
        if not meshes:
            self.report({'ERROR'}, "Select a mesh (or set a target mesh).")
            return {'CANCELLED'}

        total = 0
        names = []
        for mesh_obj in meshes:
            total += zero_all_weights(mesh_obj)
            names.append(mesh_obj.name)
        self.report({'INFO'},
                    f"Zeroed all weights on {', '.join(names)} "
                    f"({total} group(s) cleared, groups kept).")
        return {'FINISHED'}


class MMR_OT_unbind_mesh(bpy.types.Operator):
    bl_idname = "mmr.unbind_mesh"
    bl_label = "Unbind Mesh"
    bl_description = ("Unbind the SELECTED mesh(es): remove the Armature "
                      "modifier, unparent (keep position), and delete ALL vertex "
                      "groups. Falls back to the stored target mesh if none "
                      "selected")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context)
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            target = get_target_mesh(context)
            if target is not None:
                meshes = [target]
        if not meshes:
            self.report({'ERROR'}, "Select a mesh to unbind (or set a target mesh).")
            return {'CANCELLED'}

        total_mods = total_vg = 0
        names = []
        for mesh_obj in meshes:
            mods, vgs = unbind_mesh(mesh_obj)
            total_mods += mods
            total_vg += vgs
            names.append(mesh_obj.name)
        self.report({'INFO'},
                    f"Unbound {', '.join(names)}: removed {total_mods} armature "
                    f"modifier(s) and {total_vg} vertex group(s).")
        return {'FINISHED'}


class MMR_OT_bind_accessories(bpy.types.Operator):
    bl_idname = "mmr.bind_accessories"
    bl_label = "Bind Accessories (Rigid)"
    bl_description = ("Rigidly bind each SELECTED extra mesh (glasses, hat, "
                      "beard, belt...) to its nearest bone so it follows the rig "
                      "without deforming. Select the accessory meshes first")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_obj = get_generated_armature(context)
        if arm_obj is None:
            self.report({'ERROR'}, "No generated armature found. Build the armature first.")
            return {'CANCELLED'}
        target = get_target_mesh(context)
        # Accessories = selected meshes that aren't the body target or armature.
        accessories = [o for o in context.selected_objects
                       if o.type == 'MESH' and o is not target and o is not arm_obj]
        if not accessories:
            self.report({'ERROR'}, "Select the accessory mesh(es) (glasses, hat...) "
                                   "to bind. The stored body mesh is skipped.")
            return {'CANCELLED'}

        bound = []
        for acc in accessories:
            bone, error = bind_accessory_to_nearest_bone(context, acc, arm_obj)
            if error:
                self.report({'WARNING'}, error)
                continue
            bound.append(f"{acc.name}->{bone.replace(BONE_PREFIX, '')}")
        if not bound:
            self.report({'ERROR'}, "No accessories were bound.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Bound accessories: " + ", ".join(bound))
        return {'FINISHED'}


class MMR_OT_transfer_accessory_weights(bpy.types.Operator):
    bl_idname = "mmr.transfer_accessory_weights"
    bl_label = "Transfer Weights To Accessories"
    bl_description = ("Copy the body mesh's skin weights onto each SELECTED extra "
                      "mesh by nearest surface (hat, hair, cloth...), so it "
                      "deforms smoothly like the body. Bind the body first, then "
                      "select the accessories and click this")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_obj = get_generated_armature(context)
        if arm_obj is None:
            self.report({'ERROR'}, "No generated armature found. Build the armature first.")
            return {'CANCELLED'}
        source = get_target_mesh(context)
        if source is None:
            self.report({'ERROR'}, "No target (body) mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        if not source.vertex_groups:
            self.report({'ERROR'}, "Body mesh has no weights. Bind With Automatic "
                                   "Weights first.")
            return {'CANCELLED'}
        accessories = [o for o in context.selected_objects
                       if o.type == 'MESH' and o is not source and o is not arm_obj]
        if not accessories:
            self.report({'ERROR'}, "Select the accessory mesh(es) to receive weights.")
            return {'CANCELLED'}

        done = []
        for acc in accessories:
            error = transfer_weights_to_accessory(
                context, source, acc, arm_obj,
                reach=context.scene.mmr_transfer_reach)
            if error:
                self.report({'WARNING'}, error)
                continue
            done.append(acc.name)
        if not done:
            self.report({'ERROR'}, "No accessories received weights.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Transferred body weights to: {', '.join(done)}.")
        return {'FINISHED'}


class MMR_OT_copy_weights_topology(bpy.types.Operator):
    bl_idname = "mmr.copy_weights_topology"
    bl_label = "Copy Weights (Same Topology)"
    bl_description = ("Copy the body mesh's weights 1:1 by vertex index onto "
                      "each SELECTED mesh with IDENTICAL topology (a duplicate/"
                      "re-skinned variant) â€” exact, and the meshes do NOT need "
                      "to overlap in space. For different topology use Transfer")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_obj = get_generated_armature(context)
        if arm_obj is None:
            self.report({'ERROR'}, "No rig target. Build or Set Selected Armature first.")
            return {'CANCELLED'}
        source = get_target_mesh(context)
        if source is None:
            self.report({'ERROR'}, "No target (source) mesh set. Use 'Set Selected Mesh'.")
            return {'CANCELLED'}
        dsts = [o for o in context.selected_objects
                if o.type == 'MESH' and o is not source and o is not arm_obj]
        if not dsts:
            self.report({'ERROR'}, "Select the destination mesh(es) to copy onto.")
            return {'CANCELLED'}
        done = []
        for dst in dsts:
            error = copy_weights_same_topology(context, source, dst, arm_obj)
            if error:
                self.report({'WARNING'}, error)
                continue
            done.append(dst.name)
        if not done:
            self.report({'ERROR'}, "No mesh received weights.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Copied weights 1:1 to: {', '.join(done)}.")
        return {'FINISHED'}


class MMR_OT_bind_skirt(bpy.types.Operator):
    bl_idname = "mmr.bind_skirt"
    bl_label = "Bind Skirt / Dress"
    bl_description = ("Weight the SELECTED skirt/dress mesh(es) by height "
                      "(waist->Hips, thigh->UpLeg, shin->Leg) split across both "
                      "legs, so the lower skirt follows the lower leg and doesn't "
                      "penetrate the thigh. Select the skirt mesh(es) first")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_obj = get_generated_armature(context)
        if arm_obj is None:
            self.report({'ERROR'}, "No generated armature found. Build the armature first.")
            return {'CANCELLED'}
        target = get_target_mesh(context)
        skirts = [o for o in context.selected_objects
                  if o.type == 'MESH' and o is not arm_obj]
        # Don't silently re-weight the whole body if it's selected alongside.
        skirts = [o for o in skirts if o is not target] or skirts
        if not skirts:
            self.report({'ERROR'}, "Select the skirt/dress mesh(es) to bind.")
            return {'CANCELLED'}

        done = []
        for skirt in skirts:
            error = bind_skirt(context, skirt, arm_obj,
                               reach=context.scene.mmr_skirt_reach)
            if error:
                self.report({'WARNING'}, error)
                continue
            done.append(skirt.name)
        if not done:
            self.report({'ERROR'}, "No skirt was bound.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Bound skirt(s): {', '.join(done)} "
                              "(inverse-distance to nearby leg/hip bones).")
        return {'FINISHED'}


class MMR_OT_clean_weights(bpy.types.Operator):
    bl_idname = "mmr.clean_weights"
    bl_label = "Clean Weights"
    bl_description = ("Normalize weights, remove tiny influences, limit to 4 "
                      "influences per vertex, and delete unused non-bone groups")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        if mesh_obj is None:
            self.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        arm_obj = get_generated_armature(context)
        removed, error = clean_weights(context, mesh_obj, arm_obj)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        msg = "Weights normalized, cleaned and limited to 4 influences per vertex."
        if removed:
            msg += f" Removed {removed} unused vertex group(s)."
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _validate_weight_target(context, op):
    """Shared validation for weight operators. Returns (mesh, arm) or (None, None)."""
    mesh_obj = get_target_mesh(context)
    if mesh_obj is None:
        op.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
        return None, None
    arm_obj = get_generated_armature(context)
    if arm_obj is None:
        op.report({'ERROR'}, "No generated armature found. Build the armature first.")
        return None, None
    has_mod = any(m.type == 'ARMATURE' and m.object == arm_obj
                  for m in mesh_obj.modifiers)
    if not has_mod:
        op.report({'ERROR'}, "Mesh has no Armature modifier for the generated "
                             "armature. Bind with Automatic Weights first.")
        return None, None
    if not mesh_obj.vertex_groups:
        op.report({'ERROR'}, "Mesh has no vertex groups. Bind with Automatic "
                             "Weights first.")
        return None, None
    return mesh_obj, arm_obj


class MMR_OT_backup_weights(bpy.types.Operator):
    bl_idname = "mmr.backup_weights"
    bl_label = "Backup Weights"
    bl_description = ("Save the current weights into MMR_BACKUP_ vertex groups "
                      "(only the latest backup is kept)")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        if mesh_obj is None:
            self.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        if not mesh_obj.vertex_groups:
            self.report({'ERROR'}, "Mesh has no vertex groups to back up.")
            return {'CANCELLED'}
        ensure_object_mode(context)
        n = backup_weights(mesh_obj)
        self.report({'INFO'}, f"Backed up {n} vertex group(s) into "
                              f"'{WEIGHT_BACKUP_PREFIX}' groups.")
        return {'FINISHED'}


class MMR_OT_restore_weights(bpy.types.Operator):
    bl_idname = "mmr.restore_weights"
    bl_label = "Restore Weight Backup"
    bl_description = "Restore weights from the latest MMR_BACKUP_ groups"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj = get_target_mesh(context)
        if mesh_obj is None:
            self.report({'ERROR'}, "No target mesh set. Use 'Set Selected Mesh' first.")
            return {'CANCELLED'}
        ensure_object_mode(context)
        n = restore_weights(mesh_obj)
        if n < 0:
            self.report({'WARNING'}, "No weight backup found. Use 'Backup Weights' first.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Restored {n} vertex group(s) from backup.")
        return {'FINISHED'}


class MMR_OT_smart_mixamo_weight_refine(bpy.types.Operator):
    bl_idname = "mmr.smart_mixamo_weight_refine"
    bl_label = "Smart Mixamo Weight Refine"
    bl_description = ("Post-process automatic weights: remove cross-side "
                      "contamination, clean unrelated limb weights, refine small "
                      "parts, then limit to 4 and normalize")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_obj, arm_obj = _validate_weight_target(context, self)
        if mesh_obj is None:
            return {'CANCELLED'}

        scene = context.scene
        params = dict(WEIGHT_PROFILES[scene.mmr_weight_profile])
        stats, error = smart_weight_refine(
            context, mesh_obj, arm_obj, params,
            cross_side=scene.mmr_cross_side_cleanup,
            limit4=scene.mmr_limit_weights_4,
            clean_threshold=scene.mmr_clean_threshold,
            joint_blend=scene.mmr_joint_blend_strength,
            rigid_parts=scene.mmr_rigid_small_parts,
        )
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        print("[MMR] Weight refine stats:", stats)
        self.report({'INFO'},
                    f"Refined weights (profile {scene.mmr_weight_profile}): "
                    f"removed {stats['cross_removed']} cross-side, "
                    f"{stats['region_removed']} unrelated; "
                    f"{stats['islands_rigid']} rigid part(s).")
        return {'FINISHED'}


class MMR_OT_weight_diagnostics(bpy.types.Operator):
    bl_idname = "mmr.weight_diagnostics"
    bl_label = "Weight Diagnostics"
    bl_description = ("Report weight quality: zero-weight verts, >4-influence "
                      "verts, cross-side verts, empty groups, top groups")
    bl_options = {'REGISTER'}

    def execute(self, context):
        mesh_obj, arm_obj = _validate_weight_target(context, self)
        if mesh_obj is None:
            return {'CANCELLED'}
        d = weight_diagnostics(mesh_obj, arm_obj, context)
        print("=" * 56)
        print("[MMR] Weight Diagnostics for", mesh_obj.name)
        print(f"  vertices          : {d['n_verts']}")
        print(f"  zero-weight verts : {d['zero']}")
        print(f"  verts with >4 infl: {d['over4']}")
        print(f"  cross-side verts  : {d['cross']}")
        print(f"  empty groups      : {len(d['empty_groups'])} {d['empty_groups']}")
        print("  top 10 groups by vertex count:")
        for name, c in d["top10"]:
            print(f"    {c:6d}  {name}")
        if d["missing_required"]:
            print("  MISSING required Mixamo groups:", d["missing_required"])
        else:
            print("  all required Mixamo groups present")
        print("=" * 56)
        self.report({'INFO'},
                    f"Diagnostics: {d['zero']} zero-weight, {d['over4']} over-4, "
                    f"{d['cross']} cross-side verts, {len(d['empty_groups'])} empty "
                    f"groups. See System Console for details.")
        return {'FINISHED'}


class MMR_OT_remove_markers(bpy.types.Operator):
    bl_idname = "mmr.remove_markers"
    bl_label = "Remove Markers"
    bl_description = ("Delete all MMR joint markers and the symmetry center "
                      "(user objects are never touched)")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context)
        removed = remove_all_markers()
        if removed == 0:
            self.report({'WARNING'}, "No MMR markers found.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Removed {removed} marker object(s).")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI panel
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Action retargeting (old rig -> replacement rig)
# ---------------------------------------------------------------------------
# An action stores each bone's rotation RELATIVE TO ITS REST POSE, so replaying
# actions authored on one rig against a rig with a different rest offsets every
# bone by the rest difference. Blender evaluates
#     pose = pose_parent @ M @ basis      with  M = rest_parent^-1 @ rest_bone
# so writing
#     basis_new = M_new^-1 @ M_old @ basis_old
# into the F-Curves reproduces the source rig's world orientation exactly, for
# every bone at once (parents are already corrected when children evaluate).
#
# That is only meaningful while both rigs give a bone the same MEANING. When a
# limb chain is built differently the per-bone match is exact yet visually
# wrong, so RETARGET_REMAP lets a target bone be driven by a DIFFERENT source
# bone; those bones are solved in world space instead (see retarget_action).

RETARGET_DONE_TAG = "mmr_retargeted"

# Legs of an add-on rig whose hip sockets were estimated far from the groin:
# 'UpLeg' degenerates into a near-horizontal connector inside the pelvis and
# 'Leg' carries the whole limb. Mapping the target's real thigh to the source's
# 'Leg' keeps the limb pointing where the animator saw it.
LEG_REMAP = {
    BONE_PREFIX + "LeftUpLeg": BONE_PREFIX + "LeftLeg",
    BONE_PREFIX + "RightUpLeg": BONE_PREFIX + "RightLeg",
    BONE_PREFIX + "LeftLeg": None,     # source has no knee joint to transfer
    BONE_PREFIX + "RightLeg": None,
}


def bone_of_path(data_path):
    """'pose.bones["x"].rotation_quaternion' -> 'x' (None if not a bone path)."""
    if not data_path.startswith('pose.bones["'):
        return None
    end = data_path.find('"]', 12)
    return data_path[12:end] if end != -1 else None


def action_channel_containers(action):
    """Every F-Curve container of an action (one per slot on Blender 4.4+)."""
    containers = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            if getattr(strip, "type", "KEYFRAME") != 'KEYFRAME':
                continue
            for slot in action.slots:
                try:
                    bag = strip.channelbag(slot)
                except Exception:
                    bag = None
                if bag is not None:
                    containers.append(bag)
    return containers or [action]


def rest_relative_rotation(arm_obj, bone):
    """Rest transform of `bone` relative to its parent, as a rotation.

    The object matrix is included so a root bone is still compared in world
    space; it cancels out for every non-root bone.
    """
    world = arm_obj.matrix_world @ bone.matrix_local
    if bone.parent is not None:
        world = (arm_obj.matrix_world @ bone.parent.matrix_local).inverted() @ world
    return world.to_quaternion().normalized()


def rest_world_rotation(arm_obj, bone):
    return (arm_obj.matrix_world @ bone.matrix_local).to_quaternion().normalized()


def bone_hierarchy_order(arm_obj):
    """Bone names, parents always before their children."""
    order = []

    def walk(bone):
        order.append(bone.name)
        for child in bone.children:
            walk(child)

    for bone in arm_obj.data.bones:
        if bone.parent is None:
            walk(bone)
    return order


def retarget_hips_location_factor(src, dst):
    """Scale for the root translation channel: hip-height ratio, undoing the two
    armature objects' own scales (both are cm rigs at 0.01 normally).

    Hip height is only a PROXY for character size. When two rigs disagree about
    where the hip sits on the same body - a groin marker placed higher in the
    Mixamo rigger, say - this over- or under-scales the root motion and the feet
    slide. Compare the meshes' heights; if they match, override the factor with
    1.0 via `mmr_retarget_root_scale`.
    """
    def hips_height(arm):
        bone = arm.data.bones.get(BONE_PREFIX + "Hips")
        if bone is None:
            roots = [b for b in arm.data.bones if b.parent is None]
            if not roots:
                return 0.0
            bone = roots[0]
        return (arm.matrix_world @ bone.head_local).z

    def obj_scale(arm):
        s = arm.matrix_world.to_scale()
        return (abs(s.x) + abs(s.y) + abs(s.z)) / 3.0

    h_old, h_new = hips_height(src), hips_height(dst)
    s_old, s_new = obj_scale(src), obj_scale(dst)
    if abs(h_old) < 1e-9 or s_new < 1e-12:
        return 1.0
    return (h_new / h_old) * (s_old / s_new)


def retarget_rest_report(src, dst, remap=None):
    """(rows, worst) where rows is [(degrees, bone, source_bone)] descending.

    `worst` counts only same-name bones: those keep their source's world
    orientation verbatim, so their rest gap IS the error being cancelled. A
    remapped bone is solved in world space against a constant that absorbs the
    rest relationship, so its (usually huge) gap is not an error - it is
    reported for information and excluded from `worst`.
    """
    remap = remap or {}
    rows = []
    worst = 0.0
    for bone in dst.data.bones:
        source_name = remap.get(bone.name, bone.name)
        if source_name is None or source_name not in src.data.bones:
            continue
        delta = (rest_relative_rotation(dst, bone).inverted()
                 @ rest_relative_rotation(src, src.data.bones[source_name]))
        degrees = math.degrees(abs(delta.angle))
        if degrees > 180.0:
            degrees = 360.0 - degrees
        rows.append((degrees, bone.name, source_name))
        if source_name == bone.name:
            worst = max(worst, degrees)
    rows.sort(reverse=True)
    return rows, worst


def _aligned_channels(container, data_path, count, defaults, group_name):
    """Return the `count` F-Curves of `data_path`, all keyed at the same times.

    Missing channels are created and missing keys sampled from the existing
    curves, so values can then be edited in place - which preserves each key's
    interpolation and hand-tuned handles.
    Returns (list_of_(fcurve, keys_in_time_order), times) or (None, None).
    """
    curves = {}
    for fcurve in container.fcurves:
        if fcurve.data_path == data_path and 0 <= fcurve.array_index < count:
            curves[fcurve.array_index] = fcurve
    if not curves:
        return None, None

    times = sorted({round(k.co.x, 5)
                    for fc in curves.values() for k in fc.keyframe_points})
    if not times:
        return None, None

    for index in range(count):
        fcurve = curves.get(index)
        if fcurve is None:
            try:
                fcurve = container.fcurves.new(data_path, index=index,
                                               action_group=group_name)
            except (TypeError, RuntimeError):
                fcurve = container.fcurves.new(data_path, index=index)
            for time in times:
                fcurve.keyframe_points.insert(time, defaults[index],
                                              options={'FAST'})
            curves[index] = fcurve
        else:
            present = {round(k.co.x, 5) for k in fcurve.keyframe_points}
            for time in times:
                if time not in present:
                    fcurve.keyframe_points.insert(time, fcurve.evaluate(time),
                                                  options={'FAST'})
        curves[index].update()

    ordered = []
    for index in range(count):
        fcurve = curves[index]
        by_time = {round(k.co.x, 5): k for k in fcurve.keyframe_points}
        ordered.append((fcurve, [by_time[t] for t in times]))
    return ordered, times


def _move_key(keyframe, value):
    """Set a key's value, dragging its handles along so the easing survives."""
    delta = value - keyframe.co.y
    if abs(delta) < 1e-12:
        return
    keyframe.co.y = value
    keyframe.handle_left.y += delta
    keyframe.handle_right.y += delta


def _source_world_rotations(src, src_order, src_curves, time):
    """World rotation of every source bone at `time`, straight from the curves
    (no depsgraph, so this never touches the scene or the current frame)."""
    world = {}
    for name in src_order:
        bone = src.data.bones[name]
        parent = world[bone.parent.name] if bone.parent else Quaternion()
        chans = src_curves.get(name)
        local = (Quaternion([chans[i].evaluate(time) for i in range(4)]).normalized()
                 if chans and len(chans) == 4 else Quaternion())
        world[name] = parent @ rest_relative_rotation(src, bone) @ local
    return world


def _retarget_same_name_bones(container, dst, deltas, loc_factor, changed):
    """Pass 1: bones present under the same name on both rigs.

    A constant per-bone delta is enough here, because the parent chain is the
    same shape on both rigs and every parent is corrected too.
    """
    for name, delta in deltas.items():
        prefix = 'pose.bones["%s"].' % name

        curves, times = _aligned_channels(
            container, prefix + "rotation_quaternion", 4,
            (1.0, 0.0, 0.0, 0.0), name)
        if curves:
            previous = None
            for i in range(len(times)):
                quat = delta @ Quaternion([curves[c][1][i].co.y for c in range(4)])
                quat.normalize()
                if previous is not None:
                    quat.make_compatible(previous)
                previous = quat
                for c in range(4):
                    _move_key(curves[c][1][i], quat[c])
            for fcurve, _keys in curves:
                fcurve.update()
            changed.add(name)

        curves, times = _aligned_channels(
            container, prefix + "rotation_euler", 3, (0.0, 0.0, 0.0), name)
        if curves:
            mode = dst.pose.bones[name].rotation_mode
            if mode in {'QUATERNION', 'AXIS_ANGLE'}:
                mode = 'XYZ'
            previous = None
            for i in range(len(times)):
                euler = Euler([curves[c][1][i].co.y for c in range(3)], mode)
                reference = previous if previous is not None else euler
                result = (delta @ euler.to_quaternion()).to_euler(mode, reference)
                previous = result
                for c in range(3):
                    _move_key(curves[c][1][i], result[c])
            for fcurve, _keys in curves:
                fcurve.update()
            changed.add(name)

        curves, times = _aligned_channels(
            container, prefix + "location", 3, (0.0, 0.0, 0.0), name)
        if curves:
            for i in range(len(times)):
                vec = (delta @ Vector([curves[c][1][i].co.y
                                       for c in range(3)])) * loc_factor
                for c in range(3):
                    _move_key(curves[c][1][i], vec[c])
            for fcurve, _keys in curves:
                fcurve.update()
            changed.add(name)


def _retarget_remapped_bones(container, src, dst, remap, corrections, deltas,
                             src_curves, src_order, dst_order, changed):
    """Pass 2: bones driven by a DIFFERENT source bone.

    A constant delta cannot express this, because the source bone sits
    elsewhere in the chain. Each key time is solved in world space instead:
    walk the target hierarchy, place the bone so its world rotation equals the
    source bone's world rotation (times the constant that preserves their rest
    relationship), then store the local rotation that produces it.
    """
    targets = {}
    for name in dst_order:
        if name not in remap:
            continue
        curves, times = _aligned_channels(
            container, 'pose.bones["%s"].rotation_quaternion' % name, 4,
            (1.0, 0.0, 0.0, 0.0), name)
        if curves:
            targets[name] = (curves, times)
    if not targets:
        return

    previous = {}
    for time in sorted({t for _curves, times in targets.values() for t in times}):
        src_world = _source_world_rotations(src, src_order, src_curves, time)
        dst_world = {}
        for name in dst_order:
            bone = dst.data.bones[name]
            parent = dst_world[bone.parent.name] if bone.parent else Quaternion()
            base = parent @ rest_relative_rotation(dst, bone)
            if name in remap:
                source = remap[name]
                if source is None or source not in src_world:
                    local = Quaternion()                  # hold this bone at rest
                else:
                    local = base.inverted() @ (src_world[source] @ corrections[name])
                local.normalize()
                if name in previous:
                    local.make_compatible(previous[name])
                previous[name] = local
                curves, times = targets.get(name, (None, None))
                if curves is not None and time in times:
                    i = times.index(time)
                    for c in range(4):
                        _move_key(curves[c][1][i], local[c])
                changed.add(name)
            else:
                # The chain being built is the TARGET's, so this ancestor needs
                # its post-pass-1 value: delta @ source rotation. Deriving it
                # keeps pass 2 independent of whether pass 1 has run yet.
                chans = src_curves.get(name)
                q_src = (Quaternion([chans[i].evaluate(time)
                                     for i in range(4)]).normalized()
                         if chans and len(chans) == 4 else Quaternion())
                delta = deltas.get(name)
                local = (delta @ q_src) if delta is not None else Quaternion()
                local.normalize()
            dst_world[name] = base @ local

    for curves, _times in targets.values():
        for fcurve, _keys in curves:
            fcurve.update()


def retarget_action(action, src, dst, remap=None, loc_factor=1.0):
    """Rewrite `action` in place so it plays on `dst` the way it played on `src`.

    Bones that exist under the same name on both rigs get the constant rest
    delta; bones listed in `remap` are solved in world space against a
    different source bone. Returns the number of bones changed.
    """
    remap = remap or {}
    dst_order = bone_hierarchy_order(dst)
    src_order = bone_hierarchy_order(src)

    deltas = {}
    for bone in dst.data.bones:
        if bone.name in remap:
            continue
        source = src.data.bones.get(bone.name)
        if source is not None:
            deltas[bone.name] = (rest_relative_rotation(dst, bone).inverted()
                                 @ rest_relative_rotation(src, source))

    # Constant that preserves each remapped pair's rest relationship.
    corrections = {}
    for target, source in remap.items():
        if source is None or target not in dst.data.bones \
                or source not in src.data.bones:
            continue
        corrections[target] = (
            rest_world_rotation(src, src.data.bones[source]).inverted()
            @ rest_world_rotation(dst, dst.data.bones[target]))

    # Pass 2 walks the SOURCE rig's chain, so snapshot the curves now - pass 1
    # is about to rewrite the originals in place.
    pristine = action.copy() if remap else None
    src_curves = {}
    if pristine is not None:
        pristine.use_fake_user = False
        for bag in action_channel_containers(pristine):
            for fcurve in bag.fcurves:
                name = bone_of_path(fcurve.data_path)
                if name and fcurve.data_path.endswith("rotation_quaternion"):
                    src_curves.setdefault(name, {})[fcurve.array_index] = fcurve

    changed = set()
    try:
        for container in action_channel_containers(action):
            _retarget_same_name_bones(container, dst, deltas, loc_factor, changed)
            if remap:
                _retarget_remapped_bones(container, src, dst, remap, corrections,
                                         deltas, src_curves, src_order,
                                         dst_order, changed)
    finally:
        if pristine is not None:
            bpy.data.actions.remove(pristine, do_unlink=True)

    action[RETARGET_DONE_TAG] = True
    return len(changed)


def retarget_actions(context, src, dst, use_remap, in_place, only_used,
                     root_scale=0.0):
    """Retarget every pose-bone action. Returns (converted, skipped, report).

    root_scale 0 means "derive it from the hip heights"; any other value is used
    verbatim (1.0 when both rigs are the same character at the same scale).
    """
    remap = LEG_REMAP if use_remap else None
    loc_factor = (root_scale if root_scale > 0.0
                  else retarget_hips_location_factor(src, dst))

    wanted = []
    for action in bpy.data.actions:
        if only_used and action.users == 0:
            continue
        if any(bone_of_path(fc.data_path)
               for container in action_channel_containers(action)
               for fc in container.fcurves):
            wanted.append(action)

    converted = skipped = 0
    for action in wanted:
        if action.get(RETARGET_DONE_TAG):
            skipped += 1
            continue
        target = action
        if not in_place:
            target = action.copy()
            target.name = action.name + "_retarget"
            target.use_fake_user = True
        count = retarget_action(target, src, dst, remap, loc_factor)
        converted += 1
        print("[MMR] retargeted '%s' (%d bones)" % (target.name, count))

    rows, worst = retarget_rest_report(src, dst, remap)
    return converted, skipped, (rows, worst, loc_factor)


class MMR_OT_retarget_report(bpy.types.Operator):
    """Print how far the two rigs' rest poses differ, without changing anything.

    Run this first: it is the size of the error each action currently suffers
    """
    bl_idname = "mmr.retarget_report"
    bl_label = "Check Rest Difference"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        src = scene.mmr_retarget_source
        dst = scene.mmr_retarget_target or get_generated_armature(context)
        if src is None or dst is None:
            self.report({'ERROR'}, "Set both the Source and Target armature.")
            return {'CANCELLED'}
        if src is dst:
            self.report({'ERROR'}, "Source and Target are the same armature.")
            return {'CANCELLED'}

        remap = LEG_REMAP if scene.mmr_retarget_leg_remap else None
        rows, worst = retarget_rest_report(src, dst, remap)
        if not rows:
            self.report({'ERROR'}, "The two rigs share no bone names.")
            return {'CANCELLED'}

        print("\n[MMR] rest difference  %s -> %s" % (src.name, dst.name))
        print("[MMR] location factor %.4f"
              % retarget_hips_location_factor(src, dst))
        for degrees, name, source in rows:
            note = "  <-- large" if degrees > 20.0 else ""
            via = "" if source == name else ("   (from %s)" % source)
            print("[MMR]   %-30s %6.2f deg%s%s" % (name, degrees, via, note))

        missing = [b.name for b in dst.data.bones if b.name not in src.data.bones]
        if missing:
            print("[MMR] only on the target rig (left at rest): %s"
                  % ", ".join(missing))
        self.report({'INFO'},
                    "Worst rest difference %.1f deg on %s - see System Console"
                    % (worst, rows[0][1]))
        return {'FINISHED'}


class MMR_OT_retarget_actions(bpy.types.Operator):
    """Rewrite every action so it plays on the Target rig the way it played on
    the Source rig. SAVE YOUR FILE FIRST when 'Rewrite In Place' is on
    """
    bl_idname = "mmr.retarget_actions"
    bl_label = "Retarget Actions To Target Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        src = scene.mmr_retarget_source
        dst = scene.mmr_retarget_target or get_generated_armature(context)
        if src is None or dst is None:
            self.report({'ERROR'}, "Set both the Source and Target armature.")
            return {'CANCELLED'}
        if src is dst:
            self.report({'ERROR'}, "Source and Target are the same armature.")
            return {'CANCELLED'}

        ensure_object_mode(context)
        converted, skipped, (rows, worst, factor) = retarget_actions(
            context, src, dst,
            scene.mmr_retarget_leg_remap,
            scene.mmr_retarget_in_place,
            scene.mmr_retarget_only_used,
            scene.mmr_retarget_root_scale)

        if converted == 0:
            self.report({'WARNING'},
                        "Nothing to do (%d action(s) already retargeted)." % skipped)
            return {'CANCELLED'}
        self.report({'INFO'},
                    "Retargeted %d action(s), skipped %d. Worst rest gap was "
                    "%.1f deg; location factor %.3f."
                    % (converted, skipped, worst, factor))
        return {'FINISHED'}


class MMR_PT_main_panel(bpy.types.Panel):
    bl_label = "Mixamo Marker Rigger"
    bl_idname = "MMR_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Mixamo Rigger"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        mesh_obj = get_target_mesh(context)
        arm_obj = get_generated_armature(context)
        missing = missing_marker_joints()
        sym_active = scene.mmr_use_symmetry and realtime_symmetry_active()

        # Status
        box = layout.box()
        box.label(text="Status", icon='INFO')
        box.label(text=f"Mesh: {mesh_obj.name if mesh_obj else '-'}",
                  icon='MESH_DATA' if mesh_obj else 'ERROR')
        box.label(text=f"Armature: {arm_obj.name if arm_obj else '-'}",
                  icon='ARMATURE_DATA' if arm_obj else 'ERROR')
        placed = len(ALL_MARKERS) - len(missing)
        box.label(text=f"Markers: {placed} / {len(ALL_MARKERS)}",
                  icon='EMPTY_DATA' if not missing else 'ERROR')
        box.label(text=f"Realtime Symmetry: {'ON' if sym_active else 'OFF'}"
                       f" (axis {scene.mmr_symmetry_axis})",
                  icon='MOD_MIRROR' if sym_active else 'X')

        # Warnings
        if mesh_obj is None:
            box.label(text="Select a mesh, then 'Set Selected Mesh'.", icon='ERROR')
        elif missing and placed > 0:
            box.label(text="Some markers are missing. Recreate them.", icon='ERROR')
        elif missing:
            box.label(text="No markers yet. Create Mixamo markers.", icon='ERROR')
        elif arm_obj is None:
            box.label(text="Markers ready. Build the armature.", icon='CHECKMARK')

        # Mixamo-space guard: applying/zeroing the transform breaks animations.
        if arm_obj is not None and not armature_in_mixamo_space(arm_obj):
            warn = box.column(align=True)
            warn.label(text="Armature transform changed!", icon='ERROR')
            warn.label(text="Keep rot X=90, scale 0.01 for Mixamo anims.")
            warn.label(text="Do NOT Apply rotation/scale. Rebuild armature.")

        # Workflow
        col = layout.column(align=True)
        col.label(text="1. Mesh")
        col.operator("mmr.set_selected_mesh", icon='RESTRICT_SELECT_OFF')
        col.operator("mmr.prepare_mesh", icon='CON_SIZELIKE')

        col = layout.column(align=True)
        col.label(text="2. Markers")
        col.operator("mmr.create_markers", icon='EMPTY_DATA')

        # Symmetry sub-section
        sbox = layout.box()
        sbox.label(text="Symmetry", icon='MOD_MIRROR')
        sbox.prop(scene, "mmr_use_symmetry")
        row = sbox.row()
        row.enabled = scene.mmr_use_symmetry
        row.prop(scene, "mmr_symmetry_axis", expand=True)
        center = bpy.data.objects.get(SYMMETRY_CENTER_NAME)
        if center is not None:
            sbox.prop(center, "location", text="Center")
        else:
            sbox.label(text="Center: created with markers", icon='INFO')
        colc = sbox.column(align=True)
        colc.enabled = scene.mmr_use_symmetry
        colc.operator("mmr.refresh_symmetry", icon='FILE_REFRESH')
        colc.operator("mmr.set_center_from_mesh", icon='PIVOT_BOUNDBOX')
        colc.operator("mmr.snap_center_markers", icon='SNAP_ON')
        row = sbox.row(align=True)
        row.enabled = not sym_active
        row.operator("mmr.mirror_markers", icon='ARROW_LEFTRIGHT')
        sbox.operator("mmr.color_markers", icon='COLOR')

        col = layout.column(align=True)
        col.label(text="3. Rig")
        col.prop(scene, "mmr_skeleton_lod")

        # Character orientation. Up is locked to world Z (character stands
        # upright in Blender); only the foot-forward direction is configurable.
        fbox = layout.box()
        fbox.label(text="Orientation (Up = world Z)", icon='ORIENTATION_GIMBAL')
        row = fbox.row(align=True)
        row.label(text="Forward")
        row.prop(scene, "mmr_forward_axis", expand=True)
        row = fbox.row()
        row.prop(scene, "mmr_forward_dir", expand=True)
        fbox.operator("mmr.flip_foot_direction", icon='ARROW_LEFTRIGHT')

        col = layout.column(align=True)
        col.operator("mmr.build_armature", icon='ARMATURE_DATA')
        col.operator("mmr.build_new_armature", icon='OUTLINER_OB_ARMATURE')
        col.operator("mmr.set_selected_armature", icon='RESTRICT_SELECT_OFF')

        # Weight tools
        wbox = layout.box()
        wbox.label(text="Weight Tools", icon='MOD_VERTEX_WEIGHT')
        wbox.operator("mmr.bind_auto_weights", icon='MOD_VERTEX_WEIGHT')
        wbox.operator("mmr.bind_accessories", icon='LINKED')
        wbox.prop(scene, "mmr_transfer_reach")
        wbox.operator("mmr.transfer_accessory_weights", icon='MOD_DATA_TRANSFER')
        wbox.operator("mmr.copy_weights_topology", icon='DUPLICATE')
        wbox.prop(scene, "mmr_skirt_reach")
        wbox.operator("mmr.bind_skirt", icon='MOD_CLOTH')
        row = wbox.row(align=True)
        row.prop(scene, "mmr_weight_sym_dir", expand=True)
        wbox.operator("mmr.symmetrize_weights", icon='MOD_MIRROR')
        wbox.operator("mmr.zero_weights", icon='X')
        wbox.operator("mmr.unbind_mesh", icon='UNLINKED')
        wbox.operator("mmr.clean_weights", icon='BRUSH_DATA')
        # --- Smart Mixamo Weight Refine (staged/hidden â€” flip to re-enable) --
        if SHOW_SMART_REFINE:
            row = wbox.row(align=True)
            row.operator("mmr.backup_weights", icon='FILE_TICK')
            row.operator("mmr.restore_weights", icon='FILE_REFRESH')
            wbox.separator()
            wbox.prop(scene, "mmr_weight_profile")
            wbox.prop(scene, "mmr_cross_side_cleanup")
            wbox.prop(scene, "mmr_limit_weights_4")
            wbox.prop(scene, "mmr_rigid_small_parts")
            wbox.prop(scene, "mmr_clean_threshold")
            wbox.prop(scene, "mmr_joint_blend_strength")
            wbox.operator("mmr.smart_mixamo_weight_refine", icon='SHADERFX')
            wbox.operator("mmr.weight_diagnostics", icon='INFO')

        # Retarget existing actions onto a replacement rig
        rbox = layout.box()
        rbox.label(text="Retarget Actions", icon='ANIM')
        rbox.prop(scene, "mmr_retarget_source", text="From (old rig)")
        rbox.prop(scene, "mmr_retarget_target", text="To (new rig)")
        rsrc = scene.mmr_retarget_source
        rdst = scene.mmr_retarget_target or arm_obj
        if rsrc is not None and rdst is not None and rsrc is not rdst:
            remap = LEG_REMAP if scene.mmr_retarget_leg_remap else None
            _rows, worst = retarget_rest_report(rsrc, rdst, remap)
            rbox.label(text="Worst rest gap: %.1f deg" % worst,
                       icon='CHECKMARK' if worst < 20.0 else 'ERROR')
            if worst >= 45.0:
                warn = rbox.column(align=True)
                warn.label(text="Chains differ structurally.", icon='ERROR')
                warn.label(text="Rotations will match but limb")
                warn.label(text="shapes may still look wrong.")
        rbox.operator("mmr.retarget_report", icon='INFO')
        if rsrc is not None and rdst is not None and rsrc is not rdst:
            auto = retarget_hips_location_factor(rsrc, rdst)
            rbox.label(text="Root motion auto factor: %.3f" % auto,
                       icon='CON_LOCLIKE')
            if abs(auto - 1.0) > 0.05:
                hint = rbox.column(align=True)
                hint.label(text="Hip heights differ. If both rigs are")
                hint.label(text="the same character, set Root Motion")
                hint.label(text="Scale to 1.0 or the feet will slide.")
        rbox.prop(scene, "mmr_retarget_root_scale")
        rbox.prop(scene, "mmr_retarget_leg_remap")
        rbox.prop(scene, "mmr_retarget_only_used")
        rbox.prop(scene, "mmr_retarget_in_place")
        if scene.mmr_retarget_in_place:
            rbox.label(text="Save the .blend first!", icon='ERROR')
        rbox.operator("mmr.retarget_actions", icon='CON_ROTLIKE')

        col = layout.column(align=True)
        col.label(text="Cleanup")
        col.operator("mmr.remove_markers", icon='TRASH')


# ---------------------------------------------------------------------------
# Register / unregister
# ---------------------------------------------------------------------------

CLASSES = (
    MMR_OT_set_selected_mesh,
    MMR_OT_prepare_mesh,
    MMR_OT_create_markers,
    MMR_OT_refresh_symmetry,
    MMR_OT_set_center_from_mesh,
    MMR_OT_snap_center_markers,
    MMR_OT_color_markers,
    MMR_OT_mirror_markers,
    MMR_OT_build_armature,
    MMR_OT_build_new_armature,
    MMR_OT_set_selected_armature,
    MMR_OT_flip_foot_direction,
    MMR_OT_bind_auto_weights,
    MMR_OT_symmetrize_weights,
    MMR_OT_zero_weights,
    MMR_OT_unbind_mesh,
    MMR_OT_bind_accessories,
    MMR_OT_transfer_accessory_weights,
    MMR_OT_copy_weights_topology,
    MMR_OT_bind_skirt,
    MMR_OT_clean_weights,
    MMR_OT_backup_weights,
    MMR_OT_restore_weights,
    MMR_OT_smart_mixamo_weight_refine,
    MMR_OT_weight_diagnostics,
    MMR_OT_retarget_report,
    MMR_OT_retarget_actions,
    MMR_OT_remove_markers,
    MMR_PT_main_panel,
)


def _poll_mesh(self, obj):
    return obj.type == 'MESH'


def _poll_armature(self, obj):
    return obj.type == 'ARMATURE'


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mmr_target_mesh = bpy.props.PointerProperty(
        name="Target Mesh", type=bpy.types.Object, poll=_poll_mesh)
    bpy.types.Scene.mmr_armature = bpy.props.PointerProperty(
        name="Generated Armature", type=bpy.types.Object, poll=_poll_armature)
    bpy.types.Scene.mmr_use_symmetry = bpy.props.BoolProperty(
        name="Use Symmetry",
        description="Right-side markers follow the left side in realtime via drivers",
        default=True,
        update=_symmetry_toggled)
    bpy.types.Scene.mmr_symmetry_axis = bpy.props.EnumProperty(
        name="Symmetry Axis",
        description="Axis that gets mirrored/inverted; the other two are copied",
        items=[
            ('X', "X", "Mirror across the X axis (left/right along X)"),
            ('Y', "Y", "Mirror across the Y axis (left/right along Y)"),
            ('Z', "Z", "Mirror across the Z axis (left/right along Z)"),
        ],
        default='X',
        update=_symmetry_axis_changed)
    bpy.types.Scene.mmr_skeleton_lod = bpy.props.EnumProperty(
        name="Skeleton LOD",
        description="Level of detail of the generated skeleton",
        items=[('NO_FINGERS', "No Fingers", "Body bones only, no finger bones")],
        default='NO_FINGERS')
    bpy.types.Scene.mmr_forward_axis = bpy.props.EnumProperty(
        name="Character Forward Axis",
        description="World axis the toes/feet point along (independent of "
                    "symmetry axis). Mixamo characters face -Y in Blender",
        items=[
            ('X', "X", "Feet point along the X axis"),
            ('Y', "Y", "Feet point along the Y axis"),
            ('Z', "Z", "Feet point along the Z axis"),
        ],
        default='Y')
    bpy.types.Scene.mmr_forward_dir = bpy.props.EnumProperty(
        name="Forward Direction",
        description="Sign of the forward axis the feet point toward",
        items=[
            ('POSITIVE', "Positive", "Feet point toward the positive axis direction"),
            ('NEGATIVE', "Negative", "Feet point toward the negative axis direction"),
        ],
        default='NEGATIVE')
    bpy.types.Scene.mmr_weight_profile = bpy.props.EnumProperty(
        name="Weight Profile",
        description="Preset controlling how aggressively weights are refined",
        items=[
            ('BALANCED', "Balanced", "Good default; smooth joints, removes obvious errors"),
            ('SOFT_ORGANIC', "Soft Organic", "More smoothing, wider joint blending"),
            ('RIGID_GAME', "Rigid Game Model", "Aggressive cleanup; rigid small parts"),
        ],
        default='BALANCED')
    bpy.types.Scene.mmr_cross_side_cleanup = bpy.props.BoolProperty(
        name="Cross Side Cleanup",
        description="Remove opposite-side (left/right) bone weights",
        default=True)
    bpy.types.Scene.mmr_limit_weights_4 = bpy.props.BoolProperty(
        name="Limit Weights To 4",
        description="Limit total influences per vertex to 4 (Unity/mobile)",
        default=True)
    bpy.types.Scene.mmr_clean_threshold = bpy.props.FloatProperty(
        name="Clean Threshold",
        description="Weights below this value are removed",
        default=0.005, min=0.0, max=0.5, precision=4, step=0.1)
    bpy.types.Scene.mmr_joint_blend_strength = bpy.props.FloatProperty(
        name="Joint Blend Strength",
        description="How wide the joint blending zone is kept (higher = softer)",
        default=0.35, min=0.0, max=1.0)
    bpy.types.Scene.mmr_skirt_reach = bpy.props.FloatProperty(
        name="Skirt Bone Reach",
        description="How wide the skirt searches for bones: low = nearest bone "
                    "dominates, high = more bones (Hips/UpLeg/Leg) blend in",
        default=0.5, min=0.0, max=1.0)
    bpy.types.Scene.mmr_weight_sym_dir = bpy.props.EnumProperty(
        name="Symmetrize From",
        description="Which side's weights are the source when symmetrizing",
        items=[
            ('POS_NEG', "+X to -X", "Copy the +X half onto the -X half"),
            ('NEG_POS', "-X to +X", "Copy the -X half onto the +X half"),
        ],
        default='POS_NEG')
    bpy.types.Scene.mmr_transfer_reach = bpy.props.FloatProperty(
        name="Transfer Reach",
        description="How much Transfer Weights smooths/spreads the copied weights "
                    "along the mesh: 0 = crisp nearest-surface (hat, glove), "
                    "higher = smoother and spreads a loose garment's hem "
                    "influence up (skirt picks up the Leg bone)",
        default=0.15, min=0.0, max=1.0)
    bpy.types.Scene.mmr_rigid_small_parts = bpy.props.BoolProperty(
        name="Rigid Small Parts",
        description="Assign small disconnected islands (armor, helmet, boots) "
                    "rigidly to the nearest bone",
        default=True)
    bpy.types.Scene.mmr_retarget_source = bpy.props.PointerProperty(
        name="Retarget Source",
        description="The rig the existing actions were authored on (usually "
                    "the add-on's own MMR_Mixamo_Armature)",
        type=bpy.types.Object, poll=_poll_armature)
    bpy.types.Scene.mmr_retarget_target = bpy.props.PointerProperty(
        name="Retarget Target",
        description="The replacement rig the actions must play on. Defaults to "
                    "the rig selected in the Status box",
        type=bpy.types.Object, poll=_poll_armature)
    bpy.types.Scene.mmr_retarget_leg_remap = bpy.props.BoolProperty(
        name="Fix Leg Chain",
        description="Drive the target's thigh from the source's 'Leg' bone. "
                    "Use when the source rig's 'UpLeg' is a near-horizontal "
                    "connector inside the pelvis instead of a real thigh",
        default=False)
    bpy.types.Scene.mmr_retarget_root_scale = bpy.props.FloatProperty(
        name="Root Motion Scale",
        description="Multiplier for the root translation channel. 0 = derive it "
                    "from the two rigs' hip heights. Set 1.0 when both rigs are "
                    "the same character at the same scale but disagree on where "
                    "the hip sits, otherwise the feet slide",
        default=0.0, min=0.0, max=10.0, precision=3, step=1)
    bpy.types.Scene.mmr_retarget_only_used = bpy.props.BoolProperty(
        name="Skip Unused Actions",
        description="Only convert actions that something still references",
        default=False)
    bpy.types.Scene.mmr_retarget_in_place = bpy.props.BoolProperty(
        name="Rewrite In Place",
        description="Rewrite the actions themselves, so NLA strips and existing "
                    "assignments keep working. Off = write '<name>_retarget' "
                    "copies and leave the originals alone",
        default=True)


def unregister():
    del bpy.types.Scene.mmr_retarget_in_place
    del bpy.types.Scene.mmr_retarget_only_used
    del bpy.types.Scene.mmr_retarget_root_scale
    del bpy.types.Scene.mmr_retarget_leg_remap
    del bpy.types.Scene.mmr_retarget_target
    del bpy.types.Scene.mmr_retarget_source
    del bpy.types.Scene.mmr_weight_sym_dir
    del bpy.types.Scene.mmr_transfer_reach
    del bpy.types.Scene.mmr_skirt_reach
    del bpy.types.Scene.mmr_rigid_small_parts
    del bpy.types.Scene.mmr_joint_blend_strength
    del bpy.types.Scene.mmr_clean_threshold
    del bpy.types.Scene.mmr_limit_weights_4
    del bpy.types.Scene.mmr_cross_side_cleanup
    del bpy.types.Scene.mmr_weight_profile
    del bpy.types.Scene.mmr_forward_dir
    del bpy.types.Scene.mmr_forward_axis
    del bpy.types.Scene.mmr_skeleton_lod
    del bpy.types.Scene.mmr_symmetry_axis
    del bpy.types.Scene.mmr_use_symmetry
    del bpy.types.Scene.mmr_armature
    del bpy.types.Scene.mmr_target_mesh
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
