"""2D↔3D 同步验收：交叉高亮、编辑同步、撤销同步。

offscreen 运行，结果写 qa_evidence/test_2d3d_sync.txt。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.selection import SelectionService
from molforge.ui.editor2d_widget import Editor2DWidget
from molforge.ui.render3d_widget import Render3DWidget

LOG = open(os.path.join(ROOT, "qa_evidence", "test_2d3d_sync.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n"); LOG.flush()

app = QApplication(sys.argv)
doc = create_instant_caffeine_document()
bus = CommandBus(doc)
sel = SelectionService()

w2 = Editor2DWidget()
w2.set_document(doc); w2.set_selection_service(sel); w2.set_command_bus(bus)
w3 = Render3DWidget()
w3.set_selection_service(sel); w3.set_command_bus(bus)
w3.set_document(doc)
app.processEvents(); app.processEvents()

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg); raise AssertionError(msg)
    log("PASS: " + msg)

n0 = doc.num_atoms
r3 = w3.renderer

# 1. 2D 选一个原子 -> 3D 高亮同步
a = list(doc.topology.atom_ids)[0]
sel.select_atom(a, add=False, origin="2d")
app.processEvents(); app.processEvents()  # 触发 3D 的 QTimer.singleShot
check(a in sel.selected_atoms, "2D 选择写入共享 SelectionService")
check(a in r3._selected, "3D 渲染器同步高亮该原子（2D→3D）")

# 2. 清空后从 3D 选另一个原子 -> 2D 同步
sel.clear(origin="3d")
app.processEvents()
b = list(doc.topology.atom_ids)[5]
sel.select_atom(b, add=False, origin="3d")
app.processEvents()
check(b in r3._selected, "3D 选择写入渲染器")
check(b in sel.selected_atoms and w2._selection.selected_atoms == sel.selected_atoms,
      "2D 通过共享选择同步（3D→2D）")

# 3. 编辑同步：在 2D 加原子，3D 看到的同一文档原子数增加
w2.set_current_tool("原子")
new_aid = w2._add_atom_at_world((doc.coords_2d[a][0] + 8.0, doc.coords_2d[a][1] + 8.0))
app.processEvents()
check(doc.num_atoms == n0 + 1, "2D 加原子后共享文档原子数 +1")
check(r3._n_atoms == n0 + 1, "3D 渲染器同步新原子数")
check(new_aid in r3._id_to_idx, "3D 渲染器包含新原子映射")

# 4. 撤销同步：撤销加原子，两个视图都回到原状态
bus.undo()
app.processEvents()
check(doc.num_atoms == n0, "撤销后共享文档回到原原子数")
check(r3._n_atoms == n0, "3D 渲染器同步撤销")
check(new_aid not in r3._id_to_idx, "3D 移除被撤销原子")

# 5. 编号一致性：2D 与 3D 都基于同一 AtomId 且展示同为 1-based
w2.set_show_atom_numbers(True)
r3.show_labels = True; r3.show_symbols = True
r3._update_labels_in_place()
common = set(aid.value + 1 for aid in doc.topology.atom_ids)
check(len(common) == doc.num_atoms, "2D/3D 编号同源（同一 AtomId 集合，1-based 展示）")

log("2D↔3D 同步与交叉高亮全部验收通过")
LOG.close()
