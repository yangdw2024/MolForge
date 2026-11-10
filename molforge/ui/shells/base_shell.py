"""
ui/shells/base_shell.py - 三大独立系统共享的抽象会话外壳契约
============================================================
每个独立系统 (Studio2DShell / Studio3DShell / StudioSplitShell) 均消费同一个 DocumentSession，
拥有各自独立的菜单体系、状态栏与窗口生命周期，而非简单隐藏旧三栏面板。
"""

from __future__ import annotations

from ..gmv_window_manager import GMVWindowManager
from ...application.document_session import DocumentSession, DocumentSessionEvent
from ...application.workspace_registry import PaneCount, ViewSession, WorkspaceRegistry
from ...domain.document import MoleculeDocument


class BaseStudioShell:
    """三大独立 Studio 系统的公共会话基类（可在无头测试与 PyQt6 主窗口下共用）。"""

    shell_kind: str = "base"
    menu_titles: tuple[str, ...] = ()

    def __init__(
        self,
        document: MoleculeDocument | None = None,
        session: DocumentSession | None = None,
        view_session: ViewSession | None = None,
        pane_count: PaneCount = 1,
    ) -> None:
        reg = WorkspaceRegistry.instance()
        if session is not None:
            self.session = session
            doc = session.document
        else:
            doc = document if document is not None else MoleculeDocument(name="untitled")
            self.session = reg.get_or_create_session(doc)

        if view_session is not None:
            self.view_session = view_session
        else:
            _, self.view_session = reg.create_new_group_view(self.session.document, pane_count=pane_count)

        self.gmv_manager = GMVWindowManager(reg)
        self.is_closed: bool = False
        self.last_event: DocumentSessionEvent | None = None
        self.session.event_hub.subscribe(self._on_session_event)

    @property
    def document(self) -> MoleculeDocument:
        return self.session.document

    @property
    def gmv_tag(self) -> str:
        return self.view_session.gmv_tag

    def status_summary(self) -> dict[str, int | str]:
        return {
            "gmv_tag": self.gmv_tag,
            "atoms": self.document.topology.num_atoms,
            "bonds": self.document.topology.num_bonds,
            "electrons": self.session.total_electrons(),
            "charge": int(self.document.properties.get("charge", 0)),
            "multiplicity": self.session.spin_multiplicity(),
        }

    def close_shell(self) -> None:
        if not self.is_closed:
            self.session.event_hub.unsubscribe(self._on_session_event)
            self.gmv_manager.close_window(self.gmv_tag)
            self.is_closed = True

    def _on_session_event(self, event: DocumentSessionEvent) -> None:
        self.last_event = event
