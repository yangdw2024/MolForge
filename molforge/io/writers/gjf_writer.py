"""
gjf_writer.py - Gaussian 输入文件写出
=======================================
从 Molecule 对象生成 .gjf 文件。
默认 route: # B3LYP/6-31G(d,p) opt（可在 properties 里覆盖）。
"""

from __future__ import annotations

from pathlib import Path

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class GjfWriter(FormatHandler):
    name = "Gaussian Input"
    extensions = [".gjf"]
    description = "Gaussian 输入文件"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        rmol = mol.rdkit_mol

        route = mol.properties.get("route", "# B3LYP/6-31G(d,p) opt")
        charge = mol.properties.get("charge", 0)
        multiplicity = mol.properties.get("multiplicity", 1)
        chk = mol.properties.get("chk", path.stem + ".chk")

        # 取 3D 坐标（如果有），否则用 2D 坐标
        if mol.has_3d:
            conf = mol.conformers[0]
            coords = conf.coords
        else:
            # 没有 3D 坐标，用 RDKit 2D 坐标（z=0）
            from rdkit.Chem import AllChem
            AllChem.Compute2DCoords(rmol)
            rdkit_conf = rmol.GetConformer()
            coords = []
            for i in range(rmol.GetNumAtoms()):
                p = rdkit_conf.GetAtomPosition(i)
                coords.append([p.x, p.y, 0.0])

        # 元素符号
        from rdkit.Chem import GetPeriodicTable
        pt = GetPeriodicTable()
        syms = []
        for atom in rmol.GetAtoms():
            syms.append(pt.GetElementSymbol(atom.GetAtomicNum()))

        # 组装 gjf 文本
        lines = []
        lines.append(f"%chk={chk}")
        lines.append(f"%nprocshared=4")
        lines.append(f"%mem=4GB")
        lines.append(route)
        lines.append("")
        lines.append(mol.name or path.stem)
        lines.append("")
        lines.append(f"{charge} {multiplicity}")
        for sym, (x, y, z) in zip(syms, coords):
            lines.append(f" {sym:<3s} {x:>14.6f} {y:>14.6f} {z:>14.6f}")
        lines.append("")  # 坐标后必须空一行
        lines.append("")  # 再一个空行结束

        path.write_text("\n".join(lines), encoding="utf-8")
