"""Windows 10 x64 compatibility report, does not install or download anything.

Usage:
    python scripts/windows10_diagnostics.py
    python scripts/windows10_diagnostics.py --json win10_report.json

Qt 6.10/6.12 official docs list Windows 10 build 17763+; actual PyQt6,
QtWebEngine, VTK wheels, graphics drivers and native GUI still require a real
Windows 10 smoke test. Windows 11's NT major also reports 10, use build check.
"""
from __future__ import annotations
import argparse
import importlib.metadata as im
import json
import os
import platform
from pathlib import Path
import struct
import sys

def win10_supported(os_name:str,major:int,minor:int,build:int,bits:int)->tuple[bool,str]:
    if os_name != "Windows":
        return False,"This target requires a real Windows 10 test system"
    if bits != 64:
        return False,"Windows 10 x64 only; 32-bit runtime is not supported"
    if major != 10 or minor != 0 or build < 17763:
        return False,"Windows 10 build 17763 (1809) or later is required"
    if build >= 22000:
        return False,"This is Windows 11; project release target is Windows 10"
    return True,"Compatible Windows 10 OS build; graphics and dependencies still unverified"

def doctor()->dict:
    if sys.platform=="win32":
        version=sys.getwindowsversion()
        major,minor,build=version.major,version.minor,version.build
    else:
        major=minor=build=-1
    bits=struct.calcsize("P")*8
    ok,reason=win10_supported(platform.system(),major,minor,build,bits)
    packages={}
    for name in ("PyQt6","PyQt6-Qt6","PyQt6-WebEngine","vtk","pyvista",
                 "pyvistaqt","rdkit","numpy","openbabel"):
        try:
            packages[name]=im.version(name)
        except im.PackageNotFoundError:
            packages[name]="NOT_INSTALLED"
    result={
       "target":"Windows 10 x64 1809+ (prefer 22H2)",
       "release_target_os_valid":ok,
       "os_diagnostic":reason,
       "current_os":platform.platform(),
       "windows_build":build,
       "python":sys.version.split()[0],
       "python_executable":str(Path(sys.executable)),
       "python_bits":bits,
       "dependencies":packages,
       "project_entry":str(Path(__file__).resolve().parents[1]/"scripts/launch.py"),
       "project_local_venv":str(Path(__file__).resolve().parents[1]/".venv"),
       "download_or_install_attempted":False,
       "native_gpu_qt_interaction_verified":False,
    }
    if ok:
        result["win10_runtime_check"] = "OS_BUILD_PASS_ONLY"
    else:
        result["win10_runtime_check"] = "NOT_TESTED_ON_WIN10"
    return result

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--json")
    args=ap.parse_args(argv)
    result=doctor()
    output=json.dumps(result,ensure_ascii=False,indent=2)
    print(output)
    if args.json:
        out=Path(args.json)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(output+"\n",encoding="utf-8")
    return 0 if result["release_target_os_valid"] else 2

if __name__=="__main__":
    sys.exit(main())
