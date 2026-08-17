"""Snapshot va restore profile addon.

Snapshot gom hai lop:

  manifest.json  danh sach addon + version + nguon goc. Nhe, la thu chinh.
  blobs/*.zip    file that cua addon. Chi la phao cuu sinh.

Addon nhom A va B tai lai duoc tu kho nen mac dinh KHONG zip -> snapshot thuong
duoi 1 MB. Chi addon nhom C (nguon thu cong) moi bat buoc phai zip, vi khong con
cach nao lay lai.

Restore co hai che do:
  LATEST  tai ban moi nhat tu nguon; chi dung blob khi nguon chet. Mac dinh.
  EXACT   cai dung version da luu, bat buoc phai co blob.
"""

import datetime
import json
import os
import shutil
import zipfile

import bpy

from . import bridge, scanner

SCHEMA = 1
MANIFEST_NAME = "manifest.json"
BLOBS_DIRNAME = "blobs"


class BackupError(Exception):
    pass


def _timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M")


def _safe(name):
    keep = "-_. "
    return "".join(c for c in name if c.isalnum() or c in keep).strip() or "default"


def _zip_addon(item, out_path):
    """Dong goi addon dang cai thanh zip cai lai duoc.

    Extension can giu blender_manifest.toml o goc thu muc trong zip, nen zip
    theo dang <pkg_id>/... giong y ban phat hanh.
    """
    src = item["path"]
    pkg_id = item["pkg_id"]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isfile(src):
            # Addon legacy 1 file: giu nguyen ten file goc.
            z.write(src, os.path.basename(src))
            return

        if not os.path.isdir(src):
            raise BackupError("Khong tim thay '%s' tren dia." % src)

        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                if fn.endswith(".pyc"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src)
                z.write(full, os.path.join(pkg_id, rel))


def create(context, items, snapshot_root, profile, all_blobs=False):
    """Ghi mot snapshot. Tra ve (duong_dan, so_addon, canh_bao)."""
    stamp = _timestamp()
    snap_dir = os.path.join(snapshot_root, _safe(profile), stamp)
    blobs_dir = os.path.join(snap_dir, BLOBS_DIRNAME)

    try:
        os.makedirs(snap_dir, exist_ok=True)
    except Exception as exc:
        raise BackupError("Khong tao duoc thu muc '%s': %s" % (snap_dir, exc))

    warnings = []
    records = []

    for item in items:
        # Nhom C khong tai lai duoc tu dau ca -> bat buoc zip.
        need_blob = all_blobs or item["group"] == "C"
        blob_rel = None

        if need_blob:
            zip_name = "%s-%s.zip" % (item["pkg_id"], item["version"] or "0")
            zip_path = os.path.join(blobs_dir, zip_name)
            try:
                _zip_addon(item, zip_path)
                blob_rel = "%s/%s" % (BLOBS_DIRNAME, zip_name)
            except Exception as exc:
                warnings.append("%s: khong zip duoc (%s)" % (item["name"], exc))

        records.append({
            "pkg_id": item["pkg_id"],
            "module": item["module"],
            "name": item["name"],
            "version": item["version"],
            "enabled": item["enabled"],
            "kind": "extension" if item["is_extension"] else "legacy_addon",
            "origin": {
                "group": item["group"],
                "repo_module": item["repo_module"],
                "homepage": item["homepage"],
            },
            "blob": blob_rel,
        })

    manifest = {
        "schema": SCHEMA,
        "profile": profile,
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "blender": {
            "version": list(bpy.app.version),
            "os": bpy.app.build_platform.decode() if isinstance(bpy.app.build_platform, bytes)
                  else str(bpy.app.build_platform),
        },
        "items": records,
    }

    path = os.path.join(snap_dir, MANIFEST_NAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        raise BackupError("Khong ghi duoc manifest: %s" % exc)

    return snap_dir, len(records), warnings


def mirror_manifest(snap_dir, sync_root, profile, include_blobs=False):
    """Chep snapshot sang thu muc dong bo. Mac dinh chi chep manifest.

    Zip co the chua addon tra phi nen khong tu dong day len thu muc dung chung.
    """
    if not sync_root:
        return None

    dst = os.path.join(sync_root, _safe(profile), os.path.basename(snap_dir))
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(os.path.join(snap_dir, MANIFEST_NAME), os.path.join(dst, MANIFEST_NAME))

    if include_blobs:
        src_blobs = os.path.join(snap_dir, BLOBS_DIRNAME)
        if os.path.isdir(src_blobs):
            shutil.copytree(src_blobs, os.path.join(dst, BLOBS_DIRNAME), dirs_exist_ok=True)

    return dst


def list_snapshots(snapshot_root, profile):
    """Cac snapshot cua profile, moi nhat truoc."""
    base = os.path.join(snapshot_root, _safe(profile))
    if not os.path.isdir(base):
        return []

    out = []
    for name in sorted(os.listdir(base), reverse=True):
        snap_dir = os.path.join(base, name)
        manifest_path = os.path.join(snap_dir, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        items = data.get("items", [])
        out.append({
            "name": name,
            "path": snap_dir,
            "created": data.get("created", ""),
            "count": len(items),
            "blobs": sum(1 for i in items if i.get("blob")),
            "blender": ".".join(str(x) for x in data.get("blender", {}).get("version", [])),
        })
    return out


def read_manifest(snap_dir):
    path = os.path.join(snap_dir, MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise BackupError("Khong doc duoc manifest: %s" % exc)


def restore(context, snap_dir, mode, repo_url, token=""):
    """Cai lai addon theo snapshot. Tra ve (da_cai, bao_cao).

    Khong go bat cu addon nao dang co — restore chi them vao.
    """
    manifest = read_manifest(snap_dir)
    records = manifest.get("items", [])

    installed_now = {i["module"]: i for i in scanner.scan(repo_url)}
    repos = list(bpy.context.preferences.extensions.repos)
    by_module = {r.module: r for r in repos}

    done = []
    report = []

    ezg_repo = None
    if any(r["origin"].get("group") == "B" for r in records):
        try:
            ezg_repo = bridge.ensure_ezg_repo(repo_url, token)
        except Exception as exc:
            report.append("Khong chuan bi duoc repo EZG: %s" % exc)

    for rec in records:
        name = rec.get("name") or rec.get("pkg_id")
        module = rec.get("module", "")
        group = rec.get("origin", {}).get("group", "C")
        blob_rel = rec.get("blob")
        blob_path = os.path.join(snap_dir, blob_rel.replace("/", os.sep)) if blob_rel else None
        has_blob = bool(blob_path and os.path.isfile(blob_path))

        if module in installed_now:
            report.append("%s: da co san, bo qua" % name)
            continue

        # EXACT: bat buoc dung blob vi kho chi phuc vu ban moi nhat.
        if mode == 'EXACT':
            if has_blob:
                try:
                    bridge.install_file(blob_path, enable=rec.get("enabled", True))
                    done.append(name)
                except Exception as exc:
                    report.append("%s: %s" % (name, exc))
            else:
                report.append("%s: khong co zip nen khong cai dung ban %s duoc"
                              % (name, rec.get("version", "?")))
            continue

        # LATEST: uu tien tai lai tu kho, blob chi la phao cuu sinh.
        repo = ezg_repo if group == "B" else by_module.get(rec.get("origin", {}).get("repo_module", ""))

        if group in ("A", "B") and repo is not None:
            try:
                bridge.install(repo, rec["pkg_id"], enable=rec.get("enabled", True))
                done.append(name)
                continue
            except Exception as exc:
                report.append("%s: tai tu kho that bai (%s)" % (name, exc))

        if has_blob:
            try:
                bridge.install_file(blob_path, enable=rec.get("enabled", True))
                done.append(name)
            except Exception as exc:
                report.append("%s: %s" % (name, exc))
        else:
            where = rec.get("origin", {}).get("homepage") or "khong ro nguon"
            report.append("%s: khong co zip va khong tai lai duoc -> %s" % (name, where))

    bridge.save_prefs()
    return done, report
