"""
application/ - 应用层
========================
用例和业务逻辑。只依赖 domain 层，不依赖 GUI/VTK/SDK。

核心：
  - CommandBus：所有修改的统一入口（UI 和 AI 都走这里）
  - UndoHistory：撤销/重做历史
  - SelectionService：选择状态管理
"""

from .commands import Command, CommandResult
from .command_bus import CommandBus
from .history import UndoHistory
from .selection import SelectionService

__all__ = [
    "Command", "CommandResult",
    "CommandBus",
    "UndoHistory",
    "SelectionService",
]
