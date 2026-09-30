"""Giao dien hub: 3 tab Kho EZG / May cua toi / Backup.

Ham draw_hub() duoc dung o ca N-panel lan Preferences nen hai noi luon giong nhau.
"""

import os

import bpy
# Phai import o day, KHONG duoc import trong ham. `import bpy.utils.previews`
# gan ten `bpy` vao pham vi cuc bo, khien Python coi `bpy` la bien local trong
# CA ham do — moi dong dung `bpy` truoc dong import se nem UnboundLocalError.
import bpy.utils.previews
from bpy.types import Panel, UIList

from . import prefs as prefs_mod, scanner

CATEGORY = "EZG Hub"

# Icon theo NGUON GOC addon, khong phai theo chuc nang:
#   A  kho ngoai (extensions.blender.org...)  -> qua cau: tai tu Internet ve
#   B  kho EZG                                -> kien hang: do minh phat hanh
#   C  nguon thu cong                         -> thu muc: cai tu file tren dia
#
# Doi icon o day neu muon. Vai lua chon hop li cho nhom B, deu co san trong
# Blender 4.5: 'PACKAGE', 'SOLO_ON', 'FAKE_USER_ON', 'COMMUNITY', 'BOOKMARKS',
# 'MODIFIER'. Tranh 'FUND' - do la icon quyen gop, de gay hieu nham.
#
# Muon dung dung logo EZG thi khong can sua day, xem ICON_FILE ben duoi.
GROUP_ICON = {
    "A": 'WORLD',
    "B": 'PACKAGE',
    "C": 'FILE_FOLDER',
}

# Tha mot file PNG vuong (khuyen nghi 32x32 hoac 64x64, nen trong suot) vao
# addons/ezg_addon_hub/icons/ezg_logo.png la addon EZG se hien dung logo do
# thay cho icon co san. Khong co file thi tu dung lai GROUP_ICON["B"].
ICON_FILE = "ezg_logo.png"

_previews = None
_version = None


def _icons_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def _ezg_icon_id():
    """icon_id cua logo EZG, hoac 0 neu khong co file logo."""
    if _previews is None:
        return 0
    entry = _previews.get("ezg_logo")
    return entry.icon_id if entry else 0


def group_icon(group):
    """kwargs icon cho layout.label()/operator().

    Blender nhan icon co san qua `icon=` (chuoi) nhung icon tu anh qua
    `icon_value=` (so nguyen), nen phai tra ve kwargs chu khong tra ve mot gia tri.
    """
    if group == "B":
        icon_id = _ezg_icon_id()
        if icon_id:
            return {"icon_value": icon_id}
    return {"icon": GROUP_ICON.get(group, 'DOT')}


def hub_version():
    """Version cua chinh hub, doc tu blender_manifest.toml di kem.

    Hien o goc duoi giao dien de biet chac dang chay ban nao — huu ich nhat
    ngay sau khi bam Update, vi Blender can khoi dong lai moi nap ban moi.
    """
    global _version
    if _version is None:
        here = os.path.dirname(os.path.abspath(__file__))
        _version = scanner.read_manifest(here).get("version", "?")
    return _version


def _label_lines(layout, text, icon='NONE'):
    """Blender khong tu xuong dong trong label nen tu tach theo dau xuong dong."""
    first = True
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        layout.label(text=line, icon=icon if first else 'NONE')
        first = False


# ---------------------------------------------------------------------------
# UILists
# ---------------------------------------------------------------------------

class EZG_UL_catalog(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        if item.is_external:
            row.label(text=item.title, icon='LINKED')
        elif item.installed:
            row.label(text=item.title, icon='CHECKMARK')
        else:
            row.label(text=item.title, icon='DOT')

        sub = row.row()
        sub.alignment = 'RIGHT'
        if item.is_external:
            sub.label(text="bên thứ ba")
        elif item.installed and scanner.is_newer(item.version, item.installed_version):
            sub.label(text="v%s mới" % item.version, icon='TRIA_UP')
        elif item.version:
            sub.label(text="v" + item.version)


class EZG_UL_inventory(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text="", icon='CHECKBOX_HLT' if item.enabled else 'CHECKBOX_DEHLT')
        row.label(text=item.name, **group_icon(item.group))

        sub = row.row()
        sub.alignment = 'RIGHT'
        if item.update_version:
            sub.label(text="v%s > v%s" % (item.version, item.update_version), icon='TRIA_UP')
        elif item.version:
            sub.label(text="v" + item.version)


class EZG_UL_snapshots(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon='FILE_BACKUP')
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text="%d addon" % item.count)


# ---------------------------------------------------------------------------
# Tab: Kho EZG
# ---------------------------------------------------------------------------

def draw_store(layout, context):
    wm = context.window_manager
    p = prefs_mod.get(context)

    repo = scanner.find_repo_by_url(p.repo_url) if p else None
    if repo is None:
        box = layout.box()
        box.label(text="Kho EZG chưa được đăng kí trong Blender.", icon='ERROR')
        box.label(text="Cần bước này thì Blender mới tự kiểm tra cập nhật được.")
        box.operator("ezg.setup_repo", icon='PLUS')
        layout.separator()

    row = layout.row(align=True)
    row.operator("ezg.refresh_store", text="Tải lại kho", icon='FILE_REFRESH')

    if len(wm.ezg_catalog) == 0:
        layout.label(text="Bấm 'Tải lại kho' để xem danh sách addon EZG.", icon='INFO')
        return

    layout.template_list("EZG_UL_catalog", "", wm, "ezg_catalog", wm, "ezg_catalog_index", rows=7)

    if not (0 <= wm.ezg_catalog_index < len(wm.ezg_catalog)):
        return

    item = wm.ezg_catalog[wm.ezg_catalog_index]
    box = layout.box()

    head = box.row()
    if item.is_external:
        head.label(text=item.title, icon='LINKED')
    else:
        head.label(text=item.title, **group_icon("B"))
    if item.recommended:
        sub = head.row()
        sub.alignment = 'RIGHT'
        sub.label(text="khuyên dùng", icon='SOLO_ON')

    if item.group_label:
        box.label(text="Nhóm: " + item.group_label)

    if item.summary:
        _label_lines(box.column(align=True), item.summary)

    if item.is_external:
        box.separator()
        box.label(text="Addon của bên thứ ba — EZG không phát hành lại.", icon='INFO')
        if item.installed:
            box.label(text="Đang cài: v%s" % item.installed_version, icon='CHECKMARK')
        box.operator("ezg.open_url", text="Mở trang gốc", icon='URL').url = item.homepage
        return

    box.separator()
    if not item.installed:
        op = box.operator("ezg.install", text="Cài vào Blender", icon='IMPORT')
        op.pkg_id = item.pkg_id
    elif scanner.is_newer(item.version, item.installed_version):
        box.label(text="Đang cài v%s, kho có v%s" % (item.installed_version, item.version),
                  icon='TRIA_UP')
        box.operator("ezg.update_all", text="Cập nhật", icon='IMPORT')
    else:
        box.label(text="Đã cài bản mới nhất (v%s)" % item.installed_version, icon='CHECKMARK')


# ---------------------------------------------------------------------------
# Tab: May cua toi
# ---------------------------------------------------------------------------

def draw_machine(layout, context):
    wm = context.window_manager

    row = layout.row(align=True)
    row.operator("ezg.refresh_inventory", text="Quét lại", icon='FILE_REFRESH').check_updates = False
    row.operator("ezg.refresh_inventory", text="Kiểm tra bản mới", icon='URL').check_updates = True

    if len(wm.ezg_inventory) == 0:
        layout.label(text="Bấm 'Quét lại' để xem addon đang cài.", icon='INFO')
        return

    n_update = sum(1 for i in wm.ezg_inventory if i.update_version)
    n_manual = sum(1 for i in wm.ezg_inventory if i.group == "C")

    info = layout.row()
    info.label(text="%d addon | %d thủ công" % (len(wm.ezg_inventory), n_manual))
    if n_update:
        sub = info.row()
        sub.alignment = 'RIGHT'
        sub.label(text="%d bản mới" % n_update, icon='TRIA_UP')

    layout.template_list("EZG_UL_inventory", "", wm, "ezg_inventory", wm, "ezg_inventory_index", rows=8)

    if n_update:
        col = layout.column(align=True)

        one = col.row()
        one.scale_y = 1.2
        one.operator("ezg.update_selected", text="Cập nhật mục đang chọn", icon='IMPORT')

        big = col.row()
        big.scale_y = 1.3
        big.operator("ezg.update_all", text="Cập nhật tất cả", icon='IMPORT')

    if not (0 <= wm.ezg_inventory_index < len(wm.ezg_inventory)):
        return

    item = wm.ezg_inventory[wm.ezg_inventory_index]
    box = layout.box()
    box.label(text=item.name, **group_icon(item.group))
    box.label(text="Phiên bản: v%s" % (item.version or "?"))
    box.label(text="Nguồn: %s" % item.source_label)
    box.label(text="Trạng thái: %s" % ("đang bật" if item.enabled else "đang tắt"))

    if item.group == "C":
        box.separator()
        box.label(text="Nguồn thủ công — hub không tự cập nhật được.", icon='INFO')
        if item.homepage:
            box.operator("ezg.open_url", text="Mở trang nguồn", icon='URL').url = item.homepage
        else:
            box.label(text="Addon này không khai báo trang nguồn.")
    elif item.update_version:
        box.separator()
        box.label(text="Có bản mới: v%s" % item.update_version, icon='TRIA_UP')


# ---------------------------------------------------------------------------
# Tab: Backup
# ---------------------------------------------------------------------------

def draw_backup(layout, context):
    wm = context.window_manager
    p = prefs_mod.get(context)
    if p is None:
        return

    box = layout.box()
    box.label(text="Profile: %s" % p.resolved_profile_name(), icon='USER')
    box.label(text=p.resolved_backup_dir())
    if p.sync_dir:
        box.label(text="Đồng bộ: " + p.sync_dir, icon='UV_SYNC_SELECT')

    n_manual = sum(1 for i in wm.ezg_inventory if i.group == "C")
    if len(wm.ezg_inventory):
        note = layout.column(align=True)
        note.label(text="Sẽ lưu %d addon, trong đó %d addon thủ công được zip kèm."
                        % (len(wm.ezg_inventory), n_manual), icon='INFO')
    else:
        layout.label(text="Sang tab 'Máy của tôi' bấm Quét lại để xem sẽ lưu gì.", icon='INFO')

    big = layout.row()
    big.scale_y = 1.4
    big.operator("ezg.backup_create", text="TẠO BACKUP", icon='FILE_BACKUP')

    layout.separator()
    row = layout.row(align=True)
    row.label(text="Bản đã lưu")
    sub = row.row()
    sub.alignment = 'RIGHT'
    sub.operator("ezg.refresh_snapshots", text="", icon='FILE_REFRESH')

    if len(wm.ezg_snapshots) == 0:
        layout.label(text="Chưa có bản backup nào.", icon='DOT')
        return

    layout.template_list("EZG_UL_snapshots", "", wm, "ezg_snapshots", wm, "ezg_snapshots_index", rows=4)

    if not (0 <= wm.ezg_snapshots_index < len(wm.ezg_snapshots)):
        return

    snap = wm.ezg_snapshots[wm.ezg_snapshots_index]
    box = layout.box()
    box.label(text="Tạo lúc: %s" % (snap.created or snap.name))
    box.label(text="%d addon, %d có zip kèm" % (snap.count, snap.blobs))
    if snap.blender:
        box.label(text="Từ Blender %s" % snap.blender)

    box.separator()
    box.prop(wm, "ezg_restore_mode", text="")
    if wm.ezg_restore_mode == 'EXACT' and snap.blobs < snap.count:
        box.label(text="Chỉ %d/%d addon có zip — số còn lại sẽ bị bỏ qua."
                       % (snap.blobs, snap.count), icon='ERROR')

    op = box.operator("ezg.restore", text="Phục hồi", icon='IMPORT')
    op.path = snap.path
    op.mode = wm.ezg_restore_mode


# ---------------------------------------------------------------------------
# Khung chung
# ---------------------------------------------------------------------------

def draw_hub(layout, context):
    wm = context.window_manager

    row = layout.row()
    row.scale_y = 1.2
    row.prop(wm, "ezg_tab", expand=True)
    layout.separator()

    if wm.ezg_tab == 'STORE':
        draw_store(layout, context)
    elif wm.ezg_tab == 'MACHINE':
        draw_machine(layout, context)
    else:
        draw_backup(layout, context)

    if wm.ezg_error:
        layout.separator()
        box = layout.box()
        _label_lines(box, wm.ezg_error, icon='ERROR')
    elif wm.ezg_status:
        layout.separator()
        layout.label(text=wm.ezg_status, icon='INFO')

    foot = layout.row()
    foot.alignment = 'RIGHT'
    foot.active = False
    foot.label(text="EZG Hub v%s" % hub_version())


class EZG_PT_hub(Panel):
    bl_label = "EZG Addon Hub"
    bl_idname = "EZG_PT_hub"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    def draw(self, context):
        draw_hub(self.layout, context)


classes = (
    EZG_UL_catalog,
    EZG_UL_inventory,
    EZG_UL_snapshots,
    EZG_PT_hub,
)


def register():
    global _previews

    # Icon tu file anh phai nap qua preview collection; khong co file logo thi
    # bo qua, group_icon() se tu quay ve icon co san cua Blender.
    try:
        _previews = bpy.utils.previews.new()
        path = os.path.join(_icons_dir(), ICON_FILE)
        if os.path.isfile(path):
            _previews.load("ezg_logo", path, 'IMAGE')
    except Exception as exc:
        print("[EZG Hub] Khong nap duoc logo: %s" % exc)
        _previews = None

    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    global _previews

    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception as exc:
            # KHONG nuot im lang: go class that bai se lam lan bat ke tiep chet
            # voi "already registered", ma nguyen nhan that thi da bi giau mat.
            print("[EZG Hub] Khong go duoc %s: %s" % (c.__name__, exc))

    if _previews is not None:
        try:
            bpy.utils.previews.remove(_previews)
        except Exception as exc:
            print("[EZG Hub] Khong giai phong duoc preview: %s" % exc)
        _previews = None
