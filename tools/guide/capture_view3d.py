"""Chup vung 3D View (header + toolbar + viewport + sidebar) de lam anh huong dan.

Chay trong SANDBOX (giong tools/run_tests.ps1) de khong dung config that:

    $env:BLENDER_USER_RESOURCES = <thu muc tam>
    $env:EZG_REPO_ROOT = <repo>
    blender --factory-startup --enable-event-simulate --window-geometry 0 0 1600 900 `
        --python tools/guide/capture_view3d.py -- <addon_pkg> <sidebar_tab> <out.png>

setup_scene() hien dung canh demo cho Deco Namer; addon khac thi viet canh rieng.
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
REPO = os.environ["EZG_REPO_ROOT"]
sys.path.insert(0, os.path.join(REPO, "addons"))

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


def setup_scene():
    # Canh demo cho Deco Namer: vai khoi hop, chon 3 cai.
    bpy.ops.object.select_all(action='DESELECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    names = ["SM_Chair", "SM_Lamp", "SM_Plant", "SM_Table", "SM_Crate"]
    for i, n in enumerate(names):
        bpy.ops.mesh.primitive_cube_add(size=0.8, location=(i * 1.3 - 2.6, 0, 0.4))
        bpy.context.object.name = n
    for n in names:
        bpy.data.objects[n].select_set(n in ("SM_Chair", "SM_Lamp", "SM_Plant"))
    bpy.context.view_layer.objects.active = bpy.data.objects["SM_Lamp"]
    area = view3d_area()
    win_rgn = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=win_rgn):
        bpy.ops.view3d.view_all()


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
        mod = __import__(ADDON)
        mod.register()
        setup_scene()
        for rt in REGION_TYPES:
            handles.append((rt, bpy.types.SpaceView3D.draw_handler_add(
                make_cb(rt), (), rt, 'POST_PIXEL')))
        state["step"] = 1
        return 0.5

    if s == 1:
        # active_panel_category read-only, Ctrl+Wheel gia lap khong doi duoc tab
        # -> click gia lap len dai tab (can --enable-event-simulate)
        cur = ui.active_panel_category
        log("tab hien tai:", cur)
        if cur == TAB:
            state["step"] = 2
            return 2.0
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
