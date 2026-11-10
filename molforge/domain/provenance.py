"""
domain/provenance.py - 科学来源 / 版本溯源中心
============================================
为每个主要数值结果（工件）记录：
  sha256（自动计算）、来源、方法、单位、参数、软件与版本、时间、对应几何，
  derived_from 完整上游图，以及 kind（计算事实 / 实验观测 / AI 假设）。

任何主要数值都能沿 derived_from 图回溯到来源、方法和几何。
"""
from __future__ import annotations

import hashlib
import platform
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProvenanceKind(Enum):
    COMPUTED = "computed"
    EXPERIMENT = "experiment"
    AI_ASSUMED = "ai_assumed"


@dataclass
class ProvenanceRecord:
    record_id: str
    artifact: str
    sha256: str
    source: str
    method: str = ""
    units: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    software: str = ""
    version: str = ""
    geometry_ref: str = ""
    kind: ProvenanceKind = ProvenanceKind.COMPUTED
    derived_from: list[str] = field(default_factory=list)
    created_at: float = 0.0

    @property
    def is_fact(self) -> bool:
        return self.kind in (ProvenanceKind.COMPUTED, ProvenanceKind.EXPERIMENT)


class ProvenanceGraph:
    def __init__(self) -> None:
        self._records: dict[str, ProvenanceRecord] = {}

    def add(
        self,
        artifact: str,
        payload: bytes | str,
        source: str,
        method: str = "",
        units: dict | None = None,
        params: dict | None = None,
        software: str = "MolForge",
        version: str = "",
        geometry_ref: str = "",
        kind: ProvenanceKind = ProvenanceKind.COMPUTED,
        derived_from: list[str] | None = None,
    ) -> ProvenanceRecord:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        sha = hashlib.sha256(payload).hexdigest()
        rec = ProvenanceRecord(
            record_id=uuid.uuid4().hex[:12], artifact=artifact, sha256=sha,
            source=source, method=method, units=units or {},
            params=params or {}, software=software,
            version=version or f"Python {platform.python_version()}",
            geometry_ref=geometry_ref, kind=kind,
            derived_from=list(derived_from or []), created_at=time.time())
        self._records[rec.record_id] = rec
        return rec

    def get(self, record_id: str) -> ProvenanceRecord:
        return self._records[record_id]

    def by_artifact(self, name: str) -> list[ProvenanceRecord]:
        return [r for r in self._records.values() if r.artifact == name]

    def trace_back(self, record_id: str) -> list[ProvenanceRecord]:
        """沿 derived_from 完整回溯（含自身，去环）。"""
        out: list[ProvenanceRecord] = []
        stack = [record_id]
        seen = set()
        while stack:
            rid = stack.pop()
            if rid in seen or rid not in self._records:
                continue
            seen.add(rid)
            rec = self._records[rid]
            out.append(rec)
            stack.extend(rec.derived_from)
        return out

    def explain(self, record_id: str) -> dict:
        rec = self.get(record_id)
        return {
            "artifact": rec.artifact, "method": rec.method,
            "source": rec.source, "software": rec.software,
            "version": rec.version, "geometry_ref": rec.geometry_ref,
            "units": rec.units, "kind": rec.kind.value,
            "is_fact": rec.is_fact, "sha256": rec.sha256,
            "derived_from": rec.derived_from}

    def all_records(self) -> list[ProvenanceRecord]:
        return list(self._records.values())


# 向后兼容别名
ProvenanceTracker = ProvenanceGraph
