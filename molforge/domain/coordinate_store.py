"""
domain/coordinate_store.py - 坐标存储
======================================
管理分子的 3D 坐标帧。
小分子只存一个当前帧；大分子/轨迹可以有多帧。

设计原则：
  - 坐标是 float32（渲染精度足够），单位 Å
  - 帧之间拓扑不变，只换坐标
  - 支持增量追加、按索引删除/插入、单原子坐标更新（用于 3D 拖拽与 Undo/Redo）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass
class Frame:
    """单个坐标帧（一组原子的 3D 坐标）。"""
    index: int                       # 帧索引
    coords: np.ndarray               # shape (N, 3)，单位 Å
    energy: float | None = None      # 该帧能量（如有）
    source: str = "unknown"          # 来源说明

    def __post_init__(self):
        if not isinstance(self.coords, np.ndarray):
            self.coords = np.array(self.coords, dtype=np.float32)
        else:
            self.coords = self.coords.astype(np.float32, copy=False)
        if self.coords.ndim != 2 or self.coords.shape[1] != 3:
            raise ValueError(f"coords 必须是 (N, 3) 数组，当前 {self.coords.shape}")


class CoordinateStore:
    """
    坐标存储：管理一组原子的多个坐标帧。
    """

    def __init__(self, n_atoms: int) -> None:
        self.n_atoms = n_atoms
        self._frames: list[Frame] = []
        self._current_index: int = -1

    def add_frame(self, coords: np.ndarray, energy: float | None = None,
                  source: str = "unknown") -> int:
        """添加一帧，返回帧索引。"""
        coords_arr = np.asarray(coords, dtype=np.float32)
        if coords_arr.ndim == 1 and coords_arr.size == 0 and self.n_atoms == 0:
            coords_arr = np.zeros((0, 3), dtype=np.float32)
        if coords_arr.shape != (self.n_atoms, 3):
            raise ValueError(
                f"坐标形状不匹配：期望 ({self.n_atoms}, 3)，得到 {coords_arr.shape}"
            )
        frame = Frame(
            index=len(self._frames),
            coords=coords_arr.copy(),
            energy=energy,
            source=source,
        )
        self._frames.append(frame)
        if self._current_index < 0:
            self._current_index = 0
        return frame.index

    @property
    def num_frames(self) -> int:
        return len(self._frames)

    @property
    def current(self) -> Frame | None:
        """当前帧。"""
        if self._current_index < 0 or not self._frames:
            return None
        return self._frames[self._current_index]

    @property
    def current_index(self) -> int:
        return self._current_index

    @current_index.setter
    def current_index(self, idx: int) -> None:
        if not 0 <= idx < len(self._frames):
            raise IndexError(f"帧索引越界: {idx}，共 {len(self._frames)} 帧")
        self._current_index = idx

    def get_frame(self, idx: int) -> Frame:
        return self._frames[idx]

    def __iter__(self) -> Iterator[Frame]:
        return iter(self._frames)

    def update_current_coords(self, coords: np.ndarray) -> None:
        """更新当前帧的坐标（原地修改，不新增帧）。"""
        coords_arr = np.asarray(coords, dtype=np.float32)
        if self.current is None:
            self.n_atoms = coords_arr.shape[0]
            self.add_frame(coords_arr, source="update")
            return
        if coords_arr.shape != (self.n_atoms, 3):
            self.n_atoms = coords_arr.shape[0]
        self.current.coords = coords_arr.copy()

    def set_atom_coord(self, index: int, coord: np.ndarray | tuple[float, float, float]) -> None:
        """更新当前帧中单个原子的 3D 坐标。"""
        if self.current is None:
            return
        if 0 <= index < self.current.coords.shape[0]:
            self.current.coords[index] = np.asarray(coord, dtype=np.float32)

    def append_atoms(self, new_coords: np.ndarray) -> None:
        """
        拓扑新增原子后，为所有已有帧追加这些原子的坐标。
        若当前尚无帧，则直接创建第一帧。
        """
        new_coords = np.asarray(new_coords, dtype=np.float32)
        if new_coords.ndim == 1 and new_coords.size == 3:
            new_coords = new_coords.reshape(1, 3)
        if new_coords.ndim != 2 or new_coords.shape[1] != 3:
            raise ValueError(f"new_coords 须为 (k,3)，得到 {new_coords.shape}")
        k = new_coords.shape[0]
        if not self._frames:
            self.n_atoms = k
            self.add_frame(new_coords, source="append")
            return
        for fr in self._frames:
            fr.coords = np.vstack([fr.coords, new_coords]).astype(np.float32)
        self.n_atoms += k

    def remove_trailing_atoms(self, k: int) -> None:
        """从末尾移除 k 个原子的坐标（与 append_atoms 配对，用于撤销）。"""
        if k <= 0 or not self._frames:
            return
        for fr in self._frames:
            fr.coords = fr.coords[:-k].astype(np.float32)
        self.n_atoms = max(0, self.n_atoms - k)

    def remove_atom_at(self, index: int) -> np.ndarray | None:
        """按拓扑顺序索引移除单个原子的坐标，返回被移除原子在当前帧的坐标备份。"""
        if not self._frames or not (0 <= index < self.n_atoms):
            return None
        backup = None
        if self.current is not None and index < len(self.current.coords):
            backup = self.current.coords[index].copy()
        for fr in self._frames:
            if index < len(fr.coords):
                fr.coords = np.delete(fr.coords, index, axis=0).astype(np.float32)
        self.n_atoms = max(0, self.n_atoms - 1)
        return backup

    def insert_atom_at(self, index: int, coord: np.ndarray) -> None:
        """在指定索引处插入单个原子的 3D 坐标（用于撤销删除原子）。"""
        c = np.asarray(coord, dtype=np.float32).reshape(1, 3)
        if not self._frames:
            self.n_atoms = 1
            self.add_frame(c, source="restore")
            return
        idx = max(0, min(index, self.n_atoms))
        for fr in self._frames:
            fr.coords = np.insert(fr.coords, idx, c, axis=0).astype(np.float32)
        self.n_atoms += 1
