"""
pdb_writer.py - PDB 格式写入
==============================
RDKit 原生支持 MolToPDBFile。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class PDBWriter(FormatHandler):
    name = "PDB 蛋白质结构"
    extensions = [".pdb"]
    description = "PDB 文件"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        if mol.has_3d:
            rmol = Chem.Mol(mol.rdkit_mol)
            conf = Chem.Conformer(rmol.GetNumAtoms())
            coords = mol.conformers[0].coords
            for i in range(rmol.GetNumAtoms()):
                conf.SetAtomPosition(i, coords[i, 0], coords[i, 1], coords[i, 2])
            rmol.RemoveAllConformers()
            rmol.AddConformer(conf, assignId=True)
        else:
            rmol = mol.rdkit_mol

        Chem.MolToPDBFile(rmol, str(path))
