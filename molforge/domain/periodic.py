"""Crystallographic unit-cell and periodic-boundary helpers.

Coordinates use angstrom, angles use degrees, and cell vectors are rows of
``cell.matrix``.  The implementation supports orthorhombic and triclinic
cells without changing the non-periodic defaults of existing documents.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math

import numpy as np


@dataclass(frozen=True)
class UnitCell:
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    space_group: str = ""

    def __post_init__(self) -> None:
        lengths = (self.a, self.b, self.c)
        angles = (self.alpha, self.beta, self.gamma)
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in lengths):
            raise ValueError("晶胞边长必须为正的有限值")
        if any(not math.isfinite(float(v)) or not 0 < float(v) < 180 for v in angles):
            raise ValueError("晶胞角度必须位于 0–180°")
        if abs(float(np.linalg.det(self.matrix))) < 1e-8:
            raise ValueError("晶胞退化，体积为零")

    @property
    def matrix(self) -> np.ndarray:
        ar, br, gr = math.radians(self.alpha), math.radians(self.beta), math.radians(self.gamma)
        sg = math.sin(gr)
        if abs(sg) < 1e-12:
            raise ValueError("gamma 导致晶胞退化")
        av = np.array([self.a, 0.0, 0.0], dtype=np.float64)
        bv = np.array([self.b * math.cos(gr), self.b * sg, 0.0], dtype=np.float64)
        cx = self.c * math.cos(br)
        cy = self.c * (math.cos(ar) - math.cos(br) * math.cos(gr)) / sg
        cz2 = self.c * self.c - cx * cx - cy * cy
        if cz2 <= 1e-12:
            raise ValueError("晶胞角度无法构成有效三维盒子")
        cv = np.array([cx, cy, math.sqrt(cz2)], dtype=np.float64)
        return np.vstack((av, bv, cv))

    @property
    def volume(self) -> float:
        return abs(float(np.linalg.det(self.matrix)))

    def to_dict(self) -> dict:
        return {
            "a": float(self.a), "b": float(self.b), "c": float(self.c),
            "alpha": float(self.alpha), "beta": float(self.beta), "gamma": float(self.gamma),
            "space_group": self.space_group,
        }

    def to_cryst1(self) -> str:
        return (
            f"CRYST1{self.a:9.3f}{self.b:9.3f}{self.c:9.3f}"
            f"{self.alpha:7.2f}{self.beta:7.2f}{self.gamma:7.2f} "
            f"{self.space_group[:11]:<11s}"
        )

    def to_fractional(self, cartesian) -> np.ndarray:
        values = np.asarray(cartesian, dtype=np.float64)
        return values @ np.linalg.inv(self.matrix)

    def to_cartesian(self, fractional) -> np.ndarray:
        values = np.asarray(fractional, dtype=np.float64)
        return values @ self.matrix


def cell_from_properties(properties: dict | None) -> UnitCell | None:
    if not properties:
        return None
    raw = properties.get("cryst1")
    if not isinstance(raw, dict):
        return None
    try:
        return UnitCell(
            float(raw["a"]), float(raw["b"]), float(raw["c"]),
            float(raw["alpha"]), float(raw["beta"]), float(raw["gamma"]),
            str(raw.get("space_group", properties.get("space_group", ""))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"文档 CRYST1 晶胞无效: {exc}") from exc


def cell_from_document(document) -> UnitCell | None:
    return cell_from_properties(getattr(document, "properties", None))


def minimum_image_delta(delta, cell: UnitCell) -> np.ndarray:
    """Return a short periodic displacement for an orthorhombic/triclinic cell.

    Fractional wrapping is followed by a 27-image local search, avoiding the
    axis-aligned approximation and handling skewed cells more reliably.
    """
    vector = np.asarray(delta, dtype=np.float64)
    fractional = cell.to_fractional(vector)
    centered = fractional - np.round(fractional)
    best = centered
    best_norm = float("inf")
    for shift in product((-1.0, 0.0, 1.0), repeat=3):
        candidate = centered + np.asarray(shift)
        norm = float(np.linalg.norm(cell.to_cartesian(candidate)))
        if norm < best_norm:
            best = candidate
            best_norm = norm
    return cell.to_cartesian(best)
