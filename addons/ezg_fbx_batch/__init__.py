import bpy
import os
import json
import tempfile
import subprocess

# ---------------------------------------------------------------------------
# NGON NGU / LANGUAGE
# ---------------------------------------------------------------------------
LANG = {
    'VI': {
        'language': "Ngon ngu",
        'input_folder': "Folder FBX",
        'output_folder': "Folder Output",
        'mode': "Che do",
        'mode_separate': "Moi FBX -> 1 file .blend",
        'mode_separate_desc': "Moi file FBX thanh 1 file .blend rieng",
        'mode_single': "Gom tat ca vao 1 file .blend",
        'mode_single_desc': "Import tat ca vao 1 file, moi FBX 1 collection",
        'single_filename': "Ten file",
        'output_file': "File .blend dich",
        'single_hint': "Chon file .blend co san = them vao do; ten moi/folder = tao moi",
        'group_mode': "Gop collection",
        'gm_none': "Khong dung collection (de phang)",
        'gm_last': "Bo duoi cuoi (vd _blue, _red)",
        'gm_variant': "Bo duoi so/bien the (_Color1)",
        'gm_perfile': "Moi file 1 collection",
        'gm_all': "Tat ca vao 1 collection",
        'spread': "Dan trai cho de nhin",
        'spread_gap': "Gian cach",
        'options': "Tuy chon",
        'recursive': "Quet ca subfolder",
        'preserve_structure': "Giu cau truc folder",
        'skip_existing': "Bo qua file da co",
        'keep_textures': "Giu texture (nhung vao .blend)",
        'image_search': "Tim texture trong folder con",
        'use_anim': "Import animation",
        'auto_bone': "Auto bone orientation",
        'scale': "Scale",
        'bake_transform': "Apply transform (thu nghiem)",
        'convert': "CONVERT",
        'running': "Dang chay...",
        'processing': "Dang xu ly:",
        'last_ok': "Lan truoc: OK",
        'last_errors': "Lan truoc: %d loi",
        'err_input': "Folder FBX khong hop le.",
        'err_output': "Chua chon folder output.",
        'err_nofbx': "Khong tim thay file .fbx nao.",
        'warn_running': "Dang chay, doi xong da.",
        'warn_allskip': "Tat ca file da co san (bo qua het).",
        'err_blender': "Khong chay duoc Blender nen: %s",
        'done_ok': "Xong %d/%d file.",
        'done_err': "Xong nhung co %d loi (xem System Console).",
    },
    'EN': {
        'language': "Language",
        'input_folder': "FBX Folder",
        'output_folder': "Output Folder",
        'mode': "Mode",
        'mode_separate': "Each FBX -> one .blend",
        'mode_separate_desc': "Convert each FBX file into its own .blend file",
        'mode_single': "All into one .blend",
        'mode_single_desc': "Import everything into one file, one collection per FBX",
        'single_filename': "File name",
        'output_file': "Target .blend file",
        'single_hint': "Existing .blend = add into it; new name/folder = create new",
        'group_mode': "Group collections",
        'gm_none': "No collections (flat)",
        'gm_last': "Strip last suffix (e.g. _blue, _red)",
        'gm_variant': "Strip number/variant (_Color1)",
        'gm_perfile': "One collection per file",
        'gm_all': "Everything in one collection",
        'spread': "Spread out for visibility",
        'spread_gap': "Gap",
        'options': "Options",
        'recursive': "Scan subfolders",
        'preserve_structure': "Keep folder structure",
        'skip_existing': "Skip existing files",
        'keep_textures': "Keep textures (pack into .blend)",
        'image_search': "Search textures in subfolders",
        'use_anim': "Import animation",
        'auto_bone': "Auto bone orientation",
        'scale': "Scale",
        'bake_transform': "Apply transform (experimental)",
        'convert': "CONVERT",
        'running': "Running...",
        'processing': "Processing:",
        'last_ok': "Last run: OK",
        'last_errors': "Last run: %d errors",
        'err_input': "Invalid FBX folder.",
        'err_output': "No output folder selected.",
        'err_nofbx': "No .fbx files found.",
        'warn_running': "Already running, please wait.",
        'warn_allskip': "All files already exist (all skipped).",
        'err_blender': "Cannot launch background Blender: %s",
        'done_ok': "Done %d/%d files.",
        'done_err': "Done with %d errors (see System Console).",
    },
}


def L(context):
    try:
        return LANG.get(context.scene.fbx_converter.language, LANG['VI'])
    except Exception:
        return LANG['VI']


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
    # import vao scene roi don object moi sang collection rieng
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
            bpy.ops.wm.open_mainfile(filepath=dst)   # import vao file co san
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
_running = False
_progress = {"done": 0, "total": 0, "current": "", "errors": [], "finished": False, "ok": True}
_enum_cache = {}


def mode_items(self, context):
    lang = getattr(self, "language", "VI")
    d = LANG.get(lang, LANG['VI'])
    items = [
        ('SEPARATE', d['mode_separate'], d['mode_separate_desc']),
        ('SINGLE', d['mode_single'], d['mode_single_desc']),
    ]
    _enum_cache[lang] = items  # giu reference tranh crash GC
    return _enum_cache[lang]


# ---------------------------------------------------------------------------
# PROPERTIES
# ---------------------------------------------------------------------------
class FBXCONV_Props(bpy.types.PropertyGroup):
    language: bpy.props.EnumProperty(
        name="",
        items=[('VI', "Tieng Viet", ""), ('EN', "English", "")],
        default='VI')
    input_folder: bpy.props.StringProperty(subtype='DIR_PATH')
    output_folder: bpy.props.StringProperty(subtype='DIR_PATH')
    mode: bpy.props.EnumProperty(items=mode_items)  # dong / dynamic theo ngon ngu
    single_filename: bpy.props.StringProperty(default="library.blend")
    output_file: bpy.props.StringProperty(subtype='FILE_PATH')
    spread: bpy.props.BoolProperty(default=True)
    spread_gap: bpy.props.FloatProperty(default=1.5, min=1.0, max=10.0)
    recursive: bpy.props.BoolProperty(default=False)
    preserve_structure: bpy.props.BoolProperty(default=True)
    skip_existing: bpy.props.BoolProperty(default=True)
    pack: bpy.props.BoolProperty(default=True)          # giu texture: nhung vao .blend
    use_image_search: bpy.props.BoolProperty(default=True)
    use_anim: bpy.props.BoolProperty(default=True)
    automatic_bone_orientation: bpy.props.BoolProperty(default=True)
    bake_space_transform: bpy.props.BoolProperty(default=False)
    global_scale: bpy.props.FloatProperty(default=1.0, min=0.0001, max=1000.0)


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
    bl_label = "Convert"

    _timer = None
    _proc = None
    _progress_path = None

    def invoke(self, context, event):
        global _running, _progress
        d = L(context)
        if _running:
            self.report({'WARNING'}, d['warn_running'])
            return {'CANCELLED'}

        props = context.scene.fbx_converter
        in_dir = bpy.path.abspath(props.input_folder)
        out_dir = bpy.path.abspath(props.output_folder)

        if not in_dir or not os.path.isdir(in_dir):
            self.report({'ERROR'}, d['err_input'])
            return {'CANCELLED'}

        if props.mode == 'SEPARATE':
            if not props.output_folder.strip():
                self.report({'ERROR'}, d['err_output'])
                return {'CANCELLED'}
        else:
            if not props.output_file.strip():
                self.report({'ERROR'}, d['err_output'])
                return {'CANCELLED'}

        files = enumerate_fbx(in_dir, props.recursive)
        if not files:
            self.report({'ERROR'}, d['err_nofbx'])
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
                self.report({'WARNING'}, d['warn_allskip'])
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
        self._progress_path = os.path.join(tmpdir, "progress.json")
        cfg["progress_file"] = self._progress_path

        with open(worker_path, "w", encoding="utf-8") as f:
            f.write(WORKER)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        cmd = [bpy.app.binary_path, "--background", "--factory-startup",
               "--python", worker_path, "--", config_path]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.report({'ERROR'}, d['err_blender'] % e)
            return {'CANCELLED'}

        total = len(cfg.get("jobs", cfg.get("srcs", [])))
        _progress = {"done": 0, "total": total, "current": "",
                     "errors": [], "finished": False, "ok": True}
        _running = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _running, _progress
        d = L(context)
        if event.type == 'TIMER':
            try:
                with open(self._progress_path, "r", encoding="utf-8") as f:
                    _progress = json.load(f)
            except Exception:
                pass
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            if self._proc.poll() is not None:
                self._finish(context)
                errs = _progress.get("errors", [])
                if _progress.get("ok", False) and not errs:
                    self.report({'INFO'}, d['done_ok'] %
                                (_progress.get("done", 0), _progress.get("total", 0)))
                else:
                    self.report({'WARNING'}, d['done_err'] % len(errs))
                    for e in errs[:20]:
                        print("[FBXConv]", e)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def _finish(self, context):
        global _running
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        _running = False


# ---------------------------------------------------------------------------
# PANEL
# ---------------------------------------------------------------------------
class FBXCONV_PT_panel(bpy.types.Panel):
    bl_label = "FBX -> Blend"
    bl_idname = "FBXCONV_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "FBX Convert"

    def draw(self, context):
        layout = self.layout
        props = context.scene.fbx_converter
        d = L(context)

        layout.label(text=d['language'] + ":")
        layout.prop(props, "language", text="")

        layout.separator()
        layout.prop(props, "mode", text=d['mode'])

        col = layout.column(align=True)
        col.prop(props, "input_folder", text=d['input_folder'])
        if props.mode == 'SINGLE':
            col.prop(props, "output_file", text=d['output_file'])
        else:
            col.prop(props, "output_folder", text=d['output_folder'])

        if props.mode == 'SINGLE':
            layout.label(text=d['single_hint'], icon='INFO')
            layout.prop(props, "spread", text=d['spread'])
            if props.spread:
                layout.prop(props, "spread_gap", text=d['spread_gap'])
        else:
            layout.prop(props, "preserve_structure", text=d['preserve_structure'])
            layout.prop(props, "skip_existing", text=d['skip_existing'])

        box = layout.box()
        box.label(text=d['options'], icon='PREFERENCES')
        box.prop(props, "recursive", text=d['recursive'])
        box.prop(props, "pack", text=d['keep_textures'])
        box.prop(props, "use_image_search", text=d['image_search'])
        box.prop(props, "use_anim", text=d['use_anim'])
        box.prop(props, "automatic_bone_orientation", text=d['auto_bone'])
        box.prop(props, "global_scale", text=d['scale'])
        box.prop(props, "bake_space_transform", text=d['bake_transform'])

        layout.separator()
        if _running:
            layout.label(text="%s %d/%d" % (
                d['processing'], _progress.get("done", 0), _progress.get("total", 0)))
            cur = _progress.get("current", "")
            if cur:
                layout.label(text=cur, icon='FILE')
            r = layout.row()
            r.enabled = False
            r.operator("fbxconv.convert", text=d['running'])
        else:
            layout.operator("fbxconv.convert", text=d['convert'], icon='PLAY')
            if _progress.get("finished"):
                errs = _progress.get("errors", [])
                if errs:
                    layout.label(text=d['last_errors'] % len(errs), icon='ERROR')
                else:
                    layout.label(text=d['last_ok'], icon='CHECKMARK')


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------
classes = (FBXCONV_Props, FBXCONV_OT_convert, FBXCONV_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.fbx_converter = bpy.props.PointerProperty(type=FBXCONV_Props)


def unregister():
    del bpy.types.Scene.fbx_converter
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
