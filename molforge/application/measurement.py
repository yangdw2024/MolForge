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


def distance(coords: np.ndarray, i: int, j: int) -> float:
    """
    计算两个原子之间的距离（Å）。

    Args:
        coords: (N, 3) 坐标数组
        i: 第一个原子索引
        j: 第二个原子索引

    Returns:
        距离（Å）
    """
    diff = coords[i] - coords[j]
    return float(np.linalg.norm(diff))


def angle(coords: np.ndarray, i: int, j: int, k: int) -> tuple[float, bool, str]:
    """
    计算键角（i-j-k）。

    Args:
        coords: (N, 3) 坐标数组
        i: 第一个原子索引
        j: 中间原子索引
        k: 第三个原子索引

    Returns:
        (角度，是否有效，诊断信息)
    """
    v1 = coords[i] - coords[j]
    v2 = coords[k] - coords[j]

    # 检查退化
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < 1e-6 or norm2 < 1e-6:
        return 0.0, False, "原子重合，角度无定义"

    # dot 积
    cos_theta = np.dot(v1, v2) / (norm1 * norm2)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)

    theta_rad = math.acos(cos_theta)
    theta_deg = math.degrees(theta_rad)

    return theta_deg, True, ""


def dihedral(coords: np.ndarray, i: int, j: int, k: int, l: int) -> tuple[float, bool, str]:
    """
    计算二面角（i-j-k-l）。

    Args:
        coords: (N, 3) 坐标数组
        i: 第一个原子索引
        j: 第二个原子索引
        k: 第三个原子索引
        l: 第四个原子索引

    Returns:
        (角度，是否有效，诊断信息)
    """
    # 向量 (按照标准 IUPAC 链式有向定义：b1: i->j, b2: j->k, b3: k->l，严格对齐 Gaussian / Chem3D / Multiwfn)
    b1 = coords[j] - coords[i]
    b2 = coords[k] - coords[j]
    b3 = coords[l] - coords[k]

    # 检查退化
    norm_b2 = np.linalg.norm(b2)
    if norm_b2 < 1e-6:
        return 0.0, False, "中间原子重合，二面角无定义"

    # 法向量
    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)

    norm_n1 = np.linalg.norm(n1)
    norm_n2 = np.linalg.norm(n2)

    if norm_n1 < 1e-6 or norm_n2 < 1e-6:
        return 0.0, False, "共线原子，二面角无定义"

    n1_norm = n1 / norm_n1
    n2_norm = n2 / norm_n2

    # 二面角
    m1 = np.cross(n1_norm, b2 / norm_b2)
    x = np.dot(n1_norm, n2_norm)
    y = np.dot(m1, n2_norm)

    angle_rad = math.atan2(y, x)
    angle_deg = math.degrees(angle_rad)

    return angle_deg, True, ""


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
                         idx_map: dict[AtomId, int]) -> Measurement:
        """测量距离。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        d = distance(coords, i, j)
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
                      idx_map: dict[AtomId, int]) -> Measurement:
        """测量键角。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        k = idx_map[atom_ids[2]]
        value, valid, diagnostic = angle(coords, i, j, k)
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
                         idx_map: dict[AtomId, int]) -> Measurement:
        """测量二面角。"""
        i = idx_map[atom_ids[0]]
        j = idx_map[atom_ids[1]]
        k = idx_map[atom_ids[2]]
        l = idx_map[atom_ids[3]]
        value, valid, diagnostic = dihedral(coords, i, j, k, l)
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
