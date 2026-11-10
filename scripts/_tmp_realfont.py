"""临时：用真实 windows 平台（不显示窗口）渲染编号，验证数字真实字形。"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# 不设 offscreen，使用真实平台
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.selection import SelectionService
from molforge.ui.editor2d_widget import Editor2DWidget

app = QApplication(sys.argv)
doc = create_instant_caffeine_document()
bus = CommandBus(doc); sel = SelectionService()
w = Editor2DWidget()
w.set_document(doc); w.set_selection_service(sel); w.set_command_bus(bus)
w.resize(900, 700)
w.set_show_atom_numbers(True)
# 不 show，直接 render 到 pixmap
pix = QPixmap(w.size()); w.render(pix)
out = os.path.join(ROOT, "qa_evidence", "05c_realfont.png")
pix.save(out)
from PIL import Image
im = Image.open(out)
im.crop((525, 245, 625, 295)).resize((400, 200)).save(
    os.path.join(ROOT, "qa_evidence", "05d_realfont_zoom.png"))
print("saved", out)
