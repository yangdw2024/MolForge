"""
application/ai/observation.py - AI 结构/几何/工件观察工具
========================================================
给 AI 提供一个**只读、限量、带单位、可判断过期**的观察窗口：
  - observe_selection   已选 AtomID / BondID（含元素、坐标、键级）
  - observe_conformer   当前构象/帧状态（不倾倒全部坐标）
  - observe_artifacts   工件元数据（只给路径与类型，不自动传文件）

每个结果都带：
  units  单位（坐标 Å、能量 eV/Hartree、时间 ps）
  stale  与观察时记录的 revision 比对，判断是否过期
  data_complete  是否为真实数据（无数据时显式 False，绝不虚构）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ...domain.document import MoleculeDocument
from ..selection import SelectionService


@dataclass
class Observation:
    kind: str
    data: dict[str, Any]
    units: dict[str, str]
    observed_revision: int
    data_complete: bool = True
    note: str = ""

    def is_stale(self, document: MoleculeDocument) -> bool:
        """数据是否已过期（文档 revision 已变化）。"""
        return document.revision != self.observed_revision


class ObservationTool:
    """AI 只读观察工具。"""

    # 一次观察最多返回的坐标数（限制数据量，防止上下文爆炸）
    MAX_COORDS = 50

    def __init__(
        self,
        document: MoleculeDocument,
        selection: SelectionService | None = None,
        artifact_provider: Callable[[], list[dict]] | None = None,
    ) -> None:
        self.document = document
        self.selection = selection
        self.artifact_provider = artifact_provider

    @property
    def _units(self) -> dict[str, str]:
        return dict(self.document.units)

    # ---------- 选择 ----------

    def observe_selection(self) -> Observation:
        if self.selection is None or self.selection.is_empty:
            return Observation(
                kind="selection", data={"selected_atoms": [], "selected_bonds": []},
                units=self._units, observed_revision=self.document.revision,
                data_complete=False, note="当前没有选中任何对象")

        atoms = []
        for aid in sorted(self.selection.selected_atoms):
            atom = self.document.topology.get_atom(aid)
            from ...domain.elements import get_element
            symbol = get_element(atom.atomic_num).symbol
            entry: dict[str, Any] = {"atom_id": aid, "element": symbol,
                                     "formal_charge": atom.formal_charge}
            coord = self._safe_coord(aid)
            if coord is not None:
                entry["coord_angstrom"] = coord
            atoms.append(entry)

        bonds = []
        for bid in sorted(self.selection.selected_bonds):
            bond = self.document.topology.get_bond(bid)
            bonds.append({"bond_id": bid, "begin": bond.begin,
                          "end": bond.end, "order": bond.order})

        return Observation(
            kind="selection",
            data={"selected_atoms": atoms, "selected_bonds": bonds,
                  "count": len(atoms) + len(bonds)},
            units=self._units, observed_revision=self.document.revision,
            note=(f"共 {len(atoms)} 个原子、{len(bonds)} 个键"
                  + ("（坐标已限量，仅显示选中项）" if len(atoms) > self.MAX_COORDS
                     else "")))

    # ---------- 构象 ----------

    def observe_conformer(self) -> Observation:
        has_3d = self.document.has_3d
        if not has_3d:
            return Observation(
                kind="conformer",
                data={"has_3d": False, "num_frames": 0},
                units=self._units, observed_revision=self.document.revision,
                data_complete=False, note="当前分子没有 3D 构象/坐标")

        store = self.document.coordinates
        cur = store.current
        # 只返回当前帧的少量坐标（限量），不倾倒全部
        sample = []
        if cur is not None:
            n = min(len(cur.coords), self.MAX_COORDS)
            for i in range(n):
                sample.append([round(float(x), 4) for x in cur.coords[i]])
        return Observation(
            kind="conformer",
            data={"has_3d": True, "num_frames": store.num_frames,
                  "current_frame": store.current_index,
                  "num_atoms": self.document.num_atoms,
                  "sample_coords_angstrom": sample,
                  "sample_truncated": len(cur.coords) > self.MAX_COORDS if cur else False},
            units=self._units, observed_revision=self.document.revision,
            note="坐标仅为当前帧前若干个样本，完整数据需用读取工具")

    # ---------- 工件 ----------

    def observe_artifacts(self) -> Observation:
        if self.artifact_provider is None:
            artifacts = []
            note = "没有注册工件来源"
        else:
            artifacts = self.artifact_provider()
            note = f"共 {len(artifacts)} 个工件"
        # 只返回元数据（名称/类型/路径/大小），绝不自动读取或上传文件
        safe = []
        for a in artifacts:
            safe.append({k: a.get(k) for k in
                         ("name", "type", "path", "size", "source") if k in a})
        return Observation(
            kind="artifacts", data={"artifacts": safe, "count": len(safe)},
            units=self._units, observed_revision=self.document.revision,
            data_complete=bool(safe), note=note)

    # ---------- 工具 ----------

    def _safe_coord(self, aid) -> list[float] | None:
        """取原子当前坐标；无坐标或索引越界返回 None（不虚构）。"""
        if not self.document.has_3d:
            return None
        try:
            store = self.document.coordinates
            cur = store.current
            if cur is None:
                return None
            # 坐标按拓扑 atom_ids 顺序排列
            ordered = list(self.document.topology.atom_ids)
            if aid not in ordered:
                return None
            idx = ordered.index(aid)
            if idx >= len(cur.coords):
                return None
            return [round(float(x), 4) for x in cur.coords[idx]]
        except Exception:
            return None
