"""Song ngu Viet/Anh: nut VI/EN doi duoc MOI addon EZG ma khong mat du lieu.

CHAY BANG tools\\run_tests.ps1 (hoac: .\\tools\\run_tests.ps1 -Only test_i18n).

Dang chuyen doi tung addon thi dat EZG_I18N_ONLY=<pkg>[,<pkg>...] de chi bat
va kiem tra cac addon do.

Kiem tra:
  1. Lint tinh (tools/i18n_lint.py): chuoi tieng Viet deu boc tr(), ban chep
     ezg_i18n.py khop ban goc...
  2. Mac dinh la tieng Viet khi chua co file ngon ngu.
  3. Bam EN: moi addon dang ki lai; nhan, tooltip, ten property, enum va chu
     ve trong panel KHONG con dau tieng Viet nao.
  4. Du lieu (property cua Scene/WindowManager, preferences) va so handler
     giu nguyen qua cac lan doi.
  5. Addon dang ban (ezg_i18n_busy) thi hoan doi, khong go class giua chung.
"""

import atexit
import os
import sys

import bpy

REPO_ROOT = os.environ.get("EZG_REPO_ROOT")
if not REPO_ROOT:
    print("LOI: thieu bien EZG_REPO_ROOT. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)
if not os.environ.get("BLENDER_USER_RESOURCES"):
    print("LOI: chua co BLENDER_USER_RESOURCES. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import i18n_lint  # noqa: E402

ADDON_DIR = os.path.join(REPO_ROOT, "addons")
REPO_MODULE = "ezgdev"

only = [p.strip() for p in os.environ.get("EZG_I18N_ONLY", "").split(",") if p.strip()]
pkg_ids = only or i18n_lint.addon_ids()

failures = []
step = 0


def check(label, cond, detail=""):
    global step
    step += 1
    print("  [%02d] %s %s %s" % (step, "OK  " if cond else "LOI ", label, detail if not cond else ""))
    if not cond:
        failures.append(label)


def listing(items, limit=12):
    items = list(items)
    lines = ["\n        %s" % x for x in items[:limit]]
    if len(items) > limit:
        lines.append("\n        ... va %d muc nua" % (len(items) - limit))
    return "".join(lines)


# ---------------------------------------------------------------------------
print("=" * 70)
print("1) Lint tinh")
for pkg in pkg_ids:
    errors = i18n_lint.lint_addon(pkg)
    check("%s: lint song ngu" % pkg, not errors, "(%d loi)%s" % (len(errors), listing(errors)))

# ---------------------------------------------------------------------------
print("-" * 70)
print("2) Bat addon, mac dinh tieng Viet")

repos = bpy.context.preferences.extensions.repos
repo = repos.new(name="EZG Dev", module=REPO_MODULE, custom_directory=ADDON_DIR)
repo.use_custom_directory = True
repo.enabled = True

lang_file = bpy.utils.user_resource('CONFIG', path="ezg_language.txt")
if os.path.isfile(lang_file):
    os.remove(lang_file)


@atexit.register
def _cleanup():
    # Cac test sau chay chung sandbox: dung de lai 'en', ke ca khi test nay chet giua chung.
    if os.path.isfile(lang_file):
        os.remove(lang_file)


def runtime_prop_keys():
    keys = set()
    for attr in dir(bpy.types):
        rna = getattr(getattr(bpy.types, attr, None), "bl_rna", None)
        if rna is None:
            continue
        try:
            keys.update((attr, p.identifier) for p in rna.properties if p.is_runtime)
        except Exception:
            pass
    return frozenset(keys)


# Property Python co san cua Blender co chu nhu "Bézier" (é trung dau tieng Viet):
# chup truoc khi bat addon EZG de chi xet property ma addon them vao.
BLENDER_OWN = runtime_prop_keys()

mods = {}
for pkg in pkg_ids:
    name = "bl_ext.%s.%s" % (REPO_MODULE, pkg)
    try:
        bpy.ops.preferences.addon_enable(module=name)
    except Exception as exc:
        check("%s: bat duoc" % pkg, False, str(exc))
        continue
    mod = sys.modules.get(name)
    if mod is None or name not in bpy.context.preferences.addons:
        check("%s: bat duoc" % pkg, False)
        continue
    helper = getattr(mod, "ezg_i18n", None)
    if helper is None or not hasattr(helper, "request_refresh"):
        check("%s: dung ezg_i18n" % pkg, False, "(chua import ezg_i18n)")
        continue
    mods[pkg] = mod

if not mods:
    print("Khong co addon nao dung ezg_i18n de kiem tra tiep.")
    sys.exit(1)


def walk_subclasses(base):
    for sub in base.__subclasses__():
        yield sub
        yield from walk_subclasses(sub)


BASES = (bpy.types.Operator, bpy.types.Panel, bpy.types.Menu, bpy.types.UIList,
         bpy.types.PropertyGroup, bpy.types.AddonPreferences, bpy.types.Header)


def registered_classes(mod):
    seen, out = set(), []
    for base in BASES:
        for cls in walk_subclasses(base):
            if cls in seen:
                continue
            seen.add(cls)
            # bl_rna chi co trong __dict__ khi class dang duoc dang ki.
            if cls.__dict__.get("bl_rna") is not None and \
                    getattr(cls, "__module__", "").startswith(mod.__name__):
                out.append(cls)
    return out


def op_rna(cls):
    cat, name = cls.bl_idname.split(".", 1)
    return getattr(getattr(bpy.ops, cat), name).get_rna_type()


def prop_strings(rna, where):
    for p in rna.properties:
        if p.identifier == "rna_type":
            continue
        yield "%s.%s name" % (where, p.identifier), p.name
        yield "%s.%s description" % (where, p.identifier), p.description
        if p.type == 'ENUM':
            for e in p.enum_items:
                yield "%s.%s[%s]" % (where, p.identifier, e.identifier), e.name
                yield "%s.%s[%s] tip" % (where, p.identifier, e.identifier), e.description


def static_strings(mod):
    for cls in registered_classes(mod):
        if issubclass(cls, bpy.types.Operator):
            if cls.bl_idname.endswith(".ezg_language"):
                continue  # ten ngon ngu ("Tiếng Việt") co y giu nguyen
            rna = op_rna(cls)
            yield cls.bl_idname + " label", rna.name
            yield cls.bl_idname + " tooltip", rna.description
            yield from prop_strings(rna, cls.bl_idname)
        elif issubclass(cls, (bpy.types.Panel, bpy.types.Menu, bpy.types.Header)):
            yield cls.__name__ + " label", getattr(cls, "bl_label", "")
            yield cls.__name__ + " tooltip", getattr(cls, "bl_description", "") or ""
        elif issubclass(cls, (bpy.types.PropertyGroup, bpy.types.AddonPreferences)):
            yield from prop_strings(cls.bl_rna, cls.__name__)


def runtime_type_strings(exclude=frozenset()):
    """Property Python gan thang len kieu cua Blender (Scene, Object, WindowManager...)."""
    for attr in dir(bpy.types):
        rna_type = getattr(bpy.types, attr, None)
        rna = getattr(rna_type, "bl_rna", None)
        if rna is None:
            continue
        try:
            props = [p for p in rna.properties if p.is_runtime]
        except Exception:
            continue
        for p in props:
            if (attr, p.identifier) in exclude:
                continue
            yield "%s.%s name" % (attr, p.identifier), p.name
            yield "%s.%s description" % (attr, p.identifier), p.description
            if p.type == 'ENUM':
                for e in p.enum_items:
                    yield "%s.%s[%s]" % (attr, p.identifier, e.identifier), e.name
                    yield "%s.%s[%s] tip" % (attr, p.identifier, e.identifier), e.description


class FakeLayout:
    """Layout gia: ghi lai moi text=/heading= ma ham draw truyen vao."""

    def __init__(self, sink):
        object.__setattr__(self, "_sink", sink)

    def __getattr__(self, name):
        def call(*args, **kwargs):
            for key in ("text", "heading"):
                value = kwargs.get(key)
                if isinstance(value, str) and value:
                    self._sink.append(value)
            return FakeLayout(self._sink)
        return call

    def __setattr__(self, name, value):
        pass


class FakeSelf:
    def __init__(self, cls, layout):
        self._cls = cls
        self.layout = layout

    def __getattr__(self, name):
        value = getattr(self._cls, name)
        if callable(value) and not isinstance(value, type) and hasattr(value, "__get__"):
            return value.__get__(self, type(self))
        return value


def drawn_strings(mod):
    """Chu ma cac panel/menu ve ra voi context hien tai.

    Chi phu duoc nhanh ma context cua test di toi; nhanh can object dang chon,
    area... se nem loi va bi bo qua. Lint tinh lo phan con lai.
    """
    out = []
    for cls in registered_classes(mod):
        if not issubclass(cls, (bpy.types.Panel, bpy.types.Menu, bpy.types.Header)):
            continue
        for fn_name in ("draw_header", "draw_header_preset", "draw"):
            fn = cls.__dict__.get(fn_name)
            if fn is None:
                continue
            sink = []
            try:
                fn(FakeSelf(cls, FakeLayout(sink)), bpy.context)
            except Exception:
                pass
            out += [("%s.%s" % (cls.__name__, fn_name), s) for s in sink]
    return out


def vi_leaks(pairs):
    return ["%s = %r" % (where, text[:70]) for where, text in pairs
            if text and i18n_lint.has_vi(text)]


def handler_counts():
    out = {}
    for name in dir(bpy.app.handlers):
        value = getattr(bpy.app.handlers, name)
        if isinstance(value, list):
            out[name] = len(value)
    return out


def is_simple(p):
    if p.type in ('BOOLEAN', 'INT', 'FLOAT'):
        return getattr(p, "array_length", 0) == 0
    if p.type == 'ENUM':
        return not p.is_enum_flag
    return p.type == 'STRING'


def snapshot():
    """Gia tri cac property Python tren Scene/WindowManager + preferences addon."""
    out = {}
    owners = (("scene", bpy.context.scene), ("wm", bpy.context.window_manager))
    for tag, owner in owners:
        for p in owner.bl_rna.properties:
            if not p.is_runtime:
                continue
            value = getattr(owner, p.identifier, None)
            key = "%s.%s" % (tag, p.identifier)
            if p.type == 'POINTER' and value is not None:
                for sp in value.bl_rna.properties:
                    if sp.identifier != "rna_type" and is_simple(sp):
                        out["%s.%s" % (key, sp.identifier)] = getattr(value, sp.identifier)
            elif p.type == 'COLLECTION':
                out[key + " len"] = len(value)
            elif is_simple(p):
                out[key] = value
    for name, mod in mods.items():
        addon = bpy.context.preferences.addons.get(mod.__name__)
        prefs = getattr(addon, "preferences", None)
        if prefs is not None:
            for sp in prefs.bl_rna.properties:
                if sp.identifier != "rna_type" and is_simple(sp):
                    out["prefs.%s.%s" % (name, sp.identifier)] = getattr(prefs, sp.identifier)
    return out


def class_counts():
    return {pkg: len(registered_classes(mod)) for pkg, mod in mods.items()}


def switch(value):
    """Bam nut VI/EN that (operator cua addon dau tien), roi chay phan timer ngay."""
    first = next(iter(mods.values()))
    ops = [c for c in registered_classes(first) if issubclass(c, bpy.types.Operator)
           and c.bl_idname.endswith(".ezg_language")]
    cat = ops[0].bl_idname.split(".")[0]
    getattr(getattr(bpy.ops, cat), "ezg_language")(lang=value)
    # Timer khong chay trong che do background -> goi thang phan viec cua timer.
    return {pkg: mod.ezg_i18n.refresh_now(mod) for pkg, mod in mods.items()}


for pkg, mod in mods.items():
    ops = [c for c in registered_classes(mod) if issubclass(c, bpy.types.Operator)
           and c.bl_idname.endswith(".ezg_language")]
    check("%s: co dung 1 operator nut VI/EN" % pkg, len(ops) == 1, "(=%d)" % len(ops))
    check("%s: mac dinh la tieng Viet" % pkg, mod.ezg_i18n.lang() == "vi", mod.ezg_i18n.lang())
    check("%s: co ve nut VI/EN trong panel" % pkg,
          {"VI", "EN"} <= {s for _, s in drawn_strings(mod)})

# Doi vai gia tri khoi mac dinh de biet chac chung song sot qua lan dang ki lai.
# Phai lam TRUOC khi chup chuoi VI goc: doi tab thi panel ve noi dung khac.
if "ezg_addon_hub" in mods:
    hub_prefs = bpy.context.preferences.addons[mods["ezg_addon_hub"].__name__].preferences
    hub_prefs.profile_name = "i18n.user"
    bpy.context.window_manager.ezg_tab = 'BACKUP'

vi_static = {pkg: [s for _, s in static_strings(mod)] + [s for _, s in drawn_strings(mod)]
             for pkg, mod in mods.items()}
for pkg, strings in vi_static.items():
    check("%s: che do VI that su co tieng Viet" % pkg, any(i18n_lint.has_vi(s) for s in strings))

base_snapshot = snapshot()
base_handlers = handler_counts()
base_classes = class_counts()

# ---------------------------------------------------------------------------
print("-" * 70)
print("3) Bam EN")
done = switch("en")
check("file ngon ngu ghi 'en'", open(lang_file, encoding="utf-8").read().strip() == "en")
check("moi addon dang ki lai xong", all(done.values()), done)
for pkg, mod in mods.items():
    check("%s: dang o tieng Anh" % pkg, mod.ezg_i18n.lang() == "en", mod.ezg_i18n.lang())
    leaks = vi_leaks(list(static_strings(mod)) + drawn_strings(mod))
    check("%s: EN khong con chu tieng Viet" % pkg, not leaks, listing(leaks))

leaks = vi_leaks(runtime_type_strings(exclude=BLENDER_OWN))
check("property gan len kieu Blender khong con tieng Viet", not leaks, listing(leaks))
check("so class dang ki giu nguyen", class_counts() == base_classes, (class_counts(), base_classes))
check("so handler giu nguyen", handler_counts() == base_handlers)
diff = {k: (v, snapshot().get(k)) for k, v in base_snapshot.items() if snapshot().get(k) != v}
check("du lieu giu nguyen khi doi sang EN", not diff, listing("%s: %r -> %r" % (k, a, b)
                                                              for k, (a, b) in diff.items()))

# ---------------------------------------------------------------------------
print("-" * 70)
print("4) Bam VI")
done = switch("vi")
check("moi addon dang ki lai xong", all(done.values()), done)
for pkg, mod in mods.items():
    check("%s: ve tieng Viet" % pkg, mod.ezg_i18n.lang() == "vi", mod.ezg_i18n.lang())
    now = [s for _, s in static_strings(mod)] + [s for _, s in drawn_strings(mod)]
    lost = sorted(set(vi_static[pkg]) - set(now))
    extra = sorted(set(now) - set(vi_static[pkg]))
    check("%s: chuoi VI giong het truoc khi doi" % pkg, sorted(now) == sorted(vi_static[pkg]),
          listing(["mat: %r" % x for x in lost] + ["them: %r" % x for x in extra]))
check("so class dang ki giu nguyen", class_counts() == base_classes)
check("so handler giu nguyen", handler_counts() == base_handlers)
diff = {k: (v, snapshot().get(k)) for k, v in base_snapshot.items() if snapshot().get(k) != v}
check("du lieu giu nguyen khi doi ve VI", not diff, listing("%s: %r -> %r" % (k, a, b)
                                                            for k, (a, b) in diff.items()))

# ---------------------------------------------------------------------------
print("-" * 70)
print("5) Addon dang ban thi hoan doi")
pkg, mod = next(iter(mods.items()))
had_busy = hasattr(mod, "ezg_i18n_busy")
old_busy = getattr(mod, "ezg_i18n_busy", None)
mod.ezg_i18n_busy = lambda: True
mod.ezg_i18n.save_lang("en")
check("dang ban -> refresh_now tra False", mod.ezg_i18n.refresh_now(mod) is False)
check("dang ban -> chua doi ngon ngu", mod.ezg_i18n.lang() == "vi")
if had_busy:
    mod.ezg_i18n_busy = old_busy
else:
    del mod.ezg_i18n_busy
check("het ban -> doi duoc", mod.ezg_i18n.refresh_now(mod) is True and mod.ezg_i18n.lang() == "en")
done = switch("vi")
check("tra ve VI", all(done.values()) and all(m.ezg_i18n.lang() == "vi" for m in mods.values()))

print("-" * 70)
print("6) File ngon ngu hong -> ve mac dinh")
with open(lang_file, "w", encoding="utf-8") as f:
    f.write("xx")
check("gia tri la -> tieng Viet", mod.ezg_i18n.saved_lang() == "vi")

print("=" * 70)
if failures:
    print("THAT BAI %d/%d muc:" % (len(failures), step))
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("TAT CA %d KIEM TRA DEU DAT" % step)
sys.exit(0)
