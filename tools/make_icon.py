"""Tao icon 64x64 cho hub tu logo EasyGoing day du.

    blender --background --factory-startup --python tools/make_icon.py

Vi sao can buoc nay thay vi dung thang file logo:

  - Logo goc 2000x2000, 192 KB. Icon trong danh sach chi cao bang mot dong chu,
    nen nhet ca file do vao zip cua addon la lam no phinh gap 10 lan vo ich.
  - Logo gom hai phan: hinh "eg" o tren va chu "easygoing" o duoi. O 16 pixel
    thi phan chu chi con la mot vet mo, dong thoi ep hinh chinh nho lai. Script
    cat lay rieng phan hinh.
  - Logo co nhieu khoang trang quanh vien; cat sat roi mo vuong lai giup hinh
    chiem het o icon.

Chay lai script nay moi khi doi logo goc.
"""

import os
import sys

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "docs", "brand", "ezg_logo_full.png")
DST = os.path.join(REPO, "addons", "ezg_addon_hub", "icons", "ezg_logo.png")
SIZE = 64


def load_rgba(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    return buf.reshape(h, w, 4)  # goc duoi-trai


def top_band(content):
    """Dai hang lien tuc cao nhat theo truc y — chinh la phan hinh, khong phai chu."""
    rows = content.any(axis=1)
    h = len(rows)
    bands, start = [], None
    for y in range(h):
        if rows[y] and start is None:
            start = y
        elif not rows[y] and start is not None:
            bands.append((start, y - 1))
            start = None
    if start is not None:
        bands.append((start, h - 1))
    if not bands:
        sys.exit("LOI: anh khong co noi dung nao.")
    # Goc duoi-trai nen dai co y lon nhat la dai nam TREN cung
    return max(bands, key=lambda b: b[1])


def main():
    if not os.path.isfile(SRC):
        sys.exit("LOI: khong tim thay logo goc tai %s" % SRC)

    px = load_rgba(SRC)
    h, w, _ = px.shape
    content = px[:, :, 3] > 0.5

    y0, y1 = top_band(content)
    band = content[y0:y1 + 1, :]
    xs = np.where(band.any(axis=0))[0]
    x0, x1 = int(xs.min()), int(xs.max())
    print("logo goc     : %d x %d" % (w, h))
    print("phan hinh     : x %d..%d, y %d..%d" % (x0, x1, y0, y1))

    crop = px[y0:y1 + 1, x0:x1 + 1, :]
    ch, cw, _ = crop.shape

    # Mo vuong, dem trong suot, hinh nam giua
    side = max(cw, ch)
    square = np.zeros((side, side, 4), dtype=np.float32)
    oy, ox = (side - ch) // 2, (side - cw) // 2
    square[oy:oy + ch, ox:ox + cw, :] = crop
    print("sau khi cat   : %d x %d -> mo vuong %d x %d" % (cw, ch, side, side))

    tmp = bpy.data.images.new("ezg_icon", width=side, height=side, alpha=True)
    tmp.colorspace_settings.name = 'sRGB'
    tmp.pixels.foreach_set(square.ravel())
    tmp.scale(SIZE, SIZE)

    tmp.file_format = 'PNG'
    tmp.filepath_raw = DST
    tmp.save()
    bpy.data.images.remove(tmp)

    print("da ghi        : %s (%d x %d, %d bytes)"
          % (DST, SIZE, SIZE, os.path.getsize(DST)))


main()
