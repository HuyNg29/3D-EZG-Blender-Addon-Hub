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
        description="Dia chi index.json cua kho addon EZG",
        default=DEFAULT_REPO_URL,
    )
    access_token: StringProperty(
        name="Access token",
        description="Chi can neu kho EZG dat o che do private",
        default="",
        subtype='PASSWORD',
    )
    backup_dir: StringProperty(
        name="Thu muc backup",
        description="Noi luu snapshot profile addon",
        default="",
        subtype='DIR_PATH',
    )
    sync_dir: StringProperty(
        name="Thu muc dong bo",
        description=("Tuy chon. Tro toi NAS hoac thu muc Google Drive da sync. "
                     "Hub chi ghi them ban manifest vao day, viec dong bo de OS lo"),
        default="",
        subtype='DIR_PATH',
    )
    profile_name: StringProperty(
        name="Ten profile",
        description="Snapshot duoc luu theo ten nay",
        default="",
    )
    backup_all_blobs: BoolProperty(
        name="Luu zip cho moi addon",
        description=("Mac dinh hub chi zip addon nguon thu cong (nhom C) vi addon tu kho "
                     "tai lai duoc. Bat cai nay neu muon Restore dung y het phien ban cu, "
                     "doi lai snapshot nang hon nhieu"),
        default=False,
    )
    mirror_blobs: BoolProperty(
        name="Chep ca zip sang thu muc dong bo",
        description=("CAN NHAC KY: zip co the chua addon tra phi. De tat thi chi manifest "
                     "duoc chep sang thu muc dung chung"),
        default=False,
    )

    def resolved_backup_dir(self):
        return bpy.path.abspath(self.backup_dir) if self.backup_dir else default_backup_dir()

    def resolved_profile_name(self):
        return self.profile_name.strip() or default_profile_name()

    def draw(self, context):
        layout = self.layout

        layout.label(text="Hub nam o View3D > phim N > tab 'EZG Hub'.", icon='INFO')
        layout.separator()

        box = layout.box()
        box.label(text="Kho addon EZG", icon='URL')
        box.prop(self, "repo_url", text="URL")
        box.prop(self, "access_token", text="Token")

        box = layout.box()
        box.label(text="Backup profile", icon='FILE_BACKUP')
        box.prop(self, "profile_name",
                 text="Ten profile" if self.profile_name else "Ten profile (%s)" % default_profile_name())
        box.prop(self, "backup_dir",
                 text="Thu muc" if self.backup_dir else "Thu muc (mac dinh)")
        if not self.backup_dir:
            box.label(text=default_backup_dir(), icon='DOT')
        box.prop(self, "backup_all_blobs")

        box = layout.box()
        box.label(text="Dong bo (tuy chon)", icon='UV_SYNC_SELECT')
        box.prop(self, "sync_dir", text="Thu muc")
        row = box.row()
        row.enabled = bool(self.sync_dir)
        row.prop(self, "mirror_blobs")
        if self.sync_dir and self.mirror_blobs:
            box.label(text="Zip addon tra phi se nam tren thu muc dung chung.", icon='ERROR')


def get(context=None):
    """Tra ve preferences cua hub, hoac None neu hub chua duoc bat."""
    ctx = context or bpy.context
    addon = ctx.preferences.addons.get(__package__)
    return addon.preferences if addon else None
