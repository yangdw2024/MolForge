"""
WF-03: OSC 给体/受体能级对齐图工作流 (osc_energy_diagram.py)
============================================================
输入文件: 至少 2 个分子的 Gaussian .fchk + 同名 .log/.out（严格执行双源能级一致性校验 |ΔE| <= 0.05 eV）
调用工具: Python + openpyxl + python-pptx (+ 可选 Multiwfn & VMD)
输出结果:
  - osc_energy_levels.svg (经典横线阶梯能级对齐图)
  - osc_rectangle_levels.svg (色块矩形带隙对比图)
  - osc_2xN_levels.svg (2xN 网格对比图)
  - osc_energy_levels.xlsx (带格式与注释的 Excel 汇总表)
  - osc_energy_levels.pptx (可直接在 PowerPoint 中编辑的矢量能级幻灯片)
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
from .scientific_workflows import export_osc_levels


def run_osc_energy_workflow(
    inputs: Iterable[tuple[str | Path, str | Path | None]],
    output_parent: str | Path,
) -> Path:
    return export_osc_levels(inputs, output_parent)
