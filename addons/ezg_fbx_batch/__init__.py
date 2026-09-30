import bpy
import os
import json
import tempfile
import subprocess
import traceback

from . import ezg_i18n
from .ezg_i18n import tr

# ---------------------------------------------------------------------------
# WORKER SCRIPT (chay boi tien trinh Blender rieng --background)
# ---------------------------------------------------------------------------
WORKER = r'''
import bpy, sys, json, os

argv = sys.argv[sys.argv.index("--") + 1:]
config_path = argv[0]
with open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

opts = cfg["options"]
progress_path = cfg["progress_file"]

try:
    bpy.ops.preferences.addon_enable(module="io_scene_fbx")
except Exception:
    pass


def write_progress(done, total, current="", errors=None, finished=False, ok=True):
    data = {"done": done, "total": total, "current": current,
            "errors": errors or [], "finished": finished, "ok": ok}
    try:
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_into_new_collection(name, path):
    # import into the scene, then move the new objects to their own collection
    before = set(bpy.data.objects)
    import_fbx(path)
    new_objs = [o for o in bpy.data.objects if o not in before]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    for o in new_objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)


def import_fbx(path):
    kwargs = {
        "filepath": path,
        "global_scale": opts.get("global_scale", 1.0),
        "use_anim": opts.get("use_anim", True),
        "automatic_bone_orientation": opts.get("automatic_bone_orientation", True),
        "use_image_search": opts.get("use_image_search", True),
    }
    if opts.get("bake_space_transform", False):
        kwargs["bake_space_transform"] = True
    bpy.ops.import_scene.fbx(**kwargs)


def do_pack():
    if opts.get("pack", True):
        try:
            bpy.ops.file.pack_all()
        except Exception:
            pass


def save_blend(dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=dst)


def spread_groups(group_objs, gap):
    import math
    import numpy as np
    keys = list(group_objs.keys())
    n = len(keys)
    if n <= 1:
        return
    bpy.context.view_layer.update()
    step = 0.0
    for objs in group_objs.values():
        for o in objs:
            if o.type == 'MESH':
                step = max(step, o.dimensions.x, o.dimensions.y)
    step = (step or 1.0) * gap
    cols = max(1, int(math.ceil(math.sqrt(n))))
    done = set()
    for idx, key in enumerate(keys):
        ox = (idx % cols - (cols - 1) / 2.0) * step
        oy = (idx // cols) * -step
        for o in group_objs[key]:
            if o.type != 'MESH' or o.data is None or o.data.name in done:
                continue
            done.add(o.data.name)
            m = o.data
            arr = np.empty(len(m.vertices) * 3, dtype=np.float32)
            m.vertices.foreach_get('co', arr)
            arr[0::3] += ox
            arr[1::3] += oy
            m.vertices.foreach_set('co', arr)
            m.update()


errors = []
mode = cfg["mode"]

try:
    if mode == "SEPARATE":
        jobs = cfg["jobs"]
        total = len(jobs)
        write_progress(0, total)
        for i, job in enumerate(jobs):
            src, dst = job["src"], job["dst"]
            name = os.path.basename(src)
            write_progress(i, total, name, errors)
            try:
                reset_scene()
                import_fbx(src)
                do_pack()
                save_blend(dst)
            except Exception as e:
                errors.append("%s: %s" % (name, e))
            write_progress(i + 1, total, name, errors)
        write_progress(total, total, "", errors, finished=True, ok=(len(errors) == 0))

    else:  # SINGLE
        srcs = cfg["srcs"]
        dst = cfg["dst"]
        open_existing = cfg.get("open_existing", False)
        spread = cfg.get("spread", True)
        gap = cfg.get("spread_gap", 1.5)
        total = len(srcs)
        write_progress(0, total)
        if open_existing:
            bpy.ops.wm.open_mainfile(filepath=dst)   # import into the existing file
        else:
            reset_scene()

        spread_map = {}
        for i, src in enumerate(srcs):
            name = os.path.basename(src)
            stem = os.path.splitext(name)[0]
            skey = stem.rsplit('_', 1)[0] if '_' in stem else stem
            write_progress(i, total, name, errors)
            try:
                before = set(bpy.data.objects)
                import_fbx(src)
                new_objs = [o for o in bpy.data.objects if o not in before]
                spread_map.setdefault(skey, []).extend(new_objs)
            except Exception as e:
                errors.append("%s: %s" % (name, e))
            write_progress(i + 1, total, name, errors)

        if spread:
            spread_groups(spread_map, gap)
        do_pack()
        save_blend(dst)
        write_progress(total, total, "", errors, finished=True, ok=(len(errors) == 0))

except Exception as e:
    errors.append("FATAL: %s" % e)
    write_progress(0, 0, "", errors, finished=True, ok=False)
'''


# ---------------------------------------------------------------------------
# TRANG THAI (module-level) cho Panel
# ---------------------------------------------------------------------------
_progress = {"done": 0, "total": 0, "current": "", "errors": [], "finished": False, "ok": True}
_enum_cache = {}

# Tien trinh Blender nen dang convert. Giu o cap module, KHONG tren operator:
# Blender huy modal khi mo file khac / dong cua so, nhung tien trinh van chay
# tiep va van phai duoc theo doi - khong thi panel bao xong trong khi file con
# dang ghi, va nut convert cho chay chong lan hai.
_proc = None
_progress_path = None
_modal_timer = None   # timer cua modal bao ket qua, giu de unregister go duoc
_modal_alive = False  # modal bao ket qua con song (Blender huy no khi mo file khac)


def _conversion_alive():
    return _proc is not None and _proc.poll() is None


def _read_progress():
    global _progress
    if not _progress_path:
        return
    try:
        with open(_progress_path, "r", encoding="utf-8") as f:
            _progress = json.load(f)
    except Exception:
        pass  # worker dang ghi do, lan sau doc lai


def _finalize():
    """Chot ket qua khi tien trinh nen da thoat. Watcher va modal deu goi, ai
    toi truoc lam; lan sau _proc da la None nen khong lam lai."""
    global _proc
    if _proc is None or _proc.poll() is None:
        return
    code = _proc.returncode
    _proc = None
    _read_progress()
    if not _progress.get("finished"):
        # Worker chet ma khong kip ghi ket qua (crash, bi kill...): truoc day
        # truong hop nay bi bao "Xong 0/N file" nhu thanh cong.
        errors = list(_progress.get("errors", []))
        errors.append(tr("Blender nền dừng giữa chừng (mã thoát %s)",
                         "Background Blender stopped early (exit code %s)") % code)
        _progress.update(errors=errors, finished=True, ok=False)
    for e in _progress.get("errors", [])[:20]:
        print("[FBXConv]", e)


def _redraw_views():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _watch():
    """Timer song qua lan mo file: cap nhat tien do cho panel toi khi tien trinh
    nen xong, ke ca khi Blender da huy modal."""
    _read_progress()
    _finalize()
    try:
        _redraw_views()
    except Exception:
        pass
    return 0.5 if _proc is not None else None


def _start_watch():
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=0.5, persistent=True)


def _stop_modal(wm):
    """Go timer cua modal va ha co. Goi o MOI loi ra cua modal: xong, loi,
    cancel, unregister. Tien trinh nen (neu con) van do _watch theo doi."""
    global _modal_timer, _modal_alive
    _modal_alive = False
    timer, _modal_timer = _modal_timer, None
    if timer is not None and wm is not None:
        try:
            wm.event_timer_remove(timer)
        except Exception:
            pass


def ezg_i18n_busy():
    """ezg_i18n goi truoc khi doi ngon ngu: con convert (hoac modal con song)
    thi hoan, vi go class cua modal dang chay la Blender co the crash."""
    return _modal_alive or _conversion_alive()


def mode_items(self, context):
    # Moi ngon ngu tao list MOT lan roi giu mai trong cache: Blender khong tu giu
    # tham chieu toi chuoi tra ve tu callback -> chu rac hoac crash.
    lang = ezg_i18n.lang()
    items = _enum_cache.get(lang)
    if items is None:
        items = _enum_cache[lang] = [
            ('SEPARATE', tr("Mỗi FBX -> 1 file .blend", "Each FBX -> One .blend"),
             tr("Mỗi file FBX thành 1 file .blend riêng",
                "Convert each FBX file into its own .blend file")),
            ('SINGLE', tr("Gom tất cả vào 1 file .blend", "All Into One .blend"),
             tr("Import tất cả vào 1 file, mỗi FBX 1 collection",
                "Import everything into one file, one collection per FBX")),
        ]
    return items


# ---------------------------------------------------------------------------
# PROPERTIES
# ---------------------------------------------------------------------------
class FBXCONV_Props(bpy.types.PropertyGroup):
    input_folder: bpy.props.StringProperty(name=tr("Thư mục FBX", "FBX Folder"),
                                           subtype='DIR_PATH')
    output_folder: bpy.props.StringProperty(name=tr("Thư mục xuất", "Output Folder"),
                                            subtype='DIR_PATH')
    mode: bpy.props.EnumProperty(name=tr("Chế độ", "Mode"), items=mode_items)
    single_filename: bpy.props.StringProperty(name=tr("Tên file", "File Name"),
                                              default="library.blend")
    output_file: bpy.props.StringProperty(name=tr("File .blend đích", "Target .blend File"),
                                          subtype='FILE_PATH')
    spread: bpy.props.BoolProperty(name=tr("Dàn trải cho dễ nhìn", "Spread Out for Visibility"),
                                   default=True)
    spread_gap: bpy.props.FloatProperty(name=tr("Giãn cách", "Gap"),
                                        default=1.5, min=1.0, max=10.0)
    recursive: bpy.props.BoolProperty(name=tr("Quét cả thư mục con", "Scan Subfolders"),
                                      default=False)
    preserve_structure: bpy.props.BoolProperty(name=tr("Giữ cấu trúc thư mục",
                                                       "Keep Folder Structure"),
                                               default=True)
    skip_existing: bpy.props.BoolProperty(name=tr("Bỏ qua file đã có", "Skip Existing Files"),
                                          default=True)
    pack: bpy.props.BoolProperty(name=tr("Giữ texture (nhúng vào .blend)",
                                         "Keep Textures (Pack into .blend)"),
                                 default=True)
    use_image_search: bpy.props.BoolProperty(name=tr("Tìm texture trong thư mục con",
                                                     "Search Textures in Subfolders"),
                                             default=True)
    use_anim: bpy.props.BoolProperty(name="Import Animation",  # i18n-skip
                                     default=True)
    automatic_bone_orientation: bpy.props.BoolProperty(name="Auto Bone Orientation",  # i18n-skip
                                                       default=True)
    bake_space_transform: bpy.props.BoolProperty(name=tr("Apply transform (thử nghiệm)",
                                                         "Apply Transform (Experimental)"),
                                                 default=False)
    global_scale: bpy.props.FloatProperty(name="Scale",  # i18n-skip
                                          default=1.0, min=0.0001, max=1000.0)


# ---------------------------------------------------------------------------
# HELPER
# ---------------------------------------------------------------------------
def enumerate_fbx(root, recursive):
    out = []
    if recursive:
        for dp, _, fnames in os.walk(root):
            for f in fnames:
                if f.lower().endswith(".fbx"):
                    out.append(os.path.join(dp, f))
    else:
        for f in os.listdir(root):
            p = os.path.join(root, f)
            if os.path.isfile(p) and f.lower().endswith(".fbx"):
                out.append(p)
    return sorted(out)


# ---------------------------------------------------------------------------
# OPERATOR
# ---------------------------------------------------------------------------
class FBXCONV_OT_convert(bpy.types.Operator):
    bl_idname = "fbxconv.convert"
    bl_label = tr("Chuyển đổi", "Convert")
    bl_description = tr("Chuyển hàng loạt file FBX trong thư mục sang .blend "
                        "(chạy bằng một Blender nền)",
                        "Batch-convert the FBX files in the folder to .blend "
                        "(runs in a background Blender)")

    def invoke(self, context, event):
        global _progress, _modal_timer, _modal_alive, _proc, _progress_path
        _finalize()  # lan truoc da xong ma watcher chua kip chot
        if _conversion_alive():
            self.report({'WARNING'}, tr("Đang chạy, đợi xong đã.", "Already running, please wait."))
            return {'CANCELLED'}

        props = context.scene.fbx_converter
        in_dir = bpy.path.abspath(props.input_folder)
        out_dir = bpy.path.abspath(props.output_folder)

        if not in_dir or not os.path.isdir(in_dir):
            self.report({'ERROR'}, tr("Thư mục FBX không hợp lệ.", "Invalid FBX folder."))
            return {'CANCELLED'}

        if props.mode == 'SEPARATE':
            if not props.output_folder.strip():
                self.report({'ERROR'}, tr("Chưa chọn thư mục xuất.", "No output folder selected."))
                return {'CANCELLED'}
        else:
            if not props.output_file.strip():
                self.report({'ERROR'}, tr("Chưa chọn file .blend đích.",
                                          "No target .blend file selected."))
                return {'CANCELLED'}

        files = enumerate_fbx(in_dir, props.recursive)
        if not files:
            self.report({'ERROR'}, tr("Không tìm thấy file .fbx nào.", "No .fbx files found."))
            return {'CANCELLED'}

        options = {
            "global_scale": props.global_scale,
            "use_anim": props.use_anim,
            "automatic_bone_orientation": props.automatic_bone_orientation,
            "bake_space_transform": props.bake_space_transform,
            "pack": props.pack,
            "use_image_search": props.use_image_search,
        }
        cfg = {"mode": props.mode, "options": options}

        if props.mode == 'SEPARATE':
            jobs = []
            for src in files:
                if props.preserve_structure:
                    rel = os.path.relpath(src, in_dir)
                    dst = os.path.join(out_dir, os.path.splitext(rel)[0] + ".blend")
                else:
                    base = os.path.splitext(os.path.basename(src))[0]
                    dst = os.path.join(out_dir, base + ".blend")
                if props.skip_existing and os.path.exists(dst):
                    continue
                jobs.append({"src": src, "dst": dst})
            if not jobs:
                self.report({'WARNING'}, tr("Tất cả file đã có sẵn (bỏ qua hết).",
                                            "All files already exist (all skipped)."))
                return {'CANCELLED'}
            cfg["jobs"] = jobs
        else:
            out_file = bpy.path.abspath(props.output_file).strip()
            if os.path.isdir(out_file):
                out_file = os.path.join(out_file, "library.blend")
            elif not out_file.lower().endswith(".blend"):
                out_file += ".blend"
            cfg["dst"] = out_file
            cfg["open_existing"] = os.path.isfile(out_file)
            cfg["spread"] = props.spread
            cfg["spread_gap"] = props.spread_gap
            cfg["srcs"] = files

        tmpdir = tempfile.mkdtemp(prefix="fbxconv_")
        worker_path = os.path.join(tmpdir, "worker.py")
        config_path = os.path.join(tmpdir, "config.json")
        progress_path = os.path.join(tmpdir, "progress.json")
        cfg["progress_file"] = progress_path

        with open(worker_path, "w", encoding="utf-8") as f:
            f.write(WORKER)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        cmd = [bpy.app.binary_path, "--background", "--factory-startup",
               "--python", worker_path, "--", config_path]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.report({'ERROR'}, tr("Không chạy được Blender nền: %s",
                                      "Could not launch background Blender: %s") % e)
            return {'CANCELLED'}

        total = len(cfg.get("jobs", cfg.get("srcs", [])))
        _progress = {"done": 0, "total": total, "current": "",
                     "errors": [], "finished": False, "ok": True}
        _proc, _progress_path = proc, progress_path
        _start_watch()

        # Modal chi con lo bao ket qua len thanh trang thai; theo doi tien do
        # la viec cua _watch, nen modal co bi huy thi viec convert van dung.
        wm = context.window_manager
        _modal_timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        _modal_alive = True   # chi bat SAU khi modal da vao hang doi
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER' or _conversion_alive():
            return {'PASS_THROUGH'}
        try:
            _finalize()  # _watch co the da chot truoc; goi lai vo hai
            _stop_modal(context.window_manager)
            errs = _progress.get("errors", [])
            if _progress.get("ok", False) and not errs:
                self.report({'INFO'}, tr("Xong %d/%d file.", "Done: %d/%d files.") %
                            (_progress.get("done", 0), _progress.get("total", 0)))
            else:
                self.report({'WARNING'}, tr("Xong nhưng có %d lỗi (xem System Console).",
                                            "Done with %d errors (see System Console).")
                            % len(errs))
            return {'FINISHED'}
        except Exception:
            # Loi giua chung: Blender bo modal ma khong goi cancel() -> tu don,
            # khong thi _modal_alive (va ezg_i18n_busy) ket o True mai.
            traceback.print_exc()
            _stop_modal(context.window_manager)
            self.report({'ERROR'}, tr("Lỗi khi theo dõi tiến trình (xem System Console).",
                                      "Error while tracking the conversion (see System Console)."))
            return {'CANCELLED'}

    def cancel(self, context):
        # Blender huy modal (mo file khac, dong cua so...). Tien trinh nen van
        # chay: _watch theo doi tiep, nut convert van bi chan toi khi no xong.
        _stop_modal(getattr(context, "window_manager", None))


# ---------------------------------------------------------------------------
# PANEL
# ---------------------------------------------------------------------------
class FBXCONV_PT_panel(bpy.types.Panel):
    bl_label = "FBX -> Blend"  # i18n-skip
    bl_idname = "FBXCONV_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "FBX Convert"

    def draw_header_preset(self, context):
        ezg_i18n.draw_toggle(self.layout, "fbxconv")

    def draw(self, context):
        layout = self.layout
        props = context.scene.fbx_converter

        # Nhan cua cac property lay tu name=tr(...) trong FBXCONV_Props.
        layout.prop(props, "mode")

        col = layout.column(align=True)
        col.prop(props, "input_folder")
        if props.mode == 'SINGLE':
            col.prop(props, "output_file")
        else:
            col.prop(props, "output_folder")

        if props.mode == 'SINGLE':
            layout.label(text=tr("Chọn file .blend có sẵn = thêm vào đó; tên mới/thư mục = tạo mới",
                                 "Existing .blend = add into it; new name/folder = create new"),
                         icon='INFO')
            layout.prop(props, "spread")
            if props.spread:
                layout.prop(props, "spread_gap")
        else:
            layout.prop(props, "preserve_structure")
            layout.prop(props, "skip_existing")

        box = layout.box()
        box.label(text=tr("Tuỳ chọn", "Options"), icon='PREFERENCES')
        box.prop(props, "recursive")
        box.prop(props, "pack")
        box.prop(props, "use_image_search")
        box.prop(props, "use_anim")
        box.prop(props, "automatic_bone_orientation")
        box.prop(props, "global_scale")
        box.prop(props, "bake_space_transform")

        layout.separator()
        if _conversion_alive():
            layout.label(text=tr("Đang xử lý: %d/%d", "Processing: %d/%d") % (
                _progress.get("done", 0), _progress.get("total", 0)))
            cur = _progress.get("current", "")
            if cur:
                layout.label(text=cur, icon='FILE')
            r = layout.row()
            r.enabled = False
            r.operator("fbxconv.convert", text=tr("Đang chạy...", "Running..."))
        else:
            layout.operator("fbxconv.convert", text=tr("CHUYỂN ĐỔI", "CONVERT"), icon='PLAY')
            if _progress.get("finished"):
                errs = _progress.get("errors", [])
                if errs:
                    layout.label(text=tr("Lần trước: %d lỗi", "Last run: %d errors") % len(errs),
                                 icon='ERROR')
                else:
                    layout.label(text=tr("Lần trước: OK", "Last run: OK"), icon='CHECKMARK')


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------
classes = (FBXCONV_Props, FBXCONV_OT_convert, FBXCONV_PT_panel,
           ezg_i18n.make_language_operator("fbxconv"))


def register():
    ezg_i18n.register_classes(classes)
    bpy.types.Scene.fbx_converter = bpy.props.PointerProperty(type=FBXCONV_Props)
    # Tat roi bat lai addon trong luc tien trinh nen van chay: theo doi tiep.
    if _conversion_alive():
        _start_watch()


def unregister():
    # Tat addon giua luc convert: Blender huy modal ma KHONG goi cancel()
    # -> tu go timer va ha co. (Doi ngon ngu thi khong toi day khi dang ban.)
    _stop_modal(getattr(bpy.context, "window_manager", None))
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
    del bpy.types.Scene.fbx_converter
    ezg_i18n.unregister_classes(classes)
