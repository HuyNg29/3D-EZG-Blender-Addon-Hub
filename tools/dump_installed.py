"""In danh sach extension dang cai, dung dinh dang chep thang vao profile.toml.

Dung khi muon cap nhat bo profile mau theo mot may da cai san moi thu:

    blender --background --python tools/dump_installed.py

CHI DOC. Khong goi save_userpref(), khong sua gi trong preferences.

Addon EZG bi bo qua co chu dich: build_installer.py tu quet addons/ nen liet ke
lai o profile.toml se thanh hai nguon su that cho cung mot thu.
"""

import sys

import addon_utils
import bpy

# Kho cua chinh EZG - addon o day khong can ghi vao profile.toml.
EZG_URL_HINT = "3D-EZG-Blender-Addon-Hub"


def main():
    repos = {r.module: r for r in bpy.context.preferences.extensions.repos}
    enabled = set(bpy.context.preferences.addons.keys())

    by_repo = {}
    for mod in addon_utils.modules(refresh=False):
        name = mod.__name__
        if not name.startswith("bl_ext."):
            continue
        try:
            _, repo_module, pkg_id = name.split(".", 2)
        except ValueError:
            continue

        repo = repos.get(repo_module)
        if repo is None or repo.source == 'SYSTEM':
            continue
        # Chi lay addon den tu kho co remote_url: kho cuc bo (user_default) la
        # thu muc dev tren may nay, may khac khong tai lai duoc.
        if not (repo.use_remote_url and (repo.remote_url or "").strip()):
            continue
        if EZG_URL_HINT in (repo.remote_url or ""):
            continue

        info = getattr(mod, "bl_info", {}) or {}
        by_repo.setdefault(repo_module, []).append(
            (pkg_id, info.get("name") or pkg_id, name in enabled))

    if not by_repo:
        print("Khong tim thay addon nao tu kho ben ngoai.")
        return 0

    print("")
    print("# ---- chep tu day vao profile.toml ----")
    for repo_module in sorted(by_repo):
        repo = repos[repo_module]
        rows = sorted(by_repo[repo_module], key=lambda t: t[0].lower())
        width = max(len(r[0]) for r in rows) + 3

        print("")
        print("[[repos]]")
        print('module = "%s"' % repo_module)
        print('label = "%s"' % repo.name)
        print("")
        print("packages = [")
        for pkg_id, name, is_on in rows:
            note = "" if is_on else "   # dang TAT tren may nay"
            print('  { id = %-*s name = "%s" },%s'
                  % (width, '"%s",' % pkg_id, name.replace('"', "'"), note))
        print("]")
    print("")
    print("# ---- het ----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
