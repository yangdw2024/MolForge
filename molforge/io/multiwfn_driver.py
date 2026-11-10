"""Multiwfn  headless automation driver.

Provides non-blocking, automated integration with Multiwfn (Tian Lu, Beijing Kein Research Center):
  1. QTAIM (Quantum Theory of Atoms in Molecules):
     - Topology critical points: (3,-3) attractors, (3,-1) bond critical points (BCPs),
       (3,+1) ring critical points (RCPs), (3,+3) cage critical points (CCPs).
     - Real-space properties at CPs: rho, Laplacian, energy density H(r), G(r), V(r), ellipticity.
     - 3D gradient bond paths connecting attractors through BCPs.
  2. NCI / RDG (Non-Covalent Interactions / Reduced Density Gradient):
     - Ab initio NCI (from .wfn/.fchk) or Promolecular NCI (from .xyz/.pdb/MoleculeDocument).
     - Produces sign(lambda2)*rho and RDG volumetric cube grids + scatter data.
  3. ELF / LOL / ESP 3D spatial grids:
     - Electron Localization Function, Localized Orbital Locator, Electrostatic Potential.
  4. Population Analysis & Atomic Charges:
     - ADCH (Atomic Dipole Corrected Hirshfeld), Hirshfeld, CM5, RESP charges + dipole.
  5. Bond Order Analysis:
     - Mayer bond order matrix and total atomic valences.

All coordinates are strictly converted from Bohr to Angstrom upon import.
Subprocess execution is strictly protected with timeouts and redirected stdin ending with 'q'.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import numpy as np

from molforge.io.cube_reader import CubeData, read_cube

BOHR_TO_ANGSTROM = 0.529177210903


@dataclass
class CriticalPoint:
    """QTAIM 拓扑临界点。"""
    index: int
    cp_type: str                   # "(3,-3)", "(3,-1)", "(3,+1)", "(3,+3)"
    type_name: str                 # "Nuclear Attractor", "Bond Critical Point", etc.
    coords_angstrom: np.ndarray    # (3,) Å
    coords_bohr: np.ndarray        # (3,) Bohr
    nucleus: Optional[str] = None  # e.g. "1(O )"
    rho: float = 0.0               # 电子密度
    laplacian: float = 0.0         # 电子密度拉普拉斯量 ∇²ρ
    energy_density_H: float = 0.0  # 总能量密度 H(r)
    potential_energy_V: float = 0.0 # 势能密度 V(r)
    lagrangian_kinetic_G: float = 0.0 # 动能密度 G(r)
    elf: float = 0.0               # 电子定域化函数 ELF
    lol: float = 0.0               # 局域轨道定位器 LOL
    rdg: float = 0.0               # 约化密度梯度 RDG
    sign_lambda2_rho: float = 0.0  # sign(λ₂)ρ
    ellipticity: float = 0.0       # 键椭圆度 ε = λ₁/λ₂ - 1


@dataclass
class BondPath:
    """QTAIM 3D 梯度键径 (从核到 BCP 的梯度矢量积分路径)。"""
    path_index: int
    points_angstrom: np.ndarray    # (N, 3) Å
    points_bohr: np.ndarray        # (N, 3) Bohr
    bcp_index: Optional[int] = None
    connected_nuclei: Tuple[str, str] = ("", "")


@dataclass
class QTAIMResult:
    """QTAIM 拓扑分析完整结果。"""
    critical_points: List[CriticalPoint] = field(default_factory=list)
    paths: List[BondPath] = field(default_factory=list)
    raw_summary: str = ""

    @property
    def bcps(self) -> List[CriticalPoint]:
        return [cp for cp in self.critical_points if cp.cp_type == "(3,-1)"]

    @property
    def attractors(self) -> List[CriticalPoint]:
        return [cp for cp in self.critical_points if cp.cp_type == "(3,-3)"]

    @property
    def ring_cps(self) -> List[CriticalPoint]:
        return [cp for cp in self.critical_points if cp.cp_type == "(3,+1)"]

    @property
    def cage_cps(self) -> List[CriticalPoint]:
        return [cp for cp in self.critical_points if cp.cp_type == "(3,+3)"]


@dataclass
class NCIResult:
    """弱相互作用 NCI / RDG 分析结果。"""
    sign_lambda2_rho_cube: Optional[CubeData] = None
    rdg_cube: Optional[CubeData] = None
    scatter_points: Optional[np.ndarray] = None  # (M, 2) [sign(λ₂)ρ, RDG]
    is_promolecular: bool = False
    cube_files: List[Path] = field(default_factory=list)


@dataclass
class PopulationResult:
    """原子电荷与布居分析结果。"""
    method: str
    charges: Dict[int, float] = field(default_factory=dict) # atom_index (1-based) -> charge
    atom_labels: Dict[int, str] = field(default_factory=dict)
    dipole_au: Optional[np.ndarray] = None
    dipole_debye: Optional[np.ndarray] = None


@dataclass
class MayerBondOrderResult:
    """Mayer 键级分析结果。"""
    bond_orders: Dict[Tuple[int, int], float] = field(default_factory=dict) # (a1, a2) -> BO
    total_valences: Dict[int, float] = field(default_factory=dict)         # atom_idx -> valence
    free_valences: Dict[int, float] = field(default_factory=dict)          # atom_idx -> free valence
    atom_labels: Dict[int, str] = field(default_factory=dict)


class MultiwfnDriver:
    """Multiwfn 官方命令行无头执行器。"""

    DEFAULT_PATHS = [
        Path(r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe"),
        Path(r"C:\Multiwfn\Multiwfn.exe"),
        Path(r"E:\Multiwfn\Multiwfn.exe"),
    ]

    def __init__(self, executable_path: Optional[str | Path] = None, work_dir: Optional[str | Path] = None):
        self._executable = self._resolve_executable(executable_path)
        self.work_dir = Path(work_dir) if work_dir else Path(r"E:\temp")
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_executable(self, custom_path: Optional[str | Path]) -> Optional[Path]:
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return p
        which = shutil.which("Multiwfn") or shutil.which("Multiwfn.exe")
        if which:
            return Path(which)
        for cand in self.DEFAULT_PATHS:
            if cand.is_file():
                return cand
        return None

    @property
    def is_available(self) -> bool:
        return self._executable is not None and self._executable.is_file()

    @property
    def executable_path(self) -> Optional[Path]:
        return self._executable

    def _run_commands(self, input_file: str | Path, command_script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        """安全执行 Multiwfn，严格重定向 stdin 并在结尾添加安全退出指令。"""
        if not self.is_available:
            raise RuntimeError(f"未检测到 Multiwfn 可执行程序，请检查路径配置。")

        inp = Path(input_file).resolve()
        if not inp.is_file():
            raise FileNotFoundError(f"输入文件不存在: {inp}")

        # 确保以 q 退出
        full_script = command_script.strip()
        if not full_script.endswith("q"):
            full_script += "\nq\nq\n"
        else:
            full_script += "\nq\n"

        proc = subprocess.run(
            [str(self._executable), str(inp)],
            input=full_script,
            text=True,
            capture_output=True,
            cwd=str(self.work_dir),
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc

    # =========================================================================
    # 1. QTAIM 拓扑临界点与键径分析 (Menu 2)
    # =========================================================================

    def run_qtaim_analysis(self, wfn_path: str | Path, timeout: int = 90) -> QTAIMResult:
        """执行 Bader QTAIM 拓扑分析：搜索 CPs，生成键径，提取完整实空间性质。"""
        # Multiwfn 指令流:
        # 2: Topology analysis
        # 2: Search CPs from nuclear positions
        # 3: Search CPs from midpoint of atomic pairs
        # 8: Generating the paths connecting (3,-3) and (3,-1) CPs
        # -5 -> 4 -> 0: Save points of all paths to paths.txt, return
        # 7 -> -1: Show and output properties of all CPs to CPprop.txt
        # q -> q: Exit
        script = "\n".join([
            "2",
            "2",
            "3",
            "8",
            "-5",
            "4",
            "0",
            "7",
            "-1",
            "q",
            "q",
        ])

        proc = self._run_commands(wfn_path, script, timeout=timeout)
        stem = Path(wfn_path).stem

        # 查找输出文件: Multiwfn 自动生成 <stem>_CPprop.txt 或 CPprop.txt
        cpprop_candidates = [
            self.work_dir / f"{stem}_CPprop.txt",
            self.work_dir / "CPprop.txt",
        ]
        cpprop_path = next((p for p in cpprop_candidates if p.is_file()), None)

        paths_candidates = [
            self.work_dir / "paths.txt",
            self.work_dir / f"{stem}_paths.txt",
        ]
        paths_path = next((p for p in paths_candidates if p.is_file()), None)

        cps: List[CriticalPoint] = []
        if cpprop_path and cpprop_path.exists():
            cps = self._parse_cpprop(cpprop_path.read_text(encoding="utf-8", errors="replace"))

        bond_paths: List[BondPath] = []
        if paths_path and paths_path.exists():
            bond_paths = self._parse_paths(paths_path.read_text(encoding="utf-8", errors="replace"))

        return QTAIMResult(
            critical_points=cps,
            paths=bond_paths,
            raw_summary=proc.stdout,
        )

    def _parse_cpprop(self, text: str) -> List[CriticalPoint]:
        cps: List[CriticalPoint] = []
        blocks = re.split(r"-{4,}\s+CP\s+(\d+),\s+Type\s+(\([3\+\-1\,]+\))\s+-{4,}", text)
        i = 1
        type_names = {
            "(3,-3)": "核引力中心 Nuclear Attractor (3,-3)",
            "(3,-1)": "键临界点 Bond Critical Point (3,-1)",
            "(3,+1)": "环临界点 Ring Critical Point (3,+1)",
            "(3,+3)": "笼临界点 Cage Critical Point (3,+3)",
        }

        while i < len(blocks) - 2:
            cp_idx = int(blocks[i])
            cp_type = blocks[i+1].strip()
            body = blocks[i+2]
            i += 3

            type_name = type_names.get(cp_type, f"临界点 {cp_type}")
            m_nuc = re.search(r"Corresponding nucleus:\s*(.+)", body)
            nucleus = m_nuc.group(1).strip() if m_nuc else None

            pos_bohr = np.zeros(3)
            pos_ang = np.zeros(3)
            m_bohr = re.search(r"Position \(Bohr\):\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)", body)
            if m_bohr:
                pos_bohr = np.array([float(m_bohr.group(1)), float(m_bohr.group(2)), float(m_bohr.group(3))])
            m_ang = re.search(r"Position \(Angstrom\):\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)", body)
            if m_ang:
                pos_ang = np.array([float(m_ang.group(1)), float(m_ang.group(2)), float(m_ang.group(3))])
            elif m_bohr:
                pos_ang = pos_bohr * BOHR_TO_ANGSTROM

            def _val(pat: str) -> float:
                m = re.search(pat, body)
                if m:
                    try:
                        return float(m.group(1))
                    except ValueError:
                        return 0.0
                return 0.0

            cps.append(CriticalPoint(
                index=cp_idx,
                cp_type=cp_type,
                type_name=type_name,
                coords_angstrom=pos_ang,
                coords_bohr=pos_bohr,
                nucleus=nucleus,
                rho=_val(r"Density of all electrons:\s+([-\d\.\+Eed]+)"),
                laplacian=_val(r"Laplacian of electron density:\s+([-\d\.\+Eed]+)"),
                energy_density_H=_val(r"Energy density E\(r\) or H\(r\):\s+([-\d\.\+Eed]+)"),
                potential_energy_V=_val(r"Potential energy density V\(r\):\s+([-\d\.\+Eed]+)"),
                lagrangian_kinetic_G=_val(r"Lagrangian kinetic energy G\(r\):\s+([-\d\.\+Eed]+)"),
                elf=_val(r"Electron localization function \(ELF\):\s+([-\d\.\+Eed]+)"),
                lol=_val(r"Localized orbital locator \(LOL\):\s+([-\d\.\+Eed]+)"),
                rdg=_val(r"Reduced density gradient \(RDG\):\s+([-\d\.\+Eed]+)"),
                sign_lambda2_rho=_val(r"Sign\(lambda2\)\*rho:\s+([-\d\.\+Eed]+)"),
                ellipticity=_val(r"Ellipticity of electron density:\s+([-\d\.\+Eed]+)"),
            ))
        return cps

    def _parse_paths(self, text: str) -> List[BondPath]:
        paths: List[BondPath] = []
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("Path index:"):
                parts = line.split(":")
                path_idx = int(parts[1].strip())
                i += 1
                if i >= len(lines):
                    break
                try:
                    n_pts = int(lines[i].strip())
                except ValueError:
                    i += 1
                    continue
                pts_bohr = []
                i += 1
                for _ in range(n_pts):
                    if i < len(lines):
                        pt_parts = lines[i].split()
                        if len(pt_parts) >= 3:
                            try:
                                pts_bohr.append([float(pt_parts[0]), float(pt_parts[1]), float(pt_parts[2])])
                            except ValueError:
                                pass
                        i += 1
                if pts_bohr:
                    arr_bohr = np.array(pts_bohr, dtype=float)
                    arr_ang = arr_bohr * BOHR_TO_ANGSTROM
                    paths.append(BondPath(
                        path_index=path_idx,
                        points_angstrom=arr_ang,
                        points_bohr=arr_bohr,
                    ))
            else:
                i += 1
        return paths

    # =========================================================================
    # 2. NCI / RDG 弱相互作用分析 (Menu 20)
    # =========================================================================

    def run_nci_analysis(
        self,
        input_file: str | Path,
        grid_quality: int = 1, # 1: low (fast), 2: medium, 3: high
        is_promolecular: Optional[bool] = None,
        timeout: int = 120,
    ) -> NCIResult:
        """执行 NCI / RDG 分析，生成 sign(λ₂)ρ 与 RDG 3D Cube 网格及散点。"""
        inp = Path(input_file).resolve()
        if is_promolecular is None:
            # 自动识别：若为 xyz / pdb 则使用分子原初密度近似
            is_promolecular = inp.suffix.lower() in [".xyz", ".pdb", ".gro"]

        mode = "2" if is_promolecular else "1"
        # 指令流:
        # 20: Visual study of weak interaction
        # 1 or 2: NCI analysis (ab initio or promolecular)
        # grid_quality: 1 (fast/low) or 2 (medium)
        # 3: Output cube files to func1.cub (sign(λ₂)ρ) and func2.cub (RDG)
        # 2: Output scatter points to output.txt
        # q -> q: Exit
        script = "\n".join([
            "20",
            mode,
            str(grid_quality),
            "3",
            "2",
            "q",
            "q",
        ])

        self._run_commands(inp, script, timeout=timeout)

        f1 = self.work_dir / "func1.cub"
        f2 = self.work_dir / "func2.cub"
        scatter_file = self.work_dir / "output.txt"

        s_rho_cube = read_cube(f1, convert_bohr=True) if f1.is_file() else None
        rdg_cube = read_cube(f2, convert_bohr=True) if f2.is_file() else None

        scatter_data = None
        if scatter_file.is_file():
            try:
                raw = np.loadtxt(str(scatter_file), comments="#")
                if raw.ndim == 2 and raw.shape[1] >= 2:
                    scatter_data = raw[:, :2] # col 0: sign(λ₂)ρ, col 1: RDG
            except Exception:
                pass

        return NCIResult(
            sign_lambda2_rho_cube=s_rho_cube,
            rdg_cube=rdg_cube,
            scatter_points=scatter_data,
            is_promolecular=is_promolecular,
            cube_files=[p for p in (f1, f2) if p.is_file()],
        )

    # =========================================================================
    # 3. ELF / LOL / ESP 空间三维网格 (Menu 5)
    # =========================================================================

    def run_grid_calculation(
        self,
        wfn_path: str | Path,
        func_type: int = 9, # 9: ELF, 10: LOL, 12: ESP, 1: Rho, 3: Laplacian
        grid_quality: int = 1,
        timeout: int = 120,
    ) -> Optional[CubeData]:
        """计算空间网格属性 (ELF/LOL/ESP) 并导出为 CubeData。"""
        # 指令流:
        # 5: Output and plot specific property in spatial region
        # <func_type>: 9 (ELF) / 10 (LOL) / 12 (ESP)
        # <grid_quality>: 1 (low) / 2 (medium)
        # 2: Export data to a Gaussian cube file in current folder
        # 0: Return
        # q: Exit
        script = "\n".join([
            "5",
            str(func_type),
            str(grid_quality),
            "2",
            "0",
            "q",
        ])

        self._run_commands(wfn_path, script, timeout=timeout)
        stem = Path(wfn_path).stem

        type_suffixes = {
            9: "ELF",
            10: "LOL",
            12: "ESP",
            1: "density",
            3: "laplacian",
        }
        suf = type_suffixes.get(func_type, f"func{func_type}")

        # Multiwfn 自动生成 <stem>_<suf>.cub
        cub_candidates = [
            self.work_dir / f"{stem}_{suf}.cub",
            self.work_dir / f"{stem}_{suf.lower()}.cub",
            self.work_dir / f"{stem}_{suf.upper()}.cub",
            self.work_dir / "density.cub",
        ]
        target = next((p for p in cub_candidates if p.is_file()), None)
        if target:
            return read_cube(target, convert_bohr=True)
        return None

    # =========================================================================
    # 4. ADCH / Hirshfeld 原子电荷与偶极 (Menu 7)
    # =========================================================================

    def run_population_analysis(
        self,
        wfn_path: str | Path,
        method: str = "ADCH", # "ADCH", "Hirshfeld", "CM5", "RESP"
        grid_quality: int = 1,
        timeout: int = 90,
    ) -> PopulationResult:
        """执行布居分析计算原子净电荷。推荐 ADCH（校正原子偶极的赫氏电荷）。"""
        method_map = {
            "HIRSHFELD": "1",
            "ADCH": "11",
            "CM5": "16",
            "RESP": "18",
        }
        opt = method_map.get(method.upper(), "11")

        script = "\n".join([
            "7",
            opt,
            str(grid_quality),
            "n", # Don't output .chg file, we parse stdout directly
            "0",
            "q",
        ])

        proc = self._run_commands(wfn_path, script, timeout=timeout)
        return self._parse_population_output(proc.stdout, method)

    def _parse_population_output(self, text: str, method: str) -> PopulationResult:
        charges: Dict[int, float] = {}
        labels: Dict[int, str] = {}
        dipole_au = None

        m_dip = re.search(r"X/Y/Z of dipole moment from the charge \(a\.u\.\)\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)", text)
        if m_dip:
            dipole_au = np.array([float(m_dip.group(1)), float(m_dip.group(2)), float(m_dip.group(3))])

        # Atom    1(O ):    -0.36728452
        for line in text.splitlines():
            m = re.match(r"\s*Atom\s+(\d+)\((.+?)\)\s*:\s*([-\d\.\+Eed]+)", line)
            if m:
                idx = int(m.group(1))
                sym = m.group(2).strip()
                val = float(m.group(3))
                charges[idx] = val
                labels[idx] = sym

        dipole_debye = dipole_au * 2.5417464519 if dipole_au is not None else None

        return PopulationResult(
            method=method,
            charges=charges,
            atom_labels=labels,
            dipole_au=dipole_au,
            dipole_debye=dipole_debye,
        )

    # =========================================================================
    # 5. Mayer 键级分析 (Menu 9)
    # =========================================================================

    def run_mayer_bond_order(
        self,
        fchk_path: str | Path,
        threshold: float = 0.05,
        timeout: int = 90,
    ) -> MayerBondOrderResult:
        """从 Gaussian .fchk 计算 Mayer 键级与原子总价。"""
        script = "\n".join([
            "9",
            "1", # Mayer bond order
            "n", # Don't output bndmat.txt
            "0",
            "q",
        ])

        proc = self._run_commands(fchk_path, script, timeout=timeout)
        return self._parse_mayer_output(proc.stdout)

    def _parse_mayer_output(self, text: str) -> MayerBondOrderResult:
        bos: Dict[Tuple[int, int], float] = {}
        valences: Dict[int, float] = {}
        free_vals: Dict[int, float] = {}
        labels: Dict[int, str] = {}

        lines = text.splitlines()
        in_bo = False
        in_val = False

        for line in lines:
            if "Bond orders with absolute value >=" in line:
                in_bo = True
                in_val = False
                continue
            elif "Total valences and free valences defined by Mayer:" in line:
                in_bo = False
                in_val = True
                continue
            elif "If outputting bond order matrix" in line or "================" in line:
                in_bo = False
                in_val = False

            if in_bo:
                # #    1:         1(C )    2(H )    0.93327430
                m = re.search(r"#\s*\d+:\s+(\d+)\((.+?)\)\s+(\d+)\((.+?)\)\s+([-\d\.\+Eed]+)", line)
                if m:
                    a1 = int(m.group(1))
                    sym1 = m.group(2).strip()
                    a2 = int(m.group(3))
                    sym2 = m.group(4).strip()
                    bo = float(m.group(5))
                    bos[(a1, a2)] = bo
                    labels[a1] = sym1
                    labels[a2] = sym2

            elif in_val:
                # Atom     1(C ) :    3.78818001    0.00000000
                m = re.search(r"Atom\s+(\d+)\((.+?)\)\s*:\s+([-\d\.\+Eed]+)\s+([-\d\.\+Eed]+)", line)
                if m:
                    a_idx = int(m.group(1))
                    sym = m.group(2).strip()
                    t_val = float(m.group(3))
                    f_val = float(m.group(4))
                    valences[a_idx] = t_val
                    free_vals[a_idx] = f_val
                    labels[a_idx] = sym

        return MayerBondOrderResult(
            bond_orders=bos,
            total_valences=valences,
            free_valences=free_vals,
            atom_labels=labels,
        )

    # =========================================================================
    # 6. 从当前 MoleculeDocument 导出临时 XYZ 用于 Multiwfn
    # =========================================================================

    def export_document_xyz(self, doc: Any, output_name: str = "current_mol.xyz") -> Path:
        """将当前 MolForge MoleculeDocument 导出为标准 XYZ 文件 (用于 Promolecular NCI 等)。"""
        out_path = self.work_dir / output_name
        coords = doc.coordinates.get_3d_coords()
        atoms = doc.topology.atoms

        lines = [str(len(atoms)), "Generated by MolForge for Multiwfn Analysis"]
        for i, atom in enumerate(atoms):
            sym = getattr(atom, "symbol", None) or getattr(atom, "element", "C")
            pos = coords[i]
            lines.append(f"{sym:<2} {pos[0]:14.8f} {pos[1]:14.8f} {pos[2]:14.8f}")

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path
