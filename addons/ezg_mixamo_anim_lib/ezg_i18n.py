"""Song ngu Viet / Anh dung chung cho moi addon EZG.

BAN GOC nam o tools/ezg_i18n.py. Moi addon mang mot BAN CHEP y het o
addons/<pkg>/ezg_i18n.py, vi extension khong import cheo duoc nhau. Sua o ban
goc roi chay `python tools/sync_i18n.py`; tests/test_i18n.py bao loi neu co ban
chep lech ban goc.

Cach dung trong addon:

    from . import ezg_i18n
    from .ezg_i18n import tr

    class FOO_OT_bar(bpy.types.Operator):
        bl_label = tr("Tạo rig", "Build Rig")                # chuoi TINH
        bl_description = tr("Mô tả tiếng Việt", "English tooltip")
        size: IntProperty(name=tr("Cỡ", "Size"))

        def execute(self, context):
            self.report({'INFO'}, tr("Xong %d", "Done %d") % n)  # chuoi DONG

    classes = (..., ezg_i18n.make_language_operator("foo"))

    def register():
        ezg_i18n.register_classes(classes)

    def unregister():
        ezg_i18n.unregister_classes(classes)

    # trong draw_header_preset cua panel chinh:
    ezg_i18n.draw_toggle(self.layout, "foo")

Chuoi TINH (bl_label, bl_description, name/description/items cua property)
duoc Blender chep lai luc register_class. Vi vay doi ngon ngu = go roi dang ki
lai ca addon: request_refresh() goi addon.unregister() + addon.register()
trong mot timer. Du lieu property nam trong .blend / userpref nen khong mat.

Giao thuc giua cac addon (GIU ON DINH, addon cu va moi phai noi chuyen duoc):
  - addon_module.ezg_i18n.request_refresh(addon_module)
  - addon_module.ezg_i18n_busy()   tuy chon: True thi hoan doi ngon ngu
"""

import os
import sys
import traceback

import bpy

LANGS = ("vi", "en")
DEFAULT_LANG = "vi"

# Mot file cho MOI addon EZG: bam VI/EN o addon nao cung doi het.
FILE_NAME = "ezg_language.txt"

# Ngon ngu ma cac class cua CHINH addon nay dang duoc dang ki. Moi addon co ban
# chep rieng nen co bien rieng; request_refresh() dua no ve gia tri trong file.
_lang = None

_SOURCE_ATTR = "_ezg_i18n_source"
_TEXT_ATTRS = ("bl_label", "bl_description")


# ---------------------------------------------------------------------------
# Ngon ngu dang dung
# ---------------------------------------------------------------------------

def settings_path():
    return bpy.utils.user_resource('CONFIG', path=FILE_NAME)


def saved_lang():
    """Ngon ngu trong file dung chung; thieu file hoac hong thi la DEFAULT_LANG."""
    try:
        with open(settings_path(), encoding="utf-8") as f:
            value = f.read().strip().lower()
    except OSError:
        return DEFAULT_LANG
    return value if value in LANGS else DEFAULT_LANG


def save_lang(value):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)


def lang():
    global _lang
    if _lang is None:
        _lang = saved_lang()
    return _lang


# ---------------------------------------------------------------------------
# Chuoi song ngu
# ---------------------------------------------------------------------------

class Text(str):
    """Chuoi mang ca hai ban dich. Gia tri str la ban cua ngon ngu luc tao ra.

    Dung duoc ngay nhu str thuong (label, report, % format...). Rieng chuoi tinh
    trong than class thi localize() doc lai .vi/.en truoc moi lan dang ki.
    """

    def __new__(cls, vi, en):
        obj = super().__new__(cls, en if lang() == "en" else vi)
        obj.vi = vi
        obj.en = en
        return obj

    def current(self):
        return self.en if lang() == "en" else self.vi


def tr(vi, en):
    """Chon ban dich theo ngon ngu dang dung. Tham so dau LUON la tieng Viet."""
    return Text(vi, en)


def _resolve(value):
    if isinstance(value, Text):
        return value.current()
    if isinstance(value, (list, tuple)):
        return type(value)(_resolve(v) for v in value)
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    return value


def _has_text(value):
    if isinstance(value, Text):
        return True
    if isinstance(value, (list, tuple)):
        return any(_has_text(v) for v in value)
    if isinstance(value, dict):
        return any(_has_text(v) for v in value.values())
    return False


def localize(cls):
    """Dien ngon ngu hien tai vao chuoi tinh cua class. Goi NGAY TRUOC register_class.

    Lan dau goi thi chup lai ban goc (co ca hai ngon ngu) de cac lan sau van dich
    lai duoc, vi gia tri tren class se bi ghi de bang str thuong.
    """
    source = cls.__dict__.get(_SOURCE_ATTR)
    if source is None:
        annotations = cls.__dict__.get("__annotations__", {})
        source = {
            "attrs": {a: getattr(cls, a) for a in _TEXT_ATTRS
                      if isinstance(getattr(cls, a, None), Text)},
            "props": {name: d for name, d in annotations.items()
                      if _has_text(getattr(d, "keywords", None))},
        }
        setattr(cls, _SOURCE_ATTR, source)

    for attr, text in source["attrs"].items():
        setattr(cls, attr, text.current())

    annotations = cls.__dict__.get("__annotations__")
    for name, deferred in source["props"].items():
        annotations[name] = deferred.function(**_resolve(deferred.keywords))
    return cls


def register_classes(classes):
    for cls in classes:
        localize(cls)
        bpy.utils.register_class(cls)


def unregister_classes(classes):
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as exc:
            # Nuot im lang thi lan dang ki sau chet voi "already registered"
            # ma khong ai biet vi sao.
            print("[EZG i18n] Khong go duoc %s: %s" % (cls.__name__, exc))


# ---------------------------------------------------------------------------
# Doi ngon ngu
# ---------------------------------------------------------------------------

def ezg_addon_modules():
    """Module cua moi addon EZG dang bat (ca extension lan addon cai tay)."""
    for name in bpy.context.preferences.addons.keys():
        if name.rsplit(".", 1)[-1].startswith("ezg_"):
            mod = sys.modules.get(name)
            if mod is not None:
                yield mod


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for win in getattr(wm, "windows", ()):
        for area in win.screen.areas:
            area.tag_redraw()


def refresh_now(mod):
    """Dang ki lai addon `mod` bang ngon ngu trong file.

    True: xong, hoac khong can lam gi. False: addon dang ban, goi lai sau.
    """
    global _lang
    target = saved_lang()
    if target == lang():
        return True
    if mod.__name__ not in bpy.context.preferences.addons:
        return True  # addon da bi tat trong luc cho

    busy = getattr(mod, "ezg_i18n_busy", None)
    if busy is not None and busy():
        return False

    mod.unregister()
    _lang = target
    try:
        mod.register()
    except Exception:
        traceback.print_exc()
        print("[EZG i18n] Dang ki lai %s that bai." % mod.__name__)
    _redraw()
    return True


def request_refresh(mod):
    """Hen dang ki lai `mod` trong timer.

    Khong lam ngay duoc: nut VI/EN la operator cua chinh addon, go class cua
    mot operator dang chay la Blender co the crash.
    """
    def tick():
        try:
            return None if refresh_now(mod) else 0.5
        except Exception:
            traceback.print_exc()
            return None

    bpy.app.timers.register(tick, first_interval=0.0)


def set_language(value):
    """Luu ngon ngu va bao moi addon EZG dang bat doi theo."""
    if value not in LANGS:
        return
    save_lang(value)
    for mod in ezg_addon_modules():
        helper = getattr(mod, "ezg_i18n", None)
        request = getattr(helper, "request_refresh", None)
        if request is not None:
            request(mod)


def make_language_operator(prefix):
    """Operator '<prefix>.ezg_language' cho nut VI/EN cua mot addon.

    Moi addon can idname rieng: dung chung mot idname thi tat addon nay se go
    mat nut cua addon kia.
    """
    def execute(self, context):
        set_language(self.lang)
        return {'FINISHED'}

    return type("%s_OT_ezg_language" % prefix.upper(), (bpy.types.Operator,), {
        "bl_idname": "%s.ezg_language" % prefix,
        "bl_label": tr("Ngôn ngữ", "Language"),
        "bl_description": tr("Đổi ngôn ngữ cho mọi addon EZG",
                             "Switch the language of every EZG add-on"),
        "bl_options": {'INTERNAL'},
        "__annotations__": {
            "lang": bpy.props.EnumProperty(items=[
                ("vi", "Tiếng Việt", ""),
                ("en", "English", ""),
            ]),
        },
        "execute": execute,
    })


def draw_toggle(layout, prefix):
    """Cap nut VI | EN; nut cua ngon ngu dang dung duoc an xuong."""
    row = layout.row(align=True)
    current = lang()
    for code, label in (("vi", "VI"), ("en", "EN")):
        op = row.operator("%s.ezg_language" % prefix, text=label, depress=(current == code))
        op.lang = code
