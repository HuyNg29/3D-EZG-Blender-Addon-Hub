"""EZG Addon Hub — quan li addon EZG, kiem ke may, backup profile addon.

Extension nen KHONG co bl_info: moi thong tin do nam trong blender_manifest.toml.
Import trong goi phai la relative, va tham chieu module phai dung __package__.
"""

import bpy

from . import ezg_i18n, ops, prefs, props, ui


def register():
    # Preferences dang ki truoc: cac phan con lai deu doc tuy chon tu day.
    ezg_i18n.register_classes((prefs.EZGHubPreferences,))
    props.register()
    ops.register()
    ui.register()


def unregister():
    ui.unregister()
    ops.unregister()
    props.unregister()
    ezg_i18n.unregister_classes((prefs.EZGHubPreferences,))
