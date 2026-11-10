"""
application/calculators/gaussian_job_spec.py - Gaussian 11 页签计算配置契约与校验器
===================================================================================
严格实现 4.3 节要求：
  - 统一驱动 11 个页签：Job Type / Method / Title / Link 0 / General / Guess / Pop. / PBC / Solvation / Add. Inp. / Preview
  - 严格校验：
    1. 拒绝空文档提交（绝不将空分子伪装成单个 C 原子提交真实计算！）
    2. 校验电子数与自旋多重度奇偶性匹配
    3. 校验坐标有限性、任务与方法兼容性、PBC 不支持组合拦截
    4. 记录 document_id 与 document_revision，用于防止过期结果覆盖新编辑
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, asdict
from typing import Literal

from ...domain.document import MoleculeDocument
from ...domain.elements import ELEMENTS

JobTypeOption = Literal["Energy", "Optimization", "Frequency", "Opt+Freq", "TD-SCF", "IRC", "Scan"]


@dataclass
class GaussianJobSpec:
    # 1. Job Type
    job_type: JobTypeOption = "Optimization"
    optimize_to_ts: bool = False
    compute_raman: bool = False
    td_nstates: int = 6

    # 2. Method
    theory_family: str = "DFT"        # "HF" | "DFT" | "MP2" | "CCSD(T)" | "Semi-Empirical"
    functional_or_method: str = "B3LYP"
    basis_set: str = "def2SVP"
    dispersion: str = "GD3BJ"         # "None" | "GD3" | "GD3BJ"
    spin_restriction: str = "Default" # "Default" | "Restricted" | "Unrestricted"
    charge: int = 0
    multiplicity: int = 1

    # 3. Title
    title: str = "MolForge Quantum Calculation"

    # 4. Link 0
    memory_gb: int = 12
    nproc_shared: int = 8
    chk_filename: str = "molforge_job.chk"
    save_chk: bool = True

    # 5. General
    scf_convergence: str = "Tight"    # "Normal" | "Tight" | "VeryTight"
    integral_grid: str = "UltraFine"  # "Fine" | "UltraFine" | "SuperFine"
    use_symmetry: bool = True

    # 6. Guess
    guess_type: str = "Default"       # "Default" | "Read" | "Core" | "Huckel" | "Mix"

    # 7. Pop.
    pop_level: str = "Regular"        # "None" | "Minimal" | "Regular" | "Full"
    compute_nbo: bool = False
    compute_esp_charges: bool = False

    # 8. PBC
    enable_pbc: bool = False
    pbc_dimensions: int = 0

    # 9. Solvation
    solvation_model: str = "None"     # "None" | "IEFPCM" | "CPCM" | "SMD"
    solvent: str = "Water"

    # 10. Add. Inp.
    additional_route_keywords: str = ""
    additional_tail_input: str = ""

    # 11. Provenance & Edit Tracking
    document_id: str = ""
    document_revision: int = 0
    custom_edited_gjf: str | None = None

    def to_preset_dict(self) -> dict:
        d = asdict(self)
        d.pop("document_id", None)
        d.pop("document_revision", None)
        d.pop("custom_edited_gjf", None)
        return d

    @classmethod
    def default_spec(cls, doc: MoleculeDocument | None = None) -> "GaussianJobSpec":
        spec = cls()
        if doc is not None:
            spec.document_id = doc.document_id
            spec.document_revision = doc.revision
            spec.title = f"MolForge - {doc.name}"
            spec.charge = int(doc.properties.get("charge", 0))
            z_sum = sum(doc.topology.get_atom(aid).atomic_num for aid in doc.topology.atom_ids)
            n_elec = max(0, z_sum - spec.charge)
            spec.multiplicity = 1 if (n_elec % 2 == 0) else 2
        return spec

    def validate(self, doc: MoleculeDocument, for_submission: bool = True) -> list[str]:
        errors: list[str] = []
        if doc.topology.num_atoms == 0:
            if for_submission:
                errors.append("当前文档为空（0 个原子）：禁止将空结构伪装为单个碳原子提交计算。")
            return errors

        if not doc.has_3d or doc.coordinates.current is None:
            errors.append("当前分子缺少 3D 坐标帧。")
        else:
            coords = doc.coordinates.current.coords
            if len(coords) != doc.topology.num_atoms:
                errors.append(f"坐标数量 ({len(coords)}) 与拓扑原子数 ({doc.topology.num_atoms}) 不一致。")
            elif not all(math.isfinite(float(x)) for x in coords.ravel()):
                errors.append("3D 坐标包含非有限数值 (NaN/Inf)。")

        z_sum = sum(doc.topology.get_atom(aid).atomic_num for aid in doc.topology.atom_ids)
        n_elec = z_sum - int(self.charge)
        if n_elec <= 0:
            errors.append(f"总电子数非正 ({n_elec})，请检查电荷设置 (charge={self.charge})。")
        elif self.multiplicity < 1:
            errors.append(f"自旋多重度必须 >= 1（当前为 {self.multiplicity}）。")
        else:
            n_unpaired = int(self.multiplicity) - 1
            if n_unpaired > n_elec or (n_elec - n_unpaired) % 2 != 0:
                errors.append(
                    f"电子数 ({n_elec}) 与自旋多重度 ({self.multiplicity}) 奇偶性冲突（未成对电子数={n_unpaired}）。"
                )

        if self.enable_pbc and self.theory_family in ("MP2", "CCSD(T)"):
            errors.append(f"周期性边界条件 (PBC) 不支持与后 HF 方法 ({self.theory_family}) 组合。")

        if self.enable_pbc and self.job_type in ("TD-SCF", "IRC"):
            errors.append(f"周期性边界条件 (PBC) 不支持任务类型 {self.job_type}。")

        return errors

    def build_route_section(self) -> str:
        prefix = ""
        if self.spin_restriction == "Restricted":
            prefix = "R"
        elif self.spin_restriction == "Unrestricted":
            prefix = "U"

        if self.theory_family == "HF":
            method_kw = f"{prefix}HF"
        elif self.theory_family == "DFT":
            method_kw = f"{prefix}{self.functional_or_method}"
        else:
            method_kw = f"{prefix}{self.theory_family}"

        tokens = ["#p", f"{method_kw}/{self.basis_set}"]

        if self.job_type == "Optimization":
            tokens.append("Opt=(TS,Calcfc,NoEigenTest)" if self.optimize_to_ts else "Opt")
        elif self.job_type == "Frequency":
            tokens.append("Freq=Raman" if self.compute_raman else "Freq")
        elif self.job_type == "Opt+Freq":
            tokens.append("Opt=(TS,Calcfc,NoEigenTest)" if self.optimize_to_ts else "Opt")
            tokens.append("Freq=Raman" if self.compute_raman else "Freq")
        elif self.job_type == "TD-SCF":
            tokens.append(f"TD=(NStates={max(1, int(self.td_nstates))})")
        elif self.job_type == "IRC":
            tokens.append("IRC=CalcFC")
        elif self.job_type == "Scan":
            tokens.append("Opt=ModRedundant")

        if self.dispersion and self.dispersion != "None":
            tokens.append(f"EmpiricalDispersion={self.dispersion}")

        if self.scf_convergence and self.scf_convergence != "Normal":
            tokens.append(f"SCF={self.scf_convergence}")

        if self.integral_grid and self.integral_grid != "Fine":
            tokens.append(f"Int={self.integral_grid}")

        if not self.use_symmetry:
            tokens.append("NoSymm")

        if self.guess_type and self.guess_type != "Default":
            tokens.append(f"Guess={self.guess_type}")

        pop_opts = []
        if self.pop_level and self.pop_level != "None":
            pop_opts.append(self.pop_level)
        if self.compute_nbo:
            pop_opts.append("NBO")
        if self.compute_esp_charges:
            pop_opts.append("MK")
        if pop_opts:
            tokens.append(f"Pop=({','.join(pop_opts)})" if len(pop_opts) > 1 else f"Pop={pop_opts[0]}")

        if self.solvation_model and self.solvation_model != "None":
            tokens.append(f"SCRF=({self.solvation_model},Solvent={self.solvent})")

        if self.additional_route_keywords.strip():
            tokens.append(self.additional_route_keywords.strip())

        return " ".join(tokens)

    def generate_gjf(self, doc: MoleculeDocument, allow_sample_placeholder: bool = False) -> str:
        if self.custom_edited_gjf is not None:
            return self.custom_edited_gjf

        lines: list[str] = []
        if self.save_chk and self.chk_filename.strip():
            lines.append(f"%chk={self.chk_filename.strip()}")
        lines.append(f"%mem={max(1, int(self.memory_gb))}GB")
        lines.append(f"%nprocshared={max(1, int(self.nproc_shared))}")
        lines.append(self.build_route_section())
        lines.append("")
        lines.append(self.title.strip() or "MolForge Quantum Job")
        lines.append("")
        lines.append(f"{int(self.charge)} {int(self.multiplicity)}")

        if doc.topology.num_atoms > 0 and doc.has_3d and doc.coordinates.current is not None:
            idx_to_id, _ = doc.topology.atom_index_map()
            coords = doc.coordinates.current.coords
            for i, aid in enumerate(idx_to_id):
                if i >= len(coords):
                    break
                atom = doc.topology.get_atom(aid)
                el = ELEMENTS.get(atom.atomic_num)
                sym = el.symbol if el else "C"
                x, y, z = float(coords[i][0]), float(coords[i][1]), float(coords[i][2])
                lines.append(f" {sym:<3s}  {x:14.8f}  {y:14.8f}  {z:14.8f}")
        elif allow_sample_placeholder:
            lines.append(" ! [SAMPLE PREVIEW ONLY - EMPTY DOCUMENT]")

        lines.append("")
        if self.additional_tail_input.strip():
            lines.append(self.additional_tail_input.strip())
            lines.append("")

        return "\n".join(lines) + "\n"

    def input_hash(self, doc: MoleculeDocument) -> str:
        text = self.generate_gjf(doc, allow_sample_placeholder=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
