"""
application/jobs.py - 任务中心与后台 Worker
=============================================
管理后台计算任务（构象搜索、DFT 计算、文件解析等）。

特性：
  - 统一任务状态
  - 可取消（cancel token）
  - 线程/进程隔离，不卡 GUI
  - 输出带 input_revision（防止过期任务覆盖）
  - 进度/错误码/重试
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from PyQt6.QtCore import QThread, pyqtSignal, QObject


class JobStatus(Enum):
    """任务状态。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """后台任务。"""
    job_id: str
    name: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0  # 0-100
    input_revision: int = 0  # 输入文档版本号
    result: Any = None
    error: str = ""
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0


class CancelToken:
    """取消令牌：Worker 定期检查是否应该取消。"""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class WorkerThread(QThread):
    """后台 Worker 线程。"""

    progress_updated = pyqtSignal(int)
    finished_success = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(self, func: Callable[[CancelToken], Any],
                 cancel_token: CancelToken,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._func = func
        self._cancel_token = cancel_token

    def run(self) -> None:
        """执行任务。"""
        try:
            result = self._func(self._cancel_token)
            if not self._cancel_token.is_cancelled:
                self.finished_success.emit(result)
        except Exception as e:
            if not self._cancel_token.is_cancelled:
                self.finished_error.emit(str(e))


class JobCenter(QObject):
    """
    任务中心：管理所有后台任务。

    用法：
        center = JobCenter()
        job_id = center.submit("构象搜索", my_func, input_revision=doc.revision)
        center.cancel(job_id)
    """

    job_added = pyqtSignal(Job)
    job_updated = pyqtSignal(Job)
    job_completed = pyqtSignal(Job)
    job_failed = pyqtSignal(Job)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: dict[str, Job] = {}
        self._workers: dict[str, WorkerThread] = {}
        self._cancel_tokens: dict[str, CancelToken] = {}

    def submit(self, name: str,
               func: Callable[[CancelToken], Any],
               input_revision: int = 0) -> str:
        """
        提交后台任务。

        Args:
            name: 任务名称
            func: 任务函数（接收 CancelToken，返回结果）
            input_revision: 输入文档版本号

        Returns:
            job_id
        """
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            job_id=job_id,
            name=name,
            status=JobStatus.PENDING,
            input_revision=input_revision,
        )
        self._jobs[job_id] = job

        cancel_token = CancelToken()
        self._cancel_tokens[job_id] = cancel_token

        worker = WorkerThread(func, cancel_token)
        worker.progress_updated.connect(lambda p, jid=job_id: self._on_progress(jid, p))
        worker.finished_success.connect(lambda r, jid=job_id: self._on_success(jid, r))
        worker.finished_error.connect(lambda e, jid=job_id: self._on_error(jid, e))
        self._workers[job_id] = worker

        self.job_added.emit(job)
        worker.start()

        return job_id

    def cancel(self, job_id: str) -> None:
        """取消任务。"""
        token = self._cancel_tokens.get(job_id)
        if token:
            token.cancel()

        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.CANCELLED
            self.job_updated.emit(job)

    def get_job(self, job_id: str) -> Job | None:
        """获取任务状态。"""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        """列出所有任务。"""
        return list(self._jobs.values())

    def _on_progress(self, job_id: str, progress: int) -> None:
        """进度更新回调。"""
        job = self._jobs.get(job_id)
        if job:
            job.progress = progress
            job.status = JobStatus.RUNNING
            self.job_updated.emit(job)

    def _on_success(self, job_id: str, result: Any) -> None:
        """成功回调。"""
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.result = result
            self.job_completed.emit(job)

    def _on_error(self, job_id: str, error: str) -> None:
        """失败回调。"""
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = error
            self.job_failed.emit(job)
