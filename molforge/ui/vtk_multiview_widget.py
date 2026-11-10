"""
ui/vtk_multiview_widget.py - 单 RenderWindow 内置 1/2/4 视口 (Viewport) 多视图组件
===================================================================================
严格遵循 4.2 节 Native 稳定性守则：
  - 不在单个窗口内创建 4 个冲突的 OpenGL 上下文，而是管理 P1..P4 子视图状态与标准归一化视口矩形 (xmin, ymin, xmax, ymax)
  - 支持 P1 Front / P2 Side / P3 Top / P4 Perspective 独立相机预设与可选相机同步开关
"""

from __future__ import annotations

from typing import Literal

from ..application.workspace_registry import PaneCount, ViewSession

ViewportRect = tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax) in [0.0, 1.0]


def compute_viewport_rects(pane_count: PaneCount) -> dict[str, ViewportRect]:
    """计算单个 vtkRenderWindow 内 1 / 2 / 4 分屏的归一化视口坐标。"""
    if pane_count == 1:
        return {"P1": (0.0, 0.0, 1.0, 1.0)}
    elif pane_count == 2:
        return {
            "P1": (0.0, 0.0, 0.5, 1.0),
            "P2": (0.5, 0.0, 1.0, 1.0),
        }
    elif pane_count == 4:
        return {
            "P1": (0.0, 0.5, 0.5, 1.0),  # Top-Left: Front
            "P2": (0.5, 0.5, 1.0, 1.0),  # Top-Right: Side
            "P3": (0.0, 0.0, 0.5, 0.5),  # Bottom-Left: Top
            "P4": (0.5, 0.0, 1.0, 0.5),  # Bottom-Right: Perspective
        }
    raise ValueError(f"Unsupported pane_count: {pane_count}")


def hit_test_pane(norm_x: float, norm_y: float, pane_count: PaneCount) -> str:
    """根据归一化窗口坐标 (norm_x, norm_y) in [0, 1]^2 判定命中的子视口 P1..P4。"""
    rects = compute_viewport_rects(pane_count)
    x = max(0.0, min(1.0, float(norm_x)))
    y = max(0.0, min(1.0, float(norm_y)))
    for pid, (xmin, ymin, xmax, ymax) in rects.items():
        if xmin <= x <= xmax and ymin <= y <= ymax:
            return pid
    return "P1"


class VtkMultiviewController:
    """管理 ViewSession 的 1/2/4 视口切换、命中检测与相机预设。"""

    def __init__(self, view_session: ViewSession) -> None:
        self.view_session = view_session

    @property
    def pane_count(self) -> PaneCount:
        return self.view_session.pane_count

    @property
    def viewports(self) -> dict[str, ViewportRect]:
        return compute_viewport_rects(self.view_session.pane_count)

    def set_layout(self, count: PaneCount) -> dict[str, ViewportRect]:
        self.view_session.set_pane_layout(count)
        return self.viewports

    def select_pane_at(self, norm_x: float, norm_y: float) -> str:
        pid = hit_test_pane(norm_x, norm_y, self.view_session.pane_count)
        self.view_session.active_pane = pid
        return pid


def apply_multiview_to_render_window(render_window, primary_renderer, pane_count: PaneCount, shared_actors: list | None = None) -> list:
    """
    在同一个 vtkRenderWindow 内通过 SetViewport(xmin, ymin, xmax, ymax) 配置 1 / 2 / 4 视口 (P1..P4)，
    避免创建多个冲突的 QVTKRenderWindowInteractor / OpenGL 上下文（彻底杜绝 0xC0000409 崩溃）。
    返回附加的次级 vtkRenderer 列表。
    """
    try:
        import vtk
    except ImportError:
        return []
    if render_window is None or primary_renderer is None:
        return []

    rects = compute_viewport_rects(pane_count)
    p1_rect = rects.get("P1", (0.0, 0.0, 1.0, 1.0))
    primary_renderer.SetViewport(*p1_rect)

    # 移除此前创建的辅助分屏 renderer（保留 primary_renderer）
    existing = render_window.GetRenderers()
    to_remove = []
    if existing is not None:
        existing.InitTraversal()
        ren_item = existing.GetNextItem()
        while ren_item is not None:
            if ren_item is not primary_renderer and ren_item.GetLayer() == primary_renderer.GetLayer():
                to_remove.append(ren_item)
            ren_item = existing.GetNextItem()
    for r in to_remove:
        try:
            render_window.RemoveRenderer(r)
        except Exception:
            pass

    aux_renderers = []
    cam_presets = {
        "P2": ((22.0, 0.0, 0.0), (0.0, 0.0, 1.0)),   # Side view
        "P3": ((0.0, 22.0, 0.0), (0.0, 0.0, -1.0)),  # Top view
        "P4": ((14.0, 14.0, 14.0), (0.0, 1.0, 0.0)), # Isometric perspective
    }
    bg_colors = {
        "P2": (0.075, 0.125, 0.190),
        "P3": (0.062, 0.110, 0.168),
        "P4": (0.070, 0.118, 0.180),
    }

    for pid in ("P2", "P3", "P4"):
        if pid not in rects:
            continue
        sub_ren = vtk.vtkRenderer()
        sub_ren.SetViewport(*rects[pid])
        c_rgb = bg_colors.get(pid, (0.07, 0.12, 0.18))
        sub_ren.SetBackground(*c_rgb)
        for act in (shared_actors or []):
            if act is not None:
                try:
                    sub_ren.AddActor(act)
                except Exception:
                    pass
        cam = sub_ren.GetActiveCamera()
        if cam is not None and pid in cam_presets:
            pos, up = cam_presets[pid]
            cam.SetPosition(*pos)
            cam.SetFocalPoint(0.0, 0.0, 0.0)
            cam.SetViewUp(*up)
            sub_ren.ResetCamera()
        render_window.AddRenderer(sub_ren)
        aux_renderers.append(sub_ren)

    return aux_renderers

