# Test đang tạm treo

`tools\run_tests.ps1` chỉ quét `tests\test_*.py` ở tầng ngoài, **không** đệ quy — nên
hai test trong thư mục này không chạy.

Chúng được giữ lại vì phần logic kiểm tra vẫn có giá trị, chỉ là **kịch bản dựng dữ liệu
đã lỗi thời**, không phải addon hỏng.

## Vì sao treo

Cả hai test dựng một nhân vật chân ngắn tổng hợp bằng `ezg_mixamo_marker_rigger`, áp một
animation Mixamo, rồi **kỳ vọng bàn chân lún xuống dưới sàn**, sau đó kiểm tra tính năng
floor-lock / foot-IK có kéo chân lên không.

Chạy lại hôm nay, phép đo đầu tiên đã sai tiền đề:

```
without floor-lock: lowest foot Z = 0.253
FAIL feet sink below floor without lock (0.253)
```

`0.253` là số **dương** — bàn chân đang lơ lửng **trên** sàn 25 cm chứ không lún xuống.
Nghĩa là tình huống mà test muốn tạo ra đã không xảy ra, nên phần kiểm tra floor-lock phía
sau **chưa từng được thực thi có ý nghĩa**. Đây không phải bằng chứng floor-lock hỏng.

Nguyên nhân nhiều khả năng: hai test viết ngày 06/07/2026, còn `ezg_mixamo_marker_rigger`
sau đó đã đổi cách dựng armature cho khớp Mixamo — object xoay **+90° trục X** và scale
**0.01**, dữ liệu xương lưu **Y-up theo centimet** (xem `addons/ezg_mixamo_marker_rigger/README.md`).
Nhân vật tổng hợp trong test vì thế ra tỉ lệ và cao độ khác hẳn dự tính ban đầu.

## Cần làm gì để bật lại

Dựng lại phần fixture sao cho nhân vật thật sự có chân lún dưới sàn theo quy ước rig mới,
rồi chuyển file về lại `tests/`. Phần assert từ dòng `bake_foot_floor_lock` trở đi giữ nguyên
được — chỉ hình học đầu vào cần sửa.

Cả hai cũng cần bộ FBX mẫu; xem `kit.assets_dir()` và tham số `-Assets` của `run_tests.ps1`.
