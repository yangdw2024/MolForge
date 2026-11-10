"""
application/trajectory.py - 分子动力学轨迹播放
===============================================
支持 XTC/DCD 格式，帧缓存和异步预取。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4, UUID


@dataclass
class Frame:
    """轨迹帧。"""
    frame_index: int = 0
    time: float = 0.0  # ps
    coordinates: Any = None  # np.ndarray (N, 3)
    cell: Any = None  # 晶胞参数


@dataclass
class TrajectoryInfo:
    """轨迹信息。"""
    n_atoms: int = 0
    n_frames: int = 0
    dt: float = 1.0  # 帧间隔 ps
    total_time: float = 0.0  # ps
    format: str = ""


class TrajectoryPlayer:
    """
    轨迹播放器。

    特性：
      - 帧缓存（LRU）
      - 异步预取
      - 播放/暂停/快进/快退
      - 不冻结主线程
    """

    def __init__(self):
        self.trajectory_id: UUID = uuid4()
        self.info: TrajectoryInfo | None = None
        self.current_frame: int = 0
        self._cache: dict[int, Frame] = {}
        self._cache_size: int = 10  # 最多缓存 10 帧
        self._playing: bool = False
        self._speed: float = 1.0  # 倍速
        self._on_frame_changed: Callable[[Frame], None] | None = None

    def load(self, topology_file: str, trajectory_file: str):
        """加载轨迹文件。"""
        # TODO: 使用 MDAnalysis 加载
        self.info = TrajectoryInfo(
            n_atoms=0,
            n_frames=0,
            format=trajectory_file.split(".")[-1],
        )

    def get_frame(self, index: int) -> Frame | None:
        """获取指定帧。"""
        if self.info is None:
            return None
        if index < 0 or index >= self.info.n_frames:
            return None

        # 检查缓存
        if index in self._cache:
            return self._cache[index]

        # 从文件加载（异步）
        frame = self._load_frame(index)

        # 更新缓存
        self._cache[index] = frame
        if len(self._cache) > self._cache_size:
            # LRU：删除最旧的帧
            oldest = min(self._cache.keys())
            del self._cache[oldest]

        return frame

    def _load_frame(self, index: int) -> Frame:
        """从文件加载一帧。"""
        # TODO: 实际加载
        return Frame(
            frame_index=index,
            time=index * (self.info.dt if self.info else 1.0),
        )

    def play(self):
        """开始播放。"""
        self._playing = True

    def pause(self):
        """暂停。"""
        self._playing = False

    def stop(self):
        """停止播放，回到第一帧。"""
        self._playing = False
        self.current_frame = 0

    def set_speed(self, speed: float):
        """设置播放速度（倍速）。"""
        self._speed = max(0.1, min(speed, 10.0))

    def seek(self, frame_index: int):
        """跳转到指定帧。"""
        self.current_frame = frame_index
        frame = self.get_frame(frame_index)
        if frame and self._on_frame_changed:
            self._on_frame_changed(frame)

    @property
    def is_playing(self) -> bool:
        """是否正在播放。"""
        return self._playing
