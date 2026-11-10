#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_surfanalysis.py
解析 Multiwfn ESPrhoiso 输出的 <prefix>_sum.txt，提取 OSC 表面分析关键描述符。
用法:
    python parse_surfanalysis.py <sum.txt> [sum2.txt ...]
输出: 控制台打印表格 + 同目录生成 esp_descriptors.csv
关键描述符 (从 sum.txt 正则提取):
    Vs,min / Vs,max       kcal/mol   表面 ESP 极小/极大
    SASA                  Angstrom^2 分子表面积
    sigma2_pos/neg/tot    (kcal/mol)^2  正/负/总方差
    nu                    电荷平衡度 (越小越平衡)
    Pi (Omega)            kcal/mol   内部分离强度
    MPI                   kcal/mol   分子极性指数
    Polar area ratio      %          |ESP|>10 kcal/mol 面积占比
"""
import sys, re, json, csv, pathlib

PATTERNS = {
    "Vs_min_kcal":  r"Minimal value:\s+([-\d.]+)\s+kcal/mol",
    "Vs_max_kcal":  r"Maximal value:\s+([-\d.]+)\s+kcal/mol",
    "SASA_A2":      r"Overall surface area:\s+[\d.]+\s+Bohr\^2\s+\(\s*([\d.]+)\s+Angstrom\^2\)",
    "sigma2_pos":   r"Positive variance:\s+[\d.]+\s+a\.u\.\^2\s+\(\s*([\d.]+)\s+\(kcal/mol\)\^2\)",
    "sigma2_neg":   r"Negative variance:\s+[\d.]+\s+a\.u\.\^2\s+\(\s*([\d.]+)\s+\(kcal/mol\)\^2\)",
    "sigma2_tot":   r"Overall variance \(sigma\^2_tot\):\s+[\d.]+\s+a\.u\.\^2\s+\(\s*([\d.]+)\s+\(kcal/mol\)\^2\)",
    "nu":           r"Balance of charges \(nu\):\s+([-\d.]+)",
    "Pi_kcal":      r"Internal charge separation \(Pi\):\s+[\d.]+\s+a\.u\.\s+\(\s*([-\d.]+)\s+kcal/mol\)",
    "MPI_kcal":     r"Molecular polarity index \(MPI\):\s+[\d.]+\s+eV\s+\(\s*([-\d.]+)\s+kcal/mol\)",
    "polar_area_pct": r"Polar surface area \(\|ESP\| > 10 kcal/mol\):\s+[\d.]+\s+Angstrom\^2\s+\(\s*([\d.]+)\s*%\)",
}

def parse_one(path):
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")
    out = {"file": pathlib.Path(path).name}
    for k, pat in PATTERNS.items():
        m = re.search(pat, text)
        out[k] = float(m.group(1)) if m else None
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    rows = [parse_one(p) for p in sys.argv[1:]]
    cols = ["file"] + list(PATTERNS.keys())
    # 打印
    for r in rows:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    # 写 CSV 到第一个文件同目录
    out_csv = pathlib.Path(sys.argv[1]).parent / "esp_descriptors.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"\nCSV written: {out_csv}")

if __name__ == "__main__":
    main()
