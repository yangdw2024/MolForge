"""
application/fragment_catalog.py - 对标 GaussView Element Fragments 的分类基团库
================================================================================
每个 FragmentSpec 提供：
  - 精确校准的局部 3D 模板坐标（入口原子位于原点 (0,0,0)，主生长方向沿 +X 轴 (1,0,0)）
  - 完整的显式氢与键级拓扑（单键/双键/三键/芳香键），无需外部网络或不稳定力场即可 100% 确定性接枝
  - 化学连接键级 (attachment_bond_order) 与离去氢替换策略
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class FragmentAtomTemplate:
    atomic_num: int
    symbol: str
    local_xyz: tuple[float, float, float]  # 单位 Å，入口原子 index=0 位于 (0,0,0)
    formal_charge: int = 0
    aromatic: bool = False


@dataclass(frozen=True)
class FragmentBondTemplate:
    begin_idx: int
    end_idx: int
    order: int = 1


@dataclass(frozen=True)
class FragmentSpec:
    id: str
    name_cn: str
    name_en: str
    formula: str
    category: str  # "C" | "O" | "N" | "Common"
    smiles: str
    attachment_bond_order: int
    atoms: tuple[FragmentAtomTemplate, ...]
    bonds: tuple[FragmentBondTemplate, ...]
    description: str = ""
    geometry_key: str | None = None


FRAGMENT_CATALOG: tuple[FragmentSpec, ...] = (
    # ======================== C 元素片段 ========================
    FragmentSpec(
        id="c_atom",
        name_cn="单碳原子 (C)",
        name_en="Carbon Atom",
        formula="-C",
        category="C",
        smiles="C",
        attachment_bond_order=1,
        atoms=(FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),),
        bonds=(),
        description="单个 sp3 碳原子节点",
    ),
    FragmentSpec(
        id="methyl",
        name_cn="甲基 (-CH₃)",
        name_en="Methyl",
        formula="-CH3",
        category="C",
        smiles="C",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(1, "H", (0.36, 1.03, 0.0)),
            FragmentAtomTemplate(1, "H", (0.36, -0.515, 0.892)),
            FragmentAtomTemplate(1, "H", (0.36, -0.515, -0.892)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 1),
            FragmentBondTemplate(0, 2, 1),
            FragmentBondTemplate(0, 3, 1),
        ),
        description="标准四面体甲基 (-CH₃)",
    ),
    FragmentSpec(
        id="vinyl",
        name_cn="乙烯基 (-CH=CH₂)",
        name_en="Vinyl",
        formula="-CH=CH2",
        category="C",
        smiles="C=C",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (0.67, 1.16, 0.0)),
            FragmentAtomTemplate(1, "H", (0.54, -0.94, 0.0)),
            FragmentAtomTemplate(1, "H", (0.13, 2.10, 0.0)),
            FragmentAtomTemplate(1, "H", (1.75, 1.16, 0.0)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 2),
            FragmentBondTemplate(0, 2, 1),
            FragmentBondTemplate(1, 3, 1),
            FragmentBondTemplate(1, 4, 1),
        ),
        description="平面 sp2 乙烯基 (-CH=CH₂)",
    ),
    FragmentSpec(
        id="ethynyl",
        name_cn="乙炔基 (-C≡CH)",
        name_en="Ethynyl",
        formula="-C#CH",
        category="C",
        smiles="C#C",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (1.20, 0.0, 0.0)),
            FragmentAtomTemplate(1, "H", (2.26, 0.0, 0.0)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 3),
            FragmentBondTemplate(1, 2, 1),
        ),
        description="线性 sp 乙炔基 (-C≡CH)",
    ),
    FragmentSpec(
        id="isopropyl",
        name_cn="异丙基 (-CH(CH₃)₂)",
        name_en="Isopropyl",
        formula="-CH(CH3)2",
        category="C",
        smiles="CC(C)",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (0.51, 1.26, 0.70)),
            FragmentAtomTemplate(6, "C", (0.51, -1.26, 0.70)),
            FragmentAtomTemplate(1, "H", (0.36, 0.0, -1.03)),
            FragmentAtomTemplate(1, "H", (1.60, 1.26, 0.70)),
            FragmentAtomTemplate(1, "H", (0.15, 2.15, 0.18)),
            FragmentAtomTemplate(1, "H", (0.15, 1.30, 1.73)),
            FragmentAtomTemplate(1, "H", (1.60, -1.26, 0.70)),
            FragmentAtomTemplate(1, "H", (0.15, -2.15, 0.18)),
            FragmentAtomTemplate(1, "H", (0.15, -1.30, 1.73)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 1),
            FragmentBondTemplate(0, 2, 1),
            FragmentBondTemplate(0, 3, 1),
            FragmentBondTemplate(1, 4, 1),
            FragmentBondTemplate(1, 5, 1),
            FragmentBondTemplate(1, 6, 1),
            FragmentBondTemplate(2, 7, 1),
            FragmentBondTemplate(2, 8, 1),
            FragmentBondTemplate(2, 9, 1),
        ),
        description="支链异丙基片段 (-iPr)",
    ),
    FragmentSpec(
        id="tert_butyl",
        name_cn="叔丁基 (-C(CH₃)₃)",
        name_en="tert-Butyl",
        formula="-C(CH3)3",
        category="C",
        smiles="CC(C)(C)",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (0.51, 1.44, 0.0)),
            FragmentAtomTemplate(6, "C", (0.51, -0.72, 1.25)),
            FragmentAtomTemplate(6, "C", (0.51, -0.72, -1.25)),
            FragmentAtomTemplate(1, "H", (1.60, 1.44, 0.0)),
            FragmentAtomTemplate(1, "H", (0.15, 1.96, 0.89)),
            FragmentAtomTemplate(1, "H", (0.15, 1.96, -0.89)),
            FragmentAtomTemplate(1, "H", (1.60, -0.72, 1.25)),
            FragmentAtomTemplate(1, "H", (0.15, -0.20, 2.14)),
            FragmentAtomTemplate(1, "H", (0.15, -1.75, 1.25)),
            FragmentAtomTemplate(1, "H", (1.60, -0.72, -1.25)),
            FragmentAtomTemplate(1, "H", (0.15, -0.20, -2.14)),
            FragmentAtomTemplate(1, "H", (0.15, -1.75, -1.25)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 1),
            FragmentBondTemplate(0, 2, 1),
            FragmentBondTemplate(0, 3, 1),
            FragmentBondTemplate(1, 4, 1),
            FragmentBondTemplate(1, 5, 1),
            FragmentBondTemplate(1, 6, 1),
            FragmentBondTemplate(2, 7, 1),
            FragmentBondTemplate(2, 8, 1),
            FragmentBondTemplate(2, 9, 1),
            FragmentBondTemplate(3, 10, 1),
            FragmentBondTemplate(3, 11, 1),
            FragmentBondTemplate(3, 12, 1),
        ),
        description="大位阻叔丁基片段 (-tBu)",
    ),

    # ======================== O 元素片段 ========================
    FragmentSpec(
        id="o_atom",
        name_cn="单氧原子 (O)",
        name_en="Oxygen Atom",
        formula="-O",
        category="O",
        smiles="O",
        attachment_bond_order=1,
        atoms=(FragmentAtomTemplate(8, "O", (0.0, 0.0, 0.0)),),
        bonds=(),
        description="单个氧原子节点",
    ),
    FragmentSpec(
        id="hydroxyl",
        name_cn="羟基 (-OH)",
        name_en="Hydroxyl",
        formula="-OH",
        category="O",
        smiles="O",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(8, "O", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(1, "H", (0.32, 0.91, 0.0)),
        ),
        bonds=(FragmentBondTemplate(0, 1, 1),),
        description="醇/酚羟基 (-OH)",
    ),
    FragmentSpec(
        id="carbonyl",
        name_cn="羰基/甲酰基 (-CH=O)",
        name_en="Formyl / Carbonyl",
        formula="-CH=O",
        category="O",
        smiles="C=O",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(8, "O", (0.62, 1.06, 0.0)),
            FragmentAtomTemplate(1, "H", (0.55, -0.95, 0.0)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 2),
            FragmentBondTemplate(0, 2, 1),
        ),
        description="羰基/醛基连接模板 (-CH=O)",
    ),
    FragmentSpec(
        id="methoxy",
        name_cn="醚键/甲氧基 (-OCH₃)",
        name_en="Methoxy / Ether",
        formula="-OCH3",
        category="O",
        smiles="OC",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(8, "O", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (0.71, 1.22, 0.0)),
            FragmentAtomTemplate(1, "H", (1.79, 1.08, 0.0)),
            FragmentAtomTemplate(1, "H", (0.42, 1.78, 0.89)),
            FragmentAtomTemplate(1, "H", (0.42, 1.78, -0.89)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 1),
            FragmentBondTemplate(1, 2, 1),
            FragmentBondTemplate(1, 3, 1),
            FragmentBondTemplate(1, 4, 1),
        ),
        description="甲氧基/醚桥模板 (-O-CH₃)",
    ),

    # ======================== N 元素片段 ========================
    FragmentSpec(
        id="n_atom",
        name_cn="单氮原子 (N)",
        name_en="Nitrogen Atom",
        formula="-N",
        category="N",
        smiles="N",
        attachment_bond_order=1,
        atoms=(FragmentAtomTemplate(7, "N", (0.0, 0.0, 0.0)),),
        bonds=(),
        description="单个氮原子节点",
    ),
    FragmentSpec(
        id="amino",
        name_cn="氨基 (-NH₂)",
        name_en="Amino",
        formula="-NH2",
        category="N",
        smiles="N",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(7, "N", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(1, "H", (0.38, 0.82, 0.45)),
            FragmentAtomTemplate(1, "H", (0.38, -0.82, 0.45)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 1),
            FragmentBondTemplate(0, 2, 1),
        ),
        description="三角锥伯氨基 (-NH₂)",
    ),
    FragmentSpec(
        id="nitro",
        name_cn="硝基 (-NO₂)",
        name_en="Nitro",
        formula="-NO2",
        category="N",
        smiles="[N+](=O)[O-]",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(7, "N", (0.0, 0.0, 0.0), formal_charge=1),
            FragmentAtomTemplate(8, "O", (0.58, 1.08, 0.0), formal_charge=0),
            FragmentAtomTemplate(8, "O", (0.58, -1.08, 0.0), formal_charge=-1),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 2),
            FragmentBondTemplate(0, 2, 1),
        ),
        description="强吸电子平面硝基 (-NO₂)",
    ),
    FragmentSpec(
        id="cyano",
        name_cn="氰基 (-C≡N)",
        name_en="Cyano",
        formula="-CN",
        category="N",
        smiles="C#N",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(7, "N", (1.16, 0.0, 0.0)),
        ),
        bonds=(FragmentBondTemplate(0, 1, 3),),
        description="线性强吸电子氰基 (-C≡N，OSC A 端高频基团)",
    ),

    # ======================== Common 通用高频基团 ========================
    FragmentSpec(
        id="carboxyl",
        name_cn="羧基 (-COOH)",
        name_en="Carboxyl",
        formula="-COOH",
        category="Common",
        smiles="C(=O)O",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(8, "O", (0.60, 1.05, 0.0)),
            FragmentAtomTemplate(8, "O", (0.68, -1.16, 0.0)),
            FragmentAtomTemplate(1, "H", (1.64, -1.05, 0.0)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 2),
            FragmentBondTemplate(0, 2, 1),
            FragmentBondTemplate(2, 3, 1),
        ),
        description="羧酸基团 (-COOH)",
    ),
    FragmentSpec(
        id="phenyl",
        name_cn="苯基 (-C₆H₅)",
        name_en="Phenyl",
        formula="-C6H5",
        category="Common",
        smiles="c1ccccc1",
        attachment_bond_order=1,
        atoms=(
            FragmentAtomTemplate(6, "C", (0.0, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (0.70, 1.21, 0.0)),
            FragmentAtomTemplate(6, "C", (2.10, 1.21, 0.0)),
            FragmentAtomTemplate(6, "C", (2.80, 0.0, 0.0)),
            FragmentAtomTemplate(6, "C", (2.10, -1.21, 0.0)),
            FragmentAtomTemplate(6, "C", (0.70, -1.21, 0.0)),
            FragmentAtomTemplate(1, "H", (0.16, 2.15, 0.0)),
            FragmentAtomTemplate(1, "H", (2.64, 2.15, 0.0)),
            FragmentAtomTemplate(1, "H", (3.88, 0.0, 0.0)),
            FragmentAtomTemplate(1, "H", (2.64, -2.15, 0.0)),
            FragmentAtomTemplate(1, "H", (0.16, -2.15, 0.0)),
        ),
        bonds=(
            FragmentBondTemplate(0, 1, 2),
            FragmentBondTemplate(1, 2, 1),
            FragmentBondTemplate(2, 3, 2),
            FragmentBondTemplate(3, 4, 1),
            FragmentBondTemplate(4, 5, 2),
            FragmentBondTemplate(5, 0, 1),
            FragmentBondTemplate(1, 6, 1),
            FragmentBondTemplate(2, 7, 1),
            FragmentBondTemplate(3, 8, 1),
            FragmentBondTemplate(4, 9, 1),
            FragmentBondTemplate(5, 10, 1),
        ),
        description="标准芳香苯环片段 (-Ph)",
    ),
)

_BY_ID: dict[str, FragmentSpec] = {f.id: f for f in FRAGMENT_CATALOG}


class FragmentCatalog:
    """基团目录查询服务。"""

    @staticmethod
    def all_fragments() -> tuple[FragmentSpec, ...]:
        return FRAGMENT_CATALOG

    @staticmethod
    def get(fragment_id: str) -> FragmentSpec | None:
        return _BY_ID.get(fragment_id)

    @staticmethod
    def by_category(category: str) -> list[FragmentSpec]:
        cat = category.strip().upper()
        if cat in ("C", "O", "N"):
            return [f for f in FRAGMENT_CATALOG if f.category == cat]
        return [f for f in FRAGMENT_CATALOG if f.category.upper() == cat]

    @staticmethod
    def for_element_symbol(symbol: str) -> list[FragmentSpec]:
        cat = symbol.strip().upper()
        sym = symbol.strip().capitalize()
        if sym in ("C", "O", "N"):
            return [f for f in FRAGMENT_CATALOG if f.category == sym or f.category == "Common"]
        return [f for f in FRAGMENT_CATALOG if f.category.upper() == cat]
