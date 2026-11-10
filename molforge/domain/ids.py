"""
domain/ids.py - 稳定标识符
============================
AtomId / BondId 是文档内的稳定标识符。
编辑过程中（添加/删除原子）ID 不重复、不漂移。

注意：
  - RDKit AtomIdx、VTK vertex index、Mol* internal ID 都不是稳定 ID，
    它们只是适配器层的映射。
  - AtomId 用单调递增整数，删除后不复用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class AtomId:
    """原子稳定标识符（文档内唯一）。"""
    value: int

    def __repr__(self) -> str:
        return f"Atom#{self.value}"


@dataclass(frozen=True, order=True)
class BondId:
    """键稳定标识符（文档内唯一）。"""
    value: int

    def __repr__(self) -> str:
        return f"Bond#{self.value}"


class IdCounter:
    """单调递增 ID 计数器，删除的 ID 不复用。"""

    def __init__(self) -> None:
        self._next_atom = 0
        self._next_bond = 0

    def next_atom(self) -> AtomId:
        aid = AtomId(self._next_atom)
        self._next_atom += 1
        return aid

    def next_bond(self) -> BondId:
        bid = BondId(self._next_bond)
        self._next_bond += 1
        return bid

    def state_dict(self) -> dict:
        return {"next_atom": self._next_atom, "next_bond": self._next_bond}

    def load_state_dict(self, state: dict) -> None:
        self._next_atom = state["next_atom"]
        self._next_bond = state["next_bond"]
