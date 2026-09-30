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

from . import ezg_i18n
from .ezg_i18n import tr


def _is_armature(self, ob):
    return ob is not None and ob.type == 'ARMATURE'


class EZG_AT_MapItem(PropertyGroup):
    """Một cặp xương nguồn -> đích."""

    role: StringProperty(name=tr("Vai trò", "Role"), default="")
    side: StringProperty(name=tr("Bên", "Side"), default="")
    src: StringProperty(name=tr("Xương nguồn", "Source Bone"), default="")
    tgt: StringProperty(name=tr("Xương đích", "Target Bone"), default="")
    use: BoolProperty(name=tr("Dùng", "Use"), default=True)
    pos: BoolProperty(
        name=tr("Truyền vị trí", "Transfer Position"), default=False,
        description=tr("Truyền cả VỊ TRÍ của xương này, không chỉ góc xoay. Bật cho "
                       "xương IK mang vị trí thật (cổ chân, cổ tay treo riêng vào "
                       "root). Xương FK bình thường thì để tắt",
                       "Transfer this bone's POSITION too, not just its rotation. Enable "
                       "for IK bones that carry the real position (ankles or wrists "
                       "parented straight to the root). Leave off for regular FK bones"),
    )
    anchor: StringProperty(
        name=tr("Xương neo", "Anchor Bone"), default="",
        description=tr("Xương ĐÍCH dùng làm mốc đo vị trí (phải là một cặp khác đang "
                       "có trong bảng). Vị trí đặt theo hướng của rig nguồn nhưng dài "
                       "theo tỉ lệ chi của rig đích, tính từ mốc này. Neo cổ chân vào "
                       "ĐẦU GỐI cho kết quả tốt hơn nhiều so với neo vào hông",
                       "TARGET bone used as the reference point for the position (must be "
                       "another pair in the table). The position follows the source rig's "
                       "direction but the target rig's limb proportions, measured from "
                       "this point. Anchoring an ankle to the KNEE gives much better "
                       "results than anchoring it to the hips"),
    )

    @property
    def label(self):
        return "%s%s" % (self.role, ("." + self.side) if self.side else "")


class EZG_AT_Settings(PropertyGroup):
    source: PointerProperty(
        name=tr("Nguồn", "Source"), type=bpy.types.Object, poll=_is_armature,
        description=tr("Armature đang có animation cần chuyển đi",
                       "Armature that has the animation to transfer"),
    )
    target: PointerProperty(
        name=tr("Đích", "Target"), type=bpy.types.Object, poll=_is_armature,
        description=tr("Armature sẽ nhận animation", "Armature that receives the animation"),
    )

    action_name: StringProperty(
        name="Action", default="Retargeted",  # i18n-skip
        description=tr("Tên action sẽ tạo ra trên armature đích. Trùng tên sẽ bị ghi đè",
                       "Name of the action created on the target armature. An action "
                       "with the same name is overwritten"),
    )

    align_rest: BoolProperty(
        name=tr("Căn rest pose", "Align Rest Pose"), default=True,
        description=tr("Bù chênh lệch giữa rest pose hai rig (A-pose vs T-pose). "
                       "Chỉ nên tắt khi hai rig có rest pose giống hệt nhau",
                       "Compensate for the difference between the two rigs' rest poses "
                       "(A-pose vs T-pose). Only turn off when both rigs have exactly "
                       "the same rest pose"),
    )
    use_hips_loc: BoolProperty(
        name=tr("Truyền chuyển động hông", "Transfer Hips Motion"), default=True,
        description=tr("Chuyển cả tịnh tiến của hông, không chỉ góc xoay",
                       "Transfer the hips translation too, not just the rotation"),
    )
    hips_auto: BoolProperty(
        name=tr("Tự quy đổi tỉ lệ", "Auto Scale"), default=True,
        description=tr("Quy đổi tịnh tiến hông theo tỉ lệ chiều cao hông hai nhân vật. "
                       "Tắt để tự nhập hệ số",
                       "Scale the hips translation by the ratio of the two characters' "
                       "hip heights. Turn off to enter the factor by hand"),
    )
    hips_scale: FloatProperty(
        name=tr("Hệ số hông", "Hips Scale"), default=1.0, min=0.001, max=100.0, soft_max=5.0,
        description=tr("Hệ số nhân vào tịnh tiến của hông",
                       "Multiplier applied to the hips translation"),
    )

    frame_mode: EnumProperty(
        name=tr("Khoảng frame", "Range"),
        items=[
            ('ACTION', "Action",  # i18n-skip
             tr("Lấy trọn khoảng của action bên nguồn", "Use the full range of the source action")),
            ('SCENE', "Scene",  # i18n-skip
             tr("Lấy khoảng frame của scene", "Use the scene's frame range")),
            ('MANUAL', tr("Tự nhập", "Manual"),
             tr("Tự nhập khoảng frame", "Enter the frame range by hand")),
        ],
        default='ACTION',
    )
    frame_start: IntProperty(name=tr("Bắt đầu", "Start"), default=1)
    frame_end: IntProperty(name=tr("Kết thúc", "End"), default=30)

    mapping: CollectionProperty(type=EZG_AT_MapItem)
    map_index: IntProperty(default=0)

    # --- Lat guong trai/phai ------------------------------------------------
    mirror_object: PointerProperty(
        name="Armature", type=bpy.types.Object, poll=_is_armature,  # i18n-skip
        description=tr("Armature chứa action cần lật gương",
                       "Armature that holds the action to mirror"),
    )
    mirror_action: PointerProperty(
        name="Action", type=bpy.types.Action,  # i18n-skip
        description=tr("Action cần lật gương. Để trống thì lấy action đang gán",
                       "Action to mirror. Leave empty to use the assigned action"),
    )
    mirror_name: StringProperty(
        name=tr("Tên mới", "New Name"), default="",
        description=tr("Tên action mới. Để trống thì tự thêm hậu tố _Mirror",
                       "Name of the new action. Leave empty to add the _Mirror suffix"),
    )

    # --- Nhun / khuech dai chuyen dong -------------------------------------
    polish_object: PointerProperty(
        name="Armature", type=bpy.types.Object, poll=_is_armature,  # i18n-skip
        description=tr("Armature chứa action cần chỉnh",
                       "Armature that holds the action to adjust"),
    )
    polish_action: PointerProperty(
        name="Action", type=bpy.types.Action,  # i18n-skip
        description=tr("Action cần chỉnh. Để trống thì lấy action đang gán",
                       "Action to adjust. Leave empty to use the assigned action"),
    )
    bounce_depth: FloatProperty(
        name=tr("Độ sâu", "Depth"), default=0.02, min=0.0, max=1.0, soft_max=0.15,
        unit='LENGTH', precision=4,
        description=tr("Độ hạ hông ở đáy nhịp nhún",
                       "How far the hips drop at the bottom of each bounce"),
    )
    bounce_cycles: IntProperty(
        name=tr("Số nhịp", "Cycles"), default=2, min=1, max=16,
        description=tr("Số nhịp nhún trong một vòng lặp. Phải là số NGUYÊN, "
                       "không thì chỗ nối vòng lặp sẽ giật",
                       "Number of bounces per loop. Must be a WHOLE number, "
                       "otherwise the loop seam will jerk"),
    )
    amplify_factor: FloatProperty(
        name=tr("Hệ số", "Factor"), default=1.5, min=0.0, max=10.0, soft_max=4.0,
        description=tr("Đẩy chuyển động của thân xa tư thế trung bình gấp bao nhiêu lần. "
                       "KHÔNG idempotent: chạy hai lần là nhân hai lần",
                       "How many times further to push the torso motion away from the "
                       "average pose. NOT idempotent: running it twice multiplies twice"),
    )


classes = (EZG_AT_MapItem, EZG_AT_Settings)


def register():
    ezg_i18n.register_classes(classes)
    bpy.types.Scene.ezg_anim_tools = PointerProperty(type=EZG_AT_Settings)


def unregister():
    try:
        del bpy.types.Scene.ezg_anim_tools
    except AttributeError:
        pass
    ezg_i18n.unregister_classes(classes)
