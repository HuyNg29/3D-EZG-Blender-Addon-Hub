# EZG Addon Hub

Kho addon nội bộ của EZG cho Blender **4.5 LTS trở lên**, phát hành dưới dạng
[Extensions Repository](https://docs.blender.org/manual/en/latest/advanced/extensions/creating_repository/static_repository.html)
mà Blender đọc trực tiếp.

Thiết kế chi tiết: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
Quy trình dev: [docs/DEV-WORKFLOW.md](docs/DEV-WORKFLOW.md)

---

## Trạng thái

Phase 1 — kho phát hành. Hub client (addon `ezg_addon_hub`) là Phase 2, chưa có trong repo này.

Addon hiện có:

| id | Tên | Version | Tác giả |
|---|---|---|---|
| `ezg_addon_hub` | EZG Addon Hub | 0.1.0 | EZG |
| `ezg_deco_namer` | Deco Namer | 1.5.0 | EZG |
| `ezg_fbx_batch` | FBX Batch to Blend Converter | 1.5.3 | Vit (EZG) |

Hub nằm ở **View3D → phím N → tab "EZG Hub"**, gồm ba tab con: **Kho EZG** (cài addon công ty),
**Máy của tôi** (kiểm kê mọi addon đang có, kèm nguồn gốc và bản mới), **Backup** (lưu và phục hồi
profile addon).

---

## Dành cho artist: cài addon EZG

Một lần duy nhất, trong Blender:

**Preferences → Get Extensions → Repositories → [+] → Add Remote Repository**, dán URL:

```
https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json
```

Từ đó về sau mọi addon EZG hiện trong danh sách Extensions, và **Check for Updates**
của Blender sẽ tự thấy bản mới. Không cần tải zip thủ công.

---

## Dành cho admin: thêm hoặc sửa một addon

### Cấu trúc

```
addons/<pkg_id>/
├── blender_manifest.toml    # bắt buộc
└── __init__.py
```

### Quy tắc bắt buộc

| Quy tắc | Vì sao |
|---|---|
| `id` **không bao giờ đổi** sau release đầu | Đổi id = Blender coi là addon khác → user mất settings, cài trùng |
| `version` phải bump mỗi lần release | Đây là thứ duy nhất Blender dùng để biết có update |
| `blender_version_min = "4.5.0"` | Phạm vi hỗ trợ đã chốt |
| Import nội bộ dùng relative (`from . import x`) | Module thật là `bl_ext.<repo>.<id>`, không phải tên thư mục |
| Tham chiếu module dùng `__package__`, không phải `__name__` | Ví dụ `AddonPreferences.bl_idname` |
| Dependency Python đóng gói bằng **wheels** | Không được `pip install` lúc chạy |
| `tags` phải nằm trong danh sách Blender công nhận | Sai tag → `extension validate` báo lỗi |

Không có `bl_info` trong extension — mọi thông tin đó nằm trong manifest.

### Phát hành

```bash
git commit -am "deco_namer: fix ..." && git push
```

GitHub Actions tự chạy validate → build → `server-generate` → deploy lên Pages.
**Sửa `version` trong manifest rồi push là xong**, không có thao tác tay nào khác.

### Chạy test

```powershell
.\tools\run_tests.ps1
```

**Đừng gọi `blender --python tests\...` trực tiếp** — test có ghi preferences, chạy ngoài sandbox
sẽ xoá sạch thiết lập Blender của bạn. Lý do chi tiết ở [docs/DEV-WORKFLOW.md](docs/DEV-WORKFLOW.md) mục 6.

### Build thử trước khi push

```powershell
.\tools\build_local.ps1
```

Chạy y hệt CI, kết quả trong `dist/`. Script tự dùng Python đi kèm Blender nên máy
không cần cài Python riêng. Nếu Blender ở chỗ khác:

```powershell
.\tools\build_local.ps1 -Blender "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
```

### Sửa code và thấy kết quả ngay

Đừng zip rồi cài lại mỗi lần. Trỏ Blender thẳng vào repo:

**Preferences → Get Extensions → Repositories → [+] → Add Local Repository**,
bật **Custom Directory** và chọn `<repo>\addons`.

Toàn bộ addon trong repo hiện ra trong Blender ngay, không cần cài. Chi tiết và các
lưu ý ở [docs/DEV-WORKFLOW.md](docs/DEV-WORKFLOW.md).

---

## catalog.toml

`index.json` (do Blender sinh) chỉ chứa dữ liệu kỹ thuật. `catalog.toml` bổ sung phần cho
người đọc — nhóm, mô tả tiếng Việt, thumbnail — và là thứ hub client sẽ đọc ở Phase 2.

`tools/gen_catalog.py` đối chiếu hai file: nếu `catalog.toml` mô tả một `id` không có
trong `index.json` (hoặc ngược lại), **build thất bại**. Điều này chặn trường hợp hub hiển
thị một mục chết mà không ai phát hiện.

Mục `[[external]]` trong `catalog.toml` dành cho addon **bên thứ ba** (BlenderMCP, Tripo3D…):
hub chỉ hiển thị và trỏ tới nguồn gốc, **không** đưa file vào repo EZG. Lý do ở
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) mục 4.

---

## Repo này là public — điều đó nghĩa là gì

Đã chọn public để GitHub Pages dùng được trên gói Free. Hệ quả cần nhớ khi commit:

- Toàn bộ **lịch sử commit** công khai vĩnh viễn. Xoá file ở commit sau **không** xoá nó khỏi lịch sử.
- Đừng bao giờ commit: access token, đường dẫn NAS nội bộ (`\\NAS\ezg\...`), tên khách hàng,
  hay bất cứ thứ gì trong `config.json` của hub.
- Backup profile của artist **không** thuộc repo này và không được đưa vào.
- Addon trả phí của bên thứ ba **không** được đưa vào — chỉ khai báo `[[external]]` trong
  `catalog.toml` để trỏ tới nguồn gốc.

Addon Blender dùng `bpy` vốn bắt buộc là GPL, nên việc công khai mã nguồn addon không tạo
ra nghĩa vụ mới nào. Thứ thật sự cần canh là những gì **vô tình** commit về sau.

---

## Chưa có trong repo

- `addons/ezg_addon_hub/` — hub client (Phase 2)
- `thumbs/` — ảnh thumbnail cho catalog
- `EZG-Hub-Setup.bat` — bootstrap cài hub vào mọi version Blender (Phase 4)
