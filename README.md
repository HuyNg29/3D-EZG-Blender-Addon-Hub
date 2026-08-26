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

| id | Tên | Version | Nhóm |
|---|---|---|---|
| `ezg_addon_hub` | EZG Addon Hub | 0.1.0 | Hub |
| `ezg_fbx_batch` | FBX Batch to Blend Converter | 1.5.3 | Pipeline |
| `ezg_deco_namer` | Deco Namer | 1.5.0 | Modeling / UV |
| `ezg_auto_uv_palette` | Auto UV Palette | 1.0.0 | Modeling / UV |
| `ezg_gn_info_namer` | GN Info Namer | 1.4.0 | Geometry Nodes |
| `ezg_mixamo_marker_rigger` | Manual Marker Mixamo Rigger | 0.21.0 | Rigging / Animation |
| `ezg_mixamo_anim_lib` | Mixamo Animation Library | 1.4.2 | Rigging / Animation |
| `ezg_anim_tools` | EZG Animation Tools | 1.1.0 | Rigging / Animation |

Mọi `id` đều mang tiền tố `ezg_` để không đụng tên với addon trên extensions.blender.org.

Ba addon cuối từng được phát hành thủ công dưới dạng zip với id **không** có tiền tố
(`auto_uv_palette`, `mixamo_anim_lib`, `mixamo_marker_rigger`). Bản cài tay đó là một dòng
riêng: Blender coi nó là addon khác, sẽ không tự cập nhật, và sẽ hiện panel trùng.
**Gỡ bản cài tay trước khi cài từ kho.** Tab "Máy của tôi" trong hub chỉ ra các cặp trùng này.

Hub nằm ở **View3D → phím N → tab "EZG Hub"**, gồm ba tab con: **Kho EZG** (cài addon công ty),
**Máy của tôi** (kiểm kê mọi addon đang có, kèm nguồn gốc và bản mới), **Backup** (lưu và phục hồi
profile addon).

---

## Dành cho artist: cài hub

Tải một file này về rồi **double-click**:

```
https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/EZG-Hub-Setup.bat
```

Nó tự tìm mọi bản Blender trên máy, đăng ký kho EZG, cài và bật hub. Xong mở Blender,
bấm phím **N**, vào tab **EZG Hub**.

**Đóng Blender trước khi chạy.** Blender ghi đè `userpref.blend` lúc thoát, nên cài
trong khi Blender đang mở thì thiết lập sẽ mất ngay khi bạn đóng nó. Trình cài đặt có
kiểm tra và sẽ từ chối chạy nếu thấy Blender đang mở.

<details>
<summary>Hoặc làm thủ công</summary>

**Preferences → Get Extensions → Repositories → [+] → Add Remote Repository**, dán URL:

```
https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json
```

Rồi tìm "EZG Addon Hub" trong Get Extensions và bấm Install.

</details>

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
| `blender_version_min` khai đúng mức tương thích thật | Hub cần `4.5.0`; addon khác cứ để mức thấp nhất nó chạy được, tối thiểu `4.2.0` vì Extensions không tồn tại trước đó |
| `tagline` tối đa **64 ký tự**, không kết thúc bằng dấu câu | Blender từ chối manifest dài hơn — `extension validate` bắt được |
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

| Test | Kiểm tra |
|---|---|
| `test_addons_load.py` | Mọi addon trong `addons/` bật và tắt được dưới hệ thống Extensions |
| `test_hub.py` | 22 kiểm tra cho hub: quét máy, tải kho, backup, restore |
| `test_mmr.py` | Bộ test của Marker Mixamo Rigger |
| `test_mixamo_compat.py` | Rig sinh ra khớp rig Mixamo thật (**cần FBX mẫu**) |

Một số test cần bộ FBX mẫu của Mixamo. Bộ này nặng ~33 MB nên **không nằm trong git**:

```powershell
.\tools\run_tests.ps1 -Assets "D:\EZG Addon Assets\MixamoLibResource"
```

Không trỏ tới thì các test đó tự bỏ qua, **không** tính là thất bại. Mặc định script tìm ở
`D:\EZG Addon Assets\MixamoLibResource`.

`tests/stale/` chứa test tạm treo — logic còn giá trị nhưng kịch bản dựng dữ liệu đã lỗi thời.
`run_tests.ps1` không quét thư mục con nên chúng không chạy. Lý do ở [tests/stale/README.md](tests/stale/README.md).

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

## Trình cài đặt một file

`dist/EZG-Hub-Setup.bat` được sinh tự động, **không sửa tay**. Mã nguồn ở `tools/bootstrap/`:

| File | Việc |
|---|---|
| `install_hub.ps1` | Tìm Blender (PATH, Program Files, registry, thư viện Steam), chạy bootstrap cho từng bản |
| `bootstrap.py` | Chạy trong Blender: đăng ký kho EZG, cài hub, bật, lưu preferences |

`tools/build_installer.py` ghép hai file trên, mã hoá base64 rồi nhúng vào một `.bat`.
Base64 chỉ gồm `A-Za-z0-9+/=` nên không ký tự nào bị `cmd.exe` diễn giải nhầm — tránh
được toàn bộ vấn đề escape của batch. Lúc chạy, `.bat` giải mã bằng `certutil` có sẵn
trong Windows, nên máy artist không cần cài thêm gì.

Build lại:

```powershell
python tools\build_installer.py --out dist\EZG-Hub-Setup.bat
```

CI cũng chạy bước này và publish file lên Pages.

## Dữ liệu để ngoài git

| Thứ | Ở đâu | Vì sao |
|---|---|---|
| FBX mẫu của Mixamo (~33 MB) | `D:\EZG Addon Assets\MixamoLibResource` | Nặng, chỉ dùng cho test; đưa vào git sẽ phình repo và làm Pages chậm |
| `backup_before_nla_move.blend` (34 MB) | `D:\EZG Addon Assets` | File backup lúc phát triển, không phải mã nguồn |

Nên chuyển thư mục này lên NAS của EZG để máy khác cũng chạy được các test cần asset.

## Công cụ kèm theo

`tools/unity-fix/` — bộ script vá pipeline xuất FBX từ Blender sang Unity, đi kèm
Mixamo Animation Library từ trước. Xem `tools/unity-fix/README.txt`.

## Chưa có trong repo

- `thumbs/` — ảnh thumbnail cho catalog
