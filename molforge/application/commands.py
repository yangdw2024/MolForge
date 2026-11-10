"""
application/commands.py - 命令基类
=====================================
所有修改分子的操作都是一个 Command。
UI 按钮、快捷键、LLM 工具调用，都必须通过 CommandBus 执行 Command。

好处：
  - 统一入口：所有修改都经过权限校验、版本校验、事件发布
  - 可撤销：每个 Command 都有 undo()
  - 可审计：每个 Command 记录了谁、什么时候、改了什么
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..domain.document import MoleculeDocument


@dataclass
class CommandResult:
    """命令执行结果。"""
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    changed: bool = False  # 是否实际修改了文档


class Command(ABC):
    """
    命令抽象基类。

    子类必须实现：
      - do(doc): 执行修改
      - undo(doc): 撤销修改

    可选：
      - description: 人类可读的命令描述（显示在撤销菜单里）
      - requires_confirmation: 是否需要用户确认（删除、覆写文件等危险操作）
    """

    description: str = "未命名命令"
    requires_confirmation: bool = False

    @abstractmethod
    def do(self, doc: MoleculeDocument) -> CommandResult:
        """执行命令，修改文档。"""
        ...

    @abstractmethod
    def undo(self, doc: MoleculeDocument) -> CommandResult:
        """撤销命令，恢复文档到执行前状态。"""
        ...
