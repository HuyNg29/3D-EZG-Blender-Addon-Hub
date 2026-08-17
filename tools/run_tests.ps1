# Chay test cua hub trong MOT SANDBOX RIENG.
#
# BAT BUOC dung script nay thay vi goi blender --python truc tiep.
#
# Ly do: test phai goi bpy.ops.wm.save_userpref() de kiem tra luong cai dat.
# Neu chay tren config that, lenh do se GHI DE userpref.blend cua ban — mat het
# trang thai bat/tat addon, asset library, theme, keymap va preferences cua tung
# addon. Da tung xay ra that.
#
# BLENDER_USER_RESOURCES tro config/scripts/extensions sang thu muc tam, nen
# moi thu test lam deu nam trong sandbox va bi xoa sau khi chay.
#
#   .\tools\run_tests.ps1
#   .\tools\run_tests.ps1 -Keep          # giu sandbox lai de xem xet

param(
    [string]$Blender = "D:\AppInstall\Steam\steamapps\common\Blender\blender.exe",
    [switch]$Keep
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $Blender)) {
    throw "Khong tim thay blender.exe tai '$Blender'. Truyen -Blender <duong dan>."
}

$sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("ezghub_test_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null

$tests = Get-ChildItem (Join-Path $repo "tests") -Filter "test_*.py" | Sort-Object Name
if ($tests.Count -eq 0) { throw "Khong co test nao trong tests\" }

$failed = @()
try {
    $env:BLENDER_USER_RESOURCES = $sandbox
    $env:EZG_REPO_ROOT = $repo

    foreach ($t in $tests) {
        Write-Host ""
        Write-Host ("=== {0} ===" -f $t.Name) -ForegroundColor Cyan
        # --factory-startup: khong keo addon cua may vao ket qua test.
        # --online-mode:     test co tai index.json that tu Pages.
        & $Blender --background --factory-startup --online-mode `
            --python-exit-code 1 --python $t.FullName
        if ($LASTEXITCODE -ne 0) { $failed += $t.Name }
    }
}
finally {
    Remove-Item Env:\BLENDER_USER_RESOURCES -ErrorAction SilentlyContinue
    Remove-Item Env:\EZG_REPO_ROOT -ErrorAction SilentlyContinue
    if ($Keep) {
        Write-Host "Sandbox giu lai: $sandbox" -ForegroundColor Yellow
    } else {
        Remove-Item $sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host ("THAT BAI: {0}" -f ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
Write-Host "TAT CA TEST DEU DAT" -ForegroundColor Green
