# Manual Marker Mixamo Rigger (MVP, v0.9)

## Mixamo-compatible skeleton (works with the Animation Library)

The generated armature now matches a skeleton imported via **"Import as New
Character"** (Mixamo Animation Library), so Mixamo animation actions apply
directly without the character flying away or breaking:

- The armature **object** is built rotated **+90° on X** and scaled **0.01**,
  and the bone **data** is stored **Y-up in centimetres** — exactly what the
  FBX importer (`automatic_bone_orientation=False`) produces for Mixamo rigs.
- Bone **roll** is aligned to Mixamo's rest convention (spine/legs local +Z
  forward, arms local +Z down), so animation rotations transfer correctly.
- Bone **directions** run joint → next joint, so every child's head sits exactly
  on its parent's tail and the chains stay connected (they are *not* straightened
  onto a canonical axis — that kept the heads on the joints but pushed the tails
  off the next joint, breaking the chain). **The character should be in a real
  T-pose** (arms out horizontally, legs straight) so the resulting directions
  match Mixamo's rest pose and animation rotations transfer without twist.
- Bones still **appear on your character** in the viewport (world positions are
  unchanged); only the internal data space is Mixamo-style.

Verified against the real `T-Pose.fbx`: generated bone rest orientations match
the imported Mixamo rig within ~11° (direction) / ~8° (roll), and applying
`Standing Melee Punch` keeps the Hips within 0.8 m (no fly-away).

### Character orientation in Blender

The character **must stand upright in Blender's Z-up world** (head at +Z) — this
is required and the **Up axis is locked to Z** (not user-configurable), because
the Mixamo conversion (+90° X object rotation) maps world Z-up → Mixamo Y-up.

- **Up = Z (locked)** — body vertical in the Blender viewport
- **Forward = -Y** (configurable) — the character faces -Y; feet point -Y
- **Left / Right = X** (Symmetry axis)

Only the **foot-forward** direction is configurable (Orientation box). If the
Chin marker isn't clearly above the Groin marker along Z, **Build** refuses with
a clear message — recreate the markers on a standing character.

> Upgrading from an old version? If a saved scene had "Up Axis = Y", markers
> used to lay out horizontally and the rig came out lying on its side. That
> setting is gone now — just **Create Mixamo Markers** again (they appear
> vertical/Z-up), place them, and Build.

### Unity export

Because the rig already matches Mixamo, export FBX with Blender's standard
settings (**Up: Y, Forward: -Z**, Apply Unit + Apply Transform). Unity then
imports it Y-up with correct bones — same as any Mixamo character. Do **not**
lay the character along Y in Blender to "pre-rotate" for Unity; the FBX
exporter handles the Z-up → Y-up conversion.

### ⚠️ Do NOT apply the armature's rotation/scale

The generated armature intentionally has **rotation X = 90°** and **scale =
0.01** — identical to an imported Mixamo character. This is REQUIRED:

- Keep it → animations play in place (character stays put).
- Apply/zero it (Ctrl+A → Rotation & Scale, or setting rotation to 0) → the
  character **flies ~12 m away** when animated, because Mixamo's Hips
  translation is in centimetres and only the 0.01 scale converts it back.

A mesh at rotation 0 bound to this armature (rotation 90) is correct and
expected — exactly how imported Mixamo characters are set up. If you
accidentally changed the transform, the panel shows a warning; just click
**Build Mixamo Armature** again to restore it.

### Applying animations

1. In the Mixamo Animation Library, select your generated `MMR_Mixamo_Armature`.
2. Use **Apply to Selected Armature** (or the list's click-to-preview).
3. Body bones (20, no fingers) are driven; the animation's finger/toe keys are
   harmlessly ignored until fingers are added in a later version.

Run `blender -b --factory-startup --python mixamo_compat_test.py` (with the
Animation Library resources present) to re-verify compatibility.


Blender 4.x add-on with a **Mixamo-style workflow**: place 10 markers
(chin, groin, shoulders, elbows, wrists, knees) on a T-Pose humanoid — right-side
markers mirror the left side **in realtime**, on a selectable symmetry axis
(X / Y / Z) — the add-on estimates the full Mixamo-compatible skeleton, binds
with automatic weights, and cleans weights for Unity/mobile (max 4 influences
per vertex).

Single file: `mixamo_marker_rigger.py`

## Install

1. Blender → **Edit → Preferences → Add-ons → Install...** (v4.2+: dropdown arrow → *Install from Disk*)
2. Pick `mixamo_marker_rigger.py`, enable **Manual Marker Mixamo Rigger**.
3. Panel appears in **3D Viewport → Sidebar (N) → "Mixamo Rigger" tab**.

## Workflow (like Mixamo)

1. Select your T-Pose character mesh → **Set Selected Mesh**
2. **Prepare Mesh** (applies rotation + scale, keeps location)
3. **Create Mixamo Markers** — 10 sphere empties appear, auto-scaled to
   the mesh, in the `MMR_Joint_Markers` collection:
   - Yellow (center): `Chin`, `Groin`
   - Green (left): `LeftShoulder`, `LeftElbow`, `LeftWrist`, `LeftKnee`
   - Blue (right): `RightShoulder`, `RightElbow`, `RightWrist`, `RightKnee`
4. Move the chin, groin and **left-side** markers onto the character —
   with **Use Symmetry** on (default), the right-side markers follow
   **live in the viewport** via drivers on the selected **Symmetry Axis**:
   - `X`: `Right.X = 2·cx − Left.X`, `Y = Left.Y`, `Z = Left.Z`
   - `Y`: `Right.Y = 2·cy − Left.Y`, `X = Left.X`, `Z = Left.Z`
   - `Z`: `Right.Z = 2·cz − Left.Z`, `X = Left.X`, `Y = Left.Y`

   where `cx/cy/cz` come from the `MMR_SYMMETRY_CENTER` empty. Pick the axis
   that matches your character's left/right direction. Changing the axis
   rebuilds the drivers immediately — no need to recreate markers or press
   Mirror.

   Symmetry controls (in the panel's **Symmetry** box):
   - **Symmetry Axis**: X / Y / Z (default X)
   - **Center**: the `MMR_SYMMETRY_CENTER` location (editable)
   - **Refresh Realtime Symmetry**: rebuild drivers for the current axis
   - **Set Symmetry Center From Selected Mesh**: set the center's active-axis
     component to the mesh bounding-box center
   - **Snap Center Markers To Symmetry Plane**: move Chin/Groin onto the plane
     along the active axis
   - **Mirror Left To Right**: manual fallback (respects the axis), disabled
     while realtime symmetry is on

   Right markers are locked while driven; chin/groin are locked on the active
   axis. Turning symmetry off bakes the current mirrored positions and unlocks
   everything.
5. **Skeleton LOD: No Fingers** (default and only MVP option) →
   **Build Mixamo Armature** — the full skeleton (Hips, Spine chain, Neck,
   Head, shoulders, arms, hands, legs, feet = 20 `mixamorig:` bones) is
   estimated from the markers + mesh bounding box.
   **Build As New Armature** — same, but creates an ADDITIONAL armature
   (named `MMR_Mixamo_Armature_<mesh>`, auto-uniquified) without touching any
   existing armature — use it to rig several characters in one file. The new
   rig is untagged, so later normal rebuilds never delete it, and it becomes
   the Bind target. (Normal **Build Mixamo Armature** only ever replaces the
   add-on's own managed rig.)
   **Set Selected Armature** — reuse an EXISTING armature as the rig target
   instead of building: select the armature object and click it; Bind and all
   weight tools then use that rig. Warns if the armature has no `mixamorig:`
   bones (animations won't match by name) or isn't in Mixamo object space
   (rot X=90, scale 0.01 — animations may play wrong).
6. **Bind With Automatic Weights**
7. **Smart Mixamo Weight Refine** (recommended) — see "Weight Tools" below
8. **Clean Weights** (normalize → clean tiny weights → limit to 4 → normalize)
9. **Remove Markers** when done (also removes the symmetry center)

## Weight Tools

After **Bind With Automatic Weights**, the "Weight Tools" box offers a smarter
post-process that pushes the result closer to Mixamo quality. It never replaces
automatic weights — it refines them.

- **Backup Weights / Restore Weight Backup** — save/restore the current weights
  into `MMR_BACKUP_` groups (only the latest backup is kept). Take a backup
  before refining so you can revert. Backup groups are ignored by every weight
  operation (they never deform and are never normalized), but remember to
  remove them before a final FBX export.
- **Smart Mixamo Weight Refine** runs, in order: cross-side cleanup (drops
  opposite left/right bone weights), region cleanup (drops weights from
  unrelated limb chains while preserving joint blends near elbow/knee/
  shoulder/hip), optional rigid small-part assignment, remove tiny weights,
  limit to 4, normalize.
- **Copy Weights (Same Topology)** — copies the body mesh's weights **1:1 by
  vertex index** onto each selected mesh with IDENTICAL topology (a duplicate /
  re-skinned variant). Exact, and the meshes do **not** need to overlap in
  space — unlike Transfer, which samples by nearest surface and requires the
  characters to stand on top of each other. Errors clearly (and suggests
  Transfer) when the vertex counts differ.
- **Bind Skirt / Dress** — for a skirt/dress mesh that automatic weights bind
  only to the thigh (`UpLeg`), so it penetrates the leg when the knee bends.
  Select the skirt mesh(es) and click this: each vertex is weighted by
  **inverse distance to the nearby lower-body bones** (Hips, Spine, both
  UpLeg, both Leg, both Foot), keeping its 4 strongest influences. So a vertex
  near the knee naturally picks up **both `UpLeg` and `Leg`** (a wider search
  than nearest-bone), side vertices lean toward their own leg, and centre
  vertices blend both legs (no tearing). The **Skirt Bone Reach** slider widens
  the falloff (low = nearest bone dominates, high = more bones blend in).
  Not physics — a static skin approximation.
- **Symmetrize Weights** — makes the selected mesh's weights symmetric across
  the symmetry plane, treating the source half as the single source of truth:
  the target half is **zeroed in all groups first**, then each target vertex
  copies its mirror vertex's weights with Left/Right bone names swapped
  (`mixamorig:LeftArm` ↔ `RightArm`); mirror partners are searched on the
  source side only, and vertices **on the plane itself** get equal weights for
  each Left/Right bone pair (source bone wins, total kept), so the centre line
  deforms identically to both halves. Fixes an asymmetric side (e.g. after
  auto-weight) so left deforms exactly like right. Pick which side is the
  source with **Symmetrize From** (`+X to -X` or `-X to +X`). (Done manually —
  Blender's built-in mirror can't flip the `mixamorig:` names.)
- **Zero All Weights** — sets every vertex weight of the selected mesh(es) to 0
  in all vertex groups, **keeping the groups, the armature modifier and the
  parent**. A clean slate for painting weights by hand (differs from Unbind,
  which deletes the groups and detaches the mesh).
- **Unbind Mesh** — fully unbinds the selected mesh(es): removes the Armature
  modifier, unparents (keeping world position), and deletes ALL vertex groups.
  Use it to start weighting over, or to detach a mesh from the rig. Falls back
  to the stored target mesh if nothing is selected.
- **Bind Accessories (Rigid)** — for separate meshes NOT joined to the body
  (glasses, hat, beard, belt, shoulder pads...). Select the accessory
  object(s), then click it: each is rigidly bound (single vertex group = 1.0 +
  armature modifier + parented) to its **nearest bone** so it follows the rig
  without deforming (glasses/hat → Head, belt → Hips, etc.). Automatic Weights
  only binds the one stored body mesh, so accessories must be bound with this.
  (If an accessory is *joined into* the body mesh as a disconnected island,
  use **Rigid Small Parts** in Smart Mixamo Weight Refine instead.)
- **Transfer Weights To Accessories** — copies the body's skin weights onto each
  selected extra mesh using Blender's Data Transfer (nearest-surface,
  interpolated) for **smooth, even** weights (same quality as automatic
  weights), then smooths them across the accessory's own surface. Best for
  accessories that deform *like the body region they sit on* — hat/hair, cloth,
  a **skirt/dress**. The **Transfer Reach** slider controls the smoothing/
  spreading: `0` = crisp nearest-surface (hat, glove); **raise it so a loose
  skirt spreads the lower-leg (`Leg`) influence up from its hem**. Bind the body
  first, then select the accessories and click this. (Use **Bind Accessories
  (Rigid)** for hard parts like glasses that must not deform.)
- **Weight Diagnostics** prints (to the System Console) zero-weight verts,
  >4-influence verts, cross-side verts, empty groups, the top-10 groups, and
  whether all required Mixamo groups exist.

Controls:

- **Weight Profile**: `Balanced` (default), `Soft Organic` (more smoothing,
  wider joint blend, no cross-side/rigid aggression), `Rigid Game Model`
  (aggressive cleanup, rigid small parts — good for low-poly/cartoon/mobile).
- **Cross Side Cleanup** (default on) — remove opposite-side weights.
- **Limit Weights To 4** (default on) — Unity/mobile cap.
- **Rigid Small Parts** (default on) — small disconnected islands (helmet,
  shoulder pad, wrist guard, belt, boots) are assigned rigidly to the nearest
  bone; the main body island is never rigid-assigned.
- **Clean Threshold** (default 0.005) — weights below this are dropped.
- **Joint Blend Strength** (default 0.35) — how wide the joint blend zone is
  kept (higher = softer around joints).

Side detection uses the selected **Symmetry Axis** and the `MMR_SYMMETRY_CENTER`
position (not hard-coded to X); vertices within a small center band are treated
as center region and keep spine/hip/shoulder blends.

This improves automatic weights but does not fully replace manual weight
painting — shoulders, armpits, groin, skirts, cloaks and armor may still need
touch-ups.

## Retarget Actions (moving to a replacement rig)

An action stores every bone's rotation **relative to its rest pose**, so actions
authored on the generated rig are offset by the rest difference when replayed on
another rig (e.g. a skeleton downloaded from mixamo.com) — bones come out
twisted. The **Retarget Actions** box rewrites the F-Curves so they play on the
new rig the way they played on the old one; no animation has to be redone.

Blender evaluates `pose = pose_parent @ M @ basis` with
`M = rest_parent⁻¹ @ rest_bone`, so writing `basis_new = M_new⁻¹ @ M_old @ basis_old`
into every bone's curves reproduces the source rig's world orientation exactly
(parents are already corrected by the time children evaluate). It is instant —
no frame-by-frame baking.

1. **From (old rig)** — the rig the actions were authored on.
2. **To (new rig)** — the replacement rig (defaults to the Status box rig).
3. **Check Rest Difference** — prints the per-bone rest gap to the System
   Console without changing anything. Run this first: it is the size of the
   error each action currently suffers.
4. **Retarget Actions To Target Rig** — converts every action.

Options:

- **Fix Leg Chain** — see the warning below. Off by default.
- **Skip Unused Actions** — ignore actions nothing references any more.
- **Rewrite In Place** (default on) — rewrites the actions themselves, so NLA
  strips and existing assignments keep working. **Save the .blend first.** Turn
  it off to get `<name>_retarget` copies and leave the originals alone.

Each converted action is tagged `mmr_retargeted`, so running the tool twice
never applies the delta twice.

Handled: `rotation_quaternion`, `rotation_euler` (kept continuous, no 360°
jumps), `location` (rotated by the delta and scaled by the two rigs' hip-height
ratio), Blender 4.4+ slotted actions, and per-key interpolation/handles. Bones
that exist only on the target rig (fingers, `ToeBase`, `HeadTop_End`) simply
stay at rest.

### ⚠️ Rotation retargeting cannot fix a structurally different chain

The maths matches **orientations**, not proportions. If a limb is built
differently on the two rigs, matching orientations bone-for-bone faithfully
reproduces the *source's* geometry — including its defects.

The common case is the leg. When the hip sockets were estimated far from the
groin, the generated `UpLeg` degenerates into a near-horizontal connector inside
the pelvis and `Leg` carries the whole limb, while a real Mixamo `UpLeg` is the
thigh. Copying orientations then swings the target's real thigh out sideways and
lifts the knee above the hip. **Fix Leg Chain** handles exactly this: the
target's thigh is driven by the source's `Leg` bone instead, solved in world
space, and the target's `Leg` is held at rest (the source has no knee joint to
transfer). Measured on a real case: knee height went from *above* the hip
(0.139 vs 0.118) to a correct descent (hip 0.118 → knee 0.058 → ankle 0.041).

When reading the per-bone report, remember a remapped bone's **children** cannot
match the source either — `Foot` hangs off the remapped `Leg`, so it inherits
that intentional mismatch even though its own delta was applied correctly.

Two things retargeting still cannot fix, because they are properties of the
rigs and not of the actions:

- **Different limb proportions.** Joint positions still differ, so silhouettes
  won't match exactly.
- **A badly auto-rigged target.** Check the target's shin against a real Mixamo
  skeleton, where `Leg` is ~39% of hip height. A shin of ~12% means the knee was
  placed almost at the ankle in the Mixamo web rigger, and no retarget will make
  knee bends read correctly — re-rig with the knee marker placed properly.

## How the skeleton is estimated

All joint positions are computed in **world space** and converted to armature
local space when the edit bones are created (the armature is built with an
identity transform). **Build Mixamo Armature** requires the mesh to have
applied rotation/scale — run **Prepare Mesh** first or it will refuse and warn.

- `Neck` (the base of the neck) is placed at the **height of your Shoulder
  markers**, projected onto the Groin→Chin axis — not at a fixed fraction of it,
  which put the neck up near the jaw when the Chin marker sat high. It is clamped
  to 55–92% of the Groin→Chin span (a warning is printed if the clamp kicks in).
- Spine chain (`Spine` / `Spine1` / `Spine2`) is interpolated between Groin and
  `Neck` (28% / 51% / 74%) along the body-up vector, so it stays vertical through
  the body and always below the neck; `Hips` sits slightly above the groin.
- **Shoulders** come from the `LeftShoulder`/`RightShoulder` markers you place
  (no longer estimated): `LeftShoulder` bone runs from `Spine2` to the shoulder
  marker, and `LeftArm` starts exactly at the shoulder marker → elbow, so the
  upper arm begins at the real shoulder. `LeftForeArm` elbow→wrist, `LeftHand`
  extends past the wrist. (`LeftShoulder`/`LeftUpLeg` branch off the parent's
  *head*, so those two stay unconnected; every other bone is connected to its
  parent's tail.)
- Hip sockets are offset from the groin toward each knee (~35% along the
  symmetry axis) so the two legs don't share one point; ankles are placed
  under the knees near the mesh bottom.
- **Feet** point along the separate **Character Forward Axis** + **Forward
  Direction** settings (default `+Y`), *not* the symmetry axis. Both feet use
  the same forward vector (never mirrored). Foot length is
  `max(height·0.08, lower_leg·0.25)`, so foot bones are never zero-length.
  If the feet point backward, click **Flip Foot Direction** (toggles
  Positive/Negative and rebuilds the armature).
- The left/right direction always follows the selected **Symmetry Axis**
  (X/Y/Z) — nothing is hard-coded to X.
- After all bones are created, bone roll is set deterministically with
  `calculate_roll(GLOBAL_POS_Z)` so local axes are consistent (no random
  twist); the console prints the estimated shoulder/hip positions and axis.

## Notes

* Character must face **-Y** (Blender front view) and stand on Z with center at X = 0.
* The add-on never deletes user meshes, and refuses to overwrite an armature named
  `MMR_Mixamo_Armature` that it didn't generate itself.
* **Create Mixamo Markers** also cleans up any leftover markers from older
  add-on versions (anything prefixed `MMR_MARKER_`).
* Build validates: all 8 markers exist, no marker sits at the world origin,
  no zero-length bones (safe offsets added automatically).

## MVP limitations

* No fingers, toes, facial bones, IK, or control bones (Skeleton LOD: No Fingers only).
* Bone rolls are left at 0.
* Skeleton quality depends on marker placement + mesh bounding box; unusual
  proportions may need manual bone tweaks after generation.
* Automatic weights can fail on non-manifold / overlapping geometry — Blender's
  standard limitation; the add-on reports the error.

## Headless test

```
blender -b --factory-startup --python test_mmr.py
```
