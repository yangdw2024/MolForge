"""
domain/biomolecule.py - 生物分子数据模型
==========================================
PDB/mmCIF 层级：Model → Chain → Residue → Atom
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4, UUID


@dataclass
class BioAtom:
    """生物分子原子。"""
    atom_id: UUID = field(default_factory=uuid4)
    name: str = ""  # 原子名（CA, CB, N, O...）
    element: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    occupancy: float = 1.0
    b_factor: float = 0.0
    alt_loc: str = ""  # 替代位置
    insertion_code: str = ""  # 插入码


@dataclass
class Residue:
    """残基。"""
    residue_id: UUID = field(default_factory=uuid4)
    name: str = ""  # 残基名（ALA, GLY, SER...）
    number: int = 0  # 残基号
    insertion_code: str = ""
    atoms: list[BioAtom] = field(default_factory=list)
    is_standard: bool = True  # 是否标准氨基酸
    is_ligand: bool = False  # 是否配体


@dataclass
class Chain:
    """链。"""
    chain_id: UUID = field(default_factory=uuid4)
    chain_name: str = ""  # 链 ID（A, B, C...）
    residues: list[Residue] = field(default_factory=list)


@dataclass
class Model:
    """模型（多模型文件中的一个）。"""
    model_id: UUID = field(default_factory=uuid4)
    model_number: int = 1
    chains: list[Chain] = field(default_factory=list)


@dataclass
class Biomolecule:
    """生物分子（完整 PDB/mmCIF 结构）。"""
    biomolecule_id: UUID = field(default_factory=uuid4)
    title: str = ""
    models: list[Model] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_chain(self, chain_name: str) -> Chain | None:
        """按名称获取链。"""
        for model in self.models:
            for chain in model.chains:
                if chain.chain_name == chain_name:
                    return chain
        return None

    def get_ligands(self) -> list[Residue]:
        """获取所有配体。"""
        ligands = []
        for model in self.models:
            for chain in model.chains:
                for res in chain.residues:
                    if res.is_ligand:
                        ligands.append(res)
        return ligands

    @property
    def num_atoms(self) -> int:
        """总原子数。"""
        count = 0
        for model in self.models:
            for chain in model.chains:
                for res in chain.residues:
                    count += len(res.atoms)
        return count

    @property
    def num_residues(self) -> int:
        """总残基数。"""
        count = 0
        for model in self.models:
            for chain in model.chains:
                count += len(chain.residues)
        return count
