---
name: esp-surface-analysis
description: 从 Gaussian 优化好的 fchk 出发，用 Multiwfn 在 0.001 a.u. 电子密度等值面上做静电势(ESP)表面分析，输出 sigma2+/sigma2-/nu/Pi/MPI 等 OSC 关键描述符，并通过 VMD 离屏渲染出 BWR 配色、带 ESP 极大(红)/极小(蓝)特征点的论文级 ESP 表面图。
---

# ESP Surface Analysis Workflow (Multiwfn + VMD)

## Hardware
- Multiwfn 3.8: <MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\Multiwfn.exe
- VMD 1.9.3: <VMD_DIR>\vmd.exe, Tachyon: <VMD_DIR>\tachyon_WIN64.exe
- Python: <PYTHON>
- Strict serial, no parallel Multiwfn runs

## Workflow Overview (two-step Multiwfn)

Step 1: -ESPrhoiso 0.001 -> density.cub + totesp.cub (for VMD coloring)
Step 2: ESPext.txt (main menu 12) -> mol.pdb + surfanalysis.pdb + vtx.pdb

Why two steps? -ESPrhoiso CLI only outputs cube files, not pdb/vtx.
Full surface analysis (menu 12) outputs pdb/vtx but not density/totesp cub.

## Step 1: -ESPrhoiso for cube files

cmd /c "Multiwfn.exe xxx.fchk -ESPrhoiso 0.001 < ESPiso_input.txt"

ESPiso_input.txt (9 lines, from Multiwfn examples):
  5 = grid precision (high)
  1 = mapped function = ESP
  3,2,0,5,12,1,2 = other options

Output:
  <fchk>_density.cub (~25 MB, high-res ~1.7M grid points)
  <fchk>_totesp.cub (~2 MB, low-res ~130K grid points)

NOTE: The two cubes have DIFFERENT grid sizes by design.
VMD Volume coloring auto-interpolates, do NOT try to match grids.

## Step 2: Full surface analysis for pdb/vtx

Use Multiwfn自带 example: <MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\ESPext.txt

cmd /c "Multiwfn.exe xxx.fchk < ESPext.txt"

ESPext.txt (8 lines):
  12 = main menu 12 (quantitative molecular surface analysis)
  3, 0.15, 0, 5 = surface definition + grid precision
  mol.pdb = output molecule file name
  6 = export vtx.pdb
  2 = export surfanalysis.pdb

Output:
  mol.pdb - molecular structure for CPK
  surfanalysis.pdb - ESP extrema: C=max(red), O=min(blue), B-factor=kcal/mol
  vtx.pdb - ~150K surface vertices, B-factor=ESP kcal/mol

Time: ~9 min per molecule for ~60 MB fchk.

## Color Range (critical)

1 a.u. = 627.51 kcal/mol
Rule: read Vs_min/Vs_max from surfanalysis.pdb B-factor, divide by 627.51, add 20% margin.

DO NOT use fixed range for all molecules. Examples:
  ClFFCl:  Vs_min=-32.3, Vs_max=+26.7 -> colorlow=-0.065, colorhigh=+0.045
  zmy01:   Vs_min=-34.5, Vs_max=+56.7 -> colorlow=-0.065, colorhigh=+0.11
  zmy04:   Vs_min=-33.6, Vs_max=+17.5 -> colorlow=-0.064, colorhigh=+0.034

## VMD Rendering

vmd -dispdev text -e draw_ESP.tcl -args mol.pdb surfanalysis.pdb density.cub esp.cub out.bmp 0.001 colorlow colorhigh

Visual style:
  BWR blue-white-red, white bg, orthographic projection
  EdgyGlass material: opacity 0.7, specular 0.15, shininess 0.95
  Isosurface 0.001 a.u. electron density, colored by Volume 1 (ESP)
  Maxima red spheres (colorid 32), minima blue spheres (colorid 21), radius 0.07 A
  1600x1600 BMP, Tachyon ray tracing

## Histogram (ESP area distribution)

python plot_esp_hist.py vtx.pdb MolName --color red --out MolName_esp_hist.png
  --color blue = donor/neutral, red = acceptor

## Descriptors (from vtx.pdb directly)

python compute_descriptors.py vtx.pdb surfanalysis.pdb

Output: Vs_min/Vs_max, sigma2_pos/neg/tot, nu, Pi, MPI, polar_area_pct

## Common Pitfalls

- forrtl severe (24) end-of-file = normal at input stream end
- PowerShell does NOT support < redirect, must use cmd /c "..."
- No Chinese comments in .ps1 files (encoding issues)
- Color Scale Bar not auto-added in offscreen render, add manually with matplotlib
- run_esp_surface.ps1 is deprecated (assumed one-step, does not work)
