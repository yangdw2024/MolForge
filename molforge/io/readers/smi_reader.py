"""
smi_reader.py - SMILES 读取
=============================
SMILES 是文本格式，不是文件扩展名。
这个 reader 主要给"粘贴 SMILES 到输入框"用，也支持 .smi/.smiles 文件。
"""

from __future__ import annotations

from pathlib import Path

try:
    from rdkit import Chem
except ImportError:
    Chem = None

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class SmilesReader(FormatHandler):
    name = "SMILES"
    extensions = [".smi", ".smiles"]
    description = "SMILES 文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        text = path.read_text(encoding="utf-8").strip()
        # .smi 文件每行一个 SMILES，取第一行第一个 token
        first_line = text.splitlines()[0].strip() if text else ""
        smiles = first_line.split()[0] if first_line else ""
        mol = Chem.MolFromSmiles(smiles, sanitize=True)
        if mol is None:
            raise ValueError(f"SMILES 解析失败: {smiles!r}")
        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "smiles"
        m.source_path = path
        return m
