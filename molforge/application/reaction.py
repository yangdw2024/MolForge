"""
application/reaction.py - 化学反应数据模型
=============================================
化学反应画布：反应物、产物、箭头、条件。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4, UUID


@dataclass
class ReactionComponent:
    """反应组分（反应物或产物）。"""
    component_id: UUID = field(default_factory=uuid4)
    molecule_id: UUID | None = None
    role: str = "reactant"  # reactant, product, reagent, solvent, catalyst
    coefficient: float = 1.0
    position: tuple[float, float] = (0.0, 0.0)  # 2D 位置


@dataclass
class ReactionArrow:
    """反应箭头。"""
    arrow_id: UUID = field(default_factory=uuid4)
    start: tuple[float, float] = (0.0, 0.0)
    end: tuple[float, float] = (1.0, 0.0)
    arrow_type: str = "normal"  # normal, equilibrium, reversible, retrosynthetic
    conditions: str = ""  # 反应条件（文字）


@dataclass
class Reaction:
    """化学反应。"""
    reaction_id: UUID = field(default_factory=uuid4)
    name: str = ""
    reactants: list[ReactionComponent] = field(default_factory=list)
    products: list[ReactionComponent] = field(default_factory=list)
    reagents: list[ReactionComponent] = field(default_factory=list)
    arrows: list[ReactionArrow] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_reactant(self, molecule_id: UUID, position: tuple[float, float] = (0.0, 0.0)):
        """添加反应物。"""
        comp = ReactionComponent(
            molecule_id=molecule_id,
            role="reactant",
            position=position,
        )
        self.reactants.append(comp)
        return comp

    def add_product(self, molecule_id: UUID, position: tuple[float, float] = (0.0, 0.0)):
        """添加产物。"""
        comp = ReactionComponent(
            molecule_id=molecule_id,
            role="product",
            position=position,
        )
        self.products.append(comp)
        return comp

    def add_arrow(self, start: tuple[float, float], end: tuple[float, float],
                  arrow_type: str = "normal", conditions: str = ""):
        """添加反应箭头。"""
        arrow = ReactionArrow(
            start=start,
            end=end,
            arrow_type=arrow_type,
            conditions=conditions,
        )
        self.arrows.append(arrow)
        return arrow
