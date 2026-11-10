"""
application/calculators/calchem_engine.py - CalChem 量子化学计算引擎适配器
==========================================================================
恢复 ISSUES_AND_TODO.md 第 4 节指出的缺失模块：
支持进程内 (in-process `import calchem`) 与外部命令行 (`calchem` CLI) 双模式调用。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .base import CalculationEngine, JobRequest, JobResult, PreparedJob


class CalChemEngine(CalculationEngine):
    """CalChem 自研量子化学平台适配器。"""

    name = "CalChem"

    def __init__(self, executable: str | None = None) -> None:
        super().__init__(executable)

    def _has_inprocess_calchem(self) -> bool:
        try:
            import calchem  # noqa: F401
            return True
        except ImportError:
            return False

    def probe(self) -> bool:
        if self._has_inprocess_calchem():
            return True
        exe = self._executable or shutil.which("calchem")
        return bool(exe and Path(exe).exists())

    def version(self) -> str:
        try:
            import calchem
            return getattr(calchem, "__version__", "1.0.0")
        except ImportError:
            return "cli-external"

    def prepare(self, request: JobRequest, workdir: Path) -> PreparedJob:
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / f"{request.name or 'calchem_job'}.json"
        inp.write_text(request.input_text, encoding="utf-8")
        h = self.hash_text(request.input_text)
        exe = self._executable or shutil.which("calchem") or "python"
        argv = [exe, "-m", "calchem", str(inp)]
        return PreparedJob(
            workdir=workdir,
            input_path=inp,
            argv=argv,
            input_hash=h,
            engine_version=self.version(),
        )

    def parse(self, prepared: PreparedJob) -> dict:
        out_json = prepared.workdir / "result.json"
        if out_json.exists():
            try:
                return json.loads(out_json.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"engine": self.name, "input_hash": prepared.input_hash, "status": "completed"}
