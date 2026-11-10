"""
conformer.py - 3D 构象
======================
一个 Conformer 就是一组原子的 3D 坐标。
一个分子可能有多个构象（比如不同的 rotamer）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Conformer:
    """
    单个 3D 构象。

    属性:
        coords:  N×3 的 numpy 数组，每行是一个原子的 (x, y, z)，单位 Å
        energy:  这个构象的能量（如果做过优化），单位 eV 或 Hartree
        source:  构象来源（'etkdg' / 'optimized' / 'read_from_file'）
    """
    coords: np.ndarray
    energy: float | None = None
    source: str = "unknown"

    def __post_init__(self):
        if not isinstance(self.coords, np.ndarray):
            self.coords = np.array(self.coords, dtype=float)
        if self.coords.ndim != 2 or self.coords.shape[1] != 3:
            raise ValueError(
                f"coords 必须是 N×3 数组，当前形状 {self.coords.shape}"
            )

    @property
    def num_atoms(self) -> int:
        return len(self.coords)

    def atom_position(self, index: int) -> tuple[float, float, float]:
        """取第 index 个原子的坐标。"""
        x, y, z = self.coords[index]
        return float(x), float(y), float(z)
