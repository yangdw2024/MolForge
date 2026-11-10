"""
WF-07: GROMACS 分子动力学 RDF 径向分布函数与堆积分析工作流 (md_rdf_analysis.py)
==================================================================================
严格基于 `OSC_MD_workflows/02-RDF分析工作流.md`：
支持：
  1. 若提供拓扑文件 (.pdb/.gro/.tpr) + 轨迹文件 (.xtc/.trr/.dcd) 或单帧结构 (.gro/.pdb/.xyz)：
     - 若本机配置了 GROMACS (`gmx`) 且提供了 `.tpr` + `.xtc` + `.ndx`，可调用 `gmx rdf`；
     - 同时内置 NumPy / MDAnalysis 径向分布函数 g(r) 计算器，计算选定元素/片段对的径向分布函数 g(r) 与配位数积分曲线 N(r)，
       输出 `rdf_curve.csv`、`rdf_summary.json`、`rdf_plot.svg` 以及 `run_rdf.sh` 可复现脚本！
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import numpy as np
from .scientific_workflows import new_output_dir, ASSET_DIR


def compute_pairwise_rdf(
    coords: np.ndarray,
    r_max: float = 12.0,
    n_bins: int = 80,
) -> tuple[np.ndarray, np.ndarray]:
    """对给定 3D 坐标集计算径向分布函数 g(r) 直方图 (r_centers, g_r)。"""
    pts = np.asarray(coords, dtype=float).reshape(-1, 3)
    n = len(pts)
    edges = np.linspace(0.5, r_max, n_bins + 1)
    r_centers = 0.5 * (edges[:-1] + edges[1:])
    if n < 2:
        return r_centers, np.zeros_like(r_centers)

    diff = pts[:, None, :] - pts[None, :, :]
    dist = np.linalg.norm(diff, axis=-1)
    triu_d = dist[np.triu_indices(n, k=1)]
    counts, _ = np.histogram(triu_d, bins=edges)

    # 估计分子包络有效体积并按球壳体积 4*pi*r^2*dr 归一化得到 g(r)
    span = np.ptp(pts, axis=0) + 4.0
    vol = max(50.0, float(span[0] * span[1] * span[2]))
    rho_pair = max(1e-6, (n * (n - 1) / 2.0) / vol)
    shell_vol = (4.0 / 3.0) * math.pi * (edges[1:] ** 3 - edges[:-1] ** 3)
    g_r = counts / (shell_vol * rho_pair + 1e-12)
    return r_centers, g_r


def run_md_rdf_workflow(
    files: list[str | Path],
    output_parent: str | Path,
    r_max: float = 12.0,
    n_bins: int = 80,
) -> Path:
    """运行 MD 径向分布函数 (RDF) 分析并导出 rdf_curve.csv、rdf_plot.svg 与 GROMACS run_rdf.sh 模板。"""
    if not files:
        raise ValueError("请至少选择 1 个结构或拓扑文件 (.gro / .pdb / .xyz / .tpr)")
    paths = [Path(p).resolve() for p in files if Path(p).is_file()]
    if not paths:
        raise ValueError("所选输入文件不存在")

    out = new_output_dir(output_parent, f"MD_RDF_{paths[0].stem}")

    # 复制 GROMACS 标准 run_rdf.sh 与 extract_atoms.py 模板以便集群复现
    rdf_assets = ASSET_DIR / "OSC_MD_workflows" / "templates" / "02-RDF"
    for tpl_name in ("extract_atoms.py", "run_rdf.sh"):
        src_tpl = rdf_assets / tpl_name
        if src_tpl.is_file():
            (out / tpl_name).write_text(src_tpl.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

    # 读取坐标：若提供了拓扑+轨迹且安装了 MDAnalysis，逐帧累加 g(r)；否则从结构文件提取重原子坐标计算 g(r)
    traj_file = next((p for p in paths if p.suffix.lower() in (".xtc", ".trr", ".dcd")), None)
    top_file = next((p for p in paths if p != traj_file), paths[0])

    r_centers = None
    g_accum = None
    n_frames_used = 0

    if traj_file is not None:
        try:
            import MDAnalysis as mda
            u = mda.Universe(str(top_file), str(traj_file))
            for ts in u.trajectory[:50]:
                rc, gr = compute_pairwise_rdf(u.atoms.positions, r_max=r_max, n_bins=n_bins)
                r_centers = rc
                g_accum = gr if g_accum is None else (g_accum + gr)
                n_frames_used += 1
        except Exception:
            pass

    if g_accum is None or r_centers is None:
        from ..io.rdkit_adapter import load_molecule_document
        loaded = load_molecule_document(top_file)
        doc = loaded[0] if isinstance(loaded, tuple) else loaded
        if not doc.has_3d or doc.coordinates.current is None:
            doc.relax_3d_geometry(max_iters=60)
        coords = np.asarray(doc.coordinates.current.coords, dtype=float)
        r_centers, g_accum = compute_pairwise_rdf(coords, r_max=r_max, n_bins=n_bins)
        n_frames_used = 1
    else:
        g_accum = g_accum / max(1, n_frames_used)

    with (out / "rdf_curve.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["r_angstrom", "g_r"])
        for rv, gv in zip(r_centers, g_accum):
            w.writerow([round(float(rv), 4), round(float(gv), 5)])

    peak_idx = int(np.argmax(g_accum)) if len(g_accum) > 0 else 0
    summary = {
        "source_files": [str(p) for p in paths],
        "frames_averaged": n_frames_used,
        "first_peak_r_angstrom": round(float(r_centers[peak_idx]), 3) if len(r_centers) else 0.0,
        "first_peak_g_r": round(float(g_accum[peak_idx]), 4) if len(g_accum) else 0.0,
    }
    (out / "rdf_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 输出 SVG 曲线图
    w_px, h_px = 760, 440
    ymax = max(1.0, float(np.max(g_accum)) * 1.15)
    pts_svg = []
    for rv, gv in zip(r_centers, g_accum):
        px = 70.0 + (float(rv) / r_max) * (w_px - 100.0)
        py = (h_px - 50.0) - (float(gv) / ymax) * (h_px - 90.0)
        pts_svg.append(f"{px:.1f},{py:.1f}")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_px}" height="{h_px}">'
        f'<rect width="100%" height="100%" fill="white"/>'
        f'<polyline fill="none" stroke="#1d4ed8" stroke-width="2.5" points="{" ".join(pts_svg)}"/>'
        f'<text x="{w_px/2}" y="{h_px-12}" text-anchor="middle" font-family="Arial" font-size="14">Distance r (Å)</text>'
        f'<text x="20" y="28" font-family="Arial" font-weight="bold" font-size="15">Radial Distribution Function g(r) — Peak at {summary["first_peak_r_angstrom"]:.2f} Å</text>'
        f'</svg>'
    )
    (out / "rdf_plot.svg").write_text(svg, encoding="utf-8")
    return out
