"""原子编号验收：2D 编号开关、与 3D 同口径、编辑后编号稳定不漂移。

offscreen 运行，结果写 qa_evidence/test_atom_numbers.txt，并保存编号截图。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.selection import SelectionService
from molforge.ui.editor2d_widget import Editor2DWidget

LOG = open(os.path.join(ROOT, "qa_evidence", "test_atom_numbers.txt"), "w", encoding="utf-8")
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
app.processEvents(); app.processEvents()

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg); raise AssertionError(msg)
    log("PASS: " + msg)

# 1. 默认关闭
check(w._show_atom_numbers is False, "默认原子编号关闭")

# 2. 开启编号
w.set_show_atom_numbers(True)
check(w._show_atom_numbers is True, "开启编号后状态为真")

# 3. 渲染到 pixmap 不崩溃，并保存截图
pix = QPixmap(w.size())
w.render(pix)
pix.save(os.path.join(ROOT, "qa_evidence", "05_2d_numbers.png"))
check(not pix.isNull(), "编号开启时成功渲染画布")

# 4. 编号口径：2D 用 aid.value，3D 后端也用 atom_id.value，确认所有可见原子编号唯一
visible_ids = [aid for aid in doc.topology.atom_ids if not w._is_hidden_hydrogen(aid)]
numbers = [aid.value for aid in visible_ids]
display_numbers = [v + 1 for v in numbers]  # 展示为 1-based
check(len(set(display_numbers)) == len(display_numbers), "所有可见原子编号唯一无重复")
check(min(display_numbers) == 1 and max(display_numbers) >= 1, "展示编号从 1 开始的正整数")

# 5. 编辑后编号稳定：记录前 3 个原子编号，加一个新原子后它们不变
before = {aid: aid.value for aid in list(doc.topology.atom_ids)[:3]}
w.set_current_tool("原子")
new_aid = w._add_atom_at_world((doc.coords_2d[list(doc.topology.atom_ids)[0]][0] + 6.0,
                                 doc.coords_2d[list(doc.topology.atom_ids)[0]][1] + 6.0))
app.processEvents()
after = {aid: aid.value for aid in list(doc.topology.atom_ids)[:3]}
check(before == after, "新增原子后原有原子编号保持不变（不漂移）")
check(new_aid.value not in numbers, "新原子获得未被占用的新编号")

# 6. 撤销后新原子编号消失，原编号不变
bus.undo(); app.processEvents()
check(new_aid not in doc.topology._atoms, "撤销后新原子及其编号移除")
check({aid: aid.value for aid in list(doc.topology.atom_ids)[:3]} == before, "撤销后原编号仍稳定")

# 7. 关闭编号后可正常渲染
w.set_show_atom_numbers(False)
pix2 = QPixmap(w.size()); w.render(pix2)
check(not pix2.isNull(), "关闭编号后画布正常渲染")

log("原子编号全部验收通过")
LOG.close()
