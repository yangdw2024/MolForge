"""
scripts/windows11_diagnostics.py - Windows 11 x64 原生运行环境契约检查
======================================================================
专门针对 Windows 11 (NT 10.0, build >= 22000, 64-bit) 进行环境诊断，
不破坏原有 windows10_diagnostics.py 的历史契约。
"""
from __future__ import annotations
import platform
import struct

def win11_supported(
    system: str | None = None,
    major: int | None = None,
    minor: int | None = None,
    build: int | None = None,
    bits: int | None = None,
) -> tuple[bool, str]:
    sys_name = system if system is not None else platform.system()
    if sys_name != "Windows":
        return False, f"Not Windows (detected {sys_name})"
    ver = platform.version().split(".")
    maj = major if major is not None else (int(ver[0]) if len(ver) > 0 and ver[0].isdigit() else 0)
    b_num = build if build is not None else (int(ver[2]) if len(ver) > 2 and ver[2].isdigit() else 0)
    ptr_bits = bits if bits is not None else (struct.calcsize("P") * 8)
    if ptr_bits != 64:
        return False, f"Requires 64-bit Python/OS (detected {ptr_bits}-bit)"
    if maj != 10 or b_num < 22000:
        return False, f"Requires Windows 11 build >= 22000 (detected {maj}.0.{b_num})"
    return True, f"Windows 11 x64 build {b_num} supported"
