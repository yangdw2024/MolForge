"""
ui/dialogs/calchem_orbitals_dialog.py - CalChem 原生分子轨道能级阶梯与 3D 等值面一体化工作台
========================================================================================
功能：
  1. 一键运行 CalChem 纯 Rust 从头算 RHF/UHF 自洽场计算
  2. 交互式分子轨道能级列表（包含全部已占轨道、未占轨道、HOMO/LUMO 标记及能隙）
  3. 双击或点击任意轨道行，视口即时零拷贝渲染正负相位 3D 等值面
  4. 支持导出标准 Gaussian .cube 网格文件
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDoubleSpinBox, QMessageBox, QFrame, QFileDialog
)
from PyQt6.QtGui import QColor, QFont

from ...domain.document import MoleculeDocument
from ...io.calchem_bridge import (
    probe_calchem,
    run_calchem_single_point,
    get_calchem_orbital_cube_data,
    get_supported_basis_sets,
)


class CalChemOrbitalsDialog(QDialog):
    """CalChem 纯 Rust 分子轨道能级阶梯与 3D 渲染控制面板。"""

    def __init__(self, main_window, document: MoleculeDocument, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.document = document
        self.wf: Any = None
        self.cube_cache: dict[int, Any] = {}

        self.setWindowTitle(f"CalChem 原生分子轨道工作台 - {document.name}")
        self.resize(760, 580)
        self.setMinimumSize(680, 480)

        self._build_ui()
        # 初始自动计算一次
        self._on_calculate_scf()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 顶部配置栏
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>计算基组 (Basis):</b>"))
        self.basis_combo = QComboBox()
        for b in get_supported_basis_sets():
            self.basis_combo.addItem(b.upper(), b)
        top_bar.addWidget(self.basis_combo)

        top_bar.addSpacing(16)
        top_bar.addWidget(QLabel("等值面截断 (Isovalue):"))
        self.isovalue_spin = QDoubleSpinBox()
        self.isovalue_spin.setRange(0.005, 0.200)
        self.isovalue_spin.setDecimals(3)
        self.isovalue_spin.setSingleStep(0.005)
        self.isovalue_spin.setValue(0.030)
        top_bar.addWidget(self.isovalue_spin)

        top_bar.addSpacing(16)
        self.recalc_btn = QPushButton("⚡ 重新自洽求解 (Solve SCF)")
        self.recalc_btn.setProperty("role", "action")
        self.recalc_btn.clicked.connect(self._on_calculate_scf)
        top_bar.addWidget(self.recalc_btn)
        top_bar.addStretch()
        root.addLayout(top_bar)

        # 摘要信息栏
        self.summary_box = QFrame()
        self.summary_box.setStyleSheet("background-color: #121E2B; border-radius: 6px; padding: 6px;")
        s_lay = QHBoxLayout(self.summary_box)
        self.lbl_energy = QLabel("总能量: --")
        self.lbl_homo_lumo = QLabel("HOMO / LUMO: --")
        self.lbl_gap = QLabel("能隙 (Gap): --")
        self.lbl_dipole = QLabel("偶极矩: --")
        for lbl in (self.lbl_energy, self.lbl_homo_lumo, self.lbl_gap, self.lbl_dipole):
            lbl.setStyleSheet("color: #E2E8F0; font-size: 12px;")
            s_lay.addWidget(lbl)
            s_lay.addStretch()
        root.addWidget(self.summary_box)

        # 轨道能级表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "轨道序号 (MO #)", "类型 (Type)", "能级 (Hartree)", "能级 (eV)", "科学标识 (Label)"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 1)

        # 底部操作栏
        bot = QHBoxLayout()
        self.render_btn = QPushButton("👁 渲染所选轨道 3D 等值面")
        self.render_btn.setProperty("role", "action")
        self.render_btn.clicked.connect(self._on_render_selected)
        bot.addWidget(self.render_btn)

        self.clear_orb_btn = QPushButton("清除视口轨道")
        self.clear_orb_btn.clicked.connect(self._on_clear_orbital)
        bot.addWidget(self.clear_orb_btn)

        self.export_cube_btn = QPushButton("导出标准 Gaussian .cube 网格...")
        self.export_cube_btn.clicked.connect(self._on_export_cube)
        bot.addWidget(self.export_cube_btn)

        bot.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)
        root.addLayout(bot)

    def _on_calculate_scf(self) -> None:
        if not probe_calchem():
            QMessageBox.warning(self, "内核未就绪", "未检测到 CalChem 原生扩展 (_core.pyd)。")
            return
        basis = self.basis_combo.currentData()
        self.recalc_btn.setEnabled(False)
        self.recalc_btn.setText("正在求解波函数...")

        try:
            res = run_calchem_single_point(self.document, basis=basis)
            if not res.get("success"):
                QMessageBox.warning(self, "自洽场求解失败", str(res.get("error")))
                return

            self.wf = res["wavefunction"]
            self.cube_cache.clear()

            # 更新摘要
            e_tot = res["total_energy_hartree"]
            h_e = res["homo_energy_hartree"]
            l_e = res["lumo_energy_hartree"]
            gap = res["gap_ev"]
            dip = res["dipole_magnitude_debye"]

            self.lbl_energy.setText(f"<b>总能量:</b> {e_tot:.6f} Hartree")
            self.lbl_homo_lumo.setText(f"<b>HOMO/LUMO:</b> {h_e:.4f} / {l_e:.4f} a.u.")
            self.lbl_gap.setText(f"<b>能隙:</b> {gap:.3f} eV")
            self.lbl_dipole.setText(f"<b>偶极矩:</b> {dip:.2f} Debye")

            # 填充表格
            self._populate_table()
        finally:
            self.recalc_btn.setEnabled(True)
            self.recalc_btn.setText("⚡ 重新自洽求解 (Solve SCF)")

    def _populate_table(self) -> None:
        if not self.wf:
            return
        self.table.setRowCount(0)
        n_ao = self.wf.n_ao
        n_alpha = self.wf.n_alpha
        energies = list(self.wf.mo_energies)

        homo_idx = n_alpha - 1
        lumo_idx = n_alpha

        self.table.setRowCount(n_ao)
        for i in range(n_ao):
            e_h = energies[i] if i < len(energies) else 0.0
            e_ev = e_h * 27.211386245988
            is_occ = i <= homo_idx

            if i == homo_idx:
                label = "⭐ HOMO (最高占据轨道)"
                bg_col = QColor("#0F3D3E")
                fg_col = QColor("#66DEC9")
            elif i == lumo_idx:
                label = "⭐ LUMO (最低未占轨道)"
                bg_col = QColor("#3D2614")
                fg_col = QColor("#FBBF24")
            elif i < homo_idx:
                diff = homo_idx - i
                label = f"HOMO-{diff}" if diff <= 3 else "Occupied"
                bg_col = QColor("#0E1A27")
                fg_col = QColor("#93C5FD")
            else:
                diff = i - lumo_idx
                label = f"LUMO+{diff}" if diff <= 3 else "Virtual"
                bg_col = QColor("#18141F")
                fg_col = QColor("#F87171")

            type_str = "已占轨道 (Occupied)" if is_occ else "虚轨道 (Virtual)"

            item_idx = QTableWidgetItem(f"MO #{i + 1}")
            item_type = QTableWidgetItem(type_str)
            item_eh = QTableWidgetItem(f"{e_h:.6f}")
            item_eev = QTableWidgetItem(f"{e_ev:.3f}")
            item_lbl = QTableWidgetItem(label)

            for it in (item_idx, item_type, item_eh, item_eev, item_lbl):
                it.setBackground(bg_col)
                it.setForeground(fg_col)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setData(Qt.ItemDataRole.UserRole, i)

            self.table.setItem(i, 0, item_idx)
            self.table.setItem(i, 1, item_type)
            self.table.setItem(i, 2, item_eh)
            self.table.setItem(i, 3, item_eev)
            self.table.setItem(i, 4, item_lbl)

        # 默认选中 HOMO
        if 0 <= homo_idx < n_ao:
            self.table.selectRow(homo_idx)

    def _on_selection_changed(self) -> None:
        pass

    def _on_table_double_clicked(self, item: QTableWidgetItem) -> None:
        self._on_render_selected()

    def _on_render_selected(self) -> None:
        sel_rows = self.table.selectionModel().selectedRows()
        if not sel_rows:
            return
        row = sel_rows[0].row()
        mo_idx = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        basis = self.basis_combo.currentData()
        iso = float(self.isovalue_spin.value())

        # 生成或提取 CubeData
        if mo_idx not in self.cube_cache:
            cube = get_calchem_orbital_cube_data(self.document, mo_idx=mo_idx, basis=basis)
            if cube is None:
                QMessageBox.warning(self, "渲染失败", f"无法生成 MO #{mo_idx + 1} 的体数据。")
                return
            self.cube_cache[mo_idx] = cube

        cube = self.cube_cache[mo_idx]

        # 直接调度视口渲染器
        view = getattr(self.main_window, "workspace", None)
        if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
            view.view3d_real.renderer.set_orbital(cube, isovalue=iso)
            if hasattr(self.main_window, "status_left"):
                self.main_window.status_left.setText(
                    f"[{self.main_window.group_tag}] 已秒级直通渲染 CalChem MO #{mo_idx + 1} 3D 等值面 (Iso={iso:.3f})"
                )
        elif hasattr(self.main_window, "renderer"):
            self.main_window.renderer.set_orbital(cube, isovalue=iso)

    def _on_clear_orbital(self) -> None:
        view = getattr(self.main_window, "workspace", None)
        if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
            view.view3d_real.renderer.clear_orbital()
        elif hasattr(self.main_window, "renderer"):
            self.main_window.renderer.clear_orbital()

    def _on_export_cube(self) -> None:
        sel_rows = self.table.selectionModel().selectedRows()
        if not sel_rows or not self.wf:
            return
        row = sel_rows[0].row()
        mo_idx = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        fn, _ = QFileDialog.getSaveFileName(
            self, "导出 Gaussian Cube 文件", f"{self.document.name}_mo_{mo_idx + 1}.cube", "Cube Files (*.cube)"
        )
        if not fn:
            return

        try:
            from calchem import _core
            cube_str = _core.export_orbital_gaussian_cube(self.wf, mo_idx=mo_idx)
            with open(fn, "w", encoding="utf-8") as f:
                f.write(cube_str)
            QMessageBox.information(self, "导出成功", f"标准 Cube 文件已写入:\n{fn}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
