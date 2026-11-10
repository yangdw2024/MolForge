"""
io/format_matrix.py - 格式保真矩阵
=====================================
记录每种文件格式支持哪些信息，以及导入/导出时会丢失什么。

格式保真矩阵：
  - MOL: 2D 结构 + 3D 坐标 + 手性 + 电荷
  - SDF: MOL + 多构象 + 属性
  - SMILES: 2D 连接性（无坐标、无手性可选）
  - PDB: 大分子 + 残基 + 链
  - XYZ: 坐标 + 原子序数（无连接性）
  - Cube: 体数据（轨道/密度）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FormatSupport(Enum):
    """格式支持级别。"""
    FULL = "full"          # 完整支持
    PARTIAL = "partial"    # 部分支持
    NONE = "none"          # 不支持


@dataclass
class FormatCapability:
    """格式能力描述。"""
    format_name: str
    description: str
    read: bool = False
    write: bool = False
    supports_2d: bool = False
    supports_3d: bool = False
    supports_chirality: bool = False
    supports_charges: bool = False
    supports_conformers: bool = False
    supports_bonds: bool = False
    supports_atom_names: bool = False
    supports_residues: bool = False
    supports_properties: bool = False
    loss_notes: list[str] = field(default_factory=list)


# 格式保真矩阵
FORMAT_MATRIX: dict[str, FormatCapability] = {
    "mol": FormatCapability(
        format_name="MOL",
        description="MDL MOL 文件（单分子）",
        read=True, write=True,
        supports_2d=True, supports_3d=True,
        supports_chirality=True, supports_charges=True,
        supports_conformers=False, supports_bonds=True,
        supports_atom_names=True, supports_residues=False,
        supports_properties=False,
    ),
    "sdf": FormatCapability(
        format_name="SDF",
        description="MDL Structure Data File（多分子/多构象）",
        read=True, write=True,
        supports_2d=True, supports_3d=True,
        supports_chirality=True, supports_charges=True,
        supports_conformers=True, supports_bonds=True,
        supports_atom_names=True, supports_residues=False,
        supports_properties=True,
    ),
    "smiles": FormatCapability(
        format_name="SMILES",
        description="SMILES 字符串（连接性）",
        read=True, write=True,
        supports_2d=True, supports_3d=False,
        supports_chirality=True, supports_charges=True,
        supports_conformers=False, supports_bonds=True,
        supports_atom_names=False, supports_residues=False,
        supports_properties=False,
        loss_notes=["无坐标，需要生成 2D/3D"],
    ),
    "xyz": FormatCapability(
        format_name="XYZ",
        description="XYZ 坐标文件",
        read=True, write=True,
        supports_2d=False, supports_3d=True,
        supports_chirality=False, supports_charges=False,
        supports_conformers=True, supports_bonds=False,
        supports_atom_names=False, supports_residues=False,
        supports_properties=False,
        loss_notes=["无连接性（键），需要自动成键"],
    ),
    "pdb": FormatCapability(
        format_name="PDB",
        description="Protein Data Bank 格式",
        read=True, write=False,
        supports_2d=False, supports_3d=True,
        supports_chirality=False, supports_charges=True,
        supports_conformers=True, supports_bonds=True,
        supports_atom_names=True, supports_residues=True,
        supports_properties=False,
    ),
    "cif": FormatCapability(
        format_name="CIF",
        description="mmCIF 晶体结构格式",
        read=True, write=False,
        supports_2d=False, supports_3d=True,
        supports_chirality=False, supports_charges=False,
        supports_conformers=False, supports_bonds=True,
        supports_atom_names=True, supports_residues=True,
        supports_properties=True,
    ),
    "cube": FormatCapability(
        format_name="Cube",
        description="Gaussian Cube 体数据",
        read=True, write=False,
        supports_2d=False, supports_3d=True,
        supports_chirality=False, supports_charges=False,
        supports_conformers=False, supports_bonds=False,
        supports_atom_names=False, supports_residues=False,
        supports_properties=False,
        loss_notes=["仅体数据（轨道/密度），无完整分子信息"],
    ),
    "mforge": FormatCapability(
        format_name="MForge",
        description="MolForge 原生项目格式",
        read=True, write=True,
        supports_2d=True, supports_3d=True,
        supports_chirality=True, supports_charges=True,
        supports_conformers=True, supports_bonds=True,
        supports_atom_names=True, supports_residues=True,
        supports_properties=True,
    ),
}


def get_format_capability(format_name: str) -> FormatCapability | None:
    """获取格式能力描述。"""
    return FORMAT_MATRIX.get(format_name.lower())


def list_supported_formats() -> list[str]:
    """列出所有支持的格式。"""
    return [name for name, cap in FORMAT_MATRIX.items() if cap.read]


def get_import_loss_notes(format_name: str) -> list[str]:
    """获取导入该格式时会丢失的信息。"""
    cap = FORMAT_MATRIX.get(format_name.lower())
    if cap is None:
        return ["未知格式"]
    notes = list(cap.loss_notes)
    if not cap.supports_bonds:
        notes.append("无键信息，需要自动成键")
    if not cap.supports_chirality:
        notes.append("无手性信息")
    if not cap.supports_3d:
        notes.append("无 3D 坐标")
    return notes
