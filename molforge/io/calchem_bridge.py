"""
molforge/io/calchem_bridge.py - CalChem 高性能纯 Rust 量子化学内核桥接器
=======================================================================
提供与 CalChem (_core.pyd) 的直接内存级（In-Process C-ABI / NumPy 零拷贝）对接：
  1. run_calchem_single_point: 毫秒级 RHF/UHF 单点自洽场（自洽能、HOMO/LUMO、偶极矩）
  2. run_calchem_optimization: 纯 Rust BFGS 几何构象极速优化，返回精确Å坐标
  3. extract_calchem_orbital_mesh: 纯 Rust Marching Cubes 提取分子轨道正负等值面三角网格
  4. extract_calchem_esp_surface: 提取电子等密度面并投影分子静电势 (ESP) 标量色谱
  5. eval_calchem_orbital_cube_zero_copy: 直通 3D 标量体网格 (float32 ndarray)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId
from ..application.commands import Command, CommandResult

ANGSTROM_TO_BOHR = 1.8897261245650618
BOHR_TO_ANGSTROM = 0.529177210903


def _ensure_calchem_importable():
    """确保 calchem 可以在 Python 路径中加载。"""
    try:
        from calchem import _core
        return _core
    except ImportError:
        pass

    candidates = [
        Path(r"E:\YDW\Trae_Gaussian"),
        Path(r"D:\YDW\Trae_Gaussian"),
        Path(__file__).resolve().parents[3] / "Trae_Gaussian",
    ]
    for p in candidates:
        if (p / "calchem" / "_core.pyd").exists() or (p / "calchem").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            try:
                from calchem import _core
                return _core
            except ImportError:
                continue
    return None


def probe_calchem() -> bool:
    """探测当前环境是否支持 CalChem 原生内核。"""
    core = _ensure_calchem_importable()
    return core is not None


def get_supported_basis_sets() -> list[str]:
    """返回 CalChem 支持的基组列表。"""
    core = _ensure_calchem_importable()
    if core and hasattr(core, "supported_basis_sets"):
        return list(core.supported_basis_sets())
    return ["sto-3g", "6-31g", "6-31g(d)", "6-31g(d,p)", "lanl2dz", "lanl2dzdp"]


def doc_to_calchem_inputs(doc: MoleculeDocument) -> Tuple[List[str], List[List[float]], int, int]:
    """
    将 MoleculeDocument 转为 CalChem 输入元组:
    (symbols, geometry_bohr, charge, multiplicity)
    """
    if not doc.has_3d or doc.coordinates.current is None:
        raise ValueError("当前分子缺少 3D 几何坐标，无法进行量化计算")

    atom_ids = list(doc.topology.atom_ids)
    symbols: list[str] = []
    geom_bohr: list[list[float]] = []

    for aid in atom_ids:
        atom = doc.topology.get_atom(aid)
        symbols.append(atom.symbol)
        pos_ang = doc.get_atom_3d_pos(aid)
        pos_bohr = [float(c * ANGSTROM_TO_BOHR) for c in pos_ang]
        geom_bohr.append(pos_bohr)

    charge = int(getattr(doc, "total_charge", 0))
    multiplicity = int(getattr(doc, "spin_multiplicity", 1))
    return symbols, geom_bohr, charge, multiplicity


def run_calchem_single_point(
    doc: MoleculeDocument,
    basis: str = "sto-3g",
    charge: int = 0,
    multiplicity: int = 1,
    method: str = "rhf",
) -> Dict[str, Any]:
    """
    运行纯 Rust CalChem 单点能计算。
    """
    core = _ensure_calchem_importable()
    if core is None:
        return {"success": False, "error": "CalChem 原生扩展 (_core.pyd) 未找到"}

    try:
        symbols, geom_bohr, c_in, m_in = doc_to_calchem_inputs(doc)
        charge = charge if charge != 0 else c_in
        multiplicity = multiplicity if multiplicity != 1 else m_in

        wf = core.run_single_point(
            symbols=symbols,
            geometry_bohr=geom_bohr,
            charge=charge,
            multiplicity=multiplicity,
            method=method,
            basis=basis.lower(),
        )

        homo_e = wf.homo_energy_hartree
        lumo_e = wf.lumo_energy_hartree
        gap_ev = (lumo_e - homo_e) * 27.211386245988 if (homo_e is not None and lumo_e is not None) else None

        return {
            "success": True,
            "converged": wf.converged,
            "total_energy_hartree": wf.total_energy_hartree,
            "electronic_energy_hartree": wf.electronic_energy_hartree,
            "nuclear_repulsion_hartree": wf.nuclear_repulsion_hartree,
            "homo_energy_hartree": homo_e,
            "lumo_energy_hartree": lumo_e,
            "gap_ev": gap_ev,
            "dipole_debye": wf.dipole_debye,
            "dipole_magnitude_debye": wf.dipole_magnitude_debye,
            "n_ao": wf.n_ao,
            "n_alpha": wf.n_alpha,
            "n_beta": wf.n_beta,
            "wavefunction": wf,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class ApplyCalChemOptCommand(Command):
    """将 CalChem 优化的 3D 几何坐标更新至 MoleculeDocument 的事务命令（支持 Ctrl+Z 撤销）。"""

    description = "应用 CalChem 量子化学几何优化"

    def __init__(self, old_coords: np.ndarray, new_coords: np.ndarray, energy: float):
        self.old_coords = old_coords.copy()
        self.new_coords = new_coords.copy()
        self.energy = energy

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="缺少 3D 坐标无法回填优化结果")
        doc.coordinates.update_current_coords(self.new_coords.copy())
        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message=f"已成功应用 CalChem 优化几何（能量: {self.energy:.6f} Hartree）",
            data={"energy": self.energy},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="缺少 3D 坐标无法撤销")
        doc.coordinates.update_current_coords(self.old_coords.copy())
        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message="已撤销 CalChem 几何优化，恢复初始坐标",
        )


def run_calchem_optimization(
    doc: MoleculeDocument,
    basis: str = "sto-3g",
    max_steps: int = 100,
    charge: int = 0,
    multiplicity: int = 1,
) -> Dict[str, Any]:
    """
    运行纯 Rust CalChem BFGS 解析梯度几何构象优化。
    """
    core = _ensure_calchem_importable()
    if core is None:
        return {"success": False, "error": "CalChem 原生扩展 (_core.pyd) 未找到"}

    try:
        symbols, geom_bohr, c_in, m_in = doc_to_calchem_inputs(doc)
        charge = charge if charge != 0 else c_in
        multiplicity = multiplicity if multiplicity != 1 else m_in

        opt_res = core.run_optimize(
            symbols,
            geom_bohr,
            basis=basis.lower(),
            max_steps=max_steps,
            charge=charge,
            multiplicity=multiplicity,
        )

        n_atoms = len(symbols)
        coords_bohr = np.array(opt_res.coords, dtype=np.float64).reshape(n_atoms, 3)
        coords_angstrom = (coords_bohr * BOHR_TO_ANGSTROM).astype(np.float32)

        return {
            "success": True,
            "converged": opt_res.converged,
            "energy_hartree": opt_res.energy,
            "steps": opt_res.steps,
            "coords": coords_angstrom,
            "command": ApplyCalChemOptCommand(
                doc.coordinates.current.coords, coords_angstrom, opt_res.energy
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_calchem_orbital_mesh(
    doc_or_wf: Union[MoleculeDocument, Any],
    mo_idx: Optional[int] = None,
    isovalue: float = 0.03,
    basis: str = "sto-3g",
) -> Dict[str, Any]:
    """
    提取指定分子轨道的 3D 双相等值面三角网格（单位为 Å，支持直通渲染）。
    """
    core = _ensure_calchem_importable()
    if core is None:
        return {"success": False, "error": "CalChem 原生扩展 (_core.pyd) 未找到"}

    try:
        if isinstance(doc_or_wf, MoleculeDocument):
            sp = run_calchem_single_point(doc_or_wf, basis=basis)
            if not sp.get("success"):
                return sp
            wf = sp["wavefunction"]
        else:
            wf = doc_or_wf

        # 若未指定 mo_idx，默认展示 HOMO (n_alpha - 1)
        if mo_idx is None:
            mo_idx = max(0, wf.n_alpha - 1)

        dual_mesh = core.extract_orbital_isosurface(
            wf=wf,
            mo_idx=mo_idx,
            isovalue=float(isovalue),
            output_angstrom=True,
        )

        pos_v = dual_mesh.positive.vertices
        pos_f = dual_mesh.positive.faces.reshape(-1, 3) if dual_mesh.positive.faces.ndim == 1 else dual_mesh.positive.faces
        neg_v = dual_mesh.negative.vertices
        neg_f = dual_mesh.negative.faces.reshape(-1, 3) if dual_mesh.negative.faces.ndim == 1 else dual_mesh.negative.faces

        mo_energy = wf.mo_energies[mo_idx] if mo_idx < len(wf.mo_energies) else None
        is_homo = (mo_idx == (wf.n_alpha - 1))
        is_lumo = (mo_idx == wf.n_alpha)

        return {
            "success": True,
            "mo_idx": mo_idx,
            "is_homo": is_homo,
            "is_lumo": is_lumo,
            "mo_energy_hartree": mo_energy,
            "mo_energy_ev": mo_energy * 27.211386245988 if mo_energy is not None else None,
            "isovalue": isovalue,
            "positive_vertices": pos_v,
            "positive_faces": pos_f,
            "positive_normals": dual_mesh.positive.normals,
            "negative_vertices": neg_v,
            "negative_faces": neg_f,
            "negative_normals": dual_mesh.negative.normals,
            "binary_packet": dual_mesh.to_binary_packet(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_calchem_esp_surface(
    doc_or_wf: Union[MoleculeDocument, Any],
    density_isovalue: float = 0.001,
    basis: str = "sto-3g",
) -> Dict[str, Any]:
    """
    提取电子等密度面并投影分子静电势 (ESP)，返回带标量着色数据的三角网格。
    """
    core = _ensure_calchem_importable()
    if core is None:
        return {"success": False, "error": "CalChem 原生扩展 (_core.pyd) 未找到"}

    try:
        if isinstance(doc_or_wf, MoleculeDocument):
            sp = run_calchem_single_point(doc_or_wf, basis=basis)
            if not sp.get("success"):
                return sp
            wf = sp["wavefunction"]
        else:
            wf = doc_or_wf

        esp_surf = core.extract_esp_surface(
            wf=wf,
            density_isovalue=float(density_isovalue),
            output_angstrom=True,
        )

        mesh_v = esp_surf.mesh.vertices
        mesh_f = esp_surf.mesh.faces.reshape(-1, 3) if esp_surf.mesh.faces.ndim == 1 else esp_surf.mesh.faces

        return {
            "success": True,
            "density_isovalue": density_isovalue,
            "esp_min": esp_surf.esp_min,
            "esp_max": esp_surf.esp_max,
            "vertices": mesh_v,
            "faces": mesh_f,
            "esp_scalars": esp_surf.esp,  # float32 scalar per vertex
            "binary_packet": esp_surf.to_binary_packet(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def eval_calchem_orbital_cube_zero_copy(
    doc_or_wf: Union[MoleculeDocument, Any],
    mo_idx: Optional[int] = None,
    margin_bohr: float = 3.5,
    spacing_bohr: float = 0.3,
    basis: str = "sto-3g",
) -> Dict[str, Any]:
    """
    计算分子轨道 3D 体网格数据，直通 NumPy float32 ndarray（形状为 (nz, ny, nx)）。
    """
    core = _ensure_calchem_importable()
    if core is None:
        return {"success": False, "error": "CalChem 原生扩展 (_core.pyd) 未找到"}

    try:
        if isinstance(doc_or_wf, MoleculeDocument):
            sp = run_calchem_single_point(doc_or_wf, basis=basis)
            if not sp.get("success"):
                return sp
            wf = sp["wavefunction"]
        else:
            wf = doc_or_wf

        if mo_idx is None:
            mo_idx = max(0, wf.n_alpha - 1)

        origin, spacing, counts = core.auto_orbital_grid_spec(
            wf, margin_bohr=margin_bohr, spacing_bohr=spacing_bohr
        )
        grid_3d = core.eval_orbital_cube_zero_copy(wf, mo_idx, origin, spacing, counts)

        return {
            "success": True,
            "mo_idx": mo_idx,
            "origin_bohr": origin,
            "spacing_bohr": spacing,
            "counts": counts,
            "grid_3d": grid_3d,  # shape: (nz, ny, nx), dtype: float32
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_calchem_orbital_cube_data(
    doc: MoleculeDocument,
    mo_idx: Optional[int] = None,
    basis: str = "sto-3g",
) -> Any:
    """
    将 CalChem 零拷贝体网格包装为 MolForge 标准的 CubeData 对象，供 3D 视口瞬时秒级渲染。
    """
    from .cube_reader import CubeData
    res = eval_calchem_orbital_cube_zero_copy(doc, mo_idx=mo_idx, basis=basis)
    if not res.get("success"):
        return None

    origin_ang = np.array(res["origin_bohr"], dtype=float) * BOHR_TO_ANGSTROM
    sp_ang = np.array(res["spacing_bohr"], dtype=float) * BOHR_TO_ANGSTROM
    axes_ang = np.diag(sp_ang)
    counts = res["counts"]  # [nx, ny, nz]
    grid_3d = res["grid_3d"]  # (nz, ny, nx)

    values = np.transpose(grid_3d, (2, 1, 0))

    atom_ids = list(doc.topology.atom_ids)
    atomic_numbers = np.array([doc.topology.get_atom(a).atomic_num for a in atom_ids], dtype=int)
    atom_coords = np.array([doc.get_atom_3d_pos(a) for a in atom_ids], dtype=float)

    label = f"CalChem MO #{res['mo_idx']}"
    return CubeData(
        origin=origin_ang,
        axes=axes_ang,
        dims=(counts[0], counts[1], counts[2]),
        atomic_numbers=atomic_numbers,
        atom_coords=atom_coords,
        values=values,
        orbital_index=res["mo_idx"],
        orbital_label=label,
    )
