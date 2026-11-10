"""
application/events.py - 事件系统
=================================
基于事件驱动的架构，订阅方不直接互调。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4, UUID


@dataclass
class Event:
    """事件基类。"""
    event_id: UUID = field(default_factory=uuid4)
    revision: int = 0
    origin: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """事件总线：订阅方不直接互调。"""

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        """订阅事件。"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]):
        """取消订阅。"""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(handler)

    def publish(self, event_type: str, event: Event):
        """发布事件。"""
        if event_type in self._subscribers:
            for handler in self._subscribers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    print(f"事件处理错误: {e}")


# 全局事件总线
event_bus = EventBus()


# 常用事件类型
class Events:
    """常用事件类型。"""
    DOCUMENT_LOADED = "document.loaded"
    DOCUMENT_SAVED = "document.saved"
    MOLECULE_ADDED = "molecule.added"
    MOLECULE_REMOVED = "molecule.removed"
    ATOM_SELECTED = "atom.selected"
    ATOM_DESELECTED = "atom.deselected"
    BOND_SELECTED = "bond.selected"
    SELECTION_CHANGED = "selection.changed"
    VIEW_MODE_CHANGED = "view.changed"
    RENDER_STYLE_CHANGED = "render.style.changed"
    COMMAND_EXECUTED = "command.executed"
    COMMAND_UNDONE = "command.undone"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    JOB_FINISHED = "job.finished"
    JOB_FAILED = "job.failed"
    AI_PROPOSAL_CREATED = "ai.proposal.created"
    AI_PROPOSAL_APPROVED = "ai.proposal.approved"
    AI_PROPOSAL_REJECTED = "ai.proposal.rejected"
