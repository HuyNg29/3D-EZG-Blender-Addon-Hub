"""Tien ich chung cho cac test chay ben trong Blender.

Khong phai file test (ten khong bat dau bang test_) nen run_tests.ps1 bo qua.

Ly do ton tai: cac test cu duoc viet khi addon con o dang legacy, chung tu
them thu muc vao sys.path roi `import <ten_module>` va goi register() bang tay.
Cach do khong con dung khi addon la extension — module that su ten la
`bl_ext.<repo>.<pkg_id>` va phai bat qua addon_enable. Ham enable() o day lam
dung viec do va tra ve module Python de test goi ham noi bo nhu cu.
"""

import os
import sys

import bpy

REPO_MODULE = "ezgdev"


def repo_root():
    root = os.environ.get("EZG_REPO_ROOT")
    if not root:
        print("LOI: thieu bien EZG_REPO_ROOT. Chay bang tools\\run_tests.ps1.")
        sys.exit(1)
    return root


def require_sandbox():
    """Test co the ghi preferences — bat buoc phai chay trong sandbox.

    Chay tren config that se ghi de userpref.blend va xoa sach thiet lap
    Blender cua nguoi dung. Xem docs/DEV-WORKFLOW.md muc 6.
    """
    if not os.environ.get("BLENDER_USER_RESOURCES"):
        print("LOI: chua co BLENDER_USER_RESOURCES. Chay bang tools\\run_tests.ps1.")
        sys.exit(1)


def _ensure_repo():
    repos = bpy.context.preferences.extensions.repos
    for r in repos:
        if r.module == REPO_MODULE:
            return r
    repo = repos.new(name="EZG Dev", module=REPO_MODULE,
                     custom_directory=os.path.join(repo_root(), "addons"))
    repo.use_custom_directory = True
    repo.enabled = True
    return repo


def enable(pkg_id):
    """Bat mot addon trong addons/ va tra ve module Python cua no."""
    require_sandbox()
    _ensure_repo()

    module = "bl_ext.%s.%s" % (REPO_MODULE, pkg_id)
    try:
        bpy.ops.preferences.addon_enable(module=module)
    except Exception as exc:
        print("LOI: khong bat duoc '%s': %s" % (pkg_id, exc))
        sys.exit(1)

    if module not in bpy.context.preferences.addons:
        print("LOI: bat '%s' khong co hieu luc." % pkg_id)
        sys.exit(1)

    mod = sys.modules.get(module)
    if mod is None:
        print("LOI: khong lay duoc module cua '%s'." % pkg_id)
        sys.exit(1)
    return mod


def assets_dir():
    """Thu muc chua file FBX mau. None neu chua cau hinh.

    Bo asset nay nang ~33 MB nen khong nam trong git. Tro toi no bang bien
    EZG_TEST_ASSETS, hoac tham so -Assets cua run_tests.ps1.
    """
    d = os.environ.get("EZG_TEST_ASSETS")
    if d and os.path.isdir(d):
        return d
    return None


def skip(reason):
    """Bo qua test nay ma khong tinh la that bai."""
    print("BO QUA: %s" % reason)
    sys.exit(0)
