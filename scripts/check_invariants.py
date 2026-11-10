"""
不变量检查：执行→撤销→重做后，拓扑/坐标/选择/双向ID映射是否100%一致。
用法：python scripts/check_invariants.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from molforge.domain.document import MoleculeDocument
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import (
    AddAtomCommand, DeleteAtomCommand, AddBondCommand, DeleteBondCommand,
    ChangeElementCommand, ChangeBondOrderCommand, MoveAtom3DCommand,
    AddRingCommand, CleanGeometry3DCommand,
)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}  {detail}")
        failed += 1

def snapshot(doc):
    return {
        "n_atoms": doc.topology.num_atoms,
        "n_bonds": doc.topology.num_bonds,
        "has_3d": doc.has_3d,
        "coords_shape": tuple(doc.coordinates.current.coords.shape) if doc.has_3d and doc.coordinates.current is not None else None,
        "atom_ids": [aid.value for aid in doc.topology.atom_ids],
        "bond_pairs": sorted(
            (min(b.begin.value, b.end.value), max(b.begin.value, b.end.value), b.order)
            for b in [doc.topology.get_bond(bid) for bid in doc.topology.bond_ids]
        ),
    }

print("=" * 64)
print("MolForge 2.0 核心数据不变量检查：执行 → 撤销 → 重做 → 映射一致性")
print("=" * 64)

# [测试 1] AddAtomCommand 坐标写入与 Undo/Redo AtomId 零漂移
print("\n[测试1] AddAtomCommand(x=3,y=0,z=0) 坐标写入与 Redo ID 稳定性")
doc = MoleculeDocument("test")
bus = CommandBus(doc)
bus.execute(AddAtomCommand(6, 0, 0, 0))
before = snapshot(doc)
r = bus.execute(AddAtomCommand(8, 3.0, 0.0, 0.0))
after = snapshot(doc)

check("加原子后原子数+1", after["n_atoms"] == before["n_atoms"] + 1)
check("加原子后坐标帧行数+1", after["coords_shape"] == (before["n_atoms"] + 1, 3))
last = doc.coordinates.current.coords[-1]
check("新原子坐标=传入的(3,0,0)", abs(last[0] - 3.0) < 0.01 and abs(last[1]) < 0.01 and abs(last[2]) < 0.01)
bus.undo()
check("undo后回到执行前", snapshot(doc) == before)
bus.redo()
check("redo后回到执行后（AtomId 零漂移）", snapshot(doc) == after)

# [测试 2] AddBondCommand.undo() 移除键与 redo 恢复
print("\n[测试2] AddBondCommand 执行/撤销/重做")
doc2 = MoleculeDocument("test2")
bus2 = CommandBus(doc2)
bus2.execute(AddAtomCommand(6, 0, 0, 0))
bus2.execute(AddAtomCommand(6, 1.4, 0, 0))
aids = list(doc2.topology.atom_ids)
before2 = snapshot(doc2)
bus2.execute(AddBondCommand(aids[0], aids[1], 1))
after2 = snapshot(doc2)
check("加键后键数+1", after2["n_bonds"] == before2["n_bonds"] + 1)
bus2.undo()
check("undo后键数回到before", snapshot(doc2) == before2)
bus2.redo()
check("redo后键数回到after", snapshot(doc2) == after2)

# [测试 3] DeleteAtomCommand 删光单原子与恢复
print("\n[测试3] DeleteAtomCommand 删光原子与恢复")
doc3 = MoleculeDocument("test3")
bus3 = CommandBus(doc3)
bus3.execute(AddAtomCommand(6, 0, 0, 0))
atom_id = list(doc3.topology.atom_ids)[0]
bus3.execute(DeleteAtomCommand(atom_id))
check("删原子后原子数=0", doc3.topology.num_atoms == 0)
bus3.undo()
check("undo后原子数恢复为1且ID不变", doc3.topology.num_atoms == 1 and list(doc3.topology.atom_ids)[0] == atom_id)

# [测试 4] CommandBus.add_validator 验证器触发
print("\n[测试4] CommandBus.add_validator 注册的验证器触发检查")
doc4 = MoleculeDocument("test4")
bus4 = CommandBus(doc4)
validator_called = [False]
def my_validator(d):
    validator_called[0] = True
    return []
bus4.add_validator(my_validator)
bus4.execute(AddAtomCommand(6))
check("注册的验证器被调用", validator_called[0])

# [测试 5] 含化学键的中间原子删除与原位恢复（Phase 1 核心）
print("\n[测试5] 删除中间带键原子后 AtomId<->Index 映射与 Undo 原位恢复")
doc5 = MoleculeDocument("test5")
bus5 = CommandBus(doc5)
bus5.execute(AddRingCommand(size=5, aromatic=True, hetero_atoms={0: 16}))
snap5_before = snapshot(doc5)
coords5_before = doc5.coordinates.current.coords.copy()
mid_aid = list(doc5.topology.atom_ids)[2]
bus5.execute(DeleteAtomCommand(mid_aid))
check("删环中原子后原子数=4、坐标行数=4", doc5.num_atoms == 4 and doc5.coordinates.current.coords.shape == (4, 3))
check("删原子后不变量检查全通过", len(doc5.check_invariants()) == 0)
bus5.undo()
check("undo后拓扑与AtomId序列100%恢复", snapshot(doc5) == snap5_before)
check("undo后3D坐标矩阵100%恢复", np.allclose(doc5.coordinates.current.coords, coords5_before))

# [测试 6] 3D 点击空白自动成键与 3D 弹簧弛豫优化
print("\n[测试6] 3D 自动与最近原子成键 (元素相关估算 1.47 Å（C–N）) 与 3D 力场弛豫")
doc6 = MoleculeDocument("test6")
bus6 = CommandBus(doc6)
bus6.execute(AddAtomCommand(6, 0.0, 0.0, 0.0))
bus6.execute(AddAtomCommand(7, 4.0, 0.0, 0.0, auto_bond_nearest=True))
d6 = float(np.linalg.norm(doc6.coordinates.current.coords[0] - doc6.coordinates.current.coords[1]))
check("3D 点击空白自动成键且键长校准为 元素相关估算 1.47 Å（C–N）", doc6.num_bonds == 1 and abs(d6 - 1.47) < 0.01)
doc6.coordinates.current.coords[1] = [3.5, 0.0, 0.0]
bus6.execute(CleanGeometry3DCommand(max_iters=80))
d6_opt = float(np.linalg.norm(doc6.coordinates.current.coords[0] - doc6.coordinates.current.coords[1]))
check("CleanGeometry3DCommand 将拉长键恢复至合理共价键长", abs(d6_opt - 1.46) < 0.05)

print("\n" + "=" * 64)
print(f"结果：{passed} 通过, {failed} 失败")
print("=" * 64)
sys.exit(1 if failed else 0)

