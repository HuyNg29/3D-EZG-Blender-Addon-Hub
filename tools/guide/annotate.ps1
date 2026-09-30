# Ve khung do / mui ten / so thu tu / nhan len anh chup Blender.
#   powershell -File annotate.ps1 -In raw.png -Spec spec.json -Out out.png
# spec.json: { "crop":[x,y,w,h]?, "items":[
#   {"t":"box","r":[x,y,w,h]},
#   {"t":"arrow","from":[x,y],"to":[x,y]},
#   {"t":"badge","at":[cx,cy],"n":1},
#   {"t":"label","at":[x,y],"text":"...","align":"left|right|center"} ] }
# Toa do luon tinh tren anh GOC (truoc khi crop).
param([string]$In, [string]$Spec, [string]$Out)
Add-Type -AssemblyName System.Drawing
$ErrorActionPreference = "Stop"

$cfg = Get-Content -Raw -Encoding UTF8 $Spec | ConvertFrom-Json
$src = [System.Drawing.Bitmap]::FromFile($In)
$bmp = New-Object System.Drawing.Bitmap($src.Width, $src.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.DrawImage($src, 0, 0, $src.Width, $src.Height)
$src.Dispose()
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$red = [System.Drawing.Color]::FromArgb(255, 235, 45, 45)
$white = [System.Drawing.Color]::White

function RoundRect($x, $y, $w, $h, $r) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = 2 * $r
    $p.AddArc($x, $y, $d, $d, 180, 90)
    $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $p.CloseFigure()
    return $p
}


foreach ($it in $cfg.items) {

    switch ($it.t) {
        "box" {
            $pen = New-Object System.Drawing.Pen($red, 3)
            $r = $it.r
            $g.DrawPath($pen, (RoundRect $r[0] $r[1] $r[2] $r[3] 6))
        }
        "arrow" {
            $pen = New-Object System.Drawing.Pen($red, 3.5)
            $pen.CustomEndCap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap(4, 4, $true)
            $g.DrawLine($pen, [float]$it.from[0], [float]$it.from[1], [float]$it.to[0], [float]$it.to[1])
        }
        "badge" {
            $rad = 13
            $cx = $it.at[0]; $cy = $it.at[1]
            $g.FillEllipse((New-Object System.Drawing.SolidBrush($white)), $cx - $rad - 2, $cy - $rad - 2, 2 * $rad + 4, 2 * $rad + 4)
            $g.FillEllipse((New-Object System.Drawing.SolidBrush($red)), $cx - $rad, $cy - $rad, 2 * $rad, 2 * $rad)
            $f = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
            $sf = New-Object System.Drawing.StringFormat
            $sf.Alignment = "Center"; $sf.LineAlignment = "Center"
            $g.DrawString([string]$it.n, $f, (New-Object System.Drawing.SolidBrush($white)),
                (New-Object System.Drawing.RectangleF(($cx - $rad), ($cy - $rad + 1), (2 * $rad), (2 * $rad))), $sf)
        }
        "label" {
            $f = New-Object System.Drawing.Font("Segoe UI Semibold", 15, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
            $sz = $g.MeasureString([string]$it.text, $f)
            $pw = $sz.Width + 16; $ph = $sz.Height + 8
            $x = $it.at[0]; $y = $it.at[1] - $ph / 2
            if ($it.align -eq "right") { $x = $x - $pw }
            elseif ($it.align -eq "center") { $x = $x - $pw / 2 }
            $g.FillPath((New-Object System.Drawing.SolidBrush($red)), (RoundRect $x $y $pw $ph 6))
            $g.DrawString([string]$it.text, $f, (New-Object System.Drawing.SolidBrush($white)), ($x + 8), ($y + 4))
        }
    }
}
$g.Dispose()

if ($cfg.crop) {
    $c = $cfg.crop
    $rect = New-Object System.Drawing.Rectangle($c[0], $c[1], $c[2], $c[3])
    $cropped = $bmp.Clone($rect, $bmp.PixelFormat)
    $bmp.Dispose(); $bmp = $cropped
}
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "da ghi $Out"
