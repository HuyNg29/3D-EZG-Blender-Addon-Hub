"""Lop bao quanh bpy.ops.extensions.*

Hub khong tu tai file addon ve va giai nen. Moi thao tac cai / go / cap nhat
deu day sang co che goc cua Blender, nen hub khong bao gio giu mot ban cu hon
nguon. Day la nguyen tac trung tam cua thiet ke — xem docs/ARCHITECTURE.md muc 4.
"""

import bpy

from . import prefs as prefs_mod
from . import scanner


class BridgeError(Exception):
    pass


def ensure_ezg_repo(repo_url, token=""):
    """Tra ve repo EZG trong Blender, tao moi neu chua co.

    Blender can repo ton tai trong preferences thi package_install moi tro toi duoc.
    """
    repo = scanner.find_repo_by_url(repo_url)
    if repo is not None:
        if token and repo.access_token != token:
            repo.access_token = token
        return repo

    repos = bpy.context.preferences.extensions.repos

    module = prefs_mod.EZG_REPO_MODULE
    existing = {r.module for r in repos}
    if module in existing:
        # Ten module da bi chiem boi repo khac -> them hau to cho khoi dung.
        n = 2
        while "%s_%d" % (module, n) in existing:
            n += 1
        module = "%s_%d" % (module, n)

    repo = repos.new(name="EZG", module=module, remote_url=repo_url)
    repo.use_remote_url = True
    repo.enabled = True
    if token:
        repo.access_token = token
    return repo


def sync_all():
    """Tai lai index cua moi remote repo (giong nut Check for Updates)."""
    try:
        bpy.ops.extensions.repo_sync_all()
    except Exception as exc:
        raise BridgeError("Sync that bai: %s" % exc)


def sync_repo(repo):
    """Tai lai index cua rieng mot repo — nhanh hon sync_all khi chi can 1 addon."""
    idx = scanner.repo_index(repo)
    if idx < 0:
        raise BridgeError("Khong xac dinh duoc vi tri repo trong danh sach.")
    try:
        bpy.ops.extensions.repo_sync(repo_index=idx)
    except Exception as exc:
        raise BridgeError("Sync kho '%s' that bai: %s" % (repo.name, exc))


def upgrade_all():
    try:
        bpy.ops.extensions.package_upgrade_all()
    except Exception as exc:
        raise BridgeError("Cap nhat that bai: %s" % exc)


def install(repo, pkg_id, enable=True):
    idx = scanner.repo_index(repo)
    if idx < 0:
        raise BridgeError("Khong xac dinh duoc vi tri repo trong danh sach.")
    try:
        bpy.ops.extensions.package_install(
            repo_index=idx, pkg_id=pkg_id, enable_on_install=enable)
    except Exception as exc:
        raise BridgeError("Cai '%s' that bai: %s" % (pkg_id, exc))


def install_file(filepath, enable=True):
    """Cai tu file zip co san — dung khi restore addon nhom C tu blob."""
    try:
        bpy.ops.extensions.package_install_files(
            filepath=filepath, enable_on_install=enable)
    except Exception as exc:
        raise BridgeError("Cai tu file '%s' that bai: %s" % (filepath, exc))


def set_enabled(module, enabled):
    try:
        if enabled:
            bpy.ops.preferences.addon_enable(module=module)
        else:
            bpy.ops.preferences.addon_disable(module=module)
    except Exception as exc:
        raise BridgeError("Doi trang thai '%s' that bai: %s" % (module, exc))


def save_prefs():
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass
