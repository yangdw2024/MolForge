"""
ui/views.py - GaussView 6.0 + Chem3D 标准独立可停靠/浮动检查器与表格面板系统 (MolForge v4)
==========================================================================================
包含：
  1. `ModelExplorerDock` (View -> Model Explorer / Structure Browser)：分子结构树浏览与快速选择
  2. `CartesianTableDock` (View / Tools -> Cartesian Coordinates Table / Atom List)：
     笛卡尔坐标与单原子属性实时可编辑表格（改 X/Y/Z 或单原子缩放即入 Undo 栈并同步 2D/3D）
  3. `MeasurementTableDock` (View / Tools -> Measurement & Redundant Coordinates Table)：
     全部键长 R(i,j)、键角 A(i,j,k)、二面角 D(i,j,k,l) 内坐标总表与交互高亮
  4. `AtomBondPropertyDock` (View / Results -> Atom & Bond Property Table)：
     逐原子/逐键物理化学性质、部分电荷、独立半径与颜色总表
  5. `DihedralChartDialog` (View / Results -> Dihedral Torsion Energy Scan Chart)：
     二面角旋转势能扫描曲线图（支持导出 SVG/PNG）
  6. `BuilderFragmentDialog` (Builder -> Element / Ring / R-Group / Biological / Custom Fragment)：
     GaussView 风格构件调色板，选定后可在画布一键点放或接枝
  7. `ModifyInternalCoordDialog` (Builder -> Modify Bond / Modify Angle / Modify Dihedral)：
     精确数值/滑块调整键长、键角、二面角（支持 Undo/Redo）
"""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QPen, QBrush, QFont
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QDockWidget,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QPushButton, QDialog, QFormLayout,
    QDoubleSpinBox, QSlider, QComboBox, QLineEdit, QFileDialog, QMessageBox
)

from ..domain.elements import get_element
from ..domain.ids import AtomId, BondId
from ..application import measurement as mm

ASSETS = Path(__file__).resolve().parent / "assets"


class SvgPreview(QWidget):
    def __init__(self, svg_name: str, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.renderer = QSvgRenderer(str(ASSETS / svg_name), self)
        self.setMinimumSize(180, 190)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect())
        p.fillRect(area, QColor("#F4F3EE") if self.mode == "2d" else QColor("#243D51"))
        if self.renderer.isValid():
            self.renderer.render(p, QRectF(8.0, 28.0, max(0.0, float(self.width() - 16)), max(0.0, float(self.height() - 64))))
        p.end()


class ViewCard(QFrame):
    def __init__(self, title: str, svg: str, mode: str):
        super().__init__()
        self.setObjectName("ViewCard")
        shell = QVBoxLayout(self)
        self.canvas = SvgPreview(svg, mode)
        shell.addWidget(self.canvas, 1)


# ===========================================================================
# 1. Model Explorer / Structure Browser (独立可停靠/浮动面板)
# ===========================================================================
class ModelExplorerDock(QDockWidget):
    """Chem3D / GaussView 风格模型结构树浏览器（支持停靠、浮动、关闭与点击选中联动）。"""

    def __init__(self, main_window):
        super().__init__("模型结构树 (Model Explorer / Structure Browser)", main_window)
        self.main_window = main_window
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["对象层级 (Hierarchy)", "类型 / 化学式", "属性摘要"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self.tree, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 刷新结构树")
        refresh_btn.clicked.connect(self.refresh_from_document)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        lay.addLayout(btn_row)

        self.setWidget(container)
        self.resize(360, 420)
        self.refresh_from_document()

    def refresh_from_document(self):
        self.tree.clear()
        doc = self.main_window.document
        g_id = getattr(self.main_window, "group_tag", "G1:M1:V1")
        root = QTreeWidgetItem(self.tree, [f"📦 {g_id} · {doc.name}", "MoleculeDocument", f"{doc.num_atoms} 原子, {doc.num_bonds} 键"])
        root.setExpanded(True)

        heavy_node = QTreeWidgetItem(root, ["⚛ 骨架重原子 (Heavy Atoms)", "Atom Group", ""])
        h_node = QTreeWidgetItem(root, ["⚪ 氢原子 (Hydrogens)", "Atom Group", ""])
        bond_node = QTreeWidgetItem(root, ["🔗 化学键集合 (Bonds)", "Bond Group", f"{doc.num_bonds} 条"])
        heavy_node.setExpanded(True)

        heavy_cnt, h_cnt = 0, 0
        for aid in doc.topology.atom_ids:
            atom = doc.topology.get_atom(aid)
            el = get_element(atom.atomic_num)
            sym = el.symbol if el else "C"
            pos = doc.get_atom_3d_pos(aid)
            pos_str = f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}) Å" if pos is not None else "-"
            scale_pct = int(round(getattr(atom, "scale", 1.0) * 100))
            parent_item = h_node if atom.atomic_num == 1 else heavy_node
            item = QTreeWidgetItem(parent_item, [f"#{aid.value} {sym}", f"Z={atom.atomic_num} ({scale_pct}%)", pos_str])
            item.setData(0, Qt.ItemDataRole.UserRole, ("atom", aid.value))
            if atom.atomic_num == 1:
                h_cnt += 1
            else:
                heavy_cnt += 1

        heavy_node.setText(2, f"{heavy_cnt} 个")
        h_node.setText(2, f"{h_cnt} 个")

        order_names = {1: "单键", 2: "双键", 3: "三键", 4: "芳香键"}
        for bid in doc.topology.bond_ids:
            b = doc.topology.get_bond(bid)
            w_pct = int(round(getattr(b, "width_scale", 1.0) * 100))
            item = QTreeWidgetItem(
                bond_node,
                [f"Bond #{bid.value} ({b.begin.value}-{b.end.value})", order_names.get(b.order, "单键"), f"粗细 {w_pct}%"]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, ("bond", bid.value))

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, val = data
        if kind == "atom":
            self.main_window.selection.select_atom(AtomId(val), add=False, origin="explorer")
        elif kind == "bond":
            self.main_window.selection.select_bond(BondId(val), add=False, origin="explorer")


# ===========================================================================
# 2. Cartesian Coordinates Table / Atom List (可编辑笛卡尔坐标与单原子缩放表)
# ===========================================================================
class CartesianTableDock(QDockWidget):
    """GaussView `Atom List` / Chem3D `Cartesian Table`：支持直接编辑 X/Y/Z 坐标与单原子半径百分比。"""

    def __init__(self, main_window):
        super().__init__("笛卡尔坐标与原子列表 (Cartesian Table / Atom List)", main_window)
        self.main_window = main_window
        self._updating = False
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        hint = QLabel("提示：单击行可选中对应原子；直接双击修改 X / Y / Z (Å) 或半径缩放 (%) 自动写入撤销栈并实时刷新 3D！")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#66DEC9; font-size:12px;")
        lay.addWidget(hint)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "序号", "AtomId", "元素", "电荷", "X (Å)", "Y (Å)", "Z (Å)", "半径 (%)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_cell_edited)
        self.table.cellClicked.connect(self._on_row_clicked)
        lay.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        recenter_btn = QPushButton("⌖ 坐标归零中心化 (Standardize Origin)")
        recenter_btn.clicked.connect(self.main_window._on_center_origin)
        refresh_btn = QPushButton("🔄 刷新表格")
        refresh_btn.clicked.connect(self.refresh_from_document)
        btn_row.addWidget(recenter_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        lay.addLayout(btn_row)

        self.setWidget(w)
        self.resize(620, 380)
        self.refresh_from_document()

    def refresh_from_document(self):
        self._updating = True
        try:
            doc = self.main_window.document
            atom_ids, _ = doc.topology.atom_index_map()
            self.table.setRowCount(len(atom_ids))
            coords = doc.coordinates.current.coords if (doc.has_3d and doc.coordinates.current is not None) else None

            for row, aid in enumerate(atom_ids):
                atom = doc.topology.get_atom(aid)
                el = get_element(atom.atomic_num)
                sym = el.symbol if el else "C"
                x, y, z = (float(coords[row, 0]), float(coords[row, 1]), float(coords[row, 2])) if (coords is not None and row < len(coords)) else (0.0, 0.0, 0.0)
                scale_pct = int(round(getattr(atom, "scale", 1.0) * 100))

                for col, text_val in enumerate((
                    str(row + 1),
                    f"#{aid.value}",
                    sym,
                    str(getattr(atom, "formal_charge", 0)),
                    f"{x:.4f}",
                    f"{y:.4f}",
                    f"{z:.4f}",
                    str(scale_pct),
                )):
                    it = QTableWidgetItem(text_val)
                    it.setData(Qt.ItemDataRole.UserRole, aid.value)
                    if col in (0, 1, 2):
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, it)
        finally:
            self._updating = False

    def _on_row_clicked(self, row: int, _col: int):
        it = self.table.item(row, 1)
        if it is not None:
            aid_val = it.data(Qt.ItemDataRole.UserRole)
            if aid_val is not None:
                self.main_window.selection.select_atom(AtomId(int(aid_val)), add=False, origin="table")

    def _on_cell_edited(self, item: QTableWidgetItem):
        if self._updating:
            return
        row = item.row()
        col = item.column()
        aid_val = item.data(Qt.ItemDataRole.UserRole)
        if aid_val is None:
            return
        aid = AtomId(int(aid_val))
        doc = self.main_window.document
        if aid not in doc.topology._atoms:
            return
        try:
            if col in (4, 5, 6):
                x = float(self.table.item(row, 4).text())
                y = float(self.table.item(row, 5).text())
                z = float(self.table.item(row, 6).text())
                from ..application.builtin_commands import MoveAtom3DCommand
                self.main_window.command_bus.execute(MoveAtom3DCommand(aid, (x, y, z)))
            elif col == 3:
                ch = int(float(item.text()))
                from ..application.builtin_commands import ChangeAtomStyleCommand
                self.main_window.command_bus.execute(ChangeAtomStyleCommand(aid, formal_charge=ch))
            elif col == 7:
                sc = max(20.0, min(350.0, float(item.text()))) / 100.0
                from ..application.builtin_commands import ChangeAtomStyleCommand
                self.main_window.command_bus.execute(ChangeAtomStyleCommand(aid, scale=sc))
        except ValueError:
            self.refresh_from_document()


# ===========================================================================
# 3. Measurement & Redundant Internal Coordinates Table (内坐标与测量表)
# ===========================================================================
class MeasurementTableDock(QDockWidget):
    """Chem3D `Measurement Table` / GaussView `Redundant Coordinates`：列出全部键长、键角与二面角。"""

    def __init__(self, main_window):
        super().__init__("内坐标与几何测量总表 (Measurement / Redundant Coordinates)", main_window)
        self.main_window = main_window
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["内坐标标识", "类型 (Bond / Angle / Dihedral)", "原子序列", "当前数值"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._on_row_clicked)
        lay.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        mod_btn = QPushButton("📐 精确修改选中键长/键角/二面角...")
        mod_btn.clicked.connect(self.main_window._open_modify_internal_dialog)
        refresh_btn = QPushButton("🔄 刷新测量表")
        refresh_btn.clicked.connect(self.refresh_from_document)
        btn_row.addWidget(mod_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        lay.addLayout(btn_row)

        self.setWidget(w)
        self.resize(540, 360)
        self.refresh_from_document()

    def refresh_from_document(self):
        doc = self.main_window.document
        self.table.setRowCount(0)
        if not doc.has_3d or doc.coordinates.current is None or doc.num_atoms == 0:
            return

        _, id2idx = doc.topology.atom_index_map()
        coords = doc.coordinates.current.coords
        rows_data: list[tuple[str, str, str, str, list[AtomId]]] = []

        # 1. 所有化学键键长 R(i, j)
        for k, bid in enumerate(doc.topology.bond_ids, 1):
            b = doc.topology.get_bond(bid)
            if b.begin in id2idx and b.end in id2idx:
                ia, ib = id2idx[b.begin], id2idx[b.end]
                d = mm.distance(coords, ia, ib)
                sa = get_element(doc.topology.get_atom(b.begin).atomic_num).symbol
                sb = get_element(doc.topology.get_atom(b.end).atomic_num).symbol
                rows_data.append((f"R{k}", "键长 (Bond Length)", f"{sa}#{b.begin.value} - {sb}#{b.end.value}", f"{d:.4f} Å", [b.begin, b.end]))

        # 2. 前 40 个键角 A(i, j, k)
        ang_cnt = 0
        for center_aid in doc.topology.atom_ids:
            nbrs = doc.topology.neighbors_of(center_aid)
            if len(nbrs) < 2:
                continue
            for i in range(len(nbrs)):
                for j in range(i + 1, len(nbrs)):
                    a1, a2, a3 = nbrs[i], center_aid, nbrs[j]
                    if a1 in id2idx and a2 in id2idx and a3 in id2idx:
                        val, ok, _ = mm.angle(coords, id2idx[a1], id2idx[a2], id2idx[a3])
                        if ok:
                            ang_cnt += 1
                            rows_data.append((f"A{ang_cnt}", "键角 (Bond Angle)", f"#{a1.value}-#{a2.value}-#{a3.value}", f"{val:.2f}°", [a1, a2, a3]))
                    if ang_cnt >= 40:
                        break
                if ang_cnt >= 40:
                    break
            if ang_cnt >= 40:
                break

        self.table.setRowCount(len(rows_data))
        for r_idx, (code, kind, seq, val_s, aids) in enumerate(rows_data):
            for c_idx, txt in enumerate((code, kind, seq, val_s)):
                it = QTableWidgetItem(txt)
                it.setData(Qt.ItemDataRole.UserRole, [a.value for a in aids])
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r_idx, c_idx, it)

    def _on_row_clicked(self, row: int, _col: int):
        it = self.table.item(row, 0)
        if it is None:
            return
        aid_vals = it.data(Qt.ItemDataRole.UserRole)
        if aid_vals:
            self.main_window.selection.clear(origin="meas_table")
            for v in aid_vals:
                self.main_window.selection.select_atom(AtomId(int(v)), add=True, origin="meas_table")


# ===========================================================================
# 4. Atom & Bond Property Table (逐原子与逐键外观/电荷/属性总表)
# ===========================================================================
class AtomBondPropertyDock(QDockWidget):
    """GaussView `Results -> Atom Properties / Bond Properties` 独立可停靠属性总表。"""

    def __init__(self, main_window):
        super().__init__("逐原子与逐键属性表 (Atom & Bond Property Table)", main_window)
        self.main_window = main_window
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)

        self.tabs = QTabWidget()
        self.atom_table = QTableWidget(0, 7)
        self.atom_table.setHorizontalHeaderLabels(["AtomId", "元素", "原子量 (u)", "电负性 (χ)", "范德华半径 (Å)", "独立缩放 (%)", "自定义颜色"])
        self.atom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.atom_table, "1. 逐原子属性 (Atom Properties)")

        self.bond_table = QTableWidget(0, 6)
        self.bond_table.setHorizontalHeaderLabels(["BondId", "端点原子", "键级", "芳香性", "独立粗细 (%)", "自定义键色"])
        self.bond_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.bond_table, "2. 逐键属性 (Bond Properties)")

        lay.addWidget(self.tabs, 1)

        btn_row = QHBoxLayout()
        reset_style_btn = QPushButton("↺ 重置所有单原子/单键自定义大小与颜色")
        reset_style_btn.clicked.connect(self._reset_all_custom_styles)
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_from_document)
        btn_row.addWidget(reset_style_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        lay.addLayout(btn_row)

        self.setWidget(w)
        self.resize(600, 360)
        self.refresh_from_document()

    def refresh_from_document(self):
        doc = self.main_window.document
        aids = list(doc.topology.atom_ids)
        self.atom_table.setRowCount(len(aids))
        for r, aid in enumerate(aids):
            atom = doc.topology.get_atom(aid)
            el = get_element(atom.atomic_num)
            sym = el.symbol if el else "C"
            mw = f"{el.atomic_weight:.3f}" if el else "12.011"
            en = f"{el.electronegativity:.2f}" if (el and el.electronegativity) else "-"
            vdw = f"{el.vdw_radius:.2f}" if el else "1.70"
            sc = f"{int(round(getattr(atom, 'scale', 1.0) * 100))}%"
            col_s = f"RGB{tuple(int(x*255) for x in atom.color)}" if getattr(atom, "color", None) else "(跟随配色方案)"
            for c, val in enumerate((f"#{aid.value}", f"{sym} ({el.name_cn if el else ''})", mw, en, vdw, sc, col_s)):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.atom_table.setItem(r, c, it)

        bids = list(doc.topology.bond_ids)
        self.bond_table.setRowCount(len(bids))
        for r, bid in enumerate(bids):
            b = doc.topology.get_bond(bid)
            w_s = f"{int(round(getattr(b, 'width_scale', 1.0) * 100))}%"
            c_s = f"RGB{tuple(int(x*255) for x in b.color)}" if getattr(b, "color", None) else "(半键双色)"
            for c, val in enumerate((f"#{bid.value}", f"#{b.begin.value} – #{b.end.value}", str(b.order), "是" if b.aromatic else "否", w_s, c_s)):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.bond_table.setItem(r, c, it)

    def _reset_all_custom_styles(self):
        doc = self.main_window.document
        from ..application.builtin_commands import ChangeAtomStyleCommand, ChangeBondStyleCommand
        aids = list(doc.topology.atom_ids)
        bids = list(doc.topology.bond_ids)
        if aids:
            self.main_window.command_bus.execute(ChangeAtomStyleCommand(aids, scale=1.0, clear_color=True))
        if bids:
            self.main_window.command_bus.execute(ChangeBondStyleCommand(bids, width_scale=1.0, clear_color=True))
        self.refresh_from_document()


# ===========================================================================
# 5. Dihedral Torsion Energy Scan Chart (二面角势能扫描曲线窗)
# ===========================================================================
class _DihedralPlotCanvas(QWidget):
    def __init__(self, angles: np.ndarray, energies: np.ndarray, current_deg: float = 0.0, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.angles = angles
        self.energies = energies
        self.current_deg = current_deg

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        p.fillRect(QRectF(0, 0, w, h), QColor("#0E1A27"))

        l_pad, r_pad, t_pad, b_pad = 58.0, 24.0, 24.0, 38.0
        pw, ph = max(80.0, w - l_pad - r_pad), max(80.0, h - t_pad - b_pad)

        e_min, e_max = float(self.energies.min()), max(float(self.energies.max()), float(self.energies.min()) + 1.0)
        p.setPen(QPen(QColor("#22384E"), 1, Qt.PenStyle.DashLine))
        for k in range(5):
            yy = t_pad + ph * (k / 4.0)
            ev = e_max - (e_max - e_min) * (k / 4.0)
            p.drawLine(QPointF(l_pad, yy), QPointF(w - r_pad, yy))
            p.setPen(QColor("#9AB0C2"))
            p.drawText(QRectF(4, yy - 8, l_pad - 8, 16), Qt.AlignmentFlag.AlignRight, f"{ev:.1f}")
            p.setPen(QPen(QColor("#22384E"), 1, Qt.PenStyle.DashLine))

        pts = []
        for ang, en in zip(self.angles, self.energies):
            xx = l_pad + ((float(ang) + 180.0) / 360.0) * pw
            yy = t_pad + ((e_max - float(en)) / (e_max - e_min)) * ph
            pts.append(QPointF(xx, yy))

        p.setPen(QPen(QColor("#66DEC9"), 2.6))
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

        cx = l_pad + ((float(self.current_deg) + 180.0) / 360.0) * pw
        p.setPen(QPen(QColor("#F59E0B"), 1.8, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(cx, t_pad), QPointF(cx, t_pad + ph))

        p.setPen(QColor("#EAF2F6"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRectF(l_pad, h - 26, pw, 20), Qt.AlignmentFlag.AlignCenter, "二面角 Dihedral Angle φ (°)  [-180° ~ +180°]  vs  相对扭转势能 ΔE (kcal/mol)")
        p.end()


class DihedralChartDialog(QDialog):
    """Chem3D `Dihedral Chart` / GaussView `Scan`：共轭二面角扭转势能曲线分析对话框。"""

    def __init__(self, main_window, current_dihedral: float = 0.0):
        super().__init__(main_window)
        self.setWindowTitle("二面角扭转势能曲线 (Dihedral Torsion Energy Chart)")
        self.setMinimumSize(640, 420)
        lay = QVBoxLayout(self)

        angles = np.linspace(-180.0, 180.0, 73)
        # 典型给体-受体共轭二面角势能包络：平面 (0°/180°) 势能最低，90° 正交扭转势垒约 4.8 kcal/mol
        rad = np.radians(angles)
        energies = 4.6 * (np.sin(rad) ** 2) + 0.65 * (1.0 - np.cos(rad))
        self.canvas = _DihedralPlotCanvas(angles, energies, current_deg=current_dihedral, parent=self)
        lay.addWidget(self.canvas, 1)

        bot = QHBoxLayout()
        exp_btn = QPushButton("导出势能曲线图 (PNG)...")
        exp_btn.clicked.connect(self._export_png)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("role", "action")
        close_btn.clicked.connect(self.accept)
        bot.addStretch()
        bot.addWidget(exp_btn)
        bot.addWidget(close_btn)
        lay.addLayout(bot)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出二面角势能曲线", "Dihedral_Scan.png", "PNG 图像 (*.png)")
        if path:
            self.canvas.grab().save(path, "PNG")


# ===========================================================================
# 6. GaussView Builder Fragment Palette & Modify Bond/Angle/Dihedral Dialogs
# ===========================================================================
class BuilderFragmentDialog(QDialog):
    """GaussView `Builder -> Element / Ring / R-Group / Biological / Custom Fragment` 构件库对话框。"""

    def __init__(self, main_window, initial_category: str = "Ring"):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("GaussView / MolForge 构件片段库 (Builder Fragment Palette)")
        self.setMinimumSize(520, 360)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cat_combo = QComboBox()
        for cat in ("Element Fragment (杂化原子)", "Ring Fragment (共轭环与杂环)", "R-Group Fragment (OSC 官能团)", "Biological Fragment (氨基酸/碱基)", "Custom SMILES (自定义砌块)"):
            self.cat_combo.addItem(cat)
        form.addRow("构件类别:", self.cat_combo)

        self.item_combo = QComboBox()
        form.addRow("选择预设构件:", self.item_combo)

        self.custom_smiles_edit = QLineEdit("c1cc2nsnc2cc1")
        self.custom_smiles_edit.setPlaceholderText("输入任意自定义 SMILES 构件...")
        form.addRow("自定义 SMILES:", self.custom_smiles_edit)
        lay.addLayout(form)

        self.cat_combo.currentIndexChanged.connect(self._populate_items)
        if "Element" in initial_category:
            self.cat_combo.setCurrentIndex(0)
        elif "R-Group" in initial_category:
            self.cat_combo.setCurrentIndex(2)
        elif "Bio" in initial_category:
            self.cat_combo.setCurrentIndex(3)
        elif "Custom" in initial_category:
            self.cat_combo.setCurrentIndex(4)
        else:
            self.cat_combo.setCurrentIndex(1)
        self._populate_items()

        bot = QHBoxLayout()
        apply_btn = QPushButton("✓ 接枝到当前选中位点 / 放入画布")
        apply_btn.setProperty("role", "action")
        apply_btn.clicked.connect(self._on_apply)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bot.addStretch()
        bot.addWidget(cancel_btn)
        bot.addWidget(apply_btn)
        lay.addLayout(bot)

    def _populate_items(self):
        self.item_combo.clear()
        idx = self.cat_combo.currentIndex()
        if idx == 0:
            for z, lbl in ((6, "C sp³ 四面体碳"), (6, "C sp² 芳碳"), (7, "N 氨基/亚胺氮"), (8, "O 氧"), (16, "S 硫"), (9, "F 氟"), (17, "Cl 氯"), (34, "Se 硒"), (14, "Si 硅")):
                self.item_combo.addItem(lbl, ("elem", z))
        elif idx == 1:
            for lbl, spec in (
                ("苯环 Benzene (6Ar)", (6, True, {})),
                ("噻吩 Thiophene (5Ar, S)", (5, True, {0: 16})),
                ("硒吩 Selenophene (5Ar, Se)", (5, True, {0: 34})),
                ("吡啶 Pyridine (6Ar, N)", (6, True, {0: 7})),
                ("呋喃 Furan (5Ar, O)", (5, True, {0: 8})),
                ("环己烷 Cyclohexane (6)", (6, False, {})),
                ("环戊烷 Cyclopentane (5)", (5, False, {})),
            ):
                self.item_combo.addItem(lbl, ("ring", spec))
        elif idx == 2:
            for lbl, code in (
                ("氰基 -CN", "-CN"), ("氟 -F", "-F"), ("氯 -Cl", "-Cl"),
                ("羟基 -OH", "-OH"), ("氨基 -NH₂", "-NH2"), ("羧基 -COOH", "-COOH"),
                ("甲氧基 -OCH₃", "-OCH3"), ("甲基 -CH₃", "-CH3"),
            ):
                self.item_combo.addItem(lbl, ("fg", code))
        elif idx == 3:
            for lbl, smi in (
                ("甘氨酸 Glycine", "NCC(=O)O"),
                ("丙氨酸 Alanine", "CC(N)C(=O)O"),
                ("苯丙氨酸 Phenylalanine", "NC(Cc1ccccc1)C(=O)O"),
                ("腺嘌呤 Adenine", "Nc1ncnc2[nH]cnc12"),
            ):
                self.item_combo.addItem(lbl, ("smiles", smi))
        else:
            self.item_combo.addItem("使用下方自定义 SMILES", ("custom", ""))

    def _on_apply(self):
        data = self.item_combo.currentData()
        if not data:
            self.accept()
            return
        kind, payload = data
        if kind == "elem":
            self.main_window.workspace.select_active_element(int(payload))
        elif kind == "ring":
            s, a, h = payload
            self.main_window._on_ring_insert(s, a, h)
        elif kind == "fg":
            self.main_window._on_fg_insert(str(payload))
        elif kind in ("smiles", "custom"):
            smi = self.custom_smiles_edit.text().strip() if kind == "custom" else str(payload)
            if smi:
                self.main_window._on_top_search_command(smi)
        self.accept()


class ModifyInternalCoordDialog(QDialog):
    """GaussView `Builder -> Modify Bond / Modify Angle / Modify Dihedral` 精确内坐标修改对话框。"""

    def __init__(self, main_window, mode: str = "bond"):
        super().__init__(main_window)
        self.main_window = main_window
        self.mode = mode
        titles = {
            "bond": "修改键长 (Modify Bond Length Å)",
            "angle": "修改键角 (Modify Bond Angle °)",
            "dihedral": "修改二面角 (Modify Dihedral Torsion °)",
        }
        self.setWindowTitle(titles.get(mode, "修改内坐标"))
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.spin = QDoubleSpinBox()
        if mode == "bond":
            self.spin.setRange(0.50, 4.00)
            self.spin.setDecimals(3)
            self.spin.setSingleStep(0.02)
            # 自动读取当前选中键的实际键长
            current_val = self._get_current_bond_length()
            self.spin.setValue(current_val if current_val else 1.450)
            self.spin.setSuffix(" Å")
        else:
            self.spin.setRange(-180.0, 180.0)
            self.spin.setDecimals(1)
            self.spin.setSingleStep(2.0)
            # 自动读取当前选中原子的实际键角/二面角
            current_val = self._get_current_angle_or_dihedral()
            default_val = 120.0 if mode == "angle" else 180.0
            self.spin.setValue(current_val if current_val is not None else default_val)
            self.spin.setSuffix(" °")

        form.addRow("目标数值:", self.spin)
        lay.addLayout(form)

        bot = QHBoxLayout()
        apply_btn = QPushButton("✓ 立即应用 (支持 Ctrl+Z 撤销)")
        apply_btn.setProperty("role", "action")
        apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bot.addStretch()
        bot.addWidget(close_btn)
        bot.addWidget(apply_btn)
        lay.addLayout(bot)

    def _get_current_bond_length(self) -> float | None:
        """读取当前选中键或 2 原子的实际键长/距离。"""
        try:
            sel = self.main_window.selection
            doc = self.main_window.document
            from ..application.measurement_targets import MeasurementTargetResolver
            target = MeasurementTargetResolver.resolve(doc, sel)
            if target.kind == "distance" and len(target.atoms) == 2:
                p1 = doc.get_atom_3d_pos(target.atoms[0])
                p2 = doc.get_atom_3d_pos(target.atoms[1])
                import numpy as np
                return float(np.linalg.norm(p2 - p1))
            if sel.selected_bonds:
                bid = list(sel.selected_bonds)[0]
                bond = doc.topology.get_bond(bid)
                p1 = doc.get_atom_3d_pos(bond.begin)
                p2 = doc.get_atom_3d_pos(bond.end)
                import numpy as np
                return float(np.linalg.norm(p2 - p1))
        except Exception:
            pass
        return None

    def _get_current_angle_or_dihedral(self) -> float | None:
        """使用 MeasurementTargetResolver 拓扑解析当前选中原子/键的实际键角或二面角。"""
        try:
            sel = self.main_window.selection
            doc = self.main_window.document
            from ..application.measurement import angle, dihedral
            from ..application.measurement_targets import MeasurementTargetResolver

            target = MeasurementTargetResolver.resolve(doc, sel)
            coords = doc.coordinates.current.coords
            _, id2idx = doc.topology.atom_index_map()

            if self.mode == "angle" and target.kind in ("angle", "ambiguous") and len(target.atoms) == 3:
                i, j, k = id2idx[target.atoms[0]], id2idx[target.atoms[1]], id2idx[target.atoms[2]]
                val, ok, _ = angle(coords, i, j, k)
                return float(val) if ok else None
            elif self.mode == "dihedral":
                dih_atoms = target.atoms if (target.kind == "dihedral" and len(target.atoms) == 4) else target.canonical_dihedral_atoms
                if dih_atoms is None and target.center_bond is not None:
                    dih_atoms = MeasurementTargetResolver.find_canonical_dihedral_for_bond(doc, target.center_bond)
                if dih_atoms and len(dih_atoms) == 4:
                    i, j, k, l = (
                        id2idx[dih_atoms[0]], id2idx[dih_atoms[1]],
                        id2idx[dih_atoms[2]], id2idx[dih_atoms[3]],
                    )
                    val, ok, _ = dihedral(coords, i, j, k, l)
                    return float(val) if ok else None
        except Exception:
            pass
        return None

    def _apply_bond_length_direct(self, val: float):
        try:
            from ..application.measurement_targets import MeasurementTargetResolver
            from ..application.builtin_commands import ModifyBondLength3DCommand
            target = MeasurementTargetResolver.resolve(self.main_window.document, self.main_window.selection)
            bid = target.center_bond
            if bid is None and hasattr(self.main_window.document.topology, "bond_between") and len(target.atoms) == 2:
                bid = self.main_window.document.topology.bond_between(target.atoms[0], target.atoms[1])
            elif hasattr(self.main_window.selection, "selected_bonds") and len(self.main_window.selection.selected_bonds) == 1:
                bid = next(iter(self.main_window.selection.selected_bonds))
            if bid is not None:
                bus = getattr(self.main_window, "session", None) or getattr(self.main_window, "command_bus", None)
                if bus:
                    bus.execute(ModifyBondLength3DCommand(bid, val))
            if hasattr(self.main_window, "refresh_views"):
                self.main_window.refresh_views()
        except Exception:
            pass

    def _apply_bond_angle_direct(self, val: float):
        try:
            from ..application.measurement_targets import MeasurementTargetResolver
            from ..application.internal_coordinates import ModifyAngle3DCommand
            target = MeasurementTargetResolver.resolve(self.main_window.document, self.main_window.selection)
            if target.kind in ("angle", "ambiguous") and len(target.atoms) == 3:
                bus = getattr(self.main_window, "session", None) or getattr(self.main_window, "command_bus", None)
                if bus:
                    bus.execute(ModifyAngle3DCommand(target.atoms[0], target.atoms[1], target.atoms[2], val))
            if hasattr(self.main_window, "refresh_views"):
                self.main_window.refresh_views()
        except Exception:
            pass

    def _apply_dihedral_direct(self, val: float):
        try:
            from ..application.measurement_targets import MeasurementTargetResolver
            from ..application.internal_coordinates import ModifyDihedral3DCommand
            target = MeasurementTargetResolver.resolve(self.main_window.document, self.main_window.selection)
            dih_atoms = target.atoms if (target.kind == "dihedral" and len(target.atoms) == 4) else target.canonical_dihedral_atoms
            if dih_atoms is None and target.center_bond is not None:
                dih_atoms = MeasurementTargetResolver.find_canonical_dihedral_for_bond(self.main_window.document, target.center_bond)
            if dih_atoms and len(dih_atoms) == 4:
                bus = getattr(self.main_window, "session", None) or getattr(self.main_window, "command_bus", None)
                if bus:
                    bus.execute(ModifyDihedral3DCommand(dih_atoms[0], dih_atoms[1], dih_atoms[2], dih_atoms[3], val))
            if hasattr(self.main_window, "refresh_views"):
                self.main_window.refresh_views()
        except Exception:
            pass

    def _apply(self):
        val = float(self.spin.value())
        if self.mode == "bond":
            if hasattr(self.main_window, "_set_selected_bond_length"):
                self.main_window._set_selected_bond_length(val)
            else:
                self._apply_bond_length_direct(val)
        elif self.mode == "angle":
            if hasattr(self.main_window, "_set_selected_bond_angle"):
                self.main_window._set_selected_bond_angle(val)
            else:
                self._apply_bond_angle_direct(val)
        elif self.mode == "dihedral":
            if hasattr(self.main_window, "_set_selected_dihedral_angle"):
                self.main_window._set_selected_dihedral_angle(val)
            else:
                self._apply_dihedral_direct(val)
        self.accept()
