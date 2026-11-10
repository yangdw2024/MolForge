"""
WF-08: IGMH 弱相互作用分析工作流 (igmh_interaction.py)
======================================================
严格基于 `OSC_MD_workflows/11-IGMH弱相互作用工作流.md`：
支持两种工作模式：
  1. 输入 D-A 二聚体结构文件 (.xyz/.mol/.sdf/.pdb/.mol2)，自动生成带 `IOp(7/33=1) pop=full` 的 Gaussian 单点输入卡 `igmh.gjf`
     与 Multiwfn 批处理脚本 `run_igmh.sh` 及 `igmh_stdin.txt`（主功能 20 -> 10 IGMH -> 定义片段 1 与片段 2 原子序号范围 -> 生成 dg_inter.cub 与 sl2r.cub）。
  2. 若输入已算好的二聚体 `.fchk` / `.wfn` 且本机已配置 Multiwfn，自动调用 Multiwfn 执行 IGMH 分析并导出等值面网格与 VMD 渲染脚本！
"""
from __future__ import annotations

import json
from pathlib import Path
from .scientific_workflows import new_output_dir, _run


def build_multiwfn_igmh_stdin(frag1_range: str = "1-50", frag2_range: str = "51-100", grid_quality: int = 2) -> str:
    """生成 Multiwfn 主功能 20 -> 10 (IGMH) 的标准输入指令流（使用真实换行符 \n）。"""
    return (
        "20\n"
        "10\n"
        "2\n"
        f"{frag1_range}\n"
        f"{frag2_range}\n"
        f"{grid_quality}\n"
        "3\n"
        "0\n"
        "q\n"
    )


def run_igmh_workflow(
    input_file: str | Path,
    output_parent: str | Path,
    frag1_range: str = "1-30",
    frag2_range: str = "31-60",
    functional_basis: str = "wb97xd/6-31g(d,p)",
    solvent: str = "chloroform",
) -> Path:
    p = Path(input_file).resolve()
    if not p.is_file():
        raise ValueError(f"输入文件不存在: {p}")

    out = new_output_dir(output_parent, f"IGMH_{p.stem}")
    stdin_txt = build_multiwfn_igmh_stdin(frag1_range=frag1_range, frag2_range=frag2_range)
    (out / "igmh_multiwfn_stdin.txt").write_text(stdin_txt, encoding="utf-8")

    vmd_tcl = (
        "# MolForge v7.3 VMD IGMH Isosurface Script (dg_inter.cub colored by sign(lambda2)rho sl2r.cub)\n"
        "color scale method BGR\n"
        "mol new dg_inter.cub type cube first 0 last -1 step 1 waitfor 1\n"
        "mol addfile sl2r.cub type cube first 0 last -1 step 1 waitfor 1\n"
        "mol modstyle 0 top CPK 0.80 0.25 22.0 22.0\n"
        "mol addrep top\n"
        "mol modstyle 1 top Isosurface 0.004000 0 0 0 1 1\n"
        "mol modcolor 1 top Volume 1\n"
        "mol scaleminmax top 1 -0.04 0.02\n"
        "mol modmaterial 1 top EdgyShiny\n"
    )
    (out / "render_igmh_vmd.tcl").write_text(vmd_tcl, encoding="utf-8")

    if p.suffix.lower() in (".fchk", ".wfn", ".wfx", ".molden"):
        from ..io.calculators import EngineToolRegistry
        st = EngineToolRegistry.detect_tool("multiwfn")
        if not st.available or not st.executable_path:
            raise RuntimeError(f"运行 .fchk IGMH 分析需要配置 Multiwfn：{st.diagnostic}（已在 {out} 生成批处理输入与 VMD 脚本）")
        _run([st.executable_path, str(p)], out, stdin=stdin_txt, timeout=3600, allow_nonzero=True)
        (out / "igmh_status.json").write_text(
            json.dumps({"mode": "multiwfn_executed", "input": str(p), "frag1": frag1_range, "frag2": frag2_range}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out

    # 从结构文件生成 Gaussian igmh.gjf 单点能输入卡
    from ..io.rdkit_adapter import load_molecule_document
    from ..application.calculators.qc_input_generator import extract_xyz_lines
    loaded = load_molecule_document(p)
    doc = loaded[0] if isinstance(loaded, tuple) else loaded
    xyz_lines = extract_xyz_lines(doc)
    scrf_str = f" scrf(smd,solvent={solvent})" if solvent and solvent.lower() != "none" else ""
    gjf_content = (
        f"%chk={p.stem}-igmh.chk\n"
        f"%nprocshared=24\n"
        f"%mem=24GB\n"
        f"#p {functional_basis} sp IOp(7/33=1){scrf_str} pop=full\n\n"
        f"D-A Dimer Single-Point for Multiwfn IGMH ({p.stem})\n\n"
        f"0 1\n"
        + "\n".join(xyz_lines)
        + "\n\n"
    )
    (out / f"{p.stem}-igmh.gjf").write_text(gjf_content, encoding="utf-8")
    (out / "igmh_status.json").write_text(
        json.dumps(
            {
                "mode": "gjf_and_multiwfn_recipe_generated",
                "gjf_file": str(out / f"{p.stem}-igmh.gjf"),
                "multiwfn_stdin": str(out / "igmh_multiwfn_stdin.txt"),
                "vmd_tcl": str(out / "render_igmh_vmd.tcl"),
                "frag1": frag1_range,
                "frag2": frag2_range,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return out
