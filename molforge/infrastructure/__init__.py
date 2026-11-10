"""
infrastructure/ - 基础设施层
==============================
IO、计算后端、LLM 适配器等外部依赖。
"""

__all__ = ["FormatHandler", "registry", "glog_reader", "gjf_writer"]


def __getattr__(name: str):
    if name == "FormatHandler":
        from ..io.registry import FormatHandler
        return FormatHandler
    elif name == "registry":
        from ..io import registry
        return registry
    elif name == "glog_reader":
        from ..io.readers import glog_reader
        return glog_reader
    elif name == "gjf_writer":
        from ..io.writers import gjf_writer
        return gjf_writer
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
