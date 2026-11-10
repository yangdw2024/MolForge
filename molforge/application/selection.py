"""
application/selection.py - 有序选择服务（兼顾 set 兼容性与精确选择顺序）
========================================================================
支持：
  - selected_atoms / selected_bonds: 返回 set 副本（100% 兼容旧代码）
  - ordered_atoms / ordered_bonds: 返回按用户点击先后顺序排列的 tuple（用于键角 i-j-k 与二面角 i-j-k-l）
  - origin + revision 防循环通知机制
"""

from __future__ import annotations

from typing import Callable, Iterable

from ..domain.ids import AtomId, BondId


class SelectionService:
    """选择服务：同时维护选中集合与点击先后顺序。"""

    def __init__(self) -> None:
        self._selected_atoms: set[AtomId] = set()
        self._ordered_atoms: list[AtomId] = []
        self._selected_bonds: set[BondId] = set()
        self._ordered_bonds: list[BondId] = []
        self._listeners: list[Callable[[str], None]] = []
        self._last_origin: str | None = None
        self._revision: int = 0

    @property
    def selected_atoms(self) -> set[AtomId]:
        return self._selected_atoms.copy()

    @property
    def ordered_atoms(self) -> tuple[AtomId, ...]:
        return tuple(self._ordered_atoms)

    @property
    def selected_bonds(self) -> set[BondId]:
        return self._selected_bonds.copy()

    @property
    def ordered_bonds(self) -> tuple[BondId, ...]:
        return tuple(self._ordered_bonds)

    @property
    def is_empty(self) -> bool:
        return not self._selected_atoms and not self._selected_bonds

    @property
    def count(self) -> int:
        return len(self._selected_atoms) + len(self._selected_bonds)

    @property
    def last_origin(self) -> str | None:
        return self._last_origin

    @property
    def revision(self) -> int:
        return self._revision

    def select_atom(self, aid: AtomId, add: bool = False, origin: str = "command") -> None:
        if not add:
            self._selected_atoms.clear()
            self._ordered_atoms.clear()
            self._selected_bonds.clear()
            self._ordered_bonds.clear()
        if aid not in self._selected_atoms:
            self._selected_atoms.add(aid)
            self._ordered_atoms.append(aid)
        self._notify_change(origin)

    def select_atoms_ordered(self, aids: Iterable[AtomId], origin: str = "command") -> None:
        self._selected_atoms.clear()
        self._ordered_atoms.clear()
        self._selected_bonds.clear()
        self._ordered_bonds.clear()
        for aid in aids:
            if aid not in self._selected_atoms:
                self._selected_atoms.add(aid)
                self._ordered_atoms.append(aid)
        self._notify_change(origin)

    def select_atoms(self, aids: Iterable[AtomId], origin: str = "command") -> None:
        """Replace a bulk selection with one notification and deterministic ID order."""
        self.select_atoms_ordered(sorted(set(aids), key=lambda aid: aid.value), origin=origin)

    def toggle_atom(self, aid: AtomId, origin: str = "command") -> None:
        if aid in self._selected_atoms:
            self._selected_atoms.remove(aid)
            if aid in self._ordered_atoms:
                self._ordered_atoms.remove(aid)
        else:
            self._selected_atoms.add(aid)
            self._ordered_atoms.append(aid)
        self._notify_change(origin)

    def deselect_atom(self, aid: AtomId, origin: str = "command") -> None:
        if aid in self._selected_atoms:
            self._selected_atoms.remove(aid)
            if aid in self._ordered_atoms:
                self._ordered_atoms.remove(aid)
            self._notify_change(origin)

    def select_bond(self, bid: BondId, add: bool = False, origin: str = "command") -> None:
        if not add:
            self._selected_atoms.clear()
            self._ordered_atoms.clear()
            self._selected_bonds.clear()
            self._ordered_bonds.clear()
        if bid not in self._selected_bonds:
            self._selected_bonds.add(bid)
            self._ordered_bonds.append(bid)
        self._notify_change(origin)

    def toggle_bond(self, bid: BondId, origin: str = "command") -> None:
        if bid in self._selected_bonds:
            self._selected_bonds.remove(bid)
            if bid in self._ordered_bonds:
                self._ordered_bonds.remove(bid)
        else:
            self._selected_bonds.add(bid)
            self._ordered_bonds.append(bid)
        self._notify_change(origin)

    def clear(self, origin: str = "command") -> None:
        self._clear_internal(origin)

    def _clear_internal(self, origin: str) -> None:
        self._selected_atoms.clear()
        self._ordered_atoms.clear()
        self._selected_bonds.clear()
        self._ordered_bonds.clear()
        self._notify_change(origin)

    def cleanup_after_delete(self, deleted_atoms: set[AtomId], deleted_bonds: set[BondId]) -> None:
        changed = False
        for aid in deleted_atoms:
            if aid in self._selected_atoms:
                self._selected_atoms.remove(aid)
                if aid in self._ordered_atoms:
                    self._ordered_atoms.remove(aid)
                changed = True
        for bid in deleted_bonds:
            if bid in self._selected_bonds:
                self._selected_bonds.remove(bid)
                if bid in self._ordered_bonds:
                    self._ordered_bonds.remove(bid)
                changed = True
        if changed:
            self._notify_change("cleanup")

    def add_listener(self, listener: Callable[[str], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_change(self, origin: str) -> None:
        self._last_origin = origin
        self._revision += 1
        for listener in list(self._listeners):
            listener(origin)
