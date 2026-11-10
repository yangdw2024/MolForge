"""快速启动验证：启动窗口、截图、退出。"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
except Exception:
    pass

from molforge.ui.theme import STYLE
from molforge.ui.window import MolForgeWindow

OUT = ROOT / "qa_evidence"
OUT.mkdir(exist_ok=True)

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MolForgeWindow()
    win.show()

    def grab():
        pm = QPixmap(win.size())
        win.render(pm)
        p = OUT / "v5_baseline_start.png"
        pm.save(str(p))
        print(f"[saved] {p} {pm.width()}x{pm.height()}")

    QTimer.singleShot(3000, grab)
    QTimer.singleShot(4000, app.quit)
    app.exec()
    print("[done]")

if __name__ == "__main__":
    main()
