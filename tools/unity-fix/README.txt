UNITY .BLEND ANIMATION FIX
==========================

Vấn đề: kéo file .blend vào Unity chỉ ra 1 clip tên "Scene",
mất hết các animation clip (NLA strips) đã dựng trong Blender.

Nguyên nhân: script chuyển đổi của Unity (Unity-BlenderToFBX.py)
export FBX với bake_anim_use_nla_strips=False.

CÁCH DÙNG
---------
Cách 1 (khuyên dùng): double-click patch-unity.bat
  - Tự xin quyền Administrator (bấm Yes ở hộp thoại UAC)
  - Tự tìm và vá MỌI phiên bản Unity trong C:\Program Files\Unity
  - Tự backup file gốc thành Unity-BlenderToFBX.py.bak

Cách 2 (thủ công): chép file Unity-BlenderToFBX.py trong thư mục này
đè vào:
  C:\Program Files\Unity\Hub\Editor\<phiên bản>\Editor\Data\Tools\
(cần quyền Administrator)

Sau khi vá: trong Unity, right-click asset .blend -> Reimport.

LƯU Ý
-----
- Phải vá lại sau khi update Unity hoặc cài phiên bản Unity mới
  (chạy lại patch-unity.bat là xong).
- Sau khi vá, chỉ những animation đã đưa vào NLA (nút
  "Stash All to NLA (Unity)" của addon Mixamo Animation Library)
  mới được export sang Unity.
- Máy phải cài Blender và .blend phải được liên kết mở bằng Blender.
