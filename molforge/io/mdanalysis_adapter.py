"""
io/mdanalysis_adapter.py - MDAnalysis 轨迹播放与缓存
=====================================================
加载拓扑 + 轨迹（XTC/DCD/TRR），提供：
  - 原子数 / 帧数 / 时间单位（ps）/ 播放节拍
  - 错序轨迹拒绝（时间戳必须单调递增）
  - chunk LRU 缓存 + 后台线程异步预取（不冻结主线程）
  - 切帧坐标（numpy，单位 Å）

不复制分子真相源，只读取轨迹并产出坐标帧。
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np


class TrajectoryError(ValueError):
    """轨迹无法可靠读取（错序、原子数不一致等）。"""


class TrajectoryAdapter:
    """MDAnalysis 轨迹适配器。"""

    def __init__(
        self,
        topology: str | Path,
        trajectory: str | Path,
        chunk_size: int = 10,
        max_chunks: int = 6,
    ) -> None:
        import MDAnalysis as mda

        self.topology = str(topology)
        self.trajectory = str(trajectory)
        self.u = mda.Universe(self.topology, self.trajectory)

        self.n_atoms: int = len(self.u.atoms)
        self.n_frames: int = len(self.u.trajectory)
        self.dt_ps: float = float(self.u.trajectory.dt)        # 帧间隔（ps）
        self.total_time_ps: float = float(self.u.trajectory.totaltime)

        # 元素（若拓扑提供，否则用原子名推断）
        try:
            self.elements = list(self.u.atoms.elements)
        except Exception:
            self.elements = self._guess_elements()

        # chunk LRU
        self._chunk_size = max(1, int(chunk_size))
        self._max_chunks = max(1, int(max_chunks))
        self._chunks: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()
        self._prefetch_thread: threading.Thread | None = None

        self._validate()

    # ---------- 校验 ----------

    def _validate(self) -> None:
        """检查原子数一致与时间戳单调（错序拒绝）。"""
        prev_time = None
        for i, ts in enumerate(self.u.trajectory):
            if ts.n_atoms != self.n_atoms:
                raise TrajectoryError(
                    f"第 {i} 帧原子数 {ts.n_atoms} 与拓扑 {self.n_atoms} 不一致")
            t = float(ts.time)
            if prev_time is not None and t < prev_time - 1e-9:
                raise TrajectoryError(
                    f"轨迹时间戳错序：第 {i-1} 帧 {prev_time} ps > 第 {i} 帧 {t} ps")
            prev_time = t
        # 校验后回到第 0 帧
        self.u.trajectory[0]

    def _guess_elements(self) -> list[str]:
        out = []
        for name in self.u.atoms.names:
            s = "".join(c for c in str(name) if c.isalpha())
            out.append(s[:2].capitalize() if s else "X")
        return out

    # ---------- chunk 缓存 ----------

    def _chunk_index(self, frame: int) -> int:
        return frame // self._chunk_size

    def _load_chunk(self, chunk: int) -> np.ndarray:
        """加载一个 chunk 的全部帧坐标，返回 (chunk_len, n_atoms, 3)。"""
        start = chunk * self._chunk_size
        end = min(start + self._chunk_size, self.n_frames)
        data = np.empty((end - start, self.n_atoms, 3), dtype=np.float32)
        for j, fi in enumerate(range(start, end)):
            self.u.trajectory[fi]
            data[j] = self.u.trajectory.ts.positions
        return data

    def get_frame(self, frame: int) -> np.ndarray:
        """获取某帧坐标 (n_atoms, 3)，单位 Å，带 LRU。线程安全。"""
        if not 0 <= frame < self.n_frames:
            raise IndexError(f"帧 {frame} 越界（共 {self.n_frames} 帧）")
        chunk = self._chunk_index(frame)
        with self._lock:
            if chunk in self._chunks:
                self._chunks.move_to_end(chunk)
                data = self._chunks[chunk]
            else:
                data = self._load_chunk(chunk)
                self._chunks[chunk] = data
                while len(self._chunks) > self._max_chunks:
                    self._chunks.popitem(last=False)
        offset = frame - chunk * self._chunk_size
        return data[offset]

    # ---------- 异步预取 ----------

    def prefetch_async(self, frames: list[int]) -> None:
        """后台线程预取指定帧所在的 chunk，不阻塞主线程。"""
        needed = sorted({self._chunk_index(f) for f in frames})
        with self._lock:
            missing = [c for c in needed if c not in self._chunks]
        if not missing:
            return
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return
        self._prefetch_thread = threading.Thread(
            target=self._prefetch_worker, args=(missing,), daemon=True)
        self._prefetch_thread.start()

    def _prefetch_worker(self, chunks: list[int]) -> None:
        for c in chunks:
            with self._lock:
                if c in self._chunks:
                    self._chunks.move_to_end(c)
                    continue
                # 在锁内调用 _load_chunk(c)，防止后台预取线程与主线程同时修改同一个 MDAnalysis Universe 游标
                data = self._load_chunk(c)
                self._chunks[c] = data
                while len(self._chunks) > self._max_chunks:
                    self._chunks.popitem(last=False)

    def wait_prefetch(self, timeout: float | None = None) -> None:
        if self._prefetch_thread:
            self._prefetch_thread.join(timeout)

    # ---------- 播放节拍 ----------

    def frame_time_ps(self, frame: int) -> float:
        return frame * self.dt_ps

    def cached_chunk_count(self) -> int:
        with self._lock:
            return len(self._chunks)
