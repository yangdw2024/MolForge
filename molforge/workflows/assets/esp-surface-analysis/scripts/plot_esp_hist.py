#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_esp_hist.py
从 Multiwfn vtx.pdb (38万表面顶点, B因子=ESP kcal/mol) 画 ESP 表面面积百分比直方图。
样式对齐论文图: x=ESP(kcal/mol), y=Area(%), bin=5 kcal/mol, 给体蓝/受体红。

用法:
    python plot_esp_hist.py <vtx.pdb> <MolName> [--color blue|red] [--out out.png]
                   [--bin 5.0] [--xmin -35] [--xmax 35] [--ymax 30]

例:
    python plot_esp_hist.py ClFFCl_vtx.pdb ClFFCl --color red --out ClFFCl_esp_hist.png
"""
import sys, argparse, pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 论文字体
rcParams["font.family"] = "Arial"
rcParams["font.size"] = 14
rcParams["axes.linewidth"] = 1.2
rcParams["xtick.direction"] = "out"
rcParams["ytick.direction"] = "out"

COLORS = {
    "blue":  {"face": "#1f77d0", "edge": "white"},   # 给体/中性
    "red":   {"face": "#d63a3a", "edge": "white"},   # 受体/缺电子
    "gray":  {"face": "#888888", "edge": "white"},
}

def read_vtx_bfactor(path):
    """读 vtx.pdb 的 B-factor 字段 (列5, kcal/mol)。只取 HETATM 行。"""
    vals = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("HETATM"):
                continue
            # PDB 列格式: B-factor 在 61-66 列 (0-based 60:66)
            try:
                bf = float(line[60:66])
                vals.append(bf)
            except ValueError:
                continue
    return np.array(vals, dtype=float)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vtx_pdb")
    ap.add_argument("molname")
    ap.add_argument("--color", default="blue", choices=list(COLORS.keys()))
    ap.add_argument("--out", default=None)
    ap.add_argument("--bin", type=float, default=5.0)
    ap.add_argument("--xmin", type=float, default=-35.0)
    ap.add_argument("--xmax", type=float, default=35.0)
    ap.add_argument("--ymax", type=float, default=30.0)
    args = ap.parse_args()

    vals = read_vtx_bfactor(args.vtx_pdb)
    print(f"Loaded {len(vals)} surface vertices from {args.vtx_pdb}")
    print(f"ESP range: {vals.min():.2f} ~ {vals.max():.2f} kcal/mol")

    # 分箱
    bins = np.arange(args.xmin, args.xmax + args.bin, args.bin)
    counts, edges = np.histogram(vals, bins=bins)
    pct = counts / counts.sum() * 100.0
    centers = (edges[:-1] + edges[1:]) / 2.0

    # 只画非零 bin (和参考图一致, 尾部空 bin 不画)
    nonzero = pct > 0.05
    c = centers[nonzero]
    p = pct[nonzero]

    # 画图
    fig, ax = plt.subplots(figsize=(4.2, 3.6), dpi=300)
    ax.bar(c, p, width=args.bin*0.92,
           color=COLORS[args.color]["face"],
           edgecolor=COLORS[args.color]["edge"],
           linewidth=0.8)

    ax.set_xlabel("ESP (kcal/mol)", fontsize=14)
    ax.set_ylabel("Area (%)", fontsize=14)
    ax.set_title(args.molname, fontsize=15, fontweight="bold", loc="left")

    ax.set_xlim(args.xmin, args.xmax)
    ax.set_ylim(0, args.ymax)
    ax.set_xticks(np.arange(-30, 25, 10))
    ax.set_yticks(np.arange(0, args.ymax+1, 5))

    # 去掉上右边框
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 峰值标注
    peak_idx = int(np.argmax(p))
    ax.annotate(f"{p[peak_idx]:.1f}%",
                xy=(c[peak_idx], p[peak_idx]),
                xytext=(0, 4), textcoords="offset points",
                ha="center", fontsize=11, fontweight="bold")

    fig.tight_layout()
    out = args.out or f"{args.molname}_esp_hist.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {out}")

    # 打印分箱数据供核对
    print("\nBin center (kcal/mol) | Area (%)")
    for ci, pi in zip(c, p):
        print(f"  {ci:7.1f}             | {pi:5.2f}")

if __name__ == "__main__":
    main()
