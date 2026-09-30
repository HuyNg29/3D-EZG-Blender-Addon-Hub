"""Cac thao tac cua hub."""

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import backup, bridge, prefs as prefs_mod, remote, scanner


def _prefs():
    p = prefs_mod.get()
    if p is None:
        raise RuntimeError("Không đọc được preferences của hub.")
    return p


def _set_status(text="", error=""):
    wm = bpy.context.window_manager
    wm.ezg_status = text
    wm.ezg_error = error


def _fill_inventory(wm, items, updates=None):
    wm.ezg_inventory.clear()
    for it in items:
        row = wm.ezg_inventory.add()
        row.pkg_id = it["pkg_id"]
        row.module = it["module"]
        row.name = it["name"]
        row.version = it["version"]
        row.enabled = it["enabled"]
        row.group = it["group"]
        row.source_label = it["source_label"]
        row.homepage = it["homepage"]
        row.repo_module = it["repo_module"]
        row.update_version = ""
        if updates:
            newer = updates.get((it["repo_module"], it["pkg_id"]), "")
            if newer and scanner.is_newer(newer, it["version"]):
                row.update_version = newer


class EZG_OT_refresh_inventory(Operator):
    bl_idname = "ezg.refresh_inventory"
    bl_label = "Quét lại"
    bl_description = "Quét lại addon đang cài trên máy này"

    check_updates: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        items = scanner.scan(p.repo_url)

        updates = None
        if self.check_updates:
            if not remote.online():
                _set_status("", "Blender đang offline. Bật Preferences > System > Allow Online Access.")
                _fill_inventory(wm, items)
                return {'CANCELLED'}
            repos = list(context.preferences.extensions.repos)
            updates = remote.remote_versions_for_repos(repos)

        _fill_inventory(wm, items, updates)

        n_update = sum(1 for r in wm.ezg_inventory if r.update_version)
        if self.check_updates:
            _set_status("%d addon, %d có bản mới." % (len(items), n_update))
        else:
            _set_status("%d addon." % len(items))
        return {'FINISHED'}


class EZG_OT_refresh_store(Operator):
    bl_idname = "ezg.refresh_store"
    bl_label = "Tải lại kho"
    bl_description = "Tải danh sách addon EZG từ kho về"

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager

        try:
            index, catalog = remote.fetch(p.repo_url, p.access_token, force=True)
        except remote.RemoteError as exc:
            _set_status("", str(exc))
            return {'CANCELLED'}

        entries = remote.index_entries(index)
        installed = {i["pkg_id"]: i for i in scanner.scan(p.repo_url)}

        # Nhom hien thi lay tu catalog.json; pkg nao khong nam trong nhom nao
        # van phai hien ra, neu khong user se khong thay addon vua duoc them.
        meta = catalog.get("items", {}) or {}
        grouped = []
        seen = set()
        for grp in catalog.get("groups", []) or []:
            label = grp.get("label", grp.get("id", ""))
            for pkg_id in grp.get("items", []) or []:
                if pkg_id in entries:
                    grouped.append((label, pkg_id))
                    seen.add(pkg_id)
        for pkg_id in entries:
            if pkg_id not in seen:
                grouped.append(("Khác", pkg_id))

        wm.ezg_catalog.clear()
        for label, pkg_id in grouped:
            entry = entries[pkg_id]
            info = meta.get(pkg_id, {}) or {}
            row = wm.ezg_catalog.add()
            row.pkg_id = pkg_id
            row.title = info.get("title_vi") or entry.get("name") or pkg_id
            row.summary = (info.get("summary_vi") or entry.get("tagline") or "").strip()
            row.version = entry.get("version", "")
            row.group_label = label
            row.recommended = bool(info.get("recommended"))
            row.is_external = False
            row.homepage = entry.get("website", "") or ""
            inst = installed.get(pkg_id)
            row.installed = inst is not None
            row.installed_version = inst["version"] if inst else ""

        # Addon ben thu ba: hub chi tro toi nguon, khong phuc vu file.
        for ext in catalog.get("external", []) or []:
            row = wm.ezg_catalog.add()
            row.pkg_id = ext.get("id", "")
            row.title = ext.get("title_vi") or ext.get("id", "")
            row.summary = (ext.get("summary_vi") or "").strip()
            row.group_label = "Bên thứ ba"
            row.is_external = True
            row.homepage = ext.get("homepage", "")
            inst = installed.get(row.pkg_id)
            row.installed = inst is not None
            row.installed_version = inst["version"] if inst else ""

        n = sum(1 for r in wm.ezg_catalog if not r.is_external)
        _set_status("Kho EZG: %d addon." % n)
        return {'FINISHED'}


class EZG_OT_setup_repo(Operator):
    bl_idname = "ezg.setup_repo"
    bl_label = "Thêm kho EZG vào Blender"
    bl_description = ("Đăng kí kho EZG trong Preferences của Blender. "
                      "Cần bước này thì Blender mới cài và tự kiểm tra cập nhật được")

    def execute(self, context):
        p = _prefs()
        try:
            repo = bridge.ensure_ezg_repo(p.repo_url, p.access_token)
            bridge.sync_all()
        except Exception as exc:
            _set_status("", str(exc))
            return {'CANCELLED'}
        bridge.save_prefs()
        _set_status("Đã thêm kho '%s' vào Blender." % repo.name)
        return {'FINISHED'}


class EZG_OT_install(Operator):
    bl_idname = "ezg.install"
    bl_label = "Cài"
    bl_description = "Cài addon này từ kho EZG"
    bl_options = {'REGISTER'}

    pkg_id: StringProperty()

    def execute(self, context):
        p = _prefs()
        if not self.pkg_id:
            return {'CANCELLED'}
        try:
            repo = bridge.ensure_ezg_repo(p.repo_url, p.access_token)
            bridge.sync_all()
            bridge.install(repo, self.pkg_id)
        except Exception as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bridge.save_prefs()
        bpy.ops.ezg.refresh_store()
        _set_status("Đã cài '%s'." % self.pkg_id)
        self.report({'INFO'}, "Đã cài %s." % self.pkg_id)
        return {'FINISHED'}


class EZG_OT_update_selected(Operator):
    bl_idname = "ezg.update_selected"
    bl_label = "Cập nhật mục đang chọn"
    bl_description = "Chỉ cập nhật addon đang chọn trong danh sách"

    @classmethod
    def poll(cls, context):
        wm = context.window_manager
        if not (0 <= wm.ezg_inventory_index < len(wm.ezg_inventory)):
            cls.poll_message_set("Chưa chọn addon nào trong danh sách.")
            return False

        item = wm.ezg_inventory[wm.ezg_inventory_index]
        if item.group == "C":
            cls.poll_message_set(
                "'%s' là nguồn thủ công — hub không tự cập nhật được." % item.name)
            return False
        if not item.update_version:
            cls.poll_message_set("'%s' đang là bản mới nhất." % item.name)
            return False
        return True

    def execute(self, context):
        wm = context.window_manager
        item = wm.ezg_inventory[wm.ezg_inventory_index]
        name, target = item.name, item.update_version

        repo = next((r for r in context.preferences.extensions.repos
                     if r.module == item.repo_module), None)
        if repo is None:
            msg = "Không tìm thấy kho '%s' của addon này." % item.repo_module
            _set_status("", msg)
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        try:
            bridge.sync_repo(repo)
            bridge.install(repo, item.pkg_id, enable=item.enabled)
        except Exception as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bridge.save_prefs()
        remote.clear_cache()
        bpy.ops.ezg.refresh_inventory(check_updates=True)

        msg = "Đã cập nhật %s lên v%s. Khởi động lại Blender để áp dụng." % (name, target)
        _set_status(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class EZG_OT_update_all(Operator):
    bl_idname = "ezg.update_all"
    bl_label = "Cập nhật tất cả"
    bl_description = ("Đẩy sang cơ chế cập nhật của chính Blender. "
                      "Addon nguồn thủ công không nằm trong phạm vi này")

    def execute(self, context):
        try:
            bridge.sync_all()
            bridge.upgrade_all()
        except Exception as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bridge.save_prefs()
        remote.clear_cache()
        bpy.ops.ezg.refresh_inventory(check_updates=True)
        self.report({'INFO'}, "Đã chạy cập nhật. Khởi động lại Blender để áp dụng.")
        return {'FINISHED'}


class EZG_OT_open_url(Operator):
    bl_idname = "ezg.open_url"
    bl_label = "Mở trang nguồn"
    bl_description = "Mở trang gốc của addon trong trình duyệt"

    url: StringProperty()

    def execute(self, context):
        if not self.url:
            self.report({'WARNING'}, "Addon này không khai báo trang nguồn.")
            return {'CANCELLED'}
        bpy.ops.wm.url_open(url=self.url)
        return {'FINISHED'}


class EZG_OT_refresh_snapshots(Operator):
    bl_idname = "ezg.refresh_snapshots"
    bl_label = "Tải lại danh sách backup"

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        snaps = backup.list_snapshots(p.resolved_backup_dir(), p.resolved_profile_name())

        wm.ezg_snapshots.clear()
        for s in snaps:
            row = wm.ezg_snapshots.add()
            row.name = s["name"]
            row.path = s["path"]
            row.created = s["created"]
            row.count = s["count"]
            row.blobs = s["blobs"]
            row.blender = s["blender"]

        _set_status("%d bản backup." % len(snaps))
        return {'FINISHED'}


class EZG_OT_backup_create(Operator):
    bl_idname = "ezg.backup_create"
    bl_label = "Tạo backup"
    bl_description = "Lưu danh sách addon đang cài thành một snapshot"

    def execute(self, context):
        p = _prefs()
        items = scanner.scan(p.repo_url)
        if not items:
            self.report({'WARNING'}, "Không có addon nào để backup.")
            return {'CANCELLED'}

        try:
            snap_dir, count, warnings = backup.create(
                context, items, p.resolved_backup_dir(),
                p.resolved_profile_name(), p.backup_all_blobs)
        except backup.BackupError as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        mirrored = None
        if p.sync_dir:
            try:
                mirrored = backup.mirror_manifest(
                    snap_dir, bpy.path.abspath(p.sync_dir),
                    p.resolved_profile_name(), p.mirror_blobs)
            except Exception as exc:
                warnings.append("Không chép sang thư mục đồng bộ: %s" % exc)

        bpy.ops.ezg.refresh_snapshots()

        msg = "Đã backup %d addon vào %s" % (count, os.path.basename(snap_dir))
        if mirrored:
            msg += " (đã chép sang thư mục đồng bộ)"
        _set_status(msg, " | ".join(warnings))
        self.report({'WARNING'} if warnings else {'INFO'}, msg)
        for w in warnings:
            print("[EZG Hub]", w)
        return {'FINISHED'}


class EZG_OT_restore(Operator):
    bl_idname = "ezg.restore"
    bl_label = "Phục hồi"
    bl_description = "Cài lại các addon trong bản backup này"
    bl_options = {'REGISTER'}

    path: StringProperty()
    mode: EnumProperty(
        items=[('LATEST', "Bản mới nhất", ""), ('EXACT', "Đúng bản đã lưu", "")],
        default='LATEST',
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        p = _prefs()
        if not self.path or not os.path.isdir(self.path):
            self.report({'ERROR'}, "Không tìm thấy bản backup.")
            return {'CANCELLED'}

        try:
            done, report = backup.restore(
                context, self.path, self.mode, p.repo_url, p.access_token)
        except backup.BackupError as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bpy.ops.ezg.refresh_inventory()

        msg = "Đã cài lại %d addon." % len(done)
        if report:
            msg += " %d mục cần xem lại (System Console)." % len(report)
        _set_status(msg + " Khởi động lại Blender để áp dụng.", " | ".join(report[:3]))
        for line in report:
            print("[EZG Hub restore]", line)
        self.report({'WARNING'} if report else {'INFO'}, msg)
        return {'FINISHED'}


classes = (
    EZG_OT_refresh_inventory,
    EZG_OT_refresh_store,
    EZG_OT_setup_repo,
    EZG_OT_install,
    EZG_OT_update_selected,
    EZG_OT_update_all,
    EZG_OT_open_url,
    EZG_OT_refresh_snapshots,
    EZG_OT_backup_create,
    EZG_OT_restore,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
