"""
xyz_reader.py - XYZ 坐标格式读取
==================================
XYZ 是计算化学最通用的纯坐标格式。
每行一个原子：元素符号 x y z。
RDKit 原生支持。
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


@register
class XYZReader(FormatHandler):
    name = "XYZ 坐标"
    extensions = [".xyz"]
    description = "XYZ 坐标文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        # MolFromXYZFile 只接受文件路径参数
        mol = Chem.MolFromXYZFile(str(path))
        if mol is None:
            raise ValueError(f"无法从 {path.name} 读取 XYZ 文件")

        # XYZ 文件只有坐标没有键信息，尝试 sanitize，失败也不阻断
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            pass

        # 手动标记构象为 3D
        if mol.GetNumConformers() > 0:
            mol.GetConformer().Set3D(True)

        m = Molecule.from_rdkit(mol, name=path.stem)
        m.source_format = "xyz"
        m.source_path = path
        m.attach_rdkit_conformers(source="xyz_file")
        return m
