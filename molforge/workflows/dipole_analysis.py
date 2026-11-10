"""
WF-05: 分子总偶极矩与片段多极矩分析工作流 (dipole_analysis.py)
================================================================
严格基于 `dipole-visualization/SKILL.md` 与 `OSC_MD_workflows/07-偶极矩计算工作流.md`：
输入文件: Gaussian .fchk 或 .log/.out 文件
调用工具: 内置 .fchk/.log 偶极提取器 + 可选 Multiwfn (Hirshfeld 分子/片段多极矩) + VMD (render_dipole.tcl)
输出结果:
  - dipole.json / dipole.csv (总偶极矩向量 a.u. 与总偶极大小 Debye)
  - render_total_dipole.tcl (VMD 3D 偶极矩箭头绘制脚本，若配置了 VMD 则直接输出 {stem}_dipole.bmp)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from .scientific_workflows import analyze_fchk_dipole


def run_dipole_workflow(fchk_path: str | Path, output_parent: str | Path) -> Path:
    out = analyze_fchk_dipole(fchk_path, output_parent)
    dip_json = out / "dipole.json"
    if dip_json.is_file():
        data = json.loads(dip_json.read_text(encoding="utf-8"))
        vec = data.get("dipole_au", [0.0, 0.0, 0.0])
        with (out / "dipole.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["component", "value", "unit"])
            w.writerow(["mu_x", vec[0], "a.u."])
            w.writerow(["mu_y", vec[1], "a.u."])
            w.writerow(["mu_z", vec[2], "a.u."])
            w.writerow(["dipole_total", data.get("dipole_debye", 0.0), "Debye"])
    return out
