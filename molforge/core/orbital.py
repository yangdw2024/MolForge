"""
orbital.py - 分子轨道
======================
一个 Orbital 记录一个分子轨道（MO）的信息：
- 轨道编号（1, 2, 3...）
- 轨道能量（eV）
- 占据数（2 = 占据，0 = 空）
- 对应的 cube 文件路径（如果有，用来渲染轨道图）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Orbital:
    """单个分子轨道。"""

    index: int              # 轨道编号（从 1 开始）
    energy_ev: float        # 轨道能量（eV）
    occupation: float       # 占据数（闭壳层 = 2.0，空轨道 = 0.0）
    cube_path: Path | None = None  # 对应的 cube 文件（如果有）

    @property
    def is_occupied(self) -> bool:
        return self.occupation > 0.5

    @property
    def label(self) -> str:
        """人类可读标签，例如 'HOMO', 'LUMO', 'HOMO-1'。"""
        return f"MO {self.index}"
