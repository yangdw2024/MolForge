"""
molecule.py - 分子一等公民对象
==============================
Molecule 是整个软件的核心数据模型。所有 io/render/ai/ui 都围绕它转。

它不只是包一层 RDKit Mol，而是一个完整的化学对象：
- 2D 结构（原子、键、芳香性）→ rdkit_mol
- 3D 构象 → conformers 列表
- 计算结果 → energy、orbitals
- 来源信息 → source_format、source_path
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
try:
    from rdkit import Chem
except ImportError:
    Chem = None

from .conformer import Conformer
from .orbital import Orbital


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Molecule:
    """
    分子对象（一等公民）。

    属性:
        id:           唯一 ID（自动生成）
        name:         用户起的名字（可选）
        rdkit_mol:    RDKit 分子对象（2D 结构核心）
        conformers:   3D 构象列表
        energy:       单点能（Hartree，如果有）
        orbitals:     分子轨道列表（如果有）
        source_format: 来源格式（'smiles' / 'mol' / 'gjf' / 'gaussian_log'）
        source_path:  来源文件路径
        properties:   缓存的性质字典
    """

    rdkit_mol: Chem.Mol
    id: str = field(default_factory=_new_id)
    name: str | None = None
    conformers: list[Conformer] = field(default_factory=list)
    energy: float | None = None
    orbitals: list[Orbital] | None = None
    source_format: str = "unknown"
    source_path: Path | None = None
    properties: dict = field(default_factory=dict)

    # ---------- 便捷属性 ----------

    @property
    def num_atoms(self) -> int:
        return self.rdkit_mol.GetNumAtoms()

    @property
    def num_bonds(self) -> int:
        return self.rdkit_mol.GetNumBonds()

    @property
    def formula(self) -> str:
        """分子式，例如 C9H8O4。"""
        from rdkit.Chem import rdMolDescriptors
        return rdMolDescriptors.CalcMolFormula(self.rdkit_mol)

    @property
    def has_3d(self) -> bool:
        return len(self.conformers) > 0

    @property
    def homo(self) -> Orbital | None:
        """最高占据分子轨道。"""
        if not self.orbitals:
            return None
        occupied = [o for o in self.orbitals if o.is_occupied]
        return max(occupied, key=lambda o: o.energy_ev) if occupied else None

    @property
    def lumo(self) -> Orbital | None:
        """最低空分子轨道。"""
        if not self.orbitals:
            return None
        virtual = [o for o in self.orbitals if not o.is_occupied]
        return min(virtual, key=lambda o: o.energy_ev) if virtual else None

    @property
    def gap_ev(self) -> float | None:
        """HOMO-LUMO gap（eV）。"""
        if self.homo and self.lumo:
            return self.lumo.energy_ev - self.homo.energy_ev
        return None

    # ---------- 构造方法 ----------

    @classmethod
    def from_rdkit(cls, mol: Chem.Mol, name: str | None = None, attach_conformers: bool = True) -> "Molecule":
        """
        从 RDKit Mol 对象构造。

        Args:
            mol: RDKit Mol 对象
            name: 分子名称
            attach_conformers: 是否自动把 RDKit 的 3D 构象转成 MolForge Conformer
        """
        instance = cls(rdkit_mol=mol, name=name)
        if attach_conformers:
            instance.attach_rdkit_conformers(source="from_rdkit")
        return instance

    def attach_rdkit_conformers(self, source: str = "read_from_file") -> int:
        """
        把 RDKit Mol 里的所有 3D 构象转成 MolForge Conformer 挂到当前分子上。

        返回：成功附加的构象数量。
        """
        n = 0
        if self.rdkit_mol.GetNumConformers() == 0:
            return 0
        for conf in self.rdkit_mol.GetConformers():
            if not conf.Is3D():
                continue
            n_atoms = self.rdkit_mol.GetNumAtoms()
            coords = np.zeros((n_atoms, 3), dtype=float)
            for i in range(n_atoms):
                p = conf.GetAtomPosition(i)
                coords[i] = [p.x, p.y, p.z]
            self.conformers.append(Conformer(coords=coords, source=source))
            n += 1
        return n

    def summary(self) -> str:
        """一行人类可读摘要。"""
        parts = [f"{self.formula}"]
        if self.name:
            parts.insert(0, self.name)
        if self.energy is not None:
            parts.append(f"E={self.energy:.6f} Ha")
        if self.gap_ev is not None:
            parts.append(f"gap={self.gap_ev:.2f} eV")
        return " | ".join(parts)
