"""v6.0 启动验证 + 截图。"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
except Exception:
    pass

from molforge.ui.theme import STYLE
from molforge.ui.window import MolForgeWindow

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MolForgeWindow()
    win.show()
    win.resize(1600, 900)

    def screenshot():
        pix = win.grab()
        out = ROOT / "qa_evidence" / "v6_baseline_start.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(out))
        print(f"截图保存: {out}")
        print(f"分子: {win.document.name}, {win.document.num_atoms} 原子, {win.document.num_bonds} 键")
        app.quit()

    QTimer.singleShot(2000, screenshot)
    app.exec()

if __name__ == "__main__":
    main()
