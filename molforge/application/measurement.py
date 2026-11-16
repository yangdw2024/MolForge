"""
application/measurement.py - 几何测量三件套
=============================================
距离、键角、二面角测量。

单位约定：
  - 距离：Å（埃）
  - 角度：度
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from ..domain.ids import AtomId


@dataclass(frozen=True)
class Measurement:
    """测量结果。"""
    type: Literal["distance", "angle", "dihedral"]
    atoms: tuple[AtomId, ...]
    value: float  # 距离（Å）或角度（度）
    valid: bool = True  # 几何退化时为 False
    diagnostic: str = ""  # 退化时的说明


def distance(coords: np.ndarray, i: int, j: int, cell=None) -> float:
    """计算原子距离（Å）；提供 ``UnitCell`` 时采用最小镜像约定。"""
    diff = coords[i] - coords[j]
    if cell is not None:
        from ..domain.periodic import minimum_image_delta
        diff = minimum_image_delta(diff, cell)
    return float(np.linalg.norm(diff))


def angle(coords: np.ndarray, i: int, j: int, k: int, cell=None) -> tuple[float, bool, str]:
    """计算键角 i-j-k（度），可选采用周期最小镜像向量。"""
    v1 = coords[i] - coords[j]
    v2 = coords[k] - coords[j]
    if cell is not None:
        from ..domain.periodic import minimum_image_delta
        v1 = minimum_image_delta(v1, cell)
        v2 = minimum_image_delta(v2, cell)

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < 1e-6 or norm2 < 1e-6:
        return 0.0, False, "原子重合，角度无定义"

    cos_theta = np.dot(v1, v2) / (norm1 * norm2)
    theta_rad = math.acos(np.clip(cos_theta, -1.0, 1.0))
    return math.degrees(theta_rad), True, ""


def dihedral(coords: np.ndarray, i: int, j: int, k: int, l: int, cell=None) -> tuple[float, bool, str]:
    """计算有向二面角 i-j-k-l（度），可选逐链段展开周期坐标。"""
    b1 = coords[j] - coords[i]
    b2 = coords[k] - coords[j]
    b3 = coords[l] - coords[k]
    if cell is not None:
        from ..domain.periodic import minimum_image_delta
        b1 = minimum_image_delta(b1, cell)
        b2 = minimum_image_delta(b2, cell)
        b3 = minimum_image_delta(b3, cell)

    norm_b2 = np.linalg.norm(b2)
    if norm_b2 < 1e-6:
        return 0.0, False, "中间原子重合，二面角无定义"

    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)
    norm_n1 = np.linalg.norm(n1)
    norm_n2 = np.linalg.norm(n2)
    if norm_n1 < 1e-6 or norm_n2 < 1e-6:
        return 0.0, False, "共线原子，二面角无定义"

    n1_norm = n1 / norm_n1
    n2_norm = n2 / norm_n2
    u2 = b2 / norm_b2
    x = float(np.dot(n1_norm, n2_norm))
    y = float(np.dot(np.cross(n1_norm, n2_norm), u2))
    return math.degrees(math.atan2(y, x)), True, ""


class MeasurementService:
    """
    测量服务：管理测量对象。

    用法：
        service = MeasurementService()
        m = service.measure_distance(doc, aid1, aid2)
    """

    def __init__(self) -> None:
        self._measurements: list[Measurement] = []

    def measure_distance(self, coords: np.ndarray,
                         atom_ids: tuple[AtomId, AtomId],
                         idx_map: dict[AtomId, int], cell=None) -> Measurement:
        """测量距离，可选传入晶胞采用最小镜像。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        d = distance(coords, i, j, cell)
        m = Measurement(
            type="distance",
            atoms=atom_ids,
            value=d,
            valid=True,
        )
        self._measurements.append(m)
        return m

    def measure_angle(self, coords: np.ndarray,
                      atom_ids: tuple[AtomId, AtomId, AtomId],
                      idx_map: dict[AtomId, int], cell=None) -> Measurement:
        """测量键角，可选采用周期最小镜像。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        k = idx_map[atom_ids[2]]
        value, valid, diagnostic = angle(coords, i, j, k, cell)
        m = Measurement(
            type="angle",
            atoms=atom_ids,
            value=value,
            valid=valid,
            diagnostic=diagnostic,
        )
        self._measurements.append(m)
        return m

    def measure_dihedral(self, coords: np.ndarray,
                         atom_ids: tuple[AtomId, AtomId, AtomId, AtomId],
                         idx_map: dict[AtomId, int], cell=None) -> Measurement:
        """测量二面角，可选逐链段展开周期坐标。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        k = idx_map[atom_ids[2]]
        l = idx_map[atom_ids[3]]
        value, valid, diagnostic = dihedral(coords, i, j, k, l, cell)
        m = Measurement(
            type="dihedral",
            atoms=atom_ids,
            value=value,
            valid=valid,
            diagnostic=diagnostic,
        )
        self._measurements.append(m)
        return m

    def cleanup_after_delete(self, deleted_atoms: set[AtomId]) -> None:
        """删除原子后清理测量（使用 dataclasses.replace 替换冻结记录，避免 FrozenInstanceError）。"""
        updated: list[Measurement] = []
        for m in self._measurements:
            if any(aid in deleted_atoms for aid in m.atoms):
                updated.append(replace(m, valid=False, diagnostic="原子已删除，测量无效"))
            else:
                updated.append(m)
        self._measurements = updated

    @property
    def measurements(self) -> list[Measurement]:
        return self._measurements.copy()
