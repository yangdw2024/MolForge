"""
molforge/ai/mcp/mcp_server.py - 工业标准 Model Context Protocol (MCP) 服务端
========================================================================
遵循 Anthropic / Open Protocol 标准 (JSON-RPC 2.0 stdio):
  - 允许外部 AI Agent (Claude 3.7/3.5, Gemini 2.0, DeepSeek R1, GPT-4o, Cursor, Antigravity)
    作为智能大脑直接通过 MCP 协议感知并控制 MolForge！
  - 导出四大核心能力：
    1. Tools: 分子几何感知、原子编辑(加/删/连键)、精确内坐标微调、CalChem 原生量化计算、Linux Slurm HPC 任务打包
    2. Resources: 当前活动分子结构 (molecule://active/json, molecule://active/xyz)
    3. Prompts: 预置化学家专家提示词 (DFT计算向导、构象搜索、机理推导)
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional
import numpy as np

# 强制 UTF-8 标准输入输出 (MCP 工业协议规范强制要求)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

MCP_PROTOCOL_VERSION = "2024-11-05"


class MolForgeMCPServer:
    """基于标准 JSON-RPC 2.0 的 MolForge MCP 服务端。"""

    def __init__(self, document=None, command_bus=None):
        self.document = document
        self.command_bus = command_bus
        self._tools: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._register_default_tools()

    def set_context(self, document, command_bus=None):
        self.document = document
        self.command_bus = command_bus

    def _aid_at_1based(self, idx: int):
        if not self.document:
            return None
        atoms = list(self.document.topology.atom_ids)
        return next((aid for aid in atoms if aid.value + 1 == idx), None)

    def _register_default_tools(self) -> None:
        self._tools["get_molecule_info"] = self._tool_get_molecule_info
        self._tools["add_atom"] = self._tool_add_atom
        self._tools["delete_atom"] = self._tool_delete_atom
        self._tools["add_bond"] = self._tool_add_bond
        self._tools["modify_internal_coordinate"] = self._tool_modify_internal_coordinate
        self._tools["run_calchem_scf"] = self._tool_run_calchem_scf
        self._tools["run_calchem_opt"] = self._tool_run_calchem_opt
        self._tools["generate_hpc_slurm_script"] = self._tool_generate_hpc_slurm_script
        self._tools["run_planarity"] = self._tool_run_planarity
        self._tools["run_rest_scf"] = self._tool_run_rest_scf

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_molecule_info",
                "description": "获取 MolForge 当前活动分子的完整化学信息（化学式、原子序数、3D 坐标、点群、电荷与自旋）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "add_atom",
                "description": "在指定已有原子附近添加一个新原子，或在指定 3D 坐标处添加原子（通过命令总线执行，支持可撤销）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "near_atom": {"type": "integer", "description": "参考原子的 1-based 序号", "minimum": 1},
                        "atomic_num": {"type": "integer", "description": "新原子的原子序数 (1~118)", "minimum": 1, "maximum": 118},
                        "x": {"type": "number", "description": "可选绝对 X 坐标 (Å)"},
                        "y": {"type": "number", "description": "可选绝对 Y 坐标 (Å)"},
                        "z": {"type": "number", "description": "可选绝对 Z 坐标 (Å)"},
                    },
                    "required": ["atomic_num"],
                },
            },
            {
                "name": "delete_atom",
                "description": "删除指定 1-based 序号的原子及其相关化学键（通过命令总线执行，支持可撤销）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "atom_index": {"type": "integer", "description": "要删除原子的 1-based 序号", "minimum": 1},
                    },
                    "required": ["atom_index"],
                },
            },
            {
                "name": "add_bond",
                "description": "在两个已有原子之间添加化学键（通过命令总线执行，支持可撤销）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "atom_a": {"type": "integer", "description": "第一个原子 1-based 序号", "minimum": 1},
                        "atom_b": {"type": "integer", "description": "第二个原子 1-based 序号", "minimum": 1},
                    },
                    "required": ["atom_a", "atom_b"],
                },
            },
            {
                "name": "modify_internal_coordinate",
                "description": "严格保序精确修改分子的内坐标（键长/键角/二面角），自动联动旋转连通子图刚体几何，保持其他键长不变（可撤销）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "coord_type": {
                            "type": "string",
                            "enum": ["bond_length", "bond_angle", "dihedral"],
                            "description": "内坐标类型",
                        },
                        "atoms": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "原子编号列表 (1-based序号)。键长需2个，键角需3个(中间为顶点)，二面角需4个。",
                        },
                        "target_value": {
                            "type": "number",
                            "description": "目标数值（键长单位为 Å，键角/二面角单位为度 °）",
                        },
                    },
                    "required": ["coord_type", "atoms", "target_value"],
                },
            },
            {
                "name": "run_calchem_scf",
                "description": "调用 CalChem 纯 Rust 内核秒级执行从头算 RHF 自洽场计算，获取精确总能量、HOMO/LUMO 能级、能隙与偶极矩。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "basis": {
                            "type": "string",
                            "enum": ["sto-3g", "6-31g", "6-31g(d)", "6-31g(d,p)", "lanl2dz"],
                            "default": "sto-3g",
                            "description": "量化计算基组",
                        },
                    },
                },
            },
            {
                "name": "run_calchem_opt",
                "description": "调用 CalChem 纯 Rust BFGS 算法执行高精度 3D 几何构象优化，并自动通过命令总线回填更新视口（支持可撤销）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "basis": {"type": "string", "default": "sto-3g"},
                        "max_steps": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "generate_hpc_slurm_script",
                "description": "为当前分子生成可直接提交至远程 Linux 超算集群运行的 Slurm 批处理计算脚本 (Gaussian/ORCA/GROMACS/CalChem)。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "engine": {"type": "string", "enum": ["g16", "orca", "gromacs", "xtb", "calchem"]},
                        "job_name": {"type": "string", "default": "chem_calc"},
                        "n_cores": {"type": "integer", "default": 16},
                        "memory_mb": {"type": "integer", "default": 32000},
                        "walltime": {"type": "string", "default": "24:00:00"},
                    },
                    "required": ["engine"],
                },
            },
            {
                "name": "run_planarity",
                "description": "对当前分子计算重原子最佳拟合平面的平面度 RMSD（MPP）与最大离面距离。",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "run_rest_scf",
                "description": "在 WSL2 环境中调用复旦大学 REST (Rust-based Electronic Structure Toolkit) 原生执行真实 DFT/双杂化 SCF 计算，获取总能量、Mulliken 电荷与轨道能隙。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "xc": {
                            "type": "string",
                            "enum": ["b3lyp", "hf", "pbe0", "wb97xd", "cam-b3lyp", "xyg3", "xygjos", "r-xdh7"],
                            "default": "b3lyp",
                            "description": "交换相关泛函或双杂化方法",
                        },
                        "basis": {
                            "type": "string",
                            "enum": ["STO-3G", "def2-SVP", "def2-TZVP", "6-31G*", "cc-pVDZ"],
                            "default": "def2-SVP",
                            "description": "基组名称",
                        },
                    },
                },
            },
        ]

    # ---------- 具体工具逻辑实现 ----------
    def _tool_get_molecule_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "当前未加载分子文档"}
        doc = self.document
        atom_ids = list(doc.topology.atom_ids)
        atoms = []
        for aid in atom_ids:
            a = doc.topology.get_atom(aid)
            pos = doc.get_atom_3d_pos(aid) if doc.has_3d else None
            atoms.append({
                "index": aid.value + 1,
                "atomic_num": a.atomic_num,
                "symbol": getattr(a, "symbol", "X"),
                "xyz": pos.tolist() if pos is not None else None,
            })
        return {
            "name": doc.name,
            "num_atoms": doc.num_atoms,
            "num_bonds": doc.topology.num_bonds,
            "has_3d": doc.has_3d,
            "formula": doc.formula if hasattr(doc, "formula") else "",
            "atoms": atoms,
        }

    def _tool_add_atom(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...application.builtin_commands import AddAtomCommand
        near_atom = args.get("near_atom")
        aid = self._aid_at_1based(near_atom) if near_atom is not None else None
        if near_atom is not None and aid is None:
            return {"error": f"参考原子 #{near_atom} 越界", "success": False}
        x = args.get("x")
        y = args.get("y")
        z = args.get("z")
        bus = self.command_bus
        if not bus:
            from ...application.command_bus import CommandBus
            bus = CommandBus(self.document)
        res = bus.execute(AddAtomCommand(
            atomic_num=args.get("atomic_num", 6),
            x=x, y=y, z=z,
            bond_to=aid,
        ))
        if not getattr(res, "success", True):
            return {"error": getattr(res, "message", "添加原子失败"), "success": False}
        return {
            "success": True,
            "message": getattr(res, "message", ""),
            "num_atoms": self.document.num_atoms,
        }

    def _tool_delete_atom(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...application.builtin_commands import DeleteAtomCommand
        aid = self._aid_at_1based(args["atom_index"])
        if aid is None:
            return {"error": f"原子 #{args['atom_index']} 越界"}
        bus = self.command_bus
        if not bus:
            from ...application.command_bus import CommandBus
            bus = CommandBus(self.document)
        res = bus.execute(DeleteAtomCommand(aid))
        return {
            "success": getattr(res, "success", True),
            "message": getattr(res, "message", ""),
            "num_atoms": self.document.num_atoms,
        }

    def _tool_add_bond(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...application.builtin_commands import AddBondCommand
        a = self._aid_at_1based(args["atom_a"])
        b = self._aid_at_1based(args["atom_b"])
        if a is None or b is None:
            return {"error": "成键原子编号越界"}
        bus = self.command_bus
        if not bus:
            from ...application.command_bus import CommandBus
            bus = CommandBus(self.document)
        res = bus.execute(AddBondCommand(a, b, order=1))
        return {
            "success": getattr(res, "success", True),
            "message": getattr(res, "message", ""),
            "num_bonds": self.document.topology.num_bonds,
        }

    def _tool_run_calchem_scf(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...io.calchem_bridge import run_calchem_single_point
        basis = args.get("basis", "sto-3g")
        res = run_calchem_single_point(self.document, basis=basis)
        if not res.get("success"):
            return {"error": res.get("error", "计算失败")}
        return {
            "converged": res["converged"],
            "total_energy_hartree": res["total_energy_hartree"],
            "homo_energy_hartree": res["homo_energy_hartree"],
            "lumo_energy_hartree": res["lumo_energy_hartree"],
            "gap_ev": res["gap_ev"],
            "dipole_debye": res["dipole_debye"],
        }

    def _tool_run_calchem_opt(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...io.calchem_bridge import run_calchem_optimization
        basis = args.get("basis", "sto-3g")
        max_steps = args.get("max_steps", 50)
        res = run_calchem_optimization(self.document, basis=basis, max_steps=max_steps)
        if not res.get("success"):
            return {"error": res.get("error", "优化失败")}
        if self.command_bus and "command" in res:
            self.command_bus.execute(res["command"])
        return {
            "converged": res["converged"],
            "steps": res["steps"],
            "final_energy_hartree": res["energy_hartree"],
            "applied_to_viewport": bool(self.command_bus),
        }

    def _tool_modify_internal_coordinate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...domain.ids import AtomId
        ctype = args["coord_type"]
        atoms = [AtomId(x - 1) for x in args["atoms"]]
        val = float(args["target_value"])

        if ctype == "bond_length" and len(atoms) == 2:
            from ...application.builtin_commands import ModifyBondLength3DCommand
            bid = self.document.topology.bond_between(atoms[0], atoms[1])
            if bid is None:
                return {"error": f"原子 #{args['atoms'][0]} 与 #{args['atoms'][1]} 之间不存在化学键"}
            cmd = ModifyBondLength3DCommand(bid, val)
        elif ctype == "bond_angle" and len(atoms) == 3:
            from ...application.internal_coordinates import ModifyAngle3DCommand
            cmd = ModifyAngle3DCommand(atoms[0], atoms[1], atoms[2], val)
        elif ctype == "dihedral" and len(atoms) == 4:
            from ...application.internal_coordinates import ModifyDihedral3DCommand
            cmd = ModifyDihedral3DCommand(atoms[0], atoms[1], atoms[2], atoms[3], val)
        else:
            return {"error": f"不合法的内坐标修改参数 (type={ctype}, atoms={args['atoms']})"}

        bus = self.command_bus
        if not bus:
            from ...application.command_bus import CommandBus
            bus = CommandBus(self.document)
        r = bus.execute(cmd)
        return {"success": r.success, "message": r.message}

    def _tool_generate_hpc_slurm_script(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from ...infrastructure.hpc.slurm_generator import SlurmScriptGenerator, JobSpec
        from ...infrastructure.hpc.cluster_config import ClusterProfile
        eng = args["engine"]
        job = JobSpec(
            job_name=args.get("job_name", "chem_job"),
            engine=eng,
            input_file=f"input.{'gjf' if eng == 'g16' else 'inp'}",
            output_file=f"output.{'log' if eng == 'g16' else 'out'}",
            n_cores=args.get("n_cores", 16),
            memory_mb=args.get("memory_mb", 32000),
            walltime=args.get("walltime", "24:00:00"),
        )
        script = SlurmScriptGenerator.generate(job, ClusterProfile())
        return {"engine": eng, "slurm_script": script}

    def _tool_run_planarity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...application.calculators.qc_input_generator import export_document_to_xyz
        from ...workflows.planarity_analysis import run_planarity_workflow
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "molforge_mcp_plane.xyz")
        export_document_to_xyz(self.document, tmp)
        out = run_planarity_workflow(tmp, tempfile.gettempdir())
        summary_path = os.path.join(str(out), "planarity.json")
        with open(summary_path, encoding="utf-8") as fh:
            return json.load(fh)

    def _tool_run_rest_scf(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document:
            return {"error": "未找到当前分子"}
        from ...application.calculators.rest_engine import RestEngine
        engine = RestEngine()
        if not engine.probe():
            return {"error": "未检测到本地 WSL2 REST 虚拟环境 (/home/administrator/miniforge3/envs/rest-py311/bin/rest)"}
        xc = args.get("xc", "b3lyp")
        basis = args.get("basis", "def2-SVP")
        res = engine.run_calculation(self.document, xc=xc, basis=basis)
        if not res.get("ok"):
            return {"error": "REST 计算未正常收敛或执行失败", "details": res}
        return res

    # ---------- JSON-RPC 2.0 协议主分发器 ----------
    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {"name": "molforge-mcp-server", "version": "8.0.0"},
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                },
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_definitions()},
            }
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name in self._tools:
                try:
                    res = self._tools[name](arguments)
                    is_err = bool(res.get("error"))
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "isError": is_err,
                            "content": [
                                {"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}
                            ],
                        },
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": f"Tool execution failed: {str(e)}"}],
                        },
                    }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method/Tool '{name}' not found"},
            }
        elif method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {
                            "uri": "molecule://active/json",
                            "name": "Current Active Molecule JSON",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "molecule://active/xyz",
                            "name": "Current Active Molecule XYZ",
                            "mimeType": "chemical/x-xyz",
                        },
                    ]
                },
            }
        elif method == "resources/read":
            uri = params.get("uri", "")
            if not self.document:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "No active molecule loaded"},
                }
            if uri == "molecule://active/json":
                from ...io.mforge_storage import serialize_document_to_dict
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(serialize_document_to_dict(self.document), ensure_ascii=False, indent=2),
                            }
                        ]
                    },
                }
            elif uri == "molecule://active/xyz":
                from ...application.calculators.qc_input_generator import extract_xyz_lines
                lines = extract_xyz_lines(self.document)
                xyz_text = f"{self.document.num_atoms}\n{self.document.name}\n" + "\n".join(lines) + "\n"
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "chemical/x-xyz",
                                "text": xyz_text,
                            }
                        ]
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Resource URI '{uri}' not found"},
            }
        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "prompts": [
                        {
                            "name": "dft_optimization_guide",
                            "description": "量子化学 DFT 几何构型优化向导提示词",
                        },
                        {
                            "name": "conformer_search_advisor",
                            "description": "分子柔性构象搜索与低能构象聚类向导",
                        },
                    ]
                },
            }
        elif method == "prompts/get":
            pname = params.get("name", "")
            if pname == "dft_optimization_guide":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "description": "量子化学 DFT 几何构型优化向导",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": "你是一位资深计算化学家。请检查当前分子的 3D 构象合理性，建议合适的 DFT 泛函与基组（如 B3LYP-D3BJ/def2-SVP），并通过 modify_internal_coordinate 或 run_calchem_opt 协助用户完成预优化。",
                                },
                            }
                        ],
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Prompt '{pname}' not found"},
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unsupported MCP method: {method}"},
        }

    def run_stdio_loop(self) -> None:
        """从标准输入读取 JSON-RPC 消息并写入标准输出。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    from ...io.rdkit_adapter import create_sample_molecule
    from ...application.command_bus import CommandBus
    doc = create_sample_molecule("咖啡因")
    bus = CommandBus(doc)
    server = MolForgeMCPServer(doc, bus)
    server.run_stdio_loop()

