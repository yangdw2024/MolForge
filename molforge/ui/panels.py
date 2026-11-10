"""
ui/panels.py - MolForge 现代科学级桌面左右侧边栏与属性面板系统
===================================================================
核心重构升级：
  1. 【左侧栏 LeftPanel 全能重构】：
     - Tab 0: 🧱 结构砌块 (OSC 给受体共轭骨架、经典分子、常见芳香/杂环、常用官能团，内置实时模糊过滤搜索)
     - Tab 1: ⚛️ 元素与键 (常用元素 CPK 真实色标网格、化学键级一键设定、自动加氢/去氢/2D美化/3D力场优化/居中)
     - Tab 2: 🌳 结构树 (实时原子列表与化学键列表，支持点击列表行直接在 2D/3D 画布中联动高亮选中，实现全链路响应)
  2. 【彻底消除滚轮卡死与垂直滚动失效】：
     - 彻底移除 CollapsibleCard 标题行多余的 HorizontalWheelScrollArea，消除无谓事件拦截，恢复原生顺滑垂直滚轮！
     - 优化 WheelGuardFilter，未聚焦控件的滚轮事件主动向外冒泡给垂直滚动容器，绝不吃掉滚轮事件！
  3. 【右侧栏 RightPanel 工业级抗截断与模型配置】：
     - 面板最小宽度提至 330px，输入框、按钮预留充裕显示边距，杜绝任何中文字体或 Placeholder 被截断！
     - 模型名采用高可靠 QLineEdit 直接绑定（去除多余下拉覆盖 Bug），新增醒目「💾 保存配置」按键与「✓ 已同步」实时灯。
     - AI 助手就地异步对话，支持模型调用工具时界面确认与分析结果格式化渲染，并提供可选「🗗 独立弹窗」。
     - 属性面板在无选中项时呈现分子全局物化画像（MW、单同位素、电荷、自旋、LogP、TPSA、对称性等）。
"""
from __future__ import annotations

import os
import sys
import html
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QSettings, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QIcon, QWheelEvent, QColor, QCursor
from PyQt6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QStackedWidget, QButtonGroup, QComboBox, QTextEdit,
    QSizePolicy, QDoubleSpinBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QSlider, QListWidget, QListWidgetItem, QCheckBox, QMenu
)

from .settings_panel import WheelGuardFilter, install_wheel_guard
from .theme import refresh_button_visual
from .scrolling import HorizontalWheelScrollArea

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def ic(name: str) -> QIcon:
    p = ICON_DIR / f"{name}.svg"
    return QIcon(str(p)) if p.exists() else QIcon()


def section(text: str) -> QLabel:
    q = QLabel(text.upper())
    q.setProperty("role", "section")
    return q


def muted(text: str) -> QLabel:
    q = QLabel(text)
    q.setWordWrap(True)
    q.setProperty("role", "muted")
    return q


def create_smooth_scroll_area(content_widget: QWidget) -> QScrollArea:
    """创建不截断、无背景补丁、自适应宽度的顺滑纵向滚动区。"""
    content_widget.setObjectName("ScrollPage")
    content_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setWidget(content_widget)
    return sa


class CollapsibleCard(QFrame):
    """Blender / DaVinci 风格可折叠属性卡片模块（纯净标题，不截获垂直滚轮事件）。"""

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleCard")
        self._title = title

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        arrow = "▾" if expanded else "▸"
        self.header_btn = QPushButton(f"{arrow}  {title}")
        self.header_btn.setObjectName("CardHeaderBtn")
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(expanded)
        self.header_btn.clicked.connect(self._on_toggled)
        root.addWidget(self.header_btn)

        self.body = QWidget()
        self.body.setObjectName("ScrollPage")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 9, 10, 10)
        self.body_layout.setSpacing(7)
        self.body.setVisible(expanded)
        root.addWidget(self.body)

    def _on_toggled(self, checked: bool):
        self.body.setVisible(checked)
        arrow = "▾" if checked else "▸"
        self.header_btn.setText(f"{arrow}  {self._title}" if self._title else "")


class TopBar(QFrame):
    open_clicked = pyqtSignal()
    export_clicked = pyqtSignal()
    qc_workbench_clicked = pyqtSignal()
    search_submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("TopBar")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        strip = QWidget()
        strip.setObjectName("ToolbarStrip")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        brand = QLabel("MolForge")
        brand.setProperty("role", "brand")
        brand.setStyleSheet("font-size:16px; font-weight:800; color:#66DEC9; margin-right:4px;")
        lay.addWidget(brand)

        self.project_label = QLabel("未命名分子")
        self.project_label.setStyleSheet("color:#EAF2F6; font-size:13px; font-weight:600;")
        lay.addWidget(self.project_label)

        self.status_label = QLabel("● 就绪")
        self.status_label.setStyleSheet("color:#66DEC9; font-weight:700; font-size:12px;")
        lay.addWidget(self.status_label)

        lay.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("快捷命令或智能搜索 (Ctrl+K)...")
        self.search_input.setMinimumWidth(180)
        self.search_input.setMaximumWidth(260)
        self.search_input.returnPressed.connect(lambda: self.search_submitted.emit(self.search_input.text().strip()))
        lay.addWidget(self.search_input)

        open_btn = QPushButton("📂 打开 / 导入")
        open_btn.setMinimumWidth(96)
        open_btn.setToolTip("打开分子或量化输出：.log / .out / .gjf / .xyz / .mol / .sdf / .pdb / ctrl.in (Ctrl+O)")
        open_btn.clicked.connect(self.open_clicked.emit)
        lay.addWidget(open_btn)

        qc_btn = QPushButton("⚛ 量化 / 能级图")
        qc_btn.setMinimumWidth(106)
        qc_btn.setToolTip("打开 Gaussian、复旦 REST 与 OSC HOMO-LUMO 能级图工作台 (Ctrl+G)")
        qc_btn.clicked.connect(self.qc_workbench_clicked.emit)
        lay.addWidget(qc_btn)

        export = QPushButton("💾 导出 / 保存")
        export.setMinimumWidth(96)
        export.setProperty("role", "action")
        export.setToolTip("导出 2D 矢量 SVG / PNG / GJF / REST ctrl.in / XYZ / PDB / MOL (Ctrl+S)")
        export.clicked.connect(self.export_clicked.emit)
        lay.addWidget(export)

        outer.addWidget(strip)
        self.setFixedHeight(48)

    def set_project(self, text: str):
        self.project_label.setText(text)

    def set_status(self, text: str, color: str = "#66DEC9"):
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color:{color}; font-weight:700; font-size:12px;")


class NavigationRail(QFrame):
    """为了兼容性保留的导航条对象（现主要作为内部信号兼容）"""
    rail_selected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("NavRail")
        self.setFixedWidth(0)
        self.setVisible(False)

    def set_active_index(self, tab_idx: int):
        pass


# ==============================================================================
# 左侧全功能化学工具箱与结构树 (LeftPanel / Sidebar)
# ==============================================================================

class LeftPanel(QFrame):
    """
    MolForge 现代科学建模工具箱与结构树 (LeftPanel)
    三合一全功能面板：
      Tab 0: 🧱 结构砌块 (共轭砌块、环系模板、官能团取代，带实时搜索)
      Tab 1: ⚛️ 元素与键 (CPK 常用元素调色板、键级设定、结构几何修饰)
      Tab 2: 🌳 结构树 (实时原子列表与化学键列表，支持点击联动 2D/3D 画布选中)
    """

    def __init__(self, on_molecule_selected=None, on_ring_insert=None, on_fg_insert=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(380)

        self.on_molecule_selected = on_molecule_selected
        self.on_ring_insert = on_ring_insert
        self.on_fg_insert = on_fg_insert
        self.on_element_selected = None
        self.on_bond_order_selected = None
        self.on_clean_2d = None
        self.on_clean_3d = None
        self.on_add_h = None
        self.on_remove_h = None
        self.on_center = None
        self.on_atom_selected = None
        self.on_bond_selected = None
        self._current_document = None

        self._wheel_guard = WheelGuardFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 8, 6, 8)
        outer.setSpacing(6)

        # 顶部胶囊导航条
        tab_frame = QFrame()
        tab_frame.setObjectName("TabStripFrame")
        tabs = QHBoxLayout(tab_frame)
        tabs.setContentsMargins(2, 2, 2, 2)
        tabs.setSpacing(2)

        self.tab_buttons: list[QPushButton] = []
        for i, title in enumerate(("🧱 砌块库", "⚛️ 元素/键", "🌳 结构树")):
            b = QPushButton(title)
            b.setProperty("role", "tab")
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, idx=i: self.switch_tab(idx))
            tabs.addWidget(b)
            self.tab_buttons.append(b)
            refresh_button_visual(b, active=(i == 0))
        outer.addWidget(tab_frame)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # 1. 砌块与基团页
        self.stack.addWidget(create_smooth_scroll_area(self._build_fragments_page()))
        # 2. 元素与成键页
        self.stack.addWidget(create_smooth_scroll_area(self._build_elements_and_bonds_page()))
        # 3. 结构树与测量页
        self.stack.addWidget(create_smooth_scroll_area(self._build_structure_tree_page()))

        self.stack.setCurrentIndex(0)

    def set_document(self, document):
        self._current_document = document
        if self.stack.currentIndex() == 2:
            self.refresh_structure_tree(document)

    def switch_tab(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            for i, b in enumerate(self.tab_buttons):
                refresh_button_visual(b, active=(i == index))
            if index == 2 and self._current_document is not None:
                self.refresh_structure_tree(self._current_document)

    # ---------- Tab 0: 结构砌块库 ----------
    def _build_fragments_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(7)

        # 快速搜索框
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("🔍 快速筛选砌块、分子、环系或基团...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter_edit)

        # 💡 使用指南卡片（操作逻辑一目了然）
        guide_frame = QFrame()
        guide_frame.setObjectName("GuideBox")
        guide_frame.setStyleSheet("background-color: rgba(13, 148, 136, 0.12); border: 1px solid rgba(94, 234, 212, 0.28); border-radius: 6px; padding: 5px;")
        g_lay = QVBoxLayout(guide_frame)
        g_lay.setContentsMargins(4, 4, 4, 4)
        g_lay.setSpacing(3)
        lbl_g1 = QLabel("💡 <b>砌块与基团使用指南：</b>")
        lbl_g1.setStyleSheet("color: #5EEAD4; font-weight: 700;")
        lbl_g2 = QLabel("• <b>选中原子时</b>：点击环系/基团，自动在其上精准接枝取代")
        lbl_g2.setStyleSheet("color: #C2D5E5;")
        lbl_g3 = QLabel("• <b>未选原子时</b>：点击环系在画布中心放置独立新结构")
        lbl_g3.setStyleSheet("color: #C2D5E5;")
        lbl_g4 = QLabel("• <b>点击分子库</b>：一键载入标准分子，支持随时另存为自定义砌块")
        lbl_g4.setStyleSheet("color: #C2D5E5;")
        g_lay.addWidget(lbl_g1)
        g_lay.addWidget(lbl_g2)
        g_lay.addWidget(lbl_g3)
        g_lay.addWidget(lbl_g4)
        lay.addWidget(guide_frame)

        # ⭐ 我的自定义砌块 (用户保存分子与片段库)
        self.custom_card = CollapsibleCard("⭐ 我的自定义砌块 (CUSTOM)", expanded=True)
        c_lay = self.custom_card.body_layout
        row_c_actions = QHBoxLayout()
        btn_save_cur = QPushButton("➕ 存整分子")
        btn_save_cur.setToolTip("将当前画布中的分子保存为自定义砌块")
        btn_save_cur.setStyleSheet("QPushButton { font-weight:700; }")
        btn_save_cur.clicked.connect(self._on_save_current_as_fragment)
        row_c_actions.addWidget(btn_save_cur)

        btn_save_sel = QPushButton("✂️ 存选中片段")
        btn_save_sel.setToolTip("将当前画布中选中的原子片段保存为自定义砌块")
        btn_save_sel.setStyleSheet("QPushButton { font-weight:700; }")
        btn_save_sel.clicked.connect(self._on_save_selected_as_fragment)
        row_c_actions.addWidget(btn_save_sel)
        c_lay.addLayout(row_c_actions)

        self.custom_chips_container = QWidget()
        self.custom_chips_layout = QVBoxLayout(self.custom_chips_container)
        self.custom_chips_layout.setContentsMargins(0, 2, 0, 0)
        self.custom_chips_layout.setSpacing(4)
        c_lay.addWidget(self.custom_chips_container)
        self.custom_fragment_buttons: list[tuple[str, QPushButton]] = []
        self._refresh_custom_fragments_card()
        lay.addWidget(self.custom_card)

        # 分类分子库
        self.molecule_buttons: list[tuple[str, QPushButton]] = []
        from ..io.rdkit_adapter import SAMPLE_MOLECULES

        mol_categories = [
            ("🌟 光伏与共轭材料 (OSC)", [
                "PM6 核心单元 (BDT-F)", "Y6 受体核心单元", "ITIC 核心单元", "BDT 给体核 (苯并二噻吩)",
                "咔唑 (Carbazole)", "芴 (Fluorene)", "螺芴 (Spiro 核心)", "并五苯 (Pentacene)",
                "碗烯 (Corannulene/C60片段)", "IC 端基 (1,3-茚满酮型)", "2F-IC 端基 (Y6/IT-4F)",
                "2Cl-IC 端基 (BTP-eC9)", "BT 受体核 (苯并噻二唑)", "DTBT 光伏单元", "噻吩-苯-噻吩"
            ], True),
            ("💊 常用药物与生化单元 (BIO)", [
                "咖啡因", "阿司匹林", "布洛芬", "扑热息痛 (对乙酰氨基酚)",
                "腺嘌呤 (Adenine)", "鸟嘌呤 (Guanine)", "胞嘧啶 (Cytosine)",
                "胸腺嘧啶 (Thymine)", "尿嘧啶 (Uracil)"
            ], False),
            ("⬡ 经典芳烃与多环稠环", [
                "苯", "萘 (Naphthalene)", "蒽 (Anthracene)", "菲 (Phenanthrene)",
                "芘 (Pyrene)", "三联苯 (p-Terphenyl)"
            ], False),
            ("⬠ 常见杂环与配体", [
                "吡啶 (Pyridine)", "噻吩 (Thiophene)", "呋喃 (Furan)", "吡咯 (Pyrrole)",
                "吲哚 (Indole)", "喹啉 (Quinoline)", "联吡啶 (2,2-Bipyridine)"
            ], False),
        ]

        self.mol_cards = []
        for cat_title, mol_names, is_exp in mol_categories:
            card = CollapsibleCard(cat_title, expanded=is_exp)
            card_lay = card.body_layout
            grid = QGridLayout()
            grid.setSpacing(5)
            col_idx = 0
            for txt in mol_names:
                if txt in SAMPLE_MOLECULES:
                    b = QPushButton(txt)
                    b.setProperty("role", "chip")
                    b.setCheckable(True)
                    b.setMinimumHeight(28)
                    b.setToolTip(f"点击载入标准分子「{txt}」")
                    b.clicked.connect(lambda checked=False, name=txt: self._on_molecule_clicked(name))
                    grid.addWidget(b, col_idx // 2, col_idx % 2)
                    self.molecule_buttons.append((txt, b))
                    col_idx += 1
            card_lay.addLayout(grid)
            lay.addWidget(card)
            self.mol_cards.append(card)

        # 环系与稠环
        self.ring_card = CollapsibleCard("共轭环与常见环系 (RINGS)", expanded=True)
        r_lay = self.ring_card.body_layout
        r_lay.addWidget(muted("选中原子时接枝；未选中时在画布放置独立新环："))
        r_grid = QGridLayout()
        r_grid.setSpacing(5)
        self.ring_buttons: list[tuple[str, QPushButton]] = []
        ring_defs = [
            ("⬡ 苯环 (6Ar)", 6, True, {}),
            ("⬠ 噻吩 (S)", 5, True, {0: 16}),
            ("⬡ 吡啶 (N)", 6, True, {0: 7}),
            ("⬠ 呋喃 (O)", 5, True, {0: 8}),
            ("⬠ 吡咯 (NH)", 5, True, {0: 7}),
            ("⬠ 咪唑 (N2)", 5, True, {0: 7, 2: 7}),
            ("⬠ 噻唑 (S,N)", 5, True, {0: 16, 2: 7}),
            ("⬠ 恶唑 (O,N)", 5, True, {0: 8, 2: 7}),
            ("⬡ 环己烷", 6, False, {}),
            ("⬠ 环戊烷", 5, False, {}),
            ("□ 环丁烷", 4, False, {}),
            ("△ 环丙烷", 3, False, {}),
        ]
        for idx, (name, size, arom, hetero) in enumerate(ring_defs):
            b = QPushButton(name)
            b.setProperty("role", "chip")
            b.setCheckable(True)
            b.setMinimumHeight(28)
            b.setToolTip(f"向当前选中原子接上 {name}；未选时放置独立新环")
            b.clicked.connect(lambda checked=False, btn=b, s=size, a=arom, h=hetero: self._on_ring_clicked(btn, s, a, h))
            r_grid.addWidget(b, idx // 2, idx % 2)
            self.ring_buttons.append((name, b))
        r_lay.addLayout(r_grid)
        lay.addWidget(self.ring_card)

        # 官能团取代
        self.fg_card = CollapsibleCard("常用官能团取代 (GROUPS)", expanded=True)
        f_lay = self.fg_card.body_layout
        f_lay.addWidget(muted("选中原子后点击接枝并优化几何构型："))
        f_grid = QGridLayout()
        f_grid.setSpacing(5)
        self.fg_buttons: list[tuple[str, QPushButton]] = []
        fgs = [
            ("氟代 -F", "-F"),
            ("氯代 -Cl", "-Cl"),
            ("溴代 -Br", "-Br"),
            ("碘代 -I", "-I"),
            ("羟基 -OH", "-OH"),
            ("氨基 -NH₂", "-NH2"),
            ("硝基 -NO₂", "-NO2"),
            ("氰基 -CN", "-CN"),
            ("羧基 -COOH", "-COOH"),
            ("醛基 -CHO", "-CHO"),
            ("甲氧基 -OCH₃", "-OCH3"),
            ("甲基 -CH₃", "-CH3"),
            ("三氟甲基 -CF₃", "-CF3"),
        ]
        for idx, (fg_label, fg_code) in enumerate(fgs):
            b = QPushButton(fg_label)
            b.setProperty("role", "chip")
            b.setCheckable(True)
            b.setMinimumHeight(28)
            b.setToolTip(f"接枝 {fg_label}，实时同步 2D/3D")
            b.clicked.connect(lambda checked=False, btn=b, code=fg_code: self._on_fg_clicked(btn, code))
            f_grid.addWidget(b, idx // 2, idx % 2)
            self.fg_buttons.append((fg_label, b))
        f_lay.addLayout(f_grid)
        lay.addWidget(self.fg_card)

        lay.addStretch(1)
        return w

    def _apply_filter(self, query: str):
        q = query.strip().lower()
        for name, btn in self.molecule_buttons:
            btn.setVisible(not q or q in name.lower())
        for name, btn in self.ring_buttons:
            btn.setVisible(not q or q in name.lower())
        for name, btn in self.fg_buttons:
            btn.setVisible(not q or q in name.lower())
        for name, btn in getattr(self, "custom_fragment_buttons", []):
            btn.setVisible(not q or q in name.lower())

    def _refresh_custom_fragments_card(self):
        while self.custom_chips_layout.count() > 0:
            item = self.custom_chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count() > 0:
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        from ..domain.custom_fragments import load_custom_fragments
        frags = load_custom_fragments()
        self.custom_fragment_buttons = []
        if not frags:
            self.custom_chips_layout.addWidget(muted("暂无自定义砌块。点击上方按钮可将分子或选中片段存入。"))
            return
        grid = QGridLayout()
        grid.setSpacing(5)
        for idx, item in enumerate(frags):
            name = item.get("name", "未命名")
            smi = item.get("smiles", "")
            desc = item.get("description", "")
            btn = QPushButton(f"★ {name}")
            btn.setProperty("role", "chip")
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.setToolTip(f"{name}\nSMILES: {smi}\n说明: {desc}\n（左键插入当前画布，右键可删除）")
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, n=name: self._show_custom_fragment_menu(n))
            btn.clicked.connect(lambda checked=False, s=smi, n=name: self._on_custom_fragment_clicked(s, n))
            grid.addWidget(btn, idx // 2, idx % 2)
            self.custom_fragment_buttons.append((name, btn))
        self.custom_chips_layout.addLayout(grid)

    def _show_custom_fragment_menu(self, name: str):
        menu = QMenu(self)
        del_act = menu.addAction(f"🗑️ 删除砌块「{name}」")
        del_act.triggered.connect(lambda: self._on_delete_custom_fragment(name))
        menu.exec(QCursor.pos())

    def _on_delete_custom_fragment(self, name: str):
        from ..domain.custom_fragments import remove_custom_fragment
        if remove_custom_fragment(name):
            self._refresh_custom_fragments_card()

    def _on_custom_fragment_clicked(self, smiles: str, name: str):
        if getattr(self, "on_custom_fragment_insert", None):
            self.on_custom_fragment_insert(smiles, name)
        elif hasattr(self, "_window_ref") and self._window_ref is not None:
            from ..io.rdkit_adapter import create_molecule_from_smiles
            try:
                new_doc = create_molecule_from_smiles(smiles, name=name)
                self._window_ref._merge_document_into_current(new_doc)
            except Exception as e:
                QMessageBox.warning(self, "插入失败", f"无法插入自定义砌块: {e}")

    def _on_save_current_as_fragment(self):
        win = getattr(self, "_window_ref", None)
        if win is None:
            QMessageBox.information(self, "提示", "请在工作台画布中打开分子后再保存。")
            return
        doc = getattr(win, "document", None)
        if doc is None or doc.num_atoms == 0:
            QMessageBox.information(self, "提示", "当前文档为空，无法保存为砌块。")
            return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "保存自定义砌块", "请输入自定义砌块名称：", text=doc.name or "我的砌块")
        if not ok or not name.strip():
            return
        from ..io.rdkit_adapter import doc_to_rdkit
        from rdkit import Chem
        try:
            rdmol = doc_to_rdkit(doc)[0]
            smi = Chem.MolToSmiles(rdmol)
            if not smi:
                raise ValueError("未能生成有效的 SMILES")
            from ..domain.custom_fragments import add_custom_fragment
            add_custom_fragment(name.strip(), smi, f"{doc.num_atoms} 原子 · 全分子")
            self._refresh_custom_fragments_card()
            QMessageBox.information(self, "保存成功", f"自定义砌块「{name.strip()}」已成功保存到左侧砌块库！")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法将当前分子转换为砌块: {e}")

    def _on_save_selected_as_fragment(self):
        win = getattr(self, "_window_ref", None)
        if win is None:
            QMessageBox.information(self, "提示", "请在工作台画布中打开分子。")
            return
        doc = getattr(win, "document", None)
        sel = getattr(win, "selection", None)
        if doc is None or sel is None or not sel.selected_atoms:
            QMessageBox.information(self, "提示", "请先在 2D 或 3D 画布中选中要保存为砌块的原子片段。")
            return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "保存选中片段为砌块", "请输入片段砌块名称：", text=f"片段_{len(sel.selected_atoms)}原子")
        if not ok or not name.strip():
            return
        try:
            from ..domain.document import MoleculeDocument
            sub_doc = MoleculeDocument(name=name.strip())
            old_to_new = {}
            for aid in sel.selected_atoms:
                old_atom = doc.topology.get_atom(aid)
                new_aid = sub_doc.topology.add_atom(old_atom.atomic_num, formal_charge=old_atom.formal_charge, aromatic=old_atom.aromatic)
                old_to_new[aid] = new_aid
            for bid in doc.topology.bond_ids:
                b = doc.topology.get_bond(bid)
                if b.begin in old_to_new and b.end in old_to_new:
                    sub_doc.topology.add_bond(old_to_new[b.begin], old_to_new[b.end], b.order, aromatic=b.aromatic)
            from ..io.rdkit_adapter import doc_to_rdkit
            from rdkit import Chem
            rdmol = doc_to_rdkit(sub_doc, sanitize=False)[0]
            smi = Chem.MolToSmiles(rdmol)
            if not smi:
                raise ValueError("未能生成有效 SMILES")
            from ..domain.custom_fragments import add_custom_fragment
            add_custom_fragment(name.strip(), smi, f"{len(sel.selected_atoms)} 原子片段")
            self._refresh_custom_fragments_card()
            QMessageBox.information(self, "保存成功", f"选中片段「{name.strip()}」已成功存为自定义砌块！")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法提取选中片段: {e}")

    def _on_ring_clicked(self, clicked_btn: QPushButton, size: int, aromatic: bool, hetero: dict):
        for _, b in self.ring_buttons:
            refresh_button_visual(b, active=(b is clicked_btn))
        for _, b in self.fg_buttons:
            refresh_button_visual(b, active=False)
        if self.on_ring_insert is not None:
            self.on_ring_insert(size, aromatic, hetero)

    def _on_fg_clicked(self, clicked_btn: QPushButton, fg_code: str):
        for _, b in self.fg_buttons:
            refresh_button_visual(b, active=(b is clicked_btn))
        for _, b in self.ring_buttons:
            refresh_button_visual(b, active=False)
        if self.on_fg_insert is not None:
            self.on_fg_insert(fg_code)

    def _on_molecule_clicked(self, name: str):
        for mol_name, btn in self.molecule_buttons:
            refresh_button_visual(btn, active=(mol_name == name))
        if self.on_molecule_selected:
            self.on_molecule_selected(name)

    # ---------- Tab 1: 元素调色板与成键设定 ----------
    def _build_elements_and_bonds_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(7)

        # 元素调色板
        el_card = CollapsibleCard("常用化学元素调色板 (ELEMENTS)", expanded=True)
        e_lay = el_card.body_layout
        e_grid = QGridLayout()
        e_grid.setSpacing(5)

        elements_data = [
            ("C", 6, "#333333", "#EAF2F6", "碳"),
            ("H", 1, "#E8E8E8", "#1E293B", "氢"),
            ("O", 8, "#EF4444", "#FFFFFF", "氧"),
            ("N", 7, "#3B82F6", "#FFFFFF", "氮"),
            ("S", 16, "#EAB308", "#1E293B", "硫"),
            ("P", 15, "#F97316", "#FFFFFF", "磷"),
            ("F", 9, "#84CC16", "#1E293B", "氟"),
            ("Cl", 17, "#10B981", "#FFFFFF", "氯"),
            ("Br", 35, "#B91C1C", "#FFFFFF", "溴"),
            ("I", 53, "#9333EA", "#FFFFFF", "碘"),
            ("B", 5, "#F472B6", "#1E293B", "硼"),
            ("Si", 14, "#CBD5E1", "#1E293B", "硅"),
            ("Fe", 26, "#EA580C", "#FFFFFF", "铁"),
            ("Pt", 78, "#6366F1", "#FFFFFF", "铂"),
        ]

        self.element_palette_buttons: list[QPushButton] = []
        for i, (sym, z, bg_col, text_col, name_cn) in enumerate(elements_data):
            b = QPushButton(f"{sym} {name_cn}")
            b.setCheckable(True)
            b.setMinimumHeight(28)
            b.setToolTip(f"{name_cn} (原子序数: {z}) - 点击切换当前绘制元素")
            b.setStyleSheet(
                f"QPushButton {{ background-color: {bg_col}; color: {text_col}; font-weight: bold; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); }}"
                f"QPushButton:hover {{ border: 2px solid #5EEAD4; }}"
                f"QPushButton:checked {{ border: 2px solid #66DEC9; font-size: 13px; }}"
            )
            b.clicked.connect(lambda checked=False, btn=b, atomic_z=z: self._on_palette_element_clicked(btn, atomic_z))
            e_grid.addWidget(b, i // 2, i % 2)
            self.element_palette_buttons.append(b)
            if z == 6:  # 默认选中碳
                b.setChecked(True)
        e_lay.addLayout(e_grid)

        more_el_btn = QPushButton("🧪 周期表选择更多元素...")
        more_el_btn.clicked.connect(lambda: getattr(self, "on_open_periodic_table", lambda: None)())
        e_lay.addWidget(more_el_btn)
        lay.addWidget(el_card)

        # 键级选择
        b_card = CollapsibleCard("化学键型设定 (BOND ORDERS)", expanded=True)
        b_lay = b_card.body_layout
        b_grid = QGridLayout()
        b_grid.setSpacing(5)

        bonds_data = [
            ("— 单键 (Single)", 1),
            ("= 双键 (Double)", 2),
            ("≡ 叁键 (Triple)", 3),
            (": 芳香键 (Aromatic)", 4),
            ("▲ 楔形前向 (Wedge)", 5),
            ("▰ 虚线后向 (Dash)", 6),
        ]
        self.bond_type_buttons: list[QPushButton] = []
        for idx, (label, order_val) in enumerate(bonds_data):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setMinimumHeight(28)
            b.clicked.connect(lambda checked=False, btn=b, oval=order_val: self._on_palette_bond_clicked(btn, oval))
            b_grid.addWidget(b, idx // 2, idx % 2)
            self.bond_type_buttons.append(b)
            if order_val == 1:
                refresh_button_visual(b, active=True)
        b_lay.addLayout(b_grid)
        lay.addWidget(b_card)

        # 结构快捷工具
        t_card = CollapsibleCard("结构修饰快捷工具 (QUICK ACTIONS)", expanded=True)
        t_lay = t_card.body_layout
        for icon_txt, tip, cb_name in [
            ("⚡ 自动补齐氢原子 (Add H)", "为当前结构未满价态的重原子补齐 3D 氢原子", "on_add_h"),
            ("💨 隐藏全部氢原子 (Remove H)", "隐藏或移除所有氢原子以清晰展示分子骨架", "on_remove_h"),
            ("✨ 2D 骨架美化 (Clean 2D)", "按 RDKit 拓扑美学重新排列 2D 平面坐标", "on_clean_2d"),
            ("🔄 3D 快速力场优化 (Clean 3D)", "执行 MMFF94 / UFF 快速力场能量极小化", "on_clean_3d"),
            ("🎯 空间居中归零 (Center)", "将分子几何中心无损平移对齐至三维原点 (0,0,0)", "on_center"),
        ]:
            btn = QPushButton(icon_txt)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked=False, name=cb_name: getattr(self, name, lambda: None)() if getattr(self, name, None) else None)
            t_lay.addWidget(btn)
        lay.addWidget(t_card)

        lay.addStretch(1)
        return w

    def _on_palette_element_clicked(self, clicked_btn: QPushButton, atomic_z: int):
        for b in self.element_palette_buttons:
            b.setChecked(b is clicked_btn)
        if self.on_element_selected:
            self.on_element_selected(atomic_z)

    def _on_palette_bond_clicked(self, clicked_btn: QPushButton, order: int):
        for b in self.bond_type_buttons:
            refresh_button_visual(b, active=(b is clicked_btn))
        if self.on_bond_order_selected:
            self.on_bond_order_selected(order)

    # ---------- Tab 2: 结构树与测量 ----------
    def _build_structure_tree_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(7)

        # 结构统计卡片
        self.tree_info_label = QLabel("当前分子原子与化学键树：")
        self.tree_info_label.setStyleSheet("color:#66DEC9; font-weight:700; font-size:12px;")
        lay.addWidget(self.tree_info_label)

        # 原子表格
        atom_card = CollapsibleCard("原子列表 (ATOMS - 点击在视口中选中)", expanded=True)
        a_lay = atom_card.body_layout
        self.atom_table = QTableWidget(0, 5)
        self.atom_table.setHorizontalHeaderLabels(["#ID", "元素", "X (Å)", "Y (Å)", "Z (Å)"])
        self.atom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.atom_table.verticalHeader().setVisible(False)
        self.atom_table.setAlternatingRowColors(True)
        self.atom_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.atom_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.atom_table.setMinimumHeight(170)
        self.atom_table.cellClicked.connect(self._on_atom_table_clicked)
        a_lay.addWidget(self.atom_table)
        lay.addWidget(atom_card)

        # 键表格
        bond_card = CollapsibleCard("化学键列表 (BONDS - 点击在视口中选中)", expanded=True)
        b_lay = bond_card.body_layout
        self.bond_table = QTableWidget(0, 4)
        self.bond_table.setHorizontalHeaderLabels(["#ID", "原子对", "键级", "键长 (Å)"])
        self.bond_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bond_table.verticalHeader().setVisible(False)
        self.bond_table.setAlternatingRowColors(True)
        self.bond_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bond_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.bond_table.setMinimumHeight(150)
        self.bond_table.cellClicked.connect(self._on_bond_table_clicked)
        b_lay.addWidget(self.bond_table)
        lay.addWidget(bond_card)

        lay.addStretch(1)
        return w

    def _on_atom_table_clicked(self, row: int, col: int):
        item = self.atom_table.item(row, 0)
        if item is not None and self.on_atom_selected:
            aid = item.data(Qt.ItemDataRole.UserRole)
            if aid is None:
                try:
                    raw_val = int(item.text().lstrip("#")) - 1
                    aid = AtomId(raw_val)
                except Exception:
                    pass
            if aid is not None:
                self.on_atom_selected(aid)

    def _on_bond_table_clicked(self, row: int, col: int):
        item = self.bond_table.item(row, 0)
        if item is not None and self.on_bond_selected:
            bid = item.data(Qt.ItemDataRole.UserRole)
            if bid is None:
                try:
                    raw_val = int(item.text().lstrip("#")) - 1
                    bid = BondId(raw_val)
                except Exception:
                    pass
            if bid is not None:
                self.on_bond_selected(bid)

    def refresh_structure_tree(self, document):
        if document is None or not hasattr(document, "topology"):
            return
        top = document.topology
        coords_arr = document.coordinates.current.coords if hasattr(document, "coordinates") and document.coordinates and document.coordinates.current is not None else None

        # 大体系虚拟截断保护：超过 500 个原子/键时仅渲染前 500 项，防止超大盒子导致 GUI 假死
        max_display = 500
        total_atoms = top.num_atoms
        total_bonds = top.num_bonds
        disp_atom_count = min(total_atoms, max_display)
        disp_bond_count = min(total_bonds, max_display)

        if total_atoms > max_display:
            self.tree_info_label.setText(f"{document.name}：共 {total_atoms} 原子 · {total_bonds} 键 (当前显示前 {disp_atom_count} 个)")
        else:
            self.tree_info_label.setText(f"{document.name}：共 {total_atoms} 原子 · {total_bonds} 键")

        # 刷新原子列表
        self.atom_table.setRowCount(disp_atom_count)
        atom_id_list = list(top.atom_ids)[:disp_atom_count]
        for row, aid in enumerate(atom_id_list):
            atom = top.get_atom(aid)
            it0 = QTableWidgetItem(f"#{aid.value + 1}")
            it0.setData(Qt.ItemDataRole.UserRole, aid)
            it0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.atom_table.setItem(row, 0, it0)

            it1 = QTableWidgetItem(f"{atom.symbol} ({atom.atomic_num})")
            it1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.atom_table.setItem(row, 1, it1)

            p3 = document.get_atom_3d_pos(aid)
            if p3 is None and coords_arr is not None and aid.value < len(coords_arr):
                p3 = coords_arr[aid.value]

            if p3 is not None:
                it_x = QTableWidgetItem(f"{float(p3[0]):.3f}")
                it_y = QTableWidgetItem(f"{float(p3[1]):.3f}")
                it_z = QTableWidgetItem(f"{float(p3[2]):.3f}")
            else:
                it_x = QTableWidgetItem("0.000")
                it_y = QTableWidgetItem("0.000")
                it_z = QTableWidgetItem("0.000")

            it_x.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_y.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_z.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.atom_table.setItem(row, 2, it_x)
            self.atom_table.setItem(row, 3, it_y)
            self.atom_table.setItem(row, 4, it_z)

        # 刷新化学键列表
        self.bond_table.setRowCount(disp_bond_count)
        order_names = {1: "单键", 2: "双键", 3: "叁键", 4: "芳香"}
        bond_id_list = list(top.bond_ids)[:disp_bond_count]
        for row, bid in enumerate(bond_id_list):
            bond = top.get_bond(bid)
            a1 = top.get_atom(bond.begin)
            a2 = top.get_atom(bond.end)
            pair_str = f"#{bond.begin.value + 1} {a1.symbol} - #{bond.end.value + 1} {a2.symbol}"
            b_order_str = order_names.get(int(bond.order), f"{bond.order}")
            
            # 计算键长
            length_str = "—"
            p1 = document.get_atom_3d_pos(bond.begin)
            p2 = document.get_atom_3d_pos(bond.end)
            if p1 is None and coords_arr is not None and bond.begin.value < len(coords_arr):
                p1 = coords_arr[bond.begin.value]
            if p2 is None and coords_arr is not None and bond.end.value < len(coords_arr):
                p2 = coords_arr[bond.end.value]

            if p1 is not None and p2 is not None:
                import numpy as np
                dist = float(np.linalg.norm(np.asarray(p1) - np.asarray(p2)))
                length_str = f"{dist:.3f}"

            it_b0 = QTableWidgetItem(f"#{bid.value + 1}")
            it_b0.setData(Qt.ItemDataRole.UserRole, bid)
            it_b0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bond_table.setItem(row, 0, it_b0)

            it_b1 = QTableWidgetItem(pair_str)
            it_b1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bond_table.setItem(row, 1, it_b1)

            it_b2 = QTableWidgetItem(b_order_str)
            it_b2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bond_table.setItem(row, 2, it_b2)

            it_b3 = QTableWidgetItem(length_str)
            it_b3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.bond_table.setItem(row, 3, it_b3)


# 保持向后兼容别名
Sidebar = LeftPanel


class RightPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("RightPanel")
        self._document_provider = None
        self._command_bus_provider = None
        self._selection_provider = None
        self.ai_action_executor = None
        self._chat_worker = None
        self._chat_bridge = None
        self._wheel_guard = WheelGuardFilter(self)
        self.setMinimumWidth(260)
        self.setMaximumWidth(600)

        from ..application.ai.deepseek_client import DeepSeekChemistryAssistant
        self.settings_store = QSettings("MolForge", "AI_Config")
        saved_key = self.settings_store.value("deepseek_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        self.deepseek = DeepSeekChemistryAssistant(api_key=str(saved_key))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 10, 9, 9)
        outer.setSpacing(8)

        # 顶部精致分段胶囊导航条
        tab_frame = QFrame()
        tab_frame.setObjectName("TabStripFrame")
        tabs = QHBoxLayout(tab_frame)
        tabs.setContentsMargins(3, 3, 3, 3)
        tabs.setSpacing(3)
        self.stack = QStackedWidget()

        self._tab_buttons: list[QPushButton] = []
        for i, title in enumerate(("属性", "AI 助手", "量化", "历史", "设置")):
            b = QPushButton(title)
            b.setProperty("role", "tab")
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, index=i: self.switch_tab(index))
            tabs.addWidget(b)
            self._tab_buttons.append(b)
            refresh_button_visual(b, active=(i == 0))
        outer.addWidget(tab_frame)

        self.inspect_page = self._inspect()
        self.stack.addWidget(create_smooth_scroll_area(self.inspect_page))

        self.assistant_page = self._assistant()
        self.stack.addWidget(create_smooth_scroll_area(self.assistant_page))

        self.jobs_page, self.jobs_box = self._page()
        self.stack.addWidget(create_smooth_scroll_area(self.jobs_page))

        self.history_page, self.history_box = self._page()
        self.stack.addWidget(create_smooth_scroll_area(self.history_page))

        from .settings_panel import SettingsPanel
        self.settings_panel = SettingsPanel()
        self.stack.addWidget(create_smooth_scroll_area(self.settings_panel))

        self.stack.currentChanged.connect(self._on_tab_changed)
        self.stack.setCurrentIndex(0)
        outer.addWidget(self.stack, 1)

    def switch_tab(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            for i, b in enumerate(self._tab_buttons):
                refresh_button_visual(b, active=(i == index))

    def _page(self):
        page = QWidget()
        page.setObjectName("ScrollPage")
        box = QVBoxLayout(page)
        box.setContentsMargins(2, 2, 5, 10)
        box.setSpacing(9)
        return page, box

    def _inspect(self):
        page, box = self._page()

        mol_card = CollapsibleCard("当前分子概览 (MOLECULE)", expanded=True)
        mc_lay = mol_card.body_layout
        self.mol_name_label = QLabel("咖啡因 · C₈H₁₀N₄O₂")
        self.mol_name_label.setWordWrap(True)
        self.mol_name_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #66DEC9;")
        mc_lay.addWidget(self.mol_name_label)

        self.inspect_labels = {}
        for t, v in (
            ("化学式", "C8H10N4O2"),
            ("相对分子质量", "194.19 Da"),
            ("原子 (重/氢)", "24 (14 重 / 10 氢)"),
            ("化学键 (单/双/芳)", "25 键"),
            ("净电荷 / 自旋", "0 / 单重态 (Singlet)"),
            ("环系数量", "2 环 (双环稠合)"),
            ("可旋转单键", "3 个"),
            ("空间质心 (Å)", "(0.00, 0.00, 0.00)"),
            ("空间点群对称性", "C1 (非对称)"),
            ("3D 渲染器", "VTK Studio Phong"),
        ):
            row = QHBoxLayout()
            row.addWidget(muted(t))
            row.addStretch()
            value_label = QLabel(v)
            value_label.setProperty("role", "value")
            self.inspect_labels[t] = value_label
            row.addWidget(value_label)
            mc_lay.addLayout(row)
        box.addWidget(mol_card)

        box.addWidget(self._atom_editor_card())
        box.addWidget(self._bond_editor_card())

        meas_card = CollapsibleCard("3D 空间几何测量 (GEOMETRY)", expanded=True)
        self.measure_label = QLabel("按住 Shift 选中 2 原子测键长(Å)，3 原子测键角(°)，4 原子测二面角(°)")
        self.measure_label.setWordWrap(True)
        self.measure_label.setStyleSheet("color:#9AB0C2;")
        meas_card.body_layout.addWidget(self.measure_label)
        mod_ic_btn = QPushButton("📐 精确修改选中内坐标 (键长/键角/二面角)...")
        mod_ic_btn.clicked.connect(lambda: getattr(self, "on_open_modify_internal", lambda: None)() if getattr(self, "on_open_modify_internal", None) else None)
        meas_card.body_layout.addWidget(mod_ic_btn)
        box.addWidget(meas_card)

        box.addWidget(self._visualization_card())

        box.addStretch(1)
        return page

    def update_measurement(self, text):
        self.measure_label.setText(text)
        self.measure_label.setStyleSheet("color:#66DEC9; font-weight:700; font-size:13px;")

    def _visualization_card(self):
        card = CollapsibleCard("🎨 科学可视化与渲染控制 (VISUALIZATION)", expanded=True)
        l = card.body_layout

        l.addWidget(muted("3D 分子展示风格 (REPRESENTATION)："))
        grid_st = QGridLayout()
        grid_st.setSpacing(5)
        self.repr_buttons = []
        for idx, (label, mode_code) in enumerate([
            ("⚽ 球棍模型 (Ball & Stick)", "ball_stick"),
            ("🌐 空间填充 (CPK)", "cpk"),
            ("🥢 棍状模型 (Stick)", "line"),
            ("🧵 细线框 (Wireframe)", "wireframe"),
        ]):
            btn = QPushButton(label)
            btn.setProperty("role", "chip")
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.clicked.connect(lambda checked=False, m=mode_code, b=btn: self._on_switch_3d_repr(m, b))
            grid_st.addWidget(btn, idx // 2, idx % 2)
            self.repr_buttons.append((mode_code, btn))
            refresh_button_visual(btn, active=(idx == 0))
        l.addLayout(grid_st)

        l.addWidget(muted("3D 视口标注与参考系统："))
        row_chk = QHBoxLayout()
        self.chk_3d_labels = QCheckBox("显示原子序号 (#ID)")
        self.chk_3d_labels.toggled.connect(self._on_toggle_3d_labels)
        row_chk.addWidget(self.chk_3d_labels)

        self.chk_3d_symbols = QCheckBox("显示元素符号")
        self.chk_3d_symbols.toggled.connect(self._on_toggle_3d_symbols)
        row_chk.addWidget(self.chk_3d_symbols)
        l.addLayout(row_chk)

        row_chk2 = QHBoxLayout()
        self.chk_3d_axes = QCheckBox("显示空间坐标轴")
        self.chk_3d_axes.setChecked(True)
        self.chk_3d_axes.toggled.connect(self._on_toggle_3d_axes)
        row_chk2.addWidget(self.chk_3d_axes)

        self.chk_3d_hs = QCheckBox("显示 3D 氢原子")
        self.chk_3d_hs.setChecked(True)
        self.chk_3d_hs.toggled.connect(self._on_toggle_3d_hs)
        row_chk2.addWidget(self.chk_3d_hs)
        l.addLayout(row_chk2)

        l.addWidget(muted("3D 视口背景环境预设："))
        row_bg = QHBoxLayout()
        self.combo_3d_bg = QComboBox()
        self.combo_3d_bg.addItems(["深邃科研黑 (Studio Dark)", "学术纯白 (Paper White)", "蓝灰微光 (Slate #1E293B)"])
        self.combo_3d_bg.currentIndexChanged.connect(self._on_change_3d_background_preset)
        row_bg.addWidget(self.combo_3d_bg, 1)
        l.addLayout(row_bg)

        l.addWidget(muted("2D 绘图视图快速控制："))
        row_2d = QHBoxLayout()
        btn_fit_2d = QPushButton("⛶ 2D 画布居中适配")
        btn_fit_2d.setToolTip("自动将 2D 分子缩放居中于当前画布")
        btn_fit_2d.clicked.connect(self._on_fit_2d_view)
        row_2d.addWidget(btn_fit_2d)

        btn_paper_2d = QPushButton("切换 2D 纸面底色")
        btn_paper_2d.setToolTip("在 ChemDraw 暖白纸面与暗夜底色间切换")
        btn_paper_2d.clicked.connect(self._on_toggle_2d_paper)
        row_2d.addWidget(btn_paper_2d)
        l.addLayout(row_2d)

        return card

    def _on_switch_3d_repr(self, mode_code: str, clicked_btn: QPushButton):
        for m, b in getattr(self, "repr_buttons", []):
            refresh_button_visual(b, active=(b is clicked_btn))
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            from ..rendering.contracts import RepresentationMode
            mode_map = {
                "ball_stick": RepresentationMode.BALL_AND_STICK,
                "cpk": RepresentationMode.CPK,
                "line": RepresentationMode.LINE,
                "wireframe": RepresentationMode.LINE,
            }
            if mode_code in mode_map:
                win.workspace.view3d_real.set_mode(mode_map[mode_code])

    def _on_toggle_3d_labels(self, checked: bool):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            win.workspace.view3d_real.set_view_options(show_labels=checked)

    def _on_toggle_3d_symbols(self, checked: bool):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            win.workspace.view3d_real.set_view_options(show_symbols=checked)

    def _on_toggle_3d_axes(self, checked: bool):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            win.workspace.view3d_real.set_view_options(show_axes=checked)

    def _on_toggle_3d_hs(self, checked: bool):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            win.workspace.view3d_real.set_view_options(show_hydrogens=checked)

    def _on_change_3d_background_preset(self, index: int):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view3d_real"):
            colors = [
                (0.047, 0.086, 0.133),
                (0.98, 0.98, 0.98),
                (0.118, 0.161, 0.231),
            ]
            if 0 <= index < len(colors):
                r, g, b = colors[index]
                win.workspace.view3d_real.set_background_color(r, g, b)

    def _on_fit_2d_view(self):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view2d"):
            win.workspace.view2d.fit_view()

    def _on_toggle_2d_paper(self):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "workspace") and win.workspace and hasattr(win.workspace, "view2d"):
            win.workspace.view2d._toggle_paper_mode()

    def _atom_editor_card(self):
        from PyQt6.QtWidgets import QSlider, QComboBox
        card = CollapsibleCard("选中原子属性 (ATOM INSPECTOR)", expanded=True)
        l = card.body_layout

        # 多选原子片段专属信息卡片
        self.multi_atom_card = QFrame()
        self.multi_atom_card.setStyleSheet("background:#13283E; border:1px solid #1F4565; border-radius:6px; padding:6px;")
        mac_lay = QVBoxLayout(self.multi_atom_card)
        mac_lay.setContentsMargins(6, 6, 6, 6)
        mac_lay.setSpacing(5)

        self.multi_atom_ids_label = QLabel("已选中片段原子序号：")
        self.multi_atom_ids_label.setWordWrap(True)
        self.multi_atom_ids_label.setStyleSheet("color:#66DEC9; font-weight:700; font-size:12px;")
        mac_lay.addWidget(self.multi_atom_ids_label)

        self.multi_atom_pos_label = QLabel("片段几何质心：—")
        self.multi_atom_pos_label.setStyleSheet("color:#9AB0C2; font-size:11px;")
        mac_lay.addWidget(self.multi_atom_pos_label)

        row_mac_btns = QHBoxLayout()
        btn_frag_save = QPushButton("💾 存为砌块...")
        btn_frag_save.setToolTip("将当前选中的原子片段保存到左侧砌块库")
        btn_frag_save.clicked.connect(self._save_selected_fragment_to_library)
        row_mac_btns.addWidget(btn_frag_save)

        btn_frag_clear = QPushButton("取消多选")
        btn_frag_clear.clicked.connect(self._clear_selection)
        row_mac_btns.addWidget(btn_frag_clear)
        mac_lay.addLayout(row_mac_btns)

        l.addWidget(self.multi_atom_card)
        self.multi_atom_card.setVisible(False)

        self.atom_info_label = QLabel("未选中原子（点击 2D/3D 原子即可选中）")
        self.atom_info_label.setWordWrap(True)
        self.atom_info_label.setStyleSheet("color:#9AB0C2; font-weight:600;")
        l.addWidget(self.atom_info_label)

        row_el = QHBoxLayout()
        row_el.addWidget(muted("元素种类"))
        row_el.addStretch()
        self.atom_element_label = QLabel("—")
        self.atom_element_label.setProperty("role", "value")
        row_el.addWidget(self.atom_element_label)
        change_btn = QPushButton("周期表替换...")
        change_btn.clicked.connect(self._change_selected_atom_element)
        row_el.addWidget(change_btn)
        l.addLayout(row_el)

        row_sc_hdr = QHBoxLayout()
        row_sc_hdr.addWidget(muted("选中原子大小（只调这个）"))
        row_sc_hdr.addStretch()
        self.atom_scale_val_lbl = QLabel("100%")
        self.atom_scale_val_lbl.setProperty("role", "value")
        row_sc_hdr.addWidget(self.atom_scale_val_lbl)
        l.addLayout(row_sc_hdr)

        self.atom_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.atom_scale_slider.setRange(40, 300)
        self.atom_scale_slider.setValue(100)
        install_wheel_guard(self.atom_scale_slider, self._wheel_guard)
        self.atom_scale_slider.valueChanged.connect(self._on_selected_atom_scale_changed)
        l.addWidget(self.atom_scale_slider)

        row_ch = QHBoxLayout()
        row_ch.addWidget(muted("形式电荷"))
        row_ch.addStretch()
        self.atom_charge_combo = QComboBox()
        for c in (-2, -1, 0, 1, 2):
            self.atom_charge_combo.addItem(("+" if c > 0 else "") + str(c) if c != 0 else "0", c)
        self.atom_charge_combo.setCurrentIndex(2)
        install_wheel_guard(self.atom_charge_combo, self._wheel_guard)
        self.atom_charge_combo.currentIndexChanged.connect(self._on_charge_changed)
        row_ch.addWidget(self.atom_charge_combo)

        color_btn = QPushButton("自定义颜色...")
        color_btn.clicked.connect(self._on_pick_atom_color)
        row_ch.addWidget(color_btn)
        l.addLayout(row_ch)

        # 杂化方式 + 相连成键邻居原子
        row_hyb = QHBoxLayout()
        row_hyb.addWidget(muted("配位与杂化方式"))
        row_hyb.addStretch()
        self.atom_hyb_label = QLabel("—")
        self.atom_hyb_label.setProperty("role", "value")
        row_hyb.addWidget(self.atom_hyb_label)
        l.addLayout(row_hyb)

        self.atom_neighbors_label = QLabel("相连成键邻居: —")
        self.atom_neighbors_label.setWordWrap(True)
        self.atom_neighbors_label.setStyleSheet("color:#7DAEFA; font-size:11px; padding:2px 0;")
        l.addWidget(self.atom_neighbors_label)

        self.atom_vdw_label = QLabel("vdW 半径 / 质量: —")
        self.atom_vdw_label.setStyleSheet("color:#9AB0C2; font-size:11px;")
        l.addWidget(self.atom_vdw_label)

        self.atom_partial_charge_label = QLabel("量化部分电荷: 暂未计算 (可由 REST 产出)")
        self.atom_partial_charge_label.setStyleSheet("color:#66DEC9; font-size:11px; font-weight:600;")
        l.addWidget(self.atom_partial_charge_label)

        row_xyz_lbl = QHBoxLayout()
        row_xyz_lbl.addWidget(muted("空间几何绝对坐标 (Å):"))
        l.addLayout(row_xyz_lbl)

        row_xyz = QHBoxLayout()
        row_xyz.setSpacing(4)
        self.atom_x_spin = QDoubleSpinBox()
        self.atom_y_spin = QDoubleSpinBox()
        self.atom_z_spin = QDoubleSpinBox()
        for prefix, sp in (("X:", self.atom_x_spin), ("Y:", self.atom_y_spin), ("Z:", self.atom_z_spin)):
            sp.setPrefix(prefix)
            sp.setRange(-999.0, 999.0)
            sp.setDecimals(3)
            sp.setSingleStep(0.05)
            install_wheel_guard(sp, self._wheel_guard)
            sp.editingFinished.connect(self._on_atom_xyz_changed)
            row_xyz.addWidget(sp, 1)
        l.addLayout(row_xyz)

        self.atom_editor_card_widget = card
        return card

    def _bond_editor_card(self):
        from PyQt6.QtWidgets import QSlider, QComboBox
        card = CollapsibleCard("选中化学键属性 (BOND INSPECTOR)", expanded=True)
        l = card.body_layout

        self.bond_info_label = QLabel("未选中化学键（点击 2D/3D 键即可选中）")
        self.bond_info_label.setWordWrap(True)
        self.bond_info_label.setStyleSheet("color:#9AB0C2; font-weight:600;")
        l.addWidget(self.bond_info_label)

        row_bo = QHBoxLayout()
        row_bo.addWidget(muted("键级类型"))
        self.bond_order_combo = QComboBox()
        for order, label in ((1, "单键 (Single)"), (2, "双键 (Double)"), (3, "三键 (Triple)"), (4, "芳香键 (Aromatic)")):
            self.bond_order_combo.addItem(label, order)
        install_wheel_guard(self.bond_order_combo, self._wheel_guard)
        self.bond_order_combo.currentIndexChanged.connect(self._on_bond_order_changed)
        row_bo.addWidget(self.bond_order_combo, 1)
        l.addLayout(row_bo)

        row_bw_hdr = QHBoxLayout()
        row_bw_hdr.addWidget(muted("选中键粗细（只调选中键）"))
        row_bw_hdr.addStretch()
        self.bond_width_val_lbl = QLabel("100%")
        self.bond_width_val_lbl.setProperty("role", "value")
        row_bw_hdr.addWidget(self.bond_width_val_lbl)
        l.addLayout(row_bw_hdr)

        self.bond_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.bond_width_slider.setRange(40, 220)
        self.bond_width_slider.setValue(100)
        install_wheel_guard(self.bond_width_slider, self._wheel_guard)
        self.bond_width_slider.valueChanged.connect(self._on_selected_bond_width_changed)
        l.addWidget(self.bond_width_slider)
        l.addWidget(muted("↑ 仅缩放当前选中化学键粗细（全局粗细在[设置]页）"))

        row_bl = QHBoxLayout()
        row_bl.addWidget(muted("精确键长 (Å)"))
        self.bond_length_spin = QDoubleSpinBox()
        self.bond_length_spin.setRange(0.45, 4.50)
        self.bond_length_spin.setDecimals(3)
        self.bond_length_spin.setSingleStep(0.02)
        self.bond_length_spin.setValue(1.45)
        self.bond_length_spin.setToolTip("选中键后显示真实键长；改数值或点[应用]即沿键方向移动基团并支持 Ctrl+Z 撤销")
        install_wheel_guard(self.bond_length_spin, self._wheel_guard)
        self.bond_length_spin.editingFinished.connect(self._on_bond_length_changed)
        row_bl.addWidget(self.bond_length_spin, 1)
        apply_bl_btn = QPushButton("应用")
        apply_bl_btn.setMinimumWidth(48)
        apply_bl_btn.clicked.connect(self._on_bond_length_changed)
        row_bl.addWidget(apply_bl_btn)
        l.addLayout(row_bl)

        self.bond_angle_dih_label = QLabel("相邻键角 / 二面角：选中化学键后自动计算")
        self.bond_angle_dih_label.setWordWrap(True)
        self.bond_angle_dih_label.setStyleSheet("color:#7DAEFA; font-size:12px; font-weight:600;")
        l.addWidget(self.bond_angle_dih_label)

        self.bond_ring_label = QLabel("环系归属: —")
        self.bond_ring_label.setStyleSheet("color:#9AB0C2; font-size:11px;")
        l.addWidget(self.bond_ring_label)

        # 精确修改键角/二面角按钮
        row_ang = QHBoxLayout()
        mod_ang_btn = QPushButton("📐 精确修改键角...")
        mod_ang_btn.setToolTip("选中 3 个相邻原子后，精确修改中间键角（°）")
        mod_ang_btn.clicked.connect(self._on_modify_angle)
        row_ang.addWidget(mod_ang_btn)
        mod_dih_btn = QPushButton("🔄 精确修改二面角...")
        mod_dih_btn.setToolTip("选中 4 个相邻原子后，精确修改二面角扭转角（°）")
        mod_dih_btn.clicked.connect(self._on_modify_dihedral)
        row_ang.addWidget(mod_dih_btn)
        l.addLayout(row_ang)

        row_bc = QHBoxLayout()
        row_bc.addWidget(muted("键色定制"))
        row_bc.addStretch()
        bond_color_btn = QPushButton("自定义键色...")
        bond_color_btn.clicked.connect(self._on_pick_bond_color)
        row_bc.addWidget(bond_color_btn)
        l.addLayout(row_bc)
        return card

    def _on_bond_length_changed(self):
        if hasattr(self, "on_bond_length") and self.on_bond_length:
            self.on_bond_length(float(self.bond_length_spin.value()))

    def _on_bond_order_changed(self, idx):
        if hasattr(self, "on_bond_order") and self.on_bond_order:
            self.on_bond_order(self.bond_order_combo.itemData(idx))

    def _on_bond_width_changed(self, v: int):
        self.bond_width_val_lbl.setText(f"{v}%")
        if hasattr(self, "on_bond_width") and self.on_bond_width:
            self.on_bond_width(v / 100.0)

    def _on_modify_angle(self):
        """弹出精确修改键角对话框（支持显式回调与 _window_ref 双路径）。"""
        if hasattr(self, "on_modify_angle") and callable(self.on_modify_angle):
            self.on_modify_angle()
            return
        from .views import ModifyInternalCoordDialog
        win = getattr(self, "_window_ref", None) or self.window()
        if win is not None:
            ModifyInternalCoordDialog(win, "angle").exec()

    def _on_modify_dihedral(self):
        """弹出精确修改二面角对话框（支持显式回调与 _window_ref 双路径）。"""
        if hasattr(self, "on_modify_dihedral") and callable(self.on_modify_dihedral):
            self.on_modify_dihedral()
            return
        from .views import ModifyInternalCoordDialog
        win = getattr(self, "_window_ref", None) or self.window()
        if win is not None:
            ModifyInternalCoordDialog(win, "dihedral").exec()

    def _on_selected_bond_width_changed(self, v: int):
        self.bond_width_val_lbl.setText(f"{v}%")
        if hasattr(self, "on_selected_bond_width") and self.on_selected_bond_width:
            self.on_selected_bond_width(v / 100.0)

    def _on_pick_bond_color(self):
        if hasattr(self, "on_pick_bond_color") and self.on_pick_bond_color:
            self.on_pick_bond_color()

    def update_selected_bond(self, bond):
        if bond is None:
            self.bond_info_label.setText("未选中化学键（点击 2D/3D 键即可选中）")
            return
        names = {1: "单键", 2: "双键", 3: "三键", 4: "芳香键"}
        self.bond_info_label.setText(
            f"✓ 已选中键 #{bond.id.value + 1} (#{bond.begin.value + 1}–#{bond.end.value + 1}) · {names.get(bond.order, str(bond.order))}"
        )
        self.bond_order_combo.blockSignals(True)
        for i in range(self.bond_order_combo.count()):
            if self.bond_order_combo.itemData(i) == bond.order:
                self.bond_order_combo.setCurrentIndex(i)
        self.bond_order_combo.blockSignals(False)
        w_pct = int(round(float(getattr(bond, "width_scale", 1.0)) * 100))
        self.bond_width_slider.blockSignals(True)
        self.bond_width_slider.setValue(max(40, min(220, w_pct)))
        self.bond_width_val_lbl.setText(f"{w_pct}%")
        self.bond_width_slider.blockSignals(False)
        # 填入当前真实键长（从 3D 坐标算）
        try:
            doc = self._document_provider() if self._document_provider else None
            if doc is not None and getattr(doc, "has_3d", False) and doc.coordinates.current is not None:
                _, id2idx = doc.topology.atom_index_map()
                coords = doc.coordinates.current.coords
                a, b = bond.begin, bond.end
                if a in id2idx and b in id2idx:
                    import numpy as np
                    from ..application import measurement as mm
                    ia, ib = id2idx[a], id2idx[b]
                    d = float(np.linalg.norm(coords[ib] - coords[ia]))
                    self.bond_length_spin.blockSignals(True)
                    self.bond_length_spin.setValue(round(d, 3))
                    self.bond_length_spin.blockSignals(False)
                    # 计算相邻键角与二面角
                    nbrs_a = [n for n in doc.topology.neighbors_of(a) if n != b and n in id2idx]
                    nbrs_b = [n for n in doc.topology.neighbors_of(b) if n != a and n in id2idx]
                    extra_parts = [f"键长: {d:.3f} Å"]
                    if nbrs_a:
                        ang_v, ok_a, _ = mm.angle(coords, id2idx[nbrs_a[0]], ia, ib)
                        if ok_a:
                            extra_parts.append(f"邻角: {ang_v:.1f}°")
                    from ..application.measurement_targets import MeasurementTargetResolver
                    canon_dih = MeasurementTargetResolver.find_canonical_dihedral_for_bond(doc, bond.id)
                    if canon_dih:
                        i, j, k, l = canon_dih
                        if i in id2idx and j in id2idx and k in id2idx and l in id2idx:
                            dih_v, ok_d, _ = mm.dihedral(coords, id2idx[i], id2idx[j], id2idx[k], id2idx[l])
                            if ok_d:
                                extra_parts.append(f"主二面角(#{i.value+1}-#{j.value+1}-#{k.value+1}-#{l.value+1}): {dih_v:.1f}°")
                    elif nbrs_a and nbrs_b:
                        dih_v, ok_d, _ = mm.dihedral(coords, id2idx[nbrs_a[0]], ia, ib, id2idx[nbrs_b[0]])
                        if ok_d:
                            extra_parts.append(f"二面角: {dih_v:.1f}°")
                    self.bond_angle_dih_label.setText("  ·  ".join(extra_parts))
                    is_ring = doc.topology.is_bond_in_ring(bond.id) if hasattr(doc.topology, "is_bond_in_ring") else False
                    self.bond_ring_label.setText(f"环系归属：{'环内化学键 (In Ring)' if is_ring else '链状可旋转单键 (Chain / Rotatable)'}")
        except Exception:
            pass

    def _on_atom_xyz_changed(self):
        if hasattr(self, "on_atom_xyz_edited") and self.on_atom_xyz_edited:
            self.on_atom_xyz_edited(
                float(self.atom_x_spin.value()),
                float(self.atom_y_spin.value()),
                float(self.atom_z_spin.value()),
            )

    def _change_selected_atom_element(self):
        if hasattr(self, "on_change_element") and self.on_change_element:
            self.on_change_element()

    def _on_atom_scale_changed(self, v: int):
        self.atom_scale_val_lbl.setText(f"{v}%")
        if hasattr(self, "on_atom_scale") and self.on_atom_scale:
            self.on_atom_scale(v / 100.0)

    def _on_selected_atom_scale_changed(self, v: int):
        self.atom_scale_val_lbl.setText(f"{v}%")
        if hasattr(self, "on_selected_atom_scale") and self.on_selected_atom_scale:
            self.on_selected_atom_scale(v / 100.0)

    def _on_charge_changed(self, idx):
        if hasattr(self, "on_charge") and self.on_charge:
            self.on_charge(self.atom_charge_combo.itemData(idx))

    def _on_pick_atom_color(self):
        if hasattr(self, "on_pick_color") and self.on_pick_color:
            self.on_pick_color()

    def _save_selected_fragment_to_library(self):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "sidebar"):
            win.sidebar._on_save_selected_as_fragment()

    def _clear_selection(self):
        win = getattr(self, "_window_ref", None)
        if win and hasattr(win, "selection") and win.selection:
            win.selection.clear()

    def update_selected_atoms_summary(self, atom_ids: list, doc=None):
        if not hasattr(self, "multi_atom_card"):
            return
        if not atom_ids or len(atom_ids) <= 1:
            self.multi_atom_card.setVisible(False)
            return
        self.multi_atom_card.setVisible(True)
        sorted_ids = sorted(atom_ids, key=lambda a: a.value if hasattr(a, "value") else int(a))
        id_numbers = [a.value + 1 if hasattr(a, "value") else int(a) + 1 for a in sorted_ids]
        id_str = ", ".join(f"#{i}" for i in id_numbers[:12])
        if len(id_numbers) > 12:
            id_str += f" ... 等共 {len(id_numbers)} 个原子"
        self.multi_atom_ids_label.setText(f"✓ 已选中 {len(id_numbers)} 个原子序号：\n{id_str}")
        self.atom_info_label.setText(f"✓ 当前多选：{len(id_numbers)} 个原子（可一键存为砌块或拖拽平移）")
        if doc and doc.has_3d and doc.coordinates.current is not None:
            coords = [doc.coordinates.current.coords[a.value] for a in sorted_ids if a.value < len(doc.coordinates.current.coords)]
            if coords:
                mean_pos = np.mean(coords, axis=0)
                self.multi_atom_pos_label.setText(f"选中片段质心: ({mean_pos[0]:.3f}, {mean_pos[1]:.3f}, {mean_pos[2]:.3f}) Å")

    def update_selected_atom(
        self,
        elem,
        charge=0,
        atom_scale: float = 1.0,
        atom_id=None,
        xyz: tuple[float, float, float] | None = None,
        hybridization: str = "—",
        frozen: bool = False,
    ):
        if elem is None:
            self.atom_info_label.setText("未选中原子（点击 2D/3D 原子即可选中）")
            self.atom_element_label.setText("—")
            self.atom_hyb_label.setText("—")
            return
        w_val = getattr(elem, "atomic_weight", getattr(elem, "atomic_mass", 12.011))
        id_str = f"#{atom_id.value+1} " if hasattr(atom_id, "value") else ""
        self.atom_info_label.setText(f"✓ 已选中原子 {id_str}：{elem.name_cn} · {elem.symbol} ({w_val:.3f} u)")
        self.atom_element_label.setText(f"{elem.symbol} (Z={elem.atomic_number})" + (" · 坐标已冻结" if frozen else ""))
        self.atom_hyb_label.setText(hybridization)
        vdw_r = getattr(elem, "vdw_radius", getattr(elem, "radius_vdw", 1.70))
        self.atom_vdw_label.setText(f"vdW 半径: {vdw_r:.2f} Å  ·  原子量: {w_val:.3f} u")
        nbr_strs = []
        if atom_id is not None and self._document_provider:
            doc = self._document_provider()
            if doc:
                atom = doc.topology.get_atom(atom_id)
                m_ch = atom.properties.get("mulliken_charge", None)
                if m_ch is not None:
                    self.atom_partial_charge_label.setText(f"Mulliken 电荷: {float(m_ch):+.4f} e")
                else:
                    self.atom_partial_charge_label.setText("量化部分电荷: 暂未计算 (可由 REST 产出)")
                for nbr_id in doc.topology.neighbors_of(atom_id):
                    nbr_atom = doc.topology.get_atom(nbr_id)
                    nbr_strs.append(f"{nbr_atom.symbol}#{nbr_id.value+1}")
        self.atom_neighbors_label.setText("相连成键邻居: " + (", ".join(nbr_strs) if nbr_strs else "孤立原子"))
        if xyz is not None:
            for sp, val in ((self.atom_x_spin, xyz[0]), (self.atom_y_spin, xyz[1]), (self.atom_z_spin, xyz[2])):
                sp.blockSignals(True)
                sp.setValue(round(float(val), 3))
                sp.blockSignals(False)
        self.atom_charge_combo.blockSignals(True)
        for i in range(self.atom_charge_combo.count()):
            if self.atom_charge_combo.itemData(i) == charge:
                self.atom_charge_combo.setCurrentIndex(i)
        self.atom_charge_combo.blockSignals(False)
        sc_pct = int(round(float(atom_scale) * 100))
        self.atom_scale_slider.blockSignals(True)
        self.atom_scale_slider.setValue(max(40, min(300, sc_pct)))
        self.atom_scale_val_lbl.setText(f"{sc_pct}%")
        self.atom_scale_slider.blockSignals(False)

    def update_molecule_info(self, name: str, formula: str, num_atoms: int, num_bonds: int,
                             molecular_weight: float = 0.0, heavy_atoms: int = 0, hydrogens: int = 0,
                             charge: int = 0, spin_mult: int = 1, spin_label: str = "Singlet",
                             rings_count: int = 0, rotatable_bonds: int = 0,
                             centroid_str: str = "(0.00, 0.00, 0.00)", point_group: str = "C1", **kwargs):
        self.mol_name_label.setText(f"{name} · {formula}")
        if "化学式" in self.inspect_labels:
            self.inspect_labels["化学式"].setText(formula)
        if "相对分子质量" in self.inspect_labels:
            self.inspect_labels["相对分子质量"].setText(f"{molecular_weight:.2f} Da")
        if "原子 (重/氢)" in self.inspect_labels:
            self.inspect_labels["原子 (重/氢)"].setText(f"{num_atoms} ({heavy_atoms} 重 / {hydrogens} 氢)")
        if "化学键 (单/双/芳)" in self.inspect_labels:
            self.inspect_labels["化学键 (单/双/芳)"].setText(f"{num_bonds} 键")
        if "净电荷 / 自旋" in self.inspect_labels:
            self.inspect_labels["净电荷 / 自旋"].setText(f"{charge:+d} / {spin_label} (M={spin_mult})")
        if "环系数量" in self.inspect_labels:
            self.inspect_labels["环系数量"].setText(f"{rings_count} 环")
        if "可旋转单键" in self.inspect_labels:
            self.inspect_labels["可旋转单键"].setText(f"{rotatable_bonds} 个")
        if "空间质心 (Å)" in self.inspect_labels:
            self.inspect_labels["空间质心 (Å)"].setText(centroid_str)
        if "空间点群对称性" in self.inspect_labels:
            self.inspect_labels["空间点群对称性"].setText(point_group)

    # ---------- DeepSeek AI 助手页 ----------

    def _assistant(self):
        page, box = self._page()

        self.assistant_context_label = QLabel("尚未加载分子")
        self.assistant_context_label.setWordWrap(True)
        self.assistant_context_label.setStyleSheet(
            "color:#EAF2F6; background:#132436; border:1px solid #243E56;"
            "border-radius:7px; padding:8px 10px; font-size:12px;"
        )
        box.addWidget(self.assistant_context_label)

        cfg_card = CollapsibleCard("AI 助手与大模型配置 (LLM / MCP CONFIG)", expanded=True)
        cfg_lay = cfg_card.body_layout

        from ..ai.mcp_bridge import get_llm_config, set_llm_config
        cfg = get_llm_config()

        # 平台预设
        row_prov = QHBoxLayout()
        row_prov.addWidget(muted("服务商:"))
        self.provider_combo = QComboBox()
        self.providers_data = {
            "DeepSeek (官方)": {
                "url": "https://api.deepseek.com/v1",
                "models": ["deepseek-chat", "deepseek-reasoner"],
            },
            "OpenAI / ChatGPT": {
                "url": "https://api.openai.com/v1",
                "models": ["gpt-4o", "gpt-4o-mini", "o1", "gpt-4.5-preview"],
            },
            "通义千问 (Qwen / 阿里百炼)": {
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
            },
            "月之暗面 (Kimi / Moonshot)": {
                "url": "https://api.moonshot.cn/v1",
                "models": ["moonshot-v1-8k", "moonshot-v1-32k"],
            },
            "智谱清言 (GLM-4 / Zhipu)": {
                "url": "https://open.bigmodel.cn/api/paas/v4",
                "models": ["glm-4-plus", "glm-4-flash"],
            },
            "Ollama 本地大模型": {
                "url": "http://localhost:11434/v1",
                "models": ["deepseek-r1:14b", "qwen2.5:14b", "llama3.3"],
            },
            "Antigravity MCP / 本地端点": {
                "url": "http://127.0.0.1:8000/v1",
                "models": ["default-model"],
            },
            "自定义端点 (Custom URL)": {
                "url": "http://127.0.0.1:8000/v1",
                "models": ["default-model"],
            },
        }
        for p_name in self.providers_data:
            self.provider_combo.addItem(p_name)
        install_wheel_guard(self.provider_combo, self._wheel_guard)
        row_prov.addWidget(self.provider_combo, 1)
        cfg_lay.addLayout(row_prov)

        # Base URL
        row_url = QHBoxLayout()
        row_url.addWidget(muted("Base URL:"))
        self.ds_url_input = QLineEdit()
        self.ds_url_input.setText(cfg["base_url"])
        self.ds_url_input.editingFinished.connect(self._on_ds_config_changed)
        row_url.addWidget(self.ds_url_input, 1)
        cfg_lay.addLayout(row_url)

        # Model Name (高可靠 QLineEdit 直接绑定，消除下拉框重置冲突)
        row_m = QHBoxLayout()
        row_m.addWidget(muted("模型名:"))
        self.ds_model_input = QLineEdit()
        self.ds_model_input.setText(cfg["model"])
        self.ds_model_input.setPlaceholderText("如 antigravity / gemini-3.8-flash-low / deepseek-chat")
        self.ds_model_input.editingFinished.connect(self._on_ds_config_changed)
        row_m.addWidget(self.ds_model_input, 1)
        cfg_lay.addLayout(row_m)

        # Match provider with cfg["base_url"]
        matched_provider = None
        for p_name, p_info in self.providers_data.items():
            if p_info["url"].rstrip("/") == cfg["base_url"].rstrip("/"):
                matched_provider = p_name
                break
        if matched_provider is None:
            matched_provider = "自定义端点 (Custom URL)"

        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentText(matched_provider)
        self.provider_combo.blockSignals(False)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        # 初始装载模型名
        self.ds_model_input.setText(cfg["model"])

        # API Key
        self.ds_key_input = QLineEdit()
        self.ds_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ds_key_input.setPlaceholderText("填入 API Key (如 sk-...)，留空自动使用内置化学规则引擎")
        if cfg["api_key"] and cfg["api_key"] != "EMPTY":
            self.ds_key_input.setText(cfg["api_key"])
        else:
            self.ds_key_input.setText("")
        self.ds_key_input.editingFinished.connect(self._on_ds_config_changed)
        cfg_lay.addWidget(self.ds_key_input)

        row_save = QHBoxLayout()
        self.save_cfg_btn = QPushButton("💾 保存配置")
        self.save_cfg_btn.setStyleSheet("font-weight:700; padding:4px 14px;")
        self.save_cfg_btn.clicked.connect(self._save_and_confirm_config)
        row_save.addWidget(self.save_cfg_btn)

        self.save_feedback_lbl = QLabel("")
        self.save_feedback_lbl.setStyleSheet("color:#66DEC9; font-size:12px; font-weight:700;")
        row_save.addWidget(self.save_feedback_lbl, 1)
        cfg_lay.addLayout(row_save)

        lbl_sync = QLabel("✓ 此处配置已全局持久化，独立对话窗口与 MCP 工具链自动实时继承。")
        lbl_sync.setStyleSheet("color: #5EEAD4; font-size: 11px; padding: 2px 0;")
        cfg_lay.addWidget(lbl_sync)

        box.addWidget(cfg_card)

        tools_card = CollapsibleCard("一键量化与结构分析 (QUICK TOOLS)", expanded=True)
        t_lay = tools_card.body_layout
        for txt, callback in (
            ("🔍 检查当前分子官能团 (RDKit SMARTS)", self._check_functional_groups),
            ("🧬 生成 3D 多构象系综 (ETKDGv3 + MMFF94)", self._generate_conformer),
            ("⚛ 打开 Gaussian / 复旦 REST / 能级图工作台", self._prepare_dft),
        ):
            b = QPushButton(txt)
            b.clicked.connect(callback)
            t_lay.addWidget(b)
        box.addWidget(tools_card)

        chat_card = CollapsibleCard("AI 科研助手对话 (AI SCIENTIST / MCP)", expanded=True)
        c_lay = chat_card.body_layout

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setMinimumHeight(210)
        self.chat_history.setHtml(
            "<div style='color:#9AB0C2; font-size:12px; line-height:1.45;'>"
            "<b style='color:#66DEC9'>MolForge AI Scientist 已就绪 (已支持 OpenAI / DeepSeek / 通义 / Ollama / MCP)。</b><br>"
            "无论是否填入在线 Key，均可直接输入自然语言执行操作：<br>"
            "• <span style='color:#7DAEFA'>“帮我生成复旦 REST 的 XYG3 输入卡”</span><br>"
            "• <span style='color:#7DAEFA'>“生成 Gaussian CAM-B3LYP TD-DFT 输入”</span><br>"
            "• <span style='color:#7DAEFA'>“加一个噻吩环”</span> / <span style='color:#7DAEFA'>“引入氰基 -CN”</span>"
            "</div>"
        )
        c_lay.addWidget(self.chat_history)

        input_row = QHBoxLayout()
        self.ai_prompt_input = QLineEdit()
        self.ai_prompt_input.setPlaceholderText("输入问题或建模/计算指令回车发送...")
        self.ai_prompt_input.returnPressed.connect(self._on_ask_question)
        input_row.addWidget(self.ai_prompt_input, 1)

        self.ai_prompt_send_btn = QPushButton("发送")
        self.ai_prompt_send_btn.setProperty("role", "action")
        self.ai_prompt_send_btn.clicked.connect(self._on_ask_question)
        input_row.addWidget(self.ai_prompt_send_btn)

        standalone_btn = QPushButton("🗗 独立弹窗")
        standalone_btn.setToolTip("在独立弹出窗口中打开全功能 LLM / MCP 工具对话")
        standalone_btn.clicked.connect(self._open_standalone_dialog)
        input_row.addWidget(standalone_btn)

        c_lay.addLayout(input_row)
        box.addWidget(chat_card)

        box.addStretch(1)
        return page

    def _on_provider_changed(self, idx: int):
        p_name = self.provider_combo.currentText()
        data = self.providers_data.get(p_name)
        if data:
            self.ds_url_input.setText(data["url"])
            if hasattr(self, "ds_model_input") and data.get("models"):
                if p_name != "自定义端点 (Custom URL)":
                    self.ds_model_input.setText(data["models"][0])
            self._on_ds_config_changed()

    def _on_ds_config_changed(self):
        key = self.ds_key_input.text().strip()
        model = self.ds_model_input.text().strip() if hasattr(self, "ds_model_input") else "default-model"
        url = self.ds_url_input.text().strip() or "http://127.0.0.1:8000/v1"
        self.deepseek.api_key = key
        self.deepseek.model = model
        self.deepseek.base_url = url
        from ..ai.mcp_bridge import set_llm_config
        set_llm_config(url, key or "EMPTY", model)
        if self._chat_bridge is not None:
            self._chat_bridge.config = {"base_url": url, "api_key": key or "EMPTY", "model": model}

    def _save_and_confirm_config(self):
        url = self.ds_url_input.text().strip() or "http://127.0.0.1:8000/v1"
        model = self.ds_model_input.text().strip() if hasattr(self, "ds_model_input") else "default-model"
        key = self.ds_key_input.text().strip() or "EMPTY"
        from ..ai.mcp_bridge import set_llm_config
        set_llm_config(url, key, model)
        if self._chat_bridge is not None:
            self._chat_bridge.config = {"base_url": url, "api_key": key, "model": model}
        if hasattr(self, "save_feedback_lbl"):
            self.save_feedback_lbl.setText(f"✓ 已保存: {model}")
            QTimer.singleShot(3000, lambda: self.save_feedback_lbl.setText(""))

    def _sync_ai_config_from_global(self):
        from ..ai.mcp_bridge import get_llm_config
        cfg = get_llm_config()
        cur_url = cfg["base_url"]
        matched_provider = None
        for p_name, p_info in self.providers_data.items():
            if p_info["url"].rstrip("/") == cur_url.rstrip("/"):
                matched_provider = p_name
                break
        if matched_provider is None:
            matched_provider = "自定义端点 (Custom URL)"
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentText(matched_provider)
        self.provider_combo.blockSignals(False)

        self.ds_url_input.setText(cur_url)
        if hasattr(self, "ds_model_input"):
            self.ds_model_input.setText(cfg["model"])

        if cfg["api_key"] and cfg["api_key"] != "EMPTY":
            self.ds_key_input.setText(cfg["api_key"])
        else:
            self.ds_key_input.setText("")

    def _open_standalone_dialog(self):
        from .live_llm_dialog import LiveLlmDialog
        owner = self.window()
        dialog = LiveLlmDialog(owner, self._document_provider)
        dialog.exec()
        self._sync_ai_config_from_global()

    def update_molecule_context(self, name: str, formula: str, num_atoms: int, num_bonds: int,
                                molecular_weight: float = 0.0):
        if not hasattr(self, "assistant_context_label"):
            return
        mw_txt = f" · {molecular_weight:.2f} Da" if molecular_weight > 0 else ""
        self.assistant_context_label.setText(
            f"当前分子上下文：{name}  •  {formula}\n{num_atoms} 原子 · {num_bonds} 键{mw_txt}"
        )

    def set_document_provider(self, provider):
        self._document_provider = provider

    def set_command_bus_provider(self, provider):
        self._command_bus_provider = provider

    def set_selection_provider(self, provider):
        self._selection_provider = provider

    def _check_functional_groups(self):
        if self._document_provider is None:
            return
        doc = self._document_provider()
        found = []
        try:
            from ..io.rdkit_adapter import doc_to_rdkit
            from rdkit import Chem
            rdmol, _, _ = doc_to_rdkit(doc, sanitize=True)
            patterns = [
                ("噻吩环 (Thiophene)", Chem.MolFromSmarts("c1ccsc1")),
                ("苯环/芳香六元环", Chem.MolFromSmarts("c1ccccc1")),
                ("氰基 (-C≡N)", Chem.MolFromSmarts("[CX2]#[NX1]")),
                ("氟代 (-F)", Chem.MolFromSmarts("[#6][F]")),
                ("氯代 (-Cl)", Chem.MolFromSmarts("[#6][Cl]")),
                ("羰基 (C=O)", Chem.MolFromSmarts("[CX3]=[OX1]")),
                ("羧基 (-COOH)", Chem.MolFromSmarts("[CX3](=O)[OX2H1]")),
                ("酯基 (-COO-)", Chem.MolFromSmarts("[CX3](=O)[OX2][#6]")),
                ("羟基 (-OH)", Chem.MolFromSmarts("[OX2H1]")),
                ("酰胺 (-CON-)", Chem.MolFromSmarts("[NX3][CX3](=[OX1])")),
                ("氨基 (-NH₂)", Chem.MolFromSmarts("[NX3H2]")),
                ("甲基 (-CH₃)", Chem.MolFromSmarts("[CH3]")),
            ]
            for name, patt in patterns:
                if patt is not None:
                    hits = len(rdmol.GetSubstructMatches(patt))
                    if hits > 0:
                        found.append(f"• {name}: {hits} 处")
        except Exception as e:
            found.append(f"• 拓扑统计: {doc.num_atoms} 原子, {doc.num_bonds} 键 ({e})")
        if not found:
            found = ["• 未匹配到预设特征官能团"]
        msg = f"分子：{doc.name}\n" + "\n".join(found)
        self.switch_tab(1)
        self.chat_history.append(f"<hr><b style='color:#66DEC9'>[官能团分析]</b><br><pre>{msg}</pre>")

    def _generate_conformer(self):
        if getattr(self, "on_generate_conformers", None):
            self.on_generate_conformers()

    def _prepare_dft(self):
        if getattr(self, "on_open_qc_log", None):
            self.on_open_qc_log()

    def _on_ask_question(self):
        text = self.ai_prompt_input.text().strip()
        if not text:
            return
        if self._chat_worker and self._chat_worker.isRunning():
            QMessageBox.information(self, "请求处理中", "当前已有 AI 请求正在运行，请等待回复完成。")
            return
        if self._document_provider is None:
            self.chat_history.append("<div style='color:#E06C75;'>⚠️ 未检测到分子文档。</div>")
            return
        doc = self._document_provider()
        if doc is None:
            self.chat_history.append("<div style='color:#E06C75;'>⚠️ 当前没有打开的分子文档，请先在画布中打开或创建分子。</div>")
            return
        bus = self._command_bus_provider() if self._command_bus_provider else getattr(self.window(), 'command_bus', None)
        if bus is None or bus.document is not doc:
            self.chat_history.append("<div style='color:#E06C75;'>⚠️ 当前窗口命令总线与文档不一致，无法执行操作。</div>")
            return

        url = self.ds_url_input.text().strip() or "http://127.0.0.1:8000/v1"
        model = self.ds_model_input.text().strip() if hasattr(self, "ds_model_input") else "default-model"
        key = self.ds_key_input.text().strip() or "EMPTY"
        from ..ai.mcp_bridge import MolForgeMCPBridge, set_llm_config
        set_llm_config(url, key, model)

        if self._chat_bridge is None or self._chat_bridge.document is not doc:
            self._chat_bridge = MolForgeMCPBridge(doc, bus)
        self._chat_bridge.config = {"base_url": url, "api_key": key, "model": model}

        self.ai_prompt_input.clear()
        self.chat_history.append(
            f"<div style='margin-top:8px; margin-bottom:4px;'>"
            f"<b style='color:#7DAEFA;'>🧑 你：</b> {html.escape(text)}"
            f"</div>"
        )
        self.chat_history.append(
            "<div style='color:#66DEC9; font-size:12px; margin-bottom:6px;'>"
            "⏳ 正在连接 AI 端点并分析分子结构...</div>"
        )
        self.ai_prompt_send_btn.setEnabled(False)
        self.ai_prompt_send_btn.setText("思考中...")

        from .live_llm_dialog import _ChatWorker
        self._chat_worker = _ChatWorker(self._chat_bridge, text, self)
        self._chat_worker.tool_requested.connect(self._on_panel_tool_requested)
        self._chat_worker.reply.connect(self._on_panel_chat_reply)
        self._chat_worker.finished.connect(self._on_panel_chat_finished)
        self._chat_worker.start()

    def _on_panel_tool_requested(self, name, args, packet):
        try:
            if name in {'add_atom', 'delete_atom', 'add_bond'}:
                allowed = QMessageBox.question(
                    self,
                    "确认分子修改",
                    f"模型请求执行工具：{name}\n参数：{args}\n\n是否应用到当前分子画布？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if allowed != QMessageBox.StandardButton.Yes:
                    packet['result'] = {'ok': False, 'error': '用户取消了本次结构修改'}
                    self.chat_history.append(
                        f"<div style='color:#E06C75; font-size:11px;'>❌ <b>工具 {html.escape(name)}</b>：用户取消执行</div>"
                    )
                    return
            packet['result'] = self._chat_bridge.dispatch(name, args)
            self.chat_history.append(
                f"<div style='color:#E5C07B; font-size:11px;'>🔧 <b>执行工具 {html.escape(name)}</b>：{html.escape(str(packet['result'])[:140])}</div>"
            )
        except Exception as exc:
            packet['result'] = {'ok': False, 'error': str(exc)}
            self.chat_history.append(
                f"<div style='color:#E06C75; font-size:11px;'>⚠️ <b>工具错误</b>：{html.escape(str(exc))}</div>"
            )
        finally:
            packet['event'].set()

    def _on_panel_chat_reply(self, reply_text):
        formatted = html.escape(reply_text).replace('\n', '<br>')
        self.chat_history.append(
            f"<div style='margin-top:6px; margin-bottom:8px; line-height:1.45;'>"
            f"<b style='color:#66DEC9;'>🤖 MolForge AI：</b><br>{formatted}"
            f"</div>"
        )
        QTimer.singleShot(60, self._scroll_chat_to_bottom)

    def _scroll_chat_to_bottom(self):
        sb = self.chat_history.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _on_panel_chat_finished(self):
        if hasattr(self, 'ai_prompt_send_btn'):
            self.ai_prompt_send_btn.setEnabled(True)
            self.ai_prompt_send_btn.setText("发送")

    def _on_tab_changed(self, index):
        if index == 2:
            self._refresh_jobs()
        elif index == 3:
            self._refresh_history()

    def _clear_box(self, box):
        while box.count():
            item = box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _refresh_jobs(self):
        self._clear_box(self.jobs_box)
        box = self.jobs_box

        eng_card = CollapsibleCard("量化计算引擎状态 (ENGINES)", expanded=True)
        e_lay = eng_card.body_layout
        from ..application.calculators.registry import _all_engines
        for eng in _all_engines():
            ok = eng.probe()
            st = "本地可执行已就绪" if ok else "输入卡生成就绪"
            col = "#22C55E" if ok else "#66DEC9"
            lbl = QLabel(f"• <b>{eng.name}</b>: <span style='color:{col}'>{st}</span>")
            e_lay.addWidget(lbl)

        open_qc_btn = QPushButton("⚛ 打开 Gaussian / 复旦 REST / 能级图工作台...")
        open_qc_btn.setProperty("role", "action")
        open_qc_btn.clicked.connect(self._prepare_dft)
        e_lay.addWidget(open_qc_btn)
        box.addWidget(eng_card)

        cmd_card = CollapsibleCard("最近执行的建模与计算操作", expanded=True)
        c_lay = cmd_card.body_layout
        cmds = []
        if self._command_bus_provider is not None:
            cmds = self._command_bus_provider().history.executed_commands
        if not cmds:
            c_lay.addWidget(muted("暂无编辑命令记录。"))
        else:
            for cmd in cmds[-12:]:
                row = QHBoxLayout()
                row.addWidget(muted(f"• {cmd.description}"))
                row.addStretch()
                done = QLabel("已生效")
                done.setStyleSheet("color: #66DEC9; font-size: 11px;")
                row.addWidget(done)
                c_lay.addLayout(row)
        box.addWidget(cmd_card)
        box.addStretch(1)

    def _refresh_history(self):
        bus = self._command_bus_provider() if self._command_bus_provider else None
        can_undo = bool(bus and bus.history.can_undo)
        can_redo = bool(bus and bus.history.can_redo)
        undo_cmds = list(bus.history._undo_stack) if bus else []
        redo_cmds = list(reversed(bus.history._redo_stack)) if bus else []

        # 若历史面板控件已存在，原地平滑刷新列表内容，绝不销毁重构，防止事件循环重入假死！
        if hasattr(self, "btn_undo") and hasattr(self, "history_list"):
            self.btn_undo.setEnabled(can_undo)
            self.btn_redo.setEnabled(can_redo)
            self.history_list.blockSignals(True)
            self.history_list.clear()

            item0 = QListWidgetItem("🏁 0. 初始结构 (起点)")
            self.history_list.addItem(item0)
            for idx, cmd in enumerate(undo_cmds, 1):
                desc = getattr(cmd, "description", type(cmd).__name__)
                it = QListWidgetItem(f"✓ {idx}. {desc}")
                self.history_list.addItem(it)

            active_row = len(undo_cmds)
            self.history_list.setCurrentRow(active_row)
            cur_item = self.history_list.item(active_row)
            if cur_item:
                cur_item.setText(cur_item.text() + "  ◀ [当前状态]")
                cur_item.setForeground(QColor("#5EEAD4"))

            for idx, cmd in enumerate(redo_cmds, len(undo_cmds) + 1):
                desc = getattr(cmd, "description", type(cmd).__name__)
                it = QListWidgetItem(f"↷ {idx}. {desc}  (可重做)")
                it.setForeground(QColor("#688094"))
                self.history_list.addItem(it)

            self.history_list.blockSignals(False)
            if hasattr(self, "history_export_btn"):
                self.history_export_btn.setEnabled(bool(undo_cmds or (bus and bus.history.audit_events)))
            return

        self._clear_box(self.history_box)
        box = self.history_box
        h_card = CollapsibleCard("操作历史与时间线跳转 (HISTORY TIMELINE)", expanded=True)
        h_lay = h_card.body_layout

        row_act = QHBoxLayout()
        self.btn_undo = QPushButton("⏪ 撤销 (Ctrl+Z)")
        self.btn_undo.setEnabled(can_undo)
        self.btn_undo.setMinimumHeight(30)
        self.btn_undo.setStyleSheet("QPushButton { font-weight:700; font-size:12px; }")
        self.btn_undo.clicked.connect(self._history_do_undo)
        row_act.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("⏩ 重做 (Ctrl+Y)")
        self.btn_redo.setEnabled(can_redo)
        self.btn_redo.setMinimumHeight(30)
        self.btn_redo.setStyleSheet("QPushButton { font-weight:700; font-size:12px; }")
        self.btn_redo.clicked.connect(self._history_do_redo)
        row_act.addWidget(self.btn_redo)

        btn_clear = QPushButton("🗑️ 清空")
        btn_clear.setToolTip("清空当前撤销与重做历史栈")
        btn_clear.setMinimumHeight(30)
        btn_clear.clicked.connect(self._history_do_clear)
        row_act.addWidget(btn_clear)
        h_lay.addLayout(row_act)

        h_lay.addWidget(muted("点击下方任意历史记录，可直接时空跳转至该步分子构型："))

        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(240)
        self.history_list.setStyleSheet(
            "QListWidget { background:#0F1B29; border:1px solid #243B52; border-radius:6px; color:#EAF2F6; padding:4px; }"
            "QListWidget::item { padding:7px 10px; border-bottom:1px solid #17283B; border-radius:4px; }"
            "QListWidget::item:hover { background:#1C2E42; }"
            "QListWidget::item:selected { background:#0D9488; color:#FFFFFF; font-weight:bold; }"
        )

        item0 = QListWidgetItem("🏁 0. 初始结构 (起点)")
        self.history_list.addItem(item0)
        for idx, cmd in enumerate(undo_cmds, 1):
            desc = getattr(cmd, "description", type(cmd).__name__)
            it = QListWidgetItem(f"✓ {idx}. {desc}")
            self.history_list.addItem(it)

        active_row = len(undo_cmds)
        self.history_list.setCurrentRow(active_row)
        cur_item = self.history_list.item(active_row)
        if cur_item:
            cur_item.setText(cur_item.text() + "  ◀ [当前状态]")
            cur_item.setForeground(QColor("#5EEAD4"))

        for idx, cmd in enumerate(redo_cmds, len(undo_cmds) + 1):
            desc = getattr(cmd, "description", type(cmd).__name__)
            it = QListWidgetItem(f"↷ {idx}. {desc}  (可重做)")
            it.setForeground(QColor("#688094"))
            self.history_list.addItem(it)

        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        h_lay.addWidget(self.history_list)

        self.history_export_btn = QPushButton("📦 导出本次操作为技能 (Export Skill)...")
        self.history_export_btn.setEnabled(bool(undo_cmds or (bus and bus.history.audit_events)))
        self.history_export_btn.setMinimumHeight(32)
        self.history_export_btn.clicked.connect(self._export_history_skill)
        h_lay.addWidget(self.history_export_btn)

        h_lay.addWidget(muted("快捷键提示：Ctrl+Z 撤销，Ctrl+Y 重做。点击列表行可直接回退或前进。"))
        box.addWidget(h_card)
        box.addStretch(1)
        box.addStretch(1)

    def _history_do_undo(self):
        bus = self._command_bus_provider() if self._command_bus_provider else None
        if bus and bus.history.can_undo:
            bus.undo()
            self._refresh_history()

    def _history_do_redo(self):
        bus = self._command_bus_provider() if self._command_bus_provider else None
        if bus and bus.history.can_redo:
            bus.redo()
            self._refresh_history()

    def _history_do_clear(self):
        bus = self._command_bus_provider() if self._command_bus_provider else None
        if bus:
            bus.history.clear()
            self._refresh_history()

    def _on_history_item_clicked(self, item: QListWidgetItem):
        row = self.history_list.row(item)
        bus = self._command_bus_provider() if self._command_bus_provider else None
        if not bus:
            return
        current_active = len(bus.history._undo_stack)
        if row < current_active:
            # 需要 Undo 的步数
            steps = current_active - row
            for _ in range(steps):
                bus.undo()
            self._refresh_history()
        elif row > current_active:
            # 需要 Redo 的步数
            steps = row - current_active
            for _ in range(steps):
                bus.redo()
            self._refresh_history()

    def _export_history_skill(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from ..runtime import data_dir
        from ..io.history_skill import export_history_skill
        folder = QFileDialog.getExistingDirectory(self, "选择 D/E 盘技能保存目录", str(data_dir()))
        if not folder:
            return
        try:
            bus = self._command_bus_provider()
            result = export_history_skill(bus.document, bus.history.audit_events, Path(folder))
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "技能已导出", str(result / "SKILL.md"))
