"""
png_writer.py - 2D 结构图导出 PNG
====================================
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Draw

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class PngWriter(FormatHandler):
    name = "PNG"
    extensions = [".png"]
    description = "PNG 位图"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        Draw.MolToFile(
            mol.rdkit_mol,
            str(path),
            size=(600, 400),
            kekulize=True,
        )
