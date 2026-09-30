"""Tuy chon cua hub. Luu trong userpref.blend cua Blender, khong phai file rieng."""

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import AddonPreferences

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
        name="URL kho EZG",
        description="Địa chỉ index.json của kho addon EZG",
        default=DEFAULT_REPO_URL,
    )
    access_token: StringProperty(
        name="Access token",
        description="Chỉ cần nếu kho EZG đặt ở chế độ private",
        default="",
        subtype='PASSWORD',
    )
    backup_dir: StringProperty(
        name="Thư mục backup",
        description="Nơi lưu snapshot profile addon",
        default="",
        subtype='DIR_PATH',
    )
    sync_dir: StringProperty(
        name="Thư mục đồng bộ",
        description=("Tuỳ chọn. Trỏ tới NAS hoặc thư mục Google Drive đã sync. "
                     "Hub chỉ ghi thêm bản manifest vào đây, việc đồng bộ để OS lo"),
        default="",
        subtype='DIR_PATH',
    )
    profile_name: StringProperty(
        name="Tên profile",
        description="Snapshot được lưu theo tên này",
        default="",
    )
    backup_all_blobs: BoolProperty(
        name="Lưu zip cho mọi addon",
        description=("Mặc định hub chỉ zip addon nguồn thủ công (nhóm C) vì addon từ kho "
                     "tải lại được. Bật cái này nếu muốn Restore đúng y hệt phiên bản cũ, "
                     "đổi lại snapshot nặng hơn nhiều"),
        default=False,
    )
    mirror_blobs: BoolProperty(
        name="Chép cả zip sang thư mục đồng bộ",
        description=("CÂN NHẮC KỸ: zip có thể chứa addon trả phí. Để tắt thì chỉ manifest "
                     "được chép sang thư mục dùng chung"),
        default=False,
    )

    def resolved_backup_dir(self):
        return bpy.path.abspath(self.backup_dir) if self.backup_dir else default_backup_dir()

    def resolved_profile_name(self):
        return self.profile_name.strip() or default_profile_name()

    def draw(self, context):
        layout = self.layout

        layout.label(text="Hub nằm ở View3D > phím N > tab 'EZG Hub'.", icon='INFO')
        layout.separator()

        box = layout.box()
        box.label(text="Kho addon EZG", icon='URL')
        box.prop(self, "repo_url", text="URL")
        box.prop(self, "access_token", text="Token")

        box = layout.box()
        box.label(text="Backup profile", icon='FILE_BACKUP')
        box.prop(self, "profile_name",
                 text="Tên profile" if self.profile_name else "Tên profile (%s)" % default_profile_name())
        box.prop(self, "backup_dir",
                 text="Thư mục" if self.backup_dir else "Thư mục (mặc định)")
        if not self.backup_dir:
            box.label(text=default_backup_dir(), icon='DOT')
        box.prop(self, "backup_all_blobs")

        box = layout.box()
        box.label(text="Đồng bộ (tuỳ chọn)", icon='UV_SYNC_SELECT')
        box.prop(self, "sync_dir", text="Thư mục")
        row = box.row()
        row.enabled = bool(self.sync_dir)
        row.prop(self, "mirror_blobs")
        if self.sync_dir and self.mirror_blobs:
            box.label(text="Zip addon trả phí sẽ nằm trên thư mục dùng chung.", icon='ERROR')


def get(context=None):
    """Tra ve preferences cua hub, hoac None neu hub chua duoc bat."""
    ctx = context or bpy.context
    addon = ctx.preferences.addons.get(__package__)
    return addon.preferences if addon else None
