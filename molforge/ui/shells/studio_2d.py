"""
ui/shells/studio_2d.py - 独立 2D 化学结构设计系统 (Studio2DShell & 全新独立 Studio2DWindow)
=============================================================================================
严格遵循 PROMPT_v7_1_complete.md 规范：
  - Studio2DWindow 是从零构建的全新 QMainWindow，绝不包装或继承 MolForgeWindow！
  - 无左侧导航栏、无右侧属性面板、无顶部工具栏、无 3D VTK 实例化开销
  - 顶部菜单栏：File / Edit / Structure / Build / View / Calculate / Results / Help
  - 中央区域：100% 占满的纯 2D 画布 (Editor2DWidget(chromeless=True))
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
from pathlib import Path
from ...domain.document import MoleculeDocument
from ...io.rdkit_adapter import (
    create_instant_caffeine_document,
    load_molecule_document,
    compute_formula_and_weight_fast,
    export_document_to_mol_v2000,
)

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



class Studio2DShell(BaseStudioShell):
    shell_kind = "studio_2d"
    menu_titles = ("File", "Edit", "Draw", "Structure", "Templates", "View", "Tools", "Window", "Help")


class Studio2DWindow(StudioTabs, QMainWindow):
    """
    对标 ChemDraw 的全新独立 2D 化学绘图主窗口（纯菜单栏 + 100% 中央 2D 画布 + 底部状态栏，绝不包装 MolForgeWindow）。
    """

    _open_windows: list["Studio2DWindow"] = []

    def __init__(self, document: MoleculeDocument | None = None, session=None, view_session=None):
        super().__init__()
        doc = document if document is not None else MoleculeDocument(name="未命名-1")
        self.shell = Studio2DShell(document=doc, session=session, view_session=view_session)
        self.session = self.shell.session
        self.view_session = self.shell.view_session
        self.document = self.shell.document
        self.command_bus = self.session.command_bus
        self.selection = self.session.selection
        self.group_tag = self.shell.gmv_tag

        self.setWindowTitle(f"MolForge {__version__} Studio 2D · [{self.group_tag}] {self.document.name}")
        self.resize(1080, 740)

        from ..editor2d_widget import Editor2DWidget
        self.canvas2d = Editor2DWidget(self)
        self.canvas2d.set_document(self.document)
        self.canvas2d.set_selection_service(self.selection)
        self.canvas2d.set_command_bus(self.command_bus)

        # 状态栏必须在 init_tabs 之前创建：init_tabs 内部会触发 refresh_views，
        # 而 refresh_views 要写 status_label，顺序反了会启动崩溃。
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label, 1)

        self.init_tabs(self.canvas2d)

        self._build_menus()
        self.install_studio_toolbar()
        self.install_window_menu()
        Studio2DWindow._open_windows.append(self)
        self.refresh_views()

    def _build_menus(self) -> None:
        mb = self.menuBar()
        mb.clear()

        # 1. 文件
        m_file = mb.addMenu("文件(&F)")
        act_new = QAction("新建 2D 文档 (Ctrl+N)", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._on_new_blank)
        m_file.addAction(act_new)

        act_demo = QAction("打开示例结构 (咖啡因)", self)
        act_demo.triggered.connect(self._on_open_caffeine_demo)
        m_file.addAction(act_demo)

        act_clear = QAction("清空当前画布 (Ctrl+Shift+Delete)", self)
        act_clear.setShortcut("Ctrl+Shift+Delete")
        act_clear.triggered.connect(self._on_clear_canvas)
        m_file.addAction(act_clear)

        act_open = QAction("打开结构 (.mol/.sdf/.smi/.xyz/.gjf/.log)... (Ctrl+O)", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open_file)
        m_file.addAction(act_open)

        act_save = QAction("保存完整工程 (Ctrl+S)", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(lambda: self.save_project())
        m_file.addAction(act_save)

        m_file.addSeparator()
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
        for tool_lbl, tool_name, sc in (
            ("选择 / 移动工具 (V)", "选择", "V"),
            ("绘制原子工具 (A)", "原子", "A"),
            ("绘制 / 切换键工具 (B)", "键", "B"),
            ("擦除原子 / 键工具 (E)", "擦除", "E"),
        ):
            act = QAction(tool_lbl, self)
            act.setShortcut(sc)
            act.triggered.connect(lambda _=False, tn=tool_name: self._set_2d_tool(tn))
            m_struct.addAction(act)
        m_struct.addSeparator()
        act_clean2d = QAction("清理 2D 结构布局", self)
        act_clean2d.triggered.connect(self._clean_active)
        m_struct.addAction(act_clean2d)

        m_struct.addSeparator()
        act_sync_3d = QAction("⚡ 从当前 2D 生成 3D 构象 (ETKDG + UFF)... (F6)", self)
        act_sync_3d.setShortcut("F6")
        act_sync_3d.triggered.connect(self.generate_3d_conformation)
        m_struct.addAction(act_sync_3d)

        act_proj_2d = QAction("📐 将 3D 构象投影至 2D 布局 (Ctrl+Shift+P)", self)
        act_proj_2d.setShortcut("Ctrl+Shift+P")
        act_proj_2d.triggered.connect(self.project_3d_to_2d)
        m_struct.addAction(act_proj_2d)

        # 4. 构建
        m_build = mb.addMenu("构建(&B)")
        for sym, z in (("碳 (C)", 6), ("氮 (N)", 7), ("氧 (O)", 8), ("硫 (S)", 16), ("氟 (F)", 9), ("氯 (Cl)", 17)):
            act = QAction(f"当前元素: {sym}", self)
            act.triggered.connect(lambda _=False, az=z: self.canvas2d.set_current_element(az))
            m_build.addAction(act)
        m_build.addSeparator()
        act_frag = QAction("元素片段库 (C / O / N / 常用)...", self)
        act_frag.triggered.connect(self._open_element_fragments_dialog)
        m_build.addAction(act_frag)

        act_ring = QAction("环 / R-基团构建器...", self)
        act_ring.triggered.connect(self._open_builder_fragment_dialog)
        m_build.addAction(act_ring)

        # 5. 视图
        m_view = mb.addMenu("视图(&V)")
        act_paper = QAction("切换暖色纸张 / 深色蓝图画布", self)
        act_paper.triggered.connect(lambda: self.canvas2d._toggle_paper_mode())
        m_view.addAction(act_paper)

        act_h = QAction("切换隐式 / 显式氢原子", self)
        act_h.triggered.connect(lambda: self.canvas2d._toggle_explicit_h())
        m_view.addAction(act_h)

        act_fit = QAction("居中 & 适配窗口", self)
        act_fit.triggered.connect(self._center_active)
        m_view.addAction(act_fit)

        # 6. 计算
        m_calc = mb.addMenu("计算(&C)")
        act_gauss = QAction("Gaussian 计算设置 (11 标签页向导)... (Ctrl+G)", self)
        act_gauss.setShortcut("Ctrl+G")
        act_gauss.triggered.connect(self._open_gaussian_setup)
        m_calc.addAction(act_gauss)

        act_rest = QAction("复旦 REST 输入生成器 (ctrl.in)...", self)
        act_rest.triggered.connect(self._open_rest_setup)
        m_calc.addAction(act_rest)

        # 7. 结果
        m_res = mb.addMenu("结果(&R)")
        from ..qc_result_dialog import populate_v7_results_menu
        populate_v7_results_menu(m_res, self, lambda: self.document)

        # 8. 帮助
        m_help = mb.addMenu("帮助(&H)")
        act_about = QAction("关于 MolForge Studio 2D…", self)
        act_about.triggered.connect(
            lambda: QMessageBox.information(self, "MolForge Studio 2D", f"MolForge v{__import__('molforge').__version__} · 独立 2D 化学绘图系统 (零 VTK 开销)")
        )
        m_help.addAction(act_about)

    def _set_2d_tool(self, tool_name: str) -> None:
        self._set_active_tool(tool_name)
        self.refresh_views()

    def _on_new_blank(self) -> None:
        self.add_document_tab()

    def _on_open_caffeine_demo(self) -> None:
        caffeine_doc = create_instant_caffeine_document()
        self.add_document_tab(document=caffeine_doc)

    def _on_clear_canvas(self) -> None:
        if self.canvas2d is not None and self.document is not None:
            if self.document.num_atoms > 0:
                self.canvas2d._select_all()
                self.canvas2d.delete_selected()
                self.canvas2d.fit_view()
                self.refresh_views()

    def open_molecule_file(self, path: str) -> None:
        self.open_document_tab(path)

    def _on_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开分子文件", "",
            "Chemistry Files (*.mol *.sdf *.smi *.xyz *.gjf *.log *.out *.pdb *.mol2);;All Files (*)"
        )
        if path:
            self.open_molecule_file(path)

    def _on_export_2d(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 2D 结构", f"{self.document.name}.svg",
            "SVG Vector (*.svg);;MOL V2000 (*.mol);;PNG Image (*.png)"
        )
        if not path:
            return
        if path.lower().endswith(".mol"):
            Path(path).write_text(export_document_to_mol_v2000(self.document), encoding="utf-8")
        elif path.lower().endswith(".svg"):
            from ...io.writers.svg_writer import write_svg_2d
            write_svg_2d(self.document, path)
        else:
            self.canvas2d.grab().save(path)

    def _open_element_fragments_dialog(self) -> None:
        from ..dialogs.element_fragments import ElementFragmentsDialog
        from ...application.fragment_commands import InsertFragmentCommand
        dlg = ElementFragmentsDialog(parent=self, initial_category="C")
        if dlg.exec() and dlg.selected_fragment is not None:
            sel_atoms = list(self.selection.selected_atoms)
            anchor = sel_atoms[-1] if sel_atoms else None
            self.command_bus.execute(InsertFragmentCommand(dlg.selected_fragment, anchor_atom_id=anchor))
            self.canvas2d.recompute_2d_layout()
            self.refresh_views()

    def _open_builder_fragment_dialog(self) -> None:
        from ..views import BuilderFragmentDialog
        BuilderFragmentDialog(self, "Ring").exec()
        self.refresh_views()

    def _open_gaussian_setup(self) -> None:
        from ..dialogs.gaussian_calculation_setup import GaussianCalculationSetupDialog
        GaussianCalculationSetupDialog(self.document, parent=self).exec()

    def _open_rest_setup(self) -> None:
        from ..qc_result_dialog import QcResultDialog
        QcResultDialog(parent=self, document=self.document, initial_tab=1).exec()

    def _open_welcome(self) -> None:
        from ..welcome_window import AppController
        AppController.instance().show_welcome()

    def refresh_views(self) -> None:
        if hasattr(self, "tabs") and self.tabs.currentWidget() is not None:
            self.tabs.setTabText(self.tabs.currentIndex(), self.document.name)
        # 关键修复：切换标签页后，必须重新 set_document，否则 2D 画布的 _document 是空的
        if hasattr(self, 'canvas2d') and self.canvas2d is not None:
            self.canvas2d.set_document(self.document)
        self.canvas2d.update()
        n_atoms, n_elec, charge, spin = _compute_electron_count(self.document)
        formula, _ = compute_formula_and_weight_fast(self.document)
        self.setWindowTitle(f"MolForge {__version__} Studio 2D · [{self.group_tag}] {self.document.name}")
        self.status_label.setText(
            f"Atoms: {n_atoms}    Electrons: {n_elec}    Charge: {charge}    Spin: {spin}    "
            f"|    Formula: {formula}    |    [{self.group_tag}]"
        )


    def generate_3d_conformation(self) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import GenerateConformation3DCommand
        res = self.command_bus.execute(GenerateConformation3DCommand(optimize_iters=150))
        self.refresh_views()
        QMessageBox.information(self, "3D 构象生成", res.message)

    def project_3d_to_2d(self) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import Project3DTo2DCommand
        res = self.command_bus.execute(Project3DTo2DCommand(use_coordgen=True))
        self.canvas2d.set_document(self.document)
        self.canvas2d.fit_view()
        self.refresh_views()
