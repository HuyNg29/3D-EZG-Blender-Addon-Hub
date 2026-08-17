# Build toan bo repo ra dist\ y het nhu GitHub Actions lam.
# Dung de kiem tra TRUOC khi push, khoi phai doi CI chay xong moi biet hong.
#
#   .\tools\build_local.ps1
#   .\tools\build_local.ps1 -Blender "D:\duong\dan\blender.exe"

param(
    [string]$Blender = "D:\AppInstall\Steam\steamapps\common\Blender\blender.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $repo "dist"

if (-not (Test-Path $Blender)) {
    throw "Khong tim thay blender.exe tai '$Blender'. Truyen -Blender <duong dan>."
}

# Dung Python di kem Blender -> may admin khong can cai Python rieng.
$blenderRoot = Split-Path -Parent $Blender
$python = Get-ChildItem -Path $blenderRoot -Filter "python.exe" -Recurse -Depth 4 -ErrorAction SilentlyContinue |
          Where-Object { $_.FullName -like "*\python\bin\*" } |
          Select-Object -First 1 -ExpandProperty FullName
if (-not $python) { throw "Khong tim thay Python di kem Blender trong '$blenderRoot'." }

# --factory-startup: khong load add-on cua user -> output sach, khong bi anh huong
# boi add-on dang cai tren may admin (vd BlenderMCP, Tripo3D chiem port).
$blenderArgs = @("--factory-startup", "--command")

if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null

$addonDirs = Get-ChildItem (Join-Path $repo "addons") -Directory
if ($addonDirs.Count -eq 0) { throw "Khong co addon nao trong addons\" }

foreach ($d in $addonDirs) {
    Write-Host "--- validate $($d.Name)" -ForegroundColor Cyan
    & $Blender @blenderArgs extension validate $d.FullName
    if ($LASTEXITCODE -ne 0) { throw "validate that bai: $($d.Name)" }

    Write-Host "--- build $($d.Name)" -ForegroundColor Cyan
    & $Blender @blenderArgs extension build --source-dir $d.FullName --output-dir $dist
    if ($LASTEXITCODE -ne 0) { throw "build that bai: $($d.Name)" }
}

Write-Host "--- server-generate" -ForegroundColor Cyan
& $Blender @blenderArgs extension server-generate --repo-dir $dist --html
if ($LASTEXITCODE -ne 0) { throw "server-generate that bai" }

Write-Host "--- gen_catalog" -ForegroundColor Cyan
& $python (Join-Path $repo "tools\gen_catalog.py") `
    --catalog (Join-Path $repo "catalog.toml") `
    --index (Join-Path $dist "index.json") `
    --out (Join-Path $dist "catalog.json")
if ($LASTEXITCODE -ne 0) { throw "gen_catalog that bai" }

Write-Host "--- build_installer" -ForegroundColor Cyan
& $python (Join-Path $repo "tools\build_installer.py") --out (Join-Path $dist "EZG-Hub-Setup.bat")
if ($LASTEXITCODE -ne 0) { throw "build_installer that bai" }

Write-Host ""
Write-Host "OK. Ket qua trong $dist" -ForegroundColor Green
Get-ChildItem $dist | Select-Object Name, Length | Format-Table -AutoSize
