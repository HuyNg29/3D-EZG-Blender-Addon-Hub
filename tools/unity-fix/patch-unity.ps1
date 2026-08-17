# Patch Unity's Blender-to-FBX converter to export NLA strips as animation clips.
# Fixes: dragging a .blend into Unity only produces one "Scene" clip.
# Run: double-click patch-unity.bat (or run this script as Administrator).

$ErrorActionPreference = 'Stop'

# Self-elevate if not running as Administrator.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    exit
}

$roots = @(
    'C:\Program Files\Unity\Hub\Editor',
    'C:\Program Files\Unity'
) | Where-Object { Test-Path $_ }

$files = foreach ($root in $roots) {
    Get-ChildItem $root -Recurse -Filter 'Unity-BlenderToFBX.py' -ErrorAction SilentlyContinue
}
$files = $files | Sort-Object FullName -Unique

if (-not $files) {
    Write-Host 'No Unity-BlenderToFBX.py found. Is Unity installed?' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw
    if ($content -match 'bake_anim_use_nla_strips=True') {
        Write-Host "[OK - already patched] $($f.FullName)" -ForegroundColor Green
    }
    elseif ($content -match 'bake_anim_use_nla_strips=False') {
        Copy-Item $f.FullName "$($f.FullName).bak" -Force
        $content -replace 'bake_anim_use_nla_strips=False', 'bake_anim_use_nla_strips=True' |
            Set-Content $f.FullName -Encoding ascii -NoNewline
        Write-Host "[PATCHED] $($f.FullName)" -ForegroundColor Yellow
    }
    else {
        Write-Host "[SKIPPED - unexpected content] $($f.FullName)" -ForegroundColor Red
    }
}

Write-Host ''
Write-Host 'Done. Right-click your .blend assets in Unity and choose Reimport.' -ForegroundColor Cyan
Read-Host 'Press Enter to close'
