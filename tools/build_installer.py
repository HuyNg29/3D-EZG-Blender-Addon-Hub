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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOTSTRAP_DIR = os.path.join(HERE, "bootstrap")

LINE_WIDTH = 76

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

    # Here-string nhay don giu noi dung nguyen van. Chi mot dong bat dau bang
    # '@ moi ket thuc no, nen phai chac chan bootstrap.py khong co dong nhu vay.
    for line in python.splitlines():
        if line.startswith("'@"):
            sys.exit("bootstrap.py co dong bat dau bang '@ - se lam hong here-string.")

    combined = "$BootstrapPython = @'\r\n" + python + "\r\n'@\r\n\r\n" + driver
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

    return os.path.getsize(out_path), len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "dist",
                                                  "EZG-Hub-Setup.bat"))
    args = ap.parse_args()

    size, n_lines = build(args.out)
    print("Da tao %s (%d bytes, %d dong base64)" % (args.out, size, n_lines))


if __name__ == "__main__":
    main()
