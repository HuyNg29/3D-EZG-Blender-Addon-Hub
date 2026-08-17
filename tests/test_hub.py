"""Smoke test cho ezg_addon_hub: bat addon roi goi lan luot tung thao tac.

CHAY BANG tools\\run_tests.ps1, khong goi blender --python truc tiep.
Test co goi save_userpref(); chay ngoai sandbox se ghi de userpref.blend that.
"""

import json
import os
import sys
import tempfile

import bpy

REPO_ROOT = os.environ.get("EZG_REPO_ROOT")
if not REPO_ROOT:
    print("LOI: thieu bien EZG_REPO_ROOT. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)

# Chan chay nham tren config that: run_tests.ps1 luon dat BLENDER_USER_RESOURCES.
if not os.environ.get("BLENDER_USER_RESOURCES"):
    print("LOI: chua co BLENDER_USER_RESOURCES. Chay bang tools\\run_tests.ps1.")
    sys.exit(1)

ADDON_DIR = os.path.join(REPO_ROOT, "addons")
REPO_MODULE = "ezgdev"
HUB = "bl_ext.%s.ezg_addon_hub" % REPO_MODULE
LIVE_URL = "https://huyng29.github.io/3D-EZG-Blender-Addon-Hub/index.json"

# Addon chac chan da co tren Pages — dung de kiem tra, khong khoa cung tong so
# vi kho con duoc bo sung theo thoi gian.
EXPECTED_IN_STORE = {"ezg_deco_namer", "ezg_fbx_batch"}

failures = []
step = 0


def check(label, cond, detail=""):
    global step
    step += 1
    print("  [%02d] %s %s %s" % (step, "OK  " if cond else "LOI ", label, detail if not cond else ""))
    if not cond:
        failures.append(label)


print("=" * 70)
repos = bpy.context.preferences.extensions.repos
repo = repos.new(name="EZG Dev", module=REPO_MODULE, custom_directory=ADDON_DIR)
repo.use_custom_directory = True
repo.enabled = True

bpy.ops.preferences.addon_enable(module=HUB)
check("bat duoc hub", HUB in bpy.context.preferences.addons)
if HUB not in bpy.context.preferences.addons:
    sys.exit(1)

p = bpy.context.preferences.addons[HUB].preferences
tmp_backup = tempfile.mkdtemp(prefix="ezgbak_")
tmp_sync = tempfile.mkdtemp(prefix="ezgsync_")
p.repo_url = LIVE_URL
p.backup_dir = tmp_backup
p.sync_dir = tmp_sync
p.profile_name = "test.user"

wm = bpy.context.window_manager

print("-" * 70)
print("1) Quet may")
bpy.ops.ezg.refresh_inventory()
n_inv = len(wm.ezg_inventory)
check("quet ra addon", n_inv > 0, "(=%d)" % n_inv)
check("hub tu nhan ra chinh no", any(r.pkg_id == "ezg_addon_hub" for r in wm.ezg_inventory))
check("phan loai nhom hop le", all(r.group in ("A", "B", "C") for r in wm.ezg_inventory))
check("moi addon deu co ten", all(r.name for r in wm.ezg_inventory))

print("-" * 70)
print("2) Tai kho EZG tu Pages")
res = bpy.ops.ezg.refresh_store()
check("refresh_store chay", 'FINISHED' in res, str(res) + " err=" + wm.ezg_error)
store_ids = {r.pkg_id for r in wm.ezg_catalog if not r.is_external}
check("kho co du addon mong doi", EXPECTED_IN_STORE <= store_ids,
      "(thieu %s)" % (EXPECTED_IN_STORE - store_ids))
check("co muc ben thu ba", any(r.is_external for r in wm.ezg_catalog))
check("moi muc deu co tieu de", all(r.title for r in wm.ezg_catalog))

print("-" * 70)
print("3) Kiem tra ban moi qua mang")
bpy.ops.ezg.refresh_inventory(check_updates=True)
check("check_updates khong loi", not wm.ezg_error, wm.ezg_error)

print("-" * 70)
print("4) Tao backup")
res = bpy.ops.ezg.backup_create()
check("backup_create chay", 'FINISHED' in res, str(res) + " err=" + wm.ezg_error)

prof = os.path.join(tmp_backup, "test.user")
snaps = os.listdir(prof) if os.path.isdir(prof) else []
check("co dung 1 snapshot", len(snaps) == 1, "(=%r)" % snaps)

if snaps:
    snap_dir = os.path.join(prof, snaps[0])
    mpath = os.path.join(snap_dir, "manifest.json")
    check("co manifest.json", os.path.isfile(mpath))
    if os.path.isfile(mpath):
        with open(mpath, encoding="utf-8") as f:
            data = json.load(f)
        check("manifest du so addon", len(data["items"]) == n_inv,
              "(%d vs %d)" % (len(data["items"]), n_inv))
        check("manifest co schema", data.get("schema") == 1)

        c_items = [i for i in data["items"] if i["origin"]["group"] == "C"]
        c_blob = [i for i in c_items if i.get("blob")]
        check("addon nhom C deu duoc zip", len(c_items) == len(c_blob),
              "(%d/%d)" % (len(c_blob), len(c_items)))

        ab_blob = [i for i in data["items"]
                   if i["origin"]["group"] in ("A", "B") and i.get("blob")]
        check("nhom A/B khong zip (snapshot nhe)", not ab_blob, "(%d bi zip thua)" % len(ab_blob))

        missing = [i["pkg_id"] for i in data["items"]
                   if i.get("blob") and not os.path.isfile(
                       os.path.join(snap_dir, i["blob"].replace("/", os.sep)))]
        check("moi blob khai bao deu ton tai", not missing, "(thieu %r)" % missing)

    sync_prof = os.path.join(tmp_sync, "test.user")
    if os.path.isdir(sync_prof):
        sub = os.listdir(sync_prof)[0]
        files = sorted(os.listdir(os.path.join(sync_prof, sub)))
        # Mac dinh KHONG day zip len thu muc dung chung: zip co the chua addon tra phi.
        check("dong bo chi chep manifest", files == ["manifest.json"], "(=%r)" % files)
    else:
        check("co chep sang thu muc dong bo", False)

print("-" * 70)
print("5) Liet ke ban backup")
bpy.ops.ezg.refresh_snapshots()
check("liet ke duoc snapshot", len(wm.ezg_snapshots) == 1, "(=%d)" % len(wm.ezg_snapshots))

print("-" * 70)
print("6) Restore khi moi addon deu dang co -> khong cai lai gi")
if len(wm.ezg_snapshots):
    res = bpy.ops.ezg.restore('EXEC_DEFAULT', path=wm.ezg_snapshots[0].path, mode='LATEST')
    check("restore chay", 'FINISHED' in res, str(res))
    check("khong lam thay doi so addon", len(wm.ezg_inventory) == n_inv,
          "(%d vs %d)" % (len(wm.ezg_inventory), n_inv))

print("-" * 70)
print("7) Nut 'Cap nhat muc dang chon'")
check("operator co ton tai", hasattr(bpy.ops.ezg, "update_selected"))

# poll phai chan dung 2 truong hop, neu khong user se bam vao mot nut vo nghia
no_update = next((i for i, r in enumerate(wm.ezg_inventory)
                  if not r.update_version and r.group != "C"), None)
if no_update is not None:
    wm.ezg_inventory_index = no_update
    check("chan khi muc dang chon da la ban moi nhat",
          not bpy.ops.ezg.update_selected.poll())

manual = next((i for i, r in enumerate(wm.ezg_inventory) if r.group == "C"), None)
if manual is not None:
    wm.ezg_inventory_index = manual
    check("chan khi muc dang chon la nguon thu cong",
          not bpy.ops.ezg.update_selected.poll())

has_update = next((i for i, r in enumerate(wm.ezg_inventory)
                   if r.update_version and r.group != "C"), None)
if has_update is not None:
    wm.ezg_inventory_index = has_update
    check("cho phep khi muc dang chon co ban moi",
          bpy.ops.ezg.update_selected.poll())
else:
    print("       (khong co addon nao co ban moi de thu truong hop cho phep)")

print("=" * 70)
if failures:
    print("THAT BAI %d/%d muc:" % (len(failures), step))
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("TAT CA %d KIEM TRA DEU DAT" % step)
sys.exit(0)
