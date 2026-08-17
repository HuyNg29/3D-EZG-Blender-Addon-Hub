"""Sinh catalog.json tu catalog.toml, doi chieu voi index.json cua Blender.

  - index.json   do `extension server-generate` sinh -> Blender doc de cai/update
  - catalog.json do script nay sinh              -> hub doc de hien thi

Script cung lam nhiem vu KIEM TRA: neu catalog.toml nhac toi mot id khong co trong
index.json (hoac nguoc lai), no bao loi va dung build, thay vi de hub hien thi mot
muc chet ma khong ai phat hien.

Chi dung thu vien chuan cua Python 3.11 (tomllib) nen chay duoc bang Python di kem
Blender, khong can cai them gi:

    <blender>/4.5/python/bin/python.exe tools/gen_catalog.py \
        --catalog catalog.toml --index dist/index.json --out dist/catalog.json
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path


def load_index_versions(index_path: Path) -> dict:
    """Tra ve {id: version} tu index.json do Blender sinh."""
    with index_path.open("rb") as f:
        data = json.load(f)
    versions = {}
    for entry in data.get("data", []):
        pkg_id = entry.get("id")
        if pkg_id:
            versions[pkg_id] = entry.get("version", "")
    return versions


def check(catalog: dict, index_versions: dict) -> list:
    """Tra ve danh sach loi nhat quan giua catalog.toml va index.json."""
    errors = []
    items = catalog.get("items", {})

    for pkg_id in sorted(items):
        if pkg_id not in index_versions:
            errors.append(
                "catalog.toml mo ta '%s' nhung index.json khong co. "
                "Sai id, hay addon chua duoc build?" % pkg_id
            )

    for pkg_id in sorted(index_versions):
        if pkg_id not in items:
            errors.append(
                "index.json co '%s' nhung catalog.toml khong mo ta. "
                "Them [items.%s] vao catalog.toml." % (pkg_id, pkg_id)
            )

    for group in catalog.get("groups", []):
        for pkg_id in group.get("items", []):
            if pkg_id not in items:
                errors.append(
                    "Nhom '%s' tro toi '%s' khong co trong [items]."
                    % (group.get("id", "?"), pkg_id)
                )

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    with args.catalog.open("rb") as f:
        catalog = tomllib.load(f)

    index_versions = load_index_versions(args.index)

    errors = check(catalog, index_versions)
    if errors:
        for e in errors:
            print("LOI: " + e, file=sys.stderr)
        return 1

    items = catalog.get("items", {})
    # Version la nguon su that duy nhat tu manifest -> luon lay tu index.json,
    # khong bao gio ghi tay trong catalog.toml (tranh lech hai cho).
    for pkg_id, meta in items.items():
        meta["version"] = index_versions[pkg_id]
        meta["summary_vi"] = meta.get("summary_vi", "").strip()

    out = {
        "schema": catalog.get("schema", 1),
        "groups": catalog.get("groups", []),
        "items": items,
        "external": catalog.get("external", []),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Da ghi %s (%d addon EZG, %d addon ben thu ba)"
          % (args.out, len(items), len(out["external"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
