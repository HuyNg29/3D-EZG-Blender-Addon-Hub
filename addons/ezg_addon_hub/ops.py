"""Cac thao tac cua hub."""

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import backup, bridge, ezg_i18n, prefs as prefs_mod, remote, scanner
from .ezg_i18n import tr


def _prefs():
    p = prefs_mod.get()
    if p is None:
        raise RuntimeError(tr("Không đọc được preferences của hub.", "Could not read the hub preferences."))
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
    bl_label = tr("Quét lại", "Rescan")
    bl_description = tr("Quét lại addon đang cài trên máy này", "Rescan the add-ons installed on this machine")

    check_updates: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        items = scanner.scan(p.repo_url)

        updates = None
        if self.check_updates:
            if not remote.online():
                _set_status("", tr("Blender đang offline. Bật Preferences > System > Allow Online Access.", "Blender is offline. Enable Preferences > System > Allow Online Access."))
                _fill_inventory(wm, items)
                return {'CANCELLED'}
            repos = list(context.preferences.extensions.repos)
            updates = remote.remote_versions_for_repos(repos)

        _fill_inventory(wm, items, updates)

        n_update = sum(1 for r in wm.ezg_inventory if r.update_version)
        if self.check_updates:
            _set_status(tr("%d addon, %d có bản mới.", "%d add-ons, %d with updates.") % (len(items), n_update))
        else:
            _set_status(tr("%d addon.", "%d add-ons.") % len(items))
        return {'FINISHED'}


class EZG_OT_refresh_store(Operator):
    bl_idname = "ezg.refresh_store"
    bl_label = tr("Tải lại kho", "Reload repository")
    bl_description = tr("Tải danh sách addon EZG từ kho về", "Download the EZG add-on list from the repository")

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
                grouped.append(("", pkg_id))  # UI tu ghi "Khac"

        wm.ezg_catalog.clear()
        for label, pkg_id in grouped:
            entry = entries[pkg_id]
            info = meta.get(pkg_id, {}) or {}
            row = wm.ezg_catalog.add()
            row.pkg_id = pkg_id
            row.title = info.get("title_vi") or entry.get("name") or pkg_id
            row.summary = (info.get("summary_vi") or entry.get("tagline") or "").strip()
            row.summary_en = (info.get("summary_en") or "").strip()
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
            row.summary_en = (ext.get("summary_en") or "").strip()
            row.group_label = ""  # UI tu ghi "Ben thu ba" theo ngon ngu
            row.is_external = True
            row.homepage = ext.get("homepage", "")
            inst = installed.get(row.pkg_id)
            row.installed = inst is not None
            row.installed_version = inst["version"] if inst else ""

        n = sum(1 for r in wm.ezg_catalog if not r.is_external)
        _set_status(tr("Kho EZG: %d addon.", "EZG repository: %d add-ons.") % n)
        return {'FINISHED'}


class EZG_OT_setup_repo(Operator):
    bl_idname = "ezg.setup_repo"
    bl_label = tr("Thêm kho EZG vào Blender", "Add EZG repository to Blender")
    bl_description = tr("Đăng kí kho EZG trong Preferences của Blender. "
                        "Cần bước này thì Blender mới cài và tự kiểm tra cập nhật được",
                        "Register the EZG repository in Blender's Preferences. Blender "
                        "needs this to install and check for updates on its own")

    def execute(self, context):
        p = _prefs()
        try:
            repo = bridge.ensure_ezg_repo(p.repo_url, p.access_token)
            bridge.sync_all()
        except Exception as exc:
            _set_status("", str(exc))
            return {'CANCELLED'}
        bridge.save_prefs()
        _set_status(tr("Đã thêm kho '%s' vào Blender.", "Added repository '%s' to Blender.") % repo.name)
        return {'FINISHED'}


class EZG_OT_install(Operator):
    bl_idname = "ezg.install"
    bl_label = tr("Cài", "Install")
    bl_description = tr("Cài addon này từ kho EZG", "Install this add-on from the EZG repository")
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
        _set_status(tr("Đã cài '%s'.", "Installed '%s'.") % self.pkg_id)
        self.report({'INFO'}, tr("Đã cài %s.", "Installed %s.") % self.pkg_id)
        return {'FINISHED'}


class EZG_OT_update_selected(Operator):
    bl_idname = "ezg.update_selected"
    bl_label = tr("Cập nhật mục đang chọn", "Update selected")
    bl_description = tr("Chỉ cập nhật addon đang chọn trong danh sách", "Update only the add-on selected in the list")

    @classmethod
    def poll(cls, context):
        wm = context.window_manager
        if not (0 <= wm.ezg_inventory_index < len(wm.ezg_inventory)):
            cls.poll_message_set(tr("Chưa chọn addon nào trong danh sách.", "No add-on selected in the list."))
            return False

        item = wm.ezg_inventory[wm.ezg_inventory_index]
        if item.group == "C":
            cls.poll_message_set(
                tr("'%s' là nguồn thủ công — hub không tự cập nhật được.", "'%s' is a manual source — the hub cannot update it.") % item.name)
            return False
        if not item.update_version:
            cls.poll_message_set(tr("'%s' đang là bản mới nhất.", "'%s' is already the latest version.") % item.name)
            return False
        return True

    def execute(self, context):
        wm = context.window_manager
        item = wm.ezg_inventory[wm.ezg_inventory_index]
        name, target = item.name, item.update_version

        repo = next((r for r in context.preferences.extensions.repos
                     if r.module == item.repo_module), None)
        if repo is None:
            msg = tr("Không tìm thấy kho '%s' của addon này.", "Repository '%s' of this add-on was not found.") % item.repo_module
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

        msg = tr("Đã cập nhật %s lên v%s. Khởi động lại Blender để áp dụng.", "Updated %s to v%s. Restart Blender to apply.") % (name, target)
        _set_status(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class EZG_OT_update_all(Operator):
    bl_idname = "ezg.update_all"
    bl_label = tr("Cập nhật tất cả", "Update all")
    bl_description = tr("Đẩy sang cơ chế cập nhật của chính Blender. "
                        "Addon nguồn thủ công không nằm trong phạm vi này",
                        "Hands off to Blender's own update mechanism. "
                        "Manual-source add-ons are not covered")

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
        self.report({'INFO'}, tr("Đã chạy cập nhật. Khởi động lại Blender để áp dụng.", "Update finished. Restart Blender to apply."))
        return {'FINISHED'}


class EZG_OT_open_url(Operator):
    bl_idname = "ezg.open_url"
    bl_label = tr("Mở trang nguồn", "Open source page")
    bl_description = tr("Mở trang gốc của addon trong trình duyệt", "Open the add-on's homepage in the browser")

    url: StringProperty()

    def execute(self, context):
        if not self.url:
            self.report({'WARNING'}, tr("Addon này không khai báo trang nguồn.", "This add-on declares no source page."))
            return {'CANCELLED'}
        bpy.ops.wm.url_open(url=self.url)
        return {'FINISHED'}


def _select_snapshot(wm, path):
    for i, row in enumerate(wm.ezg_snapshots):
        if os.path.normcase(row.path) == os.path.normcase(path):
            wm.ezg_snapshots_index = i
            return


class EZG_OT_refresh_snapshots(Operator):
    bl_idname = "ezg.refresh_snapshots"
    bl_label = tr("Tải lại danh sách backup", "Reload backup list")

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        snaps = backup.list_snapshots(p.resolved_backup_dir(), p.resolved_profile_name())

        wm.ezg_snapshots.clear()
        for s in snaps:
            row = wm.ezg_snapshots.add()
            row.name = s["label"] or s["name"]
            row.label = s["label"]
            row.path = s["path"]
            row.created = s["created"]
            row.count = s["count"]
            row.blobs = s["blobs"]
            row.blender = s["blender"]

        _set_status(tr("%d bản backup.", "%d backups.") % len(snaps))
        return {'FINISHED'}


class EZG_OT_backup_create(Operator):
    bl_idname = "ezg.backup_create"
    bl_label = tr("Tạo backup", "Create backup")
    bl_description = tr("Lưu danh sách addon đang cài thành một snapshot", "Save the installed add-on list as a snapshot")

    # Bo trong thi lay o "Ten backup" tren panel.
    label: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        label = self.label if self.properties.is_property_set("label") else wm.ezg_backup_label
        items = scanner.scan(p.repo_url)
        if not items:
            self.report({'WARNING'}, tr("Không có addon nào để backup.", "No add-ons to back up."))
            return {'CANCELLED'}

        try:
            snap_dir, count, warnings = backup.create(
                context, items, p.resolved_backup_dir(),
                p.resolved_profile_name(), p.backup_all_blobs, label)
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
                warnings.append(tr("Không chép sang thư mục đồng bộ: %s", "Could not copy to the sync folder: %s") % exc)

        bpy.ops.ezg.refresh_snapshots()
        _select_snapshot(wm, snap_dir)  # chon san ban vua tao -> doi ten duoc ngay
        wm.ezg_backup_label = ""

        name = backup.clean_label(label) or os.path.basename(snap_dir)
        msg = tr("Đã backup %d addon vào '%s'", "Backed up %d add-ons to '%s'") % (count, name)
        if mirrored:
            msg += tr(" (đã chép sang thư mục đồng bộ)", " (copied to the sync folder)")
        _set_status(msg, " | ".join(warnings))
        self.report({'WARNING'} if warnings else {'INFO'}, msg)
        for w in warnings:
            print("[EZG Hub]", w)
        return {'FINISHED'}


class EZG_OT_backup_rename(Operator):
    bl_idname = "ezg.backup_rename"
    bl_label = tr("Đổi tên backup", "Rename Backup")
    bl_description = tr("Đặt hoặc đổi tên bản backup này. Để trống thì hiện lại theo giờ tạo",
                        "Name or rename this backup. Leave empty to show its creation time again")
    bl_options = {'REGISTER'}

    path: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    label: StringProperty(name=tr("Tên", "Name"), options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if not self.properties.is_property_set("label"):
            try:
                self.label = backup.clean_label(backup.read_manifest(self.path).get("label"))
            except backup.BackupError:
                pass
        return context.window_manager.invoke_props_dialog(
            self, width=320, title=tr("Đổi tên backup", "Rename Backup"),
            confirm_text=tr("Đổi tên", "Rename"))

    def draw(self, context):
        self.layout.prop(self, "label", text="",
                         placeholder=tr("Để trống = hiện theo giờ tạo",
                                        "Empty = show the creation time"))

    def execute(self, context):
        p = _prefs()
        wm = context.window_manager
        if not self.path or not os.path.isdir(self.path):
            self.report({'ERROR'}, tr("Không tìm thấy bản backup.", "Backup not found."))
            return {'CANCELLED'}

        try:
            label, mirrored = backup.rename(
                self.path, self.label,
                bpy.path.abspath(p.sync_dir) if p.sync_dir else None,
                p.resolved_profile_name())
        except backup.BackupError as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bpy.ops.ezg.refresh_snapshots()
        _select_snapshot(wm, self.path)

        if label:
            msg = tr("Đã đặt tên backup: '%s'", "Backup renamed to '%s'") % label
        else:
            msg = tr("Đã bỏ tên, backup hiện lại theo giờ tạo.",
                     "Name removed; the backup shows its creation time again.")
        if mirrored:
            msg += tr(" (đổi cả bản ở thư mục đồng bộ)", " (sync folder copy too)")
        _set_status(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class EZG_OT_restore(Operator):
    bl_idname = "ezg.restore"
    bl_label = tr("Phục hồi", "Restore")
    bl_description = tr("Cài lại các addon trong bản backup này", "Reinstall the add-ons in this backup")
    bl_options = {'REGISTER'}

    path: StringProperty()
    mode: EnumProperty(
        items=[('LATEST', tr("Bản mới nhất", "Latest version"), ""),
               ('EXACT', tr("Đúng bản đã lưu", "Exact saved version"), "")],
        default='LATEST',
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        p = _prefs()
        if not self.path or not os.path.isdir(self.path):
            self.report({'ERROR'}, tr("Không tìm thấy bản backup.", "Backup not found."))
            return {'CANCELLED'}

        try:
            done, report = backup.restore(
                context, self.path, self.mode, p.repo_url, p.access_token)
        except backup.BackupError as exc:
            _set_status("", str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        bpy.ops.ezg.refresh_inventory()

        msg = tr("Đã cài lại %d addon.", "Reinstalled %d add-ons.") % len(done)
        if report:
            msg += tr(" %d mục cần xem lại (System Console).", " %d items need attention (System Console).") % len(report)
        _set_status(msg + tr(" Khởi động lại Blender để áp dụng.", " Restart Blender to apply."), " | ".join(report[:3]))
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
    EZG_OT_backup_rename,
    EZG_OT_restore,
    ezg_i18n.make_language_operator("ezg"),
)


def register():
    ezg_i18n.register_classes(classes)


def unregister():
    ezg_i18n.unregister_classes(classes)
