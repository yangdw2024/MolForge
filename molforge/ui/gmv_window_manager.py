"""
ui/gmv_window_manager.py - GaussView 风格 G:M:V 多窗口与视图生命周期管理器
===========================================================================
统一协调 WorkspaceRegistry 与顶层窗口实例，确保：
  - G1:M1:V1 与克隆视图 G1:M1:V2 共享同一个 DocumentSession (同一 CommandBus 与 UndoHistory)
  - 窗口关闭时安全释放 VTK / Qt 监听器并更新 WorkspaceRegistry，避免悬空回调与 0xC0000409 崩溃
"""

from __future__ import annotations

from typing import Any

from ..application.document_session import DocumentSession
from ..application.workspace_registry import PaneCount, ViewSession, WorkspaceRegistry
from ..domain.document import MoleculeDocument


class GMVWindowManager:
    """管理 G:M:V 窗口注册、克隆视图与生命周期回收。"""

    def __init__(self, registry: WorkspaceRegistry | None = None) -> None:
        self.registry: WorkspaceRegistry = registry or WorkspaceRegistry.instance()
        self._window_by_tag: dict[str, Any] = {}

    def register_new_group_window(
        self,
        document: MoleculeDocument,
        window_obj: Any = None,
        pane_count: PaneCount = 1,
    ) -> tuple[DocumentSession, ViewSession]:
        session, view = self.registry.create_new_group_view(document, pane_count=pane_count)
        if window_obj is not None:
            self._window_by_tag[view.gmv_tag] = window_obj
        return session, view

    def register_add_molecule_to_group(
        self,
        group_id: int,
        document: MoleculeDocument,
        window_obj: Any = None,
        pane_count: PaneCount = 1,
    ) -> tuple[DocumentSession, ViewSession]:
        session, view = self.registry.add_molecule_to_group(group_id, document, pane_count=pane_count)
        if window_obj is not None:
            self._window_by_tag[view.gmv_tag] = window_obj
        return session, view

    def register_clone_view(
        self,
        source_gmv_tag: str,
        window_obj: Any = None,
        pane_count: PaneCount = 1,
    ) -> tuple[DocumentSession, ViewSession]:
        session, view = self.registry.clone_view(source_gmv_tag, pane_count=pane_count)
        if window_obj is not None:
            self._window_by_tag[view.gmv_tag] = window_obj
        return session, view

    def close_window(self, gmv_tag: str) -> None:
        self._window_by_tag.pop(gmv_tag, None)
        self.registry.close_view(gmv_tag)

    @property
    def open_tags(self) -> list[str]:
        return list(self.registry.active_views.keys())
