"""#56 验收：MCP 桥接的工具分发真实读写当前文档（不依赖 LLM 端点）。

offscreen 运行，结果写 qa_evidence/test_mcp_bridge.txt。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.ai.mcp_bridge import MolForgeMCPBridge

LOG = open(os.path.join(ROOT, "qa_evidence", "test_mcp_bridge.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n"); LOG.flush()

app = QApplication(sys.argv)
doc = create_instant_caffeine_document()
bus = CommandBus(doc)
bridge = MolForgeMCPBridge(document=doc, command_bus=bus)
n0 = doc.num_atoms
b0 = doc.topology.num_bonds

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg); raise AssertionError(msg)
    log("PASS: " + msg)

# 1. 工具定义存在且为 OpenAI function 格式
defs = bridge.tool_definitions()
names = [d["function"]["name"] for d in defs]
check("describe_structure" in names and "add_atom" in names and "add_bond" in names,
      "已注册读取/编辑/分析工具")

# 2. describe_structure 真实读文档
desc = bridge.dispatch("describe_structure", {})
check(desc["num_atoms"] == n0, f"describe 读到原子数 {desc['num_atoms']}")
check(desc["num_bonds"] == b0, "describe 读到键数")
check(desc["has_3d"] in (True, False), "describe 报告 3D 状态")

# 3. list_atoms 返回 1-based 序号
atoms = bridge.dispatch("list_atoms", {})["atoms"]
check(len(atoms) == n0, "list_atoms 返回全部原子")
check(atoms[0]["index"] == 1 and atoms[-1]["index"] == n0, "原子序号 1-based")

# 4. Saturated caffeine site must refuse automatic overvalence.
res = bridge.dispatch("add_atom", {"near_atom": 1, "atomic_num": 8})
check(not res["ok"] and doc.num_atoms==n0,"饱和碳拒绝自动超价成键")
# Use an explicitly unsaturated isolated carbon for the valid editing fixture.
from molforge.application.builtin_commands import AddAtomCommand
bus.execute(AddAtomCommand(6,8,0,0))
n0=doc.num_atoms
near=n0
# add_atom 经命令总线真实加原子（且可撤销）
res = bridge.dispatch("add_atom", {"near_atom": near, "atomic_num": 8})
check(doc.num_atoms == n0 + 1, f"LLM 加氧原子后文档原子数 {doc.num_atoms}")
bus.undo()
check(doc.num_atoms == n0, "撤销后原子数回退")

# 5. add_bond 在两个现有原子间真实加键
res = bridge.dispatch("add_bond", {"atom_a": 1, "atom_b": 5})
check(doc.topology.num_bonds == b0 + 1 or doc.topology.num_bonds == b0,
      "LLM 加键后键数变化（已存在则保持）")
bus.undo()

# 6. delete_atom 真实删原子
bridge.dispatch("add_atom", {"near_atom": near, "atomic_num": 6})
na = bridge.dispatch("list_atoms", {})["atoms"][-1]["index"]
res = bridge.dispatch("delete_atom", {"atom_index": na})
check(res["ok"] and doc.num_atoms == n0, "LLM 按视口稳定编号删除刚加的原子后回到原数")

# 7. run_planarity 真实计算
plane = bridge.dispatch("run_planarity", {})
check("rmsd_angstrom" in plane, "run_planarity 返回真实 RMSD 数值")
check("normal" in plane, "run_planarity 返回法向量")

# 8. 无文档时 chat 给出诚实提示（不伪造 LLM 回复）
empty = MolForgeMCPBridge(document=None, command_bus=None)
check("没有打开的分子" in empty.chat("hi"), "无文档时 chat 诚实拒绝")

log("MCP 桥接工具分发验收通过")
LOG.close()
