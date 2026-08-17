# Trinh cai dat EZG Addon Hub - phan dieu khien.
#
# File nay KHONG dung truc tiep. tools\build_installer.py nhung bootstrap.py vao
# bien $BootstrapPython roi dong goi ca hai thanh mot file EZG-Hub-Setup.bat.
#
# Nhiem vu: tim moi ban Blender tren may, chay bootstrap.py trong tung ban.
#
# Chi dung ASCII: file nay chay trong console cmd.exe voi codepage mac dinh,
# ky tu co dau se hien thanh rac.

$ErrorActionPreference = "Stop"

function Write-Head($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "  $text" -ForegroundColor Red }

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " EZG Addon Hub - Trinh cai dat" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Blender phai dang dong
#
# Blender ghi de userpref.blend luc thoat. Neu cai trong khi Blender dang mo,
# moi thay doi se bi xoa ngay khi user dong chuong trinh - im lang, kho hieu.
# ---------------------------------------------------------------------------
if (Get-Process -Name "blender" -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Err "Blender dang mo. Hay dong Blender hoan toan roi chay lai file nay."
    Write-Err "(Cai luc Blender dang chay thi thiet lap se mat khi ban dong Blender.)"
    Write-Host ""
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Tim Blender
# ---------------------------------------------------------------------------
Write-Head "Dang tim Blender tren may..."

$found = New-Object System.Collections.Generic.List[string]

function Add-Candidate($path) {
    if (-not $path) { return }
    try { $full = (Resolve-Path -LiteralPath $path -ErrorAction Stop).Path } catch { return }
    if ((Test-Path -LiteralPath $full -PathType Leaf) -and ($found -notcontains $full)) {
        $found.Add($full)
    }
}

# a) Trong PATH
$cmd = Get-Command blender.exe -ErrorAction SilentlyContinue
if ($cmd) { Add-Candidate $cmd.Source }

# b) Thu muc cai dat tieu chuan
foreach ($root in @("$env:ProgramFiles\Blender Foundation", "${env:ProgramFiles(x86)}\Blender Foundation")) {
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Add-Candidate (Join-Path $_.FullName "blender.exe")
        }
    }
}

# c) Registry - ban cai bang installer
foreach ($key in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                   "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                   "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
    try {
        Get-ItemProperty $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*Blender*" -and $_.InstallLocation } |
            ForEach-Object { Add-Candidate (Join-Path $_.InstallLocation "blender.exe") }
    } catch {}
}

# d) Steam - doc libraryfolders.vdf de bat ca thu vien tren o dia khac
try {
    $steam = (Get-ItemProperty "HKCU:\SOFTWARE\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
    if ($steam) {
        $libs = @($steam)
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        if (Test-Path -LiteralPath $vdf) {
            $hits = Select-String -LiteralPath $vdf -Pattern '"path"\s+"(.+?)"' -AllMatches
            foreach ($h in $hits) {
                foreach ($m in $h.Matches) { $libs += ($m.Groups[1].Value -replace '\\\\', '\') }
            }
        }
        foreach ($lib in ($libs | Sort-Object -Unique)) {
            Add-Candidate (Join-Path $lib "steamapps\common\Blender\blender.exe")
        }
    }
} catch {}

# e) Chuong trinh mo file .blend
try {
    $cmdLine = (Get-ItemProperty "HKLM:\SOFTWARE\Classes\blendfile\shell\open\command" -ErrorAction SilentlyContinue)."(default)"
    if ($cmdLine -match '"([^"]+blender\.exe)"') { Add-Candidate $Matches[1] }
} catch {}

if ($found.Count -eq 0) {
    Write-Err "Khong tim thay Blender tren may nay."
    Write-Host ""
    Write-Host "  Keo file blender.exe tha vao cua so nay roi bam Enter," -ForegroundColor Yellow
    Write-Host "  hoac bam Enter luon de thoat." -ForegroundColor Yellow
    $manual = Read-Host "  Duong dan blender.exe"
    if ($manual) { Add-Candidate $manual.Trim().Trim('"') }
    if ($found.Count -eq 0) { exit 1 }
}

foreach ($b in $found) { Write-Ok $b }

# ---------------------------------------------------------------------------
# 3. Chay bootstrap trong tung ban Blender
# ---------------------------------------------------------------------------
$pyPath = Join-Path $env:TEMP "ezg_bootstrap.py"
Set-Content -LiteralPath $pyPath -Value $BootstrapPython -Encoding utf8

$okCount = 0
$skipCount = 0

$logOut = Join-Path $env:TEMP "ezg_bootstrap_out.txt"
$logErr = Join-Path $env:TEMP "ezg_bootstrap_err.txt"

foreach ($blender in $found) {
    Write-Head ("Cai vao: " + $blender)

    # KHONG dung --factory-startup: bootstrap goi save_userpref(), ket hop voi
    # factory-startup se ghi de sach thiet lap Blender cua user.
    #
    # KHONG dung `2>&1`: trong PowerShell 5.1, redirect stderr cua mot native exe
    # boc TUNG DONG stderr thanh ErrorRecord (NativeCommandError). Vi tren la
    # $ErrorActionPreference = "Stop", mot dong log vo hai cua addon nao do dang
    # bat trong Blender (vd tripo_addon in "WebSocket server started") se lam ca
    # trinh cai dat chet giua duong, khong bao gi.
    # Start-Process ghi thang ra file, khong di qua stream cua PowerShell.
    $proc = Start-Process -FilePath $blender `
                          -ArgumentList @("--background", "--python", $pyPath) `
                          -NoNewWindow -Wait -PassThru `
                          -RedirectStandardOutput $logOut `
                          -RedirectStandardError $logErr
    $code = $proc.ExitCode

    # bootstrap.py in moi thu (ke ca "LOI:") ra stdout; doc them stderr de neu
    # Blender crash that thi con dau vet.
    $out = @()
    if (Test-Path -LiteralPath $logOut) { $out += Get-Content -LiteralPath $logOut }
    if (Test-Path -LiteralPath $logErr) { $out += Get-Content -LiteralPath $logErr }

    foreach ($line in $out) {
        $text = "$line"
        if ($text -match '^(LOI|OK|Blender \d|Da them kho|Kho EZG|Hub |Blender dang tat)') {
            Write-Host "  $text"
        }
    }

    if ($code -eq 0) {
        Write-Ok "Thanh cong."
        $okCount++
    } else {
        Write-Warn "Bo qua ban nay - xem dong LOI o tren."
        Write-Warn ("Log day du: " + $logOut)
        $skipCount++
    }
}

Remove-Item -LiteralPath $pyPath -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
if ($okCount -gt 0) {
    Write-Host (" XONG: da cai vao {0} ban Blender." -f $okCount) -ForegroundColor Green
    if ($skipCount -gt 0) {
        Write-Host (" Bo qua {0} ban - thuong la version cu hon 4.5." -f $skipCount) -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host " Mo Blender > phim N > tab 'EZG Hub'." -ForegroundColor Green
} else {
    Write-Host " KHONG cai duoc vao ban Blender nao." -ForegroundColor Red
    Write-Host " Hub can Blender 4.5 tro len." -ForegroundColor Red
}
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

if ($okCount -gt 0) { exit 0 } else { exit 1 }
