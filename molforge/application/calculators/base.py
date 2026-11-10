"""
calculators/base.py - 受控计算引擎抽象
======================================
统一外部计算程序（ORCA / xtb / Gaussian ...）的生命周期：
  probe   检测可执行是否存在（不抛异常，返回 bool）
  prepare 写输入文件、计算输入哈希，返回 PreparedJob
  run     用 argv（非 shell）启动子进程，限资源、可取消、记录日志
  parse   解析输出，返回结构化结果

所有外部调用都不经过 shell，避免命令注入；输入参数与源码哈希落盘，保证可复现。
"""
from __future__ import annotations

import abc
import hashlib
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path


class EngineNotFound(RuntimeError):
    """引擎未安装 / 可执行不存在。"""


@dataclass
class JobRequest:
    name: str
    input_text: str
    method: str = ""
    extra_args: list[str] = field(default_factory=list)


@dataclass
class PreparedJob:
    workdir: Path
    input_path: Path
    argv: list[str]
    input_hash: str
    engine_version: str


@dataclass
class JobResult:
    ok: bool
    return_code: int
    stdout_tail: str
    output_path: Path
    input_hash: str
    cancelled: bool = False


class CalculationEngine(abc.ABC):
    """计算引擎基类。"""

    name: str = "engine"

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable

    # ---- probe ----
    @abc.abstractmethod
    def probe(self) -> bool:
        """可执行是否存在。"""

    @abc.abstractmethod
    def version(self) -> str:
        """引擎版本（probe 成功后调用）。"""

    # ---- prepare ----
    @abc.abstractmethod
    def prepare(self, request: JobRequest, workdir: Path) -> PreparedJob:
        """写输入、构造 argv、计算输入哈希。"""

    # ---- run（通用，子类一般无需重写）----
    def run(
        self,
        prepared: PreparedJob,
        timeout: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> JobResult:
        """以 argv 启动子进程（非 shell），可取消，记录输出。"""
        if not self.probe():
            raise EngineNotFound(f"{self.name} 未安装或可执行不存在")

        workdir = prepared.workdir
        log_path = workdir / "run.log"
        proc = subprocess.Popen(
            prepared.argv,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,           # 关键：不走 shell
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # 取消：轮询 cancel_event，终止进程
        def _watch():
            if cancel_event is None:
                return
            while proc.poll() is None:
                if cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return
                cancel_event.wait(0.2)

        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()

        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            return JobResult(
                ok=False, return_code=-1, stdout_tail=out[-2000:],
                output_path=log_path, input_hash=prepared.input_hash,
                cancelled=False)

        log_path.write_text(out or "", encoding="utf-8")
        cancelled = bool(cancel_event and cancel_event.is_set())
        return JobResult(
            ok=(proc.returncode == 0 and not cancelled),
            return_code=proc.returncode,
            stdout_tail=(out or "")[-2000:],
            output_path=log_path,
            input_hash=prepared.input_hash,
            cancelled=cancelled)

    # ---- parse ----
    @abc.abstractmethod
    def parse(self, prepared: PreparedJob) -> dict:
        """解析输出文件，返回结构化结果字典。"""

    # ---- 工具 ----
    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
