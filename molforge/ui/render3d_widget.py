"""
ui/render3d_widget.py - 零崩溃异步命令派发 3D 视口组件
========================================================
核心保障：
1. `eventFilter` 内绝不同步调用 `CommandBus.execute()`、`SelectionService` 通知或 `VTK Render()`！
   所有修改选择、加删原子、建键、改键级、提交拖拽坐标的动作，一律通过 `QTimer.singleShot(0, ...)`
   推迟到 `QVTKRenderWindowInteractor` 事件栈完全退出后的干净主循环执行。
2. 移除了被动鼠标移动 (`NoButton`) 时的 60Hz 悬停渲染调用与 `self.setFocus()` 焦点抢夺。
3. 拖动原子时，通过合并节流 (`_pending_live_drag`) 原地更新 `vtkMolecule` 的原子与相连化学键，
   实现“按住原子拖动时化学键实时跟随变形，松手后自动进 Undo 栈”。
"""
from __future__ import annotations
from .scrolling import HorizontalWheelScrollArea

import math
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPointF

try:
    from pyvistaqt import QtInteractor
except ImportError:  # pragma: no cover
    QtInteractor = None

from ..rendering.vtk_backend import VtkRendererBackend
from ..rendering.contracts import RenderSnapshot, RepresentationMode
from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId
from ..domain.elements import get_element
from ..application.selection import SelectionService



from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QPolygonF

# P0-4：四种工具模式的统一状态机与实时操作指南表
TOOL_MODE_STATE_TABLE: dict[str, dict[str, str]] = {
    "选择": {
        "name": "选择 (Select)",
        "hud_short": "左键点选/拖动选中原子(支持多选平移) · Shift+拖空白框选/套索 · 右键弹出菜单",
        "status_hint": "当前模式：选择 (V)  |  操作：左键点选/拖动选中原子(支持多选一起平移)，Shift+拖空白框选/套索，右键弹出完整菜单",
    },
    "原子": {
        "name": "建原子 (Atom)",
        "hud_short": "左键点空白加原子并自动成键 · 从已有原子拖拽定向生长新键 · 右键菜单",
        "status_hint": "当前模式：建原子 (A)  |  操作：左键点空白加原子并自动成键，从已有原子拖拽定向生长新键，右键菜单",
    },
    "键": {
        "name": "建键 (Bond)",
        "hud_short": "在两原子间拖拽建键 · 左键点已有键切换单/双/三键 · 右键菜单",
        "status_hint": "当前模式：建键 (B)  |  操作：在两原子间拖拽建键，左键点击已有化学键切换单/双/三键，右键菜单",
    },
    "擦除": {
        "name": "擦除 (Erase)",
        "hud_short": "左键点击任意原子或化学键立即删除 (支持 Ctrl+Z 撤销) · 右键菜单",
        "status_hint": "当前模式：擦除 (E)  |  操作：左键点击任意原子或化学键立即删除（支持 Ctrl+Z 撤销）",
    },
}


def _points_in_polygon_numpy(x: np.ndarray, y: np.ndarray, poly_pts: list[tuple[float, float]]) -> np.ndarray:
    """纯 NumPy 射线法 (Ray-Casting) 判断一组屏幕投影点 (x, y) 是否位于套索/多边形闭合区域内。"""
    n_pts = len(poly_pts)
    inside = np.zeros(len(x), dtype=bool)
    if n_pts < 3 or len(x) == 0:
        return inside
    px = np.array([p[0] for p in poly_pts], dtype=np.float64)
    py = np.array([p[1] for p in poly_pts], dtype=np.float64)
    j = n_pts - 1
    for i in range(n_pts):
        xi, yi = px[i], py[i]
        xj, yj = px[j], py[j]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi)
        inside ^= cond
        j = i
    return inside


class SelectionOverlayWidget(QWidget):
    """支持矩形框选 (Box) 与自由套索/多边形 (Lasso/Polygon) 的半透明青色高亮绘制层。"""

    def __init__(self, parent=None, chromeless: bool = False):
        super().__init__(parent)
        self._chromeless = bool(chromeless)
        self.pane_count: int = 1
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.mode: str = "box"  # "box" | "lasso"
        self.points: list[QPointF] = []

    def paintEvent(self, event):
        if not self.points:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(0, 229, 255, 230), 1.8, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 229, 255, 42))

        if self.mode == "box" and len(self.points) >= 2:
            p1, p2 = self.points[0], self.points[-1]
            x1, x2 = sorted([p1.x(), p2.x()])
            y1, y2 = sorted([p1.y(), p2.y()])
            painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
        elif len(self.points) >= 2:
            poly = QPolygonF(self.points)
            painter.drawPolygon(poly)
        painter.end()


class Render3DWidget(QWidget):
    """
    Studio 3D 分子建模与渲染视口（零崩溃异步事件状态机）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: MoleculeDocument | None = None
        self._selection: SelectionService | None = None
        self._command_bus = None
        self._last_doc_id: str | None = None
        self._bond_ids: list[BondId] = []

        # 3D 交互状态机变量
        self._press_qpos: QPointF | None = None
        self._press_atom_id: AtomId | None = None
        self._press_bond_id: BondId | None = None
        self._drag_start_3d: np.ndarray | None = None
        self._current_drag_3d: np.ndarray | None = None
        self._is_dragging_atom: bool = False
        self._is_dragging_bond: bool = False
        self._intercepting_left_mouse: bool = False
        self._live_drag_scheduled: bool = False
        self._pending_rb_points: tuple[np.ndarray, np.ndarray] | None = None
        self._multi_drag_start: dict = {}
        self._is_box_selecting = False
        self._box_start_qpos = None
        self._box_end_qpos = None

        self.on_add_atom_at_3d = None
        self.on_delete_selected_3d = None
        self.status_callback = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("ViewHeader")
        header.setMinimumHeight(36)
        header.setStyleSheet(
            "QFrame#ViewHeader { background-color: #0E1926; border-bottom: 1px solid #1E3246; }"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 3, 10, 3)
        h_lay.setSpacing(6)

        title = QLabel("3D 视口")
        title.setStyleSheet(
            "color: #66DEC9; background: #132A38; border: 1px solid #265264; "
            "border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700;"
        )
        h_lay.addWidget(title)

        self.hud_info_label = QLabel("[选择 (Select)] 左键点选/拖动选中原子(支持多选平移) · Shift+拖框选/套索 · 右键菜单")
        self.hud_info_label.setMinimumWidth(110)
        self.hud_info_label.setMaximumWidth(180)
        self.hud_info_label.setStyleSheet("color: #EAF2F6; font-size: 12px; font-weight: 600; background: transparent;")
        h_lay.addWidget(self.hud_info_label, 1)

        clean_btn = QPushButton("⚡ 3D 优化")
        clean_btn.setMinimumWidth(78)
        clean_btn.setToolTip("执行 MMFF94 / 谐振弹簧 3D 几何弛豫优化并居中视角 (Ctrl+M)")
        clean_btn.setStyleSheet(
            "QPushButton { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; "
            "border-radius:6px; padding:3px 9px; font-size:12px; font-weight:800; }"
            "QPushButton:hover { background:#14B8A6; color:#021815; }"
        )
        clean_btn.clicked.connect(self.clean_3d_geometry)
        h_lay.addWidget(clean_btn)

        reset_btn = QPushButton("⌖ 正视")
        reset_btn.setMinimumWidth(58)
        reset_btn.setToolTip("按分子主平面法向重置 3D 相机视角")
        reset_btn.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 9px; font-size:12px; font-weight:600; }"
            "QPushButton:hover { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; }"
        )
        reset_btn.clicked.connect(self.reset_camera)
        h_lay.addWidget(reset_btn)

        _hdr_btn_style = (
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 6px; font-size:12px; font-weight:600; }"
            "QPushButton:checked { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; font-weight:800; }"
            "QPushButton:hover { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; }"
        )
        for label, direction, tip in [
            ("前", "front", "前视图 (沿 -Z)"),
            ("侧", "side", "侧视图 (沿 -X)"),
            ("俯", "top", "俯视图 (沿 +Y)"),
            ("轴", "iso", "等轴测图"),
        ]:
            btn = QPushButton(label)
            btn.setMinimumWidth(34)
            btn.setToolTip(tip)
            btn.setStyleSheet(_hdr_btn_style)
            btn.clicked.connect(lambda checked, d=direction: self.set_view_direction(d))
            h_lay.addWidget(btn)

        zoom_in_btn = QPushButton("＋")
        zoom_in_btn.setMinimumWidth(28)
        zoom_in_btn.setToolTip("放大 3D 视图 (Zoom In)")
        zoom_in_btn.setStyleSheet(_hdr_btn_style)
        zoom_in_btn.clicked.connect(lambda: self.renderer.zoom_camera(1.22))
        h_lay.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("－")
        zoom_out_btn.setMinimumWidth(28)
        zoom_out_btn.setToolTip("缩小 3D 视图 (Zoom Out)")
        zoom_out_btn.setStyleSheet(_hdr_btn_style)
        zoom_out_btn.clicked.connect(lambda: self.renderer.zoom_camera(0.82))
        h_lay.addWidget(zoom_out_btn)

        self.region_mode_btn = QPushButton("⬚ 框选")
        self.region_mode_btn.setCheckable(True)
        self.region_mode_btn.setMinimumWidth(56)
        self.region_mode_btn.setToolTip("点击切换 Shift+拖拽选择方式：[⬚ 矩形框选] ⇄ [➰ 自由套索选择]")
        self.region_mode_btn.setStyleSheet(_hdr_btn_style)
        self.region_mode_btn.clicked.connect(self._toggle_select_region_mode)
        h_lay.addWidget(self.region_mode_btn)

        self.lbl_toggle_btn = QPushButton("🔢 原子编号")
        self.lbl_toggle_btn.setCheckable(True)
        self.lbl_toggle_btn.setMinimumWidth(78)
        self.lbl_toggle_btn.setToolTip(
            "显示/隐藏 3D 原子元素与唯一编号标签（如 C1, N2, O3...）。\n"
            "用途：在测量键长/键角/二面角、或编写 Multiwfn (IGMH/偶极) 与 GROMACS (index.ndx) 原子组范围时定位每个原子的序号。"
        )
        self.lbl_toggle_btn.setStyleSheet(_hdr_btn_style)
        self.lbl_toggle_btn.toggled.connect(lambda checked: self.set_view_options(show_labels=checked))
        h_lay.addWidget(self.lbl_toggle_btn)

        self.axes_toggle_btn = QPushButton("🧭 坐标轴")
        self.axes_toggle_btn.setCheckable(True)
        self.axes_toggle_btn.setChecked(True)
        self.axes_toggle_btn.setMinimumWidth(68)
        self.axes_toggle_btn.setToolTip("显示/隐藏 3D 视口左下角的三维 XYZ 笛卡尔坐标轴指示器 (红=X, 绿=Y, 蓝=Z)")
        self.axes_toggle_btn.setStyleSheet(_hdr_btn_style)
        self.axes_toggle_btn.toggled.connect(lambda checked: self.set_view_options(show_axes=checked))
        h_lay.addWidget(self.axes_toggle_btn)

        self._header_frame = HorizontalWheelScrollArea(header, height=36)
        root.addWidget(self._header_frame)
        if getattr(self, "_chromeless", False):
            self._header_frame.hide()

        self.plotter = QtInteractor(self) if QtInteractor is not None else QWidget(self)
        self.renderer = VtkRendererBackend()
        if QtInteractor is not None:
            self.plotter.set_background(
                color=[0.067, 0.114, 0.173],
                top=[0.145, 0.227, 0.314],
            )
            inter = self.plotter.interactor
            inter.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            inter.setStyleSheet("border:none; background:transparent;")
            inter.installEventFilter(self)
            self.renderer.attach(self.plotter)

        root.addWidget(self.plotter, 1)
        def release_labels(_=None, backend=self.renderer):
            if backend._native_labels is not None:backend._native_labels.close()
        self.destroyed.connect(release_labels)

        # 框选/套索半透明绘制叠加层 + 拖拽文件支持 + LOD 恢复定时器
        self.setAcceptDrops(True)
        self._select_region_mode: str = "box"  # "box" | "lasso"
        self._lasso_points: list[QPointF] = []
        self._keep_multi_on_press: bool = False
        self._box_overlay = SelectionOverlayWidget(self.plotter)
        self._box_overlay.hide()

        self._lod_timer = QTimer(self)
        self._lod_timer.setSingleShot(True)
        self._lod_timer.setInterval(180)
        self._lod_timer.timeout.connect(lambda: self.renderer.end_interactive_lod())

    def _refresh_atom_labels(self):
        self.renderer._update_labels_in_place()
        self.renderer.render()

    def _toggle_select_region_mode(self, checked: bool):
        if checked:
            self._select_region_mode = "lasso"
            self.region_mode_btn.setText("➰ 套索")
        else:
            self._select_region_mode = "box"
            self.region_mode_btn.setText("⬚ 框选")
        self._update_hud_text()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            local_p = urls[0].toLocalFile()
            win = self.window()
            if local_p and hasattr(win, "open_molecule_file"):
                win.open_molecule_file(local_p)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def _update_box_overlay(self):
        """根据框选起点/终点或套索轨迹点更新半透明高亮层，并实时更新状态栏提示。"""
        if not self._is_box_selecting or self._box_start_qpos is None or self._box_end_qpos is None:
            self._box_overlay.hide()
            return
        inter = self._interactor_widget()
        self._box_overlay.setGeometry(0, 0, inter.width(), inter.height())
        self._box_overlay.mode = getattr(self, "_select_region_mode", "box")
        if self._box_overlay.mode == "lasso":
            self._box_overlay.points = list(self._lasso_points)
        else:
            self._box_overlay.points = [self._box_start_qpos, self._box_end_qpos]
        self._box_overlay.show()
        self._box_overlay.raise_()
        self._box_overlay.update()
        if self.status_callback is not None:
            mode_cn = "自由套索选择" if self._box_overlay.mode == "lasso" else "矩形框选"
            self.status_callback(f"正在{mode_cn}... 松开鼠标完成多选，随后可直接按住任意选中原子同步平移全体")

    def _interactor_widget(self) -> QWidget:
        if QtInteractor is not None and hasattr(self.plotter, "interactor"):
            return self.plotter.interactor
        return self.plotter

    def _update_hud_text(self):
        tool = self.renderer.current_tool
        elem = get_element(self.renderer.current_element)
        sym = elem.symbol if elem else "C"
        info = TOOL_MODE_STATE_TABLE.get(tool, TOOL_MODE_STATE_TABLE["选择"])
        self.hud_info_label.setText(f"{info['name']} · {sym}")
        self.hud_info_label.setToolTip(info["hud_short"])
        if self.status_callback is not None:
            try:
                self.status_callback(info["status_hint"])
            except Exception:
                pass

    def set_command_bus(self, bus):
        if getattr(self, "_command_bus", None) is bus and getattr(self, "_bus_callback", None) is not None:
            return
        previous = getattr(self, "_command_bus", None)
        callback = getattr(self, "_bus_callback", None)
        if previous is not None and callback is not None:
            previous.remove_listener(callback)
        self._command_bus = bus
        self._bus_callback = lambda _doc: self._on_bus_document_changed()
        bus.add_listener(self._bus_callback)
        self.destroyed.connect(lambda _=None, service=bus, cb=self._bus_callback: service.remove_listener(cb))

    def _on_bus_document_changed(self):
        if self._document is None:
            return
        # 合并到事件循环，避免命令栈内直接重入 VTK
        QTimer.singleShot(0, lambda: self._refresh_from_document(reset_cam=False))

    def set_current_tool(self, tool_name: str):
        self.renderer.current_tool = tool_name
        self._update_hud_text()

    def set_current_element(self, atomic_num: int):
        self.renderer.current_element = int(atomic_num)
        self._update_hud_text()

    def set_document(self, doc: MoleculeDocument):
        is_new_doc = (self._last_doc_id != doc.document_id)
        self._document = doc
        self._last_doc_id = doc.document_id
        self._refresh_from_document(reset_cam=is_new_doc)

    def set_conformer_coords(self, coords):
        if self._document is None:
            return
        coords = np.asarray(coords, dtype=np.float32)
        n = self._document.topology.num_atoms
        if coords.shape[0] != n:
            return
        store = self._document.ensure_coordinates()
        if store.current is None:
            store.add_frame(coords, source="ETKDG")
        else:
            store.update_current_coords(coords)
        self._refresh_from_document(reset_cam=False)

    def clean_3d_geometry(self):
        if self._document is None or self._document.num_atoms == 0:
            return
        if self._command_bus is not None:
            from ..application.builtin_commands import CleanGeometry3DCommand
            res = self._command_bus.execute(CleanGeometry3DCommand(max_iters=120))
            if self.status_callback and res.message:
                self.status_callback(res.message)
        else:
            self._document.relax_3d_geometry(max_iters=120)
            self._refresh_from_document(reset_cam=False)
        self.reset_camera()

    def get_camera_view_basis(self):
        """获取当前 3D 视口相机正交基 (right, true_up)，用于精确 3D->2D 视平面投影。"""
        if hasattr(self, "renderer") and self.renderer is not None:
            try:
                w, h = float(max(10, self.width())), float(max(10, self.height()))
                cam_pos, cam_focal, cam_up, fov_y = self.renderer._get_camera_params()
                from ..rendering.vtk_backend import compute_camera_basis
                eye, forward, right, true_up, tx, ty = compute_camera_basis(
                    cam_pos, cam_focal, cam_up, fov_y, w, h
                )
                return right, true_up
            except Exception:
                pass
        return None, None

    def _refresh_from_document(self, reset_cam: bool = False):
        if self._document is None:
            return

        doc = self._document
        atom_ids, id_to_idx = doc.topology.atom_index_map()
        atomic_numbers = [doc.topology.get_atom(aid).atomic_num for aid in atom_ids]

        bonds = []
        self._bond_ids = []
        for bid in doc.topology.bond_ids:
            bond = doc.topology.get_bond(bid)
            if bond.begin in id_to_idx and bond.end in id_to_idx:
                order = 4 if bond.aromatic else bond.order
                bonds.append((id_to_idx[bond.begin], id_to_idx[bond.end], order))
                self._bond_ids.append(bid)

        n = len(atomic_numbers)
        if n == 0:
            coords = np.zeros((0, 3), dtype=np.float32)
        else:
            store = doc.ensure_coordinates()
            if store.current is not None and store.current.coords.shape == (n, 3):
                coords = store.current.coords.copy()
            else:
                doc.relax_3d_geometry(max_iters=80)
                coords = doc.coordinates.current.coords.copy() if doc.coordinates.current is not None else np.zeros((n, 3), dtype=np.float32)

        is_massive = (n > 1500)
        if is_massive:
            atom_scales = np.ones(n, dtype=np.float32)
            atom_colors = {}
            bond_scales = np.ones(len(self._bond_ids), dtype=np.float32)
            bond_colors = {}
            atom_opacities = None
            atom_glows = {}
        else:
            # 提取每个原子的独立 scale 与独立 color，以及每条键的独立 width_scale 与独立 color (P0 核心要求！)
            atom_scales = [float(getattr(doc.topology.get_atom(aid), "scale", 1.0)) for aid in atom_ids]
            atom_colors = {}
            for i, aid in enumerate(atom_ids):
                c = getattr(doc.topology.get_atom(aid), "color", None)
                if c is not None:
                    atom_colors[i] = tuple(float(x) for x in c)

            bond_scales = []
            bond_colors = {}
            for b_idx, bid in enumerate(self._bond_ids):
                b_obj = doc.topology.get_bond(bid)
                bond_scales.append(float(getattr(b_obj, "width_scale", 1.0)))
                bc = getattr(b_obj, "color", None)
                if bc is not None:
                    bond_colors[b_idx] = tuple(float(x) for x in bc)
            atom_opacities = [float(doc.topology.get_atom(a).properties.get("opacity", 1.0)) for a in atom_ids]
            atom_glows = {i: tuple(doc.topology.get_atom(a).properties.get("glow_color", (0.3, 0.8, 1.0))) + (float(doc.topology.get_atom(a).properties.get("glow", 0.0)),) for i, a in enumerate(atom_ids)}

        selected = self._selection.selected_atoms if self._selection is not None else set()
        selected_bonds = self._selection.selected_bonds if self._selection is not None else set()
        measure_chain = None
        if self._selection is not None and not self._selection.is_empty:
            try:
                from ..application.measurement_targets import MeasurementTargetResolver
                target = MeasurementTargetResolver.resolve(doc, self._selection)
                if (
                    len(selected) in (2, 3, 4)
                    or (len(selected_bonds) == 2 and not selected)
                ):
                    if target.kind in ('distance', 'angle', 'dihedral', 'ambiguous') and target.atoms:
                        measure_chain = list(target.atoms)
            except Exception:
                pass

        snapshot = RenderSnapshot(
            measure_chain=measure_chain,
            atom_ids=atom_ids,
            atomic_numbers=np.array(atomic_numbers, dtype=np.int32),
            bonds=bonds,
            coordinates=coords,
            mode=self.renderer._mode,
            selected_atoms=selected,
            selected_bonds=selected_bonds,
            bond_ids=list(self._bond_ids),
            atom_scales=np.array(atom_scales, dtype=np.float32),
            atom_colors=atom_colors,
            atom_opacities=atom_opacities,
            atom_glows=atom_glows,
            bond_scales=np.array(bond_scales, dtype=np.float32),
            bond_colors=bond_colors,
            show_hydrogens=self.renderer.show_hydrogens,
            show_bonds=self.renderer.show_bonds,
            show_labels=self.renderer.show_labels,
            show_symbols=self.renderer.show_symbols,
            show_axes=self.renderer.show_axes,
            color_scheme=self.renderer._color_scheme,
        )

        self.renderer.set_snapshot(snapshot, reset_cam=reset_cam)
        self._update_hud_text()

    # ---------- 异步安全动作派发器（全部在 eventFilter 栈退出后执行！） ----------

    def _defer(self, fn):
        """将任何会修改 Selection / CommandBus / VTK 的动作推迟到干净的 Qt 主事件循环。"""
        QTimer.singleShot(0, fn)

    def _flush_live_drag(self):
        """合并节流执行 3D 实时拖原子（含框选/套索多原子同步平移！）或橡皮筋预览更新。"""
        self._live_drag_scheduled = False
        if self._is_dragging_atom and self._press_atom_id is not None and self._current_drag_3d is not None:
            multi = getattr(self, "_multi_drag_start", None) or {}
            if len(multi) > 1 and self._press_atom_id in multi and self._drag_start_3d is not None:
                delta = np.asarray(self._current_drag_3d, dtype=np.float32) - np.asarray(self._drag_start_3d, dtype=np.float32)
                pos_map = {aid: (orig + delta) for aid, orig in multi.items()}
                self.renderer.update_multi_atoms_coords(pos_map)
            else:
                self.renderer.update_single_atom_coord(self._press_atom_id, self._current_drag_3d)
        elif self._is_dragging_bond and self._pending_rb_points is not None:
            p1, p2 = self._pending_rb_points
            self.renderer.update_rubberband_3d(p1, p2)

    # ---------- Qt EventFilter（纯数学拾取 + 零同步 VTK/Command 调用） ----------

    def eventFilter(self, obj, event) -> bool:
        inter = self._interactor_widget()
        if obj is not inter or self._document is None:
            return super().eventFilter(obj, event)

        et = event.type()

        # 双击空白处：即使在“选择”模式下也支持直接加原子并自动成键！
        if et == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            lx, ly = pos.x(), pos.y()
            w, h = inter.width(), inter.height()
            hit_aid = self.renderer.pick_atom_id_at_qt(lx, ly, w, h)
            if hit_aid is None and self._command_bus is not None:
                world_pos = self.renderer.unproject_qt_to_world(lx, ly, w, h)
                elem = self.renderer.current_element
                from ..application.builtin_commands import AddAtomCommand
                self._defer(lambda wp=world_pos, z=elem: self._command_bus.execute(
                    AddAtomCommand(z, x=float(wp[0]), y=float(wp[1]), z=float(wp[2]), auto_bond_nearest=True)
                ))
                return True

        # 1. 鼠标按下
        if et == QEvent.Type.MouseButtonPress:
            pos = event.position()
            lx, ly = pos.x(), pos.y()
            w, h = inter.width(), inter.height()
            btn = event.button()
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            tool = self.renderer.current_tool

            # 右键点击：弹出上下文菜单（不再直接删除）；右键点空白 -> VTK 缩放/旋转
            if btn == Qt.MouseButton.RightButton:
                hit_aid = self.renderer.pick_atom_id_at_qt(lx, ly, w, h)
                hit_b_idx = self.renderer.pick_bond_idx_at_qt(lx, ly, w, h) if hit_aid is None else -1
                hit_bid = self._bond_ids[hit_b_idx] if (0 <= hit_b_idx < len(self._bond_ids)) else None
                self._defer(lambda a=hit_aid, b=hit_bid, qx=int(lx), qy=int(ly): self._show_context_menu(a, b, qx, qy))
                return True

            if btn != Qt.MouseButton.LeftButton:
                return False

            # 左键按下：调用 100% 纯 NumPy 拾取（零 C++ VTK 调用）
            hit_aid = self.renderer.pick_atom_id_at_qt(lx, ly, w, h)
            hit_b_idx = -1 if hit_aid is not None else self.renderer.pick_bond_idx_at_qt(lx, ly, w, h)
            hit_bid = self._bond_ids[hit_b_idx] if (0 <= hit_b_idx < len(self._bond_ids)) else None

            self._press_qpos = QPointF(pos)
            self._press_atom_id = hit_aid
            self._press_bond_id = hit_bid
            self._is_dragging_atom = False
            self._is_dragging_bond = False
            self._current_drag_3d = None
            self._pending_rb_points = None

            # 工具 A：擦除模式
            if tool == "擦除":
                if hit_aid is not None and self._command_bus is not None:
                    from ..application.builtin_commands import DeleteAtomCommand
                    self._defer(lambda a=hit_aid: self._command_bus.execute(DeleteAtomCommand(a)))
                elif hit_bid is not None and self._command_bus is not None:
                    from ..application.builtin_commands import DeleteBondCommand
                    self._defer(lambda b=hit_bid: self._command_bus.execute(DeleteBondCommand(b)))
                self._reset_interaction_state()
                return True

            # 工具 B：原子模式
            if tool == "原子":
                self._intercepting_left_mouse = True
                if hit_aid is not None:
                    self._drag_start_3d = None if self._document.topology.get_atom(hit_aid).properties.get("frozen") else self._document.get_atom_3d_pos(hit_aid)
                return True

            # 工具 C：键模式
            if tool == "键":
                if hit_aid is not None:
                    self._intercepting_left_mouse = True
                    self._drag_start_3d = None if self._document.topology.get_atom(hit_aid).properties.get("frozen") else self._document.get_atom_3d_pos(hit_aid)
                    if self._selection is not None:
                        self._defer(lambda a=hit_aid: self._selection.select_atom(a, add=False, origin="3d"))
                    return True
                if hit_bid is not None and self._command_bus is not None:
                    self._defer(lambda b=hit_bid: self._cycle_bond_order_safe(b))
                    self._reset_interaction_state()
                    return True
                return False

            # 工具 D：选择模式（命中原子 -> 选中并准备拖动；若点在已多选的原子上，保留多选以便一起拖动！）
            if hit_aid is not None:
                self._drag_start_3d = None if self._document.topology.get_atom(hit_aid).properties.get("frozen") else self._document.get_atom_3d_pos(hit_aid)
                self._intercepting_left_mouse = True
                self._keep_multi_on_press = False
                if self._selection is not None:
                    already_in_multi = (
                        not shift
                        and hit_aid in self._selection.selected_atoms
                        and len(self._selection.selected_atoms) > 1
                    )
                    if already_in_multi:
                        # 关键修复 (P0-1)：点击已框选的多个原子之一时不清空其他选中原子，立即同步捕获全部初始坐标！
                        self._keep_multi_on_press = True
                        self._capture_multi_drag_origins()
                    elif shift:
                        self._selection.toggle_atom(hit_aid, origin="3d")
                        self._capture_multi_drag_origins()
                    else:
                        self._selection.select_atom(hit_aid, add=False, origin="3d")
                        self._capture_multi_drag_origins()
                return True

            if hit_bid is not None:
                # 选择模式下点键：只选中键，不切换键级（切换键级走右键菜单或键工具）
                if self._selection is not None:
                    self._defer(lambda b=hit_bid: self._selection.select_bond(b, add=shift, origin="3d"))
                self._reset_interaction_state()
                return True

            # 选择模式下左键点空白：
            # - 普通点空白：清空选中，开启 3D 旋转 LOD 防卡顿，返回 False 给 VTK 旋转相机
            # - Shift+点空白：开始框选 / 套索选择模式
            if shift:
                self._is_box_selecting = True
                self._box_start_qpos = QPointF(pos)
                self._box_end_qpos = QPointF(pos)
                self._lasso_points = [QPointF(pos)]
                self._intercepting_left_mouse = True
                return True
            else:
                if self._selection is not None and not self._selection.is_empty:
                    self._defer(lambda: self._selection.clear(origin="3d"))
                self._reset_interaction_state()
                self.renderer.begin_interactive_lod()
                self._lod_timer.start()
                return False

        # 滚轮缩放：启用 LOD 加速并在静止后恢复
        if et == QEvent.Type.Wheel:
            self.renderer.begin_interactive_lod()
            self._lod_timer.start()
            return False

        # 2. 鼠标移动
        if et == QEvent.Type.MouseMove:
            if not self._intercepting_left_mouse or self._press_qpos is None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.renderer.begin_interactive_lod()
                    self._lod_timer.start()
                return False

            pos = event.position()
            lx, ly = pos.x(), pos.y()
            w, h = inter.width(), inter.height()
            moved_px = math.hypot(lx - self._press_qpos.x(), ly - self._press_qpos.y())
            if moved_px < 4.0:
                return True

            # 框选 / 套索模式：更新矩形终点或套索轨迹点
            if self._is_box_selecting:
                self._box_end_qpos = QPointF(lx, ly)
                if getattr(self, "_select_region_mode", "box") == "lasso":
                    if not self._lasso_points or math.hypot(
                        lx - self._lasso_points[-1].x(), ly - self._lasso_points[-1].y()
                    ) >= 4.0:
                        self._lasso_points.append(QPointF(lx, ly))
                self._update_box_overlay()
                return True

            tool = self.renderer.current_tool

            # 在“键”或“原子”模式下从已有原子拖动 -> 3D 橡皮筋预览圆柱
            if tool in ("键", "原子") and self._press_atom_id is not None and self._drag_start_3d is not None:
                self._is_dragging_bond = True
                hover_aid = self.renderer.pick_atom_id_at_qt(lx, ly, w, h)
                if hover_aid is not None and hover_aid != self._press_atom_id:
                    end_pos = self._document.get_atom_3d_pos(hover_aid)
                else:
                    end_pos = self.renderer.unproject_qt_to_world(lx, ly, w, h, ref_point=self._drag_start_3d)
                if end_pos is not None:
                    self._pending_rb_points = (self._drag_start_3d.copy(), end_pos.copy())
                    if not self._live_drag_scheduled:
                        self._live_drag_scheduled = True
                        self._defer(self._flush_live_drag)
                return True

            # 在“选择”模式下按住原子拖动 -> 实时更新单个或全部多选原子的 3D 坐标
            if tool == "选择" and self._press_atom_id is not None and self._drag_start_3d is not None:
                self._is_dragging_atom = True
                if not getattr(self, "_multi_drag_start", None):
                    self._capture_multi_drag_origins()
                self._current_drag_3d = self.renderer.unproject_qt_to_world(
                    lx, ly, w, h, ref_point=self._drag_start_3d
                )
                if not self._live_drag_scheduled:
                    self._live_drag_scheduled = True
                    self._defer(self._flush_live_drag)
                return True

            return True

        # 3. 鼠标释放
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if not self._intercepting_left_mouse:
                self._lod_timer.start()
                return False

            pos = event.position()
            lx, ly = pos.x(), pos.y()
            w, h = inter.width(), inter.height()
            moved_px = math.hypot(lx - self._press_qpos.x(), ly - self._press_qpos.y()) if self._press_qpos else 0.0
            tool = self.renderer.current_tool
            press_aid = self._press_atom_id
            start_3d = self._drag_start_3d.copy() if self._drag_start_3d is not None else None
            was_drag_atom = self._is_dragging_atom
            was_drag_bond = self._is_dragging_bond
            was_box_select = self._is_box_selecting
            box_start = self._box_start_qpos
            box_end = self._box_end_qpos
            lasso_pts = list(getattr(self, "_lasso_points", []))
            keep_multi = getattr(self, "_keep_multi_on_press", False)
            # 关键修复 (P0-1)：必须在 _reset_interaction_state() 清空 _multi_drag_start 之前先拷贝一份！
            saved_multi_origins = {k: v.copy() for k, v in (getattr(self, "_multi_drag_start", None) or {}).items()}

            self._reset_interaction_state()
            self._defer(self.renderer.clear_rubberband)

            # 框选 / 套索完成：投影所有原子到屏幕坐标，选中区域内的原子并立即捕获多选初始坐标！
            if was_box_select and box_start is not None and box_end is not None:
                self._defer(
                    lambda bs=box_start, be=box_end, lp=lasso_pts, ww=w, hh=h: self._finish_box_select(bs, be, ww, hh, lp)
                )
                return True

            # A. 完成 3D 拖原子改坐标 -> 提交 MoveAtomsBatch3DCommand（多选单步 Ctrl+Z 恢复！）或 MoveAtom3DCommand
            if was_drag_atom and press_aid is not None and start_3d is not None:
                final_pos = self.renderer.unproject_qt_to_world(lx, ly, w, h, ref_point=start_3d)
                if self._command_bus is not None:
                    from ..application.builtin_commands import MoveAtom3DCommand, MoveAtomsBatch3DCommand
                    delta = np.asarray(final_pos, dtype=np.float32) - np.asarray(start_3d, dtype=np.float32)
                    if len(saved_multi_origins) > 1 and press_aid in saved_multi_origins:
                        moves = {aid: (orig, orig + delta) for aid, orig in saved_multi_origins.items()}
                        self._defer(lambda mv=moves: (
                            self._command_bus.execute(MoveAtomsBatch3DCommand(mv)),
                            self._capture_multi_drag_origins(),
                        ))
                    else:
                        self._defer(lambda a=press_aid, fp=final_pos, sp=start_3d: (
                            self._command_bus.execute(MoveAtom3DCommand(a, fp, sp)),
                            self._capture_multi_drag_origins(),
                        ))
                return True

            # 若在已多选的原子上仅仅单击（未拖动），则此时才将选择集收敛到该单个原子
            if not was_drag_atom and moved_px < 4.0 and keep_multi and press_aid is not None and self._selection is not None:
                self._defer(lambda a=press_aid: (
                    self._selection.select_atom(a, add=False, origin="3d"),
                    self._capture_multi_drag_origins(),
                ))
                return True

            # B. 完成 3D 橡皮筋拖拽画键 -> 连接到目标原子或在终点新建原子并成键
            if was_drag_bond and press_aid is not None and moved_px >= 5.0:
                target_aid = self.renderer.pick_atom_id_at_qt(lx, ly, w, h)
                if target_aid is not None and target_aid != press_aid:
                    self._defer(lambda a=press_aid, b=target_aid: self._execute_bond_between(a, b))
                elif self._command_bus is not None and start_3d is not None:
                    end_3d = self.renderer.unproject_qt_to_world(lx, ly, w, h, ref_point=start_3d)
                    vec = end_3d - start_3d
                    norm = float(np.linalg.norm(vec))
                    elem = self.renderer.current_element
                    from ..domain.chemistry import estimate_bond_length
                    length = estimate_bond_length(self._document.topology.get_atom(press_aid).atomic_num, elem)
                    placed_3d = (start_3d + (vec / norm) * length) if norm > 0.1 else None
                    from ..application.builtin_commands import AddAtomCommand
                    if placed_3d is not None:
                        self._defer(lambda p=placed_3d, z=elem, pa=press_aid: self._command_bus.execute(
                            AddAtomCommand(z, x=float(p[0]), y=float(p[1]), z=float(p[2]), bond_to=pa, bond_order=1)
                        ))
                    else:
                        self._defer(lambda z=elem, pa=press_aid: self._command_bus.execute(
                            AddAtomCommand(z, bond_to=pa, bond_order=1)
                        ))
                return True

            # C. 原地点击（未拖动）：在“原子”或“键”模式下执行加原子/生长新键
            if moved_px < 5.0 and self._command_bus is not None:
                elem = self.renderer.current_element
                from ..application.builtin_commands import AddAtomCommand
                if tool in ("原子", "键") and press_aid is not None:
                    self._defer(lambda z=elem, pa=press_aid: self._command_bus.execute(
                        AddAtomCommand(z, bond_to=pa, bond_order=1)
                    ))
                elif tool == "原子" and press_aid is None:
                    world_pos = self.renderer.unproject_qt_to_world(lx, ly, w, h)
                    self._defer(lambda wp=world_pos, z=elem: self._command_bus.execute(
                        AddAtomCommand(z, x=float(wp[0]), y=float(wp[1]), z=float(wp[2]), auto_bond_nearest=True)
                    ))

            return True

        return super().eventFilter(obj, event)

    def _cycle_bond_order_safe(self, bid: BondId):
        if self._document is None or bid not in self._document.topology._bonds:
            return
        if self._selection is not None:
            self._selection.select_bond(bid, add=False, origin="3d")
        if self._command_bus is not None:
            bond = self._document.topology.get_bond(bid)
            next_order = (bond.order % 3) + 1
            from ..application.builtin_commands import ChangeBondOrderCommand
            self._command_bus.execute(ChangeBondOrderCommand(bid, next_order))

    def _execute_bond_between(self, atom_a: AtomId, atom_b: AtomId):
        if self._command_bus is None or self._document is None:
            return
        from ..application.builtin_commands import AddBondCommand, ChangeBondOrderCommand
        existing = self._document.topology.bond_between(atom_a, atom_b)
        if existing is not None:
            cur_order = self._document.topology.get_bond(existing).order
            next_order = (cur_order % 3) + 1
            self._command_bus.execute(ChangeBondOrderCommand(existing, next_order))
        else:
            self._command_bus.execute(AddBondCommand(atom_a, atom_b, order=1))

    def _finish_box_select(self, box_start, box_end, widget_w: int, widget_h: int, lasso_pts: list | None = None):
        """框选或套索选择完成：投影所有原子到屏幕坐标，选中区域内的原子并立即捕获多选平移起点！"""
        if self._document is None or self._selection is None:
            return
        coords = self.renderer._coordinates
        atom_ids = self.renderer._atom_ids
        if coords is None or atom_ids is None or len(atom_ids) == 0:
            return

        sx, sy, _, _ = self.renderer._project_points_to_qt_numpy(coords, widget_w, widget_h)
        sy_qt = sy

        mode = getattr(self, "_select_region_mode", "box")
        if mode == "lasso" and lasso_pts and len(lasso_pts) >= 3:
            poly = [(p.x(), p.y()) for p in lasso_pts]
            inside = _points_in_polygon_numpy(sx, sy_qt, poly)
        else:
            x1, x2 = sorted([box_start.x(), box_end.x()])
            y1, y2 = sorted([box_start.y(), box_end.y()])
            if (x2 - x1) < 5 and (y2 - y1) < 5:
                return
            inside = (sx >= x1) & (sx <= x2) & (sy_qt >= y1) & (sy_qt <= y2)

        selected = [atom_ids[i] for i in range(len(atom_ids)) if inside[i]]

        if selected:
            # 批量选择：只发一次通知、只重建一次高亮，避免逐原子 select 造成 O(N²) 重复更新与卡顿
            self._selection.select_atoms_ordered(selected, origin="3d")
            # 关键修复 (P0-1)：框选/套索完成后立即收集所有选中原子的初始 3D 坐标！
            self._capture_multi_drag_origins()
            if self.status_callback is not None:
                self.status_callback(f"已选中 {len(selected)} 个原子 — 按住任意选中原子拖动即可同步平移全体 (Ctrl+Z 一键撤销)")
        else:
            self._selection.clear(origin="3d")
            self._multi_drag_start = {}

    def _show_context_menu(self, hit_aid: AtomId | None, hit_bid: BondId | None, qx: int, qy: int):
        """
        P0-3 对标 GaussView 6.0 的完整 3D 右键上下文菜单：
          - 对原子右键：删原子、改元素类型、改原子颜色、改原子大小、改形式电荷、两原子间建键、复制该原子坐标、查看原子详情
          - 对键右键：删键、切换键级(单/双/三/芳香)、精确改键长(Å)、改键颜色、改键粗细、查看键长/键角详情
          - 对空白右键：粘贴分子(追加)、导出 SMILES 到剪贴板、新建空白画布、导入文件、切换框选/套索、显隐氢/标签/元素符号/坐标轴、切换 2D/3D 视图
        """
        if self._document is None:
            return
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background:#132030; color:#EAF2F6; border:1px solid #2F4F6F; padding:5px; font-size:12px; }"
            "QMenu::item { padding:6px 22px; border-radius:4px; }"
            "QMenu::item:selected { background:#0D9488; color:#FFFFFF; font-weight:600; }"
            "QMenu::separator { height:1px; background:#23394F; margin:4px 6px; }"
        )

        # 若右键点中了某个尚未选中的原子/键，则选中它；若点中的原子已在多选集合中则保留多选
        if self._selection is not None:
            if hit_aid is not None and hit_aid not in self._selection.selected_atoms:
                self._selection.select_atom(hit_aid, add=False, origin="3d")
                self._capture_multi_drag_origins()
            elif hit_bid is not None and hit_bid not in self._selection.selected_bonds:
                self._selection.select_bond(hit_bid, add=False, origin="3d")

        sel_atoms = list(self._selection.selected_atoms) if self._selection else []
        sel_bonds = list(self._selection.selected_bonds) if self._selection else []
        win = self.window()

        # ==================== 1. 原子专属右键菜单 ====================
        if hit_aid is not None or (len(sel_atoms) > 0 and hit_bid is None):
            target_aid = hit_aid or sel_atoms[0]
            n_atoms = len(sel_atoms)
            act_del = menu.addAction(f"🗑️ 删除选中原子 ({n_atoms} 个) [Del]")
            act_del.triggered.connect(self._delete_selected_atoms)

            elem_menu = menu.addMenu("🧪 修改元素类型 (Element)...")
            for z_val, sym_lbl in (
                (6, "C · 碳 (Z=6)"), (7, "N · 氮 (Z=7)"), (8, "O · 氧 (Z=8)"),
                (16, "S · 硫 (Z=16)"), (9, "F · 氟 (Z=9)"), (17, "Cl · 氯 (Z=17)"),
                (35, "Br · 溴 (Z=35)"), (15, "P · 磷 (Z=15)"), (14, "Si · 硅 (Z=14)"),
                (34, "Se · 硒 (Z=34)"), (1, "H · 氢 (Z=1)"),
            ):
                act_el = elem_menu.addAction(sym_lbl)
                act_el.triggered.connect(lambda _=False, z=z_val: self._change_selected_atoms_element(z))
            elem_menu.addSeparator()
            act_pt = elem_menu.addAction("📅 打开 118 元素周期表...")
            act_pt.triggered.connect(lambda: self._pick_context_element())

            scale_menu = menu.addMenu("📏 修改选中原子大小 (Radius Scale)...")
            for sc_val, sc_lbl in ((0.5, "50% (小)"), (0.8, "80%"), (1.0, "100% (标准)"), (1.3, "130%"), (1.6, "160%"), (2.0, "200% (大球)")):
                act_sc = scale_menu.addAction(sc_lbl)
                act_sc.triggered.connect(lambda _=False, s=sc_val: self._set_selected_atoms_scale_menu(s))

            chg_menu = menu.addMenu("⚡ 修改形式电荷 (Formal Charge)...")
            for q_val in (-2, -1, 0, +1, +2):
                q_lbl = f"{q_val:+d}" if q_val != 0 else "0 (中性)"
                act_q = chg_menu.addAction(q_lbl)
                act_q.triggered.connect(lambda _=False, q=q_val: self._set_selected_atoms_charge_menu(q))

            act_color = menu.addAction("🎨 修改选中原子颜色...")
            act_color.triggered.connect(self._pick_selected_atom_color)
            act_reset_color = menu.addAction("↺ 恢复默认 CPK 元素色")
            act_reset_color.triggered.connect(self._reset_selected_atom_color)

            if len(sel_atoms) == 2:
                a, b = sel_atoms[0], sel_atoms[1]
                existing = self._document.topology.bond_between(a, b)
                label = "🔗 在两选中原子间建键" if existing is None else "🔗 切换两原子间键级"
                act_bond = menu.addAction(label)
                act_bond.triggered.connect(lambda _=False, aa=a, bb=b: self._execute_bond_between(aa, bb))

            menu.addSeparator()
            act_copy_atom = menu.addAction("📋 复制选中原子 XYZ 坐标 (Ctrl+C)")
            act_copy_atom.triggered.connect(self._copy_selection_xyz)
            act_detail_a = menu.addAction("ℹ️ 查看原子详细属性...")
            act_detail_a.triggered.connect(lambda _=False, a=target_aid: self._show_atom_details_dialog(a))
            menu.addSeparator()

        # ==================== 2. 化学键专属右键菜单 ====================
        elif hit_bid is not None or len(sel_bonds) > 0:
            target_bid = hit_bid or sel_bonds[0]
            n_bonds = len(sel_bonds)
            act_del_b = menu.addAction(f"🗑️ 删除选中化学键 ({n_bonds} 条) [Del]")
            act_del_b.triggered.connect(self._delete_selected_bonds)

            bo_menu = menu.addMenu("🔀 切换化学键级 (Bond Order)...")
            for bo_val, bo_lbl in ((1, "单键 (Single, 1)"), (2, "双键 (Double, 2)"), (3, "三键 (Triple, 3)")):
                act_bo = bo_menu.addAction(bo_lbl)
                act_bo.triggered.connect(lambda _=False, b=target_bid, o=bo_val: self._set_bond_order_menu(b, o))
            act_cycle = menu.addAction("🔄 循环切换键级 (单→双→三)")
            act_cycle.triggered.connect(lambda _=False, b=target_bid: self._cycle_bond_order_safe(b))

            act_len = menu.addAction("📐 精确修改键长 (Å)...")
            act_len.triggered.connect(lambda _=False, b=target_bid: self._prompt_modify_bond_length_inline(b))

            bw_menu = menu.addMenu("📏 修改选中键粗细 (Width Scale)...")
            for bw_val, bw_lbl in ((0.6, "60% (细)"), (1.0, "100% (标准)"), (1.4, "140%"), (1.8, "180%"), (2.2, "220% (粗)")):
                act_bw = bw_menu.addAction(bw_lbl)
                act_bw.triggered.connect(lambda _=False, w_s=bw_val: self._set_selected_bonds_width_menu(w_s))

            act_bcolor = menu.addAction("🎨 修改选中键颜色...")
            act_bcolor.triggered.connect(self._pick_selected_bond_color)
            act_breset = menu.addAction("↺ 恢复默认双色半键渲染")
            act_breset.triggered.connect(self._reset_selected_bond_color)

            menu.addSeparator()
            act_detail_b = menu.addAction("ℹ️ 查看键长与相邻键角详情...")
            act_detail_b.triggered.connect(lambda _=False, b=target_bid: self._show_bond_details_dialog(b))
            menu.addSeparator()

        # ==================== 3. 空白处 / 画布通用右键菜单 ====================
        act_paste = menu.addAction("📥 粘贴分子到当前画布 (追加 Ctrl+V)")
        act_paste.triggered.connect(self._paste_from_clipboard)

        act_copy_smi = menu.addAction("🧬 导出当前分子 SMILES 到剪贴板")
        act_copy_smi.triggered.connect(self._copy_smiles_to_clipboard)

        act_copy = menu.addAction("📋 复制选中/全部 XYZ 坐标 (Ctrl+C)")
        act_copy.triggered.connect(self._copy_selection_xyz)

        menu.addSeparator()
        sel_mode_menu = menu.addMenu("⬚ 切换 Shift+拖拽选择方式...")
        act_box_m = sel_mode_menu.addAction("⬚ 矩形框选 (Box Select)")
        act_box_m.setCheckable(True)
        act_box_m.setChecked(getattr(self, "_select_region_mode", "box") == "box")
        act_box_m.triggered.connect(lambda: self.region_mode_btn.setChecked(False) or self._toggle_select_region_mode(False))
        act_lasso_m = sel_mode_menu.addAction("➰ 自由套索选择 (Lasso Select)")
        act_lasso_m.setCheckable(True)
        act_lasso_m.setChecked(getattr(self, "_select_region_mode", "box") == "lasso")
        act_lasso_m.triggered.connect(lambda: self.region_mode_btn.setChecked(True) or self._toggle_select_region_mode(True))

        view_sub = menu.addMenu("👁️ 3D 视图显示与画布控制...")
        act_vh = view_sub.addAction(f"{'✓ ' if self.renderer.show_hydrogens else ''}显示/隐藏氢原子 (Hydrogens)")
        act_vh.triggered.connect(lambda: self.set_view_options(show_hydrogens=not self.renderer.show_hydrogens))
        act_vl = view_sub.addAction(f"{'✓ ' if self.renderer.show_labels else ''}显示/隐藏原子序号 (#1, #2...)")
        act_vl.triggered.connect(lambda: self.set_view_options(show_labels=not self.renderer.show_labels))
        act_vs = view_sub.addAction(f"{'✓ ' if self.renderer.show_symbols else ''}显示/隐藏元素符号 (C, N, O...)")
        act_vs.triggered.connect(lambda: self.set_view_options(show_symbols=not self.renderer.show_symbols))
        act_va = view_sub.addAction(f"{'✓ ' if self.renderer.show_axes else ''}显示/隐藏 XYZ 角落坐标轴")
        act_va.triggered.connect(lambda: self.set_view_options(show_axes=not self.renderer.show_axes))
        label_scope = view_sub.addMenu("编号范围")
        for key, title in (("heavy","重原子与选中原子"),("all","全部可见原子（默认）"),("selected","仅选中原子")):
            action = label_scope.addAction(title)
            action.setCheckable(True); action.setChecked(self.renderer.label_scope == key)
            action.triggered.connect(lambda _=False, k=key: (setattr(self.renderer,"label_scope",k),self._refresh_atom_labels()))
        view_sub.addSeparator()
        act_v23 = view_sub.addAction("🔀 切换 2D / 3D / 双视图分屏")
        act_v23.triggered.connect(self._cycle_workspace_view_mode)

        menu.addSeparator()
        act_new_blank = menu.addAction("📄 新建空白分子画布 (Ctrl+Shift+N)")
        act_new_blank.triggered.connect(lambda: getattr(win, "_on_new_blank", lambda: None)())
        act_open_f = menu.addAction("📂 导入分子文件 (Ctrl+O)...")
        act_open_f.triggered.connect(lambda: getattr(win, "_on_open_file", lambda: None)())
        act_clear = menu.addAction("清空当前选择")
        act_clear.triggered.connect(lambda: self._selection.clear(origin="3d") if self._selection else None)

        from .modeling_actions import add_modeling_actions
        add_modeling_actions(self, menu, hit_aid, hit_bid)
        menu.exec(QCursor.pos())

    def _pick_context_element(self):
        from .element_picker import ElementPickerDialog
        dialog = ElementPickerDialog(self, compact=True)
        if dialog.exec() and dialog.selected_element:
            self._change_selected_atoms_element(dialog.selected_element.atomic_number)

    def export_scene_png(self, path=None):
        from pathlib import Path
        from ..runtime import data_dir
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import QRect
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self,"导出3D画面",str(data_dir()/"molecule.png"),"PNG (*.png)")
        if not path:
            return False
        destination=Path(path).resolve()
        if destination.drive.upper() not in ("D:","E:"):
            raise ValueError("图像必须保存到D/E盘")
        self._refresh_atom_labels()
        self.plotter.render()
        pixels=np.ascontiguousarray(self.plotter.screenshot(return_img=True))
        h,w,channels=pixels.shape
        fmt=QImage.Format.Format_RGBA8888 if channels==4 else QImage.Format.Format_RGB888
        output=QImage(pixels.data,w,h,pixels.strides[0],fmt).copy()
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not output.save(str(destination),"PNG"):
            raise OSError("图像保存失败")
        return True

    def _copy_selection_xyz(self):
        """把选中原子的 XYZ 坐标复制到剪贴板。"""
        if self._document is None or self._selection is None:
            return
        from PyQt6.QtGui import QGuiApplication
        atoms = list(self._selection.selected_atoms)
        if not atoms:
            atoms = list(self._document.topology.atom_ids)
        lines = []
        for aid in atoms:
            pos = self._document.get_atom_3d_pos(aid)
            if pos is not None:
                z = self._document.topology.get_atom(aid).atomic_num
                from ..domain.elements import get_element
                elem = get_element(z)
                sym = elem.symbol if elem else "C"
                lines.append(f"{sym} {pos[0]:.6f} {pos[1]:.6f} {pos[2]:.6f}")
        txt = f"{len(lines)}\nPasted from MolForge\n" + "\n".join(lines)
        QGuiApplication.clipboard().setText(txt)

    def _paste_from_clipboard(self):
        """委托给主窗口的粘贴逻辑。"""
        win = self.window()
        if hasattr(win, "_on_paste_molecule"):
            win._on_paste_molecule()

    def _change_selected_atoms_element(self, atomic_num: int):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeElementCommand
        for aid in list(self._selection.selected_atoms):
            self._command_bus.execute(ChangeElementCommand(aid, int(atomic_num)))

    def _set_selected_atoms_scale_menu(self, scale: float):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeAtomStyleCommand
        atoms = list(self._selection.selected_atoms)
        if atoms:
            self._command_bus.execute(ChangeAtomStyleCommand(atoms, scale=float(scale)))
            for aid in atoms:
                self.update_single_atom_style(aid, scale=float(scale))

    def _set_selected_atoms_charge_menu(self, charge: int):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeAtomStyleCommand
        atoms = list(self._selection.selected_atoms)
        if atoms:
            self._command_bus.execute(ChangeAtomStyleCommand(atoms, formal_charge=int(charge)))

    def _reset_selected_atom_color(self):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeAtomStyleCommand
        atoms = list(self._selection.selected_atoms)
        if atoms:
            self._command_bus.execute(ChangeAtomStyleCommand(atoms, clear_color=True))
            for aid in atoms:
                self.update_single_atom_style(aid, color=None)

    def _set_bond_order_menu(self, bid: BondId, order: int):
        if self._command_bus is None:
            return
        from ..application.builtin_commands import ChangeBondOrderCommand
        self._command_bus.execute(ChangeBondOrderCommand(bid, int(order)))

    def _set_selected_bonds_width_menu(self, width_scale: float):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeBondStyleCommand
        bonds = list(self._selection.selected_bonds)
        if bonds:
            self._command_bus.execute(ChangeBondStyleCommand(bonds, width_scale=float(width_scale)))
            for bid in bonds:
                self.update_single_bond_style(bid, width_scale=float(width_scale))

    def _reset_selected_bond_color(self):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.builtin_commands import ChangeBondStyleCommand
        bonds = list(self._selection.selected_bonds)
        if bonds:
            self._command_bus.execute(ChangeBondStyleCommand(bonds, clear_color=True))
            for bid in bonds:
                self.update_single_bond_style(bid, color=None)

    def _prompt_modify_bond_length_inline(self, bid: BondId):
        if self._document is None or self._command_bus is None or bid not in self._document.topology._bonds:
            return
        from PyQt6.QtWidgets import QInputDialog
        bond = self._document.topology.get_bond(bid)
        p1 = self._document.get_atom_3d_pos(bond.begin)
        p2 = self._document.get_atom_3d_pos(bond.end)
        cur_d = float(np.linalg.norm(p2 - p1)) if (p1 is not None and p2 is not None) else 1.45
        val, ok = QInputDialog.getDouble(
            self, "精确修改化学键长 (Modify Bond Length)",
            f"键 #{bid.value} ({bond.begin.value}-{bond.end.value}) 当前键长 {cur_d:.3f} Å，请输入新键长 (Å):",
            cur_d, 0.45, 4.50, 3
        )
        if ok:
            from ..application.builtin_commands import ModifyBondLength3DCommand
            self._command_bus.execute(ModifyBondLength3DCommand(bid, float(val)))

    def _show_atom_details_dialog(self, aid: AtomId):
        if self._document is None or aid not in self._document.topology._atoms:
            return
        from PyQt6.QtWidgets import QMessageBox
        atom = self._document.topology.get_atom(aid)
        el = get_element(atom.atomic_num)
        pos = self._document.get_atom_3d_pos(aid)
        nbrs = self._document.topology.neighbors_of(aid)
        deg = len(nbrs)
        hyb = "sp³" if deg >= 4 else ("sp²" if (atom.aromatic or deg == 3) else ("sp" if deg == 2 else "端基/单配位"))
        pos_str = f"({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f}) Å" if pos is not None else "无"
        QMessageBox.information(
            self,
            f"原子详情 #{aid.value}",
            f"<b>原子 ID</b>: #{aid.value}<br>"
            f"<b>元素符号</b>: {el.symbol if el else 'C'} ({el.name_cn if el else ''}, Z={atom.atomic_num})<br>"
            f"<b>3D 笛卡尔坐标</b>: {pos_str}<br>"
            f"<b>形式电荷</b>: {atom.formal_charge:+d}<br>"
            f"<b>配位数 / 估计杂化</b>: {deg} 配位 ({hyb})<br>"
            f"<b>独立半径缩放</b>: {getattr(atom, 'scale', 1.0):.2f}x",
        )

    def _show_bond_details_dialog(self, bid: BondId):
        if self._document is None or bid not in self._document.topology._bonds:
            return
        from PyQt6.QtWidgets import QMessageBox
        bond = self._document.topology.get_bond(bid)
        p1 = self._document.get_atom_3d_pos(bond.begin)
        p2 = self._document.get_atom_3d_pos(bond.end)
        d = float(np.linalg.norm(p2 - p1)) if (p1 is not None and p2 is not None) else 0.0
        QMessageBox.information(
            self,
            f"化学键详情 #{bid.value}",
            f"<b>化学键 ID</b>: #{bid.value}<br>"
            f"<b>连接原子</b>: #{bond.begin.value} — #{bond.end.value}<br>"
            f"<b>键级 (Bond Order)</b>: {bond.order} {'(芳香共轭)' if bond.aromatic else ''}<br>"
            f"<b>当前 3D 键长</b>: {d:.4f} Å<br>"
            f"<b>独立粗细缩放</b>: {getattr(bond, 'width_scale', 1.0):.2f}x",
        )

    def _copy_smiles_to_clipboard(self):
        win = self.window()
        if hasattr(win, "_export_smiles_string"):
            from PyQt6.QtGui import QGuiApplication
            smi = win._export_smiles_string()
            QGuiApplication.clipboard().setText(smi)
            if self.status_callback:
                self.status_callback(f"已导出当前分子 SMILES 到剪贴板: {smi}")

    def _cycle_workspace_view_mode(self):
        win = self.window()
        if hasattr(win, "workspace"):
            ws = win.workspace
            cur = 2
            for idx, b in enumerate(getattr(ws, "view_mode_buttons", [])):
                if b.isChecked():
                    cur = idx
            ws.set_mode((cur + 1) % 3)

    def _delete_selected_atoms(self):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.selection_commands import DeleteSelectionCommand
        self._command_bus.execute(DeleteSelectionCommand(self._selection.selected_atoms, self._selection.selected_bonds))
        self._selection.clear(origin="3d")

    def _delete_selected_bonds(self):
        if self._command_bus is None or self._selection is None:
            return
        from ..application.selection_commands import DeleteSelectionCommand
        self._command_bus.execute(DeleteSelectionCommand(bond_ids=self._selection.selected_bonds))
        self._selection.clear(origin="3d")

    def _pick_selected_atom_color(self):
        if self._command_bus is None or self._selection is None:
            return
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(parent=self, title="选择选中原子颜色")
        if not c.isValid():
            return
        color = (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)
        from ..application.builtin_commands import ChangeAtomStyleCommand
        atoms = list(self._selection.selected_atoms)
        self._command_bus.execute(ChangeAtomStyleCommand(atoms, color=color))

    def _pick_selected_bond_color(self):
        if self._command_bus is None or self._selection is None:
            return
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(parent=self, title="选择选中键颜色")
        if not c.isValid():
            return
        color = (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)
        from ..application.builtin_commands import ChangeBondStyleCommand
        bonds = list(self._selection.selected_bonds)
        self._command_bus.execute(ChangeBondStyleCommand(bonds, color=color))

    def _open_modify_bond_length(self):
        """委托给主窗口的修改键长对话框。"""
        win = self.window()
        if hasattr(win, "_on_open_modify_bond_length"):
            win._on_open_modify_bond_length()
        elif hasattr(win, "workspace") and hasattr(win.workspace, "window"):
            parent = win.workspace.window()
            if hasattr(parent, "_on_open_modify_bond_length"):
                parent._on_open_modify_bond_length()

    def _reset_interaction_state(self):
        self._press_qpos = None
        self._press_atom_id = None
        self._press_bond_id = None
        self._drag_start_3d = None
        self._current_drag_3d = None
        self._is_dragging_atom = False
        self._is_dragging_bond = False
        self._intercepting_left_mouse = False
        self._pending_rb_points = None
        self._multi_drag_start: dict = {}
        self._is_box_selecting = False
        self._box_start_qpos = None
        self._box_end_qpos = None
        if hasattr(self, "_box_overlay"):
            self._box_overlay.hide()

    def _capture_multi_drag_origins(self):
        """选中变化后，记录所有选中原子的初始 3D 坐标，供多选平移使用。"""
        if self._selection is None or self._document is None or not self._document.has_3d:
            self._multi_drag_start = {}
            return
        self._multi_drag_start = {}
        for aid in self._selection.selected_atoms:
            pos = self._document.get_atom_3d_pos(aid)
            if pos is not None and not self._document.topology.get_atom(aid).properties.get("frozen"):
                self._multi_drag_start[aid] = np.asarray(pos, dtype=np.float32).copy()

    # ---------- 选择同步与键盘快捷键 ----------

    def set_selection_service(self, selection):
        if getattr(self, "_selection", None) is selection and getattr(self, "_selection_callback", None) is not None:
            return
        previous = getattr(self, "_selection", None)
        callback = getattr(self, "_selection_callback", None)
        if previous is not None and callback is not None:
            previous.remove_listener(callback)
        self._selection = selection
        self._selection_callback = lambda origin: QTimer.singleShot(0, self._do_apply_external_selection)
        selection.add_listener(self._selection_callback)
        self.destroyed.connect(lambda _=None, service=selection, cb=self._selection_callback: service.remove_listener(cb))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._defer(self.on_delete_selected_3d or self._delete_selected_atoms)
            return
        super().keyPressEvent(event)

    def _do_apply_external_selection(self):
        if self._selection is None:
            return
        try:
            measure_chain = None
            if self._document is not None and not self._selection.is_empty:
                from ..application.measurement_targets import MeasurementTargetResolver
                target = MeasurementTargetResolver.resolve(self._document, self._selection)
                if (
                    len(self._selection.selected_atoms) in (2, 3, 4)
                    or (len(self._selection.selected_bonds) == 2 and not self._selection.selected_atoms)
                ):
                    if target.kind in ('distance', 'angle', 'dihedral', 'ambiguous') and target.atoms:
                        measure_chain = list(target.atoms)
            self.renderer.set_selection(
                self._selection.selected_atoms,
                self._selection.selected_bonds,
                measure_chain=measure_chain,
            )
        except Exception as e:
            print("3D highlight error:", e)

    def set_mode(self, mode: RepresentationMode):
        self.renderer.set_mode(mode)
        self._update_hud_text()
        self.hud_info_label.setToolTip(
            "CPK：参考范德华半径 × 全局/单原子显示缩放；球棍：半径再乘0.25。"
            "默认缩放1时CPK半径与Å坐标同尺度。键长来自坐标，键管粗细仅用于显示。"
        )

    def set_material_preset(self, name: str):
        self.renderer.set_material_preset(name)

    def set_roughness(self, value: float):
        self.renderer.set_roughness(value)

    def set_metallic(self, value: float):
        self.renderer.set_metallic(value)

    def reset_camera(self):
        self.renderer.reset_camera()

    def set_view_direction(self, direction: str):
        """设置固定视图方向：front/side/top/iso。"""
        self.renderer.set_view_direction(direction)

    def set_atom_scale(self, scale: float):
        self.renderer.set_atom_scale(scale)

    def set_bond_scale(self, scale: float):
        self.renderer.set_bond_scale(scale)

    def set_background_color(self, r: float, g: float, b: float):
        self.renderer.set_background_color(r, g, b)

    def load_orbital_cube(self, path: str, isovalue: float = 0.05):
        from molforge.io.cube_reader import read_cube
        cube = read_cube(path)
        self.renderer.set_orbital(cube, isovalue=isovalue)
        return cube

    def clear_orbital(self):
        self.renderer.clear_orbital()

    def show_bio_points(self, bio):
        from molforge.domain.elements import get_element
        self._bio_actors = []
        for m in bio.models:
            coords, colors = [], []
            for c in m.chains:
                for r in c.residues:
                    for a in r.atoms:
                        coords.append(a.coord)
                        z = {"H": 1, "C": 6, "N": 7, "O": 8, "S": 16,
                             "P": 15, "FE": 26}.get(a.element.upper(), 6)
                        colors.append(get_element(z).cpk_color)
            coords = np.array(coords)
            if QtInteractor is not None:
                act = self.plotter.add_points(
                    coords, scalars=np.array(colors), rgb=True,
                    render_points_as_spheres=True, point_size=11)
                self._bio_actors.append(act)
        if QtInteractor is not None:
            self.plotter.reset_camera()

    def clear_bio_points(self):
        if hasattr(self, "_bio_actors") and QtInteractor is not None:
            for a in self._bio_actors:
                a.VisibilityOff()
            self._bio_actors = []

    def update_single_atom_style(self, atom_id: AtomId, scale: float | None = None, color: tuple | None = "__keep__"):
        if scale is not None:
            self.renderer.set_single_atom_scale(atom_id, scale)
        if color != "__keep__":
            self.renderer.set_single_atom_color(atom_id, color)

    def update_single_bond_style(self, bond_id: BondId, width_scale: float | None = None, color: tuple | None = "__keep__"):
        if bond_id in self._bond_ids:
            b_idx = self._bond_ids.index(bond_id)
            if width_scale is not None:
                self.renderer.set_single_bond_scale(b_idx, width_scale)
            if color != "__keep__":
                self.renderer.set_single_bond_color(b_idx, color)

    def set_color_scheme(self, scheme_name: str):
        self.renderer.set_color_scheme(scheme_name)

    def set_view_options(self, **kwargs):
        self.renderer.set_view_options(**kwargs)
        self.lbl_toggle_btn.blockSignals(True)
        self.lbl_toggle_btn.setChecked(self.renderer.show_labels)
        self.lbl_toggle_btn.blockSignals(False)
    def set_header_visible(self, visible: bool) -> None:
        if hasattr(self, "_header_frame") and self._header_frame is not None:
            self._header_frame.setVisible(visible)

    def set_multiview_layout(self, pane_count: int = 1) -> list:
        """
        在当前 Render3DWidget 的同一个 vtkRenderWindow 内切换 1 / 2 / 4 视口 (P1..P4)，
        直接对接 self.plotter 与 self.renderer（修复 viewer/backend 属性名不匹配问题）。
        """
        from .vtk_multiview_widget import apply_multiview_to_render_window
        self.pane_count = int(pane_count) if pane_count in (1, 2, 4) else 1
        self.renderer._ensure_scene_initialized()
        rw = (
            getattr(self.plotter, "ren_win", None)
            or getattr(self.plotter, "render_window", None)
            or (self.plotter.interactor.GetRenderWindow() if hasattr(self.plotter, "interactor") else None)
        )
        ren = getattr(self.plotter, "renderer", None)
        shared = [
            getattr(self.renderer, "_atom_actor", None),
            getattr(self.renderer, "_bond_actor", None),
            getattr(self.renderer, "_highlight_actor", None),
            getattr(self.renderer, "_hl_bond_actor", None),
            getattr(self.renderer, "_surface_actor", None),
            *(layer[3] for layer in self.renderer._glow_layers),
        ]
        aux = apply_multiview_to_render_window(rw, ren, self.pane_count, shared_actors=shared)  # type: ignore[arg-type]
        self.renderer._aux_renderers = aux
        if self.renderer._native_labels is not None:
            self.renderer._native_labels.set_views([ren]+aux)
            self.renderer.render()
        return aux

