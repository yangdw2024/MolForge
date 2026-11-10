# -*- coding: utf-8 -*-
# verify_from_log.py
# 直接从 Gaussian log 抓最后一次 SCF 的 HOMO/LUMO (Hartree) -> eV
import re, os

HA2EV = 27.211386245988
BASE = r"<D_DRIVE_YDW>\OSC\Object_1\Binary_Datas\B3LYP_6-311g(d,p)"
files = [
    ("BTP-ClFFCl", "ydw-BTP-ClFFCl_B3LYP.log"),
    ("BTP-FClClF", "ydw-BTP-FClClF_B3LYP.log"),
    ("BTP-FClFCl", "ydw-BTP-FClFCl_B3LYP.log"),
    ("BTP-FFClCl", "ydw-BTP-FFClCl_B3LYP.log"),
    ("HDO-4Cl",    "ydw-HDO4Cl_B3LYP.log"),
]

occ_re  = re.compile(r'Alpha\s+occ\.\s+eigenvalues\s*--\s*(.*)')
virt_re = re.compile(r'Alpha\s+virt\.\s+eigenvalues\s*--\s*(.*)')

def parse(path):
    occ_vals, virt_vals = [], []
    last_occ_block, last_virt_block = [], []
    with open(path, 'r', errors='ignore') as f:
        for ln in f:
            mo = occ_re.search(ln)
            mv = virt_re.search(ln)
            if mo:
                raw = mo.group(1)
                raw = re.sub(r'(?<=\d)(?=-)', ' ', raw)  # 相邻负数之间补空格
                nums = [float(x) for x in raw.split()]
                # 新的一组 occ 行: 如果上一组 occ 之后已经出现过 virt, 说明是新一轮 SCF, 重置
                if last_virt_block:
                    last_occ_block, last_virt_block = [], []
                last_occ_block.extend(nums)
            elif mv:
                raw = re.sub(r'(?<=\d)(?=-)', ' ', mv.group(1))
                nums = [float(x) for x in raw.split()]
                last_virt_block.extend(nums)
    # 最后一轮的 HOMO = occ 块最后一个, LUMO = virt 块第一个
    return last_occ_block[-1], last_virt_block[0]

print(f"{'Molecule':<14}{'HOMO(Ha)':>12}{'HOMO(eV)':>10}{'LUMO(Ha)':>12}{'LUMO(eV)':>10}")
print("-" * 60)
for name, fn in files:
    eh, el = parse(os.path.join(BASE, fn))
    print(f"{name:<14}{eh:>12.6f}{eh*HA2EV:>10.3f}{el:>12.6f}{el*HA2EV:>10.3f}")
