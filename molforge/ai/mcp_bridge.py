"""
mcp_bridge.py - MolForge 大语言模型桥接（OpenAI 兼容端点 + 真实 function calling）
=================================================================================
让外部 LLM（任意 OpenAI 兼容端点：本地 vLLM/Ollama/DeepSeek/OpenAI 等）能：
  1. 读取当前画布分子（原子/键/元素/坐标/公式）
  2. 通过命令总线真实编辑结构（加/删原子、加/删键、修改内坐标，可撤销）
  3. 调用本地分析与量子化学工具（平面性、CalChem SCF/Opt、超算 Slurm 脚本生成）

不引入 openai 第三方依赖，直接用标准库 urllib 调 /chat/completions；
所有结构修改必须经 CommandBus（带撤销），LLM 不能直接写文档。
配置从 QSettings("MolForge", "LLM") 读取：base_url / api_key / model。
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Optional

try:
    from PyQt6.QtCore import QSettings
except ImportError:
    QSettings = None

from ..application.builtin_commands import AddAtomCommand, DeleteAtomCommand, AddBondCommand


from pathlib import Path


def _config_file() -> Path:
    try:
        from ..runtime import data_dir
        d = data_dir() / "settings"
    except Exception:
        d = Path(__file__).resolve().parents[2] / "user_data" / "settings"
    d.mkdir(parents=True, exist_ok=True)
    return d / "llm_config.json"


def _settings() -> Optional[Any]:
    if QSettings is None:
        return None
    try:
        from ..runtime import configure_runtime
        configure_runtime()
        return QSettings("MolForge", "LLM")
    except Exception:
        return None


_CONFIG_CACHE: dict[str, str] = {}


def get_llm_config() -> dict[str, str]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE:
        return dict(_CONFIG_CACHE)
    """读取全局统一的大模型配置（打通右侧面板 AI_Config、独立弹窗 LLM 与 JSON 持久化存储，彻底杜绝割裂二次配置）。"""
    base_url = "http://127.0.0.1:8000/v1"
    api_key = "EMPTY"
    model = "default-model"

    # 1. 优先读取磁盘配置文件 (Single Source of Truth)
    cfg_file = _config_file()
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
                if isinstance(disk_data, dict):
                    if disk_data.get("base_url"):
                        base_url = str(disk_data["base_url"]).strip()
                    if disk_data.get("api_key"):
                        api_key = str(disk_data["api_key"]).strip()
                    if disk_data.get("model"):
                        model = str(disk_data["model"]).strip()
            return {
                "base_url": base_url or "http://127.0.0.1:8000/v1",
                "api_key": api_key or "EMPTY",
                "model": model or "default-model",
            }
        except Exception:
            pass

    # 2. 读取 QSettings("MolForge", "LLM")
    s_llm = _settings()
    if s_llm is not None:
        try:
            v_url = s_llm.value("base_url", "", str)
            v_key = s_llm.value("api_key", "", str)
            v_model = s_llm.value("model", "", str)
            if v_url: base_url = v_url.strip()
            if v_key: api_key = v_key.strip()
            if v_model: model = v_model.strip()
        except Exception:
            pass

    # 3. 读取 QSettings("MolForge", "AI_Config")
    if QSettings is not None:
        try:
            s_ai = QSettings("MolForge", "AI_Config")
            ai_url = s_ai.value("llm_base_url", "", str)
            ai_key = s_ai.value("deepseek_api_key", "", str)
            ai_model = s_ai.value("llm_model_name", "", str)
            if ai_url: base_url = ai_url.strip()
            if ai_key: api_key = ai_key.strip()
            if ai_model: model = ai_model.strip()
        except Exception:
            pass

    return {
        "base_url": base_url or "http://127.0.0.1:8000/v1",
        "api_key": api_key or "EMPTY",
        "model": model or "default-model",
    }


def set_llm_config(base_url: str, api_key: str, model: str) -> None:
    global _CONFIG_CACHE
    base_url = str(base_url).strip() or "http://127.0.0.1:8000/v1"
    api_key = str(api_key).strip() or "EMPTY"
    model = str(model).strip() or "default-model"
    _CONFIG_CACHE = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
    }
    """持久化保存大模型配置，同步写入 MolForge/LLM、MolForge/AI_Config 与本地 JSON 文件，保持 100% 同步。"""
    base_url = str(base_url).strip() or "http://127.0.0.1:8000/v1"
    api_key = str(api_key).strip() or "EMPTY"
    model = str(model).strip() or "default-model"

    # 1. 写入磁盘 JSON 文件 (单点真理)
    try:
        cfg_file = _config_file()
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            }, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # 2. 写入 QSettings("MolForge", "LLM")
    s_llm = _settings()
    if s_llm is not None:
        try:
            s_llm.setValue("base_url", base_url)
            s_llm.setValue("api_key", api_key)
            s_llm.setValue("model", model)
            s_llm.sync()
        except Exception:
            pass

    # 3. 写入 QSettings("MolForge", "AI_Config")
    if QSettings is not None:
        try:
            s_ai = QSettings("MolForge", "AI_Config")
            s_ai.setValue("llm_base_url", base_url)
            s_ai.setValue("deepseek_api_key", api_key)
            s_ai.setValue("llm_model_name", model)
            s_ai.sync()
        except Exception:
            pass


class MolForgeMCPBridge:
    """把当前 MoleculeDocument + CommandBus 暴露给 LLM 的 function-calling 桥。"""

    def __init__(self, document=None, command_bus=None):
        self.document = document
        self.command_bus = command_bus
        self.history: list[dict] = []
        self.config = get_llm_config()

    # ---------- 工具定义（OpenAI function calling 格式） ----------
    def tool_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "describe_structure",
                    "description": "返回当前画布分子的摘要：名称、公式、原子数、键数、元素统计、是否有3D坐标。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_atoms",
                    "description": "列出当前分子所有原子（视口稳定编号（AtomId+1，删除后可能不连续）、元素符号、3D 坐标）。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_atom",
                    "description": "在指定已有原子附近添加一个新原子（元素由 atomic_num 指定）。需要命令总线。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "near_atom": {"type": "integer", "description": "参考原子的视口稳定编号（AtomId+1，删除后可能不连续）", "minimum": 1},
                            "atomic_num": {"type": "integer", "description": "新原子的原子序数，如 6=C, 7=N, 8=O, 1=H", "minimum": 1},
                        },
                        "required": ["near_atom", "atomic_num"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_atom",
                    "description": "删除指定视口稳定编号（AtomId+1，删除后可能不连续）的原子（连带其键）。需要命令总线。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "atom_index": {"type": "integer", "description": "要删除原子的视口稳定编号（AtomId+1，删除后可能不连续）", "minimum": 1},
                        },
                        "required": ["atom_index"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_bond",
                    "description": "在两个视口稳定编号（AtomId+1，删除后可能不连续）的原子之间添加单键。需要命令总线。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "atom_a": {"type": "integer", "description": "第一个原子视口稳定编号（AtomId+1，删除后可能不连续）", "minimum": 1},
                            "atom_b": {"type": "integer", "description": "第二个原子视口稳定编号（AtomId+1，删除后可能不连续）", "minimum": 1},
                        },
                        "required": ["atom_a", "atom_b"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "modify_internal_coordinate",
                    "description": "精确修改分子的内坐标（键长/键角/二面角），自动联动旋转连通子图刚体几何，保持其他键长不变（可撤销）。",
                    "parameters": {
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
            },
            {
                "type": "function",
                "function": {
                    "name": "run_calchem_scf",
                    "description": "调用 CalChem 纯 Rust 内核秒级执行从头算 RHF 自洽场计算，获取精确总能量、HOMO/LUMO 能级、能隙与偶极矩。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "basis": {
                                "type": "string",
                                "enum": ["sto-3g", "6-31g", "6-31g(d)", "6-31g(d,p)", "lanl2dz"],
                                "description": "量化计算基组",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_calchem_opt",
                    "description": "调用 CalChem 纯 Rust BFGS 算法执行高精度 3D 几何构象优化，并自动通过命令总线回填更新视口（支持可撤销）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "basis": {"type": "string", "description": "量化计算基组"},
                            "max_steps": {"type": "integer", "description": "最大优化步数", "minimum": 1},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_hpc_slurm_script",
                    "description": "为当前分子生成可直接提交至远程 Linux 超算集群运行的 Slurm 批处理计算脚本 (Gaussian/ORCA/GROMACS/CalChem)。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "engine": {"type": "string", "enum": ["g16", "orca", "gromacs", "xtb", "calchem"], "description": "计算软件"},
                            "job_name": {"type": "string", "description": "作业名称"},
                            "n_cores": {"type": "integer", "description": "CPU核心数", "minimum": 1},
                            "memory_mb": {"type": "integer", "description": "内存限额 (MB)", "minimum": 100},
                            "walltime": {"type": "string", "description": "运行时长限制"},
                        },
                        "required": ["engine"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_planarity",
                    "description": "对当前分子计算重原子最佳拟合平面的平面度 RMSD（MPP）。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_rest_scf",
                    "description": "在 WSL2 环境中调用复旦大学 REST (Rust-based Electronic Structure Toolkit) 原生执行真实 DFT/双杂化 SCF 计算，获取总能量、Mulliken 电荷与轨道能隙。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "xc": {
                                "type": "string",
                                "enum": ["b3lyp", "hf", "pbe0", "wb97xd", "cam-b3lyp", "xyg3", "xygjos", "r-xdh7"],
                                "description": "交换相关泛函或双杂化方法",
                            },
                            "basis": {
                                "type": "string",
                                "enum": ["STO-3G", "def2-SVP", "def2-TZVP", "6-31G*", "cc-pVDZ"],
                                "description": "基组名称",
                            },
                        },
                    },
                },
            },
        ]

    # ---------- 工具实现 ----------
    def _elem_symbol(self, z: int) -> str:
        from ..domain.elements import get_element
        el = get_element(z)
        return el.symbol if el else "C"

    def _aid_at_1based(self, idx: int):
        if not self.document:
            return None
        atoms = list(self.document.topology.atom_ids)
        return next((aid for aid in atoms if aid.value + 1 == idx), None)

    def _tool_describe(self) -> dict:
        d = self.document
        from collections import Counter
        cnt = Counter(self.document.topology.get_atom(a).atomic_num for a in d.topology.atom_ids)
        elems = {self._elem_symbol(z): c for z, c in cnt.items()}
        return {
            "name": d.name,
            "num_atoms": d.num_atoms,
            "num_bonds": d.topology.num_bonds,
            "elements": elems,
            "has_3d": bool(d.has_3d and d.coordinates.current is not None),
        }

    def _tool_list_atoms(self) -> dict:
        d = self.document
        rows = []
        coords = d.coordinates.current.coords if (d.has_3d and d.coordinates.current is not None) else None
        for i, aid in enumerate(d.topology.atom_ids, start=1):
            z = d.topology.get_atom(aid).atomic_num
            c = coords[i - 1].tolist() if coords is not None and i - 1 < len(coords) else None
            rows.append({"index": aid.value + 1, "element": self._elem_symbol(z), "coord_3d": c})
        return {"atoms": rows}

    def _tool_add_atom(self, near_atom: int, atomic_num: int) -> dict:
        aid = self._aid_at_1based(near_atom)
        if aid is None or self.command_bus is None:
            return {"ok": False, "error": "参考原子越界或未连接命令总线"}
        res = self.command_bus.execute(AddAtomCommand(atomic_num=atomic_num, bond_to=aid))
        return {"ok": getattr(res, "success", True), "message": getattr(res, "message", ""), "num_atoms": self.document.num_atoms}

    def _tool_delete_atom(self, atom_index: int) -> dict:
        aid = self._aid_at_1based(atom_index)
        if aid is None or self.command_bus is None:
            return {"ok": False, "error": "原子越界或未连接命令总线"}
        res = self.command_bus.execute(DeleteAtomCommand(aid))
        return {"ok": getattr(res, "success", True), "message": getattr(res, "message", ""), "num_atoms": self.document.num_atoms}

    def _tool_add_bond(self, atom_a: int, atom_b: int) -> dict:
        a, b = self._aid_at_1based(atom_a), self._aid_at_1based(atom_b)
        if a is None or b is None or self.command_bus is None:
            return {"ok": False, "error": "原子越界或未连接命令总线"}
        res = self.command_bus.execute(AddBondCommand(a, b, order=1))
        return {"ok": getattr(res, "success", True), "message": getattr(res, "message", ""), "num_bonds": self.document.topology.num_bonds}

    def _tool_modify_internal_coordinate(self, coord_type: str, atoms: list[int], target_value: float) -> dict:
        if self.document is None:
            return {"ok": False, "error": "没有打开的分子"}
        from ..domain.ids import AtomId
        val = float(target_value)
        atom_ids = [self._aid_at_1based(x) for x in atoms]
        if any(a is None for a in atom_ids):
            return {"ok": False, "error": f"指定的原子序号越界: {atoms}"}

        if coord_type == "bond_length" and len(atom_ids) == 2:
            from ..application.builtin_commands import ModifyBondLength3DCommand
            bid = self.document.topology.bond_between(atom_ids[0], atom_ids[1])
            if bid is None:
                return {"ok": False, "error": f"原子 #{atoms[0]} 与 #{atoms[1]} 之间不存在化学键"}
            cmd = ModifyBondLength3DCommand(bid, val)
        elif coord_type == "bond_angle" and len(atom_ids) == 3:
            from ..application.internal_coordinates import ModifyAngle3DCommand
            cmd = ModifyAngle3DCommand(atom_ids[0], atom_ids[1], atom_ids[2], val)
        elif coord_type == "dihedral" and len(atom_ids) == 4:
            from ..application.internal_coordinates import ModifyDihedral3DCommand
            cmd = ModifyDihedral3DCommand(atom_ids[0], atom_ids[1], atom_ids[2], atom_ids[3], val)
        else:
            return {"ok": False, "error": f"不合法的内坐标修改参数 (coord_type={coord_type}, atoms={atoms})"}

        bus = self.command_bus
        if bus is None:
            from ..application.command_bus import CommandBus
            bus = CommandBus(self.document)
        r = bus.execute(cmd)
        return {"ok": r.success, "message": r.message}

    def _tool_run_calchem_scf(self, basis: str = "sto-3g") -> dict:
        if self.document is None:
            return {"ok": False, "error": "没有打开的分子"}
        from ..io.calchem_bridge import run_calchem_single_point
        res = run_calchem_single_point(self.document, basis=basis)
        if not res.get("success"):
            return {"ok": False, "error": res.get("error", "计算失败")}
        return {
            "ok": True,
            "converged": res.get("converged"),
            "total_energy_hartree": res.get("total_energy_hartree"),
            "homo_energy_hartree": res.get("homo_energy_hartree"),
            "lumo_energy_hartree": res.get("lumo_energy_hartree"),
            "gap_ev": res.get("gap_ev"),
            "dipole_debye": res.get("dipole_debye"),
        }

    def _tool_run_calchem_opt(self, basis: str = "sto-3g", max_steps: int = 50) -> dict:
        if self.document is None:
            return {"ok": False, "error": "没有打开的分子"}
        from ..io.calchem_bridge import run_calchem_optimization
        res = run_calchem_optimization(self.document, basis=basis, max_steps=max_steps)
        if not res.get("success"):
            return {"ok": False, "error": res.get("error", "优化失败")}
        if self.command_bus and "command" in res:
            self.command_bus.execute(res["command"])
        return {
            "ok": True,
            "converged": res.get("converged"),
            "steps": res.get("steps"),
            "final_energy_hartree": res.get("energy_hartree"),
            "applied_to_viewport": bool(self.command_bus),
        }

    def _tool_generate_hpc_slurm_script(
        self,
        engine: str,
        job_name: str = "chem_job",
        n_cores: int = 16,
        memory_mb: int = 32000,
        walltime: str = "24:00:00",
    ) -> dict:
        from ..infrastructure.hpc.slurm_generator import SlurmScriptGenerator, JobSpec
        from ..infrastructure.hpc.cluster_config import ClusterProfile
        job = JobSpec(
            job_name=job_name,
            engine=engine,
            input_file=f"{job_name}.{'gjf' if engine == 'g16' else 'inp'}",
            output_file=f"{job_name}.{'log' if engine == 'g16' else 'out'}",
            n_cores=n_cores,
            memory_mb=memory_mb,
            walltime=walltime,
        )
        script = SlurmScriptGenerator.generate(job, ClusterProfile())
        return {"ok": True, "engine": engine, "slurm_script": script}

    def _tool_planarity(self) -> dict:
        from ..application.calculators.qc_input_generator import export_document_to_xyz
        from ..workflows.planarity_analysis import run_planarity_workflow
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "molforge_mcp_plane.xyz")
        export_document_to_xyz(self.document, tmp)
        out = run_planarity_workflow(tmp, tempfile.gettempdir())
        summary_path = os.path.join(str(out), "planarity.json")
        with open(summary_path, encoding="utf-8") as fh:
            return json.load(fh)

    def _tool_run_rest_scf(self, xc: str = "b3lyp", basis: str = "def2-SVP") -> dict:
        if self.document is None:
            return {"ok": False, "error": "没有打开的分子"}
        from ..application.calculators.rest_engine import RestEngine
        engine = RestEngine()
        if not engine.probe():
            return {"ok": False, "error": "未检测到本地 WSL2 REST 虚拟环境 (/home/administrator/miniforge3/envs/rest-py311/bin/rest)"}
        return engine.run_calculation(self.document, xc=xc, basis=basis)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            if self.document is None:
                return {"ok": False, "error": "没有打开的分子"}
            spec = next((d["function"]["parameters"] for d in self.tool_definitions() if d["function"]["name"] == name), None)
            if spec is None or not isinstance(arguments, dict):
                raise ValueError(f"未知工具 '{name}' 或参数必须是对象")
            props = spec.get("properties", {})
            required_keys = set(spec.get("required", []))

            # 1. 检查必需参数
            missing = required_keys - set(arguments.keys())
            if missing:
                raise ValueError(f"缺少必需参数: {sorted(missing)}")

            # 2. 检查未知参数
            extra = set(arguments.keys()) - set(props.keys())
            if extra:
                raise ValueError(f"包含未知参数: {sorted(extra)}")

            # 3. 按 schema 动态进行类型校验
            for key, value in arguments.items():
                pinfo = props.get(key, {})
                ptype = pinfo.get("type")
                if ptype == "integer":
                    if not isinstance(value, int) or isinstance(value, bool):
                        raise ValueError(f"{key} 必须是整数")
                    min_val = pinfo.get("minimum", 1 if key in ("near_atom", "atom_index", "atom_a", "atom_b") else None)
                    if min_val is not None and value < min_val:
                        raise ValueError(f"{key} 必须 >= {min_val}")
                    if key == "atomic_num" and not (1 <= value <= 118):
                        raise ValueError("atomic_num 超出元素范围1–118")
                elif ptype == "number":
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        raise ValueError(f"{key} 必须是数值")
                elif ptype == "string":
                    if not isinstance(value, str):
                        raise ValueError(f"{key} 必须是字符串")
                    if "enum" in pinfo and value not in pinfo["enum"]:
                        raise ValueError(f"{key} 的值 '{value}' 不在允许的枚举范围 {pinfo['enum']} 内")
                elif ptype == "array":
                    if not isinstance(value, list):
                        raise ValueError(f"{key} 必须是列表")
                    item_type = pinfo.get("items", {}).get("type")
                    if item_type == "integer":
                        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in value):
                            raise ValueError(f"{key} 中的元素必须是 >= 1 的整数")

            return self._dispatch_validated(name, arguments)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _dispatch_validated(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "describe_structure":
            return self._tool_describe()
        if name == "list_atoms":
            return self._tool_list_atoms()
        if name == "add_atom":
            return self._tool_add_atom(**arguments)
        if name == "delete_atom":
            return self._tool_delete_atom(**arguments)
        if name == "add_bond":
            return self._tool_add_bond(**arguments)
        if name == "modify_internal_coordinate":
            return self._tool_modify_internal_coordinate(**arguments)
        if name == "run_calchem_scf":
            return self._tool_run_calchem_scf(**arguments)
        if name == "run_calchem_opt":
            return self._tool_run_calchem_opt(**arguments)
        if name == "generate_hpc_slurm_script":
            return self._tool_generate_hpc_slurm_script(**arguments)
        if name == "run_planarity":
            return self._tool_planarity()
        if name == "run_rest_scf":
            return self._tool_run_rest_scf(**arguments)
        return {"error": f"未知工具: {name}"}

    # ---------- 对话循环（OpenAI 兼容） ----------
    def chat(self, user_message: str, max_tool_rounds: int = 6, tool_executor=None) -> str:
        """发送一轮消息，自动执行 LLM 请求的工具调用，返回最终文本答复。"""
        cfg = self.config if getattr(self, 'config', None) else get_llm_config()
        from urllib.parse import urlsplit
        if urlsplit(cfg["base_url"]).scheme not in ("http", "https"):
            return "LLM端点必须是http/https地址"
        if self.document is not None:
            self.history.append({"role": "user", "content": user_message})
        else:
            return "当前没有打开的分子文档，LLM 无可读取的结构。"

        for _ in range(max_tool_rounds):
            payload = {
                "model": cfg["model"],
                "messages": self.history,
                "tools": self.tool_definitions(),
                "tool_choice": "auto",
            }
            url = cfg["base_url"].rstrip("/") + "/chat/completions"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {cfg['api_key']}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                return f"无法连接 LLM 端点 ({cfg['base_url']})：{exc}"

            try:
                msg = data["choices"][0]["message"]
                if not isinstance(msg, dict):
                    raise ValueError("message不是对象")
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                return f"LLM响应格式错误：{exc}"
            tool_calls = msg.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                return "LLM响应格式错误：tool_calls必须是数组"
            if not tool_calls:
                reply = msg.get("content", "")
                self.history.append(msg)
                return reply

            self.history.append(msg)
            for call in tool_calls:
                if not isinstance(call, dict) or not isinstance(call.get("function"), dict) or not call.get("id") or not isinstance(call["function"].get("name"), str):
                    return "LLM响应格式错误：工具调用缺少id/function/name"
                fname = call["function"]["name"]
                try:
                    fargs = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    fargs = {}
                result = (tool_executor or self.dispatch)(fname, fargs)
                self.history.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": fname,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        return "达到最大工具调用轮数，已停止。"
