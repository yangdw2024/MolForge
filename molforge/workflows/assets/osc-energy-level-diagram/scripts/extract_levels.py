# -*- coding: utf-8 -*-
# extract_levels.py
# 从 Gaussian fchk 提取 HOMO/LUMO 轨道能量 (Hartree -> eV)
# 数据来自 <D_DRIVE_YDW>\OSC\Object_1\Binary_Datas\B3LYP_6-311g(d,p)\
import re

HA2EV = 27.211386245988
BASE = r"<D_DRIVE_YDW>\OSC\Object_1\Binary_Datas\B3LYP_6-311g(d,p)"

# (显示名, fchk文件名, HOMO轨道号 1-based)
targets = [
    ("BTP-ClFFCl", "ydw-BTP-ClFFCl_B3LYP.fchk", 407),
    ("BTP-FClClF", "ydw-BTP-FClClF_B3LYP.fchk", 407),
    ("BTP-FClFCl", "ydw-BTP-FClFCl_B3LYP.fchk", 407),
    ("BTP-FFClCl", "ydw-BTP-FFClCl_B3LYP.fchk", 407),
    ("HDO-4Cl",    "ydw-HDO4Cl_B3LYP.fchk",     463),
]

def read_orb_energies(path):
    """流式读取 fchk, 返回 Alpha Orbital Energies 列表 (Hartree), 0-based"""
    vals = []
    n = None
    started = False
    with open(path, 'r') as f:
        for ln in f:
            if not started:
                if ln.startswith("Alpha Orbital Energies"):
                    m = re.search(r'N=\s*(\d+)', ln)
                    n = int(m.group(1))
                    started = True
                continue
            for p in ln.split():
                try:
                    vals.append(float(p.replace('D', 'E')))
                except ValueError:
                    pass
            if n is not None and len(vals) >= n:
                break
    return vals

print(f"{'Molecule':<14}{'HOMO#':>6}{'HOMO(eV)':>12}{'LUMO#':>6}{'LUMO(eV)':>12}{'Gap(eV)':>10}")
print("-" * 60)
results = {}
import os
for name, fname, hi in targets:
    path = os.path.join(BASE, fname)
    e = read_orb_energies(path)
    eh = e[hi - 1] * HA2EV
    el = e[hi] * HA2EV
    gap = el - eh
    results[name] = (eh, el, gap)
    print(f"{name:<14}{hi:>6}{eh:>12.4f}{hi+1:>6}{el:>12.4f}{gap:>10.4f}")

# 存成字典供拼图脚本用
import json
out = {k: {"homo": round(v[0], 2), "lumo": round(v[1], 2), "gap": round(v[2], 2)}
       for k, v in results.items()}
with open(os.path.join(os.path.dirname(__file__), "levels.json"), "w") as f:
    json.dump(out, f, indent=2)
print("\nsaved -> levels.json")
