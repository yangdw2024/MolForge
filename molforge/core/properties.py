"""
properties.py - 分子性质计算
============================
接收一个 Molecule 对象，计算常用描述符。
纯函数，不依赖 UI。
"""

from __future__ import annotations

from rdkit.Chem import Descriptors, rdMolDescriptors

from .molecule import Molecule


def compute_properties(mol: Molecule) -> dict:
    """
    计算常用分子性质，返回字典。

    返回字段:
        formula:         分子式（C9H8O4）
        molecular_weight: 分子量 g/mol
        exact_mass:      精确质量
        heavy_atoms:     重原子数
        logp:            LogP
        tpsa:            TPSA (Å²)
        rotatable_bonds: 可旋转键数
        hbd:             氢键给体数
        hba:             氢键受体数
        rings:           环数
    """
    rmol = mol.rdkit_mol
    return {
        "formula": rdMolDescriptors.CalcMolFormula(rmol),
        "molecular_weight": round(Descriptors.MolWt(rmol), 3),
        "exact_mass": round(rdMolDescriptors.CalcExactMolWt(rmol), 4),
        "heavy_atoms": rmol.GetNumHeavyAtoms(),
        "logp": round(Descriptors.MolLogP(rmol), 3),
        "tpsa": round(rdMolDescriptors.CalcTPSA(rmol), 2),
        "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(rmol),
        "hbd": rdMolDescriptors.CalcNumHBD(rmol),
        "hba": rdMolDescriptors.CalcNumHBA(rmol),
        "rings": rdMolDescriptors.CalcNumRings(rmol),
    }
