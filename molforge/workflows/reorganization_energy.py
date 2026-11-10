"""
WF-04: OSC 内球重组能 (λ_h / λ_e) 四点法与 Marcus 电荷转移速率工作流 (reorganization_energy.py)
==================================================================================================
严格基于 `OSC_MD_workflows/06-重组能计算工作流.md` 与 `09-电荷转移动力学K工作流.md`：
支持两种工作模式：
  模式 A（生成 4 点法 Gaussian 输入卡）：
    输入分子结构 (.xyz/.mol/.sdf/.pdb/.gjf)，一键生成全套 4 个 Gaussian 16 输入文件：
      1. reorg-opt-中性.gjf   (0 1, opt, E(N, R_N))
      2. reorg-opt-阴离子.gjf (-1 2, opt, E(A-, R_A-)) 或 阳离子 (+1 2, opt, E(D+, R_D+))
      3. reorg-sp-中性.gjf    (0 1, sp at charged geometry, E(N, R_charged))
      4. reorg-sp-阴离子.gjf  (±1 2, sp at neutral geometry, E(charged, R_N))
  模式 B（从 4 个 Gaussian .log/.out 解析能量计算四点法重组能 λ 与 Marcus 速率 k_ET）：
    λ_1 = E(N, R_charged) - E(N, R_N)
    λ_2 = E(charged, R_N) - E(charged, R_charged)
    λ_total = λ_1 + λ_2 (单位: eV 与 meV)
    并结合电子耦合 V_DA (eV) 与驱动力 ΔG (eV) 计算标准 Marcus 速率：
    k_ET = (2π/ħ) |V_DA|² / sqrt(4π λ k_B T) * exp(-(ΔG + λ)² / (4 λ k_B T))
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from .scientific_workflows import new_output_dir, HARTREE_TO_EV

KB_EV_PER_K = 8.617333262e-5
HBAR_EV_S = 6.582119569e-16


def parse_last_scf_energy_hartree(log_path: str | Path) -> float:
    """从 Gaussian .log/.out 中提取最后一步收敛的 SCF Done 能量 (Hartree)。"""
    p = Path(log_path)
    if not p.is_file():
        raise ValueError(f"日志文件不存在: {p}")
    scf_re = re.compile(r"SCF\s+Done:\s+E\([^\)]+\)\s*=\s*([-+]?\d+\.\d+(?:[DEde][-+]?\d+)?)")
    last_val: float | None = None
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = scf_re.search(line)
            if m:
                last_val = float(m.group(1).replace("D", "E").replace("d", "e"))
    if last_val is None:
        raise ValueError(f"未在 {p.name} 中找到 'SCF Done:' 能量记录")
    return last_val


def compute_marcus_rate(v_da_ev: float, lambda_ev: float, dg_ev: float = 0.0, temp_k: float = 298.15) -> dict[str, float]:
    """根据 `09-速率/marcus_rate.py` 计算非绝热极限下的 Marcus 电荷转移速率 k (s^-1)。"""
    if lambda_ev <= 0.0 or temp_k <= 0.0:
        raise ValueError("重组能 λ 与温度 T 必须大于 0")
    kbt = KB_EV_PER_K * temp_k
    prefactor = (2.0 * math.pi / HBAR_EV_S) * (v_da_ev ** 2) / math.sqrt(4.0 * math.pi * lambda_ev * kbt)
    barrier_ev = ((dg_ev + lambda_ev) ** 2) / (4.0 * lambda_ev)
    rate_s1 = prefactor * math.exp(-barrier_ev / kbt)
    return {
        "v_da_ev": float(v_da_ev),
        "lambda_ev": float(lambda_ev),
        "delta_g_ev": float(dg_ev),
        "temperature_k": float(temp_k),
        "activation_barrier_ev": round(barrier_ev, 6),
        "marcus_rate_s_inv": float(rate_s1),
    }


def generate_four_point_gjf_bundle(
    structure_path_or_doc,
    output_parent: str | Path,
    carrier_type: str = "electron",  # "electron" (-1 2) or "hole" (+1 2)
    functional_basis: str = "wb97xd/6-31g(d,p)",
    solvent: str = "chloroform",
    nproc: int = 24,
    mem_gb: int = 24,
) -> Path:
    """根据分子结构生成四点法重组能全套 4 个 Gaussian .gjf 输入文件。"""
    from ..io.rdkit_adapter import load_molecule_document
    from ..application.calculators.qc_input_generator import extract_xyz_lines
    if hasattr(structure_path_or_doc, "topology"):
        doc = structure_path_or_doc
    else:
        loaded = load_molecule_document(structure_path_or_doc)
        doc = loaded[0] if isinstance(loaded, tuple) else loaded

    xyz_lines = extract_xyz_lines(doc)
    if not xyz_lines:
        raise ValueError("分子结构为空，无法生成重组能 .gjf 输入文件")
    coord_block = "\n".join(xyz_lines)
    stem = doc.name or "molecule"
    chg_ion = -1 if carrier_type == "electron" else 1
    ion_tag = "阴离子" if carrier_type == "electron" else "阳离子"
    out = new_output_dir(output_parent, f"Reorg4Pt_Inputs_{stem}")

    scrf_str = f" scrf(smd,solvent={solvent})" if solvent and solvent.lower() != "none" else ""
    specs = [
        (f"reorg-opt-中性.gjf", f"{stem}-OPT01.chk", f"#p {functional_basis} opt{scrf_str} SCF=conver=6", "中性态几何优化 E(N,RN)", 0, 1),
        (f"reorg-opt-{ion_tag}.gjf", f"{stem}-OPT12.chk", f"#p {functional_basis} opt{scrf_str} SCF=conver=6", f"{ion_tag}态几何优化 E(Ion,RIon)", chg_ion, 2),
        (f"reorg-sp-中性.gjf", f"{stem}-sp01.chk", f"#p {functional_basis} sp{scrf_str} SCF=conver=6", f"中性单点(在{ion_tag}平衡几何上) E(N,RIon)", 0, 1),
        (f"reorg-sp-{ion_tag}.gjf", f"{stem}-sp12.chk", f"#p {functional_basis} sp{scrf_str} SCF=conver=6", f"{ion_tag}单点(在中性平衡几何上) E(Ion,RN)", chg_ion, 2),
    ]
    for fname, chk, route, title, chg, mult in specs:
        content = (
            f"%chk={chk}\n"
            f"%nprocshared={nproc}\n"
            f"%mem={mem_gb}GB\n"
            f"{route}\n\n"
            f"{title}\n\n"
            f"{chg} {mult}\n"
            f"{coord_block}\n\n"
        )
        (out / fname).write_text(content, encoding="utf-8")
    return out


def run_reorganization_energy_workflow(
    log_files: list[str | Path],
    output_parent: str | Path,
    v_da_ev: float = 0.025,
    dg_ev: float = 0.0,
    temp_k: float = 298.15,
) -> Path:
    """
    输入 4 个 Gaussian .log/.out 文件（按 [OPT_neutral, OPT_charged, SP_neutral_at_charged, SP_charged_at_neutral] 顺序），
    计算 Nelson 四点法内球重组能 λ_1, λ_2, λ_total (eV / meV) 与 Marcus 电荷转移速率 k_ET。
    """
    if len(log_files) != 4:
        raise ValueError("四点法重组能计算需要精确提供 4 个 Gaussian .log/.out 文件：[1]中性优化, [2]带电态优化, [3]中性单点(带电几何), [4]带电单点(中性几何)")

    e_n_rn = parse_last_scf_energy_hartree(log_files[0])
    e_c_rc = parse_last_scf_energy_hartree(log_files[1])
    e_n_rc = parse_last_scf_energy_hartree(log_files[2])
    e_c_rn = parse_last_scf_energy_hartree(log_files[3])

    lam1_ev = (e_n_rc - e_n_rn) * HARTREE_TO_EV
    lam2_ev = (e_c_rn - e_c_rc) * HARTREE_TO_EV
    lam_tot_ev = lam1_ev + lam2_ev
    lam_tot_mev = lam_tot_ev * 1000.0

    marcus = compute_marcus_rate(v_da_ev=v_da_ev, lambda_ev=max(1e-4, abs(lam_tot_ev)), dg_ev=dg_ev, temp_k=temp_k)
    summary = {
        "E_neutral_at_neutral_hartree": e_n_rn,
        "E_charged_at_charged_hartree": e_c_rc,
        "E_neutral_at_charged_hartree": e_n_rc,
        "E_charged_at_neutral_hartree": e_c_rn,
        "lambda_1_ev": round(lam1_ev, 5),
        "lambda_2_ev": round(lam2_ev, 5),
        "lambda_total_ev": round(lam_tot_ev, 5),
        "lambda_total_mev": round(lam_tot_mev, 2),
        "marcus_kinetics": marcus,
        "files": [str(Path(p).resolve()) for p in log_files],
    }
    out = new_output_dir(output_parent, "Reorganization_Energy")
    (out / "reorganization_energy.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "reorganization_energy.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value", "unit"])
        w.writerow(["E(N, R_N)", f"{e_n_rn:.8f}", "Hartree"])
        w.writerow(["E(C, R_C)", f"{e_c_rc:.8f}", "Hartree"])
        w.writerow(["E(N, R_C)", f"{e_n_rc:.8f}", "Hartree"])
        w.writerow(["E(C, R_N)", f"{e_c_rn:.8f}", "Hartree"])
        w.writerow(["lambda_1", f"{lam1_ev:.5f}", "eV"])
        w.writerow(["lambda_2", f"{lam2_ev:.5f}", "eV"])
        w.writerow(["lambda_total", f"{lam_tot_ev:.5f}", "eV"])
        w.writerow(["lambda_total_mev", f"{lam_tot_mev:.2f}", "meV"])
        w.writerow(["Marcus_k_ET", f"{marcus['marcus_rate_s_inv']:.4e}", "s^-1"])
    return out
