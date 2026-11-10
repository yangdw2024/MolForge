"""引擎注册表：统一管理 ORCA / Gaussian / REST (Rust-based Electronic Structure Toolkit) 引擎。"""
from __future__ import annotations

from .base import CalculationEngine, EngineNotFound
from .orca_engine import OrcaEngine
from .gaussian_engine import GaussianEngine
from .rest_engine import RestEngine
from .calchem_engine import CalChemEngine


def _all_engines() -> list[CalculationEngine]:
    return [CalChemEngine(), OrcaEngine(), GaussianEngine(), RestEngine()]


def available_engines() -> list[CalculationEngine]:
    """返回本机 probe 成功的引擎。"""
    return [e for e in _all_engines() if e.probe()]


def get_engine(name: str) -> CalculationEngine:
    """按名称获取引擎；未安装时抛 EngineNotFound 并给出明确提示。"""
    for e in _all_engines():
        if e.name.lower() == name.lower():
            if e.probe():
                return e
            raise EngineNotFound(
                f"{name} 未安装或不可执行。请安装 {name} 或在计算面板生成输入卡文件。"
            )
    raise EngineNotFound(f"不支持的引擎：{name}")
