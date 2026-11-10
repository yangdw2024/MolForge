"""
calculators/gaussian_engine.py - Gaussian 16/09 受控计算引擎
============================================================
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .base import CalculationEngine, JobRequest, PreparedJob, EngineNotFound


class GaussianEngine(CalculationEngine):
    name = "Gaussian"

    def __init__(self, executable: str | None = None) -> None:
        exe = executable or shutil.which("g16") or shutil.which("g09") or r"C:\\G16W\\g16.exe"
        super().__init__(exe)

    def probe(self) -> bool:
        return bool(self._executable) and Path(self._executable).is_file()

    def version(self) -> str:
        return Path(self._executable).stem if self._executable else "g16"

    def prepare(self, request: JobRequest, workdir: Path) -> PreparedJob:
        if not self.probe():
            raise EngineNotFound("未找到 Gaussian (g16/g09)。请安装 Gaussian 或导出 .gjf 到超算运行。")
        workdir.mkdir(parents=True, exist_ok=True)
        input_path = workdir / f"{request.name}.gjf"
        input_path.write_text(request.input_text, encoding="utf-8")
        input_hash = self.hash_text(request.input_text)
        (workdir / "job.meta").write_text(
            f"engine={self.name}\\nversion={self.version()}\\ninput_hash={input_hash}\\nmethod={request.method}\\n",
            encoding="utf-8",
        )
        argv = [self._executable, str(input_path), *request.extra_args]
        return PreparedJob(
            workdir=workdir, input_path=input_path, argv=argv,
            input_hash=input_hash, engine_version=self.version()
        )

    def parse(self, prepared: PreparedJob) -> dict:
        log = prepared.workdir / "run.log"
        if not log.exists():
            alt = prepared.input_path.with_suffix(".log")
            log = alt if alt.exists() else log
        if not log.exists():
            return {"ok": False, "reason": "无输出日志"}
        text = log.read_text(encoding="utf-8", errors="replace")
        energies = re.findall(r"SCF Done:\\s+E\\([^)]+\\)\\s*=\\s*(-?\\d+\\.\\d+)", text)
        converged = "Normal termination of Gaussian" in text
        return {
            "ok": converged,
            "final_energy_hartree": float(energies[-1]) if energies else None,
            "converged": converged,
            "input_hash": prepared.input_hash,
        }
