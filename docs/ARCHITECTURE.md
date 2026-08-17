# EZG Addon Hub — Thiết kế kiến trúc

> v0.2 — 2026-08-17. **Phạm vi hỗ trợ: Blender 4.5 LTS trở lên.**

## 1. Mục tiêu

1. **Backup / restore profile addon** theo từng artist.
2. Hỗ trợ cả addon cài từ Blender (extensions.blender.org) lẫn addon ngoài (Gumroad, Blender Market, zip lẻ).
3. **Phân phối addon custom của EZG**: user chọn → tải thẳng vào Blender; admin update → user thấy update.

## 2. Quyết định nền tảng

### 2.1 Chỉ hỗ trợ Blender ≥ 4.5

Cắt bỏ toàn bộ nhánh code cho Blender < 4.2. Mọi máy đều có hệ thống **Extensions**, nghĩa là hub được dùng:

- `bpy.ops.extensions.*` cho cài / gỡ / update
- Remote Repository tự host cho addon EZG
- `blender_manifest.toml` để khai báo tương thích version

### 2.2 Dựa lưng vào Remote Extension Repository

Blender 4.2+ cho phép tự host repo: chỉ cần một `index.json` ở URL bất kỳ. Blender tự lo liệt kê, cài,
**kiểm tra và cài update**, và xác thực bằng **Access Token** nếu repo private.

`index.json` do chính Blender sinh:

```
blender --command extension build          --source-dir=addons/ezg_rig_tools --output-dir=dist
blender --command extension server-generate --repo-dir=dist --html
```

**Hệ quả**: EZG không phải tự viết versioning, downloader, update-checker. Hub chỉ là mặt tiền.

### 2.3 Addon legacy vẫn tồn tại — hub vẫn phải xử lý

Dù chỉ hỗ trợ 4.5+, **addon legacy chưa biến mất**. Blender vẫn giữ nút "Install legacy Add-on" và thư mục
`scripts/addons/`. Phần lớn addon mua trên Blender Market / Gumroad vẫn ở dạng này. Hub **không cần cài legacy
theo cách cũ**, nhưng **bắt buộc phải quét được** `scripts/addons/` để backup không bỏ sót.

---

## 3. Hub là addon hay app độc lập? → **Addon-first (hybrid)**

- **Phần chính** = extension `ezg_addon_hub` cài vào Blender.
- **Phần phụ** = bootstrap `EZG-Hub-Setup.bat`, chạy 1 lần khi setup máy.

Lý do addon thắng: trạng thái **enabled** của addon nằm trong `userpref.blend` (nhị phân), bên ngoài không đọc
được; mọi thao tác cài/gỡ/bật đều phải qua `bpy.ops`. App ngoài vẫn phải gọi `blender --background --python`,
tức viết cả hai phần.

Bootstrap giải quyết 3 việc addon không tự làm được: máy mới chưa có gì để bấm, nhiều version Blender song song,
và điền Access Token của repo EZG.

```
EZG-Hub-Setup.bat
  ├── dò version Blender (registry + %APPDATA%\Blender Foundation\Blender\*)
  └── với mỗi version >= 4.5:
        blender --background --python bootstrap.py
          ├── cài extension ezg_addon_hub
          ├── add remote repository EZG + access token
          └── bpy.ops.wm.save_userpref()
```

Sau đó hub **tự update chính nó**, vì hub cũng nằm trong repo EZG như mọi addon khác.

---

## 4. Update addon — ba nhóm nguồn

Nguyên tắc: **hub lưu con trỏ tới nguồn, không mirror file của người khác.** Nhờ vậy hub không bao giờ có
"bản cũ" để bị trễ.

| Nhóm | Ví dụ | Ai lo update | Nút Update trong hub |
|---|---|---|---|
| **A** Extension có repo | extensions.blender.org, polygoniq | Blender | `repo_sync_all` + `package_upgrade_all` |
| **B** Addon custom EZG | ezg_rig_tools | Admin push release | Y hệt A (repo EZG cũng là remote repo) |
| **C** Addon zip rời / legacy | Blender Market, Gumroad | User | Hiện version + link trang bán; không tự tải được |

Hub có nút Update, nhưng nó là **proxy** gọi cơ chế gốc của Blender chứ không phục vụ file từ kho EZG.
Nhóm C thì hub nói thật là "nguồn thủ công" — giả vờ tự update sẽ khiến user cài đè nhầm bản cũ.

---

## 5. Nơi lưu dữ liệu

### 5.1 Addon custom EZG → GitHub

Google Drive không cho direct-download ổn định (trang confirm, quota, URL đổi) nên Blender **không dùng làm
remote repo được** — mà đó chính là thứ mang lại toàn bộ giá trị. GitHub có Releases, tag, rollback, và Actions
chạy `server-generate` tự động.

### 5.2 Backup profile → Local là gốc, thư mục chia sẻ là bản sao

Snapshot gồm hai loại dữ liệu có tính chất rất khác nhau, và **phải đối xử khác nhau**:

| Dữ liệu | Kích thước | Nhạy cảm | Lưu ở đâu |
|---|---|---|---|
| `manifest.json` — danh sách addon + version + nguồn | vài chục KB | thấp | **Local + mirror lên thư mục chia sẻ** |
| `blobs/*.zip` — file thật của addon nhóm C | vài trăm MB | **cao** (addon trả phí) | **Chỉ local**, mirror là tuỳ chọn có cảnh báo |
| `config.json` — token, đường dẫn, tuỳ chọn hub | vài KB | có token | **Chỉ local**, không bao giờ sync |

Nhóm A và B **không cần blob** vì tải lại được từ nguồn. Chỉ nhóm C mới zip lại. Nhờ vậy manifest thường
**dưới 1 MB** và bản mirror lên NAS rất nhẹ.

#### Bố cục thư mục

```
%USERPROFILE%\EZG Addon Hub\               ← gốc, luôn tồn tại, không cần cấu hình
├── config.json                            ← KHÔNG sync
└── profiles\
    └── hoang.nguyen\
        ├── latest.json                    ← con trỏ tới snapshot mới nhất
        ├── 2026-08-17_1030\
        │   ├── manifest.json
        │   └── blobs\
        │       └── some_paid_addon-2.4.1.zip
        └── 2026-08-12_0915\
            └── manifest.json
```

Trong hub có setting **"Thư mục đồng bộ"**. Nếu bật, mỗi lần backup hub ghi thêm một bản manifest vào:

```
\\NAS\ezg\addon-profiles\hoang.nguyen\      ← hoặc thư mục Google Drive Desktop đã sync
└── 2026-08-17_1030\manifest.json
```

**Điểm mấu chốt**: hub chỉ *ghi file*, việc đồng bộ để OS / Drive Desktop / NAS lo. Không cần viết code gọi
Google Drive API, không cần OAuth, không cần backend.

#### Vì sao không dùng server riêng ngay từ đầu

Server chỉ thêm giá trị khi cần dashboard kiểu "ai đang dùng addon gì" hoặc ép profile chuẩn từ trên xuống.
Trước khi có nhu cầu đó, nó chỉ thêm chi phí, auth, và một điểm chết. Để Phase 5.

#### Chính sách cần chốt: blob của addon trả phí

Nếu để `blobs/` trên NAS dùng chung, artist B có thể lấy addon mà artist A mua. Mặc định của hub là
**blob chỉ nằm local**, muốn mirror phải bật thủ công và hub hiện cảnh báo. Studio tự quyết chính sách;
hướng sạch nhất là mua **studio license** rồi đưa addon đó vào một repo EZG nội bộ (biến nhóm C thành nhóm B).

### 5.3 Luồng restore trên Blender mới

```
1. Cài Blender 4.5+ mới
2. Chạy EZG-Hub-Setup.bat        → hub + remote repo EZG đã sẵn sàng
3. Hub tự dò %USERPROFILE%\EZG Addon Hub\profiles\ và thư mục chia sẻ
4. User chọn snapshot → chế độ Latest (mặc định) hoặc Exact
5. Hub cài lại:
     nhóm A → extensions.package_install từ repo blender.org
     nhóm B → extensions.package_install từ repo EZG
     nhóm C → extensions.package_install_files từ blobs/  (thiếu blob → báo link tải thủ công)
6. Bật lại đúng những addon từng enabled
7. Báo cáo: đã cài X, bỏ qua Y (không tương thích), thiếu Z (không có blob) → cần khởi động lại
```

**Latest** tải bản mới nhất từ nguồn, blob chỉ dùng khi nguồn chết. **Exact** cài đúng version đã backup —
dành cho lúc dựng lại môi trường cho project cũ.

Nếu snapshot tạo từ 4.5 mà restore vào 5.2, hub đối chiếu `blender_version_min/max` và **bỏ qua có báo cáo**
thay vì cài rồi để Blender lỗi.

---

## 6. Cấu trúc repo GitHub

### Một repo duy nhất, mỗi addon một folder — đúng như bạn nói

```
ezg-addon-hub/                          ← 1 repo cho tất cả
├── addons/
│   ├── ezg_addon_hub/                  ← chính cái hub, tự update qua đây
│   │   ├── blender_manifest.toml
│   │   ├── __init__.py
│   │   ├── core/
│   │   └── ui/
│   ├── ezg_rig_tools/
│   │   ├── blender_manifest.toml
│   │   └── __init__.py
│   └── ezg_render_queue/
│       ├── blender_manifest.toml
│       └── __init__.py
├── catalog.toml                        ← metadata hiển thị: nhóm, mô tả VN, ảnh
├── thumbs/
├── docs/
├── tools/
│   ├── gen_catalog.py                  ← catalog.toml → catalog.json, kèm kiểm tra nhất quán
│   └── build_local.ps1                 ← chạy y hệt CI, để test trước khi push
└── .github/workflows/release.yml

        ↓ GitHub Actions build → GitHub Pages

https://<org>.github.io/ezg-addon-hub/   ← Blender đọc URL này
├── index.json
├── catalog.json
├── ezg_deco_namer-1.5.0.zip
└── ezg_fbx_batch-1.5.3.zip
```

Dùng **một repo duy nhất**: `main` chứa source, bản phân phối do Actions build rồi đẩy thẳng lên
GitHub Pages qua `upload-pages-artifact` — **không commit build output vào nhánh nào cả**. Đỡ được
nhánh `gh-pages` lẫn nguy cơ zip trong repo lệch với zip đang phục vụ.

`catalog.toml` dùng TOML chứ không phải YAML/JSON vì `tomllib` có sẵn trong Python 3.11 đi kèm Blender —
nghĩa là máy admin và runner CI **không cần cài Python riêng hay thư viện nào**.

### Quy tắc bắt buộc cho mỗi folder addon

| Quy tắc | Vì sao |
|---|---|
| Phải có `blender_manifest.toml` | Không có thì không phải extension |
| `id` phải **unique và không bao giờ đổi** | Đổi id = Blender coi là addon khác → user mất settings, cài trùng |
| `version` phải bump mỗi lần release | Không bump thì Blender không thấy có update |
| `blender_version_min = "4.5.0"` | Chốt phạm vi hỗ trợ |
| Import phải là relative, tham chiếu module dùng `__package__` | Yêu cầu của extension; module name thật là `bl_ext.<repo>.<id>` |
| Dependency Python đóng gói bằng **wheels** | Không được `pip install` lúc runtime |

### GitHub Actions làm gì

Mỗi lần push vào `main`:

1. Tải Blender 4.5 LTS (portable) vào runner, có cache
2. Với mỗi folder trong `addons/`: `extension validate` rồi `extension build` → `dist/`
3. `extension server-generate --repo-dir=dist --html`
4. Sinh `catalog.json` từ `catalog.toml` — **thất bại nếu catalog và index lệch id**
5. Deploy `dist/` lên GitHub Pages

Kết quả: URL cố định `https://<org>.github.io/ezg-addon-hub/index.json` để dán vào Blender.
**Admin release addon = sửa version trong toml rồi push. Không thao tác tay nào khác.**

---

## 7. Kiến trúc client

```
┌────────────────────── Extension: ezg_addon_hub (trong Blender) ──────────────────────┐
│  UI                                                                                  │
│    ├─ Tab "Kho EZG"      addon custom, nút Cài / Update      (đọc catalog.json)       │
│    ├─ Tab "Máy của tôi"  mọi addon đang cài, nguồn, version, enabled                  │
│    └─ Tab "Backup"       tạo snapshot / restore (Latest | Exact)                      │
│  Core                                                                                │
│    ├─ scanner.py   quét extensions/ + scripts/addons/ + trạng thái enabled            │
│    ├─ origin.py    phân loại nguồn A / B / C                                          │
│    ├─ backup.py    manifest.json + blobs/                                             │
│    ├─ restore.py   latest-first, blob fallback, báo cáo bỏ sót                        │
│    └─ bridge.py    wrapper quanh bpy.ops.extensions.*                                 │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Đường dẫn liên quan (Windows, `<ver>` = 4.5 / 5.x):

- Extensions: `%APPDATA%\Blender Foundation\Blender\<ver>\extensions\<repo>\<pkg_id>\`
- Legacy addons: `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\`
- Trạng thái enabled: `userpref.blend` — chỉ đọc được qua `bpy.context.preferences.addons`

Module name của extension là `bl_ext.<repo_module>.<pkg_id>`, không phải tên thư mục trần. Scanner phải map
đúng mới so khớp được với `preferences.addons.keys()`.

---

## 8. Định dạng manifest snapshot

```json
{
  "schema": 1,
  "profile": "hoang.nguyen",
  "created_utc": "2026-08-17T10:30:00Z",
  "blender": { "version": [4, 5, 2], "os": "windows" },
  "items": [
    {
      "pkg_id": "node_wrangler",
      "name": "Node Wrangler",
      "version": "3.6.1",
      "enabled": true,
      "kind": "extension",
      "origin": { "group": "A", "repo_url": "https://extensions.blender.org/api/v1/extensions/" },
      "blob": null
    },
    {
      "pkg_id": "ezg_rig_tools",
      "version": "1.2.0",
      "enabled": true,
      "kind": "extension",
      "origin": { "group": "B", "repo_url": "https://<org>.github.io/ezg-addon-hub/index.json" },
      "blob": null
    },
    {
      "pkg_id": "some_paid_addon",
      "version": "2.4.1",
      "enabled": false,
      "kind": "legacy_addon",
      "origin": { "group": "C", "homepage": "https://blendermarket.com/products/..." },
      "blob": "blobs/some_paid_addon-2.4.1.zip",
      "sha256": "…"
    }
  ]
}
```

---

## 9. Rủi ro & xử lý

| Vấn đề | Xử lý |
|---|---|
| Cần restart sau update | Blender không hot-reload module đang chạy. Hub hiện badge "cần khởi động lại", không giả vờ đã xong |
| Extension có Python wheels | Zip lại thư mục đã cài có thể hỏng wheels → luôn ưu tiên tải lại từ repo, blob chỉ là fallback |
| Addon trả phí trong blob | Mặc định blob chỉ local. Không đẩy addon trả phí lên repo EZG dùng chung |
| Restore chéo version (4.5 → 5.2) | Đối chiếu `blender_version_min/max`, bỏ qua có báo cáo |
| Token lộ | Token read-only, scope hẹp, xoay định kỳ. `config.json` không bao giờ sync |
| Đổi `id` của addon | Cấm tuyệt đối sau release đầu tiên |

---

## 10. Lộ trình

**Phase 1 — Nền** (giá trị lớn nhất, công ít nhất)
- Repo `ezg-addon-hub` + Actions build/validate/server-generate + GitHub Pages
- Kiểm chứng: add remote repo thủ công trong Blender, cài 1 addon, bump version rồi push, xác nhận nút Update hiện lên

> Xong Phase 1 là **mục tiêu 3 (phân phối + update addon custom) đã chạy được**, chưa cần dòng code hub nào.

**Phase 2 — Hub client**: scanner, tab "Máy của tôi", tab "Kho EZG", nút Update proxy.

**Phase 3 — Backup / Restore**: manifest + blob, chế độ Latest / Exact, thư mục đồng bộ.

**Phase 4 — Bootstrap**: `EZG-Hub-Setup.bat` dò version, cài hub, ghi repo + token.

**Phase 5 (nếu cần)**: CLI `--background` cho farm, dashboard thống kê tập trung.

---

## 11. Nguồn tham khảo

- Static Extensions Repository — https://docs.blender.org/manual/en/latest/advanced/extensions/creating_repository/static_repository.html
- Extensions Command Line Arguments — https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html
- Get Extensions (Preferences) — https://docs.blender.org/manual/en/latest/editors/preferences/extensions.html
- Add-ons (legacy vs extension) — https://docs.blender.org/manual/en/latest/advanced/extensions/addons.html
- bpy.ops.extensions — https://docs.blender.org/api/current/bpy.ops.extensions.html
- Access token cho remote repo — https://projects.blender.org/blender/blender/issues/121856
- Ví dụ repo thật: polygoniq/extensions — https://github.com/polygoniq/extensions
