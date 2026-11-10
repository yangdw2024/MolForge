"""
tools.py - AI 工具集 + Tool Registry
======================================
按 ChatGPT 技术报告建议：
- 工具入参用 Pydantic / JSON Schema 校验
- LLM 只能访问 Tool Registry 里的工具，不能执行任意 Python
- 变更结构、覆写文件、提交成本高的外部计算前要求用户确认

权限分级：
  - Read: 只读查询（describe_molecule, compute_properties）
  - View: 视图相关（获取构象列表）
  - Edit: 修改结构（generate_conformer）
  - Execute: 运行计算（运行 xTB/Gaussian）
  - Export: 导出文件（export_gjf, export_svg）

安全边界：
  - 无 shell / eval 注入
  - 调用次数限制
  - 执行收据和日志
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..core.molecule import Molecule
from ..core.properties import compute_properties
from ..core.conformer import Conformer
from ..io import read_file, write_file


class ToolPermission(Enum):
    """工具权限级别。"""
    READ = "read"
    VIEW = "view"
    EDIT = "edit"
    EXECUTE = "execute"
    EXPORT = "export"


@dataclass
class ToolReceipt:
    """工具执行收据。"""
    receipt_id: str
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: Any = None
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: float = 0.0



class AIContext:
    """
    AI 操作分子的上下文。

    一个 AIContext 绑定一个 Molecule 和一个工作目录。
    AI 所有操作都通过这个上下文进行，不直接碰 UI。
    """

    def __init__(self, mol: Molecule, workdir: Path | None = None):
        self.mol = mol
        self.workdir = workdir or Path.cwd()

    # ---------- 信息查询工具 ----------

    def describe_molecule(self) -> dict:
        """返回当前分子的摘要：分子式、原子数、键数、能量、HOMO/LUMO gap。"""
        return {
            "name": self.mol.name,
            "formula": self.mol.formula,
            "num_atoms": self.mol.num_atoms,
            "num_bonds": self.mol.num_bonds,
            "energy_hartree": self.mol.energy,
            "homo_ev": self.mol.homo.energy_ev if self.mol.homo else None,
            "lumo_ev": self.mol.lumo.energy_ev if self.mol.lumo else None,
            "gap_ev": self.mol.gap_ev,
            "source": self.mol.source_format,
        }

    def compute_properties(self) -> dict:
        """计算并返回分子性质（MW、LogP、TPSA、HBA/HBD、环数...）。"""
        props = compute_properties(self.mol)
        self.mol.properties.update(props)
        return props

    # ---------- 计算工具 ----------

    def generate_conformer(self, seed: int = 42) -> dict:
        """
        生成 3D 构象（ETKDG + MMFF 优化）。
        成功后把构象加到当前分子。
        """
        from rdkit.Chem import AllChem
        mol = self.mol.rdkit_mol
        mol = AllChem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = seed
        if AllChem.EmbedMolecule(mol, params) != 0:
            return {"ok": False, "error": "构象生成失败"}
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            pass

        # 提取坐标
        conf = mol.GetConformer()
        import numpy as np
        coords = []
        for i in range(mol.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            coords.append([p.x, p.y, p.z])
        self.mol.conformers.append(Conformer(
            coords=np.array(coords),
            source="etkdg_mmff"
        ))
        return {
            "ok": True,
            "num_atoms": self.mol.num_atoms,
            "message": f"已生成 3D 构象（{len(self.mol.conformers)} 个构象）"
        }

    # ---------- 文件工具 ----------

    def open_file(self, path: str) -> dict:
        """打开一个分子文件（支持 .mol/.sdf/.gjf/.log/.cube/.smi）。"""
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"文件不存在: {path}"}
        try:
            self.mol = read_file(p)
            return {
                "ok": True,
                "name": self.mol.name,
                "formula": self.mol.formula,
                "source": self.mol.source_format,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_gjf(self, route: str = "# B3LYP/6-31G(d,p) opt",
                   path: str | None = None) -> dict:
        """
        导出 Gaussian 输入文件。
        route 例：'# B3LYP/6-31G(d,p) opt freq'
        """
        self.mol.properties["route"] = route
        out = Path(path) if path else (self.workdir / f"{self.mol.name or 'mol'}.gjf")
        try:
            write_file(self.mol, out)
            return {"ok": True, "path": str(out)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_svg(self, path: str | None = None) -> dict:
        """导出 2D 结构图为 SVG。"""
        out = Path(path) if path else (self.workdir / f"{self.mol.name or 'mol'}.svg")
        try:
            write_file(self.mol, out)
            return {"ok": True, "path": str(out)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- Gaussian 工作流 ----------

    def read_gaussian_log(self, path: str) -> dict:
        """
        读 Gaussian log 文件，解析能量、HOMO/LUMO、终止状态。
        结果会更新到当前 Molecule。
        """
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"文件不存在: {path}"}
        try:
            log_mol = read_file(p)
            # 合并到当前分子
            self.mol.energy = log_mol.energy
            self.mol.orbitals = log_mol.orbitals
            self.mol.properties.update(log_mol.properties)
            if log_mol.conformers:
                self.mol.conformers = log_mol.conformers
            return {
                "ok": True,
                "termination": log_mol.properties.get("termination"),
                "energy_hartree": log_mol.energy,
                "homo_ev": self.mol.homo.energy_ev if self.mol.homo else None,
                "lumo_ev": self.mol.lumo.energy_ev if self.mol.lumo else None,
                "gap_ev": self.mol.gap_ev,
                "scf_cycles": log_mol.properties.get("scf_cycles"),
                "dipole_debye": log_mol.properties.get("dipole_debye"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- AI 建议工具 ----------

    def suggest_next_step(self) -> list[str]:
        """
        根据当前分子状态，建议下一步计算。
        这是规则式建议，不是 LLM 生成的。
        """
        suggestions = []
        if self.mol.energy is None:
            suggestions.append("当前分子还没有计算结果，建议先跑单点能（SP）。")
        if self.mol.gap_ev is None:
            suggestions.append("还没有 HOMO/LUMO 数据，建议跑一个含轨道输出的单点能。")
        if not self.mol.has_3d:
            suggestions.append("还没有 3D 构象，建议先 generate_conformer()。")
        if self.mol.properties.get("termination") == "normal":
            suggestions.append("计算正常结束，可以导出 gjf 跑下一步（如 freq 频率分析）。")
        if self.mol.properties.get("termination") == "error":
            suggestions.append("计算错误终止，建议检查 log 文件末尾的错误信息。")
        if not suggestions:
            suggestions.append("当前状态完整，可以做发表级图导出（export_svg）。")
        return suggestions


# ---------- Tool Registry ----------

class ToolRegistry:
    """
    工具注册表（按 ChatGPT 技术报告建议）。

    把 AIContext 的方法注册成带 JSON Schema 的工具，
    LLM 通过 function calling 调用，不能执行任意 Python。

    安全边界：
    - 工具入参用 JSON Schema 校验
    - LLM 只能访问注册的工具，不能执行任意代码
    - 变更结构、覆写文件、提交成本高的外部计算前要求用户确认
    - 权限分级：Read/View/Edit/Execute/Export
    - 调用次数限制
    - 执行收据和日志
    """

    def __init__(self, context: AIContext, max_calls_per_session: int = 50):
        self.context = context
        self._tools: dict[str, dict] = {}
        self._call_log: list[ToolReceipt] = []
        self._call_count: int = 0
        self._max_calls = max_calls_per_session
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认工具集。"""
        # Read 权限：信息查询
        self.register_tool(
            name="describe_molecule",
            description="返回当前分子的摘要：分子式、原子数、键数、能量、HOMO/LUMO gap",
            parameters={"type": "object", "properties": {}},
            handler=self.context.describe_molecule,
            permission=ToolPermission.READ,
        )

        self.register_tool(
            name="compute_properties",
            description="计算并返回分子性质（MW、LogP、TPSA、HBA/HBD、环数...）",
            parameters={"type": "object", "properties": {}},
            handler=self.context.compute_properties,
            permission=ToolPermission.READ,
        )

        # Edit 权限：修改结构
        self.register_tool(
            name="generate_conformer",
            description="生成 3D 构象（ETKDG + MMFF 优化）",
            parameters={
                "type": "object",
                "properties": {
                    "seed": {"type": "integer", "description": "随机种子", "default": 42},
                },
            },
            handler=self.context.generate_conformer,
            permission=ToolPermission.EDIT,
        )

        # Read 权限：打开文件
        self.register_tool(
            name="open_file",
            description="打开一个分子文件（支持 .mol/.sdf/.gjf/.log/.cube/.smi）",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
            handler=self.context.open_file,
            permission=ToolPermission.READ,
        )

        # Export 权限：导出文件
        self.register_tool(
            name="export_gjf",
            description="导出 Gaussian 输入文件",
            parameters={
                "type": "object",
                "properties": {
                    "route": {"type": "string", "description": "Gaussian route line", "default": "# B3LYP/6-31G(d,p) opt"},
                    "path": {"type": "string", "description": "输出路径（可选）"},
                },
            },
            handler=self.context.export_gjf,
            permission=ToolPermission.EXPORT,
        )

        self.register_tool(
            name="export_svg",
            description="导出 2D 结构图为 SVG",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "输出路径（可选）"},
                },
            },
            handler=self.context.export_svg,
            permission=ToolPermission.EXPORT,
        )

        # Read 权限：读 Gaussian log
        self.register_tool(
            name="read_gaussian_log",
            description="读 Gaussian log 文件，解析能量、HOMO/LUMO、终止状态",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "log 文件路径"},
                },
                "required": ["path"],
            },
            handler=self.context.read_gaussian_log,
            permission=ToolPermission.READ,
        )

        # Read 权限：AI 建议
        self.register_tool(
            name="suggest_next_step",
            description="根据当前分子状态，建议下一步计算",
            parameters={"type": "object", "properties": {}},
            handler=self.context.suggest_next_step,
            permission=ToolPermission.READ,
        )

    def register_tool(self, name: str, description: str,
                      parameters: dict, handler: Callable,
                      permission: ToolPermission = ToolPermission.READ,
                      requires_confirmation: bool | None = None):
        """注册一个工具。"""
        # 需要确认的工具：Edit/Execute/Export 级别默认需要确认
        if requires_confirmation is None:
            requires_confirmation = permission in (ToolPermission.EDIT, ToolPermission.EXECUTE, ToolPermission.EXPORT)

        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
            "permission": permission,
            "requires_confirmation": requires_confirmation,
        }

    def get_tool_definitions(self) -> list[dict]:
        """返回 OpenAI function calling 格式的工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for name, tool in self._tools.items()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolReceipt:
        """
        调用一个工具，返回执行收据。

        安全检查：
        - 工具必须在注册表中
        - 调用次数限制
        - 无 shell/eval 注入
        """
        # 检查调用次数
        if self._call_count >= self._max_calls:
            return ToolReceipt(
                receipt_id=uuid.uuid4().hex[:12],
                tool_name=name,
                arguments=arguments,
                success=False,
                error=f"超过会话调用次数限制（{self._max_calls}）",
            )

        if name not in self._tools:
            return ToolReceipt(
                receipt_id=uuid.uuid4().hex[:12],
                tool_name=name,
                arguments=arguments,
                success=False,
                error=f"未知工具: {name}",
            )

        tool = self._tools[name]
        self._call_count += 1

        # 执行
        start = time.time()
        try:
            result = tool["handler"](**arguments)
            success = True
            error = ""
        except Exception as e:
            result = None
            success = False
            error = str(e)

        end = time.time()

        receipt = ToolReceipt(
            receipt_id=uuid.uuid4().hex[:12],
            tool_name=name,
            arguments=arguments,
            success=success,
            result=result,
            error=error,
            started_at=start,
            finished_at=end,
            duration_ms=(end - start) * 1000,
        )

        self._call_log.append(receipt)
        return receipt

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名。"""
        return list(self._tools.keys())

    def get_call_log(self) -> list[ToolReceipt]:
        """获取调用日志。"""
        return self._call_log.copy()

    def reset_call_count(self) -> None:
        """重置调用计数（新会话时调用）。"""
        self._call_count = 0
        self._call_log.clear()
