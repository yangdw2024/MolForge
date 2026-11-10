"""启动截图：验证 Gemini 补丁后的 3D 渲染。"""
import sys
sys.path.insert(0, r"E:\YDW\Trae_Chemdraw\MolForge")
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
from molforge.ui.theme import STYLE
from molforge.ui.window import MolForgeWindow

app = QApplication(sys.argv)
app.setStyleSheet(STYLE)
win = MolForgeWindow()
win.resize(1500, 880)
win.show()

def shot():
    win.grab().save(r"E:\YDW\Trae_Chemdraw\MolForge\docs\gemini_v2_startup.png", "PNG")
    print(f"原子={win.document.num_atoms}, 键={win.document.num_bonds}, has_3d={win.document.has_3d}")
    print("截图完成")
    app.quit()

QTimer.singleShot(3000, shot)
sys.exit(app.exec())
