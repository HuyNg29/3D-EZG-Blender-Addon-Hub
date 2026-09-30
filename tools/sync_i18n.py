"""Chep tools/ezg_i18n.py (ban goc) sang addons/<pkg>/ezg_i18n.py cua moi addon.

    <blender>/4.5/python/bin/python.exe tools/sync_i18n.py

Extension khong import cheo duoc nhau nen moi addon phai mang ban chep rieng.
Chi sua ban goc; sua ban chep se bi lan chep sau ghi de, va tests/test_i18n.py
bao loi ngay khi ban chep lech ban goc.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.join(os.path.dirname(HERE), "addons")
MASTER = os.path.join(HERE, "ezg_i18n.py")


def main():
    with open(MASTER, "rb") as f:
        master = f.read()
    for name in sorted(os.listdir(ADDONS_DIR)):
        pkg_dir = os.path.join(ADDONS_DIR, name)
        if not os.path.isfile(os.path.join(pkg_dir, "blender_manifest.toml")):
            continue
        dst = os.path.join(pkg_dir, "ezg_i18n.py")
        old = open(dst, "rb").read() if os.path.isfile(dst) else None
        if old == master:
            print("%-28s da khop" % name)
            continue
        shutil.copyfile(MASTER, dst)
        print("%-28s %s" % (name, "cap nhat" if old is not None else "them moi"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
