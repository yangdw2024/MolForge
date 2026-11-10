"""
ui/dialogs/aim_qtaim_dialog.py - Multiwfn 量化波函数与电子结构深度分析工作台
========================================================================
集成 Tian Lu 教授 Multiwfn 核心模块：
  1. QTAIM 拓扑临界点 (BCP/RCP/CCP) 与 3D 梯度键径
  2. NCI / RDG 弱相互作用 (从头算波函数或原初分子密度近似)
  3. ELF / LOL / ESP 空间网格等值面
  4. ADCH / Hirshfeld 原子净电荷与分子偶极
  5. Mayer 键级分析与原子总价
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDoubleSpinBox, QMessageBox, QFileDialog, QGroupBox, QProgressBar
)
from PyQt6.QtGui import QColor

from molforge.io.multiwfn_driver import MultiwfnDriver, QTAIMResult, NCIResult, PopulationResult, MayerBondOrderResult


class _MultiwfnWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, task_fn):
        super().__init__()
        self.task_fn = task_fn

    def run(self):
        try:
            res = self.task_fn()
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class AIMQTAIMDialog(QDialog):
    """Multiwfn 波函数分析控制面板。"""

    def __init__(self, main_window, document=None, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.document = document
        self.driver = MultiwfnDriver()

        self.loaded_file: Optional[Path] = None
        self.qtaim_result: Optional[QTAIMResult] = None
        self.nci_result: Optional[NCIResult] = None
        self.pop_result: Optional[PopulationResult] = None
        self.bo_result: Optional[MayerBondOrderResult] = None

        doc_name = getattr(document, "name", "当前分子")
        self.setWindowTitle(f"Multiwfn 波函数与电子结构深度分析 · {doc_name}")
        self.resize(880, 640)
        self.setMinimumSize(780, 520)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 顶部文件与环境状态条
        top_bar = QHBoxLayout()
        self.lbl_exec = QLabel()
        if self.driver.is_available:
            self.lbl_exec.setText(f"🟢 Multiwfn: {self.driver.executable_path.name}")
            self.lbl_exec.setStyleSheet("color: #4CAF50; font-size: 11px;")
        else:
            self.lbl_exec.setText("🔴 未检测到 Multiwfn.exe (可在系统 PATH 或 D:\\Multiwfn\\ 配置)")
            self.lbl_exec.setStyleSheet("color: #F44336; font-size: 11px;")
        top_bar.addWidget(self.lbl_exec)
        top_bar.addSpacing(12)

        self.btn_select_file = QPushButton("📁 打开波函数文件 (.wfn / .fchk / .molden / .xyz)...")
        self.btn_select_file.clicked.connect(self._select_file)
        top_bar.addWidget(self.btn_select_file)

        self.btn_use_current = QPushButton("⚛ 使用当前画布分子 (Promolecular)")
        self.btn_use_current.clicked.connect(self._use_current_doc)
        top_bar.addWidget(self.btn_use_current)
        top_bar.addStretch()

        root.addLayout(top_bar)

        self.lbl_active_file = QLabel("当前输入源: 尚未指定")
        self.lbl_active_file.setStyleSheet("color: #90CAF9; font-weight: bold; font-size: 12px;")
        root.addWidget(self.lbl_active_file)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        root.addWidget(self.progress_bar)

        # 选项卡分类
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_qtaim_tab(), "1. QTAIM 拓扑临界点与键径")
        self.tabs.addTab(self._build_nci_tab(), "2. NCI / RDG 弱相互作用")
        self.tabs.addTab(self._build_elf_tab(), "3. ELF / LOL 空间网格")
        self.tabs.addTab(self._build_pop_tab(), "4. ADCH / 赫氏电荷与偶极")
        self.tabs.addTab(self._build_bo_tab(), "5. Mayer 键级分析")
        root.addWidget(self.tabs, 1)

        # 底部状态条
        bot_bar = QHBoxLayout()
        self.lbl_status = QLabel("就绪。请选择输入文件或当前画布结构后点击对应功能运行。")
        self.lbl_status.setStyleSheet("color: #888; font-size: 11px;")
        bot_bar.addWidget(self.lbl_status)
        bot_bar.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bot_bar.addWidget(btn_close)
        root.addLayout(bot_bar)

    # ---------------- 1. QTAIM 拓扑选项卡 ----------------
    def _build_qtaim_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctrl = QHBoxLayout()
        btn_run = QPushButton("🚀 运行 QTAIM 拓扑全分析 (搜索 CPs & 积分键径)")
        btn_run.setProperty("role", "action")
        btn_run.clicked.connect(self._run_qtaim)
        ctrl.addWidget(btn_run)

        btn_view_3d = QPushButton("👁 3D 视口显示临界点与键径")
        btn_view_3d.clicked.connect(self._render_qtaim_3d)
        ctrl.addWidget(btn_view_3d)

        btn_clear_3d = QPushButton("❌ 清除 3D 标记")
        btn_clear_3d.clicked.connect(self._clear_qtaim_3d)
        ctrl.addWidget(btn_clear_3d)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.table_cps = QTableWidget(0, 8)
        self.table_cps.setHorizontalHeaderLabels([
            "序号", "类型", "对应核", "坐标 (X, Y, Z Å)",
            "电子密度 ρ", "拉普拉斯 ∇²ρ", "能量密度 H(r)", "椭圆度 ε"
        ])
        self.table_cps.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table_cps, 1)

        self.lbl_qtaim_summary = QLabel()
        self.lbl_qtaim_summary.setStyleSheet("color: #AAA; font-size: 11px;")
        lay.addWidget(self.lbl_qtaim_summary)
        return tab

    # ---------------- 2. NCI / RDG 选项卡 ----------------
    def _build_nci_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("网格精度:"))
        self.nci_grid_combo = QComboBox()
        self.nci_grid_combo.addItem("低精度 Low (快速预览)", 1)
        self.nci_grid_combo.addItem("中精度 Medium (推荐)", 2)
        self.nci_grid_combo.addItem("高精度 High (发表级)", 3)
        self.nci_grid_combo.setCurrentIndex(0)
        ctrl.addWidget(self.nci_grid_combo)

        ctrl.addSpacing(12)
        btn_run_nci = QPushButton("🚀 运行 NCI / RDG 相互作用分析")
        btn_run_nci.setProperty("role", "action")
        btn_run_nci.clicked.connect(self._run_nci)
        ctrl.addWidget(btn_run_nci)

        btn_render_nci = QPushButton("👁 3D 视口渲染 NCI 等值面")
        btn_render_nci.clicked.connect(self._render_nci_3d)
        ctrl.addWidget(btn_render_nci)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.lbl_nci_info = QLabel(
            "NCI (Non-Covalent Interactions) 特性：\n"
            "  - 蓝色等值面 (sign(λ₂)ρ < -0.01): 强吸引相互作用 (氢键、卤键)\n"
            "  - 绿色等值面 (-0.01 < sign(λ₂)ρ < 0.01): 范德华弱色散相互作用\n"
            "  - 红色等值面 (sign(λ₂)ρ > 0.01): 位阻排斥 (环中心/笼中心位阻碰撞)"
        )
        self.lbl_nci_info.setStyleSheet("color: #90CAF9; font-size: 11px; padding: 6px; background: rgba(30, 41, 59, 0.5); border-radius: 4px;")
        lay.addWidget(self.lbl_nci_info)
        lay.addStretch()
        return tab

    # ---------------- 3. ELF / LOL 选项卡 ----------------
    def _build_elf_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("函数类型:"))
        self.combo_grid_func = QComboBox()
        self.combo_grid_func.addItem("电子定域化函数 (ELF)", 9)
        self.combo_grid_func.addItem("局域轨道定位器 (LOL)", 10)
        self.combo_grid_func.addItem("静电势 (ESP)", 12)
        self.combo_grid_func.addItem("全电子密度 (ρ)", 1)
        ctrl.addWidget(self.combo_grid_func)

        ctrl.addSpacing(12)
        btn_run_elf = QPushButton("⚡ 计算 3D 空间网格")
        btn_run_elf.setProperty("role", "action")
        btn_run_elf.clicked.connect(self._run_elf)
        ctrl.addWidget(btn_run_elf)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.lbl_elf_status = QLabel("尚未计算空间网格。")
        self.lbl_elf_status.setStyleSheet("color: #888; font-size: 11px;")
        lay.addWidget(self.lbl_elf_status)
        lay.addStretch()
        return tab

    # ---------------- 4. 原子电荷与偶极选项卡 ----------------
    def _build_pop_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("布居方法:"))
        self.combo_pop_method = QComboBox()
        self.combo_pop_method.addItem("ADCH (原子偶极校正赫氏电荷, 强烈推荐)", "ADCH")
        self.combo_pop_method.addItem("Hirshfeld (经典赫氏电荷)", "Hirshfeld")
        self.combo_pop_method.addItem("CM5 (Charge Model 5)", "CM5")
        self.combo_pop_method.addItem("RESP (力场电荷)", "RESP")
        ctrl.addWidget(self.combo_pop_method)

        ctrl.addSpacing(12)
        btn_run_pop = QPushButton("🚀 计算原子净电荷与偶极")
        btn_run_pop.setProperty("role", "action")
        btn_run_pop.clicked.connect(self._run_population)
        ctrl.addWidget(btn_run_pop)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.table_pop = QTableWidget(0, 3)
        self.table_pop.setHorizontalHeaderLabels(["原子序号", "元素符号", "净电荷 (e)"])
        self.table_pop.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_pop, 1)

        self.lbl_dipole = QLabel("分子偶极矩: 未计算")
        self.lbl_dipole.setStyleSheet("font-weight: bold; color: #40C4FF; font-size: 12px;")
        lay.addWidget(self.lbl_dipole)
        return tab

    # ---------------- 5. Mayer 键级选项卡 ----------------
    def _build_bo_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ctrl = QHBoxLayout()
        btn_run_bo = QPushButton("🚀 计算 Mayer 键级与原子总价 (需 .fchk / .molden)")
        btn_run_bo.setProperty("role", "action")
        btn_run_bo.clicked.connect(self._run_mayer_bo)
        ctrl.addWidget(btn_run_bo)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.table_bo = QTableWidget(0, 4)
        self.table_bo.setHorizontalHeaderLabels(["原子对 A", "原子对 B", "Mayer 键级", "成键特征"])
        self.table_bo.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_bo, 1)

        self.lbl_bo_summary = QLabel()
        self.lbl_bo_summary.setStyleSheet("color: #AAA; font-size: 11px;")
        lay.addWidget(self.lbl_bo_summary)
        return tab

    # ---------------- 输入源管理 ----------------

    def _select_file(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "选择波函数或分子结构文件", "",
            "Wavefunction & Structures (*.wfn *.fchk *.molden *.xyz *.pdb *.mwfn);;All Files (*.*)"
        )
        if not fn:
            return
        self.loaded_file = Path(fn)
        self.lbl_active_file.setText(f"当前输入源: 外部文件 · {self.loaded_file.name}")
        self.lbl_status.setText(f"已载入文件: {self.loaded_file}")

    def _use_current_doc(self):
        if not self.document or len(self.document.topology.atoms) == 0:
            QMessageBox.warning(self, "提示", "当前画布无有效分子结构。")
            return
        xyz_path = self.driver.export_document_xyz(self.document, "current_canvas.xyz")
        self.loaded_file = xyz_path
        self.lbl_active_file.setText(f"当前输入源: 画布分子 · {self.document.name} (临时 XYZ)")
        self.lbl_status.setText(f"已从画布导出临时结构至: {xyz_path}")

    def _ensure_input(self) -> Optional[Path]:
        if not self.loaded_file or not self.loaded_file.is_file():
            if self.document and len(self.document.topology.atoms) > 0:
                self._use_current_doc()
            else:
                QMessageBox.warning(self, "提示", "请先选择波函数文件或载入当前画布分子。")
                return None
        return self.loaded_file

    def _start_worker(self, fn, on_success):
        if not self.driver.is_available:
            QMessageBox.critical(self, "错误", "未检测到 Multiwfn.exe。请检查安装路径。")
            return
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("正在后台安全调用 Multiwfn 进行计算，请稍候...")

        def _runner():
            try:
                res = fn()
                QTimer.singleShot(0, lambda: self._on_worker_done(res, on_success))
            except Exception as e:
                err = str(e)
                QTimer.singleShot(0, lambda: self._on_worker_err(err))

        t = threading.Thread(target=_runner, daemon=True)
        t.start()

    def _on_worker_done(self, res, on_success):
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("计算完成。")
        on_success(res)

    def _on_worker_err(self, err: str):
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"❌ 计算失败: {err}")
        QMessageBox.critical(self, "执行失败", f"Multiwfn 运行异常:\n{err}")

    # ---------------- 业务逻辑触发器 ----------------

    def _run_qtaim(self):
        inp = self._ensure_input()
        if not inp:
            return
        self._start_worker(
            lambda: self.driver.run_qtaim_analysis(inp),
            self._display_qtaim
        )

    def _display_qtaim(self, res: QTAIMResult):
        self.qtaim_result = res
        cps = res.critical_points
        self.table_cps.setRowCount(len(cps))
        for r, cp in enumerate(cps):
            self.table_cps.setItem(r, 0, QTableWidgetItem(f"CP #{cp.index}"))
            self.table_cps.setItem(r, 1, QTableWidgetItem(cp.type_name))
            self.table_cps.setItem(r, 2, QTableWidgetItem(cp.nucleus or "--"))
            pos_str = f"({cp.coords_angstrom[0]:.3f}, {cp.coords_angstrom[1]:.3f}, {cp.coords_angstrom[2]:.3f})"
            self.table_cps.setItem(r, 3, QTableWidgetItem(pos_str))
            self.table_cps.setItem(r, 4, QTableWidgetItem(f"{cp.rho:.4e}"))
            self.table_cps.setItem(r, 5, QTableWidgetItem(f"{cp.laplacian:.4e}"))
            self.table_cps.setItem(r, 6, QTableWidgetItem(f"{cp.energy_density_H:.4e}"))
            self.table_cps.setItem(r, 7, QTableWidgetItem(f"{cp.ellipticity:.4f}"))

        n_bcp = len(res.bcps)
        n_att = len(res.attractors)
        n_rcp = len(res.ring_cps)
        n_ccp = len(res.cage_cps)
        self.lbl_qtaim_summary.setText(
            f"共找到 {len(cps)} 个临界点: {n_att} 个核引力中心 (3,-3), {n_bcp} 个键临界点 (3,-1), "
            f"{n_rcp} 个环中心 (3,+1), {n_ccp} 个笼中心 (3,+3) | 键径条数: {len(res.paths)}"
        )

    def _render_qtaim_3d(self):
        if not self.qtaim_result:
            QMessageBox.information(self, "提示", "请先运行 QTAIM 分析。")
            return
        view = getattr(self.main_window, "workspace", None)
        renderer = None
        if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
            renderer = view.view3d_real.renderer
        elif hasattr(self.main_window, "renderer"):
            renderer = self.main_window.renderer

        if renderer and hasattr(renderer, "set_qtaim"):
            renderer.set_qtaim(self.qtaim_result.critical_points, self.qtaim_result.paths)
            self.lbl_status.setText(f"已在 3D 视口渲染 {len(self.qtaim_result.bcps)} 个 BCP 临界点与 {len(self.qtaim_result.paths)} 条梯度键径。")
        else:
            QMessageBox.warning(self, "视口不可用", "当前 3D 视口渲染器未就绪。")

    def _clear_qtaim_3d(self):
        view = getattr(self.main_window, "workspace", None)
        renderer = None
        if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
            renderer = view.view3d_real.renderer
        elif hasattr(self.main_window, "renderer"):
            renderer = self.main_window.renderer

        if renderer and hasattr(renderer, "clear_qtaim"):
            renderer.clear_qtaim()
            self.lbl_status.setText("已清除 3D 视口 QTAIM 标记。")

    def _run_nci(self):
        inp = self._ensure_input()
        if not inp:
            return
        q = int(self.nci_grid_combo.currentData())
        self._start_worker(
            lambda: self.driver.run_nci_analysis(inp, grid_quality=q),
            self._display_nci
        )

    def _display_nci(self, res: NCIResult):
        self.nci_result = res
        mode_str = "分子原初密度近似 (Promolecular)" if res.is_promolecular else "从头算波函数 (Ab initio)"
        self.lbl_status.setText(f"NCI 分析完成 ({mode_str})。已生成 Cube 体数据网格。")
        QMessageBox.information(self, "完成", f"NCI / RDG 网格计算成功！\n模式: {mode_str}\n点击「3D 视口渲染 NCI 等值面」即可在画布查看！")

    def _render_nci_3d(self):
        if not self.nci_result or not self.nci_result.sign_lambda2_rho_cube:
            QMessageBox.information(self, "提示", "请先运行 NCI / RDG 分析以生成网格。")
            return
        view = getattr(self.main_window, "workspace", None)
        renderer = None
        if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
            renderer = view.view3d_real.renderer
        elif hasattr(self.main_window, "renderer"):
            renderer = self.main_window.renderer

        if renderer and hasattr(renderer, "set_orbital"):
            # 渲染 sign(λ₂)ρ 双相位等值面：正为位阻排斥 (红)，负为氢键吸引 (蓝)
            renderer.set_orbital(
                self.nci_result.sign_lambda2_rho_cube,
                isovalue=0.015,
                pos_color=(0.95, 0.25, 0.25),
                neg_color=(0.25, 0.55, 0.95),
            )
            self.lbl_status.setText("已在 3D 视口渲染 NCI 弱相互作用等值面！")

    def _run_elf(self):
        inp = self._ensure_input()
        if not inp:
            return
        func = int(self.combo_grid_func.currentData())
        self._start_worker(
            lambda: self.driver.run_grid_calculation(inp, func_type=func, grid_quality=1),
            self._display_elf
        )

    def _display_elf(self, cube):
        if cube:
            self.lbl_elf_status.setText(f"网格计算成功: 尺寸 {cube.dims}，已成功载入。")
            view = getattr(self.main_window, "workspace", None)
            renderer = None
            if view and hasattr(view, "view3d_real") and hasattr(view.view3d_real, "renderer"):
                renderer = view.view3d_real.renderer
            elif hasattr(self.main_window, "renderer"):
                renderer = self.main_window.renderer
            if renderer and hasattr(renderer, "set_orbital"):
                renderer.set_orbital(cube, isovalue=0.75, pos_color=(0.2, 0.85, 0.6), neg_color=(0.8, 0.3, 0.3))
                self.lbl_status.setText("已在 3D 视口渲染 ELF/LOL 空间等值面！")
        else:
            self.lbl_elf_status.setText("网格导出失败。")

    def _run_population(self):
        inp = self._ensure_input()
        if not inp:
            return
        m = str(self.combo_pop_method.currentData())
        self._start_worker(
            lambda: self.driver.run_population_analysis(inp, method=m),
            self._display_population
        )

    def _display_population(self, res: PopulationResult):
        self.pop_result = res
        charges = res.charges
        self.table_pop.setRowCount(len(charges))
        for r, (aidx, val) in enumerate(sorted(charges.items())):
            lbl = res.atom_labels.get(aidx, "X")
            self.table_pop.setItem(r, 0, QTableWidgetItem(str(aidx)))
            self.table_pop.setItem(r, 1, QTableWidgetItem(lbl))
            item_val = QTableWidgetItem(f"{val:+.4f}")
            if val > 0.05:
                item_val.setForeground(QColor("#40C4FF"))
            elif val < -0.05:
                item_val.setForeground(QColor("#FF5252"))
            self.table_pop.setItem(r, 2, item_val)

        if res.dipole_debye is not None:
            norm_d = float(np.linalg.norm(res.dipole_debye))
            self.lbl_dipole.setText(
                f"分子偶极矩: {norm_d:.3f} Debye  (X={res.dipole_debye[0]:.2f}, Y={res.dipole_debye[1]:.2f}, Z={res.dipole_debye[2]:.2f})"
            )
        else:
            self.lbl_dipole.setText("分子偶极矩: 未输出")

    def _run_mayer_bo(self):
        inp = self._ensure_input()
        if not inp:
            return
        if inp.suffix.lower() not in [".fchk", ".molden", ".mwfn"]:
            QMessageBox.warning(self, "提示", "Mayer 键级分析需要基函数重叠积分，请选择 .fchk 或 .molden 文件。")
            return
        self._start_worker(
            lambda: self.driver.run_mayer_bond_order(inp),
            self._display_mayer_bo
        )

    def _display_mayer_bo(self, res: MayerBondOrderResult):
        self.bo_result = res
        bos = res.bond_orders
        self.table_bo.setRowCount(len(bos))
        for r, ((a1, a2), bo) in enumerate(sorted(bos.items(), key=lambda x: -x[1])):
            sym1 = res.atom_labels.get(a1, "")
            sym2 = res.atom_labels.get(a2, "")
            self.table_bo.setItem(r, 0, QTableWidgetItem(f"Atom {a1} ({sym1})"))
            self.table_bo.setItem(r, 1, QTableWidgetItem(f"Atom {a2} ({sym2})"))
            self.table_bo.setItem(r, 2, QTableWidgetItem(f"{bo:.4f}"))
            charac = "单键" if bo < 1.3 else ("双键" if bo < 2.3 else "三键")
            self.table_bo.setItem(r, 3, QTableWidgetItem(charac))

        self.lbl_bo_summary.setText(f"共识别出 {len(bos)} 对显著共价作用 (Mayer 键级 >= 0.05)。")
