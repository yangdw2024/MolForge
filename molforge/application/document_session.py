"""
application/document_session.py - 单分子唯一共享编辑会话 (DocumentSession)
==========================================================================
严格实现 S05 / P1 核心契约：
  - 同一 document_id 全局只绑定唯一一个 DocumentSession、唯一一个 CommandBus (含 UndoHistory) 与唯一一个 SelectionService；
  - 当 G1:M1:V1 与克隆视图 G1:M1:V2 指向同一分子时，在 V1 中编辑结构后 V2 自动同步刷新，
    在 V2 中按 Ctrl+Z 直接撤销 V1 发起的最后一次文档编辑！
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..domain.document import MoleculeDocument
from .command_bus import CommandBus
from .commands import Command, CommandResult
from .measurement import MeasurementService
from .selection import SelectionService


@dataclass(frozen=True)
class DocumentSessionEvent:
    document_id: str
    revision: int
    event_type: str  # "command_executed" | "undo" | "redo" | "selection_changed"
    origin: str
    message: str = ""


class DocumentEventHub:
    """会话级事件中心：广播 revision、origin 与变更类型，防止跨视图循环回调。"""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[DocumentSessionEvent], None]] = []

    def subscribe(self, callback: Callable[[DocumentSessionEvent], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[DocumentSessionEvent], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, event: DocumentSessionEvent) -> None:
        for sub in list(self._subscribers):
            sub(event)


class DocumentSession:
    """
    单个 MoleculeDocument 的唯一共享编辑会话。
    不持有任何 VTK / QWidget 原生对象，可安全被 2D Shell、3D Shell、Split Shell 及多视图共享。
    """

    def __init__(self, document: MoleculeDocument) -> None:
        self.document: MoleculeDocument = document
        self.command_bus: CommandBus = CommandBus(document)
        self.selection: SelectionService = SelectionService()
        self.measurements: MeasurementService = MeasurementService()
        self._jobs = None
        self.event_hub: DocumentEventHub = DocumentEventHub()

        self.command_bus.add_listener(self._on_bus_changed)
        self.selection.add_listener(self._on_selection_changed)

    @property
    def document_id(self) -> str:
        return self.document.document_id

    @property
    def revision(self) -> int:
        return self.document.revision

    def execute(self, cmd: Command, origin: str = "ui") -> CommandResult:
        res = self.command_bus.execute(cmd)
        if res.success and res.changed:
            # 若为删除命令，自动清理失效测量与悬空选择
            deleted_aids = set()
            if hasattr(cmd, "atom_id") and getattr(cmd, "atom_id") not in self.document.topology._atoms:
                deleted_aids.add(getattr(cmd, "atom_id"))
            if deleted_aids:
                self.measurements.cleanup_after_delete(deleted_aids)
                self.selection.cleanup_after_delete(deleted_aids, set())
            self.event_hub.publish(
                DocumentSessionEvent(
                    document_id=self.document_id,
                    revision=self.document.revision,
                    event_type="command_executed",
                    origin=origin,
                    message=res.message,
                )
            )
        return res

    def undo(self, origin: str = "ui") -> CommandResult:
        res = self.command_bus.undo()
        if res.success:
            self.event_hub.publish(
                DocumentSessionEvent(
                    document_id=self.document_id,
                    revision=self.document.revision,
                    event_type="undo",
                    origin=origin,
                    message=res.message,
                )
            )
        return res

    def redo(self, origin: str = "ui") -> CommandResult:
        res = self.command_bus.redo()
        if res.success:
            self.event_hub.publish(
                DocumentSessionEvent(
                    document_id=self.document_id,
                    revision=self.document.revision,
                    event_type="redo",
                    origin=origin,
                    message=res.message,
                )
            )
        return res

    def total_electrons(self) -> int:
        charge = int(self.document.properties.get("charge", 0))
        z_sum = sum(self.document.topology.get_atom(aid).atomic_num for aid in self.document.topology.atom_ids)
        return max(0, z_sum - charge)

    def spin_multiplicity(self) -> int:
        if "multiplicity" in self.document.properties:
            return int(self.document.properties["multiplicity"])
        n_elec = self.total_electrons()
        return 1 if (n_elec % 2 == 0) else 2

    def _on_bus_changed(self, result: CommandResult) -> None:
        pass

    def _on_selection_changed(self, origin: str) -> None:
        self.event_hub.publish(
            DocumentSessionEvent(
                document_id=self.document_id,
                revision=self.document.revision,
                event_type="selection_changed",
                origin=origin,
            )
        )

    @property
    def jobs(self):
        if self._jobs is None:
            try:
                from .jobs import JobCenter
                self._jobs = JobCenter()
            except ImportError:
                self._jobs = None
        return self._jobs
