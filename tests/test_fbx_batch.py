"""FBX Batch: tien trinh Blender nen duoc theo doi o cap module.

Hoi quy: Blender huy modal convert khi mo file khac / dong cua so, nhung tien
trinh Blender nen van chay tiep va van ghi file. Truoc day addon mat dau no:
panel bao xong trong khi file con dang ghi, va nut convert cho chay chong
lan hai. Worker chet giua chung thi bi bao "Xong 0/N file" nhu thanh cong.

Khong can cua so: tien trinh nen duoc gia lap bang mot tien trinh Python ngu
vai giay, con modal thi gia lap bang _stop_modal() (dung viec cancel() lam).

CHAY BANG tools\\run_tests.ps1.
"""

import os
import subprocess
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezg_testkit as kit  # noqa: E402

mod = kit.enable("ezg_fbx_batch")
failures = []


def check(cond, label):
    print("  %s %s" % ("OK  " if cond else "LOI ", label))
    if not cond:
        failures.append(label)


class FakeOp:
    """Thay cho operator that: chi can report(). bpy.ops khong goi duoc invoke()
    trong background vi khong co cua so nen khong co event."""

    def __init__(self):
        self.reports = []

    def report(self, kind, message):
        self.reports.append((next(iter(kind)), str(message)))


def press_convert():
    """Goi invoke() cua nut convert; tra ve (ket qua, danh sach report)."""
    op = FakeOp()
    res = mod.FBXCONV_OT_convert.invoke(op, bpy.context, None)
    return res, op.reports


print("1) Tien trinh nen con song")
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
mod._proc = sleeper
# Worker that ghi tien do vao day; gia lap worker chet truoc khi kip ghi.
mod._progress_path = os.path.join(tempfile.mkdtemp(prefix="fbxconv_test_"), "progress.json")
check(mod._conversion_alive(), "addon thay tien trinh nen dang chay")
check(mod.ezg_i18n_busy(), "dang convert -> doi ngon ngu phai hoan")

res, reports = press_convert()
check(res == {'CANCELLED'} and [k for k, _ in reports] == ['WARNING'],
      "bam convert lan hai bi chan (%s %s)" % (res, reports))
check(mod._proc is sleeper, "tien trinh dang chay khong bi thay the")

# Blender huy modal (mo file khac): cancel() goi _stop_modal.
mod._stop_modal(bpy.context.window_manager)
check(mod.ezg_i18n_busy(), "modal bi huy ma tien trinh con chay -> van ban")
res, reports = press_convert()
check(res == {'CANCELLED'} and [k for k, _ in reports] == ['WARNING'],
      "modal bi huy -> convert lan hai VAN bi chan (%s %s)" % (res, reports))

print("2) Tien trinh thoat ma khong ghi ket qua")
sleeper.wait(10)
mod._watch()   # timer khong chay trong background -> goi tay mot nhip
check(mod._proc is None, "watcher chot tien trinh da thoat")
check(not mod.ezg_i18n_busy(), "het ban sau khi tien trinh thoat")
check(mod._progress.get("finished") and mod._progress.get("ok") is False,
      "worker chet giua chung -> bao that bai, khong bao 'Xong 0/N'")
errors = mod._progress.get("errors", [])
check(any("exit code 0" in e or "mã thoát 0" in e for e in errors),
      "co dong loi ghi ma thoat (%r)" % errors)
mod._watch()   # nhip thua sau khi da chot: khong duoc no
check(mod._proc is None and len(mod._progress.get("errors", [])) == len(errors),
      "chot mot lan, nhip sau khong them loi trung")

print("3) Het ban thi convert moi chay duoc")
res, reports = press_convert()
check(res == {'CANCELLED'} and reports and reports[0][0] == 'ERROR'
      and ("Thư mục FBX không hợp lệ" in reports[0][1] or "Invalid FBX folder" in reports[0][1]),
      "qua duoc buoc 'dang chay', dung o buoc kiem tra thu muc (%s)" % reports)

if bpy.app.timers.is_registered(mod._watch):
    bpy.app.timers.unregister(mod._watch)

print()
if failures:
    print("test_fbx_batch: %d LOI" % len(failures))
    sys.exit(1)
print("test_fbx_batch: OK")
sys.exit(0)
