"""
application/workspace_registry.py - 全局工作区与 G:M:V 视图注册表
=================================================================
严格实现 2.3 / 2.4 节 G:M:V 契约：
  - GroupSession (G): 管理分子组编号 G1, G2...（单调递增计数器，关闭窗口后重建绝不产生标签冲突）
  - DocumentSession (M): 组内分子 M1, M2... 对应唯一 DocumentSession
  - ViewSession (V): 同一分子的不同视图 V1, V2... 共享同一个 DocumentSession，但拥有各自独立的
    ViewSession（相机预设、渲染样式、1/2/4 Pane 布局 P1..P4、活动子视口）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from ..domain.document import MoleculeDocument
from .document_session import DocumentSession

PaneCount = Literal[1, 2, 4]
CameraPreset = Literal["perspective", "front", "side", "top"]


@dataclass
class PaneState:
    pane_id: str  # "P1" | "P2" | "P3" | "P4"
    camera_preset: CameraPreset = "perspective"
    render_style: str = "ball_and_stick"


@dataclass
class ViewSession:
    view_uuid: str
    gmv_tag: str          # 例如 "G1:M1:V1"
    group_id: int
    molecule_index: int
    view_index: int
    document_id: str
    pane_count: PaneCount = 1
    active_pane: str = "P1"
    sync_cameras: bool = False
    panes: dict[str, PaneState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.panes:
            self.set_pane_layout(self.pane_count)

    def set_pane_layout(self, count: PaneCount) -> None:
        if count not in (1, 2, 4):
            raise ValueError(f"Unsupported pane count: {count} (expected 1, 2, or 4)")
        self.pane_count = count
        if count == 1:
            self.panes = {"P1": PaneState("P1", "perspective")}
        elif count == 2:
            self.panes = {
                "P1": PaneState("P1", "front"),
                "P2": PaneState("P2", "perspective"),
            }
        else:
            self.panes = {
                "P1": PaneState("P1", "front"),
                "P2": PaneState("P2", "side"),
                "P3": PaneState("P3", "top"),
                "P4": PaneState("P4", "perspective"),
            }
        if self.active_pane not in self.panes:
            self.active_pane = "P1"


@dataclass
class GroupSession:
    group_id: int
    next_molecule_index: int = 1
    molecule_sessions: dict[int, str] = field(default_factory=dict)  # m_idx -> document_id
    next_view_index_by_m: dict[int, int] = field(default_factory=dict)


class WorkspaceRegistry:
    """应用级工作区注册表（管理所有 DocumentSession、GroupSession 与 ViewSession）。"""

    _singleton: "WorkspaceRegistry | None" = None

    def __init__(self) -> None:
        self._documents: dict[str, DocumentSession] = {}
        self._groups: dict[int, GroupSession] = {}
        self._views: dict[str, ViewSession] = {}  # gmv_tag -> ViewSession
        self._next_group_id: int = 1

    @classmethod
    def instance(cls) -> "WorkspaceRegistry":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def reset_for_testing(self) -> None:
        self._documents.clear()
        self._groups.clear()
        self._views.clear()
        self._next_group_id = 1

    def get_or_create_session(self, document: MoleculeDocument) -> DocumentSession:
        doc_id = document.document_id
        if doc_id not in self._documents:
            self._documents[doc_id] = DocumentSession(document)
        return self._documents[doc_id]

    def get_session(self, document_id: str) -> DocumentSession | None:
        return self._documents.get(document_id)

    def create_new_group_view(self, document: MoleculeDocument, pane_count: PaneCount = 1) -> tuple[DocumentSession, ViewSession]:
        session = self.get_or_create_session(document)
        g_id = self._next_group_id
        self._next_group_id += 1
        grp = GroupSession(group_id=g_id, next_molecule_index=2)
        grp.molecule_sessions[1] = session.document_id
        grp.next_view_index_by_m[1] = 2
        self._groups[g_id] = grp

        tag = f"G{g_id}:M1:V1"
        view = ViewSession(
            view_uuid=uuid.uuid4().hex[:12],
            gmv_tag=tag,
            group_id=g_id,
            molecule_index=1,
            view_index=1,
            document_id=session.document_id,
            pane_count=pane_count,
        )
        self._views[tag] = view
        return session, view

    def add_molecule_to_group(self, group_id: int, document: MoleculeDocument, pane_count: PaneCount = 1) -> tuple[DocumentSession, ViewSession]:
        session = self.get_or_create_session(document)
        if group_id not in self._groups:
            self._groups[group_id] = GroupSession(group_id=group_id)
            if group_id >= self._next_group_id:
                self._next_group_id = group_id + 1
        grp = self._groups[group_id]
        m_idx = grp.next_molecule_index
        grp.next_molecule_index += 1
        grp.molecule_sessions[m_idx] = session.document_id
        grp.next_view_index_by_m[m_idx] = 2

        tag = f"G{group_id}:M{m_idx}:V1"
        view = ViewSession(
            view_uuid=uuid.uuid4().hex[:12],
            gmv_tag=tag,
            group_id=group_id,
            molecule_index=m_idx,
            view_index=1,
            document_id=session.document_id,
            pane_count=pane_count,
        )
        self._views[tag] = view
        return session, view

    def clone_view(self, source_gmv_tag: str, pane_count: PaneCount = 1) -> tuple[DocumentSession, ViewSession]:
        if source_gmv_tag in self._views:
            src_v = self._views[source_gmv_tag]
            g_id = src_v.group_id
            m_idx = src_v.molecule_index
            doc_id = src_v.document_id
            session = self._documents[doc_id]
        else:
            raise KeyError(f"Unknown source GMV tag: '{source_gmv_tag}'")

        grp = self._groups[g_id]
        v_idx = grp.next_view_index_by_m.get(m_idx, 1)
        grp.next_view_index_by_m[m_idx] = v_idx + 1

        tag = f"G{g_id}:M{m_idx}:V{v_idx}"
        view = ViewSession(
            view_uuid=uuid.uuid4().hex[:12],
            gmv_tag=tag,
            group_id=g_id,
            molecule_index=m_idx,
            view_index=v_idx,
            document_id=session.document_id,
            pane_count=pane_count,
        )
        self._views[tag] = view
        return session, view

    def register_explicit_tag(self, gmv_tag: str, document: MoleculeDocument, pane_count: PaneCount = 1) -> tuple[DocumentSession, ViewSession]:
        session = self.get_or_create_session(document)
        if gmv_tag in self._views:
            return session, self._views[gmv_tag]
        parts = gmv_tag.upper().split(":")
        g_id = int(parts[0].lstrip("G")) if len(parts) >= 1 and parts[0].lstrip("G").isdigit() else self._next_group_id
        m_idx = int(parts[1].lstrip("M")) if len(parts) >= 2 and parts[1].lstrip("M").isdigit() else 1
        v_idx = int(parts[2].lstrip("V")) if len(parts) >= 3 and parts[2].lstrip("V").isdigit() else 1

        if g_id >= self._next_group_id:
            self._next_group_id = g_id + 1
        if g_id not in self._groups:
            self._groups[g_id] = GroupSession(group_id=g_id)
        grp = self._groups[g_id]
        grp.molecule_sessions[m_idx] = session.document_id
        if m_idx >= grp.next_molecule_index:
            grp.next_molecule_index = m_idx + 1
        cur_next_v = grp.next_view_index_by_m.get(m_idx, 1)
        if v_idx >= cur_next_v:
            grp.next_view_index_by_m[m_idx] = v_idx + 1

        view = ViewSession(
            view_uuid=uuid.uuid4().hex[:12],
            gmv_tag=gmv_tag,
            group_id=g_id,
            molecule_index=m_idx,
            view_index=v_idx,
            document_id=session.document_id,
            pane_count=pane_count,
        )
        self._views[gmv_tag] = view
        return session, view

    def close_view(self, gmv_tag: str) -> None:
        view = self._views.pop(gmv_tag, None)
        if view is not None:
            still_used = any(v.document_id == view.document_id for v in self._views.values())
            if not still_used:
                self._documents.pop(view.document_id, None)

    @property
    def active_views(self) -> dict[str, ViewSession]:
        return dict(self._views)
