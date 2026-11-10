"""
MolForge v7.0 - AI-Native 分子工作台主入口
==========================================
直接运行 `python main.py`（支持 `--mode welcome|split|2d|3d|legacy`）或双击 `run_molforge.bat` 启动。
"""
from __future__ import annotations

import sys
from molforge.runtime import configure_runtime
configure_runtime()
from molforge import __version__
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
except Exception:
    pass

from molforge.ui.theme import STYLE
from molforge.ui.window import MolForgeWindow
from molforge.ui.welcome_window import AppController, WelcomeWindow


def run_application(argv: list[str] | None = None, default_mode: str = "welcome") -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(args)
    app.setApplicationName("MolForge")
    app.setApplicationVersion(__version__)
    try:
        from PyQt6.QtGui import QFont
        app_font = QFont("Microsoft YaHei UI", 10)
        app_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        app.setFont(app_font)
    except Exception:
        pass
    app.setStyleSheet(STYLE)

    mode = default_mode
    for i, a in enumerate(args):
        if a == "--mode" and i + 1 < len(args):
            mode = args[i + 1].strip().lower()
        elif a == "--welcome":
            mode = "welcome"

    ctrl = AppController.instance()
    if mode == "welcome":
        ctrl.show_welcome()
    elif mode in ("2d", "3d", "split"):
        ctrl.launch_system(mode)  # type: ignore[arg-type]
    else:
        window = MolForgeWindow()
        window.show()
        ctrl.active_windows.append(window)

    return app.exec()


def main():
    sys.exit(run_application(sys.argv, default_mode="welcome"))


if __name__ == "__main__":
    main()
