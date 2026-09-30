"""Tuy chon cua hub. Luu trong userpref.blend cua Blender, khong phai file rieng."""

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import AddonPreferences

from . import ezg_i18n
from .ezg_i18n import tr

# URL mac dinh cua kho EZG. Doi o day neu chuyen sang tu host.
DEFAULT_REPO_URL = "https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json"

# Ten module cua repo EZG khi hub tu them vao Blender.
EZG_REPO_MODULE = "ezg"


def default_backup_dir():
    return os.path.join(os.path.expanduser("~"), "EZG Addon Hub", "profiles")


def default_profile_name():
    # Ten dang nhap Windows la mac dinh hop ly nhat; user doi duoc trong prefs.
    return os.environ.get("USERNAME") or os.environ.get("USER") or "default"


class EZGHubPreferences(AddonPreferences):
    # Extension bat buoc dung __package__, KHONG dung __name__.
    bl_idname = __package__

    repo_url: StringProperty(
        name=tr("URL kho EZG", "EZG repository URL"),
        description=tr("Địa chỉ index.json của kho addon EZG", "Address of the EZG add-on repository index.json"),
        default=DEFAULT_REPO_URL,
    )
    access_token: StringProperty(
        name="Access token",  # i18n-skip
        description=tr("Chỉ cần nếu kho EZG đặt ở chế độ private", "Only needed if the EZG repository is private"),
        default="",
        subtype='PASSWORD',
    )
    backup_dir: StringProperty(
        name=tr("Thư mục backup", "Backup folder"),
        description=tr("Nơi lưu snapshot profile addon", "Where add-on profile snapshots are stored"),
        default="",
        subtype='DIR_PATH',
    )
    sync_dir: StringProperty(
        name=tr("Thư mục đồng bộ", "Sync folder"),
        description=tr("Tuỳ chọn. Trỏ tới NAS hoặc thư mục Google Drive đã sync. "
                        "Hub chỉ ghi thêm bản manifest vào đây, việc đồng bộ để OS lo",
                        "Optional. Point to a NAS or a synced Google Drive folder. "
                        "The hub only adds the manifest here; the OS does the syncing"),
        default="",
        subtype='DIR_PATH',
    )
    profile_name: StringProperty(
        name=tr("Tên profile", "Profile name"),
        description=tr("Snapshot được lưu theo tên này", "Snapshots are stored under this name"),
        default="",
    )
    backup_all_blobs: BoolProperty(
        name=tr("Lưu zip cho mọi addon", "Zip every add-on"),
        description=tr("Mặc định hub chỉ zip addon nguồn thủ công (nhóm C) vì addon từ kho "
                        "tải lại được. Bật cái này nếu muốn Restore đúng y hệt phiên bản cũ, "
                        "đổi lại snapshot nặng hơn nhiều",
                        "By default the hub only zips manual-source add-ons (group C), since "
                        "repository add-ons can be downloaded again. Enable this to restore the "
                        "exact old versions, at the cost of much larger snapshots"),
        default=False,
    )
    mirror_blobs: BoolProperty(
        name=tr("Chép cả zip sang thư mục đồng bộ", "Copy zips to the sync folder too"),
        description=tr("CÂN NHẮC KỸ: zip có thể chứa addon trả phí. Để tắt thì chỉ manifest "
                        "được chép sang thư mục dùng chung",
                        "THINK TWICE: zips may contain paid add-ons. When off, only the "
                        "manifest is copied to the shared folder"),
        default=False,
    )

    def resolved_backup_dir(self):
        return bpy.path.abspath(self.backup_dir) if self.backup_dir else default_backup_dir()

    def resolved_profile_name(self):
        return self.profile_name.strip() or default_profile_name()

    def draw(self, context):
        layout = self.layout

        layout.label(text=tr("Hub nằm ở View3D > phím N > tab 'EZG Hub'.",
                             "The hub lives in View3D > N key > 'EZG Hub' tab."), icon='INFO')
        row = layout.row()
        row.label(text=tr("Ngôn ngữ mọi addon EZG", "Language of all EZG add-ons"))
        ezg_i18n.draw_toggle(row, "ezg")
        layout.separator()

        box = layout.box()
        box.label(text=tr("Kho addon EZG", "EZG add-on repository"), icon='URL')
        box.prop(self, "repo_url", text="URL")
        box.prop(self, "access_token", text="Token")  # i18n-skip

        box = layout.box()
        box.label(text="Backup profile", icon='FILE_BACKUP')  # i18n-skip
        box.prop(self, "profile_name",
                 text=tr("Tên profile", "Profile name") if self.profile_name
                 else tr("Tên profile (%s)", "Profile name (%s)") % default_profile_name())
        box.prop(self, "backup_dir",
                 text=tr("Thư mục", "Folder") if self.backup_dir
                 else tr("Thư mục (mặc định)", "Folder (default)"))
        if not self.backup_dir:
            box.label(text=default_backup_dir(), icon='DOT')
        box.prop(self, "backup_all_blobs")

        box = layout.box()
        box.label(text=tr("Đồng bộ (tuỳ chọn)", "Sync (optional)"), icon='UV_SYNC_SELECT')
        box.prop(self, "sync_dir", text=tr("Thư mục", "Folder"))
        row = box.row()
        row.enabled = bool(self.sync_dir)
        row.prop(self, "mirror_blobs")
        if self.sync_dir and self.mirror_blobs:
            box.label(text=tr("Zip addon trả phí sẽ nằm trên thư mục dùng chung.", "Paid add-on zips will end up in the shared folder."), icon='ERROR')


def get(context=None):
    """Tra ve preferences cua hub, hoac None neu hub chua duoc bat."""
    ctx = context or bpy.context
    addon = ctx.preferences.addons.get(__package__)
    return addon.preferences if addon else None
