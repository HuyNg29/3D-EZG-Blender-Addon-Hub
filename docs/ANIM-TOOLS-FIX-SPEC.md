> **Trạng thái (2026-09-22): đã thực hiện xong trong `ezg_anim_tools` 1.4.0** —
> commit `f6299cc`, kèm regression test trong `tests/test_anim_tools.py`.
>
> Giữ lại vì phần mô tả **lớp rig** (rest lệch roll 180°, cổ chân IK treo riêng
> vào root, xương leaf làm marker) và **ngưỡng nghiệm thu** ở §5 vẫn dùng được
> cho lần sau.
>
> **Một điểm trong spec đã được sửa khi thực hiện — §Lỗi 3 chẩn đoán nhầm chỗ.**
> Đo trên Blender 4.5.14: gán action **rỗng mới** rồi `keyframe_insert` thì
> Blender tự tạo và tự nối slot, nên thêm bind ở dòng `tgt_ob.animation_data
> .action = act` là no-op (`act.slots` lúc đó còn rỗng). Nguyên nhân thật là
> action **có sẵn** mang slot tên rig khác → `action_slot` về None; trong addon
> chỗ đó nằm ở **phía nguồn**. Đề xuất "luôn nạp lại slot" cũng không tái hiện
> được (đổi qua lại hai clip có slot cùng tên, Blender nối lại đúng mỗi lần) và
> rủi ro hơn với action nhiều slot, nên code giữ ngữ nghĩa `is None` của
> `mirror.py` và nâng thành `core.bind_slot()` dùng chung.

# Spec sửa lỗi: EZG Animation Tools (`ezg_anim_tools`)

**Người viết:** phiên làm việc retarget animation khủng long trong project Unity `i003`
**Ngày:** 2026-09-22
**Cho:** session có working tree của EZG Addon Hub

---

## 0. Bối cảnh — đọc trước khi sửa

Bản cài đang chạy:

```
C:\Users\admin\AppData\Roaming\Blender Foundation\Blender\4.5\extensions\ezg\ezg_anim_tools\
    __init__.py  bounce.py  core.py  mirror.py  ops.py  props.py  roles.py  ui.py
```

Blender **4.5.14 LTS**.

Bốn lỗi dưới đây đều được phát hiện khi retarget + mirror animation giữa hai rig khủng long
xuất từ Maya qua FBX (`a_ornit_04` 71 xương → `a_varmi_01` 34 xương). Đặc điểm của lớp rig này,
rất phổ biến với asset game mua ngoài:

- **Rest pose lệch 180° về hướng giữa hai bên** (vị trí đối xứng hoàn hảo — lệch 0.0 mm —
  nhưng roll của xương trái/phải ngược nhau). Chính `mirror.rest_symmetry_error()` phát hiện
  được điều này.
- **Cấu trúc IK**: cổ chân `EbackAnkle_L/R` treo thẳng vào xương gốc `ERoot_M` thành **nhánh
  riêng**, không nằm trong chuỗi FK `ERump → EbackHip → EbackKnee`. **Vị trí** của cổ chân
  chính là điểm đặt bàn chân.
- **Xương leaf làm marker**: `EbackKnee_L/R` không có xương con, chỉ dùng làm mốc đầu gối.

Cả 4 lỗi đều **hỏng âm thầm** — không exception, không cảnh báo, chỉ sai kết quả.

---

## Lỗi 1 — `mirror.py`: lật sai đối tượng (NGHIÊM TRỌNG NHẤT)

### Triệu chứng
Mirror xong, **xương về đúng vị trí gương** nhưng **mesh rách nát**. Đo bằng chỉ số méo cạnh
(xem §5): bản mirror ra **257–268 cạnh méo** trong khi mọi clip bình thường chỉ 15–66.

### Nguyên nhân
Hàm `mirror_action()` lật **ma trận tư thế**:

```python
Pm = Mx @ src_pose[f][src] @ Mx
```

Phép này chỉ tương đương ảnh gương khi **rest pose đối xứng**, tức `R_b = Mx · R_m · Mx`.
Rig có rest lệch 180° thì không thoả, và skin — vốn được định nghĩa theo rest — bị xoắn.

Điều thực sự điều khiển skin là **ma trận biến dạng** `D = P · R⁻¹`. Muốn mesh biến dạng đúng
ảnh gương thì phải thoả:

```
D_b = Mx · D_m · Mx
```

Suy ra:

```
P_b = Mx · P_m · R_m⁻¹ · Mx · R_b
```

Công thức này đúng **bất kể rest có đối xứng hay không**.

### Sửa

File `mirror.py`, trong `mirror_action()`, vòng `for f in range(f0, f1 + 1):`

**Hiện tại:**
```python
                Pm = Mx @ src_pose[f][src] @ Mx
                rot = Pm.to_quaternion().to_matrix().to_4x4()

                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
                loc = Pm.translation if parent is None else base.translation
                P[n] = Matrix.Translation(loc) @ rot
                ob.pose.bones[n].matrix_basis = base.inverted() @ P[n]
```

**Thay bằng:**
```python
                # Lat MA TRAN BIEN DANG (P @ rest^-1), khong phai ma tran tu the.
                # Skin duoc dinh nghia theo rest, nen chi co lat bien dang moi dung
                # khi rest pose hai ben khong doi xung ve huong.
                D = src_pose[f][src] @ rest[src].inverted()
                Pm = (Mx @ D @ Mx) @ rest[n]
                rot = Pm.to_quaternion().to_matrix().to_4x4()

                base = rest[n].copy() if parent is None else \
                    P[parent.name] @ (rest[parent.name].inverted() @ rest[n])
                P[n] = Matrix.Translation(Pm.translation) @ rot
                ob.pose.bones[n].matrix_basis = base.inverted() @ P[n]
```

### Ghi chú
- Phần ghi key **không cần đổi** — hàm đã `keyframe_insert("location")` cho mọi pose bone rồi.
- Sau khi sửa, cảnh báo của `rest_symmetry_error()` trở thành **thông tin tham khảo**, không còn
  là giới hạn. Nên sửa lại lời cảnh báo: hiện nó nói *"vị trí khớp hai bản sẽ lệch chút ít"*,
  quá nhẹ so với thực tế (skin rách hẳn) — và sau khi sửa thì không còn đúng nữa.

---

## Lỗi 2 — `mirror.py`: chỉ lật vị trí cho xương gốc

### Triệu chứng
Rig có xương mang vị trí thật (IK chân/tay) thì mirror **vứt sạch** vị trí đó. Ở rig thử nghiệm:
hai cổ chân IK mất vị trí → chân rơi tự do, mesh tụt **−0.64 m** dưới mặt đất.

### Nguyên nhân
```python
loc = Pm.translation if parent is None else base.translation
```
Mọi xương không phải root đều lấy vị trí **dựng lại từ rest**, bỏ qua vị trí đã animate.

### Sửa
**Tự hết theo Lỗi 1.** Với công thức biến dạng, `Pm.translation` đã là vị trí gương đúng cho
mọi xương, nên nhánh `if parent is None` biến mất hoàn toàn (xem code thay thế ở §1).

### Đánh đổi
Action kết quả sẽ có location key cho mọi xương → to hơn (ví dụ 238 fcurve thay vì 137).
Nếu cần gọn, thêm bước hậu xử lý: xoá fcurve `location` nào có **mọi** giá trị lệch 0 dưới
ngưỡng (ví dụ `1e-5`).

---

## Lỗi 3 — `core.py`: không nối Action Slot (Blender 4.4+)

### Triệu chứng
Bake ra **đủ fcurve, đủ keyframe, `report` rỗng, không một dòng báo lỗi** — nhưng **mọi giá
trị đứng yên tuyệt đối** (biên thiên = 0.0). Nhìn viewport vẫn thấy "có pose" nên rất dễ tưởng
là xong. Đây là lỗi tốn thời gian nhất.

### Nguyên nhân
Từ Blender 4.4, gán `animation_data.action` **không tự nối slot**. Action được liên kết nhưng
không kênh nào được nối → armature đứng im ở rest.

`mirror.py` **đã có** hàm `_bind_slot()` xử lý đúng. `core.py` thì **không gọi**:

```python
    act = bpy.data.actions.new(action_name)
    act.use_fake_user = True
    if tgt_ob.animation_data is None:
        tgt_ob.animation_data_create()
    tgt_ob.animation_data.action = act          # <-- thieu bind slot
```

### Sửa

1. Chuyển `_bind_slot()` từ `mirror.py` sang `core.py` (hoặc một module dùng chung), rồi gọi
   sau mỗi lần gán action — **cả phía nguồn lẫn phía đích**.

2. Quan trọng: hàm `_bind_slot` hiện chỉ nối khi `ad.action_slot is None`:
   ```python
   if ad.action_slot is None and getattr(action, "slots", None):
   ```
   **Chưa đủ.** Slot cũ còn sót lại từ action trước sẽ chặn việc nối slot mới → clip sau đọc
   nhầm dữ liệu clip trước. Ở rig thử nghiệm điều này làm **2 cặp clip bị bake trùng nhau**
   (`idle_head_death_left` chứa đúng animation của `right`). Phải **luôn nạp lại**:

   ```python
   def _bind_slot(ad, action):
       if not hasattr(ad, "action_slot"):
           return
       cands = list(getattr(ad, "action_suitable_slots", [])) or list(getattr(action, "slots", []))
       if cands:
           try:
               ad.action_slot = cands[0]
           except Exception:
               pass
   ```
   và khi gán action thì `ad.action = None` trước, rồi `ad.action = act`.

3. Thêm **gate** sau mỗi lần bake — lỗi này hỏng âm thầm nên phải có chốt tự động:
   ```python
   var = max((max(v) - min(v)) for v in
             ([k.co[1] for k in fc.keyframe_points] for fc in act.fcurves) if v)
   if var <= 1e-4:
       raise RetargetError(
           "Bake ra action tinh hoan toan. Nhieu kha nang armature nguon khong duoc "
           "danh gia (chua noi Action Slot, hoac dang o Rest Position).")
   ```

4. Thêm gate ở phía **nguồn**, trước khi bake: sample pose của một xương giữa thân ở 3 frame,
   nếu không đổi thì báo lỗi rõ ràng thay vì bake ra rác.

---

## Lỗi 4 — `core.py`: hai lỗi với rig kiểu IK

### 4a. Chỉ truyền vị trí cho xương role `hips`

```python
        for name in smap:
            pb = tgt_ob.pose.bones[name]
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if name == hips_tgt:
                pb.keyframe_insert("location", frame=f)
```

Đúng cho rig FK thuần. Sai với rig IK: cổ chân treo riêng vào root, **vị trí** của nó là điểm
đặt bàn chân. Bỏ nó đi thì cổ chân đứng nguyên ở rest trong khi thân di chuyển → chân kéo giãn.
Đo được: khoảng cách gối→cổ chân lệch tới **93%** so với rest, trong khi clip gốc chỉ 6–27%.

**Đề xuất:** thêm tuỳ chọn per-bone trong bảng mapping — cột "truyền vị trí" + ô chọn **xương
neo**. Công thức đã kiểm chứng tốt (giãn còn 7–17%, tốt hơn cả clip gốc):

```
v          = src_pos(bone) - src_pos(anchor)
k          = rest_dist(tgt_bone, tgt_anchor) / rest_dist(src_bone, src_anchor)
want_world = tgt_pos(anchor) + v * k
```

Tức: **giữ đúng tỉ lệ duỗi chi**, đặt theo hướng của nguồn nhưng dài theo chi của nhân vật đích.

Lưu ý thứ tự: xương neo phải được tính **trước** trong `hierarchy_order`, hoặc làm thành pass 2
sau vòng lặp chính. Ở rig thử nghiệm, `EbackAnkle_L` đứng **trước** `ERump_L → EbackHip_L →
EbackKnee_L` trong thứ tự duyệt, nên bắt buộc phải pass 2.

**Không nên** tự động đoán xương neo: neo cổ chân vào **hông** cho kết quả kém (27–42%), neo vào
**đầu gối** mới tốt (7–17%). Để người dùng chọn.

### 4b. `build_alignment` không kiểm tra quan hệ cha–con

```python
    for p in pairs:
        sc, tc = p.get("src_child"), p.get("tgt_child")
        if not sc or not tc:
            align[p["tgt"]] = None
            continue
```

`resolve_children()` lấy "xương con theo vai trò kế tiếp" mà **không kiểm tra nó có thật là hậu
duệ không**. Với rig IK, vai trò `shin` (`EbackKnee`, xương leaf) lấy vai trò `foot`
(`EbackAnkle`) làm xương con — nhưng hai xương này **ở hai nhánh rời nhau**. Vector đo hướng chi
dài 0.64 bên nguồn vs 0.11 bên đích → ma trận căn là rác, lệch **86°**.

**Sửa:** kiểm tra hậu duệ trước khi dùng; không phải thì coi như `None` để rơi về fallback
"kế thừa phép căn của xương cha" (addon đã viết sẵn fallback này, đúng cho xương leaf):

```python
def _is_descendant(arm, ancestor, name):
    b = arm.bones.get(name)
    while b is not None:
        b = b.parent
        if b is not None and b.name == ancestor:
            return True
    return False

# trong build_alignment:
    if sc and not _is_descendant(src_ob.data, p["src"], sc):
        sc = None
    if tc and not _is_descendant(tgt_ob.data, p["tgt"], tc):
        tc = None
```

---

## 5. Bộ kiểm chứng (dùng để nghiệm thu, và nên đưa vào addon thành nút "Check mesh")

Quan trọng: **không tin `pose_bone.matrix` sau `frame_set` trong script.** Blender thường không
đánh giá lại khi đổi action/mute/frame giữa chừng, trả về pose của clip trước. Suốt phiên làm
việc, nhiều phép đo cho ra **mọi clip đều bằng nhau** vì lý do này. Luôn tính FK **thẳng từ
fcurve**:

```python
def basis(act, bone, f):
    q = [1.0, 0, 0, 0]; loc = [0, 0, 0]
    for i in range(4):
        c = next((x for x in act.fcurves
                  if x.data_path == 'pose.bones["%s"].rotation_quaternion' % bone
                  and x.array_index == i), None)
        if c: q[i] = c.evaluate(f)
    for i in range(3):
        c = next((x for x in act.fcurves
                  if x.data_path == 'pose.bones["%s"].location' % bone
                  and x.array_index == i), None)
        if c: loc[i] = c.evaluate(f)
    Q = Quaternion(q); Q.normalize()
    return Matrix.Translation(Vector(loc)) @ Q.to_matrix().to_4x4()

def fk(act, f):                      # order = hierarchy_order(arm)
    P = {}
    for n in order:
        p = arm.bones[n].parent
        base = rest[n].copy() if p is None else \
               P[p.name] @ (rest[p.name].inverted() @ rest[n])
        P[n] = base @ basis(act, n, f)
    return P
```

### Chỉ số méo mesh — tự tính skinning, phát hiện rách

```python
M   = {n: P[n] @ rest[n].inverted() for n in P}     # ma tran bien dang
pos = []
for i, v in enumerate(me.vertices):
    acc = Vector((0, 0, 0))
    for bone_name, w in W[i]:                        # W: trong so da chuan hoa
        acc += (M[bone_name] @ v.co) * w
    pos.append(acc)

bad = sum(1 for k, (a, b) in enumerate(edges)
          if rest_len[k] > 1e-6
          and not (0.5 <= (pos[a] - pos[b]).length / rest_len[k] <= 2.0))
```

### Ngưỡng nghiệm thu đã đo trên rig thử nghiệm

| | cạnh méo | giãn tối đa |
|---|---|---|
| 12 clip gốc của hoạ sĩ | 7 – 66 | 4 – 33× |
| clip retarget đạt | 15 – 59 | 3.6 – 26× |
| **clip mirror HỎNG (lỗi 1)** | **257 – 268** | 33× |
| clip mirror ĐÚNG (sau khi sửa) | 14 – 45 | 5.6 – 11.7× |

### Phép thử riêng cho mirror — sắc và rẻ

**Độ dài cạnh bất biến qua phép phản chiếu.** Nên bản mirror đúng phải có chỉ số méo **ngang
bằng bản gốc, từng frame**. Thêm phép thứ hai: tâm khối mesh phải **đổi dấu trên trục lật với
cùng độ lớn**.

Kết quả sau khi sửa (rig thử nghiệm, clip `idle_head_death_*`):

```
frame   right [méo, giãn]    mirror [méo, giãn]    tâm X right   tâm X mirror
  2       43, 5.54             45, 5.61             -0.0382       +0.0400
 20       15, 4.24             14, 6.15             -0.0387       +0.0413
 30       42, 18.33            38, 11.65            -0.2199       +0.2206
 41       31, 12.30            28, 7.65             -0.2377       +0.2387
```

### `mirror_error()` phải sửa theo

Hàm này hiện so `want = (Mx @ A[f][src] @ Mx).to_quaternion()`. Sau khi sửa Lỗi 1 nó sẽ báo sai
lệch giả. Đổi sang cùng công thức biến dạng:

```python
D    = A[f][src] @ rest[src].inverted()
want = ((Mx @ D @ Mx) @ rest[n]).to_quaternion()
```

---

## 6. Thứ tự đề xuất

1. **Lỗi 3** (bind slot) — vài dòng, ảnh hưởng mọi rig, hỏng âm thầm nguy hiểm nhất.
2. **Lỗi 1** (+2 tự hết) — một công thức, sửa hẳn mirror cho rig rest không đối xứng.
3. **Lỗi 4b** (kiểm tra hậu duệ) — vài dòng, tránh ma trận căn rác.
4. **Lỗi 4a** (truyền vị trí per-bone) — cần đụng UI + props, làm sau cùng.

Mỗi mục nên kèm một regression test dùng chỉ số ở §5 — cả 4 lỗi đều không ném exception, chỉ
sai kết quả, nên test theo giá trị là cách duy nhất bắt được.
