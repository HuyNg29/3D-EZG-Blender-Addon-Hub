# Chup anh huong dan trong MOT SANDBOX RIENG, xong tu xoa sandbox.
#
#   .\tools\guide\capture.ps1 -Addon ezg_deco_namer -Tab Deco -Out deco.png
#   .\tools\guide\capture.ps1 -Addon ezg_auto_uv_palette -Tab "UV Palette" -Scene uv_palette -Out uv.png
#   .\tools\guide\capture.ps1 -Addon none -Tab "EZG Hub" -Scene hub_store -Out hub.png
#
# -Addon none : canh hub_* tu cai addon that tu kho tren Pages, nen luon bat --online-mode.
# Xem capture_view3d.py de biet cac canh co san.
param(
    [Parameter(Mandatory)] [string]$Addon,
    [Parameter(Mandatory)] [string]$Tab,
    [Parameter(Mandatory)] [string]$Out,
    [string]$Scene = "deco_namer",
    [int]$Width = 1600,
    [int]$Height = 900,
    [string]$Blender = "D:\AppInstall\Steam\steamapps\common\Blender\blender.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Out = [System.IO.Path]::GetFullPath($Out)
Remove-Item -LiteralPath $Out -ErrorAction SilentlyContinue

$sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("ezghub_guide_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
try {
    $env:BLENDER_USER_RESOURCES = $sandbox
    $env:EZG_REPO_ROOT = $repo
    # Nhu run_tests.ps1: ha ErrorActionPreference quanh lenh goi .exe de dong
    # stderr cua Blender khong bi PowerShell 5.1 bien thanh loi ket thuc.
    $ErrorActionPreference = "Continue"
    & $Blender --factory-startup --online-mode --enable-event-simulate `
        --window-geometry 0 0 $Width $Height `
        --python (Join-Path $PSScriptRoot "capture_view3d.py") -- $Addon $Tab $Out $Scene 2>&1 |
        ForEach-Object { "$_" } | Where-Object { $_ -match "\[capture\]|Error|Traceback|RuntimeError" }
    $ErrorActionPreference = "Stop"
    if (-not (Test-Path -LiteralPath $Out)) { throw "Khong chup duoc $Out" }
} finally {
    Remove-Item -Recurse -Force -LiteralPath $sandbox -ErrorAction SilentlyContinue
    Remove-Item Env:\BLENDER_USER_RESOURCES -ErrorAction SilentlyContinue
}
