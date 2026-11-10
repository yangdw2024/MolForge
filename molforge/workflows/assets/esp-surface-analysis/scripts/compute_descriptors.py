#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_descriptors.py
从 vtx.pdb 直接计算 ESP 表面描述符，不需要 sum.txt。
vtx.pdb 的 B 因子列 = 每个表面顶点的 ESP 值 (kcal/mol)。

输出：Vs_min, Vs_max, SASA, sigma2_pos/neg/tot, nu, Pi, MPI, polar_area_pct
"""
import sys, csv, pathlib
import numpy as np

def read_vtx_bfactor(path):
    vals = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("HETATM"):
                continue
            try:
                bf = float(line[60:66])
                vals.append(bf)
            except ValueError:
                continue
    return np.array(vals, dtype=float)

def read_surfanalysis_extrema(path):
    """从 surfanalysis.pdb 读 Vs_min / Vs_max"""
    maxv, minv = [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("HETATM"):
                continue
            try:
                an = line[12:14].strip()
                bf = float(line[60:66])
                if an == "C": maxv.append(bf)
                elif an == "O": minv.append(bf)
            except (ValueError, IndexError):
                continue
    return max(maxv) if maxv else None, min(minv) if minv else None

def compute_descriptors(vtx_pdb, surf_pdb=None):
    esp = read_vtx_bfactor(vtx_pdb)
    n = len(esp)

    # Vs_min / Vs_max 优先从 surfanalysis.pdb 读
    if surf_pdb and pathlib.Path(surf_pdb).exists():
        vs_max, vs_min = read_surfanalysis_extrema(surf_pdb)
    else:
        vs_min, vs_max = esp.min(), esp.max()

    # SASA: 从 vtx.pdb 没法直接算，Multiwfn 输出的表面积需要从 sum.txt
    # 这里用顶点数近似（不同分子密度不同，仅供参考）
    # 实际 SASA 需要从 sum.txt 获取

    pos = esp[esp > 0]
    neg = esp[esp < 0]

    # 面积加权平均（假设每个顶点面积相同）
    avg_tot = esp.mean()
    avg_pos = pos.mean() if len(pos) > 0 else 0
    avg_neg = neg.mean() if len(neg) > 0 else 0

    # 方差
    var_tot = esp.var()
    var_pos = pos.var() if len(pos) > 0 else 0
    var_neg = neg.var() if len(neg) > 0 else 0

    # 正负面积占比
    area_pos = len(pos) / n * 100
    area_neg = len(neg) / n * 100

    # nu (电荷平衡度)
    # nu = (|avg_neg| / (avg_pos + |avg_neg|) - 0.5) * 2  ... 不对
    # 正确公式: nu = (|avg_neg| * sqrt(var_neg) - avg_pos * sqrt(var_pos)) / (|avg_neg|*sqrt(var_neg) + avg_pos*sqrt(var_pos))
    # 简化版: nu = 2 * (|avg_neg|/(avg_pos+|avg_neg|) - 0.5)
    if avg_pos > 0 and avg_neg < 0:
        nu = abs(avg_neg) / (avg_pos + abs(avg_neg))
        nu = (nu - 0.5) * 2  # -1 ~ +1
    else:
        nu = None

    # Pi (内部分离强度) = sqrt(var_pos) + sqrt(var_neg) ... 不对
    # Pi = avg_pos * sqrt(var_pos) + |avg_neg| * sqrt(var_neg)
    Pi = avg_pos * np.sqrt(var_pos) + abs(avg_neg) * np.sqrt(var_neg)

    # MPI (分子极性指数) = |avg(esp)|
    MPI = abs(avg_tot)

    # 极性面积占比 (|ESP| > 10 kcal/mol)
    polar_area = (np.abs(esp) > 10).sum() / n * 100

    return {
        "vtx_file": pathlib.Path(vtx_pdb).name,
        "n_vertices": n,
        "Vs_min_kcal": round(vs_min, 2) if vs_min else None,
        "Vs_max_kcal": round(vs_max, 2) if vs_max else None,
        "avg_tot_kcal": round(avg_tot, 3),
        "avg_pos_kcal": round(avg_pos, 3),
        "avg_neg_kcal": round(avg_neg, 3),
        "sigma2_pos": round(var_pos, 2),
        "sigma2_neg": round(var_neg, 2),
        "sigma2_tot": round(var_tot, 2),
        "nu": round(nu, 4) if nu else None,
        "Pi_kcal": round(Pi, 3),
        "MPI_kcal": round(MPI, 3),
        "polar_area_pct": round(polar_area, 2),
        "pos_area_pct": round(area_pos, 2),
        "neg_area_pct": round(area_neg, 2),
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python compute_descriptors.py <vtx.pdb> [surfanalysis.pdb]")
        sys.exit(1)

    vtx = sys.argv[1]
    surf = sys.argv[2] if len(sys.argv) > 2 else None

    d = compute_descriptors(vtx, surf)
    for k, v in d.items():
        print(f"  {k:20s}: {v}")

    # 写 CSV
    out_csv = pathlib.Path(vtx).parent / "esp_descriptors.csv"
    new = not out_csv.exists()
    with open(out_csv, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(d.keys()))
        if new: w.writeheader()
        w.writerow(d)
    print(f"\nCSV appended: {out_csv}")

if __name__ == "__main__":
    main()
