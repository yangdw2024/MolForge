"""
domain/topology.py - 分子拓扑（带稳定双向 AtomId <-> 数组索引映射）
===================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from .ids import AtomId, BondId, IdCounter


@dataclass
class Atom:
    """一个原子的静态属性（不含坐标）。"""
    id: AtomId
    atomic_num: int           # 原子序数（6=C, 7=N...）
    formal_charge: int = 0    # 形式电荷
    implicit_h: int = 0       # 隐式氢数
    aromatic: bool = False    # 是否芳香原子
    color: tuple | None = None  # 自定义颜色 (r,g,b) 0-1；None 用默认 CPK
    scale: float = 1.0        # 单原子显示缩放
    properties: dict = field(default_factory=dict)

    @property
    def element(self) -> int:
        return self.atomic_num

    @element.setter
    def element(self, val: int) -> None:
        self.atomic_num = int(val)

    @property
    def symbol(self) -> str:
        from .elements import get_element
        el = get_element(self.atomic_num)
        return el.symbol if el else "X"


@dataclass
class Bond:
    """一个键的静态属性。"""
    id: BondId
    begin: AtomId
    end: AtomId
    order: int = 1            # 键级：1=单, 2=双, 3=三, 4=芳香
    aromatic: bool = False
    color: tuple | None = None
    width_scale: float = 1.0
    properties: dict = field(default_factory=dict)

    def other_end(self, aid: AtomId) -> AtomId | None:
        if self.begin == aid:
            return self.end
        if self.end == aid:
            return self.begin
        return None


class Topology:
    """
    分子拓扑：原子 + 键的连接关系，维护稳定的双向 ID <-> 索引映射。
    """

    def __init__(self) -> None:
        self._atoms: dict[AtomId, Atom] = {}
        self._bonds: dict[BondId, Bond] = {}
        self._adjacency: dict[AtomId, list[BondId]] = {}
        self._id_counter = IdCounter()

    # ---------- 双向映射表（Phase 1 核心要求） ----------

    def atom_index_map(self) -> tuple[list[AtomId], dict[AtomId, int]]:
        """返回 (idx_to_atom_id 列表, atom_id_to_idx 字典)。"""
        idx_to_id = list(self._atoms.keys())
        id_to_idx = {aid: i for i, aid in enumerate(idx_to_id)}
        return idx_to_id, id_to_idx

    def bond_index_map(self) -> tuple[list[BondId], dict[BondId, int]]:
        """返回 (idx_to_bond_id 列表, bond_id_to_idx 字典)。"""
        idx_to_id = list(self._bonds.keys())
        id_to_idx = {bid: i for i, bid in enumerate(idx_to_id)}
        return idx_to_id, id_to_idx

    # ---------- 原子操作 ----------

    def add_atom(
        self,
        atomic_num: int,
        formal_charge: int = 0,
        aromatic: bool = False,
        atom_id: AtomId | None = None,
    ) -> AtomId:
        """添加一个原子，返回新原子 ID。若传入 atom_id（如 redo），则复用该 ID 防止漂移。"""
        if atom_id is not None:
            aid = atom_id
            if hasattr(self._id_counter, "_next_atom") and aid.value >= self._id_counter._next_atom:
                self._id_counter._next_atom = aid.value + 1
        else:
            aid = self._id_counter.next_atom()

        atom = Atom(
            id=aid,
            atomic_num=int(atomic_num),
            formal_charge=int(formal_charge),
            aromatic=bool(aromatic),
        )
        self._atoms[aid] = atom
        if aid not in self._adjacency:
            self._adjacency[aid] = []
        return aid

    def restore_atom(self, atom: Atom, index: int | None = None) -> AtomId:
        """恢复已删除的原子（保持原有 AtomId 与在拓扑中的顺序索引）。"""
        aid = atom.id
        if hasattr(self._id_counter, "_next_atom") and aid.value >= self._id_counter._next_atom:
            self._id_counter._next_atom = aid.value + 1
        if index is None or index >= len(self._atoms):
            self._atoms[aid] = atom
        else:
            items = list(self._atoms.items())
            items.insert(max(0, index), (aid, atom))
            self._atoms = dict(items)
        if aid not in self._adjacency:
            self._adjacency[aid] = []
        return aid

    def remove_atom(self, aid: AtomId) -> None:
        """删除原子，同时删除所有关联键。"""
        if aid not in self._atoms:
            return
        bond_ids = list(self._adjacency.get(aid, []))
        for bid in bond_ids:
            self.remove_bond(bid)
        del self._atoms[aid]
        del self._adjacency[aid]

    def get_atom(self, aid: AtomId) -> Atom:
        return self._atoms[aid]

    def index_of_atom(self, aid: AtomId) -> int:
        """返回原子在当前拓扑序列中的索引（0-based）。"""
        for idx, k in enumerate(self._atoms.keys()):
            if k == aid:
                return idx
        raise KeyError(f"原子 {aid} 不存在")

    @property
    def num_atoms(self) -> int:
        return len(self._atoms)

    @property
    def atom_ids(self) -> Iterator[AtomId]:
        return iter(self._atoms.keys())

    # ---------- 键操作 ----------

    def add_bond(
        self,
        a: AtomId,
        b: AtomId,
        order: int = 1,
        aromatic: bool = False,
        bond_id: BondId | None = None,
    ) -> BondId:
        """在两个原子之间添加键。若传入 bond_id（如 redo），则复用该 ID。"""
        if a not in self._atoms or b not in self._atoms:
            raise ValueError("键的两端原子必须存在")
        if a == b:
            raise ValueError("不能在同一原子上建立自环键")
        existing = self.bond_between(a, b)
        if existing is not None:
            bond = self._bonds[existing]
            bond.order = int(order)
            bond.aromatic = bool(aromatic)
            return existing

        if bond_id is not None:
            bid = bond_id
            if hasattr(self._id_counter, "_next_bond") and bid.value >= self._id_counter._next_bond:
                self._id_counter._next_bond = bid.value + 1
        else:
            bid = self._id_counter.next_bond()

        bond = Bond(id=bid, begin=a, end=b, order=int(order), aromatic=bool(aromatic))
        self._bonds[bid] = bond
        self._adjacency[a].append(bid)
        self._adjacency[b].append(bid)
        return bid

    def restore_bond(self, bond: Bond) -> BondId:
        """恢复已删除的键（保持原有 BondId）。"""
        if bond.begin not in self._atoms or bond.end not in self._atoms:
            raise ValueError("恢复键失败：端点原子不存在")
        bid = bond.id
        if hasattr(self._id_counter, "_next_bond") and bid.value >= self._id_counter._next_bond:
            self._id_counter._next_bond = bid.value + 1
        self._bonds[bid] = bond
        if bid not in self._adjacency[bond.begin]:
            self._adjacency[bond.begin].append(bid)
        if bid not in self._adjacency[bond.end]:
            self._adjacency[bond.end].append(bid)
        return bid

    def remove_bond(self, bid: BondId) -> None:
        """删除键。"""
        if bid not in self._bonds:
            return
        bond = self._bonds[bid]
        if bond.begin in self._adjacency and bid in self._adjacency[bond.begin]:
            self._adjacency[bond.begin].remove(bid)
        if bond.end in self._adjacency and bid in self._adjacency[bond.end]:
            self._adjacency[bond.end].remove(bid)
        del self._bonds[bid]

    def get_bond(self, bid: BondId) -> Bond:
        return self._bonds[bid]

    @property
    def num_bonds(self) -> int:
        return len(self._bonds)

    @property
    def bond_ids(self) -> Iterator[BondId]:
        return iter(self._bonds.keys())

    # ---------- 查询 ----------

    def all_atom_ids(self) -> list[AtomId]:
        return list(self._atoms.keys())

    def adjacent_atoms(self, aid: AtomId) -> list[AtomId]:
        return self.neighbors_of(aid)

    def bonds_of(self, aid: AtomId) -> list[BondId]:
        """返回与指定原子相连的所有化学键 ID。"""
        return list(self._adjacency.get(aid, []))

    def neighbors_of(self, aid: AtomId) -> list[AtomId]:
        """返回与指定原子直接相连的所有原子 ID。"""
        result = []
        for bid in self._adjacency.get(aid, []):
            bond = self._bonds.get(bid)
            if bond is None:
                continue
            other = bond.end if bond.begin == aid else bond.begin
            result.append(other)
        return result

    def bond_between(self, a: AtomId, b: AtomId) -> BondId | None:
        """查找两个原子之间的键，不存在返回 None。"""
        for bid in self._adjacency.get(a, []):
            bond = self._bonds.get(bid)
            if bond is None:
                continue
            if (bond.begin == b and bond.end == a) or (bond.begin == a and bond.end == b):
                return bid
        return None

    def atom_count_array(self) -> np.ndarray:
        """返回所有原子的原子序数数组（按添加顺序）。"""
        return np.array(
            [self._atoms[aid].atomic_num for aid in self._atoms],
            dtype=np.int32,
        )
