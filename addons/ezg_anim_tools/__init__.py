"""EZG Animation Tools — hai việc quanh chuyện chuyển động giữa các rig.

  Retarget  chuyển animation từ bộ xương này sang bộ xương khác (core.py)
  Mirror    tạo bản lật gương trái/phải của một action (mirror.py)

View3D > phím N > tab "EZG Anim".

Import phải là relative và tham chiếu module dùng `__package__`: tên module thật
của extension là `bl_ext.<repo>.ezg_anim_tools`, không phải tên thư mục trần.
"""

from . import ops, props, ui

_modules = (props, ops, ui)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        try:
            m.unregister()
        except Exception:
            pass
