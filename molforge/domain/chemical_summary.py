"""Honest, testable chemical summary helpers for the main window.

The functions in this module distinguish explicit document metadata from
calculation defaults.  Geometric shape is not presented as a formal point
group determination.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_MULTIPLICITY_NAMES = {
    1: "Singlet",
    2: "Doublet",
    3: "Triplet",
    4: "Quartet",
    5: "Quintet",
    6: "Sextet",
}


@dataclass(frozen=True)
class SpinState:
    multiplicity: int
    label: str
    explicit: bool
    total_electrons: int


@dataclass(frozen=True)
class GeometryShape:
    kind: str
    label: str
    thickness_rms: float | None
    point_group: str = "未计算"


def resolve_spin_state(document) -> SpinState:
    """Return explicit spin metadata or a clearly labelled calculation default.

    Electron parity cannot establish the actual electronic state.  In
    particular, an even-electron molecule must not be asserted to be a singlet
    unless the document explicitly says so.
    """
    total_charge = 0
    total_electrons = 0
    for aid in document.topology.atom_ids:
        atom = document.topology.get_atom(aid)
        charge = int(getattr(atom, "formal_charge", 0))
        total_charge += charge
        total_electrons += int(atom.atomic_num) - charge

    raw = None
    if "multiplicity" in document.properties:
        raw = document.properties["multiplicity"]
    elif "spin_multiplicity" in document.properties:
        raw = document.properties["spin_multiplicity"]

    if raw is not None:
        try:
            multiplicity = int(raw)
            if multiplicity < 1:
                raise ValueError
        except (TypeError, ValueError):
            default = 2 if total_electrons % 2 else 1
            return SpinState(default, "多重度无效 · 请检查文档属性", False, total_electrons)
        label = _MULTIPLICITY_NAMES.get(multiplicity, f"Mult={multiplicity}")
        return SpinState(multiplicity, label, True, total_electrons)

    default = 2 if total_electrons % 2 else 1
    default_name = _MULTIPLICITY_NAMES[default]
    return SpinState(default, f"未指定（默认 {default_name}）", False, total_electrons)


def analyze_geometry_shape(coordinates, tolerance: float = 0.12) -> GeometryShape:
    """Classify linear/planar/non-planar geometry with rigid-motion-invariant SVD.

    This deliberately does not return C1/Cs or any other formal point group.
    """
    coords = np.asarray(coordinates, dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1:] != (3,):
        return GeometryShape("invalid", "坐标无效", None)
    n = len(coords)
    if n == 0:
        return GeometryShape("empty", "无坐标", None)
    if n == 1:
        return GeometryShape("point", "单原子", 0.0)
    if not np.all(np.isfinite(coords)):
        return GeometryShape("invalid", "坐标含非有限值", None)
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be a positive finite value")

    centered = coords - coords.mean(axis=0)
    if float(np.max(np.linalg.norm(centered, axis=1))) < 1e-12:
        return GeometryShape("coincident", "原子重合", 0.0)

    singular_values = np.linalg.svd(centered, compute_uv=False)
    scale = float(np.sqrt(n))
    normalized = singular_values / scale
    thickness = float(normalized[-1])
    if n == 2 or (len(normalized) >= 2 and float(normalized[1]) < tolerance):
        return GeometryShape("linear", "线性几何（非点群判定）", thickness)
    if thickness < tolerance:
        return GeometryShape("planar", "近平面几何（非点群判定）", thickness)
    return GeometryShape("nonplanar", "非平面几何（非点群判定）", thickness)


def count_non_ring_single_bonds(topology) -> int:
    """Count MolForge's custom flexible single-bond metric.

    Definition: non-aromatic order-1 heavy-atom bonds outside rings for which
    both endpoints have at least one additional neighbour.  This is not
    RDKit's strict rotatable-bond descriptor (which also handles amides and
    other chemical restrictions).
    """
    count = 0
    for bid in topology.bond_ids:
        bond = topology.get_bond(bid)
        if bond.order != 1 or bond.aromatic or topology.is_bond_in_ring(bid):
            continue
        begin = topology.get_atom(bond.begin)
        end = topology.get_atom(bond.end)
        if begin.atomic_num <= 1 or end.atomic_num <= 1:
            continue
        if len(topology._adjacency.get(bond.begin, ())) > 1 and len(topology._adjacency.get(bond.end, ())) > 1:
            count += 1
    return count
