"""2D 端到端鼠标验收：用 QTest 模拟真实点击/拖拽，验证事件系统在真实 Qt 下连通。

offscreen 运行，结果写 qa_evidence/test_2d_qtest.txt。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.selection import SelectionService
from molforge.ui.editor2d_widget import Editor2DWidget

LOG = open(os.path.join(ROOT, "qa_evidence", "test_2d_qtest.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n"); LOG.flush()

app = QApplication(sys.argv)
doc = create_instant_caffeine_document()
bus = CommandBus(doc)
sel = SelectionService()
w = Editor2DWidget()
w.set_document(doc)
w.set_selection_service(sel)
w.set_command_bus(bus)
w.resize(900, 700)
w.show()
app.processEvents()
app.processEvents()

n0 = doc.num_atoms
b0 = doc.topology.num_bonds

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg); raise AssertionError(msg)
    log("PASS: " + msg)

# 1. 原子工具：在屏幕内找一个真正空白的像素点点击 -> 加原子
w.set_current_tool("原子")
from PyQt6.QtCore import QPointF
blank_pt = None
for cand in [QPointF(w.width() - 80, w.height() - 80),
             QPointF(120, w.height() - 120),
             QPointF(w.width() - 120, 200),
             QPointF(150, 200)]:
    if (cand.y() > w.HEADER_HEIGHT and w._find_atom_at(cand) is None
            and w._find_bond_at(cand) is None):
        blank_pt = cand; break
check(blank_pt is not None, "找到屏幕内空白像素点")
QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                 QPoint(int(blank_pt.x()), int(blank_pt.y())), delay=10)
app.processEvents()
check(doc.num_atoms == n0 + 1, f"QTest 点空白加原子 (现 {doc.num_atoms})")

# 2. 选择工具：单击一个现有原子应选中它
w.set_current_tool("选择")
first_aid = list(doc.topology.atom_ids)[0]
ax, ay = w.world_to_screen(*doc.coords_2d[first_aid])
QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                 QPoint(int(ax), int(ay)), delay=10)
app.processEvents()
check(first_aid in sel.selected_atoms, "QTest 点原子真实选中")

# 3. 键工具：从原子 A 拖到原子 B（无键的一对）-> 加键
w.set_current_tool("键")
ids = list(doc.topology.atom_ids)
a, b = None, None
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        if doc.topology.bond_between(ids[i], ids[j]) is None:
            a, b = ids[i], ids[j]; break
    if a: break
check(a is not None and b is not None, "找到一对无键原子")
ax, ay = w.world_to_screen(*doc.coords_2d[a])
bx, by = w.world_to_screen(*doc.coords_2d[b])
QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                 QPoint(int(ax), int(ay)), delay=5)
QTest.mouseMove(w, QPoint(int(bx), int(by)), delay=5)
QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                   QPoint(int(bx), int(by)), delay=5)
app.processEvents()
check(doc.topology.bond_between(a, b) is not None, "QTest 拖拽两原子真实加键")
check(doc.topology.num_bonds == b0 + 1, f"键数 +1 (现 {doc.topology.num_bonds})")

# 4. 撤销应回到初始
bus.undo(); bus.undo(); bus.undo()
app.processEvents()
check(doc.num_atoms == n0 and doc.topology.num_bonds == b0, "撤销后回到初始状态")

log("2D QTest 端到端鼠标验收通过")
LOG.close()
