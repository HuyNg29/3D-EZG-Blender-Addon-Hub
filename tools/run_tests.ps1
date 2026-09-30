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
#   .\tools\run_tests.ps1 -Only test_i18n,test_hub   # chi chay vai test

param(
    [string]$Blender = "D:\AppInstall\Steam\steamapps\common\Blender\blender.exe",
    # Ten test (co hoac khong co duoi .py). Bo trong = chay het.
    [string[]]$Only = @(),
    # Thu muc chua FBX mau cua Mixamo. Bo asset nay ~33 MB nen khong nam trong
    # git. Khong tro toi thi cac test can no se tu bo qua, khong tinh la hong.
    [string]$Assets = $(if ($env:EZG_TEST_ASSETS) { $env:EZG_TEST_ASSETS } else { "D:\EZG Addon Assets\MixamoLibResource" }),
    [switch]$Keep
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $Blender)) {
    throw "Khong tim thay blender.exe tai '$Blender'. Truyen -Blender <duong dan>."
}

$sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("ezghub_test_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null

$tests = @(Get-ChildItem (Join-Path $repo "tests") -Filter "test_*.py" | Sort-Object Name)
if ($Only.Count -gt 0) {
    $want = $Only | ForEach-Object { ($_ -split ",") } | ForEach-Object { $_.Trim() -replace "\.py$", "" } |
            Where-Object { $_ }
    $tests = @($tests | Where-Object { $want -contains $_.BaseName })
    $missing = @($want | Where-Object { $tests.BaseName -notcontains $_ })
    if ($missing.Count -gt 0) { throw "Khong co test: $($missing -join ', ')" }
}
if ($tests.Count -eq 0) { throw "Khong co test nao trong tests\" }

# Ngon ngu VI/EN dung chung cho moi addon EZG, luu trong config cua sandbox.
# Xoa truoc moi test de test nao cung bat dau tu mac dinh (tieng Viet).
$langFile = Join-Path $sandbox "config\ezg_language.txt"

$failed = @()
try {
    $env:BLENDER_USER_RESOURCES = $sandbox
    $env:EZG_REPO_ROOT = $repo

    if ($Assets -and (Test-Path -LiteralPath $Assets)) {
        $env:EZG_TEST_ASSETS = (Resolve-Path -LiteralPath $Assets).Path
        Write-Host ("Asset: " + $env:EZG_TEST_ASSETS) -ForegroundColor DarkGray
    } else {
        Remove-Item Env:\EZG_TEST_ASSETS -ErrorAction SilentlyContinue
        Write-Host "Khong co thu muc asset - test can FBX mau se bi bo qua." -ForegroundColor Yellow
    }

    foreach ($t in $tests) {
        Remove-Item -LiteralPath $langFile -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host ("=== {0} ===" -f $t.Name) -ForegroundColor Cyan
        # --factory-startup: khong keo addon cua may vao ket qua test.
        # --online-mode:     test co tai index.json that tu Pages.
        #
        # Ha ErrorActionPreference dung quanh lenh goi: PowerShell 5.1 boc moi
        # dong stderr cua .exe ngoai thanh NativeCommandError, va voi "Stop" no
        # thanh loi ket thuc — ca vong lap dut giua chung, cac test sau khong
        # duoc chay ma bao cao lai khong he noi la thieu. Chuyen nay xay ra that:
        # test_auto_uv_palette CO CHU Y in traceback (hoi quy cho bug custom
        # property pha export FBX sang Unity) nen suite dung ngay o do.
        # Ket qua van doc bang $LASTEXITCODE nhu cu, khong nuot loi that nao.
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $Blender --background --factory-startup --online-mode `
                --python-exit-code 1 --python $t.FullName
        } finally {
            $ErrorActionPreference = $prev
        }
        if ($LASTEXITCODE -ne 0) { $failed += $t.Name }
    }
}
finally {
    Remove-Item Env:\BLENDER_USER_RESOURCES -ErrorAction SilentlyContinue
    Remove-Item Env:\EZG_REPO_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\EZG_TEST_ASSETS -ErrorAction SilentlyContinue
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
