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
    for c in classes:
        bpy.utils.register_class(c)

    wm = bpy.types.WindowManager

    wm.ezg_tab = EnumProperty(
        name="Tab",
        items=[
            ('STORE', "Kho EZG", "Addon của EZG: cài và cập nhật", 'URL', 0),
            ('MACHINE', "Máy của tôi", "Mọi addon đang cài trên máy này", 'DESKTOP', 1),
            ('BACKUP', "Backup", "Lưu và phục hồi profile addon", 'FILE_BACKUP', 2),
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

    wm.ezg_restore_mode = EnumProperty(
        name="Chế độ",
        items=[
            ('LATEST', "Bản mới nhất",
             "Tải lại từ kho, chỉ dùng zip đã lưu khi nguồn không còn. Khuyên dùng"),
            ('EXACT', "Đúng bản đã lưu",
             "Cài đúng version trong snapshot. Bắt buộc phải có zip đi kèm"),
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

    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
