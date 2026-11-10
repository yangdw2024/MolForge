"""
rendering/contracts.py - 渲染器抽象接口（支持逐原子/逐键独立大小与颜色控制，兼容 bond_scales / bond_widths）
==============================================================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

import numpy as np

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId


class RepresentationMode(Enum):
    """分子表示模式。"""
    BALL_AND_STICK = "ball_stick"   # 球棍模型
    CPK = "cpk"                     # CPK 大球
    LINE = "line"                   # 线框
    SURFACE = "surface"             # 分子表面
    CARTOON = "cartoon"             # 卡通/飘带（蛋白质）
    SPACE_FILL = "space_fill"       # 空间填充


@dataclass
class RenderSnapshot:
    """
    渲染快照：从 domain 提取的只读数据，传给渲染器。
    同时支持 atom_scales / atom_colors 与 bond_scales / bond_widths / bond_colors。
    """
    atom_ids: list[AtomId]
    atomic_numbers: np.ndarray            # shape (N,)
    bonds: list[tuple[int, int, int]]     # (begin_idx, end_idx, order)
    coordinates: np.ndarray               # shape (N, 3)，单位 Å

    mode: RepresentationMode = RepresentationMode.BALL_AND_STICK

    selected_atoms: set[AtomId] | None = None
    selected_bonds: set[BondId] | None = None
    bond_ids: list[BondId] | None = None
    measure_chain: list[AtomId] | tuple[AtomId, ...] | None = None

    atom_scales: dict[Any, float] | list[float] | np.ndarray | None = None
    atom_colors: dict[Any, tuple[float, float, float]] | None = None

    atom_opacities: list[float] | None = None
    atom_glows: dict[int, tuple[float, float, float, float]] | None = None

    bond_scales: dict[Any, float] | list[float] | np.ndarray | None = None
    bond_widths: dict[Any, float] | list[float] | np.ndarray | None = None
    bond_colors: dict[Any, tuple[float, float, float]] | None = None

    show_hydrogens: bool = True
    show_bonds: bool = True
    show_labels: bool = False
    show_symbols: bool = False
    show_axes: bool = True
    color_scheme: str = "Default Scheme"

    def __post_init__(self) -> None:
        if self.bond_scales is None and self.bond_widths is not None:
            self.bond_scales = self.bond_widths
        elif self.bond_widths is None and self.bond_scales is not None:
            self.bond_widths = self.bond_scales

    @property
    def num_atoms(self) -> int:
        return len(self.atom_ids)


class Renderer3D(ABC):
    """3D 渲染器抽象基类。"""

    @abstractmethod
    def attach(self, widget: Any) -> None:
        ...

    @abstractmethod
    def set_snapshot(self, snapshot: RenderSnapshot) -> None:
        ...

    @abstractmethod
    def update_coordinates(self, coordinates: np.ndarray) -> None:
        ...

    @abstractmethod
    def set_mode(self, mode: RepresentationMode) -> None:
        ...

    @abstractmethod
    def set_selection(
        self,
        selected: set[AtomId],
        selected_bonds: set[BondId] | None = None,
        measure_chain: Sequence[AtomId] | None = None,
    ) -> None:
        ...

    @abstractmethod
    def reset_camera(self) -> None:
        ...

    @abstractmethod
    def export_image(self, path: str, width: int = 1920, height: int = 1080) -> None:
        ...

    @abstractmethod
    def render(self) -> None:
        ...

    def set_material_preset(self, preset_name: str) -> None:
        pass
