"""
cube_reader.py - Gaussian cube 文件读取
=========================================
cube 文件存三维网格上的标量场（分子轨道、电子密度）。
这里只解析头和原子坐标，不解析庞大的网格数据（渲染时再按需读）。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule
from ...core.conformer import Conformer


@register
class CubeReader(FormatHandler):
    name = "Gaussian Cube"
    extensions = [".cube", ".cub"]
    description = "Cube 轨道/密度文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

        # cube 格式：
        # Line 1-2: 注释
        # Line 3: N_atoms  origin_x origin_y origin_z
        # Line 4: NX  vx1 vx2 vx3
        # Line 5: NY  vy1 vy2 vy3
        # Line 6: NZ  vz1 vz2 vz3
        # Line 7..: 原子序数 电荷  x y z（每原子一行）

        n_atoms = int(lines[2].split()[0])
        nx = int(lines[3].split()[0])
        ny = int(lines[4].split()[0])
        nz = int(lines[5].split()[0])

        atoms = []
        for i in range(6, 6 + n_atoms):
            parts = lines[i].split()
            atomic_num = int(float(parts[0]))
            x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
            atoms.append((atomic_num, x, y, z))

        # 建 RDKit Mol
        sym_map = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F", 15: "P", 16: "S", 17: "Cl"}
        xyz = f"{n_atoms}\n\n"
        for z, x, y, zc in atoms:
            xyz += f"{sym_map.get(z, 'C')} {x:.6f} {y:.6f} {zc:.6f}\n"
        mol = Chem.MolFromXYZBlock(xyz)
        if mol is not None:
            mol = Chem.AddHs(mol, addCoords=True)

        m = Molecule.from_rdkit(mol or Chem.RWMol().GetMol(), name=path.stem)
        m.source_format = "cube"
        m.source_path = path
        m.properties["grid"] = (nx, ny, nz)

        if atoms:
            import numpy as np
            coords = [[x, y, zc] for _, x, y, zc in atoms]
            m.conformers.append(Conformer(
                coords=np.array(coords),
                source="cube_file"
            ))
        return m
