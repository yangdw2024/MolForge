# ==============================================================================
# run_esp_surface.ps1
# 一键完成 Multiwfn ESPrhoiso 表面分析 + VMD 离屏渲染 BMP
# 用法:
#   .\run_esp_surface.ps1 -Fchk "D:\...\xxx.fchk" -Prefix "ClFFCl" `
#       -WorkDir "D:\...\ESP" -ColorLow -0.065 -ColorHigh 0.045
# 前置: Gaussian 优化 + 波函数稳定后的 fchk；本机 Multiwfn/VMD 路径已固定。
# ==============================================================================
param(
    [Parameter(Mandatory=$true)][string]$Fchk,
    [Parameter(Mandatory=$true)][string]$Prefix,
    [string]$WorkDir = (Get-Location).Path,
    [double]$Isoval = 0.001,
    [double]$ColorLow = -0.06,
    [double]$ColorHigh = 0.05,
    [switch]$KeepIntermediate
)

$ErrorActionPreference = "Stop"
$Multiwfn = "<MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\Multiwfn.exe"
$Vmd      = "<VMD_DIR>\vmd.exe"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $Fchk)) { throw "fchk not found: $Fchk" }
if (-not (Test-Path $Multiwfn)) { throw "Multiwfn not found: $Multiwfn" }
if (-not (Test-Path $Vmd)) { throw "VMD not found: $Vmd" }

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Push-Location $WorkDir
try {
    Write-Host "[1/3] Running Multiwfn ESPrhoiso (isoval=$Isoval) ..."
    # Multiwfn 生成的固定文件名
    $expected = @("density.cub","totesp.cub","surfanalysis.pdb","surfanalysis.txt","sum.txt","mol.pdb","vtx.pdb","vtx.txt","locsurf.pqr","surfarea.txt")
    foreach ($f in $expected) { if (Test-Path $f) { Remove-Item $f -Force } }

    $inFile = Join-Path $ScriptDir "ESPiso_input.txt"
    # PowerShell 不支持 < 重定向，必须用 cmd /c
    cmd /c "`"$Multiwfn`" `"$Fchk`" -ESPrhoiso $Isoval < `"$inFile`"" | Out-Null

    Start-Sleep -Seconds 1
    foreach ($f in $expected) {
        if (-not (Test-Path $f)) { Write-Warning "Missing output: $f" }
    }

    Write-Host "[2/3] Renaming outputs to prefix '$Prefix' ..."
    $renameMap = @{
        "mol.pdb"             = "${Prefix}_mol.pdb"
        "surfanalysis.pdb"    = "${Prefix}_surfanalysis.pdb"
        "surfanalysis.txt"     = "${Prefix}_surfanalysis.txt"
        "sum.txt"              = "${Prefix}_sum.txt"
        "density.cub"         = "${Prefix}_density.cub"
        "totesp.cub"          = "${Prefix}_totesp.cub"
        "vtx.pdb"             = "${Prefix}_vtx.pdb"
        "vtx.txt"             = "${Prefix}_vtx.txt"
        "locsurf.pqr"         = "${Prefix}_locsurf.pqr"
        "surfarea.txt"        = "${Prefix}_surfarea.txt"
    }
    foreach ($k in $renameMap.Keys) {
        if (Test-Path $k) { Rename-Item $k $renameMap[$k] -Force }
    }

    Write-Host "[3/3] Rendering ESP surface via VMD ..."
    $outBmp = Join-Path $WorkDir "${Prefix}_esp.bmp"
    $tcl = Join-Path $ScriptDir "draw_ESP.tcl"
    & $Vmd -dispdev text -e $tcl -args `
        "${Prefix}_mol.pdb" "${Prefix}_surfanalysis.pdb" `
        "${Prefix}_density.cub" "${Prefix}_totesp.cub" `
        $outBmp $Isoval $ColorLow $ColorHigh 2>&1 | Select-Object -Last 20

    Write-Host ""
    Write-Host "=== DONE ==="
    Write-Host "BMP:    $outBmp"
    Write-Host "Sum:    $(Join-Path $WorkDir "${Prefix}_sum.txt")"
    Write-Host "Points: $(Join-Path $WorkDir "${Prefix}_surfanalysis.txt")"
}
finally {
    Pop-Location
}
