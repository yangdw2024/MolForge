# -*- mode: python ; coding: utf-8 -*-
"""
MolForge v7.4.0 官方独立便携绿色版 PyInstaller 规范配置 (molforge_standalone.spec)
========================================================================
- 严禁向 C 盘写入任何临时文件或缓存
- 包含 CalChem C++ 核心库 (calchem._core.pyd)
- 收集 VTK, RDKit, PyVista, MDAnalysis, cclib 核心科学依赖
- 输出至 dist/MolForge/ 目录
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

project_root = Path(r"E:\YDW\Trae_Chemdraw\MolForge").resolve()

datas = [
    (str(project_root / "molforge" / "rendering" / "static"), "molforge/rendering/static"),
    (str(project_root / "molforge" / "ui" / "assets"), "molforge/ui/assets"),
]
binaries = []
hiddenimports = collect_submodules("molforge")

# 引入 CalChem C++ 高性能扩展
calchem_pyd = Path(r"E:\YDW\Trae_Gaussian\calchem\_core.pyd")
if calchem_pyd.is_file():
    binaries.append((str(calchem_pyd), "calchem"))
    hiddenimports.append("calchem._core")

# 收集关键科学计算库
for pkg in ["rdkit", "vtk", "pyvista", "cclib", "gemmi", "MDAnalysis"]:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"[SPEC WARN] Failed to collect {pkg}: {e}")

a = Analysis(
    [str(project_root / "scripts" / "launch.py")],
    pathex=[str(project_root), r"E:\YDW\Trae_Gaussian"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib.tests", "scipy.tests"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MolForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保留控制台以供调试，生产可设为 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MolForge",
)
