"""
rendering/bridge.py - 新旧架构桥接层
=====================================
把旧的 core/Molecule 转成新架构的 RenderSnapshot。
过渡期使用，最终主窗口完全迁移到 MoleculeDocument。
"""

from __future__ import annotations

import numpy as np
from rdkit import Chem

from .contracts import RenderSnapshot, RepresentationMode
from ..domain.ids import AtomId


def rdkit_mol_to_snapshot(
    rmol: Chem.Mol,
    mode: RepresentationMode = RepresentationMode.BALL_AND_STICK,
) -> RenderSnapshot:
    """
    从 RDKit Mol 生成 RenderSnapshot。

    过渡期桥接：旧代码用 RDKit Mol，新架构用 MoleculeDocument。
    这个函数把 RDKit Mol 转成渲染器能消费的快照。
    """
    # 原子
    n_atoms = rmol.GetNumAtoms()
    atomic_numbers = np.zeros(n_atoms, dtype=np.int32)
    atom_ids = []

    # 坐标（取第一个构象）
    coordinates = np.zeros((n_atoms, 3), dtype=np.float64)
    has_3d = rmol.GetNumConformers() > 0

    for i in range(n_atoms):
        atom = rmol.GetAtomWithIdx(i)
        atomic_numbers[i] = atom.GetAtomicNum()
        atom_ids.append(AtomId(i))  # 临时用索引作为 AtomId

        if has_3d:
            conf = rmol.GetConformer()
            p = conf.GetAtomPosition(i)
            coordinates[i] = [p.x, p.y, p.z]

    # 键
    bonds = []
    for bond in rmol.GetBonds():
        begin = bond.GetBeginAtomIdx()
        end = bond.GetEndAtomIdx()
        order = int(bond.GetBondTypeAsDouble())
        bonds.append((begin, end, order))

    return RenderSnapshot(
        atom_ids=atom_ids,
        atomic_numbers=atomic_numbers,
        bonds=bonds,
        coordinates=coordinates,
        mode=mode,
    )
