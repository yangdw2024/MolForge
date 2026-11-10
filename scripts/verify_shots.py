"""
启动 osc_studio，自动截图验证，然后退出。
"""
import sys, os, faulthandler, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_crash = Path.home() / ".molforge_crash.log"
try:
    _fp = open(_crash, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_fp, all_threads=True)
except Exception:
    _fp = None

def _excepthook(t, e, tb):
    msg = "".join(traceback.format_exception(t, e, tb))
    if _fp:
        _fp.write("\n===== UI EXCEPTION =====\n" + msg)
    sys.stderr.write(msg)
sys.excepthook = _excepthook

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
except Exception:
    pass

from molforge.ui.theme import STYLE
from molforge.ui.window import MolForgeWindow

OUT = Path(r"E:\YDW\Trae_Chemdraw\_gemini_v4_20261029\verify_shots")
OUT.mkdir(parents=True, exist_ok=True)

def grab(win, name, delay_ms, after=None):
    def _do():
        if after is not None:
            try:
                after(win)
            except Exception as e:
                print(f"[action error] {name}: {e}")
        QTimer.singleShot(400, lambda: _save(win, name))
    QTimer.singleShot(delay_ms, _do)

def _save(win, name):
    pm = QPixmap(win.size())
    win.render(pm)
    p = OUT / f"{name}.png"
    pm.save(str(p))
    print(f"[saved] {p}  {pm.width()}x{pm.height()}")

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("MolForge-verify")

    win = MolForgeWindow()
    win.show()

    # 1. 初始主界面（2D+3D 分屏）
    grab(win, "01_main_split", 2500)

    # 2. 打开模型结构树 dock
    def open_explorer(w):
        if w._explorer_dock is None:
            w.toggle_model_explorer_dock()
        else:
            w._explorer_dock.setVisible(True)
    grab(win, "02_model_explorer", 4000, open_explorer)

    # 3. 打开笛卡尔坐标表
    def open_cart(w):
        if w._cartesian_dock is None:
            w.toggle_cartesian_table_dock()
        else:
            w._cartesian_dock.setVisible(True)
    grab(win, "03_cartesian_table", 5500, open_cart)

    # 4. 打开测量表
    def open_meas(w):
        if w._measurement_dock is None:
            w.toggle_measurement_table_dock()
        else:
            w._measurement_dock.setVisible(True)
    grab(win, "04_measurement_table", 7000, open_meas)

    # 5. 打开逐原子/逐键属性表
    def open_prop(w):
        if w._property_dock is None:
            w.toggle_property_table_dock()
        else:
            w._property_dock.setVisible(True)
    grab(win, "05_property_table", 8500, open_prop)

    # 6. 新建独立 3D 窗口
    def spawn_3d(w):
        w._spawn_new_window(initial_mode=1, blank=True)
    grab(win, "06_spawn_3d_window", 10000, spawn_3d)

    # 7. 仅 3D 视图
    def only_3d(w):
        w.workspace.set_mode(1)
    grab(win, "07_only_3d", 12000, only_3d)

    # 8. 退出
    QTimer.singleShot(14000, app.quit)

    app.exec()
    print("[done]")

if __name__ == "__main__":
    main()
