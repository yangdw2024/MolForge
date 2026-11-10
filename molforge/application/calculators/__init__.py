"""受控计算引擎适配器：probe / prepare / run / parse，统一管理外部科学计算程序。"""
from .base import (
    CalculationEngine, JobRequest, PreparedJob, JobResult, EngineNotFound)
from .orca_engine import OrcaEngine
from .registry import available_engines, get_engine

__all__ = [
    "CalculationEngine", "JobRequest", "PreparedJob", "JobResult",
    "EngineNotFound", "OrcaEngine", "available_engines", "get_engine",
]
