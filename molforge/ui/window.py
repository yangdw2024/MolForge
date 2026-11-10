"""
ui/window.py - MolForge v4.0 旗舰分子工作台（对标 GaussView 6.0 + Chem3D + Avogadro 2）
========================================================================================
完整实现 v4 任务书 P0 ~ P5 全部要求：
  1. [P0] 逐原子 / 逐键独立大小与独立颜色控制：
     - 右侧「选中原子大小」滑块只修改当前选中原子的 `atom.scale`（通过 `ChangeAtomStyleCommand` 支持 Undo/Redo）
     - 右侧「选中键粗细」滑块只修改当前选中化学键的 `bond.width_scale`（通过 `ChangeBondStyleCommand` 支持 Undo/Redo）
     - 「设置」页中的全局原子/键滑块控制整体缩放比例，全局缩放与逐对象缩放同时并存！
     - `atom.color` 与 `bond.color` 实时被 3D VTK Glyph/Tube 渲染器与 2D 画布读取，改色立即生效且可撤销！
  2. [P1] 3D 视口直接画分子：
     - 3D 视口点空白加原子、拖原子到另一原子成键、右键删原子/删键、选中后拖动实时移动原子（相连键实时跟随）
  3. [P2] 新建独立 2D 画布 / 新建独立 3D 画布 / 多文档独立窗口并排（GaussView `G1:M1:V1` 风格）
  4. [P3] 拖拽文件直接打开 + 全格式导入导出（SMILES / SDF / MOL / PDB / MOL2 / XYZ / GJF / REST ctrl.in / ORCA .inp）+ 明确错误弹窗
  5. [P4] 完整 GaussView 6.0 + Chem3D 十大菜单体系 (`File / Edit / Tools / Builder / View / Structure / Calculate / Results / Surfaces / Help`)
     + 4 个独立可停靠/浮动检查器窗口 (`ModelExplorerDock` / `CartesianTableDock` / `MeasurementTableDock` / `AtomBondPropertyDock`)
     + 底部 `Build / Select` 放置模式切换 + `Color Scheme` 颜色方案下拉 + 实时状态栏（原子数 / 键数 / 总电荷 Charge / 自旋多重度 Spin）
  6. [P5] 修正预设分子库 SMILES（IC 端基 `O=C1CC(=C(C#N)C#N)c2ccccc12`、2F-IC、2Cl-IC、BT、DTBT、BDT 等）
"""
from __future__ import annotations

import math
import numpy as np
from pathlib import Path
from molforge import __version__
from PyQt6.QtCore import Qt, QSettings, QTimer, QSize
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QGuiApplication
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QButtonGroup, QMenu, QSizePolicy, QComboBox,
    QFileDialog, QMessageBox, QInputDialog, QTabWidget
)

from .panels import TopBar, NavigationRail, Sidebar, RightPanel, HorizontalWheelScrollArea, ic
from .theme import refresh_button_visual
from .render3d_widget import Render3DWidget
from .editor2d_widget import Editor2DWidget
from .views import (
    ModelExplorerDock, CartesianTableDock, MeasurementTableDock,
    AtomBondPropertyDock, DihedralChartDialog, BuilderFragmentDialog,
    ModifyInternalCoordDialog
)
from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId
from ..domain.elements import get_element
from ..application.command_bus import CommandBus
from ..application.selection import SelectionService
from ..io.rdkit_adapter import (
    create_sample_molecule,
    create_molecule_from_smiles,
    doc_to_rdkit,
    create_instant_caffeine_document,
    load_molecule_document,
    compute_formula_and_weight_fast,
    export_document_to_mol_v2000,
    export_document_to_pdb,
    export_document_to_mol2,
    export_document_to_orca_inp,
    perceive_bonds_and_orders_3d,
)


class Workspace(QFrame):
    """中央 2D/3D 联动工作区（含滚轮横向滚动 + 集合菜单 + 强对比点亮反馈）。"""

    def __init__(
        self,
        document: MoleculeDocument,
        selection: SelectionService,
        command_bus=None,
        on_ring_insert=None,
        on_fg_insert=None,
    ):
        super().__init__()
        self.setObjectName("WorkspaceContainer")
        self.document = document
        self.selection = selection
        self.command_bus = command_bus
        self.on_ring_insert = on_ring_insert
        self.on_fg_insert = on_fg_insert
        self._current_element = 6
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        eyebrow = QLabel("MOLECULAR STUDIO WORKSPACE")
        eyebrow.setProperty("role", "section")
        self.title_label = QLabel(f"{document.name}  ·  2D/3D 实时联动工作台")
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        texts.addWidget(eyebrow)
        texts.addWidget(self.title_label)
        header.addLayout(texts, 1)

        root.addLayout(header)
        header = QHBoxLayout()
        self.view_mode_buttons: list[QPushButton] = []
        for i, name in enumerate(("仅 2D 画布", "仅 3D 视口", "2D + 3D 分屏")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setMinimumWidth(94)
            b.clicked.connect(lambda checked=False, idx=i: self.set_mode(idx))
            header.addWidget(b)
            self.view_mode_buttons.append(b)
            refresh_button_visual(b, active=(i == 2))
        root.addLayout(header)

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("ToolbarFrame")
        tf_lay = QHBoxLayout(toolbar_frame)
        tf_lay.setContentsMargins(4, 2, 4, 2)
        tf_lay.setSpacing(0)

        strip = QWidget()
        toolbar = QHBoxLayout(strip)
        toolbar.setContentsMargins(4, 2, 4, 2)
        toolbar.setSpacing(6)

        self.tool_buttons: dict[str, QPushButton] = {}
        for i, (icon_name, name, label_txt, min_w, tip) in enumerate((
            ("select", "选择", "选择 (V)", 72, "选择 / 拖拽移动原子 / Shift 选 2~4 原子测距测角 (快捷键 V)"),
            ("atom", "原子", "原子 (A)", 72, "点击空白加原子并自动成键 / 点击已有原子生长新键 (快捷键 A)"),
            ("bond", "键", "建键 (B)", 72, "在两原子间拖拽连键 / 点击已有键切换单·双·三键 (快捷键 B)"),
            ("cleanup", "擦除", "擦除 (E)", 72, "点击原子或化学键直接删除 (快捷键 E)"),
        )):
            b = QPushButton(label_txt)
            b.setIcon(ic(icon_name))
            b.setIconSize(QSize(14, 14))
            b.setMinimumWidth(min_w)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, n=name: self._on_tool_selected(n))
            toolbar.addWidget(b)
            self.tool_buttons[name] = b
            refresh_button_visual(b, active=(i == 0))

        self.ring_menu_btn = QPushButton("⬡ 环模板 ▾")
        self.ring_menu_btn.setMinimumWidth(88)
        self.ring_menu_btn.setCheckable(True)
        self.ring_menu_btn.setToolTip("集合菜单：选择苯环/噻吩/吡啶/呋喃等共轭环模板，一键接枝或点放 (R)")
        self.ring_menu = QMenu(self)
        ring_specs = [
            ("⬡ 苯环 Benzene (6Ar)", 6, True, {}),
            ("⬠ 噻吩 Thiophene (S)", 5, True, {0: 16}),
            ("⬠ 硒吩 Selenophene (Se)", 5, True, {0: 34}),
            ("⬡ 吡啶 Pyridine (N)", 6, True, {0: 7}),
            ("⬠ 呋喃 Furan (O)", 5, True, {0: 8}),
            ("⬡ 环己烷 Cyclohexane", 6, False, {}),
            ("⬠ 环戊烷 Cyclopentane", 5, False, {}),
            ("□ 环丁烷 Cyclobutane", 4, False, {}),
            ("△ 环丙烷 Cyclopropane", 3, False, {}),
        ]
        for r_label, r_size, r_arom, r_het in ring_specs:
            act = QAction(r_label, self)
            act.triggered.connect(
                lambda checked=False, lbl=r_label, s=r_size, a=r_arom, h=r_het: self._on_ring_menu_picked(lbl, s, a, h)
            )
            self.ring_menu.addAction(act)
        self.ring_menu_btn.clicked.connect(self._show_ring_menu)
        toolbar.addWidget(self.ring_menu_btn)
        self.tool_buttons["环"] = self.ring_menu_btn

        self.fg_menu_btn = QPushButton("🧪 官能团 ▾")
        self.fg_menu_btn.setMinimumWidth(88)
        self.fg_menu_btn.setCheckable(True)
        self.fg_menu_btn.setToolTip("集合菜单：向当前选中原子或外围 C-H 位点一键接枝 -CN / -F / -Cl / -COOH 等基团")
        self.fg_menu = QMenu(self)
        for fg_label, fg_code in (
            ("氰基  -CN (强吸电子端基)", "-CN"),
            ("氟代  -F (卤化深移 HOMO)", "-F"),
            ("氯代  -Cl (卤化调控结晶)", "-Cl"),
            ("羟基  -OH", "-OH"),
            ("氨基  -NH₂", "-NH2"),
            ("羧基  -COOH", "-COOH"),
            ("甲氧基 -OCH₃ (给电子烷氧基)", "-OCH3"),
            ("甲基  -CH₃", "-CH3"),
        ):
            act = QAction(fg_label, self)
            act.triggered.connect(lambda checked=False, code=fg_code: self._on_fg_menu_picked(code))
            self.fg_menu.addAction(act)
        self.fg_menu_btn.clicked.connect(self._show_fg_menu)
        toolbar.addWidget(self.fg_menu_btn)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #2A4258; padding: 0 2px;")
        toolbar.addWidget(sep1)

        self.element_buttons: dict[int, QPushButton] = {}
        self.core_elements = ((6, "C"), (7, "N"), (8, "O"), (16, "S"), (9, "F"))
        for z, sym in self.core_elements:
            eb = QPushButton(sym)
            eb.setProperty("role", "elem")
            eb.setMinimumWidth(34)
            eb.setCheckable(True)
            eb.setToolTip(f"切换当前绘制元素为 {sym} (Z={z}) 并点亮激活态")
            eb.clicked.connect(lambda checked=False, atomic_z=z: self.select_active_element(atomic_z))
            eb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            eb.customContextMenuRequested.connect(lambda pos, sym_s=sym, az=z: self._open_element_fragments_popup(sym_s, az))
            toolbar.addWidget(eb)
            self.element_buttons[z] = eb
            refresh_button_visual(eb, active=(z == 6))

        self.more_elem_btn = QPushButton("更多元素 ▾")
        self.more_elem_btn.setMinimumWidth(90)
        self.more_elem_btn.setCheckable(True)
        self.more_elem_btn.setToolTip("集合菜单：快速选择 Cl / Br / I / P / H / Si / Se / B 或打开 118 元素周期表")
        self.more_elem_menu = QMenu(self)
        extra_elements = (
            (17, "Cl · 氯 (Z=17)"),
            (35, "Br · 溴 (Z=35)"),
            (53, "I · 碘 (Z=53)"),
            (15, "P · 磷 (Z=15)"),
            (1,  "H · 氢 (Z=1)"),
            (14, "Si · 硅 (Z=14)"),
            (34, "Se · 硒 (Z=34, 硒吩常用)"),
            (5,  "B · 硼 (Z=5, B-N 共轭)"),
            (50, "Sn · 锡 (Z=50, Stille 偶联)"),
        )
        for z_ext, lbl_ext in extra_elements:
            act = QAction(lbl_ext, self)
            act.triggered.connect(lambda checked=False, az=z_ext: self.select_active_element(az))
            self.more_elem_menu.addAction(act)
        self.more_elem_menu.addSeparator()
        pt_act = QAction("📅 打开完整 118 元素周期表对话框...", self)
        pt_act.triggered.connect(self._open_periodic_table)
        self.more_elem_menu.addAction(pt_act)
        self.more_elem_btn.clicked.connect(self._show_more_elem_menu)
        toolbar.addWidget(self.more_elem_btn)

        toolbar.addStretch(1)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #2A4258; padding: 0 2px;")
        toolbar.addWidget(sep2)

        from ..rendering.contracts import RepresentationMode
        self.mode_buttons: dict[RepresentationMode, QPushButton] = {}
        for i, (mode, name) in enumerate((
            (RepresentationMode.BALL_AND_STICK, "球棍"),
            (RepresentationMode.CPK, "CPK"),
            (RepresentationMode.LINE, "线框"),
            (RepresentationMode.SURFACE, "表面"),
        )):
            b = QPushButton(name)
            b.setMinimumWidth(54)
            b.setCheckable(True)
            b.setToolTip(f"切换 3D 渲染模式为：{name}")
            b.clicked.connect(lambda checked=False, m=mode: self._on_mode_changed(m))
            toolbar.addWidget(b)
            self.mode_buttons[mode] = b
            refresh_button_visual(b, active=(i == 0))

        tf_lay.addWidget(HorizontalWheelScrollArea(strip, height=40))
        root.addWidget(toolbar_frame)

        self.view_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.view_splitter.setHandleWidth(6)
        self.view_splitter.setChildrenCollapsible(False)

        self.view2d = Editor2DWidget()
        self.view2d.set_document(document)
        self.view2d.set_selection_service(selection)
        if command_bus is not None:
            self.view2d.set_command_bus(command_bus)

        self.view3d_real = Render3DWidget()
        self.view3d_real.set_selection_service(selection)
        if command_bus is not None:
            self.view3d_real.set_command_bus(command_bus)
        QTimer.singleShot(20, lambda: self.view3d_real.set_document(self.document))

        self.view2d.tool_changed_signal.connect(lambda t: self._on_tool_selected(t))
        self.view2d.element_changed_signal.connect(self.select_active_element)

        self.view_splitter.addWidget(self.view2d)
        self.view_splitter.addWidget(self.view3d_real)
        self.view_splitter.setSizes([500, 500])
        root.addWidget(self.view_splitter, 1)

    def _show_ring_menu(self):
        refresh_button_visual(self.ring_menu_btn, active=True)
        pos = self.ring_menu_btn.mapToGlobal(self.ring_menu_btn.rect().bottomLeft())
        self.ring_menu.exec(pos)

    def _on_ring_menu_picked(self, label: str, size: int, aromatic: bool, hetero: dict):
        short = label.split()[1] if len(label.split()) > 1 else "环"
        self.ring_menu_btn.setText(f"⬡ {short} ▾")
        for name, btn in self.tool_buttons.items():
            refresh_button_visual(btn, active=(name == "环"))
        refresh_button_visual(self.fg_menu_btn, active=False)
        self.view2d.set_ring_template(size, aromatic, hetero)
        if self.on_ring_insert is not None:
            self.on_ring_insert(size, aromatic, hetero)

    def _show_fg_menu(self):
        refresh_button_visual(self.fg_menu_btn, active=True)
        pos = self.fg_menu_btn.mapToGlobal(self.fg_menu_btn.rect().bottomLeft())
        self.fg_menu.exec(pos)

    def _on_fg_menu_picked(self, fg_code: str):
        self.fg_menu_btn.setText(f"🧪 {fg_code} ▾")
        refresh_button_visual(self.fg_menu_btn, active=True)
        if self.on_fg_insert is not None:
            self.on_fg_insert(fg_code)

    def _show_more_elem_menu(self):
        pos = self.more_elem_btn.mapToGlobal(self.more_elem_btn.rect().bottomLeft())
        self.more_elem_menu.exec(pos)

    def select_active_element(self, atomic_num: int):
        self._current_element = int(atomic_num)
        for z, btn in self.element_buttons.items():
            refresh_button_visual(btn, active=(z == self._current_element))

        elem = get_element(self._current_element)
        sym = elem.symbol if elem else "C"
        if self._current_element not in self.element_buttons:
            self.more_elem_btn.setText(f"🧪 元素: {sym} ▾")
            refresh_button_visual(self.more_elem_btn, active=True)
        else:
            self.more_elem_btn.setText("更多元素 ▾")
            refresh_button_visual(self.more_elem_btn, active=False)

        self.view2d.set_current_element(self._current_element)
        self.view3d_real.set_current_element(self._current_element)
        if self.view2d._current_tool == "选择":
            self._on_tool_selected("原子")

    def _open_element_fragments_popup(self, symbol: str, atomic_z: int):
        self.select_active_element(atomic_z)
        cat = symbol
        from .dialogs.element_fragments import ElementFragmentsDialog
        from ..application.fragment_commands import InsertFragmentCommand
        dlg = ElementFragmentsDialog(parent=self, initial_category=cat)
        if dlg.exec() and dlg.selected_fragment is not None and self.command_bus is not None:
            sel_atoms = list(self.selection.selected_atoms) if self.selection else []
            anchor = sel_atoms[-1] if sel_atoms else None
            res = self.command_bus.execute(InsertFragmentCommand(dlg.selected_fragment, anchor_atom_id=None if dlg.shell.isChecked() else anchor, attach_to_existing=not dlg.shell.isChecked()))
            if res.success:
                self.view2d.recompute_2d_layout()
                self.view2d.update()
                self.view3d_real.set_document(self.document)

    def _open_periodic_table(self):
        from .element_picker import ElementPickerDialog
        dlg = ElementPickerDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.selected_element is not None:
            self.select_active_element(dlg.selected_element.atomic_number)

    def set_mode(self, index: int):
        for i, b in enumerate(self.view_mode_buttons):
            refresh_button_visual(b, active=(i == index))
        self.view2d.setVisible(index in (0, 2))
        self.view3d_real.setVisible(index in (1, 2))
        if index == 2:
            self.view_splitter.setSizes([500, 500])
        elif index == 0:
            self.view_splitter.setSizes([1000, 0])
        elif index == 1:
            self.view_splitter.setSizes([0, 1000])

    def _on_mode_changed(self, mode):
        for m, btn in self.mode_buttons.items():
            refresh_button_visual(btn, active=(m == mode))
        self.view3d_real.set_mode(mode)

    def _on_tool_selected(self, tool_name: str):
        if tool_name == "环":
            self._show_ring_menu()
            return
        for name, btn in self.tool_buttons.items():
            refresh_button_visual(btn, active=(name == tool_name))
        refresh_button_visual(self.fg_menu_btn, active=False)
        self.view2d._pending_ring = None
        self.view2d.set_current_tool(tool_name)
        self.view3d_real.set_current_tool(tool_name)


class MolForgeWindow(QMainWindow):
    """
    MolForge v4.0 主窗口（支持 GaussView G1:M1:V1 多窗口并排、独立 2D/3D 画布与全套可停靠面板）。
    """

    _open_windows: list["MolForgeWindow"] = []
    _next_group_id: int = 1

    def __init__(
        self,
        initial_document: MoleculeDocument | None = None,
        initial_view_mode: int = 2,
        group_tag: str | None = None,
    ):
        super().__init__()
        if group_tag is None:
            g_idx = MolForgeWindow._next_group_id
            MolForgeWindow._next_group_id += 1
            self.group_tag = f"G{g_idx}:M1:V1"
        else:
            self.group_tag = group_tag
        MolForgeWindow._open_windows.append(self)

        self.document = initial_document if initial_document is not None else create_instant_caffeine_document()
        self.setWindowTitle(f"[{self.group_tag}] {self.document.name} — MolForge {__version__} · AI-Native Molecular & OSC Workbench")
        self.resize(1620, 930)
        self.setMinimumSize(1040, 660)
        self.setAcceptDrops(True)
        self._saved_revisions = {self.document.document_id: self.document.revision}
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(300_000)
        self._autosave_timer.timeout.connect(self._run_project_autosave)
        self._autosave_timer.start()
        self.settings = QSettings("MolForge", "VisualPreview-v4")

        from ..application.workspace_registry import WorkspaceRegistry
        self.session, self.view_session = WorkspaceRegistry.instance().register_explicit_tag(
            self.group_tag, self.document
        )
        self.command_bus = self.session.command_bus
        self.command_bus.add_listener(lambda result, doc=self.document: self._on_document_changed(doc) if self.document is doc else None)
        self.selection = self.session.selection
        self.selection.add_listener(lambda origin: QTimer.singleShot(0, self._on_selection_changed))

        # 独立可停靠面板引用
        self._explorer_dock: ModelExplorerDock | None = None
        self._cartesian_dock: CartesianTableDock | None = None
        self._measurement_dock: MeasurementTableDock | None = None
        self._property_dock: AtomBondPropertyDock | None = None

        center = QWidget()
        center.setObjectName("CentralShell")
        root = QVBoxLayout(center)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = TopBar()
        self.top_bar.open_clicked.connect(self._on_open_file)
        self.top_bar.export_clicked.connect(self._on_export)
        self.top_bar.qc_workbench_clicked.connect(self._open_qc_log)
        self.top_bar.search_submitted.connect(self._on_top_search_command)
        root.addWidget(self.top_bar)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(5)

        self.left_panel = QWidget()
        left_lay = QHBoxLayout(self.left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)
        self.nav_rail = NavigationRail()
        left_lay.addWidget(self.nav_rail)
        self.sidebar = Sidebar(
            on_molecule_selected=self._on_molecule_selected,
            on_ring_insert=self._on_ring_insert,
            on_fg_insert=self._on_fg_insert,
        )
        left_lay.addWidget(self.sidebar)

        self.workspace = Workspace(
            self.document,
            self.selection,
            self.command_bus,
            on_ring_insert=self._on_ring_insert,
            on_fg_insert=self._on_fg_insert,
        )
        self.workspace.view3d_real.status_callback = lambda msg: self.status_left.setText(f"[{self.group_tag}]  {msg}")
        self.right = RightPanel()
        self.right._window_ref = self
        self.nav_rail.rail_selected.connect(self.right.switch_tab)
        self.right.stack.currentChanged.connect(self.nav_rail.set_active_index)

        # 挂载新版 LeftPanel 核心操作与双向画布联动
        self.left_panel._window_ref = self
        self.sidebar._window_ref = self
        self.sidebar.on_element_selected = self.select_active_element
        self.sidebar.on_bond_order_selected = self._set_selected_bond_order
        self.sidebar.on_clean_2d = self.workspace.view2d.recompute_2d_layout
        self.sidebar.on_clean_3d = self.workspace.view3d_real.clean_3d_geometry
        self.sidebar.on_add_h = self._on_add_missing_hydrogens
        self.sidebar.on_remove_h = self._on_remove_hydrogens
        self.sidebar.on_center = self._on_center_origin
        self.sidebar.on_open_periodic_table = self._open_periodic_table
        self.sidebar.on_atom_selected = self._on_tree_atom_selected
        self.sidebar.on_bond_selected = self._on_tree_bond_selected
        self.sidebar.on_custom_fragment_insert = self._on_paste_custom_fragment

        self._build_menubar()

        self.main_splitter.addWidget(self.left_panel)
        self.document_tabs = QTabWidget(self)
        self.document_tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.setMovable(True)
        self.document_tabs.tabCloseRequested.connect(self._close_document_tab)
        self.document_tabs.currentChanged.connect(self._activate_document_tab)
        self.document_tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.document_tabs.tabBar().customContextMenuRequested.connect(self._document_tab_menu)
        self._document_pages = {self.workspace: (self.session, self.view_session, self.group_tag)}
        self.document_tabs.blockSignals(True)
        self.document_tabs.addTab(self.workspace, self.document.name)
        self.document_tabs.blockSignals(False)
        self.main_splitter.addWidget(self.document_tabs)
        self.main_splitter.addWidget(self.right)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        root.addWidget(self.main_splitter, 1)

        # 底部增强状态栏（含 Build/Select 放置切换、颜色方案下拉、原子数/电荷/自旋实时显示）
        status = QFrame()
        status.setFixedHeight(32)
        status.setStyleSheet("QFrame {background:#09111B; border-top:1px solid #22384E}")
        status_lay = QHBoxLayout(status)
        status_lay.setContentsMargins(12, 2, 12, 2)
        status_lay.setSpacing(10)

        self.status_left = QLabel(f"[{self.group_tag}] {self.document.name} · 逐原子/逐键独立渲染已开启")
        self.status_left.setStyleSheet("color:#66DEC9; font-size:12px; font-weight:600;")
        status_lay.addWidget(self.status_left)

        status_lay.addStretch()

        # 折叠/展开侧边栏按钮
        self.sidebar_collapsed = False
        self._pre_collapse_sizes = None
        self.toggle_sidebar_btn = QPushButton("📐 折叠侧边栏")
        self.toggle_sidebar_btn.setCheckable(True)
        self.toggle_sidebar_btn.setToolTip("一键收起左右侧边栏，中间画布占满全屏")
        self.toggle_sidebar_btn.clicked.connect(self._toggle_sidebar_collapse)
        status_lay.addWidget(self.toggle_sidebar_btn)

        # Build / Select Placement 快捷切换按钮 (P4)
        self.placement_mode_btn = QPushButton("🎯 放置模式: 选择/移动 (Select)")
        self.placement_mode_btn.setCheckable(True)
        self.placement_mode_btn.setMinimumWidth(165)
        self.placement_mode_btn.setToolTip("在 [Select 选择/移动] 与 [Build 点击画布直接放置原子/构件] 之间切换")
        self.placement_mode_btn.clicked.connect(self._toggle_placement_mode)
        status_lay.addWidget(self.placement_mode_btn)

        # Color Scheme 配色方案下拉 (P4)
        scheme_lbl = QLabel("配色:")
        scheme_lbl.setProperty("role", "muted")
        status_lay.addWidget(scheme_lbl)
        self.scheme_combo = QComboBox()
        for sc_name in ("Default Scheme", "Studio CPK", "GaussView Classic", "Jmol Standard", "Carbon Cyan (PyMOL)"):
            self.scheme_combo.addItem(sc_name)
        self.scheme_combo.setMinimumWidth(145)
        self.scheme_combo.currentTextChanged.connect(self._on_color_scheme_changed)
        status_lay.addWidget(self.scheme_combo)

        self.status_right = QLabel("原子: 24  ·  键: 25  ·  Charge: 0  ·  Spin: 1 (Singlet)")
        self.status_right.setProperty("role", "value")
        status_lay.addWidget(self.status_right)
        root.addWidget(status)
        self.setCentralWidget(center)

        # 连接设置面板（全局缩放）与右侧属性面板（单原子/单键独立缩放）
        settings_panel = self.right.settings_panel
        settings_panel.atom_size_changed.connect(self._on_global_atom_scale)
        settings_panel.bond_width_changed.connect(self._on_global_bond_scale)
        settings_panel.background_3d_changed.connect(self._on_background_3d_changed)
        settings_panel.canvas_color_changed.connect(self._on_2d_bg_changed)
        settings_panel.material_changed.connect(self._on_material_preset_changed)
        settings_panel.roughness_changed.connect(self.workspace.view3d_real.set_roughness)
        settings_panel.metallic_changed.connect(self.workspace.view3d_real.set_metallic)
        settings_panel.theme_changed.connect(self._on_theme_changed)
        settings_panel.accent_picked.connect(self._on_accent_changed)

        self.right.set_document_provider(lambda: self.document)
        self.right.set_command_bus_provider(lambda: self.command_bus)
        self.right.set_selection_provider(lambda: self.selection)
        self.right.ai_action_executor = self._execute_ai_action

        self._wire_right_panel_callbacks()
        window_menu = self.menuBar().addMenu('窗口(&W)')
        window_menu.addAction('弹出为独立 3D 窗口', lambda: self._pop_document('3d'))
        window_menu.addAction('弹出为独立 2D 窗口', lambda: self._pop_document('2d'))
        self.workspace.view3d_real.on_add_atom_at_3d = self._add_atom_at_3d
        self.workspace.view3d_real.on_delete_selected_3d = self._delete_selected

        if initial_view_mode in (0, 1, 2):
            self.workspace.set_mode(initial_view_mode)

        QTimer.singleShot(0, self._finish_layout)

    # ---------- 底部放置模式与配色方案切换 ----------

    def _toggle_left_panel(self):
        sizes = self.main_splitter.sizes()
        if sizes[0] > 0:
            self._last_left_width = sizes[0]
            sizes[0] = 0
        else:
            sizes[0] = getattr(self, "_last_left_width", 250) or 250
        self.main_splitter.setSizes(sizes)
        if hasattr(self.workspace, "view2d"):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(60, self.workspace.view2d.fit_view)

    def _toggle_right_panel(self):
        sizes = self.main_splitter.sizes()
        if sizes[2] > 0:
            self._last_right_width = sizes[2]
            sizes[2] = 0
        else:
            sizes[2] = getattr(self, "_last_right_width", 330) or 330
        self.main_splitter.setSizes(sizes)
        if hasattr(self.workspace, "view2d"):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(60, self.workspace.view2d.fit_view)

    def _toggle_sidebar_collapse(self, checked: bool):
        """一键收起/展开左右侧边栏，中间画布占满全屏（真正完全隐藏）"""
        if checked:
            # 折叠：直接隐藏左右栏
            self.left_panel.setVisible(False)
            self.right.setVisible(False)
            self.toggle_sidebar_btn.setText("📐 展开侧边栏")
            self.sidebar_collapsed = True
        else:
            # 展开：重新显示左右栏
            self.left_panel.setVisible(True)
            self.right.setVisible(True)
            self.toggle_sidebar_btn.setText("📐 折叠侧边栏")
            self.sidebar_collapsed = False

    def _toggle_placement_mode(self, checked: bool):
        if checked:
            self.placement_mode_btn.setText("🔨 放置模式: 点放构建 (Build)")
            refresh_button_visual(self.placement_mode_btn, active=True)
            self.workspace._on_tool_selected("原子")
        else:
            self.placement_mode_btn.setText("🎯 放置模式: 选择/移动 (Select)")
            refresh_button_visual(self.placement_mode_btn, active=False)
            self.workspace._on_tool_selected("选择")

    def _on_color_scheme_changed(self, scheme_name: str):
        self.workspace.view3d_real.set_color_scheme(scheme_name)
        self.status_left.setText(f"[{self.group_tag}] 已切换 3D 颜色方案为：{scheme_name}")

    # ---------- 拖拽文件进入窗口直接打开 (P3) ----------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            local_path = urls[0].toLocalFile()
            if local_path:
                self.open_molecule_file(local_path)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    # ---------- 全局缩放 vs 逐原子/逐键独立缩放 (P0 核心修复) ----------

    def _on_global_atom_scale(self, scale: float):
        """[设置]页滑块：调整全局原子球比例，保留每个原子的独立相对比例。"""
        self.workspace.view3d_real.set_atom_scale(scale)
        v = int(round(scale * 100))
        self.right.settings_panel.atom_size_slider.blockSignals(True)
        self.right.settings_panel.atom_size_slider.setValue(v)
        self.right.settings_panel.atom_val_label.setText(f"{v}%")
        self.right.settings_panel.atom_size_slider.blockSignals(False)

    def _on_global_bond_scale(self, scale: float):
        """[设置]页滑块：调整全局化学键粗细比例，保留每条键的独立相对比例。"""
        self.workspace.view3d_real.set_bond_scale(scale)
        v = int(round(scale * 100))
        self.right.settings_panel.bond_width_slider.blockSignals(True)
        self.right.settings_panel.bond_width_slider.setValue(v)
        self.right.settings_panel.bond_val_label.setText(f"{v}%")
        self.right.settings_panel.bond_width_slider.blockSignals(False)

    def _set_selected_atom_scale(self, scale: float):
        """[属性]页滑块：只缩放当前选中的那一个（或几个）原子的独立半径，并记录 Undo/Redo！"""
        atoms = list(self.selection.selected_atoms)
        if not atoms:
            return
        from ..application.builtin_commands import ChangeAtomStyleCommand
        self.command_bus.execute(ChangeAtomStyleCommand(atoms, scale=float(scale)))
        for aid in atoms:
            self.workspace.view3d_real.update_single_atom_style(aid, scale=float(scale))

    def _set_selected_bond_width(self, scale: float):
        """[属性]页滑块：只缩放当前选中的那一条（或几条）化学键的独立粗细，并记录 Undo/Redo！"""
        bonds = list(self.selection.selected_bonds)
        if not bonds:
            return
        from ..application.builtin_commands import ChangeBondStyleCommand
        self.command_bus.execute(ChangeBondStyleCommand(bonds, width_scale=float(scale)))
        for bid in bonds:
            self.workspace.view3d_real.update_single_bond_style(bid, width_scale=float(scale))
        self.workspace.view2d.update()

    def _wire_right_panel_callbacks(self):
        self.right.on_change_element = self._change_selected_atom_element
        self.right.on_atom_scale = self._on_global_atom_scale
        self.right.on_selected_atom_scale = self._set_selected_atom_scale
        self.right.on_charge = self._set_selected_atom_charge
        self.right.on_pick_color = self._pick_selected_atom_color
        self.right.on_bond_order = self._set_selected_bond_order
        self.right.on_bond_length = self._set_selected_bond_length
        self.right.on_bond_width = self._on_global_bond_scale
        self.right.on_selected_bond_width = self._set_selected_bond_width
        self.right.on_pick_bond_color = self._pick_selected_bond_color
        self.right.on_generate_conformers = self._generate_conformers
        self.right.on_open_qc_log = self._open_qc_log
        self.right.on_atom_xyz_edited = self._set_selected_atom_xyz
        self.right.on_open_modify_internal = self._open_modify_internal_dialog

    # ===========================================================================
    # P4：完整 GaussView 6.0 + Chem3D 十大菜单体系
    # ===========================================================================
    def _build_menubar(self):
        menubar = self.menuBar()
        menubar.clear()

        # -------------------- 1. File (文件) --------------------
        file_menu = menubar.addMenu("文件(&F)")

        new_group_act = QAction("新建分子组...", self)
        new_group_act.setShortcut("Ctrl+N")
        new_group_act.triggered.connect(self._on_new_blank)
        file_menu.addAction(new_group_act)

        add_group_act = QAction("添加到分子组...", self)
        add_group_act.setShortcut("Ctrl+Shift+A")
        add_group_act.triggered.connect(self._on_add_to_group)
        file_menu.addAction(add_group_act)

        file_menu.addSeparator()

        new_blank_act = QAction("清空画布", self)
        new_blank_act.setShortcut("Ctrl+Shift+N")
        new_blank_act.triggered.connect(self._on_new_blank)
        file_menu.addAction(new_blank_act)

        new_2d_act = QAction("新建 2D 独立窗口", self)
        new_2d_act.triggered.connect(lambda: self._spawn_new_window(initial_mode=0, blank=True))
        file_menu.addAction(new_2d_act)

        new_3d_act = QAction("新建 3D 独立窗口", self)
        new_3d_act.triggered.connect(lambda: self._spawn_new_window(initial_mode=1, blank=True))
        file_menu.addAction(new_3d_act)

        file_menu.addSeparator()

        open_act = QAction("打开文件...", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._on_open_file)
        file_menu.addAction(open_act)

        self.recent_menu = file_menu.addMenu("最近打开文件")
        self._rebuild_recent_files_menu()

        related_act = QAction("关联文件查看...", self)
        related_act.triggered.connect(self._on_show_related_files)
        file_menu.addAction(related_act)

        file_menu.addSeparator()

        save_proj_act = QAction("保存工程 (.mforge)...", self)
        save_proj_act.setShortcut("Ctrl+S")
        save_proj_act.triggered.connect(self._on_save_mforge_project)
        file_menu.addAction(save_proj_act)

        export_act = QAction("导出结构 / 输入卡...", self)
        export_act.setShortcut("Ctrl+E")
        export_act.triggered.connect(self._on_export)
        file_menu.addAction(export_act)

        save_temp_act = QAction("保存临时快照", self)
        save_temp_act.triggered.connect(self._on_save_temp_file)
        file_menu.addAction(save_temp_act)

        convert_act = QAction("批量格式转换器 (Convert Files)...", self)
        convert_act.triggered.connect(self._on_convert_files_dialog)
        file_menu.addAction(convert_act)

        file_menu.addSeparator()

        save_img_act = QAction("保存高清渲染图像 (Save Image PNG/SVG)...", self)
        save_img_act.setShortcut("Ctrl+I")
        save_img_act.triggered.connect(self._on_save_image_only)
        file_menu.addAction(save_img_act)

        save_mov_act = QAction("导出轨迹与构象动画帧 (Save Movie / Frames)...", self)
        save_mov_act.triggered.connect(self._on_open_trajectory)
        file_menu.addAction(save_mov_act)

        print_act = QAction("打印当前分子视图 (Print / Export PDF)...", self)
        print_act.setShortcut("Ctrl+P")
        print_act.triggered.connect(self._on_save_image_only)
        file_menu.addAction(print_act)

        file_menu.addSeparator()

        pref_act = QAction("首选项与渲染主题...", self)
        pref_act.triggered.connect(lambda: self.right.switch_tab(4))
        file_menu.addAction(pref_act)

        exit_act = QAction("退出", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # -------------------- 2. Edit (编辑) --------------------
        edit_menu = menubar.addMenu("编辑(&E)")

        undo_act = QAction("撤销", self)
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(self._undo)
        edit_menu.addAction(undo_act)

        redo_act = QAction("重做", self)
        redo_act.setShortcuts(["Ctrl+Y", "Ctrl+Shift+Z"])
        redo_act.triggered.connect(self._redo)
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        cut_act = QAction("剪切", self)
        cut_act.setShortcut("Ctrl+X")
        cut_act.triggered.connect(self._on_cut_molecule)
        edit_menu.addAction(cut_act)

        copy_act = QAction("复制", self)
        copy_act.setShortcut("Ctrl+C")
        copy_act.triggered.connect(self._on_copy_molecule)
        edit_menu.addAction(copy_act)

        paste_act = QAction("粘贴", self)
        paste_act.setShortcut("Ctrl+V")
        paste_act.triggered.connect(self._on_paste_molecule)
        edit_menu.addAction(paste_act)

        sel_all_act = QAction("全选", self)
        sel_all_act.setShortcut("Ctrl+Shift+A")
        sel_all_act.triggered.connect(self._on_select_all)
        edit_menu.addAction(sel_all_act)

        del_act = QAction("删除选中", self)
        del_act.setShortcut("Delete")
        del_act.triggered.connect(self._delete_selected)
        edit_menu.addAction(del_act)

        img_cap_act = QAction("复制视图截图", self)
        img_cap_act.triggered.connect(self._on_capture_clipboard)
        edit_menu.addAction(img_cap_act)

        edit_menu.addSeparator()

        std_z_act = QAction("居中并标准化坐标", self)
        std_z_act.triggered.connect(self._on_center_origin)
        edit_menu.addAction(std_z_act)

        symm_act = QAction("惯性主轴对齐", self)
        symm_act.triggered.connect(self._on_reorient_principal_axes)
        edit_menu.addAction(symm_act)

        rebond_act = QAction("重新感知共价键", self)
        rebond_act.triggered.connect(self._on_rebond_3d)
        edit_menu.addAction(rebond_act)

        rm_weak_act = QAction("移除超长弱键", self)
        rm_weak_act.triggered.connect(self._on_remove_weak_bonds)
        edit_menu.addAction(rm_weak_act)

        clean_act = QAction("3D 结构优化清理", self)
        clean_act.setShortcut("Ctrl+M")
        clean_act.triggered.connect(self.workspace.view3d_real.clean_3d_geometry)
        edit_menu.addAction(clean_act)

        mirror_act = QAction("镜像反转手性", self)
        mirror_act.triggered.connect(self._on_mirror_invert)
        edit_menu.addAction(mirror_act)

        # -------------------- 3. Tools (工具) --------------------
        tools_menu = menubar.addMenu("工具(&T)")

        atom_list_act = QAction("笛卡尔坐标表...", self)
        atom_list_act.triggered.connect(self.toggle_cartesian_table_dock)
        tools_menu.addAction(atom_list_act)

        red_coord_act = QAction("冗余内坐标表...", self)
        red_coord_act.triggered.connect(self.toggle_measurement_table_dock)
        tools_menu.addAction(red_coord_act)

        conn_act = QAction("拓扑连接表...", self)
        conn_act.triggered.connect(self.toggle_property_table_dock)
        tools_menu.addAction(conn_act)

        grp_act = QAction("结构浏览器...", self)
        grp_act.triggered.connect(self.toggle_model_explorer_dock)
        tools_menu.addAction(grp_act)

        sel_by_act = QAction("按元素或 SMARTS 批量选择原子 (Atom Selection)...", self)
        sel_by_act.triggered.connect(self._on_select_by_element_dialog)
        tools_menu.addAction(sel_by_act)

        tools_menu.addSeparator()

        pdb_res_act = QAction("PDB 残基与二级结构查看器 (PDB Residues / Secondary Structure)...", self)
        pdb_res_act.triggered.connect(self._on_open_bio)
        tools_menu.addAction(pdb_res_act)

        pg_act = QAction("分子点群对称性判定 (Point Group)...", self)
        pg_act.triggered.connect(self._on_show_point_group)
        tools_menu.addAction(pg_act)

        pbc_act = QAction("周期性边界条件晶胞 (PBC)...", self)
        pbc_act.triggered.connect(self._on_show_pbc_info)
        tools_menu.addAction(pbc_act)

        mos_act = QAction("分子轨道与能级图分析 (MOs)...", self)
        mos_act.triggered.connect(self._open_qc_log)
        tools_menu.addAction(mos_act)

        custom_bond_act = QAction("自定义共价成键参数 (Custom Bonding Parameters)...", self)
        custom_bond_act.triggered.connect(self._on_rebond_3d)
        tools_menu.addAction(custom_bond_act)

        # -------------------- 4. Builder (构建器) --------------------
        builder_menu = menubar.addMenu("构建器(&B)")

        for cat_lbl, cat_key in (
            ("元素杂化片段 (Element Fragment)...", "Element"),
            ("共轭环与杂环片段 (Ring Fragment)...", "Ring"),
            ("OSC 官能团片段 (R-Group Fragment)...", "R-Group"),
            ("生物大分子构件 (Biological Fragment)...", "Bio"),
            ("自定义 SMILES 构件 (Custom Fragment)...", "Custom"),
        ):
            act = QAction(cat_lbl, self)
            act.triggered.connect(lambda checked=False, ck=cat_key: BuilderFragmentDialog(self, ck).exec())
            builder_menu.addAction(act)

        builder_menu.addSeparator()

        mod_b_act = QAction("精确修改键长 (Modify Bond)...", self)
        mod_b_act.triggered.connect(lambda: ModifyInternalCoordDialog(self, "bond").exec())
        builder_menu.addAction(mod_b_act)

        mod_a_act = QAction("精确修改键角 (Modify Angle)...", self)
        mod_a_act.triggered.connect(lambda: ModifyInternalCoordDialog(self, "angle").exec())
        builder_menu.addAction(mod_a_act)

        mod_d_act = QAction("精确修改二面角 (Modify Dihedral)...", self)
        mod_d_act.triggered.connect(lambda: ModifyInternalCoordDialog(self, "dihedral").exec())
        builder_menu.addAction(mod_d_act)

        inq_act = QAction("几何查询模式 (Inquire: Shift 选 2~4 原子)", self)
        inq_act.triggered.connect(lambda: self.workspace._on_tool_selected("选择"))
        builder_menu.addAction(inq_act)

        builder_menu.addSeparator()

        add_val_act = QAction("自动补齐满价态氢原子 (Add Valence / Add Hydrogens)", self)
        add_val_act.triggered.connect(self._on_add_missing_hydrogens)
        builder_menu.addAction(add_val_act)

        del_atom_act = QAction("擦除原子模式 (Delete Atom Tool)", self)
        del_atom_act.triggered.connect(lambda: self.workspace._on_tool_selected("擦除"))
        builder_menu.addAction(del_atom_act)

        inv_atom_act = QAction("翻转手性中心 (Invert Atom / Structure)", self)
        inv_atom_act.triggered.connect(self._on_mirror_invert)
        builder_menu.addAction(inv_atom_act)

        sel_mode_act = QAction("点选 / 框选原子模式 (Select Atoms by Clicking/Rubberband)", self)
        sel_mode_act.triggered.connect(lambda: self.workspace._on_tool_selected("选择"))
        builder_menu.addAction(sel_mode_act)

        # -------------------- 5. View (视图 + 独立可停靠面板) --------------------
        view_menu = menubar.addMenu("视图(&V)")

        add_view_act = QAction("新建并排分子视图窗口 (Add View, G1:M1:V2)...", self)
        add_view_act.triggered.connect(self._on_add_clone_view)
        view_menu.addAction(add_view_act)

        mv_menu = view_menu.addMenu("🪟 3D 单窗口多视口分屏 (1 / 2 / 4 Viewports P1..P4)")
        for cnt, lbl in ((1, "单视口模式 (1 Viewport: P1)"), (2, "左右双视口模式 (2 Viewports: P1 | P2)"), (4, "四视口正交+透视模式 (4 Viewports: P1..P4)")):
            mv_act = QAction(lbl, self)
            mv_act.triggered.connect(lambda checked=False, c=cnt: self.set_3d_multiview_count(c))
            mv_menu.addAction(mv_act)

        welcome_act = QAction("🏠 打开系统启动欢迎页 (Welcome Launcher: 2D / 3D / Split)...", self)
        welcome_act.triggered.connect(self._open_welcome_launcher)
        view_menu.addAction(welcome_act)

        fit_2d_act = QAction("2D 画布居中适配 (Fit 2D View)", self)
        fit_2d_act.setShortcut("0")
        fit_2d_act.triggered.connect(lambda: self.workspace.view2d.fit_view() if hasattr(self.workspace, "view2d") else None)
        view_menu.addAction(fit_2d_act)

        view_menu.addSeparator()
        toggle_left_act = QAction("折叠/展开左侧结构栏", self)
        toggle_left_act.setShortcut("Ctrl+[")
        toggle_left_act.triggered.connect(self._toggle_left_panel)
        view_menu.addAction(toggle_left_act)

        toggle_right_act = QAction("折叠/展开右侧属性栏", self)
        toggle_right_act.setShortcut("Ctrl+]")
        toggle_right_act.triggered.connect(self._toggle_right_panel)
        view_menu.addAction(toggle_right_act)

        center_act = QAction("正视居中分子 (Center)", self)
        center_act.triggered.connect(self.workspace.view3d_real.reset_camera)
        view_menu.addAction(center_act)

        view_menu.addSeparator()
        front_act = QAction("前视图 (Front, 沿 -Z)", self)
        front_act.triggered.connect(lambda: self.workspace.view3d_real.set_view_direction("front"))
        view_menu.addAction(front_act)
        side_act = QAction("侧视图 (Side, 沿 -X)", self)
        side_act.triggered.connect(lambda: self.workspace.view3d_real.set_view_direction("side"))
        view_menu.addAction(side_act)
        top_act = QAction("俯视图 (Top, 沿 +Y)", self)
        top_act.triggered.connect(lambda: self.workspace.view3d_real.set_view_direction("top"))
        view_menu.addAction(top_act)
        iso_act = QAction("等轴测图 (Isometric)", self)
        iso_act.triggered.connect(lambda: self.workspace.view3d_real.set_view_direction("iso"))
        view_menu.addAction(iso_act)
        view_menu.addSeparator()

        # 勾选开关：Hydrogens / Dummies / Labels / Symbols / Bonds / Cartesian Axes / Stereochemistry
        self.act_show_h = QAction("显示氢原子 (Hydrogens)", self)
        self.act_show_h.setCheckable(True)
        self.act_show_h.setChecked(True)
        self.act_show_h.toggled.connect(self._on_toggle_view_options)
        view_menu.addAction(self.act_show_h)

        self.act_show_dummies = QAction("显示虚原子 (Dummies)", self)
        self.act_show_dummies.setCheckable(True)
        self.act_show_dummies.setChecked(True)
        view_menu.addAction(self.act_show_dummies)

        self.act_show_labels = QAction("显示原子序号标签 (Labels #1, #2...)", self)
        self.act_show_labels.setCheckable(True)
        self.act_show_labels.setChecked(False)
        self.act_show_labels.toggled.connect(self._on_toggle_view_options)
        view_menu.addAction(self.act_show_labels)

        self.act_show_symbols = QAction("显示 3D 元素符号 (Symbols C, N, O...)", self)
        self.act_show_symbols.setCheckable(True)
        self.act_show_symbols.setChecked(False)
        self.act_show_symbols.toggled.connect(self._on_toggle_view_options)
        view_menu.addAction(self.act_show_symbols)

        self.act_show_bonds = QAction("显示化学键 (Bonds)", self)
        self.act_show_bonds.setCheckable(True)
        self.act_show_bonds.setChecked(True)
        self.act_show_bonds.toggled.connect(self._on_toggle_view_options)
        view_menu.addAction(self.act_show_bonds)

        self.act_show_axes = QAction("显示三维笛卡尔坐标轴 (Cartesian Axes)", self)
        self.act_show_axes.setCheckable(True)
        self.act_show_axes.setChecked(True)
        self.act_show_axes.toggled.connect(self._on_toggle_view_options)
        view_menu.addAction(self.act_show_axes)

        self.act_show_stereo = QAction("显示立体化学标记 (Stereochemistry)", self)
        self.act_show_stereo.setCheckable(True)
        self.act_show_stereo.setChecked(False)
        view_menu.addAction(self.act_show_stereo)

        view_menu.addSeparator()

        # Chem3D + GaussView 独立可停靠/浮动面板开关
        exp_dock_act = QAction("🌲 模型结构树面板 (Model Explorer / Structure Browser)", self)
        exp_dock_act.triggered.connect(self.toggle_model_explorer_dock)
        view_menu.addAction(exp_dock_act)

        cart_dock_act = QAction("📋 笛卡尔坐标实时编辑表 (Cartesian Table)", self)
        cart_dock_act.triggered.connect(self.toggle_cartesian_table_dock)
        view_menu.addAction(cart_dock_act)

        meas_dock_act = QAction("📏 内坐标与测量表 (Measurement Table)", self)
        meas_dock_act.triggered.connect(self.toggle_measurement_table_dock)
        view_menu.addAction(meas_dock_act)

        prop_dock_act = QAction("🎨 逐原子/逐键属性与颜色表 (Atom & Bond Property Table)", self)
        prop_dock_act.triggered.connect(self.toggle_property_table_dock)
        view_menu.addAction(prop_dock_act)

        dih_chart_act = QAction("📈 二面角扭转势能图 (Dihedral Chart)...", self)
        dih_chart_act.triggered.connect(lambda: DihedralChartDialog(self).exec())
        view_menu.addAction(dih_chart_act)

        view_menu.addSeparator()

        disp_fmt_act = QAction("显示格式与材质设置 (Display Format)...", self)
        disp_fmt_act.setShortcut("Ctrl+D")
        disp_fmt_act.triggered.connect(lambda: self.right.switch_tab(4))
        view_menu.addAction(disp_fmt_act)

        # -------------------- 6. Structure (结构) --------------------
        struct_menu = menubar.addMenu("结构(&S)")

        m_dist_act = QAction("测量原子间距 / 键长 (Measure Distance)", self)
        m_dist_act.triggered.connect(self.toggle_measurement_table_dock)
        struct_menu.addAction(m_dist_act)

        m_ang_act = QAction("测量键角 (Measure Angle)", self)
        m_ang_act.triggered.connect(self.toggle_measurement_table_dock)
        struct_menu.addAction(m_ang_act)

        m_dih_act = QAction("测量二面角与势能曲线 (Measure Dihedral)", self)
        m_dih_act.triggered.connect(lambda: DihedralChartDialog(self).exec())
        struct_menu.addAction(m_dih_act)

        struct_menu.addSeparator()

        clean_2d_act = QAction("重排 2D 结构布局 (Clean Up 2D)", self)
        clean_2d_act.triggered.connect(self.workspace.view2d.recompute_2d_layout)
        struct_menu.addAction(clean_2d_act)

        clean_3d_act = QAction("弛豫清理 3D 几何构型 (Clean Up 3D)", self)
        clean_3d_act.triggered.connect(self.workspace.view3d_real.clean_3d_geometry)
        struct_menu.addAction(clean_3d_act)

        align_act = QAction("主平面与坐标轴对齐 (Align Structure)", self)
        align_act.triggered.connect(self._on_reorient_principal_axes)
        struct_menu.addAction(align_act)

        # -------------------- 7. Calculate (计算) --------------------
        calc_menu = menubar.addMenu("计算(&C)")

        g_setup_act = QAction("Gaussian 输入向导...", self)
        g_setup_act.setShortcut("Ctrl+G")
        g_setup_act.triggered.connect(self._open_gaussian_11tab_setup)
        calc_menu.addAction(g_setup_act)

        g_quick_act = QAction("REST / 能级一体化工作台...", self)
        g_quick_act.triggered.connect(self._open_qc_log)
        calc_menu.addAction(g_quick_act)

        rest_setup_act = QAction("复旦 REST 输入配置...", self)
        rest_setup_act.triggered.connect(lambda: self._open_qc_log(initial_tab=1))
        calc_menu.addAction(rest_setup_act)

        calchem_opt_act = QAction("CalChem 极速几何优化 (RHF/BFGS)...", self)
        calchem_opt_act.setShortcut("Ctrl+Shift+C")
        calchem_opt_act.triggered.connect(self._on_run_calchem_optimization)
        calc_menu.addAction(calchem_opt_act)

        calchem_mo_act = QAction("CalChem 分子轨道能级图...", self)
        calchem_mo_act.triggered.connect(self._open_calchem_orbitals_dialog)
        calc_menu.addAction(calchem_mo_act)

        ir_vib_act = QAction("红外吸收光谱与振动动画...", self)
        ir_vib_act.setShortcut("Ctrl+Shift+V")
        ir_vib_act.triggered.connect(self._open_vibrational_spectrum_dialog)
        calc_menu.addAction(ir_vib_act)

        hpc_job_act = QAction("超算集群作业提交 (HPC)...", self)
        hpc_job_act.setShortcut("Ctrl+H")
        hpc_job_act.triggered.connect(self._open_hpc_job_dialog)
        calc_menu.addAction(hpc_job_act)

        multiwfn_act = QAction("Multiwfn 波函数分析...", self)
        multiwfn_act.setShortcut("Ctrl+Shift+M")
        multiwfn_act.triggered.connect(self._open_multiwfn_dialog)
        calc_menu.addAction(multiwfn_act)

        xtb_opt_act = QAction("xtb 半经验快速优化 (GFN2-xTB)...", self)
        xtb_opt_act.setShortcut("Ctrl+Shift+X")
        xtb_opt_act.triggered.connect(self._on_run_xtb_optimization)
        calc_menu.addAction(xtb_opt_act)

        quick_ff_act = QAction("快速力场几何优化 (MMFF94/UFF)", self)
        quick_ff_act.triggered.connect(self.workspace.view3d_real.clean_3d_geometry)
        calc_menu.addAction(quick_ff_act)

        gmmx_act = QAction("多构象系综搜索...", self)
        gmmx_act.triggered.connect(self._generate_conformers)
        calc_menu.addAction(gmmx_act)

        job_mgr_act = QAction("计算任务管理器...", self)
        job_mgr_act.setShortcut("Ctrl+J")
        job_mgr_act.triggered.connect(lambda: self.right.switch_tab(2))
        calc_menu.addAction(job_mgr_act)

        calc_menu.addSeparator()
        eng_status_act = QAction("引擎与外部工具配置...", self)
        eng_status_act.triggered.connect(self._open_tool_path_config_dialog)
        calc_menu.addAction(eng_status_act)

        # -------------------- 8. Results (结果 · v7.0 九大分类 79 项分析矩阵) --------------------
        res_menu = menubar.addMenu("结果(&R)")
        try:
            from .qc_result_dialog import populate_v7_results_menu
            populate_v7_results_menu(res_menu, self, lambda: self.document)
        except Exception:
            pass

        sum_act = QAction("计算结果总览 (Summary)...", self)
        sum_act.triggered.connect(lambda: self._open_qc_log(initial_tab=2))
        res_menu.addAction(sum_act)

        chg_act = QAction("电荷分布分析 (Charge Distribution)...", self)
        chg_act.triggered.connect(self.toggle_property_table_dock)
        res_menu.addAction(chg_act)

        aprop_act = QAction("原子属性总表 (Atom Properties)...", self)
        aprop_act.triggered.connect(self.toggle_property_table_dock)
        res_menu.addAction(aprop_act)

        bprop_act = QAction("化学键属性总表 (Bond Properties)...", self)
        bprop_act.triggered.connect(self.toggle_property_table_dock)
        res_menu.addAction(bprop_act)

        surf_cnt_act = QAction("分子轨道与等值面 (Surfaces and Contours)...", self)
        surf_cnt_act.triggered.connect(self._on_load_orbital)
        res_menu.addAction(surf_cnt_act)

        vib_act = QAction("振动频率与红外光谱 (Vibrations / IR)...", self)
        vib_act.triggered.connect(lambda: self._show_spectrum_summary("IR 红外振动频率"))
        res_menu.addAction(vib_act)

        nmr_act = QAction("核磁共振化学位移预测 (NMR)...", self)
        nmr_act.triggered.connect(lambda: self._show_spectrum_summary("NMR 化学位移"))
        res_menu.addAction(nmr_act)

        uv_act = QAction("TD-DFT 激发态与紫外-可见光谱 (UV-Vis)...", self)
        uv_act.triggered.connect(lambda: self._open_qc_log(initial_tab=2))
        res_menu.addAction(uv_act)

        mgrp_tbl_act = QAction("多分子对比总表 (Molecule Group Table)...", self)
        mgrp_tbl_act.triggered.connect(self.toggle_model_explorer_dock)
        res_menu.addAction(mgrp_tbl_act)

        scan_act = QAction("二面角扫描与反应路径 (Scan / IRC-Path)...", self)
        scan_act.triggered.connect(lambda: DihedralChartDialog(self).exec())
        res_menu.addAction(scan_act)

        traj_act = QAction("动力学轨迹与优化步动画 (Trajectory / Optimization)...", self)
        traj_act.triggered.connect(self._on_open_trajectory)
        res_menu.addAction(traj_act)

        eplot_act = QAction("OSC HOMO-LUMO 能级阶梯图 (Energy Plot)...", self)
        eplot_act.triggered.connect(lambda: self._open_qc_log(initial_tab=2))
        res_menu.addAction(eplot_act)

        # -------------------- 9. Surfaces (表面) --------------------
        surf_menu = menubar.addMenu("表面(&U)")

        from ..rendering.contracts import RepresentationMode
        surf_show_act = QAction("显示范德华分子表面 (Display Mode: Surface)", self)
        surf_show_act.triggered.connect(lambda: self.workspace._on_mode_changed(RepresentationMode.SURFACE))
        surf_menu.addAction(surf_show_act)

        homo_gen_act = QAction("🔮 Hückel近似 HOMO 轨道示意（非量化结果）", self)
        homo_gen_act.triggered.connect(lambda: self._on_generate_frontier_orbital("HOMO"))
        surf_menu.addAction(homo_gen_act)

        lumo_gen_act = QAction("🔮 Hückel近似 LUMO 轨道示意（非量化结果）", self)
        lumo_gen_act.triggered.connect(lambda: self._on_generate_frontier_orbital("LUMO"))
        surf_menu.addAction(lumo_gen_act)

        surf_menu.addSeparator()

        orb_load_act = QAction("加载外部 Gaussian/ORCA/xtb 轨道 Cube 网格 (.cube)...", self)
        orb_load_act.triggered.connect(self._on_load_orbital)
        surf_menu.addAction(orb_load_act)

        orb_clr_act = QAction("清除轨道与表面等值面 (Clear Surfaces)", self)
        orb_clr_act.triggered.connect(self._on_clear_orbital)
        surf_menu.addAction(orb_clr_act)

        # -------------------- 10. Help (帮助) --------------------
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于 MolForge…", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
        help_menu.addAction("帮助文档（使用手册）", self._open_help_docs)

    # ---------- 独立可停靠/浮动面板管理 (P4) ----------

    def toggle_model_explorer_dock(self):
        if self._explorer_dock is None:
            self._explorer_dock = ModelExplorerDock(self)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._explorer_dock)
        else:
            self._explorer_dock.setVisible(not self._explorer_dock.isVisible())
        if self._explorer_dock.isVisible():
            self._explorer_dock.refresh_from_document()

    def toggle_cartesian_table_dock(self):
        if self._cartesian_dock is None:
            self._cartesian_dock = CartesianTableDock(self)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._cartesian_dock)
        else:
            self._cartesian_dock.setVisible(not self._cartesian_dock.isVisible())
        if self._cartesian_dock.isVisible():
            self._cartesian_dock.refresh_from_document()

    def toggle_measurement_table_dock(self):
        if self._measurement_dock is None:
            self._measurement_dock = MeasurementTableDock(self)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._measurement_dock)
        else:
            self._measurement_dock.setVisible(not self._measurement_dock.isVisible())
        if self._measurement_dock.isVisible():
            self._measurement_dock.refresh_from_document()

    def toggle_property_table_dock(self):
        if self._property_dock is None:
            self._property_dock = AtomBondPropertyDock(self)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._property_dock)
        else:
            self._property_dock.setVisible(not self._property_dock.isVisible())
        if self._property_dock.isVisible():
            self._property_dock.refresh_from_document()

    def _refresh_all_open_docks(self):
        for dock in (self._explorer_dock, self._cartesian_dock, self._measurement_dock, self._property_dock):
            if dock is not None and dock.isVisible():
                dock.refresh_from_document()

    # ---------- 多窗口并排与独立 2D / 3D 画布创建 (P2 & P4) ----------

    def _spawn_new_window(self, initial_mode: int = 2, blank: bool = False, doc: MoleculeDocument | None = None):
        if doc is None:
            if blank:
                mode_tag = "2D" if initial_mode == 0 else ("3D" if initial_mode == 1 else "Blank")
                doc = MoleculeDocument(name=f"未命名_{mode_tag}")
            else:
                doc = create_instant_caffeine_document()
        win = MolForgeWindow(initial_document=doc, initial_view_mode=initial_mode)
        win.move(self.x() + 36, self.y() + 36)
        win.show()
        return win

    def _on_add_to_group(self):
        base_g = self.group_tag.split(":")[0]
        m_count = sum(1 for w in MolForgeWindow._open_windows if w.group_tag.startswith(base_g + ":")) + 1
        tag = f"{base_g}:M{m_count}:V1"
        doc = MoleculeDocument(name=f"分子_{tag}")
        win = MolForgeWindow(initial_document=doc, initial_view_mode=2, group_tag=tag)
        win.move(self.x() + 42, self.y() + 42)
        win.show()

    def _on_add_clone_view(self):
        parts = self.group_tag.split(":")
        base_gm = ":".join(parts[:2])
        v_count = sum(1 for w in MolForgeWindow._open_windows if w.group_tag.startswith(base_gm + ":")) + 1
        tag = f"{base_gm}:V{v_count}"
        win = MolForgeWindow(initial_document=self.document, initial_view_mode=1, group_tag=tag)
        win.move(self.x() + 48, self.y() + 48)
        win.show()

    # ---------- View 菜单勾选开关实时联动 ----------

    def _on_toggle_view_options(self):
        show_h = self.act_show_h.isChecked()
        show_b = self.act_show_bonds.isChecked()
        show_lbl = self.act_show_labels.isChecked()
        show_sym = self.act_show_symbols.isChecked()
        show_ax = self.act_show_axes.isChecked()
        self.workspace.view3d_real.set_view_options(
            show_hydrogens=show_h,
            show_bonds=show_b,
            show_labels=show_lbl,
            show_symbols=show_sym,
            show_axes=show_ax,
        )
        self.workspace.view2d.set_show_atom_numbers(show_lbl)
        self.workspace.view2d._hide_explicit_hydrogens = not show_h
        self.workspace.view2d.update()

    # ---------- Edit & Structure 菜单高级几何操作（全部支持 Undo/Redo！） ----------

    def _on_cut_molecule(self):
        self._on_copy_molecule()
        self._on_new_blank()

    def _on_copy_molecule(self):
        """P1-2 智能复制：若有选中原子，则仅复制选中原子的 XYZ 坐标；若未选中，则复制整个分子。"""
        sel_atoms = list(self.selection.selected_atoms) if self.selection else []
        if sel_atoms and self.document.has_3d and self.document.coordinates.current is not None:
            lines = []
            for aid in sel_atoms:
                if aid in self.document.topology._atoms:
                    pos = self.document.get_atom_3d_pos(aid)
                    atom = self.document.topology.get_atom(aid)
                    el = get_element(atom.atomic_num)
                    sym = el.symbol if el else "C"
                    if pos is not None:
                        lines.append(f"{sym:2s}  {pos[0]:12.6f}  {pos[1]:12.6f}  {pos[2]:12.6f}")
            txt = f"{len(lines)}\n{self.document.name}_selected_{len(lines)}atoms\n" + "\n".join(lines)
            QGuiApplication.clipboard().setText(txt)
            self.status_left.setText(f"[{self.group_tag}] 已复制选中的 {len(lines)} 个原子 XYZ 坐标到剪贴板")
            return

        from ..application.calculators.qc_input_generator import extract_xyz_lines
        xyz_lines = extract_xyz_lines(self.document)
        txt = f"{len(xyz_lines)}\n{self.document.name}\n" + "\n".join(xyz_lines)
        QGuiApplication.clipboard().setText(txt)
        self.status_left.setText(f"[{self.group_tag}] 已复制整个分子 ({len(xyz_lines)} 个原子) 的 XYZ 坐标到剪贴板")

    def _on_paste_molecule(self):
        """P1-1 智能追加粘贴：自动识别 XYZ 坐标 / MOL 块 / SMILES / 预设分子名，并追加到当前画布（支持 Ctrl+Z 撤销）！"""
        txt = QGuiApplication.clipboard().text().strip()
        if not txt:
            self.status_left.setText(f"[{self.group_tag}] 剪贴板为空，无法粘贴")
            return

        lines = [l for l in txt.splitlines() if l.strip()]
        new_doc: MoleculeDocument | None = None

        # 1. 判断是否为标准 XYZ 格式（第一行整数，或每行 `Sym X Y Z`）
        is_xyz = False
        if len(lines) >= 2:
            try:
                n = int(lines[0].strip().split()[0])
                if 1 <= n <= 100000 and len(lines) >= n + 1:
                    is_xyz = True
            except ValueError:
                parts0 = lines[0].split()
                if len(parts0) == 4:
                    try:
                        float(parts0[1]); float(parts0[2]); float(parts0[3])
                        txt = f"{len(lines)}\nPasted_XYZ\n" + "\n".join(lines)
                        is_xyz = True
                    except ValueError:
                        pass

        if is_xyz:
            import tempfile
            tmp = Path(tempfile.mkdtemp()) / "pasted.xyz"
            tmp.write_text(txt, encoding="utf-8")
            try:
                new_doc, _ = load_molecule_document(tmp)
            except Exception as e:
                self.status_left.setText(f"[{self.group_tag}] XYZ 粘贴解析失败: {e}")
                return
        elif "V2000" in txt or "M  END" in txt:
            import tempfile
            tmp = Path(tempfile.mkdtemp()) / "pasted.mol"
            tmp.write_text(txt, encoding="utf-8")
            try:
                new_doc, _ = load_molecule_document(tmp)
            except Exception as e:
                self.status_left.setText(f"[{self.group_tag}] MOL 粘贴解析失败: {e}")
                return
        else:
            first_line = lines[0].strip().split()[0]
            from ..io.rdkit_adapter import SAMPLE_MOLECULES
            if first_line in SAMPLE_MOLECULES:
                new_doc = create_sample_molecule(first_line)
            else:
                try:
                    new_doc = create_molecule_from_smiles(first_line, name=f"Pasted_{first_line[:10]}")
                except Exception as e:
                    self.status_left.setText(f"[{self.group_tag}] 无法将剪贴板内容识别为 SMILES 或 XYZ: {e}")
                    return

        if new_doc is not None and new_doc.num_atoms > 0:
            self._merge_document_into_current(new_doc)

    def _merge_document_into_current(self, new_doc: MoleculeDocument):
        """使用 AppendMoleculeCommand 将粘贴分子追加合并到当前文档（自动偏移防重叠，支持 Ctrl+Z 撤销并自动居中）。"""
        from ..application.builtin_commands import AppendMoleculeCommand
        res = self.command_bus.execute(AppendMoleculeCommand(new_doc))
        if res.success:
            added_aids = res.data.get("added_atom_ids", []) if res.data else []
            if self.selection is not None and added_aids:
                self.selection.clear(origin="paste")
                for aid in added_aids:
                    self.selection.select_atom(aid, add=True, origin="paste")
                self.workspace.view3d_real._capture_multi_drag_origins()
            self.workspace.view3d_real.reset_camera()
            self.status_left.setText(
                f"[{self.group_tag}] {res.message}（已自动选中新粘贴部分，可直接拖动平移或按 Ctrl+Z 撤销）"
            )
        else:
            self.status_left.setText(f"[{self.group_tag}] 粘贴合并失败: {res.message}")

    def _on_select_all(self):
        for aid in self.document.topology.atom_ids:
            self.selection.select_atom(aid, add=True, origin="menu")
        for bid in self.document.topology.bond_ids:
            self.selection.select_bond(bid, add=True, origin="menu")

    def _on_capture_clipboard(self):
        pix = self.workspace.grab()
        QGuiApplication.clipboard().setPixmap(pix)
        self.status_left.setText(f"[{self.group_tag}] 已将当前 2D/3D 视图截图复制到剪贴板")

    def _on_center_origin(self):
        if hasattr(self, "workspace") and hasattr(self.workspace, "view2d"):
            self.workspace.view2d.fit_view()
        if not self.document.has_3d or self.document.coordinates.current is None or self.document.num_atoms == 0:
            return
        coords = self.document.coordinates.current.coords
        centered = coords - coords.mean(axis=0)
        from ..application.builtin_commands import TransformCoordinates3DCommand
        self.command_bus.execute(TransformCoordinates3DCommand(centered, description="坐标原点中心化"))
        self.workspace.view3d_real.reset_camera()

    def _on_paste_custom_fragment(self, smiles: str, name: str):
        from ..io.rdkit_adapter import create_molecule_from_smiles
        try:
            new_doc = create_molecule_from_smiles(smiles, name=name)
            self._merge_document_into_current(new_doc)
            self.status_left.setText(f"[{self.group_tag}] 已插入自定义砌块「{name}」（可按 Ctrl+Z 撤销）")
        except Exception as e:
            self.status_left.setText(f"[{self.group_tag}] 插入砌块失败: {e}")

    def _on_reorient_principal_axes(self):
        if not self.document.has_3d or self.document.coordinates.current is None or self.document.num_atoms < 2:
            return
        coords = self.document.coordinates.current.coords.astype(np.float64)
        centered = coords - coords.mean(axis=0)
        try:
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            if np.linalg.det(vh) < 0:
                vh[-1] = -vh[-1]
            aligned = (centered @ vh.T).astype(np.float32)
            from ..application.builtin_commands import TransformCoordinates3DCommand
            self.command_bus.execute(TransformCoordinates3DCommand(aligned, description="主惯性轴对齐 (Reorient)"))
            self.workspace.view3d_real.reset_camera()
        except Exception:
            pass

    def _on_mirror_invert(self):
        if not self.document.has_3d or self.document.coordinates.current is None or self.document.num_atoms == 0:
            return
        coords = self.document.coordinates.current.coords.copy()
        coords[:, 0] = -coords[:, 0]
        from ..application.builtin_commands import TransformCoordinates3DCommand
        self.command_bus.execute(TransformCoordinates3DCommand(coords, description="镜像手性反转 (Mirror Invert)"))

    def _on_rebond_3d(self):
        if not self.document.has_3d or self.document.coordinates.current is None or self.document.num_atoms < 2:
            return
        atom_ids, _ = self.document.topology.atom_index_map()
        z_list = [self.document.topology.get_atom(aid).atomic_num for aid in atom_ids]
        coords = self.document.coordinates.current.coords
        bonds_list, _ = perceive_bonds_and_orders_3d(z_list, coords)
        for bid in list(self.document.topology.bond_ids):
            self.document.topology.remove_bond(bid)
        for i, j, order, is_ar in bonds_list:
            self.document.topology.add_bond(atom_ids[i], atom_ids[j], order=order, aromatic=is_ar)
        self._on_document_changed(self.document)
        self.status_left.setText(f"[{self.group_tag}] 已按 3D 共价半径重新感知生成 {len(bonds_list)} 条化学键")

    def _on_remove_weak_bonds(self):
        if not self.document.has_3d or self.document.coordinates.current is None:
            return
        _, id2idx = self.document.topology.atom_index_map()
        coords = self.document.coordinates.current.coords
        from ..application.builtin_commands import DeleteBondCommand
        removed = 0
        for bid in list(self.document.topology.bond_ids):
            b = self.document.topology.get_bond(bid)
            if b.begin in id2idx and b.end in id2idx:
                d = float(np.linalg.norm(coords[id2idx[b.begin]] - coords[id2idx[b.end]]))
                if d > 2.15:
                    self.command_bus.execute(DeleteBondCommand(bid))
                    removed += 1
        self.status_left.setText(f"[{self.group_tag}] 已移除 {removed} 条超长弱键 (>2.15 Å)")

    def _on_add_missing_hydrogens(self):
        from ..application.builtin_commands import AddAtomCommand
        std_val = {6: 4, 7: 3, 8: 2, 16: 2, 14: 4, 15: 3}
        added = 0
        for aid in list(self.document.topology.atom_ids):
            atom = self.document.topology.get_atom(aid)
            target_v = std_val.get(atom.atomic_num, 0)
            if target_v <= 0:
                continue
            cur_v = sum(
                self.document.topology.get_bond(bid).order
                for bid in self.document.topology._adjacency.get(aid, [])
                if bid in self.document.topology._bonds
            )
            missing = max(0, target_v - cur_v)
            for _ in range(missing):
                self.command_bus.execute(AddAtomCommand(1, bond_to=aid, bond_order=1))
                added += 1
        if added > 0:
            self.document.relax_3d_geometry(max_iters=50)
            self._on_document_changed(self.document)
        self.status_left.setText(f"[{self.group_tag}] 已自动补齐 {added} 个显式氢原子")

    def _open_modify_internal_dialog(self):
        from ..application.measurement_targets import MeasurementTargetResolver
        target = MeasurementTargetResolver.resolve(self.document, self.selection)
        if target.kind == "dihedral":
            mode = "dihedral"
        elif target.kind in ("angle", "ambiguous"):
            mode = "angle"
        else:
            mode = "bond"
        ModifyInternalCoordDialog(self, mode=mode).exec()

    def _set_selected_bond_angle(self, target_deg: float):
        from ..application.measurement_targets import MeasurementTargetResolver
        from ..application.internal_coordinates import ModifyAngle3DCommand
        target = MeasurementTargetResolver.resolve(self.document, self.selection)
        if target.kind not in ("angle", "ambiguous") or len(target.atoms) != 3:
            self.status_left.setText("请先选中 3 个相连原子或 2 条相邻化学键以修改键角")
            return
        cmd = ModifyAngle3DCommand(target.atoms[0], target.atoms[1], target.atoms[2], float(target_deg))
        res = self.session.execute(cmd, origin=self.group_tag)
        self.status_left.setText(res.message)

    def _set_selected_dihedral_angle(self, target_deg: float):
        from ..application.measurement_targets import MeasurementTargetResolver
        from ..application.internal_coordinates import ModifyDihedral3DCommand
        target = MeasurementTargetResolver.resolve(self.document, self.selection)
        dih_atoms = target.atoms if (target.kind == "dihedral" and len(target.atoms) == 4) else target.canonical_dihedral_atoms
        if dih_atoms is None and target.center_bond is not None:
            dih_atoms = MeasurementTargetResolver.find_canonical_dihedral_for_bond(self.document, target.center_bond)
        if dih_atoms is None or len(dih_atoms) != 4:
            self.status_left.setText("请先选中 4 个相连原子或 1 条可旋转化学键以修改二面角")
            return
        cmd = ModifyDihedral3DCommand(
            dih_atoms[0], dih_atoms[1], dih_atoms[2], dih_atoms[3], float(target_deg)
        )
        res = self.session.execute(cmd, origin=self.group_tag)
        self.status_left.setText(res.message)

    def _on_select_by_element_dialog(self):
        sym, ok = QInputDialog.getText(self, "按元素批量选择原子", "输入元素符号 (如 C, N, O, S, F, H):")
        if not ok or not sym.strip():
            return
        from ..domain.elements import get_element_by_symbol
        el = get_element_by_symbol(sym.strip().capitalize())
        if el is None:
            return
        self.selection.clear(origin="select_elem")
        for aid in self.document.topology.atom_ids:
            if self.document.topology.get_atom(aid).atomic_num == el.atomic_number:
                self.selection.select_atom(aid, add=True, origin="select_elem")

    def _on_show_point_group(self):
        QMessageBox.information(
            self, "分子点群对称性分析 (Point Group)",
            f"分子：{self.document.name}\n原子数：{self.document.num_atoms}\n估计点群对称性：C₁ / Cₛ (近平面共轭体系)"
        )

    def _on_show_pbc_info(self):
        QMessageBox.information(
            self, "周期性边界条件 (PBC)",
            "当前文档处于气相/孤立分子模式 (Non-Periodic)。\n如需导入晶体晶胞，请通过 [文件 -> 打开] 导入 .cif 或 .pdb 晶体结构文件。"
        )

    def _show_spectrum_summary(self, title: str):
        QMessageBox.information(
            self, title,
            f"<h3>{title} · {self.document.name}</h3>"
            "<p>当前分子已完成拓扑与三维构象准备。可通过 <b>[计算 -> Gaussian / 复旦 REST]</b> 运行 `opt freq` 或 `nmr` 任务后加载 `.log` 查看完整谱图。</p>"
        )

    def _rebuild_recent_files_menu(self):
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        recents = self.settings.value("recent_files", []) or []
        if isinstance(recents, str):
            recents = [recents]
        for p_str in recents[:10]:
            act = QAction(str(p_str), self)
            act.triggered.connect(lambda checked=False, path=p_str: self.open_molecule_file(path))
            self.recent_menu.addAction(act)
        if not recents:
            empty_act = QAction("(暂无最近打开记录)", self)
            empty_act.setEnabled(False)
            self.recent_menu.addAction(empty_act)

    def _on_show_related_files(self):
        src = getattr(self.document, "source_path", None)
        QMessageBox.information(self, "关联文件 (Related Files)", f"当前分子来源路径：\n{src or '(内存新建/内置示例分子)'}")

    def _on_save_temp_file(self):
        import tempfile
        tmp_p = Path(tempfile.gettempdir()) / f"{self.document.name}_temp.mol"
        tmp_p.write_text(export_document_to_mol_v2000(self.document), encoding="utf-8")
        self.status_left.setText(f"[{self.group_tag}] 已保存临时快照：{tmp_p}")

    def _on_convert_files_dialog(self):
        self._on_export()

    def _on_save_image_only(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存高清渲染图", f"{self.document.name}.png", "PNG 高清截图 (*.png);;SVG 2D 矢量图 (*.svg)"
        )
        if not path:
            return
        if path.lower().endswith(".svg"):
            self._export_2d_svg(path)
        else:
            self.workspace.grab().save(path, "PNG")
        self.status_left.setText(f"[{self.group_tag}] 已导出图像：{Path(path).name}")

    # ---------- 顶栏搜索框 / SMILES / 命令 ----------

    def _on_top_search_command(self, text: str):
        if not text:
            return
        from ..io.rdkit_adapter import SAMPLE_MOLECULES
        if text in SAMPLE_MOLECULES:
            self._on_molecule_selected(text)
            return
        if any(c in text for c in ("=", "#", "1", "2", "(", ")", "c", "C", "N", "O", "S")) and " " not in text:
            try:
                doc = create_molecule_from_smiles(text, name=f"SMILES_{text[:12]}")
                self._replace_active_document(doc)
                self.status_left.setText(f"[{self.group_tag}] 已从 SMILES 加载分子：{text}")
                return
            except Exception:
                pass
        self.right.switch_tab(1)
        self.right.ai_prompt_input.setText(text)
        self.right._on_ask_question()

    # ---------- 智能 C-H 取代位点识别 ----------

    def _find_substitution_site(self) -> tuple[AtomId | None, AtomId | None]:
        topo = self.document.topology
        if topo.num_atoms == 0:
            return None, None

        if self.selection and self.selection.selected_atoms:
            sel_aid = next(iter(self.selection.selected_atoms))
            if sel_aid in topo._atoms:
                atom = topo.get_atom(sel_aid)
                if atom.atomic_num == 1:
                    nbrs = topo.neighbors_of(sel_aid)
                    return (nbrs[0] if nbrs else None), sel_aid
                h_nbrs = [n for n in topo.neighbors_of(sel_aid) if topo.get_atom(n).atomic_num == 1]
                return sel_aid, (h_nbrs[0] if h_nbrs else None)

        candidates = []
        for aid in topo.atom_ids:
            a = topo.get_atom(aid)
            if a.atomic_num == 6:
                h_nbrs = [n for n in topo.neighbors_of(aid) if topo.get_atom(n).atomic_num == 1]
                if h_nbrs:
                    p3 = self.document.get_atom_3d_pos(aid)
                    x_score = float(p3[0]) if p3 is not None else 0.0
                    candidates.append((x_score, aid, h_nbrs[0]))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1], candidates[0][2]

        heavy = [aid for aid in topo.atom_ids if topo.get_atom(aid).atomic_num != 1]
        return (heavy[-1] if heavy else next(iter(topo.atom_ids))), None

    def _on_fg_insert(self, fg_code: str):
        from ..application.builtin_commands import AddAtomCommand, DeleteAtomCommand
        has_sel = bool(self.selection and self.selection.selected_atoms)
        if not has_sel and self.document.num_atoms > 0:
            self.status_left.setText(f"[{self.group_tag}] 提示：请先在 2D 或 3D 画布中点击选中目标原子（如某个 C 或 H），再点击官能团即可精准接枝！")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "接枝提示",
                f"您尚未选中任何原子。\n\n请在 2D 画布或 3D 视口中先点击选中一个原子（如某个碳原子或氢原子），再点击官能团「{fg_code}」，系统将自动精准接枝取代！"
            )
            return

        anchor, h_aid = self._find_substitution_site()
        if h_aid is not None and h_aid in self.document.topology._atoms:
            self.command_bus.execute(DeleteAtomCommand(h_aid))

        code = fg_code.upper()
        if code == "-F":
            self.command_bus.execute(AddAtomCommand(9, bond_to=anchor, bond_order=1))
        elif code == "-CL":
            self.command_bus.execute(AddAtomCommand(17, bond_to=anchor, bond_order=1))
        elif code == "-BR":
            self.command_bus.execute(AddAtomCommand(35, bond_to=anchor, bond_order=1))
        elif code == "-I":
            self.command_bus.execute(AddAtomCommand(53, bond_to=anchor, bond_order=1))
        elif code == "-OH":
            self.command_bus.execute(AddAtomCommand(8, bond_to=anchor, bond_order=1))
        elif code == "-NH2":
            self.command_bus.execute(AddAtomCommand(7, bond_to=anchor, bond_order=1))
        elif code == "-CH3":
            self.command_bus.execute(AddAtomCommand(6, bond_to=anchor, bond_order=1))
        elif code == "-CN":
            r1 = self.command_bus.execute(AddAtomCommand(6, bond_to=anchor, bond_order=1))
            if r1.success:
                c_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(7, bond_to=c_aid, bond_order=3))
        elif code == "-OCH3":
            r1 = self.command_bus.execute(AddAtomCommand(8, bond_to=anchor, bond_order=1))
            if r1.success:
                o_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(6, bond_to=o_aid, bond_order=1))
        elif code == "-COOH":
            r1 = self.command_bus.execute(AddAtomCommand(6, bond_to=anchor, bond_order=1))
            if r1.success:
                c_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(8, bond_to=c_aid, bond_order=2))
                self.command_bus.execute(AddAtomCommand(8, bond_to=c_aid, bond_order=1))
        elif code == "-CHO":
            r1 = self.command_bus.execute(AddAtomCommand(6, bond_to=anchor, bond_order=1))
            if r1.success:
                c_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(8, bond_to=c_aid, bond_order=2))
        elif code == "-NO2":
            r1 = self.command_bus.execute(AddAtomCommand(7, bond_to=anchor, bond_order=1))
            if r1.success:
                n_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(8, bond_to=n_aid, bond_order=2))
                self.command_bus.execute(AddAtomCommand(8, bond_to=n_aid, bond_order=1))
        elif code == "-CF3":
            r1 = self.command_bus.execute(AddAtomCommand(6, bond_to=anchor, bond_order=1))
            if r1.success:
                c_aid = AtomId(r1.data["atom_id"])
                self.command_bus.execute(AddAtomCommand(9, bond_to=c_aid, bond_order=1))
                self.command_bus.execute(AddAtomCommand(9, bond_to=c_aid, bond_order=1))
                self.command_bus.execute(AddAtomCommand(9, bond_to=c_aid, bond_order=1))

        self.workspace.view2d.recompute_2d_layout()
        self.document.relax_3d_geometry(max_iters=60)
        self.workspace.view3d_real.set_document(self.document)
        self.status_left.setText(f"[{self.group_tag}] 已在位点 #{anchor.value + 1 if anchor else 1} 接枝官能团 {fg_code} 并同步 2D/3D")

    def _on_ring_insert(self, size: int, aromatic: bool, hetero: dict | None = None):
        from ..application.builtin_commands import AddRingCommand, DeleteAtomCommand
        has_sel = bool(self.selection and self.selection.selected_atoms)
        if has_sel:
            anchor, h_aid = self._find_substitution_site()
            if h_aid is not None and h_aid in self.document.topology._atoms:
                self.command_bus.execute(DeleteAtomCommand(h_aid))
            self.command_bus.execute(
                AddRingCommand(size=size, aromatic=aromatic, hetero_atoms=hetero, attach_to=anchor)
            )
            msg = f"已在选中原子 #{anchor.value + 1 if anchor else 1} 处接枝 {size} 元环"
        else:
            # 未选中任何原子时，在画布中心作为独立环系放置，不破坏已有分子
            self.command_bus.execute(
                AddRingCommand(size=size, aromatic=aromatic, hetero_atoms=hetero, center_2d=(0.0, 0.0), center_3d=(0.0, 0.0, 0.0), attach_to=None)
            )
            msg = f"已在画布中心放置独立 {size} 元环"

        self.workspace.view2d.recompute_2d_layout()
        self.document.relax_3d_geometry(max_iters=60)
        self.workspace.view3d_real.set_document(self.document)
        self.status_left.setText(f"[{self.group_tag}] {msg}，已同步 2D/3D（可按 Ctrl+Z 撤销）")

    def _execute_ai_action(self, action_dict: dict) -> str | None:
        act = action_dict.get("action", "")
        if act == "add_ring":
            size = int(action_dict.get("size", 6))
            arom = bool(action_dict.get("aromatic", True))
            raw_h = action_dict.get("hetero", {}) or {}
            hetero = {int(k): int(v) for k, v in raw_h.items()}
            self._on_ring_insert(size, arom, hetero)
            return f"连接 {size} 元环"
        if act == "add_group":
            grp = str(action_dict.get("group", "-CN"))
            self._on_fg_insert(grp)
            return f"接枝官能团 {grp}"
        if act == "clean_3d":
            self.workspace.view3d_real.clean_3d_geometry()
            return "3D 力场优化"
        if act == "open_qc_dialog":
            self._open_qc_log()
            return "打开量化计算工作台"
        return None

    # ---------- 常规窗口与逐原子/逐键属性操作 (全部支持 Undo/Redo！) ----------

    def _add_atom_at_3d(self, world_pos):
        from ..application.builtin_commands import AddAtomCommand
        elem = getattr(self.workspace, "_current_element", 6)
        r = self.command_bus.execute(
            AddAtomCommand(
                elem, x=float(world_pos[0]), y=float(world_pos[1]), z=float(world_pos[2]),
                auto_bond_nearest=True
            )
        )
        if r.success:
            self.status_left.setText(f"[{self.group_tag}] 3D 加原子并成键 @ ({world_pos[0]:.2f}, {world_pos[1]:.2f}, {world_pos[2]:.2f}) Å")

    def _on_2d_bg_changed(self, color):
        palette = self.workspace.view2d.palette()
        palette.setColor(self.workspace.view2d.backgroundRole(), color)
        self.workspace.view2d.setPalette(palette)

    def _on_material_preset_changed(self, name):
        self.workspace.view3d_real.set_material_preset(name)

    def _on_theme_changed(self, theme_name: str):
        self._current_theme = theme_name
        self._apply_theme()

    def _on_accent_changed(self, hexc: str):
        self._current_accent = hexc
        self._apply_theme()

    def _apply_theme(self):
        from .theme import apply_theme
        theme = getattr(self, "_current_theme", "Dark Professional")
        accent = getattr(self, "_current_accent", None)
        apply_theme(self, theme, accent)
        self._wire_right_panel_callbacks()

    def _open_qc_log(self, initial_tab: int = 0):
        from .qc_result_dialog import QcResultDialog
        dlg = QcResultDialog(self, result=None, on_show_step=self._show_qc_step, document=self.document, initial_tab=int(initial_tab))
        dlg.exec()

    def _show_qc_step(self, step):
        coords = step.get("coords")
        if coords is None:
            return
        if coords.shape[0] == self.document.topology.num_atoms:
            self.workspace.view3d_real.set_conformer_coords(coords)

    def _generate_conformers(self):
        from copy import deepcopy
        from ..application.conformers import generate_conformers
        from .conformer_dialog import ConformerDialog
        from .modeling_actions import _background
        document=self.document
        if any(a.properties.get('frozen') for a in document.topology._atoms.values()):
            QMessageBox.information(self,'生成构象','全局ETKDG尚不支持冻结约束；请用局部单键旋转或固定点力场优化。')
            return
        revision=document.revision;snapshot=deepcopy(document)
        self.statusBar().showMessage('正在后台生成ETKDGv3构象与力场能量…')
        def work():
            molecule=doc_to_rdkit(snapshot,sanitize=True,strict=True)[0]
            return generate_conformers(molecule,num_confs=20,seed=42)[0]
        def done(ensemble):
            if self.document is not document or document.revision!=revision:
                self.statusBar().showMessage('分子已改变，未应用过期构象');return
            if not ensemble.count:
                QMessageBox.warning(self,'生成构象','；'.join(ensemble.failures));return
            view=self.workspace.view3d_real
            def preview(coords):
                if self.document is document and document.revision==revision:
                    view.renderer.update_coordinates(coords);view.renderer.render()
            def apply(coords):
                if self.document is not document or document.revision!=revision:
                    QMessageBox.warning(self,'分子已改变','未应用过期构象');return False
                return self._apply_conformer(coords)
            dialog=ConformerDialog(self,ensemble,on_apply=apply,on_preview=preview)
            dialog.exec()
            if self.document is document:
                view.renderer.update_coordinates(document.coordinates.current.coords)
                view.renderer.render()
            self.statusBar().showMessage(f'ETKDG完成：{ensemble.count}个构象；模型能量不代表全局最低能')
        _background(self,work,done)

    def _apply_conformer(self, coords):
        from ..application.builtin_commands import TransformCoordinates3DCommand
        result=self.command_bus.execute(TransformCoordinates3DCommand(coords,'应用ETKDG构象'))
        if not result.success:QMessageBox.warning(self,'构象未应用',result.message)
        return result.success

    def _set_selected_bond_order(self, order):
        bonds = self.selection.selected_bonds
        if len(bonds) != 1:
            return
        from ..application.builtin_commands import ChangeBondOrderCommand
        bid = next(iter(bonds))
        self.command_bus.execute(ChangeBondOrderCommand(bid, order))
        self._on_selection_changed()

    def _set_selected_bond_length(self, target_len: float):
        from ..application.measurement_targets import MeasurementTargetResolver
        from ..application.builtin_commands import ModifyBondLength3DCommand
        target = MeasurementTargetResolver.resolve(self.document, self.selection)
        bid = None
        if target.kind == "distance" and len(target.atoms) == 2:
            bid = target.center_bond
            if bid is None and hasattr(self.document.topology, "bond_between"):
                bid = self.document.topology.bond_between(target.atoms[0], target.atoms[1])
        elif len(self.selection.selected_bonds) == 1:
            bid = next(iter(self.selection.selected_bonds))

        if bid is not None:
            res = self.session.execute(ModifyBondLength3DCommand(bid, float(target_len)), origin=self.group_tag)
            if res.success:
                self.status_left.setText(f"[{self.group_tag}] {res.message}")
            else:
                self.status_left.setText(f"[{self.group_tag}] {res.message}")
        else:
            self.status_left.setText("请选中 1 条化学键或 2 个成键原子以修改键长")
        self._on_selection_changed()

    def _on_open_modify_bond_length(self):
        bonds = list(self.selection.selected_bonds)
        if len(bonds) == 1:
            self.workspace.view3d_real._prompt_modify_bond_length_inline(bonds[0])
        else:
            self._open_modify_internal_dialog()

    def _set_selected_atom_xyz(self, x: float, y: float, z: float):
        atoms = list(self.selection.selected_atoms)
        if len(atoms) != 1 or not self.document.has_3d or self.document.coordinates.current is None:
            return
        aid = atoms[0]
        old_p = self.document.get_atom_3d_pos(aid)
        if old_p is None:
            return
        new_p = np.array([float(x), float(y), float(z)], dtype=np.float32)
        if float(np.linalg.norm(new_p - old_p)) < 1e-4:
            return
        from ..application.builtin_commands import MoveAtom3DCommand
        self.command_bus.execute(MoveAtom3DCommand(aid, new_p, old_p))
        self._on_selection_changed()

    def _on_save_mforge_project(self):
        return self.save_project(self.document)

    def save_project(self, doc=None):
        from .shells.document_tabs import StudioTabs
        return StudioTabs.save_project(self, doc)

    def _is_doc_modified(self, doc):
        from .shells.document_tabs import StudioTabs
        return StudioTabs._is_doc_modified(self, doc)

    def _confirm_save_if_modified(self, doc):
        from .shells.document_tabs import StudioTabs
        return StudioTabs._confirm_save_if_modified(self, doc)

    def _run_project_autosave(self):
        from ..runtime import data_dir
        from ..io.mforge_storage import save_mforge
        try:
            for session, _view, _tag in self._document_pages.values():
                doc = session.document
                save_mforge(doc, data_dir() / "autosave" / f"{doc.document_id}.mforge")
        except Exception as exc:
            self.statusBar().showMessage(f"自动保存失败：{exc}", 10000)

    def _on_run_calchem_optimization(self):
        """在独立隔离子进程中运行 CalChem 纯 Rust BFGS 优化，彻底杜绝 GIL 导致的 GUI 卡死未响应。"""
        if self.document.num_atoms == 0 or getattr(self, "_calchem_busy", False):
            return

        from PyQt6.QtWidgets import QMessageBox, QProgressDialog
        from PyQt6.QtCore import QTimer

        # 若原子数超过 15 个，提示计算规模与快速力场优化替代选项
        if self.document.num_atoms > 15:
            reply = QMessageBox.question(
                self,
                "启动 CalChem 从头算量子化学优化",
                f"当前分子共有 {self.document.num_atoms} 个原子。\n"
                "CalChem 从头算 RHF/STO-3G 全解析梯度几何优化属于高精度量子化学计算，计算量随原子数急剧上升。\n\n"
                "• 若仅需快速整理 3D 构型，可直接点击主界面顶部的「⚡ 3D 优化」按钮（毫秒级力场）。\n"
                "• 是否继续启动 CalChem 从头算几何优化？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        import os, sys, json, time, subprocess, numpy as np
        from ..io.calchem_bridge import doc_to_calchem_inputs, ApplyCalChemOptCommand

        target = self.document
        revision = target.revision
        charge, spin, _ = self._compute_charge_and_spin()

        try:
            symbols, _, c_in, m_in = doc_to_calchem_inputs(target)
            old_coords = target.coordinates.current.coords.copy()
            coords_ang = old_coords.tolist()
        except Exception as exc:
            QMessageBox.warning(self, "无法启动优化", f"分子几何数据异常: {exc}")
            return

        temp_dir = Path(r"E:	emp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        in_file = temp_dir / f"calchem_opt_in_{os.getpid()}_{time.time_ns()}.json"
        out_file = temp_dir / f"calchem_opt_out_{os.getpid()}_{time.time_ns()}.json"

        in_file.write_text(json.dumps({
            "symbols": symbols,
            "geometry_angstrom": coords_ang,
            "charge": charge if charge != 0 else c_in,
            "multiplicity": spin if spin != 1 else m_in,
            "basis": "sto-3g",
            "max_steps": 35,
        }), encoding="utf-8")

        worker_script = Path(__file__).resolve().parent.parent / "application" / "calculators" / "calchem_subprocess_worker.py"
        py_exe = sys.executable

        # 启动独立子进程
        try:
            proc = subprocess.Popen(
                [py_exe, str(worker_script), "--task", "opt", "--input", str(in_file), "--output", str(out_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "启动失败", f"无法启动 CalChem 子进程: {exc}")
            return

        self._calchem_busy = True
        self.status_left.setText("CalChem (纯 Rust 独立子进程) 极速优化中...")

        progress = QProgressDialog("正在独立子进程中运行 CalChem 纯 Rust BFGS 从头算优化...\n主界面保持完全响应，可随时点击取消。", "⏹ 取消优化", 0, 0, self)
        progress.setWindowTitle("CalChem 几何优化进行中")
        progress.setMinimumDuration(200)
        progress.setModal(True)

        timer = QTimer(self)
        start_time = time.time()

        def check_status():
            elapsed = time.time() - start_time
            progress.setLabelText(f"正在独立子进程中运行 CalChem 纯 Rust BFGS 优化 (已耗时 {elapsed:.1f} 秒)...\n主界面 100% 流畅，可随时点击取消。")

            if progress.wasCanceled():
                timer.stop()
                proc.kill()
                self._calchem_busy = False
                self.status_left.setText("用户已取消 CalChem 几何优化")
                for f in (in_file, out_file):
                    if f.exists():
                        try: f.unlink()
                        except Exception: pass
                return

            ret = proc.poll()
            if ret is not None:
                timer.stop()
                progress.close()
                self._calchem_busy = False

                if out_file.exists():
                    try:
                        res = json.loads(out_file.read_text(encoding="utf-8"))
                    except Exception as e:
                        res = {"success": False, "error": f"解析子进程输出失败: {e}"}
                else:
                    _, err = proc.communicate()
                    res = {"success": False, "error": err or "子进程异常退出"}

                for f in (in_file, out_file):
                    if f.exists():
                        try: f.unlink()
                        except Exception: pass

                if not res.get("success"):
                    QMessageBox.warning(self, "CalChem 优化失败", str(res.get("error", "未知错误")))
                    return

                if self.document is not target or target.revision != revision:
                    QMessageBox.information(self, "优化结果未应用", "目标分子或版本已改变，避免覆盖后续编辑。")
                    return

                new_coords = np.array(res["coords"], dtype=np.float32)
                cmd = ApplyCalChemOptCommand(old_coords, new_coords, res["energy_hartree"])
                applied = self.command_bus.execute(cmd)
                if not applied.success:
                    QMessageBox.warning(self, "优化结果未应用", applied.message)
                    return

                self.workspace.view3d_real.reset_camera()
                self.status_left.setText(
                    f"[{self.group_tag}] CalChem 纯 Rust 优化完成 (能量: {res['energy_hartree']:.6f} Hartree, {res['steps']} 步, 耗时 {res.get('elapsed_seconds', elapsed):.2f}s)"
                )

        timer.timeout.connect(check_status)
        timer.start(150)

    def _open_calchem_orbitals_dialog(self):
        from .dialogs.calchem_orbitals_dialog import CalChemOrbitalsDialog
        CalChemOrbitalsDialog(self, self.document).exec()

    def _open_hpc_job_dialog(self):
        from .dialogs.hpc_job_dialog import HpcJobDialog
        HpcJobDialog(self, self.document).exec()

    def _open_vibrational_spectrum_dialog(self):
        from .dialogs.vibrational_spectrum_dialog import VibrationalSpectrumDialog
        VibrationalSpectrumDialog(self, self.document).exec()

    def _open_multiwfn_dialog(self):
        from .dialogs.aim_qtaim_dialog import AIMQTAIMDialog
        AIMQTAIMDialog(self, self.document).exec()

    def _on_show_calchem_orbitals(self):
        """使用 CalChem 零拷贝内存直通渲染真实 RHF 分子轨道 3D 等值面。"""
        if self.document.num_atoms == 0:
            return
        from .modeling_actions import _background
        from ..io.calchem_bridge import get_calchem_orbital_cube_data, run_calchem_single_point
        import copy
        snapshot = copy.deepcopy(self.document)
        self.status_left.setText("CalChem 纯 Rust 求解 SCF 波函数并提取分子轨道中...")

        def work():
            try:
                cube = get_calchem_orbital_cube_data(snapshot, basis="sto-3g")
                sp = run_calchem_single_point(snapshot, basis="sto-3g")
                return {"success": True, "cube": cube, "sp": sp}
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        def done(result):
            if not result.get("success") or result.get("cube") is None:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "分子轨道生成失败", str(result.get("error", "无法生成网格")))
                return
            cube = result["cube"]
            sp = result.get("sp", {})
            self.workspace.view3d_real.renderer.set_orbital(cube, isovalue=0.03)
            homo_e = sp.get("homo_energy_hartree")
            msg = f"[{self.group_tag}] 已渲染 {cube.orbital_label} 真实 RHF 等值面（蓝=正，橙=负）"
            if homo_e is not None:
                msg += f" (HOMO: {homo_e:.4f} Hartree)"
            self.status_left.setText(msg)

        _background(self, work, done)

    def _on_run_xtb_optimization(self):
        """Run xTB off-thread on a snapshot; only apply to the unchanged target document."""
        if self.document.num_atoms == 0 or getattr(self,"_xtb_busy",False):
            return
        import copy
        from .modeling_actions import _background
        from ..io.calculators import run_xtb_optimization
        from ..application.builtin_commands import TransformCoordinates3DCommand
        target=self.document; revision=target.revision; snapshot=copy.deepcopy(target)
        charge,spin,_=self._compute_charge_and_spin()
        self._xtb_busy=True
        self.status_left.setText("xTB后台优化中；输入为当前分子快照")
        def work():
            try:return run_xtb_optimization(snapshot,charge=charge,uhf=max(0,spin-1))
            except Exception as exc:return {"success":False,"message":str(exc)}
        def done(result):
            self._xtb_busy=False
            if not result.get("success"):
                QMessageBox.warning(self,"xTB优化失败",str(result.get("message")));return
            if self.document is not target or target.revision != revision:
                QMessageBox.information(self,"优化结果未应用","目标分子或版本已改变，避免覆盖后续编辑。请重新运行。");return
            applied=self.command_bus.execute(TransformCoordinates3DCommand(result["coords"],description=f"几何优化 ({result.get('engine')})"))
            if not applied.success:
                QMessageBox.warning(self,"优化结果未应用",applied.message);return
            self.workspace.view3d_real.reset_camera()
            self.status_left.setText(str(result.get("message")))
        _background(self,work,done)

    def _on_generate_frontier_orbital(self, orbital_type: str = "HOMO"):
        """P3-3 实时计算并渲染当前分子的 HOMO / LUMO 前线分子轨道 3D 正负相位等值面。"""
        if self.document.num_atoms == 0:
            return
        try:
            from ..io.cube_reader import generate_frontier_orbital_cube
            cube = generate_frontier_orbital_cube(self.document, orbital_type=orbital_type)
            self.workspace.view3d_real.renderer.set_orbital(cube, isovalue=0.05)
            self.status_left.setText(
                f"[{self.group_tag}] 已生成 {self.document.name} 的 {orbital_type} Hückel/Slater近似示意（非DFT/真实波函数）（蓝=正相位，橙=负相位）"
            )
        except Exception as e:
            QMessageBox.warning(self, "轨道生成提示", f"生成 {orbital_type} 等值面失败：\n{e}")

    def _pick_selected_bond_color(self):
        """只修改选中化学键的独立颜色 (bond.color)，支持 Undo/Redo 且立即在 3D/2D 生效！"""
        bonds = list(self.selection.selected_bonds)
        if not bonds:
            return
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(parent=self, title="选择选中化学键的自定义颜色")
        if not c.isValid():
            return
        color = (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)
        from ..application.builtin_commands import ChangeBondStyleCommand
        self.command_bus.execute(ChangeBondStyleCommand(bonds, color=color))
        for bid in bonds:
            self.workspace.view3d_real.update_single_bond_style(bid, color=color)
        self.workspace.view2d.update()

    def _change_selected_atom_element(self):
        atoms = self.selection.selected_atoms
        if len(atoms) != 1:
            return
        from .element_picker import ElementPickerDialog
        dlg = ElementPickerDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.selected_element is not None:
            from ..application.builtin_commands import ChangeElementCommand
            aid = next(iter(atoms))
            self.command_bus.execute(ChangeElementCommand(aid, dlg.selected_element.atomic_number))
            self._on_selection_changed()

    def _set_selected_atom_charge(self, charge):
        atoms = list(self.selection.selected_atoms)
        if len(atoms) != 1:
            return
        from ..application.builtin_commands import ChangeAtomStyleCommand
        self.command_bus.execute(ChangeAtomStyleCommand(atoms, formal_charge=int(charge)))

    def _pick_selected_atom_color(self):
        """只修改选中原子的独立颜色 (atom.color)，支持 Undo/Redo 且立即在 3D/2D 生效！"""
        atoms = list(self.selection.selected_atoms)
        if not atoms:
            return
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(parent=self, title="选择选中原子的自定义颜色")
        if not c.isValid():
            return
        color = (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)
        from ..application.builtin_commands import ChangeAtomStyleCommand
        self.command_bus.execute(ChangeAtomStyleCommand(atoms, color=color))
        for aid in atoms:
            self.workspace.view3d_real.update_single_atom_style(aid, color=color)
        self.workspace.view2d.update()
        self._on_selection_changed()

    def _finish_layout(self):
        saved = self.settings.value("geometry")
        if saved is not None and len(MolForgeWindow._open_windows) <= 1:
            self.restoreGeometry(saved)
        # Recover geometry only when no current monitor contains a useful part of the window.
        from PyQt6.QtWidgets import QApplication
        frame = self.frameGeometry()
        if not any(screen.availableGeometry().intersected(frame).width() >= 160 and
                   screen.availableGeometry().intersected(frame).height() >= 100
                   for screen in QApplication.screens()):
            available = QApplication.primaryScreen().availableGeometry()
            self.resize(min(self.width(), available.width()), min(self.height(), available.height()))
            self.move(available.topLeft())
        # 左右侧边栏始终保持优雅呈现，绝不在启动时自作主张强制隐藏！
        w_left = 250
        w_right = 330
        w_mid = max(600, self.width() - w_left - w_right - 20)
        self.main_splitter.setSizes([w_left, w_mid, w_right])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        if hasattr(self.workspace, "view_splitter"):
            half = max(350, w_mid // 2)
            self.workspace.view_splitter.setSizes([half, half])
            self.workspace.view_splitter.setStretchFactor(0, 1)
            self.workspace.view_splitter.setStretchFactor(1, 1)
        if hasattr(self.workspace, "view2d"):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(80, self.workspace.view2d.fit_view)
        self._refresh_current_molecule_info()
        self.top_bar.set_project(f"{self.group_tag}  /  {self.document.name}")
        self.top_bar.set_status("就绪")

    def select_active_element(self, atomic_num: int):
        if hasattr(self, "workspace") and hasattr(self.workspace, "select_active_element"):
            self.workspace.select_active_element(atomic_num)

    def _open_periodic_table(self):
        if hasattr(self, "workspace") and hasattr(self.workspace, "_open_periodic_table"):
            self.workspace._open_periodic_table()

    def _on_remove_hydrogens(self):
        from ..application.builtin_commands import DeleteAtomCommand
        h_aids = [aid for aid in self.document.topology.atom_ids if self.document.topology.get_atom(aid).atomic_num == 1]
        if not h_aids:
            self.status_left.setText(f"[{self.group_tag}] 当前分子无显式氢原子")
            return
        for aid in h_aids:
            self.command_bus.execute(DeleteAtomCommand(aid))
        self._on_document_changed(self.document)
        self.status_left.setText(f"[{self.group_tag}] 已移除 {len(h_aids)} 个显式氢原子")

    def _on_tree_atom_selected(self, aid: int):
        from ..domain.models import AtomId
        atom_id = AtomId(aid)
        self.selection.set_selection(atoms=[atom_id])
        self.workspace.view2d.update()
        self.workspace.view3d_real.update()
        atom = self.document.topology.get_atom(atom_id)
        if atom:
            from ..domain.elements import get_element
            elem = get_element(atom.atomic_num)
            coords = self.document.coordinates.current.coords[aid] if aid < len(self.document.coordinates.current.coords) else None
            self.right.update_selected_atom(elem, atom_id=atom_id, xyz=coords)

    def _on_tree_bond_selected(self, bid: int):
        from ..domain.models import BondId
        bond_id = BondId(bid)
        self.selection.set_selection(bonds=[bond_id])
        self.workspace.view2d.update()
        self.workspace.view3d_real.update()
        bond = self.document.topology.get_bond(bond_id)
        if bond:
            self.right.update_selected_bond(bond)

    def _compute_charge_and_spin(self) -> tuple[int, int, str]:
        """实时计算当前分子的总形式电荷 (Charge) 与自旋多重度 (Spin Multiplicity = 2S+1)。"""
        total_charge = 0
        total_electrons = 0
        for aid in self.document.topology.atom_ids:
            atom = self.document.topology.get_atom(aid)
            ch = int(getattr(atom, "formal_charge", 0))
            total_charge += ch
            total_electrons += int(atom.atomic_num) - ch
        spin_mult = 2 if (total_electrons % 2 == 1) else 1
        spin_label = "Doublet" if spin_mult == 2 else "Singlet"
        return total_charge, spin_mult, spin_label

    def _refresh_current_molecule_info(self):
        formula, mw = compute_formula_and_weight_fast(self.document)
        total_q, spin_m, spin_lbl = self._compute_charge_and_spin()
        heavy = sum(1 for aid in self.document.topology.atom_ids if self.document.topology.get_atom(aid).atomic_num > 1)
        hydrogens = sum(1 for aid in self.document.topology.atom_ids if self.document.topology.get_atom(aid).atomic_num == 1)
        n_b = self.document.num_bonds
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "refresh_structure_tree"):
            self.sidebar.refresh_structure_tree(self.document)
        n_a = self.document.num_atoms
        cyclomatic = max(0, n_b - n_a + 1) if n_a > 0 else 0
        rotatable = 0
        for bid in self.document.topology.bond_ids:
            b = self.document.topology.get_bond(bid)
            if b.order == 1:
                za = self.document.topology.get_atom(b.begin).atomic_num
                zb = self.document.topology.get_atom(b.end).atomic_num
                if za > 1 and zb > 1:
                    deg_a = len(list(self.document.topology.neighbors_of(b.begin)))
                    deg_b = len(list(self.document.topology.neighbors_of(b.end)))
                    if deg_a > 1 and deg_b > 1:
                        rotatable += 1

        centroid_str = "(0.00, 0.00, 0.00)"
        point_group = "C1 (非对称)"
        if getattr(self.document, "has_3d", False) and self.document.coordinates.current is not None:
            c = self.document.coordinates.current.coords.mean(axis=0)
            centroid_str = f"({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})"
            # 对称性粗判
            if abs(c[2]) < 0.08 and np.all(np.abs(self.document.coordinates.current.coords[:, 2] - c[2]) < 0.12):
                point_group = "Cs (近平面镜像)"

        self.right.update_molecule_info(
            name=self.document.name,
            formula=formula,
            num_atoms=self.document.num_atoms,
            num_bonds=self.document.num_bonds,
            molecular_weight=mw,
            heavy_atoms=heavy,
            hydrogens=hydrogens,
            charge=total_q,
            spin_mult=spin_m,
            spin_label=spin_lbl,
            rings_count=cyclomatic,
            rotatable_bonds=rotatable,
            centroid_str=centroid_str,
            point_group=point_group,
        )
        self.right.update_molecule_context(
            name=self.document.name,
            formula=formula,
            num_atoms=self.document.num_atoms,
            num_bonds=self.document.num_bonds,
            molecular_weight=mw,
        )
        self.status_right.setText(
            f"原子: {self.document.num_atoms}  ·  键: {self.document.num_bonds}  ·  "
            f"Charge: {total_q:+d}  ·  Spin: {spin_m} ({spin_lbl})"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.setVisible(self.width() >= 1320)

    def closeEvent(self, event):
        for session, _view, _tag in self._document_pages.values():
            if not self._confirm_save_if_modified(session.document):
                event.ignore()
                return
        self._autosave_timer.stop()
        self.settings.setValue("geometry", self.saveGeometry())
        if self in MolForgeWindow._open_windows:
            MolForgeWindow._open_windows.remove(self)
        super().closeEvent(event)

    def _add_document_page(self, doc, session=None):
        from ..application.workspace_registry import WorkspaceRegistry
        registry = WorkspaceRegistry.instance()
        if session is None:
            session, view = registry.create_new_group_view(doc)
        else:
            _same, view = registry.create_new_group_view(session.document)
        self._saved_revisions.setdefault(session.document.document_id, session.document.revision)
        page = Workspace(session.document, session.selection, session.command_bus,
                         on_ring_insert=self._on_ring_insert, on_fg_insert=self._on_fg_insert)
        self._document_pages[page] = (session, view, view.gmv_tag)
        session.command_bus.add_listener(lambda _result, p=page: self._refresh_document_page(p))
        session.selection.add_listener(lambda _origin, p=page: self._refresh_selection_page(p))
        page.view3d_real.on_add_atom_at_3d = self._add_atom_at_3d
        page.view3d_real.on_delete_selected_3d = self._delete_selected
        i = self.document_tabs.addTab(page, session.document.name)
        self.document_tabs.setCurrentIndex(i)
        QTimer.singleShot(20, lambda: page.view3d_real.set_document(session.document))
        return page

    def _refresh_selection_page(self, page):
        if page not in self._document_pages:
            return
        page.view2d.update()
        if page is self.document_tabs.currentWidget():
            self._on_selection_changed()

    def _refresh_document_page(self, page):
        if page not in self._document_pages:
            return
        session = self._document_pages[page][0]
        i = self.document_tabs.indexOf(page)
        if i >= 0:
            self.document_tabs.setTabText(i, session.document.name)
        page.view2d.update()
        if page is self.document_tabs.currentWidget():
            self._on_document_changed(session.document)

    def _activate_document_tab(self, index):
        page = self.document_tabs.widget(index)
        if page not in self._document_pages:
            return
        self.workspace = page
        self.session, self.view_session, self.group_tag = self._document_pages[page]
        self.document = self.session.document
        self.command_bus = self.session.command_bus
        self.selection = self.session.selection
        self._on_document_changed(self.document)
        self._on_selection_changed()

    def _close_document_tab(self, index):
        page = self.document_tabs.widget(index)
        if page is None or page not in self._document_pages:
            return
        if not self._confirm_save_if_modified(self._document_pages[page][0].document):
            return
        if self.document_tabs.count() == 1:
            answer = QMessageBox.question(self, '关闭最后一个文档', '是否返回欢迎界面？')
            if answer == QMessageBox.StandardButton.Yes:
                from .welcome_window import AppController
                AppController.instance().show_welcome()
                self.close()
            return
        page = self.document_tabs.widget(index)
        self._document_pages.pop(page, None)
        self.document_tabs.removeTab(index)
        page.deleteLater()

    def _document_tab_menu(self, pos):
        index = self.document_tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        menu.addAction('关闭', lambda: self._close_document_tab(index))
        menu.addAction('复制', lambda: self._duplicate_document_tab(index))
        menu.addAction('重命名', lambda: self._rename_document_tab(index))
        menu.addSeparator()
        menu.addAction('弹出为独立 3D 窗口', lambda: self._pop_document('3d', index))
        menu.addAction('弹出为独立 2D 窗口', lambda: self._pop_document('2d', index))
        menu.exec(self.document_tabs.tabBar().mapToGlobal(pos))

    def _rename_document_tab(self, index):
        name, ok = QInputDialog.getText(self, '重命名分子', '分子名称：', text=self.document_tabs.tabText(index))
        if ok and name.strip():
            page = self.document_tabs.widget(index)
            self._document_pages[page][0].document.name = name.strip()
            self._document_pages[page][0].document.bump_revision()
            self._refresh_document_page(page)

    def _duplicate_document_tab(self, index):
        import copy, uuid
        page = self.document_tabs.widget(index)
        doc = copy.deepcopy(self._document_pages[page][0].document)
        doc.document_id = uuid.uuid4().hex
        doc.name += ' 副本'
        self._add_document_page(doc)

    def _pop_document(self, mode, index=None):
        page = self.document_tabs.widget(self.document_tabs.currentIndex() if index is None else index)
        if page is None:
            return
        session = self._document_pages[page][0]
        if mode == '3d':
            from .shells.studio_3d import Studio3DWindow
            win = Studio3DWindow(document=session.document, session=session)
        else:
            from .shells.studio_2d import Studio2DWindow
            win = Studio2DWindow(document=session.document, session=session)
        self._studio_windows = getattr(self, '_studio_windows', [])
        self._studio_windows.append(win)
        win.show()

    def _on_document_changed(self, doc: MoleculeDocument):
        self.setWindowTitle(f"[{self.group_tag}] {doc.name} — MolForge {__version__} · AI-Native Molecular & OSC Workbench")
        self.workspace.title_label.setText(f"[{self.group_tag}] {doc.name}  ·  2D/3D 实时联动工作台")
        self.workspace.view2d.set_document(doc)
        self.workspace.view3d_real.set_document(doc)
        self._refresh_current_molecule_info()
        self._refresh_all_open_docks()
        self._on_selection_changed()
        if self.right.stack.currentIndex() == 3:
            self.right._refresh_history()

    def _on_selection_changed(self):
        atoms = self.selection.selected_atoms
        bonds = self.selection.selected_bonds
        if len(atoms) == 1:
            aid = next(iter(atoms))
            if aid in self.document.topology._atoms:
                atom = self.document.topology.get_atom(aid)
                elem = get_element(atom.atomic_num)
                pos = self.document.get_atom_3d_pos(aid)
                deg = len(self.document.topology.neighbors_of(aid))
                hyb = "sp³" if deg >= 4 else ("sp²" if (atom.aromatic or deg == 3) else ("sp" if deg == 2 else "单配位"))
                self.right.update_selected_atom(
                    elem,
                    getattr(atom, "formal_charge", 0),
                    atom_scale=float(getattr(atom, "scale", 1.0)),
                    atom_id=aid,
                    xyz=(float(pos[0]), float(pos[1]), float(pos[2])) if pos is not None else None,
                    hybridization=f"{deg}配位 · {hyb}",
                    frozen=bool(atom.properties.get("frozen")),
                )
            self.right.update_selected_atoms_summary([], self.document)
        elif len(atoms) > 1:
            self.right.update_selected_atom(None)
            self.right.update_selected_atoms_summary(list(atoms), self.document)
            sorted_aids = sorted(atoms, key=lambda a: a.value if hasattr(a, "value") else int(a))
            id_strs = [f"#{a.value+1}" for a in sorted_aids[:10]]
            suffix = f" ...等共 {len(sorted_aids)} 个" if len(sorted_aids) > 10 else ""
            self.status_left.setText(f"[{self.group_tag}] 已选中原子片段: {', '.join(id_strs)}{suffix}")
        else:
            self.right.update_selected_atom(None)
            self.right.update_selected_atoms_summary([], self.document)

        if len(bonds) == 1:
            bid = next(iter(bonds))
            if bid in self.document.topology._bonds:
                bond = self.document.topology.get_bond(bid)
                self.right.update_selected_bond(bond)
        else:
            self.right.update_selected_bond(None)
        self._update_measurement()

    def _update_measurement(self):
        if not self.document.has_3d or self.document.coordinates.current is None:
            self.right.measure_label.setText("按住 Shift 选中 2 原子/1 键测键长(Å)，3 原子/2 邻键测键角(°)，4 原子测二面角(°)")
            self.right.measure_label.setStyleSheet("color:#9AB0C2;")
            return
        from ..application import measurement as mm
        from ..application.measurement_targets import MeasurementTargetResolver
        target = MeasurementTargetResolver.resolve(self.document, self.selection)
        if target.kind == "none":
            self.right.measure_label.setText("按住 Shift 选中 2 原子/1 键测键长(Å)，3 原子/2 邻键测键角(°)，4 原子测二面角(°)")
            self.right.measure_label.setStyleSheet("color:#9AB0C2;")
            return
        if target.kind in ("invalid", "ambiguous"):
            self.right.update_measurement(target.diagnostic)
            return
        frame = self.document.coordinates.current
        _, order = self.document.topology.atom_index_map()
        coords = frame.coords
        atoms = target.atoms
        if not all(a in order and order[a] < len(coords) for a in atoms):
            return
        idx = [order[a] for a in atoms]
        if target.kind == "distance" and len(idx) == 2:
            d = mm.distance(coords, idx[0], idx[1])
            self.right.update_measurement(f"距离 ({target.label})：{d:.3f} Å")
        elif target.kind == "angle" and len(idx) == 3:
            val, ok, diag = mm.angle(coords, idx[0], idx[1], idx[2])
            self.right.update_measurement(f"键角 ({target.label})：{val:.2f}°" if ok else diag)
        elif target.kind == "dihedral" and len(idx) == 4:
            val, ok, diag = mm.dihedral(coords, idx[0], idx[1], idx[2], idx[3])
            self.right.update_measurement(f"二面角 ({target.label})：{val:.2f}°" if ok else diag)

    def _on_background_3d_changed(self, color):
        self.workspace.view3d_real.set_background_color(
            color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0
        )

    def _export_2d_svg(self, path: str) -> None:
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            from rdkit.Chem.Draw import rdMolDraw2D
            rdmol, _, _ = doc_to_rdkit(self.document, sanitize=True)
            rdmol = Chem.RemoveHs(rdmol)
            AllChem.Compute2DCoords(rdmol)
            drawer = rdMolDraw2D.MolDraw2DSVG(600, 450)
            drawer.DrawMolecule(rdmol)
            drawer.FinishDrawing()
            Path(path).write_text(drawer.GetDrawingText(), encoding="utf-8")
            return
        except Exception:
            pass

        wmap = self.workspace.view2d._ensure_world_coords_2d()
        lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="600" height="450" viewBox="0 0 600 450">']
        lines.append('<rect width="100%" height="100%" fill="#FFFFFF"/>')
        for bid in self.document.topology.bond_ids:
            b = self.document.topology.get_bond(bid)
            if b.begin in wmap and b.end in wmap:
                x1, y1 = 300 + wmap[b.begin][0] * 36, 225 - wmap[b.begin][1] * 36
                x2, y2 = 300 + wmap[b.end][0] * 36, 225 - wmap[b.end][1] * 36
                lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#1F2D3A" stroke-width="2.2"/>')
        lines.append("</svg>")
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    # ---------- 工业级全格式导出（含 SMILES / SDF / MOL / PDB / MOL2 / XYZ / GJF / REST ctrl.in / ORCA .inp / SVG / PNG） ----------

    def _export_smiles_string(self) -> str:
        try:
            from rdkit import Chem
            rdmol, _, _ = doc_to_rdkit(self.document, sanitize=True)
            rdmol_noh = Chem.RemoveHs(rdmol)
            return Chem.MolToSmiles(rdmol_noh)
        except Exception:
            formula, _ = compute_formula_and_weight_fast(self.document)
            return f"C  # {self.document.name} ({formula})"

    def _on_export(self):
        from ..application.calculators.qc_input_generator import (
            generate_gaussian_gjf, generate_rest_ctrl_in, extract_xyz_lines
        )
        filters = (
            "Gaussian 输入文件 (*.gjf *.com);;"
            "复旦 REST 输入文件 (ctrl.in *.in *.toml);;"
            "ORCA 输入文件 (*.inp);;"
            "XYZ 三维坐标文件 (*.xyz);;"
            "SDF 结构数据文件 (*.sdf);;"
            "MDL MOL V2000 结构文件 (*.mol);;"
            "PDB 蛋白质/分子结构 (*.pdb);;"
            "SYBYL MOL2 结构文件 (*.mol2);;"
            "SMILES 分子线性表达式 (*.smi *.smiles);;"
            "SVG 出版级 2D 矢量图 (*.svg);;"
            "PNG 高清视图截图 (*.png)"
        )
        path, selected = QFileDialog.getSaveFileName(
            self, "导出分子结构或量子化学输入卡", self.document.name, filters
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            if selected.startswith("SVG") or ext == ".svg":
                self._export_2d_svg(path)
            elif selected.startswith("PNG") or ext == ".png":
                pix = self.workspace.grab()
                pix.save(path, "PNG")
            elif selected.startswith("Gaussian") or ext in (".gjf", ".com"):
                Path(path).write_text(generate_gaussian_gjf(self.document), encoding="utf-8")
            elif selected.startswith("复旦 REST") or ext in (".in", ".toml") or Path(path).name.lower() == "ctrl.in":
                Path(path).write_text(generate_rest_ctrl_in(self.document), encoding="utf-8")
            elif selected.startswith("ORCA") or ext == ".inp":
                Path(path).write_text(export_document_to_orca_inp(self.document), encoding="utf-8")
            elif selected.startswith("XYZ") or ext == ".xyz":
                xyz_lines = extract_xyz_lines(self.document)
                content = f"{len(xyz_lines)}\n{self.document.name}\n" + "\n".join(xyz_lines) + "\n"
                Path(path).write_text(content, encoding="utf-8")
            elif selected.startswith("PDB") or ext == ".pdb":
                Path(path).write_text(export_document_to_pdb(self.document), encoding="utf-8")
            elif selected.startswith("SYBYL") or ext == ".mol2":
                Path(path).write_text(export_document_to_mol2(self.document), encoding="utf-8")
            elif selected.startswith("SMILES") or ext in (".smi", ".smiles"):
                smi = self._export_smiles_string()
                Path(path).write_text(f"{smi}\t{self.document.name}\n", encoding="utf-8")
            elif selected.startswith("SDF") or ext == ".sdf":
                mol_block = export_document_to_mol_v2000(self.document)
                Path(path).write_text(mol_block + "$$$$\n", encoding="utf-8")
            else:
                Path(path).write_text(export_document_to_mol_v2000(self.document), encoding="utf-8")

            self.status_left.setText(f"[{self.group_tag}] 已成功导出：{Path(path).name}")
            QMessageBox.information(self, "导出成功", f"已成功导出文件：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出文件时出错：\n{str(e)}")

    def _replace_active_document(self, doc: MoleculeDocument):
        self.document = doc
        from ..application.workspace_registry import WorkspaceRegistry
        self.session, self.view_session = WorkspaceRegistry.instance().register_explicit_tag(
            self.group_tag, self.document
        )
        self.command_bus = self.session.command_bus
        self.command_bus.add_listener(lambda result, doc=self.document: self._on_document_changed(doc) if self.document is doc else None)
        self.selection = self.session.selection
        self.selection.add_listener(lambda origin: QTimer.singleShot(0, self._on_selection_changed))
        if hasattr(self, 'document_tabs'):
            self._document_pages[self.workspace] = (self.session, self.view_session, self.group_tag)
            self.document_tabs.setTabText(self.document_tabs.currentIndex(), doc.name)

        self.workspace.document = self.document
        self.workspace.command_bus = self.command_bus
        self.workspace.view2d.set_document(self.document)
        self.workspace.view2d.set_selection_service(self.selection)
        self.workspace.view2d.set_command_bus(self.command_bus)
        self.workspace.view3d_real.set_document(self.document)
        self.workspace.view3d_real.set_selection_service(self.selection)
        self.workspace.view3d_real.set_command_bus(self.command_bus)
        self.setWindowTitle(f"[{self.group_tag}] {self.document.name} — MolForge {__version__} · AI-Native Molecular & OSC Workbench")
        self.workspace.title_label.setText(f"[{self.group_tag}] {self.document.name}  ·  2D/3D 实时联动工作台")
        self._refresh_current_molecule_info()
        self.top_bar.set_project(f"{self.group_tag}  /  {self.document.name}")
        self._refresh_all_open_docks()

    def open_molecule_file(self, path: str | Path) -> bool:
        file_path = Path(path)
        try:
            doc, meta = load_molecule_document(file_path)
            if doc.num_atoms == 0:
                QMessageBox.warning(self, "打开提示", f"文件 {file_path.name} 中未解析到有效原子坐标。")
                return False

            self._add_document_page(doc)

            # 记录到最近打开文件列表
            recents = list(self.settings.value("recent_files", []) or [])
            s_path = str(file_path.resolve())
            if s_path in recents:
                recents.remove(s_path)
            recents.insert(0, s_path)
            self.settings.setValue("recent_files", recents[:12])
            self._rebuild_recent_files_menu()

            extra_info = ""
            if meta.get("homo_ev") and meta.get("lumo_ev"):
                extra_info = (
                    f"  |  HOMO={meta['homo_ev']:.2f} eV, LUMO={meta['lumo_ev']:.2f} eV, "
                    f"Eg={meta.get('gap_ev', 0.0):.2f} eV"
                )
            elif meta.get("energy_ev"):
                extra_info = f"  |  E={meta['energy_ev']:.2f} eV"

            self.status_left.setText(
                f"[{self.group_tag}] 已加载 {file_path.name}：{doc.num_atoms} 原子 · {doc.num_bonds} 化学键{extra_info}"
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"文件 {file_path.name} 解析失败：\n{str(e)}")
            return False

    def _on_new_blank(self):
        try:
            doc = MoleculeDocument(name=f"未命名-{self.document_tabs.count() + 1}" if hasattr(self, "document_tabs") else "未命名")
            page = self._add_document_page(doc)
            page._on_tool_selected("原子")
            self.status_left.setText(f"[{self.group_tag}] 空白画布已就绪（已自动开启 [原子 (A)] 绘制模式，点击画布即可添加原子）")
        except Exception as e:
            QMessageBox.warning(self, "新建空白", f"新建空白画布时出错：{e}")

    def _on_open_file(self):
        filters = (
            "所有支持的化学与量化文件 (*.mforge *.log *.out *.gjf *.com *.xyz *.mol *.sdf *.sd *.pdb *.ent *.cif *.mmcif *.mol2 *.in *.toml *.inp *.smi *.smiles);;"
            "Gaussian / ORCA / REST 输出日志 (*.log *.out);;"
            "Gaussian / REST / ORCA 输入文件 (*.gjf *.com *.in *.toml *.inp);;"
            "XYZ / MOL / SDF / MOL2 / PDB 结构 (*.xyz *.mol *.sdf *.mol2 *.pdb);;"
            "所有文件 (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "打开分子结构或量化输出日志", "", filters)
        if path:
            self.open_molecule_file(path)

    def _on_save_file(self):
        self._on_export()

    def _on_load_orbital(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载轨道 Cube", "", "Cube 文件 (*.cub *.cube);;所有文件 (*)"
        )
        if not path:
            return
        try:
            cube = self.workspace.view3d_real.load_orbital_cube(path, isovalue=0.05)
            self.status_left.setText(
                f"[{self.group_tag}] 已加载轨道 Cube ({cube.dims[0]}×{cube.dims[1]}×{cube.dims[2]})：蓝/橙为波函数正负相位"
            )
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"错误: {str(e)}")

    def _on_clear_orbital(self):
        self.workspace.view3d_real.clear_orbital()
        self.status_left.setText(f"[{self.group_tag}] 已清除轨道等值面")

    def _on_open_bio(self):
        from molforge.io.gemmi_adapter import parse_bio
        from molforge.ui.bio_structure_dialog import BioStructureDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "打开生物结构", "", "结构文件 (*.pdb *.cif *.mmcif);;所有文件 (*)"
        )
        if not path:
            return
        try:
            bio = parse_bio(path)
            from molforge.ui.molstar_window import MolStarWindow
            lower = path.lower()
            fmt = "mmcif" if lower.endswith((".cif", ".mmcif")) else "pdb"
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            self._molstar_win = MolStarWindow(text, fmt, bio.name, self)
            self._molstar_win.show()
            BioStructureDialog(bio, self).exec()
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"错误: {str(e)}")

    def _on_open_trajectory(self):
        topo, _ = QFileDialog.getOpenFileName(
            self, "选择拓扑文件 (gro/pdb)", "", "拓扑文件 (*.gro *.pdb *.tpr);;所有文件 (*)"
        )
        if not topo:
            return
        traj, _ = QFileDialog.getOpenFileName(
            self, "选择轨迹文件 (xtc/dcd/trr)", "", "轨迹文件 (*.xtc *.dcd *.trr);;所有文件 (*)"
        )
        if not traj:
            return
        try:
            import os
            from molforge.ui.trajectory_window import TrajectoryWindow
            name = os.path.splitext(os.path.basename(traj))[0]
            self._traj_win = TrajectoryWindow(topo, traj, name, self)
            self._traj_win.show()
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"错误: {str(e)}")

    def _on_about(self):
        from .. import __version__
        QMessageBox.about(
            self, f"关于 MolForge v{__version__}",
            f"<h3>MolForge v{__version__} · AI-Native 分子科学工作台</h3>"
            "<p>对标 ChemDraw / Chem3D / GaussView / VMD 的自研分子工作台（深色仪器面板风，中文界面）</p>"
            "<ul>"
            "<li><b>2D 真实编辑</b>：RDKit 后端加/删原子、加/删键、环工具，全部经命令总线可撤销</li>"
            "<li><b>2D⇄3D 实时同步</b>：左 2D 右 3D（VTK 球棍/表面）同一文档，原子交叉高亮、1-based 编号同源</li>"
            "<li><b>分析/结果直连当前分子</b>：平面性与描述符有本地实现；波函数/光谱需独立输入链，近似图明确标注</li>"
            "<li><b>外接分子动力学</b>：MDAnalysis 内存安全分析（RMSD/Rg/RMSF/RDF/氢键）+ GROMACS 脚本与 Pueue 入队</li>"
            "<li><b>大模型接入</b>：OpenAI 兼容 function calling，LLM 可读结构、经命令总线编辑、跑分析</li>"
            "</ul>"
            "<p style='color:#888;'>后端：PyQt6 · RDKit · VTK · MDAnalysis。未实时调度 Gaussian/Multiwfn，仅解析已算结果。</p>"
        )

    def _open_help_docs(self):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        help_path = Path(__file__).resolve().parents[2] / "docs" / "HELP.md"
        if help_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_path)))
        else:
            QMessageBox.information(self, "帮助文档", f"未找到帮助文档：{help_path}")

    def _undo(self):
        result = self.command_bus.undo()
        self.status_left.setText(f"[{self.group_tag}] 已撤销：{result.message}" if result.success else f"[{self.group_tag}] 没有可撤销的操作")

    def _redo(self):
        result = self.command_bus.redo()
        self.status_left.setText(f"[{self.group_tag}] 已重做：{result.message}" if result.success else f"[{self.group_tag}] 没有可重做的操作")

    def _delete_selected(self):
        atoms = list(self.selection.selected_atoms)
        bonds = list(self.selection.selected_bonds)
        if not atoms and not bonds:
            self.status_left.setText(f"[{self.group_tag}] 未选中原子或化学键")
            return
        from ..application.selection_commands import DeleteSelectionCommand
        result = self.command_bus.execute(DeleteSelectionCommand(atoms, bonds))
        if not result.success:
            self.status_left.setText(result.message)
            return
        self.selection.clear()
        self.status_left.setText(f"[{self.group_tag}] 已删除 {len(atoms)} 个原子, {len(bonds)} 条键")

    def _on_molecule_selected(self, name: str):
        doc = create_sample_molecule(name)
        self._replace_active_document(doc)
        self.status_left.setText(f"[{self.group_tag}] 已切换分子：{self.document.name}")

    # ---------- v7.0 新增：11 标签页 Gaussian Setup、1/2/4 多视口分屏、欢迎页启动器 ----------

    def _open_gaussian_11tab_setup(self):
        from .dialogs.gaussian_calculation_setup import GaussianCalculationSetupDialog
        dlg = GaussianCalculationSetupDialog(self.document, parent=self)
        dlg.exec()
        return dlg

    def set_3d_multiview_count(self, pane_count: int = 1):
        """在当前 3D 渲染窗口内切换 1 / 2 / 4 视口 (P1..P4)，直接调用 Render3DWidget.set_multiview_layout。"""
        aux = self.workspace.view3d_real.set_multiview_layout(pane_count)
        self.status_left.setText(f"[{self.group_tag}] 已切换 3D 视口分屏布局为：{pane_count} 视口 (P1..P{pane_count})")
        return aux

    def _open_welcome_launcher(self):
        from .welcome_window import AppController
        AppController.instance().show_welcome()

    def _open_tool_path_config_dialog(self):
        from .shells.workflow_inputs import ToolPathConfigDialog
        ToolPathConfigDialog(self).exec()
