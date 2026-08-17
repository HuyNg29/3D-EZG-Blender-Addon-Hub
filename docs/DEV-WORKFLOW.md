# Quy trình phát triển addon & chuyển đổi từ Addon Bundle Installer

> v0.1 — 2026-08-17. Kèm theo [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Một nguồn sự thật duy nhất: folder trong repo

Đúng như hình dung: sau khi đưa addon vào repo hub, **folder trong repo là bản gốc duy nhất**.
Mọi bản copy rải rác trên máy phải bị xoá đi, nếu không sớm muộn bạn sẽ sửa nhầm bản chết.

```
D:\3D EZG Addon Hub\
└── addons\
    ├── ezg_deco_namer\
    │   ├── blender_manifest.toml
    │   └── __init__.py          ← sửa ở đây
    └── ezg_fbx_batch\
```

Vòng đời một thay đổi:

```
sửa file trong addons\ezg_deco_namer\
      ↓
bump version trong blender_manifest.toml
      ↓
git commit + push
      ↓
GitHub Actions: validate → build → server-generate → deploy gh-pages
      ↓
user bấm Check for Updates trong Blender (hoặc hub) → thấy bản mới
```

## 2. Đừng copy file qua lại để test

Cạm bẫy lớn nhất của quy trình trên là: sửa trong repo → zip → cài vào Blender → test → phát hiện lỗi →
sửa tiếp. Vòng lặp đó quá chậm và rất dễ sửa nhầm bản đã cài rồi mất khi cài đè.

Cách đúng, cũng là cách Blender khuyến nghị chính thức: **trỏ Blender thẳng vào folder repo** bằng một
Local Repository.

```
Preferences → Get Extensions → Repositories → [+] → Add Local Repository
    Name:             EZG Dev
    Custom Directory: ☑  D:\3D EZG Addon Hub\addons
```

Blender quét `<dir>/<pkg_id>/blender_manifest.toml`, mà repo của ta có bố cục đúng như vậy — nên **toàn bộ
addon trong repo hiện ra trong Blender ngay lập tức, không cần cài, không cần copy**. Sửa file, bấm reload
(hoặc restart Blender), thấy kết quả. Commit khi hài lòng.

Vì Blender có thể ghi file cache vào thư mục đó, thêm vào `.gitignore`:

```gitignore
addons/**/__pycache__/
addons/.blender_ext/
```

> Nếu chỉ muốn phơi ra vài addon thay vì cả repo, tạo một thư mục dev riêng rồi tạo **junction** trỏ về repo
> (junction không cần quyền admin, khác với symlink):
> ```powershell
> New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\4.5\extensions\ezg_dev\ezg_deco_namer" -Target "D:\3D EZG Addon Hub\addons\ezg_deco_namer"
> ```

**Lưu ý quan trọng**: repo "EZG Dev" (local) và repo "EZG" (remote, bản phát hành) là hai repo khác nhau
trong Blender. Máy admin nên **tắt repo remote EZG** khi đang dev, tránh cảnh có hai bản cùng một addon
cùng lúc.

---

## 3. Hiện trạng: `addon_bundle_installer.zip`

Bản addon cũ đã làm được đúng phần UX cần thiết: liệt kê addon, tick chọn, một nút cài + enable hết,
hiện trạng thái "đã cài". Phần logic đó **giữ lại và tái dùng gần như nguyên vẹn** cho tab "Kho EZG".

Nhưng cách phân phối thì cần thay, vì ba vấn đề cấu trúc:

### 3.1 Không update được từng addon

Addon con nằm *bên trong* zip của bundle. Sửa một dòng trong `deco_namer.py` là phải phát lại
toàn bộ zip 477 KB cho mọi người, và mỗi người phải gỡ + cài lại thủ công. Đây chính xác là vấn đề mà
remote repository giải quyết: mỗi addon là một gói độc lập, có version riêng, update riêng.

### 3.2 `Add to bundle` ghi vào thư mục cài — dữ liệu sẽ mất

```python
def get_bundle_dir():
    return os.path.join(os.path.dirname(__file__), BUNDLED_DIRNAME)
```

`bundled/` nằm ngay trong thư mục addon đã cài của Blender. Khi cài đè bản bundle mới,
`addon_install(overwrite=True)` xoá thư mục cũ → **mọi addon bạn đã thêm vào bundle biến mất**.
Thư mục cài là chỗ tệ nhất để lưu dữ liệu người dùng.

### 3.3 Bundle phình theo thời gian

Mọi user tải toàn bộ bundle dù chỉ dùng một addon. Hiện đã 477 KB với 4 addon; thêm vài addon nữa là
hàng chục MB. Remote repo chỉ tải đúng thứ user chọn.

---

## 4. Bốn addon trong bundle đi về đâu

| File | Tác giả | Nhóm | Xử lý |
|---|---|---|---|
| `deco_namer.py` (8.5 KB) | **EZG** | B | → `addons/ezg_deco_namer/` trong repo hub |
| `fbx_batch_to_blend_new.py` (21 KB) | **Vit (EZG)** | B | → `addons/ezg_fbx_batch/` |
| `blender_mcp.py` (118 KB) | Siddharth Ahuja (bên thứ ba) | A/C | **Không** đưa vào repo EZG. Trỏ tới GitHub gốc |
| `Tripo3d_Blender_Bridge.zip` (456 KB) | Tripo3D (bên thứ ba) | A/C | **Không** đưa vào repo EZG. Trỏ tới nguồn gốc |

**456 KB / 477 KB của bundle hiện tại là addon của bên thứ ba.** Đưa chúng vào repo EZG là tự chuốc lấy
đúng vấn đề đã bàn: bản trong hub sẽ mãi mãi trễ hơn bản gốc, và phải bảo trì thủ công. Hai addon này thuộc
nhóm A/C — hub chỉ hiển thị và trỏ tới nguồn, để nguồn tự lo update.

Sau khi lọc, repo EZG khởi đầu với **2 addon thật sự của mình, tổng 30 KB**.

---

## 5. Chuyển một addon single-file sang extension

Extension bắt buộc là **thư mục** có `blender_manifest.toml`, nên `deco_namer.py` thành:

```
addons/ezg_deco_namer/
├── blender_manifest.toml
└── __init__.py            ← chính là nội dung deco_namer.py cũ, bỏ bl_info
```

```toml
schema_version = "1.0.0"

id = "ezg_deco_namer"          # KHÔNG BAO GIỜ đổi sau lần release đầu
name = "Deco Namer"
version = "1.5.0"
tagline = "Doi ten mesh theo tien to deco_NN_"
maintainer = "EZG <visual-01@easygoing.vn>"
type = "add-on"
blender_version_min = "4.5.0"
license = ["SPDX:GPL-3.0-or-later"]
```

Bốn thay đổi trong code:

1. Xoá `bl_info` (thông tin chuyển vào manifest).
2. `bl_idname = __name__` trong `AddonPreferences` → `bl_idname = __package__`.
3. Mọi import nội bộ đổi sang **relative** (`from . import xyz`).
4. Dependency Python (nếu có) đóng gói bằng **wheels**, không `pip install` lúc chạy.

Kiểm tra trước khi commit:

```bash
blender --command extension validate addons/ezg_deco_namer
```

---

## 6. Chạy test — luôn dùng `tools\run_tests.ps1`

```powershell
.\tools\run_tests.ps1
```

**Không bao giờ gọi `blender --python tests\...` trực tiếp.**

Test của hub phải gọi `bpy.ops.wm.save_userpref()` để kiểm tra luồng cài đặt. Nếu chạy trên config thật,
lệnh đó **ghi đè `userpref.blend` của bạn** — mất trạng thái bật/tắt của mọi addon, asset library,
theme, keymap, và preferences riêng của từng addon (kể cả API key). Nguy hiểm nhất là khi kết hợp với
`--factory-startup`: Blender nạp thiết lập mặc định rồi lưu đè lên bản thật.

Việc này **đã xảy ra thật một lần** trong quá trình phát triển. Blender không giữ bản sao lưu nào của
`userpref.blend`, nên không khôi phục lại được.

`run_tests.ps1` đặt biến `BLENDER_USER_RESOURCES` trỏ sang một thư mục tạm, khiến Blender dùng
config / scripts / extensions trong sandbox đó và xoá đi sau khi chạy. `tests/test_hub.py` cũng
tự thoát ngay nếu không thấy biến này, nên không chạy nhầm được.

---

## 7. Phần code cũ tái dùng được cho hub

| Từ `addon_bundle_installer` | Dùng lại vào |
|---|---|
| `ABI_UL_addons`, `draw_bundle_ui` | UI tab "Kho EZG" — gần như copy nguyên |
| `refresh_items` | `scanner.py`, đổi nguồn từ `bundled/` sang `catalog.json` + repo |
| `ABI_OT_install_selected` (tick nhiều → cài hàng loạt) | `restore.py` và nút "Cài nhiều" |
| `extract_bl_info` bằng AST (không `exec`) | Giữ, dùng để đọc addon **legacy** nhóm C khi backup |
| `addon_utils.check(module)` | Giữ, nhưng extension có module là `bl_ext.<repo>.<id>` |

Hai chỗ phải thay:

- `bpy.ops.preferences.addon_install(filepath=…)` → `bpy.ops.extensions.package_install(repo_index=…, pkg_id=…)`
- Nguồn file: thư mục `bundled/` cục bộ → remote repository
