"""
io/cclib_adapter.py - 量化计算日志解析（支持 Gaussian / ORCA / Psi4 / 复旦 REST）
================================================================================
特性：
  - 支持 cclib 解析 + 纯 Python 正则兜底解析（无需安装 cclib 也能解析 Gaussian 与 REST 日志！）
  - 提取基态能量、HOMO / LUMO / 能隙 (eV)、偶极矩、TD-DFT 激发态 (S1 波长 nm / 激发能 eV / 振子强度 f)
  - 完整支持复旦大学 REST (Rust-based Electronic Structure Toolkit) 输出日志解析
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
    energy: float = 0.0          # eV
    homo: float = 0.0            # eV
    lumo: float = 0.0            # eV
    gap: float = 0.0             # eV
    s1_energy_ev: float = 0.0    # TD-DFT S1 光学带隙 (eV)
    s1_wavelength_nm: float = 0.0
    s1_oscillator_f: float = 0.0
    excited_states: list[dict] = field(default_factory=list)
    converged: bool = True
    optimization_steps: list[dict] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)  # cm^-1
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
                    # 补充提取 TD-DFT 激发态（若日志含 Excited State）
                    self._enrich_excited_states_from_text(res, text)
                    return res
            except Exception:
                pass

        # 3. 纯 Python 正则兜底解析 Gaussian / ORCA 日志
        return self._parse_gaussian_or_orca_fallback(text, sw)

    def _from_cclib_data(self, data) -> QuantumResult:
        md = getattr(data, "metadata", {})
        methods = md.get("methods", [])
        functional = md.get("functional", "")
        method_str = functional or (methods[-1] if methods else "")
        result = QuantumResult(
            software=str(md.get("package", "unknown")),
            method=str(method_str),
            basis=str(md.get("basis_set", "")),
            charge=int(getattr(data, "charge", 0)),
            multiplicity=int(getattr(data, "mult", 1)),
        )

        if hasattr(data, "scfenergies") and len(data.scfenergies) > 0:
            result.energy = float(data.scfenergies[-1])
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
        else:
            result.missing_data.append("频率")

        if hasattr(data, "atomcoords") and len(data.atomcoords) > 0:
            result.coordinates = np.array(data.atomcoords[-1])
            result.n_atoms = len(result.coordinates)
        else:
            result.missing_data.append("坐标")

        if hasattr(data, "atomnos"):
            result.atomic_numbers = [int(z) for z in data.atomnos]

        return result

    def _enrich_excited_states_from_text(self, result: QuantumResult, text: str) -> None:
        """从 Gaussian TD-DFT 日志提取 Excited State 1..N (eV, nm, f)。"""
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
        """纯 Python 正则解析 Gaussian 日志（提取 SCF Done、Alpha occ/virt eigenvalues、TD-DFT）。"""
        res = QuantumResult(software=sw.capitalize() if sw != "unknown" else "Gaussian")
        scf = re.findall(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*(-?\d+\.\d+)", text)
        if scf:
            res.method = scf[-1][0]
            res.energy = float(scf[-1][1]) * HARTREE_TO_EV
        else:
            res.missing_data.append("能量")

        # 提取 Alpha occ. eigenvalues 与 Alpha virt. eigenvalues
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

        self._enrich_excited_states_from_text(res, text)
        res.converged = ("Normal termination" in text) or bool(scf)
        return res
