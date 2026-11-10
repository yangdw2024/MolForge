"""
application/bio_selection.py - 生物分子 Selection Resolver
==========================================================
把 BioStructure（gemmi）的 model/chain/residue/atomsite 身份合并成全局唯一的
线性原子索引，并支持：
  - 残基选中 -> 原子索引集合（altloc 按策略去重）
  - 唯一定位某个原子（多链重复编号 + altloc 也不歧义）
  - 反向：索引 -> 身份
  - altloc 策略可见（max_occ / A / 全部保留）

不复制坐标真相，只建立身份与索引映射。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..io.gemmi_adapter import BioStructure


@dataclass
class AtomEntry:
    index: int
    model: int
    chain: str
    res_name: str
    res_seq: int
    icode: str
    atom_name: str
    altloc: str
    element: str
    occupancy: float
    coord: np.ndarray

    @property
    def identity(self) -> tuple:
        return (self.model, self.chain, self.res_seq, self.icode,
                self.atom_name, self.altloc)


class BioSelectionResolver:
    """生物结构选择解析器。"""

    def __init__(self, bio: BioStructure, altloc_policy: str = "max_occ") -> None:
        self.bio = bio
        self.altloc_policy = altloc_policy   # max_occ / A / all
        self.entries: list[AtomEntry] = []
        # (model,chain,seq,icode,atomname) -> list[entry index]（altloc 组）
        self._atom_groups: dict[tuple, list[int]] = {}
        self._build()

    def _build(self) -> None:
        i = 0
        for model in self.bio.models:
            for chain in model.chains:
                for res in chain.residues:
                    norm_icode = (res.icode or "").strip()
                    for site in res.atoms:
                        entry = AtomEntry(
                            index=i, model=model.model_num, chain=chain.chain_id,
                            res_name=res.name, res_seq=res.seqid_num,
                            icode=norm_icode, atom_name=site.name,
                            altloc=site.altloc or "", element=site.element,
                            occupancy=site.occupancy, coord=site.coord)
                        self.entries.append(entry)
                        key = (model.model_num, chain.chain_id, res.seqid_num,
                               norm_icode, site.name)
                        self._atom_groups.setdefault(key, []).append(i)
                        i += 1

    @property
    def num_atoms(self) -> int:
        return len(self.entries)

    # ---------- 身份解析 ----------

    def resolve_atom(
        self, model: int, chain: str, seq: int, icode: str,
        atom_name: str, altloc: str | None = None,
    ) -> int:
        """唯一定位一个原子；altloc 省略时按策略选。缺失抛错。"""
        key = (model, chain, seq, icode or "", atom_name)
        group = self._atom_groups.get(key)
        if not group:
            raise KeyError(f"找不到原子 {key}")
        if altloc is not None:
            for ei in group:
                if self.entries[ei].altloc == altloc:
                    return ei
            raise KeyError(f"找不到原子 {key} altloc={altloc}")
        return self._pick_altloc(group)

    def _pick_altloc(self, group: list[int]) -> int:
        """按 altloc 策略从同位置原子组里选一个。"""
        if len(group) == 1:
            return group[0]
        if self.altloc_policy == "all":
            return group[0]
        if self.altloc_policy == "A":
            for ei in group:
                if self.entries[ei].altloc == "A":
                    return ei
            return group[0]
        # max_occ：占用率最高；并列时无 altloc 优先，其次字母最小
        def keyf(ei):
            e = self.entries[ei]
            return (e.occupancy, 1 if not e.altloc else 0,
                    -ord(e.altloc) if e.altloc else 0)
        return max(group, key=keyf)

    def resolve_residue(
        self, model: int, chain: str, seq: int, icode: str = "",
    ) -> list[int]:
        """返回某残基的原子索引集合（按原子名 altloc 去重）。"""
        by_name: dict[str, list[int]] = {}
        for entry in self.entries:
            if (entry.model == model and entry.chain == chain
                    and entry.res_seq == seq and entry.icode == (icode or "")):
                by_name.setdefault(entry.atom_name, []).append(entry.index)
        out = [self._pick_altloc(group) for group in by_name.values()]
        return sorted(out)

    def resolve_chain(self, model: int, chain: str) -> list[int]:
        """返回整条链的原子索引（altloc 去重）。"""
        seen_res: set[tuple] = set()
        out: list[int] = []
        for e in self.entries:
            if e.model == model and e.chain == chain:
                rk = (e.res_seq, e.icode)
                if rk not in seen_res:
                    seen_res.add(rk)
                    out.extend(self.resolve_residue(
                        model, chain, e.res_seq, e.icode))
        return sorted(set(out))

    def identity_of(self, index: int) -> AtomEntry:
        return self.entries[index]

    def altloc_variants(self, model, chain, seq, icode, atom_name) -> list[int]:
        """返回某原子全部 altloc 变体（用于在界面展示 altloc 策略）。"""
        key = (model, chain, seq, icode or "", atom_name)
        return list(self._atom_groups.get(key, []))
