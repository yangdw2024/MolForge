"""
ui/editor2d_widget.py - 零偏差坐标映射的 ChemDraw 级 2D 分子编辑器
====================================================================
核心修复（彻底解决 Issue 8/9/10/11）：
  1. 严格区分「分子 2D 世界坐标 (Å, 原点 0,0, C-C 键长 1.50 Å)」与「屏幕像素坐标 (px)」：
     - `world_to_screen(wx, wy)` 与 `screen_to_world(sx, sy)` 互为严格代数逆变换
     - 窗口缩放或 Splitter 调整大小时，绝不污染 `doc.coords_2d`，鼠标点哪里原子就精确落在哪里！
  2. 顺滑拖拽与精准画键：
     - 选择模式下按住原子拖动：实时更新 `doc.coords_2d[aid]`，释放时同步提交 `MoveAtom3DCommand`
     - 键/原子模式下从原子 A 拖向原子 B：目标原子显示磁吸高亮圈，释放即准确建键；拖向空白则在释放点新建原子并连键
     - 在选择模式下双击空白处也可直接快速添加原子
  3. 键盘快捷键状态同步信号：
     - 按 V/B/A/E 或 C/N/O/S/F/P/I/H 时发射 `tool_changed_signal` 与 `element_changed_signal`，主工具栏与 3D 视口同步切换！
"""
from __future__ import annotations
from .scrolling import HorizontalWheelScrollArea

import math
import numpy as np
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QMouseEvent, QWheelEvent, QFont, QFontMetricsF
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QMenu, QMessageBox
)

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId
from ..domain.elements import get_element
from ..io.rdkit_adapter import doc_to_rdkit

STANDARD_VALENCE: dict[int, int] = {
    1: 1, 5: 3, 6: 4, 7: 3, 8: 2, 9: 1, 14: 4, 15: 3, 16: 2, 17: 1, 35: 1, 53: 1
}
SUBSCRIPT_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-6:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / l2
    t = max(0.18, min(0.82, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


class Editor2DWidget(QWidget):
    """
    ChemDraw 级可交互 2D 分子编辑器（世界坐标 Å <-> 屏幕像素精确双射）。
    """

    atom_clicked = pyqtSignal(AtomId)
    atom_double_clicked = pyqtSignal(AtomId)
    tool_changed_signal = pyqtSignal(str)
    element_changed_signal = pyqtSignal(int)

    HEADER_HEIGHT = 36.0
    BASE_PX_PER_ANGSTROM = 36.0  # 1 Å = 36 px (1.5 Å 标准化学键 = 54 px)

    COLORS_PAPER = {
        "bg": "#F4F3EE",
        "grid": "#E2DFD7",
        "bond": "#1F2D3A",
        "text_c": "#1F2D3A",
        1:  (90, 105, 120),
        6:  (31, 45, 58),
        7:  (32, 96, 216),
        8:  (218, 42, 46),
        9:  (24, 152, 82),
        15: (212, 108, 16),
        16: (196, 142, 12),
        17: (24, 152, 82),
        35: (156, 48, 32),
        53: (128, 36, 156),
    }

    COLORS_DARK = {
        "bg": "#0C1622",
        "grid": "#192A3C",
        "bond": "#D4E1EC",
        "text_c": "#EAF2F6",
        1:  (200, 212, 224),
        6:  (212, 225, 236),
        7:  (90, 162, 255),
        8:  (255, 98, 102),
        9:  (92, 224, 146),
        15: (255, 168, 76),
        16: (248, 208, 88),
        17: (82, 218, 138),
        35: (224, 112, 92),
        53: (192, 112, 232),
    }

    def __init__(self, parent=None, chromeless: bool = False):
        super().__init__(parent)
        self._chromeless = bool(chromeless)
        if self._chromeless:
            self.HEADER_HEIGHT = 0.0
        self._document: MoleculeDocument | None = None
        self._selection = None
        self._command_bus = None
        self._current_element = 6
        self._current_tool = "选择"
        self._last_doc_id: str | None = None

        self._paper_mode: bool = True
        self._hide_explicit_hydrogens: bool = True
        # 原子编号开关：开启后在每个可见原子旁显示基于稳定 AtomId 的唯一编号（与 3D 视图一致）
        self._show_atom_numbers: bool = False

        # 视图相机变换参数：s = center + pan + w * (BASE_PX_PER_ANGSTROM * zoom)
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0

        # 交互状态
        self._drag_atom: AtomId | None = None
        self._drag_start_wpos: tuple[float, float] | None = None
        self._bond_start: AtomId | None = None
        self._dragging_bond: bool = False
        self._hover_atom: AtomId | None = None
        self._hover_bond: BondId | None = None
        self._press_pos = QPointF()
        self._mouse_pos = QPointF()
        self._panning: bool = False
        self._pan_start = QPointF()
        self._pending_ring: tuple[int, bool, dict[int, int] | None] | None = None
        self._marquee_start: QPointF | None = None
        self._marquee_rect: QRectF | None = None
        # 批量拖动多个选中的原子
        self._batch_dragging: bool = False
        self._batch_drag_start_screen: QPointF | None = None
        self._batch_drag_start_world: dict = {}

        # 性能缓存：环成员（静态拓扑属性，只在拓扑变化时重算）与网格预渲染
        self._ring_cache_key: tuple | None = None
        self._ring_atom_lists: list[list[AtomId]] = []
        self._bond_rings: dict[BondId, list[int]] = {}
        self._grid_pixmap = None
        self._grid_cache_key: tuple | None = None
        # 复用画笔/颜色/字体，避免每帧成百上千次对象构造
        self._pen_cache: dict = {}
        self._color_cache: dict = {}
        self._label_font = None

        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)

        self._build_header_overlay()
        self._apply_canvas_palette()

    def _build_header_overlay(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("Canvas2DHeader")
        header.setMinimumHeight(36)
        header.setStyleSheet(
            "QFrame#Canvas2DHeader { background-color: #0E1926; border-bottom: 1px solid #1E3246; }"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 3, 10, 3)
        h_lay.setSpacing(6)

        title = QLabel("2D 画布")
        title.setStyleSheet(
            "color: #66DEC9; background: #132A38; border: 1px solid #265264; "
            "border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700;"
        )
        h_lay.addWidget(title)

        self.tool_hint_label = QLabel("[选择] · 元素 C")
        self.tool_hint_label.setMinimumWidth(40)
        self.tool_hint_label.setStyleSheet("color: #EAF2F6; font-size: 12px; font-weight: 600; background: transparent;")
        h_lay.addWidget(self.tool_hint_label, 1)

        self.btn_toggle_h = QPushButton("隐式氢")
        self.btn_toggle_h.setCheckable(True)
        self.btn_toggle_h.setChecked(True)
        self.btn_toggle_h.setMinimumWidth(62)
        self.btn_toggle_h.setToolTip("切换：ChemDraw 骨架隐式氢 / 显示全部显式 H")
        self.btn_toggle_h.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 8px; font-size:12px; font-weight:600; }"
            "QPushButton:checked { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; font-weight:800; }"
        )
        self.btn_toggle_h.clicked.connect(self._toggle_explicit_h)
        h_lay.addWidget(self.btn_toggle_h)

        self.btn_toggle_num = QPushButton("原子编号")
        self.btn_toggle_num.setCheckable(True)
        self.btn_toggle_num.setChecked(False)
        self.btn_toggle_num.setMinimumWidth(72)
        self.btn_toggle_num.setToolTip("显示/隐藏每个原子的稳定唯一编号（与 3D 视图一致）")
        self.btn_toggle_num.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 8px; font-size:12px; font-weight:600; }"
            "QPushButton:checked { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; font-weight:800; }"
        )
        self.btn_toggle_num.toggled.connect(self.set_show_atom_numbers)
        h_lay.addWidget(self.btn_toggle_num)

        self.btn_bg_mode = QPushButton("暖白纸面")
        self.btn_bg_mode.setCheckable(True)
        self.btn_bg_mode.setChecked(True)
        self.btn_bg_mode.setMinimumWidth(68)
        self.btn_bg_mode.setToolTip("在 ChemDraw 暖白出版画布与深色蓝图画布之间切换")
        self.btn_bg_mode.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 8px; font-size:12px; font-weight:600; }"
            "QPushButton:checked { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; font-weight:800; }"
            "QPushButton:hover { background:#1F354C; color:#EAF2F6; }"
        )
        self.btn_bg_mode.clicked.connect(self._toggle_paper_mode)
        h_lay.addWidget(self.btn_bg_mode)

        # 缩放控制组：[-] 100% [+] [⛶ 居中]
        btn_zoom_out = QPushButton("－")
        btn_zoom_out.setFixedSize(26, 26)
        btn_zoom_out.setToolTip("缩小 2D 画布 (滚轮下滚)")
        btn_zoom_out.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#0D9488; color:#FFFFFF; }"
        )
        btn_zoom_out.clicked.connect(self.zoom_out)
        h_lay.addWidget(btn_zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("color:#66DEC9; font-weight:700; font-size:12px; padding:0 4px;")
        h_lay.addWidget(self.lbl_zoom)

        btn_zoom_in = QPushButton("＋")
        btn_zoom_in.setFixedSize(26, 26)
        btn_zoom_in.setToolTip("放大 2D 画布 (滚轮上滚)")
        btn_zoom_in.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#0D9488; color:#FFFFFF; }"
        )
        btn_zoom_in.clicked.connect(self.zoom_in)
        h_lay.addWidget(btn_zoom_in)

        reset_2d_btn = QPushButton("⛶ 居中适配")
        reset_2d_btn.setMinimumWidth(72)
        reset_2d_btn.setToolTip("自动缩放居中分子以完美契合当前画布 (快捷键: 0)")
        reset_2d_btn.setStyleSheet(
            "QPushButton { background:#152435; color:#95A9B8; border:1px solid #243B50; "
            "border-radius:6px; padding:3px 8px; font-size:12px; font-weight:600; }"
            "QPushButton:hover { background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; }"
        )
        reset_2d_btn.clicked.connect(self.fit_view)
        h_lay.addWidget(reset_2d_btn)

        self._header_frame = HorizontalWheelScrollArea(header, height=36)
        self._header_frame.height_changed.connect(self._on_header_height)
        lay.addWidget(self._header_frame)
        self.HEADER_HEIGHT = 0.0 if self._chromeless else float(self._header_frame.height())
        lay.addStretch(1)
        if getattr(self, "_chromeless", False):
            self._header_frame.hide()

    def _on_header_height(self, height):
        self.HEADER_HEIGHT = 0.0 if self._header_frame.isHidden() else float(height)
        self.update()

    def set_header_visible(self, visible: bool) -> None:
        self.HEADER_HEIGHT = float(self._header_frame.height()) if visible else 0.0
        if hasattr(self, "_header_frame") and self._header_frame is not None:
            self._header_frame.setVisible(visible)
        self.update()

    # ---------- 严格可逆的 2D 世界坐标 (Å) <-> 屏幕像素坐标 (px) 变换 ----------

    @property
    def _scale(self) -> float:
        return self.BASE_PX_PER_ANGSTROM * self._zoom

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """将 2D 世界坐标 (wx, wy, 单位 Å) 转换为当前画布像素坐标 (sx, sy)。"""
        cx = self.width() * 0.5 + self._pan_x
        cy = (self.height() + self.HEADER_HEIGHT) * 0.5 + self._pan_y
        s = self._scale
        return (cx + wx * s, cy - wy * s)

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """将当前画布像素坐标 (sx, sy) 逆变换为 2D 世界坐标 (wx, wy, 单位 Å)。"""
        cx = self.width() * 0.5 + self._pan_x
        cy = (self.height() + self.HEADER_HEIGHT) * 0.5 + self._pan_y
        s = max(1e-6, self._scale)
        return ((sx - cx) / s, -(sy - cy) / s)

    def _ensure_world_coords_2d(self) -> dict[AtomId, tuple[float, float]]:
        """确保 doc.coords_2d 中存储的是以 (0,0) 为中心、键长 ~1.50 Å 的世界坐标。"""
        if self._document is None or self._document.topology.num_atoms == 0:
            return {}

        doc = self._document
        atom_ids = list(doc.topology.atom_ids)

        # 若全部原子已有 2D 世界坐标，先检查是否误存了旧版屏幕像素坐标，若是则自动归一化
        if doc.coords_2d and all(aid in doc.coords_2d for aid in atom_ids):
            doc.sync_2d_coords_from_3d()
            return doc.coords_2d

        # 若部分新原子缺失 2D 坐标（例如刚在 3D 里点了加原子），调用增量同步而不打乱已有布局！
        if doc.coords_2d and any(aid in doc.coords_2d for aid in atom_ids):
            doc.sync_2d_coords_from_3d()
            return doc.coords_2d

        # 首次加载或重排：若已有 3D 坐标且原子数较大(>45)，优先走 0.1ms SVD 主平面投影；中小分子走 RDKit 2D
        coords_w: dict[AtomId, tuple[float, float]] = {}
        if doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) == len(atom_ids) and len(atom_ids) > 45:
            from ..io.rdkit_adapter import compute_2d_coords_from_3d_svd
            _, id_to_idx = doc.topology.atom_index_map()
            b_list = [
                (id_to_idx[doc.topology.get_bond(bid).begin], id_to_idx[doc.topology.get_bond(bid).end], 1)
                for bid in doc.topology.bond_ids
                if doc.topology.get_bond(bid).begin in id_to_idx and doc.topology.get_bond(bid).end in id_to_idx
            ]
            doc.coords_2d = compute_2d_coords_from_3d_svd(atom_ids, doc.coordinates.current.coords, b_list)
            return doc.coords_2d

        try:
            rdmol, atom_rdkit_idx_map, _ = doc_to_rdkit(doc, sanitize=True)
            from rdkit.Chem import AllChem
            AllChem.Compute2DCoords(rdmol)
            if rdmol.GetNumConformers() > 0:
                conf = rdmol.GetConformer()
                raw = np.array([[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y] for i in range(rdmol.GetNumAtoms())])
                center = raw.mean(axis=0) if len(raw) > 0 else np.zeros(2)
                rdkit_to_aid = {v: k for k, v in atom_rdkit_idx_map.items()}
                for i in range(rdmol.GetNumAtoms()):
                    aid = rdkit_to_aid.get(i)
                    if aid is not None:
                        coords_w[aid] = (float(raw[i, 0] - center[0]), float(raw[i, 1] - center[1]))
        except Exception:
            pass

        if not coords_w:
            if doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) == len(atom_ids):
                from ..io.rdkit_adapter import compute_2d_coords_from_3d_svd
                coords_w = compute_2d_coords_from_3d_svd(atom_ids, doc.coordinates.current.coords)
            else:
                for i, aid in enumerate(atom_ids):
                    coords_w[aid] = (float(i) * 1.50, 0.0)

        doc.coords_2d = coords_w
        return doc.coords_2d

    def _get_screen_coords(self) -> dict[AtomId, tuple[float, float]]:
        """获取所有原子在当前屏幕上的像素坐标 (sx, sy)；变换用 NumPy 向量化。"""
        world_map = self._ensure_world_coords_2d()
        if not world_map:
            return {}
        aids = list(world_map.keys())
        w = np.array([world_map[a] for a in aids], dtype=np.float64)
        cx = self.width() * 0.5 + self._pan_x
        cy = (self.height() + self.HEADER_HEIGHT) * 0.5 + self._pan_y
        s = self._scale
        sx = cx + w[:, 0] * s
        sy = cy - w[:, 1] * s
        return {a: (float(sx[i]), float(sy[i])) for i, a in enumerate(aids)}

    # ---------- 视图与工具切换 ----------

    def _toggle_explicit_h(self, checked: bool):
        self._hide_explicit_hydrogens = checked
        self.btn_toggle_h.setText("隐式氢" if checked else "全显氢")
        self.update()

    def _toggle_paper_mode(self):
        self._paper_mode = not self._paper_mode
        self.btn_bg_mode.setText("暖白纸面" if self._paper_mode else "深色蓝图")
        self._apply_canvas_palette()
        self.update()

    def _apply_canvas_palette(self):
        scheme = self.COLORS_PAPER if self._paper_mode else self.COLORS_DARK
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(scheme["bg"]))
        self.setPalette(palette)

    def recompute_2d_layout(self):
        if self._document is not None:
            self._document.coords_2d.clear()
            self._ensure_world_coords_2d()
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    def _update_tool_hint(self):
        elem = get_element(self._current_element)
        sym = elem.symbol if elem else "C"
        if self._pending_ring is not None:
            size, arom, _ = self._pending_ring
            kind = "芳香" if arom else "饱和"
            self.tool_hint_label.setText(f"放置模式：{kind} {size} 元环（点击空白放置或点原子接环）")
        else:
            self.tool_hint_label.setText(f"[{self._current_tool}] · 元素 {sym}")

    def set_document(self, doc: MoleculeDocument):
        is_new_doc = (self._last_doc_id != doc.document_id)
        self._document = doc
        self._last_doc_id = doc.document_id
        if is_new_doc:
            self._zoom = 1.0
            self._pan_x = 0.0
            self._pan_y = 0.0
        self._ensure_world_coords_2d()
        if is_new_doc and doc.num_atoms > 1:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(30, self.fit_view)
        self.update()

    def fit_view(self):
        """自动调整缩放和平移，让整个分子完整显示在画布中间"""
        if self._document is None or self._document.topology.num_atoms == 0:
            return
        coords = self._ensure_world_coords_2d()
        if not coords:
            return
        # 计算所有原子的坐标范围
        xs = [x for x, y in coords.values()]
        ys = [y for x, y in coords.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        mol_width = max(max_x - min_x + 1.2, 2.0)
        mol_height = max(max_y - min_y + 1.2, 2.0)
        # 画布大小（减去顶部标题栏）
        canvas_w = max(50.0, float(self.width()))
        canvas_h = max(50.0, float(self.height() - self.HEADER_HEIGHT))
        if canvas_w <= 80 or canvas_h <= 80:
            return
        # 计算缩放比例：保留 ~25% 优雅边距，确保分子舒展居中显示
        zoom_x = (canvas_w * 0.72) / (mol_width * self.BASE_PX_PER_ANGSTROM)
        zoom_y = (canvas_h * 0.72) / (mol_height * self.BASE_PX_PER_ANGSTROM)
        # 无界自适应缩放：支持超大分子网络（最低 0.5%）与单原子局部（最高 250%），兼顾大体系全景与微观细节
        self._zoom = max(0.005, min(2.5, min(zoom_x, zoom_y)))
        # 计算平移，让分子质心对齐画布中心
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        self._pan_x = -center_x * self.BASE_PX_PER_ANGSTROM * self._zoom
        self._pan_y = center_y * self.BASE_PX_PER_ANGSTROM * self._zoom
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(self._format_zoom_str())
        self.update()

    def _format_zoom_str(self) -> str:
        pct = self._zoom * 100.0
        if pct < 1.0:
            return f"{pct:.1f}%"
        return f"{int(pct)}%"

    def zoom_in(self):
        self._zoom = min(50.0, self._zoom * 1.25)
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(self._format_zoom_str())
        self.update()

    def zoom_out(self):
        self._zoom = max(0.005, self._zoom / 1.25)
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(self._format_zoom_str())
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, "_initial_fit_done", False) and self.width() > 180 and self.height() > 180:
            self._initial_fit_done = True
            QTimer.singleShot(60, self.fit_view)

    def set_selection_service(self, selection):
        if getattr(self, "_selection", None) is selection and getattr(self, "_selection_callback", None) is not None:
            return
        previous = getattr(self, "_selection", None)
        callback = getattr(self, "_selection_callback", None)
        if previous is not None and callback is not None:
            previous.remove_listener(callback)
        self._selection = selection
        self._selection_callback = lambda origin: self.update()
        selection.add_listener(self._selection_callback)
        self.destroyed.connect(lambda _=None, service=selection, cb=self._selection_callback: service.remove_listener(cb))

    def set_command_bus(self, bus):
        if getattr(self, "_command_bus", None) is bus and getattr(self, "_bus_callback", None) is not None:
            return
        previous = getattr(self, "_command_bus", None)
        callback = getattr(self, "_bus_callback", None)
        if previous is not None and callback is not None:
            previous.remove_listener(callback)
        self._command_bus = bus
        self._bus_callback = lambda _doc: self.update()
        bus.add_listener(self._bus_callback)
        self.destroyed.connect(lambda _=None, service=bus, cb=self._bus_callback: service.remove_listener(cb))

    def set_ring_template(self, size: int, aromatic: bool = False, hetero_atoms: dict[int, int] | None = None):
        self._pending_ring = (size, aromatic, hetero_atoms)
        self._update_tool_hint()

    def set_current_tool(self, tool: str):
        self._current_tool = tool
        self._update_tool_hint()
        self.update()

    def set_current_element(self, atomic_num: int) -> None:
        self._current_element = int(atomic_num)
        self._update_tool_hint()
        self.update()

    # ---------- 骨架氢折叠与环内双键检测 ----------

    def _is_hidden_hydrogen(self, aid: AtomId) -> bool:
        if not self._hide_explicit_hydrogens or self._document is None:
            return False
        if aid not in self._document.topology._atoms:
            return False
        atom = self._document.topology.get_atom(aid)
        if atom.atomic_num != 1:
            return False
        nbrs = self._document.topology.neighbors_of(aid)
        if len(nbrs) != 1:
            return False
        parent = self._document.topology.get_atom(nbrs[0])
        return parent.atomic_num in (6, 7, 8, 15, 16)

    def _should_show_atom_label(self, aid: AtomId) -> tuple[bool, str]:
        doc = self._document
        atom = doc.topology.get_atom(aid)
        z = atom.atomic_num
        elem = get_element(z)
        sym = elem.symbol if elem else "?"

        all_nbrs = doc.topology.neighbors_of(aid)
        visible_nbrs = [n for n in all_nbrs if not self._is_hidden_hydrogen(n)]
        folded_h = len(all_nbrs) - len(visible_nbrs)

        bond_order_sum = 0
        for bid in doc.topology._adjacency.get(aid, []):
            b = doc.topology.get_bond(bid)
            other = b.end if b.begin == aid else b.begin
            if not self._is_hidden_hydrogen(other):
                bond_order_sum += (2 if b.aromatic else b.order)

        if z == 6 and atom.formal_charge == 0 and len(visible_nbrs) >= 1:
            return False, ""

        if folded_h > 0:
            h_count = folded_h
        else:
            std_v = STANDARD_VALENCE.get(z, 0)
            h_count = max(0, std_v - bond_order_sum + atom.formal_charge) if z in (6, 7, 8, 16) else 0

        h_str = "H" if h_count == 1 else (("H" + str(h_count).translate(SUBSCRIPT_DIGITS)) if h_count > 1 else "")
        charge_str = ""
        if atom.formal_charge > 0:
            charge_str = "⁺" if atom.formal_charge == 1 else f"{atom.formal_charge}⁺"
        elif atom.formal_charge < 0:
            charge_str = "⁻" if atom.formal_charge == -1 else f"{abs(atom.formal_charge)}⁻"

        return True, f"{sym}{h_str}{charge_str}"

    def _get_color(self, key):
        col = self._color_cache.get(key)
        if col is None:
            if isinstance(key, (tuple, list)):
                col = QColor(*key)
            else:
                col = QColor(key)
            self._color_cache[key] = col
        return col

    def _get_pen(self, color_key, width, style=Qt.PenStyle.SolidLine, cap=Qt.PenCapStyle.RoundCap):
        key = (color_key, width, style, cap)
        pen = self._pen_cache.get(key)
        if pen is None:
            pen = QPen(self._get_color(color_key), width, style, cap)
            self._pen_cache[key] = pen
        return pen

    def _get_label_font(self):
        font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        font.setPointSizeF(max(1.0, 11.0 * self._zoom))
        return font

    def _ensure_grid_pixmap(self, scheme: dict):
        """网格只在尺寸/配色变化时绘制一次到 QPixmap，paintEvent 直接 drawPixmap。"""
        key = (self.width(), self.height(), int(self.HEADER_HEIGHT), scheme["grid"])
        if key == self._grid_cache_key and self._grid_pixmap is not None:
            return self._grid_pixmap
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap(self.size())
        pixmap.fill(QColor(scheme["bg"]))
        gp = QPainter(pixmap)
        gp.setPen(QPen(QColor(scheme["grid"]), 1.2))
        for y in range(int(self.HEADER_HEIGHT) + 18, self.height() - 12, 24):
            for x in range(20, self.width() - 12, 24):
                gp.drawPoint(x, y)
        gp.end()
        self._grid_pixmap = pixmap
        self._grid_cache_key = key
        return pixmap

    def _ensure_ring_cache(self) -> None:
        """环是分子拓扑的静态属性：用 RDKit SSSR 计算一次并缓存，只在拓扑变化时重算。"""
        if self._document is None:
            return
        doc = self._document
        key = (doc.document_id, doc.topology_hash())
        if key == self._ring_cache_key:
            return
        self._ring_atom_lists = []
        self._bond_rings = {}
        try:
            rdmol, atom_rdkit_idx_map, _ = doc_to_rdkit(doc, sanitize=False)
            aid_by_rdkit = {v: k for k, v in atom_rdkit_idx_map.items()}
            ring_info = rdmol.GetRingInfo()
            for r_atoms in ring_info.AtomRings():
                aids = [aid_by_rdkit[i] for i in r_atoms if i in aid_by_rdkit]
                if len(aids) >= 3:
                    ring_idx = len(self._ring_atom_lists)
                    self._ring_atom_lists.append(aids)
            # 建立 键 -> 所属环 索引：环内相邻原子对（含首尾）对应一条键
            idx_to_aid = aid_by_rdkit
            for ring_idx, r_atoms in enumerate(ring_info.AtomRings()):
                seq = list(r_atoms)
                for a, b in zip(seq, seq[1:] + seq[:1]):
                    bid = doc.topology.bond_between(idx_to_aid[a], idx_to_aid[b])
                    if bid is not None:
                        self._bond_rings.setdefault(bid, []).append(ring_idx)
        except Exception:
            self._ring_atom_lists = []
            self._bond_rings = {}
        self._ring_cache_key = key

    def _find_ring_centroids(self, screen_coords: dict[AtomId, tuple[float, float]]) -> dict[BondId, tuple[float, float]]:
        """基于缓存的环成员直接计算每个环中心，并映射到环内各键（不再每帧 BFS）。"""
        centroids: dict[BondId, tuple[float, float]] = {}
        if self._document is None:
            return centroids
        self._ensure_ring_cache()
        # 先一次性算出每个环的中心
        ring_centers: dict[int, tuple[float, float]] = {}
        for ring_idx, aids in enumerate(self._ring_atom_lists):
            pts = [screen_coords[a] for a in aids if a in screen_coords]
            if len(pts) < 3:
                continue
            arr = np.array(pts, dtype=np.float64)
            ring_centers[ring_idx] = (float(arr[:, 0].mean()), float(arr[:, 1].mean()))
        # 再单次遍历 键->环 映射查表
        for bid, ring_ids in self._bond_rings.items():
            for r in ring_ids:
                if r in ring_centers:
                    centroids[bid] = ring_centers[r]
                    break
        return centroids

    # ---------- 渲染绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        scheme = self.COLORS_PAPER if self._paper_mode else self.COLORS_DARK
        # 背景+网格走预渲染缓存，避免每帧数千次 drawPoint
        p.drawPixmap(0, 0, self._ensure_grid_pixmap(scheme))

        if self._document is None or self._document.topology.num_atoms == 0:
            p.setPen(QColor("#7D93A6"))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击或双击画布添加原子，或从左侧选择共轭环模板")
            p.end()
            return

        doc = self._document
        # 一次性计算隐藏氢集合，避免每帧对每个原子/键反复查拓扑
        hidden_h = {aid for aid in doc.topology.atom_ids if self._is_hidden_hydrogen(aid)}
        coords_2d = self._get_screen_coords()
        ring_centroids = self._find_ring_centroids(coords_2d)

        selected_atoms = self._selection.selected_atoms if self._selection is not None else set()
        selected_bonds = self._selection.selected_bonds if self._selection is not None else set()

        atom_labels: dict[AtomId, tuple[bool, str]] = {}
        for aid in list(doc.topology.atom_ids):
            if aid not in hidden_h:
                atom_labels[aid] = self._should_show_atom_label(aid)

        # 计算视口裁剪范围（保留 80px 宽裕缓冲带），开启高速视口剔除 (Viewport Frustum Culling)
        pad = 80.0
        vw_l, vw_t = -pad, float(self.HEADER_HEIGHT) - pad
        vw_r, vw_b = float(self.width()) + pad, float(self.height()) + pad

        def in_view(x: float, y: float) -> bool:
            return vw_l <= x <= vw_r and vw_t <= y <= vw_b

        def bond_in_view(x1: float, y1: float, x2: float, y2: float) -> bool:
            return in_view(x1, y1) or in_view(x2, y2) or (min(x1, x2) <= vw_r and max(x1, x2) >= vw_l and min(y1, y2) <= vw_b and max(y1, y2) >= vw_t)

        # 1. 绘制化学键（视口裁剪过滤）
        for bid in list(doc.topology.bond_ids):
            bond = doc.topology.get_bond(bid)
            if bond.begin in hidden_h or bond.end in hidden_h:
                continue
            if bond.begin in coords_2d and bond.end in coords_2d:
                x1, y1 = coords_2d[bond.begin]
                x2, y2 = coords_2d[bond.end]
                if not bond_in_view(x1, y1, x2, y2):
                    continue
                clip_start = 11.5 * self._zoom if atom_labels.get(bond.begin, (False, ""))[0] else 0.0
                clip_end = 11.5 * self._zoom if atom_labels.get(bond.end, (False, ""))[0] else 0.0
                is_sel = (bid in selected_bonds) or (bid == self._hover_bond)
                self._draw_bond(
                    p, x1, y1, x2, y2, bond.order, bond.aromatic,
                    clip_start=clip_start, clip_end=clip_end,
                    ring_center=ring_centroids.get(bid), highlighted=is_sel, scheme=scheme
                )

        # 2. 绘制选中与悬停光晕
        for aid in selected_atoms:
            if aid in coords_2d and aid not in hidden_h:
                x, y = coords_2d[aid]
                if in_view(x, y):
                    self._draw_selection_ring(p, x, y, is_hover=False)
        if self._hover_atom is not None and self._hover_atom in coords_2d and self._hover_atom not in selected_atoms:
            if self._hover_atom not in hidden_h:
                hx, hy = coords_2d[self._hover_atom]
                if in_view(hx, hy):
                    self._draw_selection_ring(p, hx, hy, is_hover=True)

        # 3. 绘制原子标签（结合 2D LOD 与视口剔除）
        is_lod_far_view = (self._zoom < 0.20)
        for aid in list(doc.topology.atom_ids):
            if aid not in coords_2d or aid in hidden_h:
                continue
            x, y = coords_2d[aid]
            if not in_view(x, y):
                continue
            atom = doc.topology.get_atom(aid)
            show_lbl, lbl_text = atom_labels.get(aid, (False, ""))
            if is_lod_far_view:
                # LOD 极远视口模式：绘制极速 CPK 彩色原子骨架点，跳过昂贵的 QFontMetrics 排版运算
                elem = get_element(atom.atomic_num)
                dot_color = self._get_color(tuple(int(c * 255) for c in elem.cpk_color)) if elem else self._get_color(scheme["text_c"])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(dot_color))
                dot_r = max(1.5, 4.0 * self._zoom)
                p.drawEllipse(QPointF(x, y), dot_r, dot_r)
            elif show_lbl:
                self._draw_atom_label(p, x, y, atom.atomic_num, lbl_text, scheme)

        # 3.5 绘制原子编号（独立角标，基于稳定 AtomId，与 3D 视图编号一致，仅在中近景且视野内绘制）
        if self._show_atom_numbers and not is_lod_far_view:
            for aid in list(doc.topology.atom_ids):
                if aid not in coords_2d or aid in hidden_h:
                    continue
                nx, ny = coords_2d[aid]
                if in_view(nx, ny):
                    self._draw_atom_number(p, nx, ny, aid.value)

        # 3.6 绘制选中原子的专属高亮序号徽标 (Badge)！
        for aid in selected_atoms:
            if aid in coords_2d and aid not in hidden_h:
                nx, ny = coords_2d[aid]
                if in_view(nx, ny):
                    self._draw_selected_atom_badge(p, nx, ny, aid.value + 1)

        # 4. 绘制拖拽建键预览线（若悬停在目标原子上，自动吸附到目标原子中心！）
        if self._dragging_bond and self._bond_start in coords_2d:
            sx, sy = coords_2d[self._bond_start]
            if self._hover_atom is not None and self._hover_atom in coords_2d and self._hover_atom != self._bond_start:
                ex, ey = coords_2d[self._hover_atom]
            else:
                ex, ey = self._mouse_pos.x(), self._mouse_pos.y()
            pen = QPen(QColor("#14A38C" if self._paper_mode else "#66DEC9"), 2.4, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))

        # 5. 框选矩形
        if self._marquee_rect is not None:
            pen = QPen(QColor(20, 163, 140), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QBrush(QColor(102, 222, 201, 38)))
            p.drawRect(self._marquee_rect.normalized())

        p.setPen(QColor("#788998" if self._paper_mode else "#627788"))
        p.setFont(QFont("Segoe UI", 9))
        vis_count = sum(1 for a in doc.topology.atom_ids if a not in hidden_h)
        p.drawText(
            14, self.height() - 10,
            f"缩放 {self._format_zoom_str()} · 显示 {vis_count}/{doc.num_atoms} 原子"
        )
        p.end()

    def _draw_bond(
        self, p: QPainter, x1: float, y1: float, x2: float, y2: float,
        order: int, aromatic: bool = False,
        clip_start: float = 0.0, clip_end: float = 0.0,
        ring_center: tuple[float, float] | None = None,
        highlighted: bool = False,
        scheme: dict = COLORS_PAPER,
    ):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-3:
            return
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux

        if highlighted:
            hl_pen = self._get_pen((102, 222, 201, 130), max(2.,8.0*self._zoom))
            p.setPen(hl_pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        sx1, sy1 = x1 + ux * min(clip_start, length * 0.35), y1 + uy * min(clip_start, length * 0.35)
        sx2, sy2 = x2 - ux * min(clip_end, length * 0.35), y2 - uy * min(clip_end, length * 0.35)

        p.setPen(self._get_pen(scheme["bond"], max(.45,2.2*self._zoom)))

        inward_sign = 1.0
        if ring_center is not None:
            mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            if ((ring_center[0] - mx) * nx + (ring_center[1] - my) * ny) < 0:
                inward_sign = -1.0

        if order == 1 and not aromatic:
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
        elif order == 2 or aromatic:
            if ring_center is not None:
                p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
                offset = 4.8 * self._zoom * inward_sign
                shrink = min(6.5*self._zoom, length * 0.18)
                ix1 = sx1 + ux * shrink + nx * offset
                iy1 = sy1 + uy * shrink + ny * offset
                ix2 = sx2 - ux * shrink + nx * offset
                iy2 = sy2 - uy * shrink + ny * offset
                if aromatic and order == 1:
                    p.setPen(self._get_pen(scheme["bond"], max(.4,1.8*self._zoom), Qt.PenStyle.DashLine))
                p.drawLine(QPointF(ix1, iy1), QPointF(ix2, iy2))
            else:
                off = 2.8*self._zoom
                p.drawLine(QPointF(sx1 + nx * off, sy1 + ny * off), QPointF(sx2 + nx * off, sy2 + ny * off))
                p.drawLine(QPointF(sx1 - nx * off, sy1 - ny * off), QPointF(sx2 - nx * off, sy2 - ny * off))
        elif order == 3:
            off = 4.2*self._zoom
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
            p.drawLine(QPointF(sx1 + nx * off, sy1 + ny * off), QPointF(sx2 + nx * off, sy2 + ny * off))
            p.drawLine(QPointF(sx1 - nx * off, sy1 - ny * off), QPointF(sx2 - nx * off, sy2 - ny * off))
        else:
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

    def _draw_selection_ring(self, p: QPainter, x: float, y: float, is_hover: bool = False):
        if is_hover:
            p.setPen(QPen(QColor(20, 163, 140, 160), 2.0))
            p.setBrush(QBrush(QColor(102, 222, 201, 55)))
            p.drawEllipse(QPointF(x, y), max(4.,13*self._zoom), max(4.,13*self._zoom))
        else:
            p.setPen(QPen(QColor(20, 163, 140, 95), max(1.5,5.*self._zoom)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), max(5.,15*self._zoom), max(5.,15*self._zoom))
            p.setPen(QPen(QColor(20, 163, 140), 2.0))
            p.drawEllipse(QPointF(x, y), max(4.,13*self._zoom), max(4.,13*self._zoom))

    def _draw_atom_label(self, p: QPainter, x: float, y: float, atomic_num: int, text: str, scheme: dict):
        if atomic_num in scheme:
            color = self._get_color(tuple(scheme[atomic_num]))
        else:
            elem = get_element(atomic_num)
            color = self._get_color(tuple(int(c * 255) for c in elem.cpk_color)) if elem else self._get_color(scheme["text_c"])

        font = self._get_label_font()
        p.setFont(font)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(text) + 4.0 * self._zoom
        th = fm.height() + 1.5 * self._zoom

        bg_rect = QRectF(x - tw * 0.5, y - th * 0.5, tw, th)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._get_color(scheme["bg"])))
        p.drawRoundedRect(bg_rect, 5.0, 5.0)
        p.setPen(color)
        p.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_atom_number(self, p: QPainter, x: float, y: float, number: int):
        """在原子右上角绘制随图缩放的轻量稳定编号。

        内部 AtomId 为 0-based，展示时统一 +1 为化学家习惯的 1-based，且与 3D 视图口径一致。
        """
        font = self._get_label_font()
        small = QFont(font)
        small.setPointSizeF(max(1.0, font.pointSizeF() * 0.72))
        small.setBold(True)
        p.setFont(small)
        fm = QFontMetricsF(small)
        txt = str(number + 1)
        tw = fm.horizontalAdvance(txt) + 5.0
        th = fm.height() + 1.0
        # 角标定位在原子右上方，避免与中心元素标签重叠
        bx = x + 11.0 * self._zoom
        by = y - 13.0 * self._zoom
        rect = QRectF(bx, by, tw, th)
        p.setPen(self._get_color("#637587" if self._paper_mode else "#B5C4D2"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)

    def _draw_selected_atom_badge(self, p: QPainter, x: float, y: float, number: int):
        """为选中的原子绘制高对比度荧光青色编号徽标，即使未开启全局编号也能醒目标记出选中的原子序号。"""
        txt = f"#{number}"
        font = QFont("Microsoft YaHei UI", max(8, int(9.5 * self._zoom)), QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(txt) + 6.0
        th = fm.height() + 2.0
        bx = x + 10.0 * self._zoom
        by = y - 14.0 * self._zoom
        rect = QRectF(bx, by, tw, th)

        p.setPen(QPen(QColor("#5EEAD4"), 1.2))
        p.setBrush(QBrush(QColor("#0D9488")))
        p.drawRoundedRect(rect, 4.0, 4.0)

        p.setPen(QColor("#FFFFFF"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)

    def set_show_atom_numbers(self, on: bool):
        """切换 2D 原子编号显示，并触发重绘。"""
        self._show_atom_numbers = bool(on)
        self.btn_toggle_num.blockSignals(True)
        self.btn_toggle_num.setChecked(bool(on))
        self.btn_toggle_num.blockSignals(False)
        self.update()

    # ---------- 拾取与生长辅助 ----------

    def _find_atom_at(self, pos: QPointF, radius: float = 22.0) -> AtomId | None:
        if self._document is None:
            return None
        coords = self._get_screen_coords()
        if not coords:
            return None
        px, py = pos.x(), pos.y()
        best_aid = None
        best_dist = float("inf")
        dyn_radius = max(radius, 16.0 * self._zoom)
        font = self._get_label_font()
        fm = QFontMetricsF(font)

        for aid, (x, y) in coords.items():
            if self._is_hidden_hydrogen(aid):
                continue
            # 1. 如果原子有文本标签（如 CH4, OH, NH2 等），优先检测标签文字矩形包围盒
            atom = self._document.topology.get_atom(aid) if aid in self._document.topology._atoms else None
            if atom is not None:
                show_lbl, lbl_text = self._should_show_atom_label(aid)
                if show_lbl and lbl_text:
                    tw = fm.horizontalAdvance(lbl_text) + 8.0 * self._zoom
                    th = fm.height() + 4.0 * self._zoom
                    l_rect = QRectF(x - tw * 0.5, y - th * 0.5, tw, th).adjusted(-6.0, -6.0, 6.0, 6.0)
                    if l_rect.contains(pos):
                        d = math.hypot(px - x, py - y)
                        if d < best_dist:
                            best_dist = d
                            best_aid = aid
                        continue

            # 2. 距离圆检测（随视口缩放动态放大）
            d = math.hypot(px - x, py - y)
            if d <= dyn_radius and d < best_dist:
                best_dist = d
                best_aid = aid
        return best_aid

    def _find_bond_at(self, pos: QPointF, tol: float = 9.0) -> BondId | None:
        if self._document is None:
            return None
        coords = self._get_screen_coords()
        best_bid = None
        best_d = tol
        for bid in list(self._document.topology.bond_ids):
            bond = self._document.topology.get_bond(bid)
            if self._is_hidden_hydrogen(bond.begin) or self._is_hidden_hydrogen(bond.end):
                continue
            if bond.begin in coords and bond.end in coords:
                x1, y1 = coords[bond.begin]
                x2, y2 = coords[bond.end]
                d = point_to_segment_dist(pos.x(), pos.y(), x1, y1, x2, y2)
                if d < best_d:
                    best_d = d
                    best_bid = bid
        return best_bid

    def _suggest_2d_sprout_world_pos(self, anchor_id: AtomId, bond_len_a: float = 1.50) -> tuple[float, float]:
        """在 2D 世界坐标系 (Å) 中计算 120° 链生长点。"""
        wmap = self._ensure_world_coords_2d()
        if anchor_id not in wmap or self._document is None:
            return (0.0, 0.0)
        x0, y0 = wmap[anchor_id]
        nbrs = [
            n for n in self._document.topology.neighbors_of(anchor_id)
            if n in wmap and not self._is_hidden_hydrogen(n)
        ]
        if not nbrs:
            return (x0 + bond_len_a * math.cos(math.pi / 6), y0 + bond_len_a * math.sin(math.pi / 6))
        if len(nbrs) == 1:
            nx, ny = wmap[nbrs[0]]
            ang = math.atan2(y0 - ny, x0 - nx)
            turn = math.pi / 3 if (anchor_id.value % 2 == 0) else -math.pi / 3
            return (x0 + bond_len_a * math.cos(ang + turn), y0 + bond_len_a * math.sin(ang + turn))
        vx = sum(wmap[n][0] - x0 for n in nbrs)
        vy = sum(wmap[n][1] - y0 for n in nbrs)
        norm = math.hypot(vx, vy)
        if norm > 1e-4:
            return (x0 - (vx / norm) * bond_len_a, y0 - (vy / norm) * bond_len_a)
        return (x0 + bond_len_a, y0)

    # ---------- 鼠标与滚轮交互 ----------

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else (1.0 / 1.12)
        # 超宽无界缩放：0.5% ~ 5000% (10,000 倍动态范围)，从超大纳米片/聚合物到单键局部自由缩放
        self._zoom = max(0.005, min(50.0, self._zoom * factor))
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(self._format_zoom_str())
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()
        if self._document is None:
            return
        pos = event.position()
        if pos.y() <= self.HEADER_HEIGHT:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = pos
            return

        is_left = (event.button() == Qt.MouseButton.LeftButton)
        is_right = (event.button() == Qt.MouseButton.RightButton)
        add_mode = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        space_pan = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)  # Alt/空格+左键平移

        # Alt+左键 或 中键 都可以平移画布
        if is_left and space_pan:
            self._panning = True
            self._pan_start = pos
            return

        # 待放置环模板优先处理
        if is_left and self._pending_ring is not None:
            hit_a = self._find_atom_at(pos)
            wpos = self.screen_to_world(pos.x(), pos.y())
            self._add_ring_at(wpos, attach_to=hit_a)
            return

        hit_atom = self._find_atom_at(pos)
        if hit_atom is not None:
            if is_left:
                if self._current_tool == "擦除":
                    self._delete_atom(hit_atom)
                    return
                if self._selection is not None:
                    if add_mode:
                        self._selection.toggle_atom(hit_atom, origin="2d")
                    else:
                        self._selection.select_atom(hit_atom, add=False, origin="2d")
                if self._current_tool == "选择" and self._document.topology.get_atom(hit_atom).properties.get("frozen"):
                    self.atom_clicked.emit(hit_atom)
                    return
                self._press_pos = QPointF(pos)
                self._dragging_bond = False
                if self._current_tool in ("键", "原子"):
                    self._bond_start = hit_atom
                else:
                    # 如果点中的原子已经在选中集合里，并且选中了多个原子，就批量拖动
                    if (self._selection is not None 
                        and len(self._selection.selected_atoms) > 1 
                        and hit_atom in self._selection.selected_atoms):
                        self._batch_dragging = True
                        self._batch_drag_start_screen = QPointF(pos)
                        self._batch_drag_start_world = {
                            aid: self._document.coords_2d.get(aid, (0, 0))
                            for aid in self._selection.selected_atoms if not self._document.topology.get_atom(aid).properties.get("frozen")
                        }
                    else:
                        self._drag_atom = hit_atom
                        self._drag_start_wpos = self._document.coords_2d.get(hit_atom)
                self.atom_clicked.emit(hit_atom)
            elif is_right:
                self._show_atom_context_menu(pos, hit_atom)
            return

        hit_bond = self._find_bond_at(pos)
        if hit_bond is not None:
            if is_left:
                if self._current_tool == "擦除":
                    self._delete_bond(hit_bond)
                    return
                if self._selection is not None:
                    self._selection.select_bond(hit_bond, add=add_mode, origin="2d")
                # 只有在"键"工具模式下，点击键才改变键级
                if self._current_tool == "键":
                    bond = self._document.topology.get_bond(hit_bond)
                    next_order = (bond.order % 3) + 1
                    if self._command_bus is not None:
                        from ..application.builtin_commands import ChangeBondOrderCommand
                        self._command_bus.execute(ChangeBondOrderCommand(hit_bond, next_order))
            elif is_right:
                self._show_bond_context_menu(pos, hit_bond)
            return

        if is_left:
            self._marquee_start = QPointF(pos)
            self._marquee_rect = QRectF(pos, pos)
        elif is_right:
            self._show_canvas_context_menu(pos)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        self._mouse_pos = pos

        if self._panning:
            delta = pos - self._pan_start
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._pan_start = pos
            self.update()
            return

        if self._marquee_start is not None:
            self._marquee_rect = QRectF(self._marquee_start, pos)
            self.update()
            return

        # 批量拖动多个选中的原子
        if self._batch_dragging and self._document is not None:
            delta_screen = pos - self._batch_drag_start_screen
            # 屏幕 delta 转世界 delta
            scale = self.BASE_PX_PER_ANGSTROM * self._zoom
            dx_world = delta_screen.x() / scale
            dy_world = delta_screen.y() / scale
            for aid, (x0, y0) in self._batch_drag_start_world.items():
                if aid in self._document.coords_2d:
                    self._document.coords_2d[aid] = (x0 + dx_world, y0 + dy_world)
            self.update()
            return

        # 选择工具下拖动原子：实时更新 2D 世界坐标，丝滑无跳变
        if self._drag_atom is not None and self._document is not None:
            wpos = self.screen_to_world(pos.x(), pos.y())
            self._document.coords_2d[self._drag_atom] = wpos
            self.update()
            return

        # 键/原子工具下拖动拉键：检测磁吸目标原子
        if self._bond_start is not None:
            if not self._dragging_bond and (pos - self._press_pos).manhattanLength() > 5:
                self._dragging_bond = True
            if self._dragging_bond:
                self._hover_atom = self._find_atom_at(pos, radius=22.0)
                self.update()
            return

        old_ha, old_hb = self._hover_atom, self._hover_bond
        self._hover_atom = self._find_atom_at(pos)
        self._hover_bond = None if self._hover_atom is not None else self._find_bond_at(pos)
        if (self._hover_atom != old_ha) or (self._hover_bond != old_hb):
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            return

        pos = event.position()

        # 1. 空白处点击或框选释放
        if self._marquee_start is not None:
            rect = QRectF(self._marquee_start, pos).normalized()
            add_mode = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if rect.width() < 6 and rect.height() < 6:
                if self._current_tool in ("原子", "键") or (self._document is not None and self._document.num_atoms == 0):
                    wpos = self.screen_to_world(pos.x(), pos.y())
                    if self._current_tool == "键":
                        # ChemDraw 标准：键工具点击空白画布，直接生成标准 C-C 键
                        self._add_standard_bond_at_world(wpos)
                    else:
                        if self._current_tool == "选择":
                            self._current_tool = "原子"
                            self._update_tool_hint()
                            self.tool_changed_signal.emit("原子")
                        self._add_atom_at_world(wpos)
                elif not add_mode and self._selection is not None:
                    self._selection.clear(origin="2d")
            else:
                self._apply_marquee(rect, add_mode)
            self._marquee_start = None
            self._marquee_rect = None
            self.update()
            return

        # 2. 批量拖动多个原子释放 -> 同步更新 3D 坐标并提交单步 MoveMultiAtoms3DCommand
        if getattr(self, "_batch_dragging", False):
            self._batch_dragging = False
            if self._document is not None and self._command_bus is not None and getattr(self, "_batch_drag_start_world", None):
                from ..application.builtin_commands import MoveMultiAtoms3DCommand
                old_3d_map = {}
                new_3d_map = {}
                for aid, (ox, oy) in self._batch_drag_start_world.items():
                    if aid in self._document.topology._atoms:
                        nx, ny = self._document.coords_2d.get(aid, (ox, oy))
                        p3 = self._document.get_atom_3d_pos(aid)
                        cz = float(p3[2]) if p3 is not None else 0.0
                        old_3d_map[aid] = p3 if p3 is not None else np.array([ox, oy, cz], dtype=np.float32)
                        new_3d_map[aid] = np.array([nx, ny, cz], dtype=np.float32)
                if old_3d_map:
                    self._command_bus.execute(MoveMultiAtoms3DCommand(old_3d_map, new_3d_map, description="批量平移选中原子"))
            self.update()
            return

        # 3. 拖动原子释放 -> 同步更新 3D 坐标并入撤销栈
        if self._drag_atom is not None:
            aid = self._drag_atom
            self._drag_atom = None
            if (pos - self._press_pos).manhattanLength() >= 3 and self._document is not None:
                wx, wy = self.screen_to_world(pos.x(), pos.y())
                old_3d = self._document.get_atom_3d_pos(aid)
                cur_z = float(old_3d[2]) if old_3d is not None else 0.0
                if self._command_bus is not None and old_3d is not None:
                    from ..application.builtin_commands import MoveAtom3DCommand
                    self._command_bus.execute(
                        MoveAtom3DCommand(aid, (wx, wy, cur_z), old_pos=old_3d, new_pos_2d=(wx, wy))
                    )
            self.update()
            return

        # 3. 画键或生长新键释放
        if self._bond_start is not None:
            start_aid = self._bond_start
            was_dragging = self._dragging_bond
            self._bond_start = None
            self._dragging_bond = False
            if was_dragging:
                target = self._find_atom_at(pos, radius=22.0)
                if target is not None and target != start_aid:
                    self._add_bond(start_aid, target)
                elif target is None:
                    wpos = self.screen_to_world(pos.x(), pos.y())
                    # ChemDraw 标准：拖出化学键时，对角度按 30° 吸附，对键长按标准 1.50 Å 吸附
                    wmap = self._ensure_world_coords_2d()
                    if start_aid in wmap:
                        sx_w, sy_w = wmap[start_aid]
                        dx, dy = wpos[0] - sx_w, wpos[1] - sy_w
                        dist = math.hypot(dx, dy)
                        if dist > 0.3:
                            ang = math.atan2(dy, dx)
                            # 吸附到最接近的 30° 倍数 (k * pi / 6)
                            snap_ang = round(ang / (math.pi / 6.0)) * (math.pi / 6.0)
                            snap_len = 1.50 if (0.75 <= dist <= 2.25) else dist
                            wpos = (sx_w + snap_len * math.cos(snap_ang), sy_w + snap_len * math.sin(snap_ang))
                    self._add_atom_at_world(wpos, bond_to=start_aid)
            else:
                atom = self._document.topology.get_atom(start_aid)
                if self._current_tool == "原子":
                    # 原子工具点击原子：如果元素不同则切换元素；若相同则仅选中，绝不无故发芽！
                    if atom.atomic_num != self._current_element:
                        from ..application.builtin_commands import ChangeElementCommand
                        if self._command_bus is not None:
                            self._command_bus.execute(ChangeElementCommand(start_aid, self._current_element))
                    elif self._selection is not None:
                        self._selection.select_atom(start_aid, add=False, origin="2d")
                elif self._current_tool == "键":
                    # 键工具点击原子：ChemDraw 标准发芽生长！
                    sprout_wpos = self._suggest_2d_sprout_world_pos(start_aid)
                    self._add_atom_at_world(sprout_wpos, bond_to=start_aid)
            self.update()

    # ---------- 命令执行 ----------

    def _add_ring_at(self, center_wpos: tuple[float, float], attach_to: AtomId | None = None):
        if self._command_bus is None or self._pending_ring is None:
            return
        from ..application.builtin_commands import AddRingCommand
        size, aromatic, hetero = self._pending_ring
        self._pending_ring = None
        self._update_tool_hint()
        self._command_bus.execute(
            AddRingCommand(
                size=size, aromatic=aromatic, hetero_atoms=hetero,
                center_2d=center_wpos, center_3d=(center_wpos[0], center_wpos[1], 0.0),
                attach_to=attach_to,
            )
        )
        self.update()

    def _add_atom_at_world(self, wpos: tuple[float, float], bond_to: AtomId | None = None) -> AtomId | None:
        if self._command_bus is None:
            return None
        from ..application.builtin_commands import AddAtomCommand
        wx, wy = float(wpos[0]), float(wpos[1])

        # 保护：若未指定成键目标，且点击位置距离已有可见原子极其接近 (< 0.70 Å)，避免重叠生成孤立原子
        if bond_to is None and self._document is not None and self._document.coords_2d:
            for aid, (ox, oy) in self._document.coords_2d.items():
                if aid in self._document.topology._atoms and not self._is_hidden_hydrogen(aid):
                    if math.hypot(wx - ox, wy - oy) < 0.70:
                        return aid
        z_val = 0.0
        if bond_to is not None and self._document is not None:
            p3 = self._document.get_atom_3d_pos(bond_to)
            if p3 is not None:
                z_val = float(p3[2])
        cmd = AddAtomCommand(
            self._current_element, x=wx, y=wy, z=z_val, bond_to=bond_to, pos_2d=(wx, wy)
        )
        result = self._command_bus.execute(cmd)
        if result.success:
            aid = AtomId(result.data["atom_id"])
            if self._document is not None:
                self._document.coords_2d[aid] = (wx, wy)
            self.update()
            return aid
        return None

    def _add_standard_bond_at_world(self, wpos: tuple[float, float]) -> tuple[AtomId | None, AtomId | None]:
        """在空白处按 ChemDraw 标准创建一条标准 C-C 单键（乙烷式基元：30° 角，键长 1.50 Å）。"""
        if self._command_bus is None or self._document is None:
            return None, None
        wx, wy = float(wpos[0]), float(wpos[1])
        bond_len = 1.50
        angle = math.pi / 6.0  # 30°
        wpos2 = (wx + bond_len * math.cos(angle), wy + bond_len * math.sin(angle))
        
        a1 = self._add_atom_at_world((wx, wy))
        if a1 is not None:
            a2 = self._add_atom_at_world(wpos2, bond_to=a1)
            return a1, a2
        return None, None

    def _add_bond(self, a: AtomId, b: AtomId):
        if self._command_bus is None or self._document is None:
            return
        from ..application.builtin_commands import AddBondCommand, ChangeBondOrderCommand
        existing = self._document.topology.bond_between(a, b)
        if existing is not None:
            cur_order = self._document.topology.get_bond(existing).order
            self._command_bus.execute(ChangeBondOrderCommand(existing, (cur_order % 3) + 1))
        else:
            self._command_bus.execute(AddBondCommand(a, b, 1))
        self.update()

    def _delete_atom(self, aid: AtomId):
        if self._command_bus is None:
            return
        from ..application.builtin_commands import DeleteAtomCommand
        self._command_bus.execute(DeleteAtomCommand(aid))
        self.update()

    def _delete_bond(self, bid: BondId):
        if self._command_bus is None:
            return
        from ..application.builtin_commands import DeleteBondCommand
        self._command_bus.execute(DeleteBondCommand(bid))
        self.update()

    def _apply_marquee(self, rect: QRectF, add: bool):
        """
        框选原子：在隐式氢模式下，框选骨架重原子时自动连带选中其挂接的所有隐式氢原子（修复 P0 Bug 3）！
        同时自动选中两端原子均在选中集内的化学键。
        """
        if self._selection is None or self._document is None:
            return
        coords = self._get_screen_coords()
        hits: set[AtomId] = {
            aid for aid, (x, y) in coords.items()
            if rect.contains(QPointF(x, y))
        }
        # 连带纳入所有已命中重原子相连的氢原子（即便在隐式氢模式下未单独绘制）
        attached_h: set[AtomId] = set()
        for aid in list(hits):
            for nb in self._document.topology.neighbors_of(aid):
                if nb in self._document.topology._atoms and self._document.topology.get_atom(nb).atomic_num == 1:
                    attached_h.add(nb)
        hits |= attached_h

        if not add:
            self._selection.clear(origin="2d")
        if hits:
            self._selection.select_atoms(hits | (self._selection.selected_atoms if add else set()), origin="2d")
            # 同步选中两端原子均被选中的化学键
            all_sel = self._selection.selected_atoms
            for bid in self._document.topology.bond_ids:
                b = self._document.topology.get_bond(bid)
                if b.begin in all_sel and b.end in all_sel:
                    self._selection.select_bond(bid, add=True, origin="2d")
        self.update()

    def delete_selected(self) -> int:
        """删除当前选中的所有化学键与原子（连带相连氢原子），完美解决 P0 Bug 2 & Bug 4。"""
        if self._selection is None or self._document is None or self._command_bus is None:
            return 0
        sel_bonds = list(self._selection.selected_bonds)
        sel_atoms = list(self._selection.selected_atoms)
        if not sel_bonds and not sel_atoms:
            return 0
        from ..application.selection_commands import DeleteSelectionCommand
        result = self._command_bus.execute(DeleteSelectionCommand(sel_atoms, sel_bonds))
        count = len(sel_atoms) + len(sel_bonds) if result.success else 0
        self._selection.clear(origin="2d")
        self.update()
        return count

    def _show_atom_context_menu(self, pos: QPointF, atom_id: AtomId):
        """原子右键上下文菜单（支持单原子操作与多选批量删除）。"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; padding: 4px; } QMenu::item { padding: 6px 24px; }")

        atom = self._document.topology.get_atom(atom_id)
        elem = get_element(atom.atomic_num)
        sym = elem.symbol if elem else "C"

        title = menu.addAction(f"原子 #{atom_id.value+1} ({sym})")
        title.setEnabled(False)
        menu.addSeparator()

        if self._selection is not None and len(self._selection.selected_atoms) > 1:
            n_sel = len(self._selection.selected_atoms)
            menu.addAction(f"🗑️ 删除选中的 {n_sel} 个原子 (Delete)", self.delete_selected)
            menu.addSeparator()

        menu.addAction("删除该原子", lambda: self._delete_atom(atom_id))
        menu.addAction("删除连通基团", lambda: self._delete_connected_fragment(atom_id))
        menu.addSeparator()

        elem_menu = menu.addMenu("改为元素")
        for s_lbl, z in [("C", 6), ("N", 7), ("O", 8), ("S", 16), ("F", 9), ("Cl", 17), ("Br", 35), ("P", 15), ("H", 1)]:
            elem_menu.addAction(s_lbl, lambda _=False, zv=z, aid=atom_id: self._change_element(aid, zv))
        menu.addSeparator()

        elem_menu.addSeparator()
        elem_menu.addAction("完整118元素周期表…", lambda: self._pick_context_element(atom_id))
        from .modeling_actions import add_modeling_actions
        add_modeling_actions(self, menu, atom_id)
        menu.addAction("复制坐标到剪贴板", lambda: self._copy_atom_coord(atom_id))
        menu.exec(self.mapToGlobal(pos.toPoint()))

    def _pick_context_element(self, atom_id):
        from .element_picker import ElementPickerDialog
        dialog = ElementPickerDialog(self, compact=True)
        if dialog.exec() and dialog.selected_element:
            self._change_element(atom_id, dialog.selected_element.atomic_number)

    def _show_bond_context_menu(self, pos: QPointF, bond_id: BondId):
        """化学键右键上下文菜单"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; padding: 4px; } QMenu::item { padding: 6px 24px; }")

        bond = self._document.topology.get_bond(bond_id)
        order_names = {1: "单键", 2: "双键", 3: "三键", 4: "芳香键"}

        title = menu.addAction(f"键 #{bond_id.value} ({order_names.get(bond.order, '未知')})")
        title.setEnabled(False)
        menu.addSeparator()

        if self._selection is not None and len(self._selection.selected_atoms) > 0:
            menu.addAction(f"🗑️ 删除选中项 (Delete)", self.delete_selected)
            menu.addSeparator()

        menu.addAction("删除该化学键", lambda: self._delete_bond(bond_id))
        menu.addSeparator()

        order_menu = menu.addMenu("切换键级")
        for order, name in [(1, "单键"), (2, "双键"), (3, "三键"), (4, "芳香")]:
            order_menu.addAction(name, lambda _=False, o=order, bid=bond_id: self._set_bond_order(bid, o))
        from .modeling_actions import add_modeling_actions
        add_modeling_actions(self, menu, bond_id=bond_id)

        menu.exec(self.mapToGlobal(pos.toPoint()))

    def _show_canvas_context_menu(self, pos: QPointF):
        """空白处右键上下文菜单（含框选后“删除选中原子”项，修复 P0 Bug 2）。"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; padding: 4px; } QMenu::item { padding: 6px 24px; }")

        # 若当前有框选或点选的原子/化学键，第一项直接提供「删除选中原子/键」
        if self._selection is not None and (len(self._selection.selected_atoms) > 0 or len(self._selection.selected_bonds) > 0):
            n_a = len(self._selection.selected_atoms)
            n_b = len(self._selection.selected_bonds)
            del_act = menu.addAction(f"🗑️ 删除选中 ({n_a} 个原子, {n_b} 条键) [Delete]")
            del_act.triggered.connect(self.delete_selected)
            menu.addSeparator()

        if self._command_bus is not None:
            undo_action = menu.addAction("撤销 (Ctrl+Z)")
            undo_action.triggered.connect(self._command_bus.undo)
            redo_action = menu.addAction("重做 (Ctrl+Y)")
            redo_action.triggered.connect(self._command_bus.redo)
            menu.addSeparator()

        menu.addAction("在此处添加当前元素原子", lambda: self._add_atom_at_world(self.screen_to_world(pos.x(), pos.y())))
        menu.addAction("清洁 2D 结构布局", self._clean_structure)
        menu.addAction("居中适配视图", self._center_view)
        menu.addSeparator()

        menu.addAction("全选所有原子（含隐式氢） (Ctrl+A)", self._select_all)
        menu.addAction("取消全选", self._deselect_all)

        menu.exec(self.mapToGlobal(pos.toPoint()))

    def _change_element(self, atom_id: AtomId, new_z: int):
        """修改原子元素类型（通过 ChangeElementCommand 支持 Undo/Redo）。"""
        if self._document is None or atom_id not in self._document.topology._atoms:
            return
        atom = self._document.topology.get_atom(atom_id)
        if atom.atomic_num == new_z:
            return
        if self._command_bus is not None:
            from ..application.builtin_commands import ChangeElementCommand
            self._command_bus.execute(ChangeElementCommand(atom_id, new_z))
        else:
            atom.atomic_num = new_z
        self.update()

    def _set_bond_order(self, bond_id: BondId, order: int):
        """设置键级"""
        if self._document is None or bond_id not in self._document.topology._bonds:
            return
        bond = self._document.topology.get_bond(bond_id)
        if bond.order == order:
            return
        if self._command_bus is not None:
            from ..application.builtin_commands import ChangeBondOrderCommand
            self._command_bus.execute(ChangeBondOrderCommand(bond_id, order))
        self.update()

    def _delete_connected_fragment(self, seed_atom: AtomId):
        """删除从 seed_atom 开始的连通基团"""
        if self._document is None:
            return
        from PyQt6.QtWidgets import QMessageBox
        visited: set[AtomId] = set()
        stack = [seed_atom]
        while stack:
            aid = stack.pop()
            if aid in visited:
                continue
            visited.add(aid)
            for neighbor in self._document.topology.neighbors_of(aid):
                if neighbor not in visited:
                    stack.append(neighbor)

        reply = QMessageBox.question(
            self, "删除基团",
            f"将删除 {len(visited)} 个原子组成的连通基团，确认？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for aid in sorted(visited, key=lambda a: a.value, reverse=True):
            if aid in self._document.topology._atoms:
                self._delete_atom(aid)
        self.update()

    def _copy_atom_coord(self, atom_id: AtomId):
        """复制原子坐标到剪贴板"""
        if self._document is None:
            return
        coord = self._document.coords_2d.get(atom_id)
        if coord:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(f"{coord[0]:.4f}, {coord[1]:.4f}")

    def _clean_structure(self):
        self.recompute_2d_layout()

    def _center_view(self):
        self.fit_view()

    def _select_all(self):
        """全选所有原子（包含隐式氢与全部化学键，修复 P0 Bug 3）。"""
        if self._selection is not None and self._document is not None:
            all_aids = set(self._document.topology.atom_ids)
            self._selection.select_atoms(all_aids, origin="2d")
            for bid in self._document.topology.bond_ids:
                self._selection.select_bond(bid, add=True, origin="2d")
            self.update()

    def _deselect_all(self):
        """取消全选"""
        if self._selection is not None:
            self._selection.clear(origin="2d")
            self.update()

    def doubleClickEvent(self, event):
        pos = event.position()
        if pos.y() <= self.HEADER_HEIGHT:
            return
        hit = self._find_atom_at(pos)
        if hit is not None and self._selection is not None:
            self._selection.select_atom(hit, origin="2d")
            self.atom_double_clicked.emit(hit)
        elif hit is None:
            wpos = self.screen_to_world(pos.x(), pos.y())
            self._add_atom_at_world(wpos)

    _ELEMENT_KEYS = {
        "c": 6, "n": 7, "o": 8, "s": 16, "p": 15,
        "f": 9, "i": 53, "h": 1,
    }

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text().lower()

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_A:
                self._select_all()
                event.accept()
                return
            if key == Qt.Key.Key_Z:
                if self._command_bus is not None:
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self._command_bus.redo()
                    else:
                        self._command_bus.undo()
                event.accept()
                self.update()
                return
            if key == Qt.Key.Key_Y:
                if self._command_bus is not None:
                    self._command_bus.redo()
                event.accept()
                self.update()
                return
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        if text == "0" or key == Qt.Key.Key_Space:
            self.fit_view()
            event.accept()
            return

        if text in self._ELEMENT_KEYS:
            z = self._ELEMENT_KEYS[text]
            # ChemDraw 标准：光标悬停在原子上或已选中原子时，按快捷键直接修改该原子的元素！
            target_aids = []
            if self._hover_atom is not None:
                target_aids = [self._hover_atom]
            elif self._selection is not None and self._selection.selected_atoms:
                target_aids = list(self._selection.selected_atoms)

            if target_aids and self._command_bus is not None:
                from ..application.builtin_commands import ChangeElementCommand
                for target_aid in target_aids:
                    self._command_bus.execute(ChangeElementCommand(target_aid, z))
                self.update()
                return

            self._current_element = z
            self._current_tool = "原子"
            self._update_tool_hint()
            self.element_changed_signal.emit(z)
            self.tool_changed_signal.emit("原子")
            self.update()
            return

        for k_char, t_name in (("v", "选择"), ("b", "键"), ("a", "原子"), ("e", "擦除")):
            if text == k_char:
                self._current_tool = t_name
                self._update_tool_hint()
                self.tool_changed_signal.emit(t_name)
                self.update()
                return

        super().keyPressEvent(event)
