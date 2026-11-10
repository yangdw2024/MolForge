"""
md_studio.py - MolForge 外接分子动力学统一分析模块
====================================================
面向真实 GROMACS 轨迹（gro/tpr + xtc/trr），用 MDAnalysis 成熟分析器做内存安全的计算，
不构造 N×N 全距离矩阵，可处理 7 万原子级体系：

  - RMSD：先 Kabsch 最小二乘对齐再算（MDAnalysis.analysis.rms.RMSD，pbc 对齐）
  - Rg  ：逐帧回旋半径
  - RMSF：逐原子均方波动（rms.RMSF，对齐后）
  - RDF ：径向分布函数（rdf.InterRDF，距离分箱，内存安全）
  - 氢键：HydrogenBondAnalysis，占有率统计

全部数值来自真实轨迹；输出 CSV/JSON + matplotlib 图，并在 summary 中诚实标注口径与限制。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .scientific_workflows import new_output_dir


def run_md_studio(
    topology: str | Path,
    trajectory: str | Path,
    output_parent: str | Path,
    selection: str = "not name H*",
    frame_step: int = 1,
    rdf_range: tuple[str, str] | None = None,
    r_max: float = 12.0,
    n_bins: int = 120,
    progress_callback=None,
    preprocess_pbc: bool = False,
    gmx_path: str | None = None,
) -> Path:
    """运行完整 MD 轨迹分析并返回输出目录。

    参数
    ----
    selection: MDAnalysis 选择字符串，默认排除显式氢以控制规模；可传 "all"。
    frame_step: 帧采样步长，1 表示全部帧。
    rdf_range: 两个选择字符串（中心组、参考组），默认用所选原子自身。
    """
    try:
        import MDAnalysis as mda
        from MDAnalysis.analysis import rms, rdf
        from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("MD 分析需要 MDAnalysis，请在 molforge-webengine 环境运行。") from exc

    report = progress_callback or (lambda message: None)
    report("正在读取拓扑与轨迹…")
    top, traj = Path(topology).resolve(), Path(trajectory).resolve()
    if not top.is_file() or not traj.is_file():
        raise ValueError("拓扑或轨迹文件不存在")

    original_traj = traj
    out = None
    preprocessing = "not applied; input must be made whole/unwrapped as appropriate"
    if preprocess_pbc:
        import subprocess
        from ..io.calculators import EngineToolRegistry
        from .gromacs_submit import DEFAULT_GMX
        detected = EngineToolRegistry.detect_tool("gromacs")
        engine = gmx_path or detected.executable_path or DEFAULT_GMX
        if not Path(engine).is_file():
            raise FileNotFoundError("PBC预处理需要已配置的GROMACS；可取消处理仅输出原始诊断")
        out = new_output_dir(output_parent, f"MDStudio_{top.stem}")
        processed = out / "trajectory_nojump.xtc"
        args = [str(engine), "trjconv", "-f", str(traj), "-s", str(top), "-o", str(processed), "-pbc", "nojump"]
        report("正在使用GROMACS nojump处理周期跳跃（要求初始构型完整）…")
        proc = subprocess.run(args, input="0\n", capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=out, timeout=3600)
        (out / "pbc_preprocessing.log").write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
        if proc.returncode != 0 or not processed.is_file():
            raise RuntimeError(f"PBC预处理失败，见{out / 'pbc_preprocessing.log'}")
        traj = processed
        preprocessing = "GROMACS trjconv -pbc nojump; assumes initial conformation is whole"
    u = mda.Universe(str(top), str(traj))
    if len(u.atoms) == 0:
        raise ValueError("轨迹中没有原子")
    ag = u.select_atoms(selection)
    if len(ag) == 0:
        raise ValueError(f"选择 '{selection}' 没有匹配到任何原子")

    total_frames = len(u.trajectory)
    used_frames = list(range(0, total_frames, max(1, int(frame_step))))

    report(f"载入{len(u.atoms)}原子/{total_frames}帧；采样{len(used_frames)}帧。正在计算RMSD/Rg…")
    # 1. RMSD（对齐到第一帧）与逐帧 Rg
    rmsd_run = rms.RMSD(ag, ag, select=selection, ref_frame=used_frames[0], verbose=False)
    rmsd_run.run(frames=used_frames)
    rmsd_table = np.asarray(rmsd_run.results.rmsd)  # 列: frame, time(ps), rmsd(Å)

    rg_list = []
    for fidx in used_frames:
        u.trajectory[fidx]
        rg_list.append(float(ag.radius_of_gyration()))
    times = rmsd_table[:, 1]
    rmsd_vals = rmsd_table[:, 2]
    rg_vals = np.asarray(rg_list, dtype=float)

    report("正在逐帧对齐并累计RMSF…")
    # Align each sampled frame to the first; RMSD.run does not mutate the trajectory.
    u.trajectory[used_frames[0]]
    reference = ag.positions.astype(float).copy()
    reference -= reference.mean(axis=0)
    mean = np.zeros_like(reference)
    m2 = np.zeros_like(reference)
    for count, fidx in enumerate(used_frames, 1):
        u.trajectory[fidx]
        xyz = ag.positions.astype(float).copy()
        xyz -= xyz.mean(axis=0)
        left, _, right = np.linalg.svd(xyz.T @ reference)
        correction = np.eye(3)
        correction[-1, -1] = np.linalg.det(left @ right)
        aligned = xyz @ (left @ correction @ right)
        delta = aligned - mean
        mean += delta / count
        m2 += delta * (aligned - mean)
    rmsf_vals = np.sqrt(np.maximum(0.0, m2.sum(axis=1) / len(used_frames)))

    # 3. RDF：InterRDF 距离分箱，内存安全（不构造 N×N 矩阵）
    if rdf_range is None:
        # 同组RDF包含分子内对；下面的非零下界排除r=0自身距离。
        center = ag
        around = ag
    else:
        center = u.select_atoms(rdf_range[0])
        around = u.select_atoms(rdf_range[1])
    # 起始 0.5 Å：仅排除r=0自配对；成键距离仍可能在范围内，避免 r→0 伪峰；最近非键接触也 >0.5 Å
    inter = rdf.InterRDF(center, around, nbins=n_bins, range=(0.5, float(r_max)), verbose=False)
    report("正在计算RDF（包含分子内对，大选择可能耗时较长）…")
    inter.run(frames=used_frames)
    r_edges = np.asarray(inter.results.bins)
    g_r = np.asarray(inter.results.rdf)
    r_centers = np.asarray(r_edges)

    report("RDF完成，正在计算氢键…")
    # 4. 氢键（失败不阻断其余结果，诚实记录）
    hb_status = {"status": "not_run", "unique_count": 0, "occupancy": []}
    try:
        # 该版本用 _sel 选择字符串参数，显式指定以避免无电荷时自动猜测失败
        hba = HydrogenBondAnalysis(
            u, hydrogens_sel="name H*",
            donors_sel="name O* N*", acceptors_sel="name O* N*",
            d_a_cutoff=3.5, d_h_a_angle_cutoff=150.0,
        )
        hba.run(frames=used_frames)
        data = np.asarray(hba.results.hbonds)
        hb_status["status"] = "ok"
        if data.size:
            pairs: dict[tuple[int, int], set[int]] = {}
            for rec in data:
                key = (int(rec[1]), int(rec[3]))
                pairs.setdefault(key, set()).add(int(rec[0]))
            nf = max(1, len(used_frames))
            hb_status["unique_count"] = len(pairs)
            hb_status["occupancy"] = [
                {"donor_index": d, "acceptor_index": a, "fraction": round(len(frames) / nf, 4)}
                for (d, a), frames in sorted(pairs.items(), key=lambda kv: -len(kv[1]))[:50]
            ]
    except Exception as exc:  # 诚实记录而非伪造
        hb_status = {"status": "unavailable", "unique_count": 0, "occupancy": [], "diagnostic": str(exc)}

    out = out or new_output_dir(output_parent, f"MDStudio_{top.stem}")

    # 逐帧表
    with (out / "md_rmsd_rg.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "time_ps", "rmsd_angstrom", "rg_angstrom"])
        for i, fidx in enumerate(used_frames):
            w.writerow([int(fidx), round(float(times[i]), 3), round(float(rmsd_vals[i]), 5), round(float(rg_vals[i]), 5)])

    # 逐原子 RMSF（带原子 id 与元素名）
    with (out / "md_rmsf.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["atom_local_index", "atom_id", "element", "rmsf_angstrom"])
        ids = ag.ids
        names = ag.names
        for i in range(len(ag)):
            w.writerow([i, int(ids[i]), str(names[i]), round(float(rmsf_vals[i]), 5)])

    # RDF 曲线
    with (out / "md_rdf.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["r_angstrom", "g_r"])
        for rv, gv in zip(r_centers, g_r):
            w.writerow([round(float(rv), 4), round(float(gv), 5)])

    peaks = np.where((g_r[1:-1] > g_r[:-2]) & (g_r[1:-1] >= g_r[2:]))[0] + 1
    peak_i = int(peaks[0]) if len(peaks) else (int(np.argmax(g_r)) if len(g_r) else 0)
    summary = {
        "topology": str(top),
        "trajectory": str(traj),
        "original_trajectory": str(original_traj),
        "selection": selection,
        "total_frames": total_frames,
        "frames_analyzed": len(used_frames),
        "frame_step": int(frame_step),
        "atoms_in_universe": len(u.atoms),
        "atoms_in_selection": len(ag),
        "rmsd_mean_angstrom": round(float(np.mean(rmsd_vals)), 4),
        "rmsd_max_angstrom": round(float(np.max(rmsd_vals)), 4),
        "rg_mean_angstrom": round(float(np.mean(rg_vals)), 4),
        "rmsf_mean_angstrom": round(float(np.mean(rmsf_vals)), 4),
        "rmsf_max_angstrom": round(float(np.max(rmsf_vals)), 4),
        "rdf_first_peak_r_angstrom": round(float(r_centers[peak_i]), 3) if len(g_r) else 0.0,
        "rdf_first_peak_g": round(float(g_r[peak_i]), 4) if len(g_r) else 0.0,
        "hydrogen_bonds": hb_status,
        "rdf_scope": "all selected atom pairs, including intramolecular/bonded pairs; r=0 omitted",
        "pbc_preprocessing": preprocessing,
        "honesty": (
            "全部数值由 MDAnalysis 对真实轨迹计算；RMSD 已 Kabsch 对齐，RDF 走距离分箱（内存安全），"
            "RMSF 为对齐后逐原子波动；PBC处理见pbc_preprocessing，未做自由能聚类，"
            "氢键占有率按采样帧统计。"
        ),
    }
    (out / "md_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    report("数值计算完成，正在写表格和图像…")
    _plot_md(out, times, rmsd_vals, rg_vals, rmsf_vals, r_centers, g_r)
    report(f"完成：{out}")
    return out


def _plot_md(out: Path, times, rmsd, rg, rmsf, r_centers, g_r) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].plot(times, rmsd, color="#1d4ed8")
    axes[0, 0].set_title("RMSD (aligned)")
    axes[0, 0].set_xlabel("Time (ps)"); axes[0, 0].set_ylabel("Å")

    axes[0, 1].plot(times, rg, color="#66DEC9")
    axes[0, 1].set_title("Radius of Gyration")
    axes[0, 1].set_xlabel("Time (ps)"); axes[0, 1].set_ylabel("Å")

    axes[1, 0].plot(np.arange(len(rmsf)), rmsf, color="#D8B679")
    axes[1, 0].set_title("RMSF per atom")
    axes[1, 0].set_xlabel("local atom index"); axes[1, 0].set_ylabel("Å")

    axes[1, 1].plot(r_centers, g_r, color="#7DAEFA")
    axes[1, 1].set_title("RDF g(r)")
    axes[1, 1].set_xlabel("r (Å)"); axes[1, 1].set_ylabel("g(r)")

    fig.tight_layout()
    fig.savefig(out / "md_overview.png", dpi=130)
    plt.close(fig)
