"""
io/cclib_adapter.py - 量化计算日志解析（支持 Gaussian / ORCA / Psi4 / 复旦 REST）
================================================================================
特性：
  - 支持 cclib 解析 + 纯 Python 正则深度兜底解析（无需安装 cclib 也能完整解析 Gaussian 与 REST 日志！）
  - 提取基态 SCF 能量 (Hartree 与 eV)、HOMO / LUMO / 能隙 (eV)、偶极矩 (Debye 与三维矢量)
  - 提取零点能 (ZPE)、吉布斯自由能 (Gibbs Free Energy)、热力学焓 (Enthalpy)
  - 提取简正振动频率与虚频判定（虚频数量、虚频列表，区分过渡态与稳定极小点）
  - 提取 Mulliken 原子净电荷分布明细表 (用于 3D 视口电荷渲染与亲核/亲电位点分析)
  - 提取 TD-DFT 激发态 (S1 波长 nm / 激发能 eV / 振子强度 f) 与几何优化步轨迹
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HARTREE_TO_EV = 27.211386245988


@dataclass
class QuantumResult:
    """量化计算结果。"""
    software: str  # gaussian / orca / rest / psi4
    method: str = ""
    basis: str = ""
    charge: int = 0
    multiplicity: int = 1
    energy: float = 0.0                  # eV
    energy_hartree: float = 0.0          # a.u. (Hartree)
    homo: float = 0.0                    # eV
    lumo: float = 0.0                    # eV
    gap: float = 0.0                     # eV
    dipole_debye: float = 0.0            # Debye
    dipole_vector: tuple[float, float, float] = (0.0, 0.0, 0.0)
    zpe_hartree: float = 0.0             # Zero-point energy (Hartree)
    gibbs_free_energy_hartree: float = 0.0 # G (Hartree)
    enthalpy_hartree: float = 0.0        # H (Hartree)
    s1_energy_ev: float = 0.0            # TD-DFT S1 光学带隙 (eV)
    s1_wavelength_nm: float = 0.0
    s1_oscillator_f: float = 0.0
    excited_states: list[dict] = field(default_factory=list)
    converged: bool = True
    optimization_steps: list[dict] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)              # cm^-1
    imaginary_frequencies: list[float] = field(default_factory=list)    # cm^-1 (<0)
    mulliken_charges: dict[int, float] = field(default_factory=dict)     # {atom_idx: charge_e}
    coordinates: np.ndarray | None = None
    n_atoms: int = 0
    atomic_numbers: list[int] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)


class CCLibAdapter:
    """
    量化计算日志统一解析器（Gaussian / ORCA / REST / Psi4）。
    """

    def __init__(self) -> None:
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import cclib  # noqa: F401
            return True
        except ImportError:
            return False

    def detect_software(self, filepath: str | Path) -> str:
        filepath = Path(filepath)
        try:
            head = filepath.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
            if "gaussian" in head:
                return "gaussian"
            if "orca" in head:
                return "orca"
            if "rust-based electronic structure" in head or "[ctrl]" in head or "rest" in head:
                return "rest"
            if "psi4" in head:
                return "psi4"
        except Exception:
            pass
        return "unknown"

    def parse(self, filepath: str | Path) -> QuantumResult:
        filepath = Path(filepath)
        if not filepath.exists():
            return QuantumResult(software="unknown", converged=False, missing_data=["文件不存在"])

        sw = self.detect_software(filepath)
        text = filepath.read_text(encoding="utf-8", errors="replace")

        # 1. 若是复旦 REST 日志，走专用 REST 解析器
        if sw == "rest":
            return self._parse_rest_text(text)

        # 2. 尝试用 cclib 解析
        if self._available:
            try:
                import cclib.io
                data = cclib.io.ccread(str(filepath))
                if data is not None:
                    res = self._from_cclib_data(data)
                    # 补充提取 TD-DFT 与热力学参数
                    self._enrich_from_text(res, text)
                    return res
            except Exception:
                pass

        # 3. 纯 Python 正则深度解析 Gaussian / ORCA 日志
        return self._parse_gaussian_or_orca_fallback(text, sw)

    def _from_cclib_data(self, data) -> QuantumResult:
        md = getattr(data, "metadata", {})
        methods = md.get("methods", [])
        functional = md.get("functional", "")
        method_str = functional or (methods[-1] if methods else "")
        result = QuantumResult(
            software=str(md.get("package", "Gaussian")),
            method=str(method_str),
            basis=str(md.get("basis_set", "")),
            charge=int(getattr(data, "charge", 0)),
            multiplicity=int(getattr(data, "mult", 1)),
        )

        if hasattr(data, "scfenergies") and len(data.scfenergies) > 0:
            result.energy = float(data.scfenergies[-1])
            result.energy_hartree = result.energy / HARTREE_TO_EV
        else:
            result.missing_data.append("能量")

        if hasattr(data, "moenergies") and hasattr(data, "homos"):
            mo_e = data.moenergies[0]
            h = int(data.homos[0])
            if 0 <= h and h + 1 < len(mo_e):
                result.homo = float(mo_e[h])
                result.lumo = float(mo_e[h + 1])
                result.gap = result.lumo - result.homo
        else:
            result.missing_data.append("轨道能级")

        result.converged = bool(getattr(data, "success", True))

        if hasattr(data, "optstatus"):
            for i, status in enumerate(data.optstatus):
                coords = None
                if hasattr(data, "atomcoords") and i < len(data.atomcoords):
                    coords = np.array(data.atomcoords[i])
                step = {
                    "step": i,
                    "energy": float(data.scfenergies[i]) if i < len(data.scfenergies) else 0.0,
                    "converged": bool(status & 4),
                    "coords": coords,
                }
                result.optimization_steps.append(step)

        if hasattr(data, "vibfreqs"):
            result.frequencies = [float(f) for f in data.vibfreqs]
            result.imaginary_frequencies = [float(f) for f in data.vibfreqs if f < 0.0]
        else:
            result.missing_data.append("频率")

        if hasattr(data, "atomcharges") and isinstance(data.atomcharges, dict):
            if "mulliken" in data.atomcharges:
                result.mulliken_charges = {i: float(c) for i, c in enumerate(data.atomcharges["mulliken"])}

        if hasattr(data, "moments") and len(data.moments) > 1:
            dip = data.moments[1]
            if dip is not None and len(dip) == 3:
                result.dipole_vector = (float(dip[0]), float(dip[1]), float(dip[2]))
                result.dipole_debye = float(np.linalg.norm(dip))

        if hasattr(data, "zpve"):
            result.zpe_hartree = float(data.zpve)

        if hasattr(data, "atomcoords") and len(data.atomcoords) > 0:
            result.coordinates = np.array(data.atomcoords[-1])
            result.n_atoms = len(result.coordinates)
        else:
            result.missing_data.append("坐标")

        if hasattr(data, "atomnos"):
            result.atomic_numbers = [int(z) for z in data.atomnos]

        return result

    def _enrich_from_text(self, result: QuantumResult, text: str) -> None:
        """从日志文本补充提取激发态、热力学修正及 Mulliken 电荷。"""
        # TD-DFT 激发态
        pattern = re.compile(
            r"Excited State\s+(\d+):\s+([A-Za-z0-9\-\?]+)\s+(-?\d+\.\d+)\s+eV\s+(\d+\.\d+)\s+nm\s+f=(\d+\.\d+)"
        )
        states = []
        for m in pattern.finditer(text):
            states.append({
                "index": int(m.group(1)),
                "symmetry": m.group(2),
                "energy_ev": float(m.group(3)),
                "wavelength_nm": float(m.group(4)),
                "oscillator_f": float(m.group(5)),
            })
        if states:
            result.excited_states = states
            s1 = states[0]
            result.s1_energy_ev = s1["energy_ev"]
            result.s1_wavelength_nm = s1["wavelength_nm"]
            result.s1_oscillator_f = s1["oscillator_f"]

        # 偶极矩
        if result.dipole_debye == 0.0:
            dip_matches = re.findall(
                r"Dipole moment.*?\n\s*X=\s*([-\d\.]+)\s+Y=\s*([-\d\.]+)\s+Z=\s*([-\d\.]+)\s+Tot=\s*([-\d\.]+)",
                text
            )
            if dip_matches:
                dx, dy, dz, dtot = dip_matches[-1]
                result.dipole_vector = (float(dx), float(dy), float(dz))
                result.dipole_debye = float(dtot)

        # 热力学修正
        zpe_m = re.search(r"Zero-point correction=\s*([-\d\.]+)", text)
        if zpe_m:
            result.zpe_hartree = float(zpe_m.group(1))

        gibbs_m = re.search(r"Sum of electronic and thermal Free Energies=\s*([-\d\.]+)", text)
        if gibbs_m:
            result.gibbs_free_energy_hartree = float(gibbs_m.group(1))

        enth_m = re.search(r"Sum of electronic and thermal Enthalpies=\s*([-\d\.]+)", text)
        if enth_m:
            result.enthalpy_hartree = float(enth_m.group(1))

        # Mulliken 电荷
        if not result.mulliken_charges:
            mull_matches = list(re.finditer(
                r"Mulliken (?:atomic )?charges(?:\s+and spin densities)?:\s*\n(?:\s+\d+\s*\n)?((?:\s+\d+\s+[A-Za-z]+\s+[-+]?\d+\.\d+\s*\n)+)",
                text
            ))
            if mull_matches:
                last_block = mull_matches[-1].group(1)
                for line in last_block.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and parts[0].isdigit():
                        idx = int(parts[0]) - 1
                        try:
                            result.mulliken_charges[idx] = float(parts[2])
                        except ValueError:
                            pass

    def _parse_rest_text(self, text: str) -> QuantumResult:
        """解析复旦 REST 输出文件。"""
        from ..application.calculators.rest_engine import parse_rest_log_text
        info = parse_rest_log_text(text)
        xc_m = re.search(r'xc\s*=\s*"?([A-Za-z0-9\-_]+)"?', text)
        bas_m = re.search(r'basis_path\s*=\s*"?([^"\n]+)"?', text)
        res = QuantumResult(
            software="REST (Fudan)",
            method=(xc_m.group(1).upper() if xc_m else "DFT/xDH"),
            basis=(Path(bas_m.group(1).strip()).name if bas_m else "def2-TZVPP"),
            energy=float(info["final_energy_ev"] or 0.0),
            energy_hartree=(float(info["final_energy_ev"] or 0.0) / HARTREE_TO_EV),
            homo=float(info["homo_ev"] or 0.0),
            lumo=float(info["lumo_ev"] or 0.0),
            gap=float(info["gap_ev"] or 0.0),
            converged=bool(info["converged"]),
        )
        if not res.energy:
            res.missing_data.append("能量")
        if not res.gap:
            res.missing_data.append("轨道能级")
        return res

    def _parse_gaussian_or_orca_fallback(self, text: str, sw: str) -> QuantumResult:
        """纯 Python 正则深度解析 Gaussian / ORCA 日志。"""
        res = QuantumResult(software=sw.capitalize() if sw != "unknown" else "Gaussian")

        # 1. 提取理论方法与 SCF Done 能量
        scf = re.findall(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*(-?\d+\.\d+)", text)
        if scf:
            res.method = scf[-1][0]
            res.energy_hartree = float(scf[-1][1])
            res.energy = res.energy_hartree * HARTREE_TO_EV
        else:
            # ORCA 兼容
            orca_scf = re.findall(r"FINAL SINGLE POINT ENERGY\s+([-\d\.]+)", text)
            if orca_scf:
                res.energy_hartree = float(orca_scf[-1])
                res.energy = res.energy_hartree * HARTREE_TO_EV
                res.method = "DFT/HF"
            else:
                res.missing_data.append("能量")

        # 2. 提取基组
        bas_m = re.search(r"Standard basis:\s+([^\(\n]+)", text)
        if bas_m:
            res.basis = bas_m.group(1).strip()

        # 3. 提取前线轨道 Alpha occ. eigenvalues 与 Alpha virt. eigenvalues
        occ_lines = re.findall(r"Alpha\s+occ\.\s+eigenvalues\s+--\s+([-\d\.\s]+)", text)
        virt_lines = re.findall(r"Alpha\s+virt\.\s+eigenvalues\s+--\s+([-\d\.\s]+)", text)
        if occ_lines and virt_lines:
            occ_vals = [float(x) for x in occ_lines[-1].split()]
            virt_vals = [float(x) for x in virt_lines[0].split()]
            if occ_vals and virt_vals:
                res.homo = occ_vals[-1] * HARTREE_TO_EV
                res.lumo = virt_vals[0] * HARTREE_TO_EV
                res.gap = res.lumo - res.homo
        else:
            res.missing_data.append("轨道能级")

        # 4. 振动分析频率与虚频判定
        freq_matches = re.findall(r"Frequencies\s*--\s*([-\d\.\s]+)", text)
        freqs = []
        for fm in freq_matches:
            for x in fm.split():
                try:
                    freqs.append(float(x))
                except ValueError:
                    pass
        if freqs:
            res.frequencies = freqs
            res.imaginary_frequencies = [f for f in freqs if f < 0.0]

        # 5. 补充激发态、偶极矩与热力学修正
        self._enrich_from_text(res, text)

        # 6. 提取分子坐标与原子种类
        std_blocks = list(re.finditer(
            r"(?:Standard|Input)\s+orientation:\s*\n\s*-+\s*\n\s*Center\s+Atomic\s+Atomic\s+Coordinates\s+\(Angstroms\)\s*\n\s*Number\s+Number\s+Type\s+X\s+Y\s+Z\s*\n\s*-+\s*\n((?:\s*\d+\s+\d+\s+\d+\s+[-\d\.]+\s+[-\d\.]+\s+[-\d\.]+\s*\n)+)\s*-+",
            text
        ))
        if std_blocks:
            last_coords_text = std_blocks[-1].group(1)
            at_nums: list[int] = []
            coords_list: list[list[float]] = []
            for line in last_coords_text.strip().splitlines():
                p = line.split()
                if len(p) >= 6:
                    try:
                        at_nums.append(int(p[1]))
                        coords_list.append([float(p[3]), float(p[4]), float(p[5])])
                    except ValueError:
                        pass
            if at_nums and coords_list:
                res.atomic_numbers = at_nums
                res.coordinates = np.array(coords_list, dtype=np.float32)
                res.n_atoms = len(at_nums)

        res.converged = ("Normal termination" in text) or ("THE OPTIMIZATION HAS CONVERGED" in text) or bool(scf)
        return res
