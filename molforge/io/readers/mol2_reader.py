"""
mol2_reader.py - SYBYL MOL2 格式读取
======================================
RDKit 原生支持 MolFromMol2File。
MOL2 是 Tripos/SYBYL 的标准格式，常见于对接和力场参数化场景。
注意：RDKit 不支持写 MOL2，写走 OpenBabel fallback。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class MOL2Reader(FormatHandler):
    name = "MOL2 (SYBYL)"
    extensions = [".mol2"]
    description = "SYBYL MOL2 文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        mol = Chem.MolFromMol2File(str(path), removeHs=False, sanitize=True)
        if mol is None:
            raise ValueError(f"无法从 {path.name} 读取 MOL2 文件")

        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "mol2"
        m.source_path = path
        m.attach_rdkit_conformers(source="mol2_file")
        return m
