"""
MolForge - 分子编辑器包
=====================
一个给计算化学研究生用的轻量分子编辑器，基于 PyQt6 + RDKit。
"""

import sys, os

# 保护 Windows Python 3.13 下 platform / numpy.testing 的 WMI COM 崩溃
if sys.platform == "win32":
    try:
        import platform
        platform._wmi_query = lambda *a, **kw: ("10.0.22631", 1, "Multiprocessor Free", 0, 0)
    except Exception:
        pass

__version__ = "7.4.0"
__app_name__ = "MolForge"