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

for pkg_id in pkg_ids:
    module = "bl_ext.%s.%s" % (REPO_MODULE, pkg_id)

    try:
        bpy.ops.preferences.addon_enable(module=module)
    except Exception as exc:
        failures.append("%s: bat that bai -> %s" % (pkg_id, exc))
        print("  LOI  %-24s bat that bai" % pkg_id)
        continue

    if module not in bpy.context.preferences.addons:
        failures.append("%s: bat khong bao loi nhung khong co hieu luc" % pkg_id)
        print("  LOI  %-24s bat khong co hieu luc" % pkg_id)
        continue

    try:
        bpy.ops.preferences.addon_disable(module=module)
    except Exception as exc:
        failures.append("%s: tat that bai -> %s" % (pkg_id, exc))
        print("  LOI  %-24s tat that bai" % pkg_id)
        continue

    if module in bpy.context.preferences.addons:
        failures.append("%s: tat roi ma van con trong danh sach" % pkg_id)
        print("  LOI  %-24s tat khong sach" % pkg_id)
        continue

    print("  OK   %-24s bat va tat sach" % pkg_id)

print("=" * 70)
if failures:
    print("THAT BAI %d/%d addon:" % (len(failures), len(pkg_ids)))
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("CA %d ADDON DEU BAT VA TAT DUOC" % len(pkg_ids))
sys.exit(0)
