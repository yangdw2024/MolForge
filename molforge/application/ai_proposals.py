"""
application/ai_proposals.py - AI 提案系统（预览 / 批准 / 事务回滚）
================================================================
AI 不能直接改文档，必须：
  1. create_proposal：在文档副本上预执行，做化学验证，计算差异，记录 base_revision
  2. 用户看到差异后批准
  3. commit：检查 stale token（base_revision）、CAS 状态转换，真正提交
  4. 提交后可用 command_bus.undo 复原

拦截：
  - 未经审批不改结构
  - 文档 revision 已变化 -> stale token，提交失败
  - 重复提交 / 非 PENDING 状态 -> 拒绝
"""
from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..domain.document import MoleculeDocument


class ProposalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    COMMITTED = "committed"


@dataclass
class ProposalDiff:
    added_atoms: list = field(default_factory=list)
    removed_atoms: list = field(default_factory=list)
    added_bonds: list = field(default_factory=list)
    removed_bonds: list = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added_atoms or self.removed_atoms
                    or self.added_bonds or self.removed_bonds)

    def summary(self) -> str:
        return (f"+{len(self.added_atoms)} 原子 / -{len(self.removed_atoms)} 原子"
                f" / +{len(self.added_bonds)} 键 / -{len(self.removed_bonds)} 键")


@dataclass
class Proposal:
    proposal_id: str
    description: str
    command: Any
    status: ProposalStatus = ProposalStatus.PENDING
    diff: ProposalDiff = field(default_factory=ProposalDiff)
    base_revision: int = 0          # stale token
    validation_errors: list = field(default_factory=list)
    created_at: float = 0.0
    committed_at: float | None = None

    @property
    def chemically_valid(self) -> bool:
        return not self.validation_errors


class AIProposalService:
    def __init__(self, document: MoleculeDocument, command_bus) -> None:
        self.document = document
        self.command_bus = command_bus
        self._proposals: dict[str, Proposal] = {}

    # ---------- 创建（副本预执行 + 化学验证）----------

    def create_proposal(self, description: str, command: Any) -> Proposal:
        doc_copy = copy.deepcopy(self.document)
        result = command.do(doc_copy)
        if not result.success:
            raise ValueError(f"命令在副本上预执行失败: {result.message}")

        # 化学验证（在副本上）
        errors = doc_copy.validate()

        diff = self._compute_diff(self.document, doc_copy)
        proposal = Proposal(
            proposal_id=uuid.uuid4().hex[:12],
            description=description, command=command, diff=diff,
            base_revision=self.document.revision,
            validation_errors=errors, created_at=time.time())
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    # ---------- 提交（stale + CAS）----------

    def commit(self, proposal_id: str) -> Any:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError("提案不存在")

        # CAS：只有 PENDING 可提交（重复提交拦截）
        if proposal.status != ProposalStatus.PENDING:
            raise RuntimeError(
                f"提案当前状态 {proposal.status.value}，不能重复提交")

        # 化学验证不过，拒绝
        if not proposal.chemically_valid:
            raise RuntimeError(
                "提案化学验证不通过: " + "; ".join(proposal.validation_errors))

        # stale token：文档已被其他操作改动
        if self.document.revision != proposal.base_revision:
            proposal.status = ProposalStatus.EXPIRED
            raise RuntimeError(
                f"提案已过期（stale token）：创建时 revision "
                f"{proposal.base_revision}，当前 {self.document.revision}")

        # 真正提交（走 command_bus，进入 Undo 历史）
        result = self.command_bus.execute(proposal.command)
        if not result.success:
            raise RuntimeError(f"提交失败: {result.message}")

        proposal.status = ProposalStatus.COMMITTED
        proposal.committed_at = time.time()
        return result

    def reject(self, proposal_id: str) -> None:
        p = self._proposals.get(proposal_id)
        if p and p.status == ProposalStatus.PENDING:
            p.status = ProposalStatus.REJECTED

    def rollback(self, proposal_id: str) -> bool:
        """撤销已提交提案（复原），走 command_bus.undo。"""
        p = self._proposals.get(proposal_id)
        if p is None or p.status != ProposalStatus.COMMITTED:
            return False
        result = self.command_bus.undo()
        if result.success:
            p.status = ProposalStatus.APPROVED  # 已回滚，标记可重新提交
        return result.success

    def get(self, proposal_id: str) -> Proposal:
        return self._proposals[proposal_id]

    def pending(self) -> list[Proposal]:
        return [p for p in self._proposals.values()
                if p.status == ProposalStatus.PENDING]

    # ---------- 差异 ----------

    def _compute_diff(self, before: MoleculeDocument,
                      after: MoleculeDocument) -> ProposalDiff:
        def atom_sig(doc):
            return set(a.value for a in doc.topology.atom_ids)

        def bond_sig(doc):
            return set((lambda b: (b.begin.value, b.end.value, b.order))(
                       doc.topology.get_bond(bid))
                       for bid in doc.topology.bond_ids)

        ba, aa = atom_sig(before), atom_sig(after)
        bb, ab = bond_sig(before), bond_sig(after)
        return ProposalDiff(
            added_atoms=sorted(aa - ba), removed_atoms=sorted(ba - aa),
            added_bonds=sorted(ab - bb), removed_bonds=sorted(bb - ab))
