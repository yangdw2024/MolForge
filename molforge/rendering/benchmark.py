"""
rendering/benchmark.py - 渲染性能基准
=========================================
测量 FPS、帧时间、首帧时间、选择延迟等。

验收门槛：
  - 1000 原子场景：60 FPS（Studio 模式）
  - 选择延迟 P95：< 50ms
  - 缩放延迟 P95：< 100ms
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkResult:
    """性能基准结果。"""
    n_atoms: int = 0
    n_bonds: int = 0
    preset: str = "Studio"
    fps: float = 0.0
    frame_time_ms: float = 0.0
    first_frame_ms: float = 0.0
    selection_p95_ms: float = 0.0
    zoom_p95_ms: float = 0.0
    cpu_bottleneck: bool = False
    gpu_bottleneck: bool = False
    io_bottleneck: bool = False


class PerformanceBenchmark:
    """
    性能基准测试器。

    用法：
        bench = PerformanceBenchmark()
        result = bench.run(backend, n_atoms=1000)
    """

    def __init__(self) -> None:
        self._frame_times: list[float] = []
        self._selection_times: list[float] = []
        self._zoom_times: list[float] = []

    def start_frame(self) -> float:
        """开始计时一帧。"""
        return time.perf_counter()

    def end_frame(self, start: float) -> float:
        """结束计时一帧，返回帧时间（ms）。"""
        elapsed = (time.perf_counter() - start) * 1000
        self._frame_times.append(elapsed)
        return elapsed

    def measure_selection(self, func: callable) -> float:
        """测量选择操作延迟。"""
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        self._selection_times.append(elapsed)
        return elapsed

    def measure_zoom(self, func: callable) -> float:
        """测量缩放操作延迟。"""
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        self._zoom_times.append(elapsed)
        return elapsed

    def p95(self, values: list[float]) -> float:
        """计算 P95 值。"""
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = int(len(sorted_v) * 0.95)
        return sorted_v[min(idx, len(sorted_v) - 1)]

    def get_result(self, n_atoms: int, n_bonds: int, preset: str) -> BenchmarkResult:
        """获取基准结果。"""
        avg_frame = sum(self._frame_times) / max(len(self._frame_times), 1)
        fps = 1000 / avg_frame if avg_frame > 0 else 0

        # 判断瓶颈
        cpu_bottleneck = avg_frame > 16.6  # > 60fps 帧时间
        gpu_bottleneck = False  # TODO: 用 GPU 时间查询
        io_bottleneck = False

        return BenchmarkResult(
            n_atoms=n_atoms,
            n_bonds=n_bonds,
            preset=preset,
            fps=fps,
            frame_time_ms=avg_frame,
            selection_p95_ms=self.p95(self._selection_times),
            zoom_p95_ms=self.p95(self._zoom_times),
            cpu_bottleneck=cpu_bottleneck,
            gpu_bottleneck=gpu_bottleneck,
            io_bottleneck=io_bottleneck,
        )

    def reset(self) -> None:
        """重置基准数据。"""
        self._frame_times.clear()
        self._selection_times.clear()
        self._zoom_times.clear()

    def check_threshold(self, result: BenchmarkResult) -> list[str]:
        """检查是否达到性能门槛，返回警告列表。"""
        warnings = []
        if result.fps < 60 and result.n_atoms <= 1000:
            warnings.append(f"FPS 过低：{result.fps:.1f} < 60（{result.n_atoms} 原子）")
        if result.selection_p95_ms > 50:
            warnings.append(f"选择延迟 P95 过高：{result.selection_p95_ms:.1f}ms > 50ms")
        if result.zoom_p95_ms > 100:
            warnings.append(f"缩放延迟 P95 过高：{result.zoom_p95_ms:.1f}ms > 100ms")
        return warnings
