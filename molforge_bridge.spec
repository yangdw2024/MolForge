# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MolForge Studio standalone headless Chemical Engine Bridge.
Outputs a self-contained directory into desktop/resources/bridge/molforge-bridge/
so Electron can launch molforge-bridge.exe without requiring system Python.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

project_root = Path(r"E:\YDW\Trae_Chemdraw\MolForge").resolve()
calchem_root = Path(r"E:\YDW\Trae_Gaussian").resolve()

datas = collect_data_files("molforge")
binaries = []
hiddenimports = (
    collect_submodules("molforge.domain")
    + collect_submodules("molforge.application")
    + collect_submodules("molforge.io")
    + collect_submodules("molforge.workflows")
    + collect_submodules("molforge.ai")
    + collect_submodules("molforge.server")
    + collect_submodules("molforge.core")
    + collect_submodules("molforge.infrastructure")
    + ["molforge.runtime", "molforge.rendering.vtk_backend"]
)

# Include CalChem C++ / Rust quantum chemistry core if present
calchem_dir = calchem_root / "calchem"
if calchem_dir.is_dir():
    try:
        ret = collect_all("calchem")
        datas += ret[0]
        binaries += ret[1]
        hiddenimports += ret[2]
    except Exception:
        pyd = calchem_dir / "_core.pyd"
        if pyd.is_file():
            binaries.append((str(pyd), "calchem"))
            hiddenimports.append("calchem._core")

for pkg in ["rdkit", "cclib", "gemmi", "scipy", "numpy"]:
    try:
        ret = collect_all(pkg)
        datas += ret[0]
        binaries += ret[1]
        hiddenimports += ret[2]
    except Exception as exc:
        print(f"[BRIDGE SPEC WARN] {pkg}: {exc}")

a = Analysis(
    [str(project_root / "molforge" / "server" / "bridge_entry.py")],
    pathex=[str(project_root), str(calchem_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt6",
        "PyQt5",
        "PySide6",
        "vtk",
        "pyvista",
        "pyvistaqt",
        "matplotlib",
        "tkinter",
        "IPython",
        "jupyter",
        "pytest",
        "unittest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="molforge-bridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="molforge-bridge",
)
