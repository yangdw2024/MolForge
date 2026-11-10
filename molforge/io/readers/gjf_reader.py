"""
gjf_reader.py - Gaussian 输入文件读取
=======================================
解析 .gjf/.com 文件：%chk、route、title、电荷/多重度、坐标。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule
from ...core.conformer import Conformer


@register
class GjfReader(FormatHandler):
    name = "Gaussian Input"
    extensions = [".gjf", ".com"]
    description = "Gaussian 输入文件"
    can_read = True
    can_write = False  # 写 gjf 在 writer 层

    def read(self, path: Path) -> Molecule:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        chk = None
        route = None
        title = ""
        charge = 0
        multiplicity = 1
        atoms = []

        i = 0
        # 1. % 开头的行
        while i < len(lines) and lines[i].startswith("%"):
            if lines[i].lower().startswith("%chk"):
                chk = lines[i].split("=", 1)[1].strip()
            i += 1

        # 2. route 行（# 开头）
        while i < len(lines) and not lines[i].strip():
            i += 1
        route_lines = []
        while i < len(lines) and lines[i].strip().startswith("#"):
            route_lines.append(lines[i].strip())
            i += 1
        route = " ".join(route_lines)

        # 3. 空行后是 title
        while i < len(lines) and not lines[i].strip():
            i += 1
        title_lines = []
        while i < len(lines) and lines[i].strip():
            title_lines.append(lines[i].strip())
            i += 1
        title = " ".join(title_lines)

        # 4. 空行后是电荷/多重度
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            parts = lines[i].split()
            if len(parts) >= 2:
                charge = int(parts[0])
                multiplicity = int(parts[1])
            i += 1

        # 5. 坐标行（直到空行或文件尾）
        while i < len(lines) and lines[i].strip():
            parts = lines[i].split()
            if len(parts) >= 4:
                sym = parts[0]
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    atoms.append((sym, x, y, z))
                except ValueError:
                    pass
            i += 1

        # 建 RDKit Mol
        if atoms:
            xyz = f"{len(atoms)}\n{title}\n"
            for sym, x, y, z in atoms:
                xyz += f"{sym} {x:.6f} {y:.6f} {z:.6f}\n"
            mol = Chem.MolFromXYZBlock(xyz)
            if mol is not None:
                mol = Chem.AddHs(mol, addCoords=True)
        else:
            mol = Chem.RWMol().GetMol()

        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "gjf"
        m.source_path = path
        m.properties["route"] = route or ""
        m.properties["charge"] = charge
        m.properties["multiplicity"] = multiplicity
        m.properties["chk"] = chk

        if atoms:
            import numpy as np
            coords = [[x, y, z] for _, x, y, z in atoms]
            m.conformers.append(Conformer(
                coords=np.array(coords),
                source="gjf_file"
            ))
        return m
