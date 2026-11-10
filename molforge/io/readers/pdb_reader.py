"""
pdb_reader.py - PDB 蛋白质数据库格式读取
==========================================
RDKit 原生支持 MolFromPDBFile。
保留残基名、链 ID 等蛋白质特有信息（写在分子属性里）。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class PDBReader(FormatHandler):
    name = "PDB 蛋白质结构"
    extensions = [".pdb", ".ent"]
    description = "PDB / ENT 蛋白质结构文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        mol = Chem.MolFromPDBFile(str(path), removeHs=False, sanitize=True)
        if mol is None:
            raise ValueError(f"无法从 {path.name} 读取 PDB 文件")

        # PDB 读出来的构象默认 Is3D=False，手动标记为 3D
        if mol.GetNumConformers() > 0:
            mol.GetConformer().Set3D(True)

        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "pdb"
        m.source_path = path
        m.attach_rdkit_conformers(source="pdb_file")
        return m
