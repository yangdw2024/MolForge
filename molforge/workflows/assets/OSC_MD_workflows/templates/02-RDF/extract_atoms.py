#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_atoms.py —— 从 GROMACS .gro 中按原子名提取指定分子的原子序号（RDF 组定义）

模板来源：Ternary_Datas/RDF/backbone-md1/test-MD1/A11.py
泛化说明：
  1) 把目标原子的"原子名列表"填进 ATOM_NAMES；
  2) 把 .gro 中"功能分子前的行数 + 标题行"作为跳过行（默认 2）；
  3) 每个分子原子数写入 ATOMS_PER_MOL（用于每 N 个原子换行，方便核对/生成 ndx）。

用法：
  python extract_atoms.py 1.gro > atoms.out
  # atoms.out 即 gmx rdf -n index.ndx 中该组的原子号，或直接喂给 make_ndx/-sel
"""
import sys

# ============ 需要按体系修改的配置 ============
GRO_FILE      = sys.argv[1] if len(sys.argv) > 1 else '1.gro'
OUT_FILE      = 'atoms.out'
SKIP_LINES    = 2                     # 跳过标题行与原子计数行
TARGET_RESNAME = 'HDO'                # 仅匹配该残基名（或置 None 忽略）
ATOMS_PER_MOL = 68                    # 每个目标分子的原子数（换行用，可设 1e9 不换行）

# 目标原子名列表（示例为 HDO 骨架，来自 A11.py；新体系替换为你的分子原子名）
ATOM_NAMES = [
    'C14','C15','C16','C17','C18','C19','C20','C21','C22','C23','C24','O1',
    'C25','N5','C26','N6','C40','C41','C42','C43','C44','C45','C46','C47',
    'C48','C49','O2','C50','C51','N7','C52','N8','Cl1','Cl2','Cl3','Cl4',
    'C1','C2','C3','C4','C5','C6','N1','N2','S1','C7','C8','N3','N4','C9',
    'S2','C10','C11','S3','C12','C13','S4','C31','C32','C33','S5','C34','C35',
]
# =============================================

name_set = set(ATOM_NAMES)

def main():
    out = open(OUT_FILE, 'w')
    count = 0
    with open(GRO_FILE) as f:
        for i, line in enumerate(f):
            if i < SKIP_LINES:
                continue
            fields = line.split()
            if len(fields) < 5:
                continue
            resname = fields[0][-5:] if len(fields[0]) >= 5 else fields[0]
            atomname = fields[1]
            atomnum  = fields[2]
            if TARGET_RESNAME and TARGET_RESNAME not in fields[0]:
                continue
            if atomname in name_set:
                count += 1
                sep = '\n' if count % ATOMS_PER_MOL == 0 else '  '
                out.write(f'{atomnum}{sep}')
    out.close()
    print(f'[info] 提取原子数: {count}', file=sys.stderr)

if __name__ == '__main__':
    main()
