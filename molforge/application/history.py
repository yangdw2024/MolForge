"""
application/history.py - 撤销/重做历史
=========================================
命令历史栈。支持 undo/redo，有最大深度限制。
"""

from __future__ import annotations

from .commands import Command
from datetime import datetime, timezone
from dataclasses import is_dataclass, asdict
from enum import Enum


class UndoHistory:
    """
    撤销/重做历史栈。

    用法：
        h = UndoHistory(max_depth=100)
        h.push(cmd1)
        h.push(cmd2)
        h.pop_undo()  # → cmd2
        h.pop_undo()  # → cmd1
        h.pop_redo()  # → cmd1
    """

    def __init__(self, max_depth: int = 100) -> None:
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self.max_depth = max_depth
        self.audit_events: list[dict] = []

    def record(self, action, command, document):
        def encode(value):
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, Enum):
                return value.value
            if is_dataclass(value):
                return encode(asdict(value))
            if isinstance(value, (tuple, list)):
                return [encode(v) for v in value]
            if isinstance(value, dict):
                return {str(k): encode(v) for k, v in value.items()}
            if hasattr(value, "tolist"):
                return encode(value.tolist())
            return {"type": type(value).__name__, "note": "not serialized"}
        self.audit_events.append({
            "time_utc": datetime.now(timezone.utc).isoformat(), "action": action,
            "command": type(command).__name__, "description": command.description,
            "revision": document.revision,
            "parameters": {k: encode(v) for k, v in vars(command).items() if not k.startswith("_")},
        })

    def push(self, command: Command) -> None:
        """推入一条新执行的命令。"""
        self._undo_stack.append(command)
        # 超过深度限制，丢掉最老的
        if len(self._undo_stack) > self.max_depth:
            self._undo_stack.pop(0)
        # 新命令执行后，清空 redo 栈
        self._redo_stack.clear()

    def pop_undo(self) -> Command | None:
        """弹出要撤销的命令。"""
        if not self._undo_stack:
            return None
        cmd = self._undo_stack.pop()
        self._redo_stack.append(cmd)
        return cmd

    def pop_redo(self) -> Command | None:
        """弹出要重做的命令。"""
        if not self._redo_stack:
            return None
        cmd = self._redo_stack.pop()
        self._undo_stack.append(cmd)
        return cmd

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def executed_commands(self) -> list[Command]:
        """当前已执行、可撤销的命令（按执行顺序）。"""
        return list(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def clear(self) -> None:
        """清空历史。"""
        self._undo_stack.clear()
        self._redo_stack.clear()
