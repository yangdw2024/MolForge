"""
WF-06: 分子平面性 (MPP / SDP) 与二聚体堆积几何工作流 (planarity_analysis.py)
==============================================================================
严格基于 `planarity-analysis/SKILL.md` 与 `OSC_MD_workflows/03-二面角-质心距分析工作流.md`：
输入文件: Gaussian .fchk 或 .xyz / .mol / .sdf / .pdb 结构文件
调用工具: NumPy SVD 最佳拟合平面求解器 (+ 可选 Multiwfn 100->21->mpp 与 VMD render_planarity.tcl)
输出结果:
  - planarity.json / planarity.csv (重原子数、平面度 RMSD/MPP Å、最大离面距离 Å、跨度 SDP Å、法向量)
  - atom_plane_deviations.pqr (含每个原子离面有向距离 d_s 的 PQR 文件，可直接用于 VMD BWR 蓝-白-红渲染)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np
from .scientific_workflows import (
    analyze_fchk_planarity,
    planarity_from_coordinates,
    read_fchk_geometry,
    new_output_dir,
)


def run_planarity_workflow(input_path: str | Path, output_parent: str | Path) -> Path:
    p = Path(input_path).resolve()
    if not p.is_file():
        raise ValueError(f"输入文件不存在: {p}")
    if p.suffix.lower() == ".fchk":
        out = analyze_fchk_planarity(p, output_parent)
        z, coords = read_fchk_geometry(p)
    else:
        from ..io.rdkit_adapter import load_molecule_document
        loaded = load_molecule_document(p)
        doc = loaded[0] if isinstance(loaded, tuple) else loaded
        if not doc.has_3d or doc.coordinates.current is None:
            doc.relax_3d_geometry(max_iters=80)
        z = np.asarray([doc.topology.get_atom(aid).atomic_num for aid in doc.topology.atom_ids], dtype=int)
        coords = np.asarray(doc.coordinates.current.coords, dtype=float)
        result = planarity_from_coordinates(z, coords)
        result.update(source=str(p), metric="重原子最佳拟合平面 RMSD (MPP)")
        out = new_output_dir(output_parent, f"Planarity_{p.stem}")
        (out / "planarity.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        with (out / "planarity.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["metric", "value", "unit"])
            for k, v in result.items():
                if isinstance(v, (int, float)):
                    w.writerow([k, v, "Å" if "angstrom" in k else ""])

    # 生成每个原子的离面距离表与 VMD BWR 可视化 .pqr 文件
    keep = z != 1
    pts = coords[keep] if np.sum(keep) >= 3 else coords
    center = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - center, full_matrices=False)
    normal = vt[-1]
    signed_d = (coords - center) @ normal
    symbols = {1: "H", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F", 14: "Si", 15: "P", 16: "S", 17: "Cl", 34: "Se", 35: "Br", 53: "I"}
    pqr_lines = []
    for i, (zi, pt, dv) in enumerate(zip(z, coords, signed_d), 1):
        sym = symbols.get(int(zi), "C")
        pqr_lines.append(
            f"ATOM  {i:5d} {sym:>2s}   MOL A   1    {pt[0]:8.3f}{pt[1]:8.3f}{pt[2]:8.3f} {dv:6.3f}  1.500 {sym:>2s}"
        )
    (out / "atom_plane_deviations.pqr").write_text("\n".join(pqr_lines) + "\nTER\nEND\n", encoding="utf-8")
    return out
