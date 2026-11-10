"""
mol_reader.py - MOL/SDF 读取
=============================
MDL MOL 和 SDF 是化学领域最通用的结构交换格式。
RDKit 自带 SDMolSupplier。
"""

from __future__ import annotations

from pathlib import Path

try:
    from rdkit import Chem
except ImportError:
    Chem = None

from ..registry import FormatHandler, register
from ...core.molecule import Molecule
from ...core.conformer import Conformer


@register
class MolReader(FormatHandler):
    name = "MOL/SDF"
    extensions = [".mol", ".sdf", ".sd"]
    description = "MOL/SDF 文件"
    can_read = True
    can_write = False  # 写 MOL/SDF 放 writer 层

    def read(self, path: Path) -> Molecule:
        suppl = Chem.SDMolSupplier(str(path), sanitize=True, removeHs=False)
        mol = None
        for m in suppl:
            if m is not None:
                mol = m
                break
        if mol is None:
            raise ValueError(f"无法从 {path.name} 读到有效分子")

        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "mol/sdf"
        m.source_path = path

        # 如果文件里有 3D 坐标，转成 Conformer
        if mol.GetNumConformers() > 0:
            conf = mol.GetConformer()
            coords = []
            for i in range(mol.GetNumAtoms()):
                p = conf.GetAtomPosition(i)
                coords.append([p.x, p.y, p.z])
            import numpy as np
            m.conformers.append(Conformer(
                coords=np.array(coords),
                source="read_from_file"
            ))
        return m
