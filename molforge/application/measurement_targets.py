"""
application/measurement_targets.py - 拓扑感知的测量与内坐标目标解析器
======================================================================
解决 P0 痛点：
  1. 选中两条相邻化学键时，自动求唯一公共顶点 j 与两侧端点 i, k，彻底杜绝测成 36.9° 同侧小角！
  2. 选中三个原子时：
     - 若拓扑中恰有唯一中心原子 j 与另外两个原子成键（开链 i-j-k），无论用户点击顺序如何，自动将 j 置为顶点；
     - 若三个原子构成三元环（彼此均成键）或互不相连，则要求按用户点击的有序序列 ordered_atoms[0]-ordered_atoms[1]-ordered_atoms[2] 解析并给出明确诊断说明。
  3. 选中四个原子时：
     - 自动识别简单有向链 i-j-k-l，或按用户点击顺序解析。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId
from .selection import SelectionService


@dataclass(frozen=True)
class ResolvedTarget:
    kind: Literal["none", "distance", "angle", "dihedral", "ambiguous", "invalid"]
    atoms: tuple[AtomId, ...] = ()
    center_bond: BondId | None = None
    canonical_dihedral_atoms: tuple[AtomId, AtomId, AtomId, AtomId] | None = None
    label: str = ""
    diagnostic: str = ""


class MeasurementTargetResolver:
    """从 SelectionService 与 MoleculeDocument 解析规范的测量/内坐标原子序列。"""

    @staticmethod
    def find_canonical_dihedral_for_bond(
        doc: MoleculeDocument, bid: BondId
    ) -> tuple[AtomId, AtomId, AtomId, AtomId] | None:
        """
        为给定的化学键 bid (j-k) 寻找最具化学意义的规范二面角链 i - j - k - l。
        规则：
          1. 优先选择非氢重原子；
          2. 其次选择原子序数最高者；
          3. 再次按 AtomId 升序排列。
        """
        if bid not in doc.topology._bonds:
            return None
        bond = doc.topology.get_bond(bid)
        j, k = bond.begin, bond.end

        def get_best_neighbor(node: AtomId, exclude: AtomId) -> AtomId | None:
            candidates: list[AtomId] = []
            for b_other_id in doc.topology._adjacency.get(node, []):
                if b_other_id in doc.topology._bonds:
                    b_other = doc.topology.get_bond(b_other_id)
                    nbr = b_other.end if b_other.begin == node else b_other.begin
                    if nbr != exclude and nbr in doc.topology._atoms:
                        candidates.append(nbr)
            if not candidates:
                return None
            # 排序：重原子(非H)优先 (-atomic_num)，原子序数大优先，AtomId 小优先
            def sort_key(aid: AtomId):
                atom = doc.topology.get_atom(aid)
                is_h = 1 if atom.atomic_num == 1 else 0
                return (is_h, -atom.atomic_num, aid.value)
            candidates.sort(key=sort_key)
            return candidates[0]

        i = get_best_neighbor(j, exclude=k)
        l = get_best_neighbor(k, exclude=j)
        if i is not None and l is not None and i != l:
            return (i, j, k, l)
        return None

    @staticmethod
    def resolve(doc: MoleculeDocument, selection: SelectionService) -> ResolvedTarget:
        ordered_atoms = list(selection.ordered_atoms)
        if not ordered_atoms and selection.selected_atoms:
            ordered_atoms = list(selection.selected_atoms)
        ordered_bonds = list(selection.ordered_bonds)
        if not ordered_bonds and selection.selected_bonds:
            ordered_bonds = list(selection.selected_bonds)

        # 情形 A：选中了 2 条相邻化学键 -> 解析键角 (i - j_shared - k)
        if len(ordered_bonds) == 2 and len(ordered_atoms) == 0:
            return MeasurementTargetResolver.resolve_angle_from_two_bonds(doc, ordered_bonds[0], ordered_bonds[1])

        # 情形 B：选中了 1 条化学键且无额外原子 -> 解析键长，并自动附带该键的主二面角候选链
        if len(ordered_bonds) == 1 and len(ordered_atoms) == 0:
            bid = ordered_bonds[0]
            if bid not in doc.topology._bonds:
                return ResolvedTarget(kind="invalid", diagnostic="选中的化学键不存在")
            bond = doc.topology.get_bond(bid)
            canon_dih = MeasurementTargetResolver.find_canonical_dihedral_for_bond(doc, bid)
            return ResolvedTarget(
                kind="distance",
                atoms=(bond.begin, bond.end),
                center_bond=bid,
                canonical_dihedral_atoms=canon_dih,
                label=f"#{bond.begin.value + 1}–#{bond.end.value + 1}",
            )

        n = len(ordered_atoms)
        if n == 2:
            a1, a2 = ordered_atoms[0], ordered_atoms[1]
            bid = doc.topology.bond_between(a1, a2) if hasattr(doc.topology, "bond_between") else None
            if bid is None and hasattr(doc.topology, "find_bond_between"):
                bid = doc.topology.find_bond_between(a1, a2)
            canon_dih = MeasurementTargetResolver.find_canonical_dihedral_for_bond(doc, bid) if bid else None
            return ResolvedTarget(
                kind="distance",
                atoms=(a1, a2),
                center_bond=bid,
                canonical_dihedral_atoms=canon_dih,
                label=f"#{a1.value + 1}–#{a2.value + 1}",
            )
        elif n == 3:
            return MeasurementTargetResolver.resolve_angle_from_three_atoms(doc, ordered_atoms)
        elif n == 4:
            return MeasurementTargetResolver.resolve_dihedral_from_four_atoms(doc, ordered_atoms)
        elif n == 0:
            return ResolvedTarget(kind="none", diagnostic="未选中原子或化学键")
        else:
            return ResolvedTarget(kind="invalid", diagnostic=f"已选中 {n} 个原子（请选择 2~4 个原子或 2 条相邻键）")

    @staticmethod
    def _are_bonded(doc: MoleculeDocument, a1: AtomId, a2: AtomId) -> bool:
        for bid in doc.topology._adjacency.get(a1, []):
            if bid in doc.topology._bonds:
                b = doc.topology.get_bond(bid)
                if (b.begin == a1 and b.end == a2) or (b.begin == a2 and b.end == a1):
                    return True
        return False

    @staticmethod
    def resolve_angle_from_two_bonds(doc: MoleculeDocument, bid1: BondId, bid2: BondId) -> ResolvedTarget:
        if bid1 not in doc.topology._bonds or bid2 not in doc.topology._bonds:
            return ResolvedTarget(kind="invalid", diagnostic="选中的化学键不存在")
        b1 = doc.topology.get_bond(bid1)
        b2 = doc.topology.get_bond(bid2)
        s1 = {b1.begin, b1.end}
        s2 = {b2.begin, b2.end}
        shared = s1 & s2
        if len(shared) != 1:
            return ResolvedTarget(
                kind="invalid",
                diagnostic="选中的两条化学键没有唯一公共顶点原子，无法测量键角",
            )
        j_center = next(iter(shared))
        i_end = b1.end if b1.begin == j_center else b1.begin
        k_end = b2.end if b2.begin == j_center else b2.begin
        return ResolvedTarget(
            kind="angle",
            atoms=(i_end, j_center, k_end),
            label=f"#{i_end.value + 1}–#{j_center.value + 1}(顶点)–#{k_end.value + 1}",
        )

    @staticmethod
    def resolve_angle_from_three_atoms(doc: MoleculeDocument, atoms: Sequence[AtomId]) -> ResolvedTarget:
        if len(atoms) != 3:
            return ResolvedTarget(kind="invalid", diagnostic="键角测量需要 3 个原子")
        a0, a1, a2 = atoms[0], atoms[1], atoms[2]
        if len({a0, a1, a2}) != 3:
            return ResolvedTarget(kind="invalid", diagnostic="包含重复原子")

        # 统计每个原子在 {a0, a1, a2} 导出子图中的度数
        sub_set = {a0, a1, a2}
        degrees: dict[AtomId, list[AtomId]] = {a0: [], a1: [], a2: []}
        for u in (a0, a1, a2):
            for v in (a0, a1, a2):
                if u != v and MeasurementTargetResolver._are_bonded(doc, u, v):
                    degrees[u].append(v)

        deg2_nodes = [u for u in (a0, a1, a2) if len(degrees[u]) == 2]

        # 1. 唯一中心原子（标准开链键角 i - j - k）：无论用户以何种顺序选中这 3 个原子，自动以度数为 2 的原子作为顶点 j！
        if len(deg2_nodes) == 1:
            j = deg2_nodes[0]
            ends = [u for u in (a0, a1, a2) if u != j]
            if len(ends) == 2 and ends[1] == a0:
                ends[0], ends[1] = ends[1], ends[0]
            i, k = ends[0], ends[1]
            return ResolvedTarget(
                kind="angle",
                atoms=(i, j, k),
                label=f"#{i.value + 1}–#{j.value + 1}(顶点)–#{k.value + 1}",
            )

        # 2. 三元环（三个原子两两成键，度数均为 2）：存在顶点歧义，显式提示或要求用户按 i->j->k 顺序选择
        if len(deg2_nodes) == 3:
            return ResolvedTarget(
                kind="ambiguous",
                atoms=(a0, a1, a2),
                label=f"#{a0.value + 1}–#{a1.value + 1}–#{a2.value + 1}",
                diagnostic=f"三元环存在顶点歧义：请确认中心顶点是否为 #{a1.value + 1}，或直接选中两条相邻环键测角",
            )

        # 3. 非完全成键三原子：严格按用户点击顺序 (a0 -> a1(顶点) -> a2)
        return ResolvedTarget(
            kind="angle",
            atoms=(a0, a1, a2),
            label=f"#{a0.value + 1}–#{a1.value + 1}(非成键顶点)–#{a2.value + 1}",
            diagnostic="非成键三原子夹角（按点击顺序以第 2 个原子为顶点）",
        )

    @staticmethod
    def resolve_dihedral_from_four_atoms(doc: MoleculeDocument, atoms: Sequence[AtomId]) -> ResolvedTarget:
        if len(atoms) != 4 or len(set(atoms)) != 4:
            return ResolvedTarget(kind="invalid", diagnostic="二面角测量需要 4 个不同原子")
        a0, a1, a2, a3 = atoms[0], atoms[1], atoms[2], atoms[3]

        # 如果当前顺序已经是连通链 a0-a1-a2-a3，直接采用
        if (
            MeasurementTargetResolver._are_bonded(doc, a0, a1)
            and MeasurementTargetResolver._are_bonded(doc, a1, a2)
            and MeasurementTargetResolver._are_bonded(doc, a2, a3)
        ):
            return ResolvedTarget(
                kind="dihedral",
                atoms=(a0, a1, a2, a3),
                label=f"#{a0.value + 1}–#{a1.value + 1}–#{a2.value + 1}–#{a3.value + 1}",
            )

        # 否则在 4 个原子的导出子图中寻找唯一简单路径 i - j - k - l
        import itertools
        valid_chains: list[tuple[AtomId, AtomId, AtomId, AtomId]] = []
        for perm in itertools.permutations(atoms, 4):
            if (
                MeasurementTargetResolver._are_bonded(doc, perm[0], perm[1])
                and MeasurementTargetResolver._are_bonded(doc, perm[1], perm[2])
                and MeasurementTargetResolver._are_bonded(doc, perm[2], perm[3])
            ):
                # 排除反向重复链 (l-k-j-i 与 i-j-k-l 二面角绝对值与符号相同)
                if perm[::-1] not in valid_chains:
                    valid_chains.append(perm)

        if len(valid_chains) == 1:
            c = valid_chains[0]
            if atoms[0] == c[3]:
                c = (c[3], c[2], c[1], c[0])
            return ResolvedTarget(
                kind="dihedral",
                atoms=c,
                label=f"#{c[0].value + 1}–#{c[1].value + 1}–#{c[2].value + 1}–#{c[3].value + 1}",
            )
        elif len(valid_chains) > 1:
            best_c = valid_chains[0]
            for c in valid_chains:
                if c[0] == atoms[0] or c[3] == atoms[0]:
                    best_c = c if c[0] == atoms[0] else (c[3], c[2], c[1], c[0])
                    break
            return ResolvedTarget(
                kind="dihedral",
                atoms=best_c,
                label=f"#{best_c[0].value + 1}–#{best_c[1].value + 1}–#{best_c[2].value + 1}–#{best_c[3].value + 1}",
            )

        return ResolvedTarget(
            kind="dihedral",
            atoms=(a0, a1, a2, a3),
            label=f"#{a0.value + 1}–#{a1.value + 1}–#{a2.value + 1}–#{a3.value + 1}",
            diagnostic="按点击顺序计算广义二面角",
        )
