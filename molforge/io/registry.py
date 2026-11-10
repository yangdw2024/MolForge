"""
registry.py - 格式注册表
=========================
每个 reader/writer 是一个 FormatHandler 子类，用 @register 装饰器注册。
UI 打开/保存文件时，从注册表查扩展名找对应的 handler。

加新格式 = 写一个新类加 @register，不动主流程。

设计：读和写分开映射，同一个扩展名可以有独立的 reader 和 writer。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.molecule import Molecule


class FormatHandler(ABC):
    """格式处理器抽象基类。"""

    # 子类必须定义
    name: str = ""                # 格式名，例如 'Gaussian Log'
    extensions: list[str] = []    # 支持的扩展名，例如 ['.log', '.out']
    description: str = ""         # 文件对话框里显示的描述

    # 子类声明自己能读/能写
    can_read: bool = False
    can_write: bool = False

    def read(self, path: Path) -> Molecule:
        """从文件读一个 Molecule。"""
        raise NotImplementedError(f"{self.name} 不支持读取")

    def write(self, mol: Molecule, path: Path) -> None:
        """把 Molecule 写到文件。"""
        raise NotImplementedError(f"{self.name} 不支持写入")


# 注册表：所有 handler 列表
_REGISTRY: list[FormatHandler] = []

# 读/写分开的扩展名映射
_READ_MAP: dict[str, FormatHandler] = {}
_WRITE_MAP: dict[str, FormatHandler] = {}

# 向后兼容：保留 _EXT_MAP（OpenBabel handler 用来检查去重）
# 现在指向 _READ_MAP，主要用于"该扩展名是否已有专门 reader"的检查
_EXT_MAP: dict[str, FormatHandler] = _READ_MAP


def register(handler_cls: type[FormatHandler]) -> type[FormatHandler]:
    """类装饰器：把一个 FormatHandler 子类注册进去。"""
    instance = handler_cls()
    _REGISTRY.append(instance)
    for ext in instance.extensions:
        ext_lower = ext.lower()
        if instance.can_read:
            _READ_MAP[ext_lower] = instance
        if instance.can_write:
            _WRITE_MAP[ext_lower] = instance
    return handler_cls


def get_reader_for_ext(ext: str) -> FormatHandler | None:
    """按扩展名找读 handler（不区分大小写）。"""
    return _READ_MAP.get(ext.lower())


def get_writer_for_ext(ext: str) -> FormatHandler | None:
    """按扩展名找写 handler（不区分大小写）。"""
    return _WRITE_MAP.get(ext.lower())


def get_handler_for_ext(ext: str) -> FormatHandler | None:
    """
    按扩展名找 handler（兼容旧接口）。
    优先返回 reader，没有再返回 writer。
    """
    return get_reader_for_ext(ext) or get_writer_for_ext(ext)


def supported_open_filters() -> str:
    """
    生成文件对话框的打开过滤器字符串。
    例如: "MOL/SDF (*.mol *.sdf);;Gaussian Log (*.log *.out);;所有文件 (*.*)"
    """
    parts = []
    for h in _REGISTRY:
        if not h.can_read:
            continue
        exts = " ".join(f"*{e}" for e in h.extensions)
        parts.append(f"{h.description or h.name} ({exts})")
    parts.append("所有文件 (*.*)")
    return ";;".join(parts)


def supported_save_filters() -> str:
    """生成保存对话框的过滤器。"""
    parts = []
    for h in _REGISTRY:
        if not h.can_write:
            continue
        exts = " ".join(f"*{e}" for e in h.extensions)
        parts.append(f"{h.description or h.name} ({exts})")
    return ";;".join(parts)


def read_file(path: Path) -> Molecule:
    """
    统一读文件入口。按扩展名找 reader handler。
    找不到就抛 ValueError。
    """
    ext = path.suffix.lower()
    handler = get_reader_for_ext(ext)
    if handler is None:
        raise ValueError(f"不支持的文件格式: {ext}（文件 {path.name}）")
    return handler.read(path)


def write_file(mol: Molecule, path: Path) -> None:
    """统一写文件入口。按扩展名找 writer handler。"""
    ext = path.suffix.lower()
    handler = get_writer_for_ext(ext)
    if handler is None:
        raise ValueError(f"不支持的文件格式: {ext}")
    handler.write(mol, path)
