"""Kiem ke addon dang cai trong Blender nay va suy ra nguon goc tung cai.

Blender khong luu "addon nay den tu dau" cho addon legacy, nen phan loai o day
dua vao vi tri file va cau hinh repo:

  A  extension den tu mot remote repo khac EZG   (vd extensions.blender.org)
  B  extension den tu repo EZG
  C  nguon thu cong: addon legacy trong scripts/addons, hoac extension nam
     trong repo cuc bo khong co remote_url

Addon core di kem Blender (thu muc addons_core) bi loai hoan toan: khong phai
thu user cai, va khong can backup.
"""

import os

import addon_utils
import bpy

try:
    import tomllib
except ImportError:  # Blender 4.5 luon co, day chi la luoi an toan
    tomllib = None

GROUP_LABEL = {
    "A": "kho ngoai",
    "B": "EZG",
    "C": "thu cong",
}


def _repos_by_module():
    return {r.module: r for r in bpy.context.preferences.extensions.repos}


def read_manifest(pkg_dir):
    """Doc blender_manifest.toml cua mot extension da cai. {} neu khong doc duoc."""
    path = os.path.join(pkg_dir, "blender_manifest.toml")
    if tomllib is None or not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _version_str(value):
    if isinstance(value, (list, tuple)):
        return ".".join(str(x) for x in value)
    return str(value) if value else ""


def version_tuple(text):
    """'1.5.10' -> (1, 5, 10). Phan khong phai so bi bo qua de khong no."""
    parts = []
    for chunk in str(text).replace("-", ".").split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts)


def is_newer(remote, installed):
    """True neu ban remote moi hon ban dang cai."""
    rt, it = version_tuple(remote), version_tuple(installed)
    if not rt or not it:
        return False
    return rt > it


def _blender_local_root():
    """Thu muc cai dat Blender — dung de nhan ra addon core di kem."""
    try:
        return os.path.normcase(bpy.utils.resource_path('LOCAL'))
    except Exception:
        return None


def scan(ezg_repo_url=""):
    """Tra ve list dict mo ta moi addon user da cai.

    Moi dict: pkg_id, module, name, version, enabled, group, source_label,
              homepage, repo_module, path, is_extension
    """
    repos = _repos_by_module()
    enabled_modules = set(bpy.context.preferences.addons.keys())
    user_addons_dir = os.path.normcase(bpy.utils.user_resource('SCRIPTS', path="addons"))
    local_root = _blender_local_root()
    ezg_url = (ezg_repo_url or "").strip().rstrip("/")

    items = []

    for mod in addon_utils.modules(refresh=False):
        module = mod.__name__
        filepath = getattr(mod, "__file__", "") or ""
        info = getattr(mod, "bl_info", {}) or {}
        pkg_dir = os.path.dirname(filepath)

        if module.startswith("bl_ext."):
            try:
                _, repo_module, pkg_id = module.split(".", 2)
            except ValueError:
                continue

            repo = repos.get(repo_module)
            if repo is not None and repo.source == 'SYSTEM':
                continue  # extension di kem ban cai Blender

            manifest = read_manifest(pkg_dir)
            remote_url = (getattr(repo, "remote_url", "") or "").strip().rstrip("/")
            has_remote = bool(repo is not None and repo.use_remote_url and remote_url)

            if has_remote and ezg_url and remote_url == ezg_url:
                group = "B"
            elif has_remote:
                group = "A"
            else:
                group = "C"

            items.append({
                "pkg_id": pkg_id,
                "module": module,
                "name": manifest.get("name") or info.get("name") or pkg_id,
                "version": manifest.get("version") or _version_str(info.get("version")),
                "enabled": module in enabled_modules,
                "group": group,
                "source_label": repo.name if repo is not None else repo_module,
                "homepage": manifest.get("website", "") or "",
                "repo_module": repo_module,
                "path": pkg_dir,
                "is_extension": True,
            })
            continue

        # --- Addon legacy ---
        if not filepath:
            continue
        norm = os.path.normcase(filepath)
        if local_root and norm.startswith(local_root):
            continue  # addon core di kem Blender
        if not norm.startswith(user_addons_dir):
            continue  # nam ngoai thu muc addon cua user, khong phai thu ta quan li

        # Addon legacy 1 file la <ten>.py, dang package la <ten>/__init__.py
        single_file = os.path.basename(filepath) != "__init__.py"

        items.append({
            "pkg_id": module,
            "module": module,
            "name": info.get("name") or module,
            "version": _version_str(info.get("version")),
            "enabled": module in enabled_modules,
            "group": "C",
            "source_label": "thu cong",
            "homepage": info.get("doc_url") or info.get("wiki_url") or "",
            "repo_module": "",
            "path": filepath if single_file else pkg_dir,
            "is_extension": False,
        })

    items.sort(key=lambda d: d["name"].lower())
    return items


def find_repo_by_url(url):
    """Repo trong Blender co remote_url trung voi url, hoac None."""
    target = (url or "").strip().rstrip("/")
    if not target:
        return None
    for repo in bpy.context.preferences.extensions.repos:
        if repo.use_remote_url and (repo.remote_url or "").strip().rstrip("/") == target:
            return repo
    return None


def repo_index(repo):
    """Vi tri cua repo trong danh sach — package_install can so nay."""
    for i, r in enumerate(bpy.context.preferences.extensions.repos):
        if r == repo:
            return i
    return -1
