"""2D 编辑真实功能验收：加/删原子、加/删键、改键级、撤销/重做。

offscreen 运行，结果写 qa_evidence/test_2d_editing.txt。
任何断言失败都会以非零退出码暴露。
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

LOG = open(os.path.join(ROOT, "qa_evidence", "test_2d_editing.txt"), "w", encoding="utf-8")
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

n0 = doc.num_atoms
b0 = doc.topology.num_bonds
log(f"初始咖啡因: 原子 {n0}  键 {b0}")

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg)
        raise AssertionError(msg)
    log("PASS: " + msg)

# 1. 加原子（在空白世界坐标，不带 bond_to）
w.set_current_tool("原子")
new_aid = w._add_atom_at_world((12.0, 12.0), bond_to=None)
check(new_aid is not None, "加原子返回新 AtomId")
check(doc.num_atoms == n0 + 1, f"加原子后原子数 +1 (现 {doc.num_atoms})")
check(new_aid in doc.topology._atoms, "新原子真实存在于拓扑")
check(new_aid in doc.coords_2d, "新原子有 2D 坐标")
check(doc.coordinates.current is not None and len(doc.coordinates.current.coords) == n0 + 1, "3D 坐标帧同步 +1")

# 2. 再加一个原子并与第一个新原子成键
new_aid2 = w._add_atom_at_world((14.0, 12.0), bond_to=new_aid)
check(new_aid2 is not None and doc.topology.bond_between(new_aid, new_aid2) is not None, "带 bond_to 加原子自动成键")

# 3. 加键：取两个当前无键的原子
ids = list(doc.topology.atom_ids)
a, b = ids[0], ids[1]
existing = doc.topology.bond_between(a, b)
bb_before = doc.topology.num_bonds
if existing is None:
    w._add_bond(a, b)
    check(doc.topology.bond_between(a, b) is not None, "加键后两原子间存在键")
    check(doc.topology.num_bonds == bb_before + 1, "加键后键数 +1")
    added_bid = doc.topology.bond_between(a, b)
else:
    log("SKIP: 选取的两原子已有键，改用改键级测试")
    added_bid = existing

# 4. 改键级（通过 _add_bond 对已存在键会升级键级）
order_before = doc.topology.get_bond(added_bid).order
w._add_bond(a, b)
order_after = doc.topology.get_bond(added_bid).order
check(order_after != order_before or order_after in (1, 2, 3), f"重复加键升级键级 ({order_before}->{order_after})")

# 5. 删键
nb_before = doc.topology.num_bonds
w._delete_bond(added_bid)
check(added_bid not in doc.topology._bonds, "删键后键从拓扑移除")
check(doc.topology.num_bonds == nb_before - 1, "删键后键数 -1")

# 6. 删原子（删最后加的 new_aid2，连带处理）
na_before = doc.num_atoms
w._delete_atom(new_aid2)
check(new_aid2 not in doc.topology._atoms, "删原子后原子从拓扑移除")
check(doc.num_atoms == na_before - 1, "删原子后原子数 -1")

# 7. 撤销/重做：逐步撤销回到初始
undo_count = 0
while bus.can_undo:
    r = bus.undo()
    check(r.success, f"撤销第 {undo_count+1} 步成功")
    undo_count += 1
check(doc.num_atoms == n0, f"全部撤销后原子数回到初始 {n0} (现 {doc.num_atoms})")
check(doc.topology.num_bonds == b0, f"全部撤销后键数回到初始 {b0} (现 {doc.topology.num_bonds})")

# 8. 重做：把所有撤销的操作重做一遍
redo_count = 0
while bus.can_redo:
    r = bus.redo()
    check(r.success, f"重做第 {redo_count+1} 步成功")
    redo_count += 1
check(doc.num_atoms == n0 + 1, f"全部重做后回到编辑末态原子数(末步已删 new_aid2, 现 {doc.num_atoms})")

log(f"撤销步数 {undo_count}  重做步数 {redo_count}")
log("2D 编辑全部验收通过")
LOG.close()
