"""
rendering/orbitals.py - 分子轨道等值面渲染
=============================================
基于 Cube 文件渲染分子轨道（HOMO/LUMO）和电子密度等值面。

特性：
  - 识别 Cube 网格原点/轴/体素维度
  - 等值面提取和相位区分（正/负波函数）
  - 渲染透明体
  - 联动 geometry_ref
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass
class CubeData:
    """Cube 文件数据。"""
    origin: np.ndarray  # (3,) 原点
    axes: np.ndarray    # (3, 3) 网格轴向量
    n_voxels: tuple[int, int, int]  # 每个轴的体素数
    data: np.ndarray    # (nx, ny, nz) 标量场
    atom_coords: np.ndarray  # (N, 3) 原子坐标
    atomic_numbers: list[int]


class CubeParser:
    """Cube 文件解析器。"""

    def parse(self, filepath: str | Path) -> CubeData:
        """
        解析 Cube 文件。

        Args:
            filepath: .cube 文件路径

        Returns:
            CubeData
        """
        filepath = Path(filepath)
        with open(filepath, "r") as f:
            lines = f.readlines()

        # 前两行是注释
        # 第三行：原子数 + 原点
        line3 = lines[2].split()
        n_atoms = int(line3[0])
        origin = np.array([float(line3[1]), float(line3[2]), float(line3[3])])

        # 接下来三行：网格轴
        axes = np.zeros((3, 3))
        n_voxels = [0, 0, 0]
        for i in range(3):
            parts = lines[3 + i].split()
            n_voxels[i] = int(parts[0])
            axes[i] = [float(parts[1]), float(parts[2]), float(parts[3])]

        # 接下来 n_atoms 行：原子信息
        atom_coords = np.zeros((n_atoms, 3))
        atomic_numbers = []
        for i in range(n_atoms):
            parts = lines[6 + i].split()
            atomic_numbers.append(int(parts[0]))
            atom_coords[i] = [float(parts[2]), float(parts[3]), float(parts[4])]

        # 剩下的是体素数据
        data_start = 6 + n_atoms
        data_values = []
        for line in lines[data_start:]:
            data_values.extend([float(x) for x in line.split()])

        data = np.array(data_values).reshape(n_voxels[0], n_voxels[1], n_voxels[2])

        return CubeData(
            origin=origin,
            axes=axes,
            n_voxels=tuple(n_voxels),
            data=data,
            atom_coords=atom_coords,
            atomic_numbers=atomic_numbers,
        )


class OrbitalRenderer:
    """
    分子轨道渲染器。

    用法：
        renderer = OrbitalRenderer()
        renderer.load_cube("homo.cube")
        renderer.set_isovalue(0.05)
        # 然后在 VTK 场景中显示
    """

    def __init__(self) -> None:
        self._cube: CubeData | None = None
        self._isovalue = 0.05
        self._positive_color = (0.2, 0.5, 1.0)  # 蓝色 = 正相位
        self._negative_color = (1.0, 0.3, 0.3)  # 红色 = 负相位
        self._opacity = 0.5

    def load_cube(self, filepath: str | Path) -> None:
        """加载 Cube 文件。"""
        parser = CubeParser()
        self._cube = parser.parse(filepath)

    def set_isovalue(self, value: float) -> None:
        """设置等值面阈值。"""
        self._isovalue = value

    def get_positive_grid(self) -> np.ndarray | None:
        """获取正相位标量场（负值设为 0）。"""
        if self._cube is None:
            return None
        return np.where(self._cube.data > 0, self._cube.data, 0)

    def get_negative_grid(self) -> np.ndarray | None:
        """获取负相位标量场（正值设为 0，取绝对值）。"""
        if self._cube is None:
            return None
        return np.where(self._cube.data < 0, -self._cube.data, 0)

    def get_bounds(self) -> tuple[float, float, float, float, float, float] | None:
        """获取网格的空间范围。"""
        if self._cube is None:
            return None
        origin = self._cube.origin
        axes = self._cube.axes
        n = self._cube.n_voxels
        end = origin + axes[0] * n[0] + axes[1] * n[1] + axes[2] * n[2]
        return (
            min(origin[0], end[0]), max(origin[0], end[0]),
            min(origin[1], end[1]), max(origin[1], end[1]),
            min(origin[2], end[2]), max(origin[2], end[2]),
        )
