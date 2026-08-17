# Auto UV Palette

Add-on Blender: xếp UV của nhiều object vào các ô của một tấm palette dùng chung.

## Cài đặt

Blender > Edit > Preferences > Add-ons > mũi tên góc trên phải > **Install from Disk…**
> chọn `auto_uv_palette-1.0.0.zip`.

Yêu cầu Blender 4.2 trở lên.

## Cách dùng

1. Ở **Object Mode**, chọn các object cần xếp.
2. Mở sidebar bằng phím `N` (trong 3D Viewport hoặc UV Editor) > tab **UV Palette**.
3. Nhập **Columns** và **Rows** (ví dụ 3 x 3, 4 x 4…).
4. Bảng preview cho thấy object nào vào ô nào (`H1 C2` = hàng 1, cột 2).
5. Bấm **Pack UVs into Palette** — xếp UV xong, add-on **tạo 1 material mới**
   (`UVPalette_3x3`…) và gán cho toàn bộ object đã chọn, thay thế material cũ.
   Material mới có sẵn 1 node Image Texture trống nối vào Base Color — chỗ gắn
   tấm palette sau khi ghép.

`Ctrl+Z` hoàn tác được như mọi thao tác Blender khác.

⚠️ **Thứ tự quan trọng**: vì Pack thay material, hãy chạy **Export Selected
Textures** (và **Clean Up** nếu muốn) **trước** khi Pack. Material cũ sau khi
bị thay sẽ không còn ai dùng — lưu file là Blender purge, texture chưa export
sẽ mất. Pack sẽ tự cảnh báo nếu phát hiện object có texture chưa export.

Quy trình đầy đủ: **Export → Clean Up → Pack → Build PSD → Assign Palette**.

## Quy tắc xếp

- **Thứ tự**: theo tên object, hiểu số nên `2. Body` đứng trước `10. Head`.
  Đặt tiền tố số vào tên để kiểm soát vị trí.
- **Hướng**: ô đầu tiên ở góc trên–trái, chạy hết hàng từ trái sang phải rồi
  xuống hàng dưới.
- **Scale**: map thẳng không gian UV 0–1 lên ô. Grid 3x3 thì UV nhân `1/3`, UV
  `(0,0)` về góc ô và `(1,1)` về góc đối diện. Add-on **không** đo bounding box,
  **không** phóng to cho lấp kín ô, **không** canh giữa — nên vị trí tương đối
  của UV trong tile được giữ nguyên, và texel density giữa các object bằng nhau.
  Object nào UV gốc chỉ chiếm 0.2–0.5 thì trong ô vẫn chỉ chiếm phần tương ứng.
- **Không padding**: ô sát nhau, không chừa khoảng đệm. Nếu về sau cần chống
  bleeding khi bake hoặc mipmap thì thêm sau.
- Mỗi object chiếm đúng 1 ô, không object nào chồng lên object khác.

Add-on giả định UV gốc nằm trong khoảng 0–1. UV tràn ra ngoài 0–1 (tiling) sẽ
tràn khỏi ô và đè sang ô bên cạnh — add-on không kiểm tra việc này.

Với grid không vuông (ví dụ 4 cột x 2 hàng) thì ô rộng `1/4` cao `1/2`, nên U và
V bị scale khác nhau và texture sẽ méo. Dùng grid vuông (3x3, 4x4…) nếu không
muốn méo.

## Export Textures

Xuất texture trong material của từng object đã chọn ra PNG.

1. Chọn các object (cùng danh sách với phần xếp UV).
2. Chọn **Size**: 2K / 4K / 8K — áp dụng cho toàn bộ, mọi ảnh ra đều vuông và
   cùng kích thước.
3. Chọn **Path** — thư mục đích, tự tạo nếu chưa có.
4. Bấm **Export Selected Textures**.

Quy tắc:

- **Tên file** lấy theo tên object: `1. Gas_m5` → `1. Gas_m5.png`. Ký tự không
  hợp lệ cho tên file (`< > : " / \ | ? *`) bị thay bằng `_`.
- **Chọn texture nào**: node Image Texture nối vào **Base Color**. Nếu không có
  node nào nối Base Color thì lấy ảnh duy nhất tìm được trong material (tìm cả
  trong node group). Nếu có nhiều ảnh mà không phân biệt được, object đó bị bỏ
  qua kèm thông báo — add-on không đoán bừa.
- **Texture gốc dưới 2048px thì bỏ qua**, không phóng to lên cho đủ size. Danh
  sách bị bỏ qua có trong thông báo kết quả.
- **Ảnh gốc không bị thay đổi**: add-on scale trên một bản copy tạm rồi xoá.
- File trùng tên sẽ **bị ghi đè**, số lượng ghi đè có trong thông báo.
- Ảnh xuất ra là PNG 8-bit. Nguồn là JPG không có alpha nên Blender ghi RGB
  (không kèm kênh alpha).

Object đang **ẩn** (`H`) không nằm trong `selected_objects` của Blender nên
không được export. Bấm `Alt+H` để hiện lại trước khi chạy.

### Clean Up Exported Textures

Xóa khỏi file .blend các texture **đã export ra PNG** — ảnh packed 4K/8K chiếm
phần lớn dung lượng file, export xong rồi thì không cần giữ bản trong .blend
nữa. Bấm nút sẽ có hộp thoại xác nhận (xóa datablock không undo được đáng
tin cậy).

Lưới an toàn — texture chỉ bị xóa khi:

- File PNG tương ứng (theo tên object) **đã tồn tại** trong thư mục export.
  Chưa export thì giữ nguyên, không xóa.
- Không còn material của object **ngoài selection** nào dùng ảnh đó. Ảnh dùng
  chung với object chưa chọn sẽ được giữ lại kèm thông báo.

Sau khi xóa, node Image Texture trong material vẫn còn nhưng trống (không còn
trỏ tới ảnh nào) — đúng chỗ để gắn tấm palette mới vào. **Lưu file** (`Ctrl+S`)
thì dung lượng .blend mới giảm thật.

### Clean Up Old Materials

Xóa khỏi file .blend các **material cũ** của những object đã export texture ra
PNG. Chạy sau **Clean Up Exported Textures** để dọn nốt vỏ material rỗng, hoặc
chạy thẳng cũng được — material bị xóa thì texture bên trong thành mồ côi, lưu
file là Blender tự dọn. Cũng có hộp thoại xác nhận như phần xóa texture.

Lưới an toàn — material chỉ bị xóa khi:

- Object gắn nó **đã có file PNG** (theo tên object) trong thư mục export.
  Chưa export thì material được giữ nguyên.
- Material **có node Image Texture** (kể cả node đã trống sau Clean Up
  texture). Material thuần màu không gắn texture sẽ được giữ lại.
- **Không phải** material palette do add-on tạo (tên bắt đầu `UVPalette_`).
- Không còn object **ngoài selection** nào dùng material đó.

Object bị xóa hết material sẽ được dọn luôn slot rỗng — Pack UVs chạy sau đó
vẫn gán material palette chung như bình thường.

## Palette PSD (Smart Object)

Ghép các PNG đã export thành 1 file Photoshop, mỗi texture là **1 layer Smart
Object** nằm đúng ô của nó — thứ tự y hệt phần xếp UV. Cần cài Photoshop.

1. Chạy **Export Selected Textures** trước (phần trên) — PSD dùng chính các PNG đó.
2. Nhập **Canvas** (px, canvas vuông). Panel hiện kích thước ô; nếu canvas
   không chia hết cho số cột/hàng sẽ cảnh báo kèm gợi ý số gần nhất (ví dụ
   grid 3x3 dùng 3072 thay vì 2048).
3. Chọn **Linked** (PSD trỏ tới file PNG, sửa PNG là PSD tự cập nhật — nhưng
   đừng di chuyển/xoá folder PNG) hoặc **Embedded** (nhúng hẳn vào PSD, tự
   chứa nhưng nặng).
4. Bấm **Build Palette PSD** — add-on ghi `auto_uv_palette_build.jsx` vào thư
   mục export rồi mở Photoshop chạy script đó. Photoshop tự dựng document,
   Place từng PNG thành Smart Object, scale vừa ô, đặt tên layer theo tên
   object. Bạn kiểm tra rồi tự **Save As** file PSD.

Nếu không tìm thấy Photoshop, add-on vẫn ghi file `.jsx` — chạy tay bằng
Photoshop > File > Scripts > Browse. Thứ tự layer trong bảng Layers: object
đầu tiên (ô trên–trái) nằm trên cùng.

Thiếu file PNG nào (chưa export, hoặc export bị bỏ qua vì texture nhỏ hơn 2K)
thì add-on báo lỗi và không mở Photoshop.

## Assign Palette

Bước cuối: gắn tấm palette đã ghép vào material chung.

1. Chọn các object (vẫn selection đó).
2. **Palette**: trỏ tới file ảnh palette — PNG, JPG, hoặc **PSD thẳng luôn**
   (Blender đọc được PSD, không cần export PNG trung gian; sửa PSD xong bấm
   gắn lại là cập nhật).
3. Bấm **Assign Palette to Material**.

Add-on nạp ảnh và gắn vào node Image Texture **trống** mà Pack đã tạo sẵn
trong `UVPalette_*`. Nếu material không có node trống thì dùng node đang nối
Base Color; không có node nào thì tạo mới và tự nối vào Base Color. Chạy lại
nhiều lần không tạo ảnh trùng lặp (ảnh đã nạp được reload thay vì nạp bản mới).

## Add-on sẽ báo lỗi và không làm gì khi

- Chưa chọn mesh object nào.
- Số object nhiều hơn số ô — thông báo cần bao nhiêu ô để bạn tăng Columns/Rows.
- Có object chưa tạo UV map, hoặc mesh rỗng.
- Nhiều object dùng chung một mesh data (linked duplicate) — không thể xếp vào
  hai ô khác nhau. Chạy `Object > Relations > Make Single User > Object & Data`
  trước.

