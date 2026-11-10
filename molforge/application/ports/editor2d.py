"""
application/ports/editor2d.py - 2D 编辑器端口接口
===================================================
定义 2D 编辑器的统一接口，Ketcher 和自研 QPainter 版本都实现这个接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable
from ...domain.document import MoleculeDocument


class Editor2DPort(ABC):
    """
    2D 编辑器端口接口。

    所有 2D 编辑器实现（Ketcher、自研 QPainter）都必须实现这个接口。
    """

    @abstractmethod
    def load_document(self, doc: MoleculeDocument) -> None:
        """加载分子文档。"""
        pass

    @abstractmethod
    def get_document(self) -> MoleculeDocument:
        """获取当前分子文档。"""
        pass

    @abstractmethod
    def set_mode(self, mode: str) -> None:
        """设置编辑模式（select, atom, bond, erase...）。"""
        pass

    @abstractmethod
    def export_svg(self) -> str:
        """导出 SVG。"""
        pass

    @abstractmethod
    def export_png(self, width: int = 800, height: int = 600) -> bytes:
        """导出 PNG。"""
        pass

    @abstractmethod
    def cleanup_2d(self) -> None:
        """自动清理 2D 布局。"""
        pass

    @abstractmethod
    def to_3d(self) -> None:
        """生成 3D 结构。"""
        pass

    def on_structure_changed(self, callback: Callable[[MoleculeDocument], None]) -> None:
        """注册结构改变回调。"""
        self._on_changed = callback

    def _notify_changed(self, doc: MoleculeDocument) -> None:
        """通知结构改变。"""
        if hasattr(self, '_on_changed'):
            self._on_changed(doc)


class Editor2DFactory:
    """2D 编辑器工厂。"""

    _implementations: dict[str, type[Editor2DPort]] = {}

    @classmethod
    def register(cls, name: str, implementation: type[Editor2DPort]):
        """注册编辑器实现。"""
        cls._implementations[name] = implementation

    @classmethod
    def create(cls, name: str) -> Editor2DPort:
        """创建编辑器实例。"""
        if name not in cls._implementations:
            raise ValueError(f"未知的 2D 编辑器: {name}")
        return cls._implementations[name]()

    @classmethod
    def list_available(cls) -> list[str]:
        """列出可用的编辑器。"""
        return list(cls._implementations.keys())
