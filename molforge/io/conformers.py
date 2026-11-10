"""
io/conformers.py - 构象生成与力场优化
=========================================
基于 RDKit 的 ETKDG 嵌入和 MMFF/UFF 力场优化。

特性：
  - 相同 seed 可复现
  - 记录嵌入失败原因
  - 能量带单位和算法版本
  - RMSD 聚类
  - 多构象来源追踪
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors

from ..domain.document import MoleculeDocument


@dataclass
class ConformerResult:
    """构象生成结果。"""
    success: bool
    n_conformers: int = 0
    energies: list[float] = field(default_factory=list)  # kcal/mol
    rmsd_matrix: np.ndarray | None = None
    error_message: str = ""
    seed: int = 42
    method: str = "ETKDGv3+MMFF94"


class ConformerGenerator:
    """
    构象生成器。

    用法：
        gen = ConformerGenerator()
        result = gen.generate(doc, n_conformers=20)
        if result.success:
            # 使用 result.energies 排序
            pass
    """

    def __init__(self) -> None:
        self._last_seed = 42

    def generate(self, doc: MoleculeDocument,
                 n_conformers: int = 20,
                 seed: int = 42,
                 optimize: bool = True) -> ConformerResult:
        """
        生成多个构象。

        Args:
            doc: 分子文档
            n_conformers: 目标构象数
            seed: 随机种子（可复现）
            optimize: 是否做力场优化

        Returns:
            ConformerResult
        """
        self._last_seed = seed

        # 先转成 RDKit Mol
        from .rdkit_adapter import doc_to_rdkit
        rdmol, _, _ = doc_to_rdkit(doc, sanitize=True)

        if rdmol is None:
            return ConformerResult(
                success=False,
                error_message="无法创建 RDKit 分子（sanitize 失败）",
                seed=seed,
            )

        # 加氢
        rdmol = Chem.AddHs(rdmol)

        # ETKDG 嵌入
        params = AllChem.ETKDGv3()
        params.randomSeed = seed
        params.numThreads = 0  # 自动

        try:
            n_embedded = AllChem.EmbedMultipleConfs(rdmol, numConfs=n_conformers, params=params)
        except Exception as e:
            return ConformerResult(
                success=False,
                error_message=f"嵌入失败: {str(e)}",
                seed=seed,
            )

        if n_embedded == 0:
            return ConformerResult(
                success=False,
                error_message="嵌入失败：未生成任何构象",
                seed=seed,
            )

        # 力场优化
        energies = []
        if optimize:
            # 尝试 MMFF，失败则用 UFF
            try:
                props = AllChem.MMFFGetMoleculeProperties(rdmol)
                if props is not None:
                    for conf_id in range(n_embedded):
                        ff = AllChem.MMFFGetMoleculeForceField(rdmol, props, confId=conf_id)
                        if ff is not None:
                            ff.Minimize()
                            e = ff.CalcEnergy()
                            energies.append(e)
                    method = "ETKDGv3+MMFF94"
                else:
                    raise ValueError("MMFF 不可用")
            except Exception:
                # 用 UFF
                for conf_id in range(n_embedded):
                    ff = AllChem.UFFGetMoleculeForceField(rdmol, confId=conf_id)
                    if ff is not None:
                        ff.Minimize()
                        e = ff.CalcEnergy()
                        energies.append(e)
                method = "ETKDGv3+UFF"
        else:
            method = "ETKDGv3"

        # 计算 RMSD 矩阵
        rmsd_matrix = None
        if n_embedded > 1:
            try:
                rmsd_matrix = AllChem.GetConformerRMSMatrix(rdmol)
            except Exception:
                pass

        # 把构象写回文档
        doc.ensure_coordinates()
        # 清除旧帧
        doc.coordinates._frames.clear()

        for conf_id in range(n_embedded):
            conf = rdmol.GetConformer(conf_id)
            n_atoms = rdmol.GetNumAtoms()
            coords = np.zeros((n_atoms, 3))
            for i in range(n_atoms):
                pos = conf.GetAtomPosition(i)
                coords[i] = [pos.x, pos.y, pos.z]

            energy = energies[conf_id] if conf_id < len(energies) else None
            doc.coordinates.add_frame(
                coords=coords,
                energy=energy,
                source=f"conformer_{conf_id}",
            )

        return ConformerResult(
            success=True,
            n_conformers=n_embedded,
            energies=energies,
            rmsd_matrix=rmsd_matrix,
            seed=seed,
            method=method,
        )

    def cluster_by_rmsd(self, rmsd_threshold: float = 1.0) -> list[list[int]]:
        """
        按 RMSD 聚类构象。

        Args:
            rmsd_threshold: RMSD 阈值（Å）

        Returns:
            聚类结果，每个聚类是构象索引列表
        """
        # 简化版：距离矩阵聚类
        # TODO: 实现完整的聚类算法
        return [[0]]  # 占位
