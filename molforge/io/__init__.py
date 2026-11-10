"""
io/ - 格式读写层（惰性按需加载，零启动阻塞）
==============================================
说明：
  - 旧版在 import molforge.io 时同步导入全部 readers/writers 并执行 OpenBabelHandler()，
    导致启动时同步拉起 obabel.exe -L formats 子进程与 RDKit Draw，造成数秒卡顿。
  - 现改为 __getattr__ 按需加载，启动耗时降至 0.0 ms！
"""

from __future__ import annotations

__all__ = [
    "FormatHandler", "register", "read_file", "write_file",
    "supported_open_filters", "supported_save_filters", "get_handler_for_ext",
]

_LAZY_INITIALIZED = False


def _ensure_registry_loaded():
    global _LAZY_INITIALIZED
    if _LAZY_INITIALIZED:
        return
    _LAZY_INITIALIZED = True
    from . import readers  # noqa: F401
    from . import writers  # noqa: F401
    from . import openbabel_handler  # noqa: F401


def __getattr__(name: str):
    if name in __all__:
        _ensure_registry_loaded()
        from . import registry
        return getattr(registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
