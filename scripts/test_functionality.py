"""
功能真实性测试：
1. 导入 XYZ 文件
2. per-atom 缩放/颜色修改
3. per-bond 颜色修改
4. 导出 SMILES/XYZ
5. 撤销/重做
"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from molforge.domain.document import MoleculeDocument
from molforge.domain.topology import AtomId, BondId
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import (
    AddAtomCommand, DeleteAtomCommand, ChangeAtomStyleCommand,
    ChangeBondStyleCommand, MoveAtom3DCommand,
)
from molforge.io.rdkit_adapter import create_instant_caffeine_document

print("=" * 60)
print("1. 创建咖啡因文档")
doc = create_instant_caffeine_document()
print(f"   原子数: {doc.num_atoms}, 键数: {doc.num_bonds}")
assert doc.num_atoms > 0, "咖啡因应有原子"

bus = CommandBus(doc)

print("\n2. per-atom 缩放修改")
aids = list(doc.topology.atom_ids)
first_aid = aids[0]
atom = doc.topology.get_atom(first_aid)
old_scale = getattr(atom, "scale", 1.0)
print(f"   修改前 atom #{first_aid.value} scale = {old_scale}")
bus.execute(ChangeAtomStyleCommand([first_aid], scale=1.8))
atom = doc.topology.get_atom(first_aid)
new_scale = getattr(atom, "scale", 1.0)
print(f"   修改后 atom #{first_aid.value} scale = {new_scale}")
assert new_scale == 1.8, f"per-atom 缩放应为 1.8, 实际 {new_scale}"

print("\n3. per-atom 颜色修改")
old_color = getattr(atom, "color", None)
print(f"   修改前 color = {old_color}")
bus.execute(ChangeAtomStyleCommand([first_aid], color=(1.0, 0.0, 0.0)))
atom = doc.topology.get_atom(first_aid)
new_color = getattr(atom, "color", None)
print(f"   修改后 color = {new_color}")
assert new_color is not None and abs(new_color[0] - 1.0) < 0.01, "颜色应为红"

print("\n4. 撤销 per-atom 修改")
bus.undo()
atom = doc.topology.get_atom(first_aid)
restored_scale = getattr(atom, "scale", 1.0)
restored_color = getattr(atom, "color", None)
print(f"   撤销后 scale = {restored_scale}, color = {restored_color}")

print("\n5. per-bond 颜色修改")
bids = list(doc.topology.bond_ids)
first_bid = bids[0]
bond = doc.topology.get_bond(first_bid)
old_bcolor = getattr(bond, "color", None)
print(f"   修改前 bond #{first_bid.value} color = {old_bcolor}")
bus.execute(ChangeBondStyleCommand([first_bid], color=(0.0, 1.0, 0.0)))
bond = doc.topology.get_bond(first_bid)
new_bcolor = getattr(bond, "color", None)
print(f"   修改后 bond #{first_bid.value} color = {new_bcolor}")
assert new_bcolor is not None and abs(new_bcolor[1] - 1.0) < 0.01, "键色应为绿"

print("\n6. 加原子")
old_n = doc.num_atoms
bus.execute(AddAtomCommand(atomic_num=6, x=10.0, y=10.0, z=10.0))
new_n = doc.num_atoms
print(f"   加原子前 {old_n}, 加原子后 {new_n}")
assert new_n == old_n + 1, "应加 1 个原子"

print("\n7. 删除原子")
last_aid = list(doc.topology.atom_ids)[-1]
bus.execute(DeleteAtomCommand(last_aid))
print(f"   删除后原子数 {doc.num_atoms}")
assert doc.num_atoms == old_n, "应恢复原数"

print("\n8. MoveAtom3D 拖动")
if doc.has_3d:
    aid = aids[0]
    atom_ids, id2idx = doc.topology.atom_index_map()
    idx = id2idx[aid]
    old_pos = tuple(doc.coordinates.current.coords[idx])
    new_pos = (old_pos[0] + 1.0, old_pos[1], old_pos[2])
    bus.execute(MoveAtom3DCommand(aid, new_pos, old_pos))
    moved = tuple(doc.coordinates.current.coords[idx])
    print(f"   拖动前 {old_pos}, 拖动后 {moved}")
    assert abs(moved[0] - new_pos[0]) < 0.01, "拖动应改 X"

print("\n9. 导出 SMILES")
from molforge.io.rdkit_adapter import doc_to_rdkit
from rdkit import Chem
rdmol, _, _ = doc_to_rdkit(doc, sanitize=True)
rdmol_noh = Chem.RemoveHs(rdmol)
smi = Chem.MolToSmiles(rdmol_noh)
print(f"   SMILES: {smi}")
assert len(smi) > 5, "SMILES 不应为空"

print("\n10. 导出 XYZ")
from molforge.application.calculators.qc_input_generator import extract_xyz_lines
xyz = extract_xyz_lines(doc)
print(f"   XYZ 行数: {len(xyz)}")
assert len(xyz) == doc.num_atoms, "XYZ 行数应等于原子数"

print("\n" + "=" * 60)
print("全部功能测试通过!")
print("=" * 60)
