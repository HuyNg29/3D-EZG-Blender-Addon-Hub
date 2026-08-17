"""Dong goi tools/bootstrap/* thanh MOT file EZG-Hub-Setup.bat.

Ket qua la mot file .bat duy nhat, gui qua chat cho artist cung duoc.
Double-click la chay: tu tim Blender, them kho EZG, cai hub.

Cach dong goi: noi bootstrap.py vao install_hub.ps1 roi ma hoa base64 va nhung
vao .bat. Base64 chi gom A-Za-z0-9+/= nen khong ky tu nao bi cmd.exe dien giai
nham - tranh duoc toan bo dia nguc escape cua batch. Khi chay, .bat ghi base64
ra file tam roi dung certutil (co san trong Windows) de giai ma.

Viet bang Python thuan thu vien chuan de chay duoc ca tren may Windows cua admin
lan runner Linux cua CI:

    python tools/build_installer.py --out dist/EZG-Hub-Setup.bat
"""

import argparse
import base64
import datetime
import json
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
BOOTSTRAP_DIR = os.path.join(HERE, "bootstrap")
ADDONS_DIR = os.path.join(REPO_ROOT, "addons")
PROFILE_TOML = os.path.join(REPO_ROOT, "profile.toml")

LINE_WIDTH = 76

# Bo profile mau di kem installer. Sinh tu addons/ nen them addon vao repo la
# bo mau tu cap nhat o lan build sau — khong co danh sach chep tay nao de lech.
PROFILE_LABEL = "Bo chuan EZG"
REPO_MODULE = "ezg"          # trung voi REPO_MODULE trong bootstrap.py
HUB_PKG = "ezg_addon_hub"    # bo ra: installer luon cai hub roi

HEADER = """@echo off
setlocal EnableExtensions
title EZG Addon Hub - Cai dat
rem =====================================================================
rem  EZG Addon Hub - trinh cai dat mot file.
rem  Sinh tu dong boi tools/build_installer.py - DUNG SUA TAY.
rem  Sua ma nguon o tools/bootstrap/ roi build lai.
rem =====================================================================
set "EZGTMP=%TEMP%\\ezg_setup_%RANDOM%%RANDOM%"
set "EZGB64=%EZGTMP%.b64"
set "EZGPS1=%EZGTMP%.ps1"
echo Dang chuan bi...
"""

FOOTER = """certutil -f -decode "%EZGB64%" "%EZGPS1%" >nul 2>&1
if errorlevel 1 (
  echo.
  echo LOI: khong giai ma duoc goi cai dat.
  del "%EZGB64%" >nul 2>&1
  pause
  exit /b 1
)
del "%EZGB64%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%EZGPS1%"
set "EZGRC=%ERRORLEVEL%"
del "%EZGPS1%" >nul 2>&1
pause
exit /b %EZGRC%
"""


def _record(pkg_id, name, repo_module, group, version="", homepage=""):
    """Mot muc trong snapshot, dung dinh dang backup.py doc duoc."""
    return {
        "pkg_id": pkg_id,
        "module": "bl_ext.%s.%s" % (repo_module, pkg_id),
        "name": name or pkg_id,
        "version": version,
        "enabled": True,
        "kind": "extension",
        "origin": {
            "group": group,
            "repo_module": repo_module,
            "homepage": homepage,
        },
        "blob": None,
    }


def ezg_items():
    """Addon EZG (nhom B) — quet thang tu addons/, khong co danh sach chep tay."""
    items = []
    for name in sorted(os.listdir(ADDONS_DIR)):
        path = os.path.join(ADDONS_DIR, name, "blender_manifest.toml")
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            m = tomllib.load(f)

        pkg_id = m.get("id")
        if not pkg_id or pkg_id == HUB_PKG:
            continue

        items.append(_record(pkg_id, m.get("name"), REPO_MODULE, "B",
                             version=m.get("version", ""),
                             homepage=m.get("website", "") or ""))
    return items


def external_items():
    """Addon tu kho khac (nhom A) — doc profile.toml.

    Khong the suy ra tu repo nhu nhom B: day la addon cua nguoi khac, chi co
    admin moi biet studio muon cai nhung cai nao.
    """
    if not os.path.isfile(PROFILE_TOML):
        return []

    with open(PROFILE_TOML, "rb") as f:
        cfg = tomllib.load(f)

    items = []
    seen = set()
    for repo in cfg.get("repos", []) or []:
        module = (repo.get("module") or "").strip()
        if not module:
            sys.exit("profile.toml: co mot [[repos]] thieu khoa 'module'.")
        if module == REPO_MODULE:
            sys.exit("profile.toml: khong liet ke kho EZG ('%s') o day — "
                     "addon EZG duoc quet tu dong tu addons/." % REPO_MODULE)

        for pkg in repo.get("packages", []) or []:
            pkg_id = (pkg.get("id") or "").strip()
            if not pkg_id:
                sys.exit("profile.toml: kho '%s' co mot package thieu 'id'." % module)
            key = (module, pkg_id)
            if key in seen:
                sys.exit("profile.toml: '%s' bi liet ke hai lan trong kho '%s'."
                         % (pkg_id, module))
            seen.add(key)
            items.append(_record(pkg_id, pkg.get("name"), module, "A"))

    return items


def build_profile_manifest():
    """Sinh snapshot mau gom addon EZG + addon tu kho ngoai.

    Khong muc nao co blob: restore che do "Ban moi nhat" tai thang tu kho ve, nen
    bo mau khong bao gio giu ban cu. Doi lai, che do "Dung ban da luu" khong dung
    duoc voi bo mau — hub tu canh bao chuyen do.

    Khong co khoa "blender": bo mau khong sinh ra tu mot ban Blender cu the nao,
    ghi dai mot version vao day chi lam nguoi doc hieu nham.
    """
    ezg = ezg_items()
    if not ezg:
        sys.exit("Khong tim thay addon EZG nao trong %s." % ADDONS_DIR)

    items = ezg + external_items()

    return {
        "schema": 1,
        "profile": PROFILE_LABEL,
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": items,
    }


def build(out_path):
    py_path = os.path.join(BOOTSTRAP_DIR, "bootstrap.py")
    ps1_path = os.path.join(BOOTSTRAP_DIR, "install_hub.ps1")

    for path in (py_path, ps1_path):
        if not os.path.isfile(path):
            sys.exit("Thieu file: %s" % path)

    with open(py_path, encoding="utf-8") as f:
        python = f.read()
    with open(ps1_path, encoding="utf-8") as f:
        driver = f.read()

    profile = build_profile_manifest()
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)

    # Here-string nhay don giu noi dung nguyen van. Chi mot dong bat dau bang
    # '@ moi ket thuc no, nen phai chac chan payload khong co dong nhu vay.
    for label, payload in (("bootstrap.py", python), ("profile mau", profile_json)):
        for line in payload.splitlines():
            if line.startswith("'@"):
                sys.exit("%s co dong bat dau bang '@ - se lam hong here-string." % label)

    combined = ("$BootstrapPython = @'\r\n" + python + "\r\n'@\r\n\r\n"
                + "$ProfileJson = @'\r\n" + profile_json + "\r\n'@\r\n\r\n"
                + driver)
    combined = combined.replace("\r\n", "\n").replace("\n", "\r\n")

    # BOM UTF-8 de PowerShell 5.1 doc dung ma hoa khi chay bang -File.
    payload = b"\xef\xbb\xbf" + combined.encode("utf-8")
    b64 = base64.b64encode(payload).decode("ascii")

    lines = [b64[i:i + LINE_WIDTH] for i in range(0, len(b64), LINE_WIDTH)]

    parts = [HEADER]
    for i, line in enumerate(lines):
        redirect = ">" if i == 0 else ">>"
        parts.append('%s"%%EZGB64%%" echo %s\r\n' % (redirect, line))
    parts.append(FOOTER)

    text = "".join(parts).replace("\r\n", "\n").replace("\n", "\r\n")

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)

    # ASCII: file .bat chay trong cmd.exe, khong duoc co ky tu ngoai bang co ban.
    with open(out_path, "wb") as f:
        f.write(text.encode("ascii"))

    return os.path.getsize(out_path), len(lines), profile["items"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "dist",
                                                  "EZG-Hub-Setup.bat"))
    args = ap.parse_args()

    size, n_lines, items = build(args.out)
    n_ezg = sum(1 for i in items if i["origin"]["group"] == "B")
    print("Da tao %s (%d bytes, %d dong base64)" % (args.out, size, n_lines))
    print("Bo profile mau '%s': %d addon (%d EZG, %d tu kho ngoai)."
          % (PROFILE_LABEL, len(items), n_ezg, len(items) - n_ezg))


if __name__ == "__main__":
    main()
