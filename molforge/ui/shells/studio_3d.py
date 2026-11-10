"""
ui/shells/studio_3d.py - GaussView 风格 3D 多窗口建模系统 (Studio3DShell & 全新独立 Studio3DWindow)
=====================================================================================================
严格遵循 PROMPT_v7_1_complete.md 规范：
  - Studio3DWindow 是从零构建的全新 QMainWindow，绝不包装或继承 MolForgeWindow！
  - 无左侧导航栏、无右侧属性面板、无顶部工具栏
  - 顶部菜单栏：File / Edit / Build / View / Calculate / Results / Windows / Help
  - 中央区域：100% 占满的 VTK 3D 画布 (Render3DWidget(chromeless=True))，支持单窗口 1 / 2 / 4 视口 (P1..P4)
  - 底部状态栏：Atoms: N   Electrons: M   Charge: Q   Spin: S
"""

from __future__ import annotations
from molforge import __version__

from pathlib import Path
from .base_shell import BaseStudioShell
try:
    from .document_tabs import StudioTabs
except ImportError:
    class StudioTabs:
        pass
from ..vtk_multiview_widget import VtkMultiviewController
from ...application.workspace_registry import PaneCount
from ...domain.document import MoleculeDocument
from ...io.rdkit_adapter import (
    create_instant_caffeine_document,
    load_molecule_document,
    compute_formula_and_weight_fast,
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



class Studio3DShell(BaseStudioShell):
    shell_kind = "studio_3d"
    menu_titles = ("File", "Edit", "Tools", "Builder", "View", "Calculate", "Results", "Windows", "Help")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.multiview = VtkMultiviewController(self.view_session)

    def set_pane_layout(self, count: PaneCount) -> dict[str, tuple[float, float, float, float]]:
        return self.multiview.set_layout(count)

    def spawn_clone_view(self, pane_count: PaneCount = 1) -> "Studio3DShell":
        session, cloned_view = self.gmv_manager.register_clone_view(self.gmv_tag, pane_count=pane_count)
        return Studio3DShell(session=session, view_session=cloned_view)

    def spawn_group_molecule(self, document: MoleculeDocument | None = None, pane_count: PaneCount = 1) -> "Studio3DShell":
        doc = document or MoleculeDocument(name="group_mol")
        session, new_view = self.gmv_manager.register_add_molecule_to_group(
            self.view_session.group_id, doc, pane_count=pane_count
        )
        return Studio3DShell(session=session, view_session=new_view)


class Studio3DWindow(StudioTabs, QMainWindow):
    """
    对标 GaussView 6 的全新简洁 3D 建模与量化主窗口（纯顶部菜单栏 + 100% 中央 VTK 画布 + 底部状态栏，绝不包装 MolForgeWindow）。
    """

    _open_windows: list["Studio3DWindow"] = []

    def __init__(
        self,
        document: MoleculeDocument | None = None,
        pane_count: PaneCount = 1,
        shell: Studio3DShell | None = None,
        session=None,
    ):
        super().__init__()
        doc = document if document is not None else create_instant_caffeine_document()
        self.shell = shell if shell is not None else Studio3DShell(document=doc, session=session, pane_count=pane_count)
        self.session = self.shell.session
        self.view_session = self.shell.view_session
        self.document = self.shell.document
        self.command_bus = self.session.command_bus
        self.selection = self.session.selection
        self.group_tag = self.shell.gmv_tag

        self.setWindowTitle(f"MolForge {__version__} Studio 3D · [{self.group_tag}] {self.document.name}")
        self.resize(1120, 760)

        from ..render3d_widget import Render3DWidget
        self.canvas3d = Render3DWidget(self)
        self.canvas3d.set_selection_service(self.selection)
        self.canvas3d.set_command_bus(self.command_bus)

        # 状态栏先于 init_tabs 创建（init_tabs 内会触发 refresh_views 写 status_label）
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label, 1)

        self.init_tabs(self.canvas3d)

        self._build_menus()
        self.install_studio_toolbar()
        self.install_window_menu()
        Studio3DWindow._open_windows.append(self)

        QTimer.singleShot(15, lambda: self._init_3d_scene(pane_count))
        self.refresh_views()

    def _init_3d_scene(self, pane_count: PaneCount) -> None:
        self.canvas3d.set_document(self.document)
        if pane_count in (1, 2, 4):
            self.set_3d_multiview_count(pane_count)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        mb.clear()

        # 1. 文件
        m_file = mb.addMenu("文件(&F)")
        act_new = QAction("新建分子组 (G:M:V)... (Ctrl+N)", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(lambda: self.add_document_tab())
        m_file.addAction(act_new)

        act_open = QAction("打开结构 / Gaussian 输出 (.gjf/.log/.xyz/.mol/.sdf/.pdb)... (Ctrl+O)", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open_file)
        m_file.addAction(act_open)

        act_save_gjf = QAction("保存完整工程 (Ctrl+S)", self)
        act_save_gjf.setShortcut("Ctrl+S")
        act_save_gjf.triggered.connect(lambda: self.save_project())
        m_file.addAction(act_save_gjf)

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

        m_edit.addSeparator()
        act_clean = QAction("3D 几何优化 (力场弛豫, Ctrl+M)", self)
        act_clean.setShortcut("Ctrl+M")
        act_clean.triggered.connect(self._clean_active)
        m_edit.addAction(act_clean)

        act_sync_3d = QAction("⚡ 重新生成 3D 空间立体构象 (ETKDG + UFF/MMFF94)... (F6)", self)
        act_sync_3d.setShortcut("F6")
        act_sync_3d.triggered.connect(self.generate_3d_conformation)
        m_edit.addAction(act_sync_3d)

        act_proj_2d = QAction("📐 将当前 3D 观察视角投影生成 2D 布局 (Ctrl+Shift+P)", self)
        act_proj_2d.setShortcut("Ctrl+Shift+P")
        act_proj_2d.triggered.connect(self.project_3d_to_2d)
        m_edit.addAction(act_proj_2d)

        # 3. 构建
        m_build = mb.addMenu("构建(&B)")
        for tool_lbl, tool_name, sc in (
            ("选择 / 拖动原子模式 (V)", "选择", "V"),
            ("放置 / 生长原子模式 (A)", "原子", "A"),
            ("绘制 / 切换键模式 (B)", "键", "B"),
            ("擦除原子 / 键模式 (E)", "擦除", "E"),
        ):
            act = QAction(tool_lbl, self)
            act.setShortcut(sc)
            act.triggered.connect(lambda _=False, tn=tool_name: self.canvas3d.set_current_tool(tn))
            m_build.addAction(act)

        m_build.addSeparator()
        act_efrag = QAction("元素片段面板 (C / O / N / 常用)...", self)
        act_efrag.triggered.connect(self._on_open_element_fragments)
        m_build.addAction(act_efrag)

        act_rfrag = QAction("环 / R-基团片段库...", self)
        act_rfrag.triggered.connect(self._on_open_ring_fragments)
        m_build.addAction(act_rfrag)

        m_build.addSeparator()
        for coord_lbl, kind in (
            ("修改键长...", "bond"),
            ("修改键角...", "angle"),
            ("修改二面角...", "dihedral"),
        ):
            act = QAction(coord_lbl, self)
            act.triggered.connect(lambda _=False, k=kind: self._on_modify_internal_coord(k))
            m_build.addAction(act)

        # 4. 视图
        m_view = mb.addMenu("视图(&V)")
        for cnt, lbl in (
            (1, "1 视口 (单视图 - P1)"),
            (2, "2 视口 (左右分屏 - P1 | P2)"),
            (4, "4 视口 (前/侧/俯/透视 - P1..P4)"),
        ):
            act = QAction(lbl, self)
            act.triggered.connect(lambda _=False, c=cnt: self.set_3d_multiview_count(c))
            m_view.addAction(act)

        m_view.addSeparator()
        from ...rendering.contracts import RepresentationMode
        for mode_enum, mode_lbl in (
            (RepresentationMode.BALL_AND_STICK, "显示模式: 球棍模型"),
            (RepresentationMode.CPK, "显示模式: CPK 空间填充"),
            (RepresentationMode.LINE, "显示模式: 线框"),
            (RepresentationMode.SURFACE, "显示模式: 范德华分子表面"),
        ):
            act = QAction(mode_lbl, self)
            act.triggered.connect(lambda _=False, m=mode_enum: self.canvas3d.set_representation_mode(m))
            m_view.addAction(act)

        m_view.addSeparator()
        act_reset_cam = QAction("居中 & 重置 3D 相机", self)
        act_reset_cam.triggered.connect(self._center_active)
        m_view.addAction(act_reset_cam)

        # 5. 计算
        m_calc = mb.addMenu("计算(&C)")
        act_gauss = QAction("Gaussian 计算设置 (11 标签页向导)... (Ctrl+G)", self)
        act_gauss.setShortcut("Ctrl+G")
        act_gauss.triggered.connect(self._on_gaussian_setup)
        m_calc.addAction(act_gauss)

        act_rest = QAction("复旦 REST 输入设置 (ctrl.in)...", self)
        act_rest.triggered.connect(self._on_rest_setup)
        m_calc.addAction(act_rest)

        act_xtb = QAction("GFN2-xTB 几何优化... (Ctrl+Shift+X)", self)
        act_xtb.setShortcut("Ctrl+Shift+X")
        act_xtb.triggered.connect(self._on_run_xtb)
        m_calc.addAction(act_xtb)

        # 6. 结果
        m_res = mb.addMenu("结果(&R)")
        from ..qc_result_dialog import populate_v7_results_menu
        populate_v7_results_menu(m_res, self, lambda: self.document)

        # 7. 窗口
        m_win = mb.addMenu("窗口(&W)")
        act_clone = QAction("添加克隆共享视图 (同 DocumentSession, G1:M1:V2)...", self)
        act_clone.triggered.connect(self._on_spawn_clone_view)
        m_win.addAction(act_clone)

        act_add_mol = QAction("向当前组添加新分子 (G1:M2:V1)...", self)
        act_add_mol.triggered.connect(self._on_spawn_group_molecule)
        m_win.addAction(act_add_mol)

        # 8. 帮助
        m_help = mb.addMenu("帮助(&H)")
        act_about = QAction("关于 MolForge Studio 3D…", self)
        act_about.triggered.connect(
            lambda: QMessageBox.information(
                self, "MolForge Studio 3D", f"MolForge v{__import__('molforge').__version__} · GaussView 风格简洁 3D 多窗口与量化系统"
            )
        )
        m_help.addAction(act_about)

    def set_3d_multiview_count(self, pane_count: PaneCount = 1) -> list:
        self.shell.set_pane_layout(pane_count)
        aux = self.canvas3d.set_multiview_layout(pane_count)
        self.refresh_views()
        return aux

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
            self.refresh_views()

    def _on_open_ring_fragments(self) -> None:
        from ..views import BuilderFragmentDialog
        BuilderFragmentDialog(self, "Ring").exec()
        self.refresh_views()

    def _on_modify_internal_coord(self, kind: str) -> None:
        from ..views import ModifyInternalCoordDialog
        ModifyInternalCoordDialog(self, kind).exec()
        self.refresh_views()

    def _on_gaussian_setup(self) -> None:
        from ..dialogs.gaussian_calculation_setup import GaussianCalculationSetupDialog
        GaussianCalculationSetupDialog(self.document, parent=self).exec()

    def _on_rest_setup(self) -> None:
        from ..qc_result_dialog import QcResultDialog
        QcResultDialog(parent=self, document=self.document, initial_tab=1).exec()

    def _on_run_xtb(self) -> None:
        from ...io.calculators import run_xtb_optimization
        from ...application.builtin_commands import MoveMultiAtoms3DCommand
        res = run_xtb_optimization(self.document)
        if res.get("success") and res.get("coords") is not None:
            new_c = res["coords"]
            atom_ids = list(self.document.topology.atom_ids)
            old_map = {aid: self.document.get_atom_3d_pos(aid) for aid in atom_ids}
            new_map = {aid: new_c[i] for i, aid in enumerate(atom_ids) if i < len(new_c)}
            self.command_bus.execute(MoveMultiAtoms3DCommand(old_map, new_map, description="xtb/MMFF94 3D 几何优化"))
            self.refresh_views()

    def _on_new_group_window(self) -> "Studio3DWindow":
        win = Studio3DWindow(document=MoleculeDocument(name="new_group_mol"), pane_count=1)
        win.move(self.x() + 36, self.y() + 36)
        win.show()
        return win

    def _on_spawn_clone_view(self) -> "Studio3DWindow":
        cloned_shell = self.shell.spawn_clone_view(pane_count=self.view_session.pane_count)
        win = Studio3DWindow(document=self.document, pane_count=self.view_session.pane_count, shell=cloned_shell)
        win.move(self.x() + 42, self.y() + 42)
        win.show()
        return win

    def _on_spawn_group_molecule(self) -> "Studio3DWindow":
        grp_shell = self.shell.spawn_group_molecule(document=create_instant_caffeine_document(), pane_count=1)
        win = Studio3DWindow(document=grp_shell.document, pane_count=1, shell=grp_shell)
        win.move(self.x() + 48, self.y() + 48)
        win.show()
        return win

    def _open_welcome(self) -> None:
        from ..welcome_window import AppController
        AppController.instance().show_welcome()

    def refresh_views(self) -> None:
        if hasattr(self, "tabs") and self.tabs.currentWidget() is not None:
            self.tabs.setTabText(self.tabs.currentIndex(), self.document.name)
        self.canvas3d.set_document(self.document)
        n_atoms, n_elec, charge, spin = _compute_electron_count(self.document)
        formula, _ = compute_formula_and_weight_fast(self.document)
        self.setWindowTitle(f"MolForge {__version__} Studio 3D · [{self.group_tag}] {self.document.name}")
        self.status_label.setText(
            f"Atoms: {n_atoms}    Electrons: {n_elec}    Charge: {charge}    Spin: {spin}    "
            f"|    Formula: {formula}    |    Viewports: {self.view_session.pane_count} ({self.group_tag})"
        )


    def project_3d_to_2d(self) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import Project3DTo2DCommand
        right, up = self.canvas3d.get_camera_view_basis()
        res = self.command_bus.execute(Project3DTo2DCommand(camera_right=right, camera_up=up))
        QMessageBox.information(self, "3D ➜ 2D 投影", res.message)

    def generate_3d_conformation(self) -> None:
        if self.document.num_atoms == 0:
            return
        from ...application.builtin_commands import GenerateConformation3DCommand
        res = self.command_bus.execute(GenerateConformation3DCommand(optimize_iters=150))
        self.canvas3d.set_document(self.document)
        self.canvas3d.reset_camera()
        QMessageBox.information(self, "3D 构象生成", res.message)
