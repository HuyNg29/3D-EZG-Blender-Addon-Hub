"""Tuỳ chọn của EZG Animation Tools. Lưu trong scene nên đi theo file .blend."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


def _is_armature(self, ob):
    return ob is not None and ob.type == 'ARMATURE'


class EZG_AT_MapItem(PropertyGroup):
    """Một cặp xương nguồn -> đích."""

    role: StringProperty(name="Role", default="")
    side: StringProperty(name="Side", default="")
    src: StringProperty(name="Source bone", default="")
    tgt: StringProperty(name="Target bone", default="")
    use: BoolProperty(name="Use", default=True)

    @property
    def label(self):
        return "%s%s" % (self.role, ("." + self.side) if self.side else "")


class EZG_AT_Settings(PropertyGroup):
    source: PointerProperty(
        name="Source", type=bpy.types.Object, poll=_is_armature,
        description="Armature dang co animation can chuyen di",
    )
    target: PointerProperty(
        name="Target", type=bpy.types.Object, poll=_is_armature,
        description="Armature se nhan animation",
    )

    action_name: StringProperty(
        name="Action", default="Retargeted",
        description="Ten action se tao ra tren armature dich. Trung ten se bi ghi de",
    )

    align_rest: BoolProperty(
        name="Align rest pose", default=True,
        description=("Bu chenh lech giua rest pose hai rig (A-pose vs T-pose). "
                     "Tat cai nay chi dung khi hai rig cung het tu the rest"),
    )
    use_hips_loc: BoolProperty(
        name="Transfer hips motion", default=True,
        description="Chuyen ca tinh tien cua hong, khong chi goc xoay",
    )
    hips_auto: BoolProperty(
        name="Auto scale", default=True,
        description=("Quy doi tinh tien hong theo ti le chieu cao hong hai nhan vat. "
                     "Tat de tu nhap he so"),
    )
    hips_scale: FloatProperty(
        name="Hips scale", default=1.0, min=0.001, max=100.0, soft_max=5.0,
        description="He so nhan vao tinh tien cua hong",
    )

    frame_mode: EnumProperty(
        name="Range",
        items=[
            ('ACTION', "Action", "Lay tron khoang cua action ben nguon"),
            ('SCENE', "Scene", "Lay khoang frame cua scene"),
            ('MANUAL', "Manual", "Tu nhap"),
        ],
        default='ACTION',
    )
    frame_start: IntProperty(name="Start", default=1)
    frame_end: IntProperty(name="End", default=30)

    mapping: CollectionProperty(type=EZG_AT_MapItem)
    map_index: IntProperty(default=0)

    # --- Lat guong trai/phai ------------------------------------------------
    mirror_object: PointerProperty(
        name="Armature", type=bpy.types.Object, poll=_is_armature,
        description="Armature chua action can lat guong",
    )
    mirror_action: PointerProperty(
        name="Action", type=bpy.types.Action,
        description="Action can lat guong. De trong thi lay action dang gan",
    )
    mirror_name: StringProperty(
        name="New name", default="",
        description="Ten action moi. De trong thi tu them hau to _Mirror",
    )

    # --- Nhun / khuech dai chuyen dong -------------------------------------
    polish_object: PointerProperty(
        name="Armature", type=bpy.types.Object, poll=_is_armature,
        description="Armature chua action can chinh",
    )
    polish_action: PointerProperty(
        name="Action", type=bpy.types.Action,
        description="Action can chinh. De trong thi lay action dang gan",
    )
    bounce_depth: FloatProperty(
        name="Depth", default=0.02, min=0.0, max=1.0, soft_max=0.15,
        unit='LENGTH', precision=4,
        description="Do ha hong o day nhip nhun",
    )
    bounce_cycles: IntProperty(
        name="Cycles", default=2, min=1, max=16,
        description=("So nhip nhun trong mot vong lap. Phai la so NGUYEN, "
                     "khong thi cho noi vong lap se giat"),
    )
    amplify_factor: FloatProperty(
        name="Factor", default=1.5, min=0.0, max=10.0, soft_max=4.0,
        description=("Day chuyen dong cua than xa tu the trung binh gap bao nhieu lan. "
                     "KHONG idempotent: chay hai lan la nhan hai lan"),
    )


classes = (EZG_AT_MapItem, EZG_AT_Settings)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.ezg_anim_tools = PointerProperty(type=EZG_AT_Settings)


def unregister():
    del bpy.types.Scene.ezg_anim_tools
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
