"""
xyz_writer.py - XYZ 坐标格式写入
==================================
RDKit 原生支持 MolToXYZFile。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class XYZWriter(FormatHandler):
    name = "XYZ 坐标"
    extensions = [".xyz"]
    description = "XYZ 坐标文件"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        # 如果有 3D 构象，把坐标写进 RDKit Mol 再导出
        if mol.has_3d:
            import numpy as np
            rmol = Chem.Mol(mol.rdkit_mol)
            conf = Chem.Conformer(rmol.GetNumAtoms())
            coords = mol.conformers[0].coords
            for i in range(rmol.GetNumAtoms()):
                conf.SetAtomPosition(i, coords[i, 0], coords[i, 1], coords[i, 2])
            rmol.RemoveAllConformers()
            rmol.AddConformer(conf, assignId=True)
        else:
            rmol = mol.rdkit_mol

        Chem.MolToXYZFile(rmol, str(path))
