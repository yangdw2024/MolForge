"""
svg_writer.py - 2D 结构图导出 SVG
===================================
用 RDKit 的 MolToFile 直接写 SVG。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Draw

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class SvgWriter(FormatHandler):
    name = "SVG"
    extensions = [".svg"]
    description = "SVG 矢量图"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        Draw.MolToFile(
            mol.rdkit_mol,
            str(path),
            size=(600, 400),
            kekulize=True,
        )
