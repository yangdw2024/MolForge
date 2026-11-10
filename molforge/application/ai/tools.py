"""
application/ai/tools.py - AI Tool Registry
==========================================
LLM 只能调用注册表里的工具，不能执行任意 Python：
  - 权限分级 Read / View / Edit / Execute / Export
  - 每个工具带输入 JSON Schema，调用前强制校验（内置轻量校验器，无外部依赖）
  - 调用次数 / 计算预算限制
  - Edit/Execute/Export 必须显式批准，否则拒绝（不产生副作用）
  - 每次调用生成带追溯信息的收据并落日志
  - 无 shell / eval
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .observation import ObservationTool


class ToolPermission(Enum):
    READ = "read"
    VIEW = "view"
    EDIT = "edit"
    EXECUTE = "execute"
    EXPORT = "export"


# 需要批准的权限级别
_NEEDS_APPROVAL = {ToolPermission.EDIT, ToolPermission.EXECUTE,
                   ToolPermission.EXPORT}


@dataclass
class ToolReceipt:
    receipt_id: str
    tool_name: str
    arguments: dict[str, Any]
    permission: str
    success: bool
    approved: bool
    result: Any = None
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: float = 0.0

    def trace(self) -> dict:
        """可追溯信息。"""
        return {
            "receipt_id": self.receipt_id, "tool": self.tool_name,
            "permission": self.permission, "success": self.success,
            "approved": self.approved, "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "started_at": self.started_at,
        }


# ---------- 轻量 JSON Schema 校验 ----------

_TYPE_MAP = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "object": dict, "array": list,
}


def validate_schema(value: Any, schema: dict, path: str = "$") -> list[str]:
    """返回错误列表（空表示通过）。支持 type/required/enum/properties/range。"""
    errs: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: 值 {value!r} 不在允许范围 {schema['enum']}")

    t = schema.get("type")
    if t:
        py = _TYPE_MAP.get(t)
        ok = isinstance(value, py) if py else True
        if t == "integer" and isinstance(value, bool):
            ok = False
        if not ok:
            errs.append(f"{path}: 期望 {t}，得到 {type(value).__name__}")
            return errs

    if t == "object":
        for r in schema.get("required", []):
            if r not in value:
                errs.append(f"{path}: 缺少必填字段 '{r}'")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs.extend(validate_schema(value[k], sub, f"{path}.{k}"))

    if t in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} 小于最小值 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} 大于最大值 {schema['maximum']}")

    if t == "array" and "items" in schema:
        for i, item in enumerate(value):
            errs.extend(validate_schema(item, schema["items"], f"{path}[{i}]"))
    return errs


# ---------- Registry ----------

class ToolRegistry:
    def __init__(self, max_calls: int = 50, budget_seconds: float = 300.0) -> None:
        self._tools: dict[str, dict] = {}
        self._log: list[ToolReceipt] = []
        self._call_count = 0
        self.max_calls = max_calls
        self.budget_seconds = budget_seconds
        self._used_seconds = 0.0

    def register(self, name: str, description: str, schema: dict,
                 handler: Callable[..., Any],
                 permission: ToolPermission = ToolPermission.READ,
                 cost_seconds: float = 0.0) -> None:
        self._tools[name] = {
            "name": name, "description": description, "schema": schema,
            "handler": handler, "permission": permission,
            "cost_seconds": cost_seconds}

    def definitions(self) -> list[dict]:
        """OpenAI function calling 格式。"""
        return [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["schema"]}}
            for t in self._tools.values()]

    def needs_approval(self, name: str) -> bool:
        return self._tools[name]["permission"] in _NEEDS_APPROVAL

    def call(self, name: str, arguments: dict[str, Any],
             approved: bool = False) -> ToolReceipt:
        rid = uuid.uuid4().hex[:12]
        start = time.time()

        def fail(msg):
            r = ToolReceipt(
                rid, name, arguments,
                self._tools.get(name, {}).get("permission",
                    ToolPermission.READ).value if name in self._tools else "?",
                False, approved, error=msg, started_at=start,
                finished_at=time.time())
            self._log.append(r)
            return r

        # 未知工具
        if name not in self._tools:
            return fail(f"未知工具: {name}")
        tool = self._tools[name]

        # 调用次数
        if self._call_count >= self.max_calls:
            return fail(f"超过调用次数限制（{self.max_calls}）")

        # 预算
        if self._used_seconds + tool["cost_seconds"] > self.budget_seconds:
            return fail(
                f"计算预算不足（已用 {self._used_seconds:.1f}s / "
                f"上限 {self.budget_seconds:.1f}s）")

        # 参数校验
        if not isinstance(arguments, dict):
            return fail("参数必须是对象")
        verrs = validate_schema(arguments, tool["schema"])
        if verrs:
            return fail("参数非法: " + "; ".join(verrs))

        # 批准门：未批准的副作用操作直接拒绝
        if self.needs_approval(name) and not approved:
            return fail(f"工具 {name} 属于 {tool['permission'].value} 级，"
                        "未获批准，已拒绝执行")

        # 执行
        self._call_count += 1
        try:
            result = tool["handler"](**arguments)
            ok, err = True, ""
        except Exception as e:
            result, ok, err = None, False, str(e)
        end = time.time()
        self._used_seconds += tool["cost_seconds"]

        receipt = ToolReceipt(
            rid, name, arguments, tool["permission"].value, ok, approved,
            result=result, error=err, started_at=start, finished_at=end,
            duration_ms=(end - start) * 1000)
        self._log.append(receipt)
        return receipt

    def log(self) -> list[ToolReceipt]:
        return list(self._log)

    @property
    def used_seconds(self) -> float:
        return self._used_seconds
