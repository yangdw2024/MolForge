"""
calculators/orca_engine.py - ORCA 受控引擎
==========================================
把 ORCA 作为本机实际可安装引擎：
  probe   检测 orca.exe
  prepare 写 .inp 输入、构造 argv（orca.exe input.inp）、算输入哈希
  parse   从输出日志提取最终能量、收敛状态
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .base import CalculationEngine, JobRequest, PreparedJob, EngineNotFound

_DEFAULT_ORCA = r"E:\ORCA\software\ORCA6.1.1\orca.exe"
_DEFAULT_MSMPI_BIN = r"D:\Microsoft_MPI\Bin"


def find_mpiexec() -> str | None:
    """探测本机可用的 MS-MPI / OpenMPI mpiexec 可执行文件。"""
    found = shutil.which("mpiexec") or shutil.which("mpiexec.exe")
    if found:
        return found
    cand = Path(_DEFAULT_MSMPI_BIN) / "mpiexec.exe"
    return str(cand) if cand.is_file() else None


class OrcaEngine(CalculationEngine):
    name = "ORCA"

    def __init__(self, executable: str | None = None) -> None:
        super().__init__(executable or _DEFAULT_ORCA)

    def probe(self) -> bool:
        return bool(self._executable) and Path(self._executable).is_file()

    def has_mpi(self) -> bool:
        return find_mpiexec() is not None

    def mpi_env(self) -> dict[str, str]:
        """返回包含 mpiexec 所在目录的环境变量副本，供并行 ORCA 子进程使用。"""
        env = os.environ.copy()
        mpi = find_mpiexec()
        if mpi:
            mpi_dir = str(Path(mpi).parent)
            cur_path = env.get("PATH", "")
            if mpi_dir.lower() not in cur_path.lower():
                env["PATH"] = f"{mpi_dir}{os.pathsep}{cur_path}" if cur_path else mpi_dir
        return env

    def version(self) -> str:
        # ORCA 版本从目录名推断；实际版本可在运行输出里取
        return Path(self._executable).parent.name or "unknown"

    def prepare(self, request: JobRequest, workdir: Path) -> PreparedJob:
        if not self.probe():
            raise EngineNotFound(
                "未找到 ORCA（orca.exe）。请安装 ORCA 或在设置中指定路径。")
        workdir.mkdir(parents=True, exist_ok=True)
        input_path = workdir / f"{request.name}.inp"
        input_path.write_text(request.input_text, encoding="utf-8")

        input_hash = self.hash_text(request.input_text)
        # 记录参数与版本，便于复现
        (workdir / "job.meta").write_text(
            f"engine={self.name}\nversion={self.version()}\n"
            f"input_hash={input_hash}\nmethod={request.method}\n",
            encoding="utf-8")

        argv = [self._executable, str(input_path), *request.extra_args]
        return PreparedJob(
            workdir=workdir, input_path=input_path, argv=argv,
            input_hash=input_hash, engine_version=self.version())

    def parse(self, prepared: PreparedJob) -> dict:
        log = prepared.workdir / "run.log"
        if not log.exists():
            return {"ok": False, "reason": "无输出日志"}
        text = log.read_text(encoding="utf-8", errors="replace")

        energies = re.findall(
            r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
        converged = "ORCA TERMINATED NORMALLY" in text
        return {
            "ok": converged,
            "final_energy_hartree": float(energies[-1]) if energies else None,
            "converged": converged,
            "input_hash": prepared.input_hash,
        }
