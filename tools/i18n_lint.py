"""Kiem tra tinh cho song ngu Viet/Anh cua addon EZG. Khong can Blender.

    <blender>/4.5/python/bin/python.exe tools/i18n_lint.py              # moi addon
    <blender>/4.5/python/bin/python.exe tools/i18n_lint.py ezg_deco_namer

Luat (xem docs/I18N.md):
  1. Chuoi co dau tieng Viet chi duoc nam o tham so DAU cua tr(), trong print(),
     hoac trong docstring. Nam cho khac nghia la che do EN van hien tieng Viet.
  2. tr() nhan dung 2 tham so vi tri; tham so thu hai (EN) khong duoc co dau.
  3. Hai ban dich cua mot tr() phai co cung placeholder (%d, %s, {}...):
     lech nhau thi chi mot ngon ngu nem TypeError luc chay.
  4. Chuoi tieng Viet KHONG DAU (kieu cu) khong duoc con sot.
  5. Chuoi chu tai cho giao dien (text=, name=/description= cua property,
     bl_label, report, poll_message_set, items cua enum) phai boc tr(), hoac
     ghi `# i18n-skip` cuoi dong neu giu nguyen o ca hai ngon ngu (ten san
     pham, thuat ngu Blender nhu "Armature").
  6. File phai o dang Unicode NFC.
  7. ezg_i18n.py cua moi addon phai giong het ban goc tools/ezg_i18n.py.
"""

import ast
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
ADDONS_DIR = os.path.join(REPO_ROOT, "addons")
MASTER = os.path.join(HERE, "ezg_i18n.py")
HELPER_NAME = "ezg_i18n.py"
SKIP_MARK = "i18n-skip"

_VI_LOWER = ("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
             "ùúủũụưừứửữựỳýỷỹỵđ")
VI_CHARS = set(_VI_LOWER + _VI_LOWER.upper())

# Tu tieng Viet viet khong dau. Chi chon tu vua KHONG trung tieng Anh, vua
# KHONG phai tu dung khi viet dung khong dau (loai "kho", "trong", "nay",
# "cung"...). Hai tu tro len trong mot chuoi thi coi la tieng Viet sot dau.
UNACCENTED_WORDS = {
    "khong", "chua", "duoc", "nguon", "cua", "chon", "nhung", "hoac",
    "truoc", "phai", "xuong", "dang", "mot", "cac", "roi", "vao", "neu",
    "voi", "tren", "duoi", "xoa", "bam", "hien", "khac", "muc", "dat", "doi",
}

UI_KEYWORDS = {"text", "heading", "message", "title", "confirm_text"}
PROP_KEYWORDS = {"name", "description"}
CLASS_TEXT_ATTRS = {"bl_label", "bl_description"}

_PLACEHOLDER = re.compile(r"%(?:\([^)]*\))?[-+ #0]*(?:\d+|\*)?(?:\.\d+)?[sdifrxXeEgGc%]|\{[^{}]*\}")
_WORD = re.compile(r"[A-Za-z]{3,}")


def has_vi(text):
    return any(c in VI_CHARS for c in text)


def unaccented_hits(text):
    words = re.findall(r"[a-z]+", text.lower())
    return sorted({w for w in words if w in UNACCENTED_WORDS})


def placeholders(text):
    return sorted(_PLACEHOLDER.findall(text))


def needs_translation(text):
    """Co chu that su (khong chi la %s, v%s, FBX...) thi can tr()."""
    return any(not w.isupper() for w in _WORD.findall(text))


def _func_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _string_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _is_docstring(node, parent):
    if not isinstance(parent, ast.Expr):
        return False
    return isinstance(node, ast.Constant)


class _Linter(ast.NodeVisitor):
    def __init__(self, path, source):
        self.path = path
        self.lines = source.splitlines()
        self.errors = []
        self.parents = {}

    def err(self, node, msg):
        rel = os.path.relpath(self.path, REPO_ROOT)
        self.errors.append("%s:%d: %s" % (rel, getattr(node, "lineno", 0), msg))

    def skipped(self, node):
        line = self.lines[node.lineno - 1] if 0 < node.lineno <= len(self.lines) else ""
        return SKIP_MARK in line

    def run(self, tree):
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
        self._check_tr_calls(tree)
        self._check_strings(tree)
        self._check_ui_sites(tree)
        return self.errors

    # --- luat 2, 3 ------------------------------------------------------
    def _check_tr_calls(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _func_name(node) == "tr":
                if len(node.args) != 2 or node.keywords:
                    self.err(node, "tr() phai co dung 2 tham so vi tri (vi, en)")
                    continue
                vi, en = (_string_value(a) for a in node.args)
                if en is not None and has_vi(en):
                    self.err(node, "ban EN cua tr() co dau tieng Viet: %r" % en[:60])
                if vi is not None and en is not None and placeholders(vi) != placeholders(en):
                    self.err(node, "placeholder lech giua VI %s va EN %s"
                             % (placeholders(vi), placeholders(en)))

    # --- luat 1, 4 ------------------------------------------------------
    def _slot(self, node):
        """'vi' / 'en' neu node la tham so cua tr(), 'print' / 'doc' neu duoc mien."""
        child = node
        parent = self.parents.get(child)
        while parent is not None:
            if isinstance(parent, ast.Call):
                name = _func_name(parent)
                if name == "print":
                    return "print"
                if name == "tr" and child in parent.args:
                    return "vi" if parent.args.index(child) == 0 else "en"
            if _is_docstring(child, parent):
                return "doc"
            if isinstance(parent, (ast.stmt,)) and not isinstance(parent, ast.Expr):
                return None
            child, parent = parent, self.parents.get(parent)
        return None

    def _check_strings(self, tree):
        for node in ast.walk(tree):
            if isinstance(self.parents.get(node), ast.JoinedStr):
                continue  # xu li ca f-string mot lan o node JoinedStr
            text = _string_value(node)
            if not text:
                continue
            slot = self._slot(node)
            if slot in ("print", "doc"):
                continue
            if has_vi(text) and slot != "vi":
                self.err(node, "chuoi tieng Viet nam ngoai tham so dau cua tr(): %r" % text[:60])
            hits = unaccented_hits(text)
            if len(hits) >= 2:
                self.err(node, "nghi la tieng Viet KHONG DAU %s: %r" % (hits, text[:60]))

    # --- luat 5 ---------------------------------------------------------
    def _literal_parts(self, node):
        """Cac chuoi literal ma gia tri `node` hien ra, bo qua phan da boc tr()."""
        if _string_value(node) is not None:
            yield node
        elif isinstance(node, ast.BinOp):            # "..." % x, "..." + x
            yield from self._literal_parts(node.left)
            if isinstance(node.op, ast.Add):
                yield from self._literal_parts(node.right)
        elif isinstance(node, ast.IfExp):            # "a" if c else "b"
            yield from self._literal_parts(node.body)
            yield from self._literal_parts(node.orelse)
        elif isinstance(node, ast.Call) and _func_name(node) == "format" \
                and isinstance(node.func, ast.Attribute):
            yield from self._literal_parts(node.func.value)

    def _plain(self, node, where):
        for part in self._literal_parts(node):
            text = _string_value(part)
            if not needs_translation(text) or self.skipped(part):
                continue
            self.err(part, "%s la chuoi tho %r: boc tr() hoac ghi '# %s'"
                     % (where, text[:50], SKIP_MARK))

    def _check_ui_sites(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _func_name(node)
                for kw in node.keywords:
                    if kw.arg in UI_KEYWORDS:
                        self._plain(kw.value, "%s=" % kw.arg)
                    elif kw.arg in PROP_KEYWORDS and name.endswith("Property"):
                        self._plain(kw.value, "%s(%s=)" % (name, kw.arg))
                    elif kw.arg == "items" and name == "EnumProperty":
                        self._check_enum_items(kw.value)
                if name == "report" and len(node.args) >= 2:
                    self._plain(node.args[1], "report()")
                if name == "poll_message_set" and node.args:
                    self._plain(node.args[0], "poll_message_set()")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in CLASS_TEXT_ATTRS \
                            and isinstance(self.parents.get(node), ast.ClassDef):
                        self._plain(node.value, target.id)
            elif isinstance(node, ast.ClassDef):
                self._check_docstring_tooltip(node)

    def _check_docstring_tooltip(self, cls):
        """Operator/Panel/Menu khong co bl_description thi Blender lay docstring lam tooltip."""
        bases = {b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "") for b in cls.bases}
        if not bases & {"Operator", "Panel", "Menu"}:
            return
        if ast.get_docstring(cls) is None:
            return
        has_desc = any(isinstance(st, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "bl_description" for t in st.targets)
            for st in cls.body)
        if not has_desc:
            self.err(cls, "class %s co docstring ma khong co bl_description: Blender "
                          "lay docstring lam tooltip, doi sang bl_description = tr(...)" % cls.name)

    def _check_enum_items(self, value):
        if not isinstance(value, (ast.List, ast.Tuple)):
            return  # callback hoac hang so dat o cho khac
        for item in value.elts:
            if isinstance(item, ast.Tuple):
                for elt in item.elts[1:3]:
                    self._plain(elt, "items cua EnumProperty")


def lint_file(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    errors = []
    if source != unicodedata.normalize("NFC", source):
        errors.append("%s: file khong o dang Unicode NFC" % os.path.relpath(path, REPO_ROOT))
    tree = ast.parse(source, filename=path)
    errors += _Linter(path, source).run(tree)
    return errors


def addon_ids():
    return sorted(n for n in os.listdir(ADDONS_DIR)
                  if os.path.isfile(os.path.join(ADDONS_DIR, n, "blender_manifest.toml")))


def lint_addon(pkg_id):
    pkg_dir = os.path.join(ADDONS_DIR, pkg_id)
    errors = []

    helper = os.path.join(pkg_dir, HELPER_NAME)
    if not os.path.isfile(helper):
        errors.append("%s: thieu %s (chay tools/sync_i18n.py)" % (pkg_id, HELPER_NAME))
    else:
        with open(helper, "rb") as a, open(MASTER, "rb") as b:
            if a.read() != b.read():
                errors.append("%s: %s lech ban goc tools/ezg_i18n.py (chay tools/sync_i18n.py)"
                              % (pkg_id, HELPER_NAME))

    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith(".py") and fn != HELPER_NAME:
                errors += lint_file(os.path.join(root, fn))
    return errors


def main(argv):
    ids = argv or addon_ids()
    total = 0
    for pkg_id in ids:
        errors = lint_addon(pkg_id)
        total += len(errors)
        print("%-28s %s" % (pkg_id, "OK" if not errors else "%d loi" % len(errors)))
        for e in errors:
            print("    " + e)
    return 1 if total else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
