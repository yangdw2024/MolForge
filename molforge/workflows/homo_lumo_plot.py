"""
WF-02: HOMO-LUMO 前线轨道能级与等值面工作流 (homo_lumo_plot.py)
================================================================
输入文件: 1 个或多个 Gaussian .fchk 文件（可选同名 .log/.out 进行双源能级交叉校验）
调用工具:
  - 内置流式 fchk 解析器（读取 Number of alpha electrons 与 Alpha Orbital Energies，无需外部工具即可出能级图）
  - Multiwfn (200 -> 3 导出 HOMO/LUMO .cub) + VMD (render_one.tcl 渲染双相位轨道图，当配置好外部引擎时自动运行)
输出结果:
  - levels.json / levels.csv (各分子 HOMO/LUMO/Gap eV 与双源校验状态)
  - homo_lumo_levels.svg (出版级矢量能级阶梯图)
  - {stem}/{stem}_HOMO.bmp, {stem}_LUMO.bmp (当 Multiwfn + VMD 可用时)
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable
from .scientific_workflows import (
    extract_frontier,
    write_levels_svg,
    run_homo_lumo,
    new_output_dir,
)


def run_homo_lumo_workflow(
    fchks: Iterable[str | Path],
    output_parent: str | Path,
    log_by_stem: dict[str, str | Path] | None = None,
    render_orbitals: bool = True,
) -> Path:
    """提取多个 .fchk 的精确 HOMO/LUMO 能级并绘制阶梯图；若本机已配置 Multiwfn+VMD 则同步渲染轨道等值面。"""
    from ..io.calculators import EngineToolRegistry
    files = [Path(p).resolve() for p in fchks]
    if not files:
        raise ValueError("请至少提供 1 个 .fchk 文件")
    mwfn_ok = EngineToolRegistry.detect_tool("multiwfn").available
    vmd_ok = EngineToolRegistry.detect_tool("vmd").available
    if render_orbitals and mwfn_ok and vmd_ok:
        return run_homo_lumo(files, output_parent, log_by_stem=log_by_stem)

    # 仅提取能级并生成 SVG/CSV/JSON（不依赖外部程序）
    out = new_output_dir(output_parent, "HOMO_LUMO_Levels")
    log_map = log_by_stem or {}
    records = [asdict(extract_frontier(f, log_map.get(f.stem))) for f in files]
    (out / "levels.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "levels.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)
    write_levels_svg(records, out / "homo_lumo_levels.svg")
    if not (mwfn_ok and vmd_ok):
        (out / "orbital_render_status.txt").write_text(
            "已从 .fchk 提取精确 HOMO/LUMO 能级并导出 SVG/CSV/JSON；如需渲染 3D 轨道 BMP，请在 [计算 -> 引擎状态] 中配置 Multiwfn 与 VMD。\n",
            encoding="utf-8",
        )
    return out
