"""
ui/welcome_window.py - 启动欢迎界面与三大独立系统工厂 (WelcomeWindow & ShellFactory)
====================================================================================
严格实现 2.2 / 4.1 节要求：
  - 提供三大独立系统入口：2D 化学绘图系统 (Studio2DShell)、3D 多窗口系统 (Studio3DShell)、2D-3D 联动系统 (StudioSplitShell)
  - 保留经典三栏工作台入口 (LegacyWorkbenchAdapter)
  - 欢迎界面延迟创建 VTK 画布，不在启动欢迎页时预先实例化重型 3D 上下文
"""

from __future__ import annotations

from typing import Literal

from ..domain.document import MoleculeDocument
from .shells import BaseStudioShell, Studio2DShell, Studio3DShell, StudioSplitShell

SystemMode = Literal["2d", "3d", "split", "legacy"]


class ShellFactory:
    """根据用户选择的系统入口按需延迟构造对应的完整 Shell。"""

    @staticmethod
    def create_shell(mode: SystemMode, document: MoleculeDocument | None = None) -> BaseStudioShell:
        doc = document if document is not None else MoleculeDocument(name="untitled")
        if mode == "2d":
            return Studio2DShell(document=doc)
        elif mode == "3d":
            return Studio3DShell(document=doc)
        elif mode == "split":
            return StudioSplitShell(document=doc)
        elif mode == "legacy":
            return StudioSplitShell(document=doc)
        raise ValueError(f"Unknown system mode: '{mode}'")

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QFileDialog
    )
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False
    QMainWindow = object  # type: ignore[misc,assignment]
    def pyqtSignal(*args, **kwargs):  # type: ignore[misc]
        return None


class WelcomeWindow(QMainWindow):
    """
    MolForge v7.0 真正可交互的启动欢迎窗口 (P0-03)：
    - 启动时不创建任何 VTK / OpenGL 上下文，实现毫秒级瞬时弹出与零显存开销
    - 提供四大独立系统入口卡片：
      1. 2D 化学结构设计系统 (Studio2DWindow)
      2. 3D 多窗口建模与量化系统 (Studio3DWindow, 支持 1/2/4 视口)
      3. 2D–3D 实时分屏联动系统 (StudioSplitWindow)
      4. 经典三栏全功能工作台 (Legacy MolForgeWindow)
    """

    system_selected = pyqtSignal(str)

    def __init__(self, on_launch_mode=None):
        super().__init__()
        self.on_launch_mode = on_launch_mode
        self.setWindowTitle(f"MolForge v{__import__('molforge').__version__} · 分子科学工作台启动器")
        self.resize(1040, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(16)

        hdr = QLabel(
            "<span style='font-size:28px;font-weight:800;color:#F0FDF4;font-family:'Microsoft YaHei UI',sans-serif;'>MolForge Studio</span><br>"
            "<span style='font-size:14px;color:#94A3B8;font-family:'Microsoft YaHei UI',sans-serif;line-height:26px;'>对标 ChemDraw / Chem3D / GaussView / VMD · 2D 拓扑设计 · 2D⇄3D 实时联动 · 量化结果分析 · 分子动力学 · AI 助手</span>"
        )
        root.addWidget(hdr)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)

        specs = [
            (
                "2d",
                "✏️ 2D 化学结构设计系统",
                "简洁 2D 绘图，多标签页，适合画分子结构、导出 SVG。",
                "启动 2D 绘图系统",
            ),
            (
                "3d",
                "🧊 3D 多窗口建模与量化系统",
                "Chem3D 风格 3D 建模，多标签页与多视口分屏。",
                "启动 3D 建模系统",
            ),
            (
                "split",
                "⚡ 2D–3D 实时分屏联动系统",
                "左边画 2D，右边看 3D，共享文档实时同步。",
                "启动 2D–3D 联动系统",
            ),
            (
                "legacy",
                "🏛️ 经典三栏全功能工作台",
                "完整功能的三栏界面：分子库、中央多标签画布和属性面板。",
                "启动经典三栏工作台",
            ),
        ]

        self.launch_buttons: dict[str, QPushButton] = {}
        for mode_key, title, desc, btn_text in specs:
            card = QFrame()
            card.setObjectName("Card")
            card.setStyleSheet(
                "QFrame#Card { background-color: #111E2E; border: 1.5px solid #1E3851; border-radius: 12px; padding: 18px; }"
                "QFrame#Card:hover { border: 1.5px solid #00D5B0; background-color: #142436; }"
            )
            c_lay = QVBoxLayout(card)
            c_lay.setSpacing(12)
            t_lbl = QLabel(f"<span style='font-size:17px;font-weight:700;color:#F8FAFC;font-family:'Microsoft YaHei UI',sans-serif;'>{title}</span>")
            t_lbl.setWordWrap(True)
            d_lbl = QLabel(f"<span style='font-size:13.5px;line-height:1.6;color:#94A3B8;font-family:'Microsoft YaHei UI',sans-serif;'>{desc}</span>")
            d_lbl.setWordWrap(True)
            c_lay.addWidget(t_lbl)
            c_lay.addWidget(d_lbl, 1)

            btn = QPushButton(btn_text)
            btn.setProperty("role", "action")
            btn.setMinimumHeight(42)
            btn.setStyleSheet("font-size: 14px; font-weight: 700; border-radius: 8px;")
            btn.clicked.connect(lambda checked=False, mk=mode_key: self.choose_mode(mk))
            c_lay.addWidget(btn)
            cards_row.addWidget(card, 1)
            self.launch_buttons[mode_key] = btn

        root.addLayout(cards_row, 1)

        bot = QHBoxLayout()
        open_btn = QPushButton("📂 直接打开分子或计算结果文件 (.mforge / .gjf / .log / .xyz / .mol / .sdf / .pdb)...")
        open_btn.setStyleSheet("font-size: 13.5px; padding: 8px 18px; border-radius: 6px;")
        open_btn.clicked.connect(self._open_file_directly)
        bot.addWidget(open_btn)
        bot.addStretch(1)
        ver_lbl = QLabel(f"<span style='color:#66DEC9;font-size:13px;font-weight:600;'>v{__import__('molforge').__version__} · 分层架构 domain/application/rendering</span>")
        bot.addWidget(ver_lbl)
        root.addLayout(bot)

    def choose_mode(self, mode: SystemMode):
        self.system_selected.emit(mode)
        if self.on_launch_mode is not None:
            return self.on_launch_mode(mode)
        win = ShellWindowFactory.create_window(mode)
        win.show()
        self.hide()
        return win

    def _open_file_directly(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开分子或量化结果文件", "",
            "分子与结果文件 (*.mforge *.gjf *.com *.log *.out *.xyz *.mol *.sdf *.pdb *.mol2);;所有文件 (*)"
        )
        if path:
            win = self.choose_mode("split")
            if hasattr(win, "open_molecule_file"):
                win.open_molecule_file(path)


class ShellWindowFactory:
    """真正创建并显示独立 Qt 主窗口的工厂类（Studio2DWindow / Studio3DWindow / StudioSplitWindow 均为独立 QMainWindow，绝不包装 MolForgeWindow）。"""

    @staticmethod
    def create_window(mode: SystemMode = "split", document: MoleculeDocument | None = None):
        from .shells.studio_2d import Studio2DWindow
        from .shells.studio_3d import Studio3DWindow
        from .shells.studio_split import StudioSplitWindow
        from .window import MolForgeWindow
        if mode == "2d":
            win = Studio2DWindow(document=document)
            win.show()
            return win
        elif mode == "3d":
            win = Studio3DWindow(document=document, pane_count=1)
            win.show()
            return win
        elif mode == "split":
            win = StudioSplitWindow(document=document)
            win.show()
            return win
        win = MolForgeWindow(initial_document=document, initial_view_mode=2)
        win.show()
        return win


class AppController:
    """应用级生命周期与多窗口切换控制器 (P0-02 / P0-03)。"""

    _instance: "AppController | None" = None

    def __init__(self) -> None:
        self.welcome_window: WelcomeWindow | None = None
        self.active_windows: list = []

    @classmethod
    def instance(cls) -> "AppController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def show_welcome(self) -> WelcomeWindow:
        if self.welcome_window is None:
            self.welcome_window = WelcomeWindow(on_launch_mode=self.launch_system)
        self.welcome_window.show()
        self.welcome_window.raise_()
        return self.welcome_window

    def launch_system(self, mode: SystemMode = "split", document: MoleculeDocument | None = None):
        win = ShellWindowFactory.create_window(mode=mode, document=document)
        self.active_windows.append(win)
        if self.welcome_window is not None and self.welcome_window.isVisible():
            self.welcome_window.hide()
        win.show()
        return win

