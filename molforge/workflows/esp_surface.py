"""
WF-01: ESP 分子表面静电势定量分析工作流 (esp_surface.py)
=========================================================
输入文件: Gaussian 优化后的 .fchk 波函数文件
调用工具: Multiwfn 3.8 (主功能 12 定量分子表面分析 + -ESPrhoiso 0.001) + VMD 1.9.4 (draw_ESP.tcl + Tachyon)
输出结果:
  - esp_descriptors.json / esp_descriptors.csv (V_min, V_max, sigma2_+, sigma2_-, sigma2_tot, nu, Pi, MPI, 正负表面积)
  - density.cub, totesp.cub, mol.pdb, surfanalysis.pdb, vtx.pdb
  - {stem}_esp.bmp (VMD BWR 蓝-白-红等值面渲染图，色阶自动按极值留 20% 裕量)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from .scientific_workflows import run_esp_surface, new_output_dir


def run_esp_surface_workflow(
    fchk_path: str | Path,
    output_parent: str | Path,
    isovalue: float = 0.001,
    grid_spacing: float = 0.15,
) -> Path:
    """执行完整 Multiwfn + VMD 静电势表面分析工作流，或在不具备外部引擎时输出可复现批处理包。"""
    out = run_esp_surface(fchk_path, output_parent, isovalue=isovalue)
    desc_json = out / "esp_descriptors.json"
    if desc_json.is_file():
        data = json.loads(desc_json.read_text(encoding="utf-8"))
        csv_p = out / "esp_descriptors.csv"
        with csv_p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["descriptor", "value"])
            for k, v in data.items():
                w.writerow([k, v])
    return out
