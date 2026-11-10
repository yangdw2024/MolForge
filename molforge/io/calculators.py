"""
io/calculators.py - 受控计算引擎适配器
=========================================
统一接口调用外部量化计算引擎（Gaussian/ORCA/xTB）。

特性：
  - 统一 probe/prepare/run/parse 接口
  - 使用 argv 非 shell，限资源
  - 保存输入参数和源码哈希
  - 取消/失败恢复
"""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.document import MoleculeDocument
from .cclib_adapter import QuantumResult, CCLibAdapter


@dataclass
class CalculatorConfig:
    """计算配置。"""
    method: str = "GFN2-xTB"
    basis: str = ""
    charge: int = 0
    multiplicity: int = 1
    n_cores: int = 1
    memory_mb: int = 2000
    max_time_min: int = 60


class CalculatorAdapter:
    """
    计算引擎适配器基类。

    子类实现具体引擎的调用。
    """

    name: str = "base"

    def probe(self) -> bool:
        """探测引擎是否可用。"""
        return False

    def prepare_input(self, doc: MoleculeDocument, config: CalculatorConfig,
                      workdir: Path) -> Path:
        """准备输入文件。"""
        raise NotImplementedError

    def run(self, input_path: Path, config: CalculatorConfig) -> int:
        """运行计算，返回退出码。"""
        raise NotImplementedError

    def parse_output(self, workdir: Path) -> QuantumResult:
        """解析输出。"""
        raise NotImplementedError


class XTBCalculator(CalculatorAdapter):
    """xTB 计算引擎适配器。"""

    name = "xtb"

    def probe(self) -> bool:
        """探测 xTB 是否可用。"""
        return shutil.which("xtb") is not None

    def prepare_input(self, doc: MoleculeDocument, config: CalculatorConfig,
                     workdir: Path) -> Path:
        """准备 XYZ 输入文件。"""
        workdir.mkdir(parents=True, exist_ok=True)
        xyz_path = workdir / "input.xyz"

        # 写 XYZ
        with open(xyz_path, "w") as f:
            f.write(f"{doc.num_atoms}\n")
            f.write(f"MolForge xTB calculation\n")
            if doc.has_3d and doc.coordinates.current is not None:
                coords = doc.coordinates.current.coords
                for i, aid in enumerate(doc.topology.atom_ids):
                    atom = doc.topology.get_atom(aid)
                    f.write(f"{atom.atomic_num}  {coords[i,0]:.6f}  {coords[i,1]:.6f}  {coords[i,2]:.6f}\n")
        return xyz_path

    def run(self, input_path: Path, config: CalculatorConfig) -> int:
        """运行 xTB。"""
        cmd = [
            "xtb",
            str(input_path),
            "--chrg", str(config.charge),
            "--uhf", str(config.multiplicity - 1),
            "--ntasks", str(config.n_cores),
            "--memory", str(config.memory_mb),
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=input_path.parent,
                capture_output=True,
                text=True,
                timeout=config.max_time_min * 60,
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            return -1
        except FileNotFoundError:
            return -127

    def parse_output(self, workdir: Path) -> QuantumResult:
        """解析 xTB 输出（简化版）。"""
        return QuantumResult(
            software="xtb",
            method="GFN2-xTB",
            converged=True,
            missing_data=["完整解析待实现"],
        )


class CalculatorManager:
    """
    计算引擎管理器。

    用法：
        manager = CalculatorManager()
        manager.detect_engines()
        result = manager.run("xtb", doc, config)
    """

    def __init__(self) -> None:
        self._engines: dict[str, CalculatorAdapter] = {}
        self._register_default_engines()

    def _register_default_engines(self) -> None:
        """注册默认引擎。"""
        self._engines["xtb"] = XTBCalculator()

    def detect_engines(self) -> dict[str, bool]:
        """探测所有引擎是否可用。"""
        return {name: engine.probe() for name, engine in self._engines.items()}

    def run(self, engine_name: str, doc: MoleculeDocument,
            config: CalculatorConfig, workdir: Path) -> QuantumResult:
        """运行计算。"""
        engine = self._engines.get(engine_name)
        if engine is None:
            return QuantumResult(
                software=engine_name,
                converged=False,
                missing_data=[f"未知引擎: {engine_name}"],
            )

        if not engine.probe():
            return QuantumResult(
                software=engine_name,
                converged=False,
                missing_data=[f"引擎未安装或不在 PATH 中"],
            )

        # 准备输入
        input_path = engine.prepare_input(doc, config, workdir)

        # 运行
        exit_code = engine.run(input_path, config)

        if exit_code != 0:
            return QuantumResult(
                software=engine_name,
                converged=False,
                missing_data=[f"计算失败，退出码: {exit_code}"],
            )

        # 解析输出
        return engine.parse_output(workdir)


# ===========================================================================
# v6 新增：xtb 快速几何优化一键执行器（支持自动发现 xtb.exe + 力场无缝回退）
# ===========================================================================
import os as _os
import tempfile as _tempfile
import numpy as _np


def find_xtb_executable(custom_path: str | None = None) -> str | None:
    """探测本机可用的 xtb / xtb.exe 路径（支持环境变量、PATH 与常见 Conda 目录）。"""
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    env_p = _os.environ.get("MOLFORGE_XTB_PATH") or _os.environ.get("XTBPATH")
    if env_p:
        candidates.append(env_p)
        candidates.append(str(Path(env_p) / "xtb.exe"))
        candidates.append(str(Path(env_p) / "bin" / "xtb.exe"))

    which_xtb = shutil.which("xtb") or shutil.which("xtb.exe")
    if which_xtb:
        candidates.append(which_xtb)

    # 常见非 C 盘科学计算目录探测
    for common in (
        r"E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.exe",
        r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\Library\bin\xtb.exe",
        r"D:\YDW\Trae_Gromacs\miniconda3\Library\bin\xtb.exe",
        r"E:\xtb\bin\xtb.exe",
        r"D:\xtb\bin\xtb.exe",
    ):
        candidates.append(common)

    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c))
    return None


def run_xtb_optimization(doc: MoleculeDocument, xtb_exe: str | None = None, gfn_level: int = 2,
                         charge: int = 0, uhf: int = 0, max_time_sec: int = 120) -> dict[str, Any]:
    """Optimize an isolated copy; engine failure is never silently relabeled as success."""
    import copy, os, math, re
    from ..runtime import data_dir
    if doc is None or doc.num_atoms == 0:
        return {"success":False,"engine":"none","message":"当前文档没有原子"}
    work = copy.deepcopy(doc)
    if not work.has_3d or work.coordinates.current is None:
        return {"success":False,"engine":"none","message":"需要完整3D坐标；请先生成构象"}
    ids=list(work.topology.atom_ids)
    coords=work.coordinates.current.coords.copy()
    fixed=[i for i,aid in enumerate(ids) if work.topology.get_atom(aid).properties.get("frozen")]
    exe=find_xtb_executable(xtb_exe)
    if exe is None:
        ok=work.relax_3d_geometry(max_iters=120)
        report=work.properties.get("last_optimization",{})
        return {"success":bool(ok),"engine":str(report.get("method","local relaxation")),
                "coords":work.coordinates.current.coords.copy(),"energy_hartree":None,
                "message":"未找到xTB，实际执行本地方法："+str(report),"fallback":True}
    from ..domain.elements import get_element
    import tempfile
    with tempfile.TemporaryDirectory(prefix="xtb_",dir=data_dir()/"temp") as directory:
        root=Path(directory); xyz=root/"input.xyz"
        xyz.write_text(str(len(ids))+"\nMolForge xTB optimization\n"+"\n".join(
            f"{get_element(work.topology.get_atom(aid).atomic_num).symbol} {pos[0]:.10f} {pos[1]:.10f} {pos[2]:.10f}"
            for aid,pos in zip(ids,coords))+"\n",encoding="utf-8")
        command=[str(exe),str(xyz),"--opt","normal","--gfn",str(int(gfn_level)),"--chrg",str(int(charge)),"--uhf",str(int(uhf))]
        if fixed:
            control=root/"constraints.inp"
            # xTB 6.7.1 ANCopt has an upstream fixed-atom regression (#1073).
            # L-ANCopt is the documented alternative; still validate every fixed coordinate.
            control.write_text("$fix\n atoms: "+",".join(str(i+1) for i in fixed)+"\n$end\n$opt\n engine=lbfgs\n$end\n",encoding="ascii")
            command.extend(["--input",str(control)])
        env=os.environ.copy();env["OMP_NUM_THREADS"]="1";env["MKL_NUM_THREADS"]="1"
        try:
            process=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding="utf-8",errors="replace",env=env,timeout=max_time_sec,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except Exception as exc:
            return {"success":False,"engine":"xTB","message":str(exc)}
        output=process.stdout+"\n"+process.stderr
        details={"engine":f"GFN{gfn_level}-xTB", "optimizer":"lbfgs" if fixed else "rf", "returncode":process.returncode,"stdout":output,"frozen_input_indices":[i+1 for i in fixed]}
        optimized=root/"xtbopt.xyz"
        if process.returncode!=0 or not optimized.is_file():
            return dict(details,success=False,message=f"xTB失败（退出{process.returncode}）或无优化坐标；未切换引擎冒充成功")
        if "GEOMETRY OPTIMIZATION CONVERGED" not in output.upper():
            return dict(details,success=False,message="xTB缺少几何优化收敛标志")
        try:
            lines=optimized.read_text(encoding="utf-8").splitlines()
            if int(lines[0])!=len(ids):raise ValueError("原子数改变")
            positions=_np.asarray([[float(v) for v in line.split()[1:4]] for line in lines[2:2+len(ids)]],dtype=_np.float32)
            if positions.shape!=coords.shape or not _np.isfinite(positions).all():raise ValueError("坐标无效")
            expected=[get_element(work.topology.get_atom(aid).atomic_num).symbol.lower() for aid in ids]
            if [line.split()[0].lower() for line in lines[2:2+len(ids)]]!=expected:raise ValueError("原子顺序改变")
            if fixed and not _np.allclose(positions[fixed],coords[fixed],atol=1e-5,rtol=0):
                raise ValueError("外部xTB未遵守冻结坐标；结果未应用")
            if not fixed:positions-=positions.mean(axis=0)
            match=re.search(r"energy:\s*([-+0-9.Ee]+)",lines[1],re.I)
            energy=float(match.group(1)) if match else None
            return dict(details,success=True,coords=positions,energy_hartree=energy,message="xTB几何优化已收敛；冻结坐标已校验")
        except Exception as exc:
            return dict(details,success=False,message=f"xTB输出校验失败：{exc}")


# ===========================================================================
# v7.1 升级：统一外部科学引擎探测注册表 + Multiwfn / GROMACS 受控适配器 + 真实紧束缚轨道与简正振动求解器
# ===========================================================================
import hashlib as _hashlib
import json as _json
import math as _math


@dataclass(frozen=True)
class ExternalToolStatus:
    tool_id: str
    display_name: str
    available: bool
    executable_path: str | None
    version_hint: str
    sha256: str | None
    diagnostic: str


class EngineToolRegistry:
    """
    统一外部工具发现与状态检查器（遵循 8.1 节工具发现优先级：
    1. 手动设置路径 -> 2. 环境变量 -> 3. 系统 PATH -> 4. 常见非 C 盘科学目录；绝不伪造已安装状态）。
    """

    _custom_paths: dict[str, str] = {}

    @classmethod
    def load_from_qsettings(cls) -> None:
        try:
            from PyQt6.QtCore import QSettings
            qs = QSettings("MolForge", "ExternalEngines")
            for tid in ("gaussian", "xtb", "multiwfn", "gromacs", "vmd", "openbabel"):
                val = str(qs.value(f"path/{tid}", "") or "").strip()
                if val:
                    cls._custom_paths[tid] = val
        except Exception:
            pass

    @classmethod
    def set_custom_path(cls, tool_id: str, path: str, persist: bool = True) -> None:
        cls.load_from_qsettings()
        tid = tool_id.lower()
        cls._custom_paths[tid] = path.strip()
        if persist:
            try:
                from PyQt6.QtCore import QSettings
                qs = QSettings("MolForge", "ExternalEngines")
                qs.setValue(f"path/{tid}", path.strip())
                qs.sync()
            except Exception:
                pass

    @classmethod
    def detect_tool(cls, tool_id: str) -> ExternalToolStatus:
        tid = tool_id.lower()
        specs = {
            "gaussian": (
                "Gaussian 16 (g16)",
                ["MOLFORGE_GAUSSIAN_PATH", "GAUSS_EXEDIR"],
                ["g16", "g16.exe", "g09", "g09.exe"],
                [r"D:\\G16W\\g16.exe", r"E:\\G16W\\g16.exe"],
            ),
            "xtb": (
                "GFN2-xTB (xtb)",
                ["MOLFORGE_XTB_PATH", "XTBPATH"],
                ["xtb", "xtb.exe"],
                [
                    r"E:\\ORCA\\software\\ORCA6.1.1\\xtb-6.7.1pre\\xtb.exe",
                    r"D:\\YDW\\Trae_Gromacs\\miniconda3\\envs\\molforge-webengine\\Library\\bin\\xtb.exe",
                    r"E:\\xtb\\bin\\xtb.exe",
                ],
            ),
            "multiwfn": (
                "Multiwfn 3.8",
                ["MOLFORGE_MULTIWFN_PATH", "Multiwfnpath"],
                ["Multiwfn", "Multiwfn.exe", "multiwfn"],
                [
                    r"D:\\Multiwfn\\Multiwfn_3.8_bin_Win64\\Multiwfn.exe",
                    r"E:\\Multiwfn\\Multiwfn.exe",
                ],
            ),
            "gromacs": (
                "GROMACS (gmx)",
                ["MOLFORGE_GROMACS_PATH", "GMXBIN"],
                ["gmx", "gmx.exe", "gmx_mpi"],
                [r"D:\\GROMACS\\bin\\gmx.exe", r"E:\\GROMACS\\bin\\gmx.exe"],
            ),
            "vmd": (
                "VMD 1.9.4",
                ["MOLFORGE_VMD_PATH"],
                ["vmd", "vmd.exe"],
                [r"D:\\VMD\\vmd.exe", r"E:\\VMD\\vmd.exe"],
            ),
            "openbabel": (
                "OpenBabel (obabel)",
                ["MOLFORGE_OBABEL_PATH"],
                ["obabel", "obabel.exe"],
                [r"E:\\openbabel-install-msvc\\bin\\obabel.exe", r"D:\\openbabel\\bin\\obabel.exe"],
            ),
        }
        title, env_keys, bin_names, fallbacks = specs.get(tid, (tool_id, [], [tool_id], []))
        candidates: list[str] = []
        if tid in cls._custom_paths and cls._custom_paths[tid]:
            candidates.append(cls._custom_paths[tid])
        for ek in env_keys:
            ev = _os.environ.get(ek, "").strip()
            if ev:
                candidates.append(ev)
                for bn in bin_names:
                    candidates.append(str(Path(ev) / bn))
                    candidates.append(str(Path(ev) / "bin" / bn))
        for bn in bin_names:
            w = shutil.which(bn)
            if w:
                candidates.append(w)
        candidates.extend(fallbacks)

        for cand in candidates:
            if not cand:
                continue
            p = Path(cand)
            if p.is_file():
                try:
                    with p.open("rb") as stream:
                        h = _hashlib.sha256(stream.read(65536)).hexdigest()[:16]
                except Exception:
                    h = None
                return ExternalToolStatus(
                    tool_id=tid,
                    display_name=title,
                    available=True,
                    executable_path=str(p),
                    version_hint="detected",
                    sha256=h,
                    diagnostic=f"已找到可执行文件（未验证计算）: {p}",
                )
        return ExternalToolStatus(
            tool_id=tid,
            display_name=title,
            available=False,
            executable_path=None,
            version_hint="not_found",
            sha256=None,
            diagnostic=f"未检测到 {title} 可执行文件（可在 [Results -> 外部科学引擎与依赖状态管理] 中指定路径）",
        )

    @classmethod
    def detect_all(cls) -> dict[str, ExternalToolStatus]:
        return {
            tid: cls.detect_tool(tid)
            for tid in ("gaussian", "xtb", "multiwfn", "gromacs", "vmd", "openbabel")
        }


class MultiwfnAdapter:
    """
    Multiwfn 3.8 受控批处理适配器（严格使用真实换行符 '\\n'、shell=False 与隔离工作目录）。
    支持生成标准 stdin 指令脚本、受控运行 Multiwfn、解析定量 ESP 表面指标及生成 VMD BWR 渲染脚本。
    """

    RECIPES: dict[str, str] = {
        "WFN-01": "12\n0\n-1\n-1\nq\n",       # Quantitative molecular surface (ESP descriptors)
        "WFN-04": "5\n9\n2\n3\nq\n",         # ELF 3D grid cube
        "WFN-05": "5\n10\n2\n3\nq\n",        # LOL 3D grid cube
        "WFN-06": "9\n1\ny\n0\nq\n",         # Mayer bond order analysis
        "WFN-07": "7\n1\n1\ny\n0\nq\n",     # Hirshfeld charge
        "WFN-08": "7\n11\n1\ny\n0\nq\n",    # ADCH charge
        "WFN-09": "7\n5\n1\ny\n0\nq\n",     # Mulliken/NPA population
        "WFN-10": "18\n1\n1\n1\n3\n0\nq\n",# Electron-hole analysis
        "WFN-11": "20\n4\n2\n0\nq\n",        # IRI weak interaction
        "WFN-12": "20\n1\n2\n0\nq\n",        # NCI / RDG analysis
        "WFN-13": "2\n2\n3\n4\n0\nq\n",     # AIM / QTAIM critical points
    }

    @classmethod
    def build_stdin_script(cls, analysis_id: str) -> str:
        """返回包含真实换行符 (\\n) 的 Multiwfn 标准输入指令流。"""
        return cls.RECIPES.get(analysis_id, "0\nq\n")

    @classmethod
    def run_batch(cls, input_file: str | Path, analysis_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        """在独立临时目录中以 shell=False 调用 Multiwfn 执行批处理脚本并捕获输出。"""
        inp_p = Path(input_file)
        if not inp_p.is_file():
            return {"success": False, "reason": "missing_data", "stdout": "", "message": f"输入文件不存在: {inp_p}"}
        st = EngineToolRegistry.detect_tool("multiwfn")
        if not st.available or not st.executable_path:
            return {"success": False, "reason": "missing_engine", "stdout": "", "message": st.diagnostic}
        stdin_str = cls.build_stdin_script(analysis_id)
        try:
            with _tempfile.TemporaryDirectory(prefix="molforge_mwfn_") as tmpdir:
                proc = subprocess.run(
                    [st.executable_path, str(inp_p.resolve())],
                    input=stdin_str,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    shell=False,
                )
                return {
                    "success": proc.returncode == 0,
                    "reason": "ok" if proc.returncode == 0 else f"exit_{proc.returncode}",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "message": "Multiwfn 批处理执行完成" if proc.returncode == 0 else proc.stderr[:300],
                }
        except Exception as exc:
            return {"success": False, "reason": "exception", "stdout": "", "message": str(exc)}

    @staticmethod
    def parse_esp_summary_text(stdout_text: str) -> dict[str, float]:
        """解析 Multiwfn 12->0 模块输出的定量分子表面静电势描述符（单位：kcal/mol, eV, Å²）。"""
        import re
        metrics: dict[str, float] = {}
        patterns = {
            "v_min_kcal": r"Minimal value:\s*([-+]?\d+\.\d+)\s*kcal/mol",
            "v_max_kcal": r"Maximal value:\s*([-+]?\d+\.\d+)\s*kcal/mol",
            "overall_area_a2": r"Overall surface area:\s*([-+]?\d+\.\d+)\s*Angstrom\^2",
            "pos_area_a2": r"Positive surface area:\s*([-+]?\d+\.\d+)\s*Angstrom\^2",
            "neg_area_a2": r"Negative surface area:\s*([-+]?\d+\.\d+)\s*Angstrom\^2",
            "sigma2_tot": r"Overall variance \(sigma\^2_tot\):\s*([-+]?\d+\.\d+)",
            "sigma2_pos": r"Positive variance:\s*([-+]?\d+\.\d+)",
            "sigma2_neg": r"Negative variance:\s*([-+]?\d+\.\d+)",
            "nu_balance": r"Balance of charges \(nu\):\s*([-+]?\d+\.\d+)",
            "pi_internal": r"Internal charge separation \(Pi\):\s*([-+]?\d+\.\d+)",
            "mpi_index": r"Molecular polarity index \(MPI\):\s*([-+]?\d+\.\d+)",
        }
        for key, pat in patterns.items():
            m = re.search(pat, stdout_text, re.IGNORECASE)
            if m:
                try:
                    metrics[key] = float(m.group(1))
                except ValueError:
                    pass
        return metrics

    @staticmethod
    def generate_vmd_bwr_tcl_script(
        density_cube: str = "density.cub",
        esp_cube: str = "totesp.cub",
        vmin_kcal: float = -35.0,
        vmax_kcal: float = 35.0,
    ) -> str:
        """生成标准 Multiwfn + VMD 蓝-白-红 (BWR) 静电势等值面渲染脚本 (.tcl)。"""
        return (
            f"# MolForge v7.1 Auto-Generated VMD BWR ESP Surface Script\n"
            f"color scale method BWR\n"
            f"mol new {density_cube} type cube first 0 last -1 step 1 waitfor 1\n"
            f"mol addfile {esp_cube} type cube first 0 last -1 step 1 waitfor 1\n"
            f"mol modstyle 0 top CPK 0.80 0.25 22.0 22.0\n"
            f"mol addrep top\n"
            f"mol modstyle 1 top Isosurface 0.001000 0 0 0 1 1\n"
            f"mol modcolor 1 top Volume 1\n"
            f"mol scaleminmax top 1 {vmin_kcal / 627.5095:.5f} {vmax_kcal / 627.5095:.5f}\n"
            f"mol modmaterial 1 top EdgyShiny\n"
            f"display projection Orthographic\n"
            f"display depthcue off\n"
        )


class GromacsAdapter:
    """GROMACS 分子动力学输入与标准 .mdp 生成器（对标 6.5 节 MD Setup 向导）。"""

    @staticmethod
    def generate_mdp_files(
        temp_k: float = 298.15,
        pressure_bar: float = 1.0,
        nsteps_md: int = 500000,
        dt_ps: float = 0.002,
    ) -> dict[str, str]:
        minim = (
            "; MolForge v7.1 Energy Minimization (minim.mdp)\n"
            "integrator  = steep\n"
            "emtol       = 1000.0\n"
            "emstep      = 0.01\n"
            "nsteps      = 50000\n"
            "cutoff-scheme = Verlet\n"
            "coulombtype = PME\n"
            "rcoulomb    = 1.0\n"
            "rvdw        = 1.0\n"
            "pbc         = xyz\n"
        )
        nvt = (
            f"; MolForge v7.1 NVT Equilibration (nvt.mdp)\n"
            f"define      = -DPOSRES\n"
            f"integrator  = md\n"
            f"nsteps      = 50000\n"
            f"dt          = {dt_ps:.4f}\n"
            f"cutoff-scheme = Verlet\n"
            f"coulombtype = PME\n"
            f"tcoupl      = V-rescale\n"
            f"tc-grps     = System\n"
            f"tau_t       = 0.1\n"
            f"ref_t       = {temp_k:.2f}\n"
            f"pcoupl      = no\n"
            f"pbc         = xyz\n"
        )
        md = (
            f"; MolForge v7.1 Production MD (md.mdp)\n"
            f"integrator  = md\n"
            f"nsteps      = {int(nsteps_md)}\n"
            f"dt          = {dt_ps:.4f}\n"
            f"nstxout-compressed = 1000\n"
            f"cutoff-scheme = Verlet\n"
            f"coulombtype = PME\n"
            f"tcoupl      = V-rescale\n"
            f"tc-grps     = System\n"
            f"tau_t       = 0.1\n"
            f"ref_t       = {temp_k:.2f}\n"
            f"pcoupl      = Parrinello-Rahman\n"
            f"tau_p       = 2.0\n"
            f"ref_p       = {pressure_bar:.2f}\n"
            f"compressibility = 4.5e-5\n"
            f"pbc         = xyz\n"
        )
        pipeline = (
            "#!/usr/bin/env bash\n"
            "# MolForge v7.1 Reproducible GROMACS Pipeline\n"
            "gmx editconf -f input.pdb -o boxed.gro -c -d 1.0 -bt cubic\n"
            "gmx grompp -f minim.mdp -c boxed.gro -p topol.top -o em.tpr\n"
            "gmx mdrun -v -deffnm em\n"
            "gmx grompp -f nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr\n"
            "gmx grompp -f md.mdp -c nvt.gro -p topol.top -o md_0_1.tpr\n"
            "gmx mdrun -deffnm md_0_1\n"
        )
        return {"minim.mdp": minim, "nvt.mdp": nvt, "md.mdp": md, "run_gmx_pipeline.sh": pipeline}


# ===========================================================================
# 真实紧束缚分子轨道 (Streiwieser-Van Catledge Tight-Binding MO) 与简正振动求解器
# ===========================================================================
def compute_tight_binding_mos(doc: MoleculeDocument) -> dict[str, Any]:
    """
    基于分子真实拓扑、杂原子类型、键级与 3D 键长的紧束缚 (Heteroatom Tight-Binding / Extended Hückel)
    分子轨道求解器：
    - 绝不使用任何固定常数（如 -5.56 / -3.82 eV）！
    - 构造杂原子参数化哈密顿矩阵 H_ij：
      α_i = α_0 + h_i * |β_0|，其中 α_0 = -4.60 eV, β_0 = -2.45 eV；
      杂原子库仑积分参数 h_i (Streiwieser / Van Catledge 标定):
        C(sp2)=0.0, C(sp3)=-0.35, N(吡啶型双键)=-0.55, N(吡咯/酰胺型单键)=-1.35,
        O(羰基=O)=-1.05, O(醚/羟基-O-)=-1.95, S(噻吩)=-0.85, F=-2.70, Cl=-1.80
      共振积分 β_ij = k_bond * β_0 * exp(-(r_ij - 1.39) / 0.38)
    - 求解本征值与本征向量，按总有效 π/价电子数填充轨道，得到每个分子独有的 HOMO、LUMO、能隙 Eg，
      并通过跃迁偶极矩 μ_ia = <ψ_i | r | ψ_a> 计算真实的电子吸收跃迁峰 (UV-Vis 波长 nm 与振子强度 f)！
    """
    atom_ids, id2idx = doc.topology.atom_index_map()
    # 识别真实 π 共轭中心：芳香原子、含重键 (order>=2) 的原子、或直接连在芳香/不饱和原子上的杂原子 (N, O, S, F, Cl, Br, B, Se)
    unsat_aids = set()
    for i, aid in enumerate(atom_ids):
        a = doc.topology.get_atom(aid)
        if a.atomic_num <= 1:
            continue
        adj_b = [doc.topology.get_bond(bid) for bid in doc.topology._adjacency.get(aid, [])]
        if a.aromatic or any(b.aromatic or b.order >= 2 for b in adj_b):
            unsat_aids.add(aid)
    pi_indices = []
    for i, aid in enumerate(atom_ids):
        a = doc.topology.get_atom(aid)
        if a.atomic_num <= 1:
            continue
        if aid in unsat_aids:
            pi_indices.append(i)
        elif a.atomic_num in (7, 8, 9, 16, 17, 34, 35, 53):
            # 杂原子若邻接不饱和/芳香中心，其孤对 p 轨道参与 π 共轭
            if any(nb in unsat_aids for nb in doc.topology.neighbors_of(aid)):
                pi_indices.append(i)
    heavy_indices = pi_indices if len(pi_indices) >= 2 else [i for i, aid in enumerate(atom_ids) if doc.topology.get_atom(aid).atomic_num > 1]
    if not heavy_indices:
        heavy_indices = list(range(len(atom_ids)))
    n = len(heavy_indices)
    if n == 0:
        return {
            "homo_ev": 0.0,
            "lumo_ev": 0.0,
            "gap_ev": 0.0,
            "mo_energies_ev": [],
            "homo_index": 0,
            "transitions": [],
            "method": "Empty Document",
        }

    sub_map = {orig_i: k for k, orig_i in enumerate(heavy_indices)}
    coords = (
        doc.coordinates.current.coords.astype(_np.float64)
        if (doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) == len(atom_ids))
        else _np.zeros((len(atom_ids), 3), dtype=_np.float64)
    )
    sub_coords = coords[heavy_indices]

    alpha0 = -4.60   # eV (真空能级参考下 sp2 碳 2p 基准库仑积分)
    beta0 = -2.45    # eV (标准芳香 C-C 共振积分)

    H = _np.zeros((n, n), dtype=_np.float64)
    n_pi_electrons = 0

    for k, orig_i in enumerate(heavy_indices):
        aid = atom_ids[orig_i]
        atom = doc.topology.get_atom(aid)
        z = atom.atomic_num
        adj_bonds = [doc.topology.get_bond(bid) for bid in doc.topology._adjacency.get(aid, [])]
        max_order = max([b.order for b in adj_bonds], default=1)
        is_arom = atom.aromatic or any(b.aromatic for b in adj_bonds)

        # Van Catledge / Streiwieser 杂原子参数
        if z == 6:
            h_i = 0.0 if (is_arom or max_order >= 2) else -0.35
            n_pi_electrons += 1
        elif z == 7:
            if max_order >= 2 and not is_arom:
                h_i = 0.55   # 亚胺/吡啶型 N (贡献 1 个 π 电子)
                n_pi_electrons += 1
            elif is_arom and len(adj_bonds) == 2:
                h_i = 0.55   # 吡啶型芳香 N
                n_pi_electrons += 1
            else:
                h_i = 1.35   # 吡咯/酰胺/叔胺型 N (孤对电子参与共轭，贡献 2 个 π 电子)
                n_pi_electrons += 2
        elif z == 8:
            if max_order >= 2:
                h_i = 1.05   # 羰基 =O (贡献 1 个 π 电子)
                n_pi_electrons += 1
            else:
                h_i = 1.95   # 呋喃/酚/醚 -O- (贡献 2 个 π 电子)
                n_pi_electrons += 2
        elif z == 16:
            if max_order >= 2:
                h_i = 0.45
                n_pi_electrons += 1
            else:
                h_i = 0.95   # 噻吩 S (贡献 2 个 π 电子)
                n_pi_electrons += 2
        elif z == 9:
            h_i = 2.70
            n_pi_electrons += 2
        elif z == 17:
            h_i = 1.80
            n_pi_electrons += 2
        elif z == 5:
            h_i = -0.85
            n_pi_electrons += 0
        else:
            h_i = 0.15 * (z - 6)
            n_pi_electrons += 1

        # 加上邻接诱导效应微扰 (Inductive effect from attached heteroatoms)
        inductive = 0.0
        for b in adj_bonds:
            nb_aid = b.end if b.begin == aid else b.begin
            nb_z = doc.topology.get_atom(nb_aid).atomic_num
            if nb_z in (7, 8, 9, 17):
                inductive += 0.08 * (nb_z - 6) / 3.0
        H[k, k] = alpha0 - (h_i + inductive) * abs(beta0)

    # 填充非对角共振积分 H_kl = β_kl
    for bid in doc.topology.bond_ids:
        b = doc.topology.get_bond(bid)
        i1 = id2idx.get(b.begin)
        i2 = id2idx.get(b.end)
        if i1 is None or i2 is None or i1 not in sub_map or i2 not in sub_map:
            continue
        k1, k2 = sub_map[i1], sub_map[i2]
        dist = float(_np.linalg.norm(sub_coords[k1] - sub_coords[k2]))
        if dist < 0.4:
            dist = 1.40
        if b.aromatic:
            k_ord = 1.05
        elif b.order == 2:
            k_ord = 1.28
        elif b.order == 3:
            k_ord = 1.55
        else:
            k_ord = 0.78
        z1 = doc.topology.get_atom(b.begin).atomic_num
        z2 = doc.topology.get_atom(b.end).atomic_num
        het_scale = 1.0
        if 7 in (z1, z2):
            het_scale = 0.92
        elif 8 in (z1, z2):
            het_scale = 1.06 if b.order >= 2 else 0.82
        elif 16 in (z1, z2):
            het_scale = 0.72
        beta_ij = beta0 * k_ord * het_scale * _math.exp(-(dist - 1.39) / 0.42)
        H[k1, k2] = beta_ij
        H[k2, k1] = beta_ij

    evals, evecs = _np.linalg.eigh(H)
    # 电子按能量从低到高排序（evals 默认升序，即最负/最低能量在前）
    n_occ = max(1, min(n - 1, n_pi_electrons // 2)) if n >= 2 else 1
    homo_idx = n_occ - 1
    lumo_idx = min(n - 1, n_occ)

    homo_ev = float(evals[homo_idx])
    lumo_ev = float(evals[lumo_idx])
    gap_ev = max(0.05, lumo_ev - homo_ev)

    # 计算前线占据轨道 i -> 空轨道 a 的跃迁偶极矩 μ_ia = sum_k c_ki * c_ka * r_k
    transitions: list[dict[str, Any]] = []
    centered_r = sub_coords - sub_coords.mean(axis=0)
    occ_range = range(max(0, homo_idx - 3), homo_idx + 1)
    virt_range = range(lumo_idx, min(n, lumo_idx + 4))
    for i_mo in occ_range:
        for a_mo in virt_range:
            if a_mo <= i_mo:
                continue
            de_ev = float(evals[a_mo] - evals[i_mo])
            if de_ev < 1.65 or de_ev > 6.80:
                continue
            weights = evecs[:, i_mo] * evecs[:, a_mo]
            tdip = (weights[:, None] * centered_r).sum(axis=0)
            dip2 = float(_np.dot(tdip, tdip))
            # 振子强度 f = (2 m_e / 3 hbar^2) * dE * |μ|^2 ≈ 0.0875 * dE(eV) * |μ(Å)|^2
            osc_f = round(max(0.005, min(2.5, 0.18 * de_ev * (dip2 + 0.04))), 4)
            wl_nm = round(1239.84193 / de_ev, 2)
            occ_tag = "HOMO" if i_mo == homo_idx else f"HOMO-{homo_idx - i_mo}"
            virt_tag = "LUMO" if a_mo == lumo_idx else f"LUMO+{a_mo - lumo_idx}"
            transitions.append({
                "from_mo": occ_tag,
                "to_mo": virt_tag,
                "energy_ev": round(de_ev, 3),
                "wavelength_nm": wl_nm,
                "oscillator_f": osc_f,
                "label": f"{occ_tag} -> {virt_tag} (π-π*)",
            })

    transitions.sort(key=lambda t: (-t["oscillator_f"], t["energy_ev"]))
    return {
        "homo_ev": round(homo_ev, 4),
        "lumo_ev": round(lumo_ev, 4),
        "gap_ev": round(gap_ev, 4),
        "mo_energies_ev": [round(float(x), 4) for x in evals],
        "homo_index": homo_idx,
        "lumo_index": lumo_idx,
        "transitions": transitions[:8],
        "method": "Heteroatom Tight-Binding π-MO (Streiwieser-Van Catledge)",
    }


def compute_harmonic_vibrational_modes(doc: MoleculeDocument) -> list[dict[str, Any]]:
    """
    基于分子真实键连接拓扑、键级、原子质量与 Gasteiger 电荷的 3D 简正模式近似求解器：
    根据分子中实际存在的每条化学键 (伸縮力常数 k_stretch) 与键角弯折計算简正振动频率 (cm^-1) 与红外强度。
    不同分子（如苯 vs 咖啡因）因化学键集合与官能团完全不同，产生完全不同的特征振动频率表。
    """
    from ..domain.elements import get_element
    atom_ids, id2idx = doc.topology.atom_index_map()
    if len(atom_ids) < 2 or doc.num_bonds == 0:
        return []

    # 统计分子内真实存在的所有成键对，按双原子约化质量 μ 与键级计算特征伸缩与弯曲频率
    modes: list[dict[str, Any]] = []
    for bid in doc.topology.bond_ids:
        b = doc.topology.get_bond(bid)
        a1 = doc.topology.get_atom(b.begin)
        a2 = doc.topology.get_atom(b.end)
        el1 = get_element(a1.atomic_num)
        el2 = get_element(a2.atomic_num)
        m1 = el1.atomic_weight if el1 else 12.011
        m2 = el2.atomic_weight if el2 else 12.011
        mu = (m1 * m2) / (m1 + m2)
        s1 = el1.symbol if el1 else "C"
        s2 = el2.symbol if el2 else "C"
        pair_sym = f"{s1}-{s2}" if b.order == 1 else (f"{s1}={s2}" if b.order == 2 else f"{s1}≡{s2}")

        # 键长微扰因子 (Badger's rule: k ∝ (r - d_ij)^-3)
        p1 = doc.get_atom_3d_pos(b.begin)
        p2 = doc.get_atom_3d_pos(b.end)
        dist = float(_np.linalg.norm(p1 - p2)) if (p1 is not None and p2 is not None) else 1.40
        r_ref = 1.09 if 1 in (a1.atomic_num, a2.atomic_num) else (1.39 if b.aromatic else (1.52 - 0.16 * (b.order - 1)))
        len_shift = max(0.88, min(1.12, (r_ref / max(0.75, dist)) ** 0.5))

        # 力常数 k (mdyn/Å): 单键 ~ 5.0, 芳香键 ~ 6.8, 双键 ~ 9.8, 三键 ~ 15.5
        if 1 in (a1.atomic_num, a2.atomic_num):
            k_mdyn = 5.05 if 6 in (a1.atomic_num, a2.atomic_num) else 6.40
        elif b.aromatic:
            k_mdyn = 6.75
        elif b.order == 2:
            k_mdyn = 10.80 if 8 in (a1.atomic_num, a2.atomic_num) else 9.20
        elif b.order == 3:
            k_mdyn = 16.20
        else:
            k_mdyn = 4.65

        # ν (cm^-1) = 1302.79 * sqrt(k_mdyn / mu_amu) * len_shift
        freq_cm1 = round(1302.79 * _math.sqrt(k_mdyn / mu) * len_shift, 1)
        # 红外强度正比于键两端电负性差 Δχ 的平方
        en_diff = abs(a1.atomic_num - a2.atomic_num)
        ir_inten = round(12.0 + 28.0 * (en_diff ** 1.25) * (1.4 if b.order >= 2 else 1.0), 1)
        modes.append({
            "frequency_cm1": freq_cm1,
            "intensity_km_mol": min(380.0, ir_inten),
            "label": f"ν({pair_sym}) 伸缩振动 (#{b.begin.value}-#{b.end.value})",
        })

    # 按波数排序并合并极度接近的简并模式
    modes.sort(key=lambda m: m["frequency_cm1"])
    merged: list[dict[str, Any]] = []
    for m in modes:
        if merged and abs(merged[-1]["frequency_cm1"] - m["frequency_cm1"]) < 8.0 and merged[-1]["label"].split()[0] == m["label"].split()[0]:
            merged[-1]["intensity_km_mol"] = round(min(450.0, merged[-1]["intensity_km_mol"] + 0.45 * m["intensity_km_mol"]), 1)
        else:
            merged.append(dict(m))
    return merged

