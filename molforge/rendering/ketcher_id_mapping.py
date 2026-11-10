"""
rendering/ketcher_id_mapping.py - Ketcher 原子 ID 映射
========================================================
将 Ketcher 的原子索引映射到内部稳定的 AtomId。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from ..domain.ids import AtomId


@dataclass
class IdMapping:
    """ID 映射表。"""
    # ketcher_index -> atom_id
    index_to_atom: dict[int, AtomId] = field(default_factory=dict)
    # atom_id -> ketcher_index
    atom_to_index: dict[AtomId, int] = field(default_factory=dict)

    def add(self, index: int, atom_id: AtomId):
        """添加映射。"""
        self.index_to_atom[index] = atom_id
        self.atom_to_index[atom_id] = index

    def remove_by_index(self, index: int):
        """按索引删除映射。"""
        if index in self.index_to_atom:
            atom_id = self.index_to_atom[index]
            del self.index_to_atom[index]
            if atom_id in self.atom_to_index:
                del self.atom_to_index[atom_id]

    def remove_by_atom(self, atom_id: AtomId):
        """按原子 ID 删除映射。"""
        if atom_id in self.atom_to_index:
            index = self.atom_to_index[atom_id]
            del self.atom_to_index[atom_id]
            if index in self.index_to_atom:
                del self.index_to_atom[index]

    def get_atom_id(self, index: int) -> AtomId | None:
        """通过索引获取原子 ID。"""
        return self.index_to_atom.get(index)

    def get_index(self, atom_id: AtomId) -> int | None:
        """通过原子 ID 获取索引。"""
        return self.atom_to_index.get(atom_id)

    def clear(self):
        """清空映射。"""
        self.index_to_atom.clear()
        self.atom_to_index.clear()


class AtomIdMapper:
    """
    原子 ID 映射器。

    负责将 Ketcher 编辑器中的原子索引映射到内部稳定的 AtomId。
    支持局部增删和重新加载时的重映射。
    """

    def __init__(self):
        self.mapping = IdMapping()
        self._next_index: int = 0

    def rebuild(self, atoms: list[Any]):
        """
        重建映射表。

        Args:
            atoms: 原子列表，每个原子有 atom_id 属性
        """
        self.mapping.clear()
        for i, atom in enumerate(atoms):
            atom_id = getattr(atom, 'atom_id', None)
            if atom_id is None:
                # 如果没有 atom_id，创建一个
                atom_id = AtomId()
            self.mapping.add(i, atom_id)
        self._next_index = len(atoms)

    def add_atom(self, atom_id: AtomId) -> int:
        """添加新原子，返回新索引。"""
        index = self._next_index
        self._next_index += 1
        self.mapping.add(index, atom_id)
        return index

    def remove_atom_by_index(self, index: int):
        """按索引删除原子。"""
        self.mapping.remove_by_index(index)

    def remove_atom_by_id(self, atom_id: AtomId):
        """按原子 ID 删除原子。"""
        self.mapping.remove_by_atom(atom_id)

    def get_atom_id(self, index: int) -> AtomId | None:
        """通过索引获取原子 ID。"""
        return self.mapping.get_atom_id(index)

    def get_index(self, atom_id: AtomId) -> int | None:
        """通过原子 ID 获取索引。"""
        return self.mapping.get_index(atom_id)

    @property
    def num_atoms(self) -> int:
        """原子数量。"""
        return len(self.mapping.index_to_atom)
