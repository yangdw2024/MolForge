# -*- coding: utf-8 -*-
"""从 Gaussian fchk 提取 HOMO/LUMO 轨道能量 (Hartree -> eV)"""
import re, csv

HA2EV = 27.211386245988

def read_orb_energies(fchk_path):
    with open(fchk_path, 'r') as f:
        lines = f.readlines()
    start = None
    n = None
    for i, ln in enumerate(lines):
        if ln.startswith("Alpha Orbital Energies"):
            m = re.search(r'N=\s*(\d+)', ln)
            n = int(m.group(1)) if m else None
            start = i + 1
            break
    if start is None:
        raise RuntimeError("Alpha Orbital Energies not found in " + fchk_path)
    vals = []
    i = start
    while len(vals) < (n or 1e9):
        parts = lines[i].split()
        for p in parts:
            try:
                vals.append(float(p.replace('D', 'E')))
            except ValueError:
                pass
        i += 1
        if i >= len(lines):
            break
    return vals

def extract_molecule(name, fchk_path, homo_orb_num):
    """homo_orb_num: 1-based HOMO orbital index"""
    e = read_orb_energies(fchk_path)
    eh = e[homo_orb_num - 1] * HA2EV
    el = e[homo_orb_num] * HA2EV
    return {
        'name': name,
        'homo_ev': round(eh, 4),
        'lumo_ev': round(el, 4),
        'gap_ev': round(el - eh, 4),
        'homo_orb': homo_orb_num,
        'lumo_orb': homo_orb_num + 1,
    }

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 4:
        print("Usage: python extract_orb_energy.py <fchk> <homo_orb_num> <name>")
        sys.exit(1)
    fchk = sys.argv[1]
    homo_num = int(sys.argv[2])
    name = sys.argv[3]
    r = extract_molecule(name, fchk, homo_num)
    print(f"{name}: HOMO={r['homo_ev']} eV, LUMO={r['lumo_ev']} eV, Gap={r['gap_ev']} eV")
