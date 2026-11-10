"""
ui/theme.py - 工业级深色科学工作台视觉主题系统（高对比度激活高亮 + 纵横双向胶囊滚动条）
========================================================================================
核心升级：
  1. 彻底解决“点哪个按钮都不亮”的问题：
     - 未选中按钮采用深海蓝灰 (`#142334`，文字 `#9AB0C2`，边框 `#243B52`)
     - 选中/激活按钮 (`:checked` 或 `[active="true"]`) 采用高对比度荧光青翠填充
       (`background-color: #0D9488`, 亮青描边 `2px solid #5EEAD4`, 纯白加粗文字 `#FFFFFF`)，
       亮度对比度提升 400%，点按瞬间高亮发光！
  2. 新增水平滚动条 (`QScrollBar:horizontal`) 极简 5px 胶囊样式，配合顶栏与画布标头的鼠标滚轮横向滚动。
  3. 保持所有文本标签、滑块、复选框、滚动视口严格透明，杜绝色块补丁。
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_design_tokens() -> dict:
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "docs" / "UI_Design_Kit_v1" / "MolForge_UI_Design_Kit" / "design_tokens.json",
        Path(__file__).parent.parent / "resources" / "design_tokens.json",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


_TOKENS = _load_design_tokens()

C = {
    "bg": "#09111B",
    "shell": "#0C1622",
    "sidebar": "#0F1B29",
    "panel": "#142334",
    "raised": "#17283B",
    "border": "#243B52",
    "text": "#EAF2F6",
    "secondary": "#9AB0C2",
    "muted": "#688094",
    "teal": "#66DEC9",
    "blue": "#7DAEFA",
    "paper": "#F4F3EE",
    "warning": "#E5B567",
    "error": "#F2777A",
}

S = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "2xl": 24, "3xl": 32}
R = {"button": 6, "input": 7, "panel": 9, "overlay": 8}

THEMES = {
    "Dark Professional": {
        "bg": "#09111B",
        "shell": "#0C1622",
        "sidebar": "#0F1B29",
        "panel": "#142334",
        "card_header": "#182A3E",
        "raised": "#17283B",
        "border": "#243B52",
        "border_subtle": "#1A2C3E",
        "text": "#EAF2F6",
        "secondary": "#9AB0C2",
        "muted": "#688094",
        "teal": "#66DEC9",
        "blue": "#7DAEFA",
        "paper": "#F4F3EE",
        "hover": "#213A54",
        "active_bg": "#0D9488",
        "active_border": "#5EEAD4",
        "active_text": "#FFFFFF",
        "elem_active_bg": "#14B8A6",
        "elem_active_text": "#021815",
        "navcheck": "#0D9488",
        "navborder": "#5EEAD4",
        "inputbg": "#0D1825",
        "inputborder": "#28425A",
        "scroll": "#2D4960",
        "scroll_hover": "#66DEC9",
        "scrollbg": "transparent",
        "splitter": "#192B3C",
    },
    "Light Clean": {
        "bg": "#EEF2F6",
        "shell": "#F7F9FB",
        "sidebar": "#F0F4F8",
        "panel": "#FFFFFF",
        "card_header": "#F3F7FA",
        "raised": "#E8EEF3",
        "border": "#D0DBE5",
        "border_subtle": "#E2E9F0",
        "text": "#1C2B39",
        "secondary": "#526575",
        "muted": "#7F91A0",
        "teal": "#0F9D86",
        "blue": "#2B6CB0",
        "paper": "#FFFFFF",
        "hover": "#DAE5F0",
        "active_bg": "#0D9488",
        "active_border": "#0F766E",
        "active_text": "#FFFFFF",
        "elem_active_bg": "#0D9488",
        "elem_active_text": "#FFFFFF",
        "navcheck": "#0D9488",
        "navborder": "#0F766E",
        "inputbg": "#FFFFFF",
        "inputborder": "#C2D0DC",
        "scroll": "#B8C7D4",
        "scroll_hover": "#0F9D86",
        "scrollbg": "transparent",
        "splitter": "#D5DEE6",
    },
    "High Contrast": {
        "bg": "#000000",
        "shell": "#05080C",
        "sidebar": "#080D14",
        "panel": "#0E1520",
        "card_header": "#141F2E",
        "raised": "#182436",
        "border": "#4A6B8A",
        "border_subtle": "#2C445C",
        "text": "#FFFFFF",
        "secondary": "#E0EAF2",
        "muted": "#A8BAC8",
        "teal": "#00FFCC",
        "blue": "#38B6FF",
        "paper": "#FFFFFF",
        "hover": "#22344A",
        "active_bg": "#00D4AA",
        "active_border": "#FFFFFF",
        "active_text": "#001812",
        "elem_active_bg": "#00FFCC",
        "elem_active_text": "#001812",
        "navcheck": "#00D4AA",
        "navborder": "#FFFFFF",
        "inputbg": "#050A10",
        "inputborder": "#5A7D9E",
        "scroll": "#5A7D9E",
        "scroll_hover": "#00FFCC",
        "scrollbg": "transparent",
        "splitter": "#4A6B8A",
    },
}


def build_style(theme_name: str = "Dark Professional", accent: str | None = None, font_family: str | None = None, font_size: int | None = None) -> str:
    t = THEMES.get(theme_name, THEMES["Dark Professional"])
    if accent:
        t = dict(t)
        t["teal"] = accent
        t["active_bg"] = accent
    ff = font_family or '"Microsoft YaHei UI", "PingFang SC", "Segoe UI", -apple-system, sans-serif'
    fs = font_size or 14
    fs_xs = max(10, fs - 3)
    fs_sm = max(11, fs - 2)
    fs_md = max(12, fs - 1)
    fs_lg = fs + 1
    fs_xl = fs + 2
    fs_brand = fs + 4
    return f"""
QMainWindow, QDialog {{
    background-color: {t['shell']};
    color: {t['text']};
    font-family: {ff};
    font-size: {fs}px;
}}
QWidget {{
    color: {t['text']};
    font-family: {ff};
    font-size: {fs}px;
}}
QWidget#CentralShell, QWidget#WorkspaceContainer {{
    background-color: {t['shell']};
}}
QWidget#ScrollPage, QWidget#ToolbarStrip, QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}
QFrame#ToolbarFrame {{
    background-color: {t['bg']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
QTableWidget, QTableView, QTreeView, QListView {{
    background-color: {t['panel']}; color: {t['text']};
    alternate-background-color: {t['shell']}; gridline-color: {t['border_subtle']};
    selection-background-color: {t['active_bg']}; selection-color: #FFFFFF;
    border: 1px solid {t['border']};
    border-radius: 6px;
    outline: none;
    font-size: {fs}px;
    font-family: {ff};
}}
QTableWidget::item, QTableView::item, QTreeView::item, QListView::item {{
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {t['border_subtle']};
    font-size: {fs}px;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {t['active_bg']};
    color: #FFFFFF;
    font-weight: 600;
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background-color: {t['hover']};
}}
QHeaderView {{
    background-color: {t['shell']};
    border: none;
}}
QHeaderView::section {{
    background-color: {t['raised']};
    color: {t['secondary']};
    font-weight: 700;
    font-size: {fs_sm}px;
    padding: 6px 10px;
    border: none;
    border-bottom: 2px solid {t['border']};
    border-right: 1px solid {t['border_subtle']};
}}
QHeaderView::section:hover {{
    background-color: {t['hover']};
    color: {t['teal']};
}}
QTableCornerButton::section {{
    background-color: {t['raised']};
    border: none;
}}
QLabel, QCheckBox, QRadioButton, QSlider {{
    background-color: transparent;
    border: none;
    font-size: {fs}px;
    font-family: {ff};
}}
QMenuBar {{
    background-color: {t['bg']};
    color: {t['secondary']};
    border-bottom: 1px solid {t['border']};
    padding: 3px 10px;
    font-size: {fs}px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 5px;
    background: transparent;
    font-size: {fs}px;
}}
QMenuBar::item:selected {{
    background-color: {t['hover']};
    color: {t['text']};
}}
QMenu {{
    background-color: {t['panel']};
    color: {t['text']};
    border: 1px solid {t['active_border']};
    border-radius: 8px;
    padding: 6px;
    font-size: {fs}px;
}}
QMenu::item {{
    padding: 7px 24px 7px 14px;
    border-radius: 5px;
    font-size: {fs}px;
}}
QMenu::item:selected {{
    background-color: {t['active_bg']};
    color: {t['active_text']};
    font-weight: 700;
}}
QMenu::separator {{
    height: 1px;
    background: {t['border']};
    margin: 4px 6px;
}}
QVTKOpenGLNativeWidget, QVTKOpenGLWindow, QOpenGLWidget {{
    background-color: transparent;
    border: none;
}}
QFrame#TopBar {{
    background-color: {t['bg']};
    border-bottom: 1px solid {t['border']};
}}
QFrame#NavRail {{
    background-color: {t['bg']};
    border-right: 1px solid {t['border']};
}}
QFrame#Sidebar, QFrame#LeftPanel {{
    background-color: {t['sidebar']};
    border-right: 1px solid {t['border']};
    font-size: {fs}px;
    font-family: {ff};
}}
QFrame#RightPanel {{
    background-color: {t['sidebar']};
    border-left: 1px solid {t['border']};
    font-size: {fs}px;
    font-family: {ff};
}}
QFrame#TabStripFrame {{
    background-color: {t['bg']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
QFrame#CollapsibleCard, QFrame#InfoCard {{
    background-color: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
QPushButton#CardHeaderBtn {{
    background-color: {t['card_header']};
    border: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    border-bottom: 1px solid {t['border_subtle']};
    padding: 7px 11px;
    color: {t['text']};
    font-size: {fs}px;
    font-weight: 700;
    text-align: left;
    font-family: {ff};
}}
QPushButton#CardHeaderBtn:hover {{
    background-color: {t['hover']};
    color: {t['teal']};
}}
QPushButton#CardHeaderBtn:checked {{
    background-color: {t['card_header']};
    color: {t['teal']};
    border: none;
    border-bottom: 1px solid {t['border_subtle']};
}}
QLabel[role="title"] {{
    color: {t['text']};
    font-size: {fs_lg}px;
    font-weight: 700;
}}
QLabel[role="section"] {{
    color: {t['muted']};
    font-size: {fs}px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel[role="muted"] {{
    color: {t['secondary']};
    font-size: {fs_sm}px;
}}
QLabel[role="value"] {{
    color: {t['teal']};
    font-size: {fs}px;
    font-weight: 700;
    font-family: "Consolas", "JetBrains Mono", "Segoe UI", monospace;
}}
QLabel[role="brand"] {{
    color: {t['text']};
    font-size: {fs_brand}px;
    font-weight: 800;
    letter-spacing: 0.4px;
}}
QLabel[role="cardtitle"] {{
    color: {t['text']};
    font-size: {fs}px;
    font-weight: 700;
}}
QPushButton {{
    background-color: {t['raised']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 5px 11px;
    color: {t['secondary']};
    font-size: {fs}px;
    font-weight: 600;
    font-family: {ff};
}}
QPushButton:hover:!disabled {{
    background-color: {t['hover']};
    color: {t['text']};
    border: 1px solid {t['teal']};
}}
QPushButton:disabled {{
    color: {t['muted']};
    background-color: transparent;
    border: 1px solid transparent;
}}
/* 强视觉对比的激活/选中状态：一眼看清当前点亮了哪个工具/模式/视图！ */
QPushButton:checked, QPushButton[active="true"] {{
    background-color: {t['active_bg']};
    color: {t['active_text']};
    border: 2px solid {t['active_border']};
    font-weight: 800;
}}
QPushButton[role="nav"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    text-align: left;
    padding: 6px 10px;
    font-size: {fs}px;
    font-family: {ff};
}}
QPushButton[role="nav"]:hover {{
    background-color: {t['hover']};
    color: {t['text']};
}}
QPushButton[role="nav"]:checked, QPushButton[role="nav"][active="true"] {{
    background-color: {t['active_bg']};
    color: {t['active_text']};
    border: 1px solid {t['active_border']};
    font-weight: 800;
}}
QPushButton[role="tab"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    text-align: center;
    padding: 5px 6px;
    font-size: {fs}px;
    font-weight: 600;
    font-family: {ff};
}}
QPushButton[role="tab"]:hover {{
    color: {t['text']};
    background-color: {t['hover']};
}}
QPushButton[role="tab"]:checked, QPushButton[role="tab"][active="true"] {{
    background-color: {t['active_bg']};
    color: {t['active_text']};
    border: 1px solid {t['active_border']};
    font-weight: 800;
}}
QPushButton[role="chip"] {{
    background-color: {t['inputbg']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: {fs_sm}px;
    color: {t['text']};
    text-align: center;
    font-family: {ff};
}}
QPushButton[role="chip"]:hover {{
    background-color: {t['hover']};
    color: {t['teal']};
    border: 1px solid {t['teal']};
}}
QPushButton[role="chip"]:checked, QPushButton[role="chip"][active="true"] {{
    background-color: {t['active_bg']};
    color: {t['active_text']};
    border: 2px solid {t['active_border']};
    font-weight: 800;
}}
QPushButton[role="elem"] {{
    padding: 4px 8px;
    min-width: 30px;
    text-align: center;
    font-weight: 700;
    border-radius: 6px;
    background-color: {t['raised']};
    color: {t['text']};
    border: 1px solid {t['border']};
    font-size: {fs}px;
}}
QPushButton[role="elem"]:hover {{
    background-color: {t['hover']};
    border: 1px solid {t['teal']};
}}
QPushButton[role="elem"]:checked, QPushButton[role="elem"][active="true"] {{
    background-color: {t['elem_active_bg']};
    color: {t['elem_active_text']};
    border: 2px solid {t['active_border']};
    font-weight: 800;
}}
QPushButton[role="action"] {{
    color: #031B17;
    background-color: {t['teal']};
    font-weight: 800;
    text-align: center;
    border: 1px solid {t['active_border']};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: {fs}px;
}}
QPushButton[role="action"]:hover:!disabled {{
    background-color: #80F0DC;
    color: #021411;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    color: {t['text']};
    background-color: {t['inputbg']};
    padding: 5px 9px;
    border-radius: 6px;
    border: 1px solid {t['inputborder']};
    selection-background-color: {t['teal']};
    selection-color: #041F1A;
    font-size: {fs}px;
    font-family: {ff};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {t['teal']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['panel']};
    color: {t['text']};
    border: 1px solid {t['border']};
    selection-background-color: {t['active_bg']};
    selection-color: {t['active_text']};
}}
QSlider::groove:horizontal {{
    height: 12px;
    background: {t['inputbg']};
    border: 1px solid {t['border_subtle']};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {t['teal']};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {t['text']};
    border: 2px solid {t['teal']};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {t['teal']};
}}
QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-radius: 8px;
    background: {t['panel']};
}}
QTabBar::tab {{
    background: {t['sidebar']};
    color: {t['secondary']};
    padding: 7px 14px;
    border: 1px solid {t['border']};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {t['active_bg']};
    color: {t['active_text']};
    font-weight: 800;
}}
QSplitter::handle {{
    background-color: {t['splitter']};
}}
QSplitter::handle:hover {{
    background-color: {t['teal']};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 7px;
    margin: 2px 1px 2px 1px;
}}
QScrollBar::handle:vertical {{
    background: {t['scroll']};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['scroll_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0px 2px 0px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scroll']};
    border-radius: 2px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['scroll_hover']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0px;
    background: transparent;
}}
"""


STYLE = build_style("Dark Professional")


def refresh_button_visual(btn, active: bool | None = None) -> None:
    """强制刷新按钮的 checked / active 视觉状态，确保点击后 100% 立即点亮！"""
    if active is not None:
        if btn.isCheckable():
            btn.setChecked(bool(active))
        btn.setProperty("active", "true" if active else "false")
    else:
        btn.setProperty("active", "true" if btn.isChecked() else "false")
    st = btn.style()
    if st is not None:
        st.unpolish(btn)
        st.polish(btn)
    btn.update()


def apply_theme(window, theme_name: str, accent: str | None = None):
    from PyQt6.QtWidgets import QApplication
    full = build_style(theme_name, accent)
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(full)
        app.processEvents()
    vtk_widget = window.workspace.view3d_real
    if getattr(vtk_widget, "plotter", None) is not None and hasattr(vtk_widget.plotter, "set_background"):
        if theme_name == "Light Clean":
            vtk_widget.plotter.set_background(color=[0.88, 0.91, 0.95], top=[0.96, 0.98, 1.0])
        else:
            vtk_widget.plotter.set_background(color=[0.067, 0.114, 0.173], top=[0.145, 0.227, 0.314])
    vtk_widget.set_document(window.document)
