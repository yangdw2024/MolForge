# -*- coding: utf-8 -*-
"""预生成 OSC 砌块真实 3D 坐标 -> Rust FragmentSpec 片段（审计修复 R11）。
坐标来源：PubChem CanonicalSMILES + RDKit ETKDGv3 + MMFF94 弛豫；C60 嵌入失败时数学截角二十面体兜底。"""
import json, math, sys

OUT = r"E:\YDW\Trae_Chemdraw\docs\desktop\fix_20261120\probe\fragments_gen.rs.txt"

SPECS = [
    ("benzene", "Benzene (苯环)", "Aromatic", "c1ccccc1"),
    ("pentacene", "Pentacene (并五苯)", "OSC", "c1ccc2cc3cc4cc5ccccc5cc4cc3cc2c1"),
    ("itic", "ITIC (受体全分子)", "OSC", None),
    ("y6", "Y6 (受体全分子)", "OSC", None),
    ("c60", "Fullerene C60 (富勒烯)", "OSC", None),
]

def load_pubchem(name):
    p = rf"E:\YDW\Trae_Chemdraw\docs\desktop\fix_20261120\probe\pubchem_{name}.json"
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    props = d["PropertyTable"]["Properties"][0]
    smi = props.get("ConnectivitySMILES") or props.get("CanonicalSMILES") or props.get("SMILES")
    return smi, props["MolecularFormula"]

def c60_math():
    phi = (1 + 5 ** 0.5) / 2
    base = [(0, 1, 3 * phi), (1, 2 + phi, 2 * phi), (phi, 2, 2 * phi + 1)]
    verts = set()
    for (a, b, c) in base:
        for sa in (1, -1):
            for sb in (1, -1):
                for sc in (1, -1):
                    v = (sa * a, sb * b, sc * c)
                    # even permutations of (x,y,z)
                    for perm in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
                        verts.add(tuple(v[i] for i in perm))
    verts = sorted(verts)
    assert len(verts) == 60, len(verts)
    scale = 1.42 / 2.0  # edge length 2 -> C-C ~1.42 A
    pts = [[round(x * scale, 3), round(y * scale, 3), round(z * scale, 3)] for (x, y, z) in verts]
    bonds = []
    for i in range(60):
        for j in range(i + 1, 60):
            d = math.dist(pts[i], pts[j])
            if d < 1.5:
                bonds.append((i, j, 1))
    assert len(bonds) == 90, len(bonds)
    # 截角二十面体顶点构型 5.6.6：每个碳恰属 1 个五元环。
    # 五元环上的 60 条边 = 6:5 单键；其余 30 条 6:6 边 = 双键（完美匹配）。
    adj = {i: set() for i in range(60)}
    for (i, j, _) in bonds:
        adj[i].add(j)
        adj[j].add(i)
    pent_edges = set()
    for start in range(60):
        stack = [(start, [start])]
        while stack:
            cur, path = stack.pop()
            if len(path) == 5:
                if start in adj[cur]:
                    cyc = path + [start]
                    for a, b in zip(cyc, cyc[1:]):
                        pent_edges.add(frozenset((a, b)))
                continue
            for nb in adj[cur]:
                if nb not in path and nb > start:
                    stack.append((nb, path + [nb]))
    assert len(pent_edges) == 60, len(pent_edges)
    bonds = [(i, j, 1 if frozenset((i, j)) in pent_edges else 2) for (i, j, _) in bonds]
    assert sum(1 for (_, _, o) in bonds if o == 2) == 30
    dbl = {i for (i, j, o) in bonds if o == 2} | {j for (i, j, o) in bonds if o == 2}
    assert len(dbl) == 60
    return [(6, p) for p in pts], bonds

def embed(smi):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    m = Chem.MolFromSmiles(smi)
    if m is None:
        raise ValueError("bad smiles")
    m = Chem.AddHs(m)
    ok = AllChem.EmbedMolecule(m, randomSeed=42, useRandomCoords=False)
    if ok != 0:
        ok = AllChem.EmbedMolecule(m, randomSeed=42, useRandomCoords=True)
    if ok != 0:
        raise ValueError("embed failed")
    AllChem.MMFFOptimizeMolecule(m, maxIters=500)
    try:
        Chem.Kekulize(m, clearAromaticFlags=True)
        bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(b.GetBondTypeAsDouble())) for b in m.GetBonds()]
    except Exception:
        bonds = []
        for b in m.GetBonds():
            if b.GetIsAromatic():
                o = 2 if (b.GetBeginAtomIdx() + b.GetEndAtomIdx()) % 2 == 0 else 1
            else:
                o = int(b.GetBondTypeAsDouble())
            bonds.append((b.GetBeginAtomIdx(), b.GetEndAtomIdx(), o))
    atoms = [(a.GetAtomicNum(), [round(c, 3) for c in m.GetConformer().GetAtomPosition(a.GetIdx())]) for a in m.GetAtoms()]
    formula = Chem.rdMolDescriptors.CalcMolFormula(m)
    return atoms, bonds, formula

lines = []
report = []
for fid, label, cat, smi in SPECS:
    if fid == "itic":
        smi, _ = load_pubchem("ITIC")
    elif fid == "y6":
        smi, _ = load_pubchem("Y6")
    elif fid == "c60":
        smi, _ = load_pubchem("buckminsterfullerene")
    try:
        atoms, bonds, formula = embed(smi)
        src = "RDKit ETKDG+MMFF"
    except Exception as e:
        if fid == "c60":
            atoms, bonds = c60_math()
            formula = "C60"
            src = "math truncated icosahedron"
        else:
            raise
    report.append(f"{fid}: {len(atoms)} atoms {len(bonds)} bonds formula={formula} src={src}")
    lines.append("        FragmentSpec {")
    lines.append(f'            id: "{fid}",')
    lines.append(f'            label: "{label}",')
    lines.append(f'            category: "{cat}",')
    lines.append(f'            formula: "{formula}",')
    lines.append("            atoms: vec![")
    for z, p in atoms:
        lines.append(f"                ({z}, [{p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f}]),")
    lines.append("            ],")
    lines.append("            bonds: vec![")
    row = []
    for (i, j, o) in bonds:
        row.append(f"({i}, {j}, {o})")
        if len(row) == 8:
            lines.append("                " + ", ".join(row) + ",")
            row = []
    if row:
        lines.append("                " + ", ".join(row) + ",")
    lines.append("            ],")
    lines.append("        },")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(report))
print("WROTE", OUT)