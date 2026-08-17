# Mixamo Animation Library (Blender 4.x – 5.x)

Add-on thư viện animation cho Blender: quét một thư mục chứa các file **FBX tải từ Mixamo**, liệt kê toàn bộ animation trong sidebar, và áp animation trực tiếp lên rig đang chọn — không cần import/xoá thủ công từng file.

## Tính năng

- **Quét thư mục** (đệ quy) chứa file `.fbx` Mixamo, hiện danh sách có ô tìm kiếm trong panel.
- **Apply to Selected Armature** — import FBX ngầm, copy action sang armature đang chọn (rig Mixamo cùng bộ xương `mixamorig:`), rồi tự xoá object tạm. Cảnh báo nếu tên xương không khớp.
- **In Place** — tự phát hiện và loại bỏ kênh root motion trên Hips (walk/run tiến về trước → đứng tại chỗ).
- **Import as New Character** — import nguyên nhân vật (mesh + rig + anim).
- **Import All as Actions** — import hàng loạt cả thư viện thành Actions (có fake user) để dùng trong Action Editor / NLA.
- **Push to NLA** và **Set Frame Range** tuỳ chọn.
- **Apply tự khớp rotation mode của rig** — Mixamo FBX luôn về dạng quaternion; nếu rig đã đổi sang Euler thì action import vào sẽ *không báo lỗi gì mà nhân vật đứng im một pose*. Từ v1.4.1, Apply / Import All / Reimport tự resample action theo mode hiện tại của xương.
- **Convert Rotation Keys** — 1 nút đổi kênh rotation của xương giữa **Quaternion (W/X/Y/Z)** và **XYZ Euler**, resample lại keyframe nên animation giữ nguyên. Cần dùng nút này vì dropdown *Rotation* trong N-panel **chỉ đổi `rotation_mode` của xương mà không chuyển key sẵn có** → key quaternion thành mồ côi, pose đứng/gãy. Mặc định quét mọi action thuộc rig (list ✓, strip NLA, action giữ bằng fake user) và đồng bộ `rotation_mode` cho cả những rig dùng chung action.
- Dấu ✓ trong danh sách cho biết animation đã được import thành Action.
- Tương thích **slotted actions** của Blender 4.4+.

## Cài đặt

### Blender 4.2 trở lên (Extensions)
1. Nén thư mục `mixamo_anim_lib` thành `.zip` (hoặc dùng file zip có sẵn).
2. `Edit > Preferences > Get Extensions > ▾ (góc phải) > Install from Disk…` → chọn file zip.

### Blender 4.0 / 4.1 (Legacy add-on)
1. `Edit > Preferences > Add-ons > Install…` → chọn file zip.
2. Bật checkbox **Mixamo Animation Library**.

## Cách dùng

1. Tải animation từ [mixamo.com](https://www.mixamo.com) ở định dạng **FBX Binary, With Skin** (hoặc Without Skin nếu đã có nhân vật) và gom về một thư mục.
2. Mở panel: **3D Viewport → phím N → tab "Mixamo Lib"**.
3. Chọn thư mục thư viện → addon tự quét (hoặc bấm **Scan Library**).
4. Chọn armature nhân vật trong scene, chọn animation trong danh sách, bấm **Apply to Selected Armature**.

> Lưu ý: việc copy action trực tiếp chỉ đúng khi rig đích cùng bộ xương Mixamo (tên xương `mixamorig:...`, cùng tỉ lệ). Với rig khác (Rigify, tự dựng…) cần retarget bằng công cụ chuyên dụng.

## Cấu trúc

```
mixamo_anim_lib/
├── __init__.py            # toàn bộ logic add-on
└── blender_manifest.toml  # manifest cho hệ thống Extensions 4.2+
```
