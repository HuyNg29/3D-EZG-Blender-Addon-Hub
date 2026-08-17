"""Moi addon trong addons/ phai bat va tat duoc duoi he thong Extensions.

Day la cho de vo nhat khi chuyen mot addon legacy sang extension: code dung
__name__ thay vi __package__, hoac import tuyet doi thay vi relative, se chay
binh thuong o dang legacy nhung chet ngay khi thanh extension. `extension
validate` KHONG bat duoc loai loi nay vi no chi doc manifest.

CHAY BANG tools\\run_tests.ps1.
"""

import os
import sys

import bpy

REPO_ROOT = os.environ.get("EZG_REPO_ROOT")
if not REPO_ROOT:
    print("LOI: thieu bien EZG_REPO_ROOT. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)

if not os.environ.get("BLENDER_USER_RESOURCES"):
    print("LOI: chua co BLENDER_USER_RESOURCES. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)

ADDON_DIR = os.path.join(REPO_ROOT, "addons")
REPO_MODULE = "ezgdev"

pkg_ids = sorted(
    name for name in os.listdir(ADDON_DIR)
    if os.path.isfile(os.path.join(ADDON_DIR, name, "blender_manifest.toml"))
)

if not pkg_ids:
    print("LOI: khong tim thay addon nao trong %s" % ADDON_DIR)
    sys.exit(1)

repos = bpy.context.preferences.extensions.repos
repo = repos.new(name="EZG Dev", module=REPO_MODULE, custom_directory=ADDON_DIR)
repo.use_custom_directory = True
repo.enabled = True

print("Tim thay %d addon trong addons/" % len(pkg_ids))
print("=" * 70)

failures = []

# Chay HAI vong. Vong thu hai moi la phan quan trong: neu unregister() bo sot
# mot class, lan bat ke tiep se chet voi "already registered as a subclass".
# Chay mot vong khong bao gio thay duoc loi do — da tung de lot mot lan that.
ROUNDS = 2


def cycle(pkg_id, module, round_no):
    """Tra ve chuoi mo ta loi, hoac None neu vong nay sach."""
    try:
        bpy.ops.preferences.addon_enable(module=module)
    except Exception as exc:
        return "vong %d: bat that bai -> %s" % (round_no, exc)

    if module not in bpy.context.preferences.addons:
        return "vong %d: bat khong bao loi nhung khong co hieu luc" % round_no

    try:
        bpy.ops.preferences.addon_disable(module=module)
    except Exception as exc:
        return "vong %d: tat that bai -> %s" % (round_no, exc)

    if module in bpy.context.preferences.addons:
        return "vong %d: tat roi ma van con trong danh sach" % round_no

    return None


for pkg_id in pkg_ids:
    module = "bl_ext.%s.%s" % (REPO_MODULE, pkg_id)

    problem = None
    for round_no in range(1, ROUNDS + 1):
        problem = cycle(pkg_id, module, round_no)
        if problem:
            break

    if problem:
        failures.append("%s: %s" % (pkg_id, problem))
        print("  LOI  %-24s %s" % (pkg_id, problem))
    else:
        print("  OK   %-24s bat va tat sach %d vong" % (pkg_id, ROUNDS))

print("=" * 70)
if failures:
    print("THAT BAI %d/%d addon:" % (len(failures), len(pkg_ids)))
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("CA %d ADDON DEU BAT VA TAT DUOC" % len(pkg_ids))
sys.exit(0)
