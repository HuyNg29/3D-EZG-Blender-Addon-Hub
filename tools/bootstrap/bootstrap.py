"""Chay BEN TRONG Blender: dang ki kho EZG roi cai hub.

QUAN TRONG: script nay PHAI chay khong co --factory-startup.

No goi save_userpref(). Neu chay kem --factory-startup, Blender se nap thiet lap
mac dinh roi ghi de len userpref.blend cua user — mat het trang thai bat/tat addon,
asset library, theme, keymap va preferences cua tung addon. Da tung xay ra that
trong qua trinh phat trien, xem docs/DEV-WORKFLOW.md muc 6.
"""

import os
import sys

import bpy

REPO_URL = os.environ.get(
    "EZG_REPO_URL",
    "https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json",
)
REPO_NAME = "EZG"
REPO_MODULE = "ezg"
HUB_PKG = "ezg_addon_hub"
MIN_VERSION = (4, 5, 0)

TOKEN = os.environ.get("EZG_ACCESS_TOKEN", "")


def fail(msg):
    print("LOI: %s" % msg)
    sys.exit(1)


print("Blender %s" % bpy.app.version_string)

if bpy.app.version < MIN_VERSION:
    fail("Hub can Blender %s tro len. Ban nay qua cu, bo qua."
         % ".".join(str(x) for x in MIN_VERSION))

# --- Blender co the dang o che do offline ---
if not bpy.app.online_access:
    print("Blender dang tat truy cap mang, dang bat len...")
    try:
        bpy.context.preferences.system.use_online_access = True
    except Exception as exc:
        fail("Khong bat duoc Allow Online Access: %s. "
             "Bat tay o Preferences > System roi chay lai." % exc)

# --- 1. Dang ki kho EZG ---
repos = bpy.context.preferences.extensions.repos
target = REPO_URL.strip().rstrip("/")

repo = None
for r in repos:
    if r.use_remote_url and (r.remote_url or "").strip().rstrip("/") == target:
        repo = r
        break

if repo is None:
    module = REPO_MODULE
    taken = {r.module for r in repos}
    n = 2
    while module in taken:
        module = "%s_%d" % (REPO_MODULE, n)
        n += 1

    repo = repos.new(name=REPO_NAME, module=module, remote_url=REPO_URL)
    repo.use_remote_url = True
    repo.enabled = True
    print("Da them kho '%s' (%s)" % (REPO_NAME, REPO_URL))
else:
    print("Kho EZG da co san, dung lai.")

if TOKEN:
    repo.access_token = TOKEN

repo_index = list(repos).index(repo)

# --- 2. Tai danh sach goi ---
try:
    bpy.ops.extensions.repo_sync(repo_index=repo_index)
except Exception as exc:
    fail("Khong tai duoc danh sach tu kho: %s" % exc)

# --- 3. Cai hub ---
module_name = "bl_ext.%s.%s" % (repo.module, HUB_PKG)
already = module_name in bpy.context.preferences.addons

try:
    bpy.ops.extensions.package_install(
        repo_index=repo_index, pkg_id=HUB_PKG, enable_on_install=True)
except Exception as exc:
    if not already:
        fail("Cai hub that bai: %s" % exc)
    print("Hub da cai san, giu nguyen.")

if module_name not in bpy.context.preferences.addons:
    try:
        bpy.ops.preferences.addon_enable(module=module_name)
    except Exception as exc:
        fail("Cai xong nhung khong bat duoc hub: %s" % exc)

if module_name not in bpy.context.preferences.addons:
    fail("Hub khong o trang thai bat sau khi cai.")

# --- 4. Luu lai, neu khong thoat Blender la mat ---
bpy.ops.wm.save_userpref()

print("OK: da cai va bat '%s'." % module_name)
print("Hub nam o View3D > phim N > tab 'EZG Hub'.")
sys.exit(0)
