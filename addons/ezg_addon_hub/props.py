"""Kieu du lieu cho UI. Gan vao WindowManager nen khong dinh vao file .blend."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import ezg_i18n
from .ezg_i18n import tr


class EZG_InventoryItem(PropertyGroup):
    """Mot addon dang cai tren may — tab 'May cua toi'."""
    pkg_id: StringProperty()
    module: StringProperty()
    name: StringProperty()
    version: StringProperty()
    enabled: BoolProperty()
    group: StringProperty()          # A / B / C
    source_label: StringProperty()
    homepage: StringProperty()
    repo_module: StringProperty()     # rong voi addon legacy
    update_version: StringProperty()  # rong neu khong co ban moi


class EZG_CatalogItem(PropertyGroup):
    """Mot muc trong kho EZG — tab 'Kho EZG'."""
    pkg_id: StringProperty()
    title: StringProperty()
    summary: StringProperty()
    summary_en: StringProperty()
    version: StringProperty()
    group_label: StringProperty()
    installed: BoolProperty()
    installed_version: StringProperty()
    recommended: BoolProperty()
    is_external: BoolProperty()      # addon ben thu ba, hub chi tro toi nguon
    homepage: StringProperty()


class EZG_SnapshotItem(PropertyGroup):
    """Mot ban backup da luu — tab 'Backup'."""
    name: StringProperty()
    path: StringProperty()
    created: StringProperty()
    count: IntProperty()
    blobs: IntProperty()
    blender: StringProperty()


classes = (
    EZG_InventoryItem,
    EZG_CatalogItem,
    EZG_SnapshotItem,
)


def register():
    ezg_i18n.register_classes(classes)

    wm = bpy.types.WindowManager

    wm.ezg_tab = EnumProperty(
        name="Tab",  # i18n-skip
        items=[
            ('STORE', tr("Kho EZG", "EZG Store"),
             tr("Addon của EZG: cài và cập nhật", "EZG add-ons: install and update"), 'URL', 0),
            ('MACHINE', tr("Máy của tôi", "My machine"),
             tr("Mọi addon đang cài trên máy này", "Every add-on installed on this machine"),
             'DESKTOP', 1),
            ('BACKUP', "Backup",  # i18n-skip
             tr("Lưu và phục hồi profile addon", "Save and restore add-on profiles"),
             'FILE_BACKUP', 2),
        ],
        default='STORE',
    )

    wm.ezg_inventory = CollectionProperty(type=EZG_InventoryItem)
    wm.ezg_inventory_index = IntProperty(default=0)

    wm.ezg_catalog = CollectionProperty(type=EZG_CatalogItem)
    wm.ezg_catalog_index = IntProperty(default=0)

    wm.ezg_snapshots = CollectionProperty(type=EZG_SnapshotItem)
    wm.ezg_snapshots_index = IntProperty(default=0)

    wm.ezg_status = StringProperty(default="")
    wm.ezg_error = StringProperty(default="")

    # Dang ki lai la do vua doi VI/EN: thong bao cu dang o ngon ngu kia, bo di.
    try:
        bpy.context.window_manager.ezg_status = ""
        bpy.context.window_manager.ezg_error = ""
    except AttributeError:
        pass  # luc Blender khoi dong context chua co window_manager

    wm.ezg_restore_mode = EnumProperty(
        name=tr("Chế độ", "Mode"),
        items=[
            ('LATEST', tr("Bản mới nhất", "Latest version"),
             tr("Tải lại từ kho, chỉ dùng zip đã lưu khi nguồn không còn. Khuyên dùng", "Download again from the repository; use saved zips only when the source is gone. Recommended")),
            ('EXACT', tr("Đúng bản đã lưu", "Exact saved version"),
             tr("Cài đúng version trong snapshot. Bắt buộc phải có zip đi kèm", "Install the exact versions in the snapshot. Requires the zips")),
        ],
        default='LATEST',
    )


def unregister():
    wm = bpy.types.WindowManager
    for attr in ("ezg_tab", "ezg_inventory", "ezg_inventory_index",
                 "ezg_catalog", "ezg_catalog_index",
                 "ezg_snapshots", "ezg_snapshots_index",
                 "ezg_status", "ezg_error", "ezg_restore_mode"):
        try:
            delattr(wm, attr)
        except Exception:
            pass

    ezg_i18n.unregister_classes(classes)
