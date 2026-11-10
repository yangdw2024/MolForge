"""
ai/observation.py - AI 观察工具
=================================
让 AI 能读取分子结构、几何和工件信息。

特性：
  - 暴露已选 AtomId/Conformer/Artifact
  - 返回单位与 stale 状态
  - 限制数据量并筛选权限
  - 不虚构数值、不自动传文件
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId
from ..application.selection import SelectionService
from ..application.invalidation import InvalidationService


@dataclass
class AtomInfo:
    """原子信息（给 AI 看的）。"""
    atom_id: str
    element: str
    atomic_num: int
    formal_charge: int
    aromatic: bool
    coordinate: tuple[float, float, float] | None = None


@dataclass
class MoleculeSummary:
    """分子摘要（给 AI 看的）。"""
    name: str
    n_atoms: int
    n_bonds: int
    has_3d: bool
    selected_atoms: list[str] = field(default_factory=list)
    stale: bool = False
    warning: str = ""


class ObservationTool:
    """
    AI 观察工具：让 AI 读取分子状态。

    用法：
        tool = ObservationTool(doc, selection, invalidation)
        summary = tool.get_molecule_summary()
        atom = tool.get_atom_info("atom_123")
    """

    def __init__(self,
                 document: MoleculeDocument,
                 selection: SelectionService,
                 invalidation: InvalidationService) -> None:
        self._doc = document
        self._selection = selection
        self._invalidation = invalidation

    def get_molecule_summary(self) -> MoleculeSummary:
        """获取分子摘要。"""
        selected = [aid.value for aid in self._selection.selected_atoms]
        warning = self._invalidation.get_warning_message()

        return MoleculeSummary(
            name=self._doc.name,
            n_atoms=self._doc.num_atoms,
            n_bonds=self._doc.num_bonds,
            has_3d=self._doc.has_3d,
            selected_atoms=selected,
            stale=bool(self._invalidation.get_stale_markers()),
            warning=warning,
        )

    def get_atom_info(self, atom_id: str) -> AtomInfo | None:
        """获取原子详细信息。"""
        from ..domain.ids import AtomId
        aid = AtomId(atom_id)

        try:
            atom = self._doc.topology.get_atom(aid)
        except KeyError:
            return None

        # 坐标
        coord = None
        if self._doc.has_3d and self._doc.coordinates.current is not None:
            # 找到原子索引
            for i, a in enumerate(self._doc.topology.atom_ids):
                if a == aid:
                    c = self._doc.coordinates.current.coords[i]
                    coord = (float(c[0]), float(c[1]), float(c[2]))
                    break

        return AtomInfo(
            atom_id=atom_id,
            element=atom.symbol if hasattr(atom, "symbol") else "?",
            atomic_num=atom.atomic_num,
            formal_charge=atom.formal_charge,
            aromatic=atom.aromatic,
            coordinate=coord,
        )

    def get_selected_atoms(self) -> list[AtomInfo]:
        """获取所有选中原子的信息。"""
        result = []
        for aid in self._selection.selected_atoms:
            info = self.get_atom_info(aid.value)
            if info:
                result.append(info)
        return result

    def get_bond_info(self, bond_id: str) -> dict[str, Any] | None:
        """获取键信息。"""
        from ..domain.ids import BondId
        bid = BondId(bond_id)
        try:
            bond = self._doc.topology.get_bond(bid)
        except KeyError:
            return None

        return {
            "bond_id": bond_id,
            "begin": bond.begin.value,
            "end": bond.end.value,
            "order": bond.order,
            "aromatic": bond.aromatic,
        }

    def get_conformer_list(self) -> list[dict[str, Any]]:
        """获取构象列表。"""
        if not self._doc.has_3d:
            return []

        result = []
        for i, frame in enumerate(self._doc.coordinates):
            result.append({
                "index": i,
                "source": frame.source,
                "energy": frame.energy,
                "units": "eV" if frame.energy else None,
            })
        return result

    def get_warning(self) -> str:
        """获取警告信息（过期等）。"""
        return self._invalidation.get_warning_message()
