"""
openbabel_handler.py - OpenBabel 通用格式处理器（零子进程阻塞版）
"""

from __future__ import annotations

from pathlib import Path

from .registry import FormatHandler, register, _EXT_MAP
from .openbabel_adapter import read_molecule, write_molecule
from ..core.molecule import Molecule

_STATIC_OB_EXTS = [
    ".cif", ".mmcif", ".cdx", ".cdxml", ".cml", ".hin", ".inp", ".mop",
    ".out", ".pqr", ".xyz", ".mol", ".sdf", ".mol2", ".pdb", ".smi",
]


@register
class OpenBabelHandler(FormatHandler):
    name = "OpenBabel 通用格式"
    description = "OpenBabel 支持的化学文件格式"
    can_read = True
    can_write = True

    def __init__(self):
        self.extensions = [e for e in _STATIC_OB_EXTS if e not in _EXT_MAP]

    def read(self, path: Path) -> Molecule:
        return read_molecule(path)

    def write(self, mol: Molecule, path: Path) -> None:
        write_molecule(mol, path)
