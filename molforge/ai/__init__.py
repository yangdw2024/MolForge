"""
ai/ - LLM 操作层
=================
AIContext 持有当前分子，通过工具操作它。
LLM 通过 function calling / MCP 调用 AIContext 的方法。
"""

__all__ = ["AIContext"]


def __getattr__(name: str):
    if name == "AIContext":
        from .tools import AIContext
        return AIContext
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
