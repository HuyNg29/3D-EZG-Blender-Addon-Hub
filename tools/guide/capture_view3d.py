"""Chup vung 3D View (header + toolbar + viewport + sidebar) de lam anh huong dan.

Chay trong SANDBOX (giong tools/run_tests.ps1) de khong dung config that:

    $env:BLENDER_USER_RESOURCES = <thu muc tam>
    $env:EZG_REPO_ROOT = <repo>
    blender --factory-startup --enable-event-simulate --window-geometry 0 0 1600 900 `
        --python tools/guide/capture_view3d.py -- <addon_pkg> <sidebar_tab> <out.png> [canh]

<addon_pkg> duoc register thang tu addons/ cua repo. Truyen "none" de bo qua: canh
hub_* tu cai hub + vai addon THAT tu kho tren Pages (can them --online-mode), vi
hub chi chay dung khi la extension da cai.

[canh] la mot khoa trong SCENES ben duoi, mac dinh deco_namer. Canh hub_backup
chi DOC thu muc backup mac dinh (~/EZG Addon Hub/profiles), khong ghi gi vao do.
Ve khung do / mui ten len anh bang tools/guide/annotate.ps1.
"""
import os
import sys
import traceback

import bpy
import gpu
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
ADDON, TAB, OUT = argv[0], argv[1], argv[2]
SCENE = argv[3] if len(argv) > 3 else "deco_namer"
REPO = os.environ["EZG_REPO_ROOT"]
sys.path.insert(0, os.path.join(REPO, "addons"))

LIVE_URL = "https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json"
HUB_MODULE = "bl_ext.ezg.ezg_addon_hub"

REGION_TYPES = ("HEADER", "TOOL_HEADER", "TOOLS", "WINDOW", "UI")
shots = {}
want = {"on": False}
handles = []


def log(*a):
    print("[capture]", *a, flush=True)


def view3d_area():
    for area in bpy.context.window.screen.areas:
        if area.type == 'VIEW_3D':
            return area
    raise RuntimeError("khong co VIEW_3D")


def make_cb(rtype):
    def cb():
        if not want["on"]:
            return
        region = bpy.context.region
        if region is None or region.type != rtype:
            return
        w, h = region.width, region.height
        px = read_fb(gpu.state.active_framebuffer_get(), w, h)
        if rtype == 'WINDOW':
            # POST_PIXEL cua viewport chi thay lop OVERLAY (nen, grid, vien, chu,
            # gizmo) — be mat mesh nam o texture render rieng, alpha = 0 o day.
            # Ve lai canh vao offscreen roi cong vao: final = overlay + scene * (1 - overlay.a)
            ctx = bpy.context
            off = gpu.types.GPUOffScreen(w, h)
            rv3d = ctx.region_data
            off.draw_view3d(ctx.scene, ctx.view_layer, ctx.space_data, region,
                            rv3d.view_matrix, rv3d.window_matrix,
                            do_color_management=True, draw_background=False)
            with off.bind():
                base = read_fb(gpu.state.active_framebuffer_get(), w, h)
            off.free()
            a = px[..., 3:4].astype(np.float32) / 255.0
            # base (khong nen) con lan grid mo (alpha thap) — nhan them alpha cua
            # base de chi lay be mat mesh dac, khong cong grid lan hai.
            ba = base[..., 3:4].astype(np.float32) / 255.0
            mix = base[..., :3].astype(np.float32) * (1.0 - a) * ba + px[..., :3].astype(np.float32)
            px = px.copy()
            px[..., :3] = np.clip(mix, 0, 255).astype(np.uint8)
        shots[rtype] = (region.x, region.y, w, h, px)
    return cb


def read_fb(fb, w, h):
    buf = fb.read_color(0, 0, w, h, 4, 0, 'UBYTE')
    buf.dimensions = w * h * 4
    return np.array(buf, dtype=np.uint8).reshape(h, w, 4)


def _row_of_cubes(names, selected, active):
    bpy.ops.object.select_all(action='DESELECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for i, n in enumerate(names):
        bpy.ops.mesh.primitive_cube_add(size=0.8, location=(i * 1.3 - 2.6, 0, 0.4))
        bpy.context.object.name = n
    for n in names:
        bpy.data.objects[n].select_set(n in selected)
    bpy.context.view_layer.objects.active = bpy.data.objects[active]
    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=win_rgn):
        bpy.ops.view3d.view_all()


def scene_deco_namer():
    # Vai khoi hop, chon 3 cai.
    _row_of_cubes(["SM_Chair", "SM_Lamp", "SM_Plant", "SM_Table", "SM_Crate"],
                  ("SM_Chair", "SM_Lamp", "SM_Plant"), "SM_Lamp")


def scene_object_spread():
    # Vai asset to nho lan lon chong het o 0,0,0 + mot cum parent (Lamp con cua
    # Table). Chon het roi bam Xep luoi that: Lamp phai nam yen tren Table.
    bpy.ops.object.select_all(action='DESELECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    mesh = bpy.ops.mesh
    specs = [
        ("Rock_01", mesh.primitive_ico_sphere_add, {"radius": 0.6, "subdivisions": 1}, None),
        ("Barrel_01", mesh.primitive_cylinder_add, {"radius": 0.5, "depth": 1.2}, None),
        ("Tree_01", mesh.primitive_cone_add, {"radius1": 0.9, "depth": 2.6}, None),
        ("Crate_01", mesh.primitive_cube_add, {"size": 1.0}, None),
        ("Tyre_01", mesh.primitive_torus_add, {"major_radius": 0.6, "minor_radius": 0.2}, None),
        ("Wall_01", mesh.primitive_cube_add, {"size": 1.0}, (3.0, 0.3, 1.5)),
        ("Monkey_01", mesh.primitive_monkey_add, {"size": 1.0}, None),
        ("Table_01", mesh.primitive_cube_add, {"size": 1.0}, (1.6, 0.9, 0.1)),
    ]
    for name, add, kw, scale in specs:
        add(**kw)
        ob = bpy.context.object
        ob.name = name
        if scale:
            ob.scale = scale
    table = bpy.data.objects["Table_01"]
    mesh.primitive_cone_add(radius1=0.25, depth=0.6, location=(0.4, 0.0, 0.35))
    lamp = bpy.context.object
    lamp.name = "Lamp_01"
    bpy.context.view_layer.update()
    lamp.parent = table
    lamp.matrix_parent_inverse = table.matrix_world.inverted()

    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        bpy.ops.object.select_all(action='SELECT')
        bpy.context.view_layer.objects.active = table
        settings = bpy.context.scene.ezg_spread
        settings.mode = 'AUTO'
        settings.gap = 0.6
        log("arrange", bpy.ops.ezg_spread.arrange())
    from math import radians
    from mathutils import Euler
    area.spaces.active.region_3d.view_rotation = \
        Euler((radians(55), 0, radians(25))).to_quaternion()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        bpy.ops.view3d.view_all()


def scene_uv_palette():
    # 5 object, chon 4. Moi cai co material + Image Texture noi Base Color de
    # panel khong bao "object khong co texture".
    names = ["1. Chair", "2. Lamp", "3. Plant", "4. Table", "5. Crate"]
    _row_of_cubes(names, names[:4], names[1])
    for n in names:
        ob = bpy.data.objects[n]
        mat = bpy.data.materials.new("M_" + n.split(" ", 1)[1])
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.new("T_" + n.split(" ", 1)[1], 64, 64)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        ob.data.materials.append(mat)
    props = bpy.context.scene.auto_uv_palette
    # Chi la chuoi hien trong panel, canh nay khong export gi ra do. Duong dan
    # tuong doi "//" bi to do vi file chua luu.
    props.export_dir = "D:\\Project\\palette_png\\"
    props.canvas_size = 3072  # chia het cho 3x3, panel khong canh bao


def scene_uv_palette_add():
    # Da co palette 3x3 chua 3 object dau; 2 object moi vua duoc xep vao o trong.
    scene_uv_palette()
    names = [o.name for o in sorted(bpy.data.objects, key=lambda o: o.name)]
    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        for batch, op in ((names[:3], bpy.ops.object.auto_uv_palette_pack),
                          (names[3:], bpy.ops.object.auto_uv_palette_add)):
            for n in names:
                bpy.data.objects[n].select_set(n in batch)
            bpy.context.view_layer.objects.active = bpy.data.objects[batch[0]]
            log(op.idname(), op())
            # Palette cu da duoc gan anh (buoc Assign Palette), nen material
            # chung co texture va panel khong bao "object khong co texture".
            for mat in bpy.data.materials:
                if mat.name.startswith("UVPalette_"):
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image is None:
                            node.image = bpy.data.images.new("palette_3x3.png", 64, 64)


MIXAMO_DIR = os.environ.get("EZG_TEST_ASSETS", r"D:\EZG Addon Assets\MixamoLibResource")


def scene_anim_lib():
    # Nhan vat T-Pose Mixamo, thu vien tro vao bo asset test, da ap 2 animation
    # (co dau tich trong danh sach), dung o giua cu dam.
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.fbx(filepath=os.path.join(MIXAMO_DIR, "T-Pose.fbx"))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    props = bpy.context.scene.mixlib
    props.library_path = MIXAMO_DIR + "\\"
    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        for name in ("Standing Equip Bow", "Standing Melee Punch"):
            bpy.ops.object.select_all(action='DESELECT')
            arm.select_set(True)
            bpy.context.view_layer.objects.active = arm
            props.active_index = _select(props.items, "name", name)
            log("apply", name, bpy.ops.mixlib.apply())
        bpy.ops.object.select_all(action='DESELECT')
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        scene = bpy.context.scene
        scene.frame_set((scene.frame_start + scene.frame_end) // 2)
        bpy.ops.view3d.view_all()
    # Xuong dang que manh, khong ve de len mesh — cho khoi che mat nhan vat.
    arm.show_in_front = False
    arm.data.display_type = 'STICK'
    # Nhin 3/4 phia truoc. Nhan vat quay mat +Y thi tay phai nam ben +X.
    from math import radians
    from mathutils import Euler
    hand = arm.pose.bones.get("mixamorig:RightHand")
    faces_pos_y = hand is not None and (arm.matrix_world @ hand.head).x > arm.location.x
    rv3d = area.spaces.active.region_3d
    rv3d.view_rotation = Euler((radians(80), 0, radians(210 if faces_pos_y else 30))).to_quaternion()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        bpy.ops.view3d.view_all()


# Ten xuong kieu Unreal cho rig dich. Rigify metarig KHONG dung duoc lam vi du:
# xuong goc cua no ten "spine" (khong co "hips"/"pelvis") nen Auto Map bo trong
# vai tro hips va retarget ra tu the lech han.
_UE_NAMES = {
    "Hips": "pelvis", "Spine": "spine_01", "Spine1": "spine_02", "Spine2": "spine_03",
    "Neck": "neck_01", "Head": "head", "HeadTop_End": "head_end",
}
_UE_SIDED = {
    "Shoulder": "clavicle", "Arm": "upperarm", "ForeArm": "lowerarm", "Hand": "hand",
    "UpLeg": "thigh", "Leg": "calf", "Foot": "foot", "ToeBase": "ball", "Toe_End": "ball_end",
}


def _ue_name(mixamo_name):
    import re
    n = mixamo_name.split(":")[-1]
    if n in _UE_NAMES:
        return _UE_NAMES[n]
    m = re.match(r"(Left|Right)Hand(Thumb|Index|Middle|Ring|Pinky)(\d)$", n)
    if m:
        return "%s_%02d_%s" % (m.group(2).lower(), int(m.group(3)), m.group(1)[0].lower())
    m = re.match(r"(Left|Right)(.+)$", n)
    if m and m.group(2) in _UE_SIDED:
        return "%s_%s" % (_UE_SIDED[m.group(2)], m.group(1)[0].lower())
    return n


def _ue_copy(src, name, x, scale):
    """Nhan ban nhan vat Mixamo (armature + mesh con) roi doi ten xuong kieu
    Unreal. Mesh phai copy ca data: ten vertex group nam tren mesh, dung chung
    thi doi ten xuong ban sao se lam hong skin cua ban goc."""
    coll = src.users_collection[0]
    arm = src.copy()
    arm.data = src.data.copy()
    arm.animation_data_clear()
    arm.name = name
    coll.objects.link(arm)
    for child in [c for c in src.children if c.type == 'MESH']:
        m = child.copy()
        m.data = child.data.copy()
        m.parent = arm
        for mod in m.modifiers:
            if mod.type == 'ARMATURE':
                mod.object = arm
        coll.objects.link(m)
    for b in arm.data.bones:
        b.name = _ue_name(b.name)  # doi ten qua RNA -> vertex group doi theo
    arm.location.x = x
    arm.scale = (scale, scale, scale)
    return arm


def _anim_tools_scene(open_panels):
    # Nguon: nhan vat Mixamo mang action dam (lay tu FBX khong skin). Dich: ban
    # sao nhan vat voi ten xuong kieu Unreal, nho hon 10%. Chay Auto Map +
    # Retarget that.
    from ezg_anim_tools import core, ui

    # Panel Mirror / Polish mac dinh dong; mo san bang cach dang ki lai class
    # truoc lan ve dau (khong co API Python mo panel). Chi doi o phien chup.
    for cls in (ui.EZG_AT_PT_retarget, ui.EZG_AT_PT_mirror, ui.EZG_AT_PT_polish):
        bpy.utils.unregister_class(cls)
        cls.bl_options = set() if cls.__name__ in open_panels else {'DEFAULT_CLOSED'}
        bpy.utils.register_class(cls)

    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.fbx(filepath=os.path.join(MIXAMO_DIR, "T-Pose.fbx"))
    src = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    src.name = "Mixamo"
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(MIXAMO_DIR, "Standing Melee Punch.fbx"))
    extra = [o for o in bpy.data.objects if o not in before]
    act = next(o for o in extra if o.type == 'ARMATURE').animation_data.action
    act.name = "Melee Punch"
    act.use_fake_user = True
    for o in extra:
        bpy.data.objects.remove(o)
    ad = src.animation_data_create()
    ad.action = act
    core.bind_slot(ad, act)

    tgt = _ue_copy(src, "Hero_UE", 1.3, src.scale.x * 0.9)
    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        bpy.ops.object.select_all(action='DESELECT')
        st = bpy.context.scene.ezg_anim_tools
        st.source, st.target = src, tgt
        st.action_name = "Melee Punch_Hero"
        log("auto_map", bpy.ops.ezg_at.auto_map(), len(st.mapping))
        log("retarget", bpy.ops.ezg_at.retarget())
        st.mirror_object = tgt
        st.polish_object = tgt
        scene = bpy.context.scene
        f0, f1 = act.frame_range
        scene.frame_start, scene.frame_end = int(f0), int(f1)
        scene.frame_set(int((f0 + f1) / 2))
        bpy.ops.object.select_all(action='DESELECT')
        tgt.select_set(True)
        bpy.context.view_layer.objects.active = tgt
    for ob in (src, tgt):
        ob.show_in_front = False
        ob.data.display_type = 'STICK'
    from math import radians
    from mathutils import Euler
    area.spaces.active.region_3d.view_rotation = \
        Euler((radians(80), 0, radians(20))).to_quaternion()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0],
                                   area=area, region=win_rgn):
        bpy.ops.view3d.view_all()


def scene_anim_tools():
    _anim_tools_scene({"EZG_AT_PT_retarget"})


def scene_anim_tools_mirror():
    _anim_tools_scene({"EZG_AT_PT_mirror", "EZG_AT_PT_polish"})


def _hub_install(extra):
    """Dang ki kho EZG + cai hub va `extra` tu Pages, y nhu EZG-Hub-Setup.bat."""
    repos = bpy.context.preferences.extensions.repos
    repo = repos.new(name="EZG", module="ezg", remote_url=LIVE_URL)
    repo.use_remote_url = True
    repo.enabled = True
    idx = list(repos).index(repo)
    bpy.ops.extensions.repo_sync(repo_index=idx)
    for pkg in ["ezg_addon_hub"] + list(extra):
        bpy.ops.extensions.package_install(repo_index=idx, pkg_id=pkg, enable_on_install=True)
        log("da cai", pkg)
    if HUB_MODULE not in bpy.context.preferences.addons:
        raise RuntimeError("cai xong nhung hub chua bat")


def _select(coll, attr, value):
    for i, row in enumerate(coll):
        if getattr(row, attr) == value:
            return i
    raise RuntimeError("khong thay %s=%s" % (attr, value))


def scene_hub_store():
    _hub_install(["ezg_deco_namer", "ezg_fbx_batch"])
    wm = bpy.context.window_manager
    bpy.ops.ezg.refresh_store()
    wm.ezg_tab = 'STORE'
    wm.ezg_catalog_index = _select(wm.ezg_catalog, "pkg_id", "ezg_auto_uv_palette")


def scene_hub_machine():
    _hub_install(["ezg_deco_namer", "ezg_fbx_batch"])
    wm = bpy.context.window_manager
    bpy.ops.ezg.refresh_inventory(check_updates=True)
    wm.ezg_tab = 'MACHINE'
    wm.ezg_inventory_index = _select(wm.ezg_inventory, "pkg_id", "ezg_deco_namer")


def scene_hub_backup():
    # Nhu may vua chay EZG-Hub-Setup.bat: chi co "Bo chuan EZG", sinh tu repo.
    # Panel van ghi duong dan backup mac dinh, nhung snapshot doc tu sandbox —
    # thu muc backup that cua may nay khong bi doc lan ghi.
    import importlib.util
    import json

    _hub_install(["ezg_deco_namer", "ezg_fbx_batch"])
    backup = sys.modules[HUB_MODULE + ".backup"]
    spec = importlib.util.spec_from_file_location(
        "build_installer", os.path.join(REPO, "tools", "build_installer.py"))
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    root = os.path.join(os.environ["BLENDER_USER_RESOURCES"], "guide_profiles")
    prefs = bpy.context.preferences.addons[HUB_MODULE].preferences
    snap = os.path.join(root, backup._safe(prefs.resolved_profile_name()), installer.PROFILE_LABEL)
    os.makedirs(snap)
    with open(os.path.join(snap, backup.MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(installer.build_profile_manifest(), f)
    real_list = backup.list_snapshots
    backup.list_snapshots = lambda _root, profile: real_list(root, profile)

    wm = bpy.context.window_manager
    bpy.ops.ezg.refresh_inventory(check_updates=False)
    bpy.ops.ezg.refresh_snapshots()
    wm.ezg_tab = 'BACKUP'
    wm.ezg_snapshots_index = _select(wm.ezg_snapshots, "name", installer.PROFILE_LABEL)


# widen: keo sidebar rong them bay nhieu px (0 = giu nguyen, anh Deco Namer
# da lam o do rong mac dinh). scroll: so nac cuon sidebar xuong.
SCENES = {
    "deco_namer": (scene_deco_namer, {}),
    "object_spread": (scene_object_spread, {}),
    "uv_palette": (scene_uv_palette, {"widen": 110}),
    "uv_palette_add": (scene_uv_palette_add, {"widen": 110, "scroll": 30}),
    "anim_lib": (scene_anim_lib, {"widen": 110}),
    # Bang mapping co 2 cot ten xuong, can sidebar rong hon han.
    "anim_tools": (scene_anim_tools, {"widen": 260}),
    "anim_tools_mirror": (scene_anim_tools_mirror, {"widen": 110}),
    "hub_store": (scene_hub_store, {"widen": 110}),
    "hub_machine": (scene_hub_machine, {"widen": 110}),
    "hub_backup": (scene_hub_backup, {"widen": 110}),
}
SETUP, OPTS = SCENES[SCENE]


state = {"step": 0, "tries": 0}


def tick():
    try:
        return _tick()
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


def _tick():
    win = bpy.context.window_manager.windows[0]
    area = view3d_area()
    ui = next(r for r in area.regions if r.type == 'UI')
    s = state["step"]

    if s == 0:
        bpy.context.preferences.system.use_region_overlap = False
        area.spaces.active.show_region_ui = True
        if ADDON != "none":
            __import__(ADDON).register()
        SETUP()
        for rt in REGION_TYPES:
            handles.append((rt, bpy.types.SpaceView3D.draw_handler_add(
                make_cb(rt), (), rt, 'POST_PIXEL')))
        state["step"] = 1
        return 0.5

    if 10 <= s <= 14:
        # Keo mep trai sidebar sang trai. Vung keo nam NGOAI region 3px (do thu
        # tung px: ui.x-3 bat duoc region_scale, ui.x-4 va ui.x+1 thi khong).
        # Phai di chuot trong viewport truoc, va di chuot + bam cung mot nhip.
        y = ui.y + ui.height // 2
        if s == 10:
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=area.x + 600, y=area.y + 400)
        elif s == 11:
            state["w0"], state["x0"] = ui.width, ui.x - 3
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state["x0"], y=y)
            win.event_simulate(type='LEFTMOUSE', value='PRESS', x=state["x0"], y=y)
        elif s in (12, 13):
            step = OPTS["widen"] // 2 * (s - 11)
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state["x0"] - step, y=y)
        else:
            win.event_simulate(type='LEFTMOUSE', value='RELEASE',
                               x=state["x0"] - OPTS["widen"], y=y)
        state["step"] += 1
        return 0.25

    if s == 15:
        log("sidebar rong", state["w0"], "->", ui.width)
        state["step"] = 2
        return 1.0

    if s == 1:
        # active_panel_category read-only, Ctrl+Wheel gia lap khong doi duoc tab
        # -> click gia lap len dai tab (can --enable-event-simulate)
        cur = ui.active_panel_category
        log("tab hien tai:", cur)
        if cur == TAB:
            # Keo sidebar SAU khi chon tab: cu bam gia lap dau tien cua phien
            # bi nuot mat, luc nay da co vai cu click tab lam "mo mang".
            state["step"] = 10 if OPTS.get("widen") and "w0" not in state else 2
            return 1.0
        state["tries"] += 1
        if state["tries"] > 70:
            raise RuntimeError("khong xoay duoc toi tab " + TAB)
        # Quet doc dai tab ben phai sidebar, click tung nac 12px toi khi trung TAB
        x = ui.x + ui.width - 10
        y = ui.y + ui.height - 20 - (state["tries"] - 1) * 12
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
        win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)
        return 0.2

    if s == 2 and OPTS.get("scroll") and not state.get("scrolled"):
        x, y = ui.x + ui.width // 2, ui.y + ui.height // 2
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        for _ in range(OPTS["scroll"]):
            win.event_simulate(type='WHEELDOWNMOUSE', value='PRESS', x=x, y=y)
        state["scrolled"] = True
        return 0.5

    if s == 2:
        # Dua chuot ra khoi sidebar de khong co nut nao bi highlight
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=area.x + 300, y=area.y + 300)
        want["on"] = True
        for r in area.regions:
            r.tag_redraw()
        state["step"] = 3
        return 0.5

    if s == 3:
        missing = [rt for rt in REGION_TYPES
                   if rt not in shots and any(r.type == rt and r.width > 1 for r in area.regions)]
        if missing:
            log("cho region:", missing)
            for r in area.regions:
                r.tag_redraw()
            state["tries"] += 1
            if state["tries"] > 60:
                raise RuntimeError("khong chup duoc " + str(missing))
            return 0.3
        img = np.zeros((area.height, area.width, 4), dtype=np.uint8)
        img[..., 3] = 255
        for rt, (x, y, w, h, px) in shots.items():
            ox, oy = x - area.x, y - area.y
            img[oy:oy + h, ox:ox + w] = px
        img[..., 3] = 255
        H, W = img.shape[:2]
        im = bpy.data.images.new("cap", W, H, alpha=False)
        im.pixels.foreach_set((img.astype(np.float32) / 255.0).ravel())
        im.filepath_raw = OUT
        im.file_format = 'PNG'
        im.save()
        log("da ghi", OUT, W, H)
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=1.0)
