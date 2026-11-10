"""
ui/shells/studio_split.py - 独立 2D—3D 实时分屏联动系统 (StudioSplitShell & 全新独立 StudioSplitWindow)
======================================================================================================
严格遵循 PROMPT_v7_1_complete.md 规范：
  - StudioSplitWindow 是从零构建的全新 QMainWindow，绝不包装或继承 MolForgeWindow！
  - 无左侧导航栏、无右侧属性面板、无顶部工具栏
  - 顶部菜单栏：File / Edit / Structure / Build / View / Calculate / Results / Windows / Help
  - 中央区域：左半 2D 画布 (Editor2DWidget(chromeless=True)) + 右半 3D 画布 (Render3DWidget(chromeless=True))，
    共享同一 DocumentSession、CommandBus 与 SelectionService，跨画布点选、编辑、单次 Ctrl+Z 撤销实时同步
  - 底部状态栏：Atoms: N   Electrons: M   Charge: Q   Spin: S
"""

from __future__ import annotations
from molforge import __version__

from .base_shell import BaseStudioShell
try:
    from .document_tabs import StudioTabs
except ImportError:
    class StudioTabs:
        pass
from ...domain.document import MoleculeDocument
from ...io.rdkit_adapter import (
    create_instant_caffeine_document,
    load_molecule_document,
    compute_formula_and_weight_fast,
)
from .studio_2d import _compute_electron_count

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QFileDialog, QMessageBox, QSplitter, QStatusBar
    )
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False
    QMainWindow = object  # type: ignore[misc,assignment]


def _compute_electron_count(doc) -> tuple[int, int, int]:
    """计算分子的总原子数、总电子数、总形式电荷与默认自旋多重度 (Atoms, Electrons, Charge, Spin)。"""
    if doc is None:
        return 0, 0, 0, 1
    n_atoms = doc.num_atoms
    charge = int(doc.properties.get("charge", sum(doc.topology.get_atom(aid).formal_charge for aid in doc.topology.atom_ids)))
    z_sum = sum(doc.topology.get_atom(aid).atomic_num for aid in doc.topology.atom_ids)
    n_elec = max(0, z_sum - charge)
    default_spin = 1 if (n_elec % 2 == 0) else 2
    spin = int(doc.properties.get("multiplicity", default_spin))
    return n_atoms, n_elec, charge, spin



class StudioSplitShell(BaseStudioShell):
    shell_kind = "studio_split"
    menu_titles = ("File", "Edit", "Structure", "Builder", "View", "Calculate", "Results", "Window", "Help")


class StudioSplitWindow(StudioTabs, QMainWindow):
    """
    全新独立 2D–3D 实时分屏联动主窗口（纯顶部菜单栏 + 中央左右 2D/3D 双画布 + 底部状态栏，绝不包装 MolForgeWindow）。
    """

    _open_windows: list["StudioSplitWindow"] = []

    def __init__(self, document: MoleculeDocument | None = None, shell: StudioSplitShell | None = None):
        super().__init__()
        doc = document if document is not None else create_instant_caffeine_document()
        self.shell = shell if shell is not None else StudioSplitShell(document=doc)
        self.session = self.shell.session
        self.view_session = self.shell.view_session
        self.document = self.shell.document
        self.command_bus = self.session.command_bus
        self.selection = self.session.selection
        self.group_tag = self.shell.gmv_tag

        self.setWindowTitle(f"MolForge {__version__} Studio Split (2D ⇄ 3D) · [{self.group_tag}] {self.document.name}")
        self.resize(1240, 780)

        from ..editor2d_widget import Editor2DWidget
        from ..render3d_widget import Render3DWidget

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        self.canvas2d = Editor2DWidget(self)
        self.canvas2d.set_document(self.document)
        self.canvas2d.set_selection_service(self.selection)
        self.canvas2d.set_command_bus(self.command_bus)

        self.canvas3d = Render3DWidget(self)
        self.canvas3d.set_selection_service(self.selection)
        self.canvas3d.set_command_bus(self.command_bus)

        self.splitter.addWidget(self.canvas2d)
        self.splitter.addWidget(self.canvas3d)
        self.splitter.setSizes([600, 640])

        # 2D ⇄ 3D 实时双向联动控制器 (P0 核心特性)
        self._live_sync_enabled = True
        self._sync_in_progress = False
        self._live_sync_timer = QTimer(self)
        self._live_sync_timer.setSingleShot(True)
        self._live_sync_timer.setInterval(400)
        self._live_sync_timer.timeout.connect(self._on_live_sync_timeout)

        if hasattr(self.command_bus, "add_listener"):
            self.command_bus.add_listener(self._on_command_bus_change)

        # 状态栏先于 init_tabs 创建（init_tabs 内会触发 refresh_views 写 status_label）
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label, 1)

        self.init_tabs(self.splitter)

        self._build_menus()
        self.install_studio_toolbar()
        self.install_window_menu()
        StudioSplitWindow._open_windows.append(self)

        QTimer.singleShot(15, lambda: self.canvas3d.set_document(self.document))
        self.refresh_views()

    def _build_menus(self) -> None:
        mb = self.menuBar()
        mb.clear()

        # 1. 文件
        m_file = mb.addMenu("文件(&F)")
        act_open = QAction("打开结构 / 量子输出 (.gjf/.log/.xyz/.mol/.sdf/.pdb)... (Ctrl+O)", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open_file)
        m_file.addAction(act_open)

        act_welcome = QAction("返回欢迎界面...", self)
        act_welcome.triggered.connect(self._open_welcome)
        m_file.addAction(act_welcome)

        act_close = QAction("关闭窗口 (Ctrl+W)", self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        # 2. 编辑
        m_edit = mb.addMenu("编辑(&E)")
        act_undo = QAction("撤销 (Ctrl+Z)", self)
        act_undo.setShortcut("Ctrl+Z")
        act_undo.triggered.connect(lambda: (self.command_bus.undo(), self.refresh_views()))
        m_edit.addAction(act_undo)

        act_redo = QAction("重做 (Ctrl+Y)", self)
        act_redo.setShortcut("Ctrl+Y")
        act_redo.triggered.connect(lambda: (self.command_bus.redo(), self.refresh_views()))
        m_edit.addAction(act_redo)

        # 3. 结构
        m_struct = mb.addMenu("结构(&S)")

        act_sync_3d = QAction("⚡ 2D ➜ 3D 构象生成 (ETKDG + UFF/MMFF94)... (F6)", self)
        act_sync_3d.setShortcut("F6")
        act_sync_3d.triggered.connect(lambda: self.generate_3d_conformation(silent=False))
        m_struct.addAction(act_sync_3d)

        act_proj_2d = QAction("📐 3D ➜ 2D 当前视角规整投影 (Ctrl+Shift+P)", self)
        act_proj_2d.setShortcut("Ctrl+Shift+P")
        act_proj_2d.triggered.connect(lambda: self.project_3d_to_2d(use_coordgen=False))
        m_struct.addAction(act_proj_2d)

        act_coordgen = QAction("⚗️ 3D ➜ 2D ChemDraw 规范二维重排", self)
        act_coordgen.triggered.connect(lambda: self.project_3d_to_2d(use_coordgen=True))
        m_struct.addAction(act_coordgen)

        m_struct.addSeparator()

        act_live_sync = QAction("✓ 开启 2D ➜ 3D 实时联动生成 (Live Sync)", self)
        act_live_sync.setCheckable(True)
        act_live_sync.setChecked(self._live_sync_enabled)
        act_live_sync.toggled.connect(self.toggle_live_sync)
        m_struct.addAction(act_live_sync)

        m_struct.addSeparator()

        act_c2d = QAction("清理 2D 布局", self)
        act_c2d.triggered.connect(lambda: self.canvas2d.recompute_2d_layout())
        m_struct.addAction(act_c2d)

        act_c3d = QAction("清理 3D 几何 (Ctrl+M)", self)
        act_c3d.setShortcut("Ctrl+M")
        act_c3d.triggered.connect(lambda: self.canvas3d.clean_3d_geometry())
        m_struct.addAction(act_c3d)

        # 4. 构建
        m_build = mb.addMenu("构建(&B)")
        for tool_lbl, tool_name, sc in (
            ("选择模式 (V)", "选择", "V"),
            ("添加原子模式 (A)", "原子", "A"),
            ("绘制键模式 (B)", "键", "B"),
            ("擦除模式 (E)", "擦除", "E"),
        ):
            act = QAction(tool_lbl, self)
            act.setShortcut(sc)
            act.triggered.connect(lambda _=False, tn=tool_name: self._set_shared_tool(tn))
            m_build.addAction(act)

        m_build.addSeparator()
        act_efrag = QAction("元素片段面板 (C / O / N / 常用)...", self)
        act_efrag.triggered.connect(self._on_open_element_fragments)
        m_build.addAction(act_efrag)

        # 5. 视图
        m_view = mb.addMenu("视图(&V)")
        for cnt, lbl in (
            (1, "3D 视口: 1 视口 (P1)"),
            (2, "3D 视口: 2 视口 (P1 | P2)"),
            (4, "3D 视口: 4 视口 (P1..P4)"),
        ):
            act = QAction(lbl, self)
            act.triggered.connect(lambda _=False, c=cnt: self.canvas3d.set_multiview_layout(c))
            m_view.addAction(act)

        # 6. 计算
        m_calc = mb.addMenu("计算(&C)")
        act_gauss = QAction("Gaussian 计算设置 (11 标签页向导)... (Ctrl+G)", self)
        act_gauss.setShortcut("Ctrl+G")
        act_gauss.triggered.connect(self._on_gaussian_setup)
        m_calc.addAction(act_gauss)

        # 7. 结果
        m_res = mb.addMenu("结果(&R)")
        from ..qc_result_dialog import populate_v7_results_menu
        populate_v7_results_menu(m_res, self, lambda: self.document)

        # 8. 窗口
        m_win = mb.addMenu("窗口(&W)")
        act_w = QAction("切换系统模式 (返回欢迎界面)...", self)
        act_w.triggered.connect(self._open_welcome)
        m_win.addAction(act_w)

        # 9. 帮助
        m_help = mb.addMenu("帮助(&H)")
        act_about = QAction("关于 MolForge Studio Split…", self)
        act_about.triggered.connect(
            lambda: QMessageBox.information(self, "MolForge Studio Split", f"MolForge v{__import__('molforge').__version__} · 2D–3D 实时分屏联动系统")
        )
        m_help.addAction(act_about)

    def _set_shared_tool(self, tool_name: str) -> None:
        self._set_active_tool(tool_name)
        self.refresh_views()

    def open_molecule_file(self, path: str) -> None:
        self.open_document_tab(path)

    def _on_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开结构或量子输出", "",
            "Chemistry & QC Files (*.gjf *.com *.log *.out *.fchk *.cube *.xyz *.mol *.sdf *.pdb *.mol2);;All Files (*)"
        )
        if path:
            self.open_molecule_file(path)

    def _on_open_element_fragments(self) -> None:
        from ..dialogs.element_fragments import ElementFragmentsDialog
        from ...application.fragment_commands import InsertFragmentCommand
        dlg = ElementFragmentsDialog(parent=self, initial_category="C")
        if dlg.exec() and dlg.selected_fragment is not None:
            sel_atoms = list(self.selection.selected_atoms)
            anchor = sel_atoms[-1] if sel_atoms else None
            self.command_bus.execute(InsertFragmentCommand(dlg.selected_fragment, anchor_atom_id=anchor))
            self.canvas2d.recompute_2d_layout()
            self.refresh_views()

    def _on_gaussian_setup(self) -> None:
        from ..dialogs.gaussian_calculation_setup import GaussianCalculationSetupDialog
        GaussianCalculationSetupDialog(self.document, parent=self).exec()

    def _open_welcome(self) -> None:
        from ..welcome_window import AppController
        AppController.instance().show_welcome()

    def refresh_views(self) -> None:
        if hasattr(self, "tabs") and self.tabs.currentWidget() is not None:
            self.tabs.setTabText(self.tabs.currentIndex(), self.document.name)
        # 关键修复：切换标签页后，必须重新 set_document
        if hasattr(self, 'canvas2d') and self.canvas2d is not None:
            self.canvas2d.set_document(self.document)
        self.canvas3d.set_document(self.document)
        n_atoms, n_elec, charge, spin = _compute_electron_count(self.document)
        formula, _ = compute_formula_and_weight_fast(self.document)
        self.setWindowTitle(f"MolForge {__version__} Studio Split (2D ⇄ 3D) · [{self.group_tag}] {self.document.name}")
        self.status_label.setText(
            f"Atoms: {n_atoms}    Electrons: {n_elec}    Charge: {charge}    Spin: {spin}    "
            f"|    Formula: {formula}    |    2D ⇄ 3D Live Sync [{self.group_tag}]"
        )


    def install_studio_toolbar(self) -> None:
        super().install_studio_toolbar()
        if hasattr(self, "studio_toolbar") and self.studio_toolbar is not None:
            tb = self.studio_toolbar
            tb.addSeparator()

            act_sync = QAction("⚡ 2D➜3D 构象 (F6)", self)
            act_sync.setToolTip("基于 RDKit ETKDG + UFF/MMFF94 从 2D 拓扑极速生成 3D 空间立体构象 (F6)")
            act_sync.triggered.connect(lambda: self.generate_3d_conformation(silent=False))
            tb.addAction(act_sync)

            act_proj = QAction("📐 3D➜2D 视角投影", self)
            act_proj.setToolTip("将当前 3D 视口相机视角正交投影至 2D 画布并规范化 ChemDraw 键长 (Ctrl+Shift+P)")
            act_proj.triggered.connect(lambda: self.project_3d_to_2d(use_coordgen=False))
            tb.addAction(act_proj)

            act_live = QAction("⚡ 实时联动", self)
            act_live.setCheckable(True)
            act_live.setChecked(self._live_sync_enabled)
            act_live.setToolTip("开启/暂停 2D 画布编辑后 400ms 自动触发 3D 空间构象生成")
            act_live.toggled.connect(self.toggle_live_sync)
            tb.addAction(act_live)

    def toggle_live_sync(self, enabled: bool) -> None:
        self._live_sync_enabled = enabled
        status = "已开启" if enabled else "已暂停"
        self.status_label.setText(f"⚡ 2D ➜ 3D 实时联动{status} | [{self.group_tag}]")

    def _on_command_bus_change(self, doc: MoleculeDocument) -> None:
        if getattr(self, "_sync_in_progress", False):
            return
        if getattr(self, "_live_sync_enabled", False) and doc.num_atoms > 0:
            if hasattr(self, "_live_sync_timer"):
                self._live_sync_timer.start()

    def _on_live_sync_timeout(self) -> None:
        if getattr(self, "_sync_in_progress", False) or self.document.num_atoms == 0:
            return
        self.generate_3d_conformation(silent=True)

    def generate_3d_conformation(self, silent: bool = False) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import GenerateConformation3DCommand

        self._sync_in_progress = True
        try:
            res = self.command_bus.execute(GenerateConformation3DCommand(optimize_iters=150))
            self.canvas3d.set_document(self.document)
            if not silent:
                self.status_label.setText(f"⚡ {res.message} | 2D ⇄ 3D Live Sync [{self.group_tag}]")
        finally:
            self._sync_in_progress = False

    def project_3d_to_2d(self, use_coordgen: bool = False) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import Project3DTo2DCommand

        self._sync_in_progress = True
        try:
            right, up = self.canvas3d.get_camera_view_basis()
            res = self.command_bus.execute(
                Project3DTo2DCommand(camera_right=right, camera_up=up, use_coordgen=use_coordgen)
            )
            self.canvas2d.set_document(self.document)
            self.canvas2d.fit_view()
            self.refresh_views()
            self.status_label.setText(f"📐 {res.message} | 2D ⇄ 3D Live Sync [{self.group_tag}]")
        finally:
            self._sync_in_progress = False
